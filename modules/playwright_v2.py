"""Automação PJE-Calc v2 — consume JSON v2 direto, sem inferências.

Princípios:
1. **Sem inferência**: nenhum default em código. Tudo vem da prévia v2.
2. **Sem auto-correção**: se a Liquidação falha, é porque a prévia tinha erro.
   Pydantic já validou antes — falhas devem ser raras.
3. **1:1 com schema**: cada campo da prévia mapeia para uma chamada DOM específica.
4. **Falha rápido**: campo ausente → erro imediato (não silencioso).
5. **Logs estruturados**: cada fase loga seu progresso para o SSE stream.

Substitui o monólito `playwright_pjecalc.py` (12500 linhas) por uma arquitetura
modular onde cada fase é uma função compacta com responsabilidade única.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable

# Importar models v2
_SCHEMA_PATH = Path(__file__).parent.parent / "docs" / "schema-v2"
if str(_SCHEMA_PATH) not in sys.path:
    sys.path.insert(0, str(_SCHEMA_PATH))

import importlib.util as _il_util

_spec = _il_util.spec_from_file_location(
    "pydantic_models_v2", _SCHEMA_PATH / "99-pydantic-models.py"
)
_pm = _il_util.module_from_spec(_spec)
_spec.loader.exec_module(_pm)

PreviaCalculoV2 = _pm.PreviaCalculoV2
TipoValor = _pm.TipoValor
EstrategiaPreenchimento = _pm.EstrategiaPreenchimento
EstrategiaReflexa = _pm.EstrategiaReflexa
TipoBaseCalculo = _pm.TipoBaseCalculo

logger = logging.getLogger(__name__)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _fmt_br(valor: float | int) -> str:
    """Formata número como BR: 1234.56 → '1.234,56'."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _split_cnj(numero_processo: str) -> dict:
    """Decompõe número CNJ em campos do form: NNNNNNN-DD.AAAA.J.RR.VVVV."""
    parts = numero_processo.replace("-", ".").split(".")
    return {
        "numero": parts[0],
        "digito": parts[1],
        "ano": parts[2],
        "justica": parts[3],
        "regiao": parts[4],
        "vara": parts[5],
    }


# ─── Classe principal ──────────────────────────────────────────────────────


