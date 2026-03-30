# tests/test_calculation_store.py — Testes do CalculationStore (persistência por processo)

from __future__ import annotations

import json
import pytest
from pathlib import Path

from infrastructure.calculation_store import CalculationStore


@pytest.fixture
def store(tmp_path):
    """CalculationStore com base_dir em diretório temporário."""
    return CalculationStore(base_dir=tmp_path / "calculations")


@pytest.fixture
def exec_dir(store):
    """Cria uma execução e retorna o diretório."""
    return store.criar_execucao("0001686-52.2026.5.07.0003", "abc-123")


class TestCriarExecucao:
    def test_directory_structure(self, exec_dir):
        """criar_execucao cria subdiretórios screenshots/ e logs/."""
        assert exec_dir.exists()
        assert (exec_dir / "screenshots").is_dir()
        assert (exec_dir / "logs").is_dir()

    def test_sessao_id_saved(self, exec_dir):
        """Salva referência da sessão em .sessao_id."""
        assert (exec_dir / ".sessao_id").read_text(encoding="utf-8") == "abc-123"

    def test_processo_dir_normalized(self, store):
        """Número do processo é normalizado para uso como diretório."""
        d = store.criar_execucao("123/456:789", "s1")
        # Caracteres inválidos devem ser substituídos por '-'
        assert "/" not in d.parent.name
        assert ":" not in d.parent.name


class TestSalvarMetadados:
    def test_json_valid(self, store, exec_dir):
        """Salva metadata.json válido com campos esperados."""
        store.salvar_metadados(exec_dir, {
            "processo": {"numero": "0001686-52.2026.5.07.0003"},
            "contrato": {"admissao": "01/01/2020"},
            "_status": "em_andamento",
            "alertas": ["campo X ausente"],
        })
        meta = json.loads((exec_dir / "metadata.json").read_text(encoding="utf-8"))
        assert meta["status"] == "em_andamento"
        assert "timestamp" in meta
        assert meta["processo"]["numero"] == "0001686-52.2026.5.07.0003"
        assert len(meta["alertas"]) == 1


class TestSalvarExtracaoLlm:
    def test_saves_raw_response(self, store, exec_dir):
        """Salva resposta bruta do LLM."""
        raw = {"model": "claude", "contrato": {"admissao": "2020-01-01"}}
        store.salvar_extracao_llm(exec_dir, raw)
        saved = json.loads((exec_dir / "llm_extraction.json").read_text(encoding="utf-8"))
        assert saved["model"] == "claude"


class TestSalvarParametrosEnviados:
    def test_saves_params(self, store, exec_dir):
        """Salva parâmetros enviados ao PJE-Calc."""
        params = {"predefinidas": [{"nome": "Horas extras"}]}
        store.salvar_parametros_enviados(exec_dir, params)
        saved = json.loads((exec_dir / "parameters_sent.json").read_text(encoding="utf-8"))
        assert saved["predefinidas"][0]["nome"] == "Horas extras"


class TestCopiarPjc:
    def test_copies_existing_file(self, store, exec_dir, tmp_path):
        """Copia arquivo .PJC para exec_dir."""
        src = tmp_path / "resultado.pjc"
        src.write_text("conteudo-pjc", encoding="utf-8")
        dest = store.copiar_pjc(exec_dir, src)
        assert dest.exists()
        assert dest.name == "final_result.pjc"
        assert dest.read_text(encoding="utf-8") == "conteudo-pjc"

    def test_nonexistent_source(self, store, exec_dir, tmp_path):
        """Se fonte não existe, retorna path mas não cria arquivo."""
        dest = store.copiar_pjc(exec_dir, tmp_path / "inexistente.pjc")
        assert not dest.exists()


class TestSalvarScreenshot:
    def test_saves_png(self, store, exec_dir):
        """Salva screenshot como PNG."""
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        path = store.salvar_screenshot(exec_dir, "01_dados_processo", png_data)
        assert path.exists()
        assert path.name == "01_dados_processo.png"
        assert path.read_bytes() == png_data


class TestSalvarLog:
    def test_saves_log_lines(self, store, exec_dir):
        """Salva log da automação."""
        lines = ["Iniciando...", "Fase 1 concluída", "FIM"]
        store.salvar_log(exec_dir, lines)
        content = (exec_dir / "logs" / "automation.log").read_text(encoding="utf-8")
        assert "Fase 1 concluída" in content


class TestAtualizarStatus:
    def test_updates_existing_metadata(self, store, exec_dir):
        """Atualiza status em metadata.json existente."""
        store.salvar_metadados(exec_dir, {"_status": "em_andamento"})
        store.atualizar_status(exec_dir, "concluido", {"pjc_path": "/tmp/x.pjc"})
        meta = json.loads((exec_dir / "metadata.json").read_text(encoding="utf-8"))
        assert meta["status"] == "concluido"
        assert meta["pjc_path"] == "/tmp/x.pjc"
        assert "atualizado_em" in meta

    def test_creates_metadata_if_missing(self, store, exec_dir):
        """Cria metadata.json se não existir."""
        store.atualizar_status(exec_dir, "erro")
        meta = json.loads((exec_dir / "metadata.json").read_text(encoding="utf-8"))
        assert meta["status"] == "erro"


class TestNormalizarProcesso:
    @pytest.mark.parametrize("entrada,esperado_parcial", [
        ("0001686-52.2026.5.07.0003", "0001686-52.2026.5.07.0003"),
        ("processo/com/barras", "processo-com-barras"),
        ("proc:com:dois:pontos", "proc-com-dois-pontos"),
        ("  espacos  ", "espacos"),
    ])
    def test_normaliza_caracteres(self, entrada, esperado_parcial):
        """Normaliza caracteres inválidos para nomes de diretório."""
        result = CalculationStore._normalizar_processo(entrada)
        assert "/" not in result
        assert ":" not in result
        assert result == esperado_parcial
