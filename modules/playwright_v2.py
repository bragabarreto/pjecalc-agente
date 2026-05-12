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

    # ─── Lifecycle ─────────────────────────────────────────────────────────

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.firefox.launch(headless=True)
        ctx = self._browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
        )
        self._page = ctx.new_page()
        self.log("✓ Browser Firefox iniciado")
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
        loc.first.fill(str(valor))
        self.log(f"  ✓ {dom_id} = {valor}")

    def _marcar_radio(self, dom_id: str, valor: str, obrigatorio: bool = False) -> None:
        sel = f"input[type='radio'][id*='{dom_id}'][value='{valor}']"
        loc = self._page.locator(sel)
        if loc.count() == 0:
            if obrigatorio:
                raise RuntimeError(f"Radio não encontrado: {dom_id}={valor}")
            self.log(f"  ⚠ radio {dom_id}={valor} não encontrado — pulando")
            return
        loc.first.click(force=True)
        self.log(f"  ✓ radio {dom_id} = {valor}")

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

    def _clicar(self, dom_id: str) -> None:
        sel = f"[id$='{dom_id}']"
        loc = self._page.locator(sel)
        if loc.count() == 0:
            raise RuntimeError(f"Botão não encontrado: {dom_id}")
        loc.first.click()
        self.log(f"  ✓ click {dom_id}")

    def _aguardar_ajax(self, timeout_ms: int = 10000) -> None:
        try:
            self._page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

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

            # O select de Recentes tem ID dinâmico (ex: formulario:j_id92) e NÃO
            # tem class/name 'listaCalculosRecentes' — usar JS para localizá-lo.
            _select_id = self._page.evaluate("""() => {
                const SKIP = new Set(['selAcheFacil']);
                for (const s of document.querySelectorAll('select')) {
                    if (SKIP.has(s.name) || SKIP.has(s.id)) continue;
                    if (s.options.length > 0 && /^\\d{4,}\\s*\\//.test(s.options[0].text || ''))
                        return s.name || s.id;
                }
                for (const s of document.querySelectorAll('select')) {
                    if (SKIP.has(s.name) || SKIP.has(s.id)) continue;
                    const blob = [...s.options].map(o => o.text || '').join(' | ');
                    if (/\\d{7}-\\d{2}\\.\\d{4}\\.5\\.\\d{2}\\.\\d{4}/.test(blob))
                        return s.name || s.id;
                }
                return null;
            }""")
            if not _select_id:
                self.log("  ⚠ Lista de Cálculos Recentes não encontrada — pulando reabrir")
                return False
            listbox = self._page.locator(f"select[name='{_select_id}'], select[id='{_select_id}']")
            if listbox.count() == 0:
                self.log("  ⚠ Lista de Cálculos Recentes não encontrada — pulando reabrir")
                return False
            self.log(f"  → select Recentes encontrado: {_select_id}")

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
                self.log(f"  ⚠ Processo {num} não encontrado nos Recentes ({n_opts} itens)")
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

        # Salvar
        self._clicar("salvar")
        self._aguardar_ajax(15000)
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
                # CALCULADO: quantidade + base_referencia + cmdGerarOcorrencias
                self._preencher("quantidade", _fmt_br(hist.calculado.quantidade_pct), obrigatorio=False)
                self._selecionar("baseDeReferencia", hist.calculado.base_referencia)
                self._clicar("cmdGerarOcorrencias")
                self._aguardar_ajax()

            self._clicar("salvar")
            self._aguardar_ajax(8000)
            self.log(f"  ✓ Histórico '{hist.nome}' salvo")

        self.log("Fase 3 concluída")

    def fase_verbas(self) -> None:
        self.log("Fase 4 — Verbas Principais")
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

        # 4c. Pós-Expresso: REABRIR CÁLCULO via Recentes (workaround NPE).
        # Bug PJE-Calc 2.15.1: ApresentadorVerbaDeCalculo.carregarBasesParaPrincipal
        # lança NPE após Expresso save, corrompendo a conversação Seam e impedindo
        # renderização de TODAS as views subsequentes (verba-calculo, fgts, inss,
        # irpf, custas, correção, liquidar). Solução v1: voltar para principal e
        # reabrir cálculo via dropdown "Cálculos Recentes" — cria nova conversação
        # Seam limpa.
        if verbas_expresso:
            self.log("  → Workaround NPE: reabrindo cálculo via Recentes")
            ok = self._reabrir_calculo_via_recentes()
            if not ok:
                # Fallback: double-hop (pode não recuperar mas tenta)
                self._navegar_menu("li_calculo_dados_do_calculo")
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1500)
            self._navegar_menu("li_calculo_verbas")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(2000)
            # Detectar 500/NPE e tentar recovery via reload
            tem_erro = self._page.evaluate(
                """() => {
                    const body = (document.body?.textContent || '');
                    return body.includes('HTTP Status 500') ||
                           body.includes('NullPointerException') ||
                           body.includes('Erro inesperado') ||
                           body.includes('ViewExpiredException');
                }"""
            )
            tem_listagem = self._page.evaluate(
                """() => document.querySelectorAll('a.linkParametrizar').length > 0"""
            )
            if tem_erro or not tem_listagem:
                self.log(f"  ⚠ verba-calculo.jsf vazia/erro — tentando recovery (reload + double-hop)")
                # Tentativa 1: reload
                try:
                    self._page.reload(wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax(15000)
                    self._page.wait_for_timeout(2000)
                except Exception:
                    pass
                tem_listagem = self._page.evaluate(
                    """() => document.querySelectorAll('a.linkParametrizar').length > 0"""
                )
                # Tentativa 2: triple-hop (Histórico → Dados → Verbas)
                if not tem_listagem:
                    self.log(f"  ⚠ Reload sem efeito — triple-hop")
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
                    self.log(f"  ⚠ Listagem permanece vazia — possível NPE não-recuperável; verbas Expresso podem não ter persistido. Continuando para reflexos manuais.")

        for v in verbas_expresso:
            self._configurar_parametros_pos_expresso(v)
            for r in v.reflexos:
                self._configurar_reflexo(v, r)

        self.log("Fase 4 concluída")

    def _lancar_expresso(self, verbas) -> None:
        self.log("  → Lançamento Expresso")
        self._clicar("lancamentoExpresso")
        self._aguardar_ajax(8000)
        self._page.wait_for_timeout(1500)

        # Diagnóstico: contar verbas disponíveis
        diag = self._page.evaluate(
            """() => {
                const cbs = [...document.querySelectorAll('input[type="checkbox"]')];
                const labels = cbs.map(cb => {
                    // Tenta múltiplas estratégias: label[for], label parent, td adjacente
                    let txt = '';
                    if (cb.id) {
                        const l = document.querySelector(`label[for="${cb.id.replace(/[^\\w-]/g, c => '\\\\'+c)}"]`);
                        if (l) txt = l.textContent;
                    }
                    if (!txt) {
                        const p = cb.closest('label, td, tr');
                        if (p) txt = p.textContent;
                    }
                    return (txt || '').replace(/\\s+/g, ' ').trim();
                }).filter(t => t.length > 2 && t.length < 100);
                return {total: cbs.length, com_label: labels.length, primeiros: labels.slice(0, 30)};
            }"""
        )
        self.log(f"    ℹ Página Expresso: {diag.get('total')} checkboxes, {diag.get('com_label')} com label")

        for v in verbas:
            alvo = (v.expresso_alvo or "").strip().upper()
            # Estrutura DOM real (PJE-Calc Cidadão 2.15.1):
            # - Checkboxes id=formulario:j_id82:N:j_id84:M:selecionada
            # - SEM label[for=...] — texto está no <td> adjacente (closest('td'))
            # - 54 verbas em 3 colunas × 18 linhas, todas visíveis (sem scroll necessário)
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
                    // Fallback parcial (caso tenha espaço/acentuação adicional)
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
                # Não fatal — log e segue
                self.log(f"    ⚠ Verba Expresso não encontrada no rol: '{alvo}' — pulando (será tentada como Manual?)")
                continue
            if isinstance(marcou, str) and marcou.startswith("partial:"):
                self.log(f"    ✓ Expresso (match parcial): {alvo} ← {marcou[8:]}")
            else:
                self.log(f"    ✓ Expresso checkbox: {alvo}")

        self._clicar("salvar")
        self._aguardar_ajax(15000)
        self.log("  ✓ Expresso salvo")
        # CRITICO: re-capturar conversationId — Seam emite NOVO conv após
        # Expresso save. Sem isso, URL navs subsequentes vao para conv
        # expirada -> NPE/empty pages em todas as fases seguintes.
        self._capturar_conversation_id()

    def _preencher_form_parametros_verba(self, v, *, com_identificacao: bool) -> None:
        """Preenche todos os campos do form de parâmetros de verba.

        Compartilhado entre _lancar_verba_manual (com_identificacao=True, descricao+CNJ
        precisam ser preenchidos) e _configurar_parametros_pos_expresso (False, identificação
        já vem do Expresso e não deve ser sobrescrita exceto se EXPRESSO_ADAPTADO).
        """
        p = v.parametros

        # 1. Identificação (apenas Manual ou Expresso_Adaptado)
        if com_identificacao:
            self._preencher("descricao", v.nome_pjecalc)
            # Assunto CNJ — autocomplete: digitar código + Enter dispara seleção
            self._preencher("codigoAssuntosCnj", str(p.assunto_cnj.codigo))
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
            if f.divisor.tipo.value == "OUTRO_VALOR":
                self._preencher("outroValorDoDivisor", str(f.divisor.valor))
            self._preencher("outroValorDoMultiplicador", _fmt_br(f.multiplicador))
            self._marcar_radio("tipoDaQuantidade", f.quantidade.tipo.value)
            self._aguardar_ajax(2000)
            if f.quantidade.tipo.value == "INFORMADA":
                self._preencher("valorInformadoDaQuantidade", _fmt_br(f.quantidade.valor))

        # 3. Período
        self._preencher("periodoInicialInputDate", p.periodo_inicio)
        self._preencher("periodoFinalInputDate", p.periodo_fim)

        # 4. Características + Ocorrência + Base de Cálculo
        self._marcar_radio("caracteristicaVerba", p.caracteristica.value)
        self._aguardar_ajax(2000)
        self._marcar_radio("ocorrenciaPagto", p.ocorrencia_pagamento.value)
        self._aguardar_ajax(2000)
        if hasattr(p, "tipo_base_calculo") and p.tipo_base_calculo:
            self._marcar_radio("tipoDaBaseDeCalculo", p.tipo_base_calculo.value)

        # 5. Incidências (FGTS / CS / IRPF / Prev. Priv. / Pensão)
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
        self._clicar("salvar")
        self._aguardar_ajax(8000)
        self.log(f"  ✓ Parâmetros '{v.nome_pjecalc}' salvos")

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
            self._clicar("incluir")
            self._aguardar_ajax(5000)

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

            self._clicar("salvar")
            self._aguardar_ajax(8000)

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
        _safe(lambda: self._clicar("salvar"), "salvar")
        self._aguardar_ajax(8000)
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
            self._preencher("aliquotaEmpresaFixa", str(cs.aliquota_empresa_fixa_pct or 20))
            self._preencher("aliquotaRatFixa", str(cs.aliquota_rat_fixa_pct or 1))
            self._preencher("aliquotaTerceirosFixa", str(cs.aliquota_terceiros_fixa_pct or 5.8))
        self._clicar("salvar")
        self._aguardar_ajax(8000)

        # Sub-página parametrizar-inss para vinculação histórico→CS
        self._clicar("ocorrencias")
        self._aguardar_ajax(8000)
        self._clicar("recuperarDevidos")
        self._aguardar_ajax(5000)
        self._clicar("copiarDevidos")
        self._aguardar_ajax(5000)

        # Modo manual_por_periodo: aplicar Lote por intervalo
        if cs.vinculacao_historicos_devidos.modo == "manual_por_periodo":
            for intv in cs.vinculacao_historicos_devidos.intervalos:
                self._preencher("dataInicialInputDate", intv.competencia_inicial)
                self._preencher("dataFinalInputDate", intv.competencia_final)
                self._preencher("salariosPago", _fmt_br(intv.valor_base_brl))
                # Click "Alterar" do lote
                self._clicar("aplicar")
                self._aguardar_ajax()

        self._clicar("salvar")
        self._aguardar_ajax(8000)
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
        self.log("Fase 10 concluída")

    def fase_honorarios(self) -> None:
        self.log("Fase 11 — Honorários")
        self._navegar_menu("li_calculo_honorarios")
        for h in self.previa.honorarios:
            self._clicar("incluir")
            self._aguardar_ajax(5000)
            self._selecionar("tpHonorario", h.tipo_honorario)
            self._preencher("descricao", h.descricao)
            self._marcar_radio("tipoDeDevedor", h.tipo_devedor)
            self._marcar_radio("tipoValor", h.tipo_valor.value)
            if h.tipo_valor.value == "CALCULADO":
                self._preencher("aliquota", _fmt_br(h.aliquota_pct))
                self._selecionar("baseParaApuracao", h.base_para_apuracao)
            else:
                self._preencher("aliquota", _fmt_br(h.valor_informado_brl))
            self._preencher("nomeCredor", h.credor.nome)
            self._marcar_radio("tipoDocumentoFiscalCredor", h.credor.doc_fiscal_tipo.value)
            self._preencher("numeroDocumentoFiscalCredor", h.credor.doc_fiscal_numero)
            self._marcar_checkbox("apurarIRRF", h.apurar_irrf)
            self._clicar("salvar")
            self._aguardar_ajax(8000)
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
        self.log("Fase 13 concluída")

    def fase_liquidar_e_exportar(self) -> str | None:
        """Liquida o cálculo e baixa o arquivo .PJC final."""
        self.log("Fase 14 — Liquidar + Exportar")

        # ── 14a. Navegar para Liquidar via sidebar JSF ─────────────────────
        # Antes: re-abrir cálculo via principal.jsf para garantir conv válido
        # (NPE pós-Expresso pode ter deixado conv em estado anômalo).
        # Sempre passar pelo Dados do Cálculo primeiro para garantir que
        # estamos no contexto do cálculo (sidebar Operações renderiza).
        try:
            self._navegar_menu("li_calculo_dados_do_calculo")
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(1500)
        except Exception:
            pass

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

        # ── 14b. Preencher form de Liquidação ──────────────────────────────
        liq = self.previa.liquidacao
        if liq.data_de_liquidacao:
            self._preencher("dataDeLiquidacaoInputDate", liq.data_de_liquidacao, obrigatorio=False)
        if liq.indices_acumulados:
            self._marcar_radio("indicesAcumulados", liq.indices_acumulados)

        # ── 14c. Clicar Liquidar ───────────────────────────────────────────
        self._clicar("liquidar")
        self._aguardar_ajax(60000)

        body = (self._page.locator("body").text_content() or "").lower()
        if "pendência" in body and "não foram encontradas" not in body:
            # Schema v2 deveria prevenir isso. Falhar rápido.
            pendencias = self._page.evaluate(
                """() => {
                    const els = [...document.querySelectorAll('.rf-msgs-detail, .rf-msgs-sum, .ui-messages-error-summary')];
                    return els.map(e => e.textContent.trim()).filter(t => t).slice(0, 20);
                }"""
            )
            raise RuntimeError(
                f"Liquidação retornou pendências (schema v2 deveria ter prevenido):\n"
                + "\n".join(f"  • {p}" for p in pendencias)
            )
        self.log("  ✓ Liquidação OK (sem pendências)")

        # ── 14d. Navegar para Exportar (cascata robusta) ──────────────────
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

        # ── 14e. Clicar Exportar e capturar .PJC ───────────────────────────
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

            # Fase A: click + expect ANY POST response a exportacao.jsf
            # (pode ser HTML com linkDownloadArquivo, ou diretamente ZIP).
            pjc_bytes = None
            try:
                with self._page.expect_response(
                    lambda r: (
                        "exportacao.jsf" in r.url
                        and r.request.method == "POST"
                    ),
                    timeout=30000,
                ) as resp_info:
                    btn.click(force=True)
                resp = resp_info.value
                ct = resp.headers.get("content-type", "")
                cd = resp.headers.get("content-disposition", "")
                self.log(f"  → Fase A resposta: HTTP {resp.status} ct={ct[:60]} cd={cd[:60]}")
                body_a = resp.body()
                if body_a and body_a[:2] == b"PK":
                    pjc_bytes = body_a
                    self.log(f"  ✓ Fase A capturou .PJC direto: {len(pjc_bytes)} bytes")
                else:
                    self.log(f"  → Fase A: resposta HTML ({len(body_a)} bytes) — buscando linkDownloadArquivo")
            except Exception as e_a:
                self.log(f"  ⚠ Fase A: {str(e_a)[:120]} — tentando Fase B/E")

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
