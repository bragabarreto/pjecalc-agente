"""Catálogo completo de campos do PJE-Calc Cidadão por página.

Visita cada página e sub-página, dumpa todos os campos:
- id (sufixo após 'formulario:')
- tipo (input/select/radio/checkbox/textarea/button)
- value default
- opções (para select/radio)
- label visível
- visibilidade (offsetParent)
- disabled/readonly

Gera arquivo data/logs/catalogo_pjecalc_completo.json + docs/pjecalc-fields-catalog.md.

Uso (no container):
    docker exec pjecalc-agente-pjecalc-1 python3 /app/scripts/cataloga_pjecalc.py

Uso (local):
    python3 scripts/cataloga_pjecalc.py
"""
import json
import sys
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, Page


BASE = os.environ.get("PJECALC_URL", "http://localhost:9257/pjecalc")
OUT_JSON = Path("/app/data/logs/catalogo_pjecalc_completo.json") if Path("/app").exists() else Path("data/logs/catalogo_pjecalc_completo.json")
OUT_MD = Path(__file__).parent.parent / "docs" / "pjecalc-fields-catalog.md"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)


def log(msg):
    print(f"[catalogo] {msg}", file=sys.stderr, flush=True)


def dump_pagina(p: Page, nome_pagina: str) -> dict:
    """Dump completo dos campos visíveis na página atual."""
    return p.evaluate(
        """(label) => {
            // Filtros para descartar lixo do framework
            const SKIP_RE = /msgAguarde|searchText|zoom|j_id_jsp|skinPanel|modalSobre|painelLabelFormula|status\\.start|status\\.stop/i;
            const norm = id => (id || '').replace(/^formulario:/, '');

            const sufixoLimpo = id => {
                if (!id) return '';
                if (SKIP_RE.test(id)) return null;
                return norm(id);
            };

            const collectField = (el) => {
                const sufixo = sufixoLimpo(el.id);
                if (!sufixo) return null;
                const lbl = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null;
                const labelTxt = (lbl?.textContent || '').replace(/\\s+/g, ' ').trim();
                // Só capturar visíveis
                const visivel = el.offsetParent !== null
                    || (el.getBoundingClientRect && el.getBoundingClientRect().width > 0);
                const result = {
                    id: sufixo,
                    full_id: el.id,
                    tag: el.tagName.toLowerCase(),
                    type: el.type || el.tagName.toLowerCase(),
                    name: el.name || '',
                    label: labelTxt,
                    disabled: !!el.disabled,
                    readonly: !!el.readOnly,
                    visivel: visivel,
                    value_default: el.type === 'password' ? '' : (el.value || '').slice(0, 200),
                };
                if (el.tagName === 'SELECT') {
                    result.opcoes = [...el.options].map(o => ({
                        v: o.value,
                        l: (o.textContent || '').trim(),
                        selected: o.selected,
                    }));
                }
                if (el.type === 'radio') {
                    result.checked = !!el.checked;
                    result.radio_value = el.value;
                }
                if (el.type === 'checkbox') {
                    result.checked = !!el.checked;
                }
                return result;
            };

            const all = [];
            // Inputs (text, hidden, radio, checkbox, password, etc.)
            document.querySelectorAll('input').forEach(el => {
                const f = collectField(el);
                if (f) all.push(f);
            });
            // Selects
            document.querySelectorAll('select').forEach(el => {
                const f = collectField(el);
                if (f) all.push(f);
            });
            // Textareas
            document.querySelectorAll('textarea').forEach(el => {
                const f = collectField(el);
                if (f) all.push(f);
            });
            // Buttons (submit/button explícitos)
            document.querySelectorAll('input[type="button"], input[type="submit"], button').forEach(el => {
                if (!el.id || SKIP_RE.test(el.id)) return;
                all.push({
                    id: norm(el.id),
                    full_id: el.id,
                    tag: el.tagName.toLowerCase(),
                    type: el.type || 'button',
                    label: (el.value || el.textContent || '').trim().slice(0, 80),
                    visivel: el.offsetParent !== null,
                });
            });

            // Agrupar radios por nome
            const radios = {};
            all.filter(f => f.type === 'radio').forEach(r => {
                const k = r.name || r.id;
                if (!radios[k]) radios[k] = {grupo: k, label_grupo: r.label, opcoes: []};
                radios[k].opcoes.push({v: r.radio_value, checked: r.checked, label: r.label});
            });

            // Tabelas (informativo): nº de linhas com checkbox :ativo
            const linhasOcorrencias = document.querySelectorAll(
                'input[type="checkbox"][id*=":listagem:"][id$=":ativo"]'
            ).length;

            return {
                pagina: label,
                url: location.href,
                titulo: document.title,
                campos: all,
                radios_agrupados: Object.values(radios),
                linhas_ocorrencias_listagem: linhasOcorrencias,
            };
        }""",
        nome_pagina,
    )


