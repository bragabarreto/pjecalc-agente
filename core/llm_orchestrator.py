# core/llm_orchestrator.py — Orquestrador Multi-LLM com injeção de knowledge base
#
# Routing:
#   Claude  → raciocínio jurídico profundo, extração, classificação, aprendizado
#   Gemini  → análise de screenshots, crash recovery, validações rápidas
#
# O orquestrador injeta automaticamente:
#   1. Conteúdo de knowledge/pje_calc_official/ nos system prompts
#   2. Regras aprendidas (RegrasAprendidas ativas) nos prompts de extração/classificação

from __future__ import annotations

import concurrent.futures
import json
import logging
import time
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from knowledge.knowledge_base import KnowledgeBase
    from infrastructure.config import Settings


class TaskType(str, Enum):
    """Tipos de tarefa para roteamento de modelo LLM."""
    LEGAL_EXTRACTION = "legal_extraction"           # Extração de sentença (texto)
    LEGAL_EXTRACTION_PDF = "legal_extraction_pdf"   # Extração de sentença (PDF nativo)
    VERBA_CLASSIFICATION = "verba_classification"   # Classificação de verbas desconhecidas
    REPORT_CONVERSION = "report_conversion"         # Conversão de relatório estruturado
    SCREENSHOT_ANALYSIS = "screenshot_analysis"     # Análise de screenshot (visão)
    CRASH_RECOVERY = "crash_recovery"               # Decisão de recovery após crash
    LEARNING_ANALYSIS = "learning_analysis"         # Análise de correções para aprendizado
    QUICK_VALIDATION = "quick_validation"           # Validação rápida de dados
    VERBA_MATCHING = "verba_matching"               # Matching semântico de verbas (sentença → Expresso)


# Routing: (modelo_primário, modelo_fallback)
# None = sem fallback para aquele tipo de tarefa
_ROUTING: dict[TaskType, tuple[str, Optional[str]]] = {
    TaskType.LEGAL_EXTRACTION:      ("claude", None),
    TaskType.LEGAL_EXTRACTION_PDF:  ("claude", None),
    TaskType.VERBA_CLASSIFICATION:  ("claude", None),
    TaskType.REPORT_CONVERSION:     ("claude", "gemini"),
    TaskType.SCREENSHOT_ANALYSIS:   ("gemini", "claude"),
    TaskType.CRASH_RECOVERY:        ("gemini", "claude"),
    TaskType.LEARNING_ANALYSIS:     ("claude", None),
    TaskType.QUICK_VALIDATION:      ("gemini", "claude"),
    TaskType.VERBA_MATCHING:        ("gemini", "claude"),  # Rápido + barato; Claude como fallback
}


