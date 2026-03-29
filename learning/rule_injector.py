# learning/rule_injector.py — Injeta regras aprendidas nos prompts LLM
#
# Rastreia também uso e acertos das regras para avaliar sua efetividade.

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class RuleInjector:
    """
    Injeta regras aprendidas em prompts LLM e rastreia sua efetividade.

    Uso em LLMOrchestrator._build_system_prompt():
        injector = RuleInjector(db)
        rules_text = injector.get_active_rules_for_prompt(task_type)
        system_prompt += rules_text

    Rastreamento de efetividade:
    - record_rule_usage(): chamado quando a regra é incluída num prompt
    - record_rule_success(): chamado quando o cálculo é confirmado sem nova correção
      no mesmo campo coberto pela regra

    Args:
        db: Sessão SQLAlchemy

    Example:
        injector = RuleInjector(db)

        # Ao criar prompt:
        rules_text = injector.get_active_rules_for_prompt("legal_extraction")
        rule_ids = injector.get_active_rule_ids()
        injector.record_rules_usage(rule_ids)

        # Ao confirmar prévia sem correção adicional:
        injector.record_rules_success(rule_ids)
    """

    _CACHE_TTL = 300  # 5 minutos

    def __init__(self, db: Session) -> None:
        self._db = db
        self._cache: list[Any] = []
        self._cache_ts: float = 0

    # ── Interface pública ──────────────────────────────────────────────────────

    def get_active_rules_for_prompt(self, task_type: str) -> str:
        """
        Retorna string formatada com regras ativas para injeção num prompt.

        Args:
            task_type: Tipo de tarefa (string do TaskType.value)

        Returns:
            Texto markdown com regras relevantes (vazio se nenhuma)
        """
        rules = self._get_cached_rules()
        if not rules:
            return ""

        # Filtrar por relevância ao task_type
        relevant = self._filter_by_task(rules, task_type)
        if not relevant:
            return ""

        lines: list[str] = [
            "\n## Regras Aprendidas de Sessões Anteriores\n"
            "Aplique estas regras quando as condições indicadas se cumprirem:\n"
        ]
        for i, rule in enumerate(relevant[:15], 1):  # máx. 15 regras
            lines.append(
                f"**Regra {i}** ({rule.tipo_regra} | "
                f"{rule.confianca:.0%} confiança)\n"
                f"- Condição: {rule.condicao}\n"
                f"- Ação: {rule.acao}"
            )

        return "\n\n".join(lines)

    def get_active_rule_ids(self) -> list[int]:
        """Retorna IDs das regras atualmente em cache."""
        rules = self._get_cached_rules()
        return [r.id for r in rules if r.id]

    def record_rules_usage(self, rule_ids: list[int]) -> None:
        """
        Incrementa aplicacoes para as regras indicadas.
        Deve ser chamado quando as regras são incluídas em um prompt.
        """
        if not rule_ids:
            return
        try:
            from infrastructure.database import RegrasAprendidas
            self._db.query(RegrasAprendidas).filter(
                RegrasAprendidas.id.in_(rule_ids)
            ).update(
                {RegrasAprendidas.aplicacoes: RegrasAprendidas.aplicacoes + 1},
                synchronize_session=False,
            )
            self._db.commit()
        except Exception as e:
            logger.warning("rule_usage_record_failed", error=str(e))

    def record_rules_success(self, rule_ids: list[int]) -> None:
        """
        Incrementa acertos para as regras indicadas.
        Deve ser chamado quando o cálculo é confirmado sem correção adicional
        nos campos cobertos pela regra.
        """
        if not rule_ids:
            return
        try:
            from infrastructure.database import RegrasAprendidas
            self._db.query(RegrasAprendidas).filter(
                RegrasAprendidas.id.in_(rule_ids)
            ).update(
                {RegrasAprendidas.acertos: RegrasAprendidas.acertos + 1},
                synchronize_session=False,
            )
            self._db.commit()
        except Exception as e:
            logger.warning("rule_success_record_failed", error=str(e))

    def deactivate_rule(self, rule_id: int) -> bool:
        """
        Desativa uma regra específica (admin action).

        Returns:
            True se a regra foi encontrada e desativada
        """
        try:
            from infrastructure.database import RegrasAprendidas
            rule = self._db.query(RegrasAprendidas).filter_by(id=rule_id).first()
            if not rule:
                return False
            rule.ativa = False
            self._db.commit()
            self._invalidate_cache()
            return True
        except Exception as e:
            logger.error("rule_deactivate_failed", rule_id=rule_id, error=str(e))
            return False

    def invalidate_cache(self) -> None:
        """Invalida o cache (chamado após nova sessão de aprendizado)."""
        self._invalidate_cache()

    # ── Auxiliares privados ────────────────────────────────────────────────────

    def _get_cached_rules(self) -> list[Any]:
        """Retorna regras ativas com cache de 5 minutos."""
        now = time.monotonic()
        if now - self._cache_ts >= self._CACHE_TTL:
            self._refresh_cache()
        return self._cache

    def _refresh_cache(self) -> None:
        """Recarrega regras ativas do banco."""
        try:
            from infrastructure.database import RegrasAprendidas
            self._cache = (
                self._db.query(RegrasAprendidas)
                .filter(RegrasAprendidas.ativa == True)
                .order_by(RegrasAprendidas.confianca.desc())
                .all()
            )
            self._cache_ts = time.monotonic()
        except Exception as e:
            logger.warning("rule_cache_refresh_failed", error=str(e))
            self._cache = []

    def _invalidate_cache(self) -> None:
        self._cache = []
        self._cache_ts = 0

    def _filter_by_task(self, rules: list[Any], task_type: str) -> list[Any]:
        """Filtra regras relevantes para o tipo de tarefa."""
        # Mapeamento task_type → tipos de regra relevantes
        task_rule_mapping: dict[str, list[str]] = {
            "legal_extraction": [
                "extracao_campo", "mapeamento_verba", "reflexa", "correcao_juros"
            ],
            "legal_extraction_pdf": [
                "extracao_campo", "mapeamento_verba", "reflexa"
            ],
            "verba_classification": [
                "mapeamento_verba", "reflexa", "classificacao_parametro"
            ],
            "report_conversion": ["extracao_campo", "mapeamento_verba"],
        }

        relevant_types = task_rule_mapping.get(task_type, [])
        if not relevant_types:
            return []  # task_type sem regras relevantes (screenshot, crash, etc.)

        return [r for r in rules if r.tipo_regra in relevant_types]
