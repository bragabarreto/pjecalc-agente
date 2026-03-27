# modules/playwright_pjecalc.py — Automação Playwright para PJE-Calc Cidadão
#
# Implementação conforme Manual Técnico v2.0:
#   - Verificação HTTP após TCP (não apenas porta)
#   - Decorator @retry com detecção de ViewExpiredException
#   - Monitor de AJAX JSF nativo (jsf.ajax.addOnEvent)
#   - Hierarquia de seletores: get_by_label → [id$=] → XPath contains → escaped CSS
#   - press_sequentially para campos de data
#   - Mapeamento dinâmico de campos para diagnóstico
#   - Tratamento do erro de primeira carga do PJE-Calc

from __future__ import annotations

import functools
import json
import re
import socket
import subprocess
import time
import urllib.request
import logging
import os
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# URL base do PJE-Calc — lida de config/env uma vez no import do módulo
try:
    from config import PJECALC_LOCAL_URL as _PJECALC_LOCAL_URL
except ImportError:
    _PJECALC_LOCAL_URL = os.environ.get(
        "PJECALC_LOCAL_URL", "http://localhost:9257/pjecalc"
    )

# Porta extraída da URL base (para checagem TCP de fallback)
def _porta_local() -> int:
    try:
        import urllib.parse as _p
        return int(_p.urlparse(_PJECALC_LOCAL_URL).port or 9257)
    except Exception:
        return 9257


# ── Decorator de retry ────────────────────────────────────────────────────────

