#!/bin/bash
# iniciar-agente.command — Duplo-clique no Finder para abrir o PJECalc Agente
# macOS: Settings > Privacy & Security > "Open Anyway" na primeira execução.

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PORT=${PORT:-8000}

# Verificar se já está rodando
if curl -s "http://localhost:$PORT/" > /dev/null 2>&1; then
  open "http://localhost:$PORT/"
  exit 0
fi

# Ativar venv se existir
if [ -d "$DIR/venv/bin" ]; then
  source "$DIR/venv/bin/activate"
elif [ -d "$DIR/.venv/bin" ]; then
  source "$DIR/.venv/bin/activate"
fi

# Verificar dependências mínimas
if ! python3 -c "import uvicorn" 2>/dev/null; then
  osascript -e 'display alert "Dependências não instaladas" message "Execute no Terminal:\n\npip install -r requirements.txt\nplaywright install chromium" as warning'
  exit 1
fi

# Carregar .env se existir
if [ -f "$DIR/.env" ]; then
  export $(grep -v '^#' "$DIR/.env" | xargs) 2>/dev/null || true
fi

echo "Iniciando PJECalc Agente na porta $PORT…"

# Iniciar uvicorn em background
python3 -m uvicorn webapp:app --host 127.0.0.1 --port "$PORT" &
UVICORN_PID=$!

# Aguardar o servidor subir (máx 15s)
for i in $(seq 1 15); do
  sleep 1
  if curl -s "http://localhost:$PORT/" > /dev/null 2>&1; then
    break
  fi
done

# Abrir no browser padrão
open "http://localhost:$PORT/"

echo ""
echo "PJECalc Agente rodando em http://localhost:$PORT/"
echo "Feche esta janela para encerrar o servidor."
echo ""

# Aguardar o processo (manter janela aberta)
wait $UVICORN_PID
