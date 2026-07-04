# tests/test_pjc_conflito.py — Plano 3, FATIA 4: diálogo de conflito de aprendizado
#
# Fluxo EXCEPCIONAL: nova correção de PJC definitivo CONTRADIZ regra consolidada
# (mesma verba+campo, valor divergente, confiança ≥ 0.6) →
#   • NÃO cria regra concorrente; abre pendência de explicação;
#   • usuário explica → LLM avalia → compreendida (refina condições + cria nova
#     regra) OU nova pergunta (loop até compreensão plena);
#   • regra NÃO consolidada (confiança < 0.6) NÃO dispara o fluxo (excepcional).
#
# LLM mockado — sem rede.

from __future__ import annotations

import json

import pytest

from learning.pjc_aprendizado import analisar_diff
from learning.pjc_conflito import (
    carregar_conflito,
    listar_conflitos,
    responder_conflito,
)


@pytest.fixture()
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from infrastructure.database import Base

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=eng)
    Session = sessionmaker(bind=eng)
    s = Session()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    import learning.pjc_aprendizado as PA
    import learning.pjc_conflito as PC
    monkeypatch.setattr(PA, "_APRENDIZADO_DIR", tmp_path)
    monkeypatch.setattr(PC, "_CONFLITOS_DIR", tmp_path / "conflitos")
    yield tmp_path


class _FakeOrchestrator:
    def __init__(self, resposta):
        self.resposta = resposta
        self.prompts = []

    def complete(self, task_type, prompt, **kw):
        self.prompts.append(prompt)
        return self.resposta


def _rel_diff(sessao, para="200"):
    return {
        "sessao_id": sessao,
        "resumo": {"campos_alterados": 1, "entidades_adicionadas_removidas": 0,
                   "identicos": False},
        "parametros_calculo": [],
        "verbas": {"adicionadas": [], "removidas": [], "alteradas": [
            {"nome": "HORAS EXTRAS 50%",
             "campos": [{"campo": "formula.FormulaCalculada.divisor.Divisor.outroValor",
                         "de": "220", "para": para}]}]},
        "reflexos": {"adicionadas": [], "removidas": [], "alteradas": []},
        "historicos": {"adicionadas": [], "removidas": [], "alteradas": []},
        "secoes": {},
    }


def _resposta_llm(para="200", condicao="quando a jornada for X"):
    return {"regras": [{
        "verba": "HORAS EXTRAS 50%",
        "campo": "formula.FormulaCalculada.divisor.Divisor.outroValor",
        "de": "220", "para": para,
        "condicao": condicao,
        "acao": f"usar divisor {para} na HORAS EXTRAS 50%",
        "generalizavel": True, "justificativa": "carga horária",
    }], "resumo": ""}


def _preparar(tmp_path, sessao, para="200"):
    (tmp_path / f"{sessao}_diff.json").write_text(
        json.dumps(_rel_diff(sessao, para), ensure_ascii=False), encoding="utf-8")


def _consolidar_regra(db, tmp_path, para="180"):
    """Cria uma regra consolidada (confiança 0.6) via análise normal."""
    _preparar(tmp_path, "s1", para)
    analisar_diff("s1", db, orchestrator=_FakeOrchestrator(
        _resposta_llm(para, "quando a jornada for 12x36")))
    from infrastructure.database import RegrasAprendidas
    return db.query(RegrasAprendidas).one()


def test_conflito_detectado_abre_pendencia_e_nao_cria_regra(db, _dirs):
    from infrastructure.database import RegrasAprendidas
    _consolidar_regra(db, _dirs, para="180")  # consolidada: divisor 180 (0.6)

    # novo PJC definitivo com divisor DIVERGENTE (200) → conflito
    _preparar(_dirs, "s2", "200")
    out = analisar_diff("s2", db, orchestrator=_FakeOrchestrator(_resposta_llm("200")))
    assert out["conflitos_abertos"] == 1 and out["regras_novas"] == 0, (
        "conflito com consolidada NÃO pode criar regra concorrente às cegas")
    assert "conflito" in out["resumo"].lower()
    assert db.query(RegrasAprendidas).count() == 1, "só a consolidada existe"

    pend = listar_conflitos()
    assert len(pend) == 1
    cf = pend[0]
    assert cf["status"] == "aguardando_explicacao"
    assert cf["nova_correcao"]["para"] == "200"
    assert cf["regra_existente"]["exemplo"]["para"] == "180"
    assert "particularidade" in cf["pergunta_atual"].lower()


