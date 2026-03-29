# infrastructure/config.py — Configurações globais com validação Pydantic v2
# Substitui config.py raiz (que agora é um shim de backward compat)

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configurações do pjecalc-agente com validação Pydantic v2.

    Lê variáveis de ambiente e arquivo .env automaticamente.
    Todos os nomes são iguais às constantes do config.py original (backward compat).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── API Keys ──────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # ── Modelos Claude ────────────────────────────────────────────────────────
    claude_model: str = "claude-sonnet-4-6"
    claude_extraction_temperature: float = 0.0
    claude_max_tokens: int = 4096

    # ── Modo cloud (auto-detectado) ───────────────────────────────────────────
    cloud_mode: bool = False   # sobrescrito pelo @model_validator abaixo

    # ── Servidor ──────────────────────────────────────────────────────────────
    port: int = 8000

    # ── Diretórios ────────────────────────────────────────────────────────────
    # DATA_DIR: sobrescrever com DATA_DIR=/app/data em Railway/Docker
    data_dir: str = ""   # resolvido em model_validator

    # ── Limites de confiança ──────────────────────────────────────────────────
    confidence_threshold_auto: float = 0.75
    confidence_threshold_block: float = 0.50

    # ── Automação ────────────────────────────────────────────────────────────
    automation_backend: str = "pyautogui"
    pjecalc_window_title: str = "PJE-Calc"
    pjecalc_url: str = "https://pje.trt7.jus.br/pjecalc"
    pjecalc_local_url: str = "http://localhost:9257/pjecalc"
    pjecalc_tomcat_timeout: int = 600
    pjecalc_dir: str = ""   # resolvido em model_validator

    # ── Tempos de espera ──────────────────────────────────────────────────────
    wait_after_click: float = 0.5
    wait_after_save: float = 1.5
    wait_after_navigate: float = 1.0
    wait_timeout_field: float = 5.0
    wait_retries: int = 3
    wait_user_timeout: int = 600

    # ── Formatos ─────────────────────────────────────────────────────────────
    date_format_pjecalc: str = "%d/%m/%Y"
    date_format_iso: str = "%Y-%m-%d"

    # ── Padrões PJE-Calc ──────────────────────────────────────────────────────
    default_carga_horaria: int = 220
    default_aliquota_fgts: float = 0.08
    default_indice_correcao: str = "Tabela JT Única Mensal"
    default_juros: str = "Juros Padrão"
    default_regime: str = "Tempo Integral"

    # ── OCR ───────────────────────────────────────────────────────────────────
    ocr_lang: str = "por"
    ocr_confidence_min: int = 80
    ocr_dpi: int = 300

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"

    # ── Learning Engine ───────────────────────────────────────────────────────
    learning_enabled: bool = True
    learning_feedback_threshold: int = 10
    learning_retraining_interval_hours: int = 24
    learning_min_session_interval_minutes: int = 60

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = ""   # resolvido em model_validator

    # ── Validadores ───────────────────────────────────────────────────────────

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_anthropic_key(cls, v: str) -> str:
        """Emite aviso se a chave não tiver o prefixo esperado (não bloqueia)."""
        if v and not v.startswith("sk-ant-"):
            import warnings
            warnings.warn(
                "ANTHROPIC_API_KEY não começa com 'sk-ant-'. Verifique se a chave está correta.",
                stacklevel=2,
            )
        return v

    @model_validator(mode="after")
    def resolve_dynamic_fields(self) -> "Settings":
        """Resolve campos que dependem de outros campos ou do sistema de arquivos."""
        base_dir = Path(__file__).parent.parent

        # DATA_DIR
        if not self.data_dir:
            self.data_dir = str(
                Path(os.environ.get("DATA_DIR", str(base_dir / "data")))
            )

        # PJECALC_DIR
        if not self.pjecalc_dir:
            self.pjecalc_dir = str(
                Path(os.environ.get("PJECALC_DIR", str(base_dir / "pjecalc-dist")))
            )

        # DATABASE_URL
        if not self.database_url:
            default_db = str(Path(self.data_dir) / "pjecalc_agent.db")
            raw = os.environ.get("DATABASE_URL", f"sqlite:///{default_db}")
            # Railway emite "postgres://" — SQLAlchemy exige "postgresql://"
            self.database_url = (
                raw.replace("postgres://", "postgresql://", 1)
                if raw.startswith("postgres://")
                else raw
            )

        # CLOUD_MODE auto-detecção (preserva lógica do config.py original)
        env_cloud = os.environ.get("CLOUD_MODE", "").strip().lower()
        if env_cloud in ("true", "1", "yes"):
            self.cloud_mode = True
        elif env_cloud in ("false", "0", "no"):
            self.cloud_mode = False
        else:
            try:
                import playwright  # noqa: F401
                self.cloud_mode = False
            except ImportError:
                self.cloud_mode = True

        # Garantir diretórios
        data_path = Path(self.data_dir)
        for subdir in ["logs/sessions", "logs/screenshots", "output", "learning"]:
            (data_path / subdir).mkdir(parents=True, exist_ok=True)

        return self

    # ── Propriedades derivadas ────────────────────────────────────────────────

    @property
    def base_dir(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def logs_dir(self) -> Path:
        return self.data_path / "logs"

    @property
    def sessions_dir(self) -> Path:
        return self.logs_dir / "sessions"

    @property
    def screenshots_dir(self) -> Path:
        return self.logs_dir / "screenshots"

    @property
    def output_dir(self) -> Path:
        return self.data_path / "output"

    @property
    def learning_dir(self) -> Path:
        return self.data_path / "learning"

    @property
    def templates_dir(self) -> Path:
        return self.base_dir / "templates"

    @property
    def pjecalc_path(self) -> Path:
        return Path(self.pjecalc_dir)

    @property
    def use_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def estados_br(self) -> list[str]:
        return [
            "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
            "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
            "RS", "RO", "RR", "SC", "SP", "SE", "TO",
        ]


# ── Instância global ──────────────────────────────────────────────────────────

settings = Settings()

# ── Re-exportações como constantes de módulo (backward compatibility) ─────────
# Permite: from config import ANTHROPIC_API_KEY  (sem mudança em código existente)

BASE_DIR = settings.base_dir
DATA_DIR = settings.data_path
LOGS_DIR = settings.logs_dir
SESSIONS_DIR = settings.sessions_dir
SCREENSHOTS_DIR = settings.screenshots_dir
OUTPUT_DIR = settings.output_dir
TEMPLATES_DIR = settings.templates_dir

ANTHROPIC_API_KEY = settings.anthropic_api_key
CLAUDE_MODEL = settings.claude_model
CLAUDE_EXTRACTION_TEMPERATURE = settings.claude_extraction_temperature
CLAUDE_MAX_TOKENS = settings.claude_max_tokens

GEMINI_API_KEY = settings.gemini_api_key
GEMINI_MODEL = settings.gemini_model
USE_GEMINI = settings.use_gemini

CLOUD_MODE = settings.cloud_mode
PORT = settings.port

CONFIDENCE_THRESHOLD_AUTO = settings.confidence_threshold_auto
CONFIDENCE_THRESHOLD_BLOCK = settings.confidence_threshold_block

AUTOMATION_BACKEND = settings.automation_backend
PJECALC_WINDOW_TITLE = settings.pjecalc_window_title
PJECALC_URL = settings.pjecalc_url
PJECALC_LOCAL_URL = settings.pjecalc_local_url
PJECALC_TOMCAT_TIMEOUT = settings.pjecalc_tomcat_timeout
PJECALC_DIR = settings.pjecalc_path

WAIT_AFTER_CLICK = settings.wait_after_click
WAIT_AFTER_SAVE = settings.wait_after_save
WAIT_AFTER_NAVIGATE = settings.wait_after_navigate
WAIT_TIMEOUT_FIELD = settings.wait_timeout_field
WAIT_RETRIES = settings.wait_retries
WAIT_USER_TIMEOUT = settings.wait_user_timeout

DATE_FORMAT_PJECALC = settings.date_format_pjecalc
DATE_FORMAT_ISO = settings.date_format_iso

DEFAULT_CARGA_HORARIA = settings.default_carga_horaria
DEFAULT_ALIQUOTA_FGTS = settings.default_aliquota_fgts
DEFAULT_INDICE_CORRECAO = settings.default_indice_correcao
DEFAULT_JUROS = settings.default_juros
DEFAULT_REGIME = settings.default_regime

OCR_LANG = settings.ocr_lang
OCR_CONFIDENCE_MIN = settings.ocr_confidence_min
OCR_DPI = settings.ocr_dpi

LOG_LEVEL = settings.log_level
LOG_FORMAT = settings.log_format

ESTADOS_BR = settings.estados_br

DATABASE_URL = settings.database_url
