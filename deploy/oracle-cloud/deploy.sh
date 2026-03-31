#!/bin/bash
# deploy.sh — Deploy manual para Oracle Cloud
#
# Uso (do seu Mac):
#   ./deploy/oracle-cloud/deploy.sh <IP> <caminho-chave-ssh>
#
# Exemplo:
#   ./deploy/oracle-cloud/deploy.sh 129.151.xx.xx ~/.ssh/oracle-vm.pem
#
# O que faz:
#   1. Faz setup inicial da VM (se primeira vez)
#   2. Clona ou atualiza o repositório
#   3. Configura .env
#   4. Build e inicia containers

set -euo pipefail

HOST="${1:?Uso: $0 <IP> <chave-ssh>}"
KEY="${2:?Uso: $0 <IP> <chave-ssh>}"
USER="opc"

echo "=== Deploy pjecalc-agente para $HOST ==="

# 1. Setup inicial (idempotente)
echo "[1/4] Executando setup da VM..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$USER@$HOST" 'bash -s' < deploy/oracle-cloud/setup-vm.sh

# 2. Clonar ou atualizar repositório
echo "[2/4] Sincronizando código..."
ssh -i "$KEY" "$USER@$HOST" bash -c "'
    if [ -d ~/pjecalc-agente/.git ]; then
        cd ~/pjecalc-agente && git pull origin main
    else
        git clone https://github.com/bragabarreto/pjecalc-agente.git ~/pjecalc-agente
    fi
    cp ~/pjecalc-agente/deploy/oracle-cloud/docker-compose.yml ~/pjecalc-agente/
'"

# 3. Configurar .env (interativo)
echo "[3/4] Configurando variáveis de ambiente..."
echo "  Informe as chaves de API (ou pressione Enter para pular):"

read -rp "  ANTHROPIC_API_KEY: " ANTHROPIC_KEY
read -rp "  GEMINI_API_KEY: " GEMINI_KEY
read -rp "  POSTGRES_PASSWORD [pjecalc_secret]: " PG_PASS
PG_PASS="${PG_PASS:-pjecalc_secret}"

ssh -i "$KEY" "$USER@$HOST" bash -c "'
    cat > ~/pjecalc-agente/.env << EOF
ANTHROPIC_API_KEY=$ANTHROPIC_KEY
GEMINI_API_KEY=$GEMINI_KEY
POSTGRES_PASSWORD=$PG_PASS
EOF
'"

# 4. Build e iniciar
echo "[4/4] Build e inicialização dos containers..."
ssh -i "$KEY" "$USER@$HOST" bash -c "'
    cd ~/pjecalc-agente
    docker compose build
    docker compose up -d
    echo ""
    echo "=== Status ==="
    docker compose ps
    echo ""
    echo "Acesse: http://$HOST:8000"
'"

echo ""
echo "=== Deploy concluído ==="
echo "URL: http://$HOST:8000"