def goto_seguro(p, url, label):
    log(f"  → {label}: {url}")
    try:
        p.goto(url, wait_until="domcontentloaded", timeout=20000)
        p.wait_for_load_state("networkidle", timeout=10000)
        p.wait_for_timeout(800)
        return True
    except Exception as e:
        log(f"    ⚠ erro navegando: {e}")
        return False


def criar_calc_minimo(p) -> str | None:
    """Cria um cálculo mínimo necessário para acessar todas as páginas. Retorna conv_id."""
    log("Criando cálculo mínimo…")
    p.goto(f"{BASE}/pages/principal.jsf", timeout=20000)
    p.wait_for_load_state("networkidle", timeout=15000)
    p.wait_for_timeout(2000)
    # Click "Novo"
    clicou = p.evaluate(
        """() => {
            const links = [...document.querySelectorAll('a')];
            for (const a of links) {
                if ((a.textContent || '').trim() === 'Novo') {
                    a.click(); return true;
                }
            }
            return false;
        }"""
    )
    if not clicou:
        log("  ⚠ Botão Novo não encontrado")
        return None
    p.wait_for_url("**/calculo*.jsf*", timeout=20000)
    p.wait_for_load_state("networkidle", timeout=15000)
    conv = p.url.split("conversationId=")[1].split("&")[0] if "conversationId=" in p.url else None
    log(f"  conv={conv}")

    # Mínimo p/ salvar
    try:
        p.click("input[type=radio][id*='documentoFiscalReclamante'][value='CPF']", force=True, timeout=5000)
        p.wait_for_timeout(500)
        p.fill("[id$='reclamanteNumeroDocumentoFiscal']", "11122233344")
    except Exception:
        pass
    try:
        p.click("input[type=radio][id*='tipoDocumentoFiscalReclamado'][value='CNPJ']", force=True, timeout=5000)
        p.wait_for_timeout(500)
        p.fill("[id$='reclamadoNumeroDocumentoFiscal']", "00000000000191")
    except Exception:
        pass
    p.fill("[id$='numero']", "0001234")
    p.fill("[id$='digito']", "56")
    p.fill("[id$='ano']", "2025")
    p.fill("[id$='regiao']", "07")
    p.fill("[id$='vara']", "0001")
    p.fill("[id$='valorDaCausa']", "1000,00")
    p.fill("[id$='autuadoEm']", "01/01/2025")
    p.fill("[id$='reclamanteNome']", "TESTE CATALOGO")
    p.fill("[id$='reclamadoNome']", "EMPRESA TESTE")
    # Aba Parâmetros
    p.evaluate(
        """[...document.querySelectorAll('.rich-tab-header')].find(t =>
            t.textContent.trim() === 'Parâmetros do Cálculo')?.click()"""
    )
    p.wait_for_timeout(2000)
    p.fill("[id$='dataAdmissaoInputDate']", "01/01/2020")
    p.fill("[id$='dataDemissaoInputDate']", "31/12/2024")
    p.fill("[id$='dataAjuizamentoInputDate']", "01/01/2025")
    p.fill("[id$='dataInicioCalculoInputDate']", "01/01/2020")
    p.fill("[id$='dataTerminoCalculoInputDate']", "31/12/2024")
    p.fill("[id$='valorMaiorRemuneracao']", "2.500,00")
    p.fill("[id$='valorUltimaRemuneracao']", "2.500,00")
    p.click("input[id$='salvar']", force=True)
    p.wait_for_timeout(8000)
    return conv


