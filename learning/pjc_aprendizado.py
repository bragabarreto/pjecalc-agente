# learning/pjc_aprendizado.py — Plano 3 do Learning Engine (FATIAS 2 e 3)
#
# FATIA 2 — análise LLM do diff PJC gerado ↔ PJC definitivo (learning/pjc_diff):
#   cada correção manual detectada vira uma REGRA candidata em RegrasAprendidas
#   (tipo_regra='pjc_definitivo'), com a unidade de aprendizado (verba, campo,
#   contexto) — nunca "tipo de processo" (cálculos são misturas de verbas).
#
# FATIA 3 — injeção + ciclo de confiança:
#   • montar_bloco_pjc_definitivo(db) devolve o bloco markdown p/ a extração
#     (Etapa 2), no MESMO canal do Plano 2 (montar_bloco_aprendizado).
#   • ciclo_confianca_pjc(): a cada novo PJC definitivo, regras cuja correção
#     NÃO se repetiu (a automação acertou) ganham confiança; a reincidência da
#     MESMA correção reconfirma a regra (dedup +0.1); confiança < 0.2 arquiva.
#
# Regras nascem com confiança 0.6 quando o LLM as classifica GENERALIZÁVEIS
# (injetáveis de imediato) e 0.4 quando específicas do caso (só entram no
# prompt se reincidirem). A sentença do caso e os invariantes do prompt SEMPRE
# prevalecem sobre regra aprendida.
#
# Invariante: TODO o fluxo é best-effort — falha de aprendizado NUNCA pode
# quebrar upload/automação. Exceções são engolidas e logadas.

from __future__ import annotations

import json
import logging
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_APRENDIZADO_DIR = Path("data/calculations/aprendizado_pjc")

# Confiança inicial e ciclo
_CONF_GENERALIZAVEL = 0.6   # injetável de imediato
_CONF_CASO = 0.4            # só injeta se reincidir
_CONF_REINCIDENCIA = 0.1    # mesma correção em novo PJC definitivo
_CONF_ACERTO = 0.05         # regra aplicada e correção NÃO se repetiu
_CONF_PISO_ARQUIVO = 0.2    # abaixo disso, ativa=False
_CONF_TETO = 0.95

LIMIAR_INJECAO = 0.6


def _norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    sem = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sem.lower().split())


_SYSTEM_PROMPT = """Você é um especialista em Direito do Trabalho e no PJE-Calc.

Um cálculo foi gerado automaticamente (a partir da sentença) e o CALCULISTA fez
correções manuais no PJE-Calc antes de incorporar o cálculo ao processo. Você
recebe o DIFF de parâmetros (gerado → definitivo) e o contexto do caso.

Sua tarefa: para cada correção, decidir se ela revela uma REGRA GENERALIZÁVEL
(algo que a automação deveria fazer diferente em casos semelhantes) ou um
ajuste específico deste caso (valor particular, preferência pontual).

Formato obrigatório da resposta (JSON válido, sem markdown):
{
  "regras": [
    {
      "verba": "NOME DA VERBA/REFLEXO/SEÇÃO afetada (ou 'GLOBAL')",
      "campo": "caminho do campo no diff (copiar exatamente)",
      "de": "valor gerado", "para": "valor corrigido",
      "condicao": "QUANDO aplicar (sinais na sentença/contexto, ex.: 'quando houver jornada 12x36')",
      "acao": "o que a automação deve fazer (ex.: 'usar divisor 180 na verba X')",
      "generalizavel": true,
      "justificativa": "fundamento jurídico/operacional em 1 frase"
    }
  ],
  "resumo": "1-2 frases sobre o que este PJC definitivo ensinou"
}

Diretrizes:
- NÃO crie regra para ajustes de valor específicos do caso sem padrão
  (generalizavel=false nesses casos, ou omita se irrelevante).
- A condição deve citar SINAIS OBSERVÁVEIS na sentença/contexto — nunca
  "sempre" sem qualificação, exceto para constantes legais.
- Uma regra por correção raiz; não desdobre a mesma causa em várias regras.
- COMENTÁRIOS/OBSERVAÇÕES removidos ou esvaziados no PJC definitivo NÃO são
  correções: o calculista USA os comentários gerados como checklist de revisão
  e os apaga verba a verba conforme revisa. NUNCA gere regra para suprimir,
  reduzir ou deixar de emitir comentários (campos comentario/observacao/
  comentarios_jg e afins) — a automação deve continuar gerando-os."""


