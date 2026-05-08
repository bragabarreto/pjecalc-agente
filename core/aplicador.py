"""Aplicador puro 1:1 do JSON v3 no PJE-Calc Cidadão (Etapa 2C).

Princípio: este módulo NÃO faz inferência. Apenas aplica literalmente o que
está no JSON validado pelo schema v3 (`infrastructure/pjecalc_pages.py`).

Diferenças vs o legado `modules/playwright_pjecalc.py`:
  - SEM auto-fix per-verba (loop de "preencher pendências")
  - SEM inferência de quantidade HE / valor de indenização
  - SEM filtros mágicos (DESLIGAMENTO=última linha; agora vem do JSON)
  - SEM map de característica/ocorrência para defaults
  - SEM fallback "valor=2700 se ausente"

Se o JSON tem `OcorrenciaVerba(indice=55, ativo=True, valor_devido='15.000,00')`,
a automação ATIVA a linha 55 e preenche `formulario:listagem:55:valorDevido`
com `15.000,00`. Pronto. Sem perguntar, sem inferir.

Se o JSON tem o valor errado, o usuário corrige na PRÉVIA antes da automação.

Estrutura
---------
    AplicadorPJECalc
      .aplicar(previa: PreviaCalculo)
        ├─ aplicar_dados_processo(previa.processo)
        ├─ aplicar_faltas(previa.faltas)
        ├─ aplicar_ferias(previa.ferias)
        ├─ aplicar_historico_salarial(previa.historico_salarial)
        ├─ aplicar_verbas(previa.verbas)               # ← núcleo
        │    ├─ aplicar_parametros_verba(v.parametros)
        │    ├─ aplicar_ocorrencias_verba(v.ocorrencias)
        │    └─ aplicar_reflexos(v.reflexos)            # recursivo
        ├─ aplicar_cartao_de_ponto(previa.cartao_de_ponto)
        ├─ aplicar_fgts(previa.fgts)
        ├─ aplicar_inss(previa.contribuicao_social)
        ├─ aplicar_irpf(previa.imposto_renda)
        ├─ aplicar_honorarios(previa.honorarios)
        ├─ aplicar_custas(previa.custas)
        ├─ aplicar_correcao_juros(previa.correcao_juros)
        └─ liquidar_e_exportar()  # → bytes do .pjc

Status (Etapa 2C — em desenvolvimento incremental)
--------------------------------------------------
✓ Skeleton + helpers (fill_text, fill_date, fill_decimal, select_value,
  click_radio, click_checkbox, navegar_menu, salvar, aguardar_ajax)
✓ aplicar_dados_processo (Fase 1)
✓ aplicar_verbas (Fase 5 — núcleo, com Parâmetros + Ocorrências + Reflexos)
✓ aplicar_fgts (Fase 7 — exemplo de página simples)
⏳ aplicar_historico_salarial (Fase 2)
⏳ aplicar_faltas, aplicar_ferias (Fases 3, 4)
⏳ aplicar_cartao_de_ponto (Fase 6)
⏳ aplicar_inss, aplicar_irpf (Fases 8, 9)
⏳ aplicar_honorarios (Fase 10)
⏳ aplicar_custas, aplicar_correcao_juros (Fases 11, 12)
⏳ liquidar_e_exportar
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional, TYPE_CHECKING

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from infrastructure.pjecalc_pages import (
    DadosProcesso, HistoricoSalarialEntry, Verba, ParametrosVerba,
    OcorrenciaVerba, FGTS, ContribuicaoSocial, ImpostoRenda, CartaoDePonto,
    Falta, FeriasEntry, CustasJudiciais, CorrecaoJuros, Honorario,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers de DOM (a maioria espelha o legado mas SEM heurísticas adicionais)
# ============================================================================


class AplicadorPJECalc:
    """Aplica um JSON v3 (PreviaCalculo) no PJE-Calc Cidadão.

    Recebe uma `Page` do Playwright já navegada para um cálculo em edição
    (ou cria um novo). Cada método `aplicar_*` corresponde a uma página do
    PJE-Calc e é responsável por navegar até ela, preencher os campos
    EXATAMENTE como estão no JSON e salvar.
    """

    def __init__(
        self,
        page: Page,
        base_url: str = "http://localhost:9257/pjecalc",
        log_cb: Optional[Callable[[str], None]] = None,
    ):
        self._page = page
        self._base_url = base_url.rstrip("/")
        self._log_cb = log_cb or (lambda msg: logger.info(msg))
        self._conv_id: Optional[str] = None
        # Cache para re-abrir cálculo via Recentes quando conv pós-Expresso
        # for disjunta. Preenchidos em aplicar_dados_processo.
        self._processo_numero: str = ""
        self._reclamante_nome: str = ""

    # ── Logging ──
    def log(self, msg: str) -> None:
        self._log_cb(msg)

    # ── Helpers de DOM ──
    def _aguardar_ajax(self, timeout_ms: int = 8000) -> None:
        """Aguarda AJAX JSF concluir (espelha lógica do legado simplificada)."""
        try:
            self._page.wait_for_function(
                "() => typeof window.__ajaxCompleto === 'undefined' "
                "|| window.__ajaxCompleto === true",
                timeout=timeout_ms,
            )
        except PlaywrightTimeout:
            try:
                self._page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                self._page.wait_for_timeout(800)
        else:
            try:
                self._page.evaluate("() => { window.__ajaxCompleto = false; }")
            except Exception:
                pass

    def _fill_text(self, sufixo: str, valor: Optional[str]) -> bool:
        """Preenche input text com sufixo de id. None/'' = no-op."""
        if valor is None or valor == "":
            return False
        try:
            loc = self._page.locator(f"input[id$='{sufixo}']").first
            if loc.count() == 0:
                self.log(f"  ⚠ campo '{sufixo}' não encontrado")
                return False
            loc.fill(str(valor))
            return True
        except Exception as e:
            self.log(f"  ⚠ fill {sufixo}: {e}")
            return False

    def _fill_date(self, sufixo: str, valor_br: Optional[str]) -> bool:
        """Preenche campo de data (formato DD/MM/YYYY). RichFaces calendar:
        usa press_sequentially para evitar abrir popup."""
        if not valor_br:
            return False
        try:
            loc = self._page.locator(f"input[id$='{sufixo}']").first
            if loc.count() == 0:
                self.log(f"  ⚠ data '{sufixo}' não encontrada")
                return False
            loc.focus()
            self._page.keyboard.press("Control+a")
            self._page.keyboard.press("Delete")
            loc.press_sequentially(valor_br.replace("/", ""), delay=40)
            self._page.keyboard.press("Escape")  # fecha popup do calendário
            self._page.wait_for_timeout(100)
            return True
        except Exception as e:
            self.log(f"  ⚠ fill_date {sufixo}: {e}")
            return False

    def _fill_decimal(self, sufixo: str, valor: Optional[str]) -> bool:
        """Preenche campo decimal BR (ex.: '1.234,56'). Aceita None."""
        if valor is None or valor == "":
            return False
        return self._fill_text(sufixo, valor)

    def _click_radio(self, name_or_sufixo: str, valor: str) -> bool:
        """Clica radio com name=name_or_sufixo. Aceita value (DOM) OU label
        visível ao usuário (texto adjacente). None/'' no-op.

        Tiers:
          1. value exato (ex: 'FIXA', 'INFORMADO')
          2. label exato (ex: 'Fixa', 'Variável', 'Informado')
          3. label includes case-insensitive
        """
        if not valor:
            return False
        try:
            # Tier 1: value exato
            sel_value = (
                f"input[type='radio'][name='formulario:{name_or_sufixo}'][value='{valor}'],"
                f"input[type='radio'][name$=':{name_or_sufixo}'][value='{valor}'],"
                f"input[type='radio'][id*='{name_or_sufixo}'][value='{valor}']"
            )
            loc = self._page.locator(sel_value).first
            if loc.count() > 0:
                loc.click(force=True)
                self._aguardar_ajax(3000)
                return True

            # Tier 2/3: por label adjacente (JSF radio: <input/> + <label for>)
            clicou = self._page.evaluate(
                """(args) => {
                    const norm = s => (s||'').toUpperCase()
                        .normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')
                        .replace(/\\s+/g,' ').trim();
                    const alvo = norm(args.valor);
                    const radios = [...document.querySelectorAll(
                        `input[type=radio][name*=':${args.nome}'], input[type=radio][id*='${args.nome}']`
                    )];
                    for (const r of radios) {
                        // Procurar label associada
                        let txt = '';
                        if (r.id) {
                            const lbl = document.querySelector(`label[for="${r.id}"]`);
                            if (lbl) txt = norm(lbl.textContent || '');
                        }
                        // Fallback: irmãos (comum em JSF radio sem label for)
                        if (!txt) {
                            let s = r.nextSibling;
                            while (s && !txt) {
                                txt = norm(s.textContent || s.nodeValue || '');
                                s = s.nextSibling;
                                if (txt) break;
                            }
                        }
                        // Tier 2: exato
                        if (txt === alvo) { r.click(); return 'tier2:' + r.id; }
                    }
                    // Tier 3: includes
                    for (const r of radios) {
                        let txt = '';
                        if (r.id) {
                            const lbl = document.querySelector(`label[for="${r.id}"]`);
                            if (lbl) txt = norm(lbl.textContent || '');
                        }
                        if (!txt) {
                            let s = r.nextSibling;
                            while (s && !txt) {
                                txt = norm(s.textContent || s.nodeValue || '');
                                s = s.nextSibling;
                                if (txt) break;
                            }
                        }
                        if (txt && (txt.includes(alvo) || alvo.includes(txt))) {
                            r.click(); return 'tier3:' + r.id;
                        }
                    }
                    return null;
                }""",
                {"nome": name_or_sufixo, "valor": valor},
            )
            if clicou:
                self._aguardar_ajax(3000)
                return True
            self.log(f"  ⚠ radio '{name_or_sufixo}={valor}' não encontrado")
            return False
        except Exception as e:
            self.log(f"  ⚠ click_radio {name_or_sufixo}={valor}: {e}")
            return False

    def _select_value(self, sufixo: str, valor: str) -> bool:
        """Seleciona option em select com sufixo. None/'' no-op.

        Tenta em ordem: por value exato → por label/texto exato →
        por texto contém (case-insensitive). Cobre selects que usam
        índice numérico (estado), texto direto (município nome),
        ou enum (tipoDaBaseTabelada).
        """
        if not valor:
            return False
        try:
            loc = self._page.locator(f"select[id$='{sufixo}']").first
            if loc.count() == 0:
                self.log(f"  ⚠ select '{sufixo}' não encontrado")
                return False
            # Tier 1: por value
            try:
                loc.select_option(value=valor, timeout=3000)
                self._aguardar_ajax(3000)
                return True
            except Exception:
                pass
            # Tier 2: por label exato
            try:
                loc.select_option(label=valor, timeout=3000)
                self._aguardar_ajax(3000)
                return True
            except Exception:
                pass
            # Tier 3: case-insensitive label match via JS
            opt_idx = self._page.evaluate(
                """(args) => {
                    const sel = document.querySelector('select[id$="' + args.sufixo + '"]');
                    if (!sel) return null;
                    const alvo = (args.valor||'').toUpperCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
                    for (const o of [...sel.options]) {
                        const t = (o.textContent||'').toUpperCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').trim();
                        if (t === alvo || t.startsWith(alvo) || (alvo.length >= 4 && t.includes(alvo))) return o.value;
                    }
                    return null;
                }""",
                {"sufixo": sufixo, "valor": valor},
            )
            if opt_idx is not None:
                loc.select_option(value=opt_idx, timeout=3000)
                self._aguardar_ajax(3000)
                return True
            self.log(f"  ⚠ select {sufixo}={valor}: nenhuma estratégia casou")
            return False
        except Exception as e:
            self.log(f"  ⚠ select {sufixo}={valor}: {e}")
            return False

    def _click_checkbox(self, sufixo: str, marcar: bool) -> bool:
        """Sincroniza estado do checkbox com `marcar`."""
        try:
            loc = self._page.locator(f"input[type='checkbox'][id$='{sufixo}']").first
            if loc.count() == 0:
                return False
            atual = loc.is_checked()
            if atual != marcar:
                loc.click(force=True)
                self._aguardar_ajax(2000)
            return True
        except Exception as e:
            self.log(f"  ⚠ checkbox {sufixo}={marcar}: {e}")
            return False

    def _clicar_salvar(self) -> bool:
        """Click 'Salvar' via dispatchEvent (compatible com A4J.AJAX.Submit).

        DOM real (Chrome MCP): id='formulario:salvar' type='button' com
        onclick=A4J.AJAX.Submit. Playwright .click() pode não disparar
        AJAX corretamente em alguns casos — dispatchEvent é mais confiável.
        """
        try:
            clicou = self._page.evaluate(
                """() => {
                    const b = document.querySelector('input[id="formulario:salvar"], input[id$=":salvar"]');
                    if (!b) return null;
                    b.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    return b.id || 'ok';
                }"""
            )
            if not clicou:
                self.log("  ⚠ botão Salvar não encontrado")
                return False
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(1500)
            return True
        except Exception as e:
            self.log(f"  ⚠ salvar: {e}")
            return False

    def _navegar_secao(self, nome_menu: str, jsf_path_fallback: str) -> bool:
        """Navega para uma seção do cálculo. Estratégia preferida: click no
        menu lateral (preserva Seam conversation). Se falhar, fallback para
        URL direta com conv_id atual.

        Confirmado via Chrome MCP live: cada fase navegada via menu lateral
        renderiza com Seam corretamente, mostrando todos os campos do form.
        URL direta pode levar a conv inválida com modal CNJ flutuante.
        """
        if self._clicar_menu_lateral(nome_menu):
            return True
        self.log(f"  ⚠ menu '{nome_menu}' falhou — fallback URL {jsf_path_fallback}")
        return self._navegar_url_calculo(jsf_path_fallback)

    def _navegar_url_calculo(self, jsf_path: str) -> bool:
        """Navega via URL direta. Sempre lê conv_id ATUAL da URL antes
        (pode ter mudado por save/Seam) e refresca pós-goto."""
        if "conversationId=" in self._page.url:
            atual = self._page.url.split("conversationId=")[1].split("&")[0].split("#")[0]
            if atual.isdigit() and atual != self._conv_id:
                self.log(f"  ↻ conv refresh: {self._conv_id} → {atual}")
                self._conv_id = atual
        if not self._conv_id:
            self.log("  ⚠ conversation_id ausente — não é possível navegar")
            return False
        url = f"{self._base_url}/pages/calculo/{jsf_path}?conversationId={self._conv_id}"
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
            self._aguardar_ajax(8000)
            if "conversationId=" in self._page.url:
                novo = self._page.url.split("conversationId=")[1].split("&")[0].split("#")[0]
                if novo.isdigit() and novo != self._conv_id:
                    self._conv_id = novo
            self._page.wait_for_timeout(400)
            return True
        except Exception as e:
            self.log(f"  ⚠ navegar {jsf_path}: {e}")
            return False

    # Mapa nome → seletor CSS do menu lateral.
    # Estrutura confirmada via screenshots (3 accordions: Cálculo / Operações
    # / Atualização / Tabelas). Tabelas são referências globais — não fazem
    # parte do cálculo individual (não usadas pelo aplicador, mas listadas
    # para evitar match cruzado em tier 2/3).
    # IDs CONFIRMADOS via inspeção DOM live (Chrome MCP, 2026-05-08).
    # Estrutura: li#li_<aba>_<secao>. NÃO há <a>, é o <li> que tem onclick;
    # mas seletor 'li#X a' funciona se houver link interno. Caso contrário,
    # o JS click no <li> dispara o handler.
    _MENU_SELECTORS = {
        # ── Aba "Cálculo" ──
        "Dados do Cálculo": "li#li_calculo_dados_do_calculo",
        "Faltas": "li#li_calculo_faltas",
        "Férias": "li#li_calculo_ferias",
        "Histórico Salarial": "li#li_calculo_historico_salarial",
        "Verbas": "li#li_calculo_verbas",
        "Cartão de Ponto": "li#li_calculo_cartao_ponto",
        "Salário-família": "li#li_calculo_salario_familia",
        "Seguro-desemprego": "li#li_calculo_seguro_desemprego",
        "FGTS": "li#li_calculo_fgts",
        "Contribuição Social": "li#li_calculo_inss",
        "Previdência Privada": "li#li_calculo_previdencia_privada",
        "Pensão Alimentícia": "li#li_calculo_pensao_alimenticia",
        "Imposto de Renda": "li#li_calculo_irpf",
        "Multas e Indenizações": "li#li_calculo_multas_e_indenizacoes",
        "Honorários": "li#li_calculo_honorarios",
        "Custas Judiciais": "li#li_calculo_custas_judiciais",
        "Correção, Juros e Multa": "li#li_calculo_correcao_juros_multa",
        "Relatórios": "li#li_calculo_relatorios",
        # ── Aba "Operações" (5 itens confirmados via DOM live) ──
        "Liquidar": "li#li_operacoes_liquidar",
        "Fechar": "li#li_operacoes_fechar",
        "Excluir": "li#li_operacoes_excluir",
        "Exportar": "li#li_operacoes_exportar",
        # CURIOSIDADE: id = 'validar' mas label = "Enviar para o PJe"
        "Enviar para o PJe": "li#li_operacoes_validar",
        # ── Aba "Tabelas" (referências globais) ──
        "Salário Mínimo": "li#li_tabelas_salario_minimo",
        "Salário Categoria": "li#li_tabelas_salario_categoria",
        "Salário-família (Tabelas)": "li#li_tabelas_salario_familia",
        "Seguro-desemprego (Tabelas)": "li#li_tabelas_seguro_desemprego",
        "Vale-transporte": "li#li_tabelas_vale_transporte",
        "Feriados": "li#li_tabelas_feriado",
        "Verbas (Tabelas)": "li#li_tabelas_verbas",
        "Contribuição Social (Tabelas)": "li#li_tabelas_inss",
        "Imposto de Renda (Tabelas)": "li#li_tabela_irpf",
        "Parâmetros Custas": "li#li_tabelas_parametros_custas",
        "Índices Gerais": "li#li_tabelas_indices_gerais",
        "Juros": "li#li_tabelas_juros",
        "Log de Infra": "li#li_tabelas_loginfra",
    }

    def _reabrir_calculo_recentes(self, processo_numero: str = "", reclamante_nome: str = "") -> bool:
        """Volta para principal.jsf e re-abre o cálculo via Recentes.
        Necessário quando a conversation atual está corrompida (ex: pós-Expresso
        save abre conv disjunta sem menu lateral do cálculo).

        Tiers de busca: CNJ → reclamante → 1º item se só houver 1.
        """
        try:
            self.log("  ↺ Re-abrindo cálculo via Recentes…")
            home = f"{self._base_url}/pages/principal.jsf"
            self._page.goto(home, wait_until="domcontentloaded", timeout=15000)
            self._aguardar_ajax(5000)
            self._page.wait_for_timeout(1500)

            # IDs do select são dinâmicos (formulario:j_idXX). Localizar por
            # label adjacente "Abrir Cálculos Recentes" + opções no formato
            # "<id_calc> / <processo> / <reclamante>".
            select_id = self._page.evaluate(
                """() => {
                    // Tier 1: select cuja primeira opção tem formato "NNNNNN / ..."
                    for (const s of document.querySelectorAll('select')) {
                        if (s.options.length > 0) {
                            const txt = (s.options[0].text || '');
                            if (/^\\d{4,}\\s*\\//.test(txt)) return s.name || s.id;
                        }
                    }
                    // Tier 2: por label próximo "Cálculos Recentes"
                    const fs = [...document.querySelectorAll('fieldset, legend, label, h3, h4, span, div')]
                        .find(e => /c[áa]lculos\\s*recentes/i.test(e.textContent || ''));
                    if (fs) {
                        const sel = fs.parentElement && fs.parentElement.querySelector('select');
                        if (sel) return sel.name || sel.id;
                    }
                    return null;
                }"""
            )
            if not select_id:
                self.log("  ⚠ select de Recentes não encontrado")
                return False
            self.log(f"  → select Recentes: {select_id}")
            listbox = self._page.locator(
                f"select[name='{select_id}'], select[id='{select_id}']"
            )
            if listbox.count() == 0:
                return False
            opts = listbox.first.locator("option")
            n = opts.count()
            self.log(f"  → Recentes: {n} opções")
            if n == 0:
                return False

            num_clean = (processo_numero or "").replace(".", "").replace("-", "").replace("/", "")
            found = None
            if num_clean:
                for i in range(n):
                    txt = (opts.nth(i).text_content() or "")
                    if num_clean in txt.replace(".", "").replace("-", "").replace("/", ""):
                        found = i
                        break
            if found is None and reclamante_nome and len(reclamante_nome) >= 5:
                up = reclamante_nome.strip().upper()
                for i in range(n):
                    if up in (opts.nth(i).text_content() or "").upper():
                        found = i
                        break
            if found is None and n == 1:
                self.log("  → Apenas 1 cálculo — usando")
                found = 0
            if found is None:
                amostra = [(opts.nth(i).text_content() or "")[:80] for i in range(min(n, 5))]
                self.log(f"  ⚠ Cálculo não encontrado. Recentes ({n}): {amostra}")
                return False

            opt_el = opts.nth(found)
            opt_el.click()
            self._page.wait_for_timeout(300)
            opt_el.dblclick()
            self._aguardar_ajax(20000)
            self._page.wait_for_timeout(2000)

            url = self._page.url
            if "calculo" in url and "conversationId" in url:
                novo = url.split("conversationId=")[1].split("&")[0].split("#")[0]
                self.log(f"  ✓ Cálculo re-aberto: conv_id={novo}")
                self._conv_id = novo
                return True
            return False
        except Exception as e:
            self.log(f"  ⚠ _reabrir_calculo_recentes: {e}")
            return False

    def _clicar_menu_lateral(self, secao: str) -> bool:
        """Clica em link do menu lateral via JS (preserva conversation Seam,
        diferente de _navegar_url_calculo que faz goto direto e pode iniciar
        nova conversation). Use APÓS save de operações que mudam conv_id
        (ex: Expresso save) ou para navegar entre páginas do cálculo.

        Estratégia em 3 tiers:
          1. Seletor exato `li#li_calculo_X a`
          2. Link <a> cujo texto/title casa o nome da seção (case-insensitive)
          3. <li> qualquer cuja substring inclua palavra-chave da seção
        """
        sel_exato = self._MENU_SELECTORS.get(secao, "")
        try:
            clicou = self._page.evaluate(
                """(args) => {
                    const norm = s => (s||'').toUpperCase()
                        .normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')
                        .replace(/\\s+/g,' ').trim();
                    const alvo = norm(args.secao);
                    // Tier 1: ID fixo
                    if (args.sel_exato) {
                        const a = document.querySelector(args.sel_exato);
                        if (a) { a.click(); return 'tier1:' + (a.id || 'ok'); }
                    }
                    // Tier 2: link cujo texto/title casa, mas DENTRO de li#li_calculo_*
                    // (preserva contexto do cálculo, evita menus Tabelas/Adm)
                    const linksCalc = [...document.querySelectorAll('li[id^="li_calculo_"] a')];
                    for (const a of linksCalc) {
                        const t = norm((a.textContent||'') + ' ' + (a.title||''));
                        if (t === alvo || t.includes(alvo)) {
                            a.click();
                            return 'tier2:' + (a.closest('li').id);
                        }
                    }
                    // Tier 3: qualquer li#li_calculo_* cuja primeira palavra do alvo casa
                    const palavra1 = alvo.split(' ')[0];
                    const lisCalc = [...document.querySelectorAll('li[id^="li_calculo_"]')];
                    for (const li of lisCalc) {
                        if (norm(li.id).includes(palavra1) || norm(li.textContent).includes(alvo)) {
                            const a = li.querySelector('a');
                            if (a) { a.click(); return 'tier3:' + li.id; }
                        }
                    }
                    return null;
                }""",
                {"sel_exato": sel_exato, "secao": secao},
            )
            if not clicou:
                # Diagnóstico: listar menus disponíveis
                lis_disponiveis = self._page.evaluate(
                    """() => [...document.querySelectorAll('li[id^="li_"]')]
                            .slice(0,20).map(li => li.id)"""
                )
                self.log(f"  ⚠ menu lateral '{secao}': não encontrado")
                self.log(f"    disponíveis: {lis_disponiveis[:15]}")
                return False
            self.log(f"  ✓ menu lateral '{secao}': {clicou}")
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(800)
            # Capturar conv_id atual
            if "conversationId=" in self._page.url:
                novo = self._page.url.split("conversationId=")[1].split("&")[0].split("#")[0]
                if novo != self._conv_id:
                    self._conv_id = novo
            return True
        except Exception as e:
            self.log(f"  ⚠ menu lateral '{secao}': {e}")
            return False

    # ────────────────────────────────────────────────────────────────────────
    # FASE 1 — Dados do Processo
    # ────────────────────────────────────────────────────────────────────────

    # UF → índice numérico do select PJE-Calc (DOM: <option value="N">UF</option>)
    _UF_INDEX = {
        "AC":"0","AL":"1","AP":"2","AM":"3","BA":"4","CE":"5","DF":"6","ES":"7",
        "GO":"8","MA":"9","MT":"10","MS":"11","MG":"12","PA":"13","PB":"14",
        "PR":"15","PE":"16","PI":"17","RJ":"18","RN":"19","RS":"20","RO":"21",
        "RR":"22","SC":"23","SP":"24","SE":"25","TO":"26",
    }

    def _set_processo_cache(self, p: DadosProcesso) -> None:
        """Salva número CNJ + nome reclamante para uso em re-abrir Recentes."""
        try:
            cnj = f"{p.numero}-{p.digito}.{p.ano}.5.{p.regiao}.{p.vara}"
            self._processo_numero = cnj
            self._reclamante_nome = p.reclamante_nome or ""
        except Exception:
            pass

    def aplicar_dados_processo(self, p: DadosProcesso) -> bool:
        """Preenche a página 1 (calculo.jsf) com TODOS os campos não-vazios
        de DadosProcesso. Salva ao final.

        Importante (DOM auditado v1):
          - estado/municipio estão na aba "Parâmetros do Cálculo" (não na
            "Dados do Processo"). Precisa clicar tab antes.
          - estado usa ÍNDICE NUMÉRICO (0=AC, 5=CE…), não a sigla.
        """
        self.log("→ Fase 1: Dados do Processo")
        self._set_processo_cache(p)
        if not self._navegar_url_calculo("calculo.jsf"):
            return False

        # ── Aba "Dados do Processo" (default, mas garantir) ──
        # Identificação
        self._fill_text("numero", p.numero)
        self._fill_text("digito", p.digito)
        self._fill_text("ano", p.ano)
        self._fill_text("regiao", p.regiao)
        self._fill_text("vara", p.vara)
        self._fill_decimal("valorDaCausa", p.valor_da_causa)
        self._fill_date("autuadoEm", p.autuado_em)

        # Reclamante
        if p.documento_fiscal_reclamante:
            self._click_radio("documentoFiscalReclamante", p.documento_fiscal_reclamante)
        self._fill_text("reclamanteNumeroDocumentoFiscal", p.reclamante_numero_documento_fiscal)
        self._fill_text("reclamanteNome", p.reclamante_nome)
        if p.reclamante_tipo_documento_previdenciario:
            self._click_radio("reclamanteTipoDocumentoPrevidenciario",
                              p.reclamante_tipo_documento_previdenciario)
        self._fill_text("reclamanteNumeroDocumentoPrevidenciario",
                        p.reclamante_numero_documento_previdenciario)
        self._fill_text("nomeAdvogadoReclamante", p.nome_advogado_reclamante)
        self._fill_text("numeroOABAdvogadoReclamante", p.numero_oab_advogado_reclamante)
        if p.tipo_documento_advogado_reclamante:
            self._click_radio("tipoDocumentoAdvogadoReclamante",
                              p.tipo_documento_advogado_reclamante)
        self._fill_text("numeroDocumentoAdvogadoReclamante",
                        p.numero_documento_advogado_reclamante)

        # Reclamado
        self._fill_text("reclamadoNome", p.reclamado_nome)
        if p.tipo_documento_fiscal_reclamado:
            self._click_radio("tipoDocumentoFiscalReclamado",
                              p.tipo_documento_fiscal_reclamado)
        self._fill_text("reclamadoNumeroDocumentoFiscal", p.reclamado_numero_documento_fiscal)
        self._fill_text("nomeAdvogadoReclamado", p.nome_advogado_reclamado)
        self._fill_text("numeroOABAdvogadoReclamado", p.numero_oab_advogado_reclamado)
        if p.tipo_documento_advogado_reclamado:
            self._click_radio("tipoDocumentoAdvogadoReclamado",
                              p.tipo_documento_advogado_reclamado)
        self._fill_text("numeroDocumentoAdvogadoReclamado",
                        p.numero_documento_advogado_reclamado)

        # ── Aba "Parâmetros do Cálculo" (clicar ANTES de estado/municipio/datas) ──
        # Estratégia em 4 tiers (espelha v1 _clicar_aba):
        #   1. id$='tabParametrosCalculo_lbl' (label da tab)
        #   2. id$='tabParametrosCalculo_header'
        #   3. .rich-tab-header com texto 'Parâmetros'
        #   4. <td>/<th> com texto 'Parâmetros do Cálculo'
        tab_clicado = False
        for sel in (
            "[id$='tabParametrosCalculo_lbl']",
            "[id$='tabParametrosCalculo_header']",
            "[id$='tabParametrosCalculo'] span",
        ):
            try:
                loc = self._page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=5000)
                    tab_clicado = True
                    self.log(f"  ✓ tab Parâmetros via {sel}")
                    break
            except Exception:
                continue
        if not tab_clicado:
            try:
                clicou = self._page.evaluate(
                    """() => {
                        const cands = [...document.querySelectorAll(
                            '.rich-tab-header, td.rich-tab-header, td.rich-tab, .rich-tab-label, span.rich-tab-label, td'
                        )];
                        const t = cands.find(e => /par[âa]metros\\s*do\\s*c[áa]lculo/i.test((e.textContent||'').trim()));
                        if (t) { t.click(); return t.id || 'ok'; }
                        return null;
                    }"""
                )
                if clicou:
                    self.log(f"  ✓ tab Parâmetros via JS evaluate: {clicou}")
                    tab_clicado = True
            except Exception:
                pass
        if not tab_clicado:
            self.log("  ⚠ tab 'Parâmetros do Cálculo' não encontrada — selects estado/municipio podem falhar")
        self._aguardar_ajax(5000)
        self._page.wait_for_timeout(1200)

        # Estado: schema v3 tem sigla (CE), DOM espera ÍNDICE
        if p.estado:
            idx_estado = self._UF_INDEX.get(p.estado.upper())
            if idx_estado:
                self._select_value("estado", idx_estado)
                self._aguardar_ajax(2000)
        # Município: select dependente do estado, popula via AJAX após estado escolhido
        if p.municipio:
            self._select_value("municipio", p.municipio)

        self._fill_date("dataAdmissaoInputDate", p.data_admissao)
        self._fill_date("dataDemissaoInputDate", p.data_demissao)
        self._fill_date("dataAjuizamentoInputDate", p.data_ajuizamento)
        self._fill_date("dataInicioCalculoInputDate", p.data_inicio_calculo)
        self._fill_date("dataTerminoCalculoInputDate", p.data_termino_calculo)
        self._fill_decimal("valorMaiorRemuneracao", p.valor_maior_remuneracao)
        self._fill_decimal("valorUltimaRemuneracao", p.valor_ultima_remuneracao)

        # Prescrição / Aviso Prévio / Outros (checkboxes)
        self._click_checkbox("prescricaoQuinquenal", p.prescricao_quinquenal)
        self._click_checkbox("prescricaoFgts", p.prescricao_fgts)
        self._click_checkbox("projetaAvisoIndenizado", p.projeta_aviso_indenizado)
        self._click_checkbox("zeraValorNegativo", p.zera_valor_negativo)
        self._click_checkbox("consideraFeriadoEstadual", p.considera_feriado_estadual)
        self._click_checkbox("consideraFeriadoMunicipal", p.considera_feriado_municipal)
        self._click_checkbox("sabadoDiaUtil", p.sabado_dia_util)

        if p.apuracao_prazo_aviso_previo and p.apuracao_prazo_aviso_previo != "NAO_APURAR":
            self._select_value("apuracaoPrazoDoAvisoPrevio", p.apuracao_prazo_aviso_previo)

        self._fill_decimal("valorCargaHorariaPadrao", p.valor_carga_horaria_padrao)
        self._fill_text("comentarios", p.comentarios)

        # Salvar e capturar conversation_id (remove anchor # também)
        ok = self._clicar_salvar()
        if ok and "conversationId=" in self._page.url:
            raw = self._page.url.split("conversationId=")[1]
            self._conv_id = raw.split("&")[0].split("#")[0]
            self.log(f"  ✓ Fase 1 OK | conv={self._conv_id}")
        return ok

    # ────────────────────────────────────────────────────────────────────────
    # FASE 5 — Verbas (núcleo do aplicador)
    # ────────────────────────────────────────────────────────────────────────

    # Maps DOM enum → o que o radio espera (espelho do schema v3)
    _MAP_CARAC = {
        "COMUM": "COMUM",
        "DECIMO_TERCEIRO_SALARIO": "DECIMO_TERCEIRO_SALARIO",
        "AVISO_PREVIO": "AVISO_PREVIO",
        "FERIAS": "FERIAS",
    }
    _MAP_OCORR = {
        "MENSAL": "MENSAL", "DEZEMBRO": "DEZEMBRO",
        "DESLIGAMENTO": "DESLIGAMENTO", "PERIODO_AQUISITIVO": "PERIODO_AQUISITIVO",
    }

    def aplicar_verbas(self, verbas: list[Verba]) -> bool:
        """Aplica a lista de verbas (PRINCIPAIS) na página 5 (verba-calculo.jsf).

        Para cada verba:
          1. Lança via Expresso (se v.lancamento=='EXPRESSO') ou cria via Manual
          2. Aplica Parâmetros literalmente
          3. Aplica Ocorrências linha-por-linha (ativa/desativa, preenche
             termoDiv/termoMult/termoQuant/valorDevido/dobra)
          4. Para cada reflexo: idem (recursivo via marcar reflex no Exibir)
        """
        self.log(f"→ Fase 5: Verbas ({len(verbas)} principais)")
        if not self._navegar_secao("Verbas", "verba/verba-calculo.jsf"):
            return False

        # Lançamento Expresso em batch para verbas com lancamento=EXPRESSO
        verbas_expresso = [v for v in verbas if v.lancamento == "EXPRESSO" and v.expresso_alvo]
        # Salvar conv ORIGINAL antes do Expresso (preserva contexto do cálculo)
        conv_original = self._conv_id
        if verbas_expresso:
            self._lancar_expresso(verbas_expresso)
            # IMPORTANTE: NÃO atualizar self._conv_id pós-save Expresso!
            # A conv pós-save é "flutuante" (sem menu lateral do cálculo).
            # Manter conv original permite que fases seguintes (FGTS, INSS,
            # IR, Honorários, Custas, Correção/Juros) re-naveguem com o
            # cálculo ainda no contexto Seam.
            url_pos = self._page.url
            self.log(f"  🔍 URL pós-Expresso save: {url_pos[-80:]}")
            self.log(f"  ↺ Mantendo conv original: {conv_original}")
            self._conv_id = conv_original
            # Estratégia 1: menu lateral (preserva Seam)
            menu_ok = self._clicar_menu_lateral("Verbas")
            # Estratégia 2: re-abrir cálculo via Recentes (conv pós-Expresso é
            # disjunta — não tem li_calculo_*; precisa restaurar contexto
            # Seam buscando o cálculo na lista da home)
            if not menu_ok:
                self.log("  ⚠ menu Verbas falhou — re-abrindo via Recentes")
                if self._reabrir_calculo_recentes(
                    processo_numero=self._processo_numero,
                    reclamante_nome=self._reclamante_nome,
                ):
                    # Após re-abrir, navegar para Verbas via menu (agora disponível)
                    if not self._clicar_menu_lateral("Verbas"):
                        self.log("  ⚠ menu Verbas continua indisponível pós-Recentes")
                        self._navegar_url_calculo("verba/verba-calculo.jsf")
                else:
                    self._navegar_url_calculo("verba/verba-calculo.jsf")
            self._page.wait_for_timeout(5000)  # Expresso save + AJAX render listagem demora
            if self._detectar_erro_pagina():
                self.log("  ⚠ Listagem em erro 500/NPE pós-Expresso — pulando aplicação detalhada")
                return False
            # Diagnóstico: dump de TODOS os <tr> + título + qualquer <table>
            try:
                dump = self._page.evaluate(
                    """() => {
                        const all_trs = [...document.querySelectorAll('tr')];
                        const tabelas = [...document.querySelectorAll('table')].map(t => ({
                            id: t.id, n_rows: t.rows.length, classe: t.className.slice(0, 60)
                        }));
                        return {
                            url: location.pathname + location.search,
                            title: document.title,
                            heading: (document.querySelector('h1, h2, .title, .rich-page-title') || {}).textContent || '',
                            n_all_trs: all_trs.length,
                            n_listagem_trs: document.querySelectorAll('tr[id*=":listagem:"]').length,
                            tabelas: tabelas.slice(0, 5),
                            // primeiros IDs de tr existentes
                            tr_ids_sample: all_trs.slice(0, 8).map(tr => tr.id || '<sem-id>'),
                            // procurar palavra "verba" no body
                            tem_verba_no_body: (document.body.textContent||'').toLowerCase().includes('verba'),
                            // procurar mensagens de erro
                            tem_erro_500: (document.body.textContent||'').includes('500') || (document.body.textContent||'').includes('NPE') || (document.body.textContent||'').includes('Erro'),
                        };
                    }"""
                )
                self.log(f"  🔍 url={dump.get('url', '?')}")
                self.log(f"  🔍 title='{dump.get('title','?')[:60]}' heading='{dump.get('heading','?')[:60]}'")
                self.log(f"  🔍 n_all_trs={dump.get('n_all_trs',0)} n_listagem={dump.get('n_listagem_trs',0)} tem_verba={dump.get('tem_verba_no_body',False)} erro_500={dump.get('tem_erro_500',False)}")
                self.log(f"  🔍 tabelas={dump.get('tabelas',[])[:3]}")
                self.log(f"  🔍 tr_ids={dump.get('tr_ids_sample',[])[:5]}")
                # Dump extra: snippet do body + IDs únicos das primeiras tabelas
                extra = self._page.evaluate(
                    """() => {
                        const body = (document.body.textContent || '').replace(/\\s+/g,' ').trim();
                        const start_erro = body.search(/(erro|exception|500|npe)/i);
                        const trs_com_id = [...document.querySelectorAll('tr[id]')].slice(0, 10).map(tr => tr.id);
                        const trs_links = [...document.querySelectorAll('tr')].filter(tr => tr.querySelector('a[id]'));
                        return {
                            body_around_erro: start_erro >= 0 ? body.slice(Math.max(0,start_erro-50), start_erro+200) : '',
                            tr_ids_with_id: trs_com_id,
                            n_trs_com_link: trs_links.length,
                            sample_link_ids: trs_links.slice(0,3).map(tr => [...tr.querySelectorAll('a')].slice(0,3).map(a => a.id || '<no-id>')),
                        };
                    }"""
                )
                self.log(f"  🔍 body_perto_erro: {(extra.get('body_around_erro','')[:200])}")
                self.log(f"  🔍 trs_com_id={extra.get('tr_ids_with_id',[])[:6]}")
                self.log(f"  🔍 n_trs_com_link={extra.get('n_trs_com_link',0)} sample_links={extra.get('sample_link_ids',[])[:3]}")
            except Exception as e:
                self.log(f"  ⚠ diagnóstico DOM falhou: {e}")

        # Verbas Manual (criadas individualmente via Manual)
        for v in verbas:
            if v.lancamento != "EXPRESSO":
                self._criar_verba_manual(v)
                # após criar manual, voltar para listagem
                self._navegar_url_calculo("verba/verba-calculo.jsf")

        # Para cada verba (Expresso ou Manual): aplicar Parâmetros + Ocorrências
        for v in verbas:
            self._aplicar_verba_completa(v)

        return True

    def _lancar_expresso(self, verbas_expresso: list[Verba]) -> bool:
        """Click 'Lançamento Expresso', marca os checkboxes das verbas
        listadas e salva. Não infere — usa apenas os nomes em
        v.expresso_alvo."""
        self.log(f"  → Lançamento Expresso: {len(verbas_expresso)} verba(s)")
        try:
            btn = self._page.locator("input[id$='lancamentoExpresso']").first
            if btn.count() == 0:
                return False
            btn.click(force=True)
            self._aguardar_ajax(5000)

            nomes_alvo = [v.expresso_alvo for v in verbas_expresso if v.expresso_alvo]
            marcou = self._page.evaluate(
                """(nomes) => {
                    const cbs = [...document.querySelectorAll(
                        'input[type=checkbox][id$=":selecionada"]'
                    )];
                    let n = 0;
                    for (const cb of cbs) {
                        const td = cb.closest('td');
                        if (!td) continue;
                        const label = td.textContent.trim().toUpperCase();
                        if (nomes.includes(label)) {
                            if (!cb.checked) cb.click();
                            n++;
                        }
                    }
                    return n;
                }""",
                [n.upper() for n in nomes_alvo],
            )
            self.log(f"    ✓ {marcou} verba(s) marcada(s) no Expresso")
            self._clicar_salvar()
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(1500)
            # NB: modal Assunto CNJ NÃO se abre em Expresso/Expresso Adaptado
            # (apenas em verbas Manuais). Se rendered no DOM, está hidden.
            return True
        except Exception as e:
            self.log(f"  ⚠ Lançamento Expresso: {e}")
            return False

    def _criar_verba_manual(self, v: Verba) -> bool:
        """Click 'Manual' → abre form Novo. Preenche descrição mínima.
        Os Parâmetros completos serão aplicados em _aplicar_verba_completa."""
        self.log(f"  → Manual: '{v.parametros.descricao}'")
        try:
            btn = self._page.locator("input[id$='incluir'][value='Manual']").first
            if btn.count() == 0:
                return False
            btn.click(force=True)
            self._aguardar_ajax(5000)
            self._fill_text("descricao", v.parametros.descricao)
            # Os demais campos são aplicados em _aplicar_parametros_verba
            self._aplicar_parametros_verba(v.parametros)
            self._clicar_salvar()
            return True
        except Exception as e:
            self.log(f"  ⚠ criar Manual '{v.parametros.descricao}': {e}")
            return False

    def _achar_link_acao_verba(self, descricao: str, kind: str) -> Optional[str]:
        """Localiza ID do link de ação (Parâmetros/Ocorrências/Exibir) para a
        verba cuja linha contenha `descricao`.

        DOM auditado v2.15.1 via Chrome MCP live (2026-05-08):
          - Tabela: table[id='formulario:listagem']
          - Linhas verba: tr.rich-table-firstrow (SEM id próprio!)
          - Linhas reflexos: tr.rich-table-row.linha-par-exibir
          - Links na linha: a[id='formulario:listagem:N:j_id558'] (Parâmetros),
            j_id559 (Ocorrências), j_id560 (Excluir)
          - Title sempre presente: 'Parâmetros da Verba', 'Ocorrências da Verba',
            'Excluir'

        Estratégia em camadas: identifica linha por texto da primeira célula
        (nome da verba); pega link do tipo desejado por title OU j_id5XX.
        """
        # Map kind → ID sufixo confirmado via Chrome MCP live
        idfix = {"parametros": "j_id558", "ocorrencias": "j_id559"}.get(kind, "")
        title_kw = {
            "parametros": ["PARAMETRO"],
            "ocorrencias": ["OCORRENCIA"],
            "exibir": ["EXIBIR", "REFLEXA", "REFLEXO"],
        }.get(kind, [])
        return self._page.evaluate(
            """(args) => {
                const {nome, idfix, titleKw} = args;
                const norm = s => (s||'').toUpperCase()
                    .normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')
                    .replace(/\\s+/g, ' ').trim();
                const alvo = norm(nome);

                // ESTRATÉGIA NOVA (Chrome MCP confirmed): iterar DIRETO pelos
                // links j_id558/559 — cada um corresponde a uma verba principal.
                // closest('tr').textContent dá nome da verba + ' Exibir'.
                let links_alvo;
                if (idfix) {
                    links_alvo = [...document.querySelectorAll(
                        `a[id*=":listagem:"][id$=":${idfix}"]`
                    )];
                } else if (titleKw && titleKw.length) {
                    links_alvo = [...document.querySelectorAll('a[id*=":listagem:"]')]
                        .filter(a => {
                            const t = norm((a.title||'') + ' ' + (a.alt||'') + ' ' + (a.textContent||''));
                            if (titleKw.includes('PARAMETRO') && (t.includes('OCORRENCIA') || t.includes('EXCLUI'))) return false;
                            if (titleKw.includes('OCORRENCIA') && (t.includes('PARAMETRO') || t.includes('EXCLUI'))) return false;
                            return titleKw.some(kw => t.includes(kw));
                        });
                } else {
                    links_alvo = [];
                }

                const candidatos = links_alvo.map(link => {
                    const tr = link.closest('tr');
                    let nomeLinha = '';
                    if (tr) {
                        nomeLinha = tr.textContent.replace(/\\s+/g,' ').trim()
                            .replace(/Exibir.*$/i, '').trim();
                    }
                    return {link, nomeLinha, normNome: norm(nomeLinha)};
                });

                // Match exato → inclusão → palavras-chave
                for (const c of candidatos) if (c.normNome === alvo) return c.link.id;
                for (const c of candidatos) {
                    if (c.normNome.includes(alvo) || alvo.includes(c.normNome)) return c.link.id;
                }
                const palavras = alvo.split(' ').filter(p => p.length >= 3);
                for (const c of candidatos) {
                    if (palavras.length && palavras.every(p => c.normNome.includes(p))) return c.link.id;
                }
                return null;
            }""",
            {"nome": descricao, "idfix": idfix, "titleKw": title_kw},
        )

    def _detectar_erro_pagina(self) -> bool:
        """Detecta HTTP 500/NPE/ViewExpired na página atual de verbas (bug
        conhecido do PJE-Calc após Expresso). Retorna True se houver erro."""
        try:
            return bool(self._page.evaluate(
                """() => {
                    const body = (document.body && document.body.textContent) || '';
                    return body.includes('HTTP Status 500') ||
                           body.includes('NullPointerException') ||
                           body.includes('Erro inesperado') ||
                           body.includes('ViewExpiredException');
                }"""
            ))
        except Exception:
            return False

    def _aplicar_verba_completa(self, v: Verba) -> bool:
        """Abre página Parâmetros da verba pelo nome, aplica TUDO + ocorrências."""
        self.log(f"  → Aplicar verba completa: '{v.parametros.descricao}'")
        try:
            # Garantir que estamos na listagem (verba-calculo.jsf)
            if "verba-calculo" not in self._page.url or "verbas-para-calculo" in self._page.url:
                self._navegar_url_calculo("verba/verba-calculo.jsf")
            if self._detectar_erro_pagina():
                self.log(f"    ⚠ verba-calculo.jsf em erro 500/NPE — pulando '{v.parametros.descricao}'")
                return False

            link_id = self._achar_link_acao_verba(v.parametros.descricao, "parametros")
            if not link_id:
                self.log(f"    ⚠ link Parâmetros de '{v.parametros.descricao}' não encontrado")
                return False
            try:
                self._page.locator(f"a[id='{link_id}']").first.click(timeout=8000)
            except Exception:
                self._page.evaluate(f"() => {{ const e = document.getElementById({link_id!r}); if (e) e.click(); }}")
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(600)

            # Aplicar Parâmetros + Salvar
            self._aplicar_parametros_verba(v.parametros)
            self._clicar_salvar()

            # Voltar à listagem e abrir Ocorrências
            if v.ocorrencias:
                self._navegar_url_calculo("verba/verba-calculo.jsf")
                if self._abrir_ocorrencias_verba(v.parametros.descricao):
                    self._aplicar_ocorrencias_verba(v.ocorrencias)
                    self._clicar_salvar()

            # Reflexos (cada reflexo é uma Verba — fluxo Exibir+Parâmetros)
            for ref in v.reflexos:
                self._navegar_url_calculo("verba/verba-calculo.jsf")
                self._aplicar_reflexo(v.parametros.descricao, ref)

            return True
        except Exception as e:
            self.log(f"  ⚠ aplicar_verba_completa '{v.parametros.descricao}': {e}")
            return False

    def _aplicar_parametros_verba(self, p: ParametrosVerba) -> None:
        """Aplica todos os campos de ParametrosVerba na tela aberta."""
        self._fill_text("descricao", p.descricao)
        self._fill_text("assuntosCnj", p.assuntos_cnj)
        self._click_radio("tipoDeVerba", "Principal" if p.tipo_de_verba == "PRINCIPAL" else "Reflexa")
        self._click_radio("tipoVariacaoDaParcela", "Fixa" if p.tipo_variacao_da_parcela == "FIXA" else "Variável")
        self._click_radio("caracteristicaVerba", self._MAP_CARAC.get(p.caracteristica_verba, "COMUM"))
        # Default da característica: COMUM→MENSAL, FERIAS→PERIODO_AQUISITIVO etc.
        # Backend aplica automaticamente via setCaracteristica. Só clicar
        # ocorrenciaPagto se diferir do default.
        defaults = {
            "COMUM": "MENSAL", "DECIMO_TERCEIRO_SALARIO": "DEZEMBRO",
            "AVISO_PREVIO": "DESLIGAMENTO", "FERIAS": "PERIODO_AQUISITIVO",
        }
        if p.ocorrencia_pagto != defaults.get(p.caracteristica_verba, "MENSAL"):
            self._click_radio("ocorrenciaPagto", self._MAP_OCORR.get(p.ocorrencia_pagto, "MENSAL"))

        self._click_radio(
            "ocorrenciaAjuizamento",
            "Sim" if p.ocorrencia_ajuizamento == "OCORRENCIAS_VENCIDAS_E_VINCENDAS" else "Não",
        )
        self._fill_date("periodoInicialInputDate", p.periodo_inicial)
        self._fill_date("periodoFinalInputDate", p.periodo_final)

        # Reflexa-specific
        if p.tipo_de_verba == "REFLEXA":
            if p.gera_reflexo:
                self._click_radio("geraReflexo", p.gera_reflexo)
            if p.gerar_principal:
                self._click_radio("gerarPrincipal", p.gerar_principal)
            self._click_radio("comporPrincipal", p.compor_principal)

        # Valor calc/inf
        self._click_radio("valor", "Calculado" if p.valor == "CALCULADO" else "Informado")
        self._fill_decimal("valorInformado", p.valor_informado)

        # Incidências
        self._click_checkbox("fgts", p.fgts)
        self._click_checkbox("inss", p.inss)
        self._click_checkbox("irpf", p.irpf)
        self._click_checkbox("previdenciaPrivada", p.previdencia_privada)
        self._click_checkbox("pensaoAlimenticia", p.pensao_alimenticia)

        # Base de Cálculo
        if p.tipo_da_base_tabelada:
            self._select_value("tipoDaBaseTabelada", p.tipo_da_base_tabelada)
            if p.base_historicos:
                self._select_value("baseHistoricos", p.base_historicos)
            if p.integralizar_base:
                self._select_value("integralizarBase", p.integralizar_base)

        # Divisor / Multiplicador
        self._click_radio("tipoDeDivisor",
                          "Carga Horária" if p.tipo_de_divisor == "CARGA_HORARIA"
                          else "Informado" if p.tipo_de_divisor == "INFORMADO"
                          else "Dias Úteis" if p.tipo_de_divisor == "DIAS_UTEIS"
                          else "Importada do Cartão de Ponto")
        self._fill_decimal("outroValorDoDivisor", p.outro_valor_do_divisor)
        self._fill_decimal("outroValorDoMultiplicador", p.outro_valor_do_multiplicador)

        # Quantidade
        self._click_radio("tipoDaQuantidade",
                          "Informada" if p.tipo_da_quantidade == "INFORMADA"
                          else "Importada do Calendário" if p.tipo_da_quantidade == "IMPORTADA_CALENDARIO"
                          else "Importada do Cartão de Ponto")
        self._fill_decimal("valorInformadoDaQuantidade", p.valor_informado_da_quantidade)
        self._click_checkbox("aplicarProporcionalidadeAQuantidade",
                             p.aplicar_proporcionalidade_quantidade)

        # Valor Pago (deduções)
        self._click_radio("tipoDoValorPago",
                          "Informado" if p.tipo_do_valor_pago == "INFORMADO" else "Calculado")
        self._fill_decimal("valorInformadoPago", p.valor_informado_pago)
        self._click_checkbox("aplicarProporcionalidadeValorPago",
                             p.aplicar_proporcionalidade_valor_pago)

        # Outros
        self._click_checkbox("zeraValorNegativo", p.zera_valor_negativo)
        self._click_checkbox("excluirFaltaJustificada", p.excluir_falta_justificada)
        self._click_checkbox("excluirFaltaNaoJustificada", p.excluir_falta_nao_justificada)
        self._click_checkbox("excluirFeriasGozadas", p.excluir_ferias_gozadas)
        self._click_checkbox("dobraValorDevido", p.dobra_valor_devido)
        self._click_checkbox("aplicarProporcionalidadeABase", p.aplicar_proporcionalidade_a_base)
        self._fill_text("comentarios", p.comentarios)

    def _abrir_ocorrencias_verba(self, descricao: str) -> bool:
        """Click no link Ocorrências (j_id559 ou title='Ocorrências da Verba')
        da linha com `descricao`. Usa fallback robusto via
        _achar_link_acao_verba."""
        link_id = self._achar_link_acao_verba(descricao, "ocorrencias")
        if not link_id:
            self.log(f"    ⚠ link Ocorrências de '{descricao}' não encontrado")
            return False
        try:
            self._page.locator(f"a[id='{link_id}']").first.click(timeout=8000)
        except Exception:
            self._page.evaluate(f"() => {{ const e = document.getElementById({link_id!r}); if (e) e.click(); }}")
        self._aguardar_ajax(8000)
        self._page.wait_for_timeout(500)
        return True

    def _aplicar_ocorrencias_verba(self, ocorrencias: list[OcorrenciaVerba]) -> None:
        """Para cada ocorrência do JSON, ativa/desativa e preenche valores
        EXATAMENTE como descrito. Itera por índice (formulario:listagem:N:*)."""
        if not ocorrencias:
            return
        self.log(f"    → {len(ocorrencias)} ocorrência(s) a aplicar")
        for oc in ocorrencias:
            try:
                # Ativar/desativar checkbox
                cbx_sel = f"input[type='checkbox'][id$='listagem:{oc.indice}:ativo']"
                cbx = self._page.locator(cbx_sel).first
                if cbx.count() > 0:
                    if cbx.is_checked() != oc.ativo:
                        cbx.click(force=True)
                        self._aguardar_ajax(1500)

                # Preencher campos (mesmo se ativo=False — mantém estado do JSON)
                if oc.termo_div is not None:
                    self._fill_decimal_by_id(f"listagem:{oc.indice}:termoDiv", oc.termo_div)
                if oc.termo_mult is not None:
                    self._fill_decimal_by_id(f"listagem:{oc.indice}:termoMult", oc.termo_mult)
                if oc.termo_quant is not None:
                    self._fill_decimal_by_id(f"listagem:{oc.indice}:termoQuant", oc.termo_quant)
                if oc.valor_devido is not None:
                    self._fill_decimal_by_id(f"listagem:{oc.indice}:valorDevido", oc.valor_devido)
                # Dobra
                dobra_sel = f"input[type='checkbox'][id$='listagem:{oc.indice}:dobra']"
                dobra = self._page.locator(dobra_sel).first
                if dobra.count() > 0 and dobra.is_checked() != oc.dobra:
                    dobra.click(force=True)
                    self._aguardar_ajax(1500)
            except Exception as e:
                self.log(f"      ⚠ ocorrência {oc.indice}: {e}")

    def _fill_decimal_by_id(self, sufixo: str, valor: str) -> None:
        """Preenche por sufixo de ID exato (sem busca por id$=...).
        Usado para ocorrências com indice fixo."""
        try:
            full = f"formulario:{sufixo}"
            inp = self._page.locator(f"input[id='{full}']").first
            if inp.count() == 0:
                return
            inp.fill(str(valor))
        except Exception as e:
            self.log(f"      ⚠ fill_by_id {sufixo}: {e}")

    def _aplicar_reflexo(self, verba_principal: str, ref: Verba) -> None:
        """Aplica um reflexo da verba principal.

        Fluxo confirmado pelo usuário (CLAUDE.md):
          1. Click "Exibir" da verba principal → abre painel inline com checkboxes
          2. Marca o checkbox cujo texto canônico = ref.expresso_alvo (ou descricao)
          3. Salva (refresh da listagem)
          4. Re-abre "Exibir" da principal — agora o botão "Parâmetros" do reflexo
             está disponível
          5. Click no Parâmetros do reflexo → aplica ParametrosVerba completos
          6. Salva
          7. Se ref.ocorrencias: abrir Ocorrências do reflexo via mesma listagem
             (a tabela mensal mostra principal + reflexos juntos — usamos a
             ocorrencias da PRINCIPAL nesse caso, então só aplicar se o caller
             explicitamente passar ocorrencias do reflexo)
        """
        nome_ref = (ref.expresso_alvo or ref.parametros.descricao or "").strip()
        if not nome_ref:
            return
        self.log(f"  → reflexo de '{verba_principal}': '{nome_ref}'")
        try:
            # Etapa 1: clicar "Exibir" da principal
            exibir_id = self._achar_link_acao_verba(verba_principal, "exibir")
            if not exibir_id:
                self.log(f"    ⚠ link Exibir de '{verba_principal}' não encontrado")
                return
            try:
                self._page.locator(f"#{exibir_id.replace(':', chr(92)+':')}").first.click(timeout=8000)
            except Exception:
                self._page.evaluate(f"() => {{ const e = document.getElementById({exibir_id!r}); if (e) e.click(); }}")
            self._aguardar_ajax(5000)
            self._page.wait_for_timeout(400)

            # Etapa 2: marcar checkbox do reflexo desejado
            marcou = self._page.evaluate(
                """(rNome) => {
                    const norm = s => (s||'').toUpperCase()
                        .normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')
                        .replace(/\\s+/g, ' ').trim();
                    const alvo = norm(rNome);
                    const palavras = alvo.split(' ').filter(p => p.length >= 3);
                    const cbs = [...document.querySelectorAll(
                        'input[type=checkbox][id*="listaReflexo"],' +
                        'input[type=checkbox][id*="reflexo"],' +
                        'input[type=checkbox][id*="Reflexo"]'
                    )];
                    for (const cb of cbs) {
                        if (cb.disabled) continue;
                        const ctx = cb.closest('td,tr,li,div') || cb.parentElement;
                        const txt = norm((ctx && ctx.textContent) || '');
                        const match = txt === alvo
                            || txt.includes(alvo)
                            || (palavras.length && palavras.every(p => txt.includes(p)));
                        if (match) {
                            if (!cb.checked) cb.click();
                            return cb.id || 'ok';
                        }
                    }
                    return null;
                }""",
                nome_ref,
            )
            if not marcou:
                self.log(f"    ⚠ checkbox reflexo '{nome_ref}' não encontrado")
                return
            self.log(f"    ✓ reflexo marcado ({marcou})")

            # Etapa 3: salvar (necessário para checkbox persistir)
            self._clicar_salvar()
            self._aguardar_ajax(6000)
            self._page.wait_for_timeout(500)

            # Etapa 4-5: re-navegar para listagem, re-abrir Exibir, achar Parâmetros do reflexo
            if not (ref.parametros and (ref.parametros.descricao or ref.parametros.assuntos_cnj)):
                # Sem parâmetros adicionais — reflexo apenas marcado
                return
            self._navegar_url_calculo("verba/verba-calculo.jsf")
            exibir_id2 = self._achar_link_acao_verba(verba_principal, "exibir")
            if exibir_id2:
                try:
                    self._page.locator(f"#{exibir_id2.replace(':', chr(92)+':')}").first.click(timeout=8000)
                except Exception:
                    self._page.evaluate(f"() => {{ const e = document.getElementById({exibir_id2!r}); if (e) e.click(); }}")
                self._aguardar_ajax(5000)

            # Achar link Parâmetros do reflexo (linha do reflexo agora visível)
            link_param_ref = self._achar_link_acao_verba(nome_ref, "parametros")
            if not link_param_ref:
                self.log(f"    ⚠ Parâmetros do reflexo '{nome_ref}' não encontrado")
                return
            try:
                self._page.locator(f"a[id='{link_param_ref}']").first.click(timeout=8000)
            except Exception:
                self._page.evaluate(f"() => {{ const e = document.getElementById({link_param_ref!r}); if (e) e.click(); }}")
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(500)

            # Etapa 6: aplicar parâmetros + salvar
            self._aplicar_parametros_verba(ref.parametros)
            self._clicar_salvar()

            # Etapa 7: ocorrências do reflexo (compartilha tabela com principal)
            if ref.ocorrencias:
                self._navegar_url_calculo("verba/verba-calculo.jsf")
                if self._abrir_ocorrencias_verba(verba_principal):
                    self._aplicar_ocorrencias_verba(ref.ocorrencias)
                    self._clicar_salvar()
        except Exception as e:
            self.log(f"    ⚠ _aplicar_reflexo '{nome_ref}': {e}")

    # ────────────────────────────────────────────────────────────────────────
    # FASE 7 — FGTS
    # ────────────────────────────────────────────────────────────────────────

    def aplicar_fgts(self, fgts: FGTS) -> bool:
        """Aplica FGTS (fgts.jsf) — DOM v2.15.1 confirmado.

        Radios usam values DOM-corretos (não labels):
          tipoDeVerba: PAGAR* / DEPOSITAR
          aliquota: DOIS_POR_CENTO / OITO_POR_CENTO*
          multaDoFgts: VINTE_POR_CENTO / QUARENTA_POR_CENTO* / SEM_MULTA
          tipoDoValorDaMulta: CALCULADA* / INFORMADA
          comporPrincipal: SIM* / NAO
        """
        if not fgts or not fgts.apurar:
            self.log("→ Fase 7: FGTS — apurar=False, pulando")
            return True
        self.log("→ Fase 7: FGTS")
        if not self._navegar_secao("FGTS", "fgts.jsf"):
            return False
        # tipoDeVerba: schema NORMAL → PAGAR; VERBA_RESCISORIA → DEPOSITAR
        tdv = "DEPOSITAR" if fgts.tipo_de_verba == "VERBA_RESCISORIA" else "PAGAR"
        self._click_radio("tipoDeVerba", tdv)
        self._click_radio("comporPrincipal", fgts.compor_principal)  # SIM/NAO

        # aliquota
        aliq_map = {"8": "OITO_POR_CENTO", "2": "DOIS_POR_CENTO", "INFORMADO": "INFORMADO"}
        self._click_radio("aliquota", aliq_map.get(fgts.aliquota, fgts.aliquota))
        self._fill_decimal("aliquotaInformada", fgts.aliquota_informada)

        # multaDoFgts
        mfg_map = {
            "MULTA_DE_40": "QUARENTA_POR_CENTO",
            "MULTA_DE_20": "VINTE_POR_CENTO",
            "SEM_MULTA": "SEM_MULTA",
        }
        self._click_radio("multaDoFgts", mfg_map.get(fgts.multa_do_fgts, fgts.multa_do_fgts))

        # tipoDoValorDaMulta
        tvm_map = {"CALCULADO": "CALCULADA", "INFORMADO": "INFORMADA"}
        self._click_radio("tipoDoValorDaMulta",
                          tvm_map.get(fgts.tipo_do_valor_da_multa, fgts.tipo_do_valor_da_multa))
        self._fill_decimal("multaInformada", fgts.multa_informada)

        # Checkboxes
        self._click_checkbox("multa", True)  # apurar multa rescisória (default true)
        self._click_checkbox("multaDoArtigo467", fgts.multa_do_artigo_467)

        # Select
        self._select_value("incidenciaDoFgts", fgts.incidencia_do_fgts)
        return self._clicar_salvar()

    # ────────────────────────────────────────────────────────────────────────
    # Helpers genéricos para listagens com botão "Novo"/"Incluir"
    # ────────────────────────────────────────────────────────────────────────

    def _clicar_novo(self) -> bool:
        """Click no botão Novo/Incluir da listagem atual.

        Confirmado via Chrome MCP live: histórico-salarial.jsf usa
        `formulario:incluir` value='Novo' type='button' com onclick=
        A4J.AJAX.Submit. dispatchEvent('click') via JS evaluate é o
        método mais confiável.

        Se form já está aberto (input nome/descricao + Salvar visíveis),
        retorna True imediatamente (idempotente).
        """
        # Pre-check: form já aberto?
        try:
            ja_aberto = self._page.evaluate(
                """() => {
                    const nome = document.querySelector('input[id$=":nome"], input[id$=":descricao"]');
                    const sv = document.querySelector('input[id="formulario:salvar"]');
                    return !!(nome && sv);
                }"""
            )
            if ja_aberto:
                self.log("  ✓ form já aberto (idempotente)")
                return True
        except Exception:
            pass

        # JS evaluate é a estratégia primária — busca por id e value/textContent
        try:
            clicou = self._page.evaluate(
                """() => {
                    // Tier 1: id$='incluir' com value='Novo'
                    let cands = [...document.querySelectorAll('input[id$=":incluir"], input[id$="incluir"]')]
                        .filter(e => /^novo$/i.test((e.value||'').trim()));
                    // Tier 2: id$='novo'
                    if (cands.length === 0) {
                        cands = [...document.querySelectorAll('input[id$=":novo"], input[id$="novo"]')];
                    }
                    // Tier 3: value='Novo' qualquer input
                    if (cands.length === 0) {
                        cands = [...document.querySelectorAll('input[type="button"], input[type="submit"]')]
                            .filter(e => /^novo$/i.test((e.value||'').trim()));
                    }
                    // Tier 4: value='Adicionar' / 'Incluir' (fallback)
                    if (cands.length === 0) {
                        cands = [...document.querySelectorAll('input[type="button"], input[type="submit"]')]
                            .filter(e => /^(adicionar|incluir)$/i.test((e.value||'').trim()));
                    }
                    // Tier 5: link <a> com texto 'Novo' MAS NÃO em menu lateral
                    // (menu lateral tem id formato 'formulario:j_id38:N:j_id41:M:j_id46')
                    if (cands.length === 0) {
                        cands = [...document.querySelectorAll('a')]
                            .filter(a => /^novo$/i.test((a.textContent||'').trim()))
                            .filter(a => !/j_id38/.test(a.id || ''));
                    }
                    if (cands.length === 0) return null;
                    const el = cands[0];
                    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    return el.id || el.value || el.textContent || 'ok';
                }"""
            )
            if clicou:
                self.log(f"  ✓ Novo clicado: {clicou}")
                self._aguardar_ajax(10000)
                # JSF/A4J render do form pode demorar — aguardar visível
                try:
                    self._page.wait_for_function(
                        "() => document.querySelector('input[id$=\":nome\"], input[id$=\":descricao\"], input[id=\"formulario:salvar\"]') != null",
                        timeout=15000,
                    )
                except Exception:
                    pass
                self._page.wait_for_timeout(1500)
                return True
        except Exception as e:
            self.log(f"  ⚠ _clicar_novo evaluate: {e}")
        return False

    # ────────────────────────────────────────────────────────────────────────
    # FASE 2 — Histórico Salarial
    # ────────────────────────────────────────────────────────────────────────

    def aplicar_historico_salarial(self, historico: list[HistoricoSalarialEntry]) -> bool:
        """Aplica entradas de Histórico Salarial em historico-salarial.jsf.

        Para cada entry:
          1. Click Novo → abre form
          2. Preenche nome, tipo_variacao, competências, tipo_valor, valor, fgts/inss
          3. Salva
        Ocorrências mensais (sub-tabela): aplicadas linha por linha após salvar.
        """
        if not historico:
            return True
        self.log(f"→ Fase 2: Histórico Salarial ({len(historico)} entry(es))")
        if not self._navegar_secao("Histórico Salarial", "historico-salarial.jsf"):
            return False
        for entry in historico:
            if not self._clicar_novo():
                self.log(f"  ⚠ Não conseguiu abrir 'Novo' para '{entry.nome}' — skip")
                # Importante: continuar SEM tentar preencher campos do form
                # (que não existe). Skip evita warnings em cascata.
                continue
            self._aguardar_ajax(3000)
            self._page.wait_for_timeout(800)
            self._fill_text("nome", entry.nome)
            # Parcela radio: schema FIXA/VARIAVEL → labels "Fixa" / "Variável"
            self._click_radio("tipoVariacaoDaParcela",
                              "Fixa" if entry.tipo_variacao_da_parcela == "FIXA" else "Variável")
            # Incidências (3 checkboxes na seção "Incidência" do form)
            self._click_checkbox("fgts", entry.fgts)
            # checkbox rotulado "Contribuição Social" — id no DOM é "inss"
            # ou "contribuicaoSocial"; tentar ambos
            self._click_checkbox("inss", entry.inss)
            self._click_checkbox("contribuicaoSocial", entry.inss)
            # checkbox "Proporcionalizar Contribuição Social" — só faz sentido
            # se inss=True; AJAX habilita ao marcar inss
            if entry.inss:
                self._aguardar_ajax(2000)
                self._click_checkbox("proporcionalizarContribuicaoSocial",
                                     entry.proporcionalizar_cs)
                self._click_checkbox("proporcionalizarCS",
                                     entry.proporcionalizar_cs)
            # Período / Tipo Valor (na seção Ocorrências do form)
            self._fill_date("competenciaInicialInputDate", entry.competencia_inicial)
            self._fill_date("competenciaFinalInputDate", entry.competencia_final)
            self._click_radio("tipoValor",
                              "Informado" if entry.tipo_valor == "INFORMADO" else "Calculado")
            self._fill_decimal("valorParaBaseDeCalculo", entry.valor_para_base_de_calculo)
            self._clicar_salvar()

            # Ocorrências mensais — abrir linha do histórico e aplicar
            if entry.ocorrencias:
                self._aplicar_ocorrencias_historico(entry)
            self._navegar_url_calculo("historico-salarial.jsf")
        return True

    def _aplicar_ocorrencias_historico(self, entry: HistoricoSalarialEntry) -> None:
        """Abre o link Ocorrências do histórico e aplica as linhas."""
        try:
            link_id = self._achar_link_acao_verba(entry.nome, "ocorrencias")
            if not link_id:
                return
            self._page.locator(f"a[id='{link_id}']").first.click(timeout=8000)
            self._aguardar_ajax(6000)
            for oc in entry.ocorrencias:
                cbx = self._page.locator(
                    f"input[type='checkbox'][id$='listagem:{oc.indice}:ativo']"
                ).first
                if cbx.count() > 0 and cbx.is_checked() != oc.ativo:
                    cbx.click(force=True)
                    self._aguardar_ajax(1500)
                if oc.valor is not None:
                    self._fill_decimal_by_id(f"listagem:{oc.indice}:valor", oc.valor)
                if oc.valor_incidencia_cs is not None:
                    self._fill_decimal_by_id(
                        f"listagem:{oc.indice}:valorIncidenciaCS", oc.valor_incidencia_cs
                    )
                if oc.valor_incidencia_fgts is not None:
                    self._fill_decimal_by_id(
                        f"listagem:{oc.indice}:valorIncidenciaFGTS", oc.valor_incidencia_fgts
                    )
            self._clicar_salvar()
        except Exception as e:
            self.log(f"  ⚠ ocorrências histórico '{entry.nome}': {e}")

    # ────────────────────────────────────────────────────────────────────────
    # FASE 3 — Faltas
    # ────────────────────────────────────────────────────────────────────────

    def aplicar_faltas(self, faltas: list[Falta]) -> bool:
        """Aplica faltas em faltas.jsf (Novo → form → Salvar por entrada)."""
        if not faltas:
            return True
        self.log(f"→ Fase 3: Faltas ({len(faltas)})")
        if not self._navegar_secao("Faltas", "faltas.jsf"):
            return False
        for f in faltas:
            if not self._clicar_novo():
                continue
            self._fill_date("dataInicio", f.data_inicio)
            self._fill_date("dataInicioInputDate", f.data_inicio)
            self._fill_date("dataFim", f.data_fim)
            self._fill_date("dataFimInputDate", f.data_fim)
            self._click_checkbox("justificada", f.justificada)
            self._click_checkbox("descontarRemuneracao", f.descontar_remuneracao)
            self._click_checkbox("descontarDsr", f.descontar_dsr)
            self._clicar_salvar()
            self._navegar_url_calculo("faltas.jsf")
        return True

    # ────────────────────────────────────────────────────────────────────────
    # FASE 4 — Férias
    # ────────────────────────────────────────────────────────────────────────

    def aplicar_ferias(self, ferias: list[FeriasEntry]) -> bool:
        """Aplica férias gozadas em ferias.jsf."""
        if not ferias:
            return True
        self.log(f"→ Fase 4: Férias ({len(ferias)} entrada(s))")
        if not self._navegar_secao("Férias", "ferias.jsf"):
            return False
        for fe in ferias:
            if not self._clicar_novo():
                continue
            self._fill_date("periodoAquisitivoInicioInputDate", fe.periodo_aquisitivo_inicio)
            self._fill_date("periodoAquisitivoFimInputDate", fe.periodo_aquisitivo_fim)
            self._fill_date("dataInicioGozoInputDate", fe.data_inicio_gozo)
            self._fill_date("dataFimGozoInputDate", fe.data_fim_gozo)
            self._click_checkbox("abonoPecuniario", fe.abono_pecuniario)
            self._click_checkbox("dobra", fe.dobra)
            self._clicar_salvar()
            self._navegar_url_calculo("ferias.jsf")
        return True

    # ────────────────────────────────────────────────────────────────────────
    # FASE 6 — Cartão de Ponto
    # ────────────────────────────────────────────────────────────────────────

    def aplicar_cartao_de_ponto(self, cp: CartaoDePonto) -> bool:
        """Aplica Cartão de Ponto (apuracao-cartaodeponto.jsf) — DOM real.

        Pulado silenciosamente se apurar=False E programação semanal vazia
        (caso típico: sentença não envolve cartão de ponto).
        """
        if not cp:
            return True
        # Skip se nada explícito a aplicar
        tem_dados = (
            cp.apurar
            or cp.tipo_apuracao_horas_extras
            or any([cp.valor_jornada_segunda, cp.valor_jornada_terca,
                    cp.valor_jornada_quarta, cp.valor_jornada_quinta,
                    cp.valor_jornada_sexta, cp.valor_jornada_sabado,
                    cp.valor_jornada_dom])
            or cp.competencia_inicial
        )
        if not tem_dados:
            return True
        self.log("→ Fase 6: Cartão de Ponto")
        if not self._navegar_secao("Cartão de Ponto", "../cartaodeponto/apuracao-cartaodeponto.jsf"):
            self._navegar_url_calculo("cartaodeponto/apuracao-cartaodeponto.jsf")

        # Tipo de apuração HE (radio com 7 opções)
        if cp.tipo_apuracao_horas_extras:
            self._click_radio("tipoApuracaoHorasExtras", cp.tipo_apuracao_horas_extras)

        # Competência
        if cp.competencia_inicial:
            self._fill_date("competenciaInicialInputDate", cp.competencia_inicial)
        if cp.competencia_final:
            self._fill_date("competenciaFinalInputDate", cp.competencia_final)

        # Jornadas por dia (HH:MM como total do dia)
        if cp.valor_jornada_segunda:
            self._fill_text("valorJornadaSegunda", cp.valor_jornada_segunda)
        if cp.valor_jornada_terca:
            self._fill_text("valorJornadaTerca", cp.valor_jornada_terca)
        if cp.valor_jornada_quarta:
            self._fill_text("valorJornadaQuarta", cp.valor_jornada_quarta)
        if cp.valor_jornada_quinta:
            self._fill_text("valorJornadaQuinta", cp.valor_jornada_quinta)
        if cp.valor_jornada_sexta:
            self._fill_text("valorJornadaSexta", cp.valor_jornada_sexta)
        if cp.valor_jornada_sabado:
            self._fill_text("valorJornadaDiariaSabado", cp.valor_jornada_sabado)
        if cp.valor_jornada_dom:
            self._fill_text("valorJornadaDiariaDom", cp.valor_jornada_dom)

        # Totais
        if cp.qt_jornada_semanal:
            self._fill_text("qtJornadaSemanal", cp.qt_jornada_semanal)
        if cp.qt_jornada_mensal:
            self._fill_text("qtJornadaMensal", cp.qt_jornada_mensal)

        # Compat: programação semanal v2 (mapear dia → valor_jornada)
        for dia_cfg in cp.programacao_semanal:
            if dia_cfg.valor_jornada:
                map_dia = {
                    "SEG": "valorJornadaSegunda", "TER": "valorJornadaTerca",
                    "QUA": "valorJornadaQuarta", "QUI": "valorJornadaQuinta",
                    "SEX": "valorJornadaSexta", "SAB": "valorJornadaDiariaSabado",
                    "DOM": "valorJornadaDiariaDom",
                }
                campo = map_dia.get(dia_cfg.dia)
                if campo:
                    self._fill_text(campo, dia_cfg.valor_jornada)
        return self._clicar_salvar()

    # ────────────────────────────────────────────────────────────────────────
    # FASE 8 — Contribuição Social (INSS)
    # ────────────────────────────────────────────────────────────────────────

    def aplicar_inss(self, inss: ContribuicaoSocial) -> bool:
        """Aplica configuração de INSS (Contribuição Social) — schema v3 expandido."""
        if not inss or not inss.apurar:
            self.log("→ Fase 8: INSS — apurar=False, pulando")
            return True
        self.log("→ Fase 8: INSS")
        if not self._navegar_secao("Contribuição Social", "inss/inss.jsf"):
            return False

        # ── Checkboxes (DOM-confirmados) ──
        # apurarInssSeguradoDevido (true*) — schema apurar_segurado_salarios_devidos
        self._click_checkbox("apurarInssSeguradoDevido", inss.apurar_segurado_salarios_devidos)
        # apurarSalariosPagos (false*)
        self._click_checkbox("apurarSalariosPagos", inss.apurar_sobre_salarios_pagos)
        # cobrarDoReclamanteDevido (true*) — schema cobrar_do_reclamante
        self._click_checkbox("cobrarDoReclamanteDevido", inss.cobrar_do_reclamante)
        # corrigirDescontoReclamante (false*) — sem mapping direto, usar com_correcao_trabalhista
        self._click_checkbox("corrigirDescontoReclamante", inss.com_correcao_trabalhista)

        # ── Radios (DOM-confirmados) ──
        # aliquotaEmpregado: SEGURADO_EMPREGADO* / EMPREGADO_DOMESTICO / FIXA
        seg_map = {
            "EMPREGADO": "SEGURADO_EMPREGADO",
            "DOMESTICO": "EMPREGADO_DOMESTICO",
            "FIXA": "FIXA",
        }
        if inss.tipo_aliquota_segurado:
            self._click_radio("aliquotaEmpregado",
                              seg_map.get(inss.tipo_aliquota_segurado, inss.tipo_aliquota_segurado))
        # aliquotaEmpregador: POR_ATIVIDADE_ECONOMICA / POR_PERIODO / FIXA*
        emp_map = {
            "ATIVIDADE_ECONOMICA": "POR_ATIVIDADE_ECONOMICA",
            "PERIODO": "POR_PERIODO",
            "FIXA": "FIXA",
        }
        if inss.tipo_aliquota_empregador:
            self._click_radio("aliquotaEmpregador",
                              emp_map.get(inss.tipo_aliquota_empregador, inss.tipo_aliquota_empregador))
            self._aguardar_ajax(1500)

        # ── Atividade econômica (CNAE) — quando ATIVIDADE_ECONOMICA ──
        if inss.atividade_economica:
            self._fill_text("buscaAtividadeEconomica", inss.atividade_economica)
            self._aguardar_ajax(2000)

        # ── Alíquotas (quando FIXA) ──
        if inss.aliquota_empresa is not None:
            self._fill_decimal("aliquotaEmpresa", inss.aliquota_empresa)
        if inss.aliquota_sat is not None:
            self._fill_decimal("aliquotaSAT", inss.aliquota_sat)
            self._fill_decimal("aliquotaRAT", inss.aliquota_sat)
        if inss.aliquota_terceiros is not None:
            self._fill_decimal("aliquotaTerceiros", inss.aliquota_terceiros)
        if inss.fap is not None:
            self._fill_decimal("fap", inss.fap)

        return self._clicar_salvar()

    # ────────────────────────────────────────────────────────────────────────
    # FASE 9 — Imposto de Renda
    # ────────────────────────────────────────────────────────────────────────

    def aplicar_irpf(self, ir: ImpostoRenda) -> bool:
        """Aplica IRPF (irpf.jsf) — schema v3 expandido conforme tela real."""
        if not ir or not ir.apurar:
            self.log("→ Fase 9: IRPF — apurar=False, pulando")
            return True
        self.log("→ Fase 9: IRPF")
        if not self._navegar_secao("Imposto de Renda", "irpf.jsf"):
            return False
        # ── Checkboxes (DOM IDs confirmados v2.15.1) ──
        self._click_checkbox("apurarImpostoRenda", ir.apurar)
        self._click_checkbox("regimeDeCaixa", ir.aplicar_regime_de_caixa)
        self._click_checkbox("aposentadoMaiorQue65Anos", ir.aposentado_maior_65)
        self._click_checkbox("cobrarDoReclamado", ir.cobrar_do_reclamado)
        self._click_checkbox("incidirSobreJurosDeMora", ir.incidir_sobre_juros_de_mora)
        self._click_checkbox("considerarTributacaoEmSeparado", ir.tributacao_em_separado)
        self._click_checkbox("considerarTributacaoExclusiva", ir.tributacao_exclusiva)
        # Deduções (4 checkboxes — DOM IDs longos confirmados)
        self._click_checkbox("deduzirContribuicaoSocialDevidaPeloReclamante",
                             ir.deduzir_contribuicao_social)
        self._click_checkbox("deduzirHonorariosDevidosPeloReclamante",
                             ir.deduzir_honorarios_reclamante)
        self._click_checkbox("deduzirPensaoAlimenticia", ir.deduzir_pensao_alimenticia)
        self._click_checkbox("deduzirPrevidenciaPrivada", ir.deduzir_previdencia_privada)
        # Dependentes (checkbox + texto)
        if ir.quantidade_dependentes > 0:
            self._click_checkbox("possuiDependentes", True)
            self._aguardar_ajax(1500)
            self._fill_text("quantidadeDependentes", str(ir.quantidade_dependentes))
        # Compat legado (regime_tributacao + meses + valores)
        if ir.regime_tributacao == "RRA":
            self._click_checkbox("tributacaoEmSeparado", True)
        if ir.meses_tributaveis is not None:
            self._fill_text("mesesTributaveis", str(ir.meses_tributaveis))
        if ir.deducoes is not None:
            self._fill_decimal("deducoes", ir.deducoes)
        if ir.pensao_alimenticia is not None:
            self._click_checkbox("pensaoAlimenticia", True)
            self._fill_decimal("valorPensao", ir.pensao_alimenticia)
            self._fill_decimal("valorDaPensao", ir.pensao_alimenticia)
        return self._clicar_salvar()

    # ────────────────────────────────────────────────────────────────────────
    # FASE 10 — Honorários
    # ────────────────────────────────────────────────────────────────────────

    def aplicar_honorarios(self, honorarios: list[Honorario]) -> bool:
        """Aplica honorários (lista de N registros)."""
        if not honorarios:
            return True
        self.log(f"→ Fase 10: Honorários ({len(honorarios)})")
        if not self._navegar_secao("Honorários", "honorarios.jsf"):
            return False
        for h in honorarios:
            if not self._clicar_novo():
                continue
            self._fill_text("descricao", h.descricao)
            tp_map = {
                "ASSISTENCIAIS": "Assistenciais",
                "ADVOCATICIOS": "Advocatícios",
                "PERICIAIS": "Periciais",
                "SUCUMBENCIA": "Sucumbência",
            }
            self._select_value("tpHonorario", tp_map.get(h.tp_honorario, h.tp_honorario))
            self._click_radio("tipoDeDevedor",
                              "Reclamante" if h.tipo_de_devedor == "RECLAMANTE" else "Reclamado")
            self._click_radio("tipoValor",
                              "Calculado" if h.tipo_valor == "CALCULADO" else "Informado")
            if h.aliquota is not None:
                self._fill_decimal("aliquota", h.aliquota)
            base_map = {
                "BRUTO_LIQUIDO": "Bruto Líquido",
                "BRUTO": "Bruto",
                "LIQUIDO": "Líquido",
                "VALOR_INFORMADO": "Valor Informado",
            }
            self._select_value("baseParaApuracao",
                               base_map.get(h.base_para_apuracao, h.base_para_apuracao))
            self._fill_text("nomeCredor", h.nome_credor)
            self._click_radio("tipoDocumentoFiscalCredor", h.tipo_documento_fiscal_credor)
            self._fill_text("numeroDocumentoFiscalCredor", h.numero_documento_fiscal_credor)
            self._click_checkbox("apurarIRRF", h.apurar_irrf)
            self._click_checkbox("incidirSobreJuros", h.incidir_sobre_juros)
            self._click_checkbox("aplicarJuros", h.aplicar_juros)
            self._clicar_salvar()
            self._navegar_url_calculo("honorarios.jsf")
        return True

    # ────────────────────────────────────────────────────────────────────────
    # FASE 11 — Custas Judiciais
    # ────────────────────────────────────────────────────────────────────────

    def aplicar_custas(self, custas: CustasJudiciais) -> bool:
        """Aplica configuração de Custas Judiciais — schema v3 expandido com
        3 radios separados (Reclamado-Conhecimento, Reclamado-Liquidação,
        Reclamante-Conhecimento) refletindo a tela real do PJE-Calc 2.15.1.
        """
        if not custas:
            return True
        self.log("→ Fase 11: Custas Judiciais")
        if not self._navegar_secao("Custas Judiciais", "custas-judiciais.jsf"):
            return False

        # Base de cálculo
        if custas.base_para_custas:
            self._select_value("baseParaCustasCalculadas", custas.base_para_custas)
            self._select_value("baseCustas", custas.base_para_custas)

        # ── Radios DOM-confirmados (IDs longos do PJE-Calc) ──
        # tipoDeCustasDeConhecimentoDoReclamado:
        #   NAO_SE_APLICA / CALCULADA_2_POR_CENTO* / INFORMADA
        self._click_radio("tipoDeCustasDeConhecimentoDoReclamado",
                          custas.reclamado_conhecimento)
        if custas.reclamado_conhecimento == "INFORMADA":
            self._aguardar_ajax(1500)
            if custas.valor_reclamado_conhecimento is not None:
                self._fill_decimal("valorReclamadoConhecimento", custas.valor_reclamado_conhecimento)
            if custas.vencimento_reclamado_conhecimento:
                self._fill_date("vencimentoReclamadoConhecimento", custas.vencimento_reclamado_conhecimento)

        # tipoDeCustasDeLiquidacao:
        #   NAO_SE_APLICA* / CALCULADA_MEIO_POR_CENTO / INFORMADA
        self._click_radio("tipoDeCustasDeLiquidacao", custas.reclamado_liquidacao)
        if custas.reclamado_liquidacao == "INFORMADA":
            self._aguardar_ajax(1500)
            if custas.valor_reclamado_liquidacao is not None:
                self._fill_decimal("valorReclamadoLiquidacao", custas.valor_reclamado_liquidacao)
            if custas.vencimento_reclamado_liquidacao:
                self._fill_date("vencimentoReclamadoLiquidacao", custas.vencimento_reclamado_liquidacao)

        # tipoDeCustasDeConhecimentoDoReclamante:
        #   NAO_SE_APLICA* / CALCULADA_2_POR_CENTO / INFORMADA
        self._click_radio("tipoDeCustasDeConhecimentoDoReclamante",
                          custas.reclamante_conhecimento)
        if custas.reclamante_conhecimento == "INFORMADA":
            self._aguardar_ajax(1500)
            if custas.valor_reclamante_conhecimento is not None:
                self._fill_decimal("valorReclamanteConhecimento", custas.valor_reclamante_conhecimento)
            if custas.vencimento_reclamante_conhecimento:
                self._fill_date("vencimentoReclamanteConhecimento", custas.vencimento_reclamante_conhecimento)

        # Percentual (entre 0 e 100, não fração)
        if custas.percentual is not None:
            self._fill_decimal("percentualCustas", custas.percentual)
            self._fill_decimal("aliquota", custas.percentual)

        # Periciais (honorários)
        if custas.valor_periciais is not None:
            self._fill_decimal("valorPericiais", custas.valor_periciais)
            self._fill_decimal("honorariosPericiais", custas.valor_periciais)

        # ── Custas Fixas (DOM real: campos texto qtde* + dataVencimentoCustasFixasInputDate) ──
        # NOTA: schema atual usa booleans (checkboxes), DOM usa quantidades (textos).
        # Schema bool=True → quantidade=1; bool=False → quantidade vazia.
        if custas.custas_fixas_vencimento:
            self._fill_date("dataVencimentoCustasFixasInputDate", custas.custas_fixas_vencimento)
        if custas.custas_fixas_atos_oj_urbana:
            self._fill_text("qtdeAtosUrbanos", "1")
        if custas.custas_fixas_atos_oj_rural:
            self._fill_text("qtdeAtosRurais", "1")
        if custas.custas_fixas_agravo_instrumento:
            self._fill_text("qtdeAgravosDeInstrumento", "1")
        if custas.custas_fixas_agravo_peticao:
            self._fill_text("qtdeAgravosDePeticao", "1")
        if custas.custas_fixas_impugnacao_sentenca:
            self._fill_text("qtdeImpugnacaoSentenca", "1")
        if custas.custas_fixas_embargos_arrematacao:
            self._fill_text("qtdeEmbargosArrematacao", "1")
        if custas.custas_fixas_embargos_execucao:
            self._fill_text("qtdeEmbargosExecucao", "1")
        if custas.custas_fixas_embargos_terceiros:
            self._fill_text("qtdeEmbargosTerceiros", "1")
        if custas.custas_fixas_recurso_revista:
            self._fill_text("qtdeRecursoRevista", "1")

        # ── Autos 5% (lista) ──
        for auto in custas.autos_5pct:
            if auto.tipo_de_auto:
                self._select_value("tipoDeAuto", auto.tipo_de_auto)
                self._fill_date("vencimentoAuto", auto.vencimento)
                self._fill_decimal("valorBemAuto", auto.valor_do_bem)
                # Click "+" para adicionar (id típico: btnAdicionarAuto / btnIncluirAuto)
                self._page.evaluate(
                    """() => {
                        const b = [...document.querySelectorAll('input[type=image], input[type=submit], input[type=button]')]
                            .find(e => /(adicionar|incluir).*auto/i.test((e.title||'') + (e.alt||'') + (e.value||'')));
                        if (b) b.click();
                    }"""
                )
                self._aguardar_ajax(2000)

        # ── Armazenamento 0,1% (lista) ──
        for arm in custas.armazenamento_0_1pct:
            if arm.inicio:
                self._fill_date("inicioArmazenamento", arm.inicio)
                self._fill_date("terminoArmazenamento", arm.termino)
                self._fill_decimal("valorBemArmazenamento", arm.valor_do_bem)
                self._page.evaluate(
                    """() => {
                        const b = [...document.querySelectorAll('input[type=image], input[type=submit], input[type=button]')]
                            .find(e => /(adicionar|incluir).*armazen/i.test((e.title||'') + (e.alt||'') + (e.value||'')));
                        if (b) b.click();
                    }"""
                )
                self._aguardar_ajax(2000)

        ok = self._clicar_salvar()

        # ── Tab "Custas Recolhidas" ──
        if (custas.recolhidas_reclamado_valor or custas.recolhidas_reclamante_valor):
            try:
                self._page.evaluate(
                    """() => {
                        const tab = [...document.querySelectorAll('.rich-tab-header, td')]
                            .find(t => /custas\\s*recolhidas/i.test((t.textContent||'').trim()));
                        if (tab) tab.click();
                    }"""
                )
                self._aguardar_ajax(3000)
                if custas.recolhidas_reclamado_valor:
                    self._fill_date("vencimentoRecolhidoReclamado", custas.recolhidas_reclamado_vencimento)
                    self._fill_decimal("valorRecolhidoReclamado", custas.recolhidas_reclamado_valor)
                if custas.recolhidas_reclamante_valor:
                    self._fill_date("vencimentoRecolhidoReclamante", custas.recolhidas_reclamante_vencimento)
                    self._fill_decimal("valorRecolhidoReclamante", custas.recolhidas_reclamante_valor)
                self._clicar_salvar()
            except Exception as e:
                self.log(f"  ⚠ Custas Recolhidas: {e}")

        return ok

    # ────────────────────────────────────────────────────────────────────────
    # FASE 12 — Correção, Juros e Multa
    # ────────────────────────────────────────────────────────────────────────

    # DOM values reais (confirmados via knowledge/pjecalc_dom_audit_trt7_2026-05-01_addendum.md)
    _IDX_CORRECAO_VALUE = {  # schema v3 → DOM option value
        "TUACDT": "TUACDT",
        "DEVEDOR_FAZENDA_PUBLICA": "TABELA_DEVEDOR_FAZENDA",
        "REPETICAO_INDEBITO": "TABELA_INDEBITO_TRIBUTARIO",
        "TJT_MENSAL": "TABELA_UNICA_JT_MENSAL",
        "TJT_DIARIA": "TABELA_UNICA_JT_DIARIO",
        "TR": "TR",
        "IGP_M": "IGPM",
        "INPC": "INPC",
        "IPC": "IPC",
        "IPCA": "IPCA",
        "IPCAE": "IPCAE",
        "IPCAE_TR": "IPCAETR",
        "SELIC_RECEITA": "SELIC",
        "SELIC_SIMPLES": "SELIC_FAZENDA",
        "SELIC_COMPOSTA": "SELIC_BACEN",
        "SEM_CORRECAO": "SEM_CORRECAO",
    }
    _TAXA_JUROS_VALUE = {  # schema v3 → DOM option value
        "JUROS_PADRAO": "JUROS_PADRAO",
        "CADERNETA_POUPANCA": "JUROS_POUPANCA",
        "FAZENDA_PUBLICA": "FAZENDA_PUBLICA",
        "SIMPLES_0_5_AM": "JUROS_MEIO_PORCENTO",
        "SIMPLES_1_AM": "JUROS_UM_PORCENTO",
        "SIMPLES_0_0333333_AD": "JUROS_ZERO_TRINTA_TRES",
        "SELIC_RECEITA": "SELIC",
        "SELIC_SIMPLES": "SELIC_FAZENDA",
        "SELIC_COMPOSTA": "SELIC_BACEN",
        "TRD_SIMPLES": "TRD_SIMPLES",
        "TRD_COMPOSTOS": "TRD_COMPOSTOS",
        "TAXA_LEGAL": "TAXA_LEGAL",
        "SEM_JUROS": "SEM_JUROS",
    }

    def aplicar_correcao_juros(self, cj: CorrecaoJuros) -> bool:
        """Aplica Correção/Juros (parametros-atualizacao.jsf) — schema v3 expandido."""
        if not cj:
            return True
        self.log("→ Fase 12: Correção/Juros")
        if not self._navegar_secao("Correção, Juros e Multa", "parametros-atualizacao/parametros-atualizacao.jsf"):
            return False

        # ── Correção Monetária ──
        val_idx = self._IDX_CORRECAO_VALUE.get(cj.indice_correcao, cj.indice_correcao)
        self._select_value("indiceTrabalhista", val_idx)
        self._click_checkbox("combinarOutroIndice", cj.combinar_com_outro_indice)
        self._click_checkbox("ignorarTaxaNegativa", cj.ignorar_taxa_negativa)

        # ── Juros de Mora ──
        # DOM: aplicarJurosFasePreJudicial (true*)
        self._click_checkbox("aplicarJurosFasePreJudicial", cj.aplicar_juros_pre_judicial)
        val_taxa = self._TAXA_JUROS_VALUE.get(cj.taxa_juros, cj.taxa_juros)
        # DOM: select 'juros' (não taxaJuros nem tabelaJuros)
        self._select_value("juros", val_taxa)

        # Combinar Outro Juros (DOM: combinarOutroJuros + select 'outroJuros')
        if cj.combinar_outra_tabela_juros or cj.tabelas_juros_adicionais:
            self._click_checkbox("combinarOutroJuros", True)
            self._aguardar_ajax(2000)
            for tab in cj.tabelas_juros_adicionais:
                val = self._TAXA_JUROS_VALUE.get(tab.tabela, tab.tabela)
                self._select_value("outroJuros", val)
                if tab.a_partir_de:
                    self._fill_date("apartirDeOutroJurosInputDate", tab.a_partir_de)
                self._aguardar_ajax(2000)

        # Base de Juros das Verbas (DOM: baseDeJurosDasVerbas, default VERBAS)
        base_map = {"VERBA": "VERBAS", "PRINCIPAL": "VERBA_INSS", "BRUTO": "VERBA_INSS_PP"}
        self._select_value("baseDeJurosDasVerbas", base_map.get(cj.base_juros, cj.base_juros))

        # Súmula 439
        if cj.sumula_439_juros_desde_ajuizamento:
            self._click_checkbox("jurosDesdeAjuizamento", True)
            self._click_checkbox("sumula439", True)

        return self._clicar_salvar()

    # ────────────────────────────────────────────────────────────────────────
    # LIQUIDAR + EXPORTAR
    # ────────────────────────────────────────────────────────────────────────

    def liquidar_e_exportar(self) -> Optional[bytes]:
        """Click Liquidar → aguardar → Exportar → captura .pjc bytes.

        URLs e IDs confirmados via Chrome MCP live (PJE-Calc TRT7 v2.15.1):
          - Liquidar: navega para liquidacao.jsf via menu lateral
            (li#li_operacoes_liquidar). Dentro: input[id='formulario:liquidar']
            value='Liquidar' type='button'.
          - Exportar: navega para exportacao.jsf (li#li_operacoes_exportar).
            Dentro: input[id='formulario:exportar'].
        """
        self.log("→ Liquidar e Exportar")
        try:
            # Etapa 1 — Click 'Liquidar' menu lateral (vai para liquidacao.jsf)
            if not self._clicar_menu_lateral("Liquidar"):
                self.log("  ⚠ menu Liquidar falhou — fallback URL direta")
                self._navegar_url_calculo("liquidacao.jsf")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(2000)

            # Etapa 2 — Click confirmação 'formulario:liquidar' (via dispatchEvent)
            clicou = self._page.evaluate(
                """() => {
                    const b = document.querySelector('input[id="formulario:liquidar"]');
                    if (!b) return null;
                    b.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    return 'ok';
                }"""
            )
            if not clicou:
                self.log("  ⚠ botão 'formulario:liquidar' não encontrado")
                return None
            self.log("  → Liquidação disparada — aguardando processamento")
            self._aguardar_ajax(120000)  # pode demorar minutos
            self._page.wait_for_timeout(5000)

            # Etapa 3 — Click 'Exportar' menu lateral (vai para exportacao.jsf)
            if not self._clicar_menu_lateral("Exportar"):
                self.log("  ⚠ menu Exportar falhou — fallback URL direta")
                self._navegar_url_calculo("exportacao.jsf")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(1500)

            # Etapa 4 — Capturar download .pjc via 'formulario:exportar'
            with self._page.expect_download(timeout=120000) as dl_info:
                self._page.evaluate(
                    """() => {
                        const b = document.querySelector('input[id="formulario:exportar"]');
                        if (b) b.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    }"""
                )
            download = dl_info.value
            path = download.path()
            if path:
                with open(path, "rb") as f:
                    pjc = f.read()
                self.log(f"  ✓ .PJC capturado ({len(pjc)} bytes) — sufixo: {download.suggested_filename}")
                return pjc
            return None
        except Exception as e:
            self.log(f"  ⚠ liquidar_e_exportar: {e}")
            return None

    # ────────────────────────────────────────────────────────────────────────
    # ORQUESTRADOR
    # ────────────────────────────────────────────────────────────────────────

    def aplicar(self, previa) -> dict:
        """Aplica a prévia v3 inteira na ordem do manual oficial PJE-Calc.

        Args:
          previa: PreviaCalculo (Pydantic v3) ou dict com chaves equivalentes

        Returns:
          dict com {sucesso, fase_falhou, pjc_bytes, mensagens}
        """
        # Permite passar dict (preview/migrate) ou model
        if hasattr(previa, "model_dump"):
            d = previa
        else:
            from infrastructure.pjecalc_pages import PreviaCalculo
            d = PreviaCalculo(**previa) if isinstance(previa, dict) else previa

        relatorio = {"sucesso": True, "fase_falhou": None, "pjc_bytes": None, "mensagens": []}

        # Pipeline na MESMA ORDEM da barra lateral do PJE-Calc:
        # Dados → Faltas → Férias → Hist.Salarial → Verbas → Cartão Ponto →
        # FGTS → Contribuição Social → Imposto Renda → Honorários → Custas →
        # Correção/Juros. Itens da UI sem schema próprio (Salário-família,
        # Seguro-desemprego, Previdência Privada, Pensão Alimentícia, Multas e
        # Indenizações) são pulados — Multas/Indenizações entram como verba.
        # ORDEM REORDENADA: Verbas (Lançamento Expresso) reseta a conversation
        # Seam tornando inválidas todas as fases subsequentes. Solução: aplicar
        # Verbas POR ÚLTIMO (antes do Liquidar). Demais fases mantêm conv=6
        # estável e podem ser aplicadas sequencialmente.
        fases = [
            ("Dados do Processo", lambda: self.aplicar_dados_processo(d.processo)),
            ("Faltas", lambda: self.aplicar_faltas(d.faltas)),
            ("Férias", lambda: self.aplicar_ferias(d.ferias)),
            ("Histórico Salarial", lambda: self.aplicar_historico_salarial(d.historico_salarial)),
            ("Cartão de Ponto", lambda: self.aplicar_cartao_de_ponto(d.cartao_de_ponto)),
            ("FGTS", lambda: self.aplicar_fgts(d.fgts)),
            ("Contribuição Social", lambda: self.aplicar_inss(d.contribuicao_social)),
            ("Imposto de Renda", lambda: self.aplicar_irpf(d.imposto_renda)),
            ("Honorários", lambda: self.aplicar_honorarios(d.honorarios)),
            ("Custas Judiciais", lambda: self.aplicar_custas(d.custas)),
            ("Correção, Juros e Multa", lambda: self.aplicar_correcao_juros(d.correcao_juros)),
            # Verbas por ÚLTIMO — Expresso save abandona conv original
            ("Verbas", lambda: self.aplicar_verbas(d.verbas)),
        ]
        for nome, func in fases:
            try:
                ok = func()
                if not ok:
                    relatorio["sucesso"] = False
                    relatorio["fase_falhou"] = nome
                    relatorio["mensagens"].append(f"Falha em {nome}")
                    return relatorio
            except Exception as e:
                relatorio["sucesso"] = False
                relatorio["fase_falhou"] = nome
                relatorio["mensagens"].append(f"Exceção em {nome}: {e}")
                return relatorio

        # Liquidar + Exportar
        pjc = self.liquidar_e_exportar()
        relatorio["pjc_bytes"] = pjc
        return relatorio