def test_regra_nao_consolidada_nao_dispara_conflito(db, _dirs):
    from infrastructure.database import RegrasAprendidas
    r = _consolidar_regra(db, _dirs, para="180")
    r.confianca = 0.4  # NÃO consolidada
    db.commit()
    _preparar(_dirs, "s2", "200")
    out = analisar_diff("s2", db, orchestrator=_FakeOrchestrator(_resposta_llm("200")))
    assert out["conflitos_abertos"] == 0 and out["regras_novas"] == 1, (
        "fluxo de conflito é EXCEPCIONAL — só contra regra consolidada")


def test_dialogo_explicacao_insuficiente_gera_nova_pergunta(db, _dirs):
    _consolidar_regra(db, _dirs, para="180")
    _preparar(_dirs, "s2", "200")
    analisar_diff("s2", db, orchestrator=_FakeOrchestrator(_resposta_llm("200")))
    cf = listar_conflitos()[0]

    orch = _FakeOrchestrator({"compreendida": False,
                              "pergunta": "Qual era a carga horária semanal do contrato?"})
    res = responder_conflito(cf["id"], "foi diferente neste caso", db, orchestrator=orch)
    assert res["status"] == "aguardando_explicacao"
    assert "carga horária" in res["pergunta"]
    # a troca ficou registrada e a pergunta atual mudou (loop continua)
    cf2 = carregar_conflito(cf["id"])
    assert len(cf2["trocas"]) == 1
    assert cf2["trocas"][0]["resposta"] == "foi diferente neste caso"
    assert cf2["pergunta_atual"] == "Qual era a carga horária semanal do contrato?"
    # o diálogo anterior vai ao LLM na próxima rodada
    res2 = responder_conflito(cf["id"], "contrato de 200h mensais", db, orchestrator=orch)
    assert "foi diferente neste caso" in orch.prompts[1]


def test_dialogo_compreensao_plena_refina_regras(db, _dirs):
    from infrastructure.database import RegrasAprendidas
    antiga = _consolidar_regra(db, _dirs, para="180")
    _preparar(_dirs, "s2", "200")
    analisar_diff("s2", db, orchestrator=_FakeOrchestrator(_resposta_llm("200")))
    cf = listar_conflitos()[0]

    orch = _FakeOrchestrator({
        "compreendida": True,
        "refinamento": {
            "condicao_regra_existente": "quando a jornada for 12x36 (carga 180h)",
            "nova_regra": {"condicao": "quando o contrato previr carga de 200h mensais",
                           "acao": "usar divisor 200 na HORAS EXTRAS 50%",
                           "generalizavel": True},
            "corrigir_regra_existente": None,
            "observacao": "Divisor segue a carga contratual: 180h→180, 200h→200.",
        },
    })
    res = responder_conflito(cf["id"], "este contrato tinha 200h mensais", db,
                             orchestrator=orch)
    assert res["status"] == "resolvido"
    assert "carga contratual" in (res["observacao"] or "")

    # regra antiga refinada + nova regra criada com gatilho explicado
    db.refresh(antiga)
    assert "12x36" in antiga.condicao
    regras = db.query(RegrasAprendidas).all()
    assert len(regras) == 2
    nova = [r for r in regras if r.id != antiga.id][0]
    assert "200h" in nova.condicao and nova.confianca == pytest.approx(0.7), (
        "nova regra nasce consolidada (0.7): a condição veio de explicação humana")
    # pendência resolvida — some da lista de pendentes
    assert listar_conflitos() == []
    assert carregar_conflito(cf["id"])["status"] == "resolvido"


def test_reincidencia_da_mesma_correcao_nao_e_conflito(db, _dirs):
    """Mesma (verba,campo,PARA) da consolidada → reconfirmação, não conflito."""
    _consolidar_regra(db, _dirs, para="180")
    _preparar(_dirs, "s2", "180")
    out = analisar_diff("s2", db, orchestrator=_FakeOrchestrator(_resposta_llm("180")))
    assert out["conflitos_abertos"] == 0 and out["regras_reconfirmadas"] == 1