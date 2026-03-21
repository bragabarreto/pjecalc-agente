#!/bin/bash
# docker-entrypoint.sh — Inicialização do container PJE-Calc Agent
# Sequência:
#   1. Inicia PJE-Calc (Tomcat Java) em background
#   2. Aguarda Tomcat responder em localhost:9257
#   3. Inicia Python Agent (FastAPI/uvicorn)

set -e

echo "=== PJE-Calc Agent — iniciando ==="

# 1. Inicia PJE-Calc em background
echo "[1/3] Iniciando PJE-Calc Cidadão..."
bash /opt/pjecalc/iniciarPjeCalc.sh

# 2. Aguarda Tomcat responder (máximo 120s)
echo "[2/3] Aguardando Tomcat na porta 9257..."
TIMEOUT=120
ELAPSED=0
until curl -sf "http://localhost:9257/pjecalc" -o /dev/null 2>&1; do
    if [ $ELAPSED -ge $TIMEOUT ]; then
        echo "ERRO: PJE-Calc não respondeu em ${TIMEOUT}s."
        echo "Verifique os logs em /opt/pjecalc/tomcat/logs/"
        exit 1
    fi
    echo "  Aguardando... (${ELAPSED}s)"
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done
echo "  PJE-Calc pronto em localhost:9257 ✓"

# 3. Inicia Python Agent
echo "[3/3] Iniciando Python Agent na porta ${PORT:-8000}..."
cd /app
exec uvicorn webapp:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1
