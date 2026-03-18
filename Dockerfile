# Dockerfile — Agente PJE-Calc (produção em nuvem)
# Base: Python 3.11 slim (Debian Bookworm)

FROM python:3.11-slim

# Metadados
LABEL maintainer="Agente PJE-Calc" \
      description="Automação de liquidação de sentenças trabalhistas"

# ── Dependências de sistema ───────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# ── Diretório de trabalho ─────────────────────────────────────────────────────
WORKDIR /app

# ── Instalar dependências Python ──────────────────────────────────────────────
# Copiar apenas requirements primeiro (cache de camadas Docker)
COPY requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt

# ── Copiar código fonte ───────────────────────────────────────────────────────
COPY . .

# ── Criar diretórios de dados (volume será montado sobre /app/data) ───────────
RUN mkdir -p data/logs/sessions data/logs/screenshots data/output static

# ── Variáveis de ambiente padrão ──────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    CLOUD_MODE=true \
    PORT=8000

# ── Porta exposta ─────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Comando de inicialização ──────────────────────────────────────────────────
# Railway sobrescreve PORT automaticamente via variável de ambiente.
CMD ["uvicorn", "webapp:app", "--host", "0.0.0.0", "--port", "8000"]
