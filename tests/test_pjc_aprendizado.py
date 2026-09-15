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


# ── #80-CF — SENTENÇA DEFINITIVA (texto alterado no ajuste manual) ───────────

def test_cf_sentenca_definitiva_entra_no_prompt(db, tmp_path, monkeypatch):
    """#80-CF (pedido do usuário, 28/07/2026): quando o calculista ALTERA o
    texto da sentença durante o ajuste manual, o texto DEFINITIVO deve entrar
    no contexto da análise — senão o LLM compara o PJC corrigido com o título
    ANTIGO e aprende correções que decorrem da mudança do texto."""
    rel = _rel_diff("scf1", _campos_divisor())
    sent = tmp_path / "scf1.sentenca_definitiva.txt"
    sent.write_text("DISPOSITIVO: horas extras com divisor 180 (jornada 12x36).",
                    encoding="utf-8")
    rel["sentenca_definitiva"] = {"alterada": True, "origem": "texto colado",
                                  "chars": 58, "arquivo": str(sent)}
    _preparar_relatorio(tmp_path, monkeypatch, rel)
    orq = _FakeOrchestrator(_REGRA_LLM)
    analisar_diff("scf1", db, orchestrator=orq)
    prompt = orq.prompts[0]
    assert "SENTENÇA DEFINITIVA" in prompt, "texto definitivo não chegou ao prompt"
    assert "divisor 180 (jornada 12x36)" in prompt, "conteúdo da sentença nova ausente"
    assert "título executivo REAL" in prompt, "instrução de avaliar contra o texto novo ausente"


def test_cf_sem_alteracao_nao_polui_o_prompt(db, tmp_path, monkeypatch):
    """Sem alteração de texto o prompt segue como antes (contexto da prévia)."""
    rel = _rel_diff("scf2", _campos_divisor())
    rel["sentenca_definitiva"] = {"alterada": False, "origem": "não informada", "chars": 0}
    _preparar_relatorio(tmp_path, monkeypatch, rel)
    orq = _FakeOrchestrator(_REGRA_LLM)
    analisar_diff("scf2", db, orchestrator=orq)
    assert "SENTENÇA DEFINITIVA" not in orq.prompts[0]


def test_cf_correcao_por_mudanca_da_sentenca_nao_generaliza(db, tmp_path, monkeypatch):
    """Correção que decorre APENAS da mudança do texto não é erro da automação
    — nasce como caso-específico (abaixo do limiar de injeção), nunca como
    regra generalizável."""
    from infrastructure.database import RegrasAprendidas

    rel = _rel_diff("scf3", _campos_divisor())
    rel["sentenca_definitiva"] = {"alterada": True, "origem": "texto colado", "chars": 10}
    _preparar_relatorio(tmp_path, monkeypatch, rel)
    resposta = json.loads(json.dumps(_REGRA_LLM))
    resposta["regras"][0]["decorre_de_mudanca_da_sentenca"] = True
    resposta["regras"][0]["generalizavel"] = True  # LLM pode se enganar
    analisar_diff("scf3", db, orchestrator=_FakeOrchestrator(resposta))
    regra = db.query(RegrasAprendidas).filter(
        RegrasAprendidas.tipo_regra == "pjc_definitivo").first()
    assert regra is not None
    assert regra.confianca < LIMIAR_INJECAO, (
        "correção decorrente da mudança do texto não pode nascer injetável")


# ── #80-DP — resposta do LLM inválida NUNCA é silenciosa ─────────────────────
#
# 0001156-86 (15/09/2026): a análise devolveu `regras_novas=0, resumo=""` com
# `analisado_em` preenchido e NENHUM motivo — a resposta (JSON truncado pelo
# teto de 4096 tokens) virou str, `analisar_diff` a tratou como "sem regras"
# e o log de warning não chegava ao docker logs.

class _FakeOrchestratorSeq:
    """Devolve respostas em sequência (1ª chamada, reemissão…) e guarda kwargs."""
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.prompts, self.kwargs = [], []

    def complete(self, task_type, prompt, **kw):
        self.prompts.append(prompt)
        self.kwargs.append(kw)
        return self.respostas.pop(0) if self.respostas else self.respostas


