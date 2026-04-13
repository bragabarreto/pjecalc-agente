# modules/automation.py — Automação de Interface do PJE-Calc
# Manual Técnico PJE-Calc, Seção 6

from __future__ import annotations

import time
import logging
from pathlib import Path
from typing import Any, Callable

from config import (
    AUTOMATION_BACKEND,
    PJECALC_WINDOW_TITLE,
    WAIT_AFTER_CLICK,
    WAIT_AFTER_SAVE,
    WAIT_AFTER_NAVIGATE,
    WAIT_TIMEOUT_FIELD,
    WAIT_RETRIES,
    DATE_FORMAT_PJECALC,
)

logger = logging.getLogger(__name__)


# ── Motor de Automação ────────────────────────────────────────────────────────

class PJECalcAutomation:
    """
    Encapsula todas as operações de automação de interface do PJE-Calc.
    Suporta PyAutoGUI (desktop/Cidadão) e Playwright (web/corporativo).
    Manual Técnico, Seção 6.1 e 6.2.
    """

    def __init__(
        self,
        backend: str = AUTOMATION_BACKEND,
        acionar_usuario: Callable[[str, list[str] | None], str] | None = None,
    ):
        self.backend = backend
        self._acionar_usuario = acionar_usuario or self._usuario_cli
        self._driver = None  # Playwright browser / pyautogui implícito
        self._log_acoes: list[dict[str, Any]] = []

        if backend == "pyautogui":
            self._init_pyautogui()
        elif backend == "playwright":
            self._init_playwright()
        else:
            raise ValueError(f"Backend não suportado: {backend}")

    # ── Inicialização ─────────────────────────────────────────────────────────

    def _init_pyautogui(self) -> None:
        try:
            import pyautogui
            pyautogui.PAUSE = WAIT_AFTER_CLICK
            pyautogui.FAILSAFE = True
            self._gui = pyautogui
        except ImportError:
            raise ImportError("Instale pyautogui: pip install pyautogui pygetwindow pillow")

    def _init_playwright(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
            self._playwright_ctx = sync_playwright().__enter__()
            self._driver = self._playwright_ctx.firefox.launch(headless=False)
        except ImportError:
            raise ImportError("Instale playwright: pip install playwright && playwright install firefox")

    def fechar(self) -> None:
        if self.backend == "playwright" and self._driver:
            self._driver.close()

    # ── Navegação principal ───────────────────────────────────────────────────

    def focar_janela_pjecalc(self) -> bool:
        """Garante que o PJE-Calc está em primeiro plano (desktop)."""
        if self.backend != "pyautogui":
            return True
        try:
            import pygetwindow as gw
            janelas = gw.getWindowsWithTitle(PJECALC_WINDOW_TITLE)
            if not janelas:
                self._acionar_usuario(
                    "Janela do PJE-Calc não encontrada. "
                    "Por favor, abra o PJE-Calc e pressione Enter para continuar.",
                    None,
                )
                janelas = gw.getWindowsWithTitle(PJECALC_WINDOW_TITLE)
                if not janelas:
                    raise RuntimeError("PJE-Calc não foi encontrado mesmo após aguardar.")
            janelas[0].activate()
            time.sleep(WAIT_AFTER_NAVIGATE)
            return True
        except ImportError:
            logger.warning("pygetwindow não disponível; assumindo PJE-Calc em foco.")
            return True

    # ── 6.2.1 Criar Novo Cálculo ──────────────────────────────────────────────

    def criar_novo_calculo(self, dados: dict[str, Any]) -> None:
        """
        Preenche a tela de criação de novo cálculo.
        Manual, Seção 6.2.1.
        """
        self.focar_janela_pjecalc()
        processo = dados.get("processo", {})

        self._log("CRIAR_CALCULO", "inicio", None, "Iniciando criação de novo cálculo")

        # Navegar: Cálculo > Novo
        self._clicar_menu("Cálculo")
        self._clicar_opcao("Novo")
        time.sleep(WAIT_AFTER_NAVIGATE)

        # Selecionar "Manual"
        self._selecionar_radio("Dados do Processo", "Manual")

        # Preencher campos
        self._preencher_campo("Reclamante", processo.get("reclamante") or "")
        self._preencher_campo("Reclamante CPF/CNPJ", processo.get("cpf_reclamante") or "")
        self._preencher_campo("Reclamado", processo.get("reclamado") or "")
        self._preencher_campo("Reclamado CPF/CNPJ", processo.get("cnpj_reclamado") or "")
        self._preencher_campo("Número do Processo", processo.get("numero") or "")

        self._log("CRIAR_CALCULO", "concluido", None, "Campos do processo preenchidos")

    # ── 6.2.2 Parâmetros do Cálculo ───────────────────────────────────────────

    def preencher_parametros_calculo(self, dados: dict[str, Any]) -> None:
        """
        Preenche todos os campos da página Parâmetros do Cálculo.
        Manual, Seção 6.2.2. CRITICO: clicar em Salvar ao final.
        """
        contrato = dados.get("contrato", {})
        processo = dados.get("processo", {})
        prescricao = dados.get("prescricao", {})
        aviso = dados.get("aviso_previo", {})

        self._log("PARAMETROS", "inicio", None, "Preenchendo Parâmetros do Cálculo")

        # Campos obrigatórios (*)
        self._preencher_campo("Estado *", processo.get("estado") or "")
        self._preencher_campo("Município *", processo.get("municipio") or "")
        self._preencher_data("Admissão *", contrato.get("admissao") or "")
        self._preencher_data("Ajuizamento *", contrato.get("ajuizamento") or "")

        # Campos condicionais
        if contrato.get("demissao"):
            self._preencher_data("Demissão", contrato["demissao"])

        if contrato.get("maior_remuneracao"):
            self._preencher_campo(
                "Maior Remuneração",
                _fmt_valor_br(contrato["maior_remuneracao"]),
            )

        if contrato.get("ultima_remuneracao"):
            self._preencher_campo(
                "Última Remuneração",
                _fmt_valor_br(contrato["ultima_remuneracao"]),
            )

        # Regime de trabalho
        regime = contrato.get("regime") or "Tempo Integral"
        self._selecionar_opcao("Regime de Trabalho", regime)

        # Carga horária
        carga = str(contrato.get("carga_horaria") or 220)
        self._preencher_campo("Carga Horária Padrão", carga)

        # Prescrição
        if prescricao.get("quinquenal"):
            self._marcar_checkbox("Prescrição Quinquenal")
        if prescricao.get("fgts"):
            self._marcar_checkbox("Prescrição FGTS")

        # Aviso Prévio
        tipo_ap = aviso.get("tipo") or "Calculado"
        self._selecionar_opcao("Prazo do Aviso Prévio", tipo_ap)
        if aviso.get("prazo_dias") and tipo_ap == "Informado":
            self._preencher_campo("Prazo (dias)", str(aviso["prazo_dias"]))
        if aviso.get("projetar"):
            self._marcar_checkbox("Projetar Aviso Prévio Indenizado")

        # SALVAR — confirmação obrigatória
        self._salvar_com_confirmacao("Parâmetros do Cálculo")
        self._log("PARAMETROS", "concluido", None, "Parâmetros salvos com sucesso")

    # ── 6.2.3 Faltas ──────────────────────────────────────────────────────────

    def preencher_faltas(self, faltas: list[dict[str, Any]]) -> None:
        """Lança faltas se indicadas na sentença. Manual, Seção 6.2.3."""
        if not faltas:
            return

        self._navegar_menu_lateral("Faltas")

        for falta in faltas:
            self._clicar_botao("Novo")
            self._preencher_data("Data Inicial", falta.get("data_inicial") or "")
            self._preencher_data("Data Final", falta.get("data_final") or falta.get("data_inicial") or "")
            if falta.get("justificada"):
                self._marcar_checkbox("Justificada")
                self._preencher_campo("Descrição", falta.get("descricao") or "Conforme sentença")
            self._salvar_com_confirmacao("Faltas")

    # ── 6.2.4 Férias ──────────────────────────────────────────────────────────

    def verificar_ferias(self, periodos_ferias: list[dict[str, Any]]) -> None:
        """
        Verifica e corrige os períodos de férias gerados automaticamente.
        Manual, Seção 6.2.4.
        """
        self._navegar_menu_lateral("Férias")
        time.sleep(WAIT_AFTER_NAVIGATE)

        for periodo in periodos_ferias:
            situacao = periodo.get("situacao")
            if situacao:
                self._selecionar_opcao("Situação", situacao)
            if periodo.get("abono"):
                self._marcar_checkbox("Abono")
            if periodo.get("dobra"):
                self._marcar_checkbox("Dobra")
            if periodo.get("periodo_gozo_inicio"):
                self._preencher_data("Período de Gozo Início", periodo["periodo_gozo_inicio"])
            if periodo.get("periodo_gozo_fim"):
                self._preencher_data("Período de Gozo Fim", periodo["periodo_gozo_fim"])

        self._salvar_com_confirmacao("Férias")

    # ── 6.2.5 Histórico Salarial ──────────────────────────────────────────────

    def preencher_historico_salarial(
        self, bases: list[dict[str, Any]]
    ) -> None:
        """
        Lança as bases de cálculo mês a mês.
        Manual, Seção 6.2.5.
        """
        self._navegar_menu_lateral("Histórico Salarial")

        for base in bases:
            self._clicar_botao("Novo")
            self._preencher_campo("Nome", base.get("nome") or "Salário Mensal")

            if base.get("incidencia_fgts"):
                self._marcar_checkbox("Incidência no FGTS")
            if base.get("incidencia_inss"):
                self._marcar_checkbox("Incidência na Contribuição Social")

            tipo_valor = base.get("tipo_valor") or "Informado"
            self._selecionar_opcao("Tipo de Valor", tipo_valor)

            if tipo_valor == "Informado" and base.get("valores_mensais"):
                self._clicar_botao("Gerar Ocorrências")
                time.sleep(WAIT_AFTER_NAVIGATE)
                for ocorrencia in base["valores_mensais"]:
                    self._preencher_campo(
                        f"Valor {ocorrencia['mes_ano']}",
                        _fmt_valor_br(ocorrencia["valor"]),
                    )

            self._salvar_com_confirmacao(f"Histórico Salarial — {base.get('nome')}")

    # ── 6.2.6 Verbas ─────────────────────────────────────────────────────────

    def preencher_verbas(
        self,
        verbas_mapeadas: dict[str, Any],
    ) -> None:
        """
        Lança todas as verbas: primeiro Expresso, depois Manual.
        Manual, Seção 6.2.6.
        """
        self._navegar_menu_lateral("Verbas")

        # Lançamento Expresso para verbas pré-definidas
        predefinidas = verbas_mapeadas.get("predefinidas", [])
        if predefinidas:
            self._lancamento_expresso(predefinidas)

        # Lançamento Manual para verbas personalizadas
        personalizadas = verbas_mapeadas.get("personalizadas", [])
        for verba in personalizadas:
            self._lancamento_manual_verba(verba)

        # Verbas não reconhecidas — reportar ao usuário
        nao_rec = verbas_mapeadas.get("nao_reconhecidas", [])
        if nao_rec:
            nomes = ", ".join(v.get("nome_sentenca", "?") for v in nao_rec)
            self._acionar_usuario(
                f"As seguintes verbas não foram reconhecidas e precisam "
                f"ser lançadas manualmente no PJE-Calc:\n{nomes}\n\n"
                "Pressione Enter após lançá-las para continuar.",
                None,
            )

    def _lancamento_expresso(self, verbas: list[dict[str, Any]]) -> None:
        """Seleciona verbas no Lançamento Expresso."""
        self._clicar_opcao("Expresso")
        time.sleep(WAIT_AFTER_NAVIGATE)
        for verba in verbas:
            nome = verba.get("nome_pjecalc") or verba.get("nome_sentenca", "")
            self._marcar_checkbox(nome)
        self._salvar_com_confirmacao("Lançamento Expresso")

    def _lancamento_manual_verba(self, verba: dict[str, Any]) -> None:
        """Preenche uma verba via Lançamento Manual."""
        self._clicar_opcao("Manual")
        time.sleep(WAIT_AFTER_NAVIGATE)

        self._preencher_campo("Nome", verba.get("nome_pjecalc") or verba.get("nome_sentenca") or "")
        self._selecionar_opcao("Característica", verba.get("caracteristica") or "Comum")
        self._selecionar_opcao("Ocorrência de Pagamento", verba.get("ocorrencia") or "Mensal")
        self._selecionar_opcao("Tipo", verba.get("tipo") or "Principal")

        if verba.get("valor_informado"):
            self._selecionar_opcao("Valor", "Informado")
            self._preencher_campo("Valor", _fmt_valor_br(verba["valor_informado"]))
        else:
            self._selecionar_opcao("Valor", "Calculado")
            if verba.get("base_calculo"):
                self._selecionar_opcao("Base de Cálculo", verba["base_calculo"])
            if verba.get("percentual"):
                self._preencher_campo("Multiplicador", _fmt_valor_br(verba["percentual"]))

        if verba.get("incidencia_fgts"):
            self._marcar_checkbox("Incidência FGTS")
        if verba.get("incidencia_inss"):
            self._marcar_checkbox("Incidência Contrib. Social")
        if verba.get("incidencia_ir"):
            self._marcar_checkbox("Incidência IRPF")

        if verba.get("periodo_inicio"):
            self._preencher_data("Período Início", verba["periodo_inicio"])
        if verba.get("periodo_fim"):
            self._preencher_data("Período Fim", verba["periodo_fim"])

        if verba.get("compor_principal") is not None:
            val = "Sim" if verba["compor_principal"] else "Não"
            self._selecionar_opcao("Compor Principal", val)

        if verba.get("assunto_cnj_sugerido"):
            self._preencher_campo("Assunto CNJ", verba["assunto_cnj_sugerido"])

        self._salvar_com_confirmacao(f"Verba: {verba.get('nome_pjecalc')}")

    # ── 6.2.7 FGTS ───────────────────────────────────────────────────────────

    def preencher_fgts(self, dados_fgts: dict[str, Any]) -> None:
        """Manual, Seção 6.2.7."""
        self._navegar_menu_lateral("FGTS")

        aliquota = dados_fgts.get("aliquota") or 0.08
        self._preencher_campo("Alíquota", _fmt_valor_br(aliquota * 100))

        if dados_fgts.get("multa_40"):
            self._marcar_checkbox("Multa 40%")
        if dados_fgts.get("multa_467"):
            self._marcar_checkbox("Multa Art. 467 CLT")

        self._salvar_com_confirmacao("FGTS")

    # ── 6.2.8 Contribuição Social ─────────────────────────────────────────────

    def preencher_contribuicao_social(self, dados_cs: dict[str, Any]) -> None:
        """Manual, Seção 6.2.8."""
        self._navegar_menu_lateral("Contribuição Social")

        responsabilidade = dados_cs.get("responsabilidade") or "Ambos"
        self._selecionar_opcao("Responsabilidade", responsabilidade)

        if dados_cs.get("lei_11941"):
            self._marcar_checkbox("Lei 11.941/2009")

        self._salvar_com_confirmacao("Contribuição Social")

    # ── 6.2.9 Imposto de Renda ────────────────────────────────────────────────

    def preencher_imposto_renda(self, dados_ir: dict[str, Any]) -> None:
        """Manual, Seção 6.2.9."""
        if not dados_ir.get("apurar"):
            return

        self._navegar_menu_lateral("Imposto de Renda")
        self._marcar_checkbox("Apurar Imposto de Renda")

        if dados_ir.get("meses_tributaveis"):
            self._preencher_campo("Quantidade de Meses", str(dados_ir["meses_tributaveis"]))
        if dados_ir.get("dependentes"):
            self._preencher_campo("Dedução por Dependente", str(dados_ir["dependentes"]))

        self._salvar_com_confirmacao("Imposto de Renda")

    # ── 6.2.10 Multas e Indenizações ──────────────────────────────────────────

    def preencher_multas_indenizacoes(
        self, verbas_indenizacoes: list[dict[str, Any]]
    ) -> None:
        """Manual, Seção 6.2.10."""
        for verba in verbas_indenizacoes:
            if verba.get("pagina_pjecalc") != "Multas e Indenizacoes":
                continue
            self._navegar_menu_lateral("Multas e Indenizações")
            self._clicar_botao("Novo")
            self._preencher_campo("Nome", verba.get("nome_pjecalc") or "")
            if verba.get("valor_informado"):
                self._preencher_campo("Valor Informado", _fmt_valor_br(verba["valor_informado"]))
            if verba.get("assunto_cnj_sugerido"):
                self._preencher_campo("Assunto CNJ", verba["assunto_cnj_sugerido"])
            self._salvar_com_confirmacao(f"Indenização: {verba.get('nome_pjecalc')}")

    # ── 6.2.11 Honorários ─────────────────────────────────────────────────────

    def preencher_honorarios(self, dados_hon: dict[str, Any]) -> None:
        """Manual, Seção 6.2.11."""
        if not dados_hon.get("percentual") and not dados_hon.get("valor_fixo"):
            return

        self._navegar_menu_lateral("Honorários")

        if dados_hon.get("parte_devedora"):
            self._selecionar_opcao("Parte Devedora", dados_hon["parte_devedora"])

        if dados_hon.get("percentual"):
            self._selecionar_opcao("Base de Cálculo", "Valor da condenação")
            self._preencher_campo("Percentual", _fmt_valor_br(dados_hon["percentual"] * 100))
        elif dados_hon.get("valor_fixo"):
            self._preencher_campo("Valor Fixo", _fmt_valor_br(dados_hon["valor_fixo"]))

        if dados_hon.get("periciais"):
            self._preencher_campo("Honorários Periciais", _fmt_valor_br(dados_hon["periciais"]))

        self._salvar_com_confirmacao("Honorários Advocatícios")

    # ── 6.2.12 Correção, Juros e Multa ───────────────────────────────────────

    def preencher_correcao_juros(self, dados_cj: dict[str, Any]) -> None:
        """Manual, Seção 6.2.12."""
        self._navegar_menu_lateral("Correção, Juros e Multa")

        indice = dados_cj.get("indice_correcao") or "TUACDT"
        self._selecionar_opcao("Índice de Correção Monetária", indice)

        taxa = dados_cj.get("taxa_juros") or "JUROS_PADRAO"
        self._selecionar_opcao("Juros de Mora", taxa)

        base = dados_cj.get("base_juros") or "Verbas"
        self._selecionar_opcao("Base dos Juros", base)

        if dados_cj.get("jam_fgts"):
            self._marcar_checkbox("Índice JAM (FGTS)")

        self._salvar_com_confirmacao("Correção, Juros e Multa")

    # ── Verificação pós-ação (Manual, Seção 6.3) ──────────────────────────────

    def _verificar_apos_salvar(self) -> bool:
        """Captura screenshot e verifica ausência de erro após Salvar."""
        time.sleep(WAIT_AFTER_SAVE)
        screenshot = self._capturar_screenshot()

        if self._detectar_erro_na_tela(screenshot):
            msg_erro = self._extrair_texto_erro(screenshot)
            self._acionar_usuario(
                f"Erro detectado ao salvar: {msg_erro}\n"
                "Corrija o problema e pressione Enter para continuar.",
                None,
            )
            return False

        logger.info("Salvar verificado com sucesso.")
        return True

    # ── Primitivas de interface ───────────────────────────────────────────────

    def _preencher_campo(self, nome: str, valor: str) -> None:
        """Localiza e preenche um campo de texto."""
        self._log("PREENCHER_CAMPO", "tentando", valor, f"Campo: {nome}")
        for tentativa in range(WAIT_RETRIES):
            try:
                if self.backend == "pyautogui":
                    self._pyautogui_preencher(nome, valor)
                else:
                    self._playwright_preencher(nome, valor)
                self._log("PREENCHER_CAMPO", "ok", valor, f"Campo '{nome}' preenchido")
                return
            except Exception as e:
                if tentativa == WAIT_RETRIES - 1:
                    self._acionar_usuario(
                        f"Campo '{nome}' não encontrado após {WAIT_RETRIES} tentativas.\n"
                        f"Preencha manualmente e pressione Enter para continuar.",
                        None,
                    )

    def _preencher_data(self, nome: str, valor: str) -> None:
        """Preenche campo de data no formato DD/MM/AAAA (padrão PJE-Calc)."""
        # Garantir formato correto (barras, não traços)
        valor_formatado = valor.replace("-", "/") if valor else ""
        self._preencher_campo(nome, valor_formatado)

    def _selecionar_opcao(self, nome: str, valor: str) -> None:
        """Seleciona uma opção em combobox/dropdown."""
        self._log("SELECIONAR_OPCAO", "tentando", valor, f"Campo: {nome}")
        if self.backend == "pyautogui":
            self._pyautogui_selecionar(nome, valor)
        else:
            self._playwright_selecionar(nome, valor)

    def _selecionar_radio(self, grupo: str, opcao: str) -> None:
        """Seleciona radio button."""
        self._log("SELECIONAR_RADIO", "tentando", opcao, f"Grupo: {grupo}")
        if self.backend == "pyautogui":
            self._pyautogui_radio(grupo, opcao)
        else:
            self._playwright_radio(grupo, opcao)

    def _marcar_checkbox(self, nome: str) -> None:
        """Marca um checkbox se ainda não estiver marcado."""
        self._log("MARCAR_CHECKBOX", "tentando", True, f"Checkbox: {nome}")
        if self.backend == "pyautogui":
            self._pyautogui_checkbox(nome)
        else:
            self._playwright_checkbox(nome)

    def _clicar_menu(self, nome: str) -> None:
        """Clica em um item de menu principal."""
        self._log("CLICAR_MENU", "tentando", None, f"Menu: {nome}")
        if self.backend == "pyautogui":
            img = self._localizar_imagem_menu(nome)
            if img:
                self._gui.click(img)
        else:
            page = self._driver.pages[0]
            page.click(f"text={nome}")
        time.sleep(WAIT_AFTER_CLICK)

    def _clicar_opcao(self, nome: str) -> None:
        self._log("CLICAR_OPCAO", "tentando", None, f"Opção: {nome}")
        if self.backend == "pyautogui":
            img = self._localizar_imagem_menu(nome)
            if img:
                self._gui.click(img)
        else:
            page = self._driver.pages[0]
            page.click(f"text={nome}")
        time.sleep(WAIT_AFTER_CLICK)

    def _clicar_botao(self, nome: str) -> None:
        self._log("CLICAR_BOTAO", "tentando", None, f"Botão: {nome}")
        if self.backend == "pyautogui":
            img = self._localizar_imagem_menu(nome)
            if img:
                self._gui.click(img)
        else:
            page = self._driver.pages[0]
            page.click(f"button:has-text('{nome}')")
        time.sleep(WAIT_AFTER_CLICK)

    def _navegar_menu_lateral(self, pagina: str) -> None:
        """Clica em item do menu lateral do PJE-Calc."""
        self._log("NAVEGAR_MENU_LATERAL", "tentando", None, f"Página: {pagina}")
        if self.backend == "pyautogui":
            img = self._localizar_imagem_menu(pagina)
            if img:
                self._gui.click(img)
        else:
            page = self._driver.pages[0]
            page.click(f".menu-lateral >> text={pagina}")
        time.sleep(WAIT_AFTER_NAVIGATE)

    def _salvar_com_confirmacao(self, contexto: str) -> None:
        """
        Clica no ícone/botão Salvar com verificação posterior.
        CRITICO: registra no log antes de executar.
        """
        self._log("SALVAR", "executando", None, f"Salvando: {contexto}")
        self._clicar_botao("Salvar")
        sucesso = self._verificar_apos_salvar()
        if not sucesso:
            logger.error(f"Falha ao salvar: {contexto}")
        else:
            self._log("SALVAR", "ok", None, f"Salvo com sucesso: {contexto}")

    # ── Backends específicos (stubs — adaptar para imagens reais) ─────────────

    def _pyautogui_preencher(self, nome: str, valor: str) -> None:
        """PyAutoGUI: localiza campo por imagem/acessibilidade e preenche."""
        try:
            import pywinauto
            app = pywinauto.Desktop(backend="uia")
            janela = app.window(title_re=f".*{PJECALC_WINDOW_TITLE}.*")
            campo = janela.child_window(title=nome, control_type="Edit")
            campo.set_edit_text(valor)
        except Exception:
            # Fallback: PyAutoGUI write (requer foco correto)
            pos = self._gui.locateOnScreen(f"assets/{_sanitizar_nome(nome)}.png", confidence=0.8)
            if pos:
                self._gui.click(pos)
                self._gui.hotkey("ctrl", "a")
                self._gui.write(valor, interval=0.03)

    def _pyautogui_selecionar(self, nome: str, valor: str) -> None:
        try:
            import pywinauto
            app = pywinauto.Desktop(backend="uia")
            janela = app.window(title_re=f".*{PJECALC_WINDOW_TITLE}.*")
            combo = janela.child_window(title=nome, control_type="ComboBox")
            combo.select(valor)
        except Exception as e:
            logger.warning(f"Seleção '{nome}={valor}' falhou: {e}")

    def _pyautogui_radio(self, grupo: str, opcao: str) -> None:
        try:
            import pywinauto
            app = pywinauto.Desktop(backend="uia")
            janela = app.window(title_re=f".*{PJECALC_WINDOW_TITLE}.*")
            radio = janela.child_window(title=opcao, control_type="RadioButton")
            radio.click_input()
        except Exception as e:
            logger.warning(f"Radio '{grupo}/{opcao}' falhou: {e}")

    def _pyautogui_checkbox(self, nome: str) -> None:
        try:
            import pywinauto
            app = pywinauto.Desktop(backend="uia")
            janela = app.window(title_re=f".*{PJECALC_WINDOW_TITLE}.*")
            cb = janela.child_window(title=nome, control_type="CheckBox")
            if not cb.get_toggle_state():
                cb.toggle()
        except Exception as e:
            logger.warning(f"Checkbox '{nome}' falhou: {e}")

    def _playwright_preencher(self, nome: str, valor: str) -> None:
        page = self._driver.pages[0]
        page.fill(f"label:has-text('{nome}') + input, input[placeholder*='{nome}']", valor)

    def _playwright_selecionar(self, nome: str, valor: str) -> None:
        page = self._driver.pages[0]
        page.select_option(f"label:has-text('{nome}') + select", label=valor)

    def _playwright_radio(self, grupo: str, opcao: str) -> None:
        page = self._driver.pages[0]
        page.click(f"input[type='radio'][value='{opcao}']")

    def _playwright_checkbox(self, nome: str) -> None:
        page = self._driver.pages[0]
        cb = page.locator(f"label:has-text('{nome}') input[type='checkbox']")
        if not cb.is_checked():
            cb.check()

    # ── Utilitários de tela ───────────────────────────────────────────────────

    def _capturar_screenshot(self) -> Any:
        """Captura screenshot atual para verificação."""
        from config import SCREENSHOTS_DIR
        from datetime import datetime

        nome = SCREENSHOTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        if self.backend == "pyautogui":
            img = self._gui.screenshot()
            img.save(str(nome))
            return img
        else:
            page = self._driver.pages[0]
            page.screenshot(path=str(nome))
            return nome

    def _detectar_erro_na_tela(self, screenshot: Any) -> bool:
        """Detecta mensagens de erro na tela (stub — adaptar para imagens reais)."""
        # TODO: implementar detecção via OCR ou accessibility tree
        return False

    def _extrair_texto_erro(self, screenshot: Any) -> str:
        return "Erro desconhecido — verifique a tela do PJE-Calc."

    def _localizar_imagem_menu(self, nome: str) -> Any:
        """Tenta localizar elemento por imagem de referência."""
        try:
            pos = self._gui.locateOnScreen(
                f"assets/{_sanitizar_nome(nome)}.png",
                confidence=0.8,
            )
            return pos
        except Exception:
            return None

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, acao: str, resultado: str, valor: Any, detalhe: str) -> None:
        from datetime import datetime
        entrada = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "acao": acao,
            "resultado": resultado,
            "valor_inserido": valor,
            "detalhe": detalhe,
            "fonte": "AUTOMATICO",
        }
        self._log_acoes.append(entrada)
        logger.info(f"[{acao}] {detalhe} → {resultado}")

    def obter_log_acoes(self) -> list[dict[str, Any]]:
        return self._log_acoes

    # ── Interação CLI padrão ──────────────────────────────────────────────────

    @staticmethod
    def _usuario_cli(mensagem: str, opcoes: list[str] | None) -> str:
        print("\n" + mensagem)
        if opcoes:
            for i, op in enumerate(opcoes, 1):
                print(f"  [{i}] {op}")
        return input("Sua resposta: ").strip()


# ── Funções auxiliares ────────────────────────────────────────────────────────

def _fmt_valor_br(valor: float | int) -> str:
    """Formata valor numérico no padrão brasileiro para campos do PJE-Calc."""
    return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _sanitizar_nome(nome: str) -> str:
    """Sanitiza nome para usar como nome de arquivo de imagem."""
    import re
    return re.sub(r"[^\w]", "_", nome.lower())