# Ordem do menu lateral, igual ao manual oficial
PAGINAS = [
    ("01_dados_processo", "calculo.jsf", "Dados do Processo"),
    ("02_historico_salarial_listing", "historico-salarial.jsf", "Histórico Salarial — listagem"),
    ("03_faltas_listing", "falta.jsf", "Faltas — listagem"),
    ("04_ferias_listing", "ferias.jsf", "Férias — listagem"),
    ("05_verbas_listing", "verba/verba-calculo.jsf", "Verbas — listagem"),
    ("06_cartao_ponto", "../cartaodeponto/apuracao-cartaodeponto.jsf", "Cartão de Ponto"),
    ("07_salario_familia", "salario-familia.jsf", "Salário-família"),
    ("08_seguro_desemprego", "seguro-desemprego.jsf", "Seguro-desemprego"),
    ("09_fgts", "fgts/fgts.jsf", "FGTS"),
    ("10_inss", "inss/inss.jsf", "Contribuição Social (INSS)"),
    ("11_previdencia_privada", "previdencia-privada.jsf", "Previdência Privada"),
    ("12_pensao_alimenticia", "pensao-alimenticia.jsf", "Pensão Alimentícia"),
    ("13_irpf", "imposto-renda.jsf", "Imposto de Renda"),
    ("14_multas_indenizacoes", "multa-indenizacao.jsf", "Multas e Indenizações"),
    ("15_honorarios", "honorario/honorario.jsf", "Honorários"),
    ("16_custas", "custas-judiciais.jsf", "Custas Judiciais"),
    ("17_correcao_juros", "correcao-juros-multa.jsf", "Correção, Juros e Multa"),
]

# Sub-páginas críticas — clicam Novo / Incluir / Manual / Expresso para abrir form
SUBPAGINAS_INCLUIR = [
    ("02b_historico_salarial_form", "historico-salarial.jsf", "Histórico Salarial — form Novo", "input[id$='incluir']"),
    ("03b_faltas_form", "falta.jsf", "Faltas — form Novo", "input[id$='incluir']"),
    ("04b_ferias_form", "ferias.jsf", "Férias — form Novo", "input[id$='incluir']"),
    ("05b_verbas_expresso", "verba/verba-calculo.jsf", "Verbas — Lançamento Expresso", "input[id$='lancamentoExpresso']"),
    ("05c_verbas_manual", "verba/verba-calculo.jsf", "Verbas — Manual (form)", "input[id$='incluir'][value='Manual']"),
    ("15b_honorarios_form", "honorario/honorario.jsf", "Honorários — form Novo", "input[id$='incluir']"),
]


