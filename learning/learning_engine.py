# learning/learning_engine.py — Motor de aprendizado contínuo do pjecalc-agente
#
# Analisa correções acumuladas dos usuários via LLM (Claude) e gera regras
# de mapeamento que melhoram a precisão das extrações futuras.

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.llm_orchestrator import LLMOrchestrator
    from knowledge.knowledge_base import KnowledgeBase


# Prompt para análise de grupos de correções
_LEARNING_SYSTEM_PROMPT = """Você é um especialista em Direito do Trabalho e em sistemas de extração automática de sentenças trabalhistas para o PJE-Calc.

Sua tarefa é analisar padrões de correção feitas por usuários em extrações automáticas e gerar REGRAS precisas que preveniriam essas correções no futuro.

Formato obrigatório da resposta (JSON válido, sem markdown):
{
  "regras": [
    {
      "tipo_regra": "mapeamento_verba" | "extracao_campo" | "classificacao_parametro" | "reflexa" | "correcao_juros",
      "condicao": "Descrição clara de QUANDO aplicar esta regra (ex: 'quando a sentença mencionar X')",
      "acao": "O que fazer (ex: 'mapear para campo Y com valor Z')",
      "confianca": 0.85,
      "justificativa": "Por que esta regra é correta juridicamente"
    }
  ],
  "resumo": "Resumo em 1-2 frases do que foi aprendido neste grupo de correções"
}

Regras para boas regras:
- Condição deve ser ESPECÍFICA e verificável no texto da sentença
- Ação deve ser EXATA e aplicável ao schema PJE-Calc
- Confiança 0.9+ apenas quando a regra é determinística (sem ambiguidade jurídica)
- Máximo 5 regras por grupo
- Não gerar regras sobre casos únicos/específicos de um processo — apenas padrões recorrentes"""


