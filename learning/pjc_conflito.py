# learning/pjc_conflito.py — Plano 3, FATIA 4: diálogo de CONFLITO de aprendizado
#
# Fluxo EXCEPCIONAL (pedido do usuário, 04/07/2026): quando uma correção de um
# novo PJC definitivo CONTRADIZ uma regra já CONSOLIDADA (ativa, confiança ≥
# 0.6, mesma verba+campo, valor divergente), a máquina NÃO cria uma regra
# concorrente às cegas nem sobrescreve a antiga — abre uma PENDÊNCIA DE
# EXPLICAÇÃO e pergunta ao usuário qual a particularidade do caso.
#
# O diálogo é iterativo: o Claude avalia cada explicação e (a) declara a
# explicação PLENAMENTE COMPREENDIDA — refinando a CONDIÇÃO da regra antiga e
# criando a nova regra com o gatilho que as distingue — ou (b) faz UMA nova
# pergunta específica. O fluxo só termina na compreensão plena.
#
# Persistência: arquivos JSON em data/calculations/aprendizado_pjc/conflitos/
# (mesmo padrão de store do Plano 3). Best-effort: falha aqui nunca quebra o
# upload/análise — no pior caso a regra conflitante simplesmente não é criada
# (a consolidada permanece intocada até o usuário explicar).

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CONFLITOS_DIR = Path("data/calculations/aprendizado_pjc/conflitos")

# Regra "consolidada" = já qualificada para injeção
LIMIAR_CONSOLIDADA = 0.6

_PERGUNTA_INICIAL = (
    "Neste cálculo você corrigiu «{campo}» da verba {verba} para «{para}», mas o "
    "aprendizado consolidado (visto em {n} caso(s) anterior(es)) prescreve "
    "«{para_antigo}» — condição registrada: {condicao_antiga}. "
    "Qual a particularidade deste caso que justifica o valor diferente? "
    "(ex.: jornada, categoria, período, determinação específica da sentença)"
)

_SYSTEM_DIALOGO = """Você é um especialista em Direito do Trabalho e no PJE-Calc,
refinando o aprendizado de máquina de um sistema de liquidação de sentenças.

Há um CONFLITO: uma regra CONSOLIDADA prescreve um valor para (verba, campo),
mas um novo cálculo revisado pelo calculista usou valor DIVERGENTE. O
calculista está explicando a particularidade. Avalie a explicação.

Responda APENAS JSON válido (sem markdown):
{
  "compreendida": true | false,
  "pergunta": "se compreendida=false: UMA pergunta específica e objetiva que falta responder",
  "refinamento": {   // OBRIGATÓRIO se compreendida=true
    "condicao_regra_existente": "condição REFINADA da regra antiga (delimitando quando ELA vale)",
    "nova_regra": {   // ou null, se a explicação mostrar que a regra antiga estava ERRADA
      "condicao": "quando aplicar o NOVO valor (a particularidade explicada)",
      "acao": "o que fazer (com o novo valor)",
      "generalizavel": true
    },
    "corrigir_regra_existente": null,  // ou {"acao": "..."} se a antiga estava ERRADA e deve mudar
    "observacao": "síntese em 1 frase do que foi compreendido"
  }
}

Critérios:
- compreendida=true SOMENTE se a explicação permite formular condições que
  DISTINGUEM objetivamente os dois cenários (sinais observáveis na sentença),
  OU se ela demonstra que a regra antiga estava simplesmente errada.
- Se a explicação for vaga ("foi diferente", "o caso pediu"), pergunte o
  critério objetivo. UMA pergunta por vez, direta.
- Nunca invente particularidade que o calculista não afirmou."""


# ── Detecção ──────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    sem = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sem.lower().split())


