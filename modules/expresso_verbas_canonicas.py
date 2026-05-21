"""Lista canônica das 54 verbas de Lançamento Expresso do PJE-Calc Cidadão.

Fonte da verdade: query DB H2 em 2026-05-21:
    SELECT SNMVERBA FROM TBVERBA WHERE STPVERBA='P' ORDER BY SNMVERBA;

CRÍTICO: alguns nomes têm TRAILING SPACE (bug do DB oficial PJE-Calc).
Manter os nomes RAW para casar com td.textContent do checkbox Expresso.

Esta lista é IMUTÁVEL — qualquer mudança requer re-query do DB para
confirmar e atualização sincronizada de classification.py + extraction.py.
"""
from __future__ import annotations
from typing import Optional
import re
import unicodedata

# 54 verbas Principal (STPVERBA='P') — ordem alfabética conforme DB
VERBAS_EXPRESSO_CANONICAS: tuple[str, ...] = (
    "13º SALÁRIO",
    "ABONO PECUNIÁRIO",
    "ACORDO (MERA LIBERALIDADE)",
    "ACORDO (MULTA)",
    "ACORDO (VERBAS INDENIZATÓRIAS)",
    "ACORDO (VERBAS REMUNERATÓRIAS)",
    "ADICIONAL DE HORAS EXTRAS 50%",
    "ADICIONAL DE INSALUBRIDADE 10%",
    "ADICIONAL DE INSALUBRIDADE 20%",
    "ADICIONAL DE INSALUBRIDADE 40%",
    "ADICIONAL DE PERICULOSIDADE 30%",
    "ADICIONAL DE PRODUTIVIDADE 30%",
    "ADICIONAL DE RISCO 40%",
    "ADICIONAL DE SOBREAVISO",
    "ADICIONAL DE TRANSFERÊNCIA 25%",
    "ADICIONAL NOTURNO 20%",
    "AJUDA DE CUSTO",
    "AVISO PRÉVIO ",  # ⚠ TRAILING SPACE no DB oficial
    "CESTA BÁSICA",
    "COMISSÃO",
    "DEVOLUÇÃO DE DESCONTOS INDEVIDOS",
    "DIFERENÇA SALARIAL",
    "DIÁRIAS - INTEGRAÇÃO AO SALÁRIO",
    "DIÁRIAS - PAGAMENTO",
    "FERIADO EM DOBRO",
    "FÉRIAS + 1/3",
    "GORJETA",
    "GRATIFICAÇÃO DE FUNÇÃO",
    "GRATIFICAÇÃO POR TEMPO DE SERVIÇO",
    "HORAS EXTRAS 100%",
    "HORAS EXTRAS 50%",
    "HORAS IN ITINERE",
    "INDENIZAÇÃO ADICIONAL",
    "INDENIZAÇÃO PIS - ABONO SALARIAL",
    "INDENIZAÇÃO POR DANO ESTÉTICO",
    "INDENIZAÇÃO POR DANO MATERIAL",
    "INDENIZAÇÃO POR DANO MORAL",
    "INTERVALO INTERJORNADAS",
    "INTERVALO INTRAJORNADA",
    "MULTA CONVENCIONAL",
    "MULTA DO ARTIGO 477 DA CLT ",  # ⚠ TRAILING SPACE no DB oficial
    "PARTICIPAÇÃO NOS LUCROS OU RESULTADOS - PLR",
    "PRÊMIO PRODUÇÃO",
    "REPOUSO SEMANAL REMUNERADO (COMISSIONISTA)",
    "REPOUSO SEMANAL REMUNERADO EM DOBRO",
    "RESTITUIÇÃO / INDENIZAÇÃO DE DESPESA",
    "SALDO DE EMPREITADA",
    "SALDO DE SALÁRIO",
    "SALÁRIO MATERNIDADE",
    "SALÁRIO RETIDO",
    "TÍQUETE-ALIMENTAÇÃO",
    "VALE TRANSPORTE",
    "VALOR PAGO - NÃO TRIBUTÁVEL",
    "VALOR PAGO - TRIBUTÁVEL",
)

assert len(VERBAS_EXPRESSO_CANONICAS) == 54, (
    f"Expresso deve ter exatamente 54 verbas, achei {len(VERBAS_EXPRESSO_CANONICAS)}"
)


def _normalizar(nome: str) -> str:
    """Normalização agressiva para comparação.

    Trata: Unicode NFC, chars invisíveis (NBSP/ZWS/NNBSP), whitespace collapse,
    trim, uppercase, e remove acentos (para fuzzy match com IA imperfeita).
    """
    if not nome:
        return ""
    # NFC unicode
    s = unicodedata.normalize("NFC", nome)
    # Remove chars invisíveis
    s = re.sub(r"[ ​  ﻿]", " ", s)
    # Collapse whitespace + trim + upper
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def _normalizar_estrita(nome: str) -> str:
    """Normalização estrita para fuzzy match — usada como último recurso.

    Remove:
    - Acentos (Á → A, ç → C)
    - Espaços e hífens (todos)
    - Pontuação (., :, etc)
    - Abrevia ARTIGO/ART → ART (e PARÁGRAFO/PARÁGRAFO → PAR)
    """
    s = _normalizar(nome)
    # Remove acentos
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    # Abreviações comuns
    s = re.sub(r"\bARTIGO\b", "ART", s)
    s = re.sub(r"\bPARAGRAFO\b", "PAR", s)
    # Remove pontuação + whitespace + hífens
    s = re.sub(r"[\s\-\.\,\:\;]+", "", s)
    return s


# Lookup table para resolução rápida
_LOOKUP_NORMALIZADO: dict[str, str] = {
    _normalizar(v): v for v in VERBAS_EXPRESSO_CANONICAS
}
_LOOKUP_ESTRITO: dict[str, str] = {
    _normalizar_estrita(v): v for v in VERBAS_EXPRESSO_CANONICAS
}


def resolver_verba_expresso(nome_query: str) -> Optional[str]:
    """Retorna o nome RAW canônico (com trailing space se houver) da verba
    Expresso que casa com a query, ou None se não encontrar.

    Estratégias em cascata:
    1. Match exato após normalização (NFC + invisible chars + whitespace + upper)
    2. Match após remover espaços e hífens (lida com "MULTA-ART.477" vs "MULTA DO ARTIGO 477 DA CLT")

    Args:
        nome_query: nome da verba como gerado pela IA ou input do usuário

    Returns:
        Nome RAW canônico do DB (use como expresso_alvo) ou None.
    """
    if not nome_query:
        return None
    n = _normalizar(nome_query)
    if n in _LOOKUP_NORMALIZADO:
        return _LOOKUP_NORMALIZADO[n]
    e = _normalizar_estrita(nome_query)
    if e in _LOOKUP_ESTRITO:
        return _LOOKUP_ESTRITO[e]
    return None


def eh_verba_expresso(nome_query: str) -> bool:
    """True se a query é uma verba Expresso canônica."""
    return resolver_verba_expresso(nome_query) is not None
