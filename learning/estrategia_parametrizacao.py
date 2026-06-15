"""learning/estrategia_parametrizacao.py — Plano 2, FATIA 1 (Captura).

Captura, por verba, COMO ela foi parametrizada num cálculo v2 exportado com
sucesso. Só ACUMULA o dataset (não injeta nada na extração ainda) — base para
as fatias seguintes (injeção + ciclo de confiança).

Fonte da verdade: a prévia v2 CONFIRMADA (a mesma que o bot aplicou). Para cada
verba em ``verbas_principais``, registra a assinatura ESTRUTURAL dos parâmetros
(valor/base/ocorrência/compor/divisor/valor_pago…) agrupando cálculos que
usaram o mesmo padrão e contando ocorrências.

Invariante: a captura NUNCA pode quebrar a automação. Toda a função é
best-effort — qualquer exceção é engolida e logada; o export segue normalmente.
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _normalizar(texto: str) -> str:
    """Remove acentos, minúsculas, colapsa espaços."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


def _get(d: Any, *path, default=None):
    """Acesso aninhado tolerante a dict/None."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def assinatura_estrutural(parametros: dict) -> dict:
    """Assinatura ESTRUTURAL do preenchimento (não os valores/períodos).

    Capta APENAS o que define o PADRÃO de parametrização — o que torna duas
    verbas "configuradas do mesmo jeito" — ignorando valores monetários,
    períodos e nomes específicos (que variam caso a caso). É a chave de
    agrupamento que revela o padrão dominante por verba.
    """
    p = parametros or {}
    base = p.get("formula_calculado", {}).get("base_calculo", {}) if isinstance(
        p.get("formula_calculado"), dict
    ) else {}
    divisor = _get(p, "formula_calculado", "divisor", default={}) or {}
    vp = p.get("valor_pago") or {}
    vd = p.get("valor_devido") or {}
    reflexos = p.get("reflexos") or []
    return {
        "valor": p.get("valor"),  # INFORMADO | CALCULADO
        "caracteristica": p.get("caracteristica"),
        "ocorrencia_pagamento": p.get("ocorrencia_pagamento"),
        "gerar_principal": p.get("gerar_principal"),
        "compor_principal": p.get("compor_principal"),
        "valor_devido_tipo": vd.get("tipo"),
        "base_tipo": base.get("tipo"),
        "base_composta": bool(base.get("bases_compostas")),
        "divisor_tipo": divisor.get("tipo"),
        "valor_pago_tipo": vp.get("tipo"),
        "reflexos": sorted(
            {_normalizar(r.get("expresso_reflex_alvo") or r.get("tipo") or "")
             for r in reflexos if isinstance(r, dict)}
        ),
    }


def _fingerprint(nome_norm: str, assinatura: dict) -> str:
    blob = nome_norm + "::" + json.dumps(assinatura, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _gatilho_contexto(verba: dict) -> dict:
    """Sinais contextuais mínimos da verba (para matching futuro)."""
    return {
        "nome_sentenca": verba.get("nome_sentenca"),
        "expresso_alvo": verba.get("expresso_alvo"),
        "estrategia": verba.get("estrategia_preenchimento"),
    }


def capturar_de_previa(
    sessao_id: str,
    previa: dict,
    db,
    versao_pjecalc: Optional[str] = None,
) -> int:
    """Registra a parametrização de cada verba da prévia v2 confirmada.

    Retorna o número de verbas capturadas. Best-effort: nunca levanta.
    """
    try:
        from infrastructure.database import EstrategiaParametrizacaoVerba
    except Exception as e:  # pragma: no cover
        logger.warning("captura estratégia: modelo indisponível (%s)", e)
        return 0

    verbas = (previa or {}).get("verbas_principais") or []
    if not isinstance(verbas, list) or not verbas:
        return 0

    capturadas = 0
    for v in verbas:
        if not isinstance(v, dict):
            continue
        nome = v.get("nome_pjecalc") or v.get("nome_sentenca")
        params = v.get("parametros")
        if not nome or not isinstance(params, dict):
            continue
        # Reflexos vivem no NÍVEL da verba (não dentro de parametros) — mesclar
        # para que a assinatura capte o padrão de reflexos e o painel recompute
        # consistente (fonte única no JSON persistido).
        params = {**params, "reflexos": v.get("reflexos") or []}
        nome_norm = _normalizar(nome)
        assin = assinatura_estrutural(params)
        fp = _fingerprint(nome_norm, assin)
        try:
            existente = (
                db.query(EstrategiaParametrizacaoVerba)
                .filter(
                    EstrategiaParametrizacaoVerba.nome_normalizado == nome_norm,
                    EstrategiaParametrizacaoVerba.assinatura == fp,
                )
                .first()
            )
            if existente:
                origens = existente.calculos_origem_list
                if sessao_id not in origens:
                    origens.append(sessao_id)
                    existente.n_calculos_origem = len(origens)
                    existente.calculos_origem = json.dumps(origens, ensure_ascii=False)
                    # confiança cresce com reincidência do padrão (cap 0.95)
                    existente.confianca = min(0.95, (existente.confianca or 0.5) + 0.1)
                # exemplar mais recente vira a referência
                existente.parametros = json.dumps(params, ensure_ascii=False)
                existente.gatilho_contexto = json.dumps(
                    _gatilho_contexto(v), ensure_ascii=False
                )
                existente.updated_at = datetime.utcnow()
            else:
                novo = EstrategiaParametrizacaoVerba(
                    nome_verba=nome,
                    nome_normalizado=nome_norm,
                    assinatura=fp,
                    gatilho_contexto=json.dumps(_gatilho_contexto(v), ensure_ascii=False),
                    estrategia_preenchimento=v.get("estrategia_preenchimento"),
                    parametros=json.dumps(params, ensure_ascii=False),
                    confianca=0.5,
                    n_calculos_origem=1,
                    calculos_origem=json.dumps([sessao_id], ensure_ascii=False),
                    versao_pjecalc=versao_pjecalc,
                )
                db.add(novo)
            capturadas += 1
        except Exception as e:
            logger.warning("captura estratégia verba '%s': %s", nome, e)
            continue

    try:
        db.commit()
    except Exception as e:
        logger.warning("captura estratégia: commit falhou (%s)", e)
        try:
            db.rollback()
        except Exception:
            pass
        return 0

    if capturadas:
        logger.info(
            "Aprendizado v2: %d verba(s) capturada(s) da sessão %s",
            capturadas, sessao_id,
        )
    return capturadas


def listar_estrategias(db, limite: int = 500) -> list[dict]:
    """Lista os padrões aprendidos, agrupados por verba (para o painel)."""
    try:
        from infrastructure.database import EstrategiaParametrizacaoVerba
    except Exception:
        return []
    try:
        rows = (
            db.query(EstrategiaParametrizacaoVerba)
            .order_by(
                EstrategiaParametrizacaoVerba.nome_normalizado,
                EstrategiaParametrizacaoVerba.n_calculos_origem.desc(),
            )
            .limit(limite)
            .all()
        )
    except Exception as e:
        logger.warning("listar_estrategias: %s", e)
        return []

    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "nome_verba": r.nome_verba,
                "estrategia": r.estrategia_preenchimento,
                "assinatura": json.loads(
                    json.dumps(assinatura_estrutural(r.parametros_dict))
                ),
                "n_calculos": r.n_calculos_origem,
                "confianca": round(r.confianca or 0.0, 2),
                "gatilho": r.gatilho_dict,
                "parametros": r.parametros_dict,
                "atualizado_em": r.updated_at.isoformat() if r.updated_at else None,
            }
        )
    return out


# ── FATIA 2 — injeção: bloco de hints aprendidos para a extração ──────────────

# Só injeta padrões REINCIDENTES (vistos em ≥2 cálculos, confiança já elevada).
# Enquanto um padrão tem n=1/conf=0.5 ele NÃO é injetado → o sistema acumula
# silenciosamente e só passa a influenciar a extração quando o padrão se prova.
LIMIAR_CONF = 0.6
LIMIAR_N = 2


def _resumo_assinatura(a: dict) -> str:
    partes = []
    for k in ("valor", "caracteristica", "ocorrencia_pagamento", "gerar_principal",
              "base_tipo", "valor_pago_tipo"):
        v = a.get(k)
        if v not in (None, "", False):
            partes.append(f"{k}={v}")
    if a.get("base_composta"):
        partes.append("base_composta=true")
    if a.get("reflexos"):
        partes.append("reflexos=[" + ", ".join(a["reflexos"]) + "]")
    return ", ".join(partes)


def montar_bloco_aprendizado(
    db, limiar_conf: float = LIMIAR_CONF, limiar_n: int = LIMIAR_N, top_n: int = 30
) -> Optional[str]:
    """Bloco markdown com padrões REINCIDENTES de parametrização, para injetar
    como referência na extração (Etapa 2). Retorna None se não há padrão
    qualificado — nesse caso NADA é injetado (no-op). Best-effort."""
    try:
        from infrastructure.database import EstrategiaParametrizacaoVerba
    except Exception:
        return None
    try:
        rows = (
            db.query(EstrategiaParametrizacaoVerba)
            .filter(
                EstrategiaParametrizacaoVerba.confianca >= limiar_conf,
                EstrategiaParametrizacaoVerba.n_calculos_origem >= limiar_n,
            )
            .order_by(
                EstrategiaParametrizacaoVerba.n_calculos_origem.desc(),
                EstrategiaParametrizacaoVerba.confianca.desc(),
            )
            .limit(top_n)
            .all()
        )
    except Exception as e:
        logger.warning("montar_bloco_aprendizado: %s", e)
        return None

    if not rows:
        return None

    linhas = []
    for r in rows:
        resumo = _resumo_assinatura(assinatura_estrutural(r.parametros_dict))
        if not resumo:
            continue
        linhas.append(
            f"- **{r.nome_verba}** (visto em {r.n_calculos_origem} cálculos, "
            f"confiança {r.confianca:.2f}): {resumo}."
        )
    if not linhas:
        return None

    return (
        "# PADRÕES APRENDIDOS DE PARAMETRIZAÇÃO (referência de cálculos anteriores)\n\n"
        "Os padrões abaixo de PREENCHIMENTO por verba se repetiram e foram "
        "confirmados em cálculos anteriores revisados e exportados com sucesso. "
        "Trate-os como DEFAULT da verba correspondente — MAS apenas como "
        "referência:\n"
        "- A **sentença deste caso** SEMPRE prevalece (períodos, valores, base, "
        "se a verba é devida, fração deferida).\n"
        "- Os **invariantes e regras do prompt acima** SEMPRE prevalecem em caso "
        "de conflito.\n"
        "- Aplique o padrão APENAS quando a verba correspondente aparecer nesta "
        "sentença e o caso for compatível; ignore os demais.\n\n"
        + "\n".join(linhas)
    )
