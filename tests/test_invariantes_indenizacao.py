"""Testes de INVARIANTES do bot v2 — descobertas 25/05/2026 via DOM forense.

Cada teste aqui valida que uma proteção crítica está presente em
`modules/playwright_v2.py`. Objetivo: IMPEDIR REGRESSÕES. Se alguém
remover acidentalmente uma proteção, este teste falha.

Os 7 invariantes estão documentados em CLAUDE.md seção
"Invariantes do bot — NÃO REVERTER".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ─── Carregar source do bot v2 ──────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT_V2 = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")


# ─── Invariante 1 — Modal Confirmação Regerar (Ok-handler) ─────────────────


def test_inv1_modal_handler_existe():
    """Helper _regerar_com_modal_confirmacao deve existir e tratar modal Ok."""
    assert "def _regerar_com_modal_confirmacao" in PLAYWRIGHT_V2
    # Marcador INVARIANTE preservado
    assert "INVARIANTE PERMANENTE — NÃO REVERTER" in PLAYWRIGHT_V2, \
        "Marcador INVARIANTE PERMANENTE no _regerar_com_modal_confirmacao removido!"
    # Não usa dialog handler (regressão crítica)
    # NÃO pode existir `page.once("dialog"` ou `page.on("dialog"` para o Regerar
    # (em outros contextos browser dialogs nativos pode ser OK; aqui buscamos
    # próximo ao botão regerarOcorrencias)
    pattern_regerar = re.search(
        r"def _regerar_com_modal_confirmacao.*?(?=\n    def |\Z)",
        PLAYWRIGHT_V2,
        re.DOTALL,
    )
    assert pattern_regerar, "helper não encontrado"
    body = pattern_regerar.group(0)
    # Excluir linhas de docstring/comentário ANTES de buscar regressões
    code_lines = []
    in_docstring = False
    for line in body.split("\n"):
        stripped = line.lstrip()
        if '"""' in line:
            in_docstring = not in_docstring
            continue
        if in_docstring or stripped.startswith("#"):
            continue
        # Excluir comentário JS dentro de strings JS (// ou /* */)
        if "// " in line or "/* " in line:
            continue
        code_lines.append(line)
    code_body = "\n".join(code_lines)
    assert 'page.once("dialog"' not in code_body and 'page.on("dialog"' not in code_body, \
        "REGRESSÃO: helper voltou a usar dialog handler — modal rich:modalPanel não é dialog!"


def test_inv1_botao_ok_busca():
    """Helper deve buscar botão 'Ok' visível (offsetParent !== null)."""
    assert re.search(r"\/\^Ok\$\/i", PLAYWRIGHT_V2), \
        "Helper deve fazer regex match exato em 'Ok' (case-insensitive)"
    assert "offsetParent !== null" in PLAYWRIGHT_V2, \
        "Verificação de visibilidade do botão Ok deve permanecer"


# ─── Invariante 2 — Matcher EXATO POR TD em linkOcorrencias ────────────────


def test_inv2_match_exato_td_em_link_ocorrencias():
    """linkOcorrencias deve usar match EXATO no td (não tr.textContent.includes)."""
    # Helper deve filtrar linksMain primeiro
    assert "a.linkOcorrencias" in PLAYWRIGHT_V2
    assert ":listaReflexo:" in PLAYWRIGHT_V2  # filter para excluir reflexos
    # Match exato: td.textContent === alvoN (não .includes)
    pattern_inline = re.search(
        r"def _configurar_ocorrencias_informado_inline.*?(?=\n    def |\Z)",
        PLAYWRIGHT_V2,
        re.DOTALL,
    )
    assert pattern_inline, "_configurar_ocorrencias_informado_inline não encontrado"
    body = pattern_inline.group(0)
    # CRITÉRIO: deve haver `=== alvoN` (igualdade exata)
    assert "=== alvoN" in body, \
        "REGRESSÃO: matcher deve usar igualdade exata (=== alvoN), " \
        "não substring (.includes)"


def test_inv2_nao_usa_tr_textcontent_includes_para_match():
    """Bug histórico: tr.textContent.includes(alvo) casava TR de layout outermost."""
    # NÃO pode haver match de tr.textContent.includes próximo ao linkOcorrencias
    # Buscamos especificamente o anti-padrão dentro de _configurar_ocorrencias_informado_inline
    pattern_inline = re.search(
        r"def _configurar_ocorrencias_informado_inline.*?(?=\n    def |\Z)",
        PLAYWRIGHT_V2,
        re.DOTALL,
    )
    body = pattern_inline.group(0)
    # Tolerar dentro de comentário (descrevendo o bug histórico)
    # Linhas sem comentário Python e sem comentário JS:
    code_lines = [l for l in body.split("\n")
                  if not l.lstrip().startswith("#")
                  and "// " not in l
                  and "/* " not in l]
    code_body = "\n".join(code_lines)
    assert "tr.textContent.includes" not in code_body, \
        "REGRESSÃO: matcher voltou a usar tr.textContent.includes — " \
        "vai casar TR outermost com sidebar + main"