def detectar_conflito(regra_existente, reg_nova: dict) -> bool:
    """True se a regra nova (candidata) CONTRADIZ a existente consolidada:
    mesma (verba, campo), `para` divergente, existente ativa e consolidada."""
    if regra_existente is None:
        return False
    if not regra_existente.ativa or (regra_existente.confianca or 0) < LIMIAR_CONSOLIDADA:
        return False
    try:
        exs = json.loads(regra_existente.exemplos_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return False
    if not exs:
        return False
    e0 = exs[0]
    return (
        _norm(e0.get("verba")) == _norm(reg_nova.get("verba"))
        and _norm(e0.get("campo")) == _norm(reg_nova.get("campo"))
        and _norm(str(e0.get("para"))) != _norm(str(reg_nova.get("para")))
    )


def abrir_conflito(sessao_id: str, regra_existente, reg_nova: dict,
                   contexto: str = "") -> dict:
    """Cria a pendência de explicação (arquivo JSON) e retorna o registro."""
    _CONFLITOS_DIR.mkdir(parents=True, exist_ok=True)
    exs = json.loads(regra_existente.exemplos_json or "[]")
    e0 = exs[0] if exs else {}
    cid = uuid.uuid4().hex[:12]
    pergunta = _PERGUNTA_INICIAL.format(
        campo=reg_nova.get("campo") or "?",
        verba=reg_nova.get("verba") or "?",
        para=reg_nova.get("para"),
        n=len(exs),
        para_antigo=e0.get("para"),
        condicao_antiga=regra_existente.condicao,
    )
    registro = {
        "id": cid,
        "sessao_id": sessao_id,
        "criado_em": datetime.utcnow().isoformat() + "Z",
        "status": "aguardando_explicacao",
        "regra_existente": {
            "id": regra_existente.id,
            "condicao": regra_existente.condicao,
            "acao": regra_existente.acao,
            "confianca": regra_existente.confianca,
            "exemplo": e0,
        },
        "nova_correcao": {
            "verba": reg_nova.get("verba"),
            "campo": reg_nova.get("campo"),
            "de": reg_nova.get("de"),
            "para": reg_nova.get("para"),
            "condicao_sugerida": reg_nova.get("condicao"),
            "acao_sugerida": reg_nova.get("acao"),
            "justificativa_llm": reg_nova.get("justificativa"),
        },
        "contexto": contexto,
        "pergunta_atual": pergunta,
        "trocas": [],
        "resolucao": None,
    }
    (_CONFLITOS_DIR / f"{cid}.json").write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Plano 3 FATIA 4: conflito de aprendizado aberto (%s) — %s/%s",
                cid, reg_nova.get("verba"), reg_nova.get("campo"))
    return registro


def listar_conflitos(status: Optional[str] = "aguardando_explicacao") -> list[dict]:
    if not _CONFLITOS_DIR.exists():
        return []
    out = []
    for p in sorted(_CONFLITOS_DIR.glob("*.json")):
        try:
            reg = json.loads(p.read_text(encoding="utf-8"))
            if status is None or reg.get("status") == status:
                out.append(reg)
        except (json.JSONDecodeError, OSError):
            continue
    return out


def carregar_conflito(conflito_id: str) -> dict | None:
    p = _CONFLITOS_DIR / f"{conflito_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _salvar(registro: dict) -> None:
    (_CONFLITOS_DIR / f"{registro['id']}.json").write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Diálogo ───────────────────────────────────────────────────────────────────