# ── FATIA 2 — análise LLM do diff ────────────────────────────────────────────

def _contexto_da_previa(sessao_id: str) -> str:
    """Resumo do contexto do caso (prévia v2) p/ ancorar o gatilho das regras."""
    try:
        from modules.webapp_v2 import _load_previa
        previa = _load_previa(sessao_id)
    except Exception:
        previa = None
    if not isinstance(previa, dict):
        return "(contexto da prévia indisponível)"
    linhas = []
    pc = previa.get("parametros_calculo") or {}
    for k in ("data_admissao", "data_demissao", "data_ajuizamento", "motivo_rescisao"):
        if pc.get(k):
            linhas.append(f"- {k}: {pc[k]}")
    for v in (previa.get("verbas_principais") or [])[:15]:
        if isinstance(v, dict):
            nome = v.get("nome_pjecalc") or v.get("nome_sentenca") or "?"
            refl = [r.get("nome") for r in (v.get("reflexos") or []) if isinstance(r, dict)]
            linhas.append(
                f"- verba: {nome} (estrategia={v.get('estrategia_preenchimento')}, "
                f"reflexos={len(refl)}, nome_sentenca={v.get('nome_sentenca')!r})"
            )
    cp = previa.get("cartoes_de_ponto") or ([previa.get("cartao_de_ponto")] if previa.get("cartao_de_ponto") else [])
    if cp:
        linhas.append(f"- cartao_de_ponto: {len(cp)} período(s) de jornada apurada")
    return "\n".join(linhas) or "(prévia vazia)"


def _diff_em_linhas(rel: dict) -> str:
    try:
        from learning.pjc_diff import resumo_legivel
        return "\n".join(resumo_legivel(rel))
    except Exception:
        return json.dumps(rel, ensure_ascii=False)[:4000]


def analisar_diff(sessao_id: str, db, orchestrator=None) -> dict:
    """FATIA 2 — analisa o diff persistido e gera/atualiza RegrasAprendidas.

    Retorna {"regras_novas": n, "regras_reconfirmadas": n, "acertos": n,
    "resumo": str}. Best-effort: nunca levanta."""
    out = {"regras_novas": 0, "regras_reconfirmadas": 0, "acertos": 0,
           "conflitos_abertos": 0, "resumo": ""}
    try:
        from learning.pjc_diff import carregar_relatorio
        rel = carregar_relatorio(sessao_id, _APRENDIZADO_DIR)
        if rel is None:
            logger.warning("pjc_aprendizado: relatório de diff ausente p/ %s", sessao_id)
            return out

        # FATIA 3 — ciclo de confiança roda SEMPRE (inclusive diff vazio:
        # PJC idêntico = a automação acertou tudo → acertos p/ regras ativas)
        out["acertos"] = ciclo_confianca_pjc(db, sessao_id, rel)

        if rel.get("resumo", {}).get("identicos"):
            out["resumo"] = "PJC definitivo idêntico ao gerado — nada a aprender; regras ativas reconfirmadas."
            _persistir_aprendizado_no_relatorio(sessao_id, out)
            return out

        # LLM
        if orchestrator is None:
            from core.llm_orchestrator import LLMOrchestrator
            from infrastructure.config import get_settings
            orchestrator = LLMOrchestrator(settings=get_settings())
        from core.llm_orchestrator import TaskType

        contexto = _contexto_da_previa(sessao_id)
        prompt = (
            "## Contexto do caso (prévia confirmada)\n"
            + contexto
            + "\n\n## Correções manuais detectadas (PJC gerado → PJC definitivo)\n"
            + _diff_em_linhas(rel)
            + "\n\n## Tarefa\nGere as regras conforme o formato. "
              "Responda APENAS com JSON válido."
        )
        result = orchestrator.complete(
            TaskType.LEARNING_ANALYSIS,
            prompt,
            system_override=_SYSTEM_PROMPT,
            inject_knowledge=False,
            inject_learned_rules=False,
            timeout=90,
        )
        regras = result.get("regras", []) if isinstance(result, dict) else []
        out["resumo"] = (result.get("resumo", "") if isinstance(result, dict) else "")

        novas, reconf, conflitos = _persistir_regras(db, sessao_id, regras,
                                                     contexto=contexto)
        out["regras_novas"], out["regras_reconfirmadas"] = novas, reconf
        out["conflitos_abertos"] = conflitos
        if conflitos:
            out["resumo"] = (out["resumo"] + " " if out["resumo"] else "") + (
                f"⚠️ {conflitos} conflito(s) com aprendizado consolidado — "
                "explicação solicitada na página inicial."
            )
        _persistir_aprendizado_no_relatorio(sessao_id, out)
        logger.info(
            "Plano 3 FATIA 2 (%s): %d regra(s) nova(s), %d reconfirmada(s), "
            "%d acerto(s), %d conflito(s)",
            sessao_id, novas, reconf, out["acertos"], conflitos,
        )
    except Exception as e:
        logger.warning("pjc_aprendizado.analisar_diff(%s): %s", sessao_id, e)
    return out