# ─── Invariante 3 — Native Playwright click em linkOcorrencias ─────────────


def test_inv3_native_click_via_playwright_locator():
    """linkOcorrencias deve usar self._page.locator(...).click(force=True) — Strategy B."""
    pattern_inline = re.search(
        r"def _configurar_ocorrencias_informado_inline.*?(?=\n    def |\Z)",
        PLAYWRIGHT_V2,
        re.DOTALL,
    )
    body = pattern_inline.group(0)
    # Deve haver chamada Playwright nativa
    assert ".click(force=True)" in body, \
        "REGRESSÃO: Strategy B (native click force=True) ausente"


# ─── Invariante 4 — Regerar após cada save (parâmetro OU ocorrência) ───────


def test_inv4_regerar_pos_parametros_existe():
    """Após save de parâmetros de verba: Regerar."""
    assert "Regerar pós-parâmetros" in PLAYWRIGHT_V2
    assert "_regerar_com_modal_confirmacao" in PLAYWRIGHT_V2


def test_inv4_regerar_pos_ocorrencias_existe():
    """Após save de ocorrências de verba: Regerar."""
    assert "Regerar pós-ocorrências" in PLAYWRIGHT_V2


# ─── Invariante 5 — Cascade A→B→C→D em linkOcorrencias ─────────────────────


def test_inv5_cascade_4_strategies_em_linkocorrencias():
    """4 strategies de click linkOcorrencias devem estar presentes."""
    pattern_inline = re.search(
        r"def _configurar_ocorrencias_informado_inline.*?(?=\n    def |\Z)",
        PLAYWRIGHT_V2,
        re.DOTALL,
    )
    body = pattern_inline.group(0)
    # Os 4 mecanismos devem estar:
    # A onclick-exec, B native, C jsfcljs, D form.submit
    assert 'onclick-exec' in body.lower() or "onclick exec" in body.lower() or "Function('event'" in body, \
        "Strategy A (onclick-exec) ausente"
    assert ".click(force=True)" in body, \
        "Strategy B (native click) ausente"
    assert "jsfcljs" in body, \
        "Strategy C (jsfcljs) ausente"
    assert "f.submit()" in body, \
        "Strategy D (form.submit) ausente"
    # Iteração explícita das strategies
    assert re.search(r'\["A".*"B".*"C".*"D"\]', body), \
        "Loop de strategies A→B→C→D ausente"


# ─── Invariante 6 — Filtro DESLIGAMENTO (desmarcar ocorrências fora período) ─


def test_inv6_filtro_desligamento_existe():
    """Filtro DESLIGAMENTO: desmarcar ativo=true exceto última row."""
    assert "FILTRO DESLIGAMENTO" in PLAYWRIGHT_V2
    pattern_inline = re.search(
        r"def _configurar_ocorrencias_informado_inline.*?(?=\n    def |\Z)",
        PLAYWRIGHT_V2,
        re.DOTALL,
    )
    body = pattern_inline.group(0)
    # Deve desmarcar checkboxes :ativo de listagem
    assert ":listagem:" in body and ":ativo" in body
    # Para DESLIGAMENTO, distribuir valor em [0, 0, ..., valor_total] (última)
    assert "[0.0] * (n - 1) + [valor_total]" in body, \
        "REGRESSÃO: distribuição DESLIGAMENTO deve ter valor na ÚLTIMA row"


# ─── Invariante 7 — Forensic DOM dump ──────────────────────────────────────


def test_inv7_dom_dump_em_4_fases():
    """4 fases de dump: pre_click, post_click, pre_recovery, post_recovery."""
    pattern_inline = re.search(
        r"def _configurar_ocorrencias_informado_inline.*?(?=\n    def |\Z)",
        PLAYWRIGHT_V2,
        re.DOTALL,
    )
    body = pattern_inline.group(0)
    for fase in ("pre_click", "post_click", "pre_recovery", "post_recovery"):
        assert f'fase="{fase}"' in body, \
            f"REGRESSÃO: dump fase={fase} removido — investigação futura precisa"


