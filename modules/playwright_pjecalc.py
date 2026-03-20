# modules/playwright_pjecalc.py — Automação Playwright para PJE-Calc Cidadão
#
# Inicia o PJE-Calc Cidadão (localhost:9257) via subprocess e preenche os
# formulários JSF/RichFaces com Playwright.  O browser fica visível ao usuário.
#
# Uso:
#   from modules.playwright_pjecalc import iniciar_e_preencher
#   iniciar_e_preencher(dados, verbas_mapeadas, sessao_id, progresso_callback)

from __future__ import annotations

import re
import socket
import subprocess
import time
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Verificação e inicialização do PJE-Calc ───────────────────────────────────

def pjecalc_rodando() -> bool:
    """Retorna True se o Tomcat do PJE-Calc já está ouvindo na porta 9257."""
    try:
        s = socket.create_connection(("127.0.0.1", 9257), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def iniciar_pjecalc(pjecalc_dir: str | Path, timeout: int = 90) -> None:
    """
    Inicia o PJE-Calc Cidadão via iniciarPjeCalc.bat se não estiver rodando.
    Aguarda até `timeout` segundos o Tomcat responder na porta 9257.
    """
    dir_path = Path(pjecalc_dir)
    bat = dir_path / "iniciarPjeCalc.bat"
    if not bat.exists():
        raise FileNotFoundError(
            f"iniciarPjeCalc.bat não encontrado em {dir_path}. "
            "Verifique a configuração PJECALC_DIR."
        )

    if pjecalc_rodando():
        logger.info("PJE-Calc já está rodando em localhost:9257.")
        return

    logger.info(f"Iniciando PJE-Calc Cidadão a partir de {dir_path}…")
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        cwd=str(dir_path),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    inicio = time.time()
    while time.time() - inicio < timeout:
        if pjecalc_rodando():
            logger.info("PJE-Calc disponível em localhost:9257.")
            time.sleep(3)   # aguarda inicialização completa do Seam/JSF
            return
        time.sleep(2)

    raise TimeoutError(
        f"PJE-Calc não ficou disponível em {timeout}s. "
        "Verifique se o Java está instalado corretamente."
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
    Todas as interações são via seletores JSF/RichFaces.
    """

    PJECALC_BASE = "http://localhost:9257/pjecalc"

    def __init__(self, log_cb: Callable[[str], None] | None = None):
        self._log_cb = log_cb or (lambda msg: None)
        self._pw = None
        self._browser = None
        self._page = None

    # ── Ciclo de vida ──────────────────────────────────────────────────────────

    def iniciar_browser(self) -> None:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(
            headless=False,
            slow_mo=200,
            args=["--start-maximized"],
        )
        ctx = self._browser.new_context(no_viewport=True)
        self._page = ctx.new_page()

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

    # ── Primitivas DOM ─────────────────────────────────────────────────────────

    def _seletores_campo(self, field_id: str) -> list[str]:
        """Gera lista de seletores para um campo JSF/RichFaces."""
        return [
            f"[id='formulario:{field_id}_input']",   # RichFaces calendar
            f"[id='formulario:{field_id}']",
            f"input[id$=':{field_id}']",
            f"input[id$='{field_id}']",
            f"textarea[id$='{field_id}']",
        ]

    def _aguardar_seletor(self, seletor: str, timeout: int = 5000):
        try:
            self._page.wait_for_selector(seletor, timeout=timeout, state="attached")
            return self._page.query_selector(seletor)
        except Exception:
            return None

    def _preencher(self, field_id: str, valor: str, obrigatorio: bool = True) -> bool:
        """Preenche um campo de input JSF."""
        if not valor:
            return False
        for sel in self._seletores_campo(field_id):
            el = self._aguardar_seletor(sel, 3000)
            if el:
                try:
                    el.triple_click()
                    el.type(valor, delay=30)
                    el.dispatch_event("input")
                    el.dispatch_event("change")
                    el.dispatch_event("blur")
                    self._log(f"  ✓ {field_id}: {valor}")
                    return True
                except Exception:
                    continue
        if obrigatorio:
            self._log(f"  ⚠ {field_id}: campo não encontrado — preencha manualmente.")
        return False

    def _preencher_data(self, field_id: str, data: str) -> bool:
        """Preenche campos de data (RichFaces calendar usa _input)."""
        return self._preencher(field_id, data)

    def _selecionar(self, field_id: str, valor: str) -> bool:
        """Seleciona opção em um <select> JSF."""
        seletores = [
            f"[id='formulario:{field_id}']",
            f"select[id$=':{field_id}']",
            f"select[id$='{field_id}']",
        ]
        for sel in seletores:
            el = self._aguardar_seletor(sel, 3000)
            if el:
                try:
                    tag = el.evaluate("e => e.tagName.toLowerCase()")
                    if tag == "select":
                        # Tenta por label (texto visível) e por value
                        try:
                            el.select_option(label=valor)
                        except Exception:
                            el.select_option(value=valor)
                        el.dispatch_event("change")
                        self._log(f"  ✓ select {field_id}: {valor}")
                        return True
                except Exception:
                    continue
        self._log(f"  ⚠ select {field_id}: não encontrado — selecione manualmente.")
        return False

    def _marcar_radio(self, field_id: str, valor: str) -> bool:
        """Clica em um radio button JSF."""
        seletores = [
            f"[id='formulario:{field_id}'] input[value='{valor}']",
            f"table[id='formulario:{field_id}'] input[value='{valor}']",
            f"input[name$='{field_id}'][value='{valor}']",
        ]
        for sel in seletores:
            el = self._aguardar_seletor(sel, 3000)
            if el:
                el.click()
                self._log(f"  ✓ radio {field_id}: {valor}")
                return True
        return False

    def _marcar_checkbox(self, field_id: str, marcar: bool = True) -> bool:
        """Marca ou desmarca um checkbox JSF."""
        seletores = [
            f"[id='formulario:{field_id}']",
            f"input[id$=':{field_id}']",
            f"input[id$='{field_id}']",
        ]
        for sel in seletores:
            el = self._aguardar_seletor(sel, 3000)
            if el:
                try:
                    tipo = el.evaluate("e => e.type")
                    if tipo == "checkbox":
                        atual = el.is_checked()
                        if atual != marcar:
                            el.click()
                        return True
                except Exception:
                    continue
        return False

    def _clicar_menu_lateral(self, texto: str) -> None:
        """Clica em um link do menu lateral pelo texto."""
        time.sleep(0.5)
        self._page.evaluate(f"""
            const links = document.querySelectorAll('a');
            for (const a of links) {{
                if (a.textContent.trim().toLowerCase().includes('{texto.lower()}')) {{
                    a.click(); break;
                }}
            }}
        """)
        time.sleep(1.5)

    def _clicar_aba(self, aba_id: str) -> None:
        """Clica em uma aba RichFaces."""
        seletores = [
            f"[id='formulario:{aba_id}_lbl']",
            f"#formulario\\:{aba_id}_lbl",
            f"[id$='{aba_id}_lbl']",
        ]
        for sel in seletores:
            el = self._aguardar_seletor(sel, 4000)
            if el:
                el.click()
                time.sleep(0.8)
                return

    def _clicar_salvar(self) -> None:
        seletores = [
            "[id='formulario:salvar']",
            "[id='formulario:btnSalvar']",
            "input[value='Salvar']",
            "button[id*='salvar']",
        ]
        for sel in seletores:
            el = self._aguardar_seletor(sel, 4000)
            if el:
                el.click()
                time.sleep(1.5)
                return
        self._log("  ⚠ Botão Salvar não encontrado — clique manualmente.")

    def _clicar_novo(self) -> None:
        seletores = [
            "[id='formulario:novo']",
            "[id='formulario:btnNovo']",
            "input[value='Novo']",
            "button[id*='novo']",
            ".sprite-novo",
        ]
        for sel in seletores:
            el = self._aguardar_seletor(sel, 4000)
            if el:
                el.click()
                time.sleep(0.8)
                return

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
            div.innerHTML = '<span style="font-size:22px">⚠️</span>' +
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
            # Aguarda o usuário clicar em Continuar (até 10 minutos)
            self._page.wait_for_selector("#pjecalc-agente-overlay", state="detached", timeout=600000)
        except Exception:
            pass

    def _verificar_e_fazer_login(self) -> None:
        """Verifica se está logado; se não, tenta credenciais padrão ou aguarda usuário."""
        url = self._page.url
        if "logon" not in url.lower():
            return

        self._log("Página de login detectada — tentando credenciais padrão…")

        # Credenciais padrão comuns do PJE-Calc Cidadão
        for usuario, senha in [("admin", "pjeadmin"), ("admin", "admin"), ("pjecalc", "pjecalc"), ("advogado", "advogado")]:
            try:
                sel_user = "input[name*='usuario'], input[id*='usuario'], input[type='text'][name*='j_'], input[name*='j_username']"
                sel_pwd  = "input[type='password']"
                sel_btn  = "input[type='submit'], button[type='submit'], input[value*='ntrar'], input[value*='ogar']"

                self._page.fill(sel_user, usuario, timeout=2000)
                self._page.fill(sel_pwd, senha, timeout=2000)
                self._page.click(sel_btn, timeout=2000)
                time.sleep(2)

                if "logon" not in self._page.url.lower():
                    self._log(f"Login automático com '{usuario}' — OK.")
                    return
            except Exception:
                continue

        # Aguarda login manual
        self._aguardar_usuario(
            "Faça o login no PJE-Calc e clique em <strong>Continuar</strong>."
        )

    # ── Navegação principal ────────────────────────────────────────────────────

    def _ir_para_calculo_externo(self) -> None:
        """Navega para a tela de Cálculo Externo (novo cálculo)."""
        self._log("Navegando para Cálculo Externo…")
        # Tenta pelo menu lateral
        self._clicar_menu_lateral("Cálculo Externo")
        time.sleep(1)
        # Se não funcionou, navega diretamente
        if "calculo" not in self._page.url.lower():
            self._page.goto(
                f"{self.PJECALC_BASE}/pages/calculo/calculoExterno.jsf",
                wait_until="domcontentloaded",
            )
            time.sleep(1.5)

    # ── Fase 1: Dados do Processo + Parâmetros ─────────────────────────────────

    def fase_dados_processo(self, dados: dict) -> None:
        self._log("Fase 1 — Dados do processo…")
        proc = dados.get("processo", {})
        cont = dados.get("contrato", {})
        pres = dados.get("prescricao", {})
        avp  = dados.get("aviso_previo", {})

        self._clicar_aba("tabDadosProcesso")
        time.sleep(0.5)

        # Número do processo
        num = _parsear_numero_processo(proc.get("numero"))
        if num:
            self._preencher("numero", num.get("numero", ""), False)
            self._preencher("digito", num.get("digito", ""), False)
            self._preencher("ano", num.get("ano", ""), False)
            self._preencher("justica", num.get("justica", ""), False)
            self._preencher("regiao", num.get("regiao", ""), False)
            self._preencher("vara", num.get("vara", ""), False)

        # Partes
        if proc.get("reclamante"):
            self._preencher("reclamanteNome", proc["reclamante"])
        if proc.get("reclamado"):
            self._preencher("reclamadoNome", proc["reclamado"])

        # Documentos fiscais
        if proc.get("cpf_reclamante"):
            self._marcar_radio("documentoFiscalReclamante", "CPF")
            self._preencher("reclamanteNumeroDocumentoFiscal", proc["cpf_reclamante"], False)
        if proc.get("cnpj_reclamado"):
            self._marcar_radio("tipoDocumentoFiscalReclamado", "CNPJ")
            self._preencher("reclamadoNumeroDocumentoFiscal", proc["cnpj_reclamado"], False)

        # Tab: Parâmetros do Cálculo
        self._log("  → Aba Parâmetros do Cálculo…")
        self._clicar_aba("tabParametrosCalculo")
        time.sleep(0.5)

        if cont.get("admissao"):
            self._preencher_data("dataAdmissao", cont["admissao"])
        if cont.get("demissao"):
            self._preencher_data("dataDemissao", cont["demissao"])
        if cont.get("ajuizamento"):
            self._preencher_data("dataAjuizamento", cont["ajuizamento"])

        if cont.get("ultima_remuneracao"):
            self._preencher("valorUltimaRemuneracao", _fmt_br(cont["ultima_remuneracao"]))
        if cont.get("maior_remuneracao"):
            self._preencher("valorMaiorRemuneracao", _fmt_br(cont["maior_remuneracao"]), False)
        if cont.get("carga_horaria"):
            self._preencher("valorCargaHorariaPadrao", str(cont["carga_horaria"]), False)

        regime_map = {
            "Tempo Integral": "INTEGRAL",
            "Tempo Parcial": "PARCIAL",
            "Trabalho Intermitente": "INTERMITENTE",
        }
        regime = regime_map.get(cont.get("regime", "Tempo Integral"), "INTEGRAL")
        self._selecionar("regimeDoContrato", regime)

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

    def fase_historico_salarial(self, dados: dict) -> None:
        self._log("Fase 2 — Histórico salarial…")
        hist_lista = dados.get("historico_salarial") or []

        if not hist_lista:
            # Fallback: usar salário único a partir de ultima_remuneracao
            cont = dados.get("contrato", {})
            sal = cont.get("ultima_remuneracao") or cont.get("maior_remuneracao")
            adm = cont.get("admissao")
            dem = cont.get("demissao")
            if sal and adm:
                hist_lista = [{"nome": "BASE DE CÁLCULO", "valor": sal, "data_inicio": adm, "data_fim": dem or adm}]

        if not hist_lista:
            self._log("  Sem histórico salarial — fase ignorada.")
            return

        self._clicar_menu_lateral("Histórico Salarial")

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

    def fase_verbas(self, verbas_mapeadas: dict) -> None:
        self._log("Fase 3 — Verbas…")
        self._clicar_menu_lateral("Verbas")

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

        # Verbas não reconhecidas
        nao_rec = verbas_mapeadas.get("nao_reconhecidas", [])
        if nao_rec:
            nomes = ", ".join(v.get("nome_sentenca", "?") for v in nao_rec)
            self._aguardar_usuario(
                f"As verbas <strong>{nomes}</strong> não foram mapeadas. "
                "Adicione-as manualmente e clique em <strong>Continuar</strong>."
            )

        self._log("Fase 3 concluída.")

    # ── Fase 4: FGTS ──────────────────────────────────────────────────────────

    def fase_fgts(self, fgts: dict) -> None:
        self._log("Fase 4 — FGTS…")
        self._clicar_menu_lateral("FGTS")

        aliquota = fgts.get("aliquota", 0.08)
        pct = round(aliquota * 100)
        # Seleciona alíquota por texto na tabela
        self._page.evaluate(f"""
            const tds = document.querySelectorAll('td');
            for (const td of tds) {{
                if (td.textContent.trim() === '{pct}%') {{ td.click(); break; }}
            }}
        """)
        time.sleep(0.3)

        if fgts.get("multa_40"):
            self._marcar_checkbox("multa", True)
        if fgts.get("multa_467"):
            self._marcar_checkbox("multaDoArtigo467", True)

        self._clicar_salvar()
        self._log("Fase 4 concluída.")

    # ── Fase 5: Contribuição Social (INSS) ────────────────────────────────────

    def fase_contribuicao_social(self, cs: dict) -> None:
        self._log("Fase 5 — Contribuição Social…")
        self._clicar_menu_lateral("Contribuição Social")

        resp_map = {"Empregado": "EMPREGADO", "Empregador": "EMPREGADOR", "Ambos": "AMBOS"}
        resp = resp_map.get(cs.get("responsabilidade", "Ambos"), "AMBOS")
        self._selecionar("responsabilidade", resp)

        if cs.get("lei_11941"):
            self._marcar_checkbox("lei11941", True)

        self._clicar_salvar()
        self._log("Fase 5 concluída.")

    # ── Fase 6: Parâmetros de Atualização ─────────────────────────────────────

    def fase_parametros_atualizacao(self, cj: dict) -> None:
        self._log("Fase 6 — Parâmetros de atualização…")
        self._clicar_menu_lateral("Parâmetros de Atualização")

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

    def fase_irpf(self, ir: dict) -> None:
        if not ir.get("apurar"):
            self._log("Fase 7 — IRPF ignorado (não apurar).")
            return

        self._log("Fase 7 — IRPF…")
        self._clicar_menu_lateral("Imposto de Renda")
        self._marcar_checkbox("apurarImpostoRenda", True)

        if ir.get("meses_tributaveis"):
            self._preencher("qtdMesesRendimento", str(ir["meses_tributaveis"]), False)
        if ir.get("dependentes"):
            self._marcar_checkbox("possuiDependentes", True)
            self._preencher("quantidadeDependentes", str(ir["dependentes"]), False)

        self._clicar_salvar()
        self._log("Fase 7 concluída.")

    # ── Fase 8: Honorários ────────────────────────────────────────────────────

    def fase_honorarios(self, hon: dict) -> None:
        if not hon.get("percentual") and not hon.get("valor_fixo") and not hon.get("periciais"):
            self._log("Fase 8 — Honorários ignorados (sem dados).")
            return

        self._log("Fase 8 — Honorários…")
        self._clicar_menu_lateral("Honorários")
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
        self._page.goto(base, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

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


# ── Função pública ─────────────────────────────────────────────────────────────

def iniciar_e_preencher(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
    pjecalc_dir: str | Path,
    log_cb: Callable[[str], None] | None = None,
) -> None:
    """
    Ponto de entrada público.
    1. Inicia PJE-Calc Cidadão (se não estiver rodando).
    2. Abre Playwright browser (visível).
    3. Preenche todos os campos do cálculo.
    """
    cb = log_cb or (lambda m: None)

    cb("Verificando PJE-Calc Cidadão…")
    iniciar_pjecalc(pjecalc_dir)
    cb("PJE-Calc disponível.")

    agente = PJECalcPlaywright(log_cb=cb)
    try:
        agente.iniciar_browser()
        agente.preencher_calculo(dados, verbas_mapeadas)
        # Browser permanece aberto para o usuário revisar e clicar Liquidar
    except Exception as exc:
        cb(f"ERRO: {exc}")
        logger.exception(f"Erro na automação Playwright: {exc}")
        raise
