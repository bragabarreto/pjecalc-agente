# tests/test_pjc_aprendizado.py — Plano 3 do Learning Engine (FATIAS 2 e 3)
#
# Valida a análise LLM do diff PJC gerado ↔ definitivo:
#   FATIA 2: regras persistidas em RegrasAprendidas (tipo_regra='pjc_definitivo'),
#     dedup por (verba,campo,para) com reconfirmação (+0.1), confiança inicial
#     0.6 (generalizável) / 0.4 (caso específico).
#   FATIA 3: ciclo de confiança (correção não repetida → acerto; piso arquiva)
#     + bloco de injeção (só regras ativas com confiança ≥ 0.6) no canal da
#     extração (Etapa 2, junto do Plano 2).
#
# O LLM é mockado (orchestrator fake) — sem chamadas de rede.

from __future__ import annotations

import json

import pytest

from learning.pjc_aprendizado import (
    LIMIAR_INJECAO,
    analisar_diff,
    ciclo_confianca_pjc,
    montar_bloco_pjc_definitivo,
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


class _FakeOrchestrator:
    def __init__(self, resposta):
        self.resposta = resposta
        self.prompts = []

    def complete(self, task_type, prompt, **kw):
        self.prompts.append(prompt)
        return self.resposta


def _rel_diff(sessao="s1", campos=None, identicos=False):
    """Relatório de diff mínimo no formato do pjc_diff."""
    alteradas = []
    if campos:
        alteradas = [{"nome": "HORAS EXTRAS 50%", "campos": campos}]
    return {
        "sessao_id": sessao,
        "resumo": {"campos_alterados": len(campos or []),
                   "entidades_adicionadas_removidas": 0,
                   "identicos": identicos},
        "parametros_calculo": [],
        "verbas": {"adicionadas": [], "removidas": [], "alteradas": alteradas},
        "reflexos": {"adicionadas": [], "removidas": [], "alteradas": []},
        "historicos": {"adicionadas": [], "removidas": [], "alteradas": []},
        "secoes": {},
    }


def _preparar_relatorio(tmp_path, monkeypatch, rel):
    """Persiste o relatório onde o módulo procura (dir monkeypatched)."""
    import learning.pjc_aprendizado as PA
    monkeypatch.setattr(PA, "_APRENDIZADO_DIR", tmp_path)
    (tmp_path / f"{rel['sessao_id']}_diff.json").write_text(
        json.dumps(rel, ensure_ascii=False), encoding="utf-8")


_REGRA_LLM = {
    "regras": [{
        "verba": "HORAS EXTRAS 50%",
        "campo": "formula.FormulaCalculada.divisor.Divisor.outroValor",
        "de": "220", "para": "180",
        "condicao": "quando a jornada apurada for 12x36 (carga mensal 180h)",
        "acao": "usar divisor 180 na verba HORAS EXTRAS 50%",
        "generalizavel": True,
        "justificativa": "divisor deve refletir a carga horária contratual",
    }],
    "resumo": "Divisor de HE deve seguir a carga da escala.",
}


def _campos_divisor():
    return [{"campo": "formula.FormulaCalculada.divisor.Divisor.outroValor",
             "de": "220", "para": "180"}]


def test_fatia2_cria_regra_e_reconfirma_em_novo_calculo(db, tmp_path, monkeypatch):
    from infrastructure.database import RegrasAprendidas

    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("s1", _campos_divisor()))
    orch = _FakeOrchestrator(_REGRA_LLM)
    out = analisar_diff("s1", db, orchestrator=orch)
    assert out["regras_novas"] == 1
    # contexto do diff chegou ao LLM
    assert "divisor" in orch.prompts[0]

    r = db.query(RegrasAprendidas).filter_by(tipo_regra="pjc_definitivo").one()
    assert r.confianca == pytest.approx(0.6), "generalizável nasce injetável (0.6)"
    assert r.ativa and "180" in r.acao
    exs = json.loads(r.exemplos_json)
    assert exs[0]["sessao_id"] == "s1" and exs[0]["campo"].endswith("outroValor")

    # MESMA correção num 2º cálculo → reconfirmação (+0.1), não regra nova
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("s2", _campos_divisor()))
    out2 = analisar_diff("s2", db, orchestrator=_FakeOrchestrator(_REGRA_LLM))
    assert out2["regras_novas"] == 0 and out2["regras_reconfirmadas"] == 1
    db.refresh(r)
    assert r.confianca == pytest.approx(0.7)
    assert len(json.loads(r.exemplos_json)) == 2


