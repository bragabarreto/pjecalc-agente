# core/browser_manager.py — Gerenciador de ciclo de vida do Playwright com tenacity
#
# Fornece:
#   - Retries baseados em tenacity (substitui @retry homebrew de playwright_pjecalc.py)
#   - Context manager para lifecycle do browser
#   - Crash recovery via screenshot → LLM decision (Gemini)
#   - Detecção de ViewExpiredException e reload automático

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING

from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.llm_orchestrator import LLMOrchestrator, TaskType


# ── Exceções customizadas ─────────────────────────────────────────────────────

class PJECalcCrashError(Exception):
    """Chromium ou contexto Playwright crashou."""


class PJECalcViewExpiredError(Exception):
    """ViewState JSF expirou — recarregar a página."""


class PJECalcBrowserError(Exception):
    """Erro genérico de automação do browser."""


# ── Decorator de retry (substitui @retry homebrew) ────────────────────────────

def pjecalc_retry(
    max_attempts: int = 3,
    min_wait: int = 2,
    max_wait: int = 10,
) -> Callable:
    """
    Decorator de retry baseado em tenacity para funções de automação PJE-Calc.

    Comportamento:
    - 3 tentativas com backoff exponencial (2s, 4s, 8s)
    - Log de aviso antes de cada nova tentativa
    - Detecta crash do Chromium e ViewExpiredException para retry específico

    Args:
        max_attempts: Número máximo de tentativas
        min_wait: Espera mínima entre tentativas (segundos)
        max_wait: Espera máxima entre tentativas (segundos)

    Example:
        @pjecalc_retry(max_attempts=3)
        def preencher_aba(self, dados):
            ...
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


# ── BrowserManager ────────────────────────────────────────────────────────────

class BrowserManager:
    """
    Context manager para o ciclo de vida do Playwright no pjecalc-agente.

    Responsabilidades:
    - Inicializar e fechar o browser corretamente
    - Detectar crashes do Chromium e reiniciar em thread limpa
    - Detectar ViewExpiredException e recarregar a página
    - Capturar screenshot em caso de erro
    - Consultar LLMOrchestrator (Gemini) para decisões de recovery

    Uso como context manager:
        with BrowserManager(headless=True) as bm:
            page = bm.page
            page.goto(url)

    Uso standalone (como na playwright_pjecalc.py):
        bm = BrowserManager(headless=False)
        bm.start()
        # ... usar bm.page ...
        bm.stop()
    """

    def __init__(
        self,
        headless: Optional[bool] = None,
        screenshots_dir: Optional[Path] = None,
        orchestrator: Optional["LLMOrchestrator"] = None,
    ) -> None:
        """
        Args:
            headless: True = headless. None = auto (headless se não há DISPLAY)
            screenshots_dir: Diretório para screenshots de diagnóstico
            orchestrator: LLMOrchestrator para decisões de crash recovery
        """
        if headless is None:
            headless = sys.platform != "win32" and not os.environ.get("DISPLAY")
        self._headless = headless
        self._screenshots_dir = screenshots_dir or Path("data/logs/screenshots")
        self._orchestrator = orchestrator

        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    # ── Context manager ────────────────────────────────────────────────────────

    def __enter__(self) -> "BrowserManager":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    # ── Ciclo de vida ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Inicia Playwright, browser, context e page."""
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        logger.info("browser_started", headless=self._headless)

    def stop(self) -> None:
        """Fecha page, context, browser e playwright com tratamento de erros."""
        for obj, name in [
            (self._page, "page"),
            (self._context, "context"),
            (self._browser, "browser"),
            (self._playwright, "playwright"),
        ]:
            if obj:
                try:
                    obj.close()
                except Exception as e:
                    logger.debug(f"close_{name}_error", error=str(e))
        self._page = self._context = self._browser = self._playwright = None
        logger.info("browser_stopped")

    @property
    def page(self) -> Any:
        """Retorna a Page atual do Playwright."""
        if not self._page:
            raise PJECalcBrowserError("Browser não iniciado. Chame start() ou use como context manager.")
        return self._page

    # ── Crash recovery ────────────────────────────────────────────────────────

    def handle_crash(self, exc: Exception, func_name: str, attempt: int) -> bool:
        """
        Tenta recuperar de um crash do Chromium.

        Args:
            exc: Exceção capturada
            func_name: Nome da função que falhou (para log)
            attempt: Número da tentativa atual

        Returns:
            True se recuperação bem-sucedida, False se não foi possível

        Side effects:
            Salva screenshot, consulta Gemini se disponível, reinicia browser
        """
        exc_str = str(exc)
        is_crash = any(k in exc_str for k in (
            "Target crashed",
            "Target page, context or browser has been closed",
            "Execution context was destroyed",
        ))

        if not is_crash:
            # Verificar ViewExpired
            try:
                if self._page:
                    body = self._page.locator("body").text_content() or ""
                    if "ViewExpired" in body or "expired" in body.lower():
                        logger.warning("viewstate_expired", func=func_name)
                        self._page.reload()
                        self._page.wait_for_load_state("networkidle")
                        return True
            except Exception:
                pass
            return False

        # Crash do Chromium → screenshot + reiniciar
        screenshot_path = self._take_screenshot(f"crash_{func_name}_{attempt}")
        logger.warning(
            "chromium_crash",
            func=func_name,
            attempt=attempt,
            screenshot=str(screenshot_path),
        )

        # Consultar Gemini para decisão de recovery (se disponível)
        if screenshot_path and self._orchestrator:
            try:
                self._ask_llm_for_recovery(screenshot_path, func_name)
            except Exception as e:
                logger.debug("llm_recovery_query_failed", error=str(e))

        # Reiniciar browser em thread nova (evita conflito com asyncio)
        return self._restart_browser_in_fresh_thread()

    def _restart_browser_in_fresh_thread(self) -> bool:
        """Reinicia o browser Playwright em uma thread totalmente nova (sem contexto asyncio)."""
        try:
            self.stop()
        except Exception:
            pass

        errors: list[Exception] = []

        def _restart() -> None:
            try:
                self.start()
            except Exception as e:
                errors.append(e)

        t = threading.Thread(target=_restart, daemon=True)
        t.start()
        t.join(timeout=30)

        if errors:
            logger.error("browser_restart_failed", error=str(errors[0]))
            return False

        logger.info("browser_restarted")
        return True

    def _take_screenshot(self, name: str) -> Optional[Path]:
        """Captura screenshot da página atual para diagnóstico."""
        if not self._page:
            return None
        try:
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            path = self._screenshots_dir / f"{ts}_{name}.png"
            self._page.screenshot(path=str(path), full_page=True)
            return path
        except Exception as e:
            logger.debug("screenshot_failed", error=str(e))
            return None

    def _ask_llm_for_recovery(self, screenshot_path: Path, context: str) -> None:
        """
        Envia screenshot ao LLM (Gemini) para obter sugestão de ação de recovery.
        Não bloqueia o fluxo principal — resultado é apenas logado.
        """
        from core.llm_orchestrator import TaskType
        import base64

        with open(screenshot_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode()

        prompt = (
            f"Screenshot capturado após falha na função '{context}' do PJE-Calc.\n"
            "Analise a imagem e descreva brevemente:\n"
            "1. O que está sendo mostrado na tela\n"
            "2. Qual parece ser o problema\n"
            "3. Qual ação de recovery é recomendada (reload, navegar para principal, aguardar, etc.)"
        )

        result = self._orchestrator.complete(  # type: ignore
            TaskType.CRASH_RECOVERY,
            prompt,
            images=[{"media_type": "image/png", "data": img_data}],
            inject_knowledge=False,
            inject_learned_rules=False,
            timeout=30,
        )
        logger.info("llm_crash_recovery_suggestion", suggestion=str(result)[:300])
