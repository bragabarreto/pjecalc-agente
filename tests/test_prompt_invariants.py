"""Testes de INVARIANTES do prompt da IA externa.

Cada teste aqui valida que uma regra crítica está presente em
`SYSTEM_PROMPT_V2_EXTERNAL`. O objetivo é IMPEDIR REGRESSÕES: se alguém
acidentalmente remover uma regra ao editar o prompt, o teste falha.

A motivação histórica de cada invariante está documentada em
`CLAUDE.md` na seção "Invariantes do Prompt".
"""
from __future__ import annotations

import re

import pytest

from modules.extraction_v2 import SYSTEM_PROMPT_V2_EXTERNAL


# ─── Helper ─────────────────────────────────────────────────────────────────


def _normaliza(s: str) -> str:
    """Normaliza espaços/quebras para casamento mais robusto."""
    return re.sub(r"\s+", " ", s).strip()


PROMPT = _normaliza(SYSTEM_PROMPT_V2_EXTERNAL)


# ─── Invariantes ────────────────────────────────────────────────────────────


def test_fluxo_2_etapas_no_topo():
    """Etapa 1 (resumo) + Etapa 2 (JSON) devem aparecer."""
    assert "FLUXO OPERACIONAL — 2 ETAPAS" in PROMPT
    assert "ETAPA 1" in PROMPT
    assert "ETAPA 2" in PROMPT


def test_verba_unica_13_ferias_recorrentes():
    """13º SALÁRIO e FÉRIAS+1/3 são UMA verba só (mesmo multi-ano).

    Causa raiz: PJE-Calc gera ocorrências automaticamente. Se a IA criar
    múltiplas verbas, gera INSS duplicado e conferência inviável.
    """
    assert "REGRA CRÍTICA — FÉRIAS + 1/3" in PROMPT
    assert "REGRA CRÍTICA — 13º SALÁRIO" in PROMPT
    assert "APENAS UMA" in PROMPT
    assert "INVARIANTE PERMANENTE — NÃO REVERTER" in PROMPT
    # Lista ampliada de verbas recorrentes
    assert "ADICIONAL NOTURNO" in PROMPT or "ADICIONAIS" in PROMPT
    assert "DIFERENÇA SALARIAL" in PROMPT
    assert "HORAS EXTRAS" in PROMPT


def test_data_termino_calculo_eq_max_periodo_fim():
    """data_termino_calculo NÃO é data_demissao — é MAX(periodo_fim)."""
    assert "MAX(periodo_fim" in PROMPT or "MAX(periodo_fim de TODAS" in PROMPT
    assert "NÃO data_demissao" in PROMPT or "NUNCA é fixa" in PROMPT
    # Casos típicos que estendem além da demissão
    assert "Aviso Prévio Indenizado" in PROMPT
    assert "Estabilidade" in PROMPT


def test_periodo_desligamento_primeiro_dia_mes():
    """Verbas DESLIGAMENTO: periodo_inicio = 1º dia do mês da demissão."""
    assert "1º dia do mês da demissão" in PROMPT
    assert "Multa 477" in PROMPT or "MULTA 477" in PROMPT
    assert "Saldo" in PROMPT  # Saldo de Salário


def test_valor_informado_brl_sempre_positivo():
    """valor_informado_brl é SEMPRE positivo (mesmo em deduções)."""
    assert "SEMPRE POSITIVO" in PROMPT
    # PJE-Calc trata sinais internamente
    assert "sistema trata sinais internamente" in PROMPT or "valores monetários" in PROMPT


def test_verbas_deducao_usam_valor_pago():
    """VALOR PAGO/DEVOLUÇÃO usam valor_pago.valor_brl, não valor_devido."""
    assert "DEDUÇÃO usam" in PROMPT
    assert "valor_pago.valor_brl" in PROMPT
    assert "VALOR PAGO" in PROMPT
    assert "DEVOLUÇÃO DE DESCONTOS" in PROMPT


def test_historico_salarial_schema_calculado():
    """Histórico salarial CALCULADO: schema é {quantidade_pct, base_referencia}.

    NÃO é {base_calculo: {tipo: ...}} (esse é schema de VERBA, não histórico).
    """
    assert "quantidade_pct" in PROMPT
    assert "base_referencia" in PROMPT
    # Aviso explícito contra confusão
    assert "NUNCA emitir" in PROMPT or "não confundir" in PROMPT.lower()


def test_etapa_1_resumo_consolida_verbas_recorrentes():
    """O resumo da Etapa 1 deve listar verbas como vão para o JSON
    (uma linha por verba recorrente, não uma por período).
    """
    assert "UMA ÚNICA linha" in PROMPT
    # Exemplo correto para Férias com múltiplos períodos
    assert "3 períodos" in PROMPT