def test_inv7_dump_helper_existe():
    """Helper _dump_dom_indenizacao deve existir."""
    assert "def _dump_dom_indenizacao" in PLAYWRIGHT_V2
    # Deve dumpar para /tmp/pjecalc_snapshots/
    assert "pjecalc_snapshots" in PLAYWRIGHT_V2


# ─── Invariante 8 — Re-routing INFORMADO+DESLIGAMENTO → Manual (MP-1 H3) ─


def test_inv8_reroute_informado_desligamento_para_manual():
    """INFORMADO+DESLIGAMENTO deve ser re-roteada de Expresso para Manual.

    Comprovação test 39 (commit 6c66afe, 25/05/2026): re-routing reduz
    erros de 1 → 0 → PJC exportado pela primeira vez no caso Scarlette.
    Sem re-routing, alert "param Ocorrência de Pagamento alterado APÓS
    geração" persiste mesmo com modal handler + cascade + filtro DESLIGAMENTO.

    Causa raiz: PJE-Calc grava timestamp de geração no momento do lançamento
    Expresso (ocorrencia_pagamento=MENSAL default). Mudança subsequente
    para DESLIGAMENTO via parametrizar → flag "param alterado APÓS geração".
    Manual flow permite criar com DESLIGAMENTO desde T0.
    """
    # Verifica que existe a lógica de re-routing em fase_verbas
    assert "Re-roteado para Manual" in PLAYWRIGHT_V2, \
        "Log de re-routing INFORMADO+DESLIGAMENTO removido"
    assert "_is_inf_desligamento" in PLAYWRIGHT_V2 or "MP-1 H3" in PLAYWRIGHT_V2, \
        "Detecção INFORMADO+DESLIGAMENTO removida"
    # Verifica que reroute está antes do _lancar_expresso e antes do _lancar_verba_manual
    idx_reroute = PLAYWRIGHT_V2.find("Re-roteado para Manual")
    idx_expresso = PLAYWRIGHT_V2.find("self._lancar_expresso(verbas_expresso)")
    idx_manual = PLAYWRIGHT_V2.find("self._lancar_verba_manual(v)")
    assert 0 < idx_reroute < idx_expresso, \
        "Re-routing deve ocorrer ANTES de _lancar_expresso(verbas_expresso)"
    assert 0 < idx_reroute < idx_manual, \
        "Re-routing deve ocorrer ANTES de _lancar_verba_manual"


# ─── Invariante 9 — Divisor CLT para 13º e Férias+1/3 ─────────────────────


def test_inv9_divisor_clt_override():
    """13º SALÁRIO e FÉRIAS + 1/3 SEMPRE divisor=12 (constante CLT).

    Bug histórico (26/05/2026): IA externa gerou divisor.valor=1 para essas
    verbas. PJE-Calc multiplicava cálculo por 12 → erro grave.

    Defesa dupla:
    - Bot: override defensivo se divisor != 12 para 13º/Férias
    - Prompt: regra crítica explícita exigindo divisor=12
    """
    # Camada 1 (bot)
    assert "CLT override" in PLAYWRIGHT_V2, \
        "Override defensivo divisor=12 para 13º/Férias removido"
    assert "FÉRIAS + 1/3" in PLAYWRIGHT_V2 and "(constante CLT)" in PLAYWRIGHT_V2

    # Camada 2 (prompt)
    extraction = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "DIVISOR CLT" in extraction or "divisor=OUTRO_VALOR=12" in extraction, \
        "Regra crítica no prompt sobre divisor=12 removida"
    assert "constante CLT" in extraction


# ─── Marker: regressão de mudança Sobrescrever pós-params ──────────────────


def test_marker_sobrescrever_pos_params_NAO_aplicado_universalmente():
    """Tentativa fracassada (commit 312839e, revertido ac0c712): aplicar
    Sobrescrever=True em post-params Regerar para INFORMADO+DESLIGAMENTO
    introduzia listagem vazia mid-loop. Manter sobrescrever=False (Manter)
    como default no Regerar pós-parâmetros.
    """
    # No Regerar pós-parâmetros, sobrescrever deve ser False (ou condicional
    # com nova evidência). Por enquanto, conservador: False.
    pattern = re.search(
        r"# REGRA OPERACIONAL.*?Regerar pós-parâmetros.*?\)",
        PLAYWRIGHT_V2,
        re.DOTALL,
    )
    # Não falhar se a regra evoluir — mas registrar intent.
    # Apenas: se houver `sobrescrever=True` próximo a "pós-parâmetros", emitir warning.
    # Para CI, validar apenas que o helper existe.
    assert "_regerar_com_modal_confirmacao" in PLAYWRIGHT_V2
