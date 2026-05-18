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
import os
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
        # Modo teste: abre cálculo existente em vez de criar novo.
        # Lido de PJECALC_CALCULO_TESTE (número CNJ do processo, ex: "0000948-78.2021.5.07.0003").
        # Quando definido, `run()` pula `_criar_novo_calculo()` e abre o cálculo existente
        # via Recentes, evitando o problema de FlushMode.MANUAL no H2.
        self._calculo_teste_processo: str | None = os.environ.get("PJECALC_CALCULO_TESTE")
        self._modo_edicao_inicial: bool = False
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

        # ── Inicialização do cálculo ───────────────────────────────────────────
        if self._calculo_teste_processo:
            self.log(f"  [TESTE] Abrindo cálculo existente: proc={self._calculo_teste_processo}")
            ok_teste = self._reabrir_calculo_via_recentes(
                processo_override=self._calculo_teste_processo
            )
            if ok_teste:
                self._modo_edicao_inicial = True
                self.log(f"  ✓ [TESTE] Modo edição ativo via Recentes — conv={self._calculo_conversation_id}")
            else:
                self.log("  ⚠ [TESTE] Não encontrado nos Recentes — tentando Buscar...")
                ok_buscar = self._reabrir_via_buscar(
                    processo_override=self._calculo_teste_processo
                )
                if ok_buscar:
                    self._modo_edicao_inicial = True
                    self.log(f"  ✓ [TESTE] Modo edição ativo via Buscar — conv={self._calculo_conversation_id}")
                else:
                    self.log("  ⚠ [TESTE] Cálculo teste não encontrado (Recentes + Buscar) — criando novo")
                    self._criar_novo_calculo()
        else:
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

        # ── Sequência de fases — ordem crítica ────────────────────────────────
        # ARQUITETURA SEAM — DOIS MODOS DE CONVERSA:
        #
        # CRIAÇÃO (conv=6): criado por "Cálculo > Novo". Nesse modo:
        #   - Menu lateral mostra apenas itens globais (não per-seção).
        #   - URL nav para fgts.jsf, inss.jsf etc. retorna frame vazia (beans não init).
        #   - Apenas HistoricoSalarialMB e CalculoMB inicializam via URL nav.
        #   - calculoAberto.calculo = null → Export NPE.
        #
        # EDIÇÃO (conv=novo via Recentes): criado ao reabrir o cálculo da lista.
        #   - Menu lateral mostra TODOS os itens per-seção.
        #   - FgtsMB, InssMB, IrpfMB, HonorariosMB, ApresentadorExportacao todos ok.
        #   - calculoAberto.calculo corretamente populado → Export funciona.
        #
        # ESTRATÉGIA:
        #   1. Fase 1 salva o processo (cria registro no DB → aparece em Recentes).
        #   2. Reabrir via Recentes → troca para conv_edit (modo edição).
        #   3. Fases 2-3 em conv_edit (Parâmetros + Histórico).
        #   4. Fases 5-13 em conv_edit (FGTS/CS/IRPF/Honorários/Custas/Correção).
        #   5. Fase 4 (Verbas/Expresso) → Seam cria conv_expresso.
        #   6. Liquidação + Export em conv_expresso (calculoAberto ok via edit mode).
        _run_fase("Fase 1 (Processo)", self.fase_processo)
        _run_fase("Fase 2 (Parâmetros)", self.fase_parametros_calculo)

        # ── Reabrir via Recentes (criação → edição) ──────────────────────────
        # Após Fase 2 (segunda save) o H2 DB tem o cálculo commitado.
        # Navegamos para principal.jsf e tentamos reabrir via Recentes para
        # obter uma nova conv em modo edição onde TODOS os beans Seam inicializam.
        # Em sessões FRESCAS (sem calcs anteriores), Recentes pode estar vazio
        # mesmo após Fase 2 — nesse caso continuamos em modo criação e aceitamos
        # que FGTS/CS/IRPF/Honorários podem retornar frames vazias (graceful skip).
        # EXCEÇÃO: modo PJECALC_CALCULO_TESTE — já estamos em edição desde o início.
        if self._modo_edicao_inicial:
            self.log("  ℹ [TESTE] Já em modo edição — skip transição Recentes pós-Fase2")
        else:
            try:
                self.log("  → Tentando transição criação→edição via Recentes...")
                ok_recentes = self._reabrir_calculo_via_recentes()
                if ok_recentes:
                    self.log(f"  ✓ Modo edição ativo — conv={self._calculo_conversation_id}")
                else:
                    self.log("  ⚠ Recentes vazio — continuando em modo criação")
            except Exception as e_rec:
                self.log(f"  ⚠ Recentes erro: {e_rec} — continuando")

        # ORDEM CONFORME MANUAL OFICIAL PJE-Calc (§"Sequencia de Preenchimento Recomendada"):
        # 3.Histórico → 4.Verbas → 5.Cartão Ponto → 6.Faltas → 7.Férias → 8.FGTS → 9.CS
        # → 10.IRPF → 11.Honorários → 12.Custas → 13.Correção → 14.Liquidar
        #
        # Verbas vêm ANTES de FGTS/CS/IRPF porque essas fases precisam que a base de
        # cálculo (verbas + reflexos) esteja populada — sem isso o PJE-Calc não
        # inicializa os beans dependentes e renderiza as páginas sem campos.
        #
        # Como Verbas muda o conv_id (cada Expresso cria nova conv), reabrir via
        # Recentes APÓS verbas para restaurar conv estável com tudo populado.
        _run_fase("Fase 3 (Histórico)", self.fase_historico_salarial)
        _run_fase("Fase 4 (Verbas)", self.fase_verbas)
        # Reabertura pós-Verbas: garantir conv estável com base de cálculo populada
        try:
            self.log("  → Reabrindo cálculo via Recentes pós-Verbas (restaurar conv)...")
            if self._reabrir_calculo_via_recentes():
                self.log(f"  ✓ Conv pós-Verbas: {self._calculo_conversation_id}")
        except Exception as e:
            self.log(f"  ⚠ Reabertura pós-Verbas falhou: {e}")
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
        # Tentar id*= primeiro (radios com id fixo); fallback name*= (JSF com IDs dinâmicos j_id*)
        for sel in (
            f"input[type='radio'][id*='{dom_id}'][value='{valor}']",
            f"input[type='radio'][name*='{dom_id}'][value='{valor}']",
        ):
            loc = self._page.locator(sel)
            if loc.count() > 0:
                loc.first.click(force=True)
                # Forçar dispatch dos eventos JSF/RichFaces. force=True às vezes
                # não dispara `change` nativo, e o a4j:support escuta esse evento
                # para re-renderizar campos dependentes (ex.: dataVencimento* nas
                # Custas só aparecem após `change` no radio tipoDeCustas*).
                try:
                    loc.first.evaluate(
                        """el => {
                            el.checked = true;
                            el.dispatchEvent(new Event('click', {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                        }"""
                    )
                except Exception:
                    pass
                self.log(f"  ✓ radio {dom_id} = {valor}")
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
                escaped_id = real_id.replace(":", "\\:")
                encontrado = self._page.locator(f"#{escaped_id}")
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

    def _clicar_salvar_flex(self, timeout_ms: int = 8000) -> bool:
        """Tenta clicar botão de save em cascata flexível.

        Sub-formulários JSF podem nomear o submit como `salvar`, `confirmar`,
        `gravar`, `aplicar` ou `atualizar`. Este helper varre essa cascata por
        sufixo de DOM ID e clica o primeiro visível. Retorna True se clicou.
        """
        nomes = ["salvar", "confirmar", "gravar", "aplicar", "atualizar"]
        for nome in nomes:
            seletores = [
                f"input[type='submit'][id$=':{nome}']",
                f"input[type='button'][id$=':{nome}']",
                f"input[id$=':{nome}']",
                f"input[id$='{nome}']",
                f"button[id$=':{nome}']",
            ]
            for sel in seletores:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    try:
                        loc.first.wait_for(state="visible", timeout=timeout_ms)
                        loc.first.click(force=True)
                        self.log(f"  ✓ click {nome} (cascata flex via {sel!r})")
                        return True
                    except Exception:
                        continue
        # Último recurso: qualquer input value="Salvar"|"Confirmar"|"Gravar"
        try:
            clicou = self._page.evaluate(
                """() => {
                    const norm = s => (s||'').trim().toUpperCase();
                    const alvos = ['SALVAR','CONFIRMAR','GRAVAR','APLICAR','ATUALIZAR'];
                    const inputs = [...document.querySelectorAll('input[type=submit],input[type=button],button')];
                    for (const v of inputs) {
                        const t = norm(v.value || v.textContent);
                        if (alvos.includes(t)) { v.click(); return 'value:'+t; }
                    }
                    return null;
                }"""
            )
            if clicou:
                self.log(f"  ✓ click salvar (cascata flex via value: {clicou})")
                return True
        except Exception:
            pass
        self.log("  ⚠ Nenhum botão Salvar/Confirmar/Gravar encontrado (cascata flex)")
        return False

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

    def _navegar_menu_via_click(self, li_id: str) -> bool:
        """Navega clicando no <a> do menu sidebar — necessário para Seam init.

        Diferente de _navegar_menu (que faz goto URL direta), este método
        SEMPRE clica no menu lateral, o que dispara o handler JSF que invoca
        @PostConstruct do bean Seam. Essencial para FGTS/CS/IRPF/Correção,
        que requerem init() do bean para renderizar campos.

        Returns True se conseguiu clicar.
        """
        try:
            clicou = self._page.evaluate("""(liId) => {
                const li = document.getElementById(liId);
                if (li) { const a = li.querySelector('a'); if (a) { a.click(); return true; } }
                // Fallback: id por sufixo (alguns menus têm prefixo)
                const tail = liId.replace('li_', '');
                const matches = document.querySelectorAll(`li[id$="${tail}"]`);
                for (const l of matches) {
                    const a = l.querySelector('a');
                    if (a) { a.click(); return true; }
                }
                return false;
            }""", li_id)
            if clicou:
                self._aguardar_ajax(10000)
                self._capturar_conversation_id()
                self.log(f"  → navegou para {li_id} via click sidebar (Seam init)")
                return True
            self.log(f"  ⚠ menu {li_id} não encontrado no sidebar")
            return False
        except Exception as e:
            self.log(f"  ⚠ _navegar_menu_via_click({li_id}): {e}")
            return False

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

    def _reabrir_calculo_via_recentes(self, processo_override: str | None = None) -> bool:
        """Volta para principal e reabre cálculo via lista 'Recentes'.

        Workaround para NPE pós-Expresso: cria nova conversação Seam limpa
        atualizando self._calculo_conversation_id. Documentado em v1
        (playwright_pjecalc.py linha 3058).

        Args:
            processo_override: Número CNJ a buscar no Recentes em vez do processo
                da prévia atual. Usado por PJECALC_CALCULO_TESTE para achar o
                cálculo de teste sem que ele precise ter sido criado agora.
                Quando set, desativa o fallback por nome de reclamante e "1 item".

        Returns True se reabriu com sucesso.
        """
        try:
            self._page.goto(
                f"{self.pjecalc_url}/pages/principal.jsf",
                wait_until="domcontentloaded", timeout=15000,
            )
            self._page.wait_for_timeout(2000)
            self._aguardar_ajax(8000)

            # O select de Recentes tem ID dinâmico (ex: formulario:j_id92) e NÃO
            # tem class/name 'listaCalculosRecentes' — usar JS para localizá-lo.
            # Diagnóstico: logar todos os selects encontrados para debug
            _diag_selects = self._page.evaluate("""() => {
                const result = [];
                for (const s of document.querySelectorAll('select')) {
                    result.push({
                        id: s.id, name: s.name, size: s.size,
                        nOpts: s.options.length,
                        first: s.options.length > 0 ? (s.options[0].text || '').slice(0, 60) : '',
                        blob: [...s.options].map(o => o.text || '').join(' | ').slice(0, 100)
                    });
                }
                return result;
            }""")
            self.log(f"  [DIAG-recentes] selects={_diag_selects}")

            _select_id = self._page.evaluate("""() => {
                const SKIP = new Set(['selAcheFacil']);
                // Tier 1: primeira opção começa com dígitos + "/" (padrão "ID / RECLAMANTE")
                for (const s of document.querySelectorAll('select')) {
                    if (SKIP.has(s.name) || SKIP.has(s.id)) continue;
                    if (s.options.length > 0 && /^\\d{4,}\\s*\\//.test(s.options[0].text || ''))
                        return s.name || s.id;
                }
                // Tier 2: blob contém padrão CNJ TRT (NNNNNNN-NN.NNNN.5.NN.NNNN)
                for (const s of document.querySelectorAll('select')) {
                    if (SKIP.has(s.name) || SKIP.has(s.id)) continue;
                    const blob = [...s.options].map(o => o.text || '').join(' | ');
                    if (/\\d{7}-\\d{2}\\.\\d{4}\\.5\\.\\d{2}\\.\\d{4}/.test(blob))
                        return s.name || s.id;
                }
                // Tier 3: listbox (size>1) com nome prefixado 'formulario:' e ≥1 opção
                for (const s of document.querySelectorAll('select')) {
                    if (SKIP.has(s.name) || SKIP.has(s.id)) continue;
                    const n = s.name || s.id || '';
                    if (s.size > 1 && n.startsWith('formulario:') && s.options.length > 0)
                        return n;
                }
                return null;
            }""")
            if not _select_id:
                self.log("  ⚠ Lista de Cálculos Recentes não encontrada ou vazia — pulando reabrir")
                return False
            listbox = self._page.locator(f"select[name='{_select_id}'], select[id='{_select_id}']")
            if listbox.count() == 0:
                self.log("  ⚠ Lista de Cálculos Recentes não encontrada — pulando reabrir")
                return False
            self.log(f"  → select Recentes encontrado: {_select_id}")

            n_opts = listbox.first.locator("option").count()
            if n_opts == 0:
                return False

            # Achar pelo CNJ do processo (ou processo_override em modo TESTE)
            num = processo_override or self.previa.processo.numero_processo
            num_clean = num.replace(".", "").replace("-", "").replace("/", "")
            found_idx = None
            options = listbox.first.locator("option")
            for i in range(n_opts):
                opt_text = (options.nth(i).text_content() or "")
                if num_clean in opt_text.replace(".", "").replace("-", "").replace("/", ""):
                    found_idx = i
                    break

            # Fallback: pelo nome do reclamante (só se NÃO estiver usando override de teste)
            if found_idx is None and processo_override is None:
                rec = (self.previa.processo.reclamante.nome or "").upper()
                if len(rec) >= 5:
                    for i in range(n_opts):
                        if rec in (options.nth(i).text_content() or "").upper():
                            found_idx = i
                            break

            # Último fallback: 1 item só na lista (só se NÃO for override de teste)
            if found_idx is None and n_opts == 1 and processo_override is None:
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

    def _reabrir_via_buscar(self, processo_override: str | None = None) -> bool:
        """Fallback: usa sidebar Buscar para pesquisar o cálculo e abri-lo em edit mode.

        Alternativa quando Recentes não inclui o calc atual (comum em sessões locais
        onde TBCALCULOSRECENTESUSUARIO não registrou o novo cálculo).

        Args:
            processo_override: Número CNJ a buscar em vez do processo da prévia.
                Usado por PJECALC_CALCULO_TESTE para localizar o cálculo de teste
                mesmo quando não está em Recentes.

        Fluxo:
        1. Click em li_calculo_buscar → calculo.jsf?conversationId=N (Buscar page)
        2. Preencher campos de busca com numero/digito/ano/regiao/vara do processo
        3. Click botão 'Buscar'
        4. Aguardar resultados e clicar no primeiro item correspondente
        5. Verificar se URL mudou para calculo.jsf em modo edição

        Returns True se reabriu com sucesso.
        """
        try:
            num_busca = processo_override or self.previa.processo.numero_processo
            self.log(f"  → Tentando Buscar como fallback de Recentes: {num_busca}")
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
            cnj = _split_cnj(num_busca)
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
            num_cnj = num_busca  # usa processo_override se definido
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

        Inclui retry automático para lidar com Tomcat recém-inicializado: o servlet
        pode responder na porta 9257 mas os beans JSF ainda não estarem prontos,
        causando navegação para principal.jsf sem transição para calculo.jsf.
        """
        _MAX_TENTATIVAS = 4
        _ESPERA_ENTRE_TENTATIVAS_MS = 15000

        for tentativa in range(1, _MAX_TENTATIVAS + 1):
            if tentativa > 1:
                self.log(f"  ⏳ Aguardando {_ESPERA_ENTRE_TENTATIVAS_MS // 1000}s para Tomcat inicializar (tentativa {tentativa}/{_MAX_TENTATIVAS})...")
                self._page.wait_for_timeout(_ESPERA_ENTRE_TENTATIVAS_MS)
                # Recarregar principal.jsf para garantir estado limpo
                try:
                    self._page.goto(
                        "http://localhost:9257/pjecalc/pages/principal.jsf",
                        wait_until="networkidle",
                        timeout=30000,
                    )
                except Exception:
                    pass

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
                self.log(f"  ⚠ Botão 'Novo' não encontrado (tentativa {tentativa}/{_MAX_TENTATIVAS})")
                if tentativa == _MAX_TENTATIVAS:
                    raise RuntimeError(
                        "Botão 'Novo' não encontrado na home do PJE-Calc após "
                        f"{_MAX_TENTATIVAS} tentativas. Verifique se está logado e em principal.jsf."
                    )
                continue

            self.log(f"  → Click via {clicou} (tentativa {tentativa}/{_MAX_TENTATIVAS})")
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

            if self._calculo_conversation_id:
                self.log(f"✓ Novo cálculo criado (conv={self._calculo_conversation_id}, url={url[-80:]})")
                return

            self.log(
                f"  ⚠ conversationId não capturado após click em 'Novo' "
                f"(tentativa {tentativa}/{_MAX_TENTATIVAS}). URL: {url[-80:]}"
            )

        raise RuntimeError(
            f"conversationId não capturado após {_MAX_TENTATIVAS} tentativas em 'Novo'. "
            f"URL atual: {self._page.url}. "
            f"Tomcat pode estar ainda inicializando ou beans JSF não prontos."
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

        # Salvar Dados do Processo — OBRIGATÓRIO antes de fase_parametros_calculo
        # que chama _navegar_menu → page.goto(), descartando todo estado DOM não salvo.
        self.log("  → Salvando Dados do Processo...")
        self._clicar("salvar")
        self._aguardar_ajax(12000)
        sucesso = self._aguardar_operacao_sucesso(timeout_ms=25000, bloqueante=False)
        if not sucesso:
            erro = self._verificar_erro_jsf()
            if erro:
                self.log(f"  ⚠ Erro JSF ao salvar Dados do Processo: {erro[:200]}")
        self._capturar_conversation_id()
        self.log("Fase 1 concluída")

    def fase_parametros_calculo(self) -> None:
        self.log("Fase 2 — Parâmetros do Cálculo")
        # Garantir que estamos em calculo.jsf (aba principal com Parâmetros).
        # Após Recentes reopen, calculo.jsf já é a página ativa, mas nav explícita
        # é necessária caso a função seja chamada de outra página.
        self._navegar_menu("li_calculo_dados_do_calculo")
        self._aguardar_ajax(5000)
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

        # Comentários JG — usa valor explícito; fallback: auto-detecta JG via honorários
        jg_text = getattr(pc, "comentarios_jg", None)
        if not jg_text:
            for hon in self.previa.honorarios:
                if (getattr(hon, "tipo_honorario", "") == "SUCUMBENCIAIS"
                        and getattr(hon, "tipo_devedor", "") == "RECLAMANTE"):
                    jg_text = (
                        "Suspensão de exigibilidade dos honorários devidos pela parte "
                        "beneficiária da Justiça Gratuita (art. 791-A, § 4º da CLT)."
                    )
                    self.log("  ℹ JG auto-detectado via honorários — preenchendo comentários")
                    break
        if jg_text:
            self._preencher("comentarios", jg_text, obrigatorio=False)

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

        # 4c. Pós-Expresso: verificar contexto Seam para ajuste de parâmetros de verbas.
        # Bug PJE-Calc 2.15.1: Expresso save muda conversationId (ex: 6→42).
        # Na nova conv, verba-calculo.jsf pode ter NPE em carregarBasesParaPrincipal.
        # NOTA: FGTS/CS/IRPF/Honorários/Custas/Correção já rodaram antes do Expresso
        # na conv=6 original — não precisamos mais nos preocupar com eles aqui.
        # Só precisamos de verba-calculo.jsf para configurar parâmetros pós-Expresso.
        if verbas_expresso:
            # Pós-Expresso: Seam criou nova conversation (ex: conv=6 → conv=42).
            # Forçar inicialização via calculo.jsf?conversationId={nova_conv}.
            ok = False
            _conv_pos = self._calculo_conversation_id
            if _conv_pos:
                try:
                    self.log(f"  → Inicializando contexto pós-Expresso: calculo.jsf?conversationId={_conv_pos}")
                    url_calc = f"{self.pjecalc_url}/pages/calculo/calculo.jsf?conversationId={_conv_pos}"
                    self._page.goto(url_calc, wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax(10000)
                    self._page.wait_for_timeout(1500)
                    self._capturar_conversation_id()
                    _diag_init = self._page.evaluate("""() => {
                        const body = document.body?.textContent || '';
                        return {
                            url: location.href.slice(-60),
                            tem_500: body.includes('HTTP Status 500') || body.includes('NullPointerException'),
                            tem_form: !!document.getElementById('formulario'),
                            n_fields: document.querySelectorAll('input[type=text],input[type=radio],input[type=checkbox],select').length
                        };
                    }""")
                    self.log(f"  [DIAG-seam-init] calculo.jsf em conv={_conv_pos}: {_diag_init}")
                    if not _diag_init['tem_500'] and _diag_init['n_fields'] > 5:
                        self.log(f"  ✓ Contexto pós-Expresso ok: conv={self._calculo_conversation_id}")
                        ok = True
                    else:
                        self.log(f"  ⚠ calculo.jsf sem campos em conv={_conv_pos} — tentando Recentes")
                except Exception as _e_init:
                    self.log(f"  ⚠ Erro ao inicializar contexto pós-Expresso: {_e_init}")

            # Tentativa B: reabrir via Recentes (só se inicialização falhou)
            if not ok:
                try:
                    _recentes_count = self._page.evaluate("""() => {
                        const SKIP = new Set(['selAcheFacil']);
                        for (const s of document.querySelectorAll('select')) {
                            if (SKIP.has(s.name) || SKIP.has(s.id)) continue;
                            if (s.size > 1 && (s.name || '').startsWith('formulario:'))
                                return s.options.length;
                        }
                        return -1;
                    }""")
                    self.log(f"  ℹ Recentes count: {_recentes_count}")
                    if _recentes_count > 0:
                        self.log("  → Tentando reabrir via Recentes (lista não-vazia)")
                        ok = self._reabrir_calculo_via_recentes()
                    else:
                        self.log(f"  ℹ Recentes vazio — prosseguindo com conv={self._calculo_conversation_id}")
                except Exception as _e_rec:
                    self.log(f"  ⚠ Erro ao checar Recentes: {_e_rec}")

            # Navegar para listagem de verbas para ajuste de parâmetros pós-Expresso
            self._navegar_menu("li_calculo_verbas")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(2000)
            tem_listagem = self._page.evaluate(
                """() => document.querySelectorAll('a.linkParametrizar').length > 0"""
            )
            if not tem_listagem:
                self.log("  ⚠ verba-calculo.jsf vazia/NPE — parâmetros pós-Expresso serão pulados")

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

            # ── SAVE POR VERBA (corrigido 14/05/2026) ─────────────────────
            # Bug anterior: este bloco estava FORA do for, o que fazia o bot
            # marcar checkbox da verba N, voltar à listagem, re-entrar no Expresso
            # (zerando a marcação), marcar verba N+1, ... e só salvar a última.
            # Resultado: 7 das 8 verbas se perdiam.
            #
            # Comportamento correto (docstring do método + Calc Machine): marcar
            # uma checkbox, salvar imediatamente, voltar à listagem, retornar ao
            # Expresso para a próxima.
            _conv_pre_expresso = self._calculo_conversation_id
            try:
                self._clicar("salvar")
                self._aguardar_ajax(15000)
                sucesso = self._aguardar_operacao_sucesso(
                    timeout_ms=15000, bloqueante=False
                )
                self.log(
                    f"  ✓ Expresso salvo [{idx+1}/{len(verbas)}: {alvo}] sucesso={sucesso}"
                )
            except Exception as e:
                self.log(
                    f"  ⚠ Expresso save [{idx+1}/{len(verbas)}: {alvo}] falhou: {e}"
                )

            # CRITICO: re-capturar conversationId — Seam emite NOVO conv após
            # Expresso save. Sem isso, URL navs subsequentes vão para conv
            # expirada -> NPE/empty pages em todas as fases seguintes.
            mudou = self._capturar_conversation_id()
            try:
                _url_pos = self._page.url
                self.log(f"    ℹ URL pós-save [{idx+1}/{len(verbas)}]: {_url_pos[-80:]}")
            except Exception:
                pass

            # Guardar conv pré-Expresso como fallback se nova conv tiver NPE
            if mudou and _conv_pre_expresso:
                self._conv_pre_expresso = _conv_pre_expresso
            else:
                self._conv_pre_expresso = None

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
        # EXPRESSO_DIRETO: NÃO ALTERAR nada que o Expresso já configurou,
        # MAS preencher valor_informado quando aplicável (sem isso, verbas como
        # RESTITUIÇÃO/INDENIZAÇÃO DE DESPESA, DANO MORAL ficam com valor 0 →
        # liquidação rejeita por pendência "deve existir ocorrência com valor != 0").
        if (not com_identificacao
                and v.estrategia_preenchimento == EstrategiaPreenchimento.EXPRESSO_DIRETO):
            self.log(f"    ℹ EXPRESSO_DIRETO: ajustando período + valor_informado se aplicável")
            # Renomear quando nome_pjecalc divergir do expresso_alvo. Importante
            # para verbas genéricas (RESTITUIÇÃO/INDENIZAÇÃO DE DESPESA, DANO
            # MATERIAL, INDENIZAÇÃO ADICIONAL) cujo nome canônico do Expresso
            # não reflete a verba específica da condenação.
            if v.nome_pjecalc and v.expresso_alvo and v.nome_pjecalc.strip().upper() != v.expresso_alvo.strip().upper():
                try:
                    self._preencher("descricao", v.nome_pjecalc, obrigatorio=False)
                    self.log(f"    ✓ descricao customizada: '{v.nome_pjecalc}' (era '{v.expresso_alvo}')")
                except Exception as e:
                    self.log(f"    ⚠ Falha renomear descricao: {e}")
            # Ajustar período (datas)
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
            # Preencher valor_informado_brl quando valor=INFORMADO
            if p.valor == TipoValor.INFORMADO and p.valor_devido and p.valor_devido.valor_informado_brl:
                try:
                    self._preencher(
                        "valorDevido",
                        _fmt_br(p.valor_devido.valor_informado_brl),
                        obrigatorio=False,
                    )
                    self.log(f"    ✓ valor_informado_brl = {p.valor_devido.valor_informado_brl}")
                except Exception as e:
                    self.log(f"    ⚠ Falha preencher valor_informado: {e}")
            # Aguardar AJAX (rerender JSF disparado pelos blurs dos campos
            # acima) antes de o caller chamar _clicar_salvar_flex. Sem isso, o
            # botão Salvar pode estar em re-mount e a cascata flex falha com
            # "Nenhum botão Salvar/Confirmar/Gravar encontrado".
            self._aguardar_ajax(3000)
            return

        # MANUAL ou EXPRESSO_ADAPTADO: configuração completa

        # 1. Identificação (apenas Manual ou Expresso_Adaptado)
        if com_identificacao:
            self._preencher("descricao", v.nome_pjecalc)
            # Assunto CNJ — autocomplete: digitar código + Enter dispara seleção
            # Default 2581 (Remuneração, Verbas Indenizatórias e Benefícios)
            # quando codigo é None — categoria ampla que cobre majoritárias.
            codigo_cnj = p.assunto_cnj.codigo if p.assunto_cnj and p.assunto_cnj.codigo else 2581
            self._selecionar_assunto_cnj(codigo_cnj)
        elif v.estrategia_preenchimento == EstrategiaPreenchimento.EXPRESSO_ADAPTADO:
            self._preencher("descricao", v.nome_pjecalc, obrigatorio=False)

        # 2. Valor (INFORMADO vs CALCULADO) — radio dispara AJAX que troca DOM
        self._marcar_radio("valor", p.valor.value)
        self._aguardar_ajax(3000)

        if p.valor == TipoValor.INFORMADO:
            self._preencher("valorDevido", _fmt_br(p.valor_devido.valor_informado_brl))
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
        # ESTRATÉGIA: JS localiza o link e retorna seu id real; o click é
        # feito via Playwright nativo (locator.click), que dispara um evento
        # trusted que o JSF/RichFaces aceita. Click programático via JS
        # (a.click() / dispatchEvent / onclick.call) falhou: o navegador
        # seguia href="#irTopoPagina" antes do onclick="jsfcljs(...);return false"
        # cancelar, e o DOM ficava na listagem ao invés de carregar o form.
        info = self._page.evaluate(
            """(candidatos) => {
                const norm = s => (s||'').toUpperCase().replace(/\\s+/g,' ').trim();
                const trs = [...document.querySelectorAll('tr')];
                for (const alvo of candidatos) {
                    const alvoN = norm(alvo);
                    for (const tr of trs) {
                        if (!norm(tr.textContent).includes(alvoN)) continue;
                        const a1 = tr.querySelector('a.linkParametrizar[title^="Parâmetros"], a.linkParametrizar[title^="Parametros"]');
                        if (a1 && a1.id) return {id: a1.id, via: 'class-title:'+alvo};
                        const links = [...tr.querySelectorAll('a.linkParametrizar')];
                        for (const link of links) {
                            if (link.id && link.id.includes(':listaReflexo:')) continue;
                            if (link.id) return {id: link.id, via: 'class-only:'+alvo};
                        }
                        const t1 = tr.querySelector('a[title*="arâmetros"], a[title*="arametros"]');
                        if (t1 && t1.id) return {id: t1.id, via: 'title-fallback:'+alvo};
                    }
                }
                return null;
            }""",
            candidatos,
        )
        clicou = None
        if info and info.get("id"):
            try:
                # Escapar `:` no id para CSS selector
                esc = info["id"].replace(":", "\\:")
                self._page.locator(f"a#{esc}").first.click(force=True, timeout=5000)
                clicou = info["via"]
            except Exception as e:
                self.log(f"    ⚠ Falha click Playwright em a#{info['id']}: {e}")
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
        # CRÍTICO: aguardar o form de Alteração carregar. Sem isso, o caller
        # tenta preencher na listagem ainda (sem campos de form) e o save flex
        # falha porque a listagem não tem botão Salvar. Sinal definitivo:
        # input formulario:descricao OU formulario:valorDevido visível.
        try:
            self._page.wait_for_selector(
                "input[id$=':descricao'], input[id$=':valorDevido']",
                state="visible",
                timeout=10000,
            )
            self.log("    ✓ form de Alteração da verba carregado (descricao visível)")
        except Exception:
            # Diagnóstico: dumpar o que está na página atual
            try:
                _diag = self._page.evaluate(
                    """() => {
                        const inputs = [...document.querySelectorAll('input,select')]
                            .map(e => e.id || e.name).filter(Boolean).slice(0, 20);
                        const btns = [...document.querySelectorAll('input[type=submit],button')]
                            .map(b => b.value || b.textContent || b.id).filter(Boolean).slice(0, 10);
                        return {url_tail: location.href.split('/').slice(-2).join('/'),
                                inputs: inputs, botoes: btns,
                                tem_descricao: !!document.querySelector('input[id$=":descricao"]'),
                                tem_salvar: !!document.querySelector('input[id$=":salvar"]')};
                    }"""
                )
                self.log(f"    ⚠ Form de Alteração não carregou em 10s — diag={_diag}")
            except Exception:
                self.log("    ⚠ Form de Alteração não carregou — sem diagnóstico DOM")
            return  # aborta — sem form, não tem o que preencher
        self._preencher_form_parametros_verba(v, com_identificacao=False)

        # NOTA (12/05/2026): "Regerar Ocorrências" só existe em modo LISTAGEM
        # (rendered="#{apresentador.emModoListagem}"). Não está disponível neste
        # form de parâmetros. Movido para _regerar_ocorrencias_verbas() chamado
        # após fim do loop de parametrização (fim da Fase 4).

        # Cascata flex: form de parâmetros pode ter botão "Salvar", "Confirmar"
        # ou "Gravar" dependendo da versão/contexto JSF.
        clicou_save = self._clicar_salvar_flex(timeout_ms=8000)
        if not clicou_save:
            # Segunda tentativa: aguardar AJAX em voo (rerender pode estar
            # repondo o botão) e tentar de novo. Observado em EXPRESSO_DIRETO
            # quando preenchimento de valorInformadoDoDevido dispara blur AJAX
            # que remove temporariamente o botão Salvar do DOM.
            self.log(f"  → retry save após AJAX-wait extra")
            self._aguardar_ajax(5000)
            clicou_save = self._clicar_salvar_flex(timeout_ms=8000)
        if not clicou_save:
            self.log(f"  ⚠ Parâmetros '{v.nome_pjecalc}': sem botão save — pulando ajuste")
            return
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
        """Cartão de Ponto — cria novo cartão via formulário Novo do PJE-Calc.

        Mapeamento DOM baseado em inspeção direta de
        cartaodeponto/apuracao-cartaodeponto.jsf (v2.15.1, 17/05/2026).
        """
        cp = getattr(self.previa, "cartao_de_ponto", None)
        if not cp:
            self.log("Fase 5 — Cartão de Ponto: sem dados (pulando)")
            return
        dados = cp.model_dump(exclude_none=True) if hasattr(cp, "model_dump") else {}
        if not dados:
            self.log("Fase 5 — Cartão de Ponto: vazio (pulando)")
            return

        self.log("Fase 5 — Cartão de Ponto")
        self._navegar_menu("li_calculo_cartao_ponto")
        self._aguardar_ajax(3000)

        # Clicar em Novo para abrir formulário de criação.
        # A listagem (cartaodeponto.jsf) tem 3 botões: Novo / Grade de Ocorrências / Visualizar Cartão.
        # Usar seletor restrito ao painel principal e fallback via JS por value="Novo".
        ja_no_form = self._page.locator("[id$='competenciaInicialInputDate']").count() > 0
        if not ja_no_form:
            clicou_novo = False
            for sel in [
                "input[type='button'][value='Novo']:not([id*='menu'])",
                "input[type='submit'][value='Novo']:not([id*='menu'])",
                "form input[value='Novo']",
            ]:
                try:
                    loc = self._page.locator(sel).first
                    if loc.count() > 0:
                        loc.click(force=True)
                        clicou_novo = True
                        self.log(f"  → click 'Novo' via {sel!r}")
                        break
                except Exception:
                    continue
            # Fallback JS: localizar input/button cujo texto/value seja exatamente "Novo"
            # e que esteja dentro do form principal (não no menu lateral)
            if not clicou_novo:
                try:
                    self._page.evaluate("""
                        () => {
                          const candidatos = Array.from(document.querySelectorAll(
                            "input[value='Novo'], button"
                          )).filter(el => {
                            const txt = (el.value || el.textContent || '').trim();
                            return txt === 'Novo' && !el.closest('[id*=menu]');
                          });
                          if (candidatos[0]) candidatos[0].click();
                        }
                    """)
                    clicou_novo = True
                    self.log("  → click 'Novo' via JS-fallback")
                except Exception as e:
                    self.log(f"  ⚠ Botão 'Novo' não encontrado nem via JS: {e}")

            # Aguardar navegação para o formulário Novo
            self._aguardar_ajax(4000)
            try:
                self._page.wait_for_selector(
                    "[id$='competenciaInicialInputDate']", state="visible", timeout=10000
                )
            except Exception:
                # Fallback final: navegar diretamente para apuracao-cartaodeponto.jsf
                conv_id = getattr(self, "_calculo_conversation_id", None)
                if conv_id:
                    base = self._page.url.split("/pjecalc/")[0]
                    direct = f"{base}/pjecalc/pages/cartaodeponto/apuracao-cartaodeponto.jsf?conversationId={conv_id}"
                    self.log(f"  → fallback URL direto: {direct}")
                    self._page.goto(direct, wait_until="domcontentloaded")
                    self._aguardar_ajax(3000)
                    try:
                        self._page.wait_for_selector(
                            "[id$='competenciaInicialInputDate']", state="visible", timeout=10000
                        )
                    except Exception as e:
                        self.log(f"  ⚠ Formulário Novo não carregou após fallback URL: {e} — pulando Cartão de Ponto")
                        return
                else:
                    self.log("  ⚠ Formulário Novo não carregou e não há conversationId — pulando Cartão de Ponto")
                    return

        # ── Período ──────────────────────────────────────────────────────────
        if cp.data_inicial:
            self._preencher("competenciaInicialInputDate", cp.data_inicial)
            self._aguardar_ajax(1000)
        if cp.data_final:
            self._preencher("competenciaFinalInputDate", cp.data_final)
            self._aguardar_ajax(1000)

        # ── Formas de Apuração ────────────────────────────────────────────────
        apu = cp.apuracao if cp.apuracao else None
        tipo_apu = getattr(apu, "tipo", "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL")
        self._marcar_radio("tipoApuracaoHorasExtras", tipo_apu)
        self._aguardar_ajax(500)
        if getattr(apu, "qtsumulatst", None):
            self._preencher("qtsumulatst", apu.qtsumulatst, obrigatorio=False)
        if getattr(apu, "qthoraseparado", None):
            self._preencher("qthoraseparado", apu.qthoraseparado, obrigatorio=False)

        # ── Considerar Feriados ───────────────────────────────────────────────
        self._marcar_checkbox("considerarFeriado", cp.considerar_feriados)
        self._marcar_checkbox("extraFeriadoSeparado", cp.extras_feriados_separado)
        self._marcar_checkbox("extraDescansoSeparado", cp.extras_domingos_separado)
        self._marcar_checkbox("extraSabadoDomingoSeparado", cp.extras_sabados_domingos_separado)

        # ── Tolerância ────────────────────────────────────────────────────────
        self._marcar_checkbox("tolerancia", cp.tolerancia_ativa)
        if cp.tolerancia_ativa:
            self._preencher("toleranciaPorTurno", cp.tolerancia_por_turno, obrigatorio=False)
            self._preencher("toleranciaPorDia", cp.tolerancia_por_dia, obrigatorio=False)

        # ── Jornada Padrão ────────────────────────────────────────────────────
        j = cp.jornada_padrao if cp.jornada_padrao else None
        # Em modo PROGRAMACAO/ESCALA, a fonte de verdade é a tabela detalhada de turnos.
        # Os campos "Jornada Diária Padrão" (Seg-Dom) e os totais Jornada Semanal/Mensal
        # têm DEFAULTS no PJE-Calc consistentes com qtJornadaSemanal=44 (Sáb=08:00).
        # Sobrescrevê-los com valores inconsistentes (ex.: Sáb=00:00 + Sem=44,00) faz
        # o backend disparar "Erro inesperado JSF" no save.
        # Estratégia: só preencher esses campos no modo LIVRE (fora dele, deixar defaults).
        modo_atual = getattr(cp, "preenchimento", "LIVRE")
        if j and modo_atual == "LIVRE":
            self._preencher("valorJornadaSegunda", getattr(j, "segunda_hhmm", "08:00"))
            self._preencher("valorJornadaTerca",   getattr(j, "terca_hhmm",   "08:00"))
            self._preencher("valorJornadaQuarta",  getattr(j, "quarta_hhmm",  "08:00"))
            self._preencher("valorJornadaQuinta",  getattr(j, "quinta_hhmm",  "08:00"))
            self._preencher("valorJornadaSexta",   getattr(j, "sexta_hhmm",   "08:00"))
            self._preencher("valorJornadaDiariaSabado", getattr(j, "sabado_hhmm", "00:00"))
            self._preencher("valorJornadaDiariaDom",    getattr(j, "domingo_hhmm", "00:00"))
            self._aguardar_ajax(1000)
            if getattr(j, "jornada_semanal", None):
                self._preencher("qtJornadaSemanal",    j.jornada_semanal, obrigatorio=False)
            if getattr(j, "jornada_mensal_media", None):
                self._preencher("qtJornadaMensal", j.jornada_mensal_media, obrigatorio=False)
        elif j:
            self.log(f"  ℹ Pulando jornada padrão (modo={modo_atual}) — defaults preservados")
        self._marcar_checkbox("jornadaDiariaFeriadoTrabalhado",    cp.jornada_feriado_trabalhado)
        self._marcar_checkbox("jornadaDiariaFeriadoNaoTrabalhado", cp.jornada_feriado_nao_trabalhado)

        # ── Períodos de Descanso ──────────────────────────────────────────────
        d = cp.descanso if cp.descanso else None
        if d:
            self._marcar_checkbox("apurarFeriadosTrabalhados",        getattr(d, "apurar_feriados_trabalhados", False))
            self._marcar_checkbox("apurarDomingosTrabalhados",         getattr(d, "apurar_domingos_trabalhados", False))
            self._marcar_checkbox("apurarSabadosDomingosTrabalhados",  getattr(d, "apurar_sabados_domingos", False))
            self._marcar_checkbox("apurarSupressaoIntervalo384",       getattr(d, "apurar_intervalo_384", False))
            self._marcar_checkbox("apurarSupressaoIntervalo72",        getattr(d, "apurar_intervalo_72", False))
            self._marcar_checkbox("apurarSupressaoIntervaloArt253",    getattr(d, "apurar_intervalo_insalubridade", False))
            if getattr(d, "apurar_intervalo_insalubridade", False):
                self._preencher("valorTrabalhoArt253",  getattr(d, "tempo_trabalho_art253", "01:40"), obrigatorio=False)
                self._preencher("valorDescansoArt253",  getattr(d, "tempo_descanso_art253", "00:20"), obrigatorio=False)
            # Interjornadas
            self._marcar_checkbox("descansoEntreJornadas", getattr(d, "descanso_entre_jornadas", False))
            if getattr(d, "descanso_entre_jornadas", False):
                self._selecionar("valorDescansoEntreJornadas", getattr(d, "valor_descanso_entre_jornadas", "11:00"))
                self._selecionar("valorDescansoEntreSemanas",  getattr(d, "valor_descanso_entre_semanas", "35:00"))
            # Intrajornada >4h–6h
            self._marcar_checkbox("intervaloIntraJornadaSupQuatroSeis", getattr(d, "intervalo_sup_4h_6h", False))
            if getattr(d, "intervalo_sup_4h_6h", False):
                self._preencher("valorIntervaloIntraJornadaSupQuatroSeis", getattr(d, "tolerancia_sup_4h_6h", "00:15"), obrigatorio=False)
            # Intrajornada >6h (nota: DOM tem typo "intervalor" → preservado)
            self._marcar_checkbox("intervalorIntraJornadaSupSeis", getattr(d, "intervalo_sup_6h", False))
            if getattr(d, "intervalo_sup_6h", False):
                self._preencher("valorIntervalorIntraJornadaSupSeis",        getattr(d, "valor_intervalo_sup_6h", "01:00"), obrigatorio=False)
                self._preencher("toleranciaIntervaloIntraJornadaSupSeis",    getattr(d, "tolerancia_sup_6h", "00:05"), obrigatorio=False)
            self._marcar_checkbox("considerarFracionamentoIntra",          getattr(d, "considerar_fracionamento", False))
            self._marcar_checkbox("apurarSupressaoIntervaloIntraIntegral", getattr(d, "apurar_supressao_integral", False))
            self._marcar_checkbox("apurarSupressaoIntervaloIntraReforma",  getattr(d, "apurar_supressao_reforma", False))
            self._marcar_checkbox("apurarExcessoIntervaloIntra",           getattr(d, "apurar_excesso_sumula118", False))
            if getattr(d, "apurar_excesso_sumula118", False):
                self._preencher("valorIntervaloIntrajornadaMaximo", getattr(d, "valor_intervalo_max_sumula118", "02:00"), obrigatorio=False)
            self._marcar_checkbox("apurarApenasExcessoAcimaJornada", getattr(d, "apurar_apenas_excesso_jornada", False))

        # ── Horário Noturno ───────────────────────────────────────────────────
        n = cp.noturno if cp.noturno else None
        if n:
            tipo_not = getattr(n, "tipo_atividade", "ATIVIDADE_URBANA")
            self._marcar_radio("horarioNoturnoApuracaroCartao", tipo_not)
            self._marcar_checkbox("apurarHorasNoturnas",             getattr(n, "apurar_horas_noturnas", False))
            self._marcar_checkbox("apurarHorasExtrasNoturnas",       getattr(n, "apurar_horas_extras_noturnas", False))
            self._marcar_checkbox("considerarReducaoFictaDaHoraNoturna", getattr(n, "reducao_ficta", True))
            self._marcar_checkbox("horarioProrrogadoSumula60",       getattr(n, "horario_prorrogado_sumula60", False))
            self._marcar_checkbox("forcarProrrogacao",               getattr(n, "forcar_prorrogacao", False))

        # ── Preenchimento de Jornadas ─────────────────────────────────────────
        # CRÍTICO: o radio dispara AJAX que renderiza a tabela (listagemProgramacao ou
        # listagemEscala). Disparar change explicitamente e aguardar a tabela aparecer
        # antes de tentar preencher os turnos — sem isso, os campos não existem ainda.
        preenchimento = getattr(cp, "preenchimento", "LIVRE")
        self._marcar_radio("preenchimentoJornadasCartao", preenchimento)
        # Disparar evento change para garantir trigger do RichFaces AJAX
        try:
            self._page.evaluate("""
                (val) => {
                  const r = document.querySelector(
                    `input[type='radio'][name*='preenchimentoJornadasCartao'][value='${val}']`
                  );
                  if (r) {
                    r.dispatchEvent(new Event('click', {bubbles:true}));
                    r.dispatchEvent(new Event('change', {bubbles:true}));
                  }
                }
            """, preenchimento)
        except Exception:
            pass
        self._aguardar_ajax(2500)

        # ── Programação Semanal — tabela 8 dias × 6 turnos ────────────────────
        # Mapeamento DOM: formulario:listagemProgramacao:{D}:{entradaM|saidaM}
        # D=0 Segunda, 1 Terça, ..., 6 Domingo, 7 Feriado; M=1..6
        if preenchimento == "PROGRAMACAO":
            ps = getattr(cp, "programacao_semanal", None)
            if ps:
                # Aguardar a tabela renderizar via AJAX (até 10s)
                try:
                    self._page.wait_for_selector(
                        "[id$='listagemProgramacao:0:entrada1']",
                        state="visible",
                        timeout=10000,
                    )
                except Exception:
                    self.log("  ⚠ Tabela Programação Semanal não renderizou — tentando recliclar radio")
                    self._page.evaluate("""
                        () => {
                          const r = document.querySelector(
                            "input[type='radio'][value='PROGRAMACAO']"
                          );
                          if (r && !r.checked) r.click();
                        }
                    """)
                    self._aguardar_ajax(3000)
                _CP_DIA_IDX = {"segunda":0, "terca":1, "quarta":2, "quinta":3,
                               "sexta":4, "sabado":5, "domingo":6, "feriado":7}
                # CRÍTICO: preencher + Tab para forçar blur natural após cada campo.
                # Sem isso o JSF backing bean não recebe os valores e o save falha
                # com "A jornada deve ter pelo menos um período de lançamento" ou NPE.
                campos_preenchidos: list[str] = []
                # Estratégia: simular digitação humana real:
                # 1. click() — foca + posiciona cursor
                # 2. type() — digita caractere por caractere (dispara keydown/keyup/input)
                # 3. press("Tab") — blur natural saindo do campo (dispara change + a4j:support)
                # Aguardar AJAX entre cada campo para o RichFaces atualizar backing bean.
                for dia_nome, idx in _CP_DIA_IDX.items():
                    jd = getattr(ps, dia_nome, None)
                    if not jd:
                        continue
                    for t_idx, turno in enumerate(getattr(jd, "turnos", [])[:6]):
                        m = t_idx + 1
                        for campo, valor in (("entrada", getattr(turno, "entrada", "")),
                                             ("saida",   getattr(turno, "saida",   ""))):
                            if not valor:
                                continue
                            sel = f"[id$='listagemProgramacao:{idx}:{campo}{m}']"
                            try:
                                loc = self._page.locator(sel).first
                                # Foca + seleciona tudo + limpa + digita
                                loc.click()
                                loc.press("Control+a")
                                loc.press("Delete")
                                loc.type(str(valor), delay=20)
                                # Blur via Tab — RichFaces precisa para disparar a4j:support
                                loc.press("Tab")
                                # Aguardar AJAX do blur (RichFaces atualiza backing bean)
                                self._page.wait_for_timeout(300)
                                campos_preenchidos.append(f"listagemProgramacao:{idx}:{campo}{m}")
                                self.log(f"  ✓ listagemProgramacao:{idx}:{campo}{m} = {valor}")
                            except Exception as e:
                                self.log(f"  ⚠ Falha ao preencher listagemProgramacao:{idx}:{campo}{m}: {e}")
                self._aguardar_ajax(2000)
                self.log(f"  ✓ {len(campos_preenchidos)} campos da Programação preenchidos (click+type+Tab)")

        # ── Escala — tipo + início + qtd_dias + tabela N × 6 turnos ────────────
        # Mapeamento DOM:
        #   formulario:escalas (select)
        #   formulario:valorHoraInicioEscala (text DD/MM/YYYY)
        #   formulario:qtdDiasTrabalhados (text número)
        #   formulario:listagemEscala:{D}:{entradaM|saidaM}
        elif preenchimento == "ESCALA":
            esc = getattr(cp, "escala", None)
            if esc:
                # Aguardar campos da Escala renderizarem após radio ESCALA
                try:
                    self._page.wait_for_selector(
                        "[id$='escalas']", state="visible", timeout=10000,
                    )
                except Exception:
                    self.log("  ⚠ Campos da Escala não renderizaram após radio ESCALA")
                tipo_escala = getattr(esc, "tipo", "OUTRA")
                if hasattr(tipo_escala, "value"):
                    tipo_escala = tipo_escala.value
                self._selecionar("escalas", tipo_escala)
                self._aguardar_ajax(800)
                if getattr(esc, "inicio", ""):
                    self._preencher("valorHoraInicioEscala", esc.inicio, obrigatorio=False)
                qtd = int(getattr(esc, "quantidade_dias", 1) or 1)
                self._preencher("qtdDiasTrabalhados", str(qtd), obrigatorio=False)
                self._aguardar_ajax(1500)
                try:
                    self._page.wait_for_selector(
                        "[id$='listagemEscala:0:entrada1']",
                        state="visible",
                        timeout=8000,
                    )
                except Exception:
                    self.log("  ⚠ Tabela Escala não renderizou após qtdDiasTrabalhados")
                for d_idx, jd in enumerate(getattr(esc, "jornadas", [])[:qtd]):
                    for t_idx, turno in enumerate(getattr(jd, "turnos", [])[:6]):
                        m = t_idx + 1
                        if getattr(turno, "entrada", ""):
                            self._preencher(f"listagemEscala:{d_idx}:entrada{m}", turno.entrada, obrigatorio=False)
                        if getattr(turno, "saida", ""):
                            self._preencher(f"listagemEscala:{d_idx}:saida{m}",   turno.saida,   obrigatorio=False)

        # ── Salvar ────────────────────────────────────────────────────────────
        try:
            self._clicar("salvar")
            self._aguardar_ajax(8000)
            sucesso = self._aguardar_operacao_sucesso(timeout_ms=15000, bloqueante=False)
            if not sucesso:
                erro = self._verificar_erro_jsf()
                if erro:
                    self.log(f"  ⚠ Erro ao salvar Cartão de Ponto: {erro[:200]}")
                # Diagnóstico forense detalhado quando o save falha
                try:
                    diag = self._page.evaluate(r"""
                        () => {
                          const result = {url: location.href, msgs: [], invalids: [], modal_text: null, body_excerpts: []};
                          // 1. Capturar mensagens RichFaces específicas com texto
                          ['.rf-msg-err', '.rf-msgs-err', '.rich-message', '.rich-messages',
                           '.rich-messages-marker', '.rich-message-detail',
                           '.rf-msgs-sum', '.rf-msg-sum', '.rf-msgs', '.rf-msg',
                           '.messageError', '.errorMessage',
                           "[id*='Erro']", "[id$='Error']", "[id*='msgs']",
                           "span.rich-message-detail", "span.rich-message-summary"].forEach(sel => {
                            document.querySelectorAll(sel).forEach(el => {
                              const t = (el.textContent || '').trim();
                              if (t && t.length > 3 && t.length < 500 && !t.match(/^(Erro|\.|\s+)$/)) {
                                result.msgs.push(`${sel}: ${t}`);
                              }
                            });
                          });
                          // 2. tooltip / title de elementos com erro
                          document.querySelectorAll('[title], [data-tooltip]').forEach(el => {
                            const tt = el.title || el.getAttribute('data-tooltip') || '';
                            if (tt && /obrigat|inv[áa]lido|erro|requir/i.test(tt) && tt.length < 300) {
                              result.msgs.push(`tooltip: ${tt}`);
                            }
                          });
                          // 3. Inputs com classes de erro JSF
                          document.querySelectorAll('input.invalid, input[aria-invalid="true"], .rich-message-marker').forEach(el => {
                            result.invalids.push(el.id || el.name || el.outerHTML.substring(0, 100));
                          });
                          // 4. Modal / dialog
                          const modal = document.querySelector('.rf-pp-cnt, .rich-modalpanel-content, .ui-dialog, .rich-mpnl-pnl');
                          if (modal) result.modal_text = modal.textContent.trim().substring(0, 500);
                          // 5. Procurar no body por linhas com palavras-chave de erro
                          const body = document.body?.textContent || '';
                          const linhas = body.split('\n').map(l => l.trim()).filter(l => l.length > 10 && l.length < 250);
                          for (const l of linhas) {
                            if (/obrigat|inv[áa]lido|n[ãa]o pode|deve ser|erro/i.test(l) && !l.match(/Erro inesperado/i)) {
                              result.body_excerpts.push(l);
                              if (result.body_excerpts.length >= 5) break;
                            }
                          }
                          return result;
                        }
                    """)
                    if diag:
                        self.log(f"  [DIAG-cartao-save] url={diag.get('url', '')[:80]}")
                        for m in (diag.get('msgs') or [])[:10]:
                            self.log(f"  [DIAG-cartao-save] msg: {m[:300]}")
                        for ex in (diag.get('body_excerpts') or [])[:5]:
                            self.log(f"  [DIAG-cartao-save] body: {ex[:250]}")
                        if diag.get('invalids'):
                            self.log(f"  [DIAG-cartao-save] inválidos: {diag['invalids'][:5]}")
                        if diag.get('modal_text'):
                            self.log(f"  [DIAG-cartao-save] modal: {diag['modal_text']}")
                except Exception as e_diag:
                    self.log(f"  [DIAG-cartao-save] falha capturar: {e_diag}")
            # Aplicar overrides via Grade de Ocorrências, se houver.
            # CRÍTICO: isolar em try/except para evitar invalidar a conv Seam
            # (sem isso, FGTS/CS/IRPF subsequentes ficam sem bean → liquidação falha).
            overrides = list(getattr(cp, "ocorrencias_override", []) or [])
            if overrides:
                try:
                    self._aplicar_ocorrencias_override(overrides)
                except Exception as e_ov:
                    self.log(f"  ⚠ Overrides falharam (não-crítico): {e_ov}")
                # SEMPRE retornar para o calculo.jsf via menu para restaurar contexto Seam
                try:
                    self._navegar_menu("li_calculo_dados_do_calculo")
                    self._aguardar_ajax(2000)
                    self.log("  ✓ Contexto Seam restaurado pós-overrides")
                except Exception:
                    pass
            self.log("Fase 5 concluída")
        except Exception as e:
            self.log(f"  ⚠ Fase 5 — Salvar: {e}")

    def _aplicar_ocorrencias_override(self, overrides: list) -> None:
        """Aplica overrides de jornada na Grade de Ocorrências (apuracao-cartaodeponto).

        Para cada override (data, turnos), navega para a Grade do mês correspondente,
        localiza a linha pela data e preenche entradaM/saidaM.

        ⚠️ Mapeamento DOM da Grade ainda PARCIAL — confirmar IDs por inspeção direta.
        """
        if not overrides:
            return
        self.log(f"  → Aplicando {len(overrides)} ocorrências override na Grade")
        # Agrupar por (mes, ano)
        from collections import defaultdict
        por_mes: dict[str, list] = defaultdict(list)
        def _campo(o, k, default=None):
            """Acessa campo em Pydantic OU dict, sem quebrar."""
            if isinstance(o, dict):
                return o.get(k, default)
            return getattr(o, k, default)

        for oc in overrides:
            data = _campo(oc, "data")
            if not data or "/" not in data:
                continue
            dd, mm, yyyy = data.split("/")
            por_mes[f"{mm}/{yyyy}"].append(oc)

        # Navegar para a Grade — botão "Grade de Ocorrências" na listagem do Cartão de Ponto
        try:
            # Voltar à listagem do cartão de ponto (botão Voltar/Fechar ou navegação direta)
            self._navegar_menu("li_calculo_cartao_ponto")
            self._aguardar_ajax(2000)
            grade_btn = self._page.locator(
                "input[value='Grade de Ocorrências'], button:has-text('Grade de Ocorrências'), a:has-text('Grade de Ocorrências')"
            ).first
            grade_btn.click(force=True)
            self._aguardar_ajax(3000)
        except Exception as e:
            self.log(f"  ⚠ Grade de Ocorrências não acessível: {e}")
            return

        # Para cada mês, selecionar via dropdown Mês/Ano e aplicar overrides
        for mes_ano, ocs in por_mes.items():
            try:
                self._selecionar("mesAno", mes_ano)
                self._aguardar_ajax(2000)
            except Exception:
                # Tentar IDs alternativos do dropdown
                for alt_id in ("competenciaApuracao", "mesAnoApuracao", "filtroMesAno"):
                    try:
                        self._selecionar(alt_id, mes_ano)
                        self._aguardar_ajax(2000)
                        break
                    except Exception:
                        continue
            # Para cada ocorrência: localizar linha pela data e preencher turnos
            for oc in ocs:
                data = _campo(oc, "data")
                turnos = _campo(oc, "turnos") or []
                try:
                    row = self._page.locator(f"tr:has(td:has-text('{data}'))").first
                    for t_idx, turno in enumerate(turnos[:6]):
                        m = t_idx + 1
                        ent = _campo(turno, "entrada", "")
                        sai = _campo(turno, "saida", "")
                        if ent:
                            row.locator(f"input[id$='entrada{m}']").first.fill(ent)
                        if sai:
                            row.locator(f"input[id$='saida{m}']").first.fill(sai)
                except Exception as e:
                    self.log(f"    ⚠ Falha ao aplicar override {data}: {e}")
            # Salvar mês
            try:
                self._clicar("salvar")
                self._aguardar_ajax(3000)
            except Exception:
                pass
        self.log(f"  ✓ Overrides aplicados")

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
        """Férias — tabela auto-gerada pelo PJE-Calc a partir de admissão/desligamento.

        IMPORTANTE (corrigido 14/05/2026): conforme manual oficial
        (knowledge/pje_calc_official/manual_completo.md §7, linha 207):

            "O sistema gera automaticamente os dados de ferias a partir de:
             datas de admissao/desligamento, regime de trabalho e faltas"
            "O usuario DEVE verificar e modificar os status sugeridos, marcar
             abonos, e informar periodos de gozo efetivos"
            "CRITICO: Clicar 'Salvar' apos modificacoes" (UM único save)

        Bug anterior: este método clicava `[id$=':incluir']` para cada período,
        mas a página ferias.jsf não tem botão Incluir (períodos já vêm
        pré-populados). 4 períodos pulados com "Botão não encontrado: incluir".

        Estratégia correta: localizar linhas auto-geradas, editar
        (status/abono/dobra/gozos) por índice, UM save no final.
        """
        ferias = getattr(self.previa, "ferias", None)
        if not ferias or not ferias.periodos:
            self.log("Fase 7 — Férias: sem períodos (pulando)")
            return

        self.log(f"Fase 7 — Férias ({len(ferias.periodos)} período(s))")
        self._navegar_menu("li_calculo_ferias")
        self._aguardar_ajax(10000)
        self._page.wait_for_timeout(1500)

        # Campos globais (no topo da página)
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

        # Tentar clicar "Regerar Férias" (manual oficial §7 linha 248) para
        # forçar o sistema a gerar as linhas auto-populadas a partir de
        # admissão/desligamento. Sem isso, a tabela pode vir vazia quando
        # esta fase roda antes da Fase 4 (Verbas).
        regerou = self._page.evaluate(
            """() => {
                const norm = s => (s||'').trim().toUpperCase();
                // Tentar por sufixo de id primeiro
                const ids = ['regerarFerias','regerar','recuperarFerias','gerarFerias'];
                for (const idSuf of ids) {
                    const inp = document.querySelector(`input[id$=':${idSuf}'], input[id$='${idSuf}']`);
                    if (inp && inp.offsetParent) { inp.click(); return 'id:'+idSuf; }
                }
                // Fallback por texto do botão
                const inputs = [...document.querySelectorAll('input[type=submit],input[type=button],button,a')];
                for (const v of inputs) {
                    const t = norm(v.value || v.textContent);
                    if (t.includes('REGERAR') && t.includes('F')) { v.click(); return 'text:'+t.slice(0,30); }
                }
                return null;
            }"""
        )
        if regerou:
            self.log(f"  ✓ Regerar Férias acionado: {regerou}")
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(2000)
        else:
            self.log("  ℹ Botão 'Regerar Férias' não encontrado — prosseguindo com diagnóstico DOM")

        # Diagnóstico DOM: descobrir id real das linhas auto-geradas
        diag = self._page.evaluate(
            """() => {
                const rows = [...document.querySelectorAll(
                    'tr[id*="dataTable"], tr[id*="listagem"], tr[id*="rowData"]'
                )];
                const sample = rows.slice(0, 5).map(r => ({
                    id: r.id,
                    cells: [...r.querySelectorAll('td')].length,
                    has_radio: !!r.querySelector('input[type=radio]'),
                    has_checkbox: !!r.querySelector('input[type=checkbox]'),
                    has_select: !!r.querySelector('select'),
                    inputs_inside: [...r.querySelectorAll('input,select')]
                        .map(e => (e.id||e.name||'').split(':').pop()).filter(Boolean).slice(0, 8)
                }));
                // descobrir prefixo comum (até o último ":")
                const prefixos = rows.map(r => r.id.split(':').slice(0,-1).join(':'))
                    .filter(Boolean);
                const prefixo_comum = prefixos.length ? prefixos[0] : null;
                // todos campos editáveis com id contendo gozo/situacao/abono/dobra
                const editaveis = [...document.querySelectorAll('input,select')]
                    .filter(e => /situacao|abono|dobra|gozo|prazo/i.test(e.id||''))
                    .map(e => e.id).slice(0, 40);
                return {
                    n_rows: rows.length,
                    sample,
                    prefixo_comum,
                    editaveis
                };
            }"""
        )
        self.log(f"  ℹ Diagnóstico Férias: {diag.get('n_rows')} linha(s) auto-geradas")
        if diag.get("sample"):
            self.log(f"  ℹ Sample linha[0]: {diag['sample'][0]}")
        if diag.get("editaveis"):
            self.log(f"  ℹ Campos editáveis (até 10): {diag['editaveis'][:10]}")

        prefixo = diag.get("prefixo_comum") or ""
        n_linhas = diag.get("n_rows") or 0

        # Férias rows: tr[id*="dataTable|listagem|rowData"] NÃO corresponde ao DOM real.
        # As linhas auto-geradas usam formulario:j_id106:N:campo — detectar via editaveis.
        if n_linhas == 0:
            import re as _re
            _editaveis = diag.get("editaveis", [])
            _sit_ids = [e for e in _editaveis if e.endswith(":situacao")]
            if _sit_ids:
                _m = _re.match(r"^(.+):\d+:situacao$", _sit_ids[0])
                if _m:
                    prefixo = _m.group(1)
                    _indices = []
                    for _sid in _sit_ids:
                        _m2 = _re.match(r"^.+:(\d+):situacao$", _sid)
                        if _m2:
                            _indices.append(int(_m2.group(1)))
                    n_linhas = max(_indices) + 1 if _indices else len(_sit_ids)
                    self.log(
                        f"  ℹ Férias: prefixo real='{prefixo}', {n_linhas} linha(s) "
                        f"(extraído de editaveis)"
                    )

        # Editar cada período — tentar mapear por índice ao JSON
        for i, p in enumerate(ferias.periodos):
            self.log(
                f"  → Período {i+1}: aquisitivo "
                f"{p.periodo_aquisitivo_inicio} → {p.periodo_aquisitivo_fim}"
            )
            if i >= n_linhas:
                self.log(
                    f"    ⚠ JSON tem {len(ferias.periodos)} períodos, mas só {n_linhas} "
                    f"linhas auto-geradas — pulando excedente"
                )
                continue

            # Cascata de seletores para cada campo da linha i
            row_prefix_candidates = []
            if prefixo:
                # JSF dataTable padrão: prefixo:N:campo
                row_prefix_candidates.append(f"{prefixo}:{i}:")
            row_prefix_candidates.extend([
                f"dataTable:{i}:",
                f"listagem:{i}:",
                f"rowData:{i}:",
            ])

            def _try_field(suffixes_per_row, valor_callback, kind="preencher"):
                """Tenta cada combinação prefixo+sufixo até achar campo."""
                for rp in row_prefix_candidates:
                    for suf in suffixes_per_row:
                        full = rp + suf
                        loc = self._page.locator(f"[id$='{full}']")
                        if loc.count() > 0:
                            try:
                                valor_callback(full)
                                return True
                            except Exception:
                                continue
                return False

            # Situação (select ou radio) — select PRIMEIRO para evitar falso-positivo
            # com _marcar_radio(obrigatorio=False) que retorna silenciosamente em selects.
            try:
                _sit_ok = False
                for _rp in row_prefix_candidates:
                    for _suf in ("situacaoFerias", "situacao", "tipoSituacao"):
                        _full_sit = _rp + _suf
                        if self._page.locator(f"select[id$='{_full_sit}']").count() > 0:
                            self._selecionar(_full_sit, p.situacao, obrigatorio=False)
                            _sit_ok = True
                            break
                        if self._page.locator(f"input[type='radio'][id*='{_full_sit}']").count() > 0:
                            self._marcar_radio(_full_sit, p.situacao, obrigatorio=False)
                            _sit_ok = True
                            break
                    if _sit_ok:
                        break
                if not _sit_ok:
                    self.log(f"    ⚠ situacao período {i+1}: campo não localizado")
            except Exception as e:
                self.log(f"    ⚠ situacao período {i+1}: {e}")

            self._aguardar_ajax(2000)

            # Dobra (checkbox)
            try:
                for rp in row_prefix_candidates:
                    cb = self._page.locator(f"input[type='checkbox'][id$='{rp}dobra']")
                    if cb.count() > 0:
                        if cb.first.is_checked() != p.dobra:
                            cb.first.click(force=True)
                        break
            except Exception as e:
                self.log(f"    ⚠ dobra período {i+1}: {e}")

            # Abono (checkbox + dias)
            try:
                for rp in row_prefix_candidates:
                    cb = self._page.locator(f"input[type='checkbox'][id$='{rp}abono']")
                    if cb.count() > 0:
                        if cb.first.is_checked() != p.abono:
                            cb.first.click(force=True)
                        if p.abono and p.dias_abono:
                            self._preencher(
                                f"{rp}diasAbono", str(p.dias_abono),
                                obrigatorio=False
                            )
                        break
            except Exception as e:
                self.log(f"    ⚠ abono período {i+1}: {e}")

            # Gozos (até 3)
            for j, gozo in enumerate([p.gozo_1, p.gozo_2, p.gozo_3], start=1):
                if not (gozo and gozo.data_inicio):
                    continue
                for rp in row_prefix_candidates:
                    inicio = self._page.locator(
                        f"input[id$='{rp}gozoInicio{j}InputDate']"
                    )
                    if inicio.count() > 0:
                        try:
                            self._preencher(
                                f"{rp}gozoInicio{j}InputDate",
                                gozo.data_inicio,
                                obrigatorio=False,
                            )
                            self._preencher(
                                f"{rp}gozoFim{j}InputDate",
                                gozo.data_fim,
                                obrigatorio=False,
                            )
                            if gozo.dobra:
                                cb_dobra = self._page.locator(
                                    f"input[type='checkbox'][id$='{rp}gozoDobra{j}']"
                                )
                                if cb_dobra.count() > 0 and not cb_dobra.first.is_checked():
                                    cb_dobra.first.click(force=True)
                        except Exception as e:
                            self.log(f"    ⚠ gozo {j} período {i+1}: {e}")
                        break

        # UM ÚNICO SAVE no final (manual oficial: "Clicar 'Salvar' após modificações")
        # Cascata flex porque página pode ter salvar/confirmar/aplicar dependendo do estado.
        if n_linhas > 0:
            try:
                clicou = self._clicar_salvar_flex(timeout_ms=8000)
                if clicou:
                    self._aguardar_ajax(10000)
                    sucesso = self._aguardar_operacao_sucesso(timeout_ms=15000, bloqueante=False)
                    if sucesso:
                        self.log("  ✓ Férias salvas")
                    else:
                        self._diagnostico_pagina(contexto="pós-save Férias")
            except Exception as e:
                self.log(f"  ⚠ save Férias: {e}")
        else:
            self.log("  ℹ Sem linhas de férias para salvar (página vazia)")

        self.log("Fase 7 concluída")

    def fase_fgts(self) -> None:
        self.log("Fase 8 — FGTS")
        # Click sidebar (Seam init) — URL direta não dispara @PostConstruct do bean
        if not self._navegar_menu_via_click("li_calculo_fgts"):
            self._navegar_menu("li_calculo_fgts")  # fallback URL direta
        self._aguardar_ajax(8000)
        self._page.wait_for_timeout(1500)

        # Diagnóstico FGTS — inclui dump completo de ids/names para depuração
        _diag_fgts = self._page.evaluate("""() => {
            const body = document.body?.textContent || '';
            const allInputs = [...document.querySelectorAll('input,select')].map(el => ({
                tag: el.tagName, type: el.type || '', id: (el.id||'').slice(-40),
                name: (el.name||'').slice(-40), value: (el.value||'').slice(0,20)
            }));
            return {
                url: location.href.slice(-60),
                tem_500: body.includes('HTTP Status 500') || body.includes('NullPointerException'),
                tem_form: !!document.getElementById('formulario'),
                radios_id: document.querySelectorAll('input[type=radio][id*=tipoDeVerba]').length,
                radios_name: document.querySelectorAll('input[type=radio][name*=tipoDeVerba]').length,
                todos_inputs: allInputs.length,
                inputs_dump: allInputs.slice(0, 25),
                msgs: [...document.querySelectorAll('.rich-messages-label,.rf-msgs-sum')]
                    .map(e=>(e.textContent||'').trim()).slice(0,3)
            };
        }""")
        self.log(f"  [DIAG-fgts] url={_diag_fgts['url']} tem_form={_diag_fgts['tem_form']} "
                 f"tem_500={_diag_fgts['tem_500']} radios_id={_diag_fgts['radios_id']} "
                 f"radios_name={_diag_fgts['radios_name']} n_inputs={_diag_fgts['todos_inputs']}")
        self.log(f"  [DIAG-fgts-inputs] {_diag_fgts['inputs_dump']}")

        # Verificar que página renderizou — usar tem_form (não tipoDeVerba, que pode ter ID dinâmico)
        if _diag_fgts['tem_500'] or not _diag_fgts['tem_form']:
            self.log("  ⚠ Fase 8 FGTS: página não renderizou (HTTP 500 ou sem formulário) — pulando")
            return
        # Checar se há campos reais de FGTS (radios ou checkboxes) — não só a frame da página.
        # Conv pré-Expresso renderiza a frame (Salvar/Ocorrências) mas sem campos reais.
        _n_form_fields = _diag_fgts.get('radios_id', 0) + _diag_fgts.get('radios_name', 0)
        if _n_form_fields == 0:
            # Contar radios+checkboxes no DOM diretamente
            _n_actual = self._page.evaluate(
                """() => document.querySelectorAll(
                    'input[type=radio],input[type=checkbox]'
                ).length"""
            )
            self.log(f"  [DIAG-fgts-fields] radios+checkboxes na página: {_n_actual}")
            if _n_actual == 0:
                # Tentar recuperar conv Seam reabrindo + CLICK no menu (não URL direta!)
                # URL direta com conversationId NÃO dispara init() do bean Seam — só
                # o click sidebar invoca o handler JSF que carrega o bean.
                self.log("  ⚠ Fase 8 FGTS: bean ausente — tentando reabrir cálculo + click menu lateral")
                try:
                    if self._reabrir_calculo_via_recentes():
                        # CLICK NO MENU em vez de URL direta — essencial para Seam init
                        clicou = self._page.evaluate("""() => {
                            const li = document.getElementById('li_calculo_fgts');
                            if (li) { const a = li.querySelector('a'); if (a) { a.click(); return true; } }
                            return false;
                        }""")
                        if clicou:
                            self._aguardar_ajax(8000)
                            self._capturar_conversation_id()
                            self.log(f"  ✓ Click menu FGTS — conv: {self._calculo_conversation_id}")
                        else:
                            self.log("  ⚠ li_calculo_fgts não encontrado no menu")
                            return
                        _n_retry = self._page.evaluate(
                            """() => document.querySelectorAll('input[type=radio],input[type=checkbox]').length"""
                        )
                        self.log(f"  [DIAG-fgts-retry] radios+checkboxes pós-click-menu: {_n_retry}")
                        if _n_retry == 0:
                            self.log("  ⚠ Fase 8 FGTS: ainda sem campos após click menu — pulando")
                            return
                    else:
                        self.log("  ⚠ Reabertura via Recentes falhou — pulando FGTS")
                        return
                except Exception as e:
                    self.log(f"  ⚠ Falha ao reabrir cálculo para FGTS: {e} — pulando")
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
        # Click sidebar (Seam init) — URL direta não dispara @PostConstruct do bean
        if not self._navegar_menu_via_click("li_calculo_inss"):
            self._navegar_menu("li_calculo_inss")
        self._aguardar_ajax(8000)
        self._page.wait_for_timeout(1000)
        # Render guard (mesma lógica do FGTS: frame vazia = bean não inicializado)
        _n_cs = self._page.evaluate(
            """() => document.querySelectorAll('input[type=radio],input[type=checkbox]').length"""
        )
        self.log(f"  [DIAG-cs] radios+checkboxes={_n_cs}")
        if _n_cs == 0:
            self.log("  ⚠ Fase 9 CS: bean ausente — tentando reabrir + click menu (Seam init)")
            try:
                if self._reabrir_calculo_via_recentes():
                    clicou = self._page.evaluate("""() => {
                        const li = document.getElementById('li_calculo_inss');
                        if (li) { const a = li.querySelector('a'); if (a) { a.click(); return true; } }
                        return false;
                    }""")
                    if clicou:
                        self._aguardar_ajax(8000)
                        self._capturar_conversation_id()
                    _n_cs_retry = self._page.evaluate(
                        """() => document.querySelectorAll('input[type=radio],input[type=checkbox]').length"""
                    )
                    self.log(f"  [DIAG-cs-retry] radios+checkboxes pós-click-menu: {_n_cs_retry}")
                    if _n_cs_retry == 0:
                        self.log("  ⚠ Fase 9 CS: ainda sem campos — pulando")
                        return
                else:
                    self.log("  ⚠ Reabertura falhou — pulando CS")
                    return
            except Exception as e:
                self.log(f"  ⚠ Falha reabrir para CS: {e} — pulando")
                return
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

        # Sub-página parametrizar-inss para vinculação histórico→CS
        if cs.apurar_segurado_devido or cs.apurar_salarios_pagos:
            try:
                self._clicar("ocorrencias")
                self._aguardar_ajax(8000)
                self._clicar("recuperarDevidos")
                self._aguardar_ajax(5000)
                self._clicar("copiarDevidos")
                self._aguardar_ajax(5000)

                # Modo manual_por_periodo: aplicar Lote por intervalo
                if (getattr(cs, "vinculacao_historicos_devidos", None) is not None
                        and cs.vinculacao_historicos_devidos.modo == "manual_por_periodo"):
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
        # Click sidebar (Seam init) — URL direta não dispara @PostConstruct do bean
        if not self._navegar_menu_via_click("li_calculo_irpf"):
            self._navegar_menu("li_calculo_irpf")
        self._aguardar_ajax(8000)
        self._page.wait_for_timeout(1000)
        _n_ir = self._page.evaluate(
            """() => document.querySelectorAll('input[type=radio],input[type=checkbox]').length"""
        )
        self.log(f"  [DIAG-irpf] radios+checkboxes={_n_ir}")
        if _n_ir == 0:
            self.log("  ⚠ Fase 10 IRPF: bean ausente — tentando reabrir + click menu (Seam init)")
            try:
                if self._reabrir_calculo_via_recentes():
                    clicou = self._page.evaluate("""() => {
                        const li = document.getElementById('li_calculo_irpf');
                        if (li) { const a = li.querySelector('a'); if (a) { a.click(); return true; } }
                        return false;
                    }""")
                    if clicou:
                        self._aguardar_ajax(8000)
                        self._capturar_conversation_id()
                    _n_ir_retry = self._page.evaluate(
                        """() => document.querySelectorAll('input[type=radio],input[type=checkbox]').length"""
                    )
                    self.log(f"  [DIAG-irpf-retry] radios+checkboxes pós-click-menu: {_n_ir_retry}")
                    if _n_ir_retry == 0:
                        self.log("  ⚠ Fase 10 IRPF: ainda sem campos — pulando")
                        return
                else:
                    self.log("  ⚠ Reabertura falhou — pulando IRPF")
                    return
            except Exception as e:
                self.log(f"  ⚠ Falha reabrir para IRPF: {e} — pulando")
                return
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
        self._aguardar_ajax(8000)
        self._page.wait_for_timeout(1000)
        # Verificar que a listagem de honorários renderizou (tem botão Incluir)
        _tem_incluir = self._page.evaluate(
            """() => !!(document.querySelector('input[id$=incluir]') ||
               document.querySelector('input[value=Incluir]') ||
               document.querySelector('a[id$=incluir]'))"""
        )
        if not _tem_incluir:
            self.log("  ⚠ Fase 11 Honorários: página sem botão Incluir — pulando")
            return
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

            # Quando devedor=RECLAMANTE, sempre cobrar (nunca descontar dos créditos)
            if h.tipo_devedor == "RECLAMANTE":
                self._selecionar("formaCobranca", "COBRAR")
                self._aguardar_ajax(1000)

            self._marcar_radio("tipoValor", h.tipo_valor.value)
            self._aguardar_ajax(2000)

            if h.tipo_valor.value == "CALCULADO":
                if h.aliquota_pct is not None:
                    pct = h.aliquota_pct * 100 if h.aliquota_pct < 1 else h.aliquota_pct
                    self._preencher("percentualHonorarios", _fmt_br(pct), obrigatorio=False)
                if h.base_para_apuracao:
                    self._selecionar("baseParaApuracao", h.base_para_apuracao, obrigatorio=False)
            else:
                if h.valor_informado_brl is not None:
                    self._preencher("valorInformado", _fmt_br(h.valor_informado_brl), obrigatorio=False)

            # Credor: para SUCUMBENCIAIS o credor é sempre o advogado da parte contrária
            credor_nome = h.credor.nome if h.credor else None
            if h.tipo_honorario == "SUCUMBENCIAIS":
                if h.tipo_devedor == "RECLAMANTE":
                    credor_nome = "ADVOGADO DO RECLAMADO"
                elif h.tipo_devedor == "RECLAMADO":
                    credor_nome = "ADVOGADO DO RECLAMANTE"
            if credor_nome:
                self._preencher("nomeCredor", credor_nome, obrigatorio=False)
            if h.credor:
                self._marcar_radio("tipoDocumentoCredor", h.credor.doc_fiscal_tipo.value)
                self._preencher("documentoFiscalCredor", h.credor.doc_fiscal_numero, obrigatorio=False)
            self._marcar_checkbox("apurarIr", h.apurar_irrf)

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
        # Click sidebar (Seam init) — URL direta não dispara @PostConstruct do bean.
        # CRÍTICO: sem isso os campos dataVencimento* não existem na DOM e ficam
        # vazios → liquidação rejeita por "Vencimento deve ser >= {data}".
        if not self._navegar_menu_via_click("li_calculo_custas_judiciais"):
            self._navegar_menu("li_calculo_custas_judiciais")
        self._aguardar_ajax(6000)
        self._page.wait_for_timeout(800)
        _n_cst = self._page.evaluate(
            """() => document.querySelectorAll('input[type=radio],select').length"""
        )
        self.log(f"  [DIAG-custas] campos={_n_cst}")
        if _n_cst == 0:
            self.log("  ⚠ Fase 12 Custas: página sem campos — pulando")
            return
        c = self.previa.custas_judiciais
        self._selecionar("baseParaCustasCalculadas", c.base_para_calculadas)
        # Marcar radios COM espera de AJAX após cada (a4j:support re-renderiza o
        # campo de data correspondente apenas quando o tipo é CALCULADA_*/INFORMADA).
        # Sem essa espera, o campo dataVencimento* não é encontrado na DOM seguinte.
        self._marcar_radio("tipoDeCustasDeConhecimentoDoReclamante", c.custas_conhecimento_reclamante)
        self._aguardar_ajax(3000); self._page.wait_for_timeout(800)
        self._marcar_radio("tipoDeCustasDeConhecimentoDoReclamado", c.custas_conhecimento_reclamado)
        self._aguardar_ajax(3000); self._page.wait_for_timeout(800)
        self._marcar_radio("tipoDeCustasDeLiquidacao", c.custas_liquidacao)
        self._aguardar_ajax(3000); self._page.wait_for_timeout(800)

        # Preencher dataVencimento* — validador do PJE-Calc exige data não-nula
        # quando o tipo correspondente é CALCULADA/INFORMADA.
        _dt_venc = (
            getattr(self.previa.parametros_calculo, "data_ajuizamento", None)
            or getattr(self.previa.parametros_calculo, "data_termino_calculo", None)
        )
        if _dt_venc:
            # Diagnóstico: listar quais dataVencimento* existem agora na DOM
            existem = self._page.evaluate("""() => {
                const result = {};
                ['dataVencimentoConhecimentoDoReclamado','dataVencimentoConhecimentoDoReclamante',
                 'dataVencimentoCustasDeLiquidacao','dataVencimentoCustasFixas'].forEach(f => {
                  result[f] = !!document.getElementById('formulario:' + f);
                  result[f + 'InputDate'] = !!document.getElementById('formulario:' + f + 'InputDate');
                });
                return result;
            }""")
            self.log(f"  [DIAG-custas-datas] {existem}")
            for _fid in [
                "dataVencimentoConhecimentoDoReclamado",
                "dataVencimentoConhecimentoDoReclamante",
                "dataVencimentoCustasDeLiquidacao",
                "dataVencimentoCustasFixas",
            ]:
                self._preencher(f"{_fid}InputDate", _dt_venc, obrigatorio=False)
                self._preencher(_fid, _dt_venc, obrigatorio=False)
            self.log(f"  ✓ dataVencimento custas = {_dt_venc}")
        self._clicar("salvar")
        self._aguardar_ajax(8000)
        self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        self.log("Fase 12 concluída")

    def fase_correcao_juros_multa(self) -> None:
        self.log("Fase 13 — Correção, Juros e Multa")
        # Click sidebar (Seam init) — URL direta não dispara @PostConstruct do bean
        if not self._navegar_menu_via_click("li_calculo_correcao_juros_multa"):
            self._navegar_menu("li_calculo_correcao_juros_multa")
        self._aguardar_ajax(6000)
        self._page.wait_for_timeout(800)

        _n_campos = self._page.evaluate(
            """() => document.querySelectorAll('select, input[type=checkbox], input[type=radio]').length"""
        )
        self.log(f"  [DIAG-correcao] campos={_n_campos}")
        if _n_campos == 0:
            self.log("  ⚠ Fase 13 Correção: página sem campos — pulando")
            return

        c = self.previa.correcao_juros_multa

        # Mapeamentos JSON → valores DOM (confirmados via dom_map_condensed.json v2.15.1)
        _INDICE_MAP = {
            "IPCAE": "IPCA_E", "IPCAETR": "IPCA_E_TR",
            "IGPM": "IGP_M",
            "SELIC": "SELIC_SIMPLES", "SELIC_FAZENDA": "SELIC_RECEITA",
            "SELIC_BACEN": "SELIC_COMPOSTA",
            "TUACDT": "TABELA_UNICA",
            "TABELA_DEVEDOR_FAZENDA": "DEVEDOR_FAZENDA_PUBLICA",
            "TABELA_INDEBITO_TRIBUTARIO": "REPETICAO_INDEBITO_TRIBUTARIO",
        }
        _JUROS_MAP = {
            "JUROS_PADRAO": "PADRAO", "JUROS_POUPANCA": "CADERNETA_POUPANCA",
            "JUROS_MEIO_PORCENTO": "SIMPLES_0_5_MES",
            "JUROS_UM_PORCENTO": "SIMPLES_1_MES",
            "JUROS_ZERO_TRINTA_TRES": "SIMPLES_0_0333333_DIA",
            "SELIC": "SELIC_SIMPLES", "SELIC_FAZENDA": "SELIC_RECEITA",
            "SELIC_BACEN": "SELIC_COMPOSTA",
            "FAZENDA_PUBLICA": "FAZENDA_PUBLICA",
        }
        _BASE_JUROS_MAP = {
            "VERBAS": "VERBA", "VERBA": "VERBA",
            "VERBA_INSS": "VERBA_MENOS_CS",
            "VERBA_INSS_PP": "VERBA_MENOS_CS_MENOS_PP",
        }
        _FGTS_CORR_MAP = {
            "UTILIZAR_INDICE_TRABALHISTA": "INDICE_TRABALHISTA",
            "UTILIZAR_INDICE_JAM": "JAM",
            "UTILIZAR_INDICE_JAM_E_TRABALHISTA": "JAM_MAIS_TRABALHISTA",
        }

        # ── Índice de Correção Trabalhista (sufixo real: indiceCorrecao) ─────
        indice_val = _INDICE_MAP.get(c.indice_trabalhista, c.indice_trabalhista)
        self._selecionar("indiceCorrecao", indice_val)

        # ── Combinar com segundo índice de correção ──────────────────────────
        combinar_indice = (
            getattr(c, "combinar_outro_indice", False)
            or getattr(c, "combinar_com_outro_indice", False)
        )
        segundo = getattr(c, "segundo_indice", None) or getattr(c, "indice_correcao_pos", None)
        data_inicio_2 = getattr(c, "data_inicio_segundo_indice", None)
        if combinar_indice and segundo:
            self._marcar_checkbox("combinarComOutro", True)
            self._aguardar_ajax(2000)
            self._selecionar("segundoIndice", _INDICE_MAP.get(segundo, segundo))
            if data_inicio_2:
                self._preencher("dataInicioSegundoIndiceInputDate", data_inicio_2, obrigatorio=False)

        # ── Ignorar Taxa Negativa ────────────────────────────────────────────
        ignorar_neg = getattr(c, "ignorar_taxa_negativa", None)
        if ignorar_neg is not None:
            self._marcar_checkbox("ignorarTaxaNegativa", bool(ignorar_neg))

        # ── Taxa de Juros (sufixo real: taxaJuros) ───────────────────────────
        juros_val = _JUROS_MAP.get(c.juros, c.juros)
        self._selecionar("taxaJuros", juros_val)

        # ── Combinar com outro juros (Lei 14.905 / taxa a partir de data) ────
        combinar_juros = (
            getattr(c, "combinar_com_outro_juros", False)
            or getattr(c, "combinar_outro_juros", False)
        )
        outro_juros = getattr(c, "outro_juros", None)
        outro_juros_de = getattr(c, "outro_juros_a_partir_de", None)
        if combinar_juros and outro_juros:
            self._marcar_checkbox("combinarComOutroJuros", True)
            self._aguardar_ajax(1500)
            self._selecionar("outroJuros", _JUROS_MAP.get(outro_juros, outro_juros))
            if outro_juros_de:
                self._preencher("outroJurosAPartirDeInputDate", outro_juros_de, obrigatorio=False)

        # ── Lei 14.905 ───────────────────────────────────────────────────────
        lei_14905 = getattr(c, "lei_14905", None)
        if lei_14905 is not None:
            self._marcar_checkbox("lei14905", bool(lei_14905))
            if lei_14905:
                data_tl = getattr(c, "data_taxa_legal", None)
                if data_tl:
                    self._preencher("dataTaxaLegalInputDate", data_tl, obrigatorio=False)

        # ── Base de Juros das Verbas ─────────────────────────────────────────
        base_val = _BASE_JUROS_MAP.get(c.base_juros_verbas, c.base_juros_verbas)
        self._selecionar("baseDeJurosDasVerbas", base_val)

        # ── FGTS: Correção (radio: INDICE_TRABALHISTA / JAM / JAM_MAIS_TRABALHISTA)
        fgts_c = getattr(c, "fgts", None)
        if fgts_c:
            fc_raw = (
                fgts_c.get("indice_correcao") if isinstance(fgts_c, dict)
                else getattr(fgts_c, "indice_correcao", None)
            )
            if fc_raw:
                self._marcar_radio("fgtsCorrecao", _FGTS_CORR_MAP.get(fc_raw, fc_raw))

        # ── Lei 11.941/2009 (CS) ─────────────────────────────────────────────
        lei11941 = getattr(c, "lei_11941", None)
        if lei11941:
            lei_ativa = (
                lei11941.get("correcao_ativa", False) if isinstance(lei11941, dict)
                else getattr(lei11941, "correcao_ativa", False)
            )
            self._marcar_checkbox("lei11941", bool(lei_ativa))

        # ── Previdência Privada ──────────────────────────────────────────────
        pp = getattr(c, "previdencia_privada", None)
        if pp:
            aplicar_juros_pp = (
                pp.get("aplicar_juros", False) if isinstance(pp, dict)
                else getattr(pp, "aplicar_juros", False)
            )
            indice_pp = (
                pp.get("indice_correcao") if isinstance(pp, dict)
                else getattr(pp, "indice_correcao", None)
            )
            self._marcar_checkbox("jurosPrevidenciaPrivada", bool(aplicar_juros_pp))
            if indice_pp:
                _pp_map = {"UTILIZAR_INDICE_TRABALHISTA": "TRABALHISTA"}
                self._selecionar("indicePrevidenciaPrivada", _pp_map.get(indice_pp, "TRABALHISTA"))

        # ── Custas ───────────────────────────────────────────────────────────
        custas_c = getattr(c, "custas", None)
        if custas_c:
            corr_ativa = (
                custas_c.get("correcao_ativa", False) if isinstance(custas_c, dict)
                else getattr(custas_c, "correcao_ativa", False)
            )
            juros_ativos = (
                custas_c.get("juros_ativos", False) if isinstance(custas_c, dict)
                else getattr(custas_c, "juros_ativos", False)
            )
            indice_custas = (
                custas_c.get("indice_correcao") if isinstance(custas_c, dict)
                else getattr(custas_c, "indice_correcao", None)
            )
            self._marcar_checkbox("atualizarCustas", bool(corr_ativa))
            if corr_ativa:
                self._aguardar_ajax(2000)
                if indice_custas:
                    _c_map = {"UTILIZAR_INDICE_TRABALHISTA": "TRABALHISTA"}
                    self._selecionar("indiceCustas", _c_map.get(indice_custas, "TRABALHISTA"))
            self._marcar_checkbox("jurosCustas", bool(juros_ativos))

        self._clicar("salvar")
        self._aguardar_ajax(8000)
        self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        self.log("Fase 13 concluída")

    def fase_liquidar_e_exportar(self) -> str | None:
        """Liquida o cálculo e baixa o arquivo .PJC final."""
        self.log("Fase 14 — Liquidar + Exportar")

        # ── 14a. Navegar para Liquidar via sidebar JSF ─────────────────────
        # Sempre passar pelo Dados do Cálculo primeiro para garantir que
        # estamos no contexto do cálculo (sidebar Operações renderiza).
        self.log(f"  [DIAG-liq] conv_id no início: {self._calculo_conversation_id}")
        try:
            self._navegar_menu("li_calculo_dados_do_calculo")
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(1500)
        except Exception:
            pass
        self.log(f"  [DIAG-liq] conv_id após dados_do_calculo: {self._calculo_conversation_id}")

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

        # Aguardar render completo da página de Liquidação. AJAX inicial após
        # navegação pelo sidebar pode levar até 15s — sem este wait, radios
        # ainda não estão no DOM e o diagnóstico volta vazio.
        try:
            self._page.wait_for_selector(
                "input[type='radio'][id*='indicesAcumulados'], "
                "input[type='radio'][name*='indicesAcumulados']",
                state="attached", timeout=15000
            )
            self.log("  ✓ Radios indicesAcumulados renderizados no DOM")
        except Exception:
            self.log("  ⚠ Radios indicesAcumulados não apareceram em 15s — diagnóstico:")
            # Dump completo da página para entender o que falta
            try:
                _dump = self._page.evaluate(
                    """() => ({
                        url: location.href.split('?')[0].split('/').pop(),
                        n_radios: document.querySelectorAll('input[type=radio]').length,
                        n_inputs: document.querySelectorAll('input').length,
                        ids_radios: [...document.querySelectorAll('input[type=radio]')]
                            .map(r => r.id||r.name).slice(0,10),
                        title: document.title,
                        msgs: [...document.querySelectorAll('.rf-msgs,.rich-messages,.error,.warning')]
                            .map(e => (e.textContent||'').trim().slice(0,80)).filter(Boolean).slice(0,5)
                    })"""
                )
                self.log(f"  [DIAG-liq-radios] {_dump}")
            except Exception:
                pass

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

        # Verificar resultado da liquidação — pendência/erro só são REAIS se
        # aparecerem nas MENSAGENS JSF (.rf-msgs-*), não em qualquer lugar do body.
        # Bug anterior: substring no body inteiro causava falso positivo (a palavra
        # "pendência" pode aparecer em sidebar/menus mesmo com liquidação OK).
        _liq_result = self._page.evaluate("""() => {
            const body = document.body?.textContent || '';
            const msgs = [...document.querySelectorAll('.rf-msgs-detail,.rf-msgs-sum,.ui-messages-error-summary,.rich-messages-label')]
                .map(e => (e.textContent||'').trim()).filter(t => t).slice(0, 10);
            const msgs_lower = msgs.map(m => m.toLowerCase()).join('\\n');
            const has_real_error =
                body.includes('HTTP Status 500')
                || body.includes('NullPointerException')
                || body.toLowerCase().includes('erro inesperado')
                || msgs_lower.includes('erro:');
            const has_pendencia_msg = msgs.some(m => /pend[êe]ncia/i.test(m));
            const has_sucesso_msg = msgs.some(m =>
                /opera[cç][ãa]o realizada com sucesso/i.test(m)
                || /liquida[cç][ãa]o realizada/i.test(m)
            );
            return {
                msgs: msgs,
                tem_pendencia: has_pendencia_msg,
                nao_encontradas: msgs_lower.includes('não foram encontradas'),
                tem_liquidado: body.toLowerCase().includes('liquidação realizada')
                    || body.toLowerCase().includes('liquidado em '),
                tem_erro: has_real_error,
                tem_sucesso: has_sucesso_msg
            };
        }""")
        self.log(
            f"  [DIAG-liquidar] msgs={_liq_result['msgs']} "
            f"pendencia={_liq_result['tem_pendencia']} "
            f"sucesso={_liq_result['tem_sucesso']} "
            f"erro={_liq_result['tem_erro']}"
        )

        # Prioridade: mensagem JSF de sucesso explícito > erro > pendência
        # (Calc Machine faz exatamente isso — sucesso "veta" os demais sinais.)
        if _liq_result['tem_sucesso']:
            self.log("  ✓ Liquidação OK (mensagem JSF de sucesso explícita)")
        elif _liq_result['tem_erro']:
            raise RuntimeError(f"Liquidação retornou erro: {_liq_result['msgs']}")
        elif _liq_result['tem_pendencia'] and not _liq_result['nao_encontradas']:
            pendencias = _liq_result['msgs']
            # Capturar detalhes das pendências — clicar em "Verificar Pendências" ou
            # navegar para sidebar/popup com a tabela de pendências detalhadas.
            try:
                self._page.evaluate("""
                    () => {
                      // Tentar clicar em qualquer link/botão de "Verificar Pendências"
                      const cands = [...document.querySelectorAll('a, input, button')]
                        .filter(el => /verificar.*pend[êe]nc|listar.*pend[êe]nc|pend[êe]nc/i.test(
                          (el.value || el.textContent || '').trim()
                        ));
                      if (cands[0]) cands[0].click();
                    }
                """)
                self._aguardar_ajax(3000)
            except Exception:
                pass
            # Capturar TODAS as tabelas/listas de pendências detalhadas
            detalhes_pendencias: list[str] = []
            try:
                detalhes = self._page.evaluate("""() => {
                    const result = {linhas: [], tabelas: [], modal: null};
                    // Linhas de tabela com pendência (rich-table)
                    document.querySelectorAll('table.rich-table tr, table[id*="pendenc"] tr, table[id*="Pendenc"] tr').forEach(tr => {
                      const cells = [...tr.querySelectorAll('td,th')].map(c => (c.textContent||'').trim()).filter(t => t);
                      if (cells.length) result.linhas.push(cells.join(' | '));
                    });
                    // Texto de modais/dialogs
                    const modal = document.querySelector('.rf-pp-cnt, .rich-modalpanel-content, .ui-dialog-content');
                    if (modal) result.modal = (modal.textContent||'').trim().substring(0, 2000);
                    // Spans com classe de detalhe
                    document.querySelectorAll('.rich-message-detail, .rf-msg-det, .rf-msgs-det').forEach(el => {
                      const t = (el.textContent||'').trim();
                      if (t.length > 5 && t.length < 500) result.tabelas.push(t);
                    });
                    return result;
                }""")
                self.log(f"  [DIAG-pendencias] tabela_linhas={len(detalhes.get('linhas', []))}")
                for ln in (detalhes.get('linhas') or [])[:30]:
                    self.log(f"  [DIAG-pendencias] {ln[:300]}")
                    detalhes_pendencias.append(ln[:300])
                for tb in (detalhes.get('tabelas') or [])[:10]:
                    self.log(f"  [DIAG-pendencias] detail: {tb[:250]}")
                    detalhes_pendencias.append(tb[:250])
                if detalhes.get('modal'):
                    self.log(f"  [DIAG-pendencias] modal: {detalhes['modal']}")
            except Exception as e:
                self.log(f"  ⚠ Falha capturar detalhes de pendências: {e}")

            # ── RETRY: segunda tentativa após capturar pendências ────────────
            # Usuário escolheu "2 tentativas antes do link manual" — algumas
            # pendências são transitórias (race AJAX) e desaparecem ao tentar
            # de novo após pequena espera.
            if not getattr(self, "_liq_retry_done", False):
                self._liq_retry_done = True
                self.log("  → Pendências detectadas — 2ª tentativa de liquidação após 3s")
                self._page.wait_for_timeout(3000)
                try:
                    self._clicar("liquidar")
                    self._aguardar_ajax(15000)
                    self._aguardar_operacao_sucesso(timeout_ms=20000, bloqueante=False)
                    _liq2 = self._page.evaluate("""() => {
                        const msgs = [...document.querySelectorAll('.rf-msgs-detail,.rf-msgs-sum')]
                            .map(e => (e.textContent||'').trim()).filter(t => t);
                        return {
                            ok: msgs.some(m => /opera[cç][ãa]o realizada com sucesso|liquida[cç][ãa]o realizada/i.test(m)),
                            pend: msgs.some(m => /pend[êe]ncia/i.test(m))
                        };
                    }""")
                    if _liq2['ok'] and not _liq2['pend']:
                        self.log("  ✓ 2ª tentativa de liquidação OK — prosseguindo para exportação")
                        # Sair do branch de pendência, segue para exportar
                        sucesso_liq = True
                        pendencias = []
                    else:
                        self.log("  ⚠ 2ª tentativa ainda com pendência — emitindo evento de edição manual")
                except Exception as e:
                    self.log(f"  ⚠ Erro 2ª tentativa: {e}")

            # Se ainda houver pendência após retry → emitir evento [MANUAL_EDIT_REQUIRED]
            if pendencias:
                self._capturar_conversation_id()
                conv = self._calculo_conversation_id or "?"
                # URL passada via proxy do app (mesma origem que o frontend usa)
                edit_url = f"/pjecalc/pages/calculo/calculo.jsf?conversationId={conv}"
                payload = {
                    "url": edit_url,
                    "conversationId": conv,
                    "pendencias": pendencias[:10],
                    "detalhes": detalhes_pendencias[:30],
                }
                # Marcador especial reconhecido pelo SSE/frontend
                import json as _json
                self.log(f"[MANUAL_EDIT_REQUIRED] {_json.dumps(payload, ensure_ascii=False)}")
                self.log(
                    "  ⚠ Liquidação bloqueada por pendências. Use o link de edição manual "
                    "para corrigir os parâmetros diretamente no PJE-Calc Cidadão. Esta é a "
                    "última alternativa — todos os demais dados já foram preenchidos pela "
                    "automação; faça apenas as correções pontuais para finalizar."
                )
                raise RuntimeError(
                    "Liquidação bloqueada por pendências após 2 tentativas. "
                    "Edição manual oferecida ao usuário."
                )
        else:
            # Sem mensagens conclusivas — assumimos OK (alertas não-bloqueadores)
            self.log("  ✓ Liquidação OK (sem mensagens bloqueadoras)")

        # Capturar conv_id pós-liquidação — Seam pode ter redirecionado para nova conv
        self._capturar_conversation_id()
        _conv_pos_liq = self._calculo_conversation_id
        self.log(f"  [DIAG-liq] conv_id pós-liquidação: {_conv_pos_liq}")

        # ── 14d. Navegar para Exportar ─────────────────────────────────────────
        # ESTRATÉGIA: sidebar PRIMEIRO (enquanto ainda estamos na página de liquidação
        # que tem o contexto Seam correto com calculoAberto inicializado).
        # URL nav direto causa NPE Java:244 porque exportacao.jsf abre nova conv
        # sem calculoAberto. Sidebar navega dentro da conv ativa.

        def _tentar_sidebar_exportar() -> str | None:
            """Tenta clicar Exportar via sidebar; retorna chave-diagnóstico ou None."""
            resultado = self._page.evaluate(
                """() => {
                    // DIAG: dump sidebar items para diagnóstico
                    const sidebarItems = [...document.querySelectorAll('li[id^=li_]')]
                        .map(li => li.id).join(',');
                    const li1 = document.getElementById('li_operacoes_exportar');
                    if (li1) { const a = li1.querySelector('a'); if (a) { a.click(); return 'li_operacoes_exportar'; } }
                    const links = [...document.querySelectorAll('a')];
                    for (const a of links) {
                        const txt = (a.textContent || '').replace(/\\s+/g,' ').trim();
                        const li = a.closest('li');
                        if (txt === 'Exportar' && li && li.id && li.id.includes('operacoes')) {
                            a.click(); return 'text-li-operacoes';
                        }
                    }
                    for (const a of links) {
                        const txt = (a.textContent || '').replace(/\\s+/g,' ').trim();
                        if (txt === 'Exportar') { a.click(); return 'text-any:' + (a.id || 'noId').slice(0,30); }
                    }
                    // Retornar null mas com DIAG de sidebar para debug
                    return null;
                }"""
            )
            # DIAG: log sidebar state when not found
            if not resultado:
                _sidebar_diag = self._page.evaluate(
                    """() => [...document.querySelectorAll('li[id^=li_]')].map(li => li.id)"""
                )
                self.log(f"  [DIAG-sidebar-exportar] items={_sidebar_diag[:15]}")
            return resultado

        def _verificar_exportacao_ok() -> dict:
            return self._page.evaluate("""() => {
                const body = document.body?.textContent || '';
                return {
                    url: location.href.slice(-70),
                    tem_form: !!document.getElementById('formulario'),
                    tem_500: body.includes('HTTP Status 500') || body.includes('NullPointerException'),
                    tem_export_btn: !!(document.querySelector('input[id$=exportar]') ||
                        document.querySelector('input[value=Exportar]')),
                    tem_erro_5: body.includes('Erro: 5') || body.includes('erro: 5')
                };
            }""")

        nav_exp = None

        # 1ª tentativa: sidebar estando na página de resultado da liquidação
        self.log("  → Tentando nav Exportar via sidebar (pós-liquidação)...")
        try:
            nav_exp = _tentar_sidebar_exportar()
            if nav_exp:
                self._aguardar_ajax(15000)
                self._page.wait_for_timeout(2000)
                _diag_exp = _verificar_exportacao_ok()
                self.log(f"  [DIAG-exp] sidebar={nav_exp} {_diag_exp}")
                if _diag_exp['tem_500'] or _diag_exp['tem_erro_5']:
                    self.log("  ⚠ Sidebar→Exportar retornou erro (NPE?) — tentando URL nav")
                    nav_exp = None  # vai tentar URL nav
        except Exception as e:
            self.log(f"  ⚠ Sidebar exportar erro: {e}")
            nav_exp = None

        # 2ª tentativa: URL nav com conv pós-liquidação
        if not nav_exp and _conv_pos_liq:
            self.log(f"  → Tentando URL nav exportacao.jsf?conversationId={_conv_pos_liq}")
            url_exp = (
                f"{self.pjecalc_url}/pages/calculo/exportacao.jsf"
                f"?conversationId={_conv_pos_liq}"
            )
            try:
                self._page.goto(url_exp, wait_until="domcontentloaded", timeout=15000)
                self._aguardar_ajax(15000)
                self._page.wait_for_timeout(1500)
                _diag_exp = _verificar_exportacao_ok()
                self.log(f"  [DIAG-exp] url-nav {_diag_exp}")
                if not _diag_exp['tem_500'] and not _diag_exp['tem_erro_5'] and _diag_exp['tem_form']:
                    nav_exp = "url-nav-direto"
            except Exception as e:
                self.log(f"  ⚠ URL nav Exportar: {e}")

        # 3ª tentativa: dados_do_calculo → sidebar novamente (re-inicializa beans)
        if not nav_exp:
            self.log("  → Tentando reabrir cálculo via Dados do Cálculo + sidebar Exportar")
            try:
                self._navegar_menu("li_calculo_dados_do_calculo")
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1500)
                _sid3 = _tentar_sidebar_exportar()
                if _sid3:
                    self._aguardar_ajax(15000)
                    self._page.wait_for_timeout(2000)
                    _diag3 = _verificar_exportacao_ok()
                    self.log(f"  [DIAG-exp] dados+sidebar={_sid3} {_diag3}")
                    if not _diag3['tem_500'] and not _diag3['tem_erro_5']:
                        nav_exp = f"dados+sidebar:{_sid3}"
            except Exception as e:
                self.log(f"  ⚠ Tentativa 3 (dados+sidebar): {e}")

        # 4ª tentativa: principal.jsf → Recentes (pós-liquidação) → sidebar Exportar
        # Após liquidação o calc está no H2 com estado LIQUIDADO.
        # Tentar reabrir via Recentes para obter nova conv em edit-mode onde
        # calculoAberto.calculo está corretamente populado.
        if not nav_exp:
            self.log("  → Tentativa 4: principal.jsf → Recentes → conv_edit → Exportar")
            try:
                ok_rec4 = self._reabrir_calculo_via_recentes()
                if ok_rec4:
                    self.log(f"  ✓ Reaberto via Recentes — conv={self._calculo_conversation_id}")
                    # Agora navegar para o Exportar via sidebar
                    _sid4 = _tentar_sidebar_exportar()
                    if not _sid4:
                        # Sidebar pode não mostrar Exportar ainda — navegar para calculo.jsf primeiro
                        self._navegar_menu("li_calculo_dados_do_calculo")
                        self._aguardar_ajax(5000)
                        _sid4 = _tentar_sidebar_exportar()
                    if _sid4:
                        self._aguardar_ajax(15000)
                        self._page.wait_for_timeout(2000)
                        _diag4 = _verificar_exportacao_ok()
                        self.log(f"  [DIAG-exp] recentes+sidebar={_sid4} {_diag4}")
                        if not _diag4['tem_500']:
                            nav_exp = f"recentes+sidebar:{_sid4}"
                    # Fallback: URL nav com nova conv
                    if not nav_exp and self._calculo_conversation_id:
                        url_exp4 = (
                            f"{self.pjecalc_url}/pages/calculo/exportacao.jsf"
                            f"?conversationId={self._calculo_conversation_id}"
                        )
                        self._page.goto(url_exp4, wait_until="domcontentloaded", timeout=15000)
                        self._aguardar_ajax(15000)
                        self._page.wait_for_timeout(1500)
                        _diag4b = _verificar_exportacao_ok()
                        self.log(f"  [DIAG-exp] recentes+url-nav {_diag4b}")
                        if not _diag4b['tem_500'] and not _diag4b['tem_erro_5'] and _diag4b['tem_form']:
                            nav_exp = f"recentes+url-nav"
            except Exception as e4:
                self.log(f"  ⚠ Tentativa 4 (recentes pós-liq): {e4}")

        if not nav_exp:
            raise RuntimeError("Exportar não localizado após 4 tentativas (sidebar, URL-nav, dados+sidebar, recentes)")
        self.log(f"  ✓ Navegação Exportar via: {nav_exp}")

        # ── 14f. Clicar Exportar e capturar .PJC ───────────────────────────
        # Estratégia: capturar response binário via expect_response
        from datetime import datetime as _dt

        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        num_limpo = self.previa.processo.numero_processo.replace("-", "").replace(".", "")
        nome_pjc = f"PROCESSO_{num_limpo}_{ts}.pjc"
        # Usar volume persistente para sobreviver a restarts/deploys.
        # Candidatos em ordem: volume Docker mapeado → fallback /tmp (dev local).
        for _candidate in [Path("/app/data/calculations/pjc_exports"), Path("/tmp/pjecalc_exports")]:
            try:
                _candidate.mkdir(parents=True, exist_ok=True)
                out_dir = _candidate
                break
            except OSError:
                continue
        else:
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

            # Fase A — CRÍTICO: expect_download PRÉ-REGISTRADO antes do clique.
            # O botão Exportar dispara um POST A4J (text/xml) que contém um
            # <script> inline com jsfcljs(...) que auto-dispara o download ZIP
            # DURANTE o processamento AJAX — antes de qualquer polling reagir.
            # expect_response capturava só o text/xml (não o ZIP); expect_download
            # é registrado antes do clique e captura o evento download corretamente.
            import pathlib as _pl
            pjc_bytes = None
            try:
                with self._page.expect_download(timeout=25000) as _dl_info:
                    btn.click(force=True)
                _dl = _dl_info.value
                _dl_path = _dl.path()
                if _dl_path:
                    pjc_bytes = _pl.Path(_dl_path).read_bytes()
                    self.log(f"  ✓ Fase A capturou .PJC via download event: {len(pjc_bytes)} bytes")
                else:
                    self.log(f"  ⚠ Fase A: download.path() vazio — tentando Fase E")
            except Exception as e_a:
                self.log(f"  ⚠ Fase A expect_download: {str(e_a)[:120]} — tentando Fase E")

            # Fase B + E: aguardar linkDownloadArquivo aparecer + disparar jsfcljs
            if not pjc_bytes:
                # Poll por linkDownloadArquivo (até 45s — server pode ser lento)
                link_ok = False
                for i in range(90):
                    if self._page.locator("[id$='linkDownloadArquivo']").count() > 0:
                        link_ok = True
                        self.log(f"  ✓ linkDownloadArquivo detectado após {i*0.5:.1f}s")
                        break
                    self._page.wait_for_timeout(500)

                if link_ok:
                    try:
                        with self._page.expect_response(
                            lambda r: (
                                "exportacao.jsf" in r.url
                                and r.request.method == "POST"
                            ),
                            timeout=60000,
                        ) as resp_info:
                            metodo = self._page.evaluate(
                                """() => {
                                    const form = document.getElementById('formulario');
                                    if (form && typeof jsfcljs === 'function') {
                                        jsfcljs(form, {'formulario:linkDownloadArquivo':'formulario:linkDownloadArquivo'}, '');
                                        return 'jsfcljs';
                                    }
                                    const link = document.querySelector("[id$='linkDownloadArquivo']");
                                    if (link) { link.click(); return 'click'; }
                                    return null;
                                }"""
                            )
                            self.log(f"  → Fase E método: {metodo}")
                        resp = resp_info.value
                        ct = resp.headers.get("content-type", "")
                        cd = resp.headers.get("content-disposition", "")
                        self.log(f"  → Fase E HTTP {resp.status} content-type={ct} disposition={cd[:80]}")
                        body = resp.body()
                        if body and body[:2] == b"PK":
                            pjc_bytes = body
                            self.log(f"  ✓ Fase E capturou .PJC: {len(pjc_bytes)} bytes")
                    except Exception as e_e:
                        self.log(f"  ⚠ Fase E: {str(e_e)[:200]}")
                else:
                    self.log(f"  ⚠ linkDownloadArquivo não apareceu em 45s")
                    # Diagnóstico: dump elementos presentes na página
                    try:
                        _diag = self._page.evaluate("""() => {
                            const ids = [...document.querySelectorAll('[id]')]
                                .map(e => e.id).filter(Boolean);
                            const inputs = [...document.querySelectorAll('input,a,button')]
                                .filter(e => e.offsetParent)
                                .map(e => (e.id || e.textContent?.trim()?.slice(0,20) || '?') + ':' + e.tagName);
                            const msgs = [...document.querySelectorAll('.rf-msgs,.rf-msg,.rich-messages,span[class*=error],span[class*=warn]')]
                                .map(e => e.textContent.trim().slice(0,100)).filter(Boolean);
                            return {
                                url: location.href.split('?')[0].split('/').pop(),
                                ids: ids.filter(i => i.includes('Download') || i.includes('export') || i.includes('link')).slice(0,10),
                                inputs: inputs.slice(0,15),
                                msgs: msgs.slice(0,5)
                            };
                        }""")
                        self.log(f"  [DIAG-export] {_diag}")
                    except Exception:
                        pass

                    # Fase F: POST direto com parâmetros jsfcljs do linkDownloadArquivo
                    try:
                        _vstate = self._page.evaluate("""() => {
                            const f = document.getElementById('formulario');
                            if (!f) return null;
                            const vs = f.querySelector('[name="javax.faces.ViewState"]');
                            return vs ? vs.value : null;
                        }""")
                        if _vstate:
                            self.log(f"  → Fase F: POST direto com ViewState ({len(_vstate)} chars)")
                            with self._page.expect_response(
                                lambda r: "exportacao.jsf" in r.url and r.request.method == "POST",
                                timeout=60000,
                            ) as _rf_info:
                                self._page.evaluate(f"""() => {{
                                    const form = document.getElementById('formulario');
                                    if (!form) return;
                                    const addHidden = (n, v) => {{
                                        let el = form.querySelector('[name="' + n + '"]');
                                        if (!el) {{ el = document.createElement('input'); el.type='hidden'; el.name=n; form.appendChild(el); }}
                                        el.value = v;
                                    }};
                                    addHidden('formulario:linkDownloadArquivo', 'formulario:linkDownloadArquivo');
                                    form.submit();
                                }}""")
                            _rf = _rf_info.value
                            _fb = _rf.body()
                            self.log(f"  → Fase F: HTTP {_rf.status} ct={_rf.headers.get('content-type','')[:40]} {len(_fb)} bytes")
                            if _fb and _fb[:2] == b"PK":
                                pjc_bytes = _fb
                                self.log(f"  ✓ Fase F capturou .PJC: {len(pjc_bytes)} bytes")
                    except Exception as e_f:
                        self.log(f"  ⚠ Fase F: {str(e_f)[:150]}")

            if not pjc_bytes:
                raise RuntimeError("Falha ao capturar download .PJC: Fase A, E e F timeout")
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