def _chave_regra(verba: str, campo: str, para: str) -> str:
    return f"{_norm(verba)}::{_norm(campo)}::{_norm(para)}"


def _persistir_regras(db, sessao_id: str, regras: list,
                      contexto: str = "") -> tuple[int, int, int]:
    """Cria/reconfirma RegrasAprendidas (tipo_regra='pjc_definitivo').

    Dedup por (verba, campo, para) via exemplos_json[0].chave — reincidência da
    MESMA correção em outro cálculo reconfirma a regra (+0.1).

    FATIA 4 — CONFLITO (excepcional): se a candidata atinge a MESMA
    (verba, campo) de uma regra CONSOLIDADA (ativa, confiança ≥ 0.6) com valor
    DIVERGENTE, NÃO cria regra concorrente — abre uma pendência de explicação
    (diálogo com o usuário) e a consolidada permanece intocada até o usuário
    explicar a particularidade. Retorna (novas, reconfirmadas, conflitos)."""
    from infrastructure.database import RegrasAprendidas
    novas = reconf = conflitos = 0
    existentes = (
        db.query(RegrasAprendidas)
        .filter(RegrasAprendidas.tipo_regra == "pjc_definitivo")
        .all()
    )
    por_chave: dict[str, Any] = {}
    por_campo: dict[str, list] = {}
    for r in existentes:
        try:
            ex = json.loads(r.exemplos_json or "[]")
            if ex and ex[0].get("chave"):
                por_chave[ex[0]["chave"]] = r
                v, c, _p = ex[0]["chave"].split("::", 2)
                por_campo.setdefault(f"{v}::{c}", []).append(r)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    for reg in regras:
        if not isinstance(reg, dict) or not reg.get("acao"):
            continue
        verba = str(reg.get("verba") or "GLOBAL")
        campo = str(reg.get("campo") or "")
        para = str(reg.get("para") or "")
        chave = _chave_regra(verba, campo, para)
        # FATIA 4 — conflito com regra consolidada (mesma verba::campo, outro para)
        if chave not in por_chave:
            try:
                from learning.pjc_conflito import abrir_conflito, detectar_conflito
                chave_campo = f"{_norm(verba)}::{_norm(campo)}"
                conflitante = next(
                    (r for r in por_campo.get(chave_campo, [])
                     if detectar_conflito(r, {"verba": verba, "campo": campo,
                                              "para": para})),
                    None,
                )
                if conflitante is not None:
                    abrir_conflito(sessao_id, conflitante,
                                   {**reg, "verba": verba, "campo": campo,
                                    "para": para},
                                   contexto=contexto)
                    conflitos += 1
                    continue  # não cria regra concorrente — aguarda explicação
            except Exception as e:
                logger.warning("detecção de conflito (%s/%s): %s", verba, campo, e)
        exemplo = {
            "chave": chave, "sessao_id": sessao_id, "verba": verba,
            "campo": campo, "de": reg.get("de"), "para": reg.get("para"),
            "justificativa": reg.get("justificativa"),
        }
        try:
            ja = por_chave.get(chave)
            if ja is not None:
                exs = json.loads(ja.exemplos_json or "[]")
                if not any(e.get("sessao_id") == sessao_id for e in exs):
                    exs.append(exemplo)
                    ja.exemplos_json = json.dumps(exs, ensure_ascii=False)
                    ja.confianca = min(_CONF_TETO, (ja.confianca or 0.5) + _CONF_REINCIDENCIA)
                    ja.ativa = True
                    ja.atualizado_em = datetime.utcnow()
                    reconf += 1
            else:
                nova = RegrasAprendidas(
                    tipo_regra="pjc_definitivo",
                    condicao=str(reg.get("condicao") or f"Verba {verba} presente no cálculo"),
                    acao=str(reg.get("acao")),
                    exemplos_json=json.dumps([exemplo], ensure_ascii=False),
                    confianca=_CONF_GENERALIZAVEL if reg.get("generalizavel") else _CONF_CASO,
                    ativa=True,
                )
                db.add(nova)
                por_chave[chave] = nova
                novas += 1
        except Exception as e:
            logger.warning("persistir regra pjc_definitivo: %s", e)
    try:
        db.commit()
    except Exception as e:
        logger.warning("pjc_aprendizado: commit regras falhou (%s)", e)
        try:
            db.rollback()
        except Exception:
            pass
        return 0, 0, conflitos
    return novas, reconf, conflitos