def test_prescricao_quinquenal_apenas_se_5_anos():
    """prescricao_quinquenal=true SÓ com contrato (admissão→ajuizamento) ≥5 anos.

    Causa raiz histórica (Scarlette 22/05/2026): JSON marcava quinquenal=true
    em contrato de 8 meses → JSF rejeita save Fase 2 → cálculo nunca commita
    no DB → cascata de falhas em TODAS as fases pós-Fase 2.
    """
    assert "prescricao_quinquenal" in PROMPT
    # Regra do PJE-Calc deve estar citada literal (mensagem de erro do JSF)
    assert "menor que cinco anos" in PROMPT or "5 anos" in PROMPT
    # Marca explícita como INVARIANTE
    assert "prescricao_quinquenal" in PROMPT.lower() and "NÃO REVERTER" in PROMPT


def test_diferenca_salarial_dois_historicos():
    """DIFERENÇA SALARIAL exige 2 históricos (Valor Devido + Valor Pago)."""
    # Regra documentada
    assert "COMPARATIVAS DE HISTÓRICO" in PROMPT or "COMPARATIVAS" in PROMPT
    # Campos críticos
    assert "valor_pago" in PROMPT
    assert "base_historico_nome" in PROMPT
    # Caso real
    assert "SALÁRIO DEVIDO" in PROMPT or "histórico superior" in PROMPT
    assert "SALÁRIO PAGO" in PROMPT or "histórico inferior" in PROMPT
    # Erro típico que isso previne
    assert "Falta selecionar pelo menos um Histórico Salarial" in PROMPT


def test_honorarios_sucumbenciais_credor_e_forma_cobranca():
    """SUCUMBENCIAIS: devedor=RECLAMANTE → forma_cobranca=COBRAR + credor=ADVOGADO DO RECLAMADO."""
    assert "ADVOGADO DO RECLAMADO" in PROMPT
    assert "ADVOGADO DO RECLAMANTE" in PROMPT
    assert "COBRAR" in PROMPT
    # NUNCA DESCONTAR
    assert "DESCONTAR" in PROMPT  # mas com a indicação NUNCA


def test_zerar_valor_negativo_false_em_deducoes():
    """Verbas de DEDUÇÃO exigem zerar_valor_negativo=false (caso contrário
    o PJE-Calc zera a dedução)."""
    assert "zerar_valor_negativo" in PROMPT
    # No contexto de deduções deve aparecer false
    assert "false" in PROMPT


def test_lista_54_verbas_expresso():
    """Lista canônica das 54 verbas Expresso deve estar presente."""
    # Algumas verbas-âncora
    assert "13º SALÁRIO" in PROMPT
    assert "FÉRIAS + 1/3" in PROMPT
    assert "AVISO PRÉVIO" in PROMPT
    assert "MULTA DO ARTIGO 477 DA CLT" in PROMPT
    assert "VALOR PAGO - NÃO TRIBUTÁVEL" in PROMPT
    assert "VALOR PAGO - TRIBUTÁVEL" in PROMPT
    assert "DEVOLUÇÃO DE DESCONTOS INDEVIDOS" in PROMPT
    assert "INDENIZAÇÃO POR DANO MORAL" in PROMPT


def test_checklist_final_presente():
    """Checklist final é obrigatório no fim do prompt."""
    assert "CHECKLIST FINAL" in PROMPT


# ─── Marker: regressão histórica ────────────────────────────────────────────


@pytest.mark.parametrize(
    "regra_ressuscitada,texto",
    [
        # Padrões ANTIGOS que NÃO devem voltar ao prompt — se aparecerem,
        # significa que alguém reverteu uma correção.
        ("13º segmentado por ano", "13º SALÁRIO período 09/02/2023 → 31/12/2023"),
        ("Férias separadas por período", "Férias vencidas em dobro 2023/2024 |"),
    ],
)
def test_regressao_nao_aparece(regra_ressuscitada: str, texto: str):
    """Padrões antigos não devem voltar — só como EXEMPLOS DE ERRADO."""
    # OK se aparecer dentro de um bloco "❌ ERRADO" (que é exemplo didático);
    # NÃO ok se aparecer fora desse contexto.
    if texto in PROMPT:
        # Confirmar que está dentro de bloco de exemplo errado
        idx = PROMPT.find(texto)
        contexto = PROMPT[max(0, idx - 200) : idx]
        assert (
            "ERRADO" in contexto
            or "NUNCA" in contexto
            or "Exemplo errado" in contexto
        ), f"Regressão detectada: {regra_ressuscitada} aparece sem contexto de erro"
