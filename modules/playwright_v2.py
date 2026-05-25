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
        sessao_id: str | None = None,
    ):
        self.previa = previa
        self.log = log_fn or (lambda m: logger.info(m))
        self.pjecalc_url = pjecalc_url
        # Sessão do app (UUID) — usado para nomear snapshots de listagem em
        # /tmp/pjecalc_snapshots/<sessao_id>_inicial.json para o endpoint
        # /api/correcao_manual_diff localizar depois.
        self.sessao_id: str | None = sessao_id
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
        # Contexto da verba sendo configurada (usado pelo helper que escolhe
        # a coluna do cartão de ponto — Hs EXT para HE, etc.)
        self._verba_atual_nome: str | None = None
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
        # Auto-aceitar dialogs nativos (confirm/alert/prompt) — fallback caso
        # alguma página caia em window.confirm em vez do jConfirm modal.
        # Sem isso, o save fica pendente esperando interação humana.
        self._page.on("dialog", lambda d: d.accept())
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

    # ─── Snapshot de campos para DOM-diff em correção manual ───────────────

    def capturar_snapshot_listagem_verbas(self) -> dict:
        """Captura o estado da listagem de Verbas no PJE-Calc.

        Usado para registrar o snapshot inicial antes de oferecer edição
        manual ao usuário e, depois, comparar com o estado final para
        gerar `CorrecaoUsuario` automaticamente (sem o usuário precisar
        descrever em texto livre).

        Retorna um dict serializável com:
          - `linhas`: lista de strings (texto completo de cada <tr> com
            input verbaSelecionada na listagem)
          - `reflexos_ativos`: lista de ids dos reflexos marcados
          - `valor_total`: texto do rodapé com o total da listagem (se houver)
          - `mensagens`: mensagens JSF visíveis no momento (pendências, erros)
          - `url`: URL atual (para verificação de contexto Seam)
        """
        try:
            return self._page.evaluate("""() => {
                const trs = [...document.querySelectorAll('tr')];
                const linhas = trs
                    .filter(tr => tr.querySelector('input[id*=":verbaSelecionada"]'))
                    .map(tr => (tr.textContent||'').replace(/\\s+/g,' ').trim())
                    .filter(t => t);
                const reflexos = [...document.querySelectorAll('input[id*=":listaReflexo:"][id$=":ativo"]')]
                    .filter(c => c.checked)
                    .map(c => c.id);
                const total_el = document.querySelector('[id*=":totalDevido"], [id*=":total"], [id$=":valorTotal"]');
                const total = total_el ? (total_el.value || total_el.textContent || '').trim() : null;
                const msgs = [...document.querySelectorAll('.rf-msgs-detail,.rf-msgs-sum,.rich-message-detail')]
                    .map(e => (e.textContent||'').trim()).filter(t => t).slice(0, 10);
                return {
                    linhas: linhas,
                    reflexos_ativos: reflexos,
                    valor_total: total,
                    mensagens: msgs,
                    url: location.href.split('#')[0]
                };
            }""")
        except Exception as e:
            self.log(f"  ⚠ Falha capturar snapshot de verbas: {e}")
            return {"erro": str(e), "linhas": [], "reflexos_ativos": [], "mensagens": []}

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
        # CARTÃO DE PONTO ANTES DE VERBAS (reordenação 18/05/2026):
        # O manual oficial CSJT (§9.7) sugere Verbas antes de Cartão, mas
        # para verbas com `quantidade.tipo=IMPORTADA_DO_CARTAO` (HE, intervalo
        # intrajornada/interjornada, adicional noturno), o dropdown de
        # colunas (Hs EXT, Hs Intrajornada, etc.) só popula APÓS o cartão
        # estar criado E APURADO. Por isso reordenamos: criar cartão +
        # apurar PRIMEIRO, depois criar verbas — assim na Fase 5 Verbas o
        # bot pode setar IMPORTADA_DO_CARTAO + Hs EXT diretamente no
        # formulário Parâmetros, sem precisar "revisitar".
        _run_fase("Fase 4 (Cartão Ponto)", self.fase_cartao_de_ponto, bool(self.previa.cartao_de_ponto))
        _run_fase("Fase 5 (Verbas)", self.fase_verbas)
        # Fechar+Reabrir pós-Verbas: força @End da outer conv para commit
        # dos saves em DB. Sem isso, os dados ficam presos na transação Seam
        # e Liquidar (em conv fresca) lê estado stale.
        try:
            self._fechar_e_reabrir_calculo("pós-Verbas")
        except Exception as e:
            self.log(f"  ⚠ Fechar+Reabrir pós-Verbas falhou: {e}")
        # Correções pós-Recentes que dependem da listagem (modo edição):
        # - Editar histórico default p/ CS + proporcionalizarINSS
        # - Fixar valorDevido em verbas INFORMADO
        _run_fase("Fase 5.5 (Correções pós-Recentes)", self.fase_pos_recentes_correcoes)
        # Fechar+Reabrir pós-Correções: commit das edições de histórico CS +
        # valorDevido em verbas INFORMADO ao DB antes de prosseguir
        try:
            self._fechar_e_reabrir_calculo("pós-Correções")
        except Exception as e:
            self.log(f"  ⚠ Fechar+Reabrir pós-Correções falhou: {e}")
        _run_fase("Fase 6 (Faltas)", self.fase_faltas, bool(self.previa.faltas))
        _run_fase("Fase 7 (Férias)", self.fase_ferias, bool(self.previa.ferias.periodos))
        _run_fase("Fase 8 (FGTS)", self.fase_fgts)
        _run_fase("Fase 9 (CS/INSS)", self.fase_contribuicao_social)
        _run_fase("Fase 10 (IRPF)", self.fase_imposto_de_renda)
        # Fases das 5 seções com schema novo (skip por omissão — JSON null = pula)
        _run_fase("Fase 10a (Salário-Família)", self.fase_salario_familia, bool(self.previa.salario_familia))
        _run_fase("Fase 10b (Seguro-Desemprego)", self.fase_seguro_desemprego, bool(self.previa.seguro_desemprego))
        _run_fase("Fase 10c (Previdência Privada)", self.fase_previdencia_privada, bool(self.previa.previdencia_privada))
        _run_fase("Fase 10d (Pensão Alimentícia)", self.fase_pensao_alimenticia, bool(self.previa.pensao_alimenticia))
        _run_fase("Fase 11 (Honorários)", self.fase_honorarios, bool(self.previa.honorarios))
        _run_fase("Fase 11b (Multas/Indenizações)", self.fase_multas_indenizacoes, bool(self.previa.multas_indenizacoes))
        _run_fase("Fase 12 (Custas)", self.fase_custas_judiciais)
        _run_fase("Fase 13 (Correção/Juros)", self.fase_correcao_juros_multa)

        # Fechar+Reabrir pré-Liquidar: força @End de toda a outer conv para
        # commit de TODAS as saves de fases 6-13 (Faltas/Férias/FGTS/CS/IRPF/
        # Custas/Honorários/Correção). Sem isso, Liquidar abre conv fresca
        # que lê DB stale.
        try:
            self._fechar_e_reabrir_calculo("pré-Liquidar")
        except Exception as e:
            self.log(f"  ⚠ Fechar+Reabrir pré-Liquidar falhou: {e}")

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
            # CRÍTICO (descoberto 19/05/2026 via teste manual no PJE-Calc):
            #
            # Playwright `fill()` + `press("Tab")` NÃO persiste inputs text em
            # certos contextos JSF a4j. Estado pós-save:
            #   descricao escrito 'INDENIZAÇÃO SUBSTITUTIVA DE REFEIÇÃO'
            #   → persistido no DB como 'RESTITUIÇÃO / INDENIZAÇÃO DE DESPESA' (canonical)
            #   → o backing bean NUNCA recebeu o valor escrito
            #
            # Mas via JS direto (el.value=...; dispatch input/change/blur) +
            # click salvar → PERSISTE corretamente.
            #
            # Por quê? Hipóteses (descobertas observacionais):
            #   - fill() do Playwright muda o value mas só dispara `input` event
            #   - press("Tab") dispara keydown trusted, mas o `blur` natural pode
            #     ser interceptado por algum handler intermediário (modais? popups?)
            #   - JSF a4j em alguns inputs (descricao tem onblur listener) precisa
            #     do `change` event dispatch explícito, não apenas blur
            #
            # SOLUÇÃO comprovada: JS direto setando value + dispatch events
            # explícitos (input, change, blur). É o mesmo que o navegador faz
            # mas garantido.
            real_id = None
            try:
                real_id = loc.first.get_attribute("id")
            except Exception:
                pass
            ok = False
            if real_id:
                try:
                    ok = self._page.evaluate(
                        """({id, valor}) => {
                            const el = document.getElementById(id);
                            if (!el) return false;
                            el.focus();
                            // Para inputs com mascara (currencyMask), o focus
                            // pode ativar listener — aguardar 1 tick antes de setar.
                            el.value = valor;
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            el.dispatchEvent(new Event('blur', {bubbles: true}));
                            return true;
                        }""",
                        {"id": real_id, "valor": str(valor)},
                    )
                except Exception as e:
                    self.log(f"  ⚠ {dom_id} via JS: {e}")
            if not ok:
                # Fallback para fill() + Tab (caso JS falhe)
                try:
                    loc.first.focus()
                    loc.first.fill(str(valor))
                    loc.first.press("Tab")
                except Exception as e:
                    self.log(f"  ⚠ {dom_id} fallback: {e}")
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
        """Marca um radio JSF simulando ação humana real.

        CRÍTICO (descoberto 18/05/2026 sessão cecf7937): JSF a4j:support
        diferencia eventos `isTrusted=true` (gerados pelo navegador real) de
        eventos sintéticos `dispatchEvent(new Event(...))`. Em verbas
        EXPRESSO_ADAPTADO com transição `valor=CALCULADO→INFORMADO`, o
        backing bean Seam IGNORA mudanças disparadas por click(force=True) +
        dispatchEvent, mantendo `valorDaVerba=CALCULADO` no servidor enquanto
        o cliente vê INFORMADO → save silenciosamente rejeitado (URL fica em
        verba-calculo.jsf sem mensagem de sucesso, sem erro JSF visível).

        SOLUÇÃO: simular ação humana com scroll → hover → click SEM force.
        Playwright aguarda o elemento ficar `actionable` e dispara eventos
        TRUSTED que o a4j:support aceita corretamente.

        Fallback com force=True + dispatchEvent só como último recurso
        (cenários onde o radio está coberto por overlay invisível).
        """
        # Tentar id*= primeiro (radios com id fixo); fallback name*= (JSF com IDs dinâmicos j_id*)
        for sel in (
            f"input[type='radio'][id*='{dom_id}'][value='{valor}']",
            f"input[type='radio'][name*='{dom_id}'][value='{valor}']",
        ):
            loc = self._page.locator(sel)
            if loc.count() == 0:
                continue
            target = loc.first
            # Estratégia 1: click humano (scroll → hover → click sem force).
            # Gera evento isTrusted=true que o JSF aceita.
            try:
                target.scroll_into_view_if_needed(timeout=3000)
                self._page.wait_for_timeout(100)
                target.hover(timeout=3000)
                self._page.wait_for_timeout(80)
                target.click(timeout=5000)
                self.log(f"  ✓ radio {dom_id} = {valor}")
                return
            except Exception as e:
                self.log(f"  ⚠ radio {dom_id}={valor}: click humano falhou ({e}) — tentando fallback")
            # Estratégia 2: fallback com force=True + dispatchEvent
            # (rare path — só ativa se hit-test falhar)
            try:
                target.click(force=True)
                try:
                    target.evaluate(
                        """el => {
                            el.checked = true;
                            el.dispatchEvent(new Event('click', {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                        }"""
                    )
                except Exception:
                    pass
                self.log(f"  ✓ radio {dom_id} = {valor} (fallback force)")
                return
            except Exception as e:
                self.log(f"  ⚠ radio {dom_id}={valor}: fallback também falhou ({e})")
        if obrigatorio:
            raise RuntimeError(f"Radio não encontrado: {dom_id}={valor}")
        self.log(f"  ⚠ radio {dom_id}={valor} não encontrado — pulando")

    def _marcar_checkbox(self, dom_id: str, marcado: bool) -> None:
        """Marca checkbox JSF — pula silenciosamente se disabled e usa click humano.

        Disabled checkboxes (ex.: aplicarProporcionalidadeAoValorDevido para
        verbas onde isPermiteAplicarPropocionalidadeAoValorDevido()=false)
        com click(force=True) ainda alteravam o DOM, mas o backing bean
        REJEITAVA a alteração — silenciosamente fazendo o save falhar sem
        mensagem de erro visível (observado em 18/05/2026 sessão cecf7937,
        v06 INDENIZAÇÃO REFEIÇÃO).
        """
        for sel in (
            f"input[type='checkbox'][id='formulario:{dom_id}']",
            f"input[type='checkbox'][id$=':{dom_id}']",
            f"input[type='checkbox'][id$='{dom_id}']",
        ):
            loc = self._page.locator(sel)
            if loc.count() == 0:
                continue
            try:
                target = loc.first
                # Pular se disabled — JSF não atualiza o bean para checkboxes
                # disabled mesmo se o DOM mudar via click(force)
                try:
                    if not target.is_enabled():
                        atual = target.is_checked()
                        if atual == marcado:
                            self.log(f"  ⊙ checkbox {dom_id} = {marcado} (disabled, valor atual coincide)")
                        else:
                            self.log(
                                f"  ⊙ checkbox {dom_id} disabled — atual={atual}, desejado={marcado} (não aplicável a esta verba, pulando)"
                            )
                        return
                except Exception:
                    pass
                # Click humano (trusted) — mesmo padrão dos radios
                if target.is_checked() != marcado:
                    try:
                        target.scroll_into_view_if_needed(timeout=2000)
                        self._page.wait_for_timeout(80)
                        target.click(timeout=4000)
                    except Exception:
                        target.click(force=True)  # fallback overlay
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

    # ─── Helpers comparativos (espelho fiel do JSON) ──────────────────────
    # Princípio (CLAUDE.md): a prévia é espelho do PJE-Calc. O bot lê o estado
    # atual do DOM e só dispara mudança quando difere do JSON. Evita AJAX
    # desnecessário que pode resetar o backing bean Seam (mudarCaracteristica
    # etc.) e funciona uniformemente para Expresso ou Manual.

    def _setar_text_se_diferente(self, dom_id: str, valor_desejado: Any, obrigatorio: bool = False) -> bool:
        """Preenche input text só se valor atual != desejado. Retorna True se mudou."""
        if valor_desejado is None or valor_desejado == "":
            return False
        try:
            loc = self._page.locator(f"[id$='{dom_id}']")
            if loc.count() == 0:
                if obrigatorio:
                    raise RuntimeError(f"DOM ID não encontrado: {dom_id}")
                return False
            atual = loc.first.input_value(timeout=1500)
            if str(atual).strip() == str(valor_desejado).strip():
                return False
            self._preencher(dom_id, valor_desejado, obrigatorio=False)
            return True
        except Exception as e:
            self.log(f"  ⚠ {dom_id} comparativo: {e}")
            return False

    def _marcar_radio_se_diferente(self, name_suffix: str, valor_desejado: str, obrigatorio: bool = False) -> bool:
        """Marca radio só se o atualmente checked != valor_desejado.

        Procura todos os inputs[type=radio][id*=name_suffix] e verifica qual
        está checked. Se for o desejado, skip. Senão, clica via _marcar_radio
        (que usa click humano + jConfirm silenciado).
        """
        try:
            atual = self._page.evaluate(
                """(nameSuf) => {
                    const radios = [...document.querySelectorAll('input[type="radio"]')]
                        .filter(r => (r.id || '').indexOf(nameSuf) >= 0 || (r.name || '').indexOf(nameSuf) >= 0);
                    const checked = radios.find(r => r.checked);
                    return checked ? checked.value : null;
                }""",
                name_suffix,
            )
            if atual == valor_desejado:
                return False
            self._marcar_radio(name_suffix, valor_desejado, obrigatorio=obrigatorio)
            return True
        except Exception as e:
            self.log(f"  ⚠ radio {name_suffix} comparativo: {e}")
            return False

    def _marcar_checkbox_se_diferente(self, dom_id: str, marcado_desejado: bool) -> bool:
        """Marca/desmarca checkbox só se estado atual != desejado."""
        try:
            loc = self._page.locator(
                f"input[type='checkbox'][id$=':{dom_id}'], input[type='checkbox'][id$='{dom_id}']"
            )
            if loc.count() == 0:
                return False
            atual = loc.first.is_checked()
            if atual == bool(marcado_desejado):
                return False
            self._marcar_checkbox(dom_id, marcado_desejado)
            return True
        except Exception as e:
            self.log(f"  ⚠ checkbox {dom_id} comparativo: {e}")
            return False

    def _selecionar_se_diferente(self, dom_id: str, valor_desejado: str, obrigatorio: bool = False) -> bool:
        """Seleciona option só se o valor atual do <select> != desejado."""
        if not valor_desejado:
            return False
        try:
            loc = self._page.locator(f"select[id$='{dom_id}']")
            if loc.count() == 0:
                if obrigatorio:
                    raise RuntimeError(f"Select não encontrado: {dom_id}")
                return False
            atual = loc.first.input_value()
            if str(atual) == str(valor_desejado):
                return False
            self._selecionar(dom_id, valor_desejado, obrigatorio=obrigatorio)
            return True
        except Exception as e:
            self.log(f"  ⚠ select {dom_id} comparativo: {e}")
            return False

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

        Silencia preventivamente o jConfirm modal de checarValor antes do
        click — sem custo se a função não existir nessa página, mas evita
        save bloqueado em verba-calculo.jsf quando valor mudou CALCULADO↔INFORMADO.
        """
        self._silenciar_dialog_confirma_valor()
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
                        target = loc.first
                        target.wait_for(state="visible", timeout=timeout_ms)
                        # Click humano (trusted event) — necessário para JSF
                        # a4j:commandButton aceitar a submission. force=True
                        # pode gerar evento isTrusted=false e o JSF a4j
                        # silenciosamente ignora a submissão (form fica em
                        # edit mode sem mensagem de sucesso/erro).
                        try:
                            target.scroll_into_view_if_needed(timeout=2000)
                            self._page.wait_for_timeout(100)
                            target.hover(timeout=2000)
                            self._page.wait_for_timeout(80)
                            target.click(timeout=timeout_ms)
                            self.log(f"  ✓ click {nome} humano (cascata flex via {sel!r})")
                        except Exception as _eh:
                            # Fallback: click com force (overlay invisível)
                            target.click(force=True)
                            self.log(f"  ✓ click {nome} fallback-force (cascata flex via {sel!r})")
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

    def _fechar_e_reabrir_calculo(self, contexto: str = "") -> bool:
        """Fluxo seguro de commit: clicar Fechar (sidebar) → @End outer conv
        → cálculo persiste no DB → Reabrir via Recentes → conv nova em edit
        mode com estado committed.

        Resolve o problema Seam EPC + H2: saves dentro de uma mesma conv
        ficam pendentes na transação até @End. Fechar é a ação UI que
        dispara @End de forma confiável.

        Args:
            contexto: tag p/ log (ex.: "pós-Verbas", "pós-CS")

        Returns True se reabertura via Recentes foi bem-sucedida.
        """
        tag = f" ({contexto})" if contexto else ""
        try:
            self.log(f"  → Fechar cálculo{tag} para commit Seam @End...")
            # ⚠ CRÍTICO (24/05/2026): se URL atual é verbas-para-calculo.jsf
            # (Expresso) ou principal.jsf, o sidebar NÃO tem li_operacoes_fechar.
            # Forçar nav para uma página com sidebar completo (verba-calculo.jsf)
            # antes de tentar o Fechar.
            try:
                url_atual = self._page.url
                precisa_nav = (
                    "verbas-para-calculo.jsf" in url_atual
                    or "principal.jsf" in url_atual
                    or "verba-calculo.jsf" not in url_atual
                )
                if precisa_nav and self._calculo_conversation_id:
                    self.log(f"    ℹ URL atual ({url_atual[-50:]}) não tem sidebar Operações — navegando para verba-calculo.jsf primeiro")
                    self._page.goto(
                        f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                        f"?conversationId={self._calculo_conversation_id}",
                        wait_until="domcontentloaded", timeout=20000,
                    )
                    self._aguardar_ajax(8000)
                    self._page.wait_for_timeout(1500)
            except Exception as _e:
                self.log(f"    ⚠ Pre-Fechar nav: {_e}")
            # Tentar sidebar click li_operacoes_fechar
            clicou = self._navegar_menu_via_click("li_operacoes_fechar")
            if not clicou:
                # Fallback: procurar link com texto "Fechar" no sidebar
                clicou = self._page.evaluate(
                    """() => {
                        const links = [...document.querySelectorAll('li a')];
                        for (const a of links) {
                            if ((a.textContent||'').trim() === 'Fechar') {
                                if (a.onclick) { a.onclick(new Event('click')); }
                                else { a.click(); }
                                return true;
                            }
                        }
                        return false;
                    }"""
                )
            if not clicou:
                # ⚠ FALLBACK (23/05/2026): quando sidebar não tem
                # li_operacoes_fechar (estamos em principal.jsf ou outra page
                # sem o menu Operações), reabrir diretamente via Recentes —
                # navegar para principal.jsf abandona qualquer conv corrente
                # (Seam @End implícito quando não passa conversationId), e a
                # reabertura pegará o cálculo mais recente do DB.
                self.log(f"  ⚠ Fechar{tag}: link não encontrado — tentando reabrir direto via Recentes")
                ok = self._reabrir_calculo_via_recentes()
                if ok:
                    self.log(f"  ✓ Reabertura direta via Recentes{tag} ok: conv={self._calculo_conversation_id}")
                return ok
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(2500)
            self.log(f"  ✓ Fechar{tag} disparado (cálculo commitado ao DB)")
            # Reabrir via Recentes
            ok = self._reabrir_calculo_via_recentes()
            if ok:
                self.log(f"  ✓ Reabertura pós-Fechar{tag} ok: conv={self._calculo_conversation_id}")
            else:
                self.log(f"  ⚠ Reabertura pós-Fechar{tag} falhou")
            return ok
        except Exception as e:
            self.log(f"  ⚠ _fechar_e_reabrir_calculo{tag}: {e}")
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
            options = listbox.first.locator("option")

            # ⚠ CRÍTICO (23/05/2026): quando o mesmo CNJ aparece MÚLTIPLAS
            # vezes em Recentes (testes repetidos), precisamos pegar o
            # cálculo MAIS RECENTE — geralmente o de MAIOR ID. Formato:
            # 'NNN / CNJ / RECLAMANTE'. Coletar TODOS os índices que
            # casam, ordenar por ID descendente, pegar o primeiro.
            def _extract_id(text: str) -> int:
                """Extrai o ID numérico inicial do label Recentes."""
                import re as _re
                m = _re.match(r"\s*(\d+)\s*/", text or "")
                return int(m.group(1)) if m else -1

            matching_indices: list[tuple[int, int]] = []  # (id, idx)
            for i in range(n_opts):
                opt_text = (options.nth(i).text_content() or "")
                if num_clean in opt_text.replace(".", "").replace("-", "").replace("/", ""):
                    matching_indices.append((_extract_id(opt_text), i))

            found_idx: int | None = None
            if matching_indices:
                # ⚠ CRÍTICO (24/05/2026): PREFERIR o cálculo CORRENTE (capturado
                # no Fase 2 via _extrair_numero_calculo) por ID EXATO. Caso não
                # haja match exato, fallback para o de maior ID (mais recente).
                # Sem isso, em testes repetidos o bot pegava cálculos órfãos
                # antigos com mesmo CNJ → liquidava cálculo VAZIO → PJC sem verbas.
                calc_num_session = getattr(self, "_calculo_numero", None)
                if calc_num_session:
                    try:
                        calc_id_int = int(str(calc_num_session).strip())
                        for cid, idx in matching_indices:
                            if cid == calc_id_int:
                                found_idx = idx
                                self.log(
                                    f"  ℹ Match EXATO do cálculo da sessão "
                                    f"(ID={calc_id_int}) em Recentes"
                                )
                                break
                    except (ValueError, TypeError):
                        pass
                if found_idx is None:
                    # Fallback: maior ID primeiro (mais recente)
                    matching_indices.sort(key=lambda t: -t[0])
                    found_idx = matching_indices[0][1]
                    if len(matching_indices) > 1:
                        self.log(
                            f"  ℹ {len(matching_indices)} cálculos com mesmo CNJ — "
                            f"sem match exato (sessão={calc_num_session}), "
                            f"escolhendo ID={matching_indices[0][0]} (mais recente)"
                        )

            # Fallback: pelo nome do reclamante (só se NÃO estiver usando override de teste)
            if found_idx is None and processo_override is None:
                rec = (self.previa.processo.reclamante.nome or "").upper()
                if len(rec) >= 5:
                    matching_indices = []
                    for i in range(n_opts):
                        opt_text_up = (options.nth(i).text_content() or "").upper()
                        if rec in opt_text_up:
                            matching_indices.append((_extract_id(options.nth(i).text_content() or ""), i))
                    if matching_indices:
                        matching_indices.sort(key=lambda t: -t[0])
                        found_idx = matching_indices[0][1]

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
                # ⚠ CRÍTICO (24/05/2026): capturar/atualizar _calculo_numero a
                # partir do label do Recentes que foi reaberto. Isso permite
                # que CHAMADAS futuras de _reabrir_calculo_via_recentes filtrem
                # pelo cálculo CORRETO (match EXATO ID) em vez de "maior ID".
                # Crucial em sessões com testes acumulados em Recentes.
                try:
                    import re as _re
                    label_recente = (options.nth(found_idx).text_content() or "").strip()
                    m_id = _re.match(r"\s*(\d+)\s*/", label_recente)
                    if m_id:
                        novo_num = m_id.group(1)
                        if not self._calculo_numero:
                            self._calculo_numero = novo_num
                            self.log(f"  ℹ Cálculo da sessão capturado via Recentes: {novo_num}")
                        elif self._calculo_numero != novo_num:
                            self.log(f"  ⚠ ATENÇÃO: Recentes reabriu cálculo {novo_num} (sessão esperava {self._calculo_numero})")
                except Exception as _e:
                    self.log(f"  ⚠ Captura calc number Recentes: {_e}")
                # Tentar também via DOM (header "Cálculo: NNN")
                try:
                    self._extrair_numero_calculo()
                except Exception:
                    pass
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
        # CRÍTICO (23/05/2026): wait_until="load" (default) espera TODOS os
        # recursos (CSS, JS, imagens, AJAX-renderers). Em ARM cloud lento o
        # PJE-Calc serve principal.jsf demorando >30s para 'load' completar.
        # Sintoma: Page.goto: Timeout 30000ms exceeded.
        # Fix: usar "domcontentloaded" (HTML pronto, mais rápido) + retry
        # com timeout maior se primeira falhar.
        last_err = None
        for tentativa in range(3):
            try:
                self._page.goto(
                    f"{self.pjecalc_url}/pages/principal.jsf",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                break
            except Exception as e:
                last_err = e
                self.log(f"  ⚠ Tentativa {tentativa+1}/3 abrir principal.jsf: {type(e).__name__}")
                if tentativa < 2:
                    self._page.wait_for_timeout(3000)
        else:
            raise last_err  # type: ignore[misc]
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

        # Comentários JG — usa valor explícito; fallback: auto-detecta JG via honorários.
        # CRÍTICO (21/05/2026): o texto DEVE indicar A PARTE beneficiária (Reclamante/
        # Reclamado/ambas), não apenas "parte beneficiária" genérico. Regra consagrada.
        jg_text = getattr(pc, "comentarios_jg", None)
        if not jg_text:
            partes_jg: list[str] = []
            for hon in self.previa.honorarios:
                if getattr(hon, "tipo_honorario", "") != "SUCUMBENCIAIS":
                    continue
                devedor = getattr(hon, "tipo_devedor", "") or ""
                if devedor == "RECLAMANTE" and "Reclamante" not in partes_jg:
                    partes_jg.append("Reclamante")
                elif devedor == "RECLAMADO" and "Reclamado" not in partes_jg:
                    partes_jg.append("Reclamado")
            if partes_jg:
                if len(partes_jg) == 1:
                    parte = partes_jg[0]
                    jg_text = (
                        f"Suspensão de exigibilidade dos honorários sucumbenciais "
                        f"devidos pelo {parte}, beneficiário da Justiça Gratuita "
                        f"(art. 791-A, § 4º, da CLT)."
                    )
                else:
                    jg_text = (
                        "Suspensão de exigibilidade dos honorários sucumbenciais "
                        "devidos por ambas as partes, beneficiárias da Justiça Gratuita "
                        "(art. 791-A, § 4º, da CLT)."
                    )
                self.log(f"  ℹ JG auto-detectado: parte(s) beneficiária(s) = {', '.join(partes_jg)}")
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
            # Históricos default (PJE-Calc já criou em Fase 2): pulamos aqui
            # pois Seam está em modo criação — listagem inacessível. Edição
            # do default será feita em fase_pos_recentes_correcoes() após
            # reabertura via Recentes.
            if _norm(hist.nome) in defaults_norm:
                self.log(f"  ⏭ Pulando '{hist.nome}' — default do PJE-Calc (edição pós-Recentes)")
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
            # Quando CS=true, marcar proporcionalizarINSS para que as ocorrências
            # da Contribuição Social sejam auto-populadas com o valor da base.
            # Sem isso, a liquidação retorna "não possui valor cadastrado para
            # todas as ocorrências da Contribuição Social sobre Salários
            # Devidos" (descoberto 19/05/2026).
            if hist.incidencias.cs_inss:
                self._aguardar_ajax(2000)
                self._marcar_checkbox("proporcionalizarINSS", True)
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

    def fase_pos_recentes_correcoes(self) -> None:
        """Correções que só podem ser feitas após reabertura via Recentes
        (Seam em modo edição com listagens completas).

        Atualmente:
        - Históricos default com CS=true → editar para marcar
          proporcionalizarINSS e gerar ocorrências CS
        - Verbas INFORMADO → garantir valorDevido != 0 em ocorrências
        """
        def _norm(s: str) -> str:
            tabela = str.maketrans("ÁÉÍÓÚÇáéíóúç", "AEIOUCaeiouc")
            return (s or "").translate(tabela).upper().strip()
        defaults_norm = {_norm(n) for n in self._HISTORICOS_DEFAULT}

        # CRÍTICO: usar SIDEBAR click (não URL-nav) para preservar a mesma
        # conversação Seam em edit mode com dados populados. URL-nav cria
        # nova conv fresh sem o histórico/verbas já lançados.

        # 1) Editar históricos default com CS=true (passar valor para
        # preencher valorParaBaseDeCalculo — sem isso ocorrências CS ficam 0)
        for hist in self.previa.historico_salarial:
            if _norm(hist.nome) in defaults_norm and hist.incidencias.cs_inss:
                try:
                    if not self._navegar_menu_via_click("li_calculo_historico_salarial"):
                        self.log(f"  ⚠ Não conseguiu navegar via sidebar — skip '{hist.nome}'")
                        continue
                    self._aguardar_ajax(8000)
                    self._page.wait_for_timeout(2000)
                    valor = float(hist.valor_brl) if hist.tipo_valor.value == "INFORMADO" and hist.valor_brl else None
                    self._editar_default_historico_para_cs(
                        hist.nome,
                        valor_brl=valor,
                        competencia_inicial=hist.competencia_inicial,
                        competencia_final=hist.competencia_final,
                    )
                except Exception as e:
                    self.log(f"  ⚠ Erro pós-Recentes editar '{hist.nome}': {e}")

        # Re-aplicar valorDevido em verbas INFORMADO pós-Recentes (defensivo:
        # se outer conv não @End'd, edits inline em fase_verbas podem ter
        # sido perdidas. Re-aplicar em conv pós-Recentes garante persistência).
        verbas_inf = [v for v in self.previa.verbas_principais
                       if getattr(v.parametros, "valor", None) == TipoValor.INFORMADO
                       and getattr(v.parametros.valor_devido, "valor_informado_brl", None)]
        for v in verbas_inf:
            try:
                if not self._navegar_menu_via_click("li_calculo_verbas"):
                    continue
                try:
                    self._page.wait_for_url("**/verba/verba-calculo.jsf**", timeout=15000)
                except Exception:
                    pass
                self._page.wait_for_load_state("networkidle", timeout=15000)
                self._page.wait_for_timeout(2000)
                self._configurar_ocorrencias_informado_inline(v)
            except Exception as e:
                self.log(f"  ⚠ Re-aplicar valorDevido '{v.nome_pjecalc}': {e}")

    def _editar_default_historico_para_cs(self, nome: str, valor_brl: float | None = None,
                                            competencia_inicial: str | None = None,
                                            competencia_final: str | None = None) -> None:
        """Edita entrada default do histórico salarial (criada pelo PJE-Calc)
        para marcar incidência CS + proporcionalizarINSS + setar valor base
        + atualizar competências + gerar ocorrências e salvar.

        valor_brl: valor a setar em valorParaBaseDeCalculo (tipo INFORMADO).
        competencia_inicial/final: período do histórico (formato MM/YYYY).
        Sem isso, default ÚLTIMA REMUNERAÇÃO tem período de 1 mês →
        ocorrências CS incompletas → liquidação bloqueia.
        """
        self.log(f"  → Editar default histórico '{nome}' para configurar CS")
        try:
            # Localizar linha pela nome e clicar linkAlterar
            clicou = self._page.evaluate(
                """(nome) => {
                    const linhas = document.querySelectorAll('table.rich-table tbody tr');
                    for (const tr of linhas) {
                        const txt = tr.textContent || '';
                        if (txt.toUpperCase().includes(nome.toUpperCase())) {
                            const link = tr.querySelector('a.linkAlterar');
                            if (link) { link.click(); return true; }
                        }
                    }
                    return false;
                }""",
                nome,
            )
            if not clicou:
                self.log(f"    ⚠ '{nome}': linkAlterar não encontrado — skip")
                return
            self._aguardar_ajax(6000)
            self._page.wait_for_timeout(1500)
            # Marcar inss (CS) + proporcionalizarINSS
            self._marcar_checkbox("inss", True)
            self._aguardar_ajax(2000)
            self._marcar_checkbox("proporcionalizarINSS", True)
            self._aguardar_ajax(1500)
            # Atualizar competências (período do histórico) se fornecidas
            if competencia_inicial:
                try:
                    self._preencher("competenciaInicialInputDate", competencia_inicial, obrigatorio=False)
                    self.log(f"    ✓ competenciaInicial = {competencia_inicial}")
                except Exception as e:
                    self.log(f"    ⚠ competenciaInicial erro: {e}")
            if competencia_final:
                try:
                    self._preencher("competenciaFinalInputDate", competencia_final, obrigatorio=False)
                    self.log(f"    ✓ competenciaFinal = {competencia_final}")
                except Exception as e:
                    self.log(f"    ⚠ competenciaFinal erro: {e}")
            # Setar valor base se fornecido (tipo INFORMADO)
            if valor_brl is not None:
                try:
                    self._preencher("valorParaBaseDeCalculo", _fmt_br(valor_brl), obrigatorio=False)
                    self.log(f"    ✓ valorParaBaseDeCalculo = {_fmt_br(valor_brl)}")
                except Exception as e:
                    self.log(f"    ⚠ valorParaBaseDeCalculo erro: {e}")
            # Garantir ocorrências geradas com CS
            try:
                self._clicar("cmdGerarOcorrencias")
                self._aguardar_ajax(6000)
                self._page.wait_for_timeout(1500)
            except Exception as e:
                self.log(f"    ⚠ cmdGerarOcorrencias erro: {e}")
            # Marcar CS em TODAS as ocorrências (incideINSS por linha):
            # selecionarTodos4 marca todos os checkboxes .labelInput4 de uma vez
            # ALTERNATIVA: iterar formulario:listagemMC:N:incideINSS
            try:
                marcados = self._page.evaluate("""() => {
                    // Estratégia 1: clicar selecionarTodos4 (select all CS)
                    const todos = document.getElementById('selecionarTodos4');
                    if (todos && !todos.checked) {
                        todos.click();
                        // Disparar o handler do prepararCheckAll
                        if (window.jQuery) {
                            window.jQuery('.labelInput4:enabled').prop('checked', true);
                            window.jQuery('.labelInput4:enabled').each(function(){
                                this.dispatchEvent(new Event('change', {bubbles: true}));
                            });
                        }
                    }
                    // Estratégia 2: marcar diretamente cada incideINSS
                    const checkboxes = document.querySelectorAll("input[id$=':incideINSS']");
                    let n = 0;
                    checkboxes.forEach(cb => {
                        if (!cb.disabled && !cb.checked) {
                            cb.checked = true;
                            cb.dispatchEvent(new Event('change', {bubbles: true}));
                            cb.dispatchEvent(new Event('click', {bubbles: true}));
                            n++;
                        }
                    });
                    return {todosClicked: !!todos, nCheckboxes: checkboxes.length, marcados: n};
                }""")
                self.log(f"    ✓ incideINSS marcado: {marcados}")
                self._aguardar_ajax(2000)
            except Exception as e:
                self.log(f"    ⚠ incideINSS erro: {e}")
            self._clicar("salvar")
            self._aguardar_ajax(8000)
            sucesso = self._aguardar_operacao_sucesso(timeout_ms=15000, bloqueante=False)
            if sucesso:
                self.log(f"    ✓ '{nome}' editado com CS+proporcionalizarINSS")
            else:
                self.log(f"    ⚠ '{nome}' editado mas sem confirmação de save")
        except Exception as e:
            self.log(f"    ⚠ Erro ao editar '{nome}': {e}")

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
            # CRÍTICO (descoberto 20/05/2026 via Chrome MCP diagnóstico):
            # Cada Expresso save cria uma nova conv Seam (6→42→48→...→86).
            # A conv da última save (86) só "vê" a última verba salva (HE 50%),
            # não as 4 anteriores. Quando o bot tenta `_configurar_parametros_pos_expresso`,
            # a listagem aparece com APENAS 1 verba e linkParametrizar falha.
            #
            # FIX: Fechar+Reabrir após os Expresso saves força @End da conv atual,
            # commita TODAS as 5 verbas ao DB, e a reabertura via Recentes cria
            # uma conv fresh com o cálculo completo (todas as verbas visíveis).
            # Test manual no Chrome confirmou: conv=192 via Recentes mostra 5 verbas
            # e linkParametrizar funciona perfeitamente.
            self._fechar_e_reabrir_calculo("pós-Expresso")

        # Histórico de F+R proativo no loop de ajuste:
        # - 12/05: F+R a cada verba (custo proibitivo)
        # - 23/05: F+R a cada N=3 verbas (HE 50% idx=2 falhava — não bastava)
        # - 23/05 noite: N=2 (resolveu para 5 verbas) — usado em test 24 (11/11)
        # - 24/05 manhã: REMOVIDO em test 27 → REGRESSÃO 11/11 → 3/11 verbas
        # - 24/05 tarde: REINTRODUZIDO com N=2. Recoveries reativos sozinhos
        #   não bastam — o Seam EPC degenera silenciosamente em formas que
        #   o recovery LEVE não detecta. Mantendo a regra do CLAUDE.md:
        #   safety nets preservados.
        #
        # Recoveries reativos COMPLEMENTARES (também não remover):
        # - Recovery LEVE (URL goto pre-conv) → commit 214ab89
        # - Recovery wrong-page (principal.jsf) → commit 48f503d
        # - Recovery listagem vazia (TRs=[]) → commit 7d07558
        # - Re-anchor pós-save → commit 8828144
        # - Auto-recovery Regerar+retry valorDevido INFORMADO → commit cc1f4e9
        # - Match EXATO calc_numero (evita cálculo errado) → commit 5b2c44f
        N_VERBAS_POR_BATCH_PARAM = 2
        for idx, v in enumerate(verbas_expresso):
            if idx > 0 and idx % N_VERBAS_POR_BATCH_PARAM == 0:
                self._fechar_e_reabrir_calculo(
                    f"pré-verba batch {idx+1}/{len(verbas_expresso)}"
                )
            try:
                self._configurar_parametros_pos_expresso(v)
            except Exception as e:
                self.log(
                    f"  ⚠ Falha ajustar parâmetros '{v.nome_pjecalc or v.expresso_alvo}': {e}"
                )
            # Para verbas INFORMADO: setar valorDevido em pelo menos uma
            # ocorrência (PJE-Calc bloqueia liquidação se TODAS as ocorrências
            # estão com valorDevido=0).
            try:
                if getattr(v.parametros, "valor", None) == TipoValor.INFORMADO and \
                   getattr(v.parametros.valor_devido, "valor_informado_brl", None):
                    self._configurar_ocorrencias_informado_inline(v)
            except Exception as e:
                self.log(
                    f"  ⚠ Falha ocorrências INFORMADO '{v.nome_pjecalc or v.expresso_alvo}': {e}"
                )
            for r in v.reflexos:
                try:
                    self._configurar_reflexo(v, r)
                except Exception as e:
                    self.log(f"  ⚠ Falha reflexo '{r.nome}': {e}")

        # CRÍTICO (descoberto 12/05/2026 via diagnóstico de pendências):
        # após alterar parâmetros das verbas, é OBRIGATÓRIO clicar "Regerar"
        # na LISTAGEM (botão regerarOcorrencias com rendered=emModoListagem).
        # Sem isso a liquidação retorna:
        #   "O parâmetro Ocorrência de Pagamento foi alterado na página
        #    Verbas, após a geração das ocorrências da verba X"
        if verbas_expresso:
            self._regerar_ocorrencias_verbas()
            # ATENÇÃO: _fixar_valordevido_ocorrencias_informadas() não pode
            # rodar aqui — Seam está em modo criação, listagem inacessível.
            # Será chamado em fase_pos_recentes_correcoes após reabertura.

        self.log("Fase 4 concluída")

    def _fixar_valordevido_ocorrencias_informadas(self, verbas) -> None:
        """Para cada verba com valor=INFORMADO, navega para Ocorrências e
        garante que ao menos a primeira linha tenha valorDevido != 0.

        Estratégia: distribuir valor_informado_brl entre TODAS as linhas
        (equal split). Se proporcionalizar=False, só preenche a primeira.
        """
        verbas_inf = [v for v in verbas if getattr(v.parametros, "valor", None) == TipoValor.INFORMADO
                       and getattr(v.parametros.valor_devido, "valor_informado_brl", None)]
        if not verbas_inf:
            return
        self.log(f"  → Fixar valorDevido em {len(verbas_inf)} verba(s) INFORMADO")
        for v in verbas_inf:
            nome = v.nome_pjecalc or v.expresso_alvo
            valor_total = float(v.parametros.valor_devido.valor_informado_brl)
            try:
                # Re-navegar via sidebar se já saímos da listagem (após processar
                # uma verba, o link Ocorrências leva para parametrizar-ocorrencia)
                if v != verbas_inf[0]:
                    self._navegar_menu_via_click("li_calculo_verbas")
                    try:
                        self._page.wait_for_url("**/verba/verba-calculo.jsf**", timeout=15000)
                    except Exception:
                        pass
                    self._page.wait_for_load_state("networkidle", timeout=15000)
                    self._page.wait_for_timeout(2000)
                # Diagnóstico: dump da URL atual + dismiss alerta se houver
                url_atual = self._page.url
                self.log(f"    ℹ URL atual antes de buscar linkOcorrencias: {url_atual}")
                # Dismiss "Alerta. Foram realizadas alterações" se aparecer
                # (pode estar bloqueando a listagem)
                try:
                    dismiss = self._page.evaluate("""() => {
                        // Procura botões OK/Continuar em divs de alerta
                        const btns = [...document.querySelectorAll('input[value="OK"], input[value="Continuar"], button')].filter(b => {
                            const t = (b.value || b.textContent || '').trim();
                            return t === 'OK' || t === 'Continuar' || t === 'Sim';
                        });
                        if (btns.length > 0) {
                            btns[0].click();
                            return {ok: true, n: btns.length};
                        }
                        return {ok: false};
                    }""")
                    if dismiss.get("ok"):
                        self.log(f"    ✓ Alerta dismiss: {dismiss}")
                        self._page.wait_for_timeout(2000)
                except Exception as e:
                    self.log(f"    ⚠ Tentativa dismiss alerta: {e}")
                # Localizar linha pela nome e clicar linkOcorrencias. Estratégia
                # robusta: procurar todos `.linkOcorrencias` na página e checar
                # o TR pai pelo nome da verba.
                res = self._page.evaluate(
                    """(nome) => {
                        const norm = (s) => (s||'').toUpperCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
                        const alvo = norm(nome);
                        // Estratégia robusta: iterar por todos .linkOcorrencias
                        const links = document.querySelectorAll('.linkOcorrencias, a[title*="Ocorr"]');
                        for (const link of links) {
                            let parent = link.closest('tr');
                            if (!parent) continue;
                            // Subir TRs irmãos até encontrar a row com o nome
                            // (em rich:dataTable às vezes nome está em row separado)
                            let txt = norm(parent.textContent || '');
                            if (txt.includes(alvo)) {
                                link.click();
                                return {ok: true, via: 'closest-tr', total: links.length};
                            }
                            // Tenta TR imediatamente seguinte (caso layout split)
                            let next = parent.nextElementSibling;
                            if (next && norm(next.textContent || '').includes(alvo)) {
                                link.click();
                                return {ok: true, via: 'next-tr', total: links.length};
                            }
                            // Tenta TR imediatamente anterior
                            let prev = parent.previousElementSibling;
                            if (prev && norm(prev.textContent || '').includes(alvo)) {
                                link.click();
                                return {ok: true, via: 'prev-tr', total: links.length};
                            }
                        }
                        // Diagnóstico: links totais + amostras
                        const sample = [...links].slice(0, 5).map(l => {
                            const tr = l.closest('tr');
                            return {
                                href: l.id || l.className,
                                trTxt: tr ? (tr.textContent || '').slice(0, 100) : '<no-tr>',
                            };
                        });
                        return {ok: false, totalLinks: links.length, sample};
                    }""",
                    nome,
                )
                if not res.get("ok"):
                    self.log(f"    ⚠ {nome}: linkOcorrencias não encontrado (diag={res.get('diag')[:3] if res.get('diag') else '[]'})")
                    continue
                self.log(f"    ✓ {nome}: linkOcorrencias clicado via {res.get('via')}")
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1500)
                # Conta linhas com input valorDevido
                inputs = self._page.locator("input[id$=':valorDevido']")
                n = inputs.count()
                if n == 0:
                    self.log(f"    ⚠ {nome}: 0 ocorrências encontradas em parametrizar-ocorrencia")
                    continue
                proporcionalizar = bool(getattr(v.parametros.valor_devido, "proporcionalizar", False))
                # Estratégia: se proporcionalizar, distribuir igualmente; senão, total no primeiro
                if proporcionalizar:
                    por_linha = round(valor_total / n, 2)
                    valores = [por_linha] * n
                    # Ajuste de centavos no último item
                    diff = round(valor_total - por_linha * n, 2)
                    if diff:
                        valores[-1] = round(valores[-1] + diff, 2)
                else:
                    valores = [valor_total] + [0.0] * (n - 1)
                # Preenche cada linha via JS direto + dispatch blur
                for i in range(n):
                    val_br = _fmt_br(valores[i])
                    el = inputs.nth(i)
                    el_id = el.evaluate("e => e.id")
                    self._page.evaluate(
                        """([id, valor]) => {
                            const el = document.getElementById(id);
                            if (!el) return false;
                            el.value = valor;
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            el.dispatchEvent(new Event('blur', {bubbles: true}));
                            return true;
                        }""",
                        [el_id, val_br],
                    )
                self._aguardar_ajax(3000)
                self.log(f"    ✓ {nome}: {n} ocorrência(s) preenchidas (total {valor_total} BRL)")
                # Salvar a página de ocorrências
                try:
                    self._clicar_salvar_flex()
                    sucesso = self._aguardar_operacao_sucesso(timeout_ms=12000, bloqueante=False)
                    if sucesso:
                        self.log(f"    ✓ {nome}: ocorrências salvas")
                    else:
                        self.log(f"    ⚠ {nome}: save sem confirmação")
                except Exception as e:
                    self.log(f"    ⚠ {nome}: erro ao salvar: {e}")
            except Exception as e:
                self.log(f"    ⚠ {nome}: erro geral: {e}")

    def _configurar_ocorrencias_informado_inline(self, v) -> None:
        """Após salvar verba INFORMADO, navegar para suas Ocorrências (mesma
        conv Seam) e setar valorDevido em pelo menos uma linha.

        Usa o mesmo padrão A4J onclick-exec de _configurar_parametros_pos_expresso
        para invocar linkOcorrencias da linha da verba, que é confiável.
        """
        nome = v.nome_pjecalc or getattr(v, "expresso_alvo", None)
        valor_total = float(v.parametros.valor_devido.valor_informado_brl)
        proporcionalizar = bool(getattr(v.parametros.valor_devido, "proporcionalizar", False))
        candidatos = [v.nome_pjecalc]
        if hasattr(v, "expresso_alvo") and v.expresso_alvo and v.expresso_alvo != v.nome_pjecalc:
            candidatos.append(v.expresso_alvo)
        self.log(f"    → Ocorrências INFORMADO de '{nome}': valor={valor_total}, proporcionalizar={proporcionalizar}")

        # Voltar para listagem (URL-nav direto preservando conv)
        self._navegar_menu("li_calculo_verbas")
        self._aguardar_ajax(10000)
        self._page.wait_for_timeout(1500)

        # ⚠ PROATIVO (24/05/2026; refinado 25/05/2026): regerar ocorrências
        # ANTES de tentar linkOcorrencias. Para verbas INFORMADO+DESLIGAMENTO
        # com período curto (ex.: INDENIZAÇÃO POR DANO MORAL), o save de
        # parâmetros NÃO sincroniza automaticamente as ocorrências com o novo
        # período — ocorrências antigas (defaults Expresso) ficam fora do range.
        # Regerar antes força PJE-Calc a gerar com período corrente.
        #
        # ⚠ FIX 25/05/2026 (DOM forense, dump_pre_recovery): clicar
        # `regerarOcorrencias` abre `<rich:modalPanel>` "Confirmação" com
        # botões Ok/Cancelar. Bot anterior usava `page.once("dialog")` que
        # NÃO captura modal JSF (só dialogs nativos do browser). Modal ficava
        # aberta, bloqueava `linkOcorrencias` subsequente → 0 inputs valorDevido.
        # Helper `_regerar_com_modal_confirmacao` clica Ok no modal.
        #
        # sobrescrever=True para descartar ocorrências antigas (fora do
        # período curto) e gerar novas dentro do range.
        try:
            ok_regerar = self._regerar_com_modal_confirmacao(
                sobrescrever=True,
                log_prefix="    ",
            )
            if ok_regerar:
                self.log(f"    ✓ Regerar Ocorrências proativo (pré linkOcorrencias)")
        except Exception as _e:
            self.log(f"    ⚠ Regerar proativo: {_e}")

        # FORENSE (25/05/2026 v2): dump DOM ANTES de clicar linkOcorrencias —
        # capturar estado real da listagem após PROATIVO Regerar.
        try:
            self._dump_dom_indenizacao(nome, fase="pre_click")
        except Exception as _ed:
            self.log(f"    ⚠ DOM dump pre_click: {_ed}")

        # Interceptar respostas HTTP durante o click linkOcorrencias para
        # diagnosticar se AJAX retornou rejeição/redirect/listagem
        _net_log: list = []
        def _on_response(resp):
            try:
                url = resp.url
                if "verba-calculo" in url or "parametrizar-ocorrencia" in url or ".jsf" in url:
                    _net_log.append({
                        "url": url[-100:],
                        "status": resp.status,
                        "method": resp.request.method,
                        "content_type": (resp.headers.get("content-type") or "")[:50],
                    })
            except Exception:
                pass
        self._page.on("response", _on_response)

        # Esperar msgAguarde sumir antes de clicar (PROATIVO Regerar pode
        # ainda estar processando server-side mesmo após networkidle).
        try:
            self._page.wait_for_function(
                """() => {
                    const m = document.getElementById('formulario:msgAguarde');
                    if (!m) return true;
                    const s = window.getComputedStyle(m);
                    return s.display === 'none' || s.visibility === 'hidden';
                }""",
                timeout=15000,
            )
        except Exception:
            self.log(f"    ⚠ msgAguarde ainda visível após 15s — prosseguindo mesmo assim")

        # Clicar linkOcorrencias usando MATCH EXATO POR TD + NATIVE Playwright click.
        # HISTÓRICO 25/05/2026:
        # - dump pre_click: matcher antigo tr.textContent.includes() casava TR
        #   de layout outermost → pegava row 0 (13º) em vez de INDENIZAÇÃO.
        #   Fix: match EXATO no td da MESMA linha do link.
        # - dump post_click: onclick-exec disparava A4J.AJAX.Submit mas servidor
        #   não navegava (mesmo padrão do bug linkParametrizar). Fix per CLAUDE.md:
        #   "Native Playwright click — respeita return false de A4J.AJAX.Submit,
        #   evita #irTopoPagina quebrar AJAX".
        # Estratégia: JS LOCALIZA id; Playwright CLICA via locator.click(force=True).
        target_id = self._page.evaluate(
            """(candidatos) => {
                const norm = s => (s||'').toUpperCase().replace(/\\s+/g,' ').trim()
                                          .replace(/EXIBIR|OCULTAR/g, '').trim();
                const linksMain = [...document.querySelectorAll('a.linkOcorrencias')]
                    .filter(a => a.id && !a.id.includes(':listaReflexo:'));
                for (const alvo of candidatos) {
                    const alvoN = norm(alvo);
                    for (const a of linksMain) {
                        const tr = a.closest('tr');
                        if (!tr) continue;
                        const tds = [...tr.querySelectorAll('td')];
                        for (const td of tds) {
                            if (norm(td.textContent) === alvoN) {
                                window.__lastLinkOcorrencias = {
                                    id: a.id, title: a.title || '',
                                    row_tds: tds.map(t => (t.textContent||'').trim().slice(0,30))
                                };
                                return a.id;
                            }
                        }
                    }
                }
                return null;
            }""",
            candidatos,
        )
        if not target_id:
            self.log(f"    ⚠ linkOcorrencias não encontrado para candidatos: {candidatos}")
            return
        meta_dbg = self._page.evaluate("() => window.__lastLinkOcorrencias")
        self.log(f"    → linkOcorrencias id={target_id} meta={meta_dbg}")

        # ⚠ CASCADE 25/05/2026: PJE-Calc Cidadão H2 local NÃO navega de
        # listagem→Ocorrências de forma confiável via onclick (limite arquitetural
        # documentado em CLAUDE.md p/ linkParametrizar; mesmo bug aqui em linkOcorrencias).
        # Estratégia: tentar 4 mecanismos em sequência. Success = inputs valorDevido > 0
        # após wait. Se A funcionar, continua normal. Se nenhum funcionar, cai no
        # recovery existente (Regerar+retry).
        def _try_strategy(strat: str) -> tuple[bool, int]:
            """Executa 1 strategy + aguarda + retorna (success, n_inputs)."""
            try:
                if strat == "A":
                    self._page.evaluate(
                        """(id) => {
                            const a = document.getElementById(id);
                            if (!a) return false;
                            const onclickStr = a.getAttribute('onclick') || '';
                            if (!onclickStr) return false;
                            const ev = new MouseEvent('click', {bubbles:true, cancelable:true, view:window});
                            try { Object.defineProperty(ev, 'target', {value:a, configurable:true}); } catch(_){}
                            try { Object.defineProperty(ev, 'currentTarget', {value:a, configurable:true}); } catch(_){}
                            try { new Function('event', onclickStr).call(a, ev); return true; }
                            catch(_){ return false; }
                        }""",
                        target_id,
                    )
                elif strat == "B":
                    esc = target_id.replace(":", "\\:")
                    self._page.locator(f"a#{esc}").first.click(force=True)
                elif strat == "C":
                    self._page.evaluate(
                        """(id) => {
                            if (typeof jsfcljs !== 'function') return false;
                            const f = document.getElementById('formulario');
                            if (!f) return false;
                            const params = {}; params[id] = id;
                            try { jsfcljs(f, params, ''); return true; } catch(_){ return false; }
                        }""",
                        target_id,
                    )
                elif strat == "D":
                    self._page.evaluate(
                        """(id) => {
                            const f = document.getElementById('formulario');
                            if (!f) return false;
                            const inp = document.createElement('input');
                            inp.type = 'hidden'; inp.name = id; inp.value = id;
                            f.appendChild(inp);
                            try { f.submit(); return true; } catch(_){ return false; }
                        }""",
                        target_id,
                    )
            except Exception as e:
                self.log(f"      strat {strat} exception: {str(e)[:80]}")
                return (False, 0)
            self._aguardar_ajax(15000)
            self._page.wait_for_timeout(2500)
            # msgAguarde sumir
            try:
                self._page.wait_for_function(
                    """() => {
                        const m = document.getElementById('formulario:msgAguarde');
                        if (!m) return true;
                        const s = window.getComputedStyle(m);
                        return s.display === 'none' || s.visibility === 'hidden';
                    }""",
                    timeout=15000,
                )
            except Exception:
                pass
            self._page.wait_for_timeout(1000)
            n_inputs = self._page.locator("input[id$=':valorDevido']").count()
            return (n_inputs > 0, n_inputs)

        success_strat: str | None = None
        n: int = 0
        for strat in ["A", "B", "C", "D"]:
            ok, n = _try_strategy(strat)
            self.log(f"    → Strategy {strat}: ok={ok} n_inputs={n}")
            if ok:
                success_strat = strat
                self.log(f"    ✓ linkOcorrencias navegou via Strategy {strat} ({n} inputs valorDevido)")
                break
            # Antes da próxima strategy, garantir que estamos na listagem
            # (strategies anteriores podem ter mudado o estado)
            if strat != "D":
                try:
                    url_now = self._page.url
                    if "verba-calculo.jsf" not in url_now:
                        self._navegar_menu("li_calculo_verbas")
                        self._aguardar_ajax(8000)
                        self._page.wait_for_timeout(1500)
                except Exception:
                    pass
        if success_strat is None:
            self.log(f"    ⚠ NENHUMA das 4 strategies (A/B/C/D) navegou para Ocorrências")
        clicou = {"ok": success_strat is not None, "via": f"cascade:{success_strat}"}

        # Desconectar listener network + log respostas capturadas
        try:
            self._page.remove_listener("response", _on_response)
        except Exception:
            pass
        if _net_log:
            self.log(f"    ℹ Net pós-cascade ({len(_net_log)} resp): {_net_log[:5]}")

        # FORENSE v2: dump pós-cascade
        try:
            self._dump_dom_indenizacao(nome, fase="post_click")
        except Exception as _ed:
            self.log(f"    ⚠ DOM dump post_click: {_ed}")

        # Re-checar inputs valorDevido (success_strat já garantiu n > 0)
        inputs = self._page.locator("input[id$=':valorDevido']")
        n = inputs.count()
        if n == 0:
            self.log(f"    ⚠ 0 inputs valorDevido encontrados — tentando Regerar Ocorrências + retry")
            # ⚠ FORENSE (25/05/2026): dump DOM completo pré-recovery para investigar
            # porque a página de Ocorrências está sem inputs valorDevido. Necessário
            # entender se é (A) página não navegou, (B) tabela vazia por filtro,
            # (C) IDs diferentes de :valorDevido, (D) inputs ocultos.
            try:
                self._dump_dom_indenizacao(nome, fase="pre_recovery")
            except Exception as _ed:
                self.log(f"    ⚠ DOM dump pre_recovery: {_ed}")
            # ⚠ RECOVERY (24/05/2026): para verbas INFORMADO+DESLIGAMENTO com
            # período curto (ex.: INDENIZAÇÃO POR DANO MORAL), o PJE-Calc
            # pode não ter gerado ocorrências (defaults Expresso usam período
            # diferente). Voltar à listagem, Regerar Ocorrências (botão da
            # listagem), depois re-navegar para linkOcorrencias dessa verba.
            try:
                self._navegar_menu("li_calculo_verbas")
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1500)
                # FIX 25/05/2026: usar helper com modal handling correto
                clicou_regerar = self._regerar_com_modal_confirmacao(
                    sobrescrever=True,
                    log_prefix="    ",
                )
                if clicou_regerar:
                    self.log(f"    ✓ Regerar Ocorrências disparado — re-navegando para linkOcorrencias")
                    # Re-acionar linkOcorrencias
                    clicou_retry = self._page.evaluate(
                        """(candidatos) => {
                            const norm = s => (s||'').toUpperCase().replace(/\\s+/g,' ').trim();
                            const linksMain = [...document.querySelectorAll('a.linkOcorrencias')]
                                .filter(a => a.id && !a.id.includes(':listaReflexo:'));
                            for (const alvo of candidatos) {
                                const alvoN = norm(alvo);
                                for (const a of linksMain) {
                                    const tr = a.closest('tr');
                                    if (!tr) continue;
                                    const tds = [...tr.querySelectorAll('td')];
                                    for (const td of tds) {
                                        const txt = norm(td.textContent.replace(/Exibir|Ocultar/gi,''));
                                        if (txt === alvoN) {
                                            const onclickStr = a.getAttribute('onclick') || '';
                                            if (onclickStr) {
                                                try { new Function('event', onclickStr).call(a, new MouseEvent('click',{bubbles:true})); return true; } catch(_){}
                                            }
                                            a.click(); return true;
                                        }
                                    }
                                }
                            }
                            return false;
                        }""",
                        candidatos,
                    )
                    if clicou_retry:
                        self._aguardar_ajax(8000)
                        self._page.wait_for_timeout(2000)
                        inputs = self._page.locator("input[id$=':valorDevido']")
                        n = inputs.count()
                        if n > 0:
                            self.log(f"    ✓ Recovery OK — {n} inputs valorDevido disponíveis")
                        else:
                            self.log(f"    ⚠ Recovery falhou — ainda 0 inputs após Regerar+retry")
                            try:
                                self._dump_dom_indenizacao(nome, fase="post_recovery")
                            except Exception as _ed:
                                self.log(f"    ⚠ DOM dump post_recovery: {_ed}")
                            return
                    else:
                        self.log(f"    ⚠ Recovery falhou: não conseguiu re-clicar linkOcorrencias")
                        return
                else:
                    self.log(f"    ⚠ Botão Regerar Ocorrências não encontrado — pulando recovery")
                    return
            except Exception as e:
                self.log(f"    ⚠ Recovery 0 inputs valorDevido falhou: {e}")
                return

        # ⚠ FILTRO DESLIGAMENTO (25/05/2026, portado de playwright_pjecalc.py v1):
        # PJE-Calc Cidadão gera ocorrências MENSAIS por todo o período do
        # contrato, IGNORANDO o ocorrencia_pagamento=DESLIGAMENTO (mesmo
        # com Sobrescrever=true em Regerar). Para 1-day DESLIGAMENTO (ex.
        # INDENIZAÇÃO POR DANO MORAL), restam N (ex 9) linhas onde apenas
        # a ÚLTIMA (mês de demissão) deveria estar ativa.
        #
        # Bot escrevendo 5000 em row[0] (mês mais antigo) → JSF reclama
        # "ocorrências fora do período". Solução: desmarcar :ativo de
        # TODAS exceto a última, depois escrever valor na última.
        ocorrencia_pagto = str(getattr(v.parametros, "ocorrencia_pagamento", "")).upper()
        is_desligamento = "DESLIGAMENTO" in ocorrencia_pagto
        if is_desligamento and n > 1:
            try:
                r = self._page.evaluate("""() => {
                    const cbxs = [...document.querySelectorAll(
                        'input[type="checkbox"][id*=":listagem:"][id$=":ativo"]'
                    )].filter(c => !c.id.includes('ativarTodos')
                                 && !c.id.includes('selecionarTodos')
                                 && !c.id.includes('listaReflexo'));
                    const indexed = cbxs.map(c => {
                        const m = c.id.match(/:listagem:(\\d+):ativo$/);
                        return {cbx: c, idx: m ? parseInt(m[1]) : -1};
                    }).filter(x => x.idx >= 0).sort((a, b) => a.idx - b.idx);
                    if (indexed.length === 0) return {erro: 'no cbx'};
                    const ultimaIdx = indexed[indexed.length - 1].idx;
                    let desmarcados = 0, mantidos = 0;
                    indexed.forEach(({cbx, idx}) => {
                        if (idx === ultimaIdx) {
                            if (!cbx.checked) cbx.click();
                            mantidos++;
                        } else {
                            if (cbx.checked) { cbx.click(); desmarcados++; }
                        }
                    });
                    return {desmarcados, mantidos, total: indexed.length, ultimaIdx};
                }""")
                self.log(f"    ✓ Filtro DESLIGAMENTO: última={r.get('ultimaIdx')}, desmarcadas={r.get('desmarcados')}, total={r.get('total')}")
                if r.get("desmarcados", 0):
                    self._aguardar_ajax(5000)
                    self._page.wait_for_timeout(1000)
            except Exception as _e_des:
                self.log(f"    ⚠ Filtro DESLIGAMENTO: {_e_des}")

        # Distribuir valor
        if proporcionalizar:
            por_linha = round(valor_total / n, 2)
            valores = [por_linha] * n
            diff = round(valor_total - por_linha * n, 2)
            if diff:
                valores[-1] = round(valores[-1] + diff, 2)
        elif is_desligamento:
            # Para DESLIGAMENTO: valor vai na ÚLTIMA linha (mês de demissão),
            # outras = 0 (já foram desmarcadas com :ativo=false acima).
            valores = [0.0] * (n - 1) + [valor_total]
        else:
            valores = [valor_total] + [0.0] * (n - 1)

        for i in range(n):
            val_br = _fmt_br(valores[i])
            el = inputs.nth(i)
            try:
                el_id = el.evaluate("e => e.id")
                self._page.evaluate(
                    """([id, valor]) => {
                        const el = document.getElementById(id);
                        if (!el) return false;
                        el.value = valor;
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        el.dispatchEvent(new Event('blur', {bubbles: true}));
                        return true;
                    }""",
                    [el_id, val_br],
                )
            except Exception as e:
                self.log(f"      ⚠ valorDevido[{i}] = {val_br}: {e}")
        self._aguardar_ajax(3000)
        self.log(f"    ✓ {n} ocorrência(s) preenchidas (total {valor_total} BRL)")

        # Salvar
        try:
            self._clicar_salvar_flex()
            sucesso = self._aguardar_operacao_sucesso(timeout_ms=15000, bloqueante=False)
            if sucesso:
                self.log(f"    ✓ Ocorrências de '{nome}' salvas")
            else:
                self.log(f"    ⚠ Ocorrências de '{nome}': sem confirmação de save")
        except Exception as e:
            self.log(f"    ⚠ Erro ao salvar ocorrências: {e}")

        # REGRA OPERACIONAL (25/05/2026, usuário): toda alteração de
        # ocorrência exige Regerar para PJE-Calc recompute downstream.
        # sobrescrever=False — preservar os valorDevido que acabamos de
        # editar (apenas regera ocorrências cujo período está sem mensal).
        try:
            self._navegar_menu("li_calculo_verbas")
            self._aguardar_ajax(6000)
            self._page.wait_for_timeout(800)
            if self._regerar_com_modal_confirmacao(
                sobrescrever=False, log_prefix="    "
            ):
                self.log(f"    ✓ Regerar pós-ocorrências '{nome}'")
        except Exception as _e:
            self.log(f"    ⚠ Regerar pós-ocorrências: {_e}")

    def _dump_dom_indenizacao(self, verba_nome: str, fase: str) -> None:
        """Captura snapshot DOM completo da página de Ocorrências quando bot
        vê 0 inputs valorDevido. Salva JSON + screenshot em /tmp/pjecalc_snapshots/.
        Endpoint `/api/diag/list_dumps` permite recuperar.
        """
        import pathlib as _pl, os as _os, json as _json, re as _re
        sessao = self.sessao_id or _os.environ.get("PJECALC_SESSAO_ID") or "unknown"
        safe_nome = _re.sub(r"[^A-Za-z0-9]+", "_", verba_nome or "verba")[:40]
        snap_dir = _pl.Path("/tmp/pjecalc_snapshots")
        snap_dir.mkdir(parents=True, exist_ok=True)
        stem = f"diag_indenizacao_{sessao}_{safe_nome}_{fase}"
        # 1. Dump DOM info
        info = self._page.evaluate("""() => {
            const all_inputs = [...document.querySelectorAll('input,select,textarea')]
                .map(e => ({tag: e.tagName, type: e.type||'', id: e.id||'', name: e.name||'',
                            value: (e.value||'').slice(0,60), disabled: !!e.disabled,
                            hidden: e.offsetParent === null}));
            const tables = [...document.querySelectorAll('table')]
                .filter(t => t.id || (t.className||'').includes('list') || (t.className||'').includes('dataTable'))
                .map(t => ({id: t.id, class: (t.className||'').slice(0,80),
                            rows: t.querySelectorAll('tr').length,
                            colgroups: t.querySelectorAll('colgroup').length,
                            html_first_500: (t.outerHTML||'').slice(0, 500)}));
            const msgs = [...document.querySelectorAll('.rich-message,.rich-messages,.box-msg-livre,[class*="message"],[class*="msg"]')]
                .map(e => (e.textContent||'').trim().replace(/\\s+/g,' ').slice(0,300))
                .filter(Boolean);
            const selectsAll = [...document.querySelectorAll('select')]
                .map(s => ({id: s.id||'', name: s.name||'', value: s.value||'',
                            n_opts: s.options.length,
                            first_opts: [...s.options].slice(0,8).map(o => (o.text||'').slice(0,40))}));
            const filtros = [...document.querySelectorAll('input[type="text"],input[type="search"]')]
                .filter(i => /filtro|busca|search|mes|ano/i.test(i.id||i.name||''))
                .map(i => ({id: i.id, name: i.name, value: i.value}));

            // FORENSE v2 (25/05/2026): elementos-chave para entender bug INDENIZAÇÃO
            // (a) msgAguarde — modal "Processando..." do PJE-Calc
            const msgAguarde = (() => {
                const m = document.getElementById('formulario:msgAguarde');
                if (!m) return {present: false};
                const s = window.getComputedStyle(m);
                return {present: true, display: s.display, visibility: s.visibility,
                        offsetParent_null: m.offsetParent === null};
            })();
            // (b) Todos os linkOcorrencias da listagem (não-reflexo)
            const allLinkOcorr = [...document.querySelectorAll('a.linkOcorrencias')]
                .filter(a => !a.id.includes(':listaReflexo:'))
                .map(a => {
                    const tr = a.closest('tr');
                    const tds = tr ? [...tr.querySelectorAll('td')].map(t => (t.textContent||'').trim().slice(0,40)) : [];
                    return {
                        id: a.id || '',
                        title: a.title || '',
                        cls: (a.className||'').slice(0,60),
                        href: (a.href||'').slice(0,80),
                        onclick_len: (a.getAttribute('onclick')||'').length,
                        onclick_first_200: (a.getAttribute('onclick')||'').slice(0,200),
                        disabled_attr: a.hasAttribute('disabled'),
                        offset_null: a.offsetParent === null,
                        tr_tds: tds.slice(0,8),
                    };
                });
            // (c) RichFaces queue / AJAX in flight
            const a4jStatus = (() => {
                try {
                    if (typeof A4J !== 'undefined' && A4J.AJAX && A4J.AJAX.QUEUE) {
                        const q = A4J.AJAX.QUEUE;
                        return {has_queue: true, requestList_len: (q.requestList||[]).length};
                    }
                } catch(_) {}
                return {has_queue: false};
            })();
            // (d) Listar todos rich:modalPanel visíveis
            const visibleModals = [...document.querySelectorAll('[id*=":mp_"], div.rich-modalpanel, [class*="modal"]')]
                .filter(el => {
                    if (el.offsetParent === null) return false;
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden';
                })
                .map(el => ({id: el.id||'', cls: (el.className||'').slice(0,80),
                             text: (el.textContent||'').trim().replace(/\\s+/g,' ').slice(0,150)}));

            return {
                url: location.href,
                title: document.title,
                body_text_first_2000: (document.body.innerText||'').slice(0, 2000),
                msgAguarde,
                allLinkOcorr,
                a4jStatus,
                visibleModals,
                inputs_total: all_inputs.length,
                valorDevido_inputs: document.querySelectorAll('input[id$=":valorDevido"]').length,
                valorDevido_inputs_partial: document.querySelectorAll('input[id*="valorDevido"]').length,
                valorPago_inputs: document.querySelectorAll('input[id*="valorPago"]').length,
                hidden_inputs_valorDevido: [...document.querySelectorAll('input[id*="valorDevido"]')]
                    .filter(e => e.offsetParent === null).length,
                tables: tables.slice(0, 10),
                msgs: msgs.slice(0, 10),
                selects: selectsAll,
                filtros: filtros,
                inputs_sample: all_inputs.filter(i => i.id.includes('formulario:')).slice(0, 40),
                inputs_with_valor: all_inputs.filter(i => /valor/i.test(i.id||i.name)).slice(0, 30),
                body_html_first_4000: (document.body.innerHTML||'').slice(0, 4000),
            };
        }""")
        json_path = snap_dir / f"{stem}.json"
        json_path.write_text(_json.dumps({
            "sessao": sessao, "verba": verba_nome, "fase": fase,
            "info": info,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        # 2. Screenshot
        try:
            shot_path = snap_dir / f"{stem}.png"
            self._page.screenshot(path=str(shot_path), full_page=True)
        except Exception:
            pass
        self.log(f"    📸 DOM dump salvo: {json_path.name}")

    def _regerar_com_modal_confirmacao(
        self,
        sobrescrever: bool = False,
        timeout_modal_ms: int = 8000,
        timeout_ajax_ms: int = 15000,
        log_prefix: str = "  ",
    ) -> bool:
        """Click Regerar Ocorrências + handle rich:modalPanel "Confirmação".

        Fluxo descoberto via DOM dump forense (25/05/2026):
        1. Click `formulario:regerarOcorrencias` abre `<rich:modalPanel>` com
           título "Confirmação", texto "Deseja gerar novamente as ocorrências
           das verbas e/ou reflexos selecionados?" e botões "Ok" / "Cancelar".
        2. Modal é overlay HTML+CSS — NÃO é dialog do browser. `page.on("dialog")`
           NÃO captura. Bot precisa achar e clicar o botão "Ok" no DOM.
        3. Se modal não for confirmada, fica aberta e BLOQUEIA navegação
           (incluindo cliques em `linkOcorrencias` de outras linhas) —
           causando o sintoma "0 inputs valorDevido em INDENIZAÇÃO POR DANO MORAL".

        Args:
            sobrescrever: se True, pré-seleciona radio `tipoRegeracao:1`
                (Sobrescrever) antes de clicar Regerar. Necessário para
                INDENIZAÇÃO+DESLIGAMENTO+período curto onde ocorrências
                antigas (defaults Expresso) ficam fora do range.

        Returns:
            True se Regerar completou (modal confirmada + AJAX concluído).
            False em qualquer ponto de falha.
        """
        # 1. Pré-selecionar radio Sobrescrever se necessário
        if sobrescrever:
            try:
                self._page.evaluate(
                    """() => {
                        const r = document.querySelector("input[id='formulario:tipoRegeracao:1']");
                        if (!r) return false;
                        r.checked = true;
                        r.dispatchEvent(new Event('change', {bubbles: true}));
                        r.dispatchEvent(new Event('click', {bubbles: true}));
                        // Também atualizar manterAlteracoes hidden (true=manter, false=sobrescrever)
                        const h = document.querySelector("input[id='formulario:manterAlteracoes']");
                        if (h) h.value = 'false';
                        return true;
                    }"""
                )
            except Exception:
                pass

        # 2. Click Regerar button
        btn_regerar = self._page.locator(
            "input[id$=':regerarOcorrencias'], input[id*=':regerarOcorrencias']"
        )
        if btn_regerar.count() == 0:
            btn_regerar = self._page.locator(
                "input[type='submit'][value='Regerar'], input[type='button'][value='Regerar']"
            )
        if btn_regerar.count() == 0:
            self.log(f"{log_prefix}⚠ Botão Regerar não encontrado na listagem")
            return False
        try:
            btn_regerar.first.click(force=True)
        except Exception as e:
            self.log(f"{log_prefix}⚠ Falha click Regerar: {e}")
            return False

        # 3. Aguardar modal aparecer (botão Ok visível)
        try:
            self._page.wait_for_function(
                """() => {
                    const btns = [...document.querySelectorAll(
                        'input[type=\"button\"], input[type=\"submit\"], button'
                    )];
                    for (const b of btns) {
                        const txt = (b.value || b.textContent || '').trim();
                        if (/^Ok$/i.test(txt) && b.offsetParent !== null) return true;
                    }
                    return false;
                }""",
                timeout=timeout_modal_ms,
            )
        except Exception:
            # Modal pode não aparecer se: (a) lista vazia, (b) já confirmado.
            # Aguardar AJAX caso tenha sido confirmação inline.
            self._aguardar_ajax(timeout_ajax_ms)
            return True

        # 4. Click "Ok" dentro da modal
        clicou_ok = self._page.evaluate(
            """() => {
                const btns = [...document.querySelectorAll(
                    'input[type="button"], input[type="submit"], button'
                )];
                for (const b of btns) {
                    if (b.offsetParent === null) continue;
                    const txt = (b.value || b.textContent || '').trim();
                    if (/^Ok$/i.test(txt)) {
                        const onclickStr = b.getAttribute('onclick') || '';
                        if (onclickStr) {
                            try {
                                new Function('event', onclickStr).call(b, new MouseEvent('click',{bubbles:true}));
                                return 'onclick-exec';
                            } catch(_) {}
                        }
                        b.click();
                        return 'click';
                    }
                }
                return null;
            }"""
        )
        if not clicou_ok:
            self.log(f"{log_prefix}⚠ Botão Ok da modal Regerar não encontrado")
            return False

        # 5. Aguardar AJAX + modal fechar
        self._aguardar_ajax(timeout_ajax_ms)
        try:
            self._page.wait_for_function(
                """() => {
                    const btns = [...document.querySelectorAll(
                        'input[type="button"], input[type="submit"], button'
                    )];
                    for (const b of btns) {
                        const txt = (b.value || b.textContent || '').trim();
                        if (/^Ok$/i.test(txt) && b.offsetParent !== null) return false;
                    }
                    return true;
                }""",
                timeout=8000,
            )
        except Exception:
            self.log(f"{log_prefix}⚠ Modal Confirmação ainda visível após Ok — pode ter falhado")
            # Não fail hard — pode ter regenerado mesmo assim
        self._page.wait_for_timeout(1500)
        return True

    def _regerar_ocorrencias_verbas(self) -> None:
        """Volta à listagem de Verbas e clica Regerar Ocorrências.

        Botão `formulario:regerarOcorrencias` (a4j:commandButton, only
        `rendered=emModoListagem`). Abre `<rich:modalPanel>` "Confirmação"
        com botões Ok/Cancelar — handler via `_regerar_com_modal_confirmacao`.
        """
        try:
            self._navegar_menu("li_calculo_verbas")
            self._aguardar_ajax(10000)
            self._page.wait_for_timeout(1500)
            ok = self._regerar_com_modal_confirmacao(
                sobrescrever=False,
                log_prefix="  ",
            )
            if ok:
                self.log("  ✓ Ocorrências regeradas em todas as verbas")
            else:
                self.log("  ⚠ Regerar disparou mas sem confirmação")
        except Exception as e:
            self.log(f"  ⚠ Falha ao regerar ocorrências: {e}")

    def _lancar_expresso(self, verbas) -> None:
        """Lança verbas via página Expresso.

        Histórico:
        - 12/05/2026 — UMA POR VEZ (padrão Calc Machine), porque batch dava
          NPE em ApresentadorVerbaDeCalculo.carregarBasesParaPrincipal pós-save.
        - 23/05/2026 — voltou a BATCH para cálculos >2 verbas: o padrão
          one-by-one + Fechar+Reabrir entre cada satura a Hibernate session
          após 2 saves (verbasParaCalculo retorna lista vazia). NPE pós-batch
          é tolerável: as verbas FICAM salvas no DB, e Fechar+Reabrir recupera
          estado para fases seguintes.
        - Para 1-2 verbas, mantém one-by-one (sem trade-off de NPE).
        """
        if len(verbas) <= 2:
            return self._lancar_expresso_individual(verbas)
        return self._lancar_expresso_batch(verbas)

    def _lancar_expresso_batch(self, verbas) -> None:
        """Versão BATCH: abre Expresso UMA vez, marca TODAS, salva UMA vez."""
        self.log(f"  → Lançamento Expresso BATCH ({len(verbas)} verba(s), single save)")
        from modules.expresso_verbas_canonicas import resolver_verba_expresso

        # Resolver alvos canônicos
        alvos: list[str] = []
        for v in verbas:
            alvo_raw = v.expresso_alvo or ""
            alvo_canonico = resolver_verba_expresso(alvo_raw)
            alvo = (alvo_canonico or alvo_raw).strip().upper()
            alvos.append(alvo)
        self.log(f"  → Alvos: {alvos}")

        # Navegar para verba-calculo.jsf
        self._navegar_menu_via_click("li_calculo_verbas")
        self._aguardar_ajax(8000)
        self._page.wait_for_timeout(1000)
        try:
            if "verba-calculo.jsf" not in self._page.url and self._calculo_conversation_id:
                self._page.goto(
                    f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                    f"?conversationId={self._calculo_conversation_id}",
                    wait_until="domcontentloaded", timeout=20000,
                )
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1000)
        except Exception:
            pass

        # Click Expresso (entrar na grade de checkboxes)
        try:
            self._clicar("lancamentoExpresso")
        except Exception as e:
            self.log(f"  ⚠ click lancamentoExpresso falhou: {e}")
            return
        self._aguardar_ajax(10000)
        self._page.wait_for_timeout(2000)

        total_cbs = self._page.evaluate(
            """() => document.querySelectorAll('input[type="checkbox"][id$=":selecionada"]').length"""
        )
        self.log(f"    ℹ Página Expresso: {total_cbs} checkboxes")
        if total_cbs == 0:
            self.log(f"  ⚠ Expresso vazio — abortando batch")
            return

        # Marcar TODAS as checkboxes alvo de uma vez (sem AJAX entre marks)
        res = self._page.evaluate(
            """(alvos) => {
                const norm = s => (s||'')
                    .normalize('NFC')
                    .replace(/[\\u00A0\\u200B\\u202F\\u2007\\uFEFF]/g, ' ')
                    .replace(/\\s+/g, ' ').trim().toUpperCase();
                const targets = alvos.map(norm);
                const cbs = [...document.querySelectorAll('input[type="checkbox"][id$=":selecionada"]')];
                const candidates = cbs.map(cb => {
                    const td = cb.closest('td');
                    return { cb, normTxt: norm(td ? td.textContent : '') };
                });
                const marcadas = [];
                const naoEncontradas = [];
                for (const tgt of targets) {
                    let achou = false;
                    // 1. Exact match
                    for (const c of candidates) {
                        if (!c.cb.checked && c.normTxt === tgt) {
                            c.cb.click(); marcadas.push(c.normTxt.slice(0,80)); achou = true; break;
                        }
                    }
                    if (achou) continue;
                    // 2. Tighter match (remove espaços/hífens)
                    const tight = s => s.replace(/[\\s\\-]+/g, '');
                    const tgtTight = tight(tgt);
                    for (const c of candidates) {
                        if (!c.cb.checked && tight(c.normTxt) === tgtTight) {
                            c.cb.click(); marcadas.push(c.normTxt.slice(0,80)); achou = true; break;
                        }
                    }
                    if (!achou) naoEncontradas.push(tgt);
                }
                return { marcadas, naoEncontradas };
            }""",
            alvos,
        )
        self.log(f"  ✓ Marcadas {len(res.get('marcadas', []))}: {res.get('marcadas', [])}")
        if res.get("naoEncontradas"):
            self.log(f"  ⚠ Não encontradas: {res.get('naoEncontradas')}")

        # Salvar UMA vez para todas
        try:
            self._clicar("salvar")
            self._aguardar_ajax(30000)  # generoso — batch save pode ser lento
            self._aguardar_operacao_sucesso(timeout_ms=20000, bloqueante=False)
        except Exception as e:
            self.log(f"  ⚠ Batch save falhou: {e}")

        # Capturar nova conv pós-batch
        self._capturar_conversation_id()
        self.log(f"  ✓ Batch save concluído — conv={self._calculo_conversation_id}")

        # NÃO chamar Fechar+Reabrir aqui — o código de fase_verbas (linha
        # 2250) já faz pós-Expresso. Duplicar quebra o estado Seam (segunda
        # tentativa não acha li_operacoes_fechar no sidebar do calc aberto
        # via Recentes, e tudo desmorona pra frente). Deixar o caller decidir.

    def _lancar_expresso_individual(self, verbas) -> None:
        """Versão UMA POR VEZ (1-2 verbas — sem trade-off de NPE)."""
        self.log(f"  → Lançamento Expresso ({len(verbas)} verba(s), uma por vez)")

        # Resolver expresso_alvo de cada verba contra a lista canônica das 54
        # (módulo expresso_verbas_canonicas). Garante que nomes com trailing
        # spaces ou variações sutis do DB sejam encontrados.
        from modules.expresso_verbas_canonicas import resolver_verba_expresso

        for idx, v in enumerate(verbas):
            alvo_raw = v.expresso_alvo or ""
            # Resolver contra catálogo canônico (trata NBSP, trailing space, etc)
            alvo_canonico = resolver_verba_expresso(alvo_raw)
            if alvo_canonico:
                # Usar nome RAW canônico (com trailing space se houver) para match
                alvo = alvo_canonico.strip().upper()
                if alvo_canonico != alvo_raw:
                    self.log(f"  ℹ Expresso resolvido: '{alvo_raw}' → '{alvo_canonico.rstrip()}' (canônico)")
            else:
                alvo = alvo_raw.strip().upper()
                self.log(f"  ⚠ Verba '{alvo_raw}' não está nas 54 Expresso canônicas — tentando match aproximado")
            self.log(f"  → [{idx+1}/{len(verbas)}] Procurando e selecionando '{alvo}'...")

            # Garantir que estamos na listagem de verbas (li_calculo_verbas).
            # ⚠ CRÍTICO (22/05/2026): após salvar uma verba, apresentadorVerba pode
            # ficar em modo ALTERACAO/CONSULTA. O botão lancamentoExpresso tem
            # rendered="#{apresentador.emModoListagem}" — quando NÃO em listagem,
            # botão não renderiza e Expresso vem com 0 checkboxes (causa raiz
            # do bug Scarlette). Solução: SEMPRE navegar via sidebar (que invoca
            # o método correto para resetar emModoListagem=true) e aguardar
            # visibilidade real do botão antes de clicar.
            self._navegar_menu_via_click("li_calculo_verbas")
            self._aguardar_ajax(8000)
            self._page.wait_for_timeout(1000)

            # ⚠ CRÍTICO (23/05/2026): após Recentes reabertura, o sidebar click
            # às vezes NÃO transiciona para verba-calculo.jsf — fica em
            # calculo.jsf (Dados/Parâmetros). Forçar URL goto como fallback se
            # ainda não estamos na página correta. Sem isso, lancamentoExpresso
            # não é encontrado em iterações pós-Recentes (2/11+).
            try:
                _url_atual = self._page.url
                if "verba-calculo.jsf" not in _url_atual and self._calculo_conversation_id:
                    self.log(
                        f"  ℹ URL pós-click sidebar não é verba-calculo.jsf "
                        f"({_url_atual[-60:]}) — forçando URL goto"
                    )
                    self._page.goto(
                        f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                        f"?conversationId={self._calculo_conversation_id}",
                        wait_until="domcontentloaded",
                        timeout=20000,
                    )
                    self._aguardar_ajax(8000)
                    self._page.wait_for_timeout(1000)
            except Exception as _e:
                self.log(f"  ⚠ Fallback URL goto verba-calculo.jsf: {_e}")

            def _verificar_modo_listagem() -> dict:
                """Inspeciona se o bean está em modo listagem (botão lancamentoExpresso
                realmente renderizado E visível, não fantasma)."""
                return self._page.evaluate(
                    """() => {
                        const el = document.querySelector("[id$='lancamentoExpresso']");
                        if (!el) return {existe: false, visivel: false, modo_listagem: false};
                        // rendered=false produz elemento ausente ou display:none
                        const visivel = !!(el.offsetParent) && getComputedStyle(el).display !== 'none';
                        return {existe: true, visivel: visivel, modo_listagem: visivel};
                    }"""
                )

            # Aguardar até modo listagem confirmado (timeout 10s, 5 retries)
            for _retry in range(5):
                _diag = _verificar_modo_listagem()
                if _diag.get("modo_listagem"):
                    break
                self.log(
                    f"    ⏳ Aguardando emModoListagem=true "
                    f"(lancamentoExpresso existe={_diag.get('existe')} "
                    f"visivel={_diag.get('visivel')})"
                )
                # Forçar sidebar click novamente — invoca método que reseta modo
                self._navegar_menu_via_click("li_calculo_verbas")
                self._aguardar_ajax(3000)
                self._page.wait_for_timeout(800)
            else:
                self.log(
                    f"    ⚠ apresentadorVerba não voltou para modo listagem em 5 tentativas "
                    f"— prosseguindo (lancamentoExpresso pode estar fantasma no DOM)"
                )

            # CRÍTICO (21/05/2026): após salvar várias verbas Expresso, o estado
            # Seam degenera e a página Expresso retorna 0 checkboxes (lista vazia).
            # Detectar isso e fazer Fechar+Reabrir antes de re-tentar.
            def _entrar_expresso_com_retry() -> int:
                """Entra na página Expresso e retorna count de checkboxes."""
                self._clicar("lancamentoExpresso")
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1500)
                try:
                    return self._page.evaluate(
                        """() => document.querySelectorAll('input[type="checkbox"][id$=":selecionada"]').length"""
                    )
                except Exception:
                    return 0

            total_cbs = _entrar_expresso_com_retry()
            if total_cbs == 0:
                self.log(f"    ⚠ Página Expresso vazia (0 checkboxes) — Fechar+Reabrir + retry")
                self._fechar_e_reabrir_calculo(f"pré-Expresso retry {idx+1}/{len(verbas)}")
                # Pós-Fechar+Reabrir: sidebar click + URL fallback + aguardar modo listagem
                self._navegar_menu_via_click("li_calculo_verbas")
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1500)
                # URL fallback: igual ao da entrada do loop — pós-Recentes
                # sidebar click às vezes não leva para verba-calculo.jsf
                try:
                    if "verba-calculo.jsf" not in self._page.url and self._calculo_conversation_id:
                        self.log(
                            "    ℹ URL pós-click sidebar (retry) não é verba-calculo.jsf "
                            "— forçando URL goto"
                        )
                        self._page.goto(
                            f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                            f"?conversationId={self._calculo_conversation_id}",
                            wait_until="domcontentloaded",
                            timeout=20000,
                        )
                        self._aguardar_ajax(8000)
                        self._page.wait_for_timeout(1000)
                except Exception as _e:
                    self.log(f"    ⚠ Fallback URL goto verba-calculo.jsf (retry): {_e}")
                for _r in range(3):
                    if _verificar_modo_listagem().get("modo_listagem"):
                        break
                    self._navegar_menu_via_click("li_calculo_verbas")
                    self._aguardar_ajax(3000)
                total_cbs = _entrar_expresso_com_retry()
            self.log(f"    ℹ Página Expresso: {total_cbs} checkboxes disponíveis")

            # Marcar checkbox da verba alvo
            # CRÍTICO (21/05/2026): DB tem MULTA 477 e outras verbas com
            # espaços trailing ou caracteres invisíveis (NBSP, ZWS) que quebram
            # match exato. norm agora trata: NFC unicode + NBSP/ZWS/NNBSP→space
            # + collapse whitespace + trim + uppercase.
            res = self._page.evaluate(
                """(alvo) => {
                    const norm = s => (s||'')
                        .normalize('NFC')
                        .replace(/[\\u00A0\\u200B\\u202F\\u2007\\uFEFF]/g, ' ')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toUpperCase();
                    const alvoN = norm(alvo);
                    const cbs = [...document.querySelectorAll('input[type="checkbox"][id$=":selecionada"]')];
                    const candidatos = cbs.map(cb => {
                        const td = cb.closest('td');
                        return { cb, txt: td ? td.textContent : '', norm: norm(td ? td.textContent : '') };
                    });
                    // 1. Match exato
                    for (const c of candidatos) {
                        if (c.norm === alvoN) { c.cb.click(); return {ok: true, via: 'exact', txt: c.norm.slice(0,80)}; }
                    }
                    // 2. Match igualdade após remover múltiplos espaços E hífens
                    const tighter = s => s.replace(/[\\s\\-]+/g, '');
                    for (const c of candidatos) {
                        if (tighter(c.norm) === tighter(alvoN)) { c.cb.click(); return {ok: true, via: 'tighter', txt: c.norm.slice(0,80)}; }
                    }
                    // 3. Match parcial: alvo CONTÉM ou está CONTIDO (último recurso)
                    for (const c of candidatos) {
                        if (c.norm && (c.norm.includes(alvoN) || alvoN.includes(c.norm))) {
                            c.cb.click(); return {ok: true, via: 'partial', txt: c.norm.slice(0,80)};
                        }
                    }
                    // Falha → retornar diagnóstico
                    return {ok: false, total: cbs.length, amostra: candidatos.slice(0,10).map(c => c.norm.slice(0,80))};
                }""",
                alvo,
            )
            marcou = res.get('ok') if isinstance(res, dict) else False
            if marcou:
                via = res.get('via', '?')
                txt = res.get('txt', '')
                self.log(f"    ✓ Verba Expresso marcada via '{via}': '{txt}'")
            else:
                amostra = res.get('amostra', []) if isinstance(res, dict) else []
                total = res.get('total', '?') if isinstance(res, dict) else '?'
                self.log(f"    ⚠ Verba Expresso não encontrada: '{alvo}' (total checkboxes: {total})")
                self.log(f"       Amostra dos primeiros 10 checkboxes do Expresso:")
                for nome in amostra:
                    self.log(f"         • '{nome}'")
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

            # ⚠ CRÍTICO (22/05/2026) — OPÇÃO F: Goto verba-calculo.jsf após save,
            # depois Fechar+Reabrir, para reset Seam EPC + commit DB.
            #
            # Sem isso, a partir do 2º save o sidebar não tem
            # li_calculo_verbas (apresentador.emModoListagem=false) e o bot
            # falha em todas as iterações seguintes.
            #
            # Sequência: (1) goto verba-calculo.jsf?conversationId={new}
            # (página com sidebar completo); (2) _fechar_e_reabrir_calculo
            # (Fechar @End + commit DB + Reabrir via Recentes em conv fresh).
            #
            # NÃO fazer na ÚLTIMA verba — loop pós-Expresso já faz F+R.
            if idx < len(verbas) - 1 and self._calculo_conversation_id:
                try:
                    url_verba_listagem = (
                        f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                        f"?conversationId={self._calculo_conversation_id}"
                    )
                    self._page.goto(
                        url_verba_listagem,
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                    self._aguardar_ajax(10000)
                    self._page.wait_for_timeout(1000)
                except Exception as e:
                    self.log(f"  ⚠ Goto verba-calculo.jsf falhou: {e}")
                self._fechar_e_reabrir_calculo(
                    f"pós Expresso save [{idx+1}/{len(verbas)}: {alvo}]"
                )

    def _silenciar_dialog_confirma_valor(self) -> None:
        """Sobrescreve `checarValor` para evitar o jConfirm modal de mudança de valor.

        CRÍTICO (descoberto 18/05/2026 sessão cecf7937 inspecionando
        verba-calculo.xhtml linhas 1463-1474):

            function checarValor() {
                if (operacao != 'ALTERACAO') return true;
                valor = $('formulario:valor:0').checked ? 'CALCULADO' : 'INFORMADO';
                if (valor == valorAnterior) return true;
                return confirma('#{mensagens.MSG0025}', $('formulario:salvar'));
            }

        Quando estamos em modo ALTERACAO e mudamos `valor` (CALCULADO ↔
        INFORMADO), o onclick do botão Salvar dispara `confirma()` que
        renderiza um modal jQuery (jConfirm) pedindo confirmação. O bot
        não responde ao modal → save fica bloqueado, retornando false →
        cascata de falhas (próximas verbas perdem listagem, Fase 5b
        também perde HE 50%).

        Solução: sobrescrever `window.checarValor` para sempre retornar
        true. O save procede direto sem modal, e como o usuário JÁ
        explicitamente configurou valor=INFORMADO no JSON, não há razão
        legítima para pedir confirmação no bot.
        """
        try:
            self._page.evaluate(
                """() => {
                    try { window.checarValor = function() { return true; }; } catch(_) {}
                    // Belt-and-suspenders: também marca como "já confirmado"
                    try {
                        if (typeof window.lista === 'undefined') { window.lista = []; }
                        if (window.lista.indexOf('formulario:salvar') === -1) {
                            window.lista.push('formulario:salvar');
                        }
                    } catch(_) {}
                }"""
            )
        except Exception:
            pass

    def _preencher_valor_informado_devido(self, valor_brl: float) -> None:
        """Preenche o input 'Devido' do bloco INFORMADO.

        ID real DOM (confirmado em verba-calculo.xhtml linha 442):
            formulario:valorInformadoDoDevido

        O sufixo `valorDevido` aparece em código legado mas NÃO existe no
        DOM. Para evitar 8s de espera + fallback ruidoso, vamos direto no
        nome correto e — se faltar — caímos para o legado.
        """
        # Aguardar o campo aparecer (re-render JSF pós-radio valor=INFORMADO)
        try:
            self._page.wait_for_selector(
                "input[id$=':valorInformadoDoDevido']",
                state="visible",
                timeout=8000,
            )
        except Exception:
            self.log(f"    ⚠ Campo valorInformadoDoDevido não apareceu em 8s — tentando fallback")
        preenchido = False
        for sufixo in ("valorInformadoDoDevido", "valorDevido"):
            try:
                if self._page.locator(f"[id$=':{sufixo}']").count() > 0:
                    self._preencher(sufixo, _fmt_br(valor_brl), obrigatorio=False)
                    preenchido = True
                    self.log(f"    ✓ valor_informado_brl = {valor_brl} (via {sufixo})")
                    break
            except Exception:
                continue
        if not preenchido:
            self.log(f"    ⚠ Falha preencher valor_informado_brl={valor_brl}")

    def _configurar_quantidade_radio(self, q_tipo: str, q, v=None) -> None:
        """Configura o bloco Quantidade (radio + sub-campos) na verba-calculo.

        Decisões baseadas em pjecalc-fields-catalog.json:
          • radios DOM: INFORMADA, IMPORTADA_DO_CALENDARIO, IMPORTADA_DO_CARTAO
          • APURADA, AVOS são valores INTERNOS do bean (não há radio
            user-clickable) — usados para 13º/Férias/SaldoSalário onde o
            sistema computa automaticamente. Pulamos silenciosamente.
          • Para IMPORTADA_DO_CARTAO: além do radio, é necessário
            selecionar o cartão de ponto disponível no dropdown
            `tipoImportadadoDoCartaoDePontoQuantidade` e clicar
            `incluirCartaoDePontoQuantidade` para vincular.
        """
        if q_tipo in ("APURADA", "AVOS"):
            self.log(f"    ⊙ quantidade.tipo={q_tipo} (valor interno do bean — sem radio no DOM, pulando)")
            return
        # Esperar o painel de quantidade aparecer (a4j:region rendered=
        # isValorDevidoCalculado). Sem esse wait, racing AJAX falha o click.
        try:
            self._page.wait_for_selector(
                "input[type='radio'][id*='tipoDaQuantidade']",
                state="attached",
                timeout=8000,
            )
        except Exception:
            self.log(f"    ⚠ Radio tipoDaQuantidade não apareceu em 8s — pulando")
            return
        # Verificar se a OPÇÃO específica existe no DOM antes de tentar marcar.
        # Após reordenação 18/05/2026, Cartão de Ponto + Apuração rodam ANTES
        # de Verbas, então IMPORTADA_DO_CARTAO deve estar disponível. Se ainda
        # não estiver, é porque o cartão não foi apurado (erro na Fase 4).
        opcao_existe = self._page.locator(
            f"input[type='radio'][id*='tipoDaQuantidade'][value='{q_tipo}']"
        ).count() > 0
        if not opcao_existe:
            self.log(
                f"    ⚠ Opção tipoDaQuantidade={q_tipo} não disponível para '{getattr(v, 'nome_pjecalc', '?')}' "
                f"(provável: Cartão de Ponto não apurado na Fase 4)"
            )
            return
        try:
            self._marcar_radio("tipoDaQuantidade", q_tipo, obrigatorio=False)
        except Exception as e:
            self.log(f"    ⚠ Falha marcar tipoDaQuantidade={q_tipo}: {e}")
            return
        self._aguardar_ajax(2500)
        self.log(f"    ✓ quantidade.tipo = {q_tipo}")
        # Sub-blocos por tipo
        try:
            if q_tipo == "INFORMADA" and getattr(q, "valor", None) is not None:
                self._preencher(
                    "valorInformadoDaQuantidade",
                    _fmt_br(q.valor),
                    obrigatorio=False,
                )
                if getattr(q, "proporcionalizar", False):
                    self._marcar_checkbox("aplicarProporcionalidadeAQuantidade", True)
            elif q_tipo == "IMPORTADA_DO_CALENDARIO":
                tipo_cal = getattr(q, "tipo_importada_calendario", None)
                if tipo_cal:
                    self._selecionar(
                        "tipoImportadaCalendario",
                        tipo_cal.value if hasattr(tipo_cal, "value") else str(tipo_cal),
                        obrigatorio=False,
                    )
            elif q_tipo == "IMPORTADA_DO_CARTAO":
                # Selecionar coluna do cartão (Hs EXT para HE) + clicar Incluir.
                # Sem este passo, a verba fica com `tipoDaQuantidade=IMPORTADA_DO_CARTAO`
                # mas sem nenhuma coluna vinculada → liquidação ignora as
                # horas apuradas no cartão (HE não soma nada).
                tipo_cp = getattr(q, "tipo_cartao_ponto", None)
                nome_v = getattr(self, "_verba_atual_nome", None)
                self._vincular_cartao_ponto_quantidade(tipo_cp, nome_verba=nome_v)
        except Exception as e:
            self.log(f"    ⚠ Falha sub-bloco quantidade: {e}")

    def _vincular_cartao_ponto_quantidade(self, tipo_cartao_ponto=None, nome_verba: str | None = None) -> None:
        """Após marcar tipoDaQuantidade=IMPORTADA_DO_CARTAO, seleciona a
        COLUNA do cartão no dropdown e clica Incluir.

        Pós-apuração do Cartão de Ponto, o dropdown lista as colunas
        apuradas (Hs EXT, Hs Trabalhadas, Hs Intrajornada, Dias Trabalhados).

        Heurística de seleção baseada em `nome_verba`:
          - HORAS EXTRAS / HE → "Hs EXT"
          - INTERVALO INTRAJORNADA → "Hs Intrajornada"
          - ADICIONAL NOTURNO → "Hs EXT" (caso sem coluna específica)
          - Default → primeira opção não-placeholder

        DOM (verba-calculo.xhtml linhas 1057-1075):
          • dropdown: formulario:...:tipoImportadadoDoCartaoDePontoQuantidade
          • botão:   formulario:...:incluirCartaoDePontoQuantidade
        """
        try:
            self._page.wait_for_selector(
                "select[id$=':tipoImportadadoDoCartaoDePontoQuantidade']",
                state="visible",
                timeout=6000,
            )
        except Exception:
            self.log(f"    ⚠ Dropdown cartão de ponto (Quantidade) não apareceu — IMPORTADA_DO_CARTAO sem vínculo")
            return
        # Heurística — qual coluna corresponde à verba
        preferir = None
        if nome_verba:
            n = nome_verba.upper()
            if "INTRAJORNADA" in n:
                preferir = "Intrajornada"
            elif "HORAS EXTRAS" in n or " HE " in f" {n} " or n.startswith("HE "):
                preferir = "Hs EXT"
            elif "INTERVALO" in n:
                preferir = "Intrajornada"
        sel = self._page.locator("select[id$=':tipoImportadadoDoCartaoDePontoQuantidade']").first
        try:
            if tipo_cartao_ponto:
                val = tipo_cartao_ponto.value if hasattr(tipo_cartao_ponto, "value") else str(tipo_cartao_ponto)
                try:
                    sel.select_option(value=val)
                    self.log(f"    ✓ cartão de ponto (Quantidade) = {val}")
                except Exception:
                    self._selecionar_primeira_opcao_cartao(sel, preferir_label=preferir)
            else:
                self._selecionar_primeira_opcao_cartao(sel, preferir_label=preferir)
        except Exception as e:
            self.log(f"    ⚠ Falha selecionar cartão (Quantidade): {e}")
            return
        # Clicar Incluir — o onclick contém A4J.AJAX.Submit, precisamos invocá-lo
        try:
            clicou = self._page.evaluate(
                """() => {
                    const btn = document.querySelector("a[id$=':incluirCartaoDePontoQuantidade'], input[id$=':incluirCartaoDePontoQuantidade']");
                    if (!btn) return null;
                    const onclickStr = btn.getAttribute('onclick') || '';
                    if (onclickStr) {
                        try { new Function('event', onclickStr).call(btn, new MouseEvent('click',{bubbles:true})); return 'onclick-exec'; } catch(_) {}
                    }
                    btn.click(); return 'plain-click';
                }"""
            )
            if clicou:
                self._aguardar_ajax(2500)
                self.log(f"    ✓ click incluirCartaoDePontoQuantidade ({clicou})")
            else:
                self.log(f"    ⚠ Botão incluirCartaoDePontoQuantidade não encontrado")
        except Exception as e:
            self.log(f"    ⚠ Falha click Incluir cartão (Quantidade): {e}")

    def _selecionar_primeira_opcao_cartao(self, sel_locator, preferir_label: str | None = None) -> None:
        """Seleciona option do dropdown de coluna do cartão de ponto.

        Pós-apuração do Cartão de Ponto, o dropdown tem opções como:
          - "Dias Trabalhados"
          - "Hs EXT"           ← ideal para HORAS EXTRAS
          - "Hs Intrajornada"  ← ideal para INTERVALO INTRAJORNADA
          - "Hs Trabalhadas"

        Se `preferir_label` for fornecido, tenta match case-insensitive
        contains. Caso contrário, usa a primeira option não-placeholder.
        """
        try:
            options = self._page.evaluate(
                """(sel) => {
                    return [...sel.options].map(o => ({value: o.value, text: (o.textContent||'').trim()}));
                }""",
                sel_locator.element_handle(),
            )
            valor_alvo = None
            label_alvo = None
            # Tentativa 1: match preferir_label (case-insensitive contains)
            if preferir_label:
                pl = preferir_label.lower()
                for o in options:
                    if o['text'].lower().find(pl) >= 0 and o['value'] and not o['value'].startswith('org.jboss'):
                        valor_alvo = o['value']
                        label_alvo = o['text']
                        break
            # Tentativa 2: primeira não-placeholder
            if not valor_alvo:
                for o in options:
                    v = (o['value'] or '').strip()
                    t = (o['text'] or '').strip()
                    if v and not v.startswith('org.jboss') and v != '0' and not t.lower().startswith('selecione'):
                        valor_alvo = v
                        label_alvo = t
                        break
            if valor_alvo:
                sel_locator.select_option(value=valor_alvo)
                self.log(f"    ✓ cartão de ponto (Quantidade) selecionado = '{label_alvo}' (value={valor_alvo})")
            else:
                self.log(f"    ⚠ Nenhuma coluna de cartão disponível no dropdown — cartão pode não ter sido apurado")
        except Exception as e:
            self.log(f"    ⚠ Falha auto-select cartão: {e}")

    def _preencher_form_parametros_verba(self, v, *, com_identificacao: bool) -> None:
        """Preenche o form Parâmetros da Verba como ESPELHO FIEL do JSON.

        Princípio único (CLAUDE.md): a prévia v2 é espelho do PJE-Calc.
        Para cada campo, o bot lê o estado atual do DOM, compara com o JSON
        e SÓ dispara mudança se divergir. Isso evita:
        - AJAX desnecessário que resetava o bean Seam (mudarCaracteristica)
        - Lógica especial por estratégia (EXPRESSO_DIRETO/ADAPTADO/MANUAL)

        Comportamento:
        - **Expresso** (com_identificacao=False): a verba foi pré-configurada
          pelo Expresso. Most campos batem com JSON → skip. Diferentes →
          aplica (ex.: HE com IMPORTADA_DO_CARTAO em vez de APURADA).
        - **Manual** (com_identificacao=True): form vazio. Todos os campos
          divergem do JSON → preenche todos. Inclui Assunto CNJ que precisa
          ser selecionado via lupa (especial).

        Nome (descricao):
        - EXPRESSO_DIRETO: nome_pjecalc == expresso_alvo → skip (igual).
        - EXPRESSO_ADAPTADO: nome_pjecalc é o nome da sentença
          (ex.: "INDENIZAÇÃO SUBSTITUTIVA DE REFEIÇÃO") → diferente do
          atual ("RESTITUIÇÃO / INDENIZAÇÃO DE DESPESA") → renomeia.
        - MANUAL: input vazio → escreve nome_pjecalc.
        """
        p = v.parametros
        # Contexto para helpers (escolher coluna correta do cartão na HE etc.)
        self._verba_atual_nome = v.nome_pjecalc or getattr(v, "expresso_alvo", None)

        # ═══ SALVAGUARDA CRÍTICA (21/05/2026):
        # Garantir que o form de Alteração atual corresponde à verba esperada.
        # Sem isso, um match errado do linkParametrizar (ex: matchou TR de HE
        # 50% por ter reflexo com texto de FÉRIAS+1/3) faria o bot editar a
        # VERBA ERRADA, renomeando e corrompendo o DB.
        # Invariante: input[id$=':descricao'].value DEVE bater com expresso_alvo
        # ou nome_pjecalc (case-insensitive). Se divergir, ABORTAR.
        if not com_identificacao:  # Pós-Expresso: já existe verba no form
            try:
                descricao_atual = self._page.evaluate(
                    """() => {
                        const el = document.querySelector("input[id$=':descricao']");
                        return el ? (el.value || '') : '';
                    }"""
                ) or ""
                expected = (getattr(v, "expresso_alvo", None) or v.nome_pjecalc or "").strip().upper()
                actual = descricao_atual.strip().upper()
                if expected and actual and expected != actual:
                    # Não bate exatamente — pode ser EXPRESSO_ADAPTADO (nome_pjecalc != expresso_alvo)
                    # nesse caso o atual deveria ser expresso_alvo (canônico) e nome_pjecalc é o renomeio desejado
                    nome_pjecalc_upper = (v.nome_pjecalc or "").strip().upper()
                    expresso_alvo_upper = (getattr(v, "expresso_alvo", None) or "").strip().upper()
                    if actual not in (expresso_alvo_upper, nome_pjecalc_upper):
                        self.log(
                            f"  🛑 ABORTANDO edição — form de Alteração mostra verba ERRADA: "
                            f"atual='{descricao_atual}' esperado='{getattr(v,'expresso_alvo',None) or v.nome_pjecalc}'"
                        )
                        self.log(f"     (Causa provável: match errado no linkParametrizar). Pulando esta verba para evitar corromper o DB.")
                        return
            except Exception as _e_safe:
                self.log(f"    ⚠ Salvaguarda descricao não pôde verificar: {_e_safe}")

        # Silenciar jConfirm modal preventivamente (necessário se valor mudar)
        self._silenciar_dialog_confirma_valor()

        # ═══ ORDEM CRÍTICA (descoberto 19/05/2026):
        # AJAX rerenders disparados por radio clicks RESETAM inputs text
        # escritos antes (re-injetam value do backing bean original).
        # SOLUÇÃO: TODOS os radios PRIMEIRO, inputs text DEPOIS, save por último.
        # Manual no PJE-Calc Docker comprovou: JS direto (el.value + dispatch)
        # PERSISTE quando feito ANTES do save SEM rerenders intermediários.

        # ─── 1. Assunto CNJ (só MANUAL — Expresso vem pré-populado) ───
        if com_identificacao:
            codigo_cnj = p.assunto_cnj.codigo if p.assunto_cnj and p.assunto_cnj.codigo else 2581
            try:
                self._selecionar_assunto_cnj(codigo_cnj)
            except Exception as e:
                self.log(f"    ⚠ Assunto CNJ {codigo_cnj}: {e}")

        # ─── 2. RADIOS ESTRUTURAIS (disparam AJAX rerender) ───
        # Parcela
        if getattr(p, "parcela", None):
            parc = p.parcela.value if hasattr(p.parcela, "value") else str(p.parcela)
            self._marcar_radio_se_diferente("tipoVariacaoDaParcela", parc)

        # Valor (CALCULADO/INFORMADO) — KEY rerender
        valor_mudou = self._marcar_radio_se_diferente("valor", p.valor.value)
        if valor_mudou:
            self._aguardar_ajax(3000)

        # Caracteristica — dispara mudarCaracteristica
        try:
            caract = p.caracteristica.value if hasattr(p.caracteristica, "value") else str(p.caracteristica)
            if self._marcar_radio_se_diferente("caracteristicaVerba", caract):
                self._aguardar_ajax(2500)
        except Exception as e:
            self.log(f"    ⚠ caracteristicaVerba: {e}")

        # Ocorrência — dispara mudarOcorrenciaPagamento
        try:
            ocorr = p.ocorrencia_pagamento.value if hasattr(p.ocorrencia_pagamento, "value") else str(p.ocorrencia_pagamento)
            if self._marcar_radio_se_diferente("ocorrenciaPagto", ocorr):
                self._aguardar_ajax(2500)
        except Exception as e:
            self.log(f"    ⚠ ocorrenciaPagto: {e}")

        # Tipo (PRINCIPAL/REFLEXA) — só rendered se valor=CALCULADO
        tipo_str = getattr(p.tipo, "value", str(p.tipo)) if getattr(p, "tipo", None) else "PRINCIPAL"
        if p.valor == TipoValor.CALCULADO:
            try:
                self._marcar_radio_se_diferente("tipoDeVerba", tipo_str)
            except Exception:
                pass

        # Gerar Reflexa / Gerar Principal / Compor Principal (não-REFLEXO)
        if tipo_str != "REFLEXO":
            try:
                gr = p.gerar_reflexa.value if hasattr(p.gerar_reflexa, "value") else str(p.gerar_reflexa)
                self._marcar_radio_se_diferente("geraReflexo", gr)
            except Exception:
                pass
            try:
                gp = p.gerar_principal.value if hasattr(p.gerar_principal, "value") else str(p.gerar_principal)
                self._marcar_radio_se_diferente("gerarPrincipal", gp)
            except Exception:
                pass
            try:
                self._marcar_radio_se_diferente("comporPrincipal", "SIM" if p.compor_principal else "NAO")
            except Exception:
                pass

        # ─── 3. SUB-BLOCO CALCULADO (Base + Divisor + Multiplicador + Quantidade) ───
        # Esses só rendem se valor=CALCULADO; pode ter mais AJAX rerenders aqui
        if p.valor == TipoValor.CALCULADO:
            f = p.formula_calculado
            if f:
                # Base de Cálculo
                # SKIP equivalente (21/05/2026): MAIOR_REMUNERACAO ≡ HISTORICO_SALARIAL+ÚLTIMA REMUNERAÇÃO
                # quando valorMaiorRemuneracao == valorUltimaRemuneracao (ambos vêm
                # de Parâmetros do Cálculo). Manual PJE-Calc confirma: 'Ultima
                # Remuneracao gera automaticamente historico salarial'. Mudar
                # tipoDaBaseTabelada limpa a tabela listagemHistoricosDaVerba e
                # gera erro JSF 'Falta selecionar Histórico Salarial' se não
                # clicar +. Preservar default Expresso é mais simples e seguro.
                tipo_mudou = False
                try:
                    atual_tipo = self._page.evaluate(
                        """() => {
                            const sel = document.querySelector("select[id$=':tipoDaBaseTabelada']");
                            return sel ? sel.value : null;
                        }"""
                    )
                    desejado_tipo = f.base_calculo.tipo.value
                    historico_nome = (f.base_calculo.historico_nome or "").strip().upper()
                    skip_equivalente = (
                        atual_tipo == "MAIOR_REMUNERACAO"
                        and desejado_tipo == "HISTORICO_SALARIAL"
                        and historico_nome == "ÚLTIMA REMUNERAÇÃO"
                    )
                    if skip_equivalente:
                        self.log("    ⊙ tipoDaBaseTabelada=MAIOR_REMUNERACAO preservado (≡ HISTORICO+ÚLTIMA; evita re-render destrutivo)")
                    else:
                        tipo_mudou = self._selecionar_se_diferente("tipoDaBaseTabelada", desejado_tipo)
                        if tipo_mudou:
                            self._aguardar_ajax(3500)
                            self._page.wait_for_timeout(500)
                except Exception as e:
                    self.log(f"    ⚠ tipoDaBaseTabelada: {e}")
                    skip_equivalente = False
                # CRÍTICO (21/05/2026): se tipoDaBaseTabelada mudou para HISTORICO_SALARIAL,
                # o AJAX re-renderiza baseHistoricos com valor visual default mas JSF
                # model server-side fica VAZIO. _selecionar_se_diferente verifica só
                # o visual → pula → JSF reclama "Campo obrigatório: Histórico Salarial".
                # FIX: forçar _selecionar() + dispatch change event JS + validação.
                if f.base_calculo.tipo == TipoBaseCalculo.HISTORICO_SALARIAL and not skip_equivalente:
                    if f.base_calculo.historico_nome:
                        if tipo_mudou:
                            self._selecionar("baseHistoricos", f.base_calculo.historico_nome, obrigatorio=False)
                        else:
                            self._selecionar_se_diferente("baseHistoricos", f.base_calculo.historico_nome)
                        # Forçar value + dispatch change (alguns JSF a4j:support não
                        # capturam Playwright select_option em re-render recente)
                        try:
                            persistiu = self._page.evaluate(
                                """(nome) => {
                                    const sel = document.querySelector("select[id$=':baseHistoricos']");
                                    if (!sel) return {ok: false, why: 'select não existe'};
                                    const opts = [...sel.options];
                                    const wanted = opts.find(o =>
                                        (o.textContent||'').trim().toUpperCase() === nome.trim().toUpperCase()
                                    );
                                    if (!wanted) return {ok: false, why: 'option não encontrada', opts: opts.map(o=>o.textContent.trim())};
                                    sel.value = wanted.value;
                                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                                    return {ok: true, value: sel.value, label: wanted.textContent.trim()};
                                }""",
                                f.base_calculo.historico_nome,
                            )
                            if persistiu and persistiu.get('ok'):
                                self.log(f"    ✓ baseHistoricos JSF-persisted: value={persistiu.get('value')} label='{persistiu.get('label')}'")
                                self._aguardar_ajax(2500)
                        except Exception as e:
                            self.log(f"    ⚠ baseHistoricos forçar dispatch: {e}")
                    if f.base_calculo.proporcionaliza:
                        self._selecionar_se_diferente("proporcionalizaHistorico", f.base_calculo.proporcionaliza.value)
                    # ═══ CRÍTICO (21/05/2026 — descoberto via Chrome MCP):
                    # XHTML mostra que após selecionar baseHistoricos + proporcionalizaHistorico,
                    # é OBRIGATÓRIO clicar o botão "+" (incluirBaseHistorico) para
                    # ADICIONAR à tabela historicosSalariaisDaVerbaParaValorDevido.
                    # Sem esse click, a tabela fica VAZIA → JSF retorna ERRO:
                    # "Falta selecionar pelo menos um Histórico Salarial para apurar
                    # o Valor Devido da Verba" → liquidação BLOQUEADA.
                    try:
                        # Antes de clicar Incluir, verificar se já há entry na lista
                        # (algumas verbas Expresso vêm pré-populadas)
                        ja_tem_historico = self._page.evaluate(
                            """() => {
                                const tabela = document.querySelector("[id$=':listagemHistoricosDaVerba'] tbody, [id$=':listagemHistoricosDaVerba']");
                                if (!tabela) return false;
                                const linhas = tabela.querySelectorAll('tr');
                                return linhas.length >= 2; // header + ao menos 1 linha de dados
                            }"""
                        )
                        if not ja_tem_historico:
                            clicou_incluir = self._page.evaluate(
                                """() => {
                                    const btn = document.querySelector("a[id$=':incluirBaseHistorico'], input[id$=':incluirBaseHistorico']");
                                    if (!btn) return null;
                                    try { btn.click(); return 'js-click'; }
                                    catch (e) { return 'erro:' + e.message; }
                                }"""
                            )
                            if clicou_incluir == 'js-click':
                                self.log(f"    ✓ click '+' incluirBaseHistorico (adicionou histórico à tabela da verba)")
                                self._aguardar_ajax(4000)
                                self._page.wait_for_timeout(800)
                            else:
                                self.log(f"    ⚠ incluirBaseHistorico não encontrado/falhou: {clicou_incluir}")
                        else:
                            self.log(f"    ⊙ histórico já estava na tabela da verba (skip incluir)")
                    except Exception as e:
                        self.log(f"    ⚠ incluirBaseHistorico: {e}")
                elif f.base_calculo.tipo == TipoBaseCalculo.VALE_TRANSPORTE:
                    if f.base_calculo.vale_transporte_nome:
                        if tipo_mudou:
                            self._selecionar("valeTransporteDevido", f.base_calculo.vale_transporte_nome, obrigatorio=False)
                        else:
                            self._selecionar_se_diferente("valeTransporteDevido", f.base_calculo.vale_transporte_nome)
                elif f.base_calculo.tipo == TipoBaseCalculo.SALARIO_DA_CATEGORIA:
                    if f.base_calculo.salario_categoria_nome:
                        if tipo_mudou:
                            self._selecionar("salarioCategoria", f.base_calculo.salario_categoria_nome, obrigatorio=False)
                        else:
                            self._selecionar_se_diferente("salarioCategoria", f.base_calculo.salario_categoria_nome)
                # Divisor (radio)
                if self._marcar_radio_se_diferente("tipoDeDivisor", f.divisor.tipo.value):
                    self._aguardar_ajax(2000)
                if f.divisor.tipo.value == "IMPORTADA_DO_CARTAO" and getattr(f.divisor, "tipo_cartao_ponto", None):
                    self._selecionar_se_diferente("tipoImportadadoDoCartaoDePontoDivisor", f.divisor.tipo_cartao_ponto)
                # Quantidade (helper especializado — pula APURADA/AVOS, vincula cartão IMPORTADA_DO_CARTAO)
                self._configurar_quantidade_radio(f.quantidade.tipo.value, f.quantidade, v=v)
            # Dobrar Valor Devido
            try:
                if getattr(p.exclusoes, "dobrar_valor_devido", False):
                    self._marcar_checkbox_se_diferente("dobrarValorDevido", True)
            except Exception:
                pass

        # ─── 4. RADIO Valor Pago — pode disparar AJAX ───
        # Aplicar tanto em valor=CALCULADO quanto INFORMADO (verbas de DEDUÇÃO).
        if getattr(p, "valor_pago", None):
            vp = p.valor_pago
            try:
                vp_tipo = vp.tipo.value if hasattr(vp.tipo, "value") else str(vp.tipo)
                if self._marcar_radio_se_diferente("tipoDoValorPago", vp_tipo):
                    self._aguardar_ajax(1500)
                if vp_tipo == "CALCULADO":
                    if vp.base_tipo:
                        bt = vp.base_tipo.value if hasattr(vp.base_tipo, "value") else str(vp.base_tipo)
                        # ⚠ CRÍTICO (23/05/2026): aguardar panelBaseTabelada
                        # renderizar APÓS tipoDoValorPago=CALCULADO. Sem wait
                        # explícito, baseTabelada não existe no DOM e o select
                        # falha silenciosamente.
                        try:
                            self._page.wait_for_selector(
                                "select[id$=':baseTabelada']",
                                state="visible", timeout=6000,
                            )
                        except Exception:
                            self.log("    ⚠ panelBaseTabelada não renderizou em 6s")
                        if self._selecionar_se_diferente("baseTabelada", bt):
                            self._aguardar_ajax(2500)
                        else:
                            # Mesmo que select 'não mudou' (já era HISTORICO_SALARIAL),
                            # disparar AJAX explicitamente para garantir que
                            # painelMinicrudsDasBasesDoValorPago seja rendererizado.
                            self._page.evaluate(
                                """() => {
                                    const sel = document.querySelector("select[id$=':baseTabelada']");
                                    if (sel) {
                                        sel.dispatchEvent(new Event('change', {bubbles:true}));
                                    }
                                }"""
                            )
                            self._aguardar_ajax(2500)
                        if bt == "HISTORICO_SALARIAL":
                            # Aguardar painelMinicrudsDasBasesDoValorPago renderizar
                            try:
                                self._page.wait_for_selector(
                                    "select[id$=':baseHistoricosValorPago']",
                                    state="visible", timeout=6000,
                                )
                            except Exception:
                                self.log("    ⚠ baseHistoricosValorPago não renderizou em 6s")
                            if vp.base_historico_nome:
                                if self._selecionar_se_diferente("baseHistoricosValorPago", vp.base_historico_nome):
                                    self.log(f"    ✓ baseHistoricosValorPago = {vp.base_historico_nome}")
                                    self._aguardar_ajax(1500)
                            if vp.proporcionaliza_historico:
                                self._selecionar_se_diferente("proporcionalizaHistoricoDoValorPago", vp.proporcionaliza_historico.value)
                            # CRÍTICO: clicar "+" incluirBaseHistoricoValorPago
                            # para adicionar à tabela. Sem isso, JSF rejeita save
                            # com "Campo obrigatório: Base do Valor Pago".
                            try:
                                # Aguardar botão ser visível
                                self._page.wait_for_selector(
                                    "[id$=':incluirBaseHistoricoValorPago']",
                                    state="visible", timeout=5000,
                                )
                            except Exception:
                                self.log("    ⚠ incluirBaseHistoricoValorPago não renderizou em 5s")
                            try:
                                clicou_inc_pago = self._page.evaluate(
                                    """() => {
                                        const btn = document.querySelector("a[id$=':incluirBaseHistoricoValorPago'], input[id$=':incluirBaseHistoricoValorPago']");
                                        if (!btn) return {ok:false, reason:'not_found'};
                                        if (btn.onclick) { btn.onclick(new Event('click')); }
                                        else { btn.click(); }
                                        return {ok:true};
                                    }"""
                                )
                                if clicou_inc_pago.get("ok"):
                                    self._aguardar_ajax(2000)
                                    self.log("    ✓ click '+' incluirBaseHistoricoValorPago (Base do Valor Pago)")
                                else:
                                    self.log(f"    ⚠ incluirBaseHistoricoValorPago: {clicou_inc_pago}")
                            except Exception as e:
                                self.log(f"    ⚠ incluirBaseHistoricoValorPago: {e}")
                        elif bt == "VALE_TRANSPORTE" and vp.base_vale_transporte_nome:
                            self._selecionar_se_diferente("valeTransportePago", vp.base_vale_transporte_nome)
                        elif bt == "SALARIO_DA_CATEGORIA" and vp.base_salario_categoria_nome:
                            self._selecionar_se_diferente("salarioCategoriaValorPago", vp.base_salario_categoria_nome)
            except Exception as e:
                self.log(f"    ⚠ Valor Pago radios: {e}")

        # ═══ A PARTIR DAQUI: NÃO HAVER MAIS RADIO CLICKS QUE RERENDEREM
        # painel onde estão os inputs text críticos (descricao, valor, período).
        # Vamos preencher TODOS os inputs text agora, com state estável.

        # Aguardar AJAX final dos radios antes de escrever inputs
        self._aguardar_ajax(2000)

        # ─── 5. INPUTS TEXT (após state estabilizado) ───
        # Nome (descricao) — REGRA CRÍTICA (21/05/2026):
        # - EXPRESSO_DIRETO: nome canônico já está no DOM (vem do Expresso).
        #   NÃO MEXER. Mudar descricao aqui é um risco — se o match anterior
        #   estiver errado, renomearíamos a verba ERRADA.
        # - EXPRESSO_ADAPTADO: usuário quer um nome customizado (ex.: pulled
        #   "RESTITUIÇÃO" mas renomeia para "INDENIZAÇÃO REFEIÇÃO"). Aplicar.
        # - MANUAL: form vazio — preencher.
        deve_setar_descricao = (
            com_identificacao  # MANUAL: form vazio sempre
            or v.estrategia_preenchimento == EstrategiaPreenchimento.EXPRESSO_ADAPTADO
        )
        if deve_setar_descricao and v.nome_pjecalc:
            mudou = self._setar_text_se_diferente("descricao", v.nome_pjecalc)
            if mudou:
                self.log(f"    ✓ descricao = '{v.nome_pjecalc}'")
        elif v.nome_pjecalc:
            self.log(f"    ⊙ descricao preservado (EXPRESSO_DIRETO — nome canônico não tocado)")

        # Período (datas)
        for sufixo in ("periodoInicialInputDate", "periodoInicial", "dataInicioInputDate"):
            if self._page.locator(f"[id$='{sufixo}']").count() > 0:
                self._setar_text_se_diferente(sufixo, p.periodo_inicio)
                break
        for sufixo in ("periodoFinalInputDate", "periodoFinal", "dataFimInputDate"):
            if self._page.locator(f"[id$='{sufixo}']").count() > 0:
                self._setar_text_se_diferente(sufixo, p.periodo_fim)
                break

        # Bloco INFORMADO — valorInformadoDoDevido + proporcionalizar
        if p.valor == TipoValor.INFORMADO:
            if p.valor_devido and p.valor_devido.valor_informado_brl is not None:
                self._preencher_valor_informado_devido(p.valor_devido.valor_informado_brl)
            if p.valor_devido and getattr(p.valor_devido, "proporcionalizar", False):
                self._marcar_checkbox_se_diferente("aplicarProporcionalidadeAoValorDevido", True)

        # Bloco CALCULADO — sub-inputs text (outroValorDoDivisor, multiplicador)
        if p.valor == TipoValor.CALCULADO:
            f = p.formula_calculado
            if f:
                if f.divisor.tipo.value == "OUTRO_VALOR" and f.divisor.valor is not None:
                    self._setar_text_se_diferente("outroValorDoDivisor", _fmt_br(f.divisor.valor))
                if f.multiplicador is not None:
                    self._setar_text_se_diferente("outroValorDoMultiplicador", _fmt_br(f.multiplicador))

        # Valor Pago — sub-inputs text
        # ⚠ CRÍTICO (21/05/2026): preencher valor_pago tanto em valor=CALCULADO
        # quanto em valor=INFORMADO. As verbas de DEDUÇÃO (VALOR PAGO -
        # TRIBUTÁVEL/NÃO TRIBUTÁVEL, DEVOLUÇÃO DE DESCONTOS INDEVIDOS) usam
        # valor=INFORMADO com o valor da dedução em valor_pago.valor_brl
        # (e valor_devido.valor_informado_brl = 0). Sem isso, o bot omitiria
        # o valor da dedução no PJE-Calc.
        if getattr(p, "valor_pago", None):
            vp = p.valor_pago
            try:
                vp_tipo = vp.tipo.value if hasattr(vp.tipo, "value") else str(vp.tipo)
                if vp_tipo == "CALCULADO":
                    if vp.quantidade_brl is not None:
                        self._setar_text_se_diferente("valorPagoQuantidade", _fmt_br(vp.quantidade_brl))
                else:
                    if vp.valor_brl is not None:
                        self._setar_text_se_diferente("valorInformadoPago", _fmt_br(vp.valor_brl))
                if vp.proporcionalizar:
                    self._marcar_checkbox_se_diferente("aplicarProporcionalidadeValorPago", True)
            except Exception as e:
                self.log(f"    ⚠ Valor Pago inputs: {e}")

        # ─── 6. INCIDÊNCIAS (checkboxes, sem AJAX) ───
        try:
            self._marcar_checkbox_se_diferente("irpf", p.incidencias.irpf)
            self._marcar_checkbox_se_diferente("inss", p.incidencias.cs_inss)
            self._marcar_checkbox_se_diferente("fgts", p.incidencias.fgts)
            self._marcar_checkbox_se_diferente("previdenciaPrivada", p.incidencias.previdencia_privada)
            self._marcar_checkbox_se_diferente("pensaoAlimenticia", p.incidencias.pensao_alimenticia)
        except Exception as e:
            self.log(f"    ⚠ Incidências: {e}")

        # ─── 7. FLAGS OPCIONAIS ───
        if hasattr(p, "natureza_indenizatoria") and p.natureza_indenizatoria is not None:
            self._marcar_checkbox_se_diferente("naturezaIndenizatoria", p.natureza_indenizatoria)
        if hasattr(p, "deduzir_inss_recolhido") and p.deduzir_inss_recolhido is not None:
            self._marcar_checkbox_se_diferente("deduzirInssRecolhido", p.deduzir_inss_recolhido)
        if hasattr(p, "considerar_competencia_paga") and p.considerar_competencia_paga is not None:
            self._marcar_checkbox_se_diferente("considerarCompetenciaPaga", p.considerar_competencia_paga)

        # ─── 8. COMENTÁRIOS (textarea, sem AJAX) ───
        if getattr(p, "comentarios", None):
            self._setar_text_se_diferente("comentarios", p.comentarios)

        # Aguardar AJAX residual antes de o caller chamar Salvar
        self._aguardar_ajax(2000)

    def _configurar_parametros_pos_expresso(self, v) -> None:
        """Ajustar parâmetros da verba pós-Expresso.

        DOM confirmado (PJE-Calc 2.15.1, institucional+Cidadão):
        - <a class="linkParametrizar" title="Parâmetros da Verba"> (verba principal)
        - <a class="linkOcorrencias" title="Ocorrências da Verba"> (ocorrências)
        - IDs JSF dinâmicos (j_id558 etc.) NÃO são confiáveis — usamos CLASSE CSS.
        - Reflexos têm linkParametrizar com title="Parametrizar" (SEM "da Verba")
          — disambiguar via id*=':listaReflexo:'.
        """
        # Setar nome da verba no contexto para que _vincular_cartao_ponto_quantidade
        # possa escolher a coluna correta do cartão (Hs EXT para HE, etc.)
        self._verba_atual_nome = v.nome_pjecalc or getattr(v, "expresso_alvo", None)
        # Match candidates: nome_pjecalc (custom) e expresso_alvo (canônico).
        # Para expresso_adaptado, o listing tem o nome canônico, não o adaptado.
        candidatos = [v.nome_pjecalc]
        if hasattr(v, "expresso_alvo") and v.expresso_alvo and v.expresso_alvo != v.nome_pjecalc:
            candidatos.append(v.expresso_alvo)
        self.log(f"  → Ajustar parâmetros: {v.nome_pjecalc} (busca: {candidatos})")
        # CRÍTICO (descoberto 19/05/2026 via Java logs):
        # NPE em ApresentadorVerbaDeCalculo.prepararMinicrudsDasBasesCadastradas:841
        # ao clicar linkParametrizar. Causa: bean Seam não inicializado
        # (verbaDeCalculoVO null) na conv após Recentes reabertura.
        # Fix: forçar iniciar() do apresentador via sidebar click ANTES de
        # cada linkParametrizar. O sidebar click invoca o factory @Begin
        # mapeado em pages.xml, garantindo bean fresco.
        try:
            self._navegar_menu_via_click("li_calculo_verbas")
            # Aguardar página estabilizar + listagem aparecer
            try:
                self._page.wait_for_function(
                    """() => document.querySelectorAll('a.linkParametrizar').length > 0""",
                    timeout=15000,
                )
            except Exception:
                pass
            self._page.wait_for_timeout(2000)
        except Exception as e:
            self.log(f"    ⚠ re-init bean (sidebar verbas): {e}")
        # ESTRATÉGIA DEFINITIVA (confirmada via inspeção DOM 17/05/2026):
        # Os links têm onclick = "A4J.AJAX.Submit('formulario', event, {...
        # parameters: {'<id>':'<id>'}}); return false;". Clicks programáticos
        # (a.click(), dispatchEvent, onclick.call, hover+click via Playwright)
        # NÃO disparavam a submission — o browser seguia href="#irTopoPagina"
        # antes do onclick conseguir cancelar.
        #
        # SOLUÇÃO: chamar A4J.AJAX.Submit() diretamente como função JS global
        # (exposta pelo RichFaces 3.3.3). Independe de evento trusted ou
        # navegação default. Confirmado: chama jsfcljs interno corretamente
        # e o servidor renderiza o form de Alteração.
        # NOVO 19/05/2026: usar click nativo Playwright via locator.
        # Antes: JS `new Function('event', onclickStr).call(a, ev)` engolia
        # o `return false` final do onclick, fazendo o browser navegar para
        # href='#irTopoPagina' e interromper o ciclo AJAX. Vídeo do usuário
        # mostrou que o flow precisa de click REAL para o form de Alteração
        # carregar. Localizamos o ID com JS, depois Playwright clica.
        # CRÍTICO (descoberto 21/05/2026 via análise log SSE):
        # O match anterior (tr.textContent.includes) era catastrófico porque
        # TR de HE 50% contém reflexos como "FÉRIAS + 1/3 SOBRE HORAS EXTRAS 50%".
        # Bot buscando "FÉRIAS + 1/3" matchava TR de HE 50%, clicava no
        # linkParametrizar dela, renomeava descricao para "FÉRIAS + 1/3" →
        # transformava HE 50% em FÉRIAS+1/3 no DB.
        # FIX: usar a CÉLULA específica da verba principal (verba-calculo.xhtml
        # linha 75-77: <rich:column><h:outputText value="#{item.nome}"/></rich:column>)
        # e fazer match EXATO no texto da célula, não no TR inteiro.
        # Estrutura DOM: rich:dataTable id="listagem" → rich:columnGroup → linha
        # principal tem 4 colunas: [checkbox] [actions/linkParametrizar] [nome] [Exibir]
        link_id_res = self._page.evaluate(
            """(candidatos) => {
                const norm = s => (s||'').toUpperCase().replace(/\\s+/g,' ').trim();
                // Iterar SOMENTE pelas linhas principais da listagem (não de reflexos)
                // linkParametrizar de verba principal tem id sem ":listaReflexo:"
                const linksMain = [...document.querySelectorAll('a.linkParametrizar')]
                    .filter(a => a.id && !a.id.includes(':listaReflexo:'));
                for (const alvo of candidatos) {
                    const alvoN = norm(alvo);
                    for (const link of linksMain) {
                        // Encontrar a célula de nome (3ª coluna na mesma row do link)
                        const tr = link.closest('tr');
                        if (!tr) continue;
                        // Pegar todas as <td> do TR pai (que contém colunas da linha)
                        const tds = tr.querySelectorAll('td');
                        // Procurar td com texto EXATAMENTE igual ao alvo (não substring)
                        let matched = false;
                        for (const td of tds) {
                            // outputText fica direto no td ou em span/div interno
                            // Verificar texto direto (excluindo filhos com classe linkDestinacoes)
                            const tdText = norm(td.textContent.replace(/Exibir|Ocultar/gi, ''));
                            if (tdText === alvoN) { matched = true; break; }
                        }
                        if (matched) {
                            return {id: link.id, via: 'exact-cell:'+alvo};
                        }
                    }
                }
                return null;
            }""",
            candidatos,
        )
        clicou = None
        if link_id_res:
            lid = link_id_res["id"]
            # CRÍTICO (descoberto 20/05/2026 via Chrome MCP):
            # `element.click()` puro do DOM JS funciona perfeitamente — o browser
            # dispara o `onclick` handler `A4J.AJAX.Submit(...); return false;` e
            # interpreta o `return false` como preventDefault, cancelando a
            # navegação `href="#irTopoPagina"` ANTES dela acontecer. AJAX é
            # processado limpo e o form de Alteração renderiza.
            #
            # Playwright `locator.click(force=True)` em ambiente headless tem
            # comportamento sutilmente diferente — em testes o form não carregava.
            # Já o `new Function('event', onclickStr).call(a, ev)` executa o JS
            # do onclick mas SEM contexto de evento real → A4J.AJAX.Submit pode
            # falhar internamente ao ler event.target.
            #
            # Estratégia primária: JS `element.click()` (confirmado funcional via
            # Chrome MCP). Fallback: onclick-exec via new Function.
            clicou = self._page.evaluate(
                """(lid) => {
                    const a = document.getElementById(lid);
                    if (!a) return null;
                    try { a.click(); return 'js-click'; }
                    catch (e) {
                        const onclickStr = a.getAttribute('onclick') || '';
                        if (!onclickStr) return null;
                        try {
                            const ev = new MouseEvent('click', {bubbles:true,cancelable:true,view:window});
                            new Function('event', onclickStr).call(a, ev);
                            return 'onclick-exec';
                        } catch (_) { return null; }
                    }
                }""",
                lid,
            )
            if clicou:
                clicou = link_id_res["via"] + ":" + clicou
            else:
                # Último fallback: Playwright force click
                try:
                    self._page.locator(f'[id="{lid}"]').click(force=True, timeout=6000)
                    clicou = link_id_res["via"] + ":playwright-force"
                except Exception as e:
                    self.log(f"    ⚠ Playwright click force também falhou: {e}")
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
            # ⚠ AUTO-RECOVERY (23/05/2026): se listagem está VAZIA (não é
            # mismatch de nome, são 0 TRs), tentar Fechar+Reabrir +
            # 1 retry. Frequentemente o cálculo TEM as verbas no DB mas
            # a conv corrente está corrompida (Seam EPC saturated).
            if not diag:  # 0 TRs com linkParametrizar — listagem vazia
                self.log(f"  → Listagem vazia detectada — Fechar+Reabrir + retry")
                try:
                    if self._fechar_e_reabrir_calculo(f"recovery listagem vazia ({v.nome_pjecalc})"):
                        # Re-navegar verbas + retry click Parâmetros
                        self._navegar_menu_via_click("li_calculo_verbas")
                        self._aguardar_ajax(8000)
                        self._page.wait_for_timeout(1500)
                        # Tentar URL goto se não estamos em verba-calculo.jsf
                        if "verba-calculo.jsf" not in self._page.url and self._calculo_conversation_id:
                            self._page.goto(
                                f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                                f"?conversationId={self._calculo_conversation_id}",
                                wait_until="domcontentloaded", timeout=20000,
                            )
                            self._aguardar_ajax(8000)
                        # Re-tentar click Parâmetros — usa MESMA lógica do
                        # click inicial (linksMain sem :listaReflexo: + EXACT
                        # match). includes() pegava reflexos por substring.
                        clicou_retry = self._page.evaluate(
                            """(candidatos) => {
                                const norm = s => (s||'').normalize('NFC').replace(/\\s+/g,' ').trim().toUpperCase();
                                const linksMain = [...document.querySelectorAll('a.linkParametrizar')]
                                    .filter(a => a.id && !a.id.includes(':listaReflexo:'));
                                for (const alvo of candidatos) {
                                    const alvoN = norm(alvo);
                                    for (const link of linksMain) {
                                        const tr = link.closest('tr');
                                        if (!tr) continue;
                                        const tds = [...tr.querySelectorAll('td')];
                                        for (const td of tds) {
                                            const tdText = norm(td.textContent.replace(/Exibir|Ocultar/gi, ''));
                                            if (tdText === alvoN) {
                                                if (link.onclick) { link.onclick(new Event('click')); }
                                                else { link.click(); }
                                                return alvo;
                                            }
                                        }
                                    }
                                }
                                return null;
                            }""",
                            candidatos,
                        )
                        if clicou_retry:
                            self.log(f"    ✓ Click Parâmetros via retry pós Fechar+Reabrir (matched='{clicou_retry}')")
                            self._aguardar_ajax(8000)
                            clicou = "retry-pos-FR"
                        else:
                            self.log(f"    ⚠ Retry pós Fechar+Reabrir também não achou {candidatos}")
                            return
                    else:
                        return
                except Exception as e:
                    self.log(f"    ⚠ Recovery listagem vazia falhou: {e}")
                    return
            else:
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
                self.log(f"    ⚠ wait_for descricao visível falhou em 10s — diag={_diag}")
                # ⚠ FALLBACK (23/05/2026): às vezes o input descricao está no
                # DOM mas Playwright reporta "not visible" (CSS animation,
                # parent panel transition, etc.). Se tem_descricao=True E
                # tem_salvar=True, ASSUMIR form carregado e prosseguir.
                if _diag.get("tem_descricao") and _diag.get("tem_salvar"):
                    self.log("    ℹ Fallback: tem_descricao+tem_salvar=True — prosseguindo (Playwright visibility false-negative)")
                else:
                    # ⚠ RECOVERY (23/05/2026): às vezes o click Parâmetros
                    # redireciona para principal.jsf (Seam fechou conv
                    # spontaneamente). URL não é verba-calculo.jsf E não
                    # tem form. Recuperar via Fechar+Reabrir + re-click.
                    url_tail = _diag.get("url_tail", "")
                    if "principal.jsf" in url_tail or "verba-calculo.jsf" not in url_tail:
                        self.log(f"    → Detectado redirect para wrong page ({url_tail})")
                        # ⚠ ESTRATÉGIA OTIMIZADA (24/05/2026): ANTES de F+R
                        # (que pode pegar cálculo errado do Recentes), tentar
                        # SIMPLES URL goto para verba-calculo.jsf?conv={pre}
                        # onde pre = a conv ANTES do redirect. Geralmente a
                        # conv pré-redirect tem o cálculo correto.
                        if self._calculo_conversation_id:
                            try:
                                self.log(f"    → Tentando recovery LEVE: URL goto verba-calculo.jsf?conv={self._calculo_conversation_id}")
                                self._page.goto(
                                    f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                                    f"?conversationId={self._calculo_conversation_id}",
                                    wait_until="domcontentloaded", timeout=15000,
                                )
                                self._aguardar_ajax(8000)
                                self._page.wait_for_timeout(1500)
                                # Tentar click Parâmetros DIRETO (sem F+R)
                                clicou_leve = self._page.evaluate(
                                    """(candidatos) => {
                                        const norm = s => (s||'').normalize('NFC').replace(/\\s+/g,' ').trim().toUpperCase();
                                        const linksMain = [...document.querySelectorAll('a.linkParametrizar')]
                                            .filter(a => a.id && !a.id.includes(':listaReflexo:'));
                                        for (const alvo of candidatos) {
                                            const alvoN = norm(alvo);
                                            for (const link of linksMain) {
                                                const tr = link.closest('tr');
                                                if (!tr) continue;
                                                const tds = [...tr.querySelectorAll('td')];
                                                for (const td of tds) {
                                                    const tdText = norm(td.textContent.replace(/Exibir|Ocultar/gi, ''));
                                                    if (tdText === alvoN) {
                                                        if (link.onclick) { link.onclick(new Event('click')); }
                                                        else { link.click(); }
                                                        return alvo;
                                                    }
                                                }
                                            }
                                        }
                                        return null;
                                    }""",
                                    candidatos,
                                )
                                if clicou_leve:
                                    self.log(f"    ✓ Recovery LEVE bem-sucedido (matched='{clicou_leve}') — pulando F+R")
                                    self._aguardar_ajax(8000)
                                    try:
                                        self._page.wait_for_selector(
                                            "input[id$=':descricao'], input[id$=':valorDevido']",
                                            state="visible", timeout=10000,
                                        )
                                        self.log("    ✓ form carregado após recovery LEVE")
                                        clicou = "recovery-leve-goto"
                                        # Continuar com o flow normal (skipping outer return)
                                    except Exception:
                                        self.log("    ⚠ form não visível após recovery LEVE — escalando para F+R")
                                        clicou_leve = None
                            except Exception as _e:
                                self.log(f"    ⚠ Recovery LEVE falhou: {_e}")
                                clicou_leve = None
                        else:
                            clicou_leve = None
                        if clicou_leve:
                            # Recovery LEVE deu certo, pular F+R e seguir flow
                            pass
                        else:
                            # Recovery PESADO (F+R + Recentes) — última opção
                            self.log(f"    → Escalando para F+R + retry (Recentes pode pegar cálculo errado)")
                        try:
                            # Skip F+R se LEVE já resolveu
                            if clicou_leve:
                                raise StopIteration("LEVE resolveu")
                            if self._fechar_e_reabrir_calculo(f"recovery wrong-page ({v.nome_pjecalc})"):
                                self._navegar_menu_via_click("li_calculo_verbas")
                                self._aguardar_ajax(8000)
                                self._page.wait_for_timeout(1500)
                                if "verba-calculo.jsf" not in self._page.url and self._calculo_conversation_id:
                                    self._page.goto(
                                        f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                                        f"?conversationId={self._calculo_conversation_id}",
                                        wait_until="domcontentloaded", timeout=20000,
                                    )
                                    self._aguardar_ajax(8000)
                                # Re-tentar click Parâmetros — MESMA lógica do
                                # click inicial (linksMain sem :listaReflexo: + EXACT)
                                clicou_retry = self._page.evaluate(
                                    """(candidatos) => {
                                        const norm = s => (s||'').normalize('NFC').replace(/\\s+/g,' ').trim().toUpperCase();
                                        const linksMain = [...document.querySelectorAll('a.linkParametrizar')]
                                            .filter(a => a.id && !a.id.includes(':listaReflexo:'));
                                        for (const alvo of candidatos) {
                                            const alvoN = norm(alvo);
                                            for (const link of linksMain) {
                                                const tr = link.closest('tr');
                                                if (!tr) continue;
                                                const tds = [...tr.querySelectorAll('td')];
                                                for (const td of tds) {
                                                    const tdText = norm(td.textContent.replace(/Exibir|Ocultar/gi, ''));
                                                    if (tdText === alvoN) {
                                                        if (link.onclick) { link.onclick(new Event('click')); }
                                                        else { link.click(); }
                                                        return alvo;
                                                    }
                                                }
                                            }
                                        }
                                        return null;
                                    }""",
                                    candidatos,
                                )
                                if clicou_retry:
                                    self.log(f"    ✓ Click Parâmetros via retry pós wrong-page recovery (matched='{clicou_retry}')")
                                    self._aguardar_ajax(8000)
                                    # Re-wait for descricao
                                    try:
                                        self._page.wait_for_selector(
                                            "input[id$=':descricao'], input[id$=':valorDevido']",
                                            state="visible", timeout=10000,
                                        )
                                        self.log("    ✓ form carregado após recovery")
                                    except Exception:
                                        self.log("    ⚠ form ainda não visível após recovery — abortando")
                                        return
                                else:
                                    self.log(f"    ⚠ Retry pós wrong-page também não achou {candidatos}")
                                    return
                            else:
                                return
                        except StopIteration:
                            # LEVE resolveu — pular F+R, seguir flow normal
                            pass
                        except Exception as e:
                            self.log(f"    ⚠ Wrong-page recovery falhou: {e}")
                            return
                    else:
                        return  # de fato form não carregou
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
            # ⚠ CRÍTICO (24/05/2026): após save bem-sucedido, Seam pode
            # redirecionar para principal.jsf (conv ended). Detectar
            # e re-anchorar em verba-calculo.jsf para próxima iteração.
            re_anchored = False
            try:
                url_pos_save = self._page.url
                self._capturar_conversation_id()
                if "principal.jsf" in url_pos_save or "verba-calculo.jsf" not in url_pos_save:
                    if self._calculo_conversation_id:
                        self.log(f"    ℹ Pós-save redirecionou para {url_pos_save[-40:]} — re-anchorando em verba-calculo.jsf")
                        self._page.goto(
                            f"{self.pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                            f"?conversationId={self._calculo_conversation_id}",
                            wait_until="domcontentloaded", timeout=20000,
                        )
                        self._aguardar_ajax(8000)
                        self._page.wait_for_timeout(1000)
                        re_anchored = True
            except Exception as _e:
                self.log(f"    ⚠ Re-anchor pós-save: {_e}")
            # REGRA OPERACIONAL (25/05/2026, usuário): toda alteração de
            # parâmetro de qualquer verba exige Regerar Ocorrências para que
            # o PJE-Calc recompute downstream (ocorrências antigas ficam
            # stale se não regerar).
            try:
                # Garantir que está na listagem (Regerar só existe em modo
                # listagem). Se não re-anchorou, navegar via sidebar.
                if not re_anchored and "verba-calculo.jsf" not in self._page.url:
                    self._navegar_menu("li_calculo_verbas")
                    self._aguardar_ajax(6000)
                    self._page.wait_for_timeout(800)
                if self._regerar_com_modal_confirmacao(
                    sobrescrever=False, log_prefix="    "
                ):
                    self.log(f"    ✓ Regerar pós-parâmetros '{v.nome_pjecalc}'")
            except Exception as _e:
                self.log(f"    ⚠ Regerar pós-parâmetros: {_e}")
        else:
            self._diagnostico_pagina(contexto=f"pós-save Parâmetros {v.nome_pjecalc}")
            # FIX B (17/05/2026): RECUPERAÇÃO pós-erro de save
            # Quando o save falha (ex.: erro JSF "A data final não pode ser
            # maior que data demissão"), a página permanece no form de
            # Alteração com erros visíveis. As próximas verbas tentam buscar
            # na "listagem" mas estão no form errado → todas falham com
            # "TRs com Parâmetros visíveis: []".
            # Solução: clicar Cancelar para voltar à listagem antes da próxima.
            try:
                cancelou = self._page.evaluate(
                    """() => {
                        const btn = document.querySelector('input[id$=":cancelar"], input[value="Cancelar"]');
                        if (!btn) return null;
                        const onclickStr = btn.getAttribute('onclick') || '';
                        if (onclickStr) {
                            try {
                                const fn = new Function('event', onclickStr);
                                fn.call(btn, new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                                return 'onclick-exec';
                            } catch(_) {}
                        }
                        btn.click();
                        return 'click';
                    }"""
                )
                if cancelou:
                    self.log(f"  → Cancelando form (via {cancelou}) para voltar à listagem")
                    self._aguardar_ajax(5000)
                    self._page.wait_for_timeout(1500)
                    # Confirmar que voltou para listagem (tem botão Incluir/Manual)
                    tem_listagem = self._page.evaluate(
                        """() => !!document.querySelector('input[id$=":incluir"], a.linkParametrizar')"""
                    )
                    if tem_listagem:
                        self.log(f"  ✓ Voltou à listagem (próxima verba pode tentar)")
                    else:
                        self.log(f"  ⚠ Cancelar não retornou à listagem — re-navegando li_calculo_verbas")
                        try:
                            self._navegar_menu("li_calculo_verbas")
                            self._aguardar_ajax(8000)
                        except Exception:
                            pass
            except Exception as e:
                self.log(f"  ⚠ Falha cancelar form: {e}")

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

            # APURAÇÃO DO CARTÃO DE PONTO — passo crítico descoberto via teste
            # manual (18/05/2026). Sem isso, o cartão fica como mera definição
            # de critérios, sem ocorrências apuradas. O dropdown
            # `tipoImportadadoDoCartaoDePontoQuantidade` da verba HE 50% fica
            # VAZIO porque não há colunas (Hs EXT, Hs Intrajornada, etc.) para
            # vincular. Manual oficial CSJT (linha 502): "Apurar Cartão de
            # Ponto: Definir Dia do Fechamento Mensal, adicionar exceções,
            # clicar Apurar".
            try:
                self._apurar_cartao_de_ponto()
            except Exception as e_apurar:
                self.log(f"  ⚠ Falha apurar cartão (não-crítico, mas HE não terá Quantidade): {e_apurar}")

            self.log("Fase 5 concluída")
        except Exception as e:
            self.log(f"  ⚠ Fase 5 — Salvar: {e}")

    def _apurar_cartao_de_ponto(self) -> None:
        """Apura o Cartão de Ponto — gera as ocorrências (Hs EXT, Hs Trabalhadas,
        Hs Intrajornada, Dias Trabalhados) que serão vinculáveis às verbas HE.

        Fluxo confirmado manualmente (18/05/2026 sessão cecf7937):
        1. Navegar para Cartão de Ponto (apuracao-cartaodeponto.jsf)
        2. Clicar botão "Visualizar Cartão" → vai para cartaodeponto.jsf (Montar)
        3. Manter "Dia do Fechamento Mensal" = 31 (default)
        4. Clicar botão "Apurar Cartão de Ponto"
        5. Aguardar "Operação realizada com sucesso" + tabela de ocorrências

        Sem este passo, a verba HE 50% com tipoDaQuantidade=IMPORTADA_DO_CARTAO
        terá dropdown vazio e ficará com Quantidade=0,0000.
        """
        self.log("  → Apurando Cartão de Ponto (gerar ocorrências)...")
        # CRÍTICO: navegar via CLICK NO LINK DO SIDEBAR (executando o onclick
        # A4J.AJAX.Submit nativo) — NÃO via URL nav direto.
        # URL-nav cria uma conv fresh onde o backing bean do cálculo não
        # carrega, e o painel de ações (Novo/Grade/Visualizar) não renderiza.
        # Click no sidebar mantém a conv corrente com calc.bean populado.
        clicou_menu = self._page.evaluate(
            """() => {
                // Achar o link "Cartão de Ponto" no sidebar
                const norm = s => (s||'').replace(/\\s+/g,' ').trim();
                const links = [...document.querySelectorAll('a[id*="j_id38"]')];
                const alvo = links.find(a => {
                    const t = norm(a.textContent || a.title || '');
                    return t === 'Cartão de Ponto' || t === 'Cartao de Ponto';
                });
                if (!alvo) return null;
                const onclickStr = alvo.getAttribute('onclick') || '';
                if (onclickStr) {
                    try { new Function('event', onclickStr).call(alvo, new MouseEvent('click',{bubbles:true})); return 'onclick:' + alvo.id.slice(0,60); } catch(_) {}
                }
                alvo.click(); return 'click:' + alvo.id.slice(0,60);
            }"""
        )
        if clicou_menu:
            self.log(f"    ✓ click sidebar Cartão de Ponto ({clicou_menu})")
            self._aguardar_ajax(5000)
        else:
            self.log("    ⚠ Link 'Cartão de Ponto' do sidebar não encontrado — fallback _navegar_menu")
            try:
                self._navegar_menu("li_calculo_cartao_ponto")
                self._aguardar_ajax(4000)
            except Exception:
                pass
        # Aguardar especificamente os botões da listagem renderizarem
        try:
            self._page.wait_for_selector(
                "[id$=':importarCartao']",
                state="visible",
                timeout=15000,
            )
        except Exception:
            self.log("    ⚠ Painel de ações Cartão de Ponto (Novo/Grade/Visualizar) não renderizou em 15s — pulando apuração")
            return
        # Procurar botão "Visualizar Cartão" — id EXATO `formulario:importarCartao`
        # (CONFUSO: o id é `importarCartao` mas o value/label é "Visualizar Cartão").
        # ATENÇÃO: NÃO usar `[id*="visualizar"]` porque casa com
        # `formulario:visualizarOcorrencias` (que é o botão "Grade de Ocorrências"
        # — outro botão da mesma página).
        clicou_vis = self._page.evaluate(
            """() => {
                const norm = s => (s||'').replace(/\\s+/g,' ').trim().toLowerCase();
                // Estratégia 1: id sufixo EXATO `:importarCartao`
                let btn = document.getElementById('formulario:importarCartao') ||
                          document.querySelector('[id$=":importarCartao"]');
                // Estratégia 2: value/text EXATO "Visualizar Cartão" (não Grade de Ocorrências)
                if (!btn) {
                    btn = [...document.querySelectorAll('input,button,a')].find(b => {
                        const v = norm(b.value || b.textContent || '');
                        return v === 'visualizar cartão' || v === 'visualizar cartao';
                    });
                }
                if (!btn) return null;
                const onclickStr = btn.getAttribute('onclick') || '';
                if (onclickStr) {
                    try { new Function('event', onclickStr).call(btn, new MouseEvent('click',{bubbles:true})); return 'onclick:' + btn.id.slice(0,50); } catch(_) {}
                }
                btn.click(); return 'click:' + btn.id.slice(0,50);
            }"""
        )
        if not clicou_vis:
            # Dump diagnóstico do que está na página
            try:
                diag = self._page.evaluate(
                    """() => {
                        const btns = [...document.querySelectorAll('input[type=button],input[type=submit],button,a')]
                            .filter(b => (b.value || b.textContent || '').trim())
                            .slice(0, 20)
                            .map(b => ({tag: b.tagName, id: (b.id||'').slice(0,60), val: (b.value||b.textContent||'').trim().slice(0,40)}));
                        return {url: location.href.slice(-80), n_btns: btns.length, btns: btns};
                    }"""
                )
                self.log(f"    ⚠ Botão 'Visualizar Cartão' não encontrado — diagnóstico:")
                self.log(f"       url: ...{diag.get('url')}")
                for b in diag.get('btns', [])[:10]:
                    self.log(f"       {b['tag']} id={b['id']!r} val={b['val']!r}")
            except Exception:
                self.log("    ⚠ Botão 'Visualizar Cartão' não encontrado — sem diagnóstico")
            return
        self.log(f"    ✓ click Visualizar Cartão ({clicou_vis})")
        self._aguardar_ajax(8000)
        self._page.wait_for_timeout(2000)
        # Aguardar a página Montar carregar (id `formulario:montarApartirDaApuracao`
        # é o botão "Apurar Cartão de Ponto" — id legado JSF é confuso mas é o que existe)
        try:
            self._page.wait_for_selector(
                "[id$=':montarApartirDaApuracao'], [id='formulario:montarApartirDaApuracao']",
                state="visible",
                timeout=15000,
            )
        except Exception:
            # ⚠ FALLBACK (24/05/2026): se o botão Apurar não apareceu via
            # Visualizar Cartão, tentar URL goto direto para cartaodeponto.jsf
            # (página onde o botão Apurar reside, com sidebar completo).
            self.log("    ⚠ Página 'Montar' não carregou — tentando URL goto cartaodeponto.jsf")
            try:
                self._capturar_conversation_id()
                if self._calculo_conversation_id:
                    self._page.goto(
                        f"{self.pjecalc_url}/pages/cartaodeponto/cartaodeponto.jsf"
                        f"?conversationId={self._calculo_conversation_id}",
                        wait_until="domcontentloaded", timeout=20000,
                    )
                    self._aguardar_ajax(8000)
                    self._page.wait_for_timeout(2000)
                    self._page.wait_for_selector(
                        "[id$=':montarApartirDaApuracao']",
                        state="visible", timeout=10000,
                    )
                    self.log("    ✓ Botão Apurar disponível após URL goto")
                else:
                    self.log("    ⚠ Sem conversationId para URL goto — pulando apuração")
                    return
            except Exception as _e:
                self.log(f"    ⚠ URL goto cartaodeponto.jsf também falhou: {_e} — pulando apuração")
                return
        # Clicar Apurar Cartão de Ponto
        clicou_apurar = self._page.evaluate(
            """() => {
                // Estratégia 1: id `formulario:montarApartirDaApuracao`
                let btn = document.getElementById('formulario:montarApartirDaApuracao') ||
                          document.querySelector('[id$=":montarApartirDaApuracao"]');
                // Estratégia 2: value contém "Apurar Cart"
                if (!btn) {
                    const norm = s => (s||'').replace(/\\s+/g,' ').trim().toLowerCase();
                    btn = [...document.querySelectorAll('input,button')].find(b =>
                        norm(b.value || b.textContent || '').indexOf('apurar cart') >= 0
                    );
                }
                if (!btn) return null;
                const onclickStr = btn.getAttribute('onclick') || '';
                if (onclickStr) {
                    try { new Function('event', onclickStr).call(btn, new MouseEvent('click',{bubbles:true})); return 'onclick:' + btn.id.slice(0,50); } catch(_) {}
                }
                btn.click(); return 'click:' + btn.id.slice(0,50);
            }"""
        )
        if not clicou_apurar:
            self.log("    ⚠ Botão 'Apurar Cartão de Ponto' não encontrado — pulando")
            return
        self.log(f"    ✓ click Apurar Cartão de Ponto ({clicou_apurar})")
        self._aguardar_ajax(15000)
        sucesso = self._aguardar_operacao_sucesso(timeout_ms=20000, bloqueante=False)
        if sucesso:
            self.log("  ✓ Cartão de Ponto APURADO — ocorrências geradas")
            # Capturar tabela de ocorrências para log diagnóstico
            try:
                resumo = self._page.evaluate(
                    """() => {
                        const trs = [...document.querySelectorAll('tr')];
                        const data = [];
                        for (const tr of trs) {
                            const tds = [...tr.querySelectorAll('td')];
                            if (tds.length >= 5 && /^\\d{2}\\/\\d{4}$/.test((tds[0].textContent||'').trim())) {
                                data.push(tds.map(td => (td.textContent||'').trim()).join(' | '));
                            }
                        }
                        return data;
                    }"""
                )
                if resumo:
                    self.log(f"    📊 Ocorrências apuradas:")
                    for linha in resumo[:6]:
                        self.log(f"       {linha}")
            except Exception:
                pass
        else:
            self.log("  ⚠ Apuração disparada mas sem mensagem de sucesso explícita")

    def _aplicar_ocorrencias_override(self, overrides: list) -> None:
        """Aplica overrides de jornada na Grade de Ocorrências.

        Fluxo confirmado por inspeção DOM ao vivo (18/05/2026):
        1. Garantir que estamos na listagem `apuracao-cartaodeponto.jsf`
           (mostra botões Novo / Grade de Ocorrências / Visualizar Cartão)
        2. Clicar `formulario:gradeOcorrencias` (botão "Grade de Ocorrências")
        3. Aguardar select `formulario:mesAno` (sufixo `mesAno`) aparecer
        4. Para cada (mes, ano) com overrides:
           a. selecionar mês no dropdown
           b. preencher inputs `entrada{M}` / `saida{M}` em cada linha (data)
           c. **CLICAR SALVAR ANTES de mudar de mês** — caso contrário, as
              alterações são perdidas (alerta exibido pelo PJE-Calc:
              "Antes de mudar o mês, após alterar as ocorrências, é
              necessário clicar no botão 'Salvar'")
        """
        if not overrides:
            return
        self.log(f"  → Aplicando {len(overrides)} ocorrências override na Grade")
        from collections import defaultdict
        por_mes: dict[str, list] = defaultdict(list)
        def _campo(o, k, default=None):
            if isinstance(o, dict):
                return o.get(k, default)
            return getattr(o, k, default)
        for oc in overrides:
            data = _campo(oc, "data")
            if not data or "/" not in data:
                continue
            dd, mm, yyyy = data.split("/")
            por_mes[f"{mm}/{yyyy}"].append(oc)

        # 1. Navegar DIRETO para a listagem de Cartão de Ponto (URL específica)
        try:
            conv = self._calculo_conversation_id
            if conv:
                url_list = (
                    f"{self.pjecalc_url}/pages/cartaodeponto/"
                    f"apuracao-cartaodeponto.jsf?conversationId={conv}"
                )
                self._page.goto(url_list, wait_until="domcontentloaded", timeout=15000)
                self._aguardar_ajax(5000)
                self._page.wait_for_timeout(1000)
            else:
                self._navegar_menu("li_calculo_cartao_ponto")
                self._aguardar_ajax(5000)
        except Exception as e:
            self.log(f"  ⚠ Falha navegar para apuracao-cartaodeponto: {e}")
            return

        # 2. Clicar botão "Grade de Ocorrências" (deve estar visível na listagem)
        try:
            clicou_grade = self._page.evaluate(
                """() => {
                    // Botão pode ser <input type=submit value="Grade de Ocorrências">
                    // ou similar — usar value/texto + onclick exec
                    const cands = [...document.querySelectorAll('input[type=submit], input[type=button], button, a')]
                        .filter(el => /grade\\s+de\\s+ocorr/i.test((el.value||el.textContent||'').trim()));
                    if (!cands.length) return null;
                    const btn = cands[0];
                    const onclickStr = btn.getAttribute('onclick') || '';
                    if (onclickStr) {
                        try {
                            const fn = new Function('event', onclickStr);
                            fn.call(btn, new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                            return 'onclick-exec:' + (btn.id||btn.value||'').slice(0,40);
                        } catch(_) {}
                    }
                    btn.click();
                    return 'click:' + (btn.id||btn.value||'').slice(0,40);
                }"""
            )
            if not clicou_grade:
                self.log("  ⚠ Botão 'Grade de Ocorrências' não encontrado")
                return
            self.log(f"  ✓ click Grade de Ocorrências ({clicou_grade})")
            self._aguardar_ajax(6000)
            self._page.wait_for_timeout(1000)
        except Exception as e:
            self.log(f"  ⚠ Erro ao clicar Grade: {e}")
            return

        # 3. Aguardar select mesAno aparecer (sinal definitivo de que a Grade carregou)
        try:
            self._page.wait_for_selector("select[id$=':mesAno']", state="visible", timeout=10000)
            self.log("  ✓ Grade carregada (select mesAno visível)")
        except Exception:
            self.log("  ⚠ select mesAno não apareceu em 10s — abortando overrides")
            return

        # 4. Para cada mês, selecionar dropdown → editar → SALVAR antes de mudar
        for mes_ano, ocs in por_mes.items():
            self.log(f"  → Aplicando {len(ocs)} override(s) no mês {mes_ano}")
            try:
                self._selecionar("mesAno", mes_ano, obrigatorio=True)
                self._aguardar_ajax(3000)  # AJAX re-renderiza a tabela
                self._page.wait_for_timeout(800)
            except Exception as e:
                self.log(f"    ⚠ Falha selecionar mês {mes_ano}: {e}")
                continue

            alterou = False
            for oc in ocs:
                data = _campo(oc, "data")
                turnos = _campo(oc, "turnos") or []
                try:
                    row = self._page.locator(f"tr:has(td:has-text('{data}'))").first
                    row.wait_for(state="visible", timeout=5000)
                    for t_idx, turno in enumerate(turnos[:6]):
                        m = t_idx + 1
                        ent = _campo(turno, "entrada", "")
                        sai = _campo(turno, "saida", "")
                        if ent:
                            inp = row.locator(f"input[id$=':entrada{m}']").first
                            inp.click()
                            inp.press("Control+a"); inp.press("Delete")
                            inp.type(ent, delay=20)
                            inp.press("Tab")
                            self._page.wait_for_timeout(200)
                        if sai:
                            inp = row.locator(f"input[id$=':saida{m}']").first
                            inp.click()
                            inp.press("Control+a"); inp.press("Delete")
                            inp.type(sai, delay=20)
                            inp.press("Tab")
                            self._page.wait_for_timeout(200)
                    alterou = True
                    self.log(f"    ✓ override {data}: {len(turnos)} turno(s)")
                except Exception as e:
                    self.log(f"    ⚠ Falha override {data}: {e}")

            # 5. CRÍTICO: Salvar ANTES de mudar de mês (alerta explícito do PJE-Calc)
            if alterou:
                try:
                    self._clicar("salvar")
                    self._aguardar_ajax(5000)
                    sucesso = self._aguardar_operacao_sucesso(timeout_ms=8000, bloqueante=False)
                    if sucesso:
                        self.log(f"  ✓ Mês {mes_ano} salvo")
                    else:
                        self.log(f"  ⚠ Save do mês {mes_ano} sem confirmação")
                except Exception as e:
                    self.log(f"  ⚠ Falha salvar mês {mes_ano}: {e}")
        self.log(f"  ✓ Overrides aplicados em {len(por_mes)} mês(es)")

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
        # Princípio CLAUDE.md: fidelidade ao JSON. Bot NÃO sobrescreve. Se IA gerou
        # comporPrincipal=NAO, segue NAO. Eventuais erros de extração são tratados
        # no prompt da IA (extraction_v2.py), não no bot.
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
        # Mesmo se o JSON omitir CS, devemos VISITAR + SALVAR a página CS
        # para que o PJE-Calc gere `inssSobreSalariosDevidos.ocorrencias`.
        # Sem essas ocorrências, a regra Drools RN02 dispara erro:
        # "Histórico Salarial X não possui valor cadastrado para todas as
        # ocorrências da Contribuição Social sobre Salários Devidos".
        # Política revisada 19/05/2026.
        somente_visitar = self.previa.contribuicao_social is None
        if somente_visitar:
            self.log("  ℹ CS omitida no JSON — apenas visitar+salvar p/ gerar ocorrências (defaults PJE-Calc)")
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
        if not somente_visitar:
            self._marcar_checkbox("apurarInssSeguradoDevido", cs.apurar_segurado_devido)
            self._marcar_checkbox("cobrarDoReclamanteDevido", cs.cobrar_do_reclamante_devido)
            self._marcar_checkbox("apurarSalariosPagos", cs.apurar_salarios_pagos)
            self._marcar_radio("aliquotaEmpregado", cs.aliquota_segurado)
            self._marcar_radio("aliquotaEmpregador", cs.aliquota_empregador)
            if cs.aliquota_empregador == "FIXA":
                self._preencher("aliquotaEmpresaFixa", str(cs.aliquota_empresa_fixa_pct or 20), obrigatorio=False)
                self._preencher("aliquotaRatFixa", str(cs.aliquota_rat_fixa_pct or 1), obrigatorio=False)
                self._preencher("aliquotaTerceirosFixa", str(cs.aliquota_terceiros_fixa_pct or 5.8), obrigatorio=False)
        else:
            # Mesmo em modo "somente visitar", precisamos marcar
            # apurarInssSeguradoDevido=true para que o save gere as
            # ocorrências OcorrenciaDeInssSobreSalariosDevidos. Sem isso,
            # o set fica vazio e a regra Drools RN02 dispara.
            self._marcar_checkbox("apurarInssSeguradoDevido", True)
            self._aguardar_ajax(2000)
        try:
            self._clicar("salvar")
            self._aguardar_ajax(8000)
            self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
            self.log("  ✓ CS página salva (ocorrências de inssSobreSalariosDevidos geradas)")
        except Exception as e:
            self.log(f"  ⚠ save CS falhou: {e}")
        # Quando somente_visitar=True, retornar aqui (não há sub-páginas a explorar)
        if somente_visitar:
            return

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
        # SKIP por ausência: idem CS (Fase 9). Quando o JSON omitir
        # imposto_de_renda, os defaults nativos do PJE-Calc valem
        # (apurar=Sim, tributação separada RRA, deduções padrão).
        if self.previa.imposto_de_renda is None:
            self.log("  ⏭ IRPF omitido no JSON — usando defaults do PJE-Calc")
            return
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

    # ─── Fases novas (5 seções com schema tipado + skip por omissão) ──────

    def fase_salario_familia(self) -> None:
        """Salário-família — espelha salario-familia.xhtml. SKIP se JSON omitir."""
        self.log("Fase 10a — Salário-Família")
        if self.previa.salario_familia is None:
            self.log("  ⏭ Salário-família omitido no JSON — usando defaults do PJE-Calc")
            return
        sf = self.previa.salario_familia
        if not self._navegar_menu_via_click("li_calculo_salario_familia"):
            self._navegar_menu("li_calculo_salario_familia")
        self._aguardar_ajax(6000)
        self._page.wait_for_timeout(800)
        try:
            self._marcar_checkbox("apurarSalarioFamilia", sf.apurar)
            self._aguardar_ajax(2000)
            if not sf.apurar:
                self._clicar("salvar")
                self._aguardar_operacao_sucesso(timeout_ms=8000, bloqueante=False)
                self.log("Fase 10a concluída (apurar=False)")
                return
            self._marcar_radio("comporPrincipal", "SIM" if sf.compor_principal else "NAO")
            self._preencher("quantFilhosMenores14Anos", str(sf.quantidade_filhos_menores_14), obrigatorio=False)
            if sf.tipo_salario_pago:
                self._selecionar("tipoSalarioPago", sf.tipo_salario_pago, obrigatorio=False)
            self._clicar("salvar")
            self._aguardar_ajax(8000)
            self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        except Exception as e:
            self.log(f"  ⚠ Falha Salário-Família: {e}")
        self.log("Fase 10a concluída")

    def fase_seguro_desemprego(self) -> None:
        """Seguro-Desemprego — espelha seguro-desemprego.xhtml. SKIP se omitido."""
        self.log("Fase 10b — Seguro-Desemprego")
        if self.previa.seguro_desemprego is None:
            self.log("  ⏭ Seguro-Desemprego omitido no JSON — defaults PJE-Calc")
            return
        sd = self.previa.seguro_desemprego
        if not self._navegar_menu_via_click("li_calculo_seguro_desemprego"):
            self._navegar_menu("li_calculo_seguro_desemprego")
        self._aguardar_ajax(6000)
        self._page.wait_for_timeout(800)
        try:
            self._marcar_checkbox("apurarSeguroDesemprego", sd.apurar)
            self._aguardar_ajax(2000)
            if not sd.apurar:
                self._clicar("salvar")
                self._aguardar_operacao_sucesso(timeout_ms=8000, bloqueante=False)
                self.log("Fase 10b concluída (apurar=False)")
                return
            self._marcar_checkbox("apurarEmpregadoDomestico", sd.apurar_empregado_domestico)
            self._marcar_radio("comporPrincipal", "SIM" if sd.compor_principal else "NAO")
            if sd.numero_parcelas is not None:
                self._preencher("numeroDeParcelas", str(sd.numero_parcelas), obrigatorio=False)
            if sd.solicitacao:
                self._selecionar("solicitacao", sd.solicitacao, obrigatorio=False)
            if sd.tipo_valor:
                self._marcar_radio("valor", sd.tipo_valor)
                self._aguardar_ajax(1500)
                if sd.tipo_valor == "INFORMADO" and sd.valor_informado_brl is not None:
                    self._preencher("valorInformado", _fmt_br(sd.valor_informado_brl), obrigatorio=False)
            if sd.tipo_salario_pago:
                self._selecionar("tipoSalarioPago", sd.tipo_salario_pago, obrigatorio=False)
            self._clicar("salvar")
            self._aguardar_ajax(8000)
            self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        except Exception as e:
            self.log(f"  ⚠ Falha Seguro-Desemprego: {e}")
        self.log("Fase 10b concluída")

    def fase_previdencia_privada(self) -> None:
        """Previdência Privada — espelha previdencia-privada.xhtml."""
        self.log("Fase 10c — Previdência Privada")
        if self.previa.previdencia_privada is None:
            self.log("  ⏭ Previdência Privada omitida — defaults PJE-Calc")
            return
        pp = self.previa.previdencia_privada
        if not self._navegar_menu_via_click("li_calculo_previdencia_privada"):
            self._navegar_menu("li_calculo_previdencia_privada")
        self._aguardar_ajax(6000)
        self._page.wait_for_timeout(800)
        try:
            self._marcar_checkbox("apurarPrevidenciaPrivada", pp.apurar)
            self._aguardar_ajax(2000)
            if not pp.apurar:
                self._clicar("salvar")
                self._aguardar_operacao_sucesso(timeout_ms=8000, bloqueante=False)
                self.log("Fase 10c concluída (apurar=False)")
                return
            for periodo in pp.aliquotas:
                try:
                    self._preencher("aliquota", _fmt_br(periodo.aliquota_pct), obrigatorio=False)
                    self._preencher("dataInicioPeriodo", periodo.data_inicio, obrigatorio=False)
                    if periodo.data_fim:
                        self._preencher("dataTerminoPeriodo", periodo.data_fim, obrigatorio=False)
                    self._clicar("cmdIncluirAliquota")
                    self._aguardar_ajax(2000)
                except Exception as e:
                    self.log(f"  ⚠ período Prev.Privada: {e}")
            self._clicar("salvar")
            self._aguardar_ajax(8000)
            self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        except Exception as e:
            self.log(f"  ⚠ Falha Previdência Privada: {e}")
        self.log("Fase 10c concluída")

    def fase_pensao_alimenticia(self) -> None:
        """Pensão Alimentícia — espelha pensao-alimenticia.xhtml."""
        self.log("Fase 10d — Pensão Alimentícia")
        if self.previa.pensao_alimenticia is None:
            self.log("  ⏭ Pensão Alimentícia omitida — defaults PJE-Calc")
            return
        pa = self.previa.pensao_alimenticia
        if not self._navegar_menu_via_click("li_calculo_pensao_alimenticia"):
            self._navegar_menu("li_calculo_pensao_alimenticia")
        self._aguardar_ajax(6000)
        self._page.wait_for_timeout(800)
        try:
            self._marcar_checkbox("apurarPensaoAlimenticia", pa.apurar)
            self._aguardar_ajax(2000)
            if not pa.apurar:
                self._clicar("salvar")
                self._aguardar_operacao_sucesso(timeout_ms=8000, bloqueante=False)
                self.log("Fase 10d concluída (apurar=False)")
                return
            if pa.aliquota_pct > 0:
                self._preencher("aliquota", _fmt_br(pa.aliquota_pct), obrigatorio=False)
            self._marcar_checkbox("incidirSobreJuros", pa.incidir_sobre_juros)
            self._clicar("salvar")
            self._aguardar_ajax(8000)
            self._aguardar_operacao_sucesso(timeout_ms=10000, bloqueante=False)
        except Exception as e:
            self.log(f"  ⚠ Falha Pensão Alimentícia: {e}")
        self.log("Fase 10d concluída")

    def fase_multas_indenizacoes(self) -> None:
        """Multas e Indenizações — espelha multas-indenizacoes.xhtml.

        Apenas executa quando há ≥ 1 multa no JSON. SKIP por list vazia.
        """
        self.log("Fase 11b — Multas e Indenizações")
        if not self.previa.multas_indenizacoes:
            self.log("  ⏭ Sem multas/indenizações no JSON")
            return
        if not self._navegar_menu_via_click("li_calculo_multas_e_indenizacoes"):
            self._navegar_menu("li_calculo_multas_e_indenizacoes")
        self._aguardar_ajax(6000)
        self._page.wait_for_timeout(800)
        for m in self.previa.multas_indenizacoes:
            try:
                self._clicar("incluir")
                self._aguardar_ajax(3000)
                self._preencher("descricao", m.descricao, obrigatorio=False)
                self._selecionar("credorDevedor", m.credor_devedor, obrigatorio=False)
                if m.terceiro_nome and "TERCEIRO" in m.credor_devedor:
                    self._preencher("terceiro", m.terceiro_nome, obrigatorio=False)
                self._marcar_radio("valor", m.tipo_valor)
                self._aguardar_ajax(1500)
                if m.tipo_valor == "CALCULADO":
                    self._preencher("aliquota", _fmt_br(m.aliquota_pct or 0), obrigatorio=False)
                    if m.tipo_base:
                        self._selecionar("tipoBaseMulta", m.tipo_base, obrigatorio=False)
                else:
                    self._preencher("valor2", _fmt_br(m.valor_brl or 0), obrigatorio=False)
                    if m.data_vencimento:
                        self._preencher("dataVencimento", m.data_vencimento, obrigatorio=False)
                self._selecionar("correcaoMonetaria", m.correcao_monetaria, obrigatorio=False)
                if m.correcao_monetaria == "OUTRO_INDICE" and m.outro_indice_correcao:
                    self._selecionar("outroIndiceCorrecao", m.outro_indice_correcao, obrigatorio=False)
                self._marcar_checkbox("aplicarJuros", m.aplicar_juros)
                if m.data_juros_a_partir_de:
                    self._preencher("dataJurosAPartirDe", m.data_juros_a_partir_de, obrigatorio=False)
                if m.tipo_cobranca_reclamante and "RECLAMANTE" in m.credor_devedor[-10:]:
                    self._selecionar("tipoCobrancaReclamante", m.tipo_cobranca_reclamante, obrigatorio=False)
                self._clicar("salvar")
                self._aguardar_ajax(5000)
                self._aguardar_operacao_sucesso(timeout_ms=8000, bloqueante=False)
            except Exception as e:
                self.log(f"  ⚠ Falha Multa '{m.descricao}': {e}")
        self.log("Fase 11b concluída")

    def fase_honorarios(self) -> None:
        self.log("Fase 11 — Honorários")
        # CRÍTICO (21/05/2026): Fase 9 (CS) pode terminar com 'Execution context
        # destroyed' deixando navegação pendente. Se Fase 11 navegar imediatamente,
        # cai em 'Navigation interrupted by another navigation'. Estabilizar primeiro.
        self._aguardar_ajax(5000)
        self._page.wait_for_timeout(2000)
        # Retry navegação até 3x se a primeira for interrompida
        nav_ok = False
        for tentativa in range(3):
            try:
                self._navegar_menu("li_calculo_honorarios")
                self._aguardar_ajax(8000)
                self._page.wait_for_timeout(1500)
                nav_ok = True
                break
            except Exception as e:
                self.log(f"  ⚠ tentativa {tentativa+1}/3 nav Honorários: {str(e)[:120]}")
                if tentativa < 2:
                    self._page.wait_for_timeout(3000)
        if not nav_ok:
            self.log("  ⚠ Fase 11 Honorários: navegação falhou 3x — pulando")
            return
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
            # ⚠ ID REAL do template (honorarios.xhtml:118): tipoCobrancaReclamante
            # (radio renderizado condicionalmente quando tipoDeDevedor=RECLAMANTE)
            if h.tipo_devedor == "RECLAMANTE":
                self._marcar_radio("tipoCobrancaReclamante", "COBRAR")
                self._aguardar_ajax(1000)

            self._marcar_radio("tipoValor", h.tipo_valor.value)
            self._aguardar_ajax(2000)

            if h.tipo_valor.value == "CALCULADO":
                if h.aliquota_pct is not None:
                    pct = h.aliquota_pct * 100 if h.aliquota_pct < 1 else h.aliquota_pct
                    # ⚠ ID REAL (honorarios.xhtml:148): aliquota (não percentualHonorarios)
                    self._preencher("aliquota", _fmt_br(pct), obrigatorio=False)
                if h.base_para_apuracao:
                    self._selecionar("baseParaApuracao", h.base_para_apuracao, obrigatorio=False)
            else:
                if h.valor_informado_brl is not None:
                    # ⚠ ID REAL (honorarios.xhtml:212): valor (não valorInformado)
                    self._preencher("valor", _fmt_br(h.valor_informado_brl), obrigatorio=False)

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
                # ⚠ IDs REAIS (honorarios.xhtml:322,335):
                #   tipoDocumentoFiscalCredor + numeroDocumentoFiscalCredor
                # CRÍTICO (22/05/2026): NÃO marcar tipoDocumentoFiscalCredor
                # se numeroDocumentoFiscalCredor estiver VAZIO. O JSF tem um
                # <f:validator validadorDinamico> em numero que dispara
                # exceção quando tipo está set mas número é vazio. Causa do
                # "Erro: 19" (MSG0013 — exceção não capturada) que corrompia
                # o estado Seam para todas as fases subsequentes (Custas/
                # Correção/Liquidar viam o cálculo "vazio"). Caso comum:
                # ADVOGADO DO RECLAMANTE sem CNPJ conhecido na sentença.
                _doc_num = (h.credor.doc_fiscal_numero or "").strip()
                if _doc_num:
                    self._marcar_radio(
                        "tipoDocumentoFiscalCredor",
                        h.credor.doc_fiscal_tipo.value,
                    )
                    self._preencher(
                        "numeroDocumentoFiscalCredor",
                        _doc_num,
                        obrigatorio=False,
                    )
                else:
                    self.log(
                        "  ℹ doc_fiscal_numero do credor vazio — "
                        "pulando tipo+número (evita validadorDinamico)"
                    )
            # ⚠ ID REAL (honorarios.xhtml:373): apurarIRRF (não apurarIr)
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
        # Estabilizar antes de navegar (evita 'Navigation interrupted' por fase
        # anterior pendente). Retry até 3x.
        self._aguardar_ajax(5000)
        self._page.wait_for_timeout(1500)
        nav_ok = False
        for tentativa in range(3):
            try:
                # Click sidebar (Seam init) — URL direta não dispara @PostConstruct do bean.
                # CRÍTICO: sem isso os campos dataVencimento* não existem na DOM e ficam
                # vazios → liquidação rejeita por "Vencimento deve ser >= {data}".
                if not self._navegar_menu_via_click("li_calculo_custas_judiciais"):
                    self._navegar_menu("li_calculo_custas_judiciais")
                self._aguardar_ajax(6000)
                self._page.wait_for_timeout(1500)
                _n_cst_tmp = self._page.evaluate(
                    """() => document.querySelectorAll('input[type=radio],select').length"""
                )
                if _n_cst_tmp > 5:
                    nav_ok = True
                    break
                self.log(f"  ⚠ tentativa {tentativa+1}/3 Custas: campos={_n_cst_tmp} (esperado >5)")
            except Exception as e:
                self.log(f"  ⚠ tentativa {tentativa+1}/3 nav Custas: {str(e)[:120]}")
            if tentativa < 2:
                self._page.wait_for_timeout(3000)
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
        # Estabilizar antes (mesmo padrão Fase 11/12)
        self._aguardar_ajax(5000)
        self._page.wait_for_timeout(1500)
        nav_ok = False
        for tentativa in range(3):
            try:
                # Click sidebar (Seam init) — URL direta não dispara @PostConstruct do bean
                if not self._navegar_menu_via_click("li_calculo_correcao_juros_multa"):
                    self._navegar_menu("li_calculo_correcao_juros_multa")
                self._aguardar_ajax(6000)
                self._page.wait_for_timeout(1500)
                _n_tmp = self._page.evaluate(
                    """() => document.querySelectorAll('select, input[type=checkbox], input[type=radio]').length"""
                )
                if _n_tmp > 10:
                    nav_ok = True
                    break
                self.log(f"  ⚠ tentativa {tentativa+1}/3 Correção: campos={_n_tmp} (esperado >10)")
            except Exception as e:
                self.log(f"  ⚠ tentativa {tentativa+1}/3 nav Correção: {str(e)[:120]}")
            if tentativa < 2:
                self._page.wait_for_timeout(3000)

        _n_campos = self._page.evaluate(
            """() => document.querySelectorAll('select, input[type=checkbox], input[type=radio]').length"""
        )
        self.log(f"  [DIAG-correcao] campos={_n_campos}")
        if _n_campos == 0:
            self.log("  ⚠ Fase 13 Correção: página sem campos — pulando")
            return

        c = self.previa.correcao_juros_multa

        # Mapeamentos JSON → valores DOM REAIS (docs/dom-mapping/dominios-values.json).
        # ⚠ Bug histórico (corrigido 22/05/2026): mapping anterior gerava valores
        # que NÃO EXISTEM no DOM (IPCA_E em vez de IPCAE, SELIC_SIMPLES em vez de
        # SELIC, TABELA_UNICA em vez de TABELA_UNICA_JT_MENSAL) — causava timeout
        # de 30s em select_option. Valores reais conforme enum do servidor:
        #
        #   indiceTrabalhista: TUACDT | TABELA_DEVEDOR_FAZENDA | TABELA_INDEBITO_TRIBUTARIO
        #                    | TABELA_UNICA_JT_MENSAL | TABELA_UNICA_JT_DIARIO
        #                    | TR | IGPM | INPC | IPC | IPCA | IPCAE | IPCAETR
        #                    | SELIC | SELIC_FAZENDA | SELIC_BACEN | SEM_CORRECAO
        _INDICE_MAP = {
            # JSON v2 (com underscores) → DOM enum real (sem underscores)
            "IPCA_E": "IPCAE",
            "IPCA_E_TR": "IPCAETR",
            "IPCAE_TR": "IPCAETR",
            "IGP_M": "IGPM",
            "SELIC_SIMPLES": "SELIC",
            "SELIC_RECEITA": "SELIC_FAZENDA",
            "SELIC_COMPOSTA": "SELIC_BACEN",
            "TABELA_UNICA": "TABELA_UNICA_JT_MENSAL",
            "DEVEDOR_FAZENDA_PUBLICA": "TABELA_DEVEDOR_FAZENDA",
            "REPETICAO_INDEBITO_TRIBUTARIO": "TABELA_INDEBITO_TRIBUTARIO",
            # Pass-through (valores já corretos no JSON)
            "IPCAE": "IPCAE", "IPCAETR": "IPCAETR", "IGPM": "IGPM",
            "INPC": "INPC", "IPC": "IPC", "IPCA": "IPCA", "TR": "TR",
            "SELIC": "SELIC", "SELIC_FAZENDA": "SELIC_FAZENDA",
            "SELIC_BACEN": "SELIC_BACEN",
            "TUACDT": "TUACDT",
            "SEM_CORRECAO": "SEM_CORRECAO",
        }
        # Juros: enum real do servidor (parametros-atualizacao.xhtml usa jurosEnum
        # do enumItems). Valores comuns: PADRAO, CADERNETA_POUPANCA, SIMPLES_0_5_MES,
        # SIMPLES_1_MES, SIMPLES_0_0333333_DIA, SELIC, SELIC_FAZENDA, SELIC_BACEN,
        # FAZENDA_PUBLICA, TAXA_LEGAL.
        _JUROS_MAP = {
            "JUROS_PADRAO": "PADRAO",
            "JUROS_POUPANCA": "CADERNETA_POUPANCA",
            "JUROS_MEIO_PORCENTO": "SIMPLES_0_5_MES",
            "JUROS_UM_PORCENTO": "SIMPLES_1_MES",
            "JUROS_ZERO_TRINTA_TRES": "SIMPLES_0_0333333_DIA",
            "SELIC_SIMPLES": "SELIC",
            "SELIC_RECEITA": "SELIC_FAZENDA",
            "SELIC_COMPOSTA": "SELIC_BACEN",
            # Pass-through
            "PADRAO": "PADRAO",
            "CADERNETA_POUPANCA": "CADERNETA_POUPANCA",
            "SELIC": "SELIC", "SELIC_FAZENDA": "SELIC_FAZENDA",
            "SELIC_BACEN": "SELIC_BACEN",
            "FAZENDA_PUBLICA": "FAZENDA_PUBLICA",
            "TAXA_LEGAL": "TAXA_LEGAL",
        }
        # baseDeJurosDasVerbas: enum real (baseDeJurosDasVerbasEnum). Valores
        # comuns: VERBA, VERBA_MENOS_CS, VERBA_MENOS_CS_MENOS_PP.
        _BASE_JUROS_MAP = {
            "VERBAS": "VERBA", "VERBA": "VERBA",
            "VERBA_INSS": "VERBA_MENOS_CS",
            "VERBA_MENOS_CS": "VERBA_MENOS_CS",
            "VERBA_INSS_PP": "VERBA_MENOS_CS_MENOS_PP",
            "VERBA_MENOS_CS_MENOS_PP": "VERBA_MENOS_CS_MENOS_PP",
        }
        _FGTS_CORR_MAP = {
            "UTILIZAR_INDICE_TRABALHISTA": "INDICE_TRABALHISTA",
            "UTILIZAR_INDICE_JAM": "JAM",
            "UTILIZAR_INDICE_JAM_E_TRABALHISTA": "JAM_MAIS_TRABALHISTA",
        }

        # ⚠ IDs REAIS do template parametros-atualizacao.xhtml (não os legados).
        # A página tem 2 abas: "Dados Gerais" (default) e "Dados Específicos".
        # Quase TODOS os IDs estavam errados no código anterior.

        # ── Aba "Dados Gerais": Índice Trabalhista ───────────────────────────
        # ID real: indiceTrabalhista (NÃO indiceCorrecao).
        indice_val = _INDICE_MAP.get(c.indice_trabalhista, c.indice_trabalhista)
        self._selecionar("indiceTrabalhista", indice_val)
        self._aguardar_ajax(1000)

        # ── Combinar com segundo índice (workflow JSF: checkbox → select →
        # data → clicar BOTÃO "+" addOutroIndice).
        # Schema v2 usa: combinar_outro_indice / indice_combinado / data_inicio_combinacao.
        # IDs reais: combinarOutroIndice, outroIndiceTrabalhista,
        # apartirDeOutroIndice, addOutroIndice (link).
        combinar_indice = (
            getattr(c, "combinar_outro_indice", False)
            or getattr(c, "combinar_com_outro_indice", False)
        )
        segundo = (
            getattr(c, "indice_combinado", None)
            or getattr(c, "segundo_indice", None)
            or getattr(c, "indice_correcao_pos", None)
        )
        data_inicio_2 = (
            getattr(c, "data_inicio_combinacao", None)
            or getattr(c, "data_inicio_segundo_indice", None)
        )
        if combinar_indice and segundo:
            self._marcar_checkbox("combinarOutroIndice", True)
            self._aguardar_ajax(2000)
            self._selecionar("outroIndiceTrabalhista", _INDICE_MAP.get(segundo, segundo))
            if data_inicio_2:
                self._preencher("apartirDeOutroIndice", data_inicio_2, obrigatorio=False)
            # Clicar botão "+" para confirmar adição na tabela
            try:
                self._clicar("addOutroIndice")
                self._aguardar_ajax(2000)
                self.log(f"  ✓ Correção combinada: {segundo} a partir de {data_inicio_2} (+ adicionado)")
            except Exception as e:
                self.log(f"  ⚠ addOutroIndice falhou: {e}")

        # ── Ignorar Taxa Negativa ────────────────────────────────────────────
        ignorar_neg = getattr(c, "ignorar_taxa_negativa", None)
        if ignorar_neg is not None:
            self._marcar_checkbox("ignorarTaxaNegativa", bool(ignorar_neg))

        # ── Aplicar Juros Pré-Judicial (controla se TabelaJuros aplica desde
        # o vencimento ou desde o ajuizamento). Schema v2 não tem campo direto
        # — só inferimos pela presença de data_inicio_juros pré-ajuizamento.
        # Por padrão, deixar TRUE (Calc-Machine pattern).
        try:
            self._marcar_checkbox("aplicarJurosFasePreJudicial", True)
            self._aguardar_ajax(800)
        except Exception:
            pass

        # ── Tabela de Juros (ID real: juros — NÃO taxaJuros) ─────────────────
        juros_val = _JUROS_MAP.get(c.juros, c.juros)
        self._selecionar("juros", juros_val)
        self._aguardar_ajax(1000)

        # ── Combinar com outro juros (Lei 14.905 — taxa a partir de data)
        # IDs reais: combinarOutroJuros, outroJuros, apartirDeOutroJuros,
        # addOutroJuros (link).
        combinar_juros = (
            getattr(c, "juros_combinar", False)
            or getattr(c, "combinar_com_outro_juros", False)
            or getattr(c, "combinar_outro_juros", False)
        )
        outro_juros = (
            getattr(c, "juros_combinado", None)
            or getattr(c, "outro_juros", None)
        )
        outro_juros_de = (
            getattr(c, "juros_combinado_data_inicio", None)
            or getattr(c, "outro_juros_a_partir_de", None)
        )
        if combinar_juros and outro_juros:
            self._marcar_checkbox("combinarOutroJuros", True)
            self._aguardar_ajax(1500)
            self._selecionar("outroJuros", _JUROS_MAP.get(outro_juros, outro_juros))
            if outro_juros_de:
                self._preencher("apartirDeOutroJuros", outro_juros_de, obrigatorio=False)
            try:
                self._clicar("addOutroJuros")
                self._aguardar_ajax(2000)
                self.log(f"  ✓ Juros combinado: {outro_juros} a partir de {outro_juros_de} (+ adicionado)")
            except Exception as e:
                self.log(f"  ⚠ addOutroJuros falhou: {e}")

        # ── Trocar para Aba "Dados Específicos" (onde estão baseDeJurosDasVerbas,
        # indiceDeCorrecaoDoFGTS, custas, previdência privada). A aba tem id
        # `tabDadosEspecificos`. Em rich:tabPanel com switchType=client, basta
        # clicar no header da aba.
        try:
            _clicked = self._page.evaluate("""() => {
                // Procurar header da aba "Dados Específicos"
                const headers = [...document.querySelectorAll('td.rich-tab-header, .rich-tabhdr')];
                for (const h of headers) {
                    const txt = (h.textContent||'').trim();
                    if (/Dados\\s+Espec[íi]ficos/i.test(txt)) {
                        h.click();
                        return true;
                    }
                }
                // Fallback: tentar clicar via link interno
                const link = document.querySelector('a[id$="tabDadosEspecificos"]');
                if (link) { link.click(); return 'link'; }
                return false;
            }""")
            if _clicked:
                self._aguardar_ajax(1500)
                self.log(f"  ✓ trocou para aba Dados Específicos ({_clicked})")
        except Exception as e:
            self.log(f"  ⚠ troca de aba falhou: {e}")

        # ── Base de Juros das Verbas (aba 2) ─────────────────────────────────
        base_val = _BASE_JUROS_MAP.get(c.base_juros_verbas, c.base_juros_verbas)
        self._selecionar("baseDeJurosDasVerbas", base_val)

        # ── FGTS: Correção (ID real: indiceDeCorrecaoDoFGTS — radio) ─────────
        fgts_c = getattr(c, "fgts", None)
        if fgts_c:
            fc_raw = (
                fgts_c.get("indice_correcao") if isinstance(fgts_c, dict)
                else getattr(fgts_c, "indice_correcao", None)
            )
            if fc_raw:
                self._marcar_radio("indiceDeCorrecaoDoFGTS", _FGTS_CORR_MAP.get(fc_raw, fc_raw))

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

        # Verificar resultado da liquidação. A página liquidacao.xhtml renderiza
        # uma seção "Pendências do Cálculo" SEMPRE que houver erros OU alertas,
        # com:
        #   <input id="*:totalErros"   value="N"> — bloqueantes (X vermelho)
        #   <input id="*:totalAlertas" value="N"> — não-bloqueantes (⚠ amarelo)
        # Cada item de pendência tem class:
        #   .validacaoErro   → bloqueante (impede a liquidação)
        #   .validacaoAlerta → não impede (informativo)
        #   .validacaoSucesso → "não há pendências" (liquidação OK)
        #
        # CRÍTICO: a automação SÓ deve travar e oferecer edição manual quando
        # totalErros > 0. Alertas amarelos não impedem a liquidação e devem
        # ser apenas registrados no log.
        _liq_result = self._page.evaluate("""() => {
            // ─ Totalizadores da tela liquidacao.xhtml ─────────────────────
            const totErrosEl = document.querySelector('input[id$=":totalErros"], input[id$="totalErros"]');
            const totAlertasEl = document.querySelector('input[id$=":totalAlertas"], input[id$="totalAlertas"]');
            const totalErros = totErrosEl ? (parseInt(totErrosEl.value, 10) || 0) : null;
            const totalAlertas = totAlertasEl ? (parseInt(totAlertasEl.value, 10) || 0) : null;

            // ─ Itens de erro (bloqueantes) e alerta (não bloqueantes) ─────
            const erros = [...document.querySelectorAll('.validacaoErro')]
                .map(el => (el.textContent || '').replace(/\\s+/g, ' ').trim())
                .filter(t => t && !/^erro:\\s*impede/i.test(t));  // exclui legenda
            const alertas = [...document.querySelectorAll('.validacaoAlerta')]
                .map(el => (el.textContent || '').replace(/\\s+/g, ' ').trim())
                .filter(t => t && !/^alerta:\\s*n[ãa]o impede/i.test(t));  // exclui legenda
            const sucesso_painel = !!document.querySelector('.validacaoSucesso');

            // ─ Mensagens JSF complementares (rf-msgs) ─────────────────────
            const msgs = [...document.querySelectorAll('.rf-msgs-detail,.rf-msgs-sum,.ui-messages-error-summary,.rich-messages-label')]
                .map(e => (e.textContent||'').trim()).filter(t => t).slice(0, 10);
            const msgs_lower = msgs.map(m => m.toLowerCase()).join('\\n');
            const has_sucesso_msg = msgs.some(m =>
                /opera[cç][ãa]o realizada com sucesso/i.test(m)
                || /liquida[cç][ãa]o realizada/i.test(m)
            );
            const body = document.body?.textContent || '';
            const has_real_error =
                body.includes('HTTP Status 500')
                || body.includes('NullPointerException')
                || body.toLowerCase().includes('erro inesperado')
                || msgs_lower.includes('erro:');

            return {
                totalErros, totalAlertas,
                erros: [...new Set(erros)].slice(0, 30),
                alertas: [...new Set(alertas)].slice(0, 30),
                sucesso_painel,
                msgs, tem_erro_500: has_real_error, tem_sucesso: has_sucesso_msg
            };
        }""")

        # Normalizar: se a tela renderizou totalizadores, usamos eles como
        # fonte da verdade. Se ainda não renderizou (race AJAX), usamos só
        # mensagens JSF como fallback.
        _tE = _liq_result['totalErros']
        _tA = _liq_result['totalAlertas']
        _erros_lista = _liq_result['erros'] or []
        _alertas_lista = _liq_result['alertas'] or []
        self.log(
            f"  [DIAG-liquidar] totalErros={_tE} totalAlertas={_tA} "
            f"painel_sucesso={_liq_result['sucesso_painel']} "
            f"msg_sucesso={_liq_result['tem_sucesso']} "
            f"erro_500={_liq_result['tem_erro_500']}"
        )
        if _erros_lista:
            self.log(f"  [DIAG-liquidar] erros[{len(_erros_lista)}]: {_erros_lista[:3]}")
        if _alertas_lista:
            self.log(f"  [DIAG-liquidar] alertas[{len(_alertas_lista)}]: {_alertas_lista[:3]}")

        # Decisão:
        #   - Erro 500 / NPE → falha técnica (raise sem oferecer edição manual)
        #   - Sucesso explícito (mensagem JSF OU painel.validacaoSucesso) → OK
        #   - totalErros > 0 → BLOQUEANTE → oferecer edição manual com lista de erros
        #   - totalErros == 0 (com ou sem alertas) → prosseguir; alertas só são logados
        if _liq_result['tem_erro_500']:
            raise RuntimeError(f"Liquidação retornou erro técnico: {_liq_result['msgs']}")
        if _liq_result['tem_sucesso'] or _liq_result['sucesso_painel'] or (
            _tE == 0 and _tA == 0 and not _erros_lista
        ):
            self.log("  ✓ Liquidação OK (sem pendências bloqueantes)")
            if _alertas_lista:
                self.log(f"  ⚠ {len(_alertas_lista)} alerta(s) não-bloqueante(s) registrados — não impedem a liquidação:")
                for _idx, _a in enumerate(_alertas_lista[:10], start=1):
                    self.log(f"    {_idx}. {_a[:180]}")
        elif _tE and _tE > 0:
            # CASO CRÍTICO: liquidação bloqueada por erros REAIS marcados com
            # X vermelho no painel "Pendências do Cálculo".
            self.log(f"  ✗ Liquidação BLOQUEADA — totalErros={_tE} (alertas={_tA or 0} ignorados)")
            # Erros bloqueantes têm prioridade absoluta. Mensagens JSF entram
            # como complemento se a lista de erros estiver vazia (improvável).
            pendencias = _erros_lista or _liq_result['msgs']
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
                        const totErrosEl2 = document.querySelector('input[id$=":totalErros"], input[id$="totalErros"]');
                        const totalErros2 = totErrosEl2 ? (parseInt(totErrosEl2.value, 10) || 0) : null;
                        const erros2 = [...document.querySelectorAll('.validacaoErro')]
                            .map(el => (el.textContent || '').replace(/\\s+/g, ' ').trim())
                            .filter(t => t && !/^erro:\\s*impede/i.test(t));
                        const msgs = [...document.querySelectorAll('.rf-msgs-detail,.rf-msgs-sum')]
                            .map(e => (e.textContent||'').trim()).filter(t => t);
                        return {
                            totalErros: totalErros2,
                            erros: [...new Set(erros2)].slice(0, 20),
                            ok: msgs.some(m => /opera[cç][ãa]o realizada com sucesso|liquida[cç][ãa]o realizada/i.test(m))
                                || !!document.querySelector('.validacaoSucesso'),
                        };
                    }""")
                    # Liquidação OK se sucesso explícito + nenhum erro bloqueante.
                    # totalErros pode ser null (painel não-renderizado = sem pendências).
                    _erros2 = _liq2.get('erros') or []
                    _tE2 = _liq2.get('totalErros')
                    if _liq2.get('ok') and (not _tE2 or _tE2 == 0) and not _erros2:
                        self.log("  ✓ 2ª tentativa de liquidação OK — prosseguindo para exportação")
                        sucesso_liq = True
                        pendencias = []
                    else:
                        if _erros2:
                            self.log(f"  ⚠ 2ª tentativa ainda com {len(_erros2)} erro(s) bloqueante(s)")
                            # Atualizar lista de pendências com os erros da 2ª tentativa
                            pendencias = _erros2
                        else:
                            self.log("  ⚠ 2ª tentativa não confirmou sucesso — oferecendo edição manual")
                except Exception as e:
                    self.log(f"  ⚠ Erro 2ª tentativa: {e}")

            # Se ainda houver pendência após retry → emitir evento [MANUAL_EDIT_REQUIRED]
            if pendencias:
                self._capturar_conversation_id()
                conv = self._calculo_conversation_id or "?"
                # URL passada via proxy do app (mesma origem que o frontend usa)
                edit_url = f"/pjecalc/pages/calculo/calculo.jsf?conversationId={conv}"
                # Screenshot da tela da pendência ANTES de navegar para verbas,
                # para diagnóstico humano. Path determinístico por sessão.
                try:
                    import pathlib as _pl, os as _os
                    sessao_pre = self.sessao_id or _os.environ.get("PJECALC_SESSAO_ID") or getattr(
                        self.previa, "_sessao_id", None
                    ) or "unknown"
                    snap_dir_pre = _pl.Path("/tmp/pjecalc_snapshots")
                    snap_dir_pre.mkdir(parents=True, exist_ok=True)
                    shot_path = snap_dir_pre / f"{sessao_pre}_pendencia.png"
                    self._page.screenshot(path=str(shot_path), full_page=True)
                    self.log(f"  📸 Screenshot pendência: {shot_path}")
                except Exception as e:
                    self.log(f"  ⚠ Screenshot pendência falhou: {e}")
                # Capturar snapshot INICIAL da listagem de Verbas para futuro
                # DOM-diff quando o usuário concluir a edição manual. Navega
                # primeiro para Verbas, captura, e persiste em filesystem.
                snapshot_inicial = None
                try:
                    self._navegar_menu("li_calculo_verbas")
                    self._aguardar_ajax(6000)
                    self._page.wait_for_timeout(800)
                    snapshot_inicial = self.capturar_snapshot_listagem_verbas()
                    # Persistir no sistema de arquivos para o endpoint de diff
                    # ler depois (path determinístico por sessão).
                    import json as _json, pathlib as _pl, os as _os
                    sessao = self.sessao_id or _os.environ.get("PJECALC_SESSAO_ID") or getattr(
                        self.previa, "_sessao_id", None
                    ) or "unknown"
                    # Salvar em DOIS locais: volume persistente (sobrevive restart)
                    # + /tmp (compat. com versões anteriores). O endpoint de diff
                    # busca em cascade.
                    snap_dirs = [
                        _pl.Path("data/calculations/_snapshots"),
                        _pl.Path("/app/data/calculations/_snapshots"),
                        _pl.Path("/tmp/pjecalc_snapshots"),
                    ]
                    payload_snapshot = _json.dumps({
                        "conv": conv,
                        "url": edit_url,
                        "snapshot": snapshot_inicial,
                    }, ensure_ascii=False)
                    paths_salvos: list[str] = []
                    for snap_dir in snap_dirs:
                        try:
                            snap_dir.mkdir(parents=True, exist_ok=True)
                            snap_path = snap_dir / f"{sessao}_inicial.json"
                            snap_path.write_text(payload_snapshot, encoding="utf-8")
                            paths_salvos.append(str(snap_path))
                        except Exception as _e_dir:
                            self.log(f"  ⚠ Snapshot dir {snap_dir} skipped: {_e_dir}")
                    if paths_salvos:
                        self.log(f"  ✓ Snapshot inicial salvo em {len(paths_salvos)} local(is): {paths_salvos[0]} ({len(snapshot_inicial.get('linhas', []))} verbas)")
                    else:
                        self.log("  ⚠ Nenhum local de snapshot disponível para gravar")
                except Exception as e:
                    self.log(f"  ⚠ Snapshot inicial falhou: {e}")
                payload = {
                    "url": edit_url,
                    "conversationId": conv,
                    "pendencias": pendencias[:10],
                    "detalhes": detalhes_pendencias[:30],
                    "snapshot_capturado": snapshot_inicial is not None,
                }
                # Marcador especial reconhecido pelo SSE/frontend
                import json as _json
                self.log(f"[MANUAL_EDIT_REQUIRED] {_json.dumps(payload, ensure_ascii=False)}")
                # Bloco legível com cada pendência enumerada — visível no log
                # mesmo que o frontend perca o evento [MANUAL_EDIT_REQUIRED].
                self.log("")
                self.log("┌─ 📋 PENDÊNCIAS BLOQUEANTES DA LIQUIDAÇÃO ─" + "─" * 20)
                _todas_pendencias = pendencias + [
                    d for d in detalhes_pendencias if d not in pendencias
                ]
                if not _todas_pendencias:
                    self.log("│  (PJE-Calc não retornou texto explícito — investigar logs do JBoss)")
                for _idx, _p in enumerate(_todas_pendencias[:15], start=1):
                    # Quebrar mensagens muito longas em múltiplas linhas
                    _texto = str(_p).strip()
                    if len(_texto) > 110:
                        _texto = _texto[:107] + "..."
                    self.log(f"│  {_idx:>2}. {_texto}")
                self.log("└" + "─" * 60)
                self.log("")
                self.log(
                    "  ⚠ Liquidação bloqueada por pendências. Use o link de edição manual "
                    "para corrigir os parâmetros diretamente no PJE-Calc Cidadão. Esta é a "
                    "última alternativa — todos os demais dados já foram preenchidos pela "
                    "automação; faça apenas as correções pontuais para finalizar."
                )
                # Enriquece a mensagem do RuntimeError com as 5 primeiras
                # pendências para que apareçam em [FIM DA EXECUÇÃO ERRO] também
                # — usuário não precisa rolar os logs até achar.
                _resumo_pend = " | ".join(
                    [str(p).strip()[:90] for p in _todas_pendencias[:5]]
                ) or "sem texto explícito do PJE-Calc"
                raise RuntimeError(
                    f"Liquidação bloqueada por pendências após 2 tentativas. "
                    f"Pendências: {_resumo_pend}. "
                    f"Edição manual oferecida ao usuário (painel acima)."
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


# ─── Snapshot externo para correção manual (DOM-diff) ──────────────────────

def capturar_snapshot_final_listagem(
    conv_id: str,
    numero_processo: str | None = None,
    pjecalc_url: str = "http://localhost:9257/pjecalc",
    log_fn: Callable[[str], None] | None = None,
) -> dict:
    """Abre Playwright efêmero, navega para a listagem de Verbas e captura
    o snapshot atual. Tenta 2 estratégias em cascata:

    1. URL direta `verba-calculo.jsf?conversationId={conv_id}` — funciona
       quando a conv Seam ainda está em modo edição com o cálculo aberto.
    2. Fallback via Home → Recentes (duplo-click no cálculo) → sidebar
       Verbas. Necessário quando a conv original expirou ou perdeu contexto.
    """
    from playwright.sync_api import sync_playwright
    _log = log_fn or (lambda m: logger.info(m))
    snap: dict = {"linhas": [], "reflexos_ativos": [], "mensagens": [], "erro": None}

    def _coletar(page) -> dict:
        return page.evaluate("""() => {
            const trs = [...document.querySelectorAll('tr')];
            const linhas = trs
                .filter(tr => tr.querySelector('input[id*=":verbaSelecionada"]'))
                .map(tr => (tr.textContent||'').replace(/\\s+/g,' ').trim())
                .filter(t => t);
            const reflexos = [...document.querySelectorAll('input[id*=":listaReflexo:"][id$=":ativo"]')]
                .filter(c => c.checked)
                .map(c => c.id);
            const total_el = document.querySelector('[id*=":totalDevido"], [id*=":total"], [id$=":valorTotal"]');
            const total = total_el ? (total_el.value || total_el.textContent || '').trim() : null;
            const msgs = [...document.querySelectorAll('.rf-msgs-detail,.rf-msgs-sum,.rich-message-detail')]
                .map(e => (e.textContent||'').trim()).filter(t => t).slice(0, 10);
            return {linhas, reflexos_ativos: reflexos, valor_total: total, mensagens: msgs, url: location.href.split('#')[0]};
        }""")

    with sync_playwright() as pw:
        try:
            browser = pw.firefox.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            # Estratégia 1: URL direta com conv_id original
            url_verbas = (
                f"{pjecalc_url}/pages/calculo/verba/verba-calculo.jsf"
                f"?conversationId={conv_id}"
            )
            page.goto(url_verbas, wait_until="domcontentloaded", timeout=20000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            snap = _coletar(page)
            snap["estrategia"] = "url-direta"

            # Estratégia 2: listagem vazia → conv pode ter expirado. Reabrir
            # via Recentes (duplo-click) + sidebar Verbas.
            if not snap.get("linhas") and numero_processo:
                _log(f"  ⚠ Listagem vazia em conv={conv_id} — tentando reabrir via Recentes")
                page.goto(f"{pjecalc_url}/pages/principal.jsf", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1500)
                # Procurar select de Recentes (não-vazio) e fazer dblclick no item certo
                reaberto = page.evaluate("""(numProc) => {
                    const SKIP = new Set(['selAcheFacil']);
                    let target = null;
                    for (const s of document.querySelectorAll('select')) {
                        if (SKIP.has(s.name) || SKIP.has(s.id)) continue;
                        if (s.size > 1 && (s.name||'').startsWith('formulario:')) { target = s; break; }
                    }
                    if (!target) return null;
                    const opts = [...target.options];
                    const idx = opts.findIndex(o => (o.text||'').includes(numProc));
                    if (idx < 0) return null;
                    target.selectedIndex = idx;
                    target.options[idx].selected = true;
                    target.dispatchEvent(new Event('change', {bubbles: true}));
                    target.dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true}));
                    target.options[idx].dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true}));
                    return idx;
                }""", numero_processo)
                if reaberto is not None:
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    page.wait_for_timeout(2000)
                    # Capturar nova conv da URL
                    m = page.evaluate("() => location.href.match(/conversationId=(\\d+)/)?.[1] || null")
                    if m:
                        page.goto(
                            f"{pjecalc_url}/pages/calculo/verba/verba-calculo.jsf?conversationId={m}",
                            wait_until="domcontentloaded", timeout=15000,
                        )
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:
                            pass
                        page.wait_for_timeout(1500)
                        snap = _coletar(page)
                        snap["estrategia"] = f"recentes-reabrir:conv={m}"
                    else:
                        _log("  ⚠ Reabertura via Recentes não mudou URL (sem conv nova)")
                else:
                    _log(f"  ⚠ Processo {numero_processo} não encontrado nos Recentes")
            browser.close()
        except Exception as e:
            _log(f"  ⚠ capturar_snapshot_final_listagem: {e}")
            snap["erro"] = str(e)
    return snap


def computar_diff_snapshots(inicial: dict, final: dict) -> dict:
    """Calcula diferenças entre dois snapshots da listagem de verbas.

    Retorna dict com:
      - `verbas_alteradas`: linhas que mudaram (texto da TR)
      - `verbas_adicionadas`: linhas novas no final
      - `verbas_removidas`: linhas que sumiram
      - `reflexos_adicionados`: ids de reflexo marcados depois
      - `reflexos_removidos`: ids de reflexo desmarcados
      - `valor_total_antes` / `valor_total_depois`
    """
    set_ini = set(inicial.get("linhas", []) or [])
    set_fim = set(final.get("linhas", []) or [])
    ref_ini = set(inicial.get("reflexos_ativos", []) or [])
    ref_fim = set(final.get("reflexos_ativos", []) or [])
    return {
        "verbas_adicionadas": sorted(list(set_fim - set_ini)),
        "verbas_removidas": sorted(list(set_ini - set_fim)),
        "verbas_alteradas": [],  # comparação fuzzy fica para v2 (mesmo nome, params diferentes)
        "reflexos_adicionados": sorted(list(ref_fim - ref_ini)),
        "reflexos_removidos": sorted(list(ref_ini - ref_fim)),
        "valor_total_antes": inicial.get("valor_total"),
        "valor_total_depois": final.get("valor_total"),
    }
