#!/bin/bash
# docker-entrypoint.sh — Inicialização do container PJE-Calc Agent
# Sequência:
#   1. Inicia PJE-Calc (Tomcat Java) em background
#   2. Inicia Python Agent (FastAPI/uvicorn) IMEDIATAMENTE → healthcheck passa
#   3. Tomcat continua inicializando em background (pode levar 3-5 min)
#      A automação verifica se o Tomcat está pronto antes de executar.

set -e

echo "=== PJE-Calc Agent — iniciando ==="

# 1. Inicia PJE-Calc em background (não bloqueia)
echo "[1/2] Iniciando PJE-Calc Cidadão em background..."
bash /opt/pjecalc/iniciarPjeCalc.sh

# Monitor do Tomcat em subshell background (só para logging)
(
    TIMEOUT=600
    ELAPSED=0
    until curl -sf "http://localhost:9257/pjecalc" -o /dev/null 2>&1 || \
          curl -sf "http://localhost:9257/" -o /dev/null 2>&1; do
        if [ $ELAPSED -ge $TIMEOUT ]; then
            echo "[PJE-Calc] AVISO: Tomcat não respondeu em ${TIMEOUT}s."
            echo "--- catalina.out (últimas 30 linhas) ---"
            tail -30 /opt/pjecalc/tomcat/logs/catalina.out 2>/dev/null || echo "(sem log)"
            echo "--- Processos Java ---"
            ps aux | grep java 2>/dev/null || echo "(nenhum)"
            break
        fi
        sleep 10
        ELAPSED=$((ELAPSED + 10))
    done
    if [ $ELAPSED -lt $TIMEOUT ]; then
        echo "[PJE-Calc] Tomcat pronto em localhost:9257 ✓ (${ELAPSED}s)"
    fi
) &

# 2. Inicia Python Agent IMEDIATAMENTE (Railway healthcheck vai passar)
echo "[2/2] Iniciando Python Agent na porta ${PORT:-8000}..."
cd /app
exec uvicorn webapp:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1
