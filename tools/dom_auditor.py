#!/usr/bin/env python3
"""
DOM Auditor — Mapeamento integral de elementos interativos do PJE-Calc Cidadao.

Navega por TODAS as paginas/abas do PJE-Calc e extrai cada campo, botao,
checkbox, select, radio, link de navegacao, etc.

Gera 3 arquivos de saida:
  1. knowledge/pjecalc_dom_map.json       — JSON completo com todos os elementos
  2. knowledge/pjecalc_dom_reference.md    — Documento legivel com tabelas
  3. knowledge/pjecalc_selectors.py        — Constantes Python com seletores

Uso:
  python tools/dom_auditor.py --url http://localhost:9257/pjecalc
  python tools/dom_auditor.py --url http://localhost:9257/pjecalc --headless
  python tools/dom_auditor.py --help

Requisitos:
  pip install playwright
  playwright install firefox
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# JS snippets injetados no browser
# ---------------------------------------------------------------------------

JS_EXTRACT_ELEMENTS = """() => {
    const results = [];

    // Helper: find associated label
    function findLabel(el) {
        if (el.id) {
            const lbl = document.querySelector(`label[for='${el.id}']`);
            if (lbl) return lbl.textContent.trim();
        }
        // Walk up to find closest label or text node
        let parent = el.parentElement;
        for (let i = 0; i < 3 && parent; i++) {
            const lbl = parent.querySelector('label');
            if (lbl && lbl !== el) return lbl.textContent.trim();
            // Check for preceding text in a <td> (common in JSF tables)
            if (parent.tagName === 'TD') {
                const prev = parent.previousElementSibling;
                if (prev) return prev.textContent.trim().replace(/:$/, '');
            }
            parent = parent.parentElement;
        }
        return '';
    }

    // Helper: get recommended selector suffix
    function selectorSuffix(id) {
        if (!id) return '';
        const parts = id.split(':');
        return parts[parts.length - 1];
    }

    // Helper: bounding rect visibility
    function isVisible(el) {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    // Helper: closest container
    function closestContainer(el) {
        const container = el.closest('fieldset, div[id], td[id], tr[id], form[id]');
        if (container && container.id) return container.tagName.toLowerCase() + '#' + container.id;
        if (container) return container.tagName.toLowerCase();
        return '';
    }

    // 1. INPUT elements
    document.querySelectorAll('input').forEach(el => {
        const tipo = el.type || 'text';
        const sufixo = selectorSuffix(el.id);
        const entry = {
            tipo: tipo === 'checkbox' ? 'checkbox' :
                  tipo === 'radio' ? 'radio' :
                  tipo === 'hidden' ? 'hidden' :
                  tipo === 'button' || tipo === 'submit' ? 'button' : 'input',
            id: el.id,
            name: el.name || '',
            label: findLabel(el),
            tipo_input: tipo,
            obrigatorio: el.required || el.getAttribute('aria-required') === 'true' ||
                         el.classList.contains('obrigatorio'),
            valor_atual: tipo === 'checkbox' || tipo === 'radio' ? String(el.checked) : (el.value || ''),
            maxlength: el.maxLength > 0 && el.maxLength < 100000 ? el.maxLength : null,
            css_classes: [...el.classList],
            visivel: isVisible(el),
            dentro_de: closestContainer(el),
            sufixo: sufixo,
            seletor_recomendado: sufixo ?
                (tipo === 'checkbox' ? `input[type='checkbox'][id$='${sufixo}']` :
                 tipo === 'radio' ? `input[type='radio'][id$='${sufixo}']` :
                 tipo === 'button' || tipo === 'submit' ? `input[id$='${sufixo}']` :
                 `input:not([type='hidden'])[id$='${sufixo}']`) : '',
            value_attr: el.getAttribute('value') || '',
        };

        // For radio buttons: include value option
        if (tipo === 'radio') {
            entry.radio_value = el.value;
            entry.radio_checked = el.checked;
            entry.radio_name = el.name;
        }

        // For checkboxes
        if (tipo === 'checkbox') {
            entry.checked = el.checked;
        }

        // For buttons
        if (tipo === 'button' || tipo === 'submit') {
            entry.texto = el.value || '';
            entry.onclick = el.getAttribute('onclick') || '';
        }

        results.push(entry);
    });

    // 2. SELECT elements
    document.querySelectorAll('select').forEach(el => {
        const sufixo = selectorSuffix(el.id);
        const opcoes = [];
        el.querySelectorAll('option').forEach(opt => {
            opcoes.push({value: opt.value, texto: opt.textContent.trim()});
        });
        results.push({
            tipo: 'select',
            id: el.id,
            name: el.name || '',
            label: findLabel(el),
            opcoes: opcoes,
            valor_selecionado: el.value,
            css_classes: [...el.classList],
            visivel: isVisible(el),
            dentro_de: closestContainer(el),
            sufixo: sufixo,
            seletor_recomendado: sufixo ? `select[id$='${sufixo}']` : '',
        });
    });

    // 3. TEXTAREA elements
    document.querySelectorAll('textarea').forEach(el => {
        const sufixo = selectorSuffix(el.id);
        results.push({
            tipo: 'textarea',
            id: el.id,
            name: el.name || '',
            label: findLabel(el),
            valor_atual: el.value || '',
            css_classes: [...el.classList],
            visivel: isVisible(el),
            dentro_de: closestContainer(el),
            sufixo: sufixo,
            seletor_recomendado: sufixo ? `textarea[id$='${sufixo}']` : '',
        });
    });

    // 4. LINK elements (a tags with onclick or href)
    document.querySelectorAll('a[onclick], a[href]:not([href="#"]):not([href=""]), a[id]').forEach(el => {
        const sufixo = selectorSuffix(el.id);
        const texto = el.textContent.trim().substring(0, 80);
        if (!texto && !el.id) return; // skip empty anonymous links
        results.push({
            tipo: 'link',
            id: el.id,
            texto: texto,
            href: el.getAttribute('href') || '',
            onclick: (el.getAttribute('onclick') || '').substring(0, 200),
            css_classes: [...el.classList],
            visivel: isVisible(el),
            dentro_de: closestContainer(el),
            sufixo: sufixo,
            seletor_recomendado: sufixo ? `a[id$='${sufixo}']` :
                                 texto ? `a:has-text('${texto.substring(0, 30)}')` : '',
            contexto: el.closest('#menupainel, [id*="menu"], nav, .sidebar') ?
                      'sidebar menu' : 'content',
        });
    });

    // 5. BUTTON elements (actual <button> tags)
    document.querySelectorAll('button').forEach(el => {
        const sufixo = selectorSuffix(el.id);
        results.push({
            tipo: 'button',
            id: el.id,
            texto: el.textContent.trim().substring(0, 80),
            tipo_button: el.type || 'button',
            onclick: (el.getAttribute('onclick') || '').substring(0, 200),
            css_classes: [...el.classList],
            visivel: isVisible(el),
            dentro_de: closestContainer(el),
            sufixo: sufixo,
            seletor_recomendado: sufixo ? `button[id$='${sufixo}']` : '',
        });
    });

    return results;
}"""

JS_EXTRACT_SIDEBAR = """() => {
    const links = [];
    // PJE-Calc sidebar uses <ul><li><a> structure with IDs like li#li_xxx
    document.querySelectorAll('#menupainel a, [id*="menu"] a, .rich-panelmenu a, li[id] > a').forEach(a => {
        const li = a.closest('li');
        links.push({
            texto: a.textContent.trim(),
            id: a.id || '',
            li_id: li ? li.id : '',
            href: a.getAttribute('href') || '',
            onclick: (a.getAttribute('onclick') || '').substring(0, 200),
            visivel: (() => { const r = a.getBoundingClientRect(); return r.width > 0 && r.height > 0; })(),
        });
    });
    return links;
}"""

JS_EXTRACT_MESSAGES = """() => {
    const selectors = {
        sucesso: '.rf-msgs-sum, .rich-messages-label',
        erro: '.rf-msgs-sum-err, .rf-msg-err, .rf-msgs-det',
        info: '.rf-msgs-inf, .rich-messages-info',
    };
    const found = {};
    for (const [tipo, sel] of Object.entries(selectors)) {
        const els = document.querySelectorAll(sel);
        found[tipo] = {
            selector: sel,
            count: els.length,
            textos: [...els].map(e => e.textContent.trim()).filter(t => t),
        };
    }
    return found;
}"""

JS_EXTRACT_TABLES = """() => {
    const tables = [];
    document.querySelectorAll('table[id], table.rich-table, table.rf-dt').forEach(t => {
        const headers = [...t.querySelectorAll('th')].map(th => th.textContent.trim());
        const rowCount = t.querySelectorAll('tbody tr').length;
        tables.push({
            id: t.id,
            css_classes: [...t.classList],
            headers: headers,
            row_count: rowCount,
        });
    });
    return tables;
}"""


# ---------------------------------------------------------------------------
# Page definitions: name -> navigation info
# ---------------------------------------------------------------------------

# Order matters: this is the sequence we navigate through
PAGINAS_AUDITORIA = [
    {
        "nome": "dados_processo",
        "titulo": "Dados do Processo",
        "sidebar_texto": "Dados do Cálculo",
        "sidebar_id": "menuCalculo",
        "aba": "tabDadosProcesso",
        "jsf": "calculo/calculo.jsf",
        "descricao": "Numero do processo, partes, documentos fiscais",
    },
    {
        "nome": "parametros_calculo",
        "titulo": "Parametros do Calculo",
        "sidebar_texto": None,  # same page, different tab
        "aba": "tabParametrosCalculo",
        "jsf": "calculo/calculo.jsf",
        "descricao": "Estado, municipio, datas, jornada, rescisao, aviso previo",
    },
    {
        "nome": "parametros_gerais",
        "titulo": "Parametros Gerais",
        "sidebar_texto": None,  # sub-tab or same page
        "aba": "tabParametrosGerais",
        "jsf": "calculo/parametros-gerais.jsf",
        "descricao": "Data inicio apuracao, carga horaria, zerar negativos",
    },
    {
        "nome": "historico_salarial",
        "titulo": "Historico Salarial",
        "sidebar_texto": "Histórico Salarial",
        "sidebar_id": "menuHistoricoSalarial",
        "jsf": "calculo/historico-salarial.jsf",
        "descricao": "Parcelas salariais, gerar ocorrencias",
    },
    {
        "nome": "ferias",
        "titulo": "Ferias",
        "sidebar_texto": "Férias",
        "sidebar_id": "menuFerias",
        "jsf": "calculo/ferias.jsf",
        "descricao": "Periodos aquisitivos, situacao, dias gozados",
    },
    {
        "nome": "faltas",
        "titulo": "Faltas",
        "sidebar_texto": "Faltas",
        "sidebar_id": "menuFaltas",
        "jsf": "calculo/faltas.jsf",
        "descricao": "Registro de ausencias",
    },
    {
        "nome": "cartao_ponto",
        "titulo": "Cartao de Ponto",
        "sidebar_texto": "Cartão de Ponto",
        "sidebar_id": "menuCartao",
        "jsf": "calculo/apuracao-cartaodeponto.jsf",
        "descricao": "Grade semanal, intervalos, horas extras/noturnas",
    },
    {
        "nome": "verbas_listagem",
        "titulo": "Verbas - Listagem",
        "sidebar_texto": "Verbas",
        "sidebar_id": "menuVerbas",
        "jsf": "verba/verba-calculo.jsf",
        "descricao": "Tabela com verbas criadas, botoes Expresso/Manual/Novo",
    },
    {
        "nome": "verbas_expresso",
        "titulo": "Verbas - Lancamento Expresso",
        "sidebar_texto": None,  # accessed via button on verba-calculo
        "botao_acesso": "btnExpresso",
        "jsf": "verba/verbas-para-calculo.xhtml",
        "descricao": "Tabela com ~60 checkboxes de verbas pre-definidas",
    },
    {
        "nome": "fgts",
        "titulo": "FGTS",
        "sidebar_texto": "FGTS",
        "sidebar_id": "menuFGTS",
        "jsf": "fgts/fgts.jsf",
        "descricao": "Tipo verba, aliquota, multas, incidencia",
    },
    {
        "nome": "contribuicao_social",
        "titulo": "Contribuicao Social (INSS)",
        "sidebar_texto": "Contribuição Social",
        "sidebar_id": "menuContribuicaoSocial",
        "jsf": "inss/inss.jsf",
        "descricao": "Apurar segurado, cobrar reclamante, correcao trabalhista",
    },
    {
        "nome": "imposto_renda",
        "titulo": "Imposto de Renda (IRPF)",
        "sidebar_texto": "Imposto de Renda",
        "sidebar_id": "menuImpostoRenda",
        "jsf": "irpf/irpf.jsf",
        "descricao": "Tributacao, deducoes, dependentes",
    },
    {
        "nome": "honorarios",
        "titulo": "Honorarios",
        "sidebar_texto": "Honorários",
        "sidebar_id": "menuHonorarios",
        "jsf": "honorarios/honorarios.jsf",
        "descricao": "Tipo, devedor, percentual, base apuracao",
    },
    {
        "nome": "correcao_juros_multa",
        "titulo": "Correcao, Juros e Multa",
        "sidebar_texto": "Correção, Juros e Multa",
        "sidebar_id": None,
        "jsf": "correcao-juros.jsf",
        "descricao": "Indice correcao, taxa juros, multa 523",
    },
    {
        "nome": "salario_familia",
        "titulo": "Salario Familia",
        "sidebar_texto": "Salário Família",
        "sidebar_id": "menuSalarioFamilia",
        "jsf": "salario-familia.jsf",
        "descricao": "Apurar, competencias, quantidade filhos",
    },
    {
        "nome": "seguro_desemprego",
        "titulo": "Seguro Desemprego",
        "sidebar_texto": "Seguro Desemprego",
        "sidebar_id": "menuSeguroDesemprego",
        "jsf": "seguro-desemprego.jsf",
        "descricao": "Apurar seguro desemprego",
    },
    {
        "nome": "pensao_alimenticia",
        "titulo": "Pensao Alimenticia",
        "sidebar_texto": "Pensão Alimentícia",
        "sidebar_id": "menuPensaoAlimenticia",
        "jsf": "pensao-alimenticia.jsf",
        "descricao": "Percentual, beneficiario",
    },
    {
        "nome": "previdencia_privada",
        "titulo": "Previdencia Privada",
        "sidebar_texto": "Previdência Privada",
        "sidebar_id": "menuPrevidenciaPrivada",
        "jsf": "previdencia-privada.jsf",
        "descricao": "Percentual previdencia privada",
    },
    {
        "nome": "liquidacao",
        "titulo": "Liquidar",
        "sidebar_texto": "Liquidar",
        "sidebar_id": "menuLiquidar",
        "jsf": "liquidacao/liquidacao.xhtml",
        "descricao": "Botao de liquidacao, data, lista calculos recentes",
    },
    {
        "nome": "exportacao",
        "titulo": "Exportar",
        "sidebar_texto": "Exportar",
        "sidebar_id": "menuExport",
        "jsf": "exportacao/exportacao.xhtml",
        "descricao": "Botao de download .PJC",
    },
]


# ---------------------------------------------------------------------------
# DOM Auditor class
# ---------------------------------------------------------------------------

class DOMAuditor:
    """Playwright-based auditor that navigates PJE-Calc and maps every element."""

    def __init__(
        self,
        base_url: str = "http://localhost:9257/pjecalc",
        headless: bool = True,
        output_dir: str | None = None,
        slow_mo: int = 100,
    ):
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.slow_mo = slow_mo
        self.output_dir = Path(output_dir) if output_dir else (
            Path(__file__).resolve().parent.parent / "knowledge"
        )
        self._pw = None
        self._browser = None
        self._page = None
        self._conversation_id: str | None = None
        self._calculo_url_base: str | None = None
        self._results: dict[str, Any] = {
            "metadata": {
                "gerado_em": datetime.now().isoformat(),
                "base_url": base_url,
                "versao_auditor": "1.0.0",
            },
            "sidebar": [],
            "paginas": {},
        }

    # -- Lifecycle -----------------------------------------------------------

    def iniciar(self) -> None:
        """Start Playwright Firefox browser."""
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().__enter__()
        self._browser = self._pw.firefox.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )
        ctx = self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        self._page = ctx.new_page()
        self._page.set_default_timeout(30000)
        print(f"[auditor] Browser Firefox iniciado (headless={self.headless})")

    def fechar(self) -> None:
        """Close browser and Playwright."""
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.__exit__(None, None, None)
        except Exception as e:
            print(f"[auditor] fechar: {e}")

    # -- Navigation helpers --------------------------------------------------

    def _aguardar_ajax(self, timeout: int = 10000) -> None:
        """Wait for JSF AJAX to complete."""
        try:
            self._page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            self._page.wait_for_timeout(2000)

    def _navegar_home(self) -> None:
        """Navigate to PJE-Calc home page."""
        url = f"{self.base_url}/pages/principal.jsf"
        print(f"[auditor] Navegando para {url}")
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._aguardar_ajax()
        self._page.wait_for_timeout(2000)

    def _criar_calculo(self) -> bool:
        """Create a new calculation via menu 'Novo'.
        O menu PJE-Calc usa RichFaces panelMenu que começa colapsado —
        usamos JavaScript para disparar onclick diretamente (A4J.AJAX.Submit).
        """
        print("[auditor] Criando novo calculo via menu 'Novo'...")

        # Accept any alert dialog (register BEFORE clicking)
        self._page.on("dialog", lambda d: d.accept())

        # Strategy 1: JS click via li#li_calculo_novo (reliable, works when collapsed)
        clicked = self._page.evaluate("""() => {
            // Try li#li_calculo_novo
            let link = document.querySelector('li#li_calculo_novo a');
            if (!link) link = document.querySelector("li[id*='calculo_novo'] a");
            if (!link) {
                // Search by text
                const all = [...document.querySelectorAll('a')];
                link = all.find(a => a.textContent.trim() === 'Novo');
            }
            if (link) {
                link.click();
                return true;
            }
            return false;
        }""")

        if not clicked:
            # Strategy 2: Playwright force click
            for sel in [
                "li#li_calculo_novo a",
                "li[id*='calculo_novo'] a",
            ]:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    try:
                        loc.first.click(force=True)
                        clicked = True
                        break
                    except Exception as e:
                        print(f"[auditor]   Force click falhou para {sel}: {e}")

        if not clicked:
            print("[auditor] ERRO: Botao 'Novo' nao encontrado/clicável")
            return False

        # Wait for JSF navigation
        self._aguardar_ajax()
        self._page.wait_for_timeout(3000)

        # Capture conversation ID from URL
        self._capturar_ids()
        if self._conversation_id:
            print(f"[auditor] Calculo criado (conversationId={self._conversation_id})")
        else:
            print("[auditor] Calculo criado (conversationId nao capturado)")
        return True

    def _capturar_ids(self) -> None:
        """Extract conversationId and URL base from current page."""
        url = self._page.url
        m = re.search(r"conversationId=(\d+)", url)
        if m:
            self._conversation_id = m.group(1)
        # Detect URL base pattern: .../pages/calculo/ or .../pages/
        m2 = re.search(r"(.*/pages/)", url)
        if m2:
            self._calculo_url_base = m2.group(1)

    def _clicar_menu_lateral(self, texto: str) -> bool:
        """Click a sidebar menu item by text (JS click for collapsed menu)."""
        # Strategy 0: by li ID from menu-pilares via JS click (confirmed IDs PJE-Calc v2.15.1)
        _LI_ID_MAP = {
            "Dados do Cálculo":     "calculo_dados_do_calculo",
            "Dados do Calculo":     "calculo_dados_do_calculo",
            "Histórico Salarial":   "calculo_historico_salarial",
            "Historico Salarial":   "calculo_historico_salarial",
            "Verbas":               "calculo_verbas",
            "FGTS":                 "calculo_fgts",
            "Honorários":           "calculo_honorarios",
            "Honorarios":           "calculo_honorarios",
            "Liquidar":             "calculo_liquidar",
            "Faltas":               "calculo_faltas",
            "Férias":               "calculo_ferias",
            "Ferias":               "calculo_ferias",
            "Contribuição Social":  "calculo_inss",
            "Contribuicao Social":  "calculo_inss",
            "Imposto de Renda":     "calculo_irpf",
            "Multas":               "calculo_multas_e_indenizacoes",
            "Cartão de Ponto":      "calculo_cartao_ponto",
            "Cartao de Ponto":      "calculo_cartao_ponto",
            "Salário Família":      "calculo_salario_familia",
            "Salario Familia":      "calculo_salario_familia",
            "Seguro Desemprego":    "calculo_seguro_desemprego",
            "Pensão Alimentícia":   "calculo_pensao_alimenticia",
            "Pensao Alimenticia":   "calculo_pensao_alimenticia",
            "Previdência Privada":  "calculo_previdencia_privada",
            "Previdencia Privada":  "calculo_previdencia_privada",
            "Exportar":             "calculo_exportar",
            "Exportação":           "calculo_exportar",
            "Correção, Juros e Multa": "calculo_correcao_juros_e_multa",
            "Custas Judiciais":     "calculo_custas_judiciais",
            "Novo":                 "calculo_novo",
        }
        li_suffix = _LI_ID_MAP.get(texto)
        if li_suffix:
            # JS click — works even when menu is collapsed (A4J onclick triggers correctly)
            clicked = self._page.evaluate(f"""() => {{
                let link = document.querySelector('li#li_{li_suffix} a');
                if (!link) link = document.querySelector("li[id*='{li_suffix}'] a");
                if (link) {{ link.click(); return true; }}
                return false;
            }}""")
            if clicked:
                self._aguardar_ajax()
                self._page.wait_for_timeout(1500)
                return True

        # Strategy 1: by menu ID pattern (legacy)
        _menu_ids = {
            "Dados do Calculo": "menuCalculo",
            "Historico Salarial": "menuHistoricoSalarial",
            "Verbas": "menuVerbas",
            "FGTS": "menuFGTS",
            "Honorários": "menuHonorarios",
            "Liquidar": "menuLiquidar",
            "Faltas": "menuFaltas",
            "Férias": "menuFerias",
            "Novo": "menuNovo",
            "Contribuição Social": "menuContribuicaoSocial",
            "Imposto de Renda": "menuImpostoRenda",
            "Multas": "menuMultas",
            "Cartão de Ponto": "menuCartao",
            "Exportar": "menuExport",
        }
        menu_id = _menu_ids.get(texto)
        if menu_id:
            sel = f"a[id*='{menu_id}']"
            loc = self._page.locator(sel)
            if loc.count() > 0:
                try:
                    loc.first.click(force=True, timeout=5000)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(1500)
                    return True
                except Exception:
                    pass

        # Strategy 2: by text content
        for sel in [
            f"a:has-text('{texto}')",
            f"span:has-text('{texto}')",
        ]:
            loc = self._page.locator(sel)
            if loc.count() > 0:
                try:
                    loc.first.click(force=True, timeout=5000)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(1500)
                    return True
                except Exception:
                    continue

        # Strategy 3: URL direct navigation
        return False

    def _navegar_url_direta(self, jsf_path: str) -> bool:
        """Navigate directly to a JSF page using conversationId."""
        if not self._conversation_id:
            return False
        base = self._calculo_url_base or f"{self.base_url}/pages/"
        # Try multiple path prefixes
        for prefix in ["calculo/", "verba/", "fgts/", "inss/", "irpf/",
                       "honorarios/", "liquidacao/", "exportacao/", ""]:
            url = f"{base}{prefix}{jsf_path}?conversationId={self._conversation_id}"
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
                self._aguardar_ajax()
                self._page.wait_for_timeout(1000)
                # Check we got a real page (not error/redirect)
                body = self._page.locator("body").text_content(timeout=3000) or ""
                if "formulario" in self._page.content()[:5000].lower() or len(body) > 200:
                    return True
            except Exception:
                continue
        return False

    def _clicar_aba(self, aba_id: str) -> bool:
        """Click a tab within the current page."""
        for sel in [
            f"[id$='{aba_id}_lbl']",
            f"[id$='{aba_id}_header']",
            f"[id$='{aba_id}'] span",
            f"td[id$='{aba_id}']",
        ]:
            loc = self._page.locator(sel)
            if loc.count() > 0:
                try:
                    loc.first.click(timeout=3000)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(800)
                    return True
                except Exception:
                    continue
        return False

    # -- Extraction ----------------------------------------------------------

    def _extrair_pagina(self, pagina_info: dict) -> dict:
        """Extract all interactive elements from the current page."""
        nome = pagina_info["nome"]
        print(f"[auditor] Extraindo elementos de: {nome} ({pagina_info['titulo']})")

        # Extract all interactive elements
        try:
            elementos = self._page.evaluate(JS_EXTRACT_ELEMENTS)
        except Exception as e:
            print(f"[auditor]   ERRO extraindo elementos: {e}")
            elementos = []

        # Extract sidebar links
        try:
            sidebar = self._page.evaluate(JS_EXTRACT_SIDEBAR)
        except Exception as e:
            print(f"[auditor]   ERRO extraindo sidebar: {e}")
            sidebar = []

        # Extract messages areas
        try:
            mensagens = self._page.evaluate(JS_EXTRACT_MESSAGES)
        except Exception as e:
            mensagens = {}

        # Extract tables
        try:
            tabelas = self._page.evaluate(JS_EXTRACT_TABLES)
        except Exception as e:
            tabelas = []

        # Page metadata
        url = self._page.url
        titulo_pagina = ""
        try:
            titulo_pagina = self._page.title()
        except Exception:
            pass

        # Count by type
        tipos_count = {}
        for el in elementos:
            t = el.get("tipo", "unknown")
            tipos_count[t] = tipos_count.get(t, 0) + 1

        # Filter: separate visible interactive vs hidden
        visiveis = [e for e in elementos if e.get("visivel") and e.get("tipo") != "hidden"]
        ocultos = [e for e in elementos if not e.get("visivel") or e.get("tipo") == "hidden"]

        result = {
            "pagina": pagina_info.get("jsf", ""),
            "titulo": pagina_info["titulo"],
            "descricao": pagina_info.get("descricao", ""),
            "url": url,
            "titulo_html": titulo_pagina,
            "total_elementos": len(elementos),
            "elementos_visiveis": len(visiveis),
            "elementos_ocultos": len(ocultos),
            "contagem_por_tipo": tipos_count,
            "elementos": elementos,
            "sidebar_links": sidebar,
            "mensagens": mensagens,
            "tabelas": tabelas,
        }

        print(f"[auditor]   -> {len(visiveis)} visiveis, {len(ocultos)} ocultos "
              f"({tipos_count})")

        # Take screenshot for reference
        try:
            ss_dir = self.output_dir / "screenshots"
            ss_dir.mkdir(parents=True, exist_ok=True)
            self._page.screenshot(
                path=str(ss_dir / f"audit_{nome}.png"),
                full_page=True,
            )
        except Exception:
            pass

        return result

    # -- Audit orchestration -------------------------------------------------

    def auditar(self) -> dict:
        """Main audit loop: navigate to each page and extract elements."""
        print("=" * 60)
        print("[auditor] Iniciando auditoria DOM do PJE-Calc")
        print(f"[auditor] URL base: {self.base_url}")
        print("=" * 60)

        # 1. Navigate to home
        self._navegar_home()

        # 2. Extract sidebar from home page
        try:
            self._results["sidebar"] = self._page.evaluate(JS_EXTRACT_SIDEBAR)
            print(f"[auditor] Sidebar: {len(self._results['sidebar'])} links encontrados")
        except Exception as e:
            print(f"[auditor] Sidebar extraction failed: {e}")

        # 3. Create new calculation
        if not self._criar_calculo():
            print("[auditor] FATAL: Nao foi possivel criar calculo. Abortando.")
            return self._results

        # 4. Audit each page
        for pagina in PAGINAS_AUDITORIA:
            nome = pagina["nome"]
            print(f"\n{'─' * 50}")
            print(f"[auditor] Pagina: {pagina['titulo']} ({nome})")
            print(f"{'─' * 50}")

            navegou = False

            # Strategy A: click tab (same page, different tab)
            if pagina.get("aba") and not pagina.get("sidebar_texto"):
                navegou = self._clicar_aba(pagina["aba"])
                if navegou:
                    print(f"[auditor]   Navegou via aba: {pagina['aba']}")

            # Strategy B: click sidebar menu
            if not navegou and pagina.get("sidebar_texto"):
                navegou = self._clicar_menu_lateral(pagina["sidebar_texto"])
                if navegou:
                    print(f"[auditor]   Navegou via sidebar: {pagina['sidebar_texto']}")
                    # If page also has a tab, click it
                    if pagina.get("aba"):
                        self._clicar_aba(pagina["aba"])

            # Strategy C: click button (e.g., Expresso button on verbas page)
            if not navegou and pagina.get("botao_acesso"):
                btn_id = pagina["botao_acesso"]
                for sel in [f"input[id*='{btn_id}']", f"a[id*='{btn_id}']",
                           f"input[value*='Expresso']", f"a:has-text('Expresso')"]:
                    loc = self._page.locator(sel)
                    if loc.count() > 0:
                        try:
                            loc.first.click(timeout=5000)
                            self._aguardar_ajax()
                            self._page.wait_for_timeout(2000)
                            navegou = True
                            print(f"[auditor]   Navegou via botao: {sel}")
                            break
                        except Exception:
                            continue

            # Strategy D: direct URL navigation
            if not navegou and pagina.get("jsf"):
                navegou = self._navegar_url_direta(pagina["jsf"])
                if navegou:
                    print(f"[auditor]   Navegou via URL direta: {pagina['jsf']}")

            if not navegou:
                print(f"[auditor]   FALHA: nao conseguiu navegar para {nome}")
                self._results["paginas"][nome] = {
                    "pagina": pagina.get("jsf", ""),
                    "titulo": pagina["titulo"],
                    "erro": "Navegacao falhou",
                    "elementos": [],
                }
                continue

            # Extract page elements
            self._capturar_ids()
            resultado = self._extrair_pagina(pagina)
            self._results["paginas"][nome] = resultado

            # Scroll down to capture elements below fold (important for Expresso)
            if nome == "verbas_expresso":
                print("[auditor]   Scrolling para capturar verbas abaixo do fold...")
                try:
                    self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    self._page.wait_for_timeout(1500)
                    # Re-extract after scroll
                    extra_elements = self._page.evaluate(JS_EXTRACT_ELEMENTS)
                    # Merge new elements (by ID, avoiding duplicates)
                    existing_ids = {e["id"] for e in resultado["elementos"] if e.get("id")}
                    for el in extra_elements:
                        if el.get("id") and el["id"] not in existing_ids:
                            resultado["elementos"].append(el)
                            existing_ids.add(el["id"])
                    resultado["total_elementos"] = len(resultado["elementos"])
                    print(f"[auditor]   Apos scroll: {resultado['total_elementos']} elementos totais")
                except Exception as e:
                    print(f"[auditor]   Scroll failed: {e}")

        # 5. Summary
        total_paginas = len(self._results["paginas"])
        total_elementos = sum(
            p.get("total_elementos", 0) for p in self._results["paginas"].values()
        )
        print(f"\n{'=' * 60}")
        print(f"[auditor] Auditoria concluida: {total_paginas} paginas, {total_elementos} elementos")
        print(f"{'=' * 60}")

        self._results["metadata"]["total_paginas"] = total_paginas
        self._results["metadata"]["total_elementos"] = total_elementos
        self._results["metadata"]["concluido_em"] = datetime.now().isoformat()

        return self._results

    # -- Output generation ---------------------------------------------------

    def gerar_saida(self) -> None:
        """Generate all 3 output files."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 1. JSON map
        json_path = self.output_dir / "pjecalc_dom_map.json"
        json_path.write_text(
            json.dumps(self._results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[auditor] JSON salvo: {json_path}")

        # 2. Markdown reference
        md_path = self.output_dir / "pjecalc_dom_reference.md"
        md_content = self._gerar_markdown()
        md_path.write_text(md_content, encoding="utf-8")
        print(f"[auditor] Markdown salvo: {md_path}")

        # 3. Python selectors
        py_path = self.output_dir / "pjecalc_selectors.py"
        py_content = self._gerar_python_selectors()
        py_path.write_text(py_content, encoding="utf-8")
        print(f"[auditor] Python selectors salvo: {py_path}")

    def _gerar_markdown(self) -> str:
        """Generate Markdown reference document."""
        lines = [
            "# PJE-Calc DOM Reference",
            "",
            f"Gerado em: {self._results['metadata'].get('gerado_em', 'N/A')}",
            f"URL base: {self._results['metadata'].get('base_url', 'N/A')}",
            "",
        ]

        # Sidebar
        sidebar = self._results.get("sidebar", [])
        if sidebar:
            lines.append("## Sidebar Navigation")
            lines.append("")
            lines.append("| Texto | ID | Li ID |")
            lines.append("|-------|-----|-------|")
            for link in sidebar:
                if link.get("texto"):
                    lines.append(
                        f"| {link['texto'][:40]} | `{link.get('id', '')}` | `{link.get('li_id', '')}` |"
                    )
            lines.append("")

        # Pages
        for nome, pagina in self._results.get("paginas", {}).items():
            lines.append(f"## {pagina.get('titulo', nome)}")
            lines.append("")
            lines.append(f"- **JSF**: `{pagina.get('pagina', '')}`")
            lines.append(f"- **URL**: `{pagina.get('url', '')}`")
            lines.append(f"- **Total elementos**: {pagina.get('total_elementos', 0)}")
            lines.append(f"- **Visiveis**: {pagina.get('elementos_visiveis', 0)}")
            if pagina.get("descricao"):
                lines.append(f"- **Descricao**: {pagina['descricao']}")
            lines.append("")

            if pagina.get("erro"):
                lines.append(f"> ERRO: {pagina['erro']}")
                lines.append("")
                continue

            # Group elements by type
            elementos = pagina.get("elementos", [])
            for tipo in ["input", "select", "checkbox", "radio", "textarea", "button", "link"]:
                tipo_els = [e for e in elementos if e.get("tipo") == tipo and e.get("visivel")]
                if not tipo_els:
                    continue

                lines.append(f"### {tipo.capitalize()}s")
                lines.append("")

                if tipo == "select":
                    lines.append("| ID Sufixo | Label | Opcoes | Seletor |")
                    lines.append("|-----------|-------|--------|---------|")
                    for el in tipo_els:
                        opcoes = el.get("opcoes", [])
                        opcoes_str = ", ".join(
                            f"{o['value']}={o['texto'][:15]}" for o in opcoes[:5]
                        )
                        if len(opcoes) > 5:
                            opcoes_str += f"... (+{len(opcoes)-5})"
                        lines.append(
                            f"| `{el.get('sufixo', '')}` "
                            f"| {el.get('label', '')[:30]} "
                            f"| {opcoes_str} "
                            f"| `{el.get('seletor_recomendado', '')}` |"
                        )
                elif tipo == "radio":
                    lines.append("| ID Sufixo | Label | Value | Name | Seletor |")
                    lines.append("|-----------|-------|-------|------|---------|")
                    for el in tipo_els:
                        lines.append(
                            f"| `{el.get('sufixo', '')}` "
                            f"| {el.get('label', '')[:30]} "
                            f"| `{el.get('radio_value', '')}` "
                            f"| `{el.get('radio_name', '')}` "
                            f"| `{el.get('seletor_recomendado', '')}` |"
                        )
                elif tipo in ("button", "link"):
                    lines.append("| ID Sufixo | Texto | Seletor |")
                    lines.append("|-----------|-------|---------|")
                    for el in tipo_els:
                        lines.append(
                            f"| `{el.get('sufixo', '')}` "
                            f"| {el.get('texto', '')[:40]} "
                            f"| `{el.get('seletor_recomendado', '')}` |"
                        )
                else:
                    lines.append("| ID Sufixo | Label | Tipo | MaxLen | Seletor |")
                    lines.append("|-----------|-------|------|--------|---------|")
                    for el in tipo_els:
                        lines.append(
                            f"| `{el.get('sufixo', '')}` "
                            f"| {el.get('label', '')[:30]} "
                            f"| `{el.get('tipo_input', '')}` "
                            f"| {el.get('maxlength') or '-'} "
                            f"| `{el.get('seletor_recomendado', '')}` |"
                        )
                lines.append("")

            # Tables
            tabelas = pagina.get("tabelas", [])
            if tabelas:
                lines.append("### Tabelas")
                lines.append("")
                for t in tabelas:
                    lines.append(f"- **{t.get('id', 'sem-id')}** "
                                f"(classes: {t.get('css_classes', [])}, "
                                f"headers: {t.get('headers', [])}, "
                                f"rows: {t.get('row_count', 0)})")
                lines.append("")

        return "\n".join(lines)

    def _gerar_python_selectors(self) -> str:
        """Generate Python file with selector constants."""
        lines = [
            '"""',
            "PJE-Calc DOM Selectors - Gerado automaticamente pelo DOM Auditor.",
            "",
            f"Gerado em: {self._results['metadata'].get('gerado_em', 'N/A')}",
            "",
            "Uso:",
            "    from knowledge.pjecalc_selectors import DadosProcesso, FGTS, ...",
            "    page.locator(DadosProcesso.NUMERO).fill('1234567')",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "",
        ]

        # Generate a class per page
        for nome, pagina in self._results.get("paginas", {}).items():
            elementos = pagina.get("elementos", [])
            if not elementos:
                continue

            # Class name from page name
            class_name = "".join(
                word.capitalize() for word in nome.split("_")
            )

            lines.append(f"class {class_name}:")
            lines.append(f'    """Seletores para: {pagina.get("titulo", nome)}"""')
            lines.append(f'    JSF = "{pagina.get("pagina", "")}"')
            lines.append("")

            # Track seen suffixes to avoid duplicates within a class
            seen_suffixes = set()

            # Add visible interactive elements as constants
            for el in elementos:
                if not el.get("visivel") or el.get("tipo") == "hidden":
                    continue
                sufixo = el.get("sufixo", "")
                sel = el.get("seletor_recomendado", "")
                if not sufixo or not sel or sufixo in seen_suffixes:
                    continue
                seen_suffixes.add(sufixo)

                # Generate constant name: camelCase to UPPER_SNAKE
                const_name = re.sub(r"([a-z])([A-Z])", r"\1_\2", sufixo).upper()
                const_name = re.sub(r"[^A-Z0-9_]", "_", const_name)
                if const_name and const_name[0].isdigit():
                    const_name = "_" + const_name

                label = el.get("label", "")
                tipo = el.get("tipo", "")
                comment = f"  # {tipo}"
                if label:
                    comment += f" - {label[:40]}"

                lines.append(f'    {const_name} = "{sel}"{comment}')

            lines.append("")
            lines.append("")

        # Add sidebar navigation class
        sidebar = self._results.get("sidebar", [])
        if sidebar:
            lines.append("class SidebarMenu:")
            lines.append('    """Seletores do menu lateral do PJE-Calc"""')
            lines.append("")
            seen = set()
            for link in sidebar:
                texto = link.get("texto", "").strip()
                id_val = link.get("id", "")
                if not texto or texto in seen:
                    continue
                seen.add(texto)
                const_name = re.sub(r"[^A-Za-z0-9]", "_", texto).upper()
                const_name = re.sub(r"_+", "_", const_name).strip("_")
                if not const_name:
                    continue
                if id_val:
                    sufixo = id_val.split(":")[-1]
                    lines.append(f'    {const_name} = "a[id*=\'{sufixo}\']"  # {texto}')
                else:
                    lines.append(f'    {const_name} = "a:has-text(\'{texto[:30]}\')"')
            lines.append("")
            lines.append("")

        # Add common message selectors
        lines.extend([
            "class Mensagens:",
            '    """Seletores de mensagens de sucesso/erro do JSF/RichFaces"""',
            "",
            "    SUCESSO = '.rf-msgs-sum, .rich-messages-label'",
            "    ERRO = '.rf-msgs-sum-err, .rf-msg-err, .rf-msgs-det'",
            "    ERRO_CAMPO = '.rf-inpt-fld-err, input.error, select.error'",
            "    INFO = '.rf-msgs-inf, .rich-messages-info'",
            "",
            "",
            "class Comum:",
            '    """Seletores comuns reutilizados em varias paginas"""',
            "",
            "    SALVAR = \"[id$='salvar']\"",
            "    NOVO = \"[id$='novo'], [id$='novoBt'], input[value='Novo']\"",
            "    INCLUIR = \"[id$='incluir']\"",
            "    CANCELAR = \"[id$='cancelar']\"",
            "    FECHAR = \"[id$='fechar']\"",
            "    CONFIRMAR = \"[id$='confirmar'], input[value='Confirmar']\"",
            "    EXCLUIR = \"[id$='excluir']\"",
            "",
        ])

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="DOM Auditor para PJE-Calc Cidadao - mapeia todos os elementos interativos"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("PJECALC_LOCAL_URL", "http://localhost:9257/pjecalc"),
        help="URL base do PJE-Calc (default: http://localhost:9257/pjecalc)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Executar Firefox em modo headless",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Diretorio de saida (default: knowledge/)",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=100,
        help="Slow motion em ms entre acoes (default: 100)",
    )
    args = parser.parse_args()

    auditor = DOMAuditor(
        base_url=args.url,
        headless=args.headless,
        output_dir=args.output_dir,
        slow_mo=args.slow_mo,
    )

    try:
        auditor.iniciar()
        auditor.auditar()
        auditor.gerar_saida()
    except KeyboardInterrupt:
        print("\n[auditor] Interrompido pelo usuario. Salvando resultados parciais...")
        auditor.gerar_saida()
    except Exception as e:
        print(f"\n[auditor] ERRO FATAL: {e}")
        import traceback
        traceback.print_exc()
        # Still try to save partial results
        try:
            auditor.gerar_saida()
        except Exception:
            pass
        sys.exit(1)
    finally:
        auditor.fechar()


if __name__ == "__main__":
    main()
