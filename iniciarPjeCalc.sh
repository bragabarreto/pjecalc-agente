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
    # Iniciar window manager leve para gerenciar foco dos dialogs Java
    # Sem WM, xdotool key vai ao vácuo (nenhuma janela tem foco no Xvfb)
    if command -v matchbox-window-manager &>/dev/null; then
        echo "[PJE-Calc] Iniciando matchbox-window-manager..."
        DISPLAY=:99 matchbox-window-manager -use_titlebar no &
        sleep 1
    fi
else
    echo "[PJE-Calc] Xvfb não encontrado — tentando sem display virtual..."
fi

# Auto-dismiss de dialogs Swing do Lancador (JOptionPane bloqueia o startup)
# xdotool envia Enter a cada 2s por 120s no display Xvfb :99
if command -v xdotool &>/dev/null; then
    echo "[PJE-Calc] Iniciando auto-dismiss de dialogs (xdotool)..."
    (
        sleep 5  # aguarda o dialog aparecer
        for i in $(seq 1 60); do
            DISPLAY=:99 xdotool key --clearmodifiers Return 2>/dev/null || true
            DISPLAY=:99 xdotool key --clearmodifiers space  2>/dev/null || true
            sleep 2
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
    &

PJE_PID=$!
echo "[PJE-Calc] Processo iniciado (PID: $PJE_PID)"
echo "[PJE-Calc] Aguarde Tomcat finalizar deploy (~30-60s)..."
echo $PJE_PID > /tmp/pjecalc.pid