def retry(max_tentativas: int = 3, delay: int = 2):
    """Retry automático com screenshot em falha, detecção de ViewExpiredException e crash recovery."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self: "PJECalcPlaywright", *args, **kwargs):
            ultima_exc = None
            for tentativa in range(1, max_tentativas + 1):
                try:
                    return func(self, *args, **kwargs)
                except Exception as exc:
                    ultima_exc = exc
                    self._log(f"  ⚠ Tentativa {tentativa}/{max_tentativas} em {func.__name__}: {exc}")
                    # Screenshot para diagnóstico
                    try:
                        os.makedirs("screenshots", exist_ok=True)
                        self._page.screenshot(
                            path=f"screenshots/erro_{func.__name__}_{tentativa}.png",
                            full_page=True,
                        )
                    except Exception:
                        pass
                    # Recuperar crash do Chromium (Target crashed / context destruído)
                    exc_str = str(exc)
                    if any(k in exc_str for k in ("Target crashed", "Target page, context or browser has been closed",
                                                    "Execution context was destroyed")):
                        self._log("  🔄 Chromium crashou — reiniciando browser…")
                        try:
                            self.fechar()
                        except Exception:
                            pass
                        try:
                            import sys
                            headless = getattr(self, "_headless", sys.platform != "win32")
                            self.iniciar_browser(headless=headless)
                            self._instalar_monitor_ajax()
                            self._page.goto(
                                f"{self.PJECALC_BASE}/pages/principal.jsf",
                                wait_until="domcontentloaded", timeout=30000
                            )
                            self._page.wait_for_timeout(2000)
                            self._log("  ✓ Browser reiniciado — retentando fase…")
                        except Exception as re_exc:
                            self._log(f"  ⚠ Falha ao reiniciar browser: {re_exc}")
                    # Recupera ViewState expirado
                    try:
                        body = self._page.locator("body").text_content() or ""
                        if "ViewExpired" in body or "expired" in body.lower():
                            self._log("  ↻ ViewState expirado — recarregando página…")
                            self._page.reload()
                            self._page.wait_for_load_state("networkidle")
                    except Exception:
                        pass
                    if tentativa < max_tentativas:
                        time.sleep(delay * tentativa)
            raise ultima_exc
        return wrapper
    return decorator


# ── Verificação e inicialização do PJE-Calc ───────────────────────────────────

def pjecalc_rodando() -> bool:
    """
    Retorna True se o PJE-Calc já está disponível via HTTP.
    Aceita 200, 302 e 404 — qualquer resposta HTTP indica Tomcat ativo.
    404 = Tomcat up mas webapp ainda deployando; 200/302 = totalmente pronto.
    Fallback para TCP se a checagem HTTP falhar (ex: timeout de rede).
    """
    try:
        with urllib.request.urlopen(_PJECALC_LOCAL_URL, timeout=2) as r:
            return r.status in (200, 302, 404)
    except Exception:
        pass
    # Fallback TCP: porta aberta sem resposta HTTP ainda
    try:
        s = socket.create_connection(("127.0.0.1", _porta_local()), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def iniciar_pjecalc(pjecalc_dir: str | Path, timeout: int = 180, log_cb=None) -> None:
    """
    Inicia o PJE-Calc Cidadão via iniciarPjeCalc.bat (Windows) ou iniciarPjeCalc.sh (Linux).
    Aguarda:
      1) porta TCP abrir
      2) HTTP responder com 200/302/404
    Emite mensagens de progresso via log_cb durante a espera.
    """
    import platform
    _log = log_cb or (lambda m: None)
    dir_path = Path(pjecalc_dir)

    if pjecalc_rodando():
        # pjecalc_rodando() já confirmou HTTP — sem espera adicional.
        # (O SSE em webapp.py faz a espera longa de 600s; aqui só confirmamos.)
        logger.info(f"PJE-Calc HTTP disponível em {_PJECALC_LOCAL_URL} — iniciando automação.")
        _log("PJE-Calc disponível — iniciando automação…")
        return

    logger.info(f"Iniciando PJE-Calc Cidadão a partir de {dir_path}…")
    _log("Iniciando PJE-Calc Cidadão… (pode levar até 3 minutos)")

    sistema = platform.system()
    if sistema == "Windows":
        launcher = dir_path / "iniciarPjeCalc.bat"
        if not launcher.exists():
            raise FileNotFoundError(
                f"iniciarPjeCalc.bat não encontrado em {dir_path}. "
                "Verifique a configuração PJECALC_DIR."
            )
        subprocess.Popen(
            ["cmd", "/c", str(launcher)],
            cwd=str(dir_path),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    elif sistema == "Darwin":
        # macOS: usa iniciarPjeCalc-macos.sh (Bootstrap direto, sem Xvfb/xdotool)
        # Fallback: iniciarPjeCalc.sh genérico, depois .app bundle
        macos_launcher = Path(__file__).parent.parent / "iniciarPjeCalc-macos.sh"
        generic_launcher = dir_path / "iniciarPjeCalc.sh"
        app_bundle = dir_path / "PJE-Calc.app"
        if macos_launcher.exists():
            subprocess.Popen(
                ["bash", str(macos_launcher)],
                env={**os.environ, "PJECALC_DIR": str(dir_path)},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif generic_launcher.exists():
            subprocess.Popen(
                ["bash", str(generic_launcher)],
                cwd=str(dir_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif app_bundle.exists():
            subprocess.Popen(["open", str(app_bundle)])
        else:
            raise FileNotFoundError(
                f"Launcher macOS não encontrado. "
                "Inicie o PJE-Calc Cidadão manualmente e tente novamente.\n"
                "Para instalar Java 8: brew install --cask temurin@8"
            )
    else:
        # Linux / Docker: usa iniciarPjeCalc.sh
        launcher = dir_path / "iniciarPjeCalc.sh"
        if not launcher.exists():
            raise FileNotFoundError(
                f"iniciarPjeCalc.sh não encontrado em {dir_path}. "
                "Verifique a configuração PJECALC_DIR ou crie o script shell."
            )
        subprocess.Popen(
            ["bash", str(launcher)],
            cwd=str(dir_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # 1) Aguarda porta TCP abrir
    inicio = time.time()
    while time.time() - inicio < timeout:
        if pjecalc_rodando():
            logger.info(f"PJE-Calc: porta TCP aberta ({_porta_local()}).")
            _log("PJE-Calc: porta TCP aberta. Aguardando deploy web…")
            break
        time.sleep(2)
    else:
        raise TimeoutError(
            f"PJE-Calc não ficou disponível em {timeout}s. "
            "Verifique se o Java está instalado corretamente."
        )

    # 2) Aguarda HTTP responder (Tomcat pode aceitar TCP antes de concluir deploy)
    _aguardar_http(timeout=180, log_cb=log_cb)


def _aguardar_http(timeout: int = 300, log_cb=None) -> None:
    """
    Aguarda o PJE-Calc responder com 200, 302 ou 404.
    404 é aceito: indica que o Tomcat está ativo mas o war ainda está sendo
    deployado. O Playwright consegue conectar assim que a página JSF responder.
    Emite progresso via log_cb a cada 15s.
    """
    url = _PJECALC_LOCAL_URL
    inicio = time.time()
    ultimo_log = -15  # força log no primeiro ciclo
    while time.time() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status in (200, 302, 404):
                    logger.info(f"PJE-Calc HTTP respondendo (status {resp.status}) — pronto.")
                    if log_cb:
                        log_cb(f"PJE-Calc pronto (HTTP {resp.status}).")
                    if resp.status == 404:
                        time.sleep(3)  # margem extra: 404 = war ainda deployando
                    return
        except Exception:
            pass
        elapsed = int(time.time() - inicio)
        if log_cb and elapsed - ultimo_log >= 15:
            log_cb(f"⏳ Aguardando PJE-Calc inicializar… ({elapsed}s/{timeout}s)")
            ultimo_log = elapsed
        time.sleep(3)
    raise TimeoutError(
        f"PJE-Calc: porta aberta mas HTTP não respondeu em {timeout}s. "
        "Verifique /api/logs/java para diagnóstico."
    )


# ── Utilitários de formatação ─────────────────────────────────────────────────

def _fmt_br(valor: float | str | None) -> str:
    """Formata número como moeda BR: 1234.56 → '1.234,56'."""
    if valor is None:
        return ""
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(valor)


def _parsear_numero_processo(numero: str | None) -> dict:
    """'0001686-52.2026.5.07.0003' → {numero, digito, ano, justica, regiao, vara}."""
    if not numero:
        return {}
    m = re.match(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})", numero.strip())
    if m:
        return {
            "numero": m.group(1),
            "digito": m.group(2),
            "ano": m.group(3),
            "justica": m.group(4),
            "regiao": m.group(5),
            "vara": m.group(6),
        }
    return {}


# ── Classe de automação Playwright ────────────────────────────────────────────

class PJECalcPlaywright:
    """
    Preenche o PJE-Calc Cidadão via Playwright (browser visível).
    Implementa as recomendações do Manual Técnico v2.0.
    """

    # URL base do PJE-Calc local — lida de PJECALC_LOCAL_URL (config/env).
    # Padrão: http://localhost:9257/pjecalc (bundled pjecalc-dist/).
    # Instalação padrão TRT: http://localhost:8080/pje-calc
    try:
        from config import PJECALC_LOCAL_URL as _LOCAL_URL
        PJECALC_BASE = _LOCAL_URL
    except ImportError:
        import os as _os
        PJECALC_BASE = _os.environ.get(
            "PJECALC_LOCAL_URL", "http://localhost:9257/pjecalc"
        )
    LOG_DIR = Path("data/logs")

    def __init__(self, log_cb: Callable[[str], None] | None = None):
        self._log_cb = log_cb or (lambda msg: None)
        self._pw = None
        self._browser = None
        self._page = None
        self._headless = False  # stored by iniciar_browser() para crash recovery
        # Capturados após criar um novo cálculo — usados para URL-based navigation
        self._calculo_url_base: str | None = None
        self._calculo_conversation_id: str | None = None

    # ── Ciclo de vida ──────────────────────────────────────────────────────────

    def iniciar_browser(self, headless: bool = False) -> None:
        import asyncio
        import os, sys
        # Em Linux sem display real (Railway/Docker), forçar headless
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            headless = True
        self._headless = headless  # salva para crash recovery no retry
        # sync_playwright().__enter__() verifica asyncio.get_event_loop().is_running().
        # Em threads filhas, asyncio pode retornar o loop do uvicorn (que está rodando),
        # causando RuntimeError. Garantir loop próprio e não-rodando para este thread.
        try:
            _loop = asyncio.get_event_loop()
            if _loop.is_running():
                asyncio.set_event_loop(asyncio.new_event_loop())
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().__enter__()
        # --no-sandbox e --disable-dev-shm-usage: obrigatórios em Docker/Railway
        # --disable-gpu / --disable-software-rasterizer: headless sem GPU dedicada
        base_args = ["--no-sandbox", "--disable-dev-shm-usage"]
        if headless:
            base_args += ["--disable-gpu", "--disable-software-rasterizer"]
        else:
            base_args += ["--start-maximized"]
        self._browser = self._pw.chromium.launch(
            headless=headless,
            slow_mo=0 if headless else 150,
            args=base_args,
        )
        # viewport explícito: necessário para offsetParent e is_visible() funcionarem
        # em modo headless — sem viewport, todos os elementos reportam offsetParent=null
        ctx = self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        self._page = ctx.new_page()
        self._page.set_default_timeout(30000)
        # Interceptar erros HTTP e erros JS (diagnóstico em produção)
        # Excluir arquivos estáticos/fontes que geram 404 inofensivos (tahoma.ttf, etc.)
        _STATIC_EXTS = ('.ttf', '.woff', '.woff2', '.otf', '.eot',
                        '.ico', '.png', '.gif', '.jpg', '.svg')
        self._page.on(
            "response",
            lambda r: self._log(f"  ⚠ HTTP {r.status}: {r.url}")
            if r.status >= 400 and "9257" in r.url
                and not r.url.split('?')[0].lower().endswith(_STATIC_EXTS)
            else None,
        )
        self._page.on(
            "console",
            lambda m: self._log(f"  [JS] {m.text}")
            if m.type == "error"
            else None,
        )

    def fechar(self) -> None:
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.__exit__(None, None, None)
        except Exception:
            pass

    # ── Logging ────────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        logger.info(msg)
        self._log_cb(msg)

    # ── Monitor de AJAX JSF ────────────────────────────────────────────────────

    def _instalar_monitor_ajax(self) -> None:
        """Injeta listener no sistema de AJAX do JSF para esperas precisas."""
        self._page.evaluate("""() => {
            window.__ajaxCompleto = true;
            if (typeof jsf !== 'undefined' && jsf.ajax) {
                jsf.ajax.addOnEvent(function(data) {
                    if (data.status === 'begin') window.__ajaxCompleto = false;
                    if (data.status === 'success' || data.status === 'complete')
                        window.__ajaxCompleto = true;
                });
            }
        }""")

    def _aguardar_ajax(self, timeout: int = 15000) -> None:
        """Aguarda conclusão do AJAX JSF; fallback para networkidle."""
        try:
            self._page.wait_for_function(
                "() => window.__ajaxCompleto === true",
                timeout=timeout,
            )
        except Exception:
            try:
                self._page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                self._page.wait_for_timeout(2000)

    # ── Descoberta dinâmica de campos ─────────────────────────────────────────

    def mapear_campos(self, nome_pagina: str = "pagina") -> list[dict]:
        """
        Cataloga todos os campos input/select/textarea da página atual.
        Salva em data/logs/campos_{nome_pagina}.json para diagnóstico.
        """
        campos = self._page.evaluate("""() => {
            const campos = [];
            document.querySelectorAll('input, select, textarea').forEach(el => {
                const lbl = document.querySelector(`label[for='${el.id}']`);
                // getBoundingClientRect funciona em headless (offsetParent não)
                const r = el.getBoundingClientRect();
                campos.push({
                    id: el.id,
                    name: el.name || '',
                    type: el.type || el.tagName.toLowerCase(),
                    tag: el.tagName.toLowerCase(),
                    label: lbl ? lbl.textContent.trim() : '',
                    visible: r.width > 0 && r.height > 0,
                    sufixo: el.id.includes(':') ? el.id.split(':').pop() : el.id
                });
            });
            return campos;
        }""")
        # Salvar para diagnóstico
        try:
            self.LOG_DIR.mkdir(parents=True, exist_ok=True)
            caminho = self.LOG_DIR / f"campos_{nome_pagina}.json"
            caminho.write_text(
                json.dumps(campos, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._log(f"  📋 Mapeamento de campos salvo: {caminho}")
        except Exception:
            pass
        return campos

    # ── Localização de elementos — hierarquia de 4 níveis ────────────────────

    def _localizar(
        self,
        field_id: str,
        label: str | None = None,
        tipo: str = "input",
        timeout: int = 5000,
    ):
        """
        Localiza elemento JSF seguindo hierarquia do manual:
        1. get_by_label (mais estável)
        2. [id$='sufixo'] (sufixo do ID)
        3. XPath contains(@id) (sem problema com dois-pontos)
        4. ID escapado (último recurso)
        Retorna Locator visível ou None.
        """
        # Nível 1: por label
        if label:
            loc = self._page.get_by_label(label, exact=False)
            if loc.count() > 0:
                return loc.first

        # Nível 2: sufixo de ID, SEMPRE com prefixo de tag para evitar match em
        # elementos errados (ex: <table class="rich-calendar-exterior"> ou <li>
        # ou <input type="hidden"> — que NÃO são interagíveis).
        sufixo = field_id.split(":")[-1]  # extrai sufixo se vier com prefixo
        seletores_base = [
            f"[id*='{sufixo}InputDate']",  # RichFaces 3.x Calendar: formulario:dataXxxInputDate
            f"[id$='{sufixo}_input']",      # RichFaces 4.x: <input id="..._input">
            f"[id$=':{sufixo}']",
            f"[id$='{sufixo}']",
        ]
        if tipo == "select":
            seletores = [f"select{s}" for s in seletores_base]
        elif tipo == "checkbox":
            seletores = [f"input[type='checkbox']{s}" for s in seletores_base]
        elif tipo == "input":
            # :not([type='hidden']) evita match em:
            #   1. <table id="...:dataAdmissao" class="rich-calendar-exterior"> (popup)
            #   2. <input id="...:dataAdmissao" type="hidden"> (campo oculto de valor)
            # O campo visível do RichFaces Calendar tem id "...InputDate" (seletor 1 acima)
            seletores = [f"input:not([type='hidden']){s}" for s in seletores_base]
        else:
            seletores = seletores_base

        for sel in seletores:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except Exception:
                continue

        # Nível 2.5: name attribute — JSF às vezes usa name= mais estável que id=
        if tipo == "select":
            seletores_name = [f"select[name$='{sufixo}']", f"select[name*='{sufixo}']"]
        elif tipo == "checkbox":
            seletores_name = [
                f"input[type='checkbox'][name$='{sufixo}']",
                f"input[type='checkbox'][name*='{sufixo}']",
            ]
        else:
            seletores_name = [f"input[name$='{sufixo}']", f"input[name*='{sufixo}']"]
        for sel in seletores_name:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except Exception:
                continue

        # Nível 3: XPath contains(@id)
        # Para "input": @type='text' exclui hidden inputs (ex: formulario:dataDemissao hidden)
        xpath_map = {
            "input":    f"//input[@type='text' and contains(@id, '{sufixo}')]",
            "select":   f"//select[contains(@id, '{sufixo}')]",
            "checkbox": f"//input[@type='checkbox' and contains(@id, '{sufixo}')]",
        }
        xpath = xpath_map.get(tipo, f"//*[contains(@id, '{sufixo}')]")
        try:
            loc = self._page.locator(xpath)
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except Exception:
            pass

        # Nível 4: ID completo com dois-pontos escapados
        escaped = field_id.replace(":", "\\:")
        try:
            loc = self._page.locator(f"#{escaped}")
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except Exception:
            pass

        return None

    # ── Primitivas DOM ─────────────────────────────────────────────────────────

    def _preencher(
        self,
        field_id: str,
        valor: str,
        obrigatorio: bool = True,
        label: str | None = None,
    ) -> bool:
        """Preenche campo de input JSF com fallback entre 4 estratégias."""
        if not valor:
            return False
        loc = self._localizar(field_id, label, tipo="input")
        if not loc:
            if obrigatorio:
                self._log(f"  ⚠ {field_id}: campo não encontrado — preencha manualmente.")
            return False
        try:
            loc.wait_for(state="visible", timeout=8000)
            loc.click()
            loc.fill("")
            loc.fill(valor)
            loc.dispatch_event("input")
            loc.dispatch_event("change")
            # Sem blur: JSF/RichFaces pode usar blur para AJAX postback → risco de HTTP 500
            self._log(f"  ✓ {field_id}: {valor}")
            return True
        except Exception as e:
            if obrigatorio:
                self._log(f"  ⚠ {field_id}: erro ao preencher — {e}")
            return False

    def _preencher_data(
        self,
        field_id: str,
        data: str,
        obrigatorio: bool = True,
        label: str | None = None,
    ) -> bool:
        """
        Preenche campo de data usando focus() + press_sequentially + Tab.
        Usa focus() em vez de click() para evitar abrir o popup do RichFaces Calendar.
        Fallback via JS direto se o método principal falhar.
        """
        if not data:
            return False
        loc = self._localizar(field_id, label, tipo="input")
        if not loc:
            if obrigatorio:
                self._log(f"  ⚠ data {field_id}: campo não encontrado — preencha manualmente.")
            return False
        try:
            loc.wait_for(state="visible", timeout=8000)
            # focus() em vez de click() para não abrir o calendar popup (RichFaces)
            loc.focus()
            # Ctrl+A + Delete — limpa campos mascarados (RichFaces) que ignoram el.value=''
            self._page.keyboard.press("Control+a")
            self._page.keyboard.press("Delete")
            # Digita apenas os dígitos — campos com máscara DD/MM/AAAA auto-inserem as barras
            digits_only = data.replace("/", "").replace("-", "")
            loc.press_sequentially(digits_only, delay=60)
            loc.dispatch_event("input")
            loc.dispatch_event("change")
            # Escape fecha popup do RichFaces Calendar sem disparar blur AJAX
            # (Tab dispara blur → AJAX postback → HTTP 500 → Salvar some do DOM)
            loc.press("Escape")
            self._log(f"  ✓ data {field_id}: {data}")
            return True
        except Exception as e:
            # Fallback A: setar valor completo com barras (campos sem máscara)
            try:
                loc.focus()
                self._page.keyboard.press("Control+a")
                self._page.keyboard.press("Delete")
                loc.press_sequentially(data, delay=60)
                loc.press("Escape")
                self._log(f"  ✓ data {field_id} (fallback A - com barras): {data}")
                return True
            except Exception:
                pass
            # Fallback B: JS direto (ignora máscara, sem blur para não disparar AJAX)
            try:
                loc.evaluate(
                    f"el => {{ el.value = '{data}'; "
                    "el.dispatchEvent(new Event('input',{bubbles:true})); "
                    "el.dispatchEvent(new Event('change',{bubbles:true})); }}"
                )
                self._log(f"  ✓ data {field_id} (JS fallback): {data}")
                return True
            except Exception as e2:
                self._log(f"  ⚠ data {field_id}: erro — {e} | fallback: {e2}")
                return False

    def _selecionar(
        self,
        field_id: str,
        valor: str,
        label: str | None = None,
        obrigatorio: bool = True,
    ) -> bool:
        """Seleciona opção em <select> JSF por label (texto visível) ou value."""
        if not valor:
            return False
        loc = self._localizar(field_id, label, tipo="select")
        if not loc:
            if obrigatorio:
                self._log(f"  ⚠ select {field_id}: não encontrado — selecione manualmente.")
            return False
        try:
            loc.wait_for(state="visible", timeout=8000)
            # Tenta por label primeiro (mais estável), depois por value
            try:
                loc.select_option(label=valor)
            except Exception:
                loc.select_option(value=valor)
            loc.dispatch_event("change")
            self._aguardar_ajax()
            self._log(f"  ✓ select {field_id}: {valor}")
            return True
        except Exception as e:
            self._log(f"  ⚠ select {field_id}: erro — {e}")
            return False

    def _extrair_opcoes_select(self, field_suffix: str) -> list[dict]:
        """
        Extrai todas as opções de um <select> cujo ID termina com field_suffix.
        Retorna lista de {value, text} para fuzzy matching.
        """
        try:
            opcoes = self._page.evaluate(f"""(suffix) => {{
                const sel = [...document.querySelectorAll('select')].find(
                    s => s.id && s.id.endsWith(suffix)
                );
                if (!sel) return [];
                return [...sel.options].map(o => ({{value: o.value, text: o.text.trim()}}));
            }}""", field_suffix)
            return opcoes or []
        except Exception:
            return []

    def _match_fuzzy(self, valor: str, opcoes: list[dict]) -> str | None:
        """
        Normaliza e compara valor com as opções disponíveis.
        Retorna o value da opção mais próxima, ou None se nenhuma encontrada.
        """
        import unicodedata

        def _norm(s: str) -> str:
            s = s.lower().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if not unicodedata.combining(c))
            return s

        val_norm = _norm(valor)
        # Exact match first (text)
        for op in opcoes:
            if _norm(op.get("text", "")) == val_norm:
                return op["value"]
        # Exact match on value
        for op in opcoes:
            if _norm(op.get("value", "")) == val_norm:
                return op["value"]
        # Substring match
        for op in opcoes:
            txt = _norm(op.get("text", ""))
            if val_norm in txt or txt in val_norm:
                return op["value"]
        return None

    def _marcar_radio(self, field_id: str, valor: str) -> bool:
        """Clica em radio button JSF."""
        seletores = [
            f"input[type='radio'][value='{valor}'][id$='{field_id}']",
            f"table[id$='{field_id}'] input[value='{valor}']",
            f"input[type='radio'][name$='{field_id}'][value='{valor}']",
            f"input[type='radio'][name*='{field_id}'][value='{valor}']",
            f"//input[@type='radio' and @value='{valor}' and contains(@id, '{field_id}')]",
            f"//input[@type='radio' and @value='{valor}' and contains(@name, '{field_id}')]",
        ]
        for sel in seletores:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    loc.first.click()
                    self._log(f"  ✓ radio {field_id}: {valor}")
                    return True
            except Exception:
                continue
        self._log(f"  ⚠ radio {field_id}={valor}: não encontrado")
        return False

    def _marcar_checkbox(
        self,
        field_id: str,
        marcar: bool = True,
        label: str | None = None,
    ) -> bool:
        """Marca ou desmarca checkbox JSF."""
        loc = self._localizar(field_id, label, tipo="checkbox")
        if not loc:
            return False
        try:
            loc.wait_for(state="visible", timeout=5000)
            if loc.is_checked() != marcar:
                loc.click()
                self._aguardar_ajax()
            return True
        except Exception:
            return False

    def _clicar_menu_lateral(self, texto: str, obrigatorio: bool = True) -> bool:
        """
        Clica em link do menu lateral via JavaScript (invulnerável a visibilidade).
        Funciona mesmo que o menu esteja colapsado — dispara o onclick do JSF/A4J
        diretamente sem depender de Playwright ver o elemento.
        Retorna True se clicou com sucesso, False se não encontrou.
        """
        # Tentativa 1: seletor de ID específico do sidebar (robusto, sem ambiguidade)
        _MENU_ID_MAP = {
            "Histórico Salarial": "a[id*='menuHistoricoSalarial']",
            "Verbas":             "a[id*='menuVerbas']",
            "FGTS":               "a[id*='menuFGTS']",
            "Honorários":         "a[id*='menuHonorarios']",
            "Liquidar":           "a[id*='menuLiquidar']",
            "Faltas":             "a[id*='menuFaltas']",
            "Férias":             "a[id*='menuFerias']",
            "Dados do Cálculo":   "a[id*='menuCalculo']",
            "Novo":               "a[id*='menuNovo']",
            "Operações":          "a[id*='menuOperacoes']",
            "Imprimir":           "a[id*='menuImprimir']",
            "Contribuição Social": "a[id*='menuContribuicaoSocial']",
            "Contribuicao Social": "a[id*='menuContribuicaoSocial']",
            "Imposto de Renda":   "a[id*='menuImpostoRenda']",
            "Multas":             "a[id*='menuMultas']",
            "Cartão de Ponto":    "a[id*='menuCartaoPonto']",
            "Salário Família":    "a[id*='menuSalarioFamilia']",
            "Seguro Desemprego":  "a[id*='menuSeguroDesemprego']",
            "Pensão Alimentícia": "a[id*='menuPensaoAlimenticia']",
            "Previdência Privada": "a[id*='menuPrevidenciaPrivada']",
        }
        sel_id = _MENU_ID_MAP.get(texto)
        if sel_id:
            loc = self._page.locator(sel_id)
            if loc.count() > 0:
                try:
                    loc.first.click(force=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    return True
                except Exception:
                    pass  # fallback para busca por texto abaixo
        self._page.wait_for_timeout(400)

        # Tentativa 2: navegação por URL com conversationId do cálculo ativo
        # (mais confiável que busca textual quando IDs do menu são dinâmicos)
        _URL_SECTION_MAP = {
            "Histórico Salarial": "historicoSalarial.jsf",
            "Verbas":             "verba.jsf",
            "FGTS":               "fgts.jsf",
            "Honorários":         "honorarios.jsf",
            "Liquidar":           "liquidar.jsf",
            "Faltas":             "falta.jsf",
            "Férias":             "ferias.jsf",
            "Contribuição Social": "contribuicaoSocial.jsf",
            "Contribuicao Social": "contribuicaoSocial.jsf",
            "Imposto de Renda":   "impostoRenda.jsf",
            "Multas":             "multas.jsf",
            "Dados do Cálculo":   "calculo.jsf",
            "Imprimir":           "imprimir.jsf",
        }
        if self._calculo_url_base and self._calculo_conversation_id:
            jsf_page = _URL_SECTION_MAP.get(texto)
            if jsf_page:
                try:
                    _url = (
                        f"{self._calculo_url_base}{jsf_page}"
                        f"?conversationId={self._calculo_conversation_id}"
                    )
                    self._log(f"  → URL nav: {jsf_page}?conversationId={self._calculo_conversation_id}")
                    self._page.goto(_url, wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    return True
                except Exception as _e:
                    self._log(f"  ⚠ URL nav falhou para '{texto}': {_e}")

        # Tentativa 3: JS click com escopo no container do menu lateral
        # Ancora-se em "Histórico Salarial" (exclusivo do menu de cálculo) para evitar
        # clicar em links homônimos do menu de referência (Tabelas).
        clicou = self._page.evaluate(
            """(texto) => {
                const allLinks = [...document.querySelectorAll('a')];
                // Tenta encontrar o link no mesmo container do menu de cálculo
                const anchors = ['Histórico Salarial', 'FGTS', 'Faltas'];
                const anchor = anchors.find(t => t !== texto);
                if (anchor) {
                    const anchorEl = allLinks.find(
                        a => a.textContent.replace(/\\s+/g, ' ').trim().includes(anchor)
                    );
                    if (anchorEl) {
                        let parent = anchorEl.parentElement;
                        for (let i = 0; i < 8 && parent && parent.tagName !== 'BODY'; i++) {
                            const found = [...parent.querySelectorAll('a')].find(
                                a => a !== anchorEl &&
                                     a.textContent.replace(/\\s+/g, ' ').trim().includes(texto)
                            );
                            if (found) { found.click(); return true; }
                            parent = parent.parentElement;
                        }
                    }
                }
                // Fallback: primeiro link com texto exato
                const el = allLinks.find(
                    a => a.textContent.replace(/\\s+/g, ' ').trim() === texto
                );
                if (el) { el.click(); return true; }
                return false;
            }""",
            texto,
        )
        if clicou:
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            return True
        # Fallback: Playwright (visível ou não)
        loc = self._page.locator(f"a:has-text('{texto}')")
        if loc.count() == 0:
            loc = self._page.get_by_role("link", name=texto)
        if loc.count() == 0:
            if obrigatorio:
                self._log(f"  ⚠ Menu '{texto}': link não encontrado.")
                try:
                    todos = self._page.evaluate("""() => {
                        return [...document.querySelectorAll('a')]
                            .map(a => a.textContent.replace(/\\s+/g, ' ').trim())
                            .filter(t => t.length > 1 && t.length < 80);
                    }""")
                    self._log(f"  ℹ Links disponíveis: {list(dict.fromkeys(todos))[:30]}")
                except Exception:
                    pass
            return False
        try:
            loc.first.click(force=True)
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            return True
        except Exception as e:
            if obrigatorio:
                self._log(f"  ⚠ Menu '{texto}': erro ao clicar — {e}")
            return False

    def _clicar_botao_id(self, id_suffix: str) -> bool:
        """Clica em botão/input pelo sufixo de ID (seletor específico, menos ambíguo que texto)."""
        loc = self._page.locator(f"input[id*='{id_suffix}'], button[id*='{id_suffix}']")
        if loc.count() > 0:
            try:
                loc.first.click()
                return True
            except Exception:
                return False
        return False

    def _verificar_secao_ativa(self, secao_esperada: str) -> bool:
        """Verifica se a seção atual (URL ou heading) corresponde à seção esperada."""
        try:
            url = self._page.url
            heading = self._page.evaluate(
                "() => (document.querySelector('h1,h2,h3,legend,.tituloPagina')||{}).textContent?.trim()||''"
            )
            self._log(f"  ℹ Seção: '{heading[:60]}' | url: ...{url[-50:]}")
            return (secao_esperada.lower() in heading.lower()
                    or secao_esperada.lower() in url.lower())
        except Exception:
            return False

    def _clicar_aba(self, aba_id: str) -> None:
        """Clica em aba RichFaces."""
        seletores = [
            f"[id$='{aba_id}_lbl']",
            f"[id$='{aba_id}_header']",
            f"[id$='{aba_id}'] span",
        ]
        for sel in seletores:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    loc.first.click()
                    self._aguardar_ajax()
                    return
            except Exception:
                continue

    def _clicar_botao(self, texto: str, obrigatorio: bool = True) -> bool:
        """Clica em botão pelo texto visível."""
        loc = self._page.locator(
            f"input[type='submit'][value='{texto}'], "
            f"input[type='button'][value='{texto}'], "
            f"button:has-text('{texto}'), "
            f"a:has-text('{texto}')"
        )
        if loc.count() > 0:
            loc.first.click()
            self._aguardar_ajax()
            return True
        if obrigatorio:
            self._log(f"  ⚠ Botão '{texto}' não encontrado.")
        return False

    def _clicar_salvar(self) -> bool:
        """Clica no botão Salvar da seção atual. Retorna True se salvou, False se não encontrou."""
        seletores = [
            "[id$='salvar']",
            "input[value='Salvar']",
            "button:has-text('Salvar')",
        ]
        for sel in seletores:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    self._log(f"  → Salvar: clicando via '{sel}'")
                    loc.first.click(force=True)
                    self._aguardar_ajax()
                    self._log(f"  ✓ Salvar: concluído (URL: {self._page.url})")
                    return True
            except Exception:
                continue
        # JS fallback: clica via DOM (seletores específicos — sem querySelector('button') genérico)
        try:
            clicou = self._page.evaluate("""() => {
                const candidates = [
                    document.querySelector('[id$=":salvar"]'),
                    document.querySelector('[id*="btnSalvar"]'),
                    document.querySelector('input[value="Salvar"]'),
                    document.querySelector('input[value*="Salvar"]'),
                    ...[...document.querySelectorAll('button')]
                        .filter(b => (b.textContent||'').trim().toLowerCase() === 'salvar'),
                ];
                const btn = candidates.find(b => b != null);
                if (btn) { btn.click(); return btn.id || btn.value || 'ok'; }
                return null;
            }""")
            if clicou:
                self._aguardar_ajax()
                self._log(f"  ✓ Salvar: concluído via JS fallback '{clicou}' (URL: {self._page.url})")
                return True
        except Exception:
            pass
        self._log("  ⚠ Botão Salvar não encontrado — clique manualmente.")
        return False

    def _clicar_novo(self) -> None:
        """Clica no botão Novo da seção atual — prioriza dentro de #formulario."""
        url_pre = self._page.url

        # Método 1: seletores CSS por ID (não ambíguos — sem button:has-text que pega top-nav)
        for sel in ["[id$='novo']", "[id$='novoBt']", "[id$='novoBtn']",
                    "input[value='Novo']"]:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    self._log(f"  → Novo: clicando via '{sel}'")
                    loc.first.click(); self._aguardar_ajax()
                    self._page.wait_for_timeout(800)
                    self._log(f"  → URL pós-Novo: {self._page.url} (mudou: {self._page.url != url_pre})")
                    return
            except Exception:
                continue

        # Método 2: JS — busca PRIMEIRO dentro de #formulario (seção atual),
        # depois fallback global. Evita clicar no "Novo" do top-nav.
        clicou = self._page.evaluate("""() => {
            const form = document.getElementById('formulario');
            const containers = form ? [form, document] : [document];
            for (const container of containers) {
                const els = [...container.querySelectorAll(
                    'a, input[type="submit"], input[type="button"], button')];
                for (const el of els) {
                    const txt = (el.textContent || el.value || el.title || '')
                        .replace(/[\\s\\u00a0]+/g,' ').trim();
                    if (txt === 'Novo' || txt === 'Nova') {
                        el.click(); return el.id || '(sem id)';
                    }
                }
            }
            return null;
        }""")
        if clicou:
            self._log(f"  → Novo: clicado via JS (elem: {clicou})")
            self._aguardar_ajax(); self._page.wait_for_timeout(800)
            self._log(f"  → URL pós-Novo: {self._page.url} (mudou: {self._page.url != url_pre})")
            return

        # Diagnóstico
        self._log("  ⚠ Botão Novo não encontrado — elementos clicáveis na página:")
        try:
            items = self._page.evaluate("""() =>
                [...document.querySelectorAll('a, input[type="submit"], button')]
                .map(el => el.id + ' | ' + (el.textContent||el.value||'').trim())
                .filter(s => s.length > 3 && s.length < 80)
            """)
            self._log(f"  {items[:25]}")
        except Exception:
            pass

    def _aguardar_usuario(self, mensagem: str) -> None:
        """Injeta overlay amarelo para o usuário agir e clicar em Continuar."""
        self._log(f"AGUARDANDO_USUARIO: {mensagem}")
        js = """
        (msg) => new Promise(resolve => {
            const div = document.createElement('div');
            div.id = 'pjecalc-agente-overlay';
            div.style.cssText = 'position:fixed;top:0;left:0;width:100%;z-index:999999;'+
                'background:#fff3cd;border-bottom:3px solid #ffc107;padding:16px 24px;'+
                'font-family:Arial;font-size:14px;display:flex;align-items:center;'+
                'gap:16px;box-shadow:0 4px 8px rgba(0,0,0,.2);';
            div.innerHTML = '<span style="font-size:22px">\u26a0\ufe0f</span>' +
                '<span style="flex:1"><strong>Ação necessária:</strong> ' + msg + '</span>' +
                '<button id="pjecalc-continuar" style="background:#1a3a6b;color:#fff;' +
                'border:none;padding:8px 20px;border-radius:4px;cursor:pointer;font-size:14px;">'+
                'Continuar</button>';
            document.body.prepend(div);
            document.getElementById('pjecalc-continuar').onclick = () => {
                div.remove(); resolve();
            };
        })
        """
        try:
            self._page.evaluate(js, mensagem)
            self._page.wait_for_selector("#pjecalc-agente-overlay", state="detached", timeout=600000)
        except Exception:
            pass

    def _verificar_e_fazer_login(self) -> None:
        """Verifica se está logado; se não, tenta credenciais via env vars ou padrão.
        NUNCA bloqueia para aguardar interação manual — lança RuntimeError em falha.
        """
        url = self._page.url
        if "logon" not in url.lower():
            return

        self._log("Página de login detectada — tentando credenciais automáticas…")
        # Prioridade: env vars PJECALC_USER/PJECALC_PASS → credenciais padrão conhecidas
        credenciais_env = []
        if os.environ.get("PJECALC_USER") and os.environ.get("PJECALC_PASS"):
            credenciais_env = [(os.environ["PJECALC_USER"], os.environ["PJECALC_PASS"])]
        for usuario, senha in credenciais_env + [
            ("admin", "pjeadmin"),
            ("admin", "admin"),
            ("pjecalc", "pjecalc"),
            ("advogado", "advogado"),
        ]:
            try:
                sel_user = "input[name*='usuario'], input[id*='usuario'], input[type='text'][name*='j_'], input[name*='j_username']"
                self._page.fill(sel_user, usuario, timeout=2000)
                self._page.fill("input[type='password']", senha, timeout=2000)
                self._page.click("input[type='submit'], button[type='submit']", timeout=2000)
                self._page.wait_for_timeout(2000)
                if "logon" not in self._page.url.lower():
                    self._log(f"Login automático com '{usuario}' — OK.")
                    return
            except Exception:
                continue

        raise RuntimeError(
            "Login automático falhou: nenhuma das credenciais padrão funcionou. "
            "Configure as variáveis de ambiente PJECALC_USER e PJECALC_PASS com as "
            "credenciais corretas do PJE-Calc Cidadão antes de iniciar a automação."
        )

    # ── Verificações de saúde (Tomcat + página) ────────────────────────────────

    def _verificar_tomcat(self, timeout: int = 120) -> bool:
        """Aguarda o Tomcat responder antes de prosseguir. Loga progresso a cada 15s."""
        url = self.PJECALC_BASE
        inicio = time.time()
        ultimo_log = -15
        while time.time() - inicio < timeout:
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    if r.status in (200, 302, 404):
                        return True
            except Exception:
                pass
            elapsed = int(time.time() - inicio)
            if elapsed > 5 and elapsed - ultimo_log >= 15:
                self._log(f"  ⏳ Aguardando Tomcat... ({elapsed}s/{timeout}s)")
                ultimo_log = elapsed
            time.sleep(5)
        self._log("  ⚠ Tomcat não respondeu — continuando mesmo assim.")
        return False

    def _verificar_pagina_pjecalc(self) -> bool:
        """Garante que a página atual é válida (no PJE-Calc, sem erro 500, com conteúdo).
        Renavega para home se necessário. Retorna True se OK."""
        url = self._page.url
        if "9257" not in url:
            self._log("  ⚠ Página fora do PJE-Calc — renavegando para home…")
            try:
                self._page.goto(
                    f"{self.PJECALC_BASE}/pages/principal.jsf",
                    wait_until="domcontentloaded", timeout=30000,
                )
                self._page.wait_for_timeout(2000)
            except Exception:
                pass
            return False
        try:
            body = self._page.locator("body").text_content(timeout=5000) or ""
            if len(body.strip()) < 50:
                self._log("  ⚠ Página com pouco conteúdo — recarregando…")
                self._page.wait_for_timeout(2000)
                self._page.reload()
                self._page.wait_for_load_state("networkidle", timeout=15000)
                return False
            if "Erro interno do servidor" in body or ("500" in body and "Erro" in body):
                self._log("  ⚠ Erro 500 detectado — voltando para home…")
                home = self._page.locator(
                    "a:has-text('Tela Inicial'), a:has-text('Página Inicial')"
                )
                if home.count() > 0:
                    home.first.click()
                    self._page.wait_for_timeout(2000)
                return False
        except Exception:
            pass
        return True

    # ── Navegação principal ────────────────────────────────────────────────────

    def _capturar_base_calculo(self) -> None:
        """Captura a URL base e conversationId do cálculo ativo para navegação por URL."""
        import re as _re
        try:
            url = self._page.url
            m_base = _re.match(r'(https?://.+/)[^/?]+\.jsf', url)
            m_conv = _re.search(r'conversationId=(\d+)', url)
            if m_base and m_conv:
                self._calculo_url_base = m_base.group(1)
                self._calculo_conversation_id = m_conv.group(1)
                self._log(
                    f"  ℹ URL base: {self._calculo_url_base} | conversationId={self._calculo_conversation_id}"
                )
        except Exception:
            pass

    def _ir_para_novo_calculo(self) -> None:
        """Navega para o formulário de Novo Cálculo via menu 'Novo'.

        Usa o fluxo 'Novo' (primeira liquidação de sentença), NÃO 'Cálculo Externo'
        (que serve apenas para atualizar cálculos existentes).
        Navegação via clique no menu — URL direta causa ViewState inválido no JSF.
        """
        self._log("Navegando para Novo Cálculo via menu…")

        self._clicar_menu_lateral("Novo")
        # Aguardar a navegação JSF estabilizar antes de interagir com a página.
        # wait_for_timeout fixo é insuficiente; networkidle garante que todos os
        # requests AJAX do JSF terminaram antes de evaluate() ser chamado.
        try:
            self._page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            self._page.wait_for_timeout(2500)
        self._aguardar_ajax()

        # Recuperação: se página de erro, volta para home e tenta novamente
        try:
            body = self._page.locator("body").text_content(timeout=3000) or ""
            if "Erro" in body and ("Servidor" in body or "inesperado" in body):
                self._log("  Erro detectado após menu — voltando para Tela Inicial…")
                link = self._page.locator("a:has-text('Tela Inicial'), a:has-text('Página Inicial')")
                if link.count() > 0:
                    link.first.click()
                    self._page.wait_for_timeout(1500)
                self._clicar_menu_lateral("Novo")
                try:
                    self._page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    self._page.wait_for_timeout(2000)
        except Exception:
            pass

        self._capturar_base_calculo()
        self._log("  ✓ Formulário de Novo Cálculo aberto.")

    # ── Fase 1: Dados do Processo + Parâmetros ─────────────────────────────────

    @retry(max_tentativas=3)
    def fase_dados_processo(self, dados: dict) -> None:
        import datetime
        self._log("Fase 1 — Dados do processo…")
        # Garantir que a página terminou de navegar antes de chamar evaluate().
        # "Execution context was destroyed" ocorre quando a página ainda está
        # em navegação JSF e evaluate() é chamado prematuramente.
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        self._aguardar_ajax()
        self.mapear_campos("fase1_dados_processo")

        proc = dados.get("processo", {})
        cont = dados.get("contrato", {})
        presc = dados.get("prescricao", {})
        ap = dados.get("aviso_previo", {})

        # ── Campos do cabeçalho (Tipo e Data de Criação) ──
        self._preencher("tipo", "Trabalhista", False)
        hoje = datetime.date.today().strftime("%d/%m/%Y")
        # Tentar IDs em ordem — para no primeiro encontrado (evita duplo preenchimento)
        _campos_data_cabecalho = [
            "dataDeCriacao", "dataCriacao", "dataDeAbertura", "dataAbertura", "dataCalculo"
        ]
        _preencheu_data_cabecalho = False
        for _fid in _campos_data_cabecalho:
            if self._preencher_data(_fid, hoje, obrigatorio=False):
                _preencheu_data_cabecalho = True
                break
        # JS fallback: encontrar qualquer input de data no cabeçalho
        if not _preencheu_data_cabecalho:
            try:
                self._page.evaluate(
                    """(data) => {
                        const inputs = document.querySelectorAll(
                            'input[id*="dataDe"], input[id*="dataCria"], input[id*="dataCalc"]'
                        );
                        if (inputs.length > 0) {
                            inputs[0].value = data;
                            inputs[0].dispatchEvent(new Event('change',{bubbles:true}));
                        }
                    }""",
                    hoje,
                )
            except Exception:
                pass

        # ── Aba Dados do Processo ──
        self._clicar_aba("tabDadosProcesso")
        self._page.wait_for_timeout(400)

        # Número do processo (campos separados na interface)
        num = _parsear_numero_processo(proc.get("numero"))
        if num:
            self._preencher("numero", num.get("numero", ""), False)
            self._preencher("digito", num.get("digito", ""), False)
            self._preencher("ano", num.get("ano", ""), False)
            self._preencher("justica", num.get("justica", ""), False)
            self._preencher("regiao", num.get("regiao", ""), False)
            self._preencher("vara", num.get("vara", ""), False)

        # Valor da causa e data de autuação
        if proc.get("valor_causa"):
            self._preencher("valorDaCausa", _fmt_br(proc["valor_causa"]), False)
            self._preencher("valorCausa", _fmt_br(proc["valor_causa"]), False)
        if proc.get("autuado_em"):
            self._preencher_data("autuadoEm", proc["autuado_em"], False)
            self._preencher_data("dataAutuacao", proc["autuado_em"], False)

        # Partes
        if proc.get("reclamante"):
            self._preencher("reclamanteNome", proc["reclamante"], False)
            self._preencher("nomeReclamante", proc["reclamante"], False)
        if proc.get("reclamado"):
            self._preencher("reclamadoNome", proc["reclamado"], False)
            self._preencher("nomeReclamado", proc["reclamado"], False)

        if proc.get("cpf_reclamante"):
            self._marcar_radio("documentoFiscalReclamante", "CPF")
            self._preencher("reclamanteNumeroDocumentoFiscal", proc["cpf_reclamante"], False)
            self._preencher("cpfReclamante", proc["cpf_reclamante"], False)
        if proc.get("cnpj_reclamado"):
            self._marcar_radio("tipoDocumentoFiscalReclamado", "CNPJ")
            self._preencher("reclamadoNumeroDocumentoFiscal", proc["cnpj_reclamado"], False)
            self._preencher("cnpjReclamado", proc["cnpj_reclamado"], False)

        if proc.get("advogado_reclamante"):
            self._preencher("nomeAdvogadoReclamante", proc["advogado_reclamante"], False)
        if proc.get("oab_reclamante"):
            self._preencher("numeroOABAdvogadoReclamante", proc["oab_reclamante"], False)

        # ── Aba Parâmetros do Cálculo ──
        self._log("  → Aba Parâmetros do Cálculo…")
        self._clicar_aba("tabParametrosCalculo")
        self._page.wait_for_timeout(600)
        self.mapear_campos("fase1_parametros")

        # Dados do contrato
        if cont.get("admissao"):
            self._preencher_data("dataAdmissao", cont["admissao"], False)
            self._preencher_data("dtAdmissao", cont["admissao"], False)
        if cont.get("demissao"):
            self._preencher_data("dataDemissao", cont["demissao"], False)
            self._preencher_data("dtDemissao", cont["demissao"], False)
        if cont.get("ajuizamento"):
            self._preencher_data("dataAjuizamento", cont["ajuizamento"], False)
            self._preencher_data("dtAjuizamento", cont["ajuizamento"], False)

        rescisao_map = {
            "sem_justa_causa": "SEM_JUSTA_CAUSA",
            "justa_causa": "JUSTA_CAUSA",
            "pedido_demissao": "PEDIDO_DEMISSAO",
            "distrato": "DISTRATO",
            "morte": "MORTE",
        }
        if cont.get("tipo_rescisao"):
            self._selecionar("tipoRescisao", rescisao_map.get(cont["tipo_rescisao"], "SEM_JUSTA_CAUSA"), obrigatorio=False)
            self._selecionar("motivoDesligamento", rescisao_map.get(cont["tipo_rescisao"], "SEM_JUSTA_CAUSA"), obrigatorio=False)

        regime_map = {
            "Tempo Integral": "TEMPO_INTEGRAL",
            "Tempo Parcial": "TEMPO_PARCIAL",
            "Trabalho Intermitente": "INTERMITENTE",
        }
        if cont.get("regime"):
            self._selecionar("regimeTrabalho", regime_map.get(cont["regime"], "TEMPO_INTEGRAL"), obrigatorio=False)
            self._selecionar("regimeDoContrato", regime_map.get(cont["regime"], "TEMPO_INTEGRAL"), obrigatorio=False)

        if cont.get("carga_horaria"):
            self._preencher("cargaHoraria", str(int(cont["carga_horaria"])), False)
            self._preencher("cargaHorariaMensal", str(int(cont["carga_horaria"])), False)

        if cont.get("maior_remuneracao"):
            self._preencher("maiorRemuneracao", _fmt_br(cont["maior_remuneracao"]), False)
            self._preencher("maiorSalario", _fmt_br(cont["maior_remuneracao"]), False)
        if cont.get("ultima_remuneracao"):
            self._preencher("ultimaRemuneracao", _fmt_br(cont["ultima_remuneracao"]), False)
            self._preencher("ultimoSalario", _fmt_br(cont["ultima_remuneracao"]), False)

        # Aviso prévio
        ap_tipo_map = {
            "Calculado": "CALCULADO",
            "Informado": "INFORMADO",
            "Nao Apurar": "NAO_APURAR",
        }
        if ap.get("tipo"):
            self._selecionar("tipoAvisoPrevio", ap_tipo_map.get(ap["tipo"], "CALCULADO"), obrigatorio=False)
            self._selecionar("avisoPrevio", ap_tipo_map.get(ap["tipo"], "CALCULADO"), obrigatorio=False)
        if ap.get("prazo_dias"):
            self._preencher("diasAvisoPrevio", str(int(ap["prazo_dias"])), False)

        # Prescrição
        if presc.get("quinquenal") is not None:
            self._marcar_checkbox("prescricaoQuinquenal", bool(presc["quinquenal"]))
        if presc.get("fgts") is not None:
            self._marcar_checkbox("prescricaoFgts", bool(presc["fgts"]))

        # Índices de correção e juros
        cj = dados.get("correcao_juros", {})
        ir = dados.get("imposto_renda", {})

        indice_map = {
            "Tabela JT Única Mensal": "IPCAE",
            "Tabela JT Unica Mensal": "IPCAE",
            "IPCA-E": "IPCAE",
            "Selic": "SELIC",
            "TRCT": "TRCT",
            "TR": "TRD",
        }
        indice = indice_map.get(cj.get("indice_correcao", ""), "IPCAE")
        self._selecionar("indiceTrabalhista", indice, obrigatorio=False)
        self._selecionar("indiceCorrecao", indice, obrigatorio=False)

        juros_map = {"Selic": "SELIC", "Juros Padrão": "TRD_SIMPLES", "Juros Padrao": "TRD_SIMPLES"}
        juros = juros_map.get(cj.get("taxa_juros", ""), "SELIC")
        self._selecionar("juros", juros, obrigatorio=False)
        self._selecionar("taxaJuros", juros, obrigatorio=False)

        base_map = {"Verbas": "VERBA_INSS", "Credito Total": "CREDITO_TOTAL"}
        base = base_map.get(cj.get("base_juros", "Verbas"), "VERBA_INSS")
        self._selecionar("baseDeJurosDasVerbas", base, obrigatorio=False)

        if ir.get("apurar"):
            self._marcar_checkbox("apurarImpostoRenda", True)
            if ir.get("meses_tributaveis"):
                self._preencher("qtdMesesRendimento", str(ir["meses_tributaveis"]), False)
            if ir.get("dependentes"):
                self._marcar_checkbox("possuiDependentes", True)
                self._preencher("quantidadeDependentes", str(ir["dependentes"]), False)

        if not self._clicar_salvar():
            self._log("  ⚠ Fase 1: Salvar não confirmado — dados do processo podem não ter persistido.")
        self._log("Fase 1 concluída.")

    # ── Utilitário de screenshot por fase ──────────────────────────────────────

    def _screenshot_fase(self, nome_fase: str) -> None:
        """Captura screenshot após conclusão de uma fase (diagnóstico não-crítico)."""
        try:
            from config import SCREENSHOTS_DIR
            import time as _t
            ts = int(_t.time())
            Path(SCREENSHOTS_DIR).mkdir(parents=True, exist_ok=True)
            path = Path(SCREENSHOTS_DIR) / f"{ts}_{nome_fase}.png"
            self._page.screenshot(path=str(path), full_page=False)
            self._log(f"  📸 {path.name}")
        except Exception as e_ss:
            logger.debug(f"Screenshot falhou (não crítico): {e_ss}")

    # ── Fase 2a: Parâmetros Gerais ─────────────────────────────────────────────

    @retry(max_tentativas=2)
    def fase_parametros_gerais(self, parametros: dict) -> None:
        """Preenche Parâmetros Gerais (Passo 2): data inicial de apuração, carga horária.

        Chamado com `passo_2_parametros_gerais` do parametrizacao.json.
        """
        self._log("Fase 2a — Parâmetros Gerais…")

        data_inicial = parametros.get("data_inicial_apuracao")
        data_final = parametros.get("data_final_apuracao")
        carga_diaria = parametros.get("carga_horaria_diaria")
        carga_semanal = parametros.get("carga_horaria_semanal")
        zerar_negativos = parametros.get("zerar_valores_negativos", True)

        if data_inicial:
            self._preencher_data("dataInicialApuracao", data_inicial, False)
            self._preencher_data("dataInicio", data_inicial, False)
        if data_final:
            self._preencher_data("dataFinalApuracao", data_final, False)
            self._preencher_data("dataFim", data_final, False)
        if carga_diaria:
            self._preencher("cargaHorariaDiaria", str(int(carga_diaria)), False)
        if carga_semanal:
            self._preencher("cargaHorariaSemanal", str(int(carga_semanal)), False)
        if zerar_negativos is not None:
            self._marcar_checkbox("zerarValoresNegativos", bool(zerar_negativos))

        if not self._clicar_salvar():
            self._log("  ⚠ Fase 2a: Salvar não confirmado — parâmetros gerais podem não ter persistido.")
        self._aguardar_ajax()
        # Captura/atualiza URL base após salvar (URL pode ter mudado com novo conversationId)
        self._capturar_base_calculo()
        self._log("  Fase 2a concluída.")

    # ── Fase 2: Histórico Salarial ─────────────────────────────────────────────

    @retry(max_tentativas=2)
    def fase_historico_salarial(self, dados: dict) -> None:
        historico = dados.get("historico_salarial", [])
        if not historico:
            self._log("Fase 2 — Histórico Salarial: sem entradas extraídas — ignorado.")
            return
        self._log(f"Fase 2 — Histórico Salarial: {len(historico)} período(s) extraído(s)…")
        self._verificar_tomcat(timeout=90)
        self._verificar_pagina_pjecalc()
        navegou = self._clicar_menu_lateral("Histórico Salarial", obrigatorio=False)
        if navegou:
            navegou = self._verificar_secao_ativa("Histórico")
        if not navegou:
            self._log("  ⚠ Histórico Salarial não disponível no menu — listando para referência:")
            for h in historico:
                self._log(f"    {h.get('data_inicio','')} a {h.get('data_fim','')} — R$ {h.get('valor','')}")
            return
        self.mapear_campos("fase2_historico_salarial")
        for h in historico:
            # Abrir formulário de novo histórico (seletor específico primeiro)
            _abriu = self._clicar_botao_id("btnNovoHistorico") or self._clicar_novo()
            try:
                self._page.wait_for_selector(
                    "input[id*='competenciaInicial'], input[id*='dataInicio'], input[id*='dataInicial']",
                    state="visible", timeout=6000
                )
            except Exception:
                self._page.wait_for_timeout(1000)

            # Nome da entrada (ex: "Salário", "Adicional Noturno Pago")
            nome_hist = h.get("nome", "Salário")
            self._preencher("historico:nome", nome_hist, False)
            self._preencher("nomeHistorico", nome_hist, False)

            # Competências (mês/ano de início e fim)
            self._preencher_data("competenciaInicial", h.get("data_inicio", ""), False)
            self._preencher_data("competenciaFinal", h.get("data_fim", ""), False)
            # Fallback: nomes alternativos de campo
            self._preencher_data("dataInicio", h.get("data_inicio", ""), False)
            self._preencher_data("dataFim", h.get("data_fim", ""), False)
            self._preencher_data("dataInicial", h.get("data_inicio", ""), False)
            self._preencher_data("dataFinal", h.get("data_fim", ""), False)

            # Valor base (valor mensal completo — sistema proporcionaliza)
            _val = _fmt_br(h.get("valor", ""))
            self._preencher("valorBase", _val, False)
            self._preencher("salario", _val, False)
            self._preencher("valor", _val, False)

            # Incidências FGTS e CS (usar valores do histórico se fornecidos)
            if h.get("incidencia_fgts") is not None:
                self._marcar_checkbox("incidenciaFGTS", bool(h["incidencia_fgts"]))
            if h.get("incidencia_cs") is not None:
                self._marcar_checkbox("incidenciaCS", bool(h["incidencia_cs"]))

            # Gerar ocorrências (cria a grade mensal de valores)
            _gerou = self._clicar_botao_id("btnGerarOcorrencias")
            if _gerou:
                self._aguardar_ajax()
                self._page.wait_for_timeout(1000)
                # Scroll para baixo — botão Salvar fica após a lista de ocorrências
                self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self._log(f"  ✓ Ocorrências geradas: {nome_hist}")

            # Salvar (seletor específico prioritário)
            self._clicar_botao_id("btnSalvarHistorico") or self._clicar_salvar()
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            try:
                self._page.wait_for_selector(
                    "[id$='filtroNome'], input[id*='competenciaInicial'], [name*='filtroNome']",
                    state="visible", timeout=5000
                )
            except Exception:
                self._clicar_menu_lateral("Histórico Salarial", obrigatorio=False)
                self._page.wait_for_timeout(800)
            self._log(f"  ✓ Período: {h.get('data_inicio','')} a {h.get('data_fim','')} — R$ {h.get('valor','')}")
        self._log("Fase 2 concluída.")

    # ── Fase 3: Verbas ─────────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_verbas(self, verbas_mapeadas: dict) -> None:
        self._log("Fase 3 — Verbas…")
        self._verificar_tomcat(timeout=90)
        self._verificar_pagina_pjecalc()
        self._clicar_menu_lateral("Verbas")
        self._verificar_secao_ativa("Verba")
        self._page.wait_for_timeout(1500)

        predefinidas = verbas_mapeadas.get("predefinidas", [])
        personalizadas = verbas_mapeadas.get("personalizadas", [])

        # Diagnóstico: listar botões disponíveis na página de verbas
        try:
            _botoes_verbas = self._page.evaluate("""() =>
                [...document.querySelectorAll('a,input[type="submit"],input[type="button"],button')]
                .map(el => ({id: el.id, txt: (el.textContent||el.value||el.title||'').replace(/\\s+/g,' ').trim()}))
                .filter(o => o.txt.length > 1 && o.txt.length < 50)
                .map(o => o.txt + (o.id ? ' [' + o.id + ']' : ''))
            """)
            self._log(f"  🔘 Botões pág Verbas: {list(dict.fromkeys(_botoes_verbas))[:20]}")
        except Exception:
            pass

        self.mapear_campos("fase3_verbas")

        # ── 3A: Lançamento Expresso (verbas predefinidas) ─────────────────────
        if predefinidas:
            self._log(f"  → Expresso: {len(predefinidas)} verba(s) predefinida(s)")

            # Clicar botão "Expresso"
            _clicou_expresso = False
            for _sel in [
                "input[id*='btnExpresso']",
                "input[value='Expresso']",
                "input[value*='Expresso']",
                "a[id*='Expresso']",
            ]:
                try:
                    _loc = self._page.locator(_sel)
                    if _loc.count() > 0:
                        _loc.first.click()
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(800)
                        _clicou_expresso = True
                        self._log(f"  ✓ Botão Expresso via '{_sel}'")
                        break
                except Exception:
                    continue

            if not _clicou_expresso:
                try:
                    _res = self._page.evaluate("""() => {
                        const el = [...document.querySelectorAll('input,button,a')]
                            .find(e => (e.value||e.textContent||'').trim().toUpperCase() === 'EXPRESSO');
                        if (el) { el.click(); return el.id || el.tagName; }
                        return null;
                    }""")
                    if _res:
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(800)
                        _clicou_expresso = True
                        self._log(f"  ✓ Botão Expresso via JS: {_res}")
                except Exception as _e:
                    self._log(f"  ⚠ Botão Expresso não encontrado: {_e}")

            if _clicou_expresso:
                # Listar verbas disponíveis no Expresso (diagnóstico)
                try:
                    _labels_exp = self._page.evaluate("""() =>
                        [...document.querySelectorAll('input[type="checkbox"]')]
                        .map(cb => {
                            const l = document.querySelector('label[for="' + cb.id + '"]');
                            return l ? l.textContent.replace(/\\s+/g,' ').trim() : '';
                        })
                        .filter(Boolean)
                    """)
                    self._log(f"  📋 Verbas Expresso disponíveis: {_labels_exp[:30]}")
                except Exception:
                    pass

                # Marcar checkboxes por nome (case-insensitive, normalizado)
                _marcadas: list[str] = []
                _nao_encontradas: list[str] = []
                for v in predefinidas:
                    nome = v.get("nome_pjecalc") or v.get("nome_sentenca") or ""
                    if not nome:
                        continue
                    if self._marcar_checkbox_expresso(nome):
                        _marcadas.append(nome)
                    else:
                        _nao_encontradas.append(nome)
                        self._log(f"  ⚠ Verba não encontrada no Expresso: {nome}")

                if _marcadas:
                    self._log(f"  ✓ Marcadas: {_marcadas}")
                    # Salvar verbas Expresso (seletor específico prioritário)
                    _salvou_expresso = (
                        self._clicar_botao_id("btnSalvarExpresso")
                        or self._clicar_salvar()
                    )
                    if _salvou_expresso:
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(1500)
                        self._log("  ✓ Verbas Expresso salvas")
                    else:
                        self._log("  ⚠ btnSalvarExpresso não encontrado — tentando Enter")
                        try:
                            self._page.keyboard.press("Enter")
                            self._aguardar_ajax()
                            self._page.wait_for_timeout(1500)
                        except Exception:
                            pass

                    # Configurar reflexos após salvar
                    self._configurar_reflexos_expresso(predefinidas)
                else:
                    self._log("  ⚠ Nenhuma verba marcada no Expresso")

                if _nao_encontradas:
                    self._log(
                        f"  → {len(_nao_encontradas)} verba(s) não encontrada(s) no Expresso "
                        f"— adicionando ao fluxo Manual: {_nao_encontradas}"
                    )
                    personalizadas = [
                        v for v in predefinidas
                        if (v.get("nome_pjecalc") or v.get("nome_sentenca") or "") in _nao_encontradas
                    ] + personalizadas
            else:
                self._log("  ⚠ Modo Expresso indisponível — todas as verbas via Manual")
                personalizadas = predefinidas + personalizadas

        # ── 3B: Verbas personalizadas (Manual/Novo) ────────────────────────
        if personalizadas:
            self._log(f"  → Manual: {len(personalizadas)} verba(s) personalizada(s)")
            self._clicar_menu_lateral("Verbas", obrigatorio=False)
            self._page.wait_for_timeout(1000)
            self._lancar_verbas_manual(personalizadas)

        nao_rec = verbas_mapeadas.get("nao_reconhecidas", [])
        if nao_rec:
            nomes = ", ".join(v.get("nome_sentenca", "?") for v in nao_rec)
            self._log(
                f"  ⚠ AVISO: {len(nao_rec)} verba(s) não mapeada(s) ignorada(s) na automação "
                f"(deveriam ter sido corrigidas na prévia): {nomes}"
            )

        self._log("Fase 3 concluída.")

    def _marcar_checkbox_expresso(self, nome: str) -> bool:
        """Localiza e marca o checkbox do Expresso cujo label contém 'nome' (case-insensitive)."""
        try:
            _resultado = self._page.evaluate(
                """(nome) => {
                    function norm(s) {
                        return s.toLowerCase()
                            .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                    }
                    const nomeLower = norm(nome);
                    const checkboxes = [...document.querySelectorAll('input[type="checkbox"]')];
                    // 1ª tentativa: label exato ou contém o nome completo
                    for (const cb of checkboxes) {
                        const lbl = document.querySelector('label[for="' + cb.id + '"]');
                        if (!lbl) continue;
                        const lblNorm = norm(lbl.textContent.trim());
                        if (lblNorm === nomeLower || lblNorm.includes(nomeLower)
                                || nomeLower.includes(lblNorm.substring(0, Math.min(lblNorm.length, 12)))) {
                            if (!cb.checked) cb.click();
                            return lbl.textContent.trim();
                        }
                    }
                    // 2ª tentativa: primeiras 2 palavras do nome
                    const palavras = nomeLower.split(' ').slice(0, 2).join(' ');
                    if (palavras.length >= 5) {
                        for (const cb of checkboxes) {
                            const lbl = document.querySelector('label[for="' + cb.id + '"]');
                            if (!lbl) continue;
                            const lblNorm = norm(lbl.textContent.trim());
                            if (lblNorm.includes(palavras)) {
                                if (!cb.checked) cb.click();
                                return lbl.textContent.trim();
                            }
                        }
                    }
                    return null;
                }""",
                nome,
            )
            if _resultado:
                self._log(f"  ✓ Expresso checkbox: {nome} → '{_resultado}'")
                self._page.wait_for_timeout(200)
                return True
            return False
        except Exception as _e:
            self._log(f"  ⚠ _marcar_checkbox_expresso({nome}): {_e}")
            return False

    def _configurar_reflexos_expresso(self, verbas: list) -> None:
        """Expande os reflexos de cada verba salva via Expresso e marca os necessários."""
        try:
            _exibir_count = self._page.evaluate("""() =>
                [...document.querySelectorAll('a')].filter(
                    a => (a.textContent || '').trim().toLowerCase().includes('exibir')
                ).length
            """)
            if not _exibir_count:
                self._log("  → Nenhum link 'Exibir' encontrado — reflexos não configurados")
                return
            self._log(f"  → Configurando reflexos ({_exibir_count} link(s) 'Exibir')…")

            # Mapa nome_pjecalc → reflexas_tipicas
            _reflexos_map: dict[str, list[str]] = {}
            for v in verbas:
                nome = v.get("nome_pjecalc") or v.get("nome_sentenca") or ""
                reflexas = v.get("reflexas_tipicas", [])
                if nome and reflexas:
                    _reflexos_map[nome] = reflexas

            if not _reflexos_map:
                return

            _linhas = self._page.evaluate("""() => {
                const rows = [...document.querySelectorAll(
                    'tr[id*="listagem"], tr.rich-table-row, tbody tr'
                )];
                return rows.map((tr, i) => ({
                    index: i,
                    texto: tr.textContent.replace(/\\s+/g,' ').trim().substring(0, 100),
                    temExibir: [...tr.querySelectorAll('a')]
                        .some(a => (a.textContent||'').trim().toLowerCase().includes('exibir')),
                }));
            }""")

            for row in _linhas:
                if not row.get("temExibir"):
                    continue
                _texto_row = row.get("texto", "").lower()

                _reflexas_needed: list[str] = []
                for nome_v, reflexas in _reflexos_map.items():
                    _kw = " ".join(nome_v.lower().split()[:2])
                    if _kw and _kw in _texto_row:
                        _reflexas_needed = reflexas
                        self._log(f"  → Reflexos de '{nome_v}': {reflexas}")
                        break

                if not _reflexas_needed:
                    continue

                row_idx = row["index"]
                try:
                    _clicou = self._page.evaluate(
                        """(idx) => {
                            const rows = [...document.querySelectorAll(
                                'tr[id*="listagem"], tr.rich-table-row, tbody tr'
                            )];
                            if (idx >= rows.length) return false;
                            const link = [...rows[idx].querySelectorAll('a')]
                                .find(a => (a.textContent||'').trim().toLowerCase().includes('exibir'));
                            if (!link) return false;
                            link.click();
                            return true;
                        }""",
                        row_idx,
                    )
                    if not _clicou:
                        continue
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                except Exception as _e:
                    self._log(f"  ⚠ Exibir row {row_idx}: {_e}")
                    continue

                for reflexo_nome in _reflexas_needed:
                    try:
                        _marcou = self._page.evaluate(
                            """(rNome) => {
                                function norm(s) {
                                    return s.toLowerCase()
                                        .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                                }
                                const rLower = norm(rNome).substring(0, 10);
                                const cbs = [...document.querySelectorAll(
                                    'input[type="checkbox"][id*="listaReflexo"],' +
                                    'input[type="checkbox"][id*="reflexo"]'
                                )].filter(cb => {
                                    const r = cb.getBoundingClientRect();
                                    return r.width > 0 && r.height > 0;
                                });
                                for (const cb of cbs) {
                                    const ctx = cb.closest('td') || cb.parentElement;
                                    const txt = norm((ctx && ctx.textContent) || '');
                                    if (txt.includes(rLower)) {
                                        if (!cb.checked) cb.click();
                                        return (ctx && ctx.textContent.trim().substring(0, 60)) || 'ok';
                                    }
                                }
                                return null;
                            }""",
                            reflexo_nome,
                        )
                        if _marcou:
                            self._log(f"  ✓ Reflexo: {reflexo_nome} → '{_marcou}'")
                        else:
                            self._log(f"  ⚠ Reflexo não encontrado: {reflexo_nome}")
                    except Exception as _e:
                        self._log(f"  ⚠ Reflexo {reflexo_nome}: {_e}")

        except Exception as _e:
            self._log(f"  ⚠ _configurar_reflexos_expresso: {_e}")

    def _lancar_verbas_manual(self, verbas: list) -> None:
        """Lança verbas individualmente via botão 'Novo' (para verbas personalizadas)."""
        carac_map = {
            "Comum": "COMUM",
            "13o Salario": "DECIMO_TERCEIRO_SALARIO",
            "Ferias": "FERIAS",
            "Aviso Previo": "AVISO_PREVIO",
        }
        ocorr_map = {
            "Mensal": "MENSAL",
            "Dezembro": "DEZEMBRO",
            "Periodo Aquisitivo": "PERIODO_AQUISITIVO",
            "Desligamento": "DESLIGAMENTO",
        }
        _url_verbas = self._page.url
        _JS_CAMPOS = """() =>
            [...document.querySelectorAll(
                'input:not([type="hidden"]):not([type="image"]):not([type="submit"]):not([type="button"]),select,textarea'
            )]
            .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
            .map(e => e.id || e.name || '').filter(Boolean)
        """
        _campos_lista = set()
        try:
            _campos_lista = set(self._page.evaluate(_JS_CAMPOS))
        except Exception:
            pass

        for i, v in enumerate(verbas):
            if self._page.url != _url_verbas:
                try:
                    self._page.goto(_url_verbas, wait_until="domcontentloaded", timeout=20000)
                    self._page.wait_for_timeout(1000)
                    self._aguardar_ajax()
                except Exception:
                    self._clicar_menu_lateral("Verbas", obrigatorio=False)
                    self._page.wait_for_timeout(800)

            _clicou_novo = self._page.evaluate("""() => {
                const filtro = document.querySelector('[id*="filtroNome"]');
                if (filtro) {
                    let el = filtro;
                    for (let n = 0; n < 15; n++) {
                        el = el.parentElement;
                        if (!el || el.tagName === 'BODY' || el.tagName === 'FORM') break;
                        const novos = [...el.querySelectorAll('a,input[type="submit"],input[type="button"],button')]
                            .filter(e => {
                                const t = (e.textContent||e.value||'').replace(/\\s+/g,' ').trim();
                                return t === 'Novo' || t === 'Nova';
                            });
                        if (novos.length > 0) { novos[0].click(); return 'FILTRO:' + novos[0].id; }
                    }
                }
                const all = [...document.querySelectorAll('a,input[type="submit"],input[type="button"],button')]
                    .filter(e => {
                        const t = (e.textContent||e.value||'').replace(/\\s+/g,' ').trim();
                        return (t === 'Novo' || t === 'Nova')
                            && !(e.className||'').toLowerCase().includes('menu');
                    });
                if (all.length > 0) { all[0].click(); return 'FB:' + all[0].id; }
                return null;
            }""")
            self._log(f"  → Manual Novo: '{_clicou_novo}'")
            nome = v.get("nome_pjecalc") or v.get("nome_sentenca") or "Verba"
            if _clicou_novo is None:
                # Tentativa 2: _clicar_novo() via seletor de ID
                self._clicar_novo()
                self._aguardar_ajax()
                self._page.wait_for_timeout(1500)
                _form_abriu = self._page.locator(
                    "[id$='descricao'], [id$='descricaoVerba'], [id$='nomeVerba']"
                ).count() > 0
                if not _form_abriu:
                    self._log(f"  ⚠ Verba '{nome}': formulário Novo não abriu — ignorada.")
                    continue
            else:
                self._aguardar_ajax()
                self._page.wait_for_timeout(2000)
            if i == 0:
                self.mapear_campos("verba_form_manual")

            _desc_ok = any(
                self._preencher(fid, nome, obrigatorio=False)
                for fid in ["descricao", "descricaoVerba", "nomeVerba", "nome", "titulo", "verba"]
            )
            if not _desc_ok:
                for _lbl in ["Descrição", "Descrição da Verba", "Nome da Verba", "Nome", "Verba"]:
                    _loc = self._page.get_by_label(_lbl, exact=False)
                    if _loc.count() > 0:
                        try:
                            _loc.first.fill(nome)
                            _loc.first.dispatch_event("change")
                            _desc_ok = True
                            break
                        except Exception:
                            continue

            carac = carac_map.get(v.get("caracteristica", "Comum"), "COMUM")
            any(self._selecionar(fid, carac, obrigatorio=False)
                for fid in ["caracteristicaVerba", "stpcaracteristicaverba",
                             "caracteristica", "tipoVerba"])

            ocorr = ocorr_map.get(v.get("ocorrencia", "Mensal"), "MENSAL")
            any(self._selecionar(fid, ocorr, obrigatorio=False)
                for fid in ["ocorrenciaPagto", "ocorrenciaDePagamento",
                             "ocorrencia", "periodicidade"])

            if v.get("valor_informado"):
                self._marcar_radio("valor", "INFORMADO") or \
                    self._marcar_radio("tipoValor", "INFORMADO")
                self._preencher("valorDevidoInformado", _fmt_br(v["valor_informado"]), False)
                self._preencher("valorInformado", _fmt_br(v["valor_informado"]), False)
            else:
                self._marcar_radio("valor", "CALCULADO") or \
                    self._marcar_radio("tipoValor", "CALCULADO")

            self._marcar_checkbox("fgts", bool(v.get("incidencia_fgts")))
            self._marcar_checkbox("inss", bool(v.get("incidencia_inss")))
            self._marcar_checkbox("irpf", bool(v.get("incidencia_ir")))

            if v.get("periodo_inicio"):
                self._preencher_data("periodoInicial", v["periodo_inicio"], False)
                self._preencher_data("dtInicial", v["periodo_inicio"], False)
            if v.get("periodo_fim"):
                self._preencher_data("periodoFinal", v["periodo_fim"], False)
                self._preencher_data("dtFinal", v["periodo_fim"], False)

            self._clicar_salvar()
            self._aguardar_ajax()
            self._page.wait_for_timeout(600)

            if self._page.url != _url_verbas:
                try:
                    self._page.goto(_url_verbas, wait_until="domcontentloaded", timeout=20000)
                    self._page.wait_for_timeout(1000)
                    self._aguardar_ajax()
                except Exception:
                    self._clicar_menu_lateral("Verbas", obrigatorio=False)
                    self._page.wait_for_timeout(800)
            self._log(f"  ✓ Verba manual: {nome}")

    # ── Fase 4: FGTS ──────────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_fgts(self, fgts: dict) -> None:
        self._log("Fase 4 — FGTS…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        # Tentar navegar para a seção FGTS no menu lateral
        navegou = self._clicar_menu_lateral("FGTS", obrigatorio=False)
        if not navegou:
            navegou = self._clicar_menu_lateral("Fundo de Garantia", obrigatorio=False)
        if navegou:
            navegou = self._verificar_secao_ativa("FGTS")
        if not navegou:
            self._log("  → Seção FGTS não encontrada no menu — incidência já configurada por verba.")
            return
        self.mapear_campos("fase4_fgts")
        # Destino do FGTS (para reclamante ou depósito em conta)
        if fgts.get("destino"):
            self._selecionar("destinoFGTS", fgts["destino"], obrigatorio=False)

        # Alíquota FGTS (padrão 8%)
        aliquota = fgts.get("aliquota", 0.08)
        self._preencher("aliquotaFgts", _fmt_br(aliquota * 100), False)
        self._preencher("percentualFgts", _fmt_br(aliquota * 100), False)
        self._preencher("aliquota", _fmt_br(aliquota * 100), False)

        # Multa: checkbox apurarMulta + select tipoMulta (40% ou 50%)
        multa_40 = fgts.get("multa_40", True)
        multa_467 = fgts.get("multa_467", False)
        if multa_40 or multa_467:
            self._marcar_checkbox("apurarMulta", True)
            tipo_multa = "CINQUENTA" if multa_467 else "QUARENTA"
            self._selecionar("tipoMulta", tipo_multa, obrigatorio=False)
        # Fallback para checkboxes específicos (versões antigas do PJE-Calc)
        self._marcar_checkbox("multa40", bool(multa_40))
        self._marcar_checkbox("multaFgts40", bool(multa_40))
        self._marcar_checkbox("multa467", bool(multa_467))
        self._marcar_checkbox("multaFgts467", bool(multa_467))

        # Saldos FGTS já depositados (dedução dos valores devidos)
        for saldo in fgts.get("saldos", []):
            if saldo.get("data") and saldo.get("valor"):
                self._preencher_data("saldoData", saldo["data"], False)
                self._preencher("saldoValor", _fmt_br(saldo["valor"]), False)
                if self._clicar_botao_id("btnAdicionarSaldo"):
                    self._aguardar_ajax()
                    self._log(f"  ✓ Saldo FGTS adicionado: {saldo['data']} R$ {saldo['valor']}")

        # Salvar (seletor específico prioritário)
        if not (self._clicar_botao_id("btnSalvarFGTS") or self._clicar_salvar()):
            self._log("  ⚠ Fase 4: Salvar FGTS não confirmado.")
        self._aguardar_ajax()
        self._log("Fase 4 concluída.")

    # ── Fase 5: Contribuição Social (INSS) ────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_contribuicao_social(self, cs: dict) -> None:
        self._log("Fase 5 — Contribuição Social (INSS)…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        navegou = (
            self._clicar_menu_lateral("Contribuição Social", obrigatorio=False)
            or self._clicar_menu_lateral("Contribuicao Social", obrigatorio=False)
            or self._clicar_menu_lateral("INSS", obrigatorio=False)
        )
        if navegou:
            navegou = self._verificar_secao_ativa("Contribui")
        if not navegou:
            self._log("  → Seção Contribuição Social não encontrada — ignorado.")
            return
        self.mapear_campos("fase5_inss")

        # Migrar schema legado (responsabilidade → booleans) se necessário
        from modules.extraction import _migrar_inss_legado
        if "responsabilidade" in cs:
            cs = _migrar_inss_legado(cs)

        # Checkboxes individuais (correspondentes exatos da UI do PJE-Calc)
        self._marcar_checkbox("apurarSeguradoSaláriosDevidos",
                              cs.get("apurar_segurado_salarios_devidos", True))
        self._marcar_checkbox("apurarSeguradoSalariosDevidos",
                              cs.get("apurar_segurado_salarios_devidos", True))
        self._marcar_checkbox("cobrarDoReclamante",
                              cs.get("cobrar_do_reclamante", True))
        self._marcar_checkbox("comCorrecaoTrabalhista",
                              cs.get("com_correcao_trabalhista", True))
        self._marcar_checkbox("apurarSobreSaláriosPagos",
                              cs.get("apurar_sobre_salarios_pagos", False))
        self._marcar_checkbox("apurarSobreSalariosPagos",
                              cs.get("apurar_sobre_salarios_pagos", False))
        if cs.get("lei_11941"):
            self._marcar_checkbox("lei11941", True)
        if not self._clicar_salvar():
            self._log("  ⚠ Fase 5: Salvar INSS não confirmado.")
        self._log("Fase 5 concluída.")

    # ── Fase 5b: Cartão de Ponto ──────────────────────────────────────────────

    @retry(max_tentativas=2)
    def fase_cartao_ponto(self, dados: dict) -> None:
        """
        Preenche o Cartão de Ponto com a jornada extraída da sentença.
        Necessário para cálculo correto de horas extras e reflexos.
        Deriva horas/dia e dias/semana a partir de carga_horaria (horas/mês).
        """
        cont = dados.get("contrato", {})
        carga_horaria = cont.get("carga_horaria")   # horas/mês (int)
        jornada_diaria = cont.get("jornada_diaria")  # horas/dia (float, extraído diretamente)
        jornada_semanal = cont.get("jornada_semanal")  # horas/semana (float)
        data_inicio = cont.get("admissao")
        data_fim = cont.get("demissao")

        # Calcular jornada se não extraída diretamente
        if not jornada_diaria and carga_horaria:
            # Padrões CLT: 220h/mês = 8h/dia 44h/sem | 180h/mês = 6h/dia 36h/sem
            # 160h/mês = 8h/dia 40h/sem (jornada reduzida)
            if carga_horaria >= 210:
                jornada_diaria = 8.0
                jornada_semanal = jornada_semanal or 44.0
            elif carga_horaria >= 175:
                jornada_diaria = 8.0
                jornada_semanal = jornada_semanal or 40.0
            elif carga_horaria >= 155:
                jornada_diaria = 6.0
                jornada_semanal = jornada_semanal or 36.0
            else:
                jornada_diaria = carga_horaria / (4.5 * 5)  # aprox
                jornada_semanal = jornada_semanal or round(jornada_diaria * 5, 1)

        if not jornada_diaria:
            self._log("Fase 5b — Cartão de Ponto: jornada não extraída — ignorado.")
            return

        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()

        navegou = (
            self._clicar_menu_lateral("Cartão de Ponto", obrigatorio=False)
            or self._clicar_menu_lateral("Jornada", obrigatorio=False)
            or self._clicar_menu_lateral("Ponto", obrigatorio=False)
        )
        if not navegou:
            self._log(
                f"  Fase 5b — Cartão de Ponto: menu não encontrado. "
                f"Jornada extraída: {jornada_diaria}h/dia, {jornada_semanal}h/sem."
            )
            return

        self.mapear_campos("fase5b_cartao_ponto")
        self._clicar_novo()
        self._page.wait_for_timeout(800)

        # Período
        if data_inicio:
            self._preencher_data("dataInicio", data_inicio, False)
            self._preencher_data("dataInicial", data_inicio, False)
        if data_fim:
            self._preencher_data("dataFim", data_fim, False)
            self._preencher_data("dataFinal", data_fim, False)

        # Jornada diária (horas)
        _jd_str = _fmt_br(jornada_diaria)
        self._preencher("jornadaDiaria", _jd_str, False)
        self._preencher("horasDia", _jd_str, False)
        self._preencher("jornada", _jd_str, False)
        self._preencher("horasJornada", _jd_str, False)

        # Jornada semanal
        if jornada_semanal:
            _js_str = _fmt_br(jornada_semanal)
            self._preencher("jornadaSemanal", _js_str, False)
            self._preencher("horasSemana", _js_str, False)
            self._preencher("cargaHorariaSemanal", _js_str, False)

        # Intervalo padrão (1h para jornadas ≥ 6h — art. 71 CLT)
        intervalo = 1.0 if jornada_diaria >= 6 else 0.0
        if intervalo:
            self._preencher("intervalo", _fmt_br(intervalo), False)
            self._preencher("horasIntervalo", _fmt_br(intervalo), False)
            self._preencher("tempoIntervalo", _fmt_br(intervalo), False)

        self._clicar_salvar()
        self._aguardar_ajax()
        self._log(
            f"  ✓ Cartão de Ponto: {jornada_diaria}h/dia × "
            f"{jornada_semanal}h/sem (intervalo {intervalo}h)"
        )
        self._log("Fase 5b concluída.")

    # ── Fase 6: Parâmetros de Atualização ─────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_parametros_atualizacao(self, cj: dict) -> None:
        self._log("Fase 6 — Parâmetros de atualização (preenchidos na Fase 1 — ignorado).")

    # ── Fase 7: IRPF ──────────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_irpf(self, ir: dict) -> None:
        if not ir.get("apurar"):
            self._log("Fase 7 — IRPF: apurar=False — ignorado.")
            return
        self._log("Fase 7 — IRPF…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        navegou = (
            self._clicar_menu_lateral("Imposto de Renda", obrigatorio=False)
            or self._clicar_menu_lateral("IRPF", obrigatorio=False)
            or self._clicar_menu_lateral("IR", obrigatorio=False)
        )
        if navegou:
            navegou = self._verificar_secao_ativa("Imposto")
        if not navegou:
            self._log("  → Seção IRPF não encontrada no menu — ignorado.")
            return
        self.mapear_campos("fase7_irpf")

        # Regime de tributação
        if ir.get("tributacao_exclusiva"):
            self._marcar_checkbox("tributacaoExclusiva", True)
            self._marcar_checkbox("tributacaoExclusivaFonte", True)
        if ir.get("regime_de_caixa"):
            self._marcar_checkbox("regimeDeCaixa", True)
            self._marcar_checkbox("regimeCaixa", True)
        if ir.get("tributacao_em_separado"):
            self._marcar_checkbox("tributacaoEmSeparado", True)

        # Deduções
        if ir.get("deducao_inss", True):
            self._marcar_checkbox("deducaoInss", True)
            self._marcar_checkbox("descontarInss", True)
        if ir.get("deducao_honorarios_reclamante"):
            self._marcar_checkbox("deducaoHonorariosReclamante", True)
            self._marcar_checkbox("descontarHonorarios", True)
        if ir.get("deducao_pensao_alimenticia"):
            self._marcar_checkbox("deducaoPensaoAlimenticia", True)
            self._marcar_checkbox("pensaoAlimenticia", True)
            if ir.get("valor_pensao"):
                self._preencher("valorPensao", _fmt_br(ir["valor_pensao"]), False)
                self._preencher("valorDaPensao", _fmt_br(ir["valor_pensao"]), False)

        # Campos numéricos
        if ir.get("dependentes"):
            self._preencher("numeroDeDependentes", str(int(ir["dependentes"])), False)
            self._preencher("dependentes", str(int(ir["dependentes"])), False)
        if ir.get("meses_tributaveis"):
            self._preencher("mesesTributaveis", str(int(ir["meses_tributaveis"])), False)

        if not self._clicar_salvar():
            self._log("  ⚠ Fase 7: Salvar IRPF não confirmado.")
        self._log("Fase 7 concluída.")

    # ── Fase 8: Honorários ────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_honorarios(self, hon_dados, periciais: float | None = None) -> None:
        """
        Preenche honorários advocatícios no PJE-Calc.
        Aceita lista de registros [{tipo, devedor, tipo_valor, base_apuracao, percentual, ...}]
        ou dict legado {percentual, parte_devedora} — migra automaticamente.
        """
        # Migrar schema legado dict → list
        from modules.extraction import _migrar_honorarios_legado
        if isinstance(hon_dados, dict):
            hon_lista = _migrar_honorarios_legado(hon_dados)
        else:
            hon_lista = hon_dados or []

        if not hon_lista:
            self._log("Fase 8 — Honorários: lista vazia — ignorado.")
            return

        self._log(f"Fase 8 — Honorários ({len(hon_lista)} registro(s))…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        navegou = (
            self._clicar_menu_lateral("Honorários", obrigatorio=False)
            or self._clicar_menu_lateral("Honorarios", obrigatorio=False)
        )
        if navegou:
            navegou = self._verificar_secao_ativa("Honorár")
        if not navegou:
            self._log("  → Seção Honorários não encontrada no menu — ignorado.")
            return

        self.mapear_campos("fase8_honorarios")

        for i, hon in enumerate(hon_lista):
            self._log(f"  → Honorário [{i+1}/{len(hon_lista)}]: {hon.get('devedor')} / {hon.get('tipo')}")
            if i > 0:
                # Clicar "Novo" para adicionar segundo registro
                clicou = (
                    self._clicar_novo()
                    or bool(self._page.locator("input[value='Novo']").first.click() if self._page.locator("input[value='Novo']").count() else None)
                )
                if not clicou:
                    self._log(f"  ⚠ Botão Novo não encontrado para honorário {i+1} — pulando.")
                    continue

            # Tipo de devedor
            devedor = hon.get("devedor", "RECLAMADO")
            self._selecionar("tipoDeDevedor", devedor, obrigatorio=False)
            self._selecionar("devedor", devedor, obrigatorio=False)
            self._selecionar("parteDevedora", devedor, obrigatorio=False)

            # Tipo de honorário (SUCUMBENCIAIS / CONTRATUAIS)
            tipo = hon.get("tipo", "SUCUMBENCIAIS")
            self._selecionar("tipoHonorario", tipo, obrigatorio=False)
            self._selecionar("tipo", tipo, obrigatorio=False)

            # Tipo de valor (CALCULADO / INFORMADO)
            tipo_valor = hon.get("tipo_valor", "CALCULADO")
            self._marcar_radio("tipoValor", tipo_valor) or self._selecionar("tipoValor", tipo_valor, obrigatorio=False)

            # Base de apuração — fuzzy match com opções reais
            base = hon.get("base_apuracao", "")
            if base:
                try:
                    opcoes = self._extrair_opcoes_select("baseParaApuracao")
                    match = self._match_fuzzy(base, opcoes)
                    if match:
                        self._selecionar("baseParaApuracao", match, obrigatorio=False)
                    else:
                        self._log(f"  ⚠ baseParaApuracao '{base}': sem match — ignorado")
                except Exception as _e:
                    self._log(f"  ⚠ baseParaApuracao: erro — {_e}")

            # Percentual ou valor informado
            if tipo_valor == "CALCULADO" and hon.get("percentual") is not None:
                pct_str = _fmt_br(hon["percentual"] * 100)
                self._preencher("percentualHonorarios", pct_str, False)
                self._preencher("percentual", pct_str, False)
            elif tipo_valor == "INFORMADO" and hon.get("valor_informado") is not None:
                self._preencher("valorInformado", _fmt_br(hon["valor_informado"]), False)
                self._preencher("valorFixo", _fmt_br(hon["valor_informado"]), False)

            # Apurar IR
            if hon.get("apurar_ir"):
                self._marcar_checkbox("apurarIr", True)
                self._marcar_checkbox("tributarIR", True)

            self._clicar_salvar()
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)

        # Honorários periciais (campo separado, fora do loop)
        if periciais is not None:
            self._log(f"  → Honorários periciais: {_fmt_br(periciais)}")
            preencheu = (
                self._preencher("honorariosPericiais", _fmt_br(periciais), False)
                or self._preencher("valorPericiais", _fmt_br(periciais), False)
                or self._preencher("honorariosPerito", _fmt_br(periciais), False)
            )
            if not preencheu:
                for lbl in ["Honorários Periciais", "Honorários do Perito", "Periciais"]:
                    loc = self._page.get_by_label(lbl, exact=False)
                    if loc.count() > 0:
                        try:
                            loc.first.fill(_fmt_br(periciais))
                            loc.first.dispatch_event("change")
                            self._aguardar_ajax()
                            preencheu = True
                            self._log(f"  ✓ Periciais via label '{lbl}'")
                            break
                        except Exception:
                            continue
            if preencheu:
                self._clicar_salvar()
                self._aguardar_ajax()
            else:
                self._log(
                    f"  ⚠ Campo periciais não encontrado — preencher manualmente: {_fmt_br(periciais)}"
                )
        self._log("Fase 8 concluída.")

    # ── Liquidar / captura do .PJC ─────────────────────────────────────────────

    def _clicar_liquidar(self) -> str | None:
        """
        Clica Liquidar, aguarda geração do cálculo e captura o arquivo .PJC.
        A automação NUNCA para aqui para interação manual:
          — Tenta navegar para menu Operações se o botão não aparecer na página atual.
          — Se o download direto não for detectado, varre a página por links de exportação.
          — Lança RuntimeError apenas se absolutamente nenhuma estratégia funcionar,
            para que o orquestrador registre a falha e ofereça o .PJC gerado pelo generator.
        """
        self._log("→ Liquidar: iniciando geração do cálculo…")
        from config import OUTPUT_DIR
        out_dir = Path(OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)

        def _localizar_botao_liquidar():
            liq_sels = [
                # Seletores específicos do PJE-Calc (skill /pjecalc-preenchimento)
                "input[id*='btnLiquidar']", "button[id*='btnLiquidar']",
                "[id$='liquidar']", "[id$='liquidarBt']", "[id$='liquidarBtn']",
                "input[value='Liquidar']", "a:has-text('Liquidar')",
                "button:has-text('Liquidar')",
            ]
            for sel in liq_sels:
                try:
                    candidate = self._page.locator(sel)
                    if candidate.count() > 0:
                        return candidate.first
                except Exception:
                    continue
            return None

        def _verificar_alertas_liquidar():
            """Loga alertas/erros presentes na página antes de liquidar."""
            try:
                alertas = self._page.locator(".alertaLiquidacao, [class*='alerta']")
                if alertas.count() > 0:
                    self._log(f"  ⚠ Alerta antes de liquidar: {alertas.first.text_content()[:120]}")
                erros = self._page.locator(".erroLiquidacao, [class*='erro']")
                if erros.count() > 0:
                    self._log(f"  ⚠ Erro antes de liquidar: {erros.first.text_content()[:120]}")
            except Exception:
                pass

        def _salvar_download(dl_info_value) -> str:
            dest = out_dir / dl_info_value.suggested_filename
            if not dest.suffix:
                dest = dest.with_suffix(".pjc")
            dl_info_value.save_as(str(dest))
            self._log(f"PJC_GERADO:{dest}")
            return str(dest)

        # Estratégia 1: navegar diretamente para menu Liquidar
        _nav_liquidar = self._clicar_menu_lateral("Liquidar", obrigatorio=False)
        if _nav_liquidar:
            self._verificar_secao_ativa("Liquidar")
            self._page.wait_for_timeout(1000)
            # Preencher data de liquidação se campo disponível
            try:
                _dt_campo = self._page.locator("input[id*='dataLiquidacao']")
                if _dt_campo.count() > 0 and not _dt_campo.first.input_value():
                    from datetime import date
                    self._preencher_data("dataLiquidacao",
                                        date.today().strftime("%d/%m/%Y"), False)
            except Exception:
                pass
            _verificar_alertas_liquidar()
        loc = _localizar_botao_liquidar()

        # Estratégia 2: navegar para menu "Operações" e tentar novamente
        if loc is None:
            self._log("  Botão Liquidar não encontrado — navegando para Operações…")
            self._clicar_menu_lateral("Operações", obrigatorio=False)
            self._clicar_menu_lateral("Operacoes", obrigatorio=False)
            self._page.wait_for_timeout(1500)
            _verificar_alertas_liquidar()
            loc = _localizar_botao_liquidar()

        # Estratégia 3: JS global (varredura de todos os elementos)
        if loc is None:
            self._log("  Tentando Liquidar via JS global…")
            clicou = self._page.evaluate("""() => {
                const all = [...document.querySelectorAll('a, input[type="submit"], button')];
                for (const el of all) {
                    const txt = (el.textContent||el.value||'').replace(/[\\s\\u00a0]+/g,' ').trim();
                    if (txt === 'Liquidar' || txt.startsWith('Liquidar')) {
                        el.click(); return true;
                    }
                }
                return false;
            }""")
            if clicou:
                self._aguardar_ajax(90000)
                self._page.wait_for_timeout(3000)
                # Verificar se apareceu link de download após clique JS
                for txt in ["Exportar", "Download", ".pjc", "Baixar"]:
                    try:
                        with self._page.expect_download(timeout=20000) as dl_info:
                            if self._clicar_botao(txt, obrigatorio=False):
                                return _salvar_download(dl_info.value)
                    except Exception:
                        continue
                # Se não encontrou download, o JS clicou mas não gerou arquivo — continua
            else:
                raise RuntimeError(
                    "Botão Liquidar não encontrado em nenhuma estratégia. "
                    "Verifique se todos os campos obrigatórios foram preenchidos "
                    "e se o PJE-Calc está na tela correta."
                )

        if loc is not None:
            # Estratégia 4: expect_download com clique direto (captura automática)
            try:
                with self._page.expect_download(timeout=120000) as dl_info:
                    loc.click()
                return _salvar_download(dl_info.value)
            except Exception as e:
                self._log(f"  ⚠ Download direto falhou ({e}) — aguardando resultado na página…")
                try:
                    loc.click()
                except Exception:
                    pass
                self._aguardar_ajax(90000)

        # Estratégia 5: página de resultado após Liquidar — varrer links de download
        self._page.wait_for_timeout(4000)
        for txt in ["Exportar", "Download", "Baixar .pjc", "Baixar", "Salvar .PJC", "Salvar"]:
            try:
                with self._page.expect_download(timeout=30000) as dl_info:
                    if self._clicar_botao(txt, obrigatorio=False):
                        return _salvar_download(dl_info.value)
            except Exception:
                continue

        # Estratégia 6: procurar href de download diretamente no DOM
        try:
            href = self._page.evaluate("""() => {
                const links = [...document.querySelectorAll('a[href]')];
                const pjc = links.find(a =>
                    a.href.includes('.pjc') || a.href.includes('exportar') ||
                    a.textContent.toLowerCase().includes('exportar') ||
                    a.textContent.toLowerCase().includes('download')
                );
                return pjc ? pjc.href : null;
            }""")
            if href:
                with self._page.expect_download(timeout=30000) as dl_info:
                    self._page.goto(href)
                return _salvar_download(dl_info.value)
        except Exception:
            pass

        self._log(
            "  ⚠ .PJC não capturado via browser — automação concluiu o preenchimento. "
            "O arquivo .PJC gerado pelo gerador nativo estará disponível para download."
        )
        return None

    # ── Orquestrador principal ─────────────────────────────────────────────────

    def preencher_calculo(
        self,
        dados: dict,
        verbas_mapeadas: dict,
        parametrizacao: dict | None = None,
    ) -> None:
        """Executa todas as fases de preenchimento do cálculo.

        Args:
            dados: output da extraction.py (dados brutos da sentença).
            verbas_mapeadas: output da classification.py.
            parametrizacao: output de parametrizacao.gerar_parametrizacao() — opcional.
                           Se presente, instrui fases específicas com dados pré-calculados.
        """
        base = f"{self.PJECALC_BASE}/pages/principal.jsf"
        self._log("Abrindo PJE-Calc…")
        self._page.goto(base, wait_until="domcontentloaded", timeout=60000)
        self._page.wait_for_timeout(2000)

        # Trata erro de primeira carga (comportamento conhecido do PJe-Calc)
        try:
            body = self._page.locator("body").text_content() or ""
            if "Erro interno" in body or "erro interno" in body.lower():
                self._log("Erro interno na primeira carga — navegando para Página Inicial…")
                link = self._page.locator("a:has-text('Página Inicial')")
                if link.count() > 0:
                    link.first.click()
                    self._aguardar_ajax()
        except Exception:
            pass

        # Instala monitor AJAX JSF
        try:
            self._instalar_monitor_ajax()
        except Exception:
            pass

        self._verificar_e_fazer_login()

        self._ir_para_novo_calculo()

        self.fase_dados_processo(dados)
        self._screenshot_fase("01_dados_processo")

        # Parâmetros Gerais — usa passo_2 do parametrizacao.json se disponível
        params_gerais = (parametrizacao or {}).get("passo_2_parametros_gerais", {})
        if not params_gerais:
            cont = dados.get("contrato", {})
            params_gerais = {
                "carga_horaria_diaria": cont.get("carga_horaria"),
                "zerar_valores_negativos": True,
            }
        self.fase_parametros_gerais(params_gerais)
        self._screenshot_fase("02a_parametros_gerais")

        self.fase_historico_salarial(dados)
        self._screenshot_fase("02_historico_salarial")

        self.fase_verbas(verbas_mapeadas)
        self._screenshot_fase("03_verbas")

        self.fase_fgts(dados.get("fgts", {}))
        self._screenshot_fase("04_fgts")

        self.fase_contribuicao_social(dados.get("contribuicao_social", {}))
        self._screenshot_fase("05_contribuicao_social")

        self.fase_cartao_ponto(dados)
        self._screenshot_fase("06_cartao_ponto")

        self.fase_parametros_atualizacao(dados.get("correcao_juros", {}))
        self._screenshot_fase("07_correcao_juros")

        self.fase_irpf(dados.get("imposto_renda", {}))
        self._screenshot_fase("08_irpf")

        self.fase_honorarios(
            dados.get("honorarios", []),
            periciais=dados.get("honorarios_periciais"),
        )
        self._screenshot_fase("09_honorarios")

        caminho_pjc = self._clicar_liquidar()
        if caminho_pjc:
            self._log("CONCLUIDO: Automação concluída — .PJC gerado e disponível para download.")
        else:
            # Preenchimento completo, mas download via browser não capturado.
            # O gerador nativo (pjc_generator.py) já gerou o .PJC na etapa de confirmação.
            self._log(
                "CONCLUIDO: Campos preenchidos automaticamente. "
                ".PJC do gerador nativo disponível para download na interface."
            )
        self._log("[FIM DA EXECUÇÃO]")


