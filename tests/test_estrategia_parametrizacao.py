"""Testes da FATIA 1 (captura) do aprendizado de parametrização por verba (Plano 2).

Garante que:
- a assinatura estrutural ignora valores/períodos e capta só o padrão;
- a captura faz upsert (agrupa cálculos com o mesmo padrão, conta ocorrências);
- padrões diferentes da MESMA verba viram linhas distintas;
- a captura é best-effort (não levanta com prévia malformada).
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest

from learning.estrategia_parametrizacao import (
    assinatura_estrutural,
    capturar_de_previa,
    listar_estrategias,
    montar_bloco_aprendizado,
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


def _verba(valor="CALCULADO", ocorr="MENSAL", base_tipo="HISTORICO_SALARIAL",
           composta=False, periodo="01/01/2024", nome="SALDO DE SALÁRIO"):
    return {
        "nome_pjecalc": nome,
        "nome_sentenca": nome.title(),
        "estrategia_preenchimento": "expresso_direto",
        "parametros": {
            "valor": valor,
            "caracteristica": "COMUM",
            "ocorrencia_pagamento": ocorr,
            "gerar_principal": "DEVIDO",
            "compor_principal": True,
            "periodo_inicio": periodo,
            "periodo_fim": "08/04/2026",
            "valor_devido": {"tipo": valor},
            "valor_pago": {"tipo": "INFORMADO"} if valor == "INFORMADO" else None,
            "formula_calculado": {
                "base_calculo": {
                    "tipo": base_tipo,
                    "bases_compostas": [{"verba": "X"}] if composta else [],
                },
                "divisor": {"tipo": "OUTRO_VALOR", "valor": 30},
            },
        },
    }


def test_assinatura_ignora_valores_e_periodos():
    a = assinatura_estrutural(_verba(periodo="01/01/2024")["parametros"])
    b = assinatura_estrutural(_verba(periodo="05/09/2025")["parametros"])
    # período diferente NÃO muda a assinatura (mesmo padrão estrutural)
    assert a == b
    assert a["valor"] == "CALCULADO"
    assert a["base_composta"] is False


def test_captura_agrupa_mesmo_padrao(db):
    capturar_de_previa("sess-1", {"verbas_principais": [_verba()]}, db)
    capturar_de_previa("sess-2", {"verbas_principais": [_verba(periodo="03/03/2025")]}, db)
    ests = listar_estrategias(db)
    # mesmo padrão estrutural → 1 linha, 2 cálculos, confiança subiu
    assert len(ests) == 1
    assert ests[0]["n_calculos"] == 2
    assert ests[0]["confianca"] > 0.5


def test_padroes_distintos_viram_linhas_distintas(db):
    # mesma verba, padrões diferentes (CALCULADO simples vs INFORMADO)
    capturar_de_previa("s1", {"verbas_principais": [_verba(valor="CALCULADO")]}, db)
    capturar_de_previa("s2", {"verbas_principais": [_verba(valor="INFORMADO")]}, db)
    ests = listar_estrategias(db)
    assert len(ests) == 2
    assert {e["assinatura"]["valor"] for e in ests} == {"CALCULADO", "INFORMADO"}


def test_captura_best_effort_nao_levanta(db):
    # prévia malformada / vazia não pode quebrar
    assert capturar_de_previa("s", {}, db) == 0
    assert capturar_de_previa("s", {"verbas_principais": "nao-lista"}, db) == 0
    assert capturar_de_previa("s", {"verbas_principais": [{"sem": "params"}]}, db) == 0


def test_base_composta_distingue_padrao(db):
    capturar_de_previa("s1", {"verbas_principais": [_verba(composta=False)]}, db)
    capturar_de_previa("s2", {"verbas_principais": [_verba(composta=True)]}, db)
    ests = listar_estrategias(db)
    assert len(ests) == 2  # composta vs não-composta = padrões distintos


def test_injecao_noop_enquanto_padrao_nao_reincide(db):
    # FATIA 2: um único cálculo (n=1, conf=0.5) NÃO injeta nada — o sistema
    # acumula em silêncio até o padrão se provar.
    capturar_de_previa("s1", {"verbas_principais": [_verba()]}, db)
    assert montar_bloco_aprendizado(db) is None


def test_injecao_dispara_quando_padrao_reincide(db):
    # mesmo padrão em 2 cálculos distintos → n=2, conf=0.6 → injeta
    capturar_de_previa("s1", {"verbas_principais": [_verba()]}, db)
    capturar_de_previa("s2", {"verbas_principais": [_verba(periodo="03/03/2025")]}, db)
    bloco = montar_bloco_aprendizado(db)
    assert bloco is not None
    assert "SALDO DE SALÁRIO" in bloco
    # framing advisory obrigatório — a sentença e os invariantes prevalecem
    assert "senten" in bloco.lower() and "prevalece" in bloco.lower()
    assert "invariantes" in bloco.lower()
    assert "2 cálculos" in bloco


def test_injecao_respeita_limiar_customizado(db):
    capturar_de_previa("s1", {"verbas_principais": [_verba()]}, db)
    # com limiar_n=1 e limiar_conf=0.5, o padrão n=1 já qualifica
    bloco = montar_bloco_aprendizado(db, limiar_conf=0.5, limiar_n=1)
    assert bloco is not None and "SALDO DE SALÁRIO" in bloco


def test_reflexos_no_nivel_da_verba_entram_na_assinatura(db):
    # reflexos vivem em v["reflexos"] (NÃO em parametros) — devem ser captados
    v = _verba(nome="DIFERENÇA SALARIAL")
    v["reflexos"] = [
        {"expresso_reflex_alvo": "FÉRIAS + 1/3 SOBRE DIFERENÇA SALARIAL"},
        {"expresso_reflex_alvo": "13º SALÁRIO SOBRE DIFERENÇA SALARIAL"},
    ]
    capturar_de_previa("s1", {"verbas_principais": [v]}, db)
    ests = listar_estrategias(db)
    assert len(ests) == 1
    refs = ests[0]["assinatura"]["reflexos"]
    assert len(refs) == 2
    assert any("ferias" in r for r in refs)
    # verba SEM reflexos = padrão distinto da mesma verba COM reflexos
    capturar_de_previa("s2", {"verbas_principais": [_verba(nome="DIFERENÇA SALARIAL")]}, db)
    assert len(listar_estrategias(db)) == 2


# ── FATIA 3 — ciclo de confiança (snapshot extração × prévia confirmada) ──────

from learning.estrategia_parametrizacao import snapshot_assinaturas


def test_snapshot_assinaturas_mapeia_verbas(db):
    prev = {"verbas_principais": [_verba(nome="SALDO DE SALÁRIO"),
                                  _verba(nome="MULTA 477", valor="INFORMADO")]}
    snap = snapshot_assinaturas(prev)
    assert set(snap.keys()) == {"saldo de salario", "multa 477"}
    assert all(isinstance(fp, str) for fp in snap.values())


def test_fatia3_validado_sobe_confianca(db):
    # 1ª captura cria o padrão (conf 0.5). 2ª captura, com snapshot == confirmado
    # (usuário NÃO alterou), sobe a confiança.
    prev = {"verbas_principais": [_verba(nome="DIFERENÇA SALARIAL")]}
    snap = snapshot_assinaturas(prev)
    capturar_de_previa("s1", prev, db, snapshot=snap)
    capturar_de_previa("s2", prev, db, snapshot=snap)
    ests = listar_estrategias(db)
    assert len(ests) == 1
    assert ests[0]["confianca"] > 0.5  # validado → +0.1


def test_fatia3_usuario_altera_penaliza_extraido(db):
    # Extração produziu CALCULADO (snapshot), mas o usuário confirmou INFORMADO.
    # O padrão CALCULADO (extraído, rejeitado) deve ser penalizado; o INFORMADO
    # (escolha do usuário) é capturado.
    extraido = {"verbas_principais": [_verba(nome="SALDO DE SALÁRIO", valor="CALCULADO")]}
    snap = snapshot_assinaturas(extraido)
    # primeiro, semear o padrão CALCULADO com confiança elevada (como se já
    # tivesse sido visto antes)
    capturar_de_previa("seed1", extraido, db, snapshot=snap)
    capturar_de_previa("seed2", extraido, db, snapshot=snap)
    conf_antes = {e["assinatura"]["valor"]: e["confianca"] for e in listar_estrategias(db)}
    # agora o usuário ALTERA para INFORMADO (confirmado != snapshot)
    confirmado = {"verbas_principais": [_verba(nome="SALDO DE SALÁRIO", valor="INFORMADO")]}
    capturar_de_previa("s3", confirmado, db, snapshot=snap)
    ests = {e["assinatura"]["valor"]: e for e in listar_estrategias(db)}
    assert "INFORMADO" in ests  # escolha do usuário capturada
    assert "CALCULADO" in ests  # padrão extraído continua, mas penalizado
    assert ests["CALCULADO"]["confianca"] < conf_antes["CALCULADO"]


def test_fatia3_verba_removida_penaliza(db):
    # Extração trouxe FÉRIAS+1/3 standalone (alucinação); usuário REMOVEU.
    # O padrão FÉRIAS deve ser penalizado.
    extraido = {"verbas_principais": [
        _verba(nome="SALDO DE SALÁRIO"),
        _verba(nome="FÉRIAS + 1/3"),
    ]}
    snap = snapshot_assinaturas(extraido)
    capturar_de_previa("e1", extraido, db, snapshot=snap)
    capturar_de_previa("e2", extraido, db, snapshot=snap)
    conf_ferias_antes = next(e["confianca"] for e in listar_estrategias(db)
                             if "RIAS" in e["nome_verba"].upper())
    # confirmada SEM a férias (usuário removeu)
    confirmado = {"verbas_principais": [_verba(nome="SALDO DE SALÁRIO")]}
    capturar_de_previa("c1", confirmado, db, snapshot=snap)
    conf_ferias_depois = next(e["confianca"] for e in listar_estrategias(db)
                              if "RIAS" in e["nome_verba"].upper())
    assert conf_ferias_depois < conf_ferias_antes


def test_fatia3_sem_snapshot_mantem_comportamento(db):
    # Sem snapshot → comportamento antigo (reincidência sobe confiança), sem erro
    prev = {"verbas_principais": [_verba(nome="13º SALÁRIO")]}
    capturar_de_previa("a", prev, db)
    capturar_de_previa("b", prev, db)
    ests = listar_estrategias(db)
    assert len(ests) == 1 and ests[0]["confianca"] > 0.5
