# Dockerfile — PJE-Calc Agent (arquitetura CalcMachine)
#
# Contém tudo em um container:
#   - PJE-Calc Cidadão (Tomcat 7 + H2 Java) na porta 9257
#   - Playwright Chromium (headless) para automação
#   - Python Agent (FastAPI/uvicorn) na porta 8000
#
# Build:  docker build -t pjecalc-agent .
# Run:    docker run -p 8000:8000 -v pjecalc-dados:/opt/pjecalc/.dados pjecalc-agent
#
# Variáveis de ambiente obrigatórias:
#   ANTHROPIC_API_KEY ou GEMINI_API_KEY
# Opcionais:
#   PORT (padrão 8000), PJECALC_DIR (padrão /opt/pjecalc)

# ── Base: OpenJDK 8 (necessário para PJE-Calc) + Python 3.11 ─────────────────
FROM eclipse-temurin:8-jre-jammy

# Python 3.11 via deadsnakes
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-distutils \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# ── Dependências de sistema para Playwright Chromium ────────────────────────
# cache-bust: 2026-03-22-v4
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright deps
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 libxshmfence1 \
    # Libs X11 exigidas pelo Java AWT (libawt_xawt.so)
    libxtst6 libxi6 libxrender1 \
    # xdotool + matchbox: auto-dismiss dialogs Java no Xvfb
    # matchbox-window-manager gerencia foco (sem WM, xdotool key vai ao vácuo)
    xdotool matchbox-window-manager \
    # Fontes para renderização correta do PJE-Calc
    fonts-liberation fonts-dejavu-core \
    # Utilitários
    curl wget bash \
    && rm -rf /var/lib/apt/lists/*

# ── PJE-Calc Cidadão ─────────────────────────────────────────────────────────
# IMPORTANTE: copiar de pjecalc-dist/ (criada manualmente sem jre/ e navegador/)
# Estrutura esperada:
#   pjecalc-dist/bin/pjecalc.jar
#   pjecalc-dist/bin/lib/*.jar
#   pjecalc-dist/tomcat/  (completo)
#   pjecalc-dist/iniciarPjeCalc.sh
#
# Se pjecalc-dist/ não existir, o build falhará com mensagem clara.
WORKDIR /opt/pjecalc
COPY pjecalc-dist/bin/ bin/
COPY pjecalc-dist/tomcat/ tomcat/
COPY iniciarPjeCalc.sh .
RUN chmod +x iniciarPjeCalc.sh \
    && mkdir -p .dados \
    && mkdir -p tomcat/logs

ENV PJECALC_DIR=/opt/pjecalc

# ── Agente Python ─────────────────────────────────────────────────────────────
WORKDIR /app

# Requirements primeiro (cache de camada Docker)
COPY requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt

# Instalar Playwright Chromium
RUN playwright install chromium --with-deps

# Código fonte
COPY . .

# Diretórios de dados
RUN mkdir -p data/logs/sessions data/logs/screenshots data/output static

# ── Variáveis de ambiente ──────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    CLOUD_MODE=false \
    PORT=8000

# ── Portas expostas ───────────────────────────────────────────────────────────
EXPOSE 8000
# 9257 é interno (PJE-Calc): não precisa ser exposto externamente

# ── Script de inicialização ───────────────────────────────────────────────────
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

CMD ["/usr/local/bin/docker-entrypoint.sh"]