def test_fatia2_regra_caso_especifico_nasce_abaixo_do_limiar(db, tmp_path, monkeypatch):
    from infrastructure.database import RegrasAprendidas
    resposta = {"regras": [{**_REGRA_LLM["regras"][0], "generalizavel": False}],
                "resumo": ""}
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("s1", _campos_divisor()))
    analisar_diff("s1", db, orchestrator=_FakeOrchestrator(resposta))
    r = db.query(RegrasAprendidas).one()
    assert r.confianca == pytest.approx(0.4) and r.confianca < LIMIAR_INJECAO, (
        "regra de caso específico NÃO pode ser injetada até reincidir")


def test_fatia3_ciclo_confianca_acerto_e_arquivamento(db, tmp_path, monkeypatch):
    from infrastructure.database import RegrasAprendidas
    # regra existente de um cálculo anterior (s1)
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("s1", _campos_divisor()))
    analisar_diff("s1", db, orchestrator=_FakeOrchestrator(_REGRA_LLM))
    r = db.query(RegrasAprendidas).one()

    # novo PJC definitivo (s3) SEM a correção do divisor → a automação acertou
    acertos = ciclo_confianca_pjc(db, "s3", _rel_diff("s3", campos=None))
    assert acertos == 1
    db.refresh(r)
    assert r.acertos == 1 and r.confianca == pytest.approx(0.65)

    # diff idêntico via analisar_diff também registra acerto (sem LLM)
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("s4", identicos=True))
    out = analisar_diff("s4", db, orchestrator=_FakeOrchestrator({"regras": []}))
    assert out["acertos"] == 1 and "idêntico" in out["resumo"]

    # piso: regra com confiança baixa é arquivada no ciclo
    r.confianca = 0.15
    db.commit()
    ciclo_confianca_pjc(db, "s5", _rel_diff("s5", campos=None))
    db.refresh(r)
    assert r.ativa is False, "confiança < 0.2 deve arquivar a regra"


def test_fatia3_bloco_injecao_respeita_limiar(db, tmp_path, monkeypatch):
    from infrastructure.database import RegrasAprendidas
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("s1", _campos_divisor()))
    analisar_diff("s1", db, orchestrator=_FakeOrchestrator(_REGRA_LLM))

    bloco = montar_bloco_pjc_definitivo(db)
    assert bloco and "PJCs DEFINITIVOS" in bloco and "divisor 180" in bloco
    assert "sentença deste caso" in bloco, "guardrail: sentença sempre prevalece"
    # aplicação registrada (métrica)
    r = db.query(RegrasAprendidas).one()
    assert r.aplicacoes == 1

    # abaixo do limiar → no-op
    r.confianca = 0.4
    db.commit()
    assert montar_bloco_pjc_definitivo(db) is None

    # canal da extração (Etapa 2) chama o bloco do Plano 3
    src = open("modules/webapp_extracao.py", encoding="utf-8").read()
    assert "montar_bloco_pjc_definitivo" in src, (
        "REGRESSÃO Plano 3 FATIA 3: bloco de PJC definitivo fora do canal de injeção")


def test_fatia2_best_effort_nao_levanta(db, tmp_path, monkeypatch):
    # relatório ausente → retorna zeros, sem exceção
    import learning.pjc_aprendizado as PA
    monkeypatch.setattr(PA, "_APRENDIZADO_DIR", tmp_path)
    out = analisar_diff("inexistente", db, orchestrator=_FakeOrchestrator({}))
    assert out == {"regras_novas": 0, "regras_reconfirmadas": 0, "acertos": 0,
                   "conflitos_abertos": 0, "resumo": ""}

    # LLM retornando lixo → sem regra, sem exceção
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("s1", _campos_divisor()))
    out2 = analisar_diff("s1", db, orchestrator=_FakeOrchestrator("texto solto"))
    assert out2["regras_novas"] == 0
