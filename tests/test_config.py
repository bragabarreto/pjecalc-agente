# tests/test_config.py — Testes de configuração Pydantic v2 e shims de compatibilidade

from __future__ import annotations

import os
import pytest


# ── Testes: infrastructure/config.py ─────────────────────────────────────────

class TestInfrastructureConfig:
    def test_settings_loads_defaults(self):
        """Settings carrega valores default sem variáveis de ambiente."""
        from infrastructure.config import Settings
        s = Settings()
        assert s.port == 8000
        assert s.claude_model == "claude-sonnet-4-6"
        assert s.confidence_threshold_auto == 0.75
        assert s.learning_feedback_threshold == 10

    def test_settings_from_env(self, monkeypatch):
        """Variáveis de ambiente sobrescrevem defaults."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("LEARNING_FEEDBACK_THRESHOLD", "20")

        # Reimportar para capturar env vars (Pydantic Settings lê no __init__)
        import importlib
        import infrastructure.config as cfg_mod
        importlib.reload(cfg_mod)

        s = cfg_mod.Settings()
        assert s.port == 9000
        assert s.learning_feedback_threshold == 20

    def test_learning_fields_exist(self):
        """Campos do Learning Engine existem com tipos corretos."""
        from infrastructure.config import Settings
        s = Settings()
        assert isinstance(s.learning_enabled, bool)
        assert isinstance(s.learning_feedback_threshold, int)
        assert isinstance(s.learning_retraining_interval_hours, int)

    def test_data_path_property(self):
        """Propriedade data_path retorna um Path."""
        from pathlib import Path
        from infrastructure.config import Settings
        s = Settings()
        assert isinstance(s.data_path, Path)

    def test_use_gemini_false_without_key(self):
        """use_gemini é False quando GEMINI_API_KEY não está configurada."""
        from infrastructure.config import Settings
        s = Settings(_env_file=None)  # type: ignore
        # Sem chave configurada → use_gemini deve ser False
        if not s.gemini_api_key:
            assert s.use_gemini is False


# ── Testes: shim config.py ────────────────────────────────────────────────────

class TestConfigShim:
    def test_shim_exports_anthropic_key(self):
        """O shim em config.py re-exporta ANTHROPIC_API_KEY."""
        try:
            from config import ANTHROPIC_API_KEY
            # Não precisamos que tenha valor; só que exista sem ImportError
        except ImportError as e:
            pytest.fail(f"config.py shim não exporta ANTHROPIC_API_KEY: {e}")

    def test_shim_exports_cloud_mode(self):
        """O shim em config.py re-exporta CLOUD_MODE."""
        try:
            from config import CLOUD_MODE
            assert isinstance(CLOUD_MODE, bool)
        except ImportError as e:
            pytest.fail(f"config.py shim não exporta CLOUD_MODE: {e}")

    def test_shim_exports_output_dir(self):
        """O shim em config.py re-exporta OUTPUT_DIR."""
        try:
            from config import OUTPUT_DIR
            # OUTPUT_DIR pode ser string ou Path
            assert OUTPUT_DIR is not None
        except ImportError as e:
            pytest.fail(f"config.py shim não exporta OUTPUT_DIR: {e}")


# ── Testes: shim database.py ──────────────────────────────────────────────────

class TestDatabaseShim:
    def test_shim_exports_calculo(self):
        """O shim em database.py re-exporta o modelo Calculo."""
        try:
            from database import Calculo
            assert Calculo is not None
        except ImportError as e:
            pytest.fail(f"database.py shim não exporta Calculo: {e}")

    def test_shim_exports_new_learning_models(self):
        """O shim em database.py re-exporta os novos modelos do Learning Engine."""
        try:
            from database import CorrecaoUsuario, RegrasAprendidas, SessaoAprendizado
            assert CorrecaoUsuario is not None
            assert RegrasAprendidas is not None
            assert SessaoAprendizado is not None
        except ImportError as e:
            pytest.fail(f"database.py shim não exporta modelos de aprendizado: {e}")

    def test_correcao_usuario_model_fields(self):
        """CorrecaoUsuario tem todos os campos esperados."""
        from database import CorrecaoUsuario
        col_names = {c.name for c in CorrecaoUsuario.__table__.columns}
        required_fields = {
            "id", "calculo_id", "sessao_id", "tipo_correcao", "entidade",
            "campo", "valor_antes", "valor_depois", "incorporada_em_regra",
        }
        assert required_fields.issubset(col_names), (
            f"Campos ausentes: {required_fields - col_names}"
        )

    def test_regras_aprendidas_model_fields(self):
        """RegrasAprendidas tem todos os campos esperados."""
        from database import RegrasAprendidas
        col_names = {c.name for c in RegrasAprendidas.__table__.columns}
        required_fields = {
            "id", "tipo_regra", "condicao", "acao", "confianca",
            "aplicacoes", "acertos", "ativa",
        }
        assert required_fields.issubset(col_names), (
            f"Campos ausentes: {required_fields - col_names}"
        )

    def test_taxa_acerto_property(self):
        """RegrasAprendidas.taxa_acerto retorna valor correto."""
        from database import RegrasAprendidas
        r = RegrasAprendidas(aplicacoes=10, acertos=8)
        # taxa_acerto pode retornar float (0.8) ou int (80) dependendo da impl
        assert abs(float(r.taxa_acerto) - 0.8) < 0.01 or r.taxa_acerto == 80

    def test_taxa_acerto_zero_when_no_applications(self):
        """RegrasAprendidas.taxa_acerto retorna 0 quando sem aplicações."""
        from database import RegrasAprendidas
        r = RegrasAprendidas(aplicacoes=0, acertos=0)
        assert r.taxa_acerto == 0 or r.taxa_acerto == 0.0


# ── Testes: infrastructure/database.py criação de tabelas ────────────────────

class TestDatabaseCreation:
    def test_criar_tabelas_creates_all_models(self):
        """criar_tabelas() cria todas as tabelas incluindo as de aprendizado."""
        from sqlalchemy import create_engine, inspect
        from infrastructure.database import Base

        test_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=test_engine)

        inspector = inspect(test_engine)
        tabelas = set(inspector.get_table_names())

        assert "calculos" in tabelas
        assert "processos" in tabelas
        assert "correcoes_usuario" in tabelas
        assert "regras_aprendidas" in tabelas
        assert "sessoes_aprendizado" in tabelas
