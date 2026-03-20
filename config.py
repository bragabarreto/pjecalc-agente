# config.py — Configurações globais do Agente PJE-Calc
# Manual Técnico v1.0 — 2026

import os
from pathlib import Path

# ── Diretórios base ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

# DATA_DIR: diretório de dados persistentes.
# Em produção (Railway/Docker) defina DATA_DIR=/app/data para usar volume montado.
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))

LOGS_DIR = DATA_DIR / "logs"
SESSIONS_DIR = LOGS_DIR / "sessions"
SCREENSHOTS_DIR = LOGS_DIR / "screenshots"
OUTPUT_DIR = DATA_DIR / "output"
TEMPLATES_DIR = BASE_DIR / "templates"

# Garantir que os diretórios existam
for _dir in [LOGS_DIR, SESSIONS_DIR, SCREENSHOTS_DIR, OUTPUT_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ── Modo cloud ───────────────────────────────────────────────────────────────
# CLOUD_MODE=true desativa automação desktop (PyAutoGUI/pywinauto indisponíveis).
CLOUD_MODE = os.environ.get("CLOUD_MODE", "false").lower() in ("true", "1", "yes")

# Porta do servidor web (Railway injeta PORT automaticamente)
PORT = int(os.environ.get("PORT", 8000))

# ── API Claude (Anthropic) ───────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"          # modelo padrão para NLP jurídico
CLAUDE_EXTRACTION_TEMPERATURE = 0.0         # determinístico para extração
CLAUDE_MAX_TOKENS = 4096

# ── Limites de confiança (NLP) ───────────────────────────────────────────────
CONFIDENCE_THRESHOLD_AUTO = 0.75    # abaixo → acionar usuário
CONFIDENCE_THRESHOLD_BLOCK = 0.50   # abaixo → parada bloqueante

# ── Automação de interface ───────────────────────────────────────────────────
AUTOMATION_BACKEND = "pyautogui"    # "pyautogui" | "playwright"
PJECALC_WINDOW_TITLE = "PJE-Calc"  # título da janela desktop
PJECALC_URL = os.environ.get("PJECALC_URL", "https://pje.trt7.jus.br/pjecalc")

# Diretório local do PJE-Calc Cidadão (para automação Playwright local).
# Pode ser sobrescrito via env var PJECALC_DIR.
PJECALC_DIR = Path(os.environ.get(
    "PJECALC_DIR",
    str(BASE_DIR.parent / "pjecalc-windows64-2.14.0"),
))

# Tempos de espera (segundos)
WAIT_AFTER_CLICK = 0.5
WAIT_AFTER_SAVE = 1.5
WAIT_AFTER_NAVIGATE = 1.0
WAIT_TIMEOUT_FIELD = 5.0            # tempo máximo para encontrar campo
WAIT_RETRIES = 3                    # tentativas antes de acionar usuário
WAIT_USER_TIMEOUT = 600             # 10 min aguardando resposta do usuário

# ── Formatos de data ─────────────────────────────────────────────────────────
DATE_FORMAT_PJECALC = "%d/%m/%Y"    # formato usado nos campos do PJE-Calc
DATE_FORMAT_ISO = "%Y-%m-%d"        # formato interno do agente

# ── Parâmetros padrão do PJE-Calc ────────────────────────────────────────────
DEFAULT_CARGA_HORARIA = 220         # horas/mês padrão
DEFAULT_ALIQUOTA_FGTS = 0.08        # 8%
DEFAULT_INDICE_CORRECAO = "Tabela JT Única Mensal"
DEFAULT_JUROS = "Juros Padrão"      # 1% a.m.
DEFAULT_REGIME = "Tempo Integral"

# ── OCR ──────────────────────────────────────────────────────────────────────
OCR_LANG = "por"                    # tesseract: português
OCR_CONFIDENCE_MIN = 80             # % mínimo; abaixo → alertar usuário
OCR_DPI = 300                       # resolução para pdf2image

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "json"                 # "json" | "text"

# ── Regiões brasileiras para mapeamento Estado/Município ─────────────────────
ESTADOS_BR = [
    "AC","AL","AP","AM","BA","CE","DF","ES","GO","MA",
    "MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN",
    "RS","RO","RR","SC","SP","SE","TO"
]