class LLMOrchestrator:
    """
    Orquestrador multi-LLM para o pjecalc-agente.

    Responsabilidades:
    - Rotear tarefas para Claude ou Gemini com base no tipo
    - Injetar knowledge base oficial do PJE-Calc nos system prompts
    - Injetar regras aprendidas (LearningEngine) nos prompts relevantes
    - Gerenciar fallback automático quando modelo primário falha
    - Parse de respostas JSON estruturadas

    Args:
        settings: Instância de Settings (infrastructure/config.py)
        knowledge_base: Instância de KnowledgeBase (knowledge/knowledge_base.py)

    Example:
        orchestrator = LLMOrchestrator(settings, knowledge_base)
        result = orchestrator.complete(
            TaskType.LEGAL_EXTRACTION,
            prompt="Extraia os dados da sentença: ...",
        )
    """

    def __init__(
        self,
        settings: "Settings",
        knowledge_base: Optional["KnowledgeBase"] = None,
    ) -> None:
        self._settings = settings
        self._kb = knowledge_base

        # Inicializar clientes LLM (lazy — só quando necessário)
        self._claude_client: Any = None
        self._gemini_client: Any = None

    # ── Interface pública ──────────────────────────────────────────────────────

    def complete(
        self,
        task_type: TaskType,
        prompt: str,
        *,
        system_override: Optional[str] = None,
        inject_knowledge: bool = True,
        inject_learned_rules: bool = True,
        images: Optional[list[dict]] = None,
        timeout: int = 120,
    ) -> dict | str:
        """
        Executa uma chamada LLM com roteamento automático e injeção de knowledge.

        Args:
            task_type: Tipo da tarefa — determina qual modelo usar
            prompt: Prompt do usuário
            system_override: Se fornecido, substitui o system prompt base
            inject_knowledge: Se True, injeta trechos do manual oficial PJE-Calc
            inject_learned_rules: Se True, injeta regras aprendidas relevantes
            images: Lista de {type: "base64", media_type: ..., data: ...} para visão
            timeout: Timeout em segundos para a chamada LLM

        Returns:
            dict se a resposta for JSON válido, str caso contrário

        Raises:
            RuntimeError: Se todos os modelos disponíveis falharem
        """
        system = self._build_system_prompt(
            task_type,
            base=system_override,
            inject_knowledge=inject_knowledge,
            inject_learned_rules=inject_learned_rules,
        )

        primary, fallback = self._route_model(task_type)
        models_to_try = [m for m in [primary, fallback] if m]

        last_error: Exception = RuntimeError("Nenhum modelo disponível")
        for model_name in models_to_try:
            try:
                if model_name == "claude":
                    raw = self._call_claude(system, prompt, images=images, timeout=timeout)
                else:
                    raw = self._call_gemini(system, prompt, timeout=timeout)
                return self._parse_response(raw)
            except Exception as e:
                logger.warning(
                    "llm_call_failed",
                    model=model_name,
                    task_type=task_type.value,
                    error=str(e),
                )
                last_error = e

        raise RuntimeError(
            f"Todos os modelos falharam para {task_type.value}: {last_error}"
        ) from last_error

    def is_available(self) -> dict[str, bool]:
        """Retorna disponibilidade de cada modelo (chave configurada)."""
        return {
            "claude": bool(self._settings.anthropic_api_key),
            "gemini": bool(self._settings.gemini_api_key),
        }

    # ── Construção do system prompt ────────────────────────────────────────────

    def _build_system_prompt(
        self,
        task_type: TaskType,
        base: Optional[str],
        inject_knowledge: bool,
        inject_learned_rules: bool,
    ) -> str:
        """
        Monta o system prompt final com:
        1. Base (override ou default para o task_type)
        2. Knowledge base oficial injetada (se inject_knowledge=True)
        3. Regras aprendidas injetadas (se inject_learned_rules=True)
        """
        parts: list[str] = []

        # 1. Base
        if base:
            parts.append(base)
        elif self._kb:
            kb_prompt = self._kb.get_system_prompt(task_type)
            if kb_prompt:
                parts.append(kb_prompt)

        # 2. Knowledge base sections relevantes para a tarefa
        if inject_knowledge and self._kb:
            sections = self._kb.get_relevant_sections(task_type)
            if sections:
                parts.append("\n## Conhecimento Oficial PJE-Calc\n" + sections)

        # 3. Regras aprendidas
        if inject_learned_rules and self._kb:
            rules_text = self._kb.format_rules_for_prompt(
                self._kb.get_learned_rules()
            )
            if rules_text:
                parts.append("\n## Regras Aprendidas de Correções Anteriores\n" + rules_text)

        return "\n\n".join(parts) if parts else _DEFAULT_SYSTEM_PROMPT

    # ── Routing ───────────────────────────────────────────────────────────────

    def _route_model(self, task_type: TaskType) -> tuple[str, Optional[str]]:
        """
        Retorna (modelo_primário, modelo_fallback) para o tipo de tarefa.
        Respeita disponibilidade real (chaves configuradas).
        """
        primary, fallback = _ROUTING.get(task_type, ("claude", None))

        # Se o modelo primário não tem chave configurada, tentar o fallback
        available = self.is_available()
        if not available.get(primary) and fallback and available.get(fallback):
            return fallback, None
        if not available.get(primary) and not (fallback and available.get(fallback)):
            raise RuntimeError(
                f"Nenhum modelo disponível para {task_type.value}. "
                "Configure ANTHROPIC_API_KEY e/ou GEMINI_API_KEY."
            )

        return primary, fallback if available.get(fallback or "") else None

    # ── Chamadas Claude ────────────────────────────────────────────────────────

    def _get_claude_client(self) -> Any:
        if self._claude_client is None:
            import anthropic
            self._claude_client = anthropic.Anthropic(
                api_key=self._settings.anthropic_api_key
            )
        return self._claude_client

    def _call_claude(
        self,
        system: str,
        prompt: str,
        images: Optional[list[dict]] = None,
        timeout: int = 120,
    ) -> str:
        """
        Chama Claude API (Anthropic).

        Args:
            system: System prompt
            prompt: User prompt
            images: Lista de imagens para visão multimodal
            timeout: Timeout em segundos

        Returns:
            Texto da resposta
        """
        client = self._get_claude_client()

        # Montar conteúdo (texto + imagens opcionais)
        content: list[dict] = []
        if images:
            for img in images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("media_type", "image/png"),
                        "data": img["data"],
                    },
                })
        content.append({"type": "text", "text": prompt})

        response = client.messages.create(
            model=self._settings.claude_model,
            max_tokens=self._settings.claude_max_tokens,
            temperature=self._settings.claude_extraction_temperature,
            system=system,
            messages=[{"role": "user", "content": content}],
            timeout=timeout,
        )
        return response.content[0].text

    # ── Chamadas Gemini ────────────────────────────────────────────────────────

    def _get_gemini_client(self) -> Any:
        if self._gemini_client is None:
            from google import genai  # type: ignore
            self._gemini_client = genai.Client(api_key=self._settings.gemini_api_key)
        return self._gemini_client

    def _call_gemini(
        self,
        system: str,
        prompt: str,
        timeout: int = 60,
    ) -> str:
        """
        Chama Gemini API (Google) com timeout via ThreadPoolExecutor.

        Args:
            system: System prompt (enviado como contexto no user message)
            prompt: User prompt
            timeout: Timeout em segundos

        Returns:
            Texto da resposta
        """
        client = self._get_gemini_client()

        # Gemini não tem system role separado — concatenamos
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        def _call() -> str:
            response = client.models.generate_content(
                model=self._settings.gemini_model,
                contents=full_prompt,
            )
            return response.text

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"Gemini não respondeu em {timeout}s"
                )

    # ── Parse de resposta ──────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> dict | str:
        """
        Tenta parsear a resposta como JSON.
        Retorna dict se JSON válido, str caso contrário.
        """
        import re
        text = raw.strip()

        # Remover blocos markdown
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Tentar extrair bloco JSON
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return raw  # Retorna string bruta se não for JSON


# ── Default system prompt (fallback quando knowledge base não disponível) ─────

_DEFAULT_SYSTEM_PROMPT = """Você é um especialista em Direito do Trabalho brasileiro e no sistema \
PJE-Calc (Programa de Cálculos da Justiça do Trabalho — CNJ/TST).
Responda com precisão técnica e jurídica. Quando retornar JSON, retorne SOMENTE JSON válido \
sem markdown, sem texto antes ou depois."""