def main():
    catalogo = {"version": "1.0", "base_url": BASE, "paginas": {}}

    with sync_playwright() as pw:
        b = pw.firefox.launch(headless=True)
        p = b.new_page()
        conv = criar_calc_minimo(p)
        if not conv:
            log("ERRO: cálculo mínimo falhou")
            return 1

        url_base = f"{BASE}/pages/calculo/"

        # Páginas top-level
        for key, jsf_path, nome in PAGINAS:
            url = f"{url_base}{jsf_path}?conversationId={conv}"
            if not goto_seguro(p, url, nome):
                catalogo["paginas"][key] = {"erro": "navegação falhou"}
                continue
            try:
                catalogo["paginas"][key] = dump_pagina(p, nome)
                log(f"    ✓ {nome}: {len(catalogo['paginas'][key].get('campos', []))} campos")
            except Exception as e:
                catalogo["paginas"][key] = {"erro": str(e)[:200]}

        # Sub-páginas (form Novo / Manual)
        for key, jsf_path, nome, btn_sel in SUBPAGINAS_INCLUIR:
            url = f"{url_base}{jsf_path}?conversationId={conv}"
            if not goto_seguro(p, url, nome):
                catalogo["paginas"][key] = {"erro": "navegação falhou"}
                continue
            try:
                # click Novo/Incluir/Manual/Expresso
                btn = p.locator(btn_sel).first
                if btn.count() == 0:
                    catalogo["paginas"][key] = {"erro": f"botão {btn_sel} não encontrado"}
                    continue
                btn.click(force=True)
                p.wait_for_timeout(3000)
                try:
                    p.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                catalogo["paginas"][key] = dump_pagina(p, nome)
                log(f"    ✓ {nome}: {len(catalogo['paginas'][key].get('campos', []))} campos")
            except Exception as e:
                catalogo["paginas"][key] = {"erro": str(e)[:200]}

        b.close()

    # Salvar JSON
    OUT_JSON.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✓ JSON: {OUT_JSON}")

    # Gerar markdown legível
    gerar_markdown(catalogo)
    log(f"✓ Markdown: {OUT_MD}")
    return 0


def gerar_markdown(catalogo: dict):
    lines = [
        "# Catálogo de Campos — PJE-Calc Cidadão (v2.15.1)",
        "",
        "Gerado automaticamente por `scripts/cataloga_pjecalc.py`. Contém TODOS os campos editáveis de cada página, com IDs reais, tipos, opções e defaults — base para refatorar a prévia HTML como espelho fiel do PJE-Calc.",
        "",
    ]
    for key, p in catalogo.get("paginas", {}).items():
        lines.append(f"## {key} — {p.get('pagina', key)}")
        lines.append("")
        if "erro" in p:
            lines.append(f"⚠️ Erro ao catalogar: `{p['erro']}`")
            lines.append("")
            continue
        lines.append(f"- URL: `{p.get('url','')}`")
        n_linhas_oc = p.get("linhas_ocorrencias_listagem", 0)
        if n_linhas_oc:
            lines.append(f"- Linhas de ocorrências (`:ativo`): **{n_linhas_oc}**")
        lines.append("")
        # Tabela de campos
        campos = [c for c in p.get("campos", []) if c.get("type") not in ("hidden", "button", "submit")]
        if campos:
            lines.append("### Campos editáveis")
            lines.append("")
            lines.append("| ID | Tipo | Label | Default | Opções/Detalhes |")
            lines.append("|---|---|---|---|---|")
            for c in campos:
                opts = ""
                if c.get("opcoes"):
                    sel_opt = next((o for o in c["opcoes"] if o.get("selected")), None)
                    opts = "; ".join(f"`{o['v']}`={o['l'][:30]}" for o in c["opcoes"][:6])
                    if len(c["opcoes"]) > 6:
                        opts += f"; … (+{len(c['opcoes'])-6})"
                disabled = "🔒" if c.get("disabled") or c.get("readonly") else ""
                visivel = "" if c.get("visivel", True) else "👻"
                lines.append(
                    f"| `{c['id']}` {disabled}{visivel} "
                    f"| {c.get('type','?')} "
                    f"| {(c.get('label') or '')[:40]} "
                    f"| {(c.get('value_default') or '')[:30]} "
                    f"| {opts[:100]} |"
                )
            lines.append("")
        # Radios agrupados
        radios = p.get("radios_agrupados") or []
        if radios:
            lines.append("### Radios (grupos)")
            lines.append("")
            for r in radios:
                opcoes_txt = ", ".join(f"`{o['v']}`" + ("✓" if o.get("checked") else "") for o in r.get("opcoes", []))
                lines.append(f"- `{r['grupo']}`: {opcoes_txt}")
            lines.append("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
