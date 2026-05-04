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
        """Executa pipeline completo. Retorna caminho do .PJC ou None."""
        self.log("══ Iniciando automação v2 ══")
        self._abrir_pjecalc()
        self._criar_novo_calculo()

        # Fases (sequência ordenada)
        self.fase_processo()
        self.fase_parametros_calculo()
        self.fase_historico_salarial()
        self.fase_verbas()
        if self.previa.cartao_de_ponto:
            self.fase_cartao_de_ponto()
        if self.previa.faltas:
            self.fase_faltas()
        if self.previa.ferias.periodos:
            self.fase_ferias()
        self.fase_fgts()
        self.fase_contribuicao_social()
        self.fase_imposto_de_renda()
        if self.previa.honorarios:
            self.fase_honorarios()
        self.fase_custas_judiciais()
        self.fase_correcao_juros_multa()

        # Liquidação
        return self.fase_liquidar_e_exportar()

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

    def _marcar_radio(self, dom_id: str, valor: str) -> None:
        sel = f"input[type='radio'][id*='{dom_id}'][value='{valor}']"
        loc = self._page.locator(sel)
        if loc.count() == 0:
            raise RuntimeError(f"Radio não encontrado: {dom_id}={valor}")
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

    def _selecionar(self, dom_id: str, valor: str) -> None:
        loc = self._page.locator(f"select[id$='{dom_id}']")
        if loc.count() == 0:
            raise RuntimeError(f"Select não encontrado: {dom_id}")
        try:
            loc.first.select_option(value=valor)
        except Exception:
            loc.first.select_option(label=valor)
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

        # 4c. Pós-Expresso: navegar à listagem + ajustar parâmetros + reflexos
        # Após o save do Expresso, página fica em verbas-para-calculo.jsf — precisa
        # forçar nav para verba-calculo.jsf para ver o listing das criadas.
        if verbas_expresso:
            self._navegar_menu("li_calculo_verbas")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(2000)

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
            self.log(f"  ⚠ Verba não encontrada na listagem ou sem link Parâmetros: {v.nome_pjecalc}")
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

    def _configurar_reflexo(self, verba_principal, reflexo) -> None:
        """Marcar checkbox do reflexo no painel da verba principal."""
        if reflexo.estrategia_reflexa == EstrategiaReflexa.MANUAL:
            self.log(f"  → Reflexo MANUAL: {reflexo.nome} (não implementado nesta versão)")
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

        self._clicar("salvar")
        self._aguardar_ajax(8000)
        self.log("Fase 5 concluída")

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
        f = self.previa.fgts
        self._marcar_radio("tipoDeVerba", f.tipo_verba)
        self._marcar_radio("comporPrincipal", f.compor_principal.value)
        self._marcar_checkbox("multa", f.multa.ativa)
        if f.multa.ativa:
            self._marcar_radio("tipoDoValorDaMulta", f.multa.tipo_valor)
            self._marcar_radio("multaDoFgts", f.multa.percentual)
        self._selecionar("incidenciaDoFgts", f.incidencia)
        self._marcar_checkbox("multaDoArtigo467", f.multa_artigo_467)
        self._marcar_checkbox("multa10", f.multa_10_lc110)
        self._clicar("salvar")
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
        nav_ok = self._page.evaluate(
            """() => {
                const links = [...document.querySelectorAll('a')];
                for (const a of links) {
                    const txt = (a.textContent || '').trim();
                    const li = a.closest('li');
                    if (txt === 'Liquidar' && li && li.id && li.id.includes('operacoes')) {
                        a.click();
                        return true;
                    }
                }
                return false;
            }"""
        )
        if not nav_ok:
            raise RuntimeError("Sidebar 'Liquidar' não localizado")
        self._aguardar_ajax(15000)

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

        # ── 14d. Navegar para Exportar ─────────────────────────────────────
        nav_exp = self._page.evaluate(
            """() => {
                const li = document.getElementById('li_operacoes_exportar');
                if (!li) return false;
                const a = li.querySelector('a');
                if (!a) return false;
                a.click();
                return true;
            }"""
        )
        if not nav_exp:
            raise RuntimeError("Sidebar 'Exportar' não localizado")
        self._aguardar_ajax(15000)

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
            with self._page.expect_response(
                lambda r: (
                    "exportacao.jsf" in r.url
                    and r.request.method == "POST"
                    and (
                        "zip" in (r.headers.get("content-type") or "").lower()
                        or ".pjc" in (r.headers.get("content-disposition") or "").lower()
                    )
                ),
                timeout=60000,
            ) as resp_info:
                # Clicar botão Exportar (input[type=submit] id termina em :exportar)
                btn = self._page.locator("input[type='submit'][id$=':exportar']").first
                btn.click()
            resp = resp_info.value
            pjc_bytes = resp.body()
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
