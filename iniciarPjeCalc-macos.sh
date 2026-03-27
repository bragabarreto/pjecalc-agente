#!/bin/bash
# iniciarPjeCalc-macos.sh — Inicia o PJE-Calc Cidadão no macOS
# Usa Bootstrap direto (bypassa Lancador.java e seus diálogos Swing)
# Não precisa de Xvfb, xdotool nem display virtual — java.awt.headless=true
#
# Uso: bash iniciarPjeCalc-macos.sh
# Requer: Java 8 instalado (brew install --cask temurin@8)

set +e

# ── Localizar diretório do PJE-Calc ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PJECALC_DIR="${PJECALC_DIR:-$SCRIPT_DIR}"
LOG_FILE="$PJECALC_DIR/pjecalc.log"
PID_FILE="$PJECALC_DIR/pjecalc.pid"

cd "$PJECALC_DIR"

echo "[PJE-Calc] Diretório: $PJECALC_DIR"
echo "[PJE-Calc] Log: $LOG_FILE"

# ── Matar instância anterior ─────────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[PJE-Calc] Encerrando instância anterior (PID: $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi
    rm -f "$PID_FILE"
fi

# ── Localizar Java 8 no macOS ────────────────────────────────────────────────
JAVA_CMD=""

# 1. Homebrew Temurin 8 (brew install --cask temurin@8)
for dir in /Library/Java/JavaVirtualMachines/temurin-8* \
           /Library/Java/JavaVirtualMachines/zulu-8* \
           /Library/Java/JavaVirtualMachines/jdk1.8* \
           /Library/Java/JavaVirtualMachines/adoptopenjdk-8*; do
    if [ -f "$dir/Contents/Home/bin/java" ]; then
        JAVA_CMD="$dir/Contents/Home/bin/java"
        break
    fi
done

# 2. JAVA_HOME definido pelo usuário (SDKMAN, jenv, etc.)
if [ -z "$JAVA_CMD" ] && [ -n "$JAVA_HOME" ] && [ -f "$JAVA_HOME/bin/java" ]; then
    JAVA_CMD="$JAVA_HOME/bin/java"
fi

# 3. java no PATH
if [ -z "$JAVA_CMD" ] && command -v java &>/dev/null; then
    JAVA_CMD="java"
fi

if [ -z "$JAVA_CMD" ]; then
    echo "[PJE-Calc] ERRO: Java 8 não encontrado."
    echo "[PJE-Calc] Instale via: brew install --cask temurin@8"
    echo "[PJE-Calc] Ou baixe em: https://adoptium.net/temurin/releases/?version=8"
    exit 1
fi

JAVA_VERSION=$("$JAVA_CMD" -version 2>&1 | head -1)
echo "[PJE-Calc] Java: $JAVA_VERSION"

# ── Montar classpath ─────────────────────────────────────────────────────────
CLASSPATH="$PJECALC_DIR/bin/pjecalc.jar"
for jar in "$PJECALC_DIR/bin/lib/"*.jar; do
    [ -f "$jar" ] && CLASSPATH="$CLASSPATH:$jar"
done

# ── Iniciar Tomcat via Bootstrap (bypassa Lancador) ──────────────────────────
echo "[PJE-Calc] Iniciando Tomcat na porta 9257 (Bootstrap direto)..."
echo "[PJE-Calc] Log em tempo real: tail -f $LOG_FILE"

"$JAVA_CMD" \
    -Djava.awt.headless=true \
    -Duser.timezone=GMT-3 \
    -Dfile.encoding=ISO-8859-1 \
    -Dseguranca.pjecalc.tokenServicos=pW4jZ4g9VM5MCy6FnB5pEfQe \
    -Dseguranca.pjekz.servico.contexto=https://pje.trt8.jus.br/pje-seguranca \
    -Xms128m \
    -Xmx512m \
    -XX:MaxPermSize=512m \
    -Dcatalina.home="$PJECALC_DIR/tomcat" \
    -Dcatalina.base="$PJECALC_DIR/tomcat" \
    -Dcaminho.instalacao="$PJECALC_DIR" \
    -cp "$CLASSPATH" \
    org.apache.catalina.startup.Bootstrap start \
    >> "$LOG_FILE" 2>&1 &

JAVA_PID=$!
echo $JAVA_PID > "$PID_FILE"
echo "[PJE-Calc] Iniciado (PID: $JAVA_PID)"
echo "[PJE-Calc] Aguarde ~30s para o Tomcat finalizar o deploy..."
echo "[PJE-Calc] Acesse: http://localhost:9257/pjecalc"
