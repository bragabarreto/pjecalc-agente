# tests/test_llm_orchestrator.py — Testes do orquestrador LLM multi-modelo

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


@pytest.fixture()
def mock_settings():
    settings = MagicMock()
    settings.anthropic_api_key = "sk-ant-test-key"
    settings.gemini_api_key = ""
    settings.claude_model = "claude-sonnet-4-6"
    settings.gemini_model = "gemini-2.5-flash"
    settings.claude_max_tokens = 4096
    settings.claude_extraction_temperature = 0.0
    return settings


@pytest.fixture()
def mock_settings_gemini(mock_settings):
    mock_settings.gemini_api_key = "AIza-test-key"
    return mock_settings


@pytest.fixture()
def orchestrator_claude_only(mock_settings):
    from core.llm_orchestrator import LLMOrchestrator
    return LLMOrchestrator(mock_settings)


@pytest.fixture()
def orchestrator_gemini(mock_settings_gemini):
    from core.llm_orchestrator import LLMOrchestrator
    return LLMOrchestrator(mock_settings_gemini)


# ── Routing ───────────────────────────────────────────────────────────────────

class TestRouting:
    def test_legal_extraction_routes_to_claude(self, orchestrator_claude_only):
        from core.llm_orchestrator import TaskType
        primary, _ = orchestrator_claude_only._route_model(TaskType.LEGAL_EXTRACTION)
        assert primary == "claude"

    def test_legal_extraction_pdf_routes_to_claude(self, orchestrator_claude_only):
        from core.llm_orchestrator import TaskType
        primary, _ = orchestrator_claude_only._route_model(TaskType.LEGAL_EXTRACTION_PDF)
        assert primary == "claude"

    def test_verba_classification_routes_to_claude(self, orchestrator_claude_only):
        from core.llm_orchestrator import TaskType
        primary, _ = orchestrator_claude_only._route_model(TaskType.VERBA_CLASSIFICATION)
        assert primary == "claude"

    def test_screenshot_routes_to_gemini(self, orchestrator_gemini):
        from core.llm_orchestrator import TaskType
        primary, fallback = orchestrator_gemini._route_model(TaskType.SCREENSHOT_ANALYSIS)
        assert primary == "gemini"
        assert fallback == "claude"

    def test_crash_recovery_routes_to_gemini(self, orchestrator_gemini):
        from core.llm_orchestrator import TaskType
        primary, _ = orchestrator_gemini._route_model(TaskType.CRASH_RECOVERY)
        assert primary == "gemini"

    def test_fallback_when_gemini_unavailable(self, orchestrator_claude_only):
        """Screenshot routing com Gemini ausente → usa Claude (fallback)."""
        from core.llm_orchestrator import TaskType
        primary, _ = orchestrator_claude_only._route_model(TaskType.SCREENSHOT_ANALYSIS)
        # Gemini não disponível → route redireciona para fallback (claude)
        assert primary == "claude"

    def test_no_model_available_raises(self, mock_settings):
        """Sem chaves configuradas → RuntimeError."""
        mock_settings.anthropic_api_key = ""
        mock_settings.gemini_api_key = ""
        from core.llm_orchestrator import LLMOrchestrator, TaskType

        orch = LLMOrchestrator(mock_settings)
        with pytest.raises(RuntimeError, match="Nenhum modelo disponível"):
            orch._route_model(TaskType.LEGAL_EXTRACTION)


# ── System prompt injection ───────────────────────────────────────────────────

