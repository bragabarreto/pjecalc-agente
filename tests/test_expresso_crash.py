# tests/test_expresso_crash.py — Testes de detecção de crash e recovery do Expresso

from __future__ import annotations

import json
import os
import pytest
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── Testes: limpar_h2_database ─────────────────────────────────────────────────

class TestLimparH2Database:
    """Testes para a função limpar_h2_database()."""

    @pytest.fixture
    def dados_dir(self, tmp_path):
        """Cria diretório .dados/ com arquivos H2 + outros."""
        d = tmp_path / ".dados"
        d.mkdir()
        # Arquivos H2 que devem ser removidos
        (d / "pjecalc.h2.db").write_text("h2-data")
        (d / "pjecalc.lock.db").write_text("lock")
        (d / "pjecalc.mv.db").write_text("mv")
        (d / "pjecalc.trace.db").write_text("trace")
        # Template que NÃO deve ser removido
        (d / "pjecalc.h2.db.template").write_text("template-data")
        # Arquivos que NÃO são H2 e NÃO devem ser removidos
        (d / "config.json").write_text("{}")
        (d / "resultado.pjc").write_text("pjc")
        return tmp_path

    def test_remove_only_h2_files(self, dados_dir):
        """Remove apenas arquivos H2, preserva JSON/PJC/template."""
        from modules.playwright_pjecalc import limpar_h2_database

        logs = []
        result = limpar_h2_database(dados_dir, log_cb=logs.append)
        assert result is True

        d = dados_dir / ".dados"
        # H2 files removidos
        assert not (d / "pjecalc.lock.db").exists()
        assert not (d / "pjecalc.mv.db").exists()
        assert not (d / "pjecalc.trace.db").exists()
        # Template preservado
        assert (d / "pjecalc.h2.db.template").exists()
        # Outros arquivos preservados
        assert (d / "config.json").exists()
        assert (d / "resultado.pjc").exists()

    def test_h2_template_restore(self, dados_dir):
        """Após remover H2, restaura do template."""
        from modules.playwright_pjecalc import limpar_h2_database

        limpar_h2_database(dados_dir)
        d = dados_dir / ".dados"
        # H2 db deve ter sido restaurado do template
        assert (d / "pjecalc.h2.db").exists()
        assert (d / "pjecalc.h2.db").read_text() == "template-data"

    def test_no_dados_dir(self, tmp_path):
        """Se .dados/ não existe, retorna False sem erro."""
        from modules.playwright_pjecalc import limpar_h2_database

        result = limpar_h2_database(tmp_path / "inexistente")
        assert result is False

    def test_no_h2_files(self, tmp_path):
        """Se não há arquivos H2, retorna False."""
        from modules.playwright_pjecalc import limpar_h2_database

        d = tmp_path / ".dados"
        d.mkdir()
        (d / "config.json").write_text("{}")
        result = limpar_h2_database(tmp_path)
        assert result is False

    def test_template_not_removed(self, dados_dir):
        """Template .h2.db.template nunca é removido."""
        from modules.playwright_pjecalc import limpar_h2_database

        limpar_h2_database(dados_dir)
        assert (dados_dir / ".dados" / "pjecalc.h2.db.template").exists()
        assert (dados_dir / ".dados" / "pjecalc.h2.db.template").read_text() == "template-data"


# ── Testes: detecção de morte do Tomcat ────────────────────────────────────────

class TestTomcatDeathDetection:
    """Testes para _tomcat_esta_vivo() via mock."""

    def test_tomcat_alive_http_200(self):
        """Detecta Tomcat vivo via HTTP 200."""
        from modules.playwright_pjecalc import PJECalcPlaywright

        mock_page = MagicMock()
        pjc = PJECalcPlaywright.__new__(PJECalcPlaywright)
        pjc._page = mock_page
        pjc._log_cb = None
        pjc.PJECALC_BASE = "http://localhost:9257/pjecalc"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            assert pjc._tomcat_esta_vivo() is True

    def test_tomcat_dead_connection_refused(self):
        """Detecta Tomcat morto quando conexão recusada."""
        from modules.playwright_pjecalc import PJECalcPlaywright

        mock_page = MagicMock()
        pjc = PJECalcPlaywright.__new__(PJECalcPlaywright)
        pjc._page = mock_page
        pjc._log_cb = None
        pjc.PJECALC_BASE = "http://localhost:9257/pjecalc"

        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError()), \
             patch("socket.create_connection", side_effect=OSError("refused")):
            assert pjc._tomcat_esta_vivo() is False


# ── Testes: feature flags ──────────────────────────────────────────────────────

class TestFeatureFlags:
    """Testes para feature flags de crash protection."""

    def test_expresso_crash_protection_default_true(self):
        """EXPRESSO_CRASH_PROTECTION default é True."""
        from config import EXPRESSO_CRASH_PROTECTION
        assert EXPRESSO_CRASH_PROTECTION is True

    def test_h2_cleanup_enabled_default_true(self):
        """H2_CLEANUP_ENABLED default é True."""
        from config import H2_CLEANUP_ENABLED
        assert H2_CLEANUP_ENABLED is True

    def test_calculation_persistence_default_true(self):
        """CALCULATION_PERSISTENCE default é True."""
        from config import CALCULATION_PERSISTENCE
        assert CALCULATION_PERSISTENCE is True