# ── Funções públicas ───────────────────────────────────────────────────────────

def iniciar_e_preencher(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
    pjecalc_dir: str | Path,
    log_cb: Callable[[str], None] | None = None,
    headless: bool = False,
    parametrizacao: dict | None = None,
) -> None:
    """
    Ponto de entrada público (modo callback).
    1. Inicia PJE-Calc Cidadão (se não estiver rodando), verificando TCP + HTTP.
    2. Abre Playwright browser.
    3. Preenche todos os campos do cálculo seguindo as 8 fases.
    """
    cb = log_cb or (lambda m: None)

    cb("Verificando PJE-Calc Cidadão…")
    iniciar_pjecalc(pjecalc_dir, log_cb=cb)
    cb("PJE-Calc disponível.")

    agente = PJECalcPlaywright(log_cb=cb)
    try:
        agente.iniciar_browser(headless=headless)
        agente.preencher_calculo(dados, verbas_mapeadas, parametrizacao=parametrizacao)
        # Browser permanece aberto para o usuário revisar e clicar Liquidar
    except Exception as exc:
        cb(f"ERRO: {exc}")
        logger.exception(f"Erro na automação Playwright: {exc}")
        raise


def preencher_como_generator(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
    pjecalc_dir: str | Path,
    modo_oculto: bool = False,
    parametrizacao: dict | None = None,
):
    """
    Generator que faz yield de mensagens de log para SSE streaming direto.
    Padrão CalcMachine: thread separada + queue.Queue como bridge.

    Uso:
        for msg in preencher_como_generator(dados, verbas, pjecalc_dir):
            # transmitir msg via SSE
    """
    import queue
    import threading

    log_queue: queue.Queue[str | None] = queue.Queue()

    def _cb(msg: str) -> None:
        log_queue.put(msg)

    def _run() -> None:
        try:
            iniciar_e_preencher(
                dados=dados,
                verbas_mapeadas=verbas_mapeadas,
                pjecalc_dir=pjecalc_dir,
                log_cb=_cb,
                headless=modo_oculto,
                parametrizacao=parametrizacao,
            )
        except Exception as exc:
            log_queue.put(f"ERRO: {exc}")
            logger.exception(f"Erro na automação (generator): {exc}")
        finally:
            log_queue.put(None)  # sentinela de fim

    threading.Thread(target=_run, daemon=True).start()

    while True:
        msg = log_queue.get()
        if msg is None:
            break
        yield msg

    yield "[FIM DA EXECUÇÃO]"