class TestSystemPromptInjection:
    def test_build_system_prompt_no_kb(self, orchestrator_claude_only):
        """Sem knowledge base → retorna apenas o base prompt."""
        from core.llm_orchestrator import TaskType
        base = "Base prompt do sistema."
        result = orchestrator_claude_only._build_system_prompt(
            TaskType.LEGAL_EXTRACTION, base,
            inject_knowledge=True, inject_learned_rules=True,
        )
        # Sem KB, deve conter pelo menos o base
        assert "Base prompt do sistema." in result

    def test_build_system_prompt_with_kb(self, mock_settings):
        """Com knowledge base → injeta conteúdo relevante."""
        from core.llm_orchestrator import LLMOrchestrator, TaskType

        mock_kb = MagicMock()
        mock_kb.get_system_prompt.return_value = "System base from KB."
        mock_kb.get_relevant_sections.return_value = "ADC 58 rule."
        mock_kb.get_learned_rules.return_value = []
        mock_kb.format_rules_for_prompt.return_value = ""

        orch = LLMOrchestrator(mock_settings, knowledge_base=mock_kb)
        result = orch._build_system_prompt(
            TaskType.LEGAL_EXTRACTION, None,
            inject_knowledge=True, inject_learned_rules=False,
        )
        assert "ADC 58 rule." in result

    def test_learned_rules_injected_in_prompt(self, mock_settings):
        """Regras aprendidas são incluídas no prompt quando inject_learned_rules=True."""
        from core.llm_orchestrator import LLMOrchestrator, TaskType

        mock_kb = MagicMock()
        mock_kb.get_system_prompt.return_value = "Base."
        mock_kb.get_relevant_sections.return_value = ""
        mock_kb.get_learned_rules.return_value = [{"tipo_regra": "mapeamento_verba"}]
        mock_kb.format_rules_for_prompt.return_value = "Regra 1: sempre usar FGTS 8%."

        orch = LLMOrchestrator(mock_settings, knowledge_base=mock_kb)
        result = orch._build_system_prompt(
            TaskType.LEGAL_EXTRACTION, "Base.",
            inject_knowledge=False, inject_learned_rules=True,
        )
        assert "Regra 1: sempre usar FGTS 8%." in result

    def test_knowledge_not_injected_when_disabled(self, mock_settings):
        """inject_knowledge=False → KB não incluída."""
        from core.llm_orchestrator import LLMOrchestrator, TaskType

        mock_kb = MagicMock()
        mock_kb.get_system_prompt.return_value = "System base."
        mock_kb.get_relevant_sections.return_value = "SEÇÃO KB NÃO DEVE APARECER."
        mock_kb.get_learned_rules.return_value = []
        mock_kb.format_rules_for_prompt.return_value = ""

        orch = LLMOrchestrator(mock_settings, knowledge_base=mock_kb)
        result = orch._build_system_prompt(
            TaskType.LEGAL_EXTRACTION, "System base.",
            inject_knowledge=False, inject_learned_rules=False,
        )
        assert "SEÇÃO KB NÃO DEVE APARECER." not in result


# ── JSON parsing ──────────────────────────────────────────────────────────────

class TestResponseParsing:
    def test_parse_valid_json(self, orchestrator_claude_only):
        result = orchestrator_claude_only._parse_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_in_markdown_block(self, orchestrator_claude_only):
        raw = '```json\n{"processo": {"numero": "1234"}}\n```'
        result = orchestrator_claude_only._parse_response(raw)
        assert isinstance(result, dict)
        assert result.get("processo", {}).get("numero") == "1234"

    def test_parse_non_json_returns_string(self, orchestrator_claude_only):
        result = orchestrator_claude_only._parse_response("Texto puro sem JSON.")
        assert isinstance(result, str)
        assert "Texto puro" in result

    def test_parse_empty_returns_empty_dict(self, orchestrator_claude_only):
        result = orchestrator_claude_only._parse_response("")
        # Vazio → retorna string vazia ou dict vazio
        assert result == "" or result == {}


# ── is_available ──────────────────────────────────────────────────────────────

class TestAvailability:
    def test_claude_available_with_key(self, orchestrator_claude_only):
        avail = orchestrator_claude_only.is_available()
        assert avail["claude"] is True
        assert avail["gemini"] is False

    def test_gemini_available_with_key(self, orchestrator_gemini):
        avail = orchestrator_gemini.is_available()
        assert avail["gemini"] is True

    def test_both_unavailable_with_empty_keys(self, mock_settings):
        mock_settings.anthropic_api_key = ""
        mock_settings.gemini_api_key = ""
        from core.llm_orchestrator import LLMOrchestrator

        orch = LLMOrchestrator(mock_settings)
        avail = orch.is_available()
        assert avail["claude"] is False
        assert avail["gemini"] is False
