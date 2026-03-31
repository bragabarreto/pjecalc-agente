#!/bin/bash
# setup-vm.sh — Configuração inicial da VM Oracle Cloud para pjecalc-agente
#
# Uso:
#   ssh -i <chave.pem> opc@<IP> 'bash -s' < setup-vm.sh
#
# Compatível com: Oracle Linux 9 (ARM64 / A2.Flex)
#
# O que faz:
#   1. Instala Docker + Docker Compose
#   2. Cria diretórios de dados persistentes
#   3. Configura firewall (firewalld)
#   4. Instala Git

set -euo pipefail

echo "=== Setup VM Oracle Cloud para pjecalc-agente ==="
echo "Data: $(date)"
echo "Arch: $(uname -m)"
echo "OS: $(cat /etc/oracle-release 2>/dev/null || cat /etc/os-release | head -1)"

# ── 1. Atualizar sistema ──────────────────────────────────────────────────────
echo "[1/5] Atualizando sistema..."
sudo dnf update -y

# ── 2. Instalar Docker ───────────────────────────────────────────────────────
echo "[2/5] Instalando Docker..."
if ! command -v docker &>/dev/null; then
    sudo dnf install -y dnf-utils
    sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
    sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo systemctl enable docker
    sudo systemctl start docker
else
    echo "  Docker já instalado: $(docker --version)"
fi

# Adicionar usuário opc ao grupo docker
sudo usermod -aG docker opc
echo "  Docker Compose: $(docker compose version 2>/dev/null || echo 'instalando...')"

# ── 3. Instalar Git ──────────────────────────────────────────────────────────
echo "[3/5] Instalando Git..."
sudo dnf install -y git

# ── 4. Criar diretórios persistentes ─────────────────────────────────────────
echo "[4/5] Criando diretórios de dados..."
sudo mkdir -p /opt/pjecalc-data/{calculations,postgres,pjecalc-dados}
sudo chown -R opc:opc /opt/pjecalc-data

# ── 5. Configurar firewall ───────────────────────────────────────────────────
echo "[5/5] Configurando firewall..."
# Oracle Linux usa firewalld
if command -v firewall-cmd &>/dev/null; then
    sudo firewall-cmd --permanent --add-port=8000/tcp
    sudo firewall-cmd --permanent --add-port=80/tcp
    sudo firewall-cmd --permanent --add-port=443/tcp
    sudo firewall-cmd --reload
    echo "  Portas 80, 443, 8000 abertas no firewalld"
fi

# iptables (fallback / regras internas Oracle Cloud)
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT 2>/dev/null || true

echo ""
echo "=== Setup concluído ==="
echo ""
echo "Próximos passos:"
echo "  1. Faça logout e login novamente (para grupo docker ativar)"
echo "  2. Clone o repo: git clone https://github.com/bragabarreto/pjecalc-agente.git"
echo "  3. Configure .env e execute: docker compose up -d"
echo ""
echo "IP público: $(curl -s ifconfig.me 2>/dev/null || echo 'N/A')"
