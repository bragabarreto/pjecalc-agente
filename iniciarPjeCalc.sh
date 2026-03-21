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
    -Xms512m \
    -Xmx1024m \
    -XX:MaxPermSize=512m \
    -jar bin/pjecalc.jar \
    &

PJE_PID=$!
echo "[PJE-Calc] Processo iniciado (PID: $PJE_PID)"
echo "[PJE-Calc] Aguarde Tomcat finalizar deploy (~30-60s)..."
echo $PJE_PID > /tmp/pjecalc.pid
