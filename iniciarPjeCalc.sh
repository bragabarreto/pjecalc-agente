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
    # Aguardar Xvfb ficar pronto (testar conexão)
    for i in $(seq 1 20); do
        if DISPLAY=:99 xdotool getactivewindow &>/dev/null 2>&1 || \
           DISPLAY=:99 xset q &>/dev/null 2>&1; then
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
# Notas:
#   -Dfile.encoding=ISO-8859-1  → preserva encoding original do PJE-Calc
#   -Duser.timezone=GMT-3       → fuso horário Brasil (Brasília)
#   -Xms128m -Xmx512m          → heap adequado para servidor
#   -XX:MaxPermSize=512m        → apenas Java 8 (ignorado no 11+)
#   -Djava.awt.headless=false   → AWT usa DISPLAY=:99 (Xvfb)
#   DISPLAY=:99                 → display virtual para Swing
echo "[PJE-Calc] Iniciando processo Java (porta 9257)..."
DISPLAY=:99 java \
    $AGENT_FLAG \
    -Djava.awt.headless=false \
    -Duser.timezone=GMT-3 \
    -Dfile.encoding=ISO-8859-1 \
    -Dseguranca.pjecalc.tokenServicos=pW4jZ4g9VM5MCy6FnB5pEfQe \
    "-Dseguranca.pjekz.servico.contexto=https://pje.trt8.jus.br/pje-seguranca" \
    -Xms128m \
    -Xmx512m \
    -XX:MaxPermSize=512m \
    -jar bin/pjecalc.jar \
    >> /opt/pjecalc/java.log 2>&1 &

PJE_PID=$!
echo "[PJE-Calc] Processo iniciado (PID: $PJE_PID)"
echo "[PJE-Calc] Log: /opt/pjecalc/java.log"
echo $PJE_PID > /tmp/pjecalc.pid
echo "[PJE-Calc] Aguarde Tomcat finalizar deploy (~30-120s)..."

# ── Watchdog: reinicia Java se o processo morrer ─────────────────────────────
# O Lancador.java pode morrer (SplashScreen ISE, OutOfMemory, etc.)
# enquanto o Tomcat ainda tinha threads ativas. O watchdog reinicia o Java
# automaticamente, restaurando o Tomcat sem intervenção manual.
(
    echo "[Watchdog] Iniciado — monitora PID $PJE_PID a cada 30s (início em 90s)."
    sleep 90  # aguarda Tomcat inicializar antes de começar a vigiar
    while true; do
        sleep 30
        [ -f /tmp/pjecalc.pid ] || { echo "[Watchdog] PID file removido — encerrando."; break; }
        CURRENT_PID=$(cat /tmp/pjecalc.pid)
        if ! kill -0 "$CURRENT_PID" 2>/dev/null; then
            echo "[Watchdog] Processo Java (PID $CURRENT_PID) morreu — reiniciando..."
            cd "$PJECALC_DIR"
            DISPLAY=:99 java \
                $AGENT_FLAG \
                -Djava.awt.headless=false \
                -Duser.timezone=GMT-3 \
                -Dfile.encoding=ISO-8859-1 \
                -Dseguranca.pjecalc.tokenServicos=pW4jZ4g9VM5MCy6FnB5pEfQe \
                "-Dseguranca.pjekz.servico.contexto=https://pje.trt8.jus.br/pje-seguranca" \
                -Xms128m \
                -Xmx512m \
                -XX:MaxPermSize=512m \
                -jar bin/pjecalc.jar \
                >> /opt/pjecalc/java.log 2>&1 &
            NEW_PID=$!
            echo $NEW_PID > /tmp/pjecalc.pid
            echo "[Watchdog] Reiniciado com PID $NEW_PID — aguardando Tomcat (120s)..."
            sleep 120  # aguarda Tomcat subir antes do próximo ciclo
        fi
    done
) &
WATCHDOG_PID=$!
echo "[PJE-Calc] Watchdog iniciado (PID: $WATCHDOG_PID)"
