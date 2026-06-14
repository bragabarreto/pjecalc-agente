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