class LearningEngine:
    """
    Analisa padrões de correção dos usuários e gera regras de mapeamento via Claude.

    Fluxo de uma sessão de aprendizado:
    1. Carregar CorrecaoUsuario com incorporada_em_regra=False
    2. Agrupar por (tipo_correcao, entidade)
    3. Para cada grupo: enviar ao Claude para análise
    4. Claude retorna: lista de regras com {condicao, acao, confianca}
    5. Salvar como RegrasAprendidas (criar nova ou atualizar similar existente)
    6. Marcar correções como incorporadas
    7. Exportar snapshot JSON em data/learning/
    8. Atualizar knowledge_base cache

    Args:
        db: Sessão SQLAlchemy
        orchestrator: LLMOrchestrator para chamadas ao Claude
        knowledge_base: KnowledgeBase para invalidar cache após aprendizado

    Example:
        engine = LearningEngine(db, orchestrator, knowledge_base)
        session = engine.run_learning_session()
        print(f"Aprendidas {session.num_regras_geradas} novas regras")
    """

    def __init__(
        self,
        db: Session,
        orchestrator: "LLMOrchestrator",
        knowledge_base: Optional["KnowledgeBase"] = None,
    ) -> None:
        self._db = db
        self._orchestrator = orchestrator
        self._kb = knowledge_base

    # ── Interface pública ──────────────────────────────────────────────────────

    def run_learning_session(self) -> Any:
        """
        Executa uma sessão completa de aprendizado.

        Processamento é síncrono — chamar como background task em webapp.py.

        Returns:
            SessaoAprendizado com status "concluida" ou "erro"

        Raises:
            Exception: propagada após marcar a sessão como "erro"
        """
        from infrastructure.database import SessaoAprendizado
        from core.llm_orchestrator import TaskType

        session = SessaoAprendizado(
            status="em_andamento",
            iniciada_em=datetime.utcnow(),
        )
        self._db.add(session)
        self._db.commit()
        logger.info("learning_session_started", session_id=session.id)

        try:
            # 1. Carregar correções não processadas
            correcoes = self._load_unincorporated_corrections()
            if not correcoes:
                logger.info("learning_session_no_corrections", session_id=session.id)
                session.status = "concluida"
                session.num_correcoes_analisadas = 0
                session.num_regras_geradas = 0
                session.num_regras_atualizadas = 0
                session.concluida_em = datetime.utcnow()
                self._db.commit()
                return session

            # 2. Agrupar por tipo
            groups = self._group_corrections(correcoes)
            new_rules: list = []
            updated_rules: list = []
            summaries: list[str] = []

            # 3. Analisar cada grupo
            for group_key, group_correcoes in groups.items():
                if len(group_correcoes) < 2:
                    # Precisamos de pelo menos 2 correções para identificar padrão
                    continue

                try:
                    rules_data, summary = self._analyze_correction_group(
                        group_key, group_correcoes
                    )
                    summaries.append(summary)

                    for rule_dict in rules_data:
                        existing = self._find_similar_rule(rule_dict)
                        if existing:
                            self._update_rule(existing, rule_dict)
                            updated_rules.append(existing)
                        else:
                            new_rule = self._save_rule(rule_dict, session.id)
                            if new_rule:
                                new_rules.append(new_rule)
                except Exception as e:
                    logger.warning(
                        "learning_group_analysis_failed",
                        group=group_key,
                        error=str(e),
                    )

            # 4. Marcar correções como incorporadas
            self._mark_corrections_incorporated(correcoes, session.id)

            # 5. Exportar snapshot
            all_rules = new_rules + updated_rules
            if all_rules:
                self._export_snapshot(all_rules, session)

            # 6. Invalidar cache da knowledge base
            if self._kb:
                self._kb.invalidate_rules_cache()

            # 7. Completar sessão
            session.status = "concluida"
            session.num_correcoes_analisadas = len(correcoes)
            session.num_regras_geradas = len(new_rules)
            session.num_regras_atualizadas = len(updated_rules)
            session.resumo = "; ".join(summaries[:3]) if summaries else "Sessão concluída sem novos padrões identificados."
            session.concluida_em = datetime.utcnow()
            from infrastructure.config import settings
            session.modelo_llm = settings.claude_model
            self._db.commit()

            logger.info(
                "learning_session_completed",
                session_id=session.id,
                new_rules=len(new_rules),
                updated_rules=len(updated_rules),
                corrections_processed=len(correcoes),
            )
            return session

        except Exception as e:
            session.status = "erro"
            session.erro_msg = str(e)
            session.concluida_em = datetime.utcnow()
            self._db.commit()
            logger.error("learning_session_failed", session_id=session.id, error=str(e))
            raise

    # ── Análise de correções ───────────────────────────────────────────────────

    def _analyze_correction_group(
        self,
        group_key: str,
        correcoes: list,
    ) -> tuple[list[dict], str]:
        """
        Envia um grupo de correções ao Claude para análise e geração de regras.

        Args:
            group_key: Chave do grupo (tipo_correcao/entidade)
            correcoes: Lista de CorrecaoUsuario do mesmo tipo/entidade

        Returns:
            (lista_de_regras, resumo_da_sessao)
        """
        from core.llm_orchestrator import TaskType

        # Formatar exemplos de correção
        exemplos: list[str] = []
        for i, c in enumerate(correcoes[:10], 1):  # máx. 10 por grupo
            antes = c.valor_antes or "null"
            depois = c.valor_depois or "null"
            contexto = json.loads(c.contexto_json) if c.contexto_json else {}
            exemplos.append(
                f"Correção {i}: campo='{c.campo}'\n"
                f"  IA extraiu: {antes}\n"
                f"  Usuário corrigiu para: {depois}\n"
                f"  Contexto: {json.dumps(contexto, ensure_ascii=False)}"
            )

        # Conteúdo adicional da knowledge base
        kb_context = ""
        if self._kb:
            kb_context = (
                "\n\n## Catálogo de Verbas PJE-Calc\n"
                + self._kb.get_verba_catalog()[:3000]  # limite razoável
            )

        prompt = (
            f"## Grupo de Correções: {group_key}\n"
            f"Total de correções neste grupo: {len(correcoes)}\n\n"
            f"### Exemplos de Correções:\n\n"
            + "\n\n".join(exemplos)
            + kb_context
            + "\n\n## Tarefa\n"
            "Analise os padrões acima e gere regras que preveniriam essas correções.\n"
            "Responda APENAS com JSON válido no formato especificado."
        )

        result = self._orchestrator.complete(
            TaskType.LEARNING_ANALYSIS,
            prompt,
            system_override=_LEARNING_SYSTEM_PROMPT,
            inject_knowledge=False,  # já incluímos manualmente acima
            inject_learned_rules=False,
            timeout=90,
        )

        if isinstance(result, dict):
            rules = result.get("regras", [])
            summary = result.get("resumo", "")
        else:
            logger.warning("learning_analysis_non_json", group=group_key)
            rules = []
            summary = ""

        return rules, summary

    # ── Agrupamento de correções ───────────────────────────────────────────────

    def _load_unincorporated_corrections(self) -> list:
        """Carrega correções com incorporada_em_regra=False."""
        from infrastructure.database import CorrecaoUsuario
        return (
            self._db.query(CorrecaoUsuario)
            .filter(CorrecaoUsuario.incorporada_em_regra == False)
            .order_by(CorrecaoUsuario.timestamp.asc())
            .all()
        )

    def _group_corrections(self, correcoes: list) -> dict[str, list]:
        """Agrupa correções por (tipo_correcao/entidade) para análise em lote."""
        groups: dict[str, list] = {}
        for c in correcoes:
            key = f"{c.tipo_correcao}/{c.entidade}"
            groups.setdefault(key, []).append(c)
        return groups

    # ── Persistência de regras ────────────────────────────────────────────────

    def _find_similar_rule(self, rule_dict: dict) -> Any:
        """Busca regra existente com mesmo tipo e condição similar."""
        from infrastructure.database import RegrasAprendidas
        existing = (
            self._db.query(RegrasAprendidas)
            .filter(
                RegrasAprendidas.tipo_regra == rule_dict.get("tipo_regra"),
                RegrasAprendidas.ativa == True,
            )
            .all()
        )
        condicao_nova = rule_dict.get("condicao", "").lower()
        for r in existing:
            # Similaridade simples por sobreposição de palavras-chave
            condicao_existente = (r.condicao or "").lower()
            palavras_novas = set(condicao_nova.split())
            palavras_existentes = set(condicao_existente.split())
            overlap = len(palavras_novas & palavras_existentes) / max(len(palavras_novas), 1)
            if overlap >= 0.6:  # 60% de sobreposição → considerar a mesma regra
                return r
        return None

    def _save_rule(self, rule_dict: dict, session_id: int) -> Any:
        """Salva uma nova RegrasAprendidas no banco."""
        from infrastructure.database import RegrasAprendidas
        try:
            rule = RegrasAprendidas(
                sessao_aprendizado_id=session_id,
                tipo_regra=rule_dict.get("tipo_regra", "extracao_campo"),
                condicao=rule_dict.get("condicao", ""),
                acao=rule_dict.get("acao", ""),
                exemplos_json=json.dumps(
                    rule_dict.get("exemplos", []), ensure_ascii=False
                ),
                confianca=float(rule_dict.get("confianca", 0.7)),
                ativa=True,
            )
            self._db.add(rule)
            self._db.flush()
            return rule
        except Exception as e:
            logger.warning("rule_save_failed", error=str(e))
            return None

    def _update_rule(self, existing: Any, rule_dict: dict) -> None:
        """Atualiza uma regra existente com novos dados."""
        nova_confianca = float(rule_dict.get("confianca", existing.confianca))
        # Média ponderada: 70% existente + 30% nova evidência
        existing.confianca = 0.7 * existing.confianca + 0.3 * nova_confianca
        existing.acao = rule_dict.get("acao", existing.acao)
        existing.atualizado_em = datetime.utcnow()
        self._db.flush()

    def _mark_corrections_incorporated(
        self, correcoes: list, session_id: int
    ) -> None:
        """Marca as correções processadas como incorporadas."""
        from infrastructure.database import CorrecaoUsuario
        for c in correcoes:
            c.incorporada_em_regra = True
            c.sessao_aprendizado_id = session_id
        self._db.commit()

    # ── Exportação de snapshot ────────────────────────────────────────────────

    def _export_snapshot(self, rules: list, session: Any) -> Optional[Path]:
        """
        Exporta snapshot JSON das regras em data/learning/.

        Arquivos gerados:
        - data/learning/rules_{session_id}.json
        - data/learning/rules_latest.json (sobrescrito a cada sessão)
        """
        try:
            from infrastructure.config import settings
            learning_dir = settings.learning_dir
        except ImportError:
            learning_dir = Path("data/learning")

        learning_dir.mkdir(parents=True, exist_ok=True)

        rules_data = [
            {
                "id": r.id,
                "tipo_regra": r.tipo_regra,
                "condicao": r.condicao,
                "acao": r.acao,
                "confianca": r.confianca,
                "aplicacoes": r.aplicacoes,
                "acertos": r.acertos,
                "ativa": r.ativa,
                "criado_em": r.criado_em.isoformat() if r.criado_em else None,
            }
            for r in rules
        ]

        snapshot = {
            "sessao_id": session.id,
            "gerado_em": datetime.utcnow().isoformat(),
            "num_regras": len(rules_data),
            "regras": rules_data,
        }

        snapshot_json = json.dumps(snapshot, ensure_ascii=False, indent=2)

        # Arquivo específico da sessão
        session_path = learning_dir / f"rules_{session.id}.json"
        session_path.write_text(snapshot_json, encoding="utf-8")

        # Arquivo "latest" (sempre atualizado)
        latest_path = learning_dir / "rules_latest.json"
        latest_path.write_text(snapshot_json, encoding="utf-8")

        session.snapshot_json = snapshot_json
        self._db.flush()

        logger.info("learning_snapshot_exported", path=str(session_path))
        return session_path