def test_dp_resposta_nao_json_persiste_erro_e_resposta_bruta(db, tmp_path, monkeypatch):
    from learning.pjc_aprendizado import MAX_TOKENS_ANALISE
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("sdk1", _campos_divisor()))
    truncado = '{"regras": [{"verba": "HORAS EXTRAS 50%", "campo": "x", "de": "220", "para": "18'
    orq = _FakeOrchestratorSeq(truncado, truncado)
    out = analisar_diff("sdk1", db, orchestrator=orq)
    assert out["regras_novas"] == 0
    assert "erro" in out and "regras" in out["erro"], out
    assert "truncamento" in out["erro"]
    assert out["resposta_bruta"].startswith('{"regras"')
    # UMA reemissão estrita, e o teto de saída ampliado nas duas chamadas
    assert len(orq.prompts) == 2 and "Reemita SOMENTE" in orq.prompts[1]
    assert all(k.get("max_tokens") == MAX_TOKENS_ANALISE for k in orq.kwargs)
    assert MAX_TOKENS_ANALISE > 4096
    # persistido no relatório — o diagnóstico deixa de ser inferencial
    rel = json.loads((tmp_path / "sdk1_diff.json").read_text(encoding="utf-8"))
    assert rel["aprendizado"]["erro"] == out["erro"]
    assert rel["aprendizado"]["resposta_bruta"] == out["resposta_bruta"]
    assert rel["aprendizado"]["analisado_em"]


def test_dp_reemissao_recupera_resposta_valida(db, tmp_path, monkeypatch):
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("sdk2", _campos_divisor()))
    orq = _FakeOrchestratorSeq("texto solto", _REGRA_LLM)
    out = analisar_diff("sdk2", db, orchestrator=orq)
    assert out["regras_novas"] == 1 and "erro" not in out
    assert len(orq.prompts) == 2


def test_dp_excecao_da_chamada_llm_fica_no_relatorio(db, tmp_path, monkeypatch):
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("sdk3", _campos_divisor()))

    class _Explode:
        def complete(self, *a, **kw):
            raise RuntimeError("Todos os modelos falharam: 529 overloaded")

    out = analisar_diff("sdk3", db, orchestrator=_Explode())
    assert out["regras_novas"] == 0 and "529 overloaded" in out["erro"]
    rel = json.loads((tmp_path / "sdk3_diff.json").read_text(encoding="utf-8"))
    assert "529 overloaded" in rel["aprendizado"]["erro"], "antes: relatório ficava SEM 'aprendizado'"


def test_dp_reexecucao_nao_bonifica_o_ciclo_duas_vezes(db, tmp_path, monkeypatch):
    """Reanálise do MESMO diff: o ciclo de confiança já rodou na 1ª execução
    (+0.05 nas regras ativas) e não é idempotente."""
    from infrastructure.database import RegrasAprendidas
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("s1", _campos_divisor()))
    analisar_diff("s1", db, orchestrator=_FakeOrchestrator(_REGRA_LLM))
    r = db.query(RegrasAprendidas).one()

    # 1ª análise de OUTRO diff sem a correção → acerto (+0.05)
    _preparar_relatorio(tmp_path, monkeypatch, _rel_diff("s9", campos=None))
    out1 = analisar_diff("s9", db, orchestrator=_FakeOrchestrator({"regras": []}))
    db.refresh(r)
    assert out1["acertos"] == 1 and r.confianca == pytest.approx(0.65)

    # reexecução do MESMO diff → NÃO soma outro acerto; relata o anterior
    out2 = analisar_diff("s9", db, orchestrator=_FakeOrchestrator({"regras": []}),
                         reexecucao=True)
    db.refresh(r)
    assert out2["acertos"] == 1 and r.confianca == pytest.approx(0.65)


def test_dp_logs_do_app_chegam_ao_stdout_do_container():
    """REGRESSÃO: só o _BufferHandler no root desliga o lastResort do Python e
    NENHUM log stdlib do app chega ao `docker logs` (só o access log do
    uvicorn). O webapp instala um StreamHandler p/ stdout no root."""
    src = open("webapp.py", encoding="utf-8").read()
    assert "_instalar_log_stdout()" in src
    assert "logging.StreamHandler(_sys.stdout)" in src
    # e a reanálise tem endpoint próprio (reprocessa o diff + LLM em background)
    assert '/api/pjc-definitivo/{sessao_id}/reanalisar' in src
    assert "reprocessar_relatorio" in src


def test_dp_orquestrador_aceita_max_tokens():
    """`complete()`/`_call_claude()` aceitam `max_tokens` (teto de saída por
    tarefa) e o warning do except não usa kwargs de structlog (TypeError)."""
    import inspect
    from core.llm_orchestrator import LLMOrchestrator
    assert "max_tokens" in inspect.signature(LLMOrchestrator.complete).parameters
    assert "max_tokens" in inspect.signature(LLMOrchestrator._call_claude).parameters
    src = open("core/llm_orchestrator.py", encoding="utf-8").read()
    assert 'model=model_name,' not in src, "logger.warning com kwargs livres levanta TypeError"
    assert "stop_reason" in src, "truncamento pelo teto de saída deve ser logado"
