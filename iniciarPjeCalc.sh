#!/bin/bash
# iniciarPjeCalc.sh — Equivalente Linux do iniciarPjeCalc.bat
# Inicia o servidor Tomcat embarcado do PJE-Calc Cidadão em Linux/Docker
#
# Uso: bash /opt/pjecalc/iniciarPjeCalc.sh
# Requer: Java 8+ instalado no sistema (OpenJDK 8 ou 11)

# Não usar set -e aqui: erros no xdotool/fluxbox não devem abortar o script
set +e

# Localização do PJE-Calc (pode ser sobrescrita via env)
PJECALC_DIR="${PJECALC_DIR:-$(dirname "$(readlink -f "$0")")}"

cd "$PJECALC_DIR"

# Verifica Java disponível
if ! command -v java &> /dev/null; then
    echo "[PJE-Calc] ERRO: Java não encontrado. Instale OpenJDK 8 ou superior." >&2
    exit 1
fi

JAVA_VERSION=$(java -version 2>&1 | head -1)
echo "[PJE-Calc] Java: $JAVA_VERSION"
echo "[PJE-Calc] Diretório: $PJECALC_DIR"
echo "[PJE-Calc] Iniciando Tomcat na porta 9257..."

# ── Limpar resíduos de execução anterior ────────────────────────────────────
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
# Matar instância Java anterior se existir (evita "porta 9257 já em uso")
if [ -f /tmp/pjecalc.pid ]; then
    OLD_PID=$(cat /tmp/pjecalc.pid)
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[PJE-Calc] Encerrando instância anterior (PID: $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi
    rm -f /tmp/pjecalc.pid
fi

# ── Iniciar Xvfb (display virtual) ─────────────────────────────────────────
if command -v Xvfb &>/dev/null; then
    echo "[PJE-Calc] Iniciando Xvfb (display virtual :99)..."
    Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
    XVFB_PID=$!
    export DISPLAY=:99
    # Aguardar Xvfb ficar pronto — getmouselocation retorna 0 assim que X aceita conexões
    for i in $(seq 1 20); do
        if DISPLAY=:99 xdotool getmouselocation &>/dev/null 2>&1; then
            echo "[PJE-Calc] Xvfb pronto após ${i}s."
            break
        fi
        sleep 1
    done
    echo "[PJE-Calc] Xvfb iniciado (PID: $XVFB_PID)."
else
    echo "[PJE-Calc] Xvfb não encontrado — tentando sem display virtual..."
fi

# ── Iniciar gerenciador de janelas (necessário para xdotool focus) ──────────
if command -v fluxbox &>/dev/null; then
    echo "[PJE-Calc] Iniciando fluxbox (window manager)..."
    DISPLAY=:99 fluxbox &>/dev/null &
    sleep 1
elif command -v openbox &>/dev/null; then
    echo "[PJE-Calc] Iniciando openbox (window manager)..."
    DISPLAY=:99 openbox &>/dev/null &
    sleep 1
else
    echo "[PJE-Calc] Nenhum window manager encontrado — continuando sem ele."
fi

# ── Auto-dismiss de dialogs Swing do Lancador ───────────────────────────────
# Estratégia: busca APENAS janelas de dialog (não a janela principal "PjeCalc")
# Os dialogs do Lancador têm títulos: "Erro", "Confirmação"
# A janela principal do Lancador tem título: "PjeCalc"
if command -v xdotool &>/dev/null; then
    echo "[PJE-Calc] Iniciando auto-dismiss de dialogs Swing..."
    (
        # Aguarda Java iniciar (~3s) e dialog aparecer (~2s adicional)
        sleep 5
        for i in $(seq 1 120); do
            # Buscar janelas com títulos conhecidos dos dialogs do Lancador
            for DIALOG_TITLE in "Erro" "Confirmação" "Confirmacao" "Aviso" "Error" "Warning"; do
                WIDS=$(DISPLAY=:99 xdotool search --onlyvisible --name "$DIALOG_TITLE" 2>/dev/null || true)
                if [ -n "$WIDS" ]; then
                    for WID in $WIDS; do
                        echo "[PJE-Calc] Dialog '$DIALOG_TITLE' encontrado (WID: $WID) — dispensando..."
                        DISPLAY=:99 xdotool windowfocus --sync "$WID" 2>/dev/null || true
                        sleep 0.2
                        # Pressionar Enter (ativa botão padrão: Sim/OK)
                        DISPLAY=:99 xdotool key --window "$WID" --clearmodifiers Return 2>/dev/null || true
                        sleep 0.2
                        # Clicar no centro-inferior da janela (onde ficam os botões)
                        GEOM=$(DISPLAY=:99 xdotool getwindowgeometry "$WID" 2>/dev/null || true)
                        W=$(echo "$GEOM" | grep -oP 'Geometry: \K[0-9]+' | head -1)
                        H=$(echo "$GEOM" | grep -oP 'Geometry: [0-9]+x\K[0-9]+' | head -1)
                        if [ -n "$W" ] && [ -n "$H" ]; then
                            CX=$((W / 2))
                            CY=$((H * 3 / 4))
                            DISPLAY=:99 xdotool mousemove --window "$WID" "$CX" "$CY" 2>/dev/null || true
                            DISPLAY=:99 xdotool click --window "$WID" 1 2>/dev/null || true
                        fi
                    done
                fi
            done
            sleep 1
        done
    ) &
else
    echo "[PJE-Calc] xdotool não encontrado — dialogs não serão auto-dismissados."
fi

# ── Java Agent (dialog suppressor) ─────────────────────────────────────────
AGENT_FLAG=""
if [ -f /opt/dialog-suppressor.jar ]; then
    AGENT_FLAG="-javaagent:/opt/dialog-suppressor.jar"
    echo "[PJE-Calc] Java Agent carregado: dialog-suppressor.jar"
else
    echo "[PJE-Calc] AVISO: dialog-suppressor.jar não encontrado em /opt/"
fi

# ── Iniciar PJE-Calc ─────────────────────────────────────────────────────────
# Propriedades Java comuns a todas as estratégias de inicialização:
#   -Dfile.encoding=ISO-8859-1  → preserva encoding original do PJE-Calc
#   -Duser.timezone=GMT-3       → fuso horário Brasil (Brasília)
#   -Xms256m -Xmx2048m           → heap 2GB (VM com 6GB RAM)
#   -XX:+UseG1GC               → GC moderno para heaps > 1GB
#   -XX:MaxPermSize=512m        → apenas Java 8 (ignorado no 11+)
#   -Djava.awt.headless=true    → sem GUI Swing → sem JOptionPane bloqueante
JAVA_BASE_OPTS="$AGENT_FLAG
    -Duser.timezone=GMT-3
    -Dfile.encoding=ISO-8859-1
    -Dseguranca.pjecalc.tokenServicos=pW4jZ4g9VM5MCy6FnB5pEfQe
    -Dseguranca.pjekz.servico.contexto=https://pje.trt8.jus.br/pje-seguranca
    -Xms256m
    -Xmx2048m
    -XX:MaxPermSize=512m
    -XX:+UseG1GC
    -XX:+HeapDumpOnOutOfMemoryError
    -XX:HeapDumpPath=/opt/pjecalc/java_heapdump.hprof
    -XX:+ExitOnOutOfMemoryError"

_iniciar_java() {
    # Abordagem A — Bootstrap direto (bypassa Lancador.java e seus JOptionPane)
    # O Tomcat é iniciado diretamente via org.apache.catalina.startup.Bootstrap,
    # sem passar pelo Lancador que exibe diálogos GUI bloqueantes.
    # -Djava.awt.headless=true desativa AWT inteiramente (sem necessidade de Xvfb).
    CLASSPATH="$PJECALC_DIR/bin/pjecalc.jar"
    for jar in "$PJECALC_DIR/bin/lib/"*.jar; do
        [ -f "$jar" ] && CLASSPATH="$CLASSPATH:$jar"
    done
    TOMCAT_CONF="$PJECALC_DIR/tomcat/conf/server.xml"

    if [ -f "$TOMCAT_CONF" ]; then
        echo "[PJE-Calc] Iniciando via Bootstrap direto (bypassa Lancador)..."
        # -Dcatalina.home e -Dcatalina.base são OBRIGATÓRIOS: o Bootstrap precisa desses
        # system properties para localizar webapps/, conf/server.xml e libs do Tomcat.
        # Sem eles o Tomcat sobe (porta ligada) mas nunca faz deploy da webapp → 404 eterno.
        # -Dcaminho.instalacao é o mesmo path que o Lancador.java passa para TomCat.setCatalinaHome().
        DISPLAY=:99 java $JAVA_BASE_OPTS \
            -Djava.awt.headless=true \
            -Dcatalina.home="$PJECALC_DIR/tomcat" \
            -Dcatalina.base="$PJECALC_DIR/tomcat" \
            -Dcaminho.instalacao="$PJECALC_DIR" \
            -cp "$CLASSPATH" \
            org.apache.catalina.startup.Bootstrap start \
            >> /opt/pjecalc/java.log 2>&1 &
        echo $! > /tmp/pjecalc.pid
        echo "[PJE-Calc] Bootstrap iniciado (PID: $(cat /tmp/pjecalc.pid))"
        return 0
    fi

    # Abordagem B — java -jar (Lancador completo) — fallback quando server.xml ausente
    # Usa Xvfb + xdotool (já iniciados acima) para dispensar diálogos Swing.
    echo "[PJE-Calc] server.xml não encontrado — usando java -jar pjecalc.jar (Lancador)..."
    DISPLAY=:99 java $JAVA_BASE_OPTS \
        -Djava.awt.headless=false \
        -jar bin/pjecalc.jar \
        >> /opt/pjecalc/java.log 2>&1 &
    echo $! > /tmp/pjecalc.pid
    echo "[PJE-Calc] Lancador iniciado (PID: $(cat /tmp/pjecalc.pid))"
}

# Restaurar template H2 se foi removido por limpar_h2_database()
# O template contém o schema Hibernate obrigatório — sem ele o contexto /pjecalc falha.
# Os dados de cálculos residuais são limpos pelo Python (limpar_h2_database → _limpar_calculos_h2).
H2_DB="$PJECALC_DIR/.dados/pjecalc.h2.db"
H2_TEMPLATE="$PJECALC_DIR/.dados/pjecalc.h2.db.template"
H2_JAR="$PJECALC_DIR/bin/lib/h2-1.3.154.jar"
if [ ! -f "$H2_DB" ] && [ -f "$H2_TEMPLATE" ]; then
    echo "[PJE-Calc] Restaurando template H2 (schema obrigatório)..."
    cp "$H2_TEMPLATE" "$H2_DB"
fi

# Limpar CÁLCULOS RESIDUAIS do template (.h2.db.template tem calcs embutidos como
# id=71 CARLOS ALBERTO 0001948-74, etc. que poluem a lista Recentes e fazem
# obterCalculoAberto() retornar calc errado no export). Executa DELETE
# diretamente via h2 RunScript antes do Tomcat subir. Tolerante a falha (se
# a tabela não existir, segue).
if [ -f "$H2_DB" ] && [ -f "$H2_JAR" ]; then
    echo "[PJE-Calc] Limpando cálculos residuais do H2 (CARLOS ALBERTO, FRANCISCO JOSE, etc.)..."
    # Credenciais confirmadas em webapps/pjecalc/META-INF/context.xml
    H2_URL="jdbc:h2:$PJECALC_DIR/.dados/pjecalc"
    H2_USER="pjecalc"
    H2_PASS="/pjecalc/"
    # Descobrir nomes das tabelas de INSTÂNCIA de cálculo via INFORMATION_SCHEMA.
    # ⚠ CUIDADO: o H2 contém também tabelas de CATÁLOGO (tipos de verba do Expresso,
    # tabelas de correção, etc.) que NÃO podem ser apagadas. Filtro restrito:
    # apenas CALCULO e tabelas dependentes que são criadas com id = FK para Calculo.
    # Tabelas de catálogo NÃO incluem 'CALCULO' como substring (ex: VERBA_PADRAO,
    # TIPO_VERBA, TABELA_JT_MENSAL, etc. — essas precisam ficar).
    CLEANUP_SQL="/tmp/pjecalc_cleanup.sql"
    DUMP_TABLES="/tmp/pjecalc_tables.txt"
    java -cp "$H2_JAR" org.h2.tools.Shell \
        -url "$H2_URL" -user "$H2_USER" -password "$H2_PASS" \
        -sql "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='PUBLIC' AND TABLE_NAME NOT LIKE 'HIBERNATE_%'" \
        > "$DUMP_TABLES" 2>&1 || true
    # Filtro CIRÚRGICO: apenas tabelas que contenham "CALCULO" no nome + PROCESSO
    # (que é 1:1 com CALCULO). NÃO incluir VERBA/HONORARIO/FGTS/etc. que podem ser
    # catálogos ou tabelas de configuração.
    {
        echo "SET REFERENTIAL_INTEGRITY FALSE;"
        grep -iE "^[A-Z_]*CALCULO[A-Z_]*\$|^PROCESSO\$|^OCORRENCIA_CALCULO|^AUX_CALCULO|^CALCULO_" "$DUMP_TABLES" 2>/dev/null | awk '{print "DELETE FROM " $1 ";"}' | head -50
        echo "SET REFERENTIAL_INTEGRITY TRUE;"
        echo "COMMIT;"
    } > "$CLEANUP_SQL"
    echo "[PJE-Calc] SQL cleanup gerado ($(wc -l < "$CLEANUP_SQL") stmts):"
    cat "$CLEANUP_SQL" | sed 's/^/  /'
    java -cp "$H2_JAR" org.h2.tools.RunScript \
        -url "$H2_URL" -user "$H2_USER" -password "$H2_PASS" \
        -script "$CLEANUP_SQL" 2>&1 | head -10 || true
    rm -f "$CLEANUP_SQL" "$DUMP_TABLES"
    echo "[PJE-Calc] Cleanup H2 concluído (preservando catálogos)."
fi

echo "[PJE-Calc] Iniciando processo Java (porta 9257)..."
_iniciar_java
echo "[PJE-Calc] Log: /opt/pjecalc/java.log"
echo "[PJE-Calc] Aguarde Tomcat finalizar deploy (~30-120s)..."

# ── Watchdog: reinicia Java se o processo morrer ─────────────────────────────
# Reinicia automaticamente usando a mesma estratégia (_iniciar_java),
# restaurando o Tomcat sem intervenção manual.
# Polling a cada 10s (rápido: detecta crash do Expresso em <15s).
# Suporta signal file /tmp/pjecalc_restart_request para restart sob demanda.
(
    PJE_PID=$(cat /tmp/pjecalc.pid 2>/dev/null || echo 0)
    echo "[Watchdog] Iniciado — monitora PID $PJE_PID a cada 10s (início em 60s)."
    sleep 60  # aguarda Tomcat inicializar antes de começar a vigiar
    while true; do
        sleep 10
        [ -f /tmp/pjecalc.pid ] || { echo "[Watchdog] PID file removido — encerrando."; break; }
        CURRENT_PID=$(cat /tmp/pjecalc.pid)

        # Signal file: Playwright solicita restart imediato
        if [ -f /tmp/pjecalc_restart_request ]; then
            echo "[Watchdog] Restart solicitado via signal file"
            rm -f /tmp/pjecalc_restart_request
            kill "$CURRENT_PID" 2>/dev/null || true
            sleep 5
            cd "$PJECALC_DIR"
            _iniciar_java
            NEW_PID=$(cat /tmp/pjecalc.pid)
            echo "[Watchdog] Reiniciado (signal) com PID $NEW_PID — aguardando 90s..."
            sleep 90
            continue
        fi

        if ! kill -0 "$CURRENT_PID" 2>/dev/null; then
            echo "[Watchdog] Processo Java (PID $CURRENT_PID) morreu — reiniciando..."
            cd "$PJECALC_DIR"
            _iniciar_java
            NEW_PID=$(cat /tmp/pjecalc.pid)
            echo "[Watchdog] Reiniciado com PID $NEW_PID — aguardando Tomcat (90s)..."
            sleep 90  # aguarda Tomcat subir antes do próximo ciclo
        fi
    done
) &
WATCHDOG_PID=$!
echo "[PJE-Calc] Watchdog iniciado (PID: $WATCHDOG_PID)"
