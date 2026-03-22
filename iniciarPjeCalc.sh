#!/bin/bash
# iniciarPjeCalc.sh — Equivalente Linux do iniciarPjeCalc.bat
# Inicia o servidor Tomcat embarcado do PJE-Calc Cidadão em Linux/Docker
#
# Uso: bash /opt/pjecalc/iniciarPjeCalc.sh
# Requer: Java 8+ instalado no sistema (OpenJDK 8 ou 11)

set -e

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

# Inicia Xvfb (display virtual) para que os diálogos Swing do Lancador
# tenham um display X11 sem precisar de monitor físico.
# O Xvfb é instalado automaticamente pelo playwright install --with-deps.
if command -v Xvfb &>/dev/null; then
    echo "[PJE-Calc] Iniciando Xvfb (display virtual :99)..."
    # Limpar lock antigo (caso de restart do container)
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
    Xvfb :99 -screen 0 1024x768x16 -nolisten tcp &
    export DISPLAY=:99
    sleep 1
else
    echo "[PJE-Calc] Xvfb não encontrado — tentando sem display virtual..."
fi

# Auto-dismiss de dialogs Swing do Lancador (JOptionPane bloqueia o startup)
# Estratégia: busca explícita de janelas no Xvfb :99 e envia Enter/click
if command -v xdotool &>/dev/null; then
    echo "[PJE-Calc] Iniciando auto-dismiss de dialogs (xdotool com busca explícita)..."
    (
        sleep 4  # aguarda Java iniciar e dialog aparecer
        for i in $(seq 1 150); do
            # Buscar QUALQUER janela visível no display :99
            WIDS=$(DISPLAY=:99 xdotool search --onlyvisible --name "" 2>/dev/null || true)
            if [ -z "$WIDS" ]; then
                # Fallback: qualquer janela (inclusive ocultas)
                WIDS=$(DISPLAY=:99 xdotool search --name "" 2>/dev/null || true)
            fi
            if [ -n "$WIDS" ]; then
                for WID in $WIDS; do
                    # Focar e enviar Enter + Space + clique no centro
                    DISPLAY=:99 xdotool windowfocus --sync "$WID" 2>/dev/null || true
                    DISPLAY=:99 xdotool key --window "$WID" --clearmodifiers Return 2>/dev/null || true
                    DISPLAY=:99 xdotool key --window "$WID" --clearmodifiers space 2>/dev/null || true
                    # Também clicar no centro da janela (botão OK/Sim)
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
            sleep 1
        done
    ) &
else
    echo "[PJE-Calc] xdotool não encontrado — dialogs não serão auto-dismissados."
fi

# Inicia PJE-Calc em background
# Notas:
#   -Dfile.encoding=ISO-8859-1  → preserva encoding original do PJE-Calc
#   -Duser.timezone=GMT-3       → fuso horário Brasil (Brasília)
#   -Xms512m -Xmx1024m          → heap reduzido para ambiente servidor (original: 1024/2048)
#   -XX:MaxPermSize=512m        → apenas para Java 8 (ignorado no Java 11+)
java \
    -Duser.timezone=GMT-3 \
    -Dfile.encoding=ISO-8859-1 \
    -Dseguranca.pjecalc.tokenServicos=pW4jZ4g9VM5MCy6FnB5pEfQe \
    "-Dseguranca.pjekz.servico.contexto=https://pje.trtXX.jus.br/pje-seguranca" \
    -Xms128m \
    -Xmx512m \
    -XX:MaxPermSize=512m \
    -jar bin/pjecalc.jar \
    > /opt/pjecalc/java.log 2>&1 &

PJE_PID=$!
echo "[PJE-Calc] Processo iniciado (PID: $PJE_PID)"
echo "[PJE-Calc] Aguarde Tomcat finalizar deploy (~30-60s)..."
echo $PJE_PID > /tmp/pjecalc.pid