def responder_conflito(conflito_id: str, explicacao: str, db,
                       orchestrator=None) -> dict:
    """Registra a explicação do usuário, avalia com o LLM e:
    - compreendida → aplica o refinamento (regra antiga + nova regra) e resolve;
    - não compreendida → devolve a próxima pergunta (loop continua).

    Retorna {"status": "resolvido"|"aguardando_explicacao"|"erro",
             "pergunta": str|None, "observacao": str|None}."""
    reg = carregar_conflito(conflito_id)
    if reg is None:
        return {"status": "erro", "pergunta": None,
                "observacao": "Conflito não encontrado"}
    if reg.get("status") == "resolvido":
        return {"status": "resolvido", "pergunta": None,
                "observacao": "Conflito já resolvido"}

    explicacao = (explicacao or "").strip()
    if not explicacao:
        return {"status": "aguardando_explicacao",
                "pergunta": reg.get("pergunta_atual"),
                "observacao": "Explicação vazia"}

    reg["trocas"].append({
        "pergunta": reg.get("pergunta_atual"),
        "resposta": explicacao,
        "em": datetime.utcnow().isoformat() + "Z",
    })

    try:
        if orchestrator is None:
            from core.llm_orchestrator import LLMOrchestrator
            from infrastructure.config import get_settings
            orchestrator = LLMOrchestrator(settings=get_settings())
        from core.llm_orchestrator import TaskType

        historico = "\n".join(
            f"PERGUNTA: {t['pergunta']}\nRESPOSTA DO CALCULISTA: {t['resposta']}"
            for t in reg["trocas"]
        )
        prompt = (
            "## Regra CONSOLIDADA (aprendizado anterior)\n"
            f"- condição: {reg['regra_existente']['condicao']}\n"
            f"- ação: {reg['regra_existente']['acao']}\n"
            f"- valor prescrito: {reg['regra_existente']['exemplo'].get('para')}\n\n"
            "## Nova correção CONFLITANTE (PJC definitivo deste caso)\n"
            f"- verba: {reg['nova_correcao']['verba']}\n"
            f"- campo: {reg['nova_correcao']['campo']}\n"
            f"- valor usado: {reg['nova_correcao']['para']} (gerado era {reg['nova_correcao']['de']})\n\n"
            f"## Contexto do caso\n{reg.get('contexto') or '(indisponível)'}\n\n"
            f"## Diálogo com o calculista\n{historico}\n\n"
            "## Tarefa\nAvalie a(s) explicação(ões) conforme o formato. "
            "Responda APENAS JSON."
        )
        result = orchestrator.complete(
            TaskType.LEARNING_ANALYSIS,
            prompt,
            system_override=_SYSTEM_DIALOGO,
            inject_knowledge=False,
            inject_learned_rules=False,
            timeout=90,
        )
    except Exception as e:
        logger.warning("responder_conflito(%s): LLM falhou (%s)", conflito_id, e)
        _salvar(reg)  # preserva a troca mesmo com falha do LLM
        return {"status": "aguardando_explicacao",
                "pergunta": reg.get("pergunta_atual"),
                "observacao": f"Falha na análise ({e}); tente novamente."}

    if not isinstance(result, dict):
        _salvar(reg)
        return {"status": "aguardando_explicacao",
                "pergunta": reg.get("pergunta_atual"),
                "observacao": "Análise inconclusiva; reformule a explicação."}

    if not result.get("compreendida"):
        pergunta = str(result.get("pergunta") or
                       "Pode detalhar o critério objetivo que distingue este caso?")
        reg["pergunta_atual"] = pergunta
        _salvar(reg)
        return {"status": "aguardando_explicacao", "pergunta": pergunta,
                "observacao": None}

    # Compreensão plena → aplicar refinamento
    refin = result.get("refinamento") or {}
    obs = _aplicar_refinamento(db, reg, refin)
    reg["status"] = "resolvido"
    reg["pergunta_atual"] = None
    reg["resolucao"] = {
        "em": datetime.utcnow().isoformat() + "Z",
        "refinamento": refin,
        "aplicado": obs,
    }
    _salvar(reg)
    logger.info("Plano 3 FATIA 4: conflito %s RESOLVIDO — %s", conflito_id, obs)
    return {"status": "resolvido", "pergunta": None,
            "observacao": refin.get("observacao") or obs}


def _aplicar_refinamento(db, reg: dict, refin: dict) -> str:
    """Aplica o refinamento nas RegrasAprendidas. Retorna descrição do aplicado."""
    from infrastructure.database import RegrasAprendidas
    feitos = []
    try:
        antiga = (db.query(RegrasAprendidas)
                  .filter_by(id=reg["regra_existente"]["id"]).first())
        if antiga is not None:
            cond_ref = refin.get("condicao_regra_existente")
            if cond_ref:
                antiga.condicao = str(cond_ref)
                feitos.append("condição da regra existente refinada")
            corr = refin.get("corrigir_regra_existente")
            if isinstance(corr, dict) and corr.get("acao"):
                antiga.acao = str(corr["acao"])
                feitos.append("ação da regra existente corrigida")
            antiga.atualizado_em = datetime.utcnow()

        nova = refin.get("nova_regra")
        if isinstance(nova, dict) and nova.get("acao"):
            nc = reg["nova_correcao"]
            exemplo = {
                "chave": f"{_norm(nc.get('verba'))}::{_norm(nc.get('campo'))}::"
                         f"{_norm(str(nc.get('para')))}",
                "sessao_id": reg.get("sessao_id"),
                "verba": nc.get("verba"), "campo": nc.get("campo"),
                "de": nc.get("de"), "para": nc.get("para"),
                "justificativa": f"explicação do calculista (conflito {reg['id']})",
            }
            db.add(RegrasAprendidas(
                tipo_regra="pjc_definitivo",
                condicao=str(nova.get("condicao") or "particularidade explicada"),
                acao=str(nova["acao"]),
                exemplos_json=json.dumps([exemplo], ensure_ascii=False),
                # nasce consolidada: a condição veio de explicação humana direta
                confianca=0.7,
                ativa=True,
            ))
            feitos.append("nova regra criada com o gatilho explicado")
        db.commit()
    except Exception as e:
        logger.warning("aplicar refinamento (%s): %s", reg.get("id"), e)
        try:
            db.rollback()
        except Exception:
            pass
        return f"falha ao aplicar ({e})"
    return "; ".join(feitos) or "nada a aplicar"