def _persistir_aprendizado_no_relatorio(sessao_id: str, aprendizado: dict) -> None:
    """Anexa o resultado do aprendizado ao relatório de diff (visível no GET)."""
    try:
        p = _APRENDIZADO_DIR / f"{sessao_id}_diff.json"
        rel = json.loads(p.read_text(encoding="utf-8"))
        rel["aprendizado"] = {**aprendizado, "analisado_em": datetime.utcnow().isoformat() + "Z"}
        p.write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("persistir aprendizado no relatório: %s", e)


def analisar_diff_em_background(sessao_id: str) -> None:
    """Entry-point p/ BackgroundTasks do FastAPI — sessão de DB própria."""
    try:
        from infrastructure.database import SessionLocal
        db = SessionLocal()
        try:
            analisar_diff(sessao_id, db)
        finally:
            db.close()
    except Exception as e:
        logger.warning("analisar_diff_em_background(%s): %s", sessao_id, e)


# ── FATIA 3 — ciclo de confiança ─────────────────────────────────────────────

def _correcoes_do_diff(rel: dict) -> set[str]:
    """Chaves (verba::campo::para) de TODAS as correções presentes num diff."""
    chaves: set[str] = set()
    for grupo in ("verbas", "reflexos", "historicos"):
        for alt in (rel.get(grupo, {}) or {}).get("alteradas", []):
            for c in alt.get("campos", []):
                chaves.add(_chave_regra(alt.get("nome", ""), c.get("campo", ""),
                                        str(c.get("para") or "")))
    for c in rel.get("parametros_calculo", []) or []:
        chaves.add(_chave_regra("GLOBAL", c.get("campo", ""), str(c.get("para") or "")))
    for sec, campos in (rel.get("secoes", {}) or {}).items():
        for c in campos:
            chaves.add(_chave_regra(sec, c.get("campo", ""), str(c.get("para") or "")))
    return chaves


def _campos_corrigidos(rel: dict) -> set[str]:
    """Chaves (verba::campo) corrigidas — sem o 'para' (p/ detectar reversões)."""
    out: set[str] = set()
    for ch in _correcoes_do_diff(rel):
        v, c, _ = ch.split("::", 2)
        out.add(f"{v}::{c}")
    return out


