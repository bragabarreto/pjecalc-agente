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
    Inicia o PJE-Calc Cidadão via iniciarPjeCalc.bat se não estiver rodando.
    Aguarda:
      1) porta TCP 9257 abrir
      2) HTTP http://localhost:9257/pjecalc responder com 200/302
    Emite mensagens de progresso via log_cb durante a espera.
    """
    _log = log_cb or (lambda m: None)
    dir_path = Path(pjecalc_dir)
    bat = dir_path / "iniciarPjeCalc.bat"
    if not bat.exists():
        raise FileNotFoundError(
            f"iniciarPjeCalc.bat não encontrado em {dir_path}. "
            "Verifique a configuração PJECALC_DIR."
        )

    if pjecalc_rodando():
        logger.info("PJE-Calc já está rodando em localhost:9257.")
        _log("PJE-Calc já está rodando. Aguardando Tomcat finalizar deploy…")
        _aguardar_http(timeout=60, log_cb=log_cb)
        return

    logger.info(f"Iniciando PJE-Calc Cidadão a partir de {dir_path}…")
    _log("Iniciando PJE-Calc Cidadão… (pode levar até 3 minutos)")
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        cwd=str(dir_path),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
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

        # Nível 2: sufixo de ID (tipo=input, select, ou qualquer)
        sufixo = field_id.split(":")[-1]  # extrai sufixo se vier com prefixo
        seletores = [
            f"[id$='{sufixo}_input']",   # RichFaces calendar
            f"[id$=':{sufixo}']",
            f"[id$='{sufixo}']",
        ]
        if tipo == "select":
            seletores = [f"select{s}" for s in seletores] + seletores
        elif tipo == "checkbox":
            seletores = [f"input[type='checkbox']{s}" for s in seletores] + seletores

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
        Preenche campo de data usando press_sequentially + Tab.
        Mais confiável para campos JSF/RichFaces com máscara de data.
        """
        if not data:
            return False
        loc = self._localizar(field_id, label, tipo="input")
        if not loc:
            self._log(f"  ⚠ data {field_id}: campo não encontrado — preencha manualmente.")
            return False
        try:
            loc.wait_for(state="visible", timeout=8000)
            loc.click()
            loc.fill("")
            loc.press_sequentially(data, delay=50)
            loc.dispatch_event("change")
            loc.press("Tab")
            self._aguardar_ajax()
            self._log(f"  ✓ data {field_id}: {data}")
            return True
        except Exception as e:
            self._log(f"  ⚠ data {field_id}: erro — {e}")
            return False

    def _selecionar(
        self,
        field_id: str,
        valor: str,
        label: str | None = None,
    ) -> bool:
        """Seleciona opção em <select> JSF por label (texto visível) ou value."""
        if not valor:
            return False
        loc = self._localizar(field_id, label, tipo="select")
        if not loc:
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

    def _clicar_menu_lateral(self, texto: str) -> None:
        """Clica em link do menu lateral. Se oculto, expande o nó pai antes."""
        self._page.wait_for_timeout(400)
        loc = self._page.locator(f"a:has-text('{texto}')")
        if loc.count() == 0:
            loc = self._page.get_by_role("link", name=texto)
        if loc.count() == 0:
            self._log(f"  ⚠ Menu '{texto}': link não encontrado.")
            return
        # Se invisível, tenta expandir o nó pai do menu RichFaces
        try:
            if not loc.first.is_visible():
                self._log(f"  → Menu '{texto}' oculto — expandindo nó pai…")
                pai = loc.first.locator(
                    "xpath=ancestor::*[contains(@class,'rich-tree-node') "
                    "or contains(@class,'menuGroup') "
                    "or contains(@class,'rich-tree-handle')][1]"
                )
                if pai.count() > 0 and pai.first.is_visible():
                    pai.first.click()
                    self._page.wait_for_timeout(600)
                else:
                    loc.first.hover(force=True)
                    self._page.wait_for_timeout(800)
                loc.first.wait_for(state="visible", timeout=5000)
        except Exception:
            pass
        try:
            loc.first.click()
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
        except Exception as e:
            self._log(f"  ⚠ Menu '{texto}': erro ao clicar — {e}")
            return
        # Fallback JavaScript
        self._page.evaluate(f"""
            const links = document.querySelectorAll('a');
            for (const a of links) {{
                if (a.textContent.trim().toLowerCase().includes('{texto.lower()}')) {{
                    a.click(); break;
                }}
            }}
        """)
        self._aguardar_ajax()
        self._log(f"  ⚠ Menu '{texto}': usado fallback JS")

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
        seletores = [
            "[id$='novo']",
            "input[value='Novo']",
            "button:has-text('Novo')",
            ".sprite-novo",
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

    # ── Navegação principal ────────────────────────────────────────────────────

    def _ir_para_calculo_externo(self) -> None:
        """Navega para a tela de Cálculo Externo via URL direta (mais confiável)."""
        self._log("Navegando para Cálculo Externo…")
        self._page.goto(
            f"{self.PJECALC_BASE}/pages/calculo/calculoExterno.jsf",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        self._aguardar_ajax()
        self._log("  ✓ Tela de Cálculo Externo carregada.")

    # ── Fase 1: Dados do Processo + Parâmetros ─────────────────────────────────

    @retry(max_tentativas=3)
    def fase_dados_processo(self, dados: dict) -> None:
        self._log("Fase 1 — Dados do processo…")
        self.mapear_campos("fase1_dados_processo")

        proc = dados.get("processo", {})
        cont = dados.get("contrato", {})
        pres = dados.get("prescricao", {})
        avp  = dados.get("aviso_previo", {})

        self._clicar_aba("tabDadosProcesso")
        self._page.wait_for_timeout(400)

        # Número do processo
        num = _parsear_numero_processo(proc.get("numero"))
        if num:
            self._preencher("numero", num.get("numero", ""), False)
            self._preencher("digito", num.get("digito", ""), False)
            self._preencher("ano", num.get("ano", ""), False)
            self._preencher("justica", num.get("justica", ""), False)
            self._preencher("regiao", num.get("regiao", ""), False)
            self._preencher("vara", num.get("vara", ""), False)

        if proc.get("reclamante"):
            self._preencher("reclamanteNome", proc["reclamante"], False)
        if proc.get("reclamado"):
            self._preencher("reclamadoNome", proc["reclamado"], False)

        if proc.get("cpf_reclamante"):
            self._marcar_radio("documentoFiscalReclamante", "CPF")
            self._preencher("reclamanteNumeroDocumentoFiscal", proc["cpf_reclamante"], False)
        if proc.get("cnpj_reclamado"):
            self._marcar_radio("tipoDocumentoFiscalReclamado", "CNPJ")
            self._preencher("reclamadoNumeroDocumentoFiscal", proc["cnpj_reclamado"], False)

        # Aba Parâmetros do Cálculo
        self._log("  → Aba Parâmetros do Cálculo…")
        self._clicar_aba("tabParametrosCalculo")
        self._page.wait_for_timeout(400)
        self.mapear_campos("fase1_parametros")

        if cont.get("admissao"):
            self._preencher_data("dataAdmissao", cont["admissao"], label="Data de Admissão")
        if cont.get("demissao"):
            self._preencher_data("dataDemissao", cont["demissao"], label="Data de Demissão")
        if cont.get("ajuizamento"):
            self._preencher_data("dataAjuizamento", cont["ajuizamento"], label="Data de Ajuizamento")

        if cont.get("ultima_remuneracao"):
            self._preencher(
                "valorUltimaRemuneracao",
                _fmt_br(cont["ultima_remuneracao"]),
                label="Última Remuneração",
            )
        if cont.get("maior_remuneracao"):
            self._preencher(
                "valorMaiorRemuneracao",
                _fmt_br(cont["maior_remuneracao"]),
                False,
            )
        if cont.get("carga_horaria"):
            self._preencher("valorCargaHorariaPadrao", str(cont["carga_horaria"]), False)

        regime_map = {
            "Tempo Integral": "INTEGRAL",
            "Tempo Parcial": "PARCIAL",
            "Trabalho Intermitente": "INTERMITENTE",
        }
        regime = regime_map.get(cont.get("regime", "Tempo Integral"), "INTEGRAL")
        self._selecionar("regimeDoContrato", regime, label="Regime do Contrato")

        if pres.get("quinquenal") is not None:
            self._marcar_checkbox("prescricaoQuinquenal", bool(pres["quinquenal"]))
        if pres.get("fgts") is not None:
            self._marcar_checkbox("prescricaoFgts", bool(pres["fgts"]))

        tipo_ap = avp.get("tipo", "Calculado")
        self._selecionar("apuracaoPrazoDoAvisoPrevio", tipo_ap)
        if tipo_ap == "Informado" and avp.get("prazo_dias"):
            self._preencher("prazoAvisoInformado", str(avp["prazo_dias"]), False)
        if avp.get("projetar"):
            self._marcar_checkbox("projetaAvisoIndenizado", True)

        self._clicar_salvar()
        self._log("Fase 1 concluída.")

    # ── Fase 2: Histórico Salarial ─────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_historico_salarial(self, dados: dict) -> None:
        self._log("Fase 2 — Histórico salarial…")
        hist_lista = dados.get("historico_salarial") or []

        if not hist_lista:
            cont = dados.get("contrato", {})
            sal = cont.get("ultima_remuneracao") or cont.get("maior_remuneracao")
            adm = cont.get("admissao")
            dem = cont.get("demissao")
            if sal and adm:
                hist_lista = [{
                    "nome": "BASE DE CÁLCULO",
                    "valor": sal,
                    "data_inicio": adm,
                    "data_fim": dem or adm,
                }]

        if not hist_lista:
            self._log("  Sem histórico salarial — fase ignorada.")
            return

        self._clicar_menu_lateral("Histórico Salarial")
        self.mapear_campos("fase2_historico")

        for h in hist_lista:
            self._clicar_novo()
            self._preencher("nome", h.get("nome") or "BASE DE CÁLCULO")
            self._marcar_radio("tipoVariacaoDaParcela", "MONETARIO")
            self._preencher("valorParaBaseDeCalculo", _fmt_br(h.get("valor", 0)))
            if h.get("data_inicio"):
                self._preencher_data("competenciaInicial", h["data_inicio"])
            if h.get("data_fim"):
                self._preencher_data("competenciaFinal", h["data_fim"])
            self._marcar_checkbox("incidenciaFGTS", True)
            self._marcar_checkbox("incidenciaINSS", True)
            self._clicar_salvar()

        self._log("Fase 2 concluída.")

    # ── Fase 3: Verbas ─────────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_verbas(self, verbas_mapeadas: dict) -> None:
        self._log("Fase 3 — Verbas…")
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

        for v in todas:
            self._clicar_novo()
            nome = v.get("nome_pjecalc") or v.get("nome_sentenca") or "Verba"
            self._preencher("descricao", nome)
            carac = carac_map.get(v.get("caracteristica", "Comum"), "COMUM")
            self._selecionar("caracteristicaVerba", carac)
            ocorr = ocorr_map.get(v.get("ocorrencia", "Mensal"), "MENSAL")
            self._selecionar("ocorrenciaPagto", ocorr)

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
            if v.get("periodo_fim"):
                self._preencher_data("periodoFinal", v["periodo_fim"], False)

            self._clicar_salvar()
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
        self._clicar_menu_lateral("FGTS")
        self.mapear_campos("fase4_fgts")

        aliquota = fgts.get("aliquota", 0.08)
        pct = round(float(aliquota) * 100) if float(aliquota) <= 1 else round(float(aliquota))
        self._page.evaluate(f"""
            const tds = document.querySelectorAll('td');
            for (const td of tds) {{
                if (td.textContent.trim() === '{pct}%') {{ td.click(); break; }}
            }}
        """)
        self._aguardar_ajax(3000)

        if fgts.get("multa_40"):
            self._marcar_checkbox("multa", True)
        if fgts.get("multa_467"):
            self._marcar_checkbox("multaDoArtigo467", True)

        self._clicar_salvar()
        self._log("Fase 4 concluída.")

    # ── Fase 5: Contribuição Social (INSS) ────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_contribuicao_social(self, cs: dict) -> None:
        self._log("Fase 5 — Contribuição Social…")
        self._clicar_menu_lateral("Contribuição Social")
        self.mapear_campos("fase5_inss")

        resp_map = {"Empregado": "EMPREGADO", "Empregador": "EMPREGADOR", "Ambos": "AMBOS"}
        resp = resp_map.get(cs.get("responsabilidade", "Ambos"), "AMBOS")
        self._selecionar("responsabilidade", resp)

        if cs.get("lei_11941"):
            self._marcar_checkbox("lei11941", True)

        self._clicar_salvar()
        self._log("Fase 5 concluída.")

    # ── Fase 6: Parâmetros de Atualização ─────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_parametros_atualizacao(self, cj: dict) -> None:
        self._log("Fase 6 — Parâmetros de atualização…")
        self._clicar_menu_lateral("Parâmetros de Atualização")
        self.mapear_campos("fase6_correcao")

        indice_map = {
            "Tabela JT Única Mensal": "IPCAE",
            "IPCA-E": "IPCAE",
            "Selic": "SELIC",
            "TRCT": "TRCT",
            "TR": "TRD",
        }
        indice = indice_map.get(cj.get("indice_correcao", ""), "IPCAE")
        self._selecionar("indiceTrabalhista", indice)

        juros_map = {"Selic": "SELIC", "Juros Padrão": "TRD_SIMPLES"}
        juros = juros_map.get(cj.get("taxa_juros", ""), "TRD_SIMPLES")
        self._selecionar("juros", juros)

        base_map = {"Verbas": "VERBA_INSS", "Credito Total": "CREDITO_TOTAL"}
        base = base_map.get(cj.get("base_juros", "Verbas"), "VERBA_INSS")
        self._selecionar("baseDeJurosDasVerbas", base)

        self._clicar_salvar()
        self._log("Fase 6 concluída.")

    # ── Fase 7: IRPF ──────────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_irpf(self, ir: dict) -> None:
        if not ir.get("apurar"):
            self._log("Fase 7 — IRPF ignorado (não apurar).")
            return

        self._log("Fase 7 — IRPF…")
        self._clicar_menu_lateral("Imposto de Renda")
        self.mapear_campos("fase7_irpf")
        self._marcar_checkbox("apurarImpostoRenda", True)

        if ir.get("meses_tributaveis"):
            self._preencher("qtdMesesRendimento", str(ir["meses_tributaveis"]), False)
        if ir.get("dependentes"):
            self._marcar_checkbox("possuiDependentes", True)
            self._preencher("quantidadeDependentes", str(ir["dependentes"]), False)

        self._clicar_salvar()
        self._log("Fase 7 concluída.")

    # ── Fase 8: Honorários ────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_honorarios(self, hon: dict) -> None:
        if not hon.get("percentual") and not hon.get("valor_fixo") and not hon.get("periciais"):
            self._log("Fase 8 — Honorários ignorados (sem dados).")
            return

        self._log("Fase 8 — Honorários…")
        self._clicar_menu_lateral("Honorários")
        self.mapear_campos("fase8_honorarios")
        self._clicar_novo()

        self._selecionar("tpHonorario", "ADVOCATICIOS")
        self._preencher("descricao", "HONORÁRIOS ADVOCATÍCIOS", False)

        devedor_map = {"Reclamado": "RECLAMADO", "Reclamante": "RECLAMANTE", "Ambos": "AMBOS"}
        devedor = devedor_map.get(hon.get("parte_devedora", "Reclamado"), "RECLAMADO")
        self._marcar_radio("tipoDeDevedor", devedor)

        if hon.get("valor_fixo"):
            self._marcar_radio("tipoValor", "INFORMADO")
            self._preencher("valor", _fmt_br(hon["valor_fixo"]), False)
        elif hon.get("percentual"):
            self._marcar_radio("tipoValor", "CALCULADO")
            pct = round(hon["percentual"] * 100, 2)
            self._preencher("aliquota", str(pct), False)

        self._clicar_salvar()
        self._log("Fase 8 concluída.")

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

        self._log("CONCLUIDO: Todas as fases preenchidas. Revise e clique em Liquidar.")


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
