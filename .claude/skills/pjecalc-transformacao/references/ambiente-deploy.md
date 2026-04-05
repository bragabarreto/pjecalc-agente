# Ambiente: Deploy Local e Cloud

## Índice

1. [Desktop (local)](#1-desktop-local)
2. [Cloud — Railway/Docker](#2-cloud--railwaydocker)
3. [Dockerfile completo](#3-dockerfile-completo)
4. [Entrypoint e startup](#4-entrypoint-e-startup)
5. [Railway config](#5-railway-config)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Desktop (local)

### Windows

```batch
cd pjecalc-dist
java -jar bin\pjecalc.jar
```

### Linux (com GUI)

```bash
cd pjecalc-dist
java -jar bin/pjecalc.jar
```

### Pré-requisitos

- **Java 8** obrigatório (Java 11+ quebra o Lancador)
- Porta 9257 livre
- Distribuição completa do PJe-Calc em `pjecalc-dist/`

### Verificação

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:9257/pjecalc/pages/principal.jsf
# 200 = OK
```

### Backend do pjecalc-agente (local)

```bash
# Terminal 1: PJe-Calc
cd pjecalc-dist && java -jar bin/pjecalc.jar

# Terminal 2: Backend FastAPI
cd pjecalc-agente
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

O Playwright conecta a `http://localhost:9257` para automação.

---

## 2. Cloud — Railway/Docker

O desafio: Lancador.jar abre JOptionPane (dialog Swing) que bloqueia em ambiente sem display.

### Estratégia A — Bootstrap Direto (RECOMENDADA)

Ignora o Lancador completamente. Inicia o Tomcat embarcado diretamente:

```bash
java -Djava.awt.headless=true \
     -Dcatalina.home=/opt/pjecalc/tomcat \
     -Dcatalina.base=/opt/pjecalc/tomcat \
     -cp "/opt/pjecalc/tomcat/bin/bootstrap.jar:/opt/pjecalc/tomcat/bin/tomcat-juli.jar" \
     org.apache.catalina.startup.Bootstrap start
```

Vantagens: sem Xvfb, sem xdotool, sem display virtual, startup mais rápido.
Requisito: `server.xml` configurado com porta 9257 e webapp do PJe-Calc.

### Estratégia B — Xvfb + xdotool (FALLBACK)

Quando Bootstrap Direto não funciona (ex: Lancador faz configurações necessárias):

```bash
# 1. Limpar locks anteriores
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

# 2. Display virtual
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
export DISPLAY=:99

# 3. Window manager leve
fluxbox &

# 4. Auto-dismiss de dialogs
while true; do
    xdotool search --name "PJe-Calc" windowactivate --sync key Return 2>/dev/null
    xdotool search --name "Confirmação" windowactivate --sync key Return 2>/dev/null
    sleep 1
done &

# 5. Lancador com dialog suppressor
java -javaagent:dialog-suppressor.jar -jar pjecalc.jar
```

### Padrão de startup (ambas estratégias)

A ordem correta para containers cloud:

1. Limpar locks X11
2. Iniciar PJe-Calc em background (Estratégia A ou B)
3. **Iniciar uvicorn IMEDIATAMENTE** (Railway healthcheck precisa de resposta rápida)
4. Poll `http://localhost:9257/pjecalc` em background (timeout 600s)
5. Watchdog monitora processo Java a cada 30s, reinicia se crashou

O ponto 3 é crítico: o Railway mata containers que não respondem ao healthcheck a tempo.

---

## 3. Dockerfile completo

```dockerfile
# Multi-stage para manter imagem menor
FROM eclipse-temurin:8-jre-jammy AS base

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    xvfb fluxbox xdotool \
    fonts-dejavu fonts-liberation \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libasound2 \
    curl wget \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt /app/
RUN pip3 install --break-system-packages --no-cache-dir -r /app/requirements.txt

# Playwright (Chromium apenas)
RUN pip3 install --break-system-packages playwright && \
    playwright install chromium && \
    playwright install-deps chromium

# PJe-Calc
COPY pjecalc-dist/ /opt/pjecalc/

# Aplicação
COPY . /app/
WORKDIR /app

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENV PORT=8000
ENV CLOUD_MODE=true

CMD ["/entrypoint.sh"]
```

**Nota:** NUNCA usar Java 11+ no Dockerfile. O PJe-Calc exige Java 8.

---

## 4. Entrypoint e startup

```bash
#!/bin/bash
set -e

echo "=== PJe-Calc Agente — Startup ==="

# 1. Limpar locks
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

# 2. Iniciar PJe-Calc (Estratégia A ou B)
if [ "${PJECALC_STRATEGY:-A}" = "A" ]; then
    echo "[STARTUP] Estratégia A: Bootstrap Direto"
    java -Djava.awt.headless=true \
         -Dcatalina.home=/opt/pjecalc/tomcat \
         -Dcatalina.base=/opt/pjecalc/tomcat \
         -cp "/opt/pjecalc/tomcat/bin/bootstrap.jar:/opt/pjecalc/tomcat/bin/tomcat-juli.jar" \
         org.apache.catalina.startup.Bootstrap start &
else
    echo "[STARTUP] Estratégia B: Xvfb + xdotool"
    Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
    export DISPLAY=:99
    sleep 1
    fluxbox &
    # Auto-dismiss loop
    (while true; do
        xdotool search --name "PJe-Calc" windowactivate --sync key Return 2>/dev/null
        xdotool search --name "Confirmação" windowactivate --sync key Return 2>/dev/null
        sleep 1
    done) &
    java -javaagent:/opt/pjecalc/dialog-suppressor.jar -jar /opt/pjecalc/pjecalc.jar &
fi

PJECALC_PID=$!

# 3. Iniciar uvicorn IMEDIATAMENTE (healthcheck Railway)
echo "[STARTUP] Iniciando uvicorn na porta $PORT"
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} &
UVICORN_PID=$!

# 4. Poll PJe-Calc em background
(
    echo "[POLL] Aguardando PJe-Calc em localhost:9257..."
    TIMEOUT=600
    START=$(date +%s)
    while true; do
        ELAPSED=$(( $(date +%s) - START ))
        if [ $ELAPSED -gt $TIMEOUT ]; then
            echo "[POLL] TIMEOUT: PJe-Calc não subiu em ${TIMEOUT}s"
            break
        fi
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9257/pjecalc/ 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" != "000" ] && [ "$HTTP_CODE" != "502" ]; then
            echo "[POLL] PJe-Calc disponível (HTTP $HTTP_CODE) após ${ELAPSED}s"
            break
        fi
        sleep 10
    done
) &

# 5. Watchdog
(
    while true; do
        sleep 30
        if ! kill -0 $PJECALC_PID 2>/dev/null; then
            echo "[WATCHDOG] PJe-Calc morreu, reiniciando..."
            # Reiniciar PJe-Calc (mesma estratégia)
            if [ "${PJECALC_STRATEGY:-A}" = "A" ]; then
                java -Djava.awt.headless=true \
                     -Dcatalina.home=/opt/pjecalc/tomcat \
                     -Dcatalina.base=/opt/pjecalc/tomcat \
                     -cp "/opt/pjecalc/tomcat/bin/bootstrap.jar:/opt/pjecalc/tomcat/bin/tomcat-juli.jar" \
                     org.apache.catalina.startup.Bootstrap start &
            fi
            PJECALC_PID=$!
        fi
    done
) &

# Manter container rodando
wait $UVICORN_PID
```

---

## 5. Railway config

```toml
# railway.toml
[build]
builder = "dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 120
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 5
```

Variáveis de ambiente:

| Variável | Valor | Descrição |
|----------|-------|-----------|
| `PORT` | 8000 | Porta do FastAPI |
| `CLOUD_MODE` | true | Desativa componentes que precisam de display |
| `PJECALC_STRATEGY` | A | A=Bootstrap Direto, B=Xvfb |
| `PJECALC_URL` | http://localhost:9257 | URL do PJe-Calc |
| `ANTHROPIC_API_KEY` | sk-ant-... | Para extração com Claude |

---

## 6. Troubleshooting

### PJe-Calc não sobe (Bootstrap Direto)

1. Verificar se `server.xml` tem `<Connector port="9257" .../>`
2. Verificar se JARs do Tomcat estão em `/opt/pjecalc/tomcat/bin/`
3. Verificar logs: `tail -f /opt/pjecalc/tomcat/logs/catalina.out`

### PJe-Calc não sobe (Xvfb)

1. `DISPLAY=:99 xdpyinfo` — se falhar, Xvfb não está rodando
2. Verificar se `dialog-suppressor.jar` existe e está no classpath
3. Testar manualmente: `DISPLAY=:99 java -jar pjecalc.jar` e observar output

### Railway healthcheck falha

O container é morto antes do PJe-Calc subir:

1. Verificar que uvicorn inicia ANTES do PJe-Calc (ponto 3 do startup)
2. Implementar `/health` endpoint que responde 200 mesmo com PJe-Calc pendente:

```python
@app.get("/health")
async def health():
    pjecalc_ok = await verificar_pjecalc()
    return {
        "status": "ok",
        "pjecalc": "ready" if pjecalc_ok else "starting",
        "uptime": time.time() - STARTUP_TIME
    }
```

### Playwright não encontra elementos

1. PJe-Calc pode não estar totalmente carregado → aumentar timeout
2. ViewState expirado → reload da página
3. IDs JSF mudaram → usar hierarquia de seletores em 4 níveis
