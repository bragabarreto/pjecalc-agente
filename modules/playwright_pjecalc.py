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

# ── Decorator de retry ────────────────────────────────────────────────────────

def retry(max_tentativas: int = 3, delay: int = 2):
    """Retry automático com screenshot em falha e detecção de ViewExpiredException."""
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
    """Retorna True se o Tomcat do PJE-Calc já está ouvindo na porta 9257."""
    try:
        s = socket.create_connection(("127.0.0.1", 9257), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def iniciar_pjecalc(pjecalc_dir: str | Path, timeout: int = 180, log_cb=None) -> None:
    """
    Inicia o PJE-Calc Cidadão via iniciarPjeCalc.bat (Windows) ou iniciarPjeCalc.sh (Linux).
    Aguarda:
      1) porta TCP 9257 abrir
      2) HTTP http://localhost:9257/pjecalc responder com 200/302
    Emite mensagens de progresso via log_cb durante a espera.
    """
    import platform
    _log = log_cb or (lambda m: None)
    dir_path = Path(pjecalc_dir)

    if pjecalc_rodando():
        logger.info("PJE-Calc já está rodando em localhost:9257.")
        _log("PJE-Calc já está rodando. Aguardando Tomcat finalizar deploy…")
        _aguardar_http(timeout=60, log_cb=log_cb)
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
            logger.info("PJE-Calc: porta TCP 9257 aberta.")
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


def _aguardar_http(timeout: int = 60, log_cb=None) -> None:
    """Aguarda http://localhost:9257/pjecalc responder. Emite progresso via log_cb."""
    url = "http://localhost:9257/pjecalc"
    inicio = time.time()
    ultimo_log = -10  # força log imediato no primeiro ciclo
    while time.time() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status in (200, 302):
                    logger.info("PJE-Calc HTTP respondendo — pronto.")
                    if log_cb:
                        log_cb("PJE-Calc pronto.")
                    time.sleep(2)  # margem para finalizar deploy Seam/JSF
                    return
        except Exception:
            pass
        elapsed = int(time.time() - inicio)
        if log_cb and elapsed - ultimo_log >= 10:
            log_cb(f"⏳ Aguardando PJE-Calc inicializar… ({elapsed}s)")
            ultimo_log = elapsed
        time.sleep(3)
    raise TimeoutError(f"PJE-Calc: porta aberta mas HTTP não respondeu em {timeout}s.")


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

    PJECALC_BASE = "http://localhost:9257/pjecalc"
    LOG_DIR = Path("data/logs")

    def __init__(self, log_cb: Callable[[str], None] | None = None):
        self._log_cb = log_cb or (lambda msg: None)
        self._pw = None
        self._browser = None
        self._page = None

    # ── Ciclo de vida ──────────────────────────────────────────────────────────

    def iniciar_browser(self, headless: bool = False) -> None:
        import os, sys
        # Em Linux sem display real (Railway/Docker), forçar headless
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            headless = True
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(
            headless=headless,
            slow_mo=0 if headless else 150,
            args=[] if headless else ["--start-maximized"],
        )
        ctx = self._browser.new_context(
            no_viewport=True,
            locale="pt-BR",
        )
        self._page = ctx.new_page()
        self._page.set_default_timeout(30000)

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
                campos.push({
                    id: el.id,
                    name: el.name || '',
                    type: el.type || el.tagName.toLowerCase(),
                    tag: el.tagName.toLowerCase(),
                    label: lbl ? lbl.textContent.trim() : '',
                    visible: el.offsetParent !== null,
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
        # elementos errados (ex: <table class="rich-calendar-exterior"> ou <li>).
        # Sem fallback sem prefixo aqui — o Nível 3 (XPath) cobre os edge cases.
        sufixo = field_id.split(":")[-1]  # extrai sufixo se vier com prefixo
        seletores_base = [
            f"[id$='{sufixo}_input']",   # RichFaces 4.x: <input id="..._input">
            f"[id$=':{sufixo}']",
            f"[id$='{sufixo}']",
        ]
        if tipo == "select":
            seletores = [f"select{s}" for s in seletores_base]
        elif tipo == "checkbox":
            seletores = [f"input[type='checkbox']{s}" for s in seletores_base]
        elif tipo == "input":
            # Prefixar com "input" evita match em <table id="...:dataAdmissao">
            # (popup oculto do RichFaces Calendar) que causava timeout no wait_for(visible)
            seletores = [f"input{s}" for s in seletores_base]
        else:
            seletores = seletores_base

        for sel in seletores:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    return loc.first
            except Exception:
                continue

        # Nível 3: XPath contains(@id)
        xpath_map = {
            "input":    f"//input[contains(@id, '{sufixo}')]",
            "select":   f"//select[contains(@id, '{sufixo}')]",
            "checkbox": f"//input[@type='checkbox' and contains(@id, '{sufixo}')]",
        }
        xpath = xpath_map.get(tipo, f"//*[contains(@id, '{sufixo}')]")
        try:
            loc = self._page.locator(xpath)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass

        # Nível 4: ID completo com dois-pontos escapados
        escaped = field_id.replace(":", "\\:")
        try:
            loc = self._page.locator(f"#{escaped}")
            if loc.count() > 0:
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
            loc.dispatch_event("blur")
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
            self._log(f"  ⚠ data {field_id}: campo não encontrado — preencha manualmente.")
            return False
        try:
            loc.wait_for(state="visible", timeout=8000)
            # focus() em vez de click() — evita abrir calendar popup (RichFaces)
            loc.focus()
            loc.evaluate("el => { el.value = ''; }")
            loc.press_sequentially(data, delay=50)
            loc.dispatch_event("input")
            loc.dispatch_event("change")
            loc.press("Tab")
            self._aguardar_ajax()
            self._log(f"  ✓ data {field_id}: {data}")
            return True
        except Exception as e:
            # Fallback: setar valor diretamente via JS (ignora máscara mas garante preenchimento)
            try:
                loc.evaluate(
                    f"el => {{ el.value = '{data}'; "
                    "el.dispatchEvent(new Event('input',{bubbles:true})); "
                    "el.dispatchEvent(new Event('change',{bubbles:true})); "
                    "el.dispatchEvent(new Event('blur',{bubbles:true})); }"
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

    def _marcar_radio(self, field_id: str, valor: str) -> bool:
        """Clica em radio button JSF."""
        seletores = [
            f"input[type='radio'][value='{valor}'][id$='{field_id}']",
            f"table[id$='{field_id}'] input[value='{valor}']",
            f"input[type='radio'][name$='{field_id}'][value='{valor}']",
            f"//input[@type='radio' and @value='{valor}' and contains(@id, '{field_id}')]",
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
        self._page.wait_for_timeout(400)
        # Método primário: JS click — bypassa visibilidade, funciona em menus colapsados
        clicou = self._page.evaluate(
            """(texto) => {
                const links = [...document.querySelectorAll('a')];
                const el = links.find(a =>
                    a.textContent.replace(/\s+/g, ' ').trim().includes(texto)
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

    def _clicar_salvar(self) -> None:
        seletores = [
            "[id$='salvar']",
            "input[value='Salvar']",
            "button:has-text('Salvar')",
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
        self._log("  ⚠ Botão Salvar não encontrado — clique manualmente.")

    def _clicar_novo(self) -> None:
        """Clica no botão Novo — busca exata por texto 'Novo'."""
        # Método 1: seletores CSS conhecidos
        for sel in ["[id$='novo']", "[id$='novoBt']", "[id$='novoBtn']",
                    "input[value='Novo']", "button:has-text('Novo')"]:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    loc.first.click(); self._aguardar_ajax()
                    self._page.wait_for_timeout(800); return
            except Exception:
                continue

        # Método 2: ARIA role (mais confiável para <a> com texto exato)
        try:
            loc = self._page.get_by_role("link", name="Novo", exact=True)
            if loc.count() > 0:
                loc.first.click(); self._aguardar_ajax()
                self._page.wait_for_timeout(800); return
        except Exception:
            pass

        # Método 3: JS sem filtro de menu, com normalização de \u00a0
        clicou = self._page.evaluate("""() => {
            const todos = [...document.querySelectorAll(
                'a, input[type="submit"], input[type="button"], button')];
            for (const el of todos) {
                const txt = (el.textContent || el.value || el.title || '')
                    .replace(/[\\s\\u00a0]+/g,' ').trim();
                if (txt === 'Novo' || txt === 'Nova') { el.click(); return true; }
            }
            return false;
        }""")
        if clicou:
            self._aguardar_ajax(); self._page.wait_for_timeout(800); return

        # Diagnóstico
        self._log("  ⚠ Botão Novo não encontrado — elementos clicáveis na página:")
        try:
            items = self._page.evaluate("""() => {
                return [...document.querySelectorAll('a, input[type="submit"], button')]
                    .map(el => el.id + ' | ' + (el.textContent||el.value||'').trim())
                    .filter(s => s.length > 3 && s.length < 80);
            }""")
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
        """Verifica se está logado; se não, tenta credenciais padrão."""
        url = self._page.url
        if "logon" not in url.lower():
            return

        self._log("Página de login detectada — tentando credenciais padrão…")
        for usuario, senha in [
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

        self._aguardar_usuario(
            "Faça o login no PJE-Calc e clique em <strong>Continuar</strong>."
        )

    # ── Verificações de saúde (Tomcat + página) ────────────────────────────────

    def _verificar_tomcat(self, timeout: int = 120) -> bool:
        """Aguarda o Tomcat responder antes de prosseguir. Loga progresso a cada 15s."""
        url = "http://localhost:9257/pjecalc"
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

    def _ir_para_calculo_externo(self) -> None:
        """Navega para o formulário de Novo Cálculo via menu 'Novo'.

        Usa o fluxo 'Novo' (primeira liquidação de sentença), NÃO 'Cálculo Externo'
        (que serve apenas para atualizar cálculos existentes).
        Navegação via clique no menu — URL direta causa ViewState inválido no JSF.
        """
        self._log("Navegando para Novo Cálculo via menu…")

        self._clicar_menu_lateral("Novo")
        self._page.wait_for_timeout(1200)

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
                self._page.wait_for_timeout(1200)
        except Exception:
            pass

        self._log("  ✓ Formulário de Novo Cálculo aberto.")

    # ── Fase 1: Dados do Processo + Parâmetros ─────────────────────────────────

    @retry(max_tentativas=3)
    def fase_dados_processo(self, dados: dict) -> None:
        import datetime
        self._log("Fase 1 — Dados do processo…")
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

        self._clicar_salvar()
        self._log("Fase 1 concluída.")

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
        if not navegou:
            self._log("  ⚠ Histórico Salarial não disponível no menu — listando para referência:")
            for h in historico:
                self._log(f"    {h.get('data_inicio','')} a {h.get('data_fim','')} — R$ {h.get('valor','')}")
            return
        self.mapear_campos("fase2_historico_salarial")
        for h in historico:
            self._clicar_novo()
            try:
                self._page.wait_for_selector(
                    "[id$='dataInicio'], [id$='dataInicial'], [name*='dataInicio']",
                    state="visible", timeout=6000
                )
            except Exception:
                self._page.wait_for_timeout(1000)
            self._preencher_data("dataInicio", h.get("data_inicio", ""), False)
            self._preencher_data("dataFim", h.get("data_fim", ""), False)
            # Tentar também nomes alternativos de campo
            self._preencher_data("dataInicial", h.get("data_inicio", ""), False)
            self._preencher_data("dataFinal", h.get("data_fim", ""), False)
            self._preencher("salario", _fmt_br(h.get("valor", "")), False)
            self._preencher("valor", _fmt_br(h.get("valor", "")), False)
            self._clicar_salvar()
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            try:
                self._page.wait_for_selector(
                    "[id$='filtroNome'], [id$='dataInicio'], [name*='filtroNome']",
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
        self.mapear_campos("fase3_verbas")

        todas = (
            verbas_mapeadas.get("predefinidas", [])
            + verbas_mapeadas.get("personalizadas", [])
        )

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

        for i, v in enumerate(todas):
            self._clicar_novo()
            # Aguardar formulário de verba — tentar múltiplos seletores conhecidos
            _form_abriu = False
            for _sel_form in [
                "input[id$='descricao'], input[id$='nome'], input[id$='nomeVerba']",
                "[id$='descricao'], [id$='nome'], [id$='nomeVerba']",
                "input[name*='descricao'], input[name*='nome']",
            ]:
                try:
                    self._page.wait_for_selector(_sel_form, state="visible", timeout=4000)
                    _form_abriu = True
                    break
                except Exception:
                    continue

            if not _form_abriu:
                self._log("  ⚠ Formulário de verba não apareceu — aguardando mais…")
                # Dump de todos os campos da página para diagnóstico (visível no SSE log)
                try:
                    ids_pg = self._page.evaluate("""() =>
                        [...document.querySelectorAll('input,select,textarea')]
                        .map(e => (e.id||e.name||'?') + '|' + e.type)
                        .filter(s => s.length > 3 && !s.startsWith('hidden'))
                    """)
                    self._log(f"  📋 Campos na página agora: {ids_pg[:25]}")
                except Exception:
                    pass
                try:
                    self._page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    self._page.wait_for_timeout(1000)

            if i == 0:
                self.mapear_campos("verba_form")  # captura IDs reais após abrir formulário
            nome = v.get("nome_pjecalc") or v.get("nome_sentenca") or "Verba"

            # Tentar múltiplos IDs para campo de descrição da verba
            _desc_ok = any(
                self._preencher(fid, nome, obrigatorio=False)
                for fid in ["descricao", "nome", "nomeVerba", "titulo", "descricaoVerba", "verba"]
            )
            if not _desc_ok:
                self._log(f"  ⚠ Campo de descrição não encontrado para: {nome}")

            carac = carac_map.get(v.get("caracteristica", "Comum"), "COMUM")
            # Tentar múltiplos IDs para select de característica
            any(self._selecionar(fid, carac, obrigatorio=False)
                for fid in ["caracteristicaVerba", "caracteristica", "tipoVerba", "tipo"])

            ocorr = ocorr_map.get(v.get("ocorrencia", "Mensal"), "MENSAL")
            # Tentar múltiplos IDs para select de ocorrência
            any(self._selecionar(fid, ocorr, obrigatorio=False)
                for fid in ["ocorrenciaPagto", "ocorrencia", "periodicidade", "frequencia"])

            if v.get("valor_informado"):
                self._marcar_radio("valor", "INFORMADO")
                self._preencher("valorDevidoInformado", _fmt_br(v["valor_informado"]), False)
            else:
                self._marcar_radio("valor", "CALCULADO")

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
            # Após salvar, garantir retorno à lista de verbas
            try:
                self._page.wait_for_selector(
                    "[id$='filtroNome'], [name*='filtroNome']",
                    state="visible", timeout=4000
                )
            except Exception:
                self._clicar_menu_lateral("Verbas")
                self._page.wait_for_timeout(800)
            self._log(f"  ✓ Verba: {nome}")

        nao_rec = verbas_mapeadas.get("nao_reconhecidas", [])
        if nao_rec:
            nomes = ", ".join(v.get("nome_sentenca", "?") for v in nao_rec)
            self._aguardar_usuario(
                f"As verbas <strong>{nomes}</strong> não foram mapeadas. "
                "Adicione-as manualmente e clique em <strong>Continuar</strong>."
            )

        self._log("Fase 3 concluída.")

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
        if not navegou:
            self._log("  → Seção FGTS não encontrada no menu — incidência já configurada por verba.")
            return
        self.mapear_campos("fase4_fgts")
        # Alíquota FGTS (padrão 8%)
        aliquota = fgts.get("aliquota", 0.08)
        self._preencher("aliquotaFgts", _fmt_br(aliquota * 100), False)
        self._preencher("percentualFgts", _fmt_br(aliquota * 100), False)
        self._preencher("aliquota", _fmt_br(aliquota * 100), False)
        # Multas
        self._marcar_checkbox("multa40", bool(fgts.get("multa_40", True)))
        self._marcar_checkbox("multaFgts40", bool(fgts.get("multa_40", True)))
        self._marcar_checkbox("multa467", bool(fgts.get("multa_467", False)))
        self._marcar_checkbox("multaFgts467", bool(fgts.get("multa_467", False)))
        self._clicar_salvar()
        self._log("Fase 4 concluída.")

    # ── Fase 5: Contribuição Social (INSS) ────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_contribuicao_social(self, cs: dict) -> None:
        self._log("Fase 5 — Contribuição Social…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        self._clicar_menu_lateral("Contribuição Social")
        self.mapear_campos("fase5_inss")
        # No Cálculo Externo os campos são automáticos — tentar preencher se existirem
        resp_map = {"Empregado": "EMPREGADO", "Empregador": "EMPREGADOR", "Ambos": "AMBOS"}
        resp = resp_map.get(cs.get("responsabilidade", "Ambos"), "AMBOS")
        self._selecionar("responsabilidade", resp, obrigatorio=False)
        if cs.get("lei_11941"):
            self._marcar_checkbox("lei11941", True)
        # Salvar apenas se o botão existir
        sels = ["[id$='salvar']", "input[value='Salvar']", "button:has-text('Salvar')"]
        for sel in sels:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    loc.first.click(); self._aguardar_ajax(); break
            except Exception:
                continue
        self._log("Fase 5 concluída.")

    # ── Fase 6: Parâmetros de Atualização ─────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_parametros_atualizacao(self, cj: dict) -> None:
        self._log("Fase 6 — Parâmetros de atualização (preenchidos na Fase 1 — ignorado).")

    # ── Fase 7: IRPF ──────────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_irpf(self, ir: dict) -> None:
        self._log("Fase 7 — IRPF (preenchido na Fase 1 — ignorado).")

    # ── Fase 8: Honorários ────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_honorarios(self, hon: dict) -> None:
        self._log("Fase 8 — Honorários…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        navegou = self._clicar_menu_lateral("Honorários", obrigatorio=False)
        if not navegou:
            navegou = self._clicar_menu_lateral("Honorarios", obrigatorio=False)
        if not navegou:
            self._log("  → Seção Honorários não encontrada no menu — ignorado.")
            return
        self.mapear_campos("fase8_honorarios")
        if hon.get("percentual"):
            # percentual vem como float (ex: 0.15) → exibir como "15" para o PJE-Calc
            self._preencher("percentualHonorarios", _fmt_br(hon["percentual"] * 100), False)
            self._preencher("percentual", _fmt_br(hon["percentual"] * 100), False)
        if hon.get("valor_fixo"):
            self._preencher("valorFixoHonorarios", _fmt_br(hon["valor_fixo"]), False)
            self._preencher("valorFixo", _fmt_br(hon["valor_fixo"]), False)
        if hon.get("periciais"):
            self._preencher("honorariosPericiais", _fmt_br(hon["periciais"]), False)
            self._preencher("valorPericiais", _fmt_br(hon["periciais"]), False)
        parte_map = {"Reclamado": "RECLAMADO", "Reclamante": "RECLAMANTE", "Ambos": "AMBOS"}
        if hon.get("parte_devedora"):
            self._selecionar("parteDevedora", parte_map.get(hon["parte_devedora"], "RECLAMADO"), obrigatorio=False)
            self._selecionar("responsabilidadeHonorarios", parte_map.get(hon["parte_devedora"], "RECLAMADO"), obrigatorio=False)
        self._clicar_salvar()
        self._log("Fase 8 concluída.")

    # ── Liquidar / captura do .PJC ─────────────────────────────────────────────

    def _clicar_liquidar(self) -> str | None:
        """Clica Liquidar, aguarda geração e captura o arquivo .PJC gerado."""
        self._log("Clicando Liquidar para gerar o .PJC…")
        from config import OUTPUT_DIR
        out_dir = Path(OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Localizar botão Liquidar
        liq_sels = [
            "[id$='liquidar']", "[id$='liquidarBt']",
            "input[value='Liquidar']", "a:has-text('Liquidar')",
            "button:has-text('Liquidar')",
        ]
        loc = None
        for sel in liq_sels:
            try:
                candidate = self._page.locator(sel)
                if candidate.count() > 0:
                    loc = candidate.first; break
            except Exception:
                continue

        if loc is None:
            # Fallback JS
            self._page.evaluate("""() => {
                const all = [...document.querySelectorAll('a, input[type="submit"], button')];
                for (const el of all) {
                    const txt = (el.textContent||el.value||'').replace(/[\\s\\u00a0]+/g,' ').trim();
                    if (txt.includes('Liquidar')) { el.click(); return; }
                }
            }""")
            self._aguardar_ajax(60000)
        else:
            try:
                with self._page.expect_download(timeout=120000) as dl_info:
                    loc.click()
                d = dl_info.value
                dest = out_dir / d.suggested_filename
                d.save_as(str(dest))
                self._log(f"PJC_GERADO:{dest}")
                return str(dest)
            except Exception as e:
                self._log(f"  ⚠ Download direto falhou ({e}) — procurando link de download…")
                loc.click()
                self._aguardar_ajax(60000)

        # Liquidar gerou página de resultado — procurar link de download do .PJC
        self._page.wait_for_timeout(3000)
        for txt in ["Exportar", "Download", "Baixar .pjc", "Salvar"]:
            try:
                with self._page.expect_download(timeout=30000) as dl_info:
                    if self._clicar_botao(txt, obrigatorio=False):
                        d = dl_info.value
                        dest = out_dir / d.suggested_filename
                        d.save_as(str(dest))
                        self._log(f"PJC_GERADO:{dest}")
                        return str(dest)
            except Exception:
                continue

        self._log("  ⚠ .PJC não capturado automaticamente. Baixe manualmente no PJE-Calc.")
        return None

    # ── Orquestrador principal ─────────────────────────────────────────────────

    def preencher_calculo(self, dados: dict, verbas_mapeadas: dict) -> None:
        """Executa todas as fases de preenchimento do cálculo."""
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

        self._ir_para_calculo_externo()

        self.fase_dados_processo(dados)
        self.fase_historico_salarial(dados)
        self.fase_verbas(verbas_mapeadas)
        self.fase_fgts(dados.get("fgts", {}))
        self.fase_contribuicao_social(dados.get("contribuicao_social", {}))
        self.fase_parametros_atualizacao(dados.get("correcao_juros", {}))
        self.fase_irpf(dados.get("imposto_renda", {}))
        self.fase_honorarios(dados.get("honorarios", {}))

        caminho_pjc = self._clicar_liquidar()
        if caminho_pjc:
            self._log("CONCLUIDO: .PJC gerado com sucesso. Disponível para download.")
        else:
            self._log("CONCLUIDO: Preencha manualmente e clique em Liquidar no PJE-Calc.")
        self._log("[FIM DA EXECUÇÃO]")


# ── Funções públicas ───────────────────────────────────────────────────────────

def iniciar_e_preencher(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
    pjecalc_dir: str | Path,
    log_cb: Callable[[str], None] | None = None,
    headless: bool = False,
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
        agente.preencher_calculo(dados, verbas_mapeadas)
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