def ciclo_confianca_pjc(db, sessao_id: str, rel: dict) -> int:
    """FATIA 3 — a cada novo PJC definitivo, para cada regra pjc_definitivo
    ATIVA: se a correção que a originou NÃO se repetiu neste diff (a automação
    acertou), a regra ganha acerto (+0.05). A reincidência da MESMA correção é
    tratada pelo dedup do _persistir_regras (+0.1). Confiança < 0.2 arquiva.

    Retorna o nº de regras com acerto registrado. Best-effort."""
    try:
        from infrastructure.database import RegrasAprendidas
    except Exception:
        return 0
    acertos = 0
    corrigidos = _campos_corrigidos(rel)
    try:
        regras = (
            db.query(RegrasAprendidas)
            .filter(RegrasAprendidas.tipo_regra == "pjc_definitivo",
                    RegrasAprendidas.ativa == True)  # noqa: E712
            .all()
        )
        for r in regras:
            try:
                exs = json.loads(r.exemplos_json or "[]")
            except (json.JSONDecodeError, TypeError):
                continue
            if not exs:
                continue
            if any(e.get("sessao_id") == sessao_id for e in exs):
                continue  # regra nasceu/reconfirmou NESTE diff — não é acerto
            # Piso PRIMEIRO: regra que decaiu abaixo do piso é arquivada e não
            # recebe bonificação (arquivar > bonificar).
            if (r.confianca or 0) < _CONF_PISO_ARQUIVO:
                r.ativa = False
                r.atualizado_em = datetime.utcnow()
                continue
            verba, campo = exs[0].get("verba", ""), exs[0].get("campo", "")
            if f"{_norm(verba)}::{_norm(campo)}" not in corrigidos:
                r.acertos = (r.acertos or 0) + 1
                r.confianca = min(_CONF_TETO, (r.confianca or 0.5) + _CONF_ACERTO)
                r.atualizado_em = datetime.utcnow()
                acertos += 1
        db.commit()
    except Exception as e:
        logger.warning("ciclo_confianca_pjc(%s): %s", sessao_id, e)
        try:
            db.rollback()
        except Exception:
            pass
        return 0
    return acertos


# ── FATIA 3 — bloco de injeção p/ a extração (Etapa 2) ───────────────────────

def montar_bloco_pjc_definitivo(db, limiar_conf: float = LIMIAR_INJECAO,
                                top_n: int = 25) -> Optional[str]:
    """Bloco markdown com as regras aprendidas de PJC definitivo, injetado na
    extração (Etapa 2) no MESMO canal do Plano 2. Retorna None se não há regra
    qualificada (no-op). Best-effort."""
    try:
        from infrastructure.database import RegrasAprendidas
        rows = (
            db.query(RegrasAprendidas)
            .filter(RegrasAprendidas.tipo_regra == "pjc_definitivo",
                    RegrasAprendidas.ativa == True,  # noqa: E712
                    RegrasAprendidas.confianca >= limiar_conf)
            .order_by(RegrasAprendidas.confianca.desc())
            .limit(top_n)
            .all()
        )
    except Exception as e:
        logger.warning("montar_bloco_pjc_definitivo: %s", e)
        return None
    if not rows:
        return None
    linhas = []
    ids = []
    for r in rows:
        linhas.append(f"- QUANDO {r.condicao.strip().rstrip('.')}: {r.acao.strip()} "
                      f"(confiança {r.confianca:.2f})")
        ids.append(r.id)
    # registrar aplicação (métrica do ciclo de vida)
    try:
        from infrastructure.database import RegrasAprendidas as _R
        db.query(_R).filter(_R.id.in_(ids)).update(
            {_R.aplicacoes: _R.aplicacoes + 1}, synchronize_session=False)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return (
        "# CORREÇÕES APRENDIDAS DE PJCs DEFINITIVOS (revisão do calculista)\n\n"
        "As regras abaixo vêm de correções que o calculista fez manualmente em "
        "cálculos anteriores (comparação PJC gerado × PJC definitivo do processo). "
        "Aplique-as como orientação — MAS:\n"
        "- A **sentença deste caso** SEMPRE prevalece.\n"
        "- Os **invariantes do prompt** SEMPRE prevalecem em conflito.\n\n"
        + "\n".join(linhas)
    )
