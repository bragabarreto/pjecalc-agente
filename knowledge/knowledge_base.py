# knowledge/knowledge_base.py — Serve conteúdo da knowledge base aos prompts LLM

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.llm_orchestrator import TaskType


# Diretório dos arquivos de conhecimento oficial
_KNOWLEDGE_DIR = Path(__file__).parent / "pje_calc_official"


class KnowledgeBase:
    """
    Carrega e serve o conhecimento oficial PJE-Calc para injeção em prompts LLM.

    Conteúdo servido:
    - system_prompt_base.txt: prompt base completo com regras PJE-Calc
    - verba_catalog_official.md: catálogo de 40+ verbas com configuração
    - manual_excerpts.md: seções chave do Manual Oficial
    - tutorial_rules.md: regras práticas do Tutorial Oficial
    - RegrasAprendidas ativas do banco de dados (cache 5 min)

    Args:
        knowledge_dir: Diretório com arquivos de conhecimento
        db_session: Sessão SQLAlchemy para consultar RegrasAprendidas (opcional)

    Example:
        kb = KnowledgeBase()
        system_prompt = kb.get_system_prompt(TaskType.LEGAL_EXTRACTION)
        orchestrator = LLMOrchestrator(settings, kb)
    """

    _CACHE_TTL = 300  # 5 minutos

    def __init__(
        self,
        knowledge_dir: Optional[Path] = None,
        db_session: Optional[Any] = None,
    ) -> None:
        self._dir = knowledge_dir or _KNOWLEDGE_DIR
        self._db = db_session
        self._file_cache: dict[str, str] = {}
        self._rules_cache: list[dict] = []
        self._rules_cache_ts: float = 0

    # ── Interface pública ──────────────────────────────────────────────────────

    def get_system_prompt(self, task_type: "TaskType") -> str:
        """
        Retorna o system prompt base para o tipo de tarefa.

        Args:
            task_type: Tipo de tarefa (TaskType enum)

        Returns:
            Conteúdo de system_prompt_base.txt com placeholder [REGRAS_APRENDIDAS]
            substituído pelas regras aprendidas ativas (se disponíveis)
        """
        from core.llm_orchestrator import TaskType as TT

        base = self._load_file("system_prompt_base.txt")

        # Injetar regras aprendidas no placeholder
        rules_text = self.format_rules_for_prompt(self.get_learned_rules())
        if rules_text and "[REGRAS_APRENDIDAS]" in base:
            base = base.replace("[REGRAS_APRENDIDAS]", rules_text)
        elif "[REGRAS_APRENDIDAS]" in base:
            base = base.replace("[REGRAS_APRENDIDAS]", "")

        return base

    def get_verba_catalog(self) -> str:
        """
        Retorna o catálogo completo de verbas PJE-Calc em markdown.

        Returns:
            Conteúdo de verba_catalog_official.md
        """
        return self._load_file("verba_catalog_official.md")

    def get_relevant_sections(self, task_type: "TaskType") -> str:
        """
        Retorna os trechos do manual/tutorial mais relevantes para a tarefa.

        Args:
            task_type: Tipo de tarefa — determina quais seções incluir

        Returns:
            String com seções concatenadas (vazia se task_type não precisa de contexto)
        """
        from core.llm_orchestrator import TaskType as TT

        sections: list[str] = []

        if task_type in (TT.LEGAL_EXTRACTION, TT.LEGAL_EXTRACTION_PDF, TT.REPORT_CONVERSION):
            # Extração precisa de tudo: verbas + manual + tutorial
            sections.append(self._load_file("verba_catalog_official.md"))

        elif task_type == TT.VERBA_CLASSIFICATION:
            # Classificação: catálogo de verbas + regras de reflexas
            sections.append(self._load_file("verba_catalog_official.md"))
            sections.append(self._section_from_manual("Seção 2 — Tipos de Lançamento"))

        elif task_type == TT.LEARNING_ANALYSIS:
            # Aprendizado: manual completo + catálogo para raciocínio sobre regras
            sections.append(self._load_file("manual_excerpts.md"))
            sections.append(self._load_file("tutorial_rules.md"))
            sections.append(self._load_file("verba_catalog_official.md"))

        elif task_type in (TT.SCREENSHOT_ANALYSIS, TT.CRASH_RECOVERY):
            # Visão/recovery: manual de preenchimento e tutorial
            sections.append(self._section_from_tutorial("Regra 8 — Erros comuns"))

        return "\n\n".join(s for s in sections if s)

    def get_learned_rules(
        self,
        rule_type: Optional[str] = None,
        active_only: bool = True,
    ) -> list[dict]:
        """
        Retorna regras aprendidas do banco de dados (cache 5 min).

        Args:
            rule_type: Filtrar por tipo (mapeamento_verba, extracao_campo, etc.)
            active_only: Retornar apenas regras ativas

        Returns:
            Lista de dicts com {tipo_regra, condicao, acao, confianca, aplicacoes, acertos}
        """
        if not self._db:
            return []

        now = time.monotonic()
        if now - self._rules_cache_ts < self._CACHE_TTL:
            rules = self._rules_cache
        else:
            try:
                from infrastructure.database import RegrasAprendidas
                query = self._db.query(RegrasAprendidas)
                if active_only:
                    query = query.filter(RegrasAprendidas.ativa == True)
                if rule_type:
                    query = query.filter(RegrasAprendidas.tipo_regra == rule_type)
                rules_orm = query.order_by(RegrasAprendidas.confianca.desc()).all()
                self._rules_cache = [
                    {
                        "id": r.id,
                        "tipo_regra": r.tipo_regra,
                        "condicao": r.condicao,
                        "acao": r.acao,
                        "confianca": r.confianca,
                        "aplicacoes": r.aplicacoes,
                        "acertos": r.acertos,
                    }
                    for r in rules_orm
                ]
                self._rules_cache_ts = now
                rules = self._rules_cache
            except Exception as e:
                logger.warning("learned_rules_fetch_failed", error=str(e))
                rules = []

        if rule_type:
            rules = [r for r in rules if r.get("tipo_regra") == rule_type]

        return rules

    def format_rules_for_prompt(self, rules: list[dict]) -> str:
        """
        Formata lista de regras para injeção num system prompt.

        Args:
            rules: Lista de dicts de RegrasAprendidas

        Returns:
            Texto formatado em markdown para inclusão no prompt
        """
        if not rules:
            return ""

        lines: list[str] = []
        lines.append(
            "As regras a seguir foram aprendidas de correções feitas por usuários. "
            "Aplique-as quando as condições indicadas se cumprirem:"
        )
        for i, rule in enumerate(rules[:20], 1):  # máx. 20 regras por prompt
            lines.append(
                f"\n**Regra {i}** ({rule.get('tipo_regra', '?')} | "
                f"confiança: {rule.get('confianca', 0):.0%})\n"
                f"- Condição: {rule.get('condicao', '')}\n"
                f"- Ação: {rule.get('acao', '')}"
            )

        return "\n".join(lines)

    def invalidate_rules_cache(self) -> None:
        """Invalida o cache de regras (chamado após nova sessão de aprendizado)."""
        self._rules_cache = []
        self._rules_cache_ts = 0

    # ── Auxiliares privados ────────────────────────────────────────────────────

    def _load_file(self, filename: str) -> str:
        """Carrega e cache um arquivo de conhecimento."""
        if filename in self._file_cache:
            return self._file_cache[filename]

        path = self._dir / filename
        try:
            content = path.read_text(encoding="utf-8")
            self._file_cache[filename] = content
            return content
        except FileNotFoundError:
            logger.warning("knowledge_file_missing", filename=filename, path=str(path))
            return ""
        except OSError as e:
            logger.error("knowledge_file_read_error", filename=filename, error=str(e))
            return ""

    def _section_from_manual(self, section_header: str) -> str:
        """Extrai uma seção específica do manual."""
        content = self._load_file("manual_excerpts.md")
        return self._extract_section(content, section_header)

    def _section_from_tutorial(self, section_header: str) -> str:
        """Extrai uma seção específica do tutorial."""
        content = self._load_file("tutorial_rules.md")
        return self._extract_section(content, section_header)

    def _extract_section(self, content: str, header: str) -> str:
        """Extrai texto entre o header e o próximo header de nível igual."""
        if not content or header not in content:
            return ""

        idx = content.find(header)
        if idx == -1:
            return ""

        # Encontrar o próximo header do mesmo nível (## ou ###)
        level = "## " if content[idx:idx+3] == "## " else "### "
        next_idx = content.find(f"\n{level}", idx + 1)

        if next_idx == -1:
            return content[idx:]
        return content[idx:next_idx]
