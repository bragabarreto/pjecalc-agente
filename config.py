# config.py — Configurações globais do Agente PJE-Calc
# Manual Técnico v1.0 — 2026

import os
from pathlib import Path

# Carrega variáveis do arquivo .env (se existir) — útil na instalação local
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv não instalado ainda (primeira execução)

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
# CLOUD_MODE=true desativa automação (sem Playwright disponível).
# Se não definido explicitamente, detecta automaticamente pela presença do Playwright.
_cloud_env = os.environ.get("CLOUD_MODE", "").strip().lower()
if _cloud_env in ("true", "1", "yes"):
    CLOUD_MODE = True
elif _cloud_env in ("false", "0", "no"):
    CLOUD_MODE = False
else:
    # Auto-detecção: se Playwright estiver instalado, automação disponível
    try:
        import playwright  # noqa: F401
        CLOUD_MODE = False
    except ImportError:
        CLOUD_MODE = True

# Porta do servidor web (Railway injeta PORT automaticamente)
PORT = int(os.environ.get("PORT", 8000))

# ── API Claude (Anthropic) ───────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"          # modelo padrão para NLP jurídico
CLAUDE_EXTRACTION_TEMPERATURE = 0.0         # determinístico para extração
CLAUDE_MAX_TOKENS = 4096

# ── API Gemini (Google) — opcional ───────────────────────────────────────────
# Se GEMINI_API_KEY estiver definida, usa Gemini 2.5 Flash para extração.
# Deixe em branco para usar Claude (padrão).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
USE_GEMINI = bool(GEMINI_API_KEY)

# ── Limites de confiança (NLP) ───────────────────────────────────────────────
CONFIDENCE_THRESHOLD_AUTO = 0.75    # abaixo → acionar usuário
CONFIDENCE_THRESHOLD_BLOCK = 0.50   # abaixo → parada bloqueante

# ── Automação de interface ───────────────────────────────────────────────────
AUTOMATION_BACKEND = "pyautogui"    # "pyautogui" | "playwright"
PJECALC_WINDOW_TITLE = "PJE-Calc"  # título da janela desktop
PJECALC_URL = os.environ.get("PJECALC_URL", "https://pje.trt7.jus.br/pjecalc")

# URL do PJE-Calc Cidadão local (Tomcat embutido).
# Instalação padrão (TRT): http://localhost:8080/pje-calc
# Versão bundled (pjecalc-dist/): http://localhost:9257/pjecalc  ← padrão
# Sobrescrever com PJECALC_LOCAL_URL=http://localhost:8080/pje-calc se necessário.
PJECALC_LOCAL_URL = os.environ.get(
    "PJECALC_LOCAL_URL",
    "http://localhost:9257/pjecalc",
)

# Timeout (segundos) para aguardar o Tomcat inicializar antes da automação.
# Local (usuário já abriu o PJE-Calc): 30s é suficiente.
# Railway/Docker (Tomcat sobe junto): 600s.
# Sobrescrever com PJECALC_TOMCAT_TIMEOUT=30 para modo local.
PJECALC_TOMCAT_TIMEOUT = int(os.environ.get("PJECALC_TOMCAT_TIMEOUT", 600))

# Diretório local do PJE-Calc Cidadão (para automação Playwright local).
# Pode ser sobrescrito via env var PJECALC_DIR.
PJECALC_DIR = Path(os.environ.get(
    "PJECALC_DIR",
    str(BASE_DIR / "pjecalc-dist"),
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
