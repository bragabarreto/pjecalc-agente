"""Testes do humanizador de erros da prévia (#80-AE)."""
import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

from modules.erro_previa_humanizer import (
    humanizar_validation_error, humanizar_incompleta, _nome_entidade, _campo_legivel,
)


def _validar_e_humanizar(payload):
    W = importlib.import_module("modules.webapp_v2")
    N = importlib.import_module("modules.json_normalizer")
    nd = N.normalize_v2_json(payload)
    try:
        W.PreviaCalculoV2.model_validate(nd)
        return None
    except Exception as e:
        return humanizar_validation_error(e, nd)


def _previa_base():
    """Prévia mínima VÁLIDA (para quebrar 1 verba isoladamente)."""
    import json
    p = json.loads((REPO_ROOT / "tests" / "fixtures_previa_min.json").read_text()) \
        if (REPO_ROOT / "tests" / "fixtures_previa_min.json").exists() else None
    return p


def test_nome_entidade_verba():
    payload = {"verbas_principais": [{"nome_pjecalc": "SALDO DE SALÁRIO"}]}
    assert "SALDO DE SALÁRIO" in _nome_entidade(("verbas_principais", 0, "parametros"), payload)
    assert "item 1" in _nome_entidade(("verbas_principais", 0), payload)


def test_campo_legivel_ignora_classes_do_union():
    # descarta nome de classe (ValorDevidoInformado), fica com o campo real
    loc = ("verbas_principais", 8, "parametros", "valor_devido",
           "ValorDevidoInformado", "valor_informado_brl")
    assert _campo_legivel(loc) == "valor_informado_brl"


def test_incompleta_gera_o_que_e_como():
    h = humanizar_incompleta(["Data de admissão", "Salário base"])
    assert "2 pendências" in h["titulo"]
    assert len(h["erros"]) == 2
    assert all(e["o_que"] and e["como_corrigir"] for e in h["erros"])


def test_humanizador_verba_informado_sem_valor():
    """Erro real: verba INFORMADO sem valor_devido>0 → mensagem clara + solução."""
    class _FakeErr(Exception):
        def errors(self):
            return [{"loc": ("verbas_principais", 1, "parametros"),
                     "msg": "Value error, ParametrosVerba: valor=INFORMADO exige "
                            "`valor_devido.valor_informado_brl > 0`.",
                     "type": "value_error"}]
    payload = {"verbas_principais": [
        {"nome_pjecalc": "SALDO"}, {"nome_pjecalc": "13º SALÁRIO"}]}
    h = humanizar_validation_error(_FakeErr(), payload)
    assert h["erros"], "deve ter ao menos 1 erro"
    e = h["erros"][0]
    assert "13º SALÁRIO" in e["entidade"] and "item 2" in e["entidade"]
    assert "INFORMADO" in e["o_que"] and "Valor Devido" in e["como_corrigir"]


def test_humanizador_nunca_levanta_em_exc_generica():
    h = humanizar_validation_error(ValueError("algo quebrou"), {})
    assert h["erros"] and h["titulo"]
    assert "algo quebrou" in h["tecnico"]


def test_wiring_confirmar_e_executar_usam_humanizador():
    src = (REPO_ROOT / "modules" / "webapp_v2.py").read_text(encoding="utf-8")
    assert src.count("humanizar_validation_error") >= 2, (
        "confirmar_previa E executar_v2_como_generator devem humanizar o erro")
    assert "humanizar_incompleta" in src
    tpl = (REPO_ROOT / "templates" / "previa_v2.html").read_text(encoding="utf-8")
    assert "mostrarErrosPrevia" in tpl and "det.humanizado" in tpl