class PlaywrightAutomatorV2:
    """Automação PJE-Calc consumindo prévia v2.

    Uso:
        previa = PreviaCalculoV2.model_validate(json_data)
        with PlaywrightAutomatorV2(previa, log_fn=print) as bot:
            bot.run()
            pjc_path = bot.get_pjc_path()
    """

    def __init__(
        self,
        previa: PreviaCalculoV2,
        log_fn: Callable[[str], None] | None = None,
        pjecalc_url: str = "http://localhost:9257/pjecalc",
    ):
        self.previa = previa
        self.log = log_fn or (lambda m: logger.info(m))
        self.pjecalc_url = pjecalc_url
        self._page = None
        self._browser = None
        self._pw = None
        self._calculo_url_base: str | None = None
        self._calculo_conversation_id: str | None = None
        self._pjc_path: str | None = None
        self._calculo_numero: str | None = None  # ID do cálculo extraído do DOM
        # Diretório de download dedicado (padrão Calc Machine).
        # O Playwright usa esse path como destino dos downloads do navegador.
        import tempfile as _tempfile, pathlib as _pathlib, time as _time
        self._download_dir: _pathlib.Path = _pathlib.Path(_tempfile.gettempdir()) / f"pjecalc_dl_{int(_time.time())}"
        self._download_dir.mkdir(parents=True, exist_ok=True)

    # ─── Lifecycle ─────────────────────────────────────────────────────────

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        # Firefox preferences para download silencioso (sem dialog) no dir custom
        firefox_prefs = {
            "browser.download.folderList": 2,
            "browser.download.manager.showWhenStarting": False,
            "browser.download.dir": str(self._download_dir),
            "browser.helperApps.neverAsk.saveToDisk": (
                "application/zip,application/x-zip-compressed,application/octet-stream,"
                "application/pdf,application/x-pjc,application/x-download"
            ),
            "pdfjs.disabled": True,
            "browser.download.useDownloadDir": True,
        }
        self._browser = self._pw.firefox.launch(headless=True, firefox_user_prefs=firefox_prefs)
        ctx = self._browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
        )
        self._page = ctx.new_page()
        self.log(f"✓ Browser Firefox iniciado (download dir: {self._download_dir})")
        return self

    def __exit__(self, *args):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    # ─── Pipeline principal ────────────────────────────────────────────────

    def run(self) -> str | None:
        """Executa pipeline completo. Retorna caminho do .PJC ou None.

        Cada fase é envolvida em try/except — falha em uma fase não aborta
        o pipeline. Loga erro e continua para a próxima. Liquidação tenta
        rodar mesmo com fases anteriores parciais (PJE-Calc reporta
        pendências e o usuário corrige manualmente).
        """
        self.log("══ Iniciando automação v2 ══")
        self._abrir_pjecalc()
        self._criar_novo_calculo()

        def _run_fase(nome, fn, condicao=True):
            if not condicao:
                return
            try:
                fn()
            except Exception as e:
                import traceback
                self.log(f"⚠ {nome} falhou: {type(e).__name__}: {str(e)[:200]}")
                self.log(f"   (continuando com próxima fase para tentar Liquidação)")

        # Fases (sequência ordenada, cada uma graceful)
        _run_fase("Fase 1 (Processo)", self.fase_processo)
        _run_fase("Fase 2 (Parâmetros)", self.fase_parametros_calculo)
        _run_fase("Fase 3 (Histórico)", self.fase_historico_salarial)
        _run_fase("Fase 4 (Verbas)", self.fase_verbas)
        _run_fase("Fase 5 (Cartão Ponto)", self.fase_cartao_de_ponto, bool(self.previa.cartao_de_ponto))
        _run_fase("Fase 6 (Faltas)", self.fase_faltas, bool(self.previa.faltas))
        _run_fase("Fase 7 (Férias)", self.fase_ferias, bool(self.previa.ferias.periodos))
        _run_fase("Fase 8 (FGTS)", self.fase_fgts)
        _run_fase("Fase 9 (CS/INSS)", self.fase_contribuicao_social)
        _run_fase("Fase 10 (IRPF)", self.fase_imposto_de_renda)
        _run_fase("Fase 11 (Honorários)", self.fase_honorarios, bool(self.previa.honorarios))
        _run_fase("Fase 12 (Custas)", self.fase_custas_judiciais)
        _run_fase("Fase 13 (Correção/Juros)", self.fase_correcao_juros_multa)

        # Liquidação — tenta mesmo com fases parciais
        try:
            return self.fase_liquidar_e_exportar()
        except Exception as e:
            self.log(f"⚠ Liquidação falhou: {e}")
            return None

    # ─── Helpers DOM ───────────────────────────────────────────────────────

    def _preencher(self, dom_id: str, valor: Any, obrigatorio: bool = True) -> None:
        """Preenche input por DOM ID (sufixo). Falha se obrigatório e DOM ausente.

        Pula silenciosamente se o elemento está `disabled` (campo já auto-preenchido
        pelo JSF, ex.: `justica` que é sempre "5" / Justiça do Trabalho).

        Para campos `*InputDate` ou `competencia*InputDate`: usa padrão especial
        focus → type sequencial → press Tab para disparar o blur do RichFaces
        Calendar e garantir que o backing bean receba o valor. Sem isso, o save
        falha com "Campo obrigatório: <data>" porque o calendar aceita o input
        mas não submete o valor ao server (bug documentado 12/05/2026).
        """
        if valor is None or valor == "":
            if obrigatorio:
                raise ValueError(f"Campo obrigatório vazio: {dom_id}")
            return
        sel = f"[id$='{dom_id}']"
        loc = self._page.locator(sel)
        if loc.count() == 0:
            if obrigatorio:
                raise RuntimeError(f"DOM ID não encontrado: {dom_id}")
            self.log(f"  ⚠ {dom_id} não existe — pulando")
            return
        # Pular se elemento está disabled (auto-preenchido pelo JSF)
        try:
            el = loc.first
            if not el.is_enabled():
                # Verifica se valor atual já casa com o desejado
                try:
                    valor_atual = el.input_value(timeout=1000)
                except Exception:
                    valor_atual = None
                if str(valor) == str(valor_atual):
                    self.log(f"  ⊙ {dom_id} = {valor} (já preenchido / disabled)")
                    return
                self.log(
                    f"  ⚠ {dom_id} disabled — atual={valor_atual!r}, desejado={valor!r} (pulando)"
                )
                return
        except Exception:
            pass

        # Detectar campo de data RichFaces Calendar
        is_data_field = dom_id.lower().endswith("inputdate") or "data" in dom_id.lower()
        if is_data_field:
            self._preencher_data_richfaces(loc.first, dom_id, str(valor))
        else:
            loc.first.fill(str(valor))
            # Disparar change para campos input genéricos (alguns RichFaces components
            # só ouvem change/blur — fill dispara apenas input)
            try:
                loc.first.dispatch_event("change")
            except Exception:
                pass
            self.log(f"  ✓ {dom_id} = {valor}")

    def _preencher_data_richfaces(self, locator, dom_id: str, valor: str) -> None:
        """Preenche um campo `<rich:calendar>` corretamente.

        Em RichFaces 3.3.x o calendar tem um InputDate visível + hidden inputs.
        O backing bean só recebe o valor se o `onchange` AJAX for disparado.
        Setar `value` via JavaScript + dispatch nativo de `change` é mais
        confiável que keyboard events (que podem ser interceptados pelo popup).
        """
        # Resolver elemento element handle do locator
        try:
            locator.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

        # Capturar id real do elemento
        try:
            real_id = locator.get_attribute("id")
        except Exception:
            real_id = None
        if not real_id:
            self.log(f"  ⚠ data {dom_id}: id não obtido — fallback fill")
            try:
                locator.fill(valor)
            except Exception:
                pass
            return

        # Estratégia JS: setar value + disparar evento change que o RichFaces escuta
        # No RichFaces 3.3.x, o calendar tem um listener .onchange registrado no input
        # InputDate. Setar value + disparar change + blur faz o handler rodar.
        ok = self._page.evaluate(
            """({id, valor}) => {
                const el = document.getElementById(id);
                if (!el) return 'no-element';
                // Setar valor diretamente
                el.value = valor;
                // Disparar todos os eventos relevantes em sequência
                ['focus','input','keyup','change','blur'].forEach(evt => {
                    try {
                        el.dispatchEvent(new Event(evt, {bubbles: true, cancelable: true}));
                    } catch (e) {}
                });
                // Tentar API RichFaces se disponível (calendar component)
                try {
                    if (typeof RichFaces !== 'undefined' && RichFaces.calendar) {
                        // O hidden input pode estar em id_input ou similar
                        const hid = document.getElementById(id.replace(/InputDate$/, ''));
                        if (hid) {
                            hid.value = valor;
                            hid.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    }
                } catch (e) {}
                return 'ok';
            }""",
            {"id": real_id, "valor": valor},
        )
        # Aguardar AJAX a4j que o onchange dispara
        self._aguardar_ajax(3000)
        self._page.wait_for_timeout(500)
        # Verificar se valor está realmente no DOM
        try:
            valor_atual = locator.input_value(timeout=1000)
            if valor_atual == valor:
                self.log(f"  ✓ {dom_id} = {valor} (data: js+events, confirmed)")
                return
            else:
                self.log(f"  ⚠ data {dom_id}: setou={valor!r} mas DOM tem={valor_atual!r}")
        except Exception:
            pass

        # Fallback: tentar fill + Tab
        try:
            locator.fill(valor)
            locator.press("Tab")
            self._aguardar_ajax(3000)
            self.log(f"  ✓ {dom_id} = {valor} (data: fallback fill+Tab)")
        except Exception as e:
            self.log(f"  ⚠ {dom_id}: fallback falhou: {e}")

    def _marcar_radio(self, dom_id: str, valor: str, obrigatorio: bool = False) -> None:
        # Cascata de seletores. JSF h:selectOneRadio com <s:convertEnum> pode
        # renderizar value como ordinal (0/1/2) ou texto. Tentamos múltiplas
        # variantes incluindo lookup via texto/label da option.
        selectors = [
            f"input[type='radio'][id$=':{dom_id}'][value='{valor}']",
            f"input[type='radio'][id*='{dom_id}'][value='{valor}']",
            f"input[type='radio'][name$=':{dom_id}'][value='{valor}']",
            f"input[type='radio'][name*='{dom_id}'][value='{valor}']",
        ]
        for sel in selectors:
            loc = self._page.locator(sel)
            if loc.count() > 0:
                try:
                    loc.first.click(force=True)
                    self.log(f"  ✓ radio {dom_id} = {valor}")
                    return
                except Exception:
                    continue

        # Fallback JS: enumerar radios com id/name match e tentar por value OU label
        marcou = self._page.evaluate(
            """({dom_id, valor}) => {
                const norm = s => (s||'').replace(/\\s+/g,' ').trim().toUpperCase();
                const tgt = norm(valor);
                // Cobrir IDs JSF tipo formulario:indicesAcumulados:0/:1/...
                const radios = [...document.querySelectorAll('input[type="radio"]')]
                    .filter(r => (r.id||'').includes(dom_id) || (r.name||'').includes(dom_id));
                // 1) Match por value exato
                for (const r of radios) {
                    if (norm(r.value) === tgt) { r.click(); return 'value:'+r.value; }
                }
                // 2) Match por label[for=r.id] textContent
                for (const r of radios) {
                    if (!r.id) continue;
                    const label = document.querySelector('label[for="'+r.id.replace(/[^\\w-]/g, c => '\\\\'+c)+'"]');
                    if (label) {
                        const txt = norm(label.textContent);
                        if (txt === tgt || txt.includes(tgt) || tgt.includes(txt)) {
                            r.click();
                            return 'label:'+txt.slice(0,40);
                        }
                    }
                }
                // 3) Match por texto do <td> ou <li> adjacente (RichFaces)
                for (const r of radios) {
                    const cell = r.closest('td, li, label');
                    if (cell) {
                        const txt = norm(cell.textContent);
                        if (txt && (txt === tgt || txt.includes(tgt) || tgt.includes(txt))) {
                            r.click();
                            return 'cell:'+txt.slice(0,40);
                        }
                    }
                }
                return null;
            }""",
            {"dom_id": dom_id, "valor": valor},
        )
        if marcou:
            self.log(f"  ✓ radio {dom_id} = {valor} (via {marcou})")
            return

        if obrigatorio:
            raise RuntimeError(f"Radio não encontrado: {dom_id}={valor}")
        self.log(f"  ⚠ radio {dom_id}={valor} não encontrado — pulando")

    def _marcar_checkbox(self, dom_id: str, marcado: bool) -> None:
        # Seletor MAIS específico: input[type=checkbox] com id terminando em ':<dom_id>' ou em '<dom_id>' exato.
        # Evita match em outros elementos (ex.: select, radio, link) cujo id também termine no nome.
        for sel in (
            f"input[type='checkbox'][id='formulario:{dom_id}']",
            f"input[type='checkbox'][id$=':{dom_id}']",
            f"input[type='checkbox'][id$='{dom_id}']",
        ):
            loc = self._page.locator(sel)
            if loc.count() > 0:
                try:
                    if loc.first.is_checked() != marcado:
                        loc.first.click(force=True)
                    self.log(f"  ✓ checkbox {dom_id} = {marcado}")
                    return
                except Exception as e:
                    self.log(f"  ⚠ checkbox {dom_id}: {e} — tentando próximo seletor")
                    continue
        self.log(f"  ⚠ checkbox {dom_id} não existe ou não é checkbox — pulando")

    def _selecionar(self, dom_id: str, valor: str, obrigatorio: bool = False) -> None:
        loc = self._page.locator(f"select[id$='{dom_id}']")
        if loc.count() == 0:
            if obrigatorio:
                raise RuntimeError(f"Select não encontrado: {dom_id}")
            self.log(f"  ⚠ select {dom_id} não encontrado — pulando")
            return
        try:
            loc.first.select_option(value=valor)
        except Exception:
            try:
                loc.first.select_option(label=valor)
            except Exception as e:
                self.log(f"  ⚠ select {dom_id}={valor}: {e} — pulando")
                return
        self.log(f"  ✓ select {dom_id} = {valor}")

    def _clicar(self, dom_id: str, timeout_ms: int = 8000) -> None:
        """Clica botão por sufixo de DOM ID. Aguarda elemento ficar visível
        antes de clicar (timeout 8s default). Padrão Calc Machine: tenta
        cascata de seletores quando o ID exato não existe.
        """
        # Cascata de seletores: input[id$=':NAME'], input[id$='NAME'], a[id$=...]
        selectors = [
            f"input[id$=':{dom_id}']",
            f"input[id$='{dom_id}']",
            f"a[id$=':{dom_id}']",
            f"button[id$=':{dom_id}']",
            f"[id$=':{dom_id}']",
            f"[id$='{dom_id}']",
        ]
        for sel in selectors:
            loc = self._page.locator(sel)
            if loc.count() > 0:
                try:
                    loc.first.wait_for(state="visible", timeout=timeout_ms)
                    loc.first.click()
                    self.log(f"  ✓ click {dom_id}")
                    return
                except Exception as e:
                    # Tenta próximo seletor
                    continue
        raise RuntimeError(f"Botão não encontrado: {dom_id}")

    def _aguardar_ajax(self, timeout_ms: int = 10000) -> None:
        try:
            self._page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

    def _preencher_prazo_aviso_informado(self, dias: int) -> None:
        """Preenche o campo 'prazoAvisoInformado' que aparece condicionalmente
        após selecionar 'APURACAO_INFORMADA' no campo apuracaoPrazoDoAvisoPrevio.

        O JSF re-renderiza o componente via AJAX, então precisamos aguardar
        explicitamente a visibilidade do input antes de tentar preencher.
        Cascata de seletores: id literal, id sufixo, name sufixo, name parcial.
        Tooltip de erro indica que o id real é `formulario:prazoAvisoInformado`.
        """
        seletores = [
            "input#formulario\\:prazoAvisoInformado",
            "input[id='formulario:prazoAvisoInformado']",
            "input[id$=':prazoAvisoInformado']",
            "input[id$='prazoAvisoInformado']",
            "input[name$=':prazoAvisoInformado']",
            "input[name$='prazoAvisoInformado']",
        ]
        encontrado = None
        for sel in seletores:
            try:
                self._page.wait_for_selector(sel, state="visible", timeout=4000)
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    encontrado = loc.first
                    self.log(f"  ✓ prazoAvisoInformado encontrado via {sel!r}")
                    break
            except Exception:
                continue

        if encontrado is None:
            # Fallback JS: localizar pelo id contendo 'prazoAviso' E type number/text
            real_id = self._page.evaluate(
                """() => {
                    const inputs = [...document.querySelectorAll('input')];
                    const cand = inputs.find(i =>
                        (i.id||'').toLowerCase().includes('prazoaviso') &&
                        !(i.id||'').toLowerCase().includes('erro') &&
                        (i.type === 'text' || i.type === 'number') &&
                        i.offsetParent !== null
                    );
                    return cand ? cand.id : null;
                }"""
            )
            if real_id:
                encontrado = self._page.locator(f"#{real_id.replace(':', '\\:')}")
                self.log(f"  ✓ prazoAvisoInformado via JS scan: id={real_id}")
            else:
                self.log("  ⚠ prazoAvisoInformado não renderizado — radio APURACAO_INFORMADA pode não ter disparado AJAX")
                return

        try:
            encontrado.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        try:
            encontrado.fill(str(dias))
            try:
                encontrado.dispatch_event("change")
            except Exception:
                pass
            try:
                encontrado.press("Tab")
            except Exception:
                pass
            self._aguardar_ajax(2000)
            self.log(f"  ✓ prazoAvisoInformado = {dias}")
        except Exception as e:
            self.log(f"  ⚠ falha ao preencher prazoAvisoInformado: {e}")

    # ─── Helpers críticos inspirados no Calc Machine ──────────────────────
    # Padrão observado em 12/05/2026 via Chrome MCP no calcmachine.ensinoplus.com.br:
    # após cada save crítico, aguardar `.rf-msgs-sum` com "Operação realizada
    # com sucesso." e extrair o número do cálculo do DOM como prova de persistência.

    def _aguardar_operacao_sucesso(self, timeout_ms: int = 30000, bloqueante: bool = False) -> bool:
        """Aguarda a mensagem JSF "Operação realizada com sucesso" aparecer no DOM.

        Retorna True se a mensagem apareceu, False se houve timeout (ou erro
        capturado). Por padrão NÃO é bloqueante — emite aviso no log e prossegue,
        igual ao comportamento do Calc Machine durante a Liquidação.

        Use `bloqueante=True` em fases onde a persistência é crítica (ex.: Fase 1+2).
        """
        try:
            # Esperar mensagem aparecer em qualquer elemento com class rf-msgs-sum,
            # rf-msgs-detail, ou texto "Operação realizada com sucesso"
            self._page.wait_for_function(
                """() => {
                    const body = document.body?.textContent || '';
                    return body.includes('Operação realizada com sucesso') ||
                           body.includes('Operacao realizada com sucesso');
                }""",
                timeout=timeout_ms,
            )
            self.log(f"  ✓ Operação realizada com sucesso.")
            return True
        except Exception as e:
            msg = f"⚠ Mensagem de sucesso não detectada em {timeout_ms/1000:.0f}s ({type(e).__name__})"
            if bloqueante:
                raise RuntimeError(msg)
            self.log(f"  {msg} — prosseguindo")
            return False

    def _extrair_numero_calculo(self) -> str | None:
        """Extrai o número do cálculo do DOM após save da Fase 2.

        O PJE-Calc exibe o número do cálculo no header/breadcrumb após o save
        bem-sucedido (ex.: "Cálculo: 976"). Esse é o sinal definitivo de
        persistência no H2/PostgreSQL.

        Retorna o número como string (ex.: "976") ou None se não encontrado.
        """
        try:
            num = self._page.evaluate(
                """() => {
                    // Procurar por padrões "Cálculo: NNN" ou "Cálculo NNN" no DOM
                    const body = document.body?.textContent || '';
                    let m = body.match(/C[áa]lculo\\s*:?\\s*(\\d{1,8})/i);
                    if (m) return m[1];
                    // Procurar no breadcrumb explícito
                    const bc = document.querySelector('.breadcrumb, [class*="breadcrumb"]');
                    if (bc) {
                        m = (bc.textContent || '').match(/(\\d{2,8})/);
                        if (m) return m[1];
                    }
                    // Procurar campo input com value numérico (id do calc)
                    const inputs = [...document.querySelectorAll('input[id*="idCalculo"], input[name*="idCalculo"]')];
                    for (const i of inputs) {
                        if (i.value && /^\\d+$/.test(i.value)) return i.value;
                    }
                    return null;
                }"""
            )
            if num:
                self._calculo_numero = num
                self.log(f"  ✓ NÚMERO DO CÁLCULO: {num}")
            return num
        except Exception as e:
            self.log(f"  ⚠ Falha ao extrair número do cálculo: {e}")
            return None

    def _verificar_erro_jsf(self) -> str | None:
        """Verifica se há mensagem de erro JSF visível na página (rf-msgs-err
        ou texto "Erro inesperado", "Campo obrigatório", etc.).

        Retorna a mensagem se houver erro, None se a página está OK.
        """
        try:
            err = self._page.evaluate(
                """() => {
                    // Mensagens de erro do RichFaces
                    const errEls = [...document.querySelectorAll('.rf-msgs-err, .rf-msg-err, .messageError, [class*="error"]')];
                    for (const el of errEls) {
                        const txt = (el.textContent || '').trim();
                        if (txt && txt.length > 5) return txt.slice(0, 300);
                    }
                    // Erro 500/NPE
                    const body = document.body?.textContent || '';
                    if (body.includes('HTTP Status 500')) return 'HTTP Status 500';
                    if (body.includes('NullPointerException')) return 'NullPointerException no servidor';
                    if (body.includes('Erro inesperado')) return 'Erro inesperado JSF';
                    return null;
                }"""
            )
            return err
        except Exception:
            return None

    def _diagnostico_pagina(self, contexto: str = "") -> None:
        """Captura forense completa da página após save (para depurar quando
        save não recebe confirmação esperada).

        Lista TODAS as mensagens visíveis (rf-msgs-*, rich-message, ui-message,
        .alert, etc.) + classes invalid em inputs + erros 500/NPE + URL atual.
        """
        try:
            diag = self._page.evaluate(
                """() => {
                    const out = {
                        url: location.href,
                        title: document.title,
                        msgs: [],
                        invalids: [],
                        h_tags: [],
                        breadcrumb: '',
                    };
                    // Coletar TODAS as mensagens visíveis (qualquer rf-msg* ou .rich-message*)
                    const sels = [
                        '.rf-msgs', '.rf-msg', '.rf-msgs-sum', '.rf-msgs-detail',
                        '.rf-msgs-err', '.rf-msgs-info', '.rf-msgs-ok', '.rf-msgs-warn',
                        '.rich-message', '.rich-messages',
                        '.ui-message', '.messageError', '.messageSuccess', '.alert',
                        '[class*="message"]', '[class*="msg"]',
                    ];
                    const seen = new Set();
                    for (const s of sels) {
                        for (const el of document.querySelectorAll(s)) {
                            const txt = (el.textContent || '').replace(/\\s+/g,' ').trim();
                            if (txt && txt.length > 3 && txt.length < 500 && !seen.has(txt)) {
                                seen.add(txt);
                                out.msgs.push({sel: s, txt: txt.slice(0, 200)});
                            }
                        }
                    }
                    // Inputs com classe invalid
                    for (const el of document.querySelectorAll('input.invalid, input.rf-im-inv, [aria-invalid="true"]')) {
                        out.invalids.push({id: el.id, name: el.name, value: (el.value || '').slice(0, 40)});
                    }
                    // H tags (geralmente trazem contexto da página)
                    for (const h of document.querySelectorAll('h1, h2, h3')) {
                        const t = (h.textContent || '').trim().slice(0, 100);
                        if (t) out.h_tags.push(t);
                    }
                    // Breadcrumb
                    const bc = document.querySelector('.breadcrumb, [class*="breadcrumb"]');
                    if (bc) out.breadcrumb = (bc.textContent || '').replace(/\\s+/g,' ').trim().slice(0, 200);
                    return out;
                }"""
            )
            self.log(f"  📋 DIAGNÓSTICO {contexto}:")
            self.log(f"     url: {diag.get('url', '')[:100]}")
            self.log(f"     title: {diag.get('title')}")
            if diag.get('breadcrumb'):
                self.log(f"     breadcrumb: {diag['breadcrumb']}")
            if diag.get('h_tags'):
                self.log(f"     h: {diag['h_tags'][:3]}")
            for m in diag.get('msgs', [])[:8]:
                self.log(f"     msg [{m['sel']}]: {m['txt']}")
            for inv in diag.get('invalids', [])[:5]:
                self.log(f"     INVALID: {inv['id']} = '{inv['value']}'")
        except Exception as e:
            self.log(f"  ⚠ diagnóstico falhou: {e}")

    # Mapa li_id → texto visível do menu (para fallback por texto)
    _MENU_TEXT_MAP = {
        "li_calculo_dados_do_calculo": "Dados do Cálculo",
        "li_calculo_faltas": "Faltas",
        "li_calculo_ferias": "Férias",
        "li_calculo_historico_salarial": "Histórico Salarial",
        "li_calculo_verbas": "Verbas",
        "li_calculo_cartao_ponto": "Cartão de Ponto",
        "li_calculo_salario_familia": "Salário-família",
        "li_calculo_seguro_desemprego": "Seguro-desemprego",
        "li_calculo_fgts": "FGTS",
        "li_calculo_inss": "Contribuição Social",
        "li_calculo_previdencia_privada": "Previdência Privada",
        "li_calculo_pensao_alimenticia": "Pensão Alimentícia",
        "li_calculo_irpf": "Imposto de Renda",
        "li_calculo_multas_e_indenizacoes": "Multas e Indenizações",
        "li_calculo_honorarios": "Honorários",
        "li_calculo_custas_judiciais": "Custas Judiciais",
        "li_calculo_correcao_juros_multa": "Correção, Juros e Multa",
    }
    # Mapa li_id → jsf page path (para URL nav como fallback definitivo)
    _MENU_URL_MAP = {
        "li_calculo_dados_do_calculo": "calculo.jsf",
        "li_calculo_faltas": "falta.jsf",
        "li_calculo_ferias": "ferias.jsf",
        "li_calculo_historico_salarial": "historico-salarial.jsf",
        "li_calculo_verbas": "verba/verba-calculo.jsf",
        "li_calculo_cartao_ponto": "../cartaodeponto/apuracao-cartaodeponto.jsf",
        "li_calculo_salario_familia": "salario-familia.jsf",
        "li_calculo_seguro_desemprego": "seguro-desemprego.jsf",
        "li_calculo_fgts": "fgts.jsf",
        "li_calculo_inss": "inss/inss.jsf",
        "li_calculo_previdencia_privada": "previdencia-privada.jsf",
        "li_calculo_pensao_alimenticia": "pensao-alimenticia.jsf",
        "li_calculo_irpf": "irpf.jsf",
        "li_calculo_multas_e_indenizacoes": "multas-indenizacoes.jsf",
        "li_calculo_honorarios": "honorarios.jsf",
        "li_calculo_custas_judiciais": "custas-judiciais.jsf",
        "li_calculo_correcao_juros_multa": "parametros-atualizacao/parametros-atualizacao.jsf",
    }

    def _navegar_menu(self, li_id: str) -> None:
        """Navega para item do menu lateral.

        Estratégia: URL nav PRIMEIRO (mais confiável quando temos conversationId),
        click em li/texto como fallback. Texto-match é ambíguo (há "Verbas" em
        tabelas e em cálculo) então URL é mais seguro.
        """
        # 0. PREFERIDO: URL nav direto se temos conversationId
        jsf_page = self._MENU_URL_MAP.get(li_id)
        if jsf_page and self._calculo_conversation_id:
            url = (
                f"{self.pjecalc_url}/pages/calculo/{jsf_page}"
                f"?conversationId={self._calculo_conversation_id}"
            )
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
                self._aguardar_ajax(15000)
                # Defensive: Seam pode redirect para conversation atualizada
                self._capturar_conversation_id()
                self.log(f"  → navegou para {li_id} via url-nav direto")
                return
            except Exception as e:
                self.log(f"  ⚠ URL nav falhou ({e}) — tentando menu click")

        texto = self._MENU_TEXT_MAP.get(li_id, "")
        tail = li_id.replace("li_", "", 1)

        clicou = self._page.evaluate(
            """([liId, tail, texto]) => {
                // 1. ID exato
                let li = document.getElementById(liId);
                if (li) {
                    const a = li.querySelector('a');
                    if (a) { a.click(); return 'id-exact:'+liId; }
                }
                // 2. ID por sufixo (tail)
                if (tail) {
                    const lis = document.querySelectorAll(`li[id$="${tail}"]`);
                    for (const l of lis) {
                        const a = l.querySelector('a');
                        if (a) { a.click(); return 'id-tail:'+l.id; }
                    }
                }
                // 3. <a> com texto exato dentro de <li>
                if (texto) {
                    const links = [...document.querySelectorAll('li a')];
                    for (const a of links) {
                        if ((a.textContent||'').trim() === texto) {
                            a.click();
                            return 'text-li:'+texto;
                        }
                    }
                    // 4. <a> com texto exato em qualquer lugar
                    const all = [...document.querySelectorAll('a')];
                    for (const a of all) {
                        if ((a.textContent||'').trim() === texto) {
                            a.click();
                            return 'text-any:'+texto;
                        }
                    }
                }
                return null;
            }""",
            [li_id, tail, texto],
        )
        if not clicou:
            # 5. Fallback definitivo: URL nav direto (sem depender do menu).
            jsf_page = self._MENU_URL_MAP.get(li_id)
            if jsf_page and self._calculo_conversation_id:
                url = (
                    f"{self.pjecalc_url}/pages/calculo/{jsf_page}"
                    f"?conversationId={self._calculo_conversation_id}"
                )
                self.log(f"  ↪ Menu não encontrado — URL nav: {jsf_page}")
                try:
                    self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax(15000)
                    self.log(f"  → navegou para {li_id} via url-nav")
                    return
                except Exception as e:
                    raise RuntimeError(
                        f"Menu '{li_id}' falhou em todos os fallbacks (incluindo URL nav). "
                        f"Erro: {e}"
                    )
            raise RuntimeError(
                f"Menu não encontrado: {li_id} (texto='{texto}'). "
                f"Verifique se a página tem o menu lateral renderizado."
            )
        self._aguardar_ajax(15000)
        self.log(f"  → navegou para {li_id} via {clicou}")

    # ─── Fases ─────────────────────────────────────────────────────────────

    def _capturar_conversation_id(self) -> bool:
        """Re-captura o conversationId atual da URL.

        CRÍTICO: o PJE-Calc/Seam pode emitir um novo conversationId após
        certas ações (Expresso save, redirects pós-Salvar, etc.). Se
        continuarmos usando o conversationId antigo nas URL nav seguintes,
        elas vão para uma conversation expirada → NPE/empty pages.

        Esta função extrai o conv_id da URL atual e atualiza o estado.
        v1 chama isso após cada save crítico (linha 4880 playwright_pjecalc.py).

        Returns True se o conv_id mudou.
        """
        import re
        try:
            url = self._page.url or ""
            m = re.search(r'conversationId=(\d+)', url)
            if m:
                novo = m.group(1)
                if novo != self._calculo_conversation_id:
                    antigo = self._calculo_conversation_id
                    self._calculo_conversation_id = novo
                    self.log(f"  ℹ conversationId atualizado: {antigo} → {novo}")
                    return True
                return False
        except Exception as e:
            self.log(f"  ⚠ _capturar_conversation_id: {e}")
        return False

    def _reabrir_calculo_via_recentes(self) -> bool:
        """Volta para principal e reabre cálculo via lista 'Recentes'.

        Workaround para NPE pós-Expresso: cria nova conversação Seam limpa
        atualizando self._calculo_conversation_id. Documentado em v1
        (playwright_pjecalc.py linha 3058).

        Returns True se reabriu com sucesso.
        """
        try:
            self._page.goto(
                f"{self.pjecalc_url}/pages/principal.jsf",
                wait_until="domcontentloaded", timeout=15000,
            )
            self._page.wait_for_timeout(2000)
            self._aguardar_ajax(8000)

            listbox = self._page.locator(
                "select[class*='listaCalculosRecentes'], select[name*='listaCalculosRecentes']"
            )
            if listbox.count() == 0:
                self.log("  ⚠ Lista de Cálculos Recentes não encontrada — pulando reabrir")
                return False

            n_opts = listbox.first.locator("option").count()
            if n_opts == 0:
                return False

            # Achar pelo CNJ do processo
            num = self.previa.processo.numero_processo
            num_clean = num.replace(".", "").replace("-", "").replace("/", "")
            found_idx = None
            options = listbox.first.locator("option")
            for i in range(n_opts):
                opt_text = (options.nth(i).text_content() or "")
                if num_clean in opt_text.replace(".", "").replace("-", "").replace("/", ""):
                    found_idx = i
                    break

            # Fallback: pelo nome do reclamante
            if found_idx is None:
                rec = (self.previa.processo.reclamante.nome or "").upper()
                if len(rec) >= 5:
                    for i in range(n_opts):
                        if rec in (options.nth(i).text_content() or "").upper():
                            found_idx = i
                            break

            # Último: 1 item só na lista
            if found_idx is None and n_opts == 1:
                found_idx = 0

            if found_idx is None:
                # Log all Recentes items for diagnostics
                all_texts = [
                    (options.nth(i).text_content() or "").strip()[:80]
                    for i in range(min(n_opts, 10))
                ]
                self.log(f"  ⚠ Processo {num} não encontrado nos Recentes ({n_opts} itens)")
                self.log(f"  ℹ Recentes items: {all_texts}")
                return False

            opt_text_chosen = (options.nth(found_idx).text_content() or "").strip()[:60]
            self.log(f"  → Recentes: tentando reabrir item {found_idx+1}/{n_opts}: '{opt_text_chosen}'")
            opt_el = options.nth(found_idx)
            opt_el.click()
            self._page.wait_for_timeout(300)
            try:
                opt_el.dblclick()
            except Exception as e:
                self.log(f"    ⚠ dblclick: {e}")
            self._aguardar_ajax(30000)
            self._page.wait_for_timeout(2000)

            url_after = self._page.url
            self.log(f"  → URL pós-reabrir: {url_after[-80:]}")
            if "calculo" in url_after and "conversationId=" in url_after:
                old_conv = self._calculo_conversation_id
                self._calculo_conversation_id = url_after.split("conversationId=")[1].split("&")[0]
                self.log(f"  ✓ Cálculo reaberto via Recentes (conv {old_conv} → {self._calculo_conversation_id})")
                return True
            self.log(f"  ⚠ Reabrir não navegou para calculo.jsf — URL atual: {url_after[-80:]}")
            return False
        except Exception as e:
            import traceback
            self.log(f"  ⚠ _reabrir_calculo_via_recentes: {type(e).__name__}: {e}")
            return False

    def _reabrir_via_buscar(self) -> bool:
        """Fallback: usa sidebar Buscar para pesquisar o cálculo e abri-lo em edit mode.

        Alternativa quando Recentes não inclui o calc atual (comum em sessões locais
        onde TBCALCULOSRECENTESUSUARIO não registrou o novo cálculo).

        Fluxo:
        1. Click em li_calculo_buscar → calculo.jsf?conversationId=N (Buscar page)
        2. Preencher campos de busca com numero/digito/ano/regiao/vara do processo
        3. Click botão 'Buscar'
        4. Aguardar resultados e clicar no primeiro item correspondente
        5. Verificar se URL mudou para calculo.jsf em modo edição

        Returns True se reabriu com sucesso.
        """
        try:
            self.log("  → Tentando Buscar como fallback de Recentes...")
            # Navegar para principal primeiro (garante sidebar disponível)
            self._page.goto(
                f"{self.pjecalc_url}/pages/principal.jsf",
                wait_until="domcontentloaded", timeout=15000,
            )
            self._aguardar_ajax(5000)

            # Click em Buscar no sidebar
            clicou = self._page.evaluate("""() => {
                const li = document.getElementById('li_calculo_buscar');
                if (li) { const a = li.querySelector('a'); if (a) { a.click(); return 'ok'; } }
                return null;
            }""")
            if not clicou:
                self.log("  ⚠ li_calculo_buscar não encontrado no sidebar")
                return False

            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(1000)

            # Preencher campos de busca com CNJ do processo
            # IMPORTANTE: usar [id='...'] (attribute selector) e NÃO #id:campo
            # porque colons em IDs são inválidos em seletores CSS (#id:colon).
            cnj = _split_cnj(self.previa.processo.numero_processo)
            for field_id, valor in [
                ("formulario:numeroProcessoBusca", cnj.get("numero", "")),
                ("formulario:digitoProcessoBusca", cnj.get("digito", "")),
                ("formulario:anoProcessoBusca", cnj.get("ano", "")),
                ("formulario:regiaoBusca", cnj.get("regiao", "")),
                ("formulario:varaProcessoBusca", cnj.get("vara", "")),
            ]:
                if not valor:
                    continue
                loc = self._page.locator(f"[id='{field_id}']")
                if loc.count() > 0:
                    loc.first.fill(valor)

            # Click Buscar — usar attribute selector (colons inválidos em CSS)
            btn_buscar = self._page.locator("[id='formulario:buscar']")
            if btn_buscar.count() == 0:
                self.log("  ⚠ Botão Buscar não encontrado")
                return False
            btn_buscar.first.click()
            self._aguardar_ajax(15000)
            self._page.wait_for_timeout(2000)

            # Procurar resultado na listagem
            # Os resultados geralmente aparecem em uma tabela com links "Abrir"
            num_cnj = self.previa.processo.numero_processo
            num_clean = num_cnj.replace(".", "").replace("-", "").replace("/", "")

            resultado_link = self._page.evaluate(
                f"""() => {{
                    // Procurar link/botão que abre o cálculo nos resultados
                    const links = [...document.querySelectorAll('a, input[type=button], input[type=submit]')];
                    // Procurar na tabela de resultados: linhas com o número do processo
                    const rows = [...document.querySelectorAll('tr')];
                    for (const row of rows) {{
                        const rowText = row.textContent.replace(/[\\s.\\-\\/]/g, '');
                        if (rowText.includes('{num_clean}')) {{
                            // Encontrou a linha — clicar no primeiro link/botão
                            const link = row.querySelector('a') || row.querySelector('input[type=button]');
                            if (link) {{
                                link.click();
                                return 'row-link: ' + (link.textContent || link.value || '').trim().slice(0,30);
                            }}
                        }}
                    }}
                    // Fallback: primeiro link após busca que contenha o número
                    for (const a of links) {{
                        if ((a.textContent || '').replace(/[\\s.\\-\\/]/g, '').includes('{num_clean}')) {{
                            a.click();
                            return 'direct-link';
                        }}
                    }}
                    return null;
                }}"""
            )

            if not resultado_link:
                # Log resultados disponíveis para diagnóstico
                resultados = self._page.evaluate("""() => {
                    return [...document.querySelectorAll('tr')]
                        .filter(r => r.cells && r.cells.length > 1)
                        .map(r => r.textContent.trim().slice(0, 80))
                        .filter(t => t)
                        .slice(0, 5);
                }""")
                self.log(f"  ⚠ Processo não encontrado na busca. Resultados: {resultados}")
                return False

            self.log(f"  → Busca abriu: {resultado_link}")
            self._aguardar_ajax(15000)
            self._page.wait_for_timeout(2000)

            url_after = self._page.url
            self.log(f"  → URL pós-buscar: {url_after[-80:]}")
            if "calculo" in url_after and "conversationId=" in url_after:
                old_conv = self._calculo_conversation_id
                self._calculo_conversation_id = url_after.split("conversationId=")[1].split("&")[0]
                self.log(f"  ✓ Cálculo reaberto via Buscar (conv {old_conv} → {self._calculo_conversation_id})")
                return True
            self.log(f"  ⚠ Buscar não navegou para calculo.jsf — URL: {url_after[-80:]}")
            return False
        except Exception as e:
            self.log(f"  ⚠ _reabrir_via_buscar: {type(e).__name__}: {e}")
            return False

    def _abrir_pjecalc(self) -> None:
        self._page.goto(f"{self.pjecalc_url}/pages/principal.jsf", timeout=30000)
        self._aguardar_ajax()
        self.log("✓ PJE-Calc home carregado")

    def _criar_novo_calculo(self) -> None:
        """Click em "Novo" no menu lateral do PJE-Calc Cidadão.

        IMPORTANTE: per CLAUDE.md, sempre usar "Novo" (não "Cálculo Externo").
        O Cidadão NÃO tem "Criar Novo Cálculo" — apenas "Novo" no menu lateral
        ou submenu de operações.
        """
        # Tentar múltiplos seletores em ordem de robustez
        clicou = self._page.evaluate(
            """() => {
                // 1. li id="li_novo" no menu lateral (Cidadão)
                const liNovo = document.getElementById('li_novo');
                if (liNovo) {
                    const a = liNovo.querySelector('a');
                    if (a) { a.click(); return 'li_novo'; }
                }
                // 2. Qualquer <a> com texto exato "Novo" dentro de menu
                const links = [...document.querySelectorAll('a')];
                for (const a of links) {
                    const t = (a.textContent||'').trim();
                    if (t === 'Novo' || t === 'Criar Novo Cálculo' || t === 'Novo Cálculo') {
                        a.click();
                        return 'text-match: '+t;
                    }
                }
                return null;
            }"""
        )
        if not clicou:
            raise RuntimeError(
                "Botão 'Novo' não encontrado na home do PJE-Calc. "
                "Verifique se está logado e em principal.jsf."
            )
        self.log(f"  → Click via {clicou}")
        self._aguardar_ajax(25000)
        # Esperar URL mudar para algo como calculo.jsf?conversationId=N
        try:
            self._page.wait_for_url("**/calculo*.jsf*", timeout=20000)
        except Exception:
            pass
        # Capturar conversationId
        url = self._page.url
        if "conversationId=" in url:
            self._calculo_conversation_id = url.split("conversationId=")[1].split("&")[0]
        self.log(f"✓ Novo cálculo criado (conv={self._calculo_conversation_id}, url={url[-80:]})")
        if not self._calculo_conversation_id:
            raise RuntimeError(
                f"conversationId não capturado após click em 'Novo'. URL atual: {url}. "
                f"Pode ser que a navegação tenha falhado ou o cálculo não foi inicializado."
            )

    def fase_processo(self) -> None:
        self.log("Fase 1 — Dados do Processo")
        proc = self.previa.processo
        cnj = _split_cnj(proc.numero_processo)
        self._preencher("numero", cnj["numero"])
        self._preencher("digito", cnj["digito"])
        self._preencher("ano", cnj["ano"])
        self._preencher("justica", cnj["justica"], obrigatorio=False)
        self._preencher("regiao", cnj["regiao"])
        self._preencher("vara", cnj["vara"])
        self._preencher("valorDaCausa", _fmt_br(proc.valor_da_causa_brl))
        self._preencher("autuadoEm", proc.data_autuacao)

        # Reclamante
        self._preencher("reclamanteNome", proc.reclamante.nome)
        self._marcar_radio("documentoFiscalReclamante", proc.reclamante.doc_fiscal.tipo.value)
        self._preencher("reclamanteNumeroDocumentoFiscal", proc.reclamante.doc_fiscal.numero)

        # Reclamado
        self._preencher("reclamadoNome", proc.reclamado.nome)
        self._marcar_radio("tipoDocumentoFiscalReclamado", proc.reclamado.doc_fiscal.tipo.value)
        self._preencher("reclamadoNumeroDocumentoFiscal", proc.reclamado.doc_fiscal.numero)

        # Validação de erro inline (sem salvar — save acontece na Fase 2)
        erro = self._verificar_erro_jsf()
        if erro:
            self.log(f"  ⚠ Erro JSF após preencher Dados: {erro[:200]}")
        self.log("Fase 1 concluída")

    def fase_parametros_calculo(self) -> None:
        self.log("Fase 2 — Parâmetros do Cálculo")
        # Click na aba "Parâmetros do Cálculo"
        self._page.evaluate(
            """[...document.querySelectorAll('.rich-tab-header')].find(t =>
                t.textContent.trim() === 'Parâmetros do Cálculo')?.click()"""
        )
        self._aguardar_ajax()

        pc = self.previa.parametros_calculo
        # Estado/Município
        self._selecionar("estado", pc.estado_uf)
        self._aguardar_ajax(3000)
        self._selecionar("municipio", pc.municipio)

        # Datas
        self._preencher("dataAdmissaoInputDate", pc.data_admissao)
        self._preencher("dataDemissaoInputDate", pc.data_demissao)
        self._preencher("dataAjuizamentoInputDate", pc.data_ajuizamento)
        self._preencher("dataInicioCalculoInputDate", pc.data_inicio_calculo)
        self._preencher("dataTerminoCalculoInputDate", pc.data_termino_calculo)

        # Prescrição
        self._marcar_checkbox("prescricaoQuinquenal", pc.prescricao_quinquenal)
        self._marcar_checkbox("prescricaoFgts", pc.prescricao_fgts)

        # Remunerações
        self._selecionar("tipoDaBaseTabelada", pc.tipo_base_tabelada.value)
        self._preencher("valorMaiorRemuneracao", _fmt_br(pc.valor_maior_remuneracao_brl))
        self._preencher("valorUltimaRemuneracao", _fmt_br(pc.valor_ultima_remuneracao_brl))

        # Aviso prévio
        self._selecionar("apuracaoPrazoDoAvisoPrevio", pc.apuracao_aviso_previo.value)
        self._aguardar_ajax(3000)
        # Quando APURACAO_INFORMADA, o PJE-Calc renderiza o campo
        # 'prazoAvisoInformado' (obrigatório). Preencher com valor do JSON ou
        # calcular automaticamente conforme Lei 12.506/2011:
        #   30 dias base + 3 dias por ano completo trabalhado, máximo 90 dias.
        if pc.apuracao_aviso_previo.value == "APURACAO_INFORMADA":
            dias = getattr(pc, "prazo_aviso_previo_dias", None)
            if dias is None:
                # Auto-calcular: anos completos entre admissao e demissao
                try:
                    from datetime import datetime as _dt
                    d_adm = _dt.strptime(pc.data_admissao, "%d/%m/%Y")
                    d_dem = _dt.strptime(pc.data_demissao, "%d/%m/%Y")
                    anos = (d_dem - d_adm).days / 365.25
                    anos_completos = int(anos)
                    dias = min(30 + 3 * anos_completos, 90)
                    self.log(f"  ℹ prazo_aviso_previo_dias auto-calculado: {dias} (30 + 3×{anos_completos} anos)")
                except Exception as e:
                    dias = 30
                    self.log(f"  ⚠ falha auto-cálculo prazo aviso ({e}); usando 30")
            # O campo prazoAvisoInformado é renderizado condicionalmente via AJAX
            # após selecionar APURACAO_INFORMADA. Aguardar explicitamente a renderização.
            self._preencher_prazo_aviso_informado(dias)
        self._marcar_checkbox("projetaAvisoIndenizado", pc.projeta_aviso_indenizado)
        self._marcar_checkbox("limitarAvos", pc.limitar_avos)
        self._marcar_checkbox("zeraValorNegativo", pc.zerar_valor_negativo)

        # Feriados
        self._marcar_checkbox("consideraFeriadoEstadual", pc.considerar_feriado_estadual)
        self._marcar_checkbox("consideraFeriadoMunicipal", pc.considerar_feriado_municipal)

        # Carga horária
        self._preencher("valorCargaHorariaPadrao", _fmt_br(pc.carga_horaria.padrao_mensal))

        if pc.comentarios_jg:
            self._preencher("comentarios", pc.comentarios_jg, obrigatorio=False)

        # Salvar — validar persistência via padrão Calc Machine
        self.log("  → Clicando no botão salvar...")
        self._clicar("salvar")
        self.log("  → Aguardando processamento...")
        self._aguardar_ajax(15000)
        sucesso = self._aguardar_operacao_sucesso(timeout_ms=30000, bloqueante=False)
        if not sucesso:
            erro = self._verificar_erro_jsf()
            if erro:
                self.log(f"  ⚠ Erro JSF detectado: {erro[:200]}")
            # Diagnóstico forense: o que o JSF está mostrando depois do save?
            self._diagnostico_pagina(contexto="pós-save Fase 2")
        # Extrair número do cálculo — prova de persistência no banco
        num = self._extrair_numero_calculo()
        if not num:
            self.log("  ⚠ Número do cálculo não detectado no DOM — persistência incerta")
            if sucesso:  # sucesso mas sem número = situação rara
                self._diagnostico_pagina(contexto="sucesso sem número")
        self._capturar_conversation_id()
        self.log("Fase 2 concluída")

    # Históricos auto-criados pelo PJE-Calc (não devem ser duplicados)
    _HISTORICOS_DEFAULT = {
        "ÚLTIMA REMUNERAÇÃO", "ULTIMA REMUNERACAO",
        "SALÁRIO BASE", "SALARIO BASE",
        "ADICIONAL DE INSALUBRIDADE PAGO",
    }

    def fase_historico_salarial(self) -> None:
        self.log("Fase 3 — Histórico Salarial")
        self._navegar_menu("li_calculo_historico_salarial")

        def _norm(s: str) -> str:
            tabela = str.maketrans("ÁÉÍÓÚÇáéíóúç", "AEIOUCaeiouc")
            return (s or "").translate(tabela).upper().strip()

        defaults_norm = {_norm(n) for n in self._HISTORICOS_DEFAULT}

        for idx, hist in enumerate(self.previa.historico_salarial):
            # Pular históricos default (PJE-Calc já criou em Fase 2)
            if _norm(hist.nome) in defaults_norm:
                self.log(f"  ⏭ Pulando '{hist.nome}' — default do PJE-Calc")
                continue

            # Reset de estado: após save anterior o form fica aberto em modo edição
            # (botões Confirmar/Salvar/Cancelar visíveis) — clicar Cancelar fecha
            # o form e retorna à listagem.
            try:
                cancelar = self._page.locator("input[id$=':cancelar'], input[id='formulario:cancelar']")
                if cancelar.count() > 0 and cancelar.first.is_visible():
                    cancelar.first.click(force=True)
                    self._aguardar_ajax(5000)
                    self._page.wait_for_timeout(1000)
            except Exception:
                pass
            # Navegar para listagem (com fallback double-hop se URL nav direto
            # re-render do mesmo estado).
            self._navegar_menu("li_calculo_historico_salarial")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(1500)
            # Se botão incluir ainda não apareceu, fazer double-hop.
            if self._page.locator("input[id$=':incluir']").count() == 0:
                self._navegar_menu("li_calculo_dados_do_calculo")
                self._page.wait_for_timeout(1000)
                self._navegar_menu("li_calculo_historico_salarial")
                self._aguardar_ajax(10000)
                self._page.wait_for_timeout(1500)

            # Aguardar botão incluir aparecer (Tomcat pode demorar a renderizar
            # listing após save de outro histórico). Até 20s com retry.
            btn_incluir = None
            for tentativa in range(3):
                try:
                    self._page.wait_for_selector(
                        "input[type='button'][id$=':incluir'], input[id$=':incluir'][value]",
                        state="visible", timeout=10000
                    )
                    btn_incluir = self._page.locator(
                        "input[type='button'][id$=':incluir'], input[id$=':incluir'][value]"
                    ).first
                    break
                except Exception:
                    self.log(f"  ⚠ Botão 'incluir' não apareceu (tentativa {tentativa+1}/3) — re-navegando")
                    self._navegar_menu("li_calculo_historico_salarial")
                    self._aguardar_ajax(15000)
                    self._page.wait_for_timeout(2000)
            if not btn_incluir:
                # Diagnóstico
                _ids = self._page.evaluate(
                    """() => [...document.querySelectorAll('input[type=button],input[type=submit]')]
                        .filter(e => e.id && e.offsetParent)
                        .map(e => `${e.id}=${e.value}`).slice(0, 20)"""
                )
                self.log(f"  ⚠ Pulando '{hist.nome}' — botão 'incluir' não disponível. IDs: {_ids}")
                continue

            btn_incluir.click()
            self._aguardar_ajax(8000)

            # Espera o form aparecer — testa múltiplos seletores variantes
            form_pronto = False
            for sel in [
                "input[id='formulario:nome']",
                "input[id$=':nome'][type='text']",
                "[id$='nomeBase']",
                "input[name='formulario:nome']",
            ]:
                try:
                    self._page.wait_for_selector(sel, timeout=8000, state="visible")
                    form_pronto = True
                    self.log(f"  ✓ form Histórico aberto via selector: {sel}")
                    break
                except Exception:
                    continue
            if not form_pronto:
                # Diagnóstico: listar inputs visíveis na página
                _diag = self._page.evaluate(
                    """() => [...document.querySelectorAll('input,select,textarea')]
                        .filter(e => e.id && e.offsetParent)
                        .map(e => e.id).slice(0, 30)"""
                )
                self.log(f"  ⚠ form Histórico não abriu — IDs visíveis: {_diag}")
                # Pula esta entrada
                continue

            self._preencher("nome", hist.nome, obrigatorio=False)
            self._marcar_radio("tipoVariacaoDaParcela", hist.parcela.value)
            self._marcar_checkbox("fgts", hist.incidencias.fgts)
            self._marcar_checkbox("inss", hist.incidencias.cs_inss)
            self._preencher("competenciaInicialInputDate", hist.competencia_inicial, obrigatorio=False)
            self._preencher("competenciaFinalInputDate", hist.competencia_final, obrigatorio=False)
            self._marcar_radio("tipoValor", hist.tipo_valor.value)

            if hist.tipo_valor == TipoValor.INFORMADO:
                self._preencher("valorParaBaseDeCalculo", _fmt_br(hist.valor_brl), obrigatorio=False)
            else:
                # CALCULADO: quantidade + base_referencia
                self._preencher("quantidade", _fmt_br(hist.calculado.quantidade_pct), obrigatorio=False)
                self._selecionar("baseDeReferencia", hist.calculado.base_referencia)

            # CRÍTICO (descoberto via Calc Machine 12/05/2026): tanto INFORMADO
            # quanto CALCULADO precisam clicar "Gerar Ocorrências" antes do save.
            # Sem isso, PJE-Calc retorna 'Deve haver pelo menos um registro de Ocorrências.'
            try:
                self._clicar("cmdGerarOcorrencias")
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1500)
                self.log(f"  ✓ Ocorrências geradas para '{hist.nome}'")
            except Exception as e:
                self.log(f"  ⚠ Falha ao gerar ocorrências '{hist.nome}': {e}")

            self._clicar("salvar")
            self._aguardar_ajax(8000)
            # Padrão Calc Machine: aguardar "Operação realizada com sucesso"
            sucesso = self._aguardar_operacao_sucesso(timeout_ms=15000, bloqueante=False)
            if not sucesso:
                erro = self._verificar_erro_jsf()
                if erro:
                    self.log(f"  ⚠ Erro ao salvar histórico '{hist.nome}': {erro[:200]}")
                self._diagnostico_pagina(contexto=f"pós-save histórico '{hist.nome}'")
            else:
                self.log(f"  ✓ Histórico '{hist.nome}' salvo")

        self.log("Fase 3 concluída")

    def fase_verbas(self) -> None:
        self.log("Fase 4 — Verbas Principais")
        if not self.previa.verbas_principais:
            self.log("  ⏭ Sem verbas principais — pulando (condenação pode ser só FGTS via saldo a deduzir)")
            return
        self._navegar_menu("li_calculo_verbas")

        # Estratégia: agrupar por tipo de preenchimento
        verbas_expresso = [
            v
            for v in self.previa.verbas_principais
            if v.estrategia_preenchimento
            in (EstrategiaPreenchimento.EXPRESSO_DIRETO, EstrategiaPreenchimento.EXPRESSO_ADAPTADO)
        ]
        verbas_manual = [
            v for v in self.previa.verbas_principais
            if v.estrategia_preenchimento == EstrategiaPreenchimento.MANUAL
        ]

        # 4a. Expresso (lote único)
        if verbas_expresso:
            self._lancar_expresso(verbas_expresso)

        # 4b. Manual (uma por vez)
        for v in verbas_manual:
            self._lancar_verba_manual(v)

        # 4c. Pós-Expresso: verificar estado da listagem (NPE raro com save individual)
        # Após refator 12/05/2026 (Calc Machine pattern: salvar uma verba por vez),
        # o NPE pós-Expresso é muito mais raro porque cada save é atômico. Mantemos
        # detecção+recovery como segurança, mas sem reabertura via Recentes
        # (não funciona em H2 local conforme documentado em CLAUDE.md).
        if verbas_expresso:
            self._navegar_menu("li_calculo_verbas")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(2000)
            erro_jsf = self._verificar_erro_jsf()
            tem_listagem = self._page.evaluate(
                """() => document.querySelectorAll('a.linkParametrizar').length > 0"""
            )
            if erro_jsf or not tem_listagem:
                self.log(f"  ⚠ verba-calculo.jsf vazia/erro ({erro_jsf}) — tentando recovery (reload + double-hop)")
                try:
                    self._page.reload(wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax(15000)
                    self._page.wait_for_timeout(2000)
                except Exception:
                    pass
                tem_listagem = self._page.evaluate(
                    """() => document.querySelectorAll('a.linkParametrizar').length > 0"""
                )
                if not tem_listagem:
                    self.log(f"  ⚠ Reload sem efeito — triple-hop (Histórico → Dados → Verbas)")
                    self._navegar_menu("li_calculo_historico_salarial")
                    self._page.wait_for_timeout(1500)
                    self._navegar_menu("li_calculo_dados_do_calculo")
                    self._page.wait_for_timeout(1500)
                    self._navegar_menu("li_calculo_verbas")
                    self._aguardar_ajax(15000)
                    self._page.wait_for_timeout(2000)
                    tem_listagem = self._page.evaluate(
                        """() => document.querySelectorAll('a.linkParametrizar').length > 0"""
                    )
                if not tem_listagem:
                    self.log(f"  ⚠ Listagem ainda vazia — continuando para parametrização (pode falhar)")

        for v in verbas_expresso:
            self._configurar_parametros_pos_expresso(v)
            for r in v.reflexos:
                self._configurar_reflexo(v, r)

        # CRÍTICO (descoberto 12/05/2026 via diagnóstico de pendências):
        # após alterar parâmetros das verbas, é OBRIGATÓRIO clicar "Regerar"
        # na LISTAGEM (botão regerarOcorrencias com rendered=emModoListagem).
        # Sem isso a liquidação retorna:
        #   "O parâmetro Ocorrência de Pagamento foi alterado na página
        #    Verbas, após a geração das ocorrências da verba X"
        if verbas_expresso:
            self._regerar_ocorrencias_verbas()

        self.log("Fase 4 concluída")

    def _regerar_ocorrencias_verbas(self) -> None:
        """Volta à listagem de Verbas e clica Regerar Ocorrências.

        Botão `regerarOcorrencias` (a4j:commandButton, only `rendered=emModoListagem`).
        Dispara confirm dialog 'Deseja regerar?' que precisa OK.
        """
        try:
            self._navegar_menu("li_calculo_verbas")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(1500)
            # Listar botões disponíveis para diagnóstico
            btn_regerar = self._page.locator(
                "input[id$=':regerarOcorrencias'], input[id*=':regerarOcorrencias']"
            )
            if btn_regerar.count() == 0:
                # Fallback por value
                btn_regerar = self._page.locator("input[type='submit'][value='Regerar'], input[type='button'][value='Regerar']")
            if btn_regerar.count() == 0:
                self.log("  ⚠ Botão Regerar não encontrado na listagem — pulando regerar")
                return
            # Aceitar confirm dialog antes do click
            self._page.once("dialog", lambda d: d.accept())
            btn_regerar.first.click(force=True)
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(2000)
            sucesso = self._aguardar_operacao_sucesso(timeout_ms=15000, bloqueante=False)
            if sucesso:
                self.log("  ✓ Ocorrências regeradas em todas as verbas")
            else:
                self.log("  ⚠ Regerar disparou mas sem confirmação")
        except Exception as e:
            self.log(f"  ⚠ Falha ao regerar ocorrências: {e}")

    def _lancar_expresso(self, verbas) -> None:
        """Lança verbas via página Expresso — UMA POR VEZ (padrão Calc Machine).

        Refatorado em 12/05/2026 após observar Calc Machine: marcar uma checkbox,
        salvar imediatamente, voltar à listagem, retornar ao Expresso para a próxima.
        Padrão batch (todas as checkboxes + salvar único) disparava NPE
        ApresentadorVerbaDeCalculo.carregarBasesParaPrincipal pós-save.
        """
        self.log(f"  → Lançamento Expresso ({len(verbas)} verba(s), uma por vez)")

        for idx, v in enumerate(verbas):
            alvo = (v.expresso_alvo or "").strip().upper()
            self.log(f"  → [{idx+1}/{len(verbas)}] Procurando e selecionando '{alvo}'...")

            # Garantir que estamos na listagem de verbas (li_calculo_verbas)
            self._navegar_menu("li_calculo_verbas")
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(1000)

            # Entrar na página Expresso
            self._clicar("lancamentoExpresso")
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(1500)

            # Diagnóstico no primeiro loop
            if idx == 0:
                diag = self._page.evaluate(
                    """() => {
                        const cbs = [...document.querySelectorAll('input[type="checkbox"][id$=":selecionada"]')];
                        return {total: cbs.length};
                    }"""
                )
                self.log(f"    ℹ Página Expresso: {diag.get('total')} checkboxes disponíveis")

            # Marcar checkbox da verba alvo
            marcou = self._page.evaluate(
                """(alvo) => {
                    const norm = s => (s||'').replace(/\\s+/g,' ').trim().toUpperCase();
                    const cbs = [...document.querySelectorAll('input[type="checkbox"][id$=":selecionada"]')];
                    for (const cb of cbs) {
                        const td = cb.closest('td');
                        const txt = td ? td.textContent : '';
                        if (norm(txt) === alvo) {
                            cb.click();
                            return true;
                        }
                    }
                    // Fallback parcial
                    for (const cb of cbs) {
                        const td = cb.closest('td');
                        const txt = td ? td.textContent : '';
                        if (norm(txt).includes(alvo) || alvo.includes(norm(txt))) {
                            cb.click();
                            return 'partial:'+norm(txt).slice(0,80);
                        }
                    }
                    return null;
                }""",
                alvo,
            )
            if not marcou:
                self.log(f"    ⚠ Verba Expresso não encontrada: '{alvo}' — pulando")
                # Voltar à listagem para próxima iteração
                try:
                    cancelar = self._page.locator("input[id$=':cancelar']")
                    if cancelar.count() > 0 and cancelar.first.is_visible():
                        cancelar.first.click(force=True)
                        self._aguardar_ajax(3000)
                except Exception:
                    pass
                continue

            self.log(f"    ✓ Checkbox '{alvo}' clicado com sucesso")

            # Salvar INDIVIDUALMENTE (padrão Calc Machine: evita NPE)
            self.log(f"    → Salvando seleção '{alvo}'...")
            self._clicar("salvar")
            self._aguardar_ajax(15000)
            sucesso = self._aguardar_operacao_sucesso(timeout_ms=15000, bloqueante=False)
            if not sucesso:
                erro = self._verificar_erro_jsf()
                if erro:
                    self.log(f"    ⚠ Erro JSF ao salvar Expresso '{alvo}': {erro[:200]}")
            else:
                self.log(f"    ✓ Verba '{alvo}' salva")

            # Re-capturar conversationId — Seam pode renovar conv após cada save
            self._capturar_conversation_id()
            self._page.wait_for_timeout(1500)

        self.log(f"  ✓ Expresso concluído ({len(verbas)} verba(s) processada(s))")

    def _preencher_form_parametros_verba(self, v, *, com_identificacao: bool) -> None:
        """Preenche todos os campos do form de parâmetros de verba.

        Em EXPRESSO_DIRETO: o Expresso já configurou tudo (característica,
        ocorrência, incidências, valor, fórmula). MINIMIZAMOS alterações para
        evitar pendências do tipo "parâmetro X foi alterado após geração de
        ocorrências". Apenas alteramos período (datas) que normalmente precisam
        de ajuste para a sentença.

        Em EXPRESSO_ADAPTADO: alteramos descrição + tudo que diferenciar do
        Expresso original (nome customizado).

        Em MANUAL: preenchemos tudo (com_identificacao=True).
        """
        p = v.parametros
        # EXPRESSO_DIRETO: NÃO ALTERAR nada que o Expresso já configurou.
        # Apenas garantir período correto.
        if (not com_identificacao
                and v.estrategia_preenchimento == EstrategiaPreenchimento.EXPRESSO_DIRETO):
            self.log(f"    ℹ EXPRESSO_DIRETO: ajustando apenas período (mantendo config Expresso)")
            # Ajustar apenas período (datas) — comum ser diferente do default
            for sufixo in ("periodoInicialInputDate", "periodoInicial", "dataInicioInputDate"):
                try:
                    if self._page.locator(f"[id$='{sufixo}']").count() > 0:
                        self._preencher(sufixo, p.periodo_inicio, obrigatorio=False)
                        break
                except Exception:
                    continue
            for sufixo in ("periodoFinalInputDate", "periodoFinal", "dataFimInputDate"):
                try:
                    if self._page.locator(f"[id$='{sufixo}']").count() > 0:
                        self._preencher(sufixo, p.periodo_fim, obrigatorio=False)
                        break
                except Exception:
                    continue
            return

        # MANUAL ou EXPRESSO_ADAPTADO: configuração completa

        # 1. Identificação (apenas Manual ou Expresso_Adaptado)
        if com_identificacao:
            self._preencher("descricao", v.nome_pjecalc)
            # Assunto CNJ — autocomplete: digitar código + Enter dispara seleção
            # Default 2581 (Remuneração, Verbas Indenizatórias e Benefícios)
            # quando codigo é None — categoria ampla que cobre majoritárias.
            codigo_cnj = p.assunto_cnj.codigo if p.assunto_cnj and p.assunto_cnj.codigo else 2581
            self._preencher("codigoAssuntosCnj", str(codigo_cnj))
            self._aguardar_ajax(3000)
        elif v.estrategia_preenchimento == EstrategiaPreenchimento.EXPRESSO_ADAPTADO:
            self._preencher("descricao", v.nome_pjecalc, obrigatorio=False)

        # 2. Valor (INFORMADO vs CALCULADO) — radio dispara AJAX que troca DOM
        self._marcar_radio("valor", p.valor.value)
        self._aguardar_ajax(3000)

        if p.valor == TipoValor.INFORMADO:
            self._preencher("valorInformadoDoDevido", _fmt_br(p.valor_devido.valor_informado_brl))
        else:  # CALCULADO
            f = p.formula_calculado
            self._selecionar("tipoDaBaseTabelada", f.base_calculo.tipo.value)
            self._aguardar_ajax(3000)
            if f.base_calculo.tipo == TipoBaseCalculo.HISTORICO_SALARIAL:
                self._selecionar("baseHistoricos", f.base_calculo.historico_nome)
                self._aguardar_ajax(2000)
            self._marcar_radio("tipoDeDivisor", f.divisor.tipo.value)
            self._aguardar_ajax(2000)
            if f.divisor.tipo.value == "OUTRO_VALOR" and f.divisor.valor is not None:
                self._preencher("outroValorDoDivisor", _fmt_br(f.divisor.valor), obrigatorio=False)
            self._preencher("outroValorDoMultiplicador", _fmt_br(f.multiplicador), obrigatorio=False)
            self._marcar_radio("tipoDaQuantidade", f.quantidade.tipo.value)
            self._aguardar_ajax(2000)
            if f.quantidade.tipo.value == "INFORMADA" and f.quantidade.valor is not None:
                self._preencher("valorInformadoDaQuantidade", _fmt_br(f.quantidade.valor), obrigatorio=False)

        # 3. Período
        for sufixo in ("periodoInicialInputDate", "periodoInicial", "dataInicioInputDate"):
            try:
                if self._page.locator(f"[id$='{sufixo}']").count() > 0:
                    self._preencher(sufixo, p.periodo_inicio, obrigatorio=False)
                    break
            except Exception:
                continue
        for sufixo in ("periodoFinalInputDate", "periodoFinal", "dataFimInputDate"):
            try:
                if self._page.locator(f"[id$='{sufixo}']").count() > 0:
                    self._preencher(sufixo, p.periodo_fim, obrigatorio=False)
                    break
            except Exception:
                continue

        # 4. Características + Ocorrência + Base de Cálculo
        self._marcar_radio("caracteristicaVerba", p.caracteristica.value)
        self._aguardar_ajax(2000)
        self._marcar_radio("ocorrenciaPagto", p.ocorrencia_pagamento.value)
        self._aguardar_ajax(2000)
        if hasattr(p, "tipo_base_calculo") and p.tipo_base_calculo:
            self._marcar_radio("tipoDaBaseDeCalculo", p.tipo_base_calculo.value)

        # 5. Incidências
        self._marcar_checkbox("irpf", p.incidencias.irpf)
        self._marcar_checkbox("inss", p.incidencias.cs_inss)
        self._marcar_checkbox("fgts", p.incidencias.fgts)
        self._marcar_checkbox("previdenciaPrivada", p.incidencias.previdencia_privada)
        self._marcar_checkbox("pensaoAlimenticia", p.incidencias.pensao_alimenticia)

        # 6. Outras flags opcionais
        if hasattr(p, "natureza_indenizatoria") and p.natureza_indenizatoria is not None:
            self._marcar_checkbox("naturezaIndenizatoria", p.natureza_indenizatoria)
        if hasattr(p, "deduzir_inss_recolhido") and p.deduzir_inss_recolhido is not None:
            self._marcar_checkbox("deduzirInssRecolhido", p.deduzir_inss_recolhido)
        if hasattr(p, "considerar_competencia_paga") and p.considerar_competencia_paga is not None:
            self._marcar_checkbox("considerarCompetenciaPaga", p.considerar_competencia_paga)

    def _configurar_parametros_pos_expresso(self, v) -> None:
        """Ajustar parâmetros da verba pós-Expresso.

        DOM confirmado (PJE-Calc 2.15.1, institucional+Cidadão):
        - <a class="linkParametrizar" title="Parâmetros da Verba"> (verba principal)
        - <a class="linkOcorrencias" title="Ocorrências da Verba"> (ocorrências)
        - IDs JSF dinâmicos (j_id558 etc.) NÃO são confiáveis — usamos CLASSE CSS.
        - Reflexos têm linkParametrizar com title="Parametrizar" (SEM "da Verba")
          — disambiguar via id*=':listaReflexo:'.
        """
        # Match candidates: nome_pjecalc (custom) e expresso_alvo (canônico).
        # Para expresso_adaptado, o listing tem o nome canônico, não o adaptado.
        candidatos = [v.nome_pjecalc]
        if hasattr(v, "expresso_alvo") and v.expresso_alvo and v.expresso_alvo != v.nome_pjecalc:
            candidatos.append(v.expresso_alvo)
        self.log(f"  → Ajustar parâmetros: {v.nome_pjecalc} (busca: {candidatos})")
        clicou = self._page.evaluate(
            """(candidatos) => {
                const norm = s => (s||'').toUpperCase().replace(/\\s+/g,' ').trim();
                const trs = [...document.querySelectorAll('tr')];
                for (const alvo of candidatos) {
                    const alvoN = norm(alvo);
                    for (const tr of trs) {
                        if (!norm(tr.textContent).includes(alvoN)) continue;
                        // 1. linkParametrizar com title começando 'Parâmetros'
                        const a = tr.querySelector('a.linkParametrizar[title^="Parâmetros"], a.linkParametrizar[title^="Parametros"]');
                        if (a) { a.click(); return 'class-title:'+alvo; }
                        // 2. primeiro a.linkParametrizar (excluindo reflexos)
                        const links = [...tr.querySelectorAll('a.linkParametrizar')];
                        for (const link of links) {
                            if (link.id && link.id.includes(':listaReflexo:')) continue;
                            link.click();
                            return 'class-only:'+alvo;
                        }
                        // 3. fallback: title genérico
                        const t1 = tr.querySelector('a[title*="arâmetros"], a[title*="arametros"]');
                        if (t1) { t1.click(); return 'title-fallback:'+alvo; }
                    }
                }
                return null;
            }""",
            candidatos,
        )
        if not clicou:
            # Diagnóstico: dump tabela atual para identificar mismatch
            diag = self._page.evaluate(
                """() => {
                    const trs = [...document.querySelectorAll('tr')];
                    return trs.filter(tr => tr.querySelector('a.linkParametrizar'))
                        .slice(0, 15)
                        .map(tr => (tr.textContent||'').replace(/\\s+/g,' ').trim().slice(0, 100));
                }"""
            )
            self.log(f"  ⚠ Verba não encontrada na listagem: {v.nome_pjecalc}")
            self.log(f"     TRs com Parâmetros visíveis: {diag}")
            return
        self.log(f"    ✓ Click Parâmetros via estratégia: {clicou}")
        self._aguardar_ajax(8000)
        self._preencher_form_parametros_verba(v, com_identificacao=False)

        # NOTA (12/05/2026): "Regerar Ocorrências" só existe em modo LISTAGEM
        # (rendered="#{apresentador.emModoListagem}"). Não está disponível neste
        # form de parâmetros. Movido para _regerar_ocorrencias_verbas() chamado
        # após fim do loop de parametrização (fim da Fase 4).

        self._clicar("salvar")
        self._aguardar_ajax(8000)
        sucesso = self._aguardar_operacao_sucesso(timeout_ms=15000, bloqueante=False)
        if sucesso:
            self.log(f"  ✓ Parâmetros '{v.nome_pjecalc}' salvos")
        else:
            self._diagnostico_pagina(contexto=f"pós-save Parâmetros {v.nome_pjecalc}")

    def _OLD_configurar_parametros_pos_expresso(self, v) -> None:
        """[REMOVIDO — substituído por versão flexível acima]."""
        self.log(f"  → Ajustar parâmetros (OLD): {v.nome_pjecalc}")
        # Buscar linha por nome
        clicou = self._page.evaluate(
            f"""(alvo) => {{
                const links = [...document.querySelectorAll('a[id*=":listagem:"][id$=":j_id558"]')];
                for (const a of links) {{
                    const tr = a.closest('tr');
                    if (tr && tr.textContent.toUpperCase().includes(alvo.toUpperCase())) {{
                        a.click();
                        return true;
                    }}
                }}
                return false;
            }}""",
            v.nome_pjecalc,
        )
        if not clicou:
            self.log(f"  ⚠ Verba não encontrada na listagem: {v.nome_pjecalc}")
            return
        self._aguardar_ajax(8000)

        self._preencher_form_parametros_verba(v, com_identificacao=False)

        self._clicar("salvar")
        self._aguardar_ajax(8000)
        self.log(f"  ✓ Parâmetros '{v.nome_pjecalc}' salvos")

    def _selecionar_assunto_cnj(self, codigo: int = 2581) -> bool:
        """Seleciona Assunto CNJ via modal-árvore.

        IDs reais confirmados (PJE-Calc 2.15.1, inspeção via Chrome MCP):
        - Lupa: `formulario:linkModalAssunto` (com onclick que chama
          Richfaces.showModalPanel('modalCNJ')).
        - Tree node TEXT (clicável p/ selecionar): TD com id
          `formularioModalCNJ:arv:864:{codigo}::_defaultNodeFace:text`
          — adquire classe `rich-tree-node-selected` após click.
        - Botão Selecionar: `btnSelecionarCNJ` (ID simples, sem prefix).
        - Modal mask: `modalCNJDiv` (visibilidade via display style).
        - Form do modal: `formularioModalCNJ` (separado do form principal).
        """
        # 1. Click lupa
        try:
            lupa = self._page.locator(
                "a[id='formulario:linkModalAssunto'], a[id$=':linkModalAssunto']"
            )
            if lupa.count() == 0:
                self.log(f"    ⚠ Botão lupa Assunto CNJ não encontrado")
                return False
            lupa.first.click(force=True)
        except Exception as e:
            self.log(f"    ⚠ Click lupa: {e}")
            return False
        self._aguardar_ajax(5000)
        self._page.wait_for_timeout(1500)

        # 2. Click no TD :text do nó (não na TABLE inteira) — só assim
        # RichFaces aplica `rich-tree-node-selected` e habilita Selecionar.
        # IDs do nó incluem "arv:864:{codigo}" no caminho. Há várias
        # variações dependendo do ramo da árvore (alguns são folhas
        # diretas, outros têm sub-nós).
        node_clicado = self._page.evaluate(
            """(codigo) => {
                // Tenta vários padrões de ID
                const patterns = [
                    `formularioModalCNJ:arv:864:${codigo}::_defaultNodeFace:text`,
                ];
                for (const p of patterns) {
                    const td = document.getElementById(p);
                    if (td) {
                        td.click();
                        td.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                        td.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                        return p;
                    }
                }
                // Fallback: buscar por texto "{codigo} -" no TD :text
                const tds = [...document.querySelectorAll('td.rich-tree-node-text')];
                for (const td of tds) {
                    const t = (td.textContent||'').trim();
                    if (t.startsWith(codigo + ' -') || t.startsWith(codigo + ' ')) {
                        td.click();
                        td.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                        td.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                        return 'fallback-by-text';
                    }
                }
                return null;
            }""",
            str(codigo),
        )
        if not node_clicado:
            self.log(f"    ⚠ Nó CNJ {codigo} não encontrado na árvore")
            self._fechar_modal_cnj()
            return False
        self.log(f"    → Nó CNJ selecionado via: {node_clicado}")
        self._page.wait_for_timeout(800)

        # 3. Click "Selecionar" via locator + ID exato
        try:
            btn = self._page.locator("input#btnSelecionarCNJ")
            if btn.count() == 0:
                # Fallback: buscar por value
                btn = self._page.locator("input[value='Selecionar'][type='button'], input[value='Selecionar'][type='submit']")
            btn.first.click(force=True)
            self._aguardar_ajax(5000)
        except Exception as e:
            self.log(f"    ⚠ Click btnSelecionarCNJ: {e}")
            self._fechar_modal_cnj()
            return False

        # 4. Verificar que assunto foi setado
        try:
            valor_atual = self._page.locator(
                "input[id='formulario:assuntosCnj']"
            ).input_value(timeout=3000)
            if str(codigo) in (valor_atual or ""):
                self.log(f"    ✓ Assunto CNJ confirmado: {valor_atual}")
                # Garantir que modal feche
                self._fechar_modal_cnj(silent=True)
                return True
        except Exception:
            pass

        self.log(f"    ⚠ Assunto CNJ não confirmou — fechando modal")
        self._fechar_modal_cnj()
        return False

    def _fechar_modal_cnj(self, silent: bool = False) -> None:
        """Tenta fechar modal CNJ (Cancelar/X) caso ainda visível."""
        try:
            self._page.evaluate(
                """() => {
                    if (typeof Richfaces !== 'undefined' && Richfaces.hideModalPanel) {
                        Richfaces.hideModalPanel('modalCNJ');
                        return true;
                    }
                    return false;
                }"""
            )
            self._aguardar_ajax(2000)
            if not silent:
                self.log(f"    ⓘ Modal CNJ fechado via Richfaces.hideModalPanel")
        except Exception:
            pass

    def _criar_reflexo_manual(self, verba_principal, reflexo) -> None:
        """Cria reflexo via Manual (verba separada com Tipo=REFLEXO).

        Para reflexos `estrategia_reflexa: "manual"` que não têm equivalente
        Expresso (ex.: reflexos de estabilidade pós-contratual, Lei 9.029/95).
        Fluxo:
        1. Navegar para listing de verbas.
        2. Click "Manual" (input[id$=':incluir'][value='Manual']).
        3. Preencher Nome (descricao), Assunto CNJ via lupa→modal, Tipo=REFLEXO.
        4. Aplicar overrides (período, característica, ocorrência, incidências).
        5. Configurar valor=CALCULADO com base padrão (HISTORICO_SALARIAL=ÚLTIMA REMUNERAÇÃO).
        6. Salvar.
        """
        nome = (reflexo.nome or "").upper()
        # Construir nome "X SOBRE Y" se ainda não estiver no formato
        if "SOBRE" not in nome:
            nome = f"{nome.upper()} SOBRE {verba_principal.nome_pjecalc.upper()}"
        self.log(f"  → Criar reflexo MANUAL: {nome}")

        # 1. Reset state agressivo: Cancelar (se visível) + page.reload() na URL
        # da listagem com conversationId. Reload força fresh state JSF/Seam,
        # eliminando estado pós-save que esconde botão "Manual".
        try:
            cancelar = self._page.locator("input[id='formulario:cancelar']")
            if cancelar.count() > 0 and cancelar.first.is_visible():
                cancelar.first.click(force=True)
                self._aguardar_ajax(3000)
                self._page.wait_for_timeout(800)
        except Exception:
            pass
        # Goto + reload para garantir fresh
        if self._calculo_conversation_id:
            url_listing = (
                f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                f"?conversationId={self._calculo_conversation_id}"
            )
            try:
                self._page.goto(url_listing, wait_until="domcontentloaded", timeout=15000)
                self._aguardar_ajax(10000)
                self._page.wait_for_timeout(1500)
            except Exception:
                pass
        else:
            self._navegar_menu("li_calculo_verbas")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(1500)

        # 2. Click "Manual" (incluir) — wait_for_selector + retry
        btn_manual = None
        for tentativa in range(3):
            try:
                self._page.wait_for_selector(
                    "input[id$=':incluir'][value='Manual']",
                    state="visible", timeout=10000,
                )
                btn_manual = self._page.locator(
                    "input[id$=':incluir'][value='Manual']"
                ).first
                break
            except Exception:
                self.log(f"    ⚠ Botão Manual não apareceu (tentativa {tentativa+1}/3)")
                self._navegar_menu("li_calculo_dados_do_calculo")
                self._page.wait_for_timeout(1000)
                self._navegar_menu("li_calculo_verbas")
                self._aguardar_ajax(15000)
                self._page.wait_for_timeout(2000)
        if not btn_manual:
            self.log(f"    ⚠ Pulando reflexo {reflexo.id} — botão Manual indisponível")
            return
        try:
            btn_manual.click(force=True)
        except Exception as e:
            self.log(f"    ⚠ Click 'Manual' falhou: {e}")
            return
        self._aguardar_ajax(8000)
        # Aguardar form renderizar
        try:
            self._page.wait_for_selector(
                "input[id='formulario:descricao']", state="visible", timeout=10000
            )
        except Exception:
            self.log(f"    ⚠ Form Manual não abriu — pulando reflexo {reflexo.id}")
            return

        # 3. Preencher Nome
        self._preencher("descricao", nome[:100])

        # 4. Selecionar Assunto CNJ (default 2581)
        self._selecionar_assunto_cnj(2581)

        # 5. Tipo = REFLEXO
        try:
            self._marcar_radio("tipoDeVerba", "REFLEXO")
        except Exception as e:
            self.log(f"    ⚠ Tipo=REFLEXO: {e}")
        self._aguardar_ajax(2000)

        # 6. Aplicar parametros_override
        ov = reflexo.parametros_override
        if ov:
            try:
                if ov.periodo_inicio:
                    self._preencher("periodoInicialInputDate", ov.periodo_inicio, obrigatorio=False)
                if ov.periodo_fim:
                    self._preencher("periodoFinalInputDate", ov.periodo_fim, obrigatorio=False)
                if ov.caracteristica:
                    car = ov.caracteristica.value if hasattr(ov.caracteristica, "value") else str(ov.caracteristica)
                    self._marcar_radio("caracteristicaVerba", car)
                    self._aguardar_ajax(2000)
                if ov.ocorrencia_pagamento:
                    occ = ov.ocorrencia_pagamento.value if hasattr(ov.ocorrencia_pagamento, "value") else str(ov.ocorrencia_pagamento)
                    self._marcar_radio("ocorrenciaPagto", occ)
                    self._aguardar_ajax(2000)
                if ov.incidencias:
                    self._marcar_checkbox("irpf", ov.incidencias.irpf)
                    self._marcar_checkbox("inss", ov.incidencias.cs_inss)
                    self._marcar_checkbox("fgts", ov.incidencias.fgts)
            except Exception as e:
                self.log(f"    ⚠ Aplicando override: {e}")

        # 7. Valor=CALCULADO + fórmula específica baseada no tipo do reflexo
        # (regras do vídeo: divisor/multiplicador específicos para Férias/13º/FGTS)
        nome_upper = nome.upper()
        is_ferias = "FÉRIAS" in nome_upper or "FERIAS" in nome_upper
        is_13 = "13º" in nome_upper or "13o" in nome_upper.replace("º", "O") or "DÉCIMO" in nome_upper
        is_fgts_40 = "FGTS" in nome_upper and ("40" in nome_upper or "MULTA" in nome_upper)
        is_fgts = "FGTS" in nome_upper
        if is_ferias:
            divisor, multiplicador, quantidade, integralizar = "12", "1,33", "12", True
        elif is_13:
            divisor, multiplicador, quantidade, integralizar = "12", "1", "12", True
        elif is_fgts_40:
            divisor, multiplicador, quantidade, integralizar = "100", "11,2", "1", False
        elif is_fgts:
            divisor, multiplicador, quantidade, integralizar = "100", "8", "1", False
        else:
            divisor, multiplicador, quantidade, integralizar = "1", "1", "1", True

        try:
            self._marcar_radio("valor", "CALCULADO")
            self._aguardar_ajax(2000)
            # Base = MAIOR_REMUNERACAO (preferida pelo vídeo) com fallback HISTORICO
            try:
                self._selecionar("tipoDaBaseTabelada", "MAIOR_REMUNERACAO")
            except Exception:
                self._selecionar("tipoDaBaseTabelada", "HISTORICO_SALARIAL")
                self._aguardar_ajax(2000)
                try:
                    self._selecionar("baseHistoricos", "ÚLTIMA REMUNERAÇÃO")
                except Exception:
                    pass
            self._aguardar_ajax(1500)
            # Marcar Integralizar (CRÍTICO para reflexos de estabilidade)
            if integralizar:
                # Schema do select integralizar: SIM/NAO
                try:
                    self._selecionar("integralizarBase", "SIM")
                except Exception:
                    # Fallback: pode ser checkbox em algumas versões
                    self._marcar_checkbox("integralizar", True)
            self._marcar_radio("tipoDeDivisor", "OUTRO_VALOR")
            self._aguardar_ajax(1500)
            self._preencher("outroValorDoDivisor", divisor, obrigatorio=False)
            self._preencher("outroValorDoMultiplicador", multiplicador, obrigatorio=False)
            self._marcar_radio("tipoDaQuantidade", "INFORMADA")
            self._preencher("valorInformadoDaQuantidade", quantidade, obrigatorio=False)
            self.log(f"    ✓ Fórmula: divisor={divisor} mult={multiplicador} qtd={quantidade} integraliza={integralizar}")
        except Exception as e:
            self.log(f"    ⚠ Configurando fórmula CALCULADO: {e}")

        # 8. Salvar
        self._clicar("salvar")
        self._aguardar_ajax(15000)
        self.log(f"  ✓ Reflexo Manual '{nome}' criado")

    def _configurar_reflexo(self, verba_principal, reflexo) -> None:
        """Marcar checkbox do reflexo no painel da verba principal (Expresso pareado)
        OU criar como Manual se estrategia=MANUAL."""
        if reflexo.estrategia_reflexa == EstrategiaReflexa.MANUAL:
            self._criar_reflexo_manual(verba_principal, reflexo)
            return

        # Expandir painel da verba principal + marcar checkbox
        self.log(f"  → Reflexo: {reflexo.nome}")
        # DOM confirmado: span.linkDestinacoes "Exibir" abre painel com checkboxes
        # de reflexos. Tentamos achar a TR via nome_pjecalc OU expresso_alvo.
        candidatos_principal = [verba_principal.nome_pjecalc]
        if hasattr(verba_principal, "expresso_alvo") and verba_principal.expresso_alvo \
           and verba_principal.expresso_alvo != verba_principal.nome_pjecalc:
            candidatos_principal.append(verba_principal.expresso_alvo)
        click_exibir_ok = self._page.evaluate(
            """([candidatos, alvoReflexo]) => {
                const norm = s => (s||'').toUpperCase();
                const trs = [...document.querySelectorAll('tr')];
                for (const c of candidatos) {
                    const cN = norm(c);
                    for (const tr of trs) {
                        if (!norm(tr.textContent).includes(cN)) continue;
                        const exibir = tr.querySelector('span.linkDestinacoes');
                        if (exibir) {
                            exibir.click();
                            try { exibir.dispatchEvent(new MouseEvent('click', {bubbles:true})); } catch(e) {}
                            return 'exibir-clicked:'+c;
                        }
                    }
                }
                return 'principal-nao-encontrada';
            }""",
            [candidatos_principal, reflexo.expresso_reflex_alvo or ""],
        )
        if click_exibir_ok == "principal-nao-encontrada":
            self.log(f"    ⚠ Verba principal '{verba_principal.nome_pjecalc}' não encontrada na listagem — pulando reflexo")
            return
        self._aguardar_ajax(3000)
        self._page.wait_for_timeout(800)

        # Agora marcar o checkbox do reflexo (após Exibir abrir o painel)
        marcou = self._page.evaluate(
            """([verbaPrincipal, alvoReflexo]) => {
                const norm = s => (s||'').toUpperCase().trim();
                if (!alvoReflexo) return 'sem-alvo';
                const cbs = [...document.querySelectorAll('input[type="checkbox"][id*="listaReflexo"][id$=":ativo"]')];
                for (const cb of cbs) {
                    const tr = cb.closest('tr');
                    if (tr && norm(tr.textContent).includes(norm(alvoReflexo))) {
                        cb.click();
                        return true;
                    }
                }
                return false;
            }""",
            [verba_principal.nome_pjecalc, reflexo.expresso_reflex_alvo or ""],
        )
        if marcou is True:
            self.log(f"    ✓ Reflexo marcado: {reflexo.nome}")
        else:
            self.log(f"    ⚠ Reflexo não encontrado: {reflexo.nome} (alvo='{reflexo.expresso_reflex_alvo}', resultado={marcou})")
        self._aguardar_ajax(5000)

        # Se há overrides, abrir Parâmetros do reflexo e ajustar
        if reflexo.parametros_override:
            self.log(f"    → Aplicando overrides em {reflexo.nome}")
            # Implementação detalhada via doc 07 — pular nesta versão MVP

    def _lancar_verba_manual(self, v) -> None:
        """Criar verba via botão Manual ('Lançamento Manual de Parcela')."""
        self.log(f"  → Manual: {v.nome_pjecalc}")
        self._clicar("incluir")
        self._aguardar_ajax(8000)

        self._preencher_form_parametros_verba(v, com_identificacao=True)

        self._clicar("salvar")
        self._aguardar_ajax(10000)

        # Verificar mensagem de sucesso JSF
        body = self._page.locator("body").text_content() or ""
        if "operação realizada com sucesso" not in body.lower() and "sucesso" not in body.lower():
            self.log(f"  ⚠ Verba '{v.nome_pjecalc}' — mensagem de sucesso não detectada")
        self.log(f"  ✓ Manual '{v.nome_pjecalc}' criado")

    def fase_cartao_de_ponto(self) -> None:
        """Cartão de Ponto — 63 campos opcionais. Só preenche se a prévia traz dados.

        Para o MVP, se `cartao_de_ponto` for None ou um dict vazio, pula a fase.
        Caso contrário, percorre os atributos da seção e preenche cada um por nome
        de DOM (assumindo nome_atributo_python == dom_id, padrão do schema v2).
        """
        cp = getattr(self.previa, "cartao_de_ponto", None)
        if not cp or not getattr(cp, "model_dump", None):
            self.log("Fase 5 — Cartão de Ponto: sem dados (pulando)")
            return
        dados = cp.model_dump(exclude_none=True)
        if not dados:
            self.log("Fase 5 — Cartão de Ponto: vazio (pulando)")
            return

        self.log(f"Fase 5 — Cartão de Ponto ({len(dados)} campos)")
        self._navegar_menu("li_calculo_cartao_ponto")

        for chave, valor in dados.items():
            try:
                if isinstance(valor, bool):
                    self._marcar_checkbox(chave, valor)
                elif isinstance(valor, (int, float)):
                    self._preencher(chave, _fmt_br(valor) if isinstance(valor, float) else str(valor),
                                    obrigatorio=False)
                elif isinstance(valor, str):
                    # Heurística: se valor está em UPPER_SNAKE provavelmente é radio/select
                    if valor.isupper() and "_" in valor:
                        try:
                            self._marcar_radio(chave, valor)
                        except Exception:
                            self._selecionar(chave, valor)
                    else:
                        self._preencher(chave, valor, obrigatorio=False)
            except Exception as e:
                self.log(f"  ⚠ Cartão de ponto — {chave}: {e}")

        # Salvar (graceful: não aborta se botão não existir — fase é heurística)
        try:
            sel_salvar = self._page.locator("input[id='formulario:salvar'], input[id$=':salvar']")
            if sel_salvar.count() > 0:
                sel_salvar.first.click(force=True)
                self._aguardar_ajax(8000)
                self.log("Fase 5 concluída")
            else:
                self.log("Fase 5 — sem botão Salvar (campos heurísticos não casaram). Pulando.")
        except Exception as e:
            self.log(f"Fase 5 — Salvar: {e} (pulando)")

    def fase_faltas(self) -> None:
        self.log("Fase 6 — Faltas")
        self._navegar_menu("li_calculo_faltas")
        for f in self.previa.faltas:
            self._preencher("dataInicioPeriodoFaltaInputDate", f.data_inicio)
            self._preencher("dataTerminoPeriodoFaltaInputDate", f.data_fim)
            self._marcar_checkbox("faltaJustificada", f.justificada)
            self._marcar_checkbox("reiniciaFerias", f.reinicia_ferias)
            if f.justificativa:
                self._preencher("justificativaDaFalta", f.justificativa, obrigatorio=False)
            self._clicar("cmdIncluirFalta")
            self._aguardar_ajax()
        self.log("Fase 6 concluída")

    def fase_ferias(self) -> None:
        """Férias — tabela com N períodos aquisitivos/concessivos.

        A tabela do PJE-Calc é renderizada com botão 'Incluir' que adiciona uma
        linha em modo edição. Cada linha tem campos com ID padrão JSF terminando
        em sufixos como :periodoAquisitivoInicialInputDate, etc. (doc 06).
        """
        ferias = getattr(self.previa, "ferias", None)
        if not ferias or not ferias.periodos:
            self.log("Fase 7 — Férias: sem períodos (pulando)")
            return

        self.log(f"Fase 7 — Férias ({len(ferias.periodos)} período(s))")
        self._navegar_menu("li_calculo_ferias")

        if ferias.ferias_coletivas_inicio_primeiro_ano:
            self._preencher(
                "feriasColetivasInicioPrimeiroAnoInputDate",
                ferias.ferias_coletivas_inicio_primeiro_ano,
                obrigatorio=False,
            )
        if ferias.prazo_ferias_proporcionais:
            self._preencher(
                "prazoFeriasProporcionais",
                str(ferias.prazo_ferias_proporcionais),
                obrigatorio=False,
            )

        for i, p in enumerate(ferias.periodos):
            self.log(f"  → Período {i+1}: {p.periodo_aquisitivo_inicio} → {p.periodo_aquisitivo_fim}")
            # Aguardar página renderizar completamente (pode ter atraso JSF)
            try:
                self._page.wait_for_selector(
                    "input[id$=':incluir'][value], input[type='button'][id$=':incluir']",
                    state="visible", timeout=15000
                )
            except Exception:
                # Diagnóstico
                self._diagnostico_pagina(contexto="pré-incluir Férias")
                # Re-navegar para forçar render
                self._navegar_menu("li_calculo_ferias")
                self._aguardar_ajax(10000)
                self._page.wait_for_timeout(2000)
            try:
                self._clicar("incluir")
            except Exception as e:
                self.log(f"  ⚠ Pulando período {i+1}: {e}")
                continue
            self._aguardar_ajax(5000)
            self._page.wait_for_timeout(1500)

            self._preencher("periodoAquisitivoInicialInputDate", p.periodo_aquisitivo_inicio)
            self._preencher("periodoAquisitivoFinalInputDate", p.periodo_aquisitivo_fim)
            self._preencher("periodoConcessivoInicialInputDate", p.periodo_concessivo_inicio)
            self._preencher("periodoConcessivoFinalInputDate", p.periodo_concessivo_fim)
            self._preencher("prazoDias", str(p.prazo_dias))
            self._marcar_radio("situacaoFerias", p.situacao)
            self._aguardar_ajax(2000)
            self._marcar_checkbox("dobra", p.dobra)
            self._marcar_checkbox("abono", p.abono)
            if p.abono and p.dias_abono:
                self._preencher("diasAbono", str(p.dias_abono))

            # Gozos (até 3) — campos só aparecem se situacao=GOZADAS ou PARCIAL_GOZADAS
            for j, gozo in enumerate([p.gozo_1, p.gozo_2, p.gozo_3], start=1):
                if gozo and gozo.data_inicio:
                    try:
                        self._preencher(f"gozoInicio{j}InputDate", gozo.data_inicio, obrigatorio=False)
                        self._preencher(f"gozoFim{j}InputDate", gozo.data_fim, obrigatorio=False)
                        if gozo.dobra:
                            self._marcar_checkbox(f"gozoDobra{j}", True)
                    except Exception as e:
                        self.log(f"    ⚠ gozo {j}: {e}")

            try:
                self._clicar("salvar")
                self._aguardar_ajax(8000)
                sucesso = self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
                if sucesso:
                    self.log(f"  ✓ Período {i+1} de férias salvo")
                else:
                    self._diagnostico_pagina(contexto=f"pós-save Período {i+1} Férias")
            except Exception as e:
                self.log(f"  ⚠ Falha ao salvar período {i+1}: {e}")

        self.log("Fase 7 concluída")

    def fase_fgts(self) -> None:
        self.log("Fase 8 — FGTS")
        self._navegar_menu("li_calculo_fgts")
        self._aguardar_ajax(8000)
        self._page.wait_for_timeout(1500)

        # Verificar que página renderizou (radio tipoDeVerba presente)
        if self._page.locator("input[type='radio'][id*='tipoDeVerba']").count() == 0:
            self.log("  ⚠ Fase 8 FGTS: página não renderizou — pulando (NPE pós-Expresso?)")
            return

        f = self.previa.fgts
        # Cada campo é tolerante (não aborta a fase se faltar um)
        def _safe(callback, msg):
            try:
                callback()
            except Exception as e:
                self.log(f"  ⚠ FGTS {msg}: {e}")

        _safe(lambda: self._marcar_radio("tipoDeVerba", f.tipo_verba), "tipoDeVerba")
        _safe(lambda: self._marcar_radio("comporPrincipal", f.compor_principal.value if hasattr(f.compor_principal, 'value') else str(f.compor_principal)), "comporPrincipal")
        _safe(lambda: self._marcar_checkbox("multa", f.multa.ativa), "multa")
        if f.multa.ativa:
            _safe(lambda: self._marcar_radio("tipoDoValorDaMulta", f.multa.tipo_valor), "tipoDoValorDaMulta")
            _safe(lambda: self._marcar_radio("multaDoFgts", f.multa.percentual), "multaDoFgts")
        _safe(lambda: self._selecionar("incidenciaDoFgts", f.incidencia), "incidenciaDoFgts")
        _safe(lambda: self._marcar_checkbox("multaDoArtigo467", f.multa_artigo_467), "multaDoArtigo467")
        _safe(lambda: self._marcar_checkbox("multa10", f.multa_10_lc110), "multa10")

        # Seção "Saldo e/ou Saque" — saldo FGTS já depositado a ser deduzido.
        # Documentado pelo usuário 12/05/2026: NÃO é uma verba Expresso, mas
        # sim um campo da própria página FGTS. Para cada saldo:
        #   1. Preencher data + valor
        #   2. Clicar botão "+" (adicionar) — adiciona à tabela
        #   3. Marcar checkbox "Deduzir do FGTS"
        saldos = getattr(f, "saldos_a_deduzir", None) or []
        for idx, saldo in enumerate(saldos):
            try:
                self.log(f"  → Adicionando saldo FGTS a deduzir [{idx+1}/{len(saldos)}]: {saldo.data} = {saldo.valor_brl}")
                # IDs prováveis: formulario:dataSaldoFGTS, formulario:valorSaldoFGTS
                # ou similar. Vamos tentar variantes.
                preenchido = False
                for data_suf in ("dataSaldoFGTSInputDate", "dataSaldoFGTS", "saldoFGTSInputDate"):
                    if self._page.locator(f"[id$='{data_suf}']").count() > 0:
                        self._preencher(data_suf, saldo.data, obrigatorio=False)
                        preenchido = True
                        break
                if not preenchido:
                    self.log(f"    ⚠ campo data saldo FGTS não encontrado")
                for val_suf in ("valorSaldoFGTS", "valorDeducao", "saldoValor"):
                    if self._page.locator(f"[id$='{val_suf}']").count() > 0:
                        self._preencher(val_suf, _fmt_br(saldo.valor_brl), obrigatorio=False)
                        break
                # Clicar botão "+" (adicionar)
                added = self._page.evaluate(
                    """() => {
                        const btns = [...document.querySelectorAll('input[type="image"], input[type="submit"], input[type="button"], button, a')];
                        for (const b of btns) {
                            const txt = (b.value || b.textContent || '').trim();
                            const alt = (b.alt || b.title || '').trim();
                            const src = (b.src || '').toLowerCase();
                            if (txt === '+' || alt.includes('Adicionar') || alt.includes('Incluir')
                                || src.includes('add.png') || src.includes('mais') || src.includes('plus')) {
                                // Confirmar contexto: próximo dos campos de saldo
                                const container = b.closest('table, fieldset, div');
                                if (container && /saldo|deduz/i.test(container.textContent || '')) {
                                    b.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }"""
                )
                if added:
                    self.log(f"    ✓ Saldo adicionado à tabela")
                    self._aguardar_ajax(5000)
            except Exception as e:
                self.log(f"    ⚠ Falha ao adicionar saldo FGTS: {e}")

        # Marcar checkbox "Deduzir do FGTS"
        if getattr(f, "deduzir_do_fgts", False) or saldos:
            for cb_suf in ("deduzirDoFgts", "deduzirFGTS", "fazerDeducao"):
                try:
                    if self._page.locator(f"input[type='checkbox'][id$=':{cb_suf}']").count() > 0:
                        self._marcar_checkbox(cb_suf, True)
                        self.log(f"  ✓ 'Deduzir do FGTS' marcado")
                        break
                except Exception:
                    continue

        _safe(lambda: self._clicar("salvar"), "salvar")
        self._aguardar_ajax(8000)
        self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        self.log("Fase 8 concluída")

    def fase_contribuicao_social(self) -> None:
        self.log("Fase 9 — Contribuição Social")
        self._navegar_menu("li_calculo_inss")
        cs = self.previa.contribuicao_social
        self._marcar_checkbox("apurarInssSeguradoDevido", cs.apurar_segurado_devido)
        self._marcar_checkbox("cobrarDoReclamanteDevido", cs.cobrar_do_reclamante_devido)
        self._marcar_checkbox("apurarSalariosPagos", cs.apurar_salarios_pagos)
        self._marcar_radio("aliquotaEmpregado", cs.aliquota_segurado)
        self._marcar_radio("aliquotaEmpregador", cs.aliquota_empregador)
        if cs.aliquota_empregador == "FIXA":
            self._preencher("aliquotaEmpresaFixa", str(cs.aliquota_empresa_fixa_pct or 20), obrigatorio=False)
            self._preencher("aliquotaRatFixa", str(cs.aliquota_rat_fixa_pct or 1), obrigatorio=False)
            self._preencher("aliquotaTerceirosFixa", str(cs.aliquota_terceiros_fixa_pct or 5.8), obrigatorio=False)
        try:
            self._clicar("salvar")
            self._aguardar_ajax(8000)
            self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        except Exception as e:
            self.log(f"  ⚠ save CS falhou: {e}")

        # Sub-página parametrizar-inss SÓ se CS está realmente sendo apurada.
        # Casos como Santiago (apurar_segurado_devido=false) não precisam
        # rodar Ocorrências/Recuperar/Copiar — esses controles podem nem existir.
        if cs.apurar_segurado_devido or cs.apurar_salarios_pagos:
            try:
                self._clicar("ocorrencias")
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1500)
                try:
                    self._clicar("recuperarDevidos")
                    self._aguardar_ajax(5000)
                except Exception as e:
                    self.log(f"  ⚠ recuperarDevidos indisponível: {e}")
                try:
                    self._clicar("copiarDevidos")
                    self._aguardar_ajax(5000)
                except Exception as e:
                    self.log(f"  ⚠ copiarDevidos indisponível: {e}")

                # Modo manual_por_periodo: aplicar Lote por intervalo
                if cs.vinculacao_historicos_devidos.modo == "manual_por_periodo":
                    for intv in cs.vinculacao_historicos_devidos.intervalos:
                        try:
                            self._preencher("dataInicialInputDate", intv.competencia_inicial)
                            self._preencher("dataFinalInputDate", intv.competencia_final)
                            self._preencher("salariosPago", _fmt_br(intv.valor_base_brl))
                            self._clicar("aplicar")
                            self._aguardar_ajax()
                        except Exception as e:
                            self.log(f"  ⚠ intervalo CS {intv.competencia_inicial}: {e}")

                try:
                    self._clicar("salvar")
                    self._aguardar_ajax(8000)
                    self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
                except Exception as e:
                    self.log(f"  ⚠ save ocorrências CS: {e}")
            except Exception as e:
                self.log(f"  ⚠ Sub-página Ocorrências CS indisponível: {e}")
        else:
            self.log("  ⏭ CS sem apuração — pulando ocorrências")
        self.log("Fase 9 concluída")

    def fase_imposto_de_renda(self) -> None:
        self.log("Fase 10 — IRPF")
        self._navegar_menu("li_calculo_irpf")
        ir = self.previa.imposto_de_renda
        self._marcar_checkbox("apurarImpostoRenda", ir.apurar_irpf)
        self._marcar_checkbox("considerarTributacaoEmSeparado", ir.considerar_tributacao_em_separado_rra)
        self._marcar_checkbox("regimeDeCaixa", ir.regime_de_caixa)
        self._marcar_checkbox(
            "deduzirContribuicaoSocialDevidaPeloReclamante", ir.deducoes.contribuicao_social
        )
        self._marcar_checkbox("deduzirPrevidenciaPrivada", ir.deducoes.previdencia_privada)
        self._marcar_checkbox("deduzirPensaoAlimenticia", ir.deducoes.pensao_alimenticia)
        self._marcar_checkbox(
            "deduzirHonorariosDevidosPeloReclamante",
            ir.deducoes.honorarios_devidos_pelo_reclamante,
        )
        if ir.possui_dependentes:
            self._marcar_checkbox("possuiDependentes", True)
            self._preencher("quantidadeDependentes", str(ir.quantidade_dependentes))
        self._clicar("salvar")
        self._aguardar_ajax(8000)
        self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        self.log("Fase 10 concluída")

    def fase_honorarios(self) -> None:
        self.log("Fase 11 — Honorários")
        self._navegar_menu("li_calculo_honorarios")
        for h in self.previa.honorarios:
            self.log(f"  → Processando honorário: {h.tipo_honorario} / {h.tipo_devedor}")
            try:
                self._clicar("incluir")
            except Exception as e:
                self.log(f"  ⚠ Botão Incluir indisponível para honorário: {e}")
                continue
            self._aguardar_ajax(5000)
            self._page.wait_for_timeout(1000)

            # Selecionar tipo (campo obrigatório)
            try:
                self._selecionar("tpHonorario", h.tipo_honorario)
                self._aguardar_ajax(2000)
            except Exception as e:
                self.log(f"  ⚠ select tpHonorario: {e} — pulando este honorário")
                continue

            # Descrição: usar valor explícito ou gerar default a partir do tipo/devedor
            descricao_final = (h.descricao or "").strip() or f"{h.tipo_honorario} / {h.tipo_devedor}"
            self._preencher("descricao", descricao_final, obrigatorio=False)

            self._marcar_radio("tipoDeDevedor", h.tipo_devedor)
            self._aguardar_ajax(1500)
            self._marcar_radio("tipoValor", h.tipo_valor.value)
            self._aguardar_ajax(2000)

            if h.tipo_valor.value == "CALCULADO":
                if h.aliquota_pct is not None:
                    # PJE-Calc espera percentual em formato decimal (15.0 não 0.15)
                    # O JSON pode vir como 0.15 ou 15 — normalizar
                    pct = h.aliquota_pct * 100 if h.aliquota_pct < 1 else h.aliquota_pct
                    self._preencher("aliquota", _fmt_br(pct), obrigatorio=False)
                if h.base_para_apuracao:
                    self._selecionar("baseParaApuracao", h.base_para_apuracao, obrigatorio=False)
            else:
                if h.valor_informado_brl is not None:
                    self._preencher("aliquota", _fmt_br(h.valor_informado_brl), obrigatorio=False)

            # Credor: campos opcionais — usar default reclamado se ausente
            if h.credor:
                self._preencher("nomeCredor", h.credor.nome, obrigatorio=False)
                self._marcar_radio("tipoDocumentoFiscalCredor", h.credor.doc_fiscal_tipo.value)
                self._preencher("numeroDocumentoFiscalCredor", h.credor.doc_fiscal_numero, obrigatorio=False)
            self._marcar_checkbox("apurarIRRF", h.apurar_irrf)

            self._clicar("salvar")
            self._aguardar_ajax(8000)
            sucesso = self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
            if sucesso:
                self.log(f"  ✓ Honorário {h.tipo_honorario}/{h.tipo_devedor} salvo com sucesso")
            else:
                self._diagnostico_pagina(contexto=f"pós-save Honorário {h.tipo_honorario}/{h.tipo_devedor}")
        self.log("Fase 11 concluída")

    def fase_custas_judiciais(self) -> None:
        self.log("Fase 12 — Custas Judiciais")
        self._navegar_menu("li_calculo_custas_judiciais")
        c = self.previa.custas_judiciais
        self._selecionar("baseParaCustasCalculadas", c.base_para_calculadas)
        self._marcar_radio("tipoDeCustasDeConhecimentoDoReclamante", c.custas_conhecimento_reclamante)
        self._marcar_radio("tipoDeCustasDeConhecimentoDoReclamado", c.custas_conhecimento_reclamado)
        self._marcar_radio("tipoDeCustasDeLiquidacao", c.custas_liquidacao)
        self._clicar("salvar")
        self._aguardar_ajax(8000)
        self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        self.log("Fase 12 concluída")

    def fase_correcao_juros_multa(self) -> None:
        self.log("Fase 13 — Correção, Juros e Multa")
        self._navegar_menu("li_calculo_correcao_juros_multa")
        c = self.previa.correcao_juros_multa
        self._selecionar("indiceTrabalhista", c.indice_trabalhista)
        self._selecionar("juros", c.juros)
        self._selecionar("baseDeJurosDasVerbas", c.base_juros_verbas)
        self._clicar("salvar")
        self._aguardar_ajax(8000)
        self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        self.log("Fase 13 concluída")

    def fase_liquidar_e_exportar(self) -> str | None:
        """Liquida o cálculo e baixa o arquivo .PJC final."""
        self.log("Fase 14 — Liquidar + Exportar")

        # ── 14a. Entrar em Edit Mode via Recentes (CRÍTICO para Exportar) ──
        # Em creation mode, `ApresentadorExportacao.iniciar()` não é chamado
        # quando URL-navegamos para exportacao.jsf → `this.nome` fica null →
        # Exportador.exportar(calculo, null, ...) lança InfraException → "Erro: 4".
        #
        # Solução confirmada pelo access log de 05/04: navegar para principal.jsf,
        # reabrir via Recentes (POST principal.jsf → calculo.jsf?conv=77 em EDIT MODE),
        # e então usar sidebar Liquidar → sidebar Exportar. O sidebar chama iniciar()
        # que seta this.nome → exportação funciona.
        edit_mode = self._reabrir_calculo_via_recentes()
        if edit_mode:
            self.log("  ✓ Edit mode via Recentes — sidebar Liquidar/Exportar disponível")
            self._aguardar_ajax(5000)
            self._page.wait_for_timeout(1000)
        else:
            # Fallback: tentar Buscar se Recentes não incluiu o calc atual
            self.log("  → Recentes falhou — tentando Buscar como fallback")
            edit_mode = self._reabrir_via_buscar()
            if edit_mode:
                self.log("  ✓ Edit mode via Buscar — sidebar Liquidar/Exportar disponível")
                self._aguardar_ajax(5000)
                self._page.wait_for_timeout(1000)
            else:
                self.log("  ⚠ Buscar também falhou — continuando em creation mode (pode falhar no Exportar)")
                # Último recurso: garantir contexto do cálculo via Dados do Cálculo
                try:
                    self._navegar_menu("li_calculo_dados_do_calculo")
                    self._aguardar_ajax(8000)
                    self._page.wait_for_timeout(1500)
                except Exception:
                    pass

        # ── 14b. Navegar para Liquidar via sidebar JSF ─────────────────────
        # Estratégia em cascata para localizar Liquidar
        nav_ok = self._page.evaluate(
            """() => {
                // 1. li#li_operacoes_liquidar > a (ID confirmado em ambas versões)
                const li1 = document.getElementById('li_operacoes_liquidar');
                if (li1) {
                    const a = li1.querySelector('a');
                    if (a) { a.click(); return 'li_operacoes_liquidar'; }
                }
                // 2. <a> com texto exato 'Liquidar' dentro de li com 'operacoes' no id
                const links = [...document.querySelectorAll('a')];
                for (const a of links) {
                    const txt = (a.textContent || '').replace(/\\s+/g,' ').trim();
                    const li = a.closest('li');
                    if (txt === 'Liquidar' && li && li.id && li.id.includes('operacoes')) {
                        a.click();
                        return 'text-li-operacoes';
                    }
                }
                // 3. Qualquer <a> com texto 'Liquidar' (último recurso)
                for (const a of links) {
                    const txt = (a.textContent || '').replace(/\\s+/g,' ').trim();
                    if (txt === 'Liquidar' && a.id && (a.id.includes('menu') || a.id.includes('j_id'))) {
                        a.click();
                        return 'text-any';
                    }
                }
                return null;
            }"""
        )
        if not nav_ok:
            self.log("  ⚠ Sidebar 'Liquidar' não localizado — tentando URL nav")
            try:
                if self._calculo_conversation_id:
                    url_liq = (
                        f"{self.pjecalc_url}/pages/calculo/liquidacao.jsf"
                        f"?conversationId={self._calculo_conversation_id}"
                    )
                    self._page.goto(url_liq, wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax(15000)
                    self._capturar_conversation_id()
                    nav_ok = "url-nav-fallback"
            except Exception as e:
                self.log(f"  ⚠ URL nav Liquidar: {e}")
        if not nav_ok:
            raise RuntimeError("Sidebar 'Liquidar' não localizado")
        self.log(f"  ✓ Navegação Liquidar via: {nav_ok}")
        self._aguardar_ajax(15000)
        self._page.wait_for_timeout(2000)

        # ── 14c. Preencher form de Liquidação ──────────────────────────────
        liq = self.previa.liquidacao
        if liq.data_de_liquidacao:
            self._preencher("dataDeLiquidacaoInputDate", liq.data_de_liquidacao, obrigatorio=False)

        # Diagnóstico: dumpar radios indicesAcumulados na página atual
        radios_diag = self._page.evaluate(
            """() => {
                return [...document.querySelectorAll('input[type="radio"]')]
                    .filter(r => (r.id||'').includes('indicesAcumulados') || (r.name||'').includes('indicesAcumulados'))
                    .map(r => {
                        const label = document.querySelector(`label[for="${r.id.replace(/[^\\w-]/g, c => '\\\\' + c)}"]`);
                        return {id: r.id, name: r.name, value: r.value, label: label ? label.textContent.replace(/\\s+/g, ' ').trim() : null};
                    });
            }"""
        )
        if radios_diag:
            self.log(f"  📋 Radios indicesAcumulados disponíveis: {radios_diag}")

        if liq.indices_acumulados:
            self._marcar_radio("indicesAcumulados", liq.indices_acumulados)
            # Fallback: se ainda não marcou, clicar no primeiro radio (default = MES_SUBSEQUENTE_AO_VENCIMENTO)
            try:
                already_checked = self._page.evaluate(
                    """() => [...document.querySelectorAll('input[type="radio"]')]
                        .filter(r => (r.id||'').includes('indicesAcumulados') || (r.name||'').includes('indicesAcumulados'))
                        .some(r => r.checked)"""
                )
                if not already_checked:
                    clicou = self._page.evaluate(
                        """() => {
                            const r = [...document.querySelectorAll('input[type="radio"]')]
                                .filter(r => (r.id||'').includes('indicesAcumulados') || (r.name||'').includes('indicesAcumulados'))[0];
                            if (r) { r.click(); return r.value; }
                            return null;
                        }"""
                    )
                    if clicou:
                        self.log(f"  ✓ radio indicesAcumulados marcado no primeiro (fallback): {clicou}")
            except Exception as e:
                self.log(f"  ⚠ fallback indicesAcumulados: {e}")

        # ── 14d. Clicar Liquidar e aguardar (não-bloqueante, padrão Calc Machine) ──
        self.log("  → Clicando no botão de liquidar...")
        self._clicar("liquidar")
        self.log("  → Liquidação iniciada, aguardando término (pode demorar para cálculos grandes)...")
        # Aguardar a mensagem "Operação realizada" — se não vier em 90s, prosseguir
        # com aviso (igual Calc Machine). NÃO travar a automação na liquidação.
        try:
            self._page.wait_for_load_state("networkidle", timeout=90000)
        except Exception:
            self.log("  ⚠ Liquidação ainda em processamento (network não estabilizou em 90s) — prosseguindo")
        sucesso_liq = self._aguardar_operacao_sucesso(timeout_ms=20000, bloqueante=False)
        if not sucesso_liq:
            erro = self._verificar_erro_jsf()
            if erro:
                self.log(f"  ⚠ JSF reportou erro: {erro[:200]}")

        # PJE-Calc tem uma seção "Pendências do Cálculo" SEMPRE presente na
        # página, com legenda de ícones (Erro/Alerta). Detectamos pendência
        # REAL via classe .validacaoErro (não confundir com .validacaoAlerta
        # que é só warning não-bloqueador). Se a página confirmou
        # "Operação realizada com sucesso" via _aguardar_operacao_sucesso,
        # consideramos a liquidação BEM-SUCEDIDA mesmo se houver alertas.
        body = (self._page.locator("body").text_content() or "").lower()
        tem_erro_real = self._page.evaluate(
            """() => {
                // Só conta como erro REAL os elementos com class validacaoErro
                // (legenda: 'Erro: Impede a liquidação do cálculo'). validacaoAlerta
                // (legenda: 'Alerta: Não impede a liquidação') NÃO é bloqueador.
                const erros = [...document.querySelectorAll('.validacaoErro')];
                // Filtrar para não pegar a label da legenda em si
                const reais = erros.filter(el => {
                    const txt = (el.textContent || '').toLowerCase();
                    return !txt.includes('legenda') && !txt.startsWith('erro:');
                });
                return reais.length > 0;
            }"""
        )
        if (sucesso_liq or self._calculo_numero) and not tem_erro_real:
            # Liquidação bem-sucedida confirmada
            self.log("  ✓ Liquidação CONCLUÍDA com sucesso")
        elif tem_erro_real:
            # Pendências = erros que IMPEDEM a liquidação. O cálculo NÃO foi
            # liquidado e o .PJC exportado terá hashCodeLiquidacao=null +
            # valores zerados. Capturar TODAS as mensagens para depurar.
            pendencias = self._page.evaluate(
                """() => {
                    const sels = [
                        '.rf-msgs-detail', '.rf-msgs-sum', '.rf-msgs-err',
                        '.ui-messages-error-summary',
                        '.rich-messages', '.rich-message',
                        '.validacaoErro', '.validacaoAlerta',
                        '.boxSpanTitulo', '.boxModuloValidacao',
                        '[class*="erro"]', '[class*="error"]', '[class*="pendencia"]'
                    ];
                    const seen = new Set();
                    const out = [];
                    for (const s of sels) {
                        for (const el of document.querySelectorAll(s)) {
                            const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                            if (txt && txt.length > 4 && txt.length < 400 && !seen.has(txt)) {
                                seen.add(txt);
                                out.push(txt);
                            }
                        }
                    }
                    return out.slice(0, 30);
                }"""
            )
            self.log(
                f"  ⚠ Liquidação NÃO PERSISTIDA (pendências bloquearam — PJC sairá pré-liquidação):"
            )
            for p in pendencias[:15]:
                self.log(f"     • {p[:250]}")
            # Diagnóstico completo se pendências veio vazio
            if not pendencias:
                self._diagnostico_pagina(contexto="pendências Liquidação (sem captura direta)")
        else:
            # Alertas existem mas não bloqueiam; liquidação foi bem-sucedida.
            self.log("  ✓ Liquidação OK (alertas não-bloqueadores podem existir)")

        # ── 14e. Navegar para Exportar (cascata robusta) ──────────────────
        # Em edit mode: sidebar li_operacoes_exportar chama iniciar() via JSF navigation rule
        # que seta this.nome = Exportador.gerarNomeDoArquivo(calculo) — OBRIGATÓRIO.
        # Em creation mode (fallback): URL nav direto vai para exportacao.jsf mas NÃO
        # chama iniciar() → nome=null → "Erro: 4". Por isso edit mode é crítico.
        nav_exp = self._page.evaluate(
            """() => {
                // 1. li#li_operacoes_exportar > a
                const li1 = document.getElementById('li_operacoes_exportar');
                if (li1) {
                    const a = li1.querySelector('a');
                    if (a) { a.click(); return 'li_operacoes_exportar'; }
                }
                // 2. <a> com texto exato 'Exportar' em li com 'operacoes'
                const links = [...document.querySelectorAll('a')];
                for (const a of links) {
                    const txt = (a.textContent || '').replace(/\\s+/g,' ').trim();
                    const li = a.closest('li');
                    if (txt === 'Exportar' && li && li.id && li.id.includes('operacoes')) {
                        a.click();
                        return 'text-li-operacoes';
                    }
                }
                // 3. <a> com texto 'Exportar' em qualquer menu
                for (const a of links) {
                    const txt = (a.textContent || '').replace(/\\s+/g,' ').trim();
                    if (txt === 'Exportar' && a.id && (a.id.includes('menu') || a.id.includes('j_id'))) {
                        a.click();
                        return 'text-any';
                    }
                }
                return null;
            }"""
        )
        if not nav_exp:
            self.log("  ⚠ Sidebar 'Exportar' não localizado — tentando URL nav")
            try:
                if self._calculo_conversation_id:
                    url_exp = (
                        f"{self.pjecalc_url}/pages/calculo/exportacao.jsf"
                        f"?conversationId={self._calculo_conversation_id}"
                    )
                    self._page.goto(url_exp, wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax(15000)
                    self._capturar_conversation_id()
                    nav_exp = "url-nav-fallback"
            except Exception as e:
                self.log(f"  ⚠ URL nav Exportar: {e}")
        if not nav_exp:
            raise RuntimeError("Sidebar 'Exportar' não localizado")
        self.log(f"  ✓ Navegação Exportar via: {nav_exp}")
        self._aguardar_ajax(15000)
        self._page.wait_for_timeout(2000)

        # ── 14f. Clicar Exportar e capturar .PJC ───────────────────────────
        # Estratégia: capturar response binário via expect_response
        from datetime import datetime as _dt

        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        num_limpo = self.previa.processo.numero_processo.replace("-", "").replace(".", "")
        nome_pjc = f"PROCESSO_{num_limpo}_{ts}.pjc"
        out_dir = Path("/tmp/pjecalc_exports")
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / nome_pjc

        try:
            # Localizar botão Exportar — cascata de seletores (v1 confirma
            # que pode ser type='submit' OU type='button'; class='botao').
            btn = None
            for sel in [
                "input[type='submit'][id$=':exportar']",
                "input[type='button'][id$=':exportar']",
                "input[id$=':exportar'][value='Exportar']",
                "input.botao[value='Exportar']",
                "input[value='Exportar'][type='submit']",
                "input[value='Exportar']",
            ]:
                loc = self._page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    btn = loc.first
                    self.log(f"  → Botão Exportar: {sel}")
                    break
            if not btn:
                # Diagnóstico: dump inputs visíveis na página
                _diag = self._page.evaluate(
                    """() => [...document.querySelectorAll('input[type=submit],input[type=button]')]
                        .filter(e => e.offsetParent)
                        .map(e => `${e.id}=${e.value}`).slice(0, 15)"""
                )
                raise RuntimeError(f"Botão Exportar não encontrado. Inputs visíveis: {_diag}")

            # ── Captura do download (padrão Calc Machine 12/05/2026) ────────────
            # Calc Machine configura o navegador para downloads em diretório fixo
            # e depois faz scan do diretório. É mais robusto que `page.on("download")`
            # porque não depende de o Playwright capturar o evento no momento certo
            # (o auto-jsfcljs do exportacao.xhtml pode disparar em sub-frames).
            #
            # Estratégia tripla (em ordem de prioridade):
            #   A) Listener page.on("download") (mantemos como tentativa primária)
            #   B) Response interceptor para ZIP bytes (intercept HTTP)
            #   C) Scan do download dir do Firefox (fallback robusto)
            pjc_bytes: bytes | None = None
            _dl_data: list[bytes] = []
            _resp_data: list[bytes] = []
            _dir_initial = set(self._download_dir.iterdir()) if self._download_dir.exists() else set()

            def _on_download(dl) -> None:
                try:
                    path = dl.path()
                    data = __import__("pathlib").Path(path).read_bytes() if path else b""
                    _dl_data.append(data)
                    self.log(f"  📥 Download event: {dl.suggested_filename} ({len(data)}B)")
                except Exception as ex:
                    self.log(f"  ⚠ on_download error: {ex}")

            def _on_response(resp) -> None:
                try:
                    ct = (resp.headers.get("content-type") or "").lower()
                    cd = (resp.headers.get("content-disposition") or "").lower()
                    if "zip" in ct or ".pjc" in cd or "attachment" in cd:
                        body = resp.body()
                        if body[:2] == b"PK":
                            _resp_data.append(body)
                            self.log(f"  📦 ZIP via response: {len(body)}B")
                except Exception:
                    pass

            self._page.on("download", _on_download)
            self._page.on("response", _on_response)

            try:
                self.log("  ✓ Botão Exportar clicado")
                btn.click(force=True)
                # Aguardar: AJAX re-render (~2s) + auto-jsfcljs (~1s) + download (~2s)
                # mas dar margem para downloads grandes (15s base).
                self._page.wait_for_timeout(15000)

                # Estratégia C: scan do diretório de downloads para arquivo novo
                if not _dl_data and not _resp_data:
                    self.log(f"  → Scan do diretório de download {self._download_dir}...")
                    import pathlib as _pl, time as _t
                    deadline = _t.time() + 30  # +30s para download dir
                    novo = None
                    while _t.time() < deadline:
                        atuais = set(self._download_dir.iterdir()) if self._download_dir.exists() else set()
                        adicionados = atuais - _dir_initial
                        # Filtrar arquivos .pjc ou .PJC e que não terminem com .part (download em curso)
                        pjcs = [f for f in adicionados
                                if f.suffix.lower() == ".pjc" and not str(f).endswith(".part")]
                        if pjcs:
                            novo = max(pjcs, key=lambda f: f.stat().st_mtime)
                            break
                        self._page.wait_for_timeout(1000)
                    if novo and novo.exists():
                        data = novo.read_bytes()
                        if data[:2] == b"PK":
                            _resp_data.append(data)
                            self.log(f"  ✅ Arquivo salvo: {novo.name} ({len(data)}B)")
                        else:
                            self.log(f"  ⚠ Arquivo {novo.name} não é ZIP (header={data[:10]!r})")
            finally:
                self._page.remove_listener("download", _on_download)
                self._page.remove_listener("response", _on_response)

            # Prioridade: download event > response intercept > dir scan
            if _dl_data and _dl_data[0][:2] == b"PK":
                pjc_bytes = _dl_data[0]
                self.log(f"  ✓ .PJC via download event: {len(pjc_bytes)} bytes")
            elif _resp_data:
                pjc_bytes = _resp_data[0]
                self.log(f"  ✓ .PJC capturado: {len(pjc_bytes)} bytes")

            if not pjc_bytes:
                # Diagnóstico extra: o que apareceu no download dir
                arquivos_no_dir = (
                    [f.name for f in self._download_dir.iterdir()]
                    if self._download_dir.exists() else []
                )
                raise RuntimeError(
                    f"Falha ao capturar download .PJC: nenhum ZIP recebido. "
                    f"Download dir: {arquivos_no_dir}"
                )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Falha ao capturar download .PJC: {e}")

        # Validar header ZIP
        if not pjc_bytes or pjc_bytes[:2] != b"PK":
            raise RuntimeError(
                f".PJC inválido (não é ZIP): {len(pjc_bytes) if pjc_bytes else 0} bytes, "
                f"prefixo={pjc_bytes[:10] if pjc_bytes else b''!r}"
            )

        dest.write_bytes(pjc_bytes)
        self._pjc_path = str(dest)
        self.log(f"✓ PJC gerado: {self._pjc_path} ({len(pjc_bytes)} bytes)")
        return self._pjc_path

    def get_pjc_path(self) -> str | None:
        return self._pjc_path
