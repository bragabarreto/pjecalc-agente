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


# ─── Invariante 9 — Divisor CLT para 13º e Férias+1/3 (no NORMALIZER!) ────


def test_inv9_divisor_clt_no_normalizer():
    """13º SALÁRIO e FÉRIAS + 1/3 SEMPRE divisor=12 (constante CLT).

    Bug histórico (26/05/2026): IA externa gerou divisor.valor=1 para essas
    verbas. PJE-Calc multiplicava cálculo por 12 → erro grave.

    ⚠ FIDELIDADE PRÉVIA↔AUTOMAÇÃO (CLAUDE.md): correção deve estar no
    NORMALIZER (antes da prévia), NÃO no bot. Caso contrário usuário vê
    divisor=1 na prévia e bot aplica 12 sem aviso — quebra fidelidade.

    Defesa em 3 camadas:
    - Camada 1 (prompt externo): IA não gera divisor=1
    - Camada 2 (normalizer): se IA escapar, corrige ANTES da prévia
    - Camada 3 (prompt interno fallback): regra reforçada
    Bot NÃO deve fazer override — apenas aplicar o JSON da prévia.
    """
    # Camada 2: normalizer (PRIMARY — preserva fidelidade prévia↔automação)
    normalizer = (REPO_ROOT / "modules" / "json_normalizer.py").read_text(encoding="utf-8")
    assert "INVARIANTE CLT" in normalizer, \
        "Normalizer não tem correção CLT divisor=12 para 13º/Férias"
    assert "FÉRIAS + 1/3" in normalizer and "fidelidade prévia↔automação" in normalizer

    # Camada 3 (prompt interno fallback)
    extraction = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "DIVISOR CLT" in extraction or "divisor=OUTRO_VALOR=12" in extraction, \
        "Regra crítica no prompt interno sobre divisor=12 removida"
    assert "constante CLT" in extraction

    # Camada 1 (prompt externo)
    ext_prompt = (REPO_ROOT / "docs" / "prompt-projeto-claude-externo.md").read_text(encoding="utf-8")
    assert "DIVISOR CLT" in ext_prompt or "constante legal de 12" in ext_prompt, \
        "Prompt externo não tem regra divisor=12"

    # Bot NÃO deve ter override — fidelidade prévia↔automação
    assert "CLT override" not in PLAYWRIGHT_V2, \
        "REGRESSÃO: bot voltou a fazer override CLT. Override deve estar no NORMALIZER, " \
        "não no bot — para preservar fidelidade prévia↔automação (CLAUDE.md)."


def test_inv9_normalizer_behavior_divisor_13o_e_ferias():
    """Teste de COMPORTAMENTO (não só grep): chama normalize_v2_json com
    payload simulando IA enviando divisor=1 e valida que corrige para 12."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from modules.json_normalizer import normalize_v2_json

    cases = [
        ("13º SALÁRIO", "DECIMO_TERCEIRO_SALARIO"),
        ("FÉRIAS + 1/3", "FERIAS"),
    ]
    for nome, caract in cases:
        payload = {
            "verbas_principais": [{
                "nome_pjecalc": nome,
                "expresso_alvo": nome,
                "parametros": {
                    "caracteristica": caract,
                    "valor": "CALCULADO",
                    "formula_calculado": {
                        "base_calculo": {"tipo": "HISTORICO_SALARIAL"},
                        "divisor": {"tipo": "OUTRO_VALOR", "valor": 1},
                        "multiplicador": 1.0,
                        "quantidade": {"tipo": "AVOS"},
                    },
                },
            }],
        }
        out = normalize_v2_json(payload)
        div = out["verbas_principais"][0]["parametros"]["formula_calculado"]["divisor"]
        assert float(div["valor"]) == 12.0, \
            f"Normalizer NÃO corrigiu divisor de '{nome}' para 12 (got {div['valor']})"


def test_inv9_normalizer_nao_toca_divisor_outras_verbas():
    """Normalizer NÃO deve forçar divisor=12 em verbas que NÃO são 13º/Férias."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from modules.json_normalizer import normalize_v2_json
    payload = {
        "verbas_principais": [{
            "nome_pjecalc": "MULTA DO ARTIGO 477 DA CLT",
            "expresso_alvo": "MULTA DO ARTIGO 477 DA CLT",
            "parametros": {
                "valor": "CALCULADO",
                "formula_calculado": {
                    "base_calculo": {"tipo": "MAIOR_REMUNERACAO"},
                    "divisor": {"tipo": "OUTRO_VALOR", "valor": 1},
                    "multiplicador": 1.0,
                    "quantidade": {"tipo": "INFORMADA"},
                },
            },
        }],
    }
    out = normalize_v2_json(payload)
    div = out["verbas_principais"][0]["parametros"]["formula_calculado"]["divisor"]
    assert float(div["valor"]) == 1.0, \
        f"Normalizer TOCOU divisor de MULTA 477 (deveria ser 1, got {div['valor']})"


# ─── Invariante 12 — Cartão de ponto MULTI-PERÍODO ────────────────────────


def test_inv12_cartoes_de_ponto_lista_schema():
    """Schema deve aceitar cartoes_de_ponto: list[CartaoDePonto] (Scarlette 27/05/2026)."""
    schema_src = (REPO_ROOT / "docs" / "schema-v2" / "99-pydantic-models.py").read_text(encoding="utf-8")
    assert "cartoes_de_ponto:" in schema_src, \
        "Schema não tem campo cartoes_de_ponto (lista)"
    assert "list[CartaoDePonto]" in schema_src, \
        "cartoes_de_ponto não é list[CartaoDePonto]"
    # cartao_de_ponto (singular) mantido por retrocompat
    assert "cartao_de_ponto: Optional[CartaoDePonto]" in schema_src, \
        "cartao_de_ponto singular removido (quebra retrocompat)"


def test_inv12_normalizer_migra_singular_para_lista():
    """Normalizer deve migrar cartao_de_ponto singular → cartoes_de_ponto[1]."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from modules.json_normalizer import normalize_v2_json
    payload = {
        "cartao_de_ponto": {
            "data_inicial": "01/01/2024",
            "data_final": "31/12/2024",
            "preenchimento": "PROGRAMACAO",
            "jornada_padrao": {},
        },
    }
    out = normalize_v2_json(payload)
    assert "cartoes_de_ponto" in out, "Campo cartoes_de_ponto não criado"
    assert isinstance(out["cartoes_de_ponto"], list), "cartoes_de_ponto não é lista"
    assert len(out["cartoes_de_ponto"]) == 1, \
        f"Esperava 1 cartão, recebeu {len(out['cartoes_de_ponto'])}"


def test_inv12_bot_itera_cartoes():
    """Bot deve iterar cartoes_de_ponto via loop com _processar_um_cartao_de_ponto."""
    src = PLAYWRIGHT_V2
    assert "cartoes_de_ponto" in src, "Bot não consome cartoes_de_ponto"
    assert "_processar_um_cartao_de_ponto" in src, \
        "Helper _processar_um_cartao_de_ponto ausente"
    assert "for idx, cp in enumerate(cartoes_validos)" in src or "for cp in cartoes_validos" in src, \
        "Bot não itera cartoes_validos em loop"


def test_inv12_prompt_orienta_multi_periodo():
    """Prompt deve orientar uso de cartoes_de_ponto (lista) p/ multi-período."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "cartoes_de_ponto" in ext, "Prompt não menciona cartoes_de_ponto"
    assert "MULTI-PERÍODO" in ext or "multi-período" in ext.lower(), \
        "Regra multi-período ausente no prompt"


# ─── Invariante 11 — Comentário JG concordância de gênero ─────────────────


def test_inv11_comentarios_jg_formato_canonico():
    """Texto JG deve ser 'parte reclamante/reclamada - NOME, beneficiária'."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "parte reclamante" in ext.lower() or "parte reclamada" in ext.lower(), \
        "Prompt não orienta uso de 'parte reclamante/reclamada'"
    # Aceita qualquer das marcas de regra crítica
    assert any(s in ext for s in [
        "REGRA CRÍTICA DE CONCORDÂNCIA",
        "POLÍTICA — preencha APENAS FATOS",
        "justica_gratuita",
    ]), "Prompt não tem regra explícita JG"
    # Aviso explícito sobre evitar em-dash (Latin-1)
    assert "Latin-1" in ext or "ISO-8859" in ext or "hífen" in ext.lower(), \
        "Prompt não avisa sobre uso de hífen (vs em-dash)"
    # Fix RODRIGO 11/06/2026: o fallback do BOT foi removido (lógica errada —
    # assumia devedor=JG; violava fidelidade prévia↔automação). O formato
    # canônico agora é responsabilidade exclusiva do NORMALIZER.
    norm = (REPO_ROOT / "modules" / "json_normalizer.py").read_text(encoding="utf-8")
    assert "beneficiária da Justiça" in norm, \
        "Normalizer não tem o texto canônico de suspensão de exigibilidade"
    assert "_build_comentarios_jg" in norm
    # NUNCA usar em-dash — PJE-Calc Latin-1 não suporta U+2014
    assert "pela parte {parte_lower} — " not in norm, \
        "REGRESSÃO: normalizer voltou a usar EM-DASH — PJE-Calc converte para ¿"


def test_inv11_normalizer_converte_legacy():
    """Normalizer deve converter 'pelo Reclamante, beneficiário' → formato novo."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from modules.json_normalizer import normalize_v2_json

    payload = {
        "processo": {
            "reclamante": {"nome": "MARIA SOUZA"},
            "reclamado": {"nome": "EMPRESA LTDA"},
        },
        "parametros_calculo": {
            "comentarios_jg": "Suspensão de exigibilidade dos honorários sucumbenciais devidos pelo Reclamante, beneficiário da Justiça Gratuita (art. 791-A, § 4º, da CLT).",
        },
        "honorarios": [{"tipo_honorario": "SUCUMBENCIAIS", "tipo_devedor": "RECLAMANTE"}],
    }
    out = normalize_v2_json(payload)
    novo = out["parametros_calculo"]["comentarios_jg"]
    assert "parte reclamante" in novo, f"Não converteu para 'parte reclamante': {novo}"
    assert "MARIA SOUZA" in novo, f"Nome ausente: {novo}"
    assert "beneficiária" in novo, f"Concordância feminina ausente: {novo}"
    # Idempotência
    out2 = normalize_v2_json(out)
    assert out2["parametros_calculo"]["comentarios_jg"] == novo, "Não é idempotente"


# ─── Invariante 10 — juros_combinacoes multi-fase (ADC 58 + TST E-ED-RR-20407) ─


def test_inv10_juros_combinacoes_schema_existe():
    """Schema v2 deve ter campo `juros_combinacoes: list[FaseJuros]` para
    suportar até N fases de juros (modelo TST 3 fases).
    """
    schema_src = (REPO_ROOT / "docs" / "schema-v2" / "99-pydantic-models.py").read_text(encoding="utf-8")
    assert "class FaseJuros" in schema_src, "Schema FaseJuros não definido"
    assert "juros_combinacoes:" in schema_src, "Campo juros_combinacoes ausente"
    assert "ADC 58" in schema_src and "E-ED-RR-20407" in schema_src, \
        "Motivação jurídica (ADC 58 + TST E-ED-RR-20407) deve estar documentada"


def test_inv10_bot_aplica_juros_combinacoes():
    """Bot deve iterar `juros_combinacoes` e clicar addOutroJuros para cada fase."""
    src = PLAYWRIGHT_V2
    assert "juros_combinacoes" in src, "Bot não consome juros_combinacoes"
    assert "addOutroJuros" in src, "Bot não clica botão '+' addOutroJuros"
    # Loop por fases
    assert "for idx, fase in enumerate(fases_juros)" in src or "for fase in fases_juros" in src, \
        "Bot não itera N fases — pode estar limitado a 1 combinação"


def test_inv10_prompt_orienta_modelo_TST():
    """Prompt interno deve orientar modelo TST E-ED-RR-20407 + Lei 14.905."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "E-ED-RR-20407" in ext, "Prompt interno não cita TST E-ED-RR-20407"
    assert "Lei 14.905" in ext, "Prompt interno não cita Lei 14.905/2024"
    assert "30/08/2024" in ext, "Data de corte Lei 14.905 ausente"
    # 2 casos cobertos (Caso A pós, Caso B antigo)
    assert "Caso A" in ext and "Caso B" in ext, \
        "Prompt não cobre os 2 casos (ajuizamento >=30/08/2024 vs <30/08/2024)"


# ─── Histórico Salarial — consolidação CALCULADO/SALARIO_MINIMO ────────────


def test_inv13_normalizer_consolida_sm_oficial():
    """2+ entradas INFORMADO com valor de SM oficial em períodos contíguos
    são consolidadas em 1 entrada CALCULADO/SALARIO_MINIMO (quantidade=1.0).

    Causa raiz histórica (Mikaely 28/05/2026): IA gerava "SALARIO MINIMO
    2024" R$ 1.412 + "SALARIO MINIMO 2025" R$ 1.518 como entradas separadas.
    """
    from modules.json_normalizer import normalize_v2_json

    payload = {
        "historico_salarial": [
            {"nome": "SALARIO MINIMO 2024", "parcela": "FIXA",
             "incidencias": {"fgts": True, "cs_inss": True},
             "competencia_inicial": "08/2024", "competencia_final": "12/2024",
             "tipo_valor": "INFORMADO", "valor_brl": 1412.0, "calculado": None},
            {"nome": "SALARIO MINIMO 2025", "parcela": "FIXA",
             "incidencias": {"fgts": True, "cs_inss": True},
             "competencia_inicial": "01/2025", "competencia_final": "08/2025",
             "tipo_valor": "INFORMADO", "valor_brl": 1518.0, "calculado": None},
        ],
        "verbas_principais": [], "honorarios": [], "parametros_calculo": {},
    }
    res = normalize_v2_json(payload)
    hs = res["historico_salarial"]
    assert len(hs) == 1, f"esperava 1 entrada consolidada, got {len(hs)}"
    h = hs[0]
    assert h["tipo_valor"] == "CALCULADO"
    assert h["calculado"]["quantidade_pct"] == 1.0
    assert h["calculado"]["base_referencia"] == "SALARIO_MINIMO"
    assert h["competencia_inicial"] == "08/2024"
    assert h["competencia_final"] == "08/2025"


def test_inv13_normalizer_coerce_quantidade_pct_100_para_1():
    """quantidade_pct=100.0 com base SALARIO_MINIMO é coercido para 1.0.

    Bug histórico: prompt antigo dizia "100.0 = 100%" — PJE-Calc interpretaria
    como 100 salários mínimos (R$ 141.200). Normalizer protege como salvaguarda.
    """
    from modules.json_normalizer import normalize_v2_json

    payload = {
        "historico_salarial": [{
            "nome": "SALARIO", "parcela": "FIXA",
            "incidencias": {"fgts": True, "cs_inss": True},
            "competencia_inicial": "01/2024", "competencia_final": "12/2024",
            "tipo_valor": "CALCULADO", "valor_brl": None,
            "calculado": {"quantidade_pct": 100.0, "base_referencia": "SALARIO_MINIMO"},
        }],
        "verbas_principais": [], "honorarios": [], "parametros_calculo": {},
    }
    res = normalize_v2_json(payload)
    assert res["historico_salarial"][0]["calculado"]["quantidade_pct"] == 1.0


def test_inv13_normalizer_nao_consolida_entradas_mistas():
    """Não consolidar quando há entrada NÃO-SM (ex.: salário negociado fora da tabela)."""
    from modules.json_normalizer import normalize_v2_json

    payload = {
        "historico_salarial": [
            {"nome": "SM 2024", "parcela": "FIXA",
             "incidencias": {"fgts": True, "cs_inss": True},
             "competencia_inicial": "01/2024", "competencia_final": "12/2024",
             "tipo_valor": "INFORMADO", "valor_brl": 1412.0, "calculado": None},
            {"nome": "SALARIO NEGOCIADO", "parcela": "FIXA",
             "incidencias": {"fgts": True, "cs_inss": True},
             "competencia_inicial": "01/2025", "competencia_final": "12/2025",
             "tipo_valor": "INFORMADO", "valor_brl": 3500.0, "calculado": None},
        ],
        "verbas_principais": [], "honorarios": [], "parametros_calculo": {},
    }
    res = normalize_v2_json(payload)
    assert len(res["historico_salarial"]) == 2, "deve preservar entradas mistas"


def test_inv14_normalizer_anula_cartao_stub_vazio():
    """cartão {ocorrencias_override:[], preenchimento:'LIVRE'} sem datas → null.

    Bug recorrente (ALINE 01/06/2026, e Mikaely antes): IA emite stub vazio
    sem data_inicial/data_final → Pydantic rejeita em /confirmar → 422.
    Normalizer deve anular ANTES da prévia (fidelidade prévia↔automação).
    """
    from modules.json_normalizer import normalize_v2_json
    # Caso 1: stub clássico LIVRE
    res1 = normalize_v2_json({
        "cartao_de_ponto": {"ocorrencias_override": [], "preenchimento": "LIVRE"},
        "cartoes_de_ponto": [],
        "verbas_principais": [], "honorarios": [], "parametros_calculo": {},
    })
    assert res1.get("cartao_de_ponto") is None
    assert res1.get("cartoes_de_ponto") == []
    # Caso 2: lista com stub vazio
    res2 = normalize_v2_json({
        "cartoes_de_ponto": [{"ocorrencias_override": [], "preenchimento": "PROGRAMACAO"}],
        "verbas_principais": [], "honorarios": [], "parametros_calculo": {},
    })
    assert res2.get("cartoes_de_ponto") == []
    # Caso 3: cartão REAL com data deve ser preservado
    real = {
        "data_inicial": "01/01/2024", "data_final": "31/12/2024",
        "preenchimento": "PROGRAMACAO",
        "programacao_semanal": {"segunda": {"turnos": [{"entrada":"08:00","saida":"17:00"}]}},
    }
    res3 = normalize_v2_json({
        "cartao_de_ponto": real,
        "cartoes_de_ponto": [],
        "verbas_principais": [], "honorarios": [], "parametros_calculo": {},
    })
    cp_res = res3.get("cartao_de_ponto") or (res3.get("cartoes_de_ponto") or [None])[0]
    assert cp_res is not None, "cartão real foi indevidamente anulado"
    assert cp_res.get("data_inicial") == "01/01/2024"


def test_inv14_prompt_orienta_cartao_null_sem_jornada():
    """Prompt interno + externo devem ter regra explícita 'NÃO emitir stub vazio'."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "NUNCA emitir stub" in ext
    assert "SEM cartão: emitir EXATAMENTE" in ext or "EXATAMENTE `null`" in ext
    extp = (REPO_ROOT / "docs" / "prompt-projeto-claude-externo.md").read_text(encoding="utf-8")
    assert "NUNCA emitir stub" in extp


def test_inv15_normalizer_consolida_historico_arbitrario_em_evolucao():
    """N entradas adjacentes mesma componente + contíguas → 1 entrada com evolucao.

    Causa raiz (ALINE 01/06/2026): IA emitia 5 entradas "SALÁRIO ABRIL/2021",
    "SALÁRIO MAIO-JUN/2021", "SALÁRIO JUL/2021-SET/2022" etc. — todas o mesmo
    componente "SALÁRIO" com valores diferentes. Schema com `evolucao` resolve.
    """
    from modules.json_normalizer import normalize_v2_json

    payload = {
        "historico_salarial": [
            {"nome":"SALÁRIO ABRIL/2021","parcela":"FIXA","incidencias":{"fgts":True,"cs_inss":True},
             "competencia_inicial":"04/2021","competencia_final":"04/2021",
             "tipo_valor":"INFORMADO","valor_brl":2577.20,"calculado":None},
            {"nome":"SALÁRIO MAIO-JUN/2021","parcela":"FIXA","incidencias":{"fgts":True,"cs_inss":True},
             "competencia_inicial":"05/2021","competencia_final":"06/2021",
             "tipo_valor":"INFORMADO","valor_brl":2650.31,"calculado":None},
            {"nome":"SALÁRIO JUL/2021-SET/2022","parcela":"FIXA","incidencias":{"fgts":True,"cs_inss":True},
             "competencia_inicial":"07/2021","competencia_final":"09/2022",
             "tipo_valor":"INFORMADO","valor_brl":2928.0,"calculado":None},
        ],
        "verbas_principais":[], "honorarios":[], "parametros_calculo":{},
    }
    res = normalize_v2_json(payload)
    hs = res["historico_salarial"]
    assert len(hs) == 1, f"esperava 1 entrada consolidada, got {len(hs)}"
    h = hs[0]
    assert h["nome"] == "SALÁRIO"
    assert h["competencia_inicial"] == "04/2021"
    assert h["competencia_final"] == "09/2022"
    assert len(h["evolucao"]) == 3
    assert h["evolucao"][0]["valor_brl"] == 2577.20
    assert h["evolucao"][2]["valor_brl"] == 2928.0


def test_inv15_normalizer_preserva_componentes_diferentes():
    """Componentes DIFERENTES (salário base + adicional) NÃO devem consolidar."""
    from modules.json_normalizer import normalize_v2_json
    payload = {
        "historico_salarial":[
            {"nome":"SALÁRIO BASE","parcela":"FIXA","incidencias":{"fgts":True,"cs_inss":True},
             "competencia_inicial":"01/2024","competencia_final":"12/2024",
             "tipo_valor":"INFORMADO","valor_brl":3000.0,"calculado":None},
            {"nome":"ADICIONAL DE PERICULOSIDADE","parcela":"FIXA","incidencias":{"fgts":True,"cs_inss":True},
             "competencia_inicial":"01/2024","competencia_final":"12/2024",
             "tipo_valor":"INFORMADO","valor_brl":900.0,"calculado":None},
        ],
        "verbas_principais":[], "honorarios":[], "parametros_calculo":{},
    }
    res = normalize_v2_json(payload)
    assert len(res["historico_salarial"]) == 2


def test_inv15_normalizer_nao_consolida_periodos_com_gap():
    """Entradas com mesmo nome canônico mas períodos NÃO-contíguos não consolidam."""
    from modules.json_normalizer import normalize_v2_json
    payload = {
        "historico_salarial":[
            {"nome":"SALÁRIO 2021","parcela":"FIXA","incidencias":{"fgts":True,"cs_inss":True},
             "competencia_inicial":"01/2021","competencia_final":"03/2021",
             "tipo_valor":"INFORMADO","valor_brl":2500.0,"calculado":None},
            # GAP de meses entre 03/2021 e 06/2022
            {"nome":"SALÁRIO 2022","parcela":"FIXA","incidencias":{"fgts":True,"cs_inss":True},
             "competencia_inicial":"06/2022","competencia_final":"12/2022",
             "tipo_valor":"INFORMADO","valor_brl":2700.0,"calculado":None},
        ],
        "verbas_principais":[], "honorarios":[], "parametros_calculo":{},
    }
    res = normalize_v2_json(payload)
    assert len(res["historico_salarial"]) == 2, "gap em períodos deve impedir consolidação"


def test_inv15_bot_aplica_evolucao_nas_ocorrencias():
    """#80-L (0000712-53, 27/06/2026): a evolução de valores de UM histórico
    salarial é aplicada às OCORRÊNCIAS mensais (1 histórico só), NÃO mais
    expandida em N históricos separados (bug: 'REMUNERACAO MENSAL' com 31 steps
    virava 31 históricos poluindo a listagem). O PJE-Calc suporta valores
    mensais distintos dentro de um único histórico (listagemMC editável).
    Fix: fase_historico_salarial itera os históricos da prévia DIRETO (sem
    _expandir_evolucao_historico) e, após 'Gerar Ocorrências', chama
    _aplicar_evolucao_ocorrencias_historico p/ editar o valor de cada mês."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    # helper que aplica a evolução nas ocorrências mensais existe e é chamado
    assert "def _aplicar_evolucao_ocorrencias_historico" in pw
    assert "_aplicar_evolucao_ocorrencias_historico(hist)" in pw
    # a fase NÃO expande mais em N históricos (itera a prévia direto)
    fase = pw[pw.find("def fase_historico_salarial"):
              pw.find("def fase_historico_salarial") + 1500]
    assert "historicos_para_processar = list(self.previa.historico_salarial)" in fase, (
        "fase_historico_salarial deve iterar a prévia direto (sem expandir em N históricos)"
    )
    assert "_expandir_evolucao_historico(" not in fase, (
        "fase_historico_salarial NÃO deve mais chamar _expandir_evolucao_historico"
    )


def test_inv16_reroute_inf_desligamento_lista_excecoes():
    """Re-rotagem MP-1 H3 é SELETIVA: verbas Expresso cujo default é
    DESLIGAMENTO (Multa 477, Saldo Salário, Aviso Prévio) NÃO devem ser
    re-roteadas para Manual — funcionam direto pelo Expresso.

    Bug histórico (ALINE 02/06/2026): regra original re-roteava TODO
    INFORMADO+DESLIGAMENTO, causando falha no Manual flow para Multa 477
    (form não renderizava em tempo, verba salva vazia, PJC sem multa).
    """
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    # Lista de exceções DEVE existir e conter Multa 477 / Saldo / Aviso
    assert "_VERBAS_EXPRESSO_DEFAULT_DESLIGAMENTO" in pw
    assert "MULTA DO ARTIGO 477 DA CLT" in pw
    assert "SALDO DE SAL" in pw  # SALDO DE SALÁRIO (com ou sem acento)
    assert "AVISO PR" in pw  # AVISO PRÉVIO
    # E a função _is_inf_desligamento deve consultar essa lista
    idx_func = pw.find("def _is_inf_desligamento")
    assert idx_func > 0
    # Após a definição da função, deve haver uso da lista para excluir
    func_block = pw[idx_func:idx_func + 1500]
    assert "_VERBAS_EXPRESSO_DEFAULT_DESLIGAMENTO" in func_block


def test_inv16_lancar_verba_manual_aguarda_form_visivel():
    """_lancar_verba_manual DEVE aguardar form visível antes de preencher.

    Bug histórico (ALINE 02/06/2026): após `click incluir` + `_aguardar_ajax`,
    o bot tentava preencher radios INSTANTANEAMENTE. O form Manual ainda não
    estava renderizado → todos os radios falhavam silenciosamente → verba
    salva vazia. Fix: wait_for_selector('input[id$=":descricao"]') por 15s.
    """
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    idx = pw.find("def _lancar_verba_manual")
    assert idx > 0
    func = pw[idx:idx + 3500]
    # DEVE haver wait_for_selector com descricao + state=visible
    assert "wait_for_selector" in func
    assert "descricao" in func
    assert "state=\"visible\"" in func or "state='visible'" in func
    # Timeout adequado (≥15s para JSF carregar form sob Seam EPC carregado)
    assert "timeout=15000" in func or "timeout=20000" in func
    # Defesa adicional: se form não abrir, deve PULAR (não salvar vazio)
    assert "Pulando" in func or "skip" in func.lower() or "return" in func


def test_inv17_normalizer_corrige_caso_a_para_b_quando_cruza_30_08_2024():
    """Cálculo que CRUZA 30/08/2024 (data-corte Lei 14.905) deve ser Caso B.

    Bug histórico (ALINE 02/06/2026): IA gerou Caso A (sem combinações,
    IPCA + TAXA_LEGAL) para cálculo com data_inicio_calculo=14/04/2021
    e data_ajuizamento=14/04/2026 — cruza 30/08/2024. Period 04/2021-08/2024
    teria IPCA + TAXA_LEGAL quando deveria ser IPCAE + SELIC pré-Lei.
    """
    from modules.json_normalizer import normalize_v2_json
    payload = {
        "parametros_calculo": {
            "data_admissao": "07/12/2016",
            "data_demissao": "01/09/2024",
            "data_ajuizamento": "14/04/2026",
            "data_inicio_calculo": "14/04/2021",
            "data_termino_calculo": "22/10/2024",
        },
        "correcao_juros_multa": {
            "indice_trabalhista": "IPCA",         # IA emitiu Caso A
            "combinar_outro_indice": False,
            "indice_combinado": None,
            "data_inicio_combinacao": None,
            "juros": "TAXA_LEGAL",
            "aplicar_juros_fase_pre_judicial": True,
            "juros_combinacoes": [],
        },
        "historico_salarial": [], "verbas_principais": [], "honorarios": [],
    }
    res = normalize_v2_json(payload)
    cjm = res["correcao_juros_multa"]
    # Após normalizer, DEVE virar Caso B
    assert cjm["indice_trabalhista"] == "IPCAE", f"esperava IPCAE, got {cjm['indice_trabalhista']}"
    assert cjm["combinar_outro_indice"] is True
    assert cjm["indice_combinado"] == "IPCA"
    assert cjm["data_inicio_combinacao"] == "30/08/2024"
    # Modelo TST (fix THAÍS 10/06/2026, supersede 587f862): fase 1 = TRD
    # (art. 39 caput Lei 8.177 — pré-judicial) + combinação TAXA_LEGAL a
    # partir do AJUIZAMENTO. Com fase 1 TRD a combinação NÃO é redundante
    # (PJE-Calc não a converte para SEM_JUROS — comprovado no PJC THAÍS).
    assert cjm["juros"] == "TRD_SIMPLES"
    assert cjm["aplicar_juros_fase_pre_judicial"] is True
    combs = cjm.get("juros_combinacoes") or []
    assert len(combs) == 1
    assert combs[0]["tabela"] == "TAXA_LEGAL"
    assert combs[0]["data_inicio"] == "14/04/2026"


def test_inv17_normalizer_caso_b_com_ajuizamento_pre_corte_tem_2_fases():
    """Caso B com ajuizamento ANTERIOR a 30/08/2024 deve ter 2 fases:
    SELIC (do ajuizamento até 29/08/2024) + TAXA_LEGAL (pós-30/08/2024).

    Cenário: contrato com pensão vitalícia ou aviso prévio projetando o
    cálculo até depois de 30/08/2024 (cruza o corte) — ajuizamento ainda
    antes da Lei 14.905.
    """
    from modules.json_normalizer import normalize_v2_json
    # Cenário realista: ação ajuizada DURANTE contrato (antes da Lei 14.905),
    # mas demissão posterior a 30/08/2024 → cálculo cruza corte.
    payload = {
        "parametros_calculo": {
            "data_admissao": "01/03/2018",
            "data_demissao": "01/06/2025",
            "data_ajuizamento": "01/03/2023",   # PRÉ-30/08/2024
            "data_inicio_calculo": "01/03/2018",
            "data_termino_calculo": "01/06/2025",   # PÓS-corte (cruza)
        },
        "correcao_juros_multa": {
            "indice_trabalhista": "IPCA",
            "combinar_outro_indice": False,
            "juros": "TAXA_LEGAL",
            "juros_combinacoes": [],
        },
        "historico_salarial": [], "verbas_principais": [], "honorarios": [],
    }
    res = normalize_v2_json(payload)
    cjm = res["correcao_juros_multa"]
    combs = cjm.get("juros_combinacoes") or []
    # Espera 2 fases: SELIC pós-ajuizamento + TAXA_LEGAL pós-30/08/2024
    assert len(combs) == 2
    fase_selic = next((c for c in combs if c.get("tabela") == "SELIC"), None)
    fase_legal = next((c for c in combs if c.get("tabela") == "TAXA_LEGAL"), None)
    assert fase_selic is not None and fase_selic["data_inicio"] == "01/03/2023"
    assert fase_legal is not None and fase_legal["data_inicio"] == "30/08/2024"
    # Fase 1 (pré-judicial) = TRD (fix THAÍS 10/06/2026)
    assert cjm["juros"] == "TRD_SIMPLES"


def test_inv17_normalizer_preserva_caso_a_quando_tudo_pos_30_08_2024():
    """Cálculo TODO pós-30/08/2024: correção Caso A preservada (IPCA direto);
    juros normalizados para o modelo TST (TRD_SIMPLES + TAXA_LEGAL@ajuizamento)."""
    from modules.json_normalizer import normalize_v2_json
    payload = {
        "parametros_calculo": {
            "data_admissao": "10/04/2025",
            "data_demissao": "01/12/2025",
            "data_ajuizamento": "04/03/2026",
            "data_inicio_calculo": "10/04/2025",   # > 30/08/2024 ✓
            "data_termino_calculo": "01/12/2025",
        },
        "correcao_juros_multa": {
            "indice_trabalhista": "IPCA",
            "combinar_outro_indice": False,
            "juros": "TAXA_LEGAL",
            "juros_combinacoes": [],
        },
        "historico_salarial": [], "verbas_principais": [], "honorarios": [],
    }
    res = normalize_v2_json(payload)
    cjm = res["correcao_juros_multa"]
    # Caso A: CORREÇÃO preservada (IPCA direto, sem combinação de índice)
    assert cjm["indice_trabalhista"] == "IPCA"
    assert cjm["combinar_outro_indice"] is False
    # JUROS (fix THAÍS 10/06/2026): fase 1 TRD_SIMPLES + TAXA_LEGAL a partir
    # do ajuizamento — TAXA_LEGAL "seca" na fase 1 aplicaria taxa legal desde
    # o VENCIMENTO (fase pré-judicial), majorando juros indevidamente.
    assert cjm["juros"] == "TRD_SIMPLES"
    combs = cjm.get("juros_combinacoes") or []
    assert len(combs) == 1
    assert combs[0]["tabela"] == "TAXA_LEGAL"
    assert combs[0]["data_inicio"] == "04/03/2026"


def test_inv17_prompt_orienta_verificar_ambas_condicoes():
    """Prompt interno deve enfatizar que Caso A exige AMBAS as condições simultaneamente."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    # Aviso explícito da verificação dupla
    assert "AMBAS" in ext and "simultaneamente" in ext
    # Erro recorrente documentado
    assert "ERRO RECORRENTE" in ext
    # Exemplo concreto ALINE
    assert "ALINE" in ext


def test_inv13_extraction_explica_quantidade_pct_como_multiplicador():
    """Prompt interno deve explicar quantidade_pct como MULTIPLICADOR (1.0=100%),
    NÃO como percentual 0–100 (100.0=100%). Evita interpretação errada como 100× SM.
    """
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "MULTIPLICADOR" in ext
    assert "1.0` = 100%" in ext or "1.0 = 100%" in ext
    assert "NUNCA emitir 100.0" in ext
    # E exemplo correto está com 1.0 (não 100.0)
    assert '"quantidade_pct": 1.0' in ext


# ─── Marker: regressão de mudança Sobrescrever pós-params ──────────────────


def test_marker_sobrescrever_pos_params_condicional_periodo_curto():
    """Evolução da regra (fix THAÍS 10/06/2026, SALÁRIO RETIDO):

    - 312839e (revertido ac0c712): Sobrescrever UNIVERSAL pós-params →
      listagem vazia mid-loop. NÃO repetir o modo universal.
    - Fix atual: Sobrescrever CONDICIONAL — somente quando
      (a) o período da verba é subconjunto ESTRITO do cálculo
          (_verba_periodo_curto) E
      (b) nenhuma ocorrência foi editada ainda (_ocorrencias_editadas False —
          Regerar é global e apagaria valorDevido de verbas INFORMADO), com
      (c) re-anchor da listagem pós-Sobrescrever (salvaguarda contra a
          regressão "listagem vazia mid-loop" do 312839e).
    """
    assert "_verba_periodo_curto" in PLAYWRIGHT_V2
    assert "_ocorrencias_editadas" in PLAYWRIGHT_V2
    # Condicional aplicado no Regerar pós-parâmetros
    assert "self._verba_periodo_curto(v)" in PLAYWRIGHT_V2
    assert 'not getattr(self, "_ocorrencias_editadas", False)' in PLAYWRIGHT_V2
    # Salvaguarda re-anchor pós-Sobrescrever documentando 312839e
    assert "312839e" in PLAYWRIGHT_V2
    assert "_regerar_com_modal_confirmacao" in PLAYWRIGHT_V2


# ─── INV-18: alias valor_mensal → valor (QuantidadeVerba) ───────────────────


def test_inv18_quantidade_aceita_valor_mensal_como_alias():
    """Bug THAÍS (10/06/2026): prompt ensinava `valor_mensal`, schema só lia
    `valor` (default 1.0) → quantidade 20 do SALDO DE SALÁRIO virou 1
    silenciosamente (R$ 1.614,79 → R$ 53,83 na liquidação).
    """
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location(
        "pyd_models", str(REPO_ROOT / "docs" / "schema-v2" / "99-pydantic-models.py")
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    q = mod.QuantidadeVerba.model_validate(
        {"tipo": "INFORMADA", "valor_mensal": 20.0, "proporcionalizar": False}
    )
    assert q.valor == 20.0, f"valor_mensal=20 deve mapear para valor=20, got {q.valor}"
    # `valor` explícito tem precedência sobre o alias
    q2 = mod.QuantidadeVerba.model_validate(
        {"tipo": "INFORMADA", "valor": 5.0, "valor_mensal": 20.0}
    )
    assert q2.valor == 5.0


def test_inv18_prompt_usa_campo_valor_canonico():
    """Exemplos do prompt devem usar `valor` (canônico), não `valor_mensal`,
    em quantidade INFORMADA."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert '"quantidade": {"tipo": "INFORMADA", "valor_mensal"' not in ext
    assert 'preencher `valor`' in ext


# ─── INV-19: template prévia usa campos CANÔNICOS de juros ──────────────────


def test_inv19_template_previa_campos_canonicos_juros():
    """Bug THAÍS (10/06/2026): template gravava juros em campos-alias
    (juros_mora, aplicar_juros_pre_judicial, segundo_indice...) que o bot
    NÃO lê → edições do usuário na prévia eram ignoradas pela automação.
    """
    tpl = (REPO_ROOT / "templates" / "previa_v2.html").read_text(encoding="utf-8")
    # Canônicos presentes
    assert 'data-campo="correcao_juros_multa.juros"' in tpl
    assert 'data-campo="correcao_juros_multa.aplicar_juros_fase_pre_judicial"' in tpl
    assert 'data-campo="correcao_juros_multa.indice_combinado"' in tpl
    assert 'data-campo="correcao_juros_multa.data_inicio_combinacao"' in tpl
    assert 'data-campo="correcao_juros_multa.combinar_outro_indice"' in tpl
    # Aliases proibidos como data-campo
    assert 'data-campo="correcao_juros_multa.juros_mora"' not in tpl
    assert 'data-campo="correcao_juros_multa.aplicar_juros_pre_judicial"' not in tpl
    assert 'data-campo="correcao_juros_multa.segundo_indice"' not in tpl
    assert 'data-campo="correcao_juros_multa.combinar_a_partir_de"' not in tpl
    # base_juros_verbas com values do schema (não VERBAS_MENOS_CS)
    assert 'value="VERBA_INSS"' in tpl
    assert 'value="VERBAS_MENOS_CS"' not in tpl
    # Sync canônico juros_combinacoes presente
    assert "sincronizarJurosCombinacoes" in tpl


# ─── INV-20: modelo TST de juros (TRD fase 1) no prompt e no bot ────────────


def test_inv20_prompt_juros_trd_fase1_taxa_legal_ajuizamento():
    """Fix THAÍS (10/06/2026, supersede 587f862): fase 1 (pré-judicial) =
    TRD_SIMPLES (art. 39 caput Lei 8.177); TAXA_LEGAL entra como combinação
    a partir do AJUIZAMENTO. TAXA_LEGAL 'seca' na fase 1 aplicava taxa legal
    desde o vencimento — juros majorados indevidamente.
    """
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "TRD_SIMPLES" in ext
    assert 'NUNCA `TAXA_LEGAL` na fase 1' in ext
    # Exemplo Caso A com combinação TAXA_LEGAL@ajuizamento
    assert '"juros": "TRD_SIMPLES"' in ext


def test_inv20_bot_mapeia_trd_simples():
    """_JUROS_MAP do bot deve mapear TRD_SIMPLES/TRD_COMPOSTOS/SEM_JUROS
    (enum DOM confirmado via PJC THAÍS: <juros>TRD_SIMPLES</juros>)."""
    assert '"TRD_SIMPLES": "TRD_SIMPLES"' in PLAYWRIGHT_V2
    assert '"TRD_COMPOSTOS": "TRD_COMPOSTOS"' in PLAYWRIGHT_V2
    assert '"SEM_JUROS": "SEM_JUROS"' in PLAYWRIGHT_V2


# ─── INV-21: fração deferida limita o período da verba (13º) ────────────────


def test_inv21_prompt_fracao_deferida_limita_periodo():
    """Bug THAÍS (10/06/2026): sentença deferiu APENAS 2/12 de 13º/2025
    (R$ 403,70); IA emitiu período do contrato inteiro → PJE-Calc liquidou
    7/12+12/12+2/12 = R$ 4.238,83 (R$ 3.835,13 a maior que o título)."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "FRAÇÃO DEFERIDA" in ext
    assert "MENOR período que gera exatamente os avos" in ext
    assert "THAÍS" in ext


# ─── INV-22..25: fixes do caso RODRIGO (0000447-51, 11/06/2026) ─────────────


def test_inv22_bot_sem_fallback_jg_auto_detectado():
    """Bug RODRIGO: fallback 'JG auto-detectado' assumia que o DEVEDOR dos
    sucumbenciais era beneficiário da JG (sem consultar justica_gratuita) →
    comentário 'parte reclamado ... beneficiária da JG' sem deferimento.
    O bot deve aplicar APENAS pc.comentarios_jg da prévia (síntese é do
    normalizer — fidelidade prévia↔automação)."""
    assert "JG auto-detectado" not in PLAYWRIGHT_V2
    # Invariante documentado no lugar do fallback
    assert "comentarios_jg=None na prévia significa" in PLAYWRIGHT_V2


def test_inv23_combinacoes_fase13_verificadas_contra_listagem():
    """Bug RODRIGO: log '✓ click add' mas bean recebia o DEFAULT do select
    (combinação juros persistida como SEM_JUROS; combinação de índice nem
    criada). Fase 13 deve usar _add_combinacao_verificada: data primeiro,
    select por último, verificação da dataTable renderizada + retry."""
    assert "_add_combinacao_verificada" in PLAYWRIGHT_V2
    assert "listagemJurosCombinados" in PLAYWRIGHT_V2
    assert "listagemIndicesCombinados" in PLAYWRIGHT_V2
    # O fluxo antigo (add sem verificação) não pode voltar
    assert PLAYWRIGHT_V2.count("self._clicar(\"addOutroJuros\")") <= 1
    assert "Sem Juros" in PLAYWRIGHT_V2  # remoção de linhas erradas


def test_inv24_base_juros_map_enum_real():
    """Bug RODRIGO: _BASE_JUROS_MAP mapeava para 'VERBA'/'VERBA_MENOS_CS' —
    values INEXISTENTES (timeout 30s). Enum real (BaseDeJurosDasVerbasEnum
    do JAR): VERBAS | VERBA_INSS | VERBA_INSS_PP."""
    assert '"VERBAS": "VERBAS"' in PLAYWRIGHT_V2
    assert '"VERBA_INSS": "VERBA_INSS"' in PLAYWRIGHT_V2
    assert '"VERBA_INSS_PP": "VERBA_INSS_PP"' in PLAYWRIGHT_V2
    assert '"VERBAS": "VERBA",' not in PLAYWRIGHT_V2


def test_inv25_normalizer_multa_467_vira_reflexos():
    """Bug RODRIGO: IA emitiu MULTA 467 como verba principal autônoma
    (expresso_alvo=MULTA 477 + mult 0.5) → Expresso não criou, reflexos
    todos inativos, multa FALTOU. Normalizer converte em reflexos
    checkbox_painel + fgts.multa_artigo_467=true."""
    from modules.json_normalizer import normalize_v2_json
    payload = {
        "verbas_principais": [
            {"id": "v01", "nome_pjecalc": "SALDO DE SALÁRIO",
             "expresso_alvo": "SALDO DE SALÁRIO", "reflexos": []},
            {"id": "v05", "nome_pjecalc": "MULTA DO ARTIGO 467 DA CLT",
             "expresso_alvo": "MULTA DO ARTIGO 477 DA CLT", "reflexos": []},
            {"id": "v06", "nome_pjecalc": "MULTA DO ARTIGO 477 DA CLT",
             "expresso_alvo": "MULTA DO ARTIGO 477 DA CLT", "reflexos": []},
        ],
        "fgts": {"multa_artigo_467": False},
        "historico_salarial": [], "honorarios": [],
    }
    res = normalize_v2_json(payload)
    nomes = [v["nome_pjecalc"] for v in res["verbas_principais"]]
    assert "MULTA DO ARTIGO 467 DA CLT" not in nomes, "verba 467 autônoma deve ser removida"
    assert "MULTA DO ARTIGO 477 DA CLT" in nomes, "477 deve ser preservada"
    saldo = next(v for v in res["verbas_principais"] if v["nome_pjecalc"] == "SALDO DE SALÁRIO")
    alvos = [r["expresso_reflex_alvo"] for r in saldo["reflexos"]]
    assert "MULTA DO ARTIGO 467 DA CLT SOBRE SALDO DE SALÁRIO" in alvos
    multa477 = next(v for v in res["verbas_principais"] if v["nome_pjecalc"] == "MULTA DO ARTIGO 477 DA CLT")
    assert multa477["reflexos"] == [], "467 NÃO incide sobre a 477"
    assert res["fgts"]["multa_artigo_467"] is True


def test_inv25_prompt_multa_467_nunca_verba_autonoma():
    """Prompt deve conter a regra: MULTA 467 NUNCA é verba principal."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "MULTA DO ART. 467 DA CLT (INVARIANTE PERMANENTE" in ext
    assert "NUNCA é verba principal" in ext
    assert "MULTA DO ARTIGO 467 DA CLT SOBRE" in ext


def test_inv26_reflexo_espelha_carac_ocorrencia_submit_unico():
    """Bug RODRIGO v18/v19 (12/06/2026): reflexo 467 sobre 13º multi-ano
    cobria só o avo do ano da rescisão (506,00 em vez de 1.201,75). A
    correção exige característica+ocorrência do reflexo ESPELHADAS da
    principal NUM ÚNICO SUBMIT: o a4j:support de cada radio valida o form
    intermediário e o servidor REJEITA ('verbas ... incompatíveis com a
    característica/ocorrência'), revertendo — DECIMO_TERCEIRO+DEZEMBRO é
    inalcançável por cliques sequenciais. Marcar via JS checked sem
    onchange; o Salvar full-form valida a combinação final e persiste."""
    assert "_ajustar_periodo_reflexo" in PLAYWRIGHT_V2
    # espelhamento em submit único via JS (NÃO _marcar_radio sequencial)
    assert "caracteristicaVerba" in PLAYWRIGHT_V2
    assert "submit único" in PLAYWRIGHT_V2 or "submit unico" in PLAYWRIGHT_V2
    assert "inalcançável por cliques" in PLAYWRIGHT_V2
    # o bloco JS marca ambos sem disparar onchange
    assert "r.checked = want" in PLAYWRIGHT_V2
    # NÃO regredir para clique sequencial no radio do reflexo
    sec = PLAYWRIGHT_V2.split("def _ajustar_periodo_reflexo")[1].split("\n    def ")[0]
    assert '_marcar_radio_se_diferente("ocorrenciaPagto"' not in sec, (
        "clique sequencial no radio do reflexo é rejeitado pelo servidor "
        "(validação de combinação) — usar o espelhamento JS em submit único"
    )
    # a correção via grade NÃO deve voltar (inputs de CALCULADO ficam vazios)
    assert "_corrigir_valor_reflexo_na_grade(verba_principal" not in sec, (
        "edição via grade é inviável p/ verba CALCULADO (dump v17: inputs vazios)"
    )


def test_inv27_seguro_desemprego_so_indenizacao_substitutiva():
    """Regra do usuário (12/06/2026): seguro-desemprego NÃO é apurado quando
    a sentença determina apenas habilitação no programa / expedição de
    ordem / entrega das guias — não há condenação pecuniária (o benefício
    é pago pelo órgão gestor, fora da liquidação). Apurar SOMENTE quando
    houver INDENIZAÇÃO SUBSTITUTIVA (conversão do benefício em dinheiro).
    Caso de origem: sentença THAÍS 0000183-68 ('expedição de ordem judicial
    para a habilitação da obreira no programa do seguro-desemprego')."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "INDENIZAÇÃO SUBSTITUTIVA" in ext
    assert "habilitação" in ext and "entrega das guias" in ext
    assert '`"seguro_desemprego": null`' in ext
    # a regra antiga ("reconhecer direito ao SD") não pode voltar
    assert "Preencher quando a sentença reconhecer direito ao SD" not in ext


def test_inv28_doc_fiscal_ausente_vira_string_vazia():
    """Caso Ariane (12/06/2026, extração in-app): sentença sem CPF/CNPJ das
    partes → IA emitia doc_fiscal.numero=null e a Etapa 2 travava na
    validação Pydantic. Documento ausente deve virar "" (completável na
    prévia), nunca bloquear o fluxo."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_models_inv28", str(REPO_ROOT / "docs" / "schema-v2" / "99-pydantic-models.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    df = mod.DocumentoFiscal.model_validate({"tipo": "CPF", "numero": None})
    assert df.numero == ""
    df2 = mod.DocumentoFiscal.model_validate({"tipo": "CNPJ", "numero": "32.567.442/0001-00"})
    assert df2.numero == "32.567.442/0001-00"
    # prompt instrui "" + aviso
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "NUNCA null" in ext and "OPCIONAL no PJE-Calc" in ext


def test_inv29_bot_nao_exige_cpf_cnpj_das_partes():
    """Caso Ariane (13/06/2026): CPF/CNPJ das partes vazio abortava a Fase 1
    ('Campo obrigatório vazio: reclamanteNumeroDocumentoFiscal') e cascateava
    (Dados do Processo não salvava → históricos/verbas CALCULADO perdidos →
    PJC só com a verba INFORMADA). O PJE-Calc NÃO exige documento fiscal das
    partes (manual: obrigatório só p/ credor de honorários). O bot deve pular
    radio + número quando o documento está vazio, sem abortar."""
    src = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    # bloco condicional que só preenche doc quando presente
    assert 'if (proc.reclamante.doc_fiscal.numero or "").strip():' in src
    assert 'if (proc.reclamado.doc_fiscal.numero or "").strip():' in src
    assert "PJE-Calc não exige; seguindo sem documento" in src
    # marcar_radio do documento DENTRO do if (12 espaços), nunca incondicional
    assert '            self._marcar_radio("documentoFiscalReclamante"' in src


def test_inv30_salario_por_fora_parcela_direta():
    """Caso Ariane #65 (14/06/2026, validado contra cálculo MANUAL 263753):
    salário por fora = DIFERENÇA SALARIAL com a PARCELA EXTRAFOLHA DIRETA
    (base = histórico 'SALÁRIO PAGO POR FORA' = o valor da parcela; valor_pago
    INFORMADO 0; divisor 1, mult 1, qtd 1; compor=NAO). PROIBIDO o modelo
    devido(SALÁRIO TOTAL) − pago(SALÁRIO REGISTRADO): o net dá a diferença mas
    a verba carrega o devido BRUTO e o reflexo de FÉRIAS lê o bruto e infla 30×.
    Comprovado: planilha manual 263753, FÉRIAS reflexo = R$ 11.742 (correto)."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "263753" in ext  # referência do cálculo manual
    assert "parcela extrafolha DIRETO" in ext or "parcela por fora" in ext
    assert '`valor_pago: {tipo: INFORMADO, valor_brl: 0.0}`' in ext
    assert "infla 30" in ext or "infla **30" in ext
    # proíbe o modelo antigo (total − registrado)
    assert "NUNCA" in ext and "SALÁRIO TOTAL" in ext and "SALÁRIO REGISTRADO" in ext


def test_inv31_bot_fallback_reflexo_manual_quando_sem_checkbox():
    """Defesa em profundidade (#64): quando o checkbox candidato do reflexo
    NUNCA aparece no painel 'Exibir', o bot deve criar o reflexo como Manual
    (em vez de desistir). Só dispara quando cb_visto=False — não afeta o fluxo
    Expresso-pareado (RODRIGO) onde o checkbox aparece e o retry trata."""
    src = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    assert "cb_visto = False" in src
    assert "cb_visto = True" in src
    # fallback condicionado a cb_visto False
    sec = src.split("def _configurar_reflexo")[1].split("\n    def ")[0]
    assert "if not cb_visto:" in sec
    assert "_criar_reflexo_manual(verba_principal, reflexo)" in sec
    assert "fallback: criando como reflexo Manual" in sec


def test_inv32_valor_pago_calculado_aceita_valor_brl_null():
    """Caso Ariane DIFERENÇA SALARIAL (13/06/2026): valor_pago CALCULADO (base
    sobre histórico) emite valor_brl=null — o valor é apurado pelo PJE-Calc a
    partir do histórico, não digitado. O schema travava (valor_brl: float
    obrigatório), bloqueando a estratégia canônica. Validator coerce None→0.0;
    INFORMADO preserva o valor."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_m_inv32", str(REPO_ROOT / "docs" / "schema-v2" / "99-pydantic-models.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    vp = m.ValorPagoVerba.model_validate(
        {"tipo": "CALCULADO", "base_tipo": "HISTORICO_SALARIAL",
         "base_historico_nome": "SALÁRIO REGISTRADO", "valor_brl": None})
    assert vp.valor_brl == 0.0
    vp2 = m.ValorPagoVerba.model_validate({"tipo": "INFORMADO", "valor_brl": 1091.10})
    assert vp2.valor_brl == 1091.10


def test_inv33_match_reflexo_tolerante_ao_rename_da_verba():
    """Caso Ariane #64 (13/06/2026): o PJE-Calc rotula o reflexo candidato no
    painel com o nome ORIGINAL do Expresso da verba (ex.: 'FÉRIAS + 1/3 SOBRE
    DIFERENÇA SALARIAL'), não com o nome_pjecalc renomeado ('... — SALÁRIO
    EXTRAFOLHA'). O match do checkbox deve aceitar MÚLTIPLOS candidatos:
    o alvo completo + '{tipo} SOBRE {expresso_alvo}' + '{tipo} SOBRE
    {nome_pjecalc}' — senão o includes() falha e cai no fallback Manual
    (base errada)."""
    src = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    sec = src.split("def _configurar_reflexo")[1].split("\n    def ")[0]
    assert "alvo_cands" in sec
    assert "expresso_alvo" in sec and "rindex(\" SOBRE \")" in sec
    # o JS deve casar por qualquer candidato
    assert "cands.some(c => txt.includes(c))" in sec


def test_inv34_saldo_informado_quando_fixado_deducao_ou_por_fora():
    """Caso Ariane #65 (14/06/2026, sentença 0000566-12 item g): SALDO DE
    SALÁRIO CALCULADO com base composta (registrado + por fora) e/ou valor pago
    a deduzir (ConPag) liquida ERRADO — a ocorrência única do DESLIGAMENTO
    resolve a base só pelo histórico secundário (R$ 1.800 em vez de R$ 7.075 →
    saldo R$ 480 em vez de R$ 1.886,67) e não regenera com divisor/quantidade
    do parâmetro. Regra: emitir SALDO como INFORMADO (valor_devido = bruto
    fixado na sentença; valor_pago INFORMADO = depósito) → roteia pelo fluxo
    Manual estável. Saldo CALCULADO simples (single histórico, sem dedução)
    permanece válido."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "4.4.quater" in ext
    assert "0000566-12" in ext  # caso documentado
    assert "1.886,67" in ext  # valor bruto faithful à sentença
    # os 3 gatilhos da exceção INFORMADO
    assert "fixa o valor bruto" in ext
    assert "salário pago por fora" in ext
    # não quebra o saldo CALCULADO simples
    assert "Saldo CALCULADO simples" in ext


def test_inv35_so_verbas_efetivamente_deferidas():
    """Caso Ariane #68 (15/06/2026): a extração é não-determinística numa
    armadilha — fundamentação cita 'férias vencidas + 1/3 se não pagas' (item
    49) mas o parágrafo seguinte (item 50) diz que NÃO havia (todas fruídas), e
    o dispositivo julga improcedentes férias proporcionais/13º (justa causa).
    A IA chegou a alucinar FÉRIAS+1/3 e 13º standalone, inflando o cálculo.
    Invariante: lançar SÓ verbas efetivamente deferidas no dispositivo; verba
    mencionada e depois negada/inexistente NÃO vira verba; reflexo ≠ verba
    autônoma."""
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "SÓ VERBAS EFETIVAMENTE DEFERIDAS" in ext
    assert "MENCIONA como potencialmente devida e em" in ext
    # caso concreto da armadilha (trecho contíguo, tolerante a quebra de linha)
    assert "férias vencidas pendentes" in ext.lower()
    assert "regularmente fruídos" in ext.lower()
    # reflexo não é verba autônoma
    assert "Reflexo ≠ verba autônoma" in ext
    # dispositivo é a fonte da verdade
    assert "DISPOSITIVO" in ext and "improcedente" in ext.lower()
    # regra consolidada de justa causa (Súmula 171) — gatilho que a IA perdia
    assert "MODALIDADE DA RESCISÃO" in ext
    assert "Súmula 171" in ext
    assert "férias VENCIDAS" in ext and "férias PROPORCIONAIS" in ext


def test_inv36_justa_causa_safeguard_deterministico():
    """Caso Ariane #68 (15/06/2026): o prompt sozinho não zera a alucinação de
    rescisórias indevidas na justa causa (~25% erram). Safeguard determinístico:
    (a) campo modalidade_rescisao extraído; (b) normalizer AUTO-remove o
    inequivocamente indevido (aviso/40%FGTS/saque/seguro); (c) FÉRIAS/13º NÃO
    são removidos (vencidas podem ser devidas) — só preservados. Sem
    modalidade → nenhuma remoção (retrocompatível)."""
    from modules.json_normalizer import normalize_v2_json

    def _mk(mod):
        return {
            "parametros_calculo": {
                "estado_uf": "CE", "municipio": "X",
                "data_admissao": "01/11/2021", "data_demissao": "08/04/2026",
                "data_ajuizamento": "20/04/2026",
                "data_inicio_calculo": "01/11/2021",
                "data_termino_calculo": "08/04/2026",
                "modalidade_rescisao": mod,
            },
            "verbas_principais": [
                {"id": "v1", "nome_pjecalc": "SALDO DE SALÁRIO", "parametros": {}},
                {"id": "v2", "nome_pjecalc": "AVISO PRÉVIO INDENIZADO", "parametros": {}},
                {"id": "v3", "nome_pjecalc": "MULTA DE 40% DO FGTS", "parametros": {}},
                {"id": "v4", "nome_pjecalc": "SEGURO-DESEMPREGO", "parametros": {}},
                {"id": "v5", "nome_pjecalc": "FÉRIAS + 1/3", "parametros": {}},
                {"id": "v6", "nome_pjecalc": "MULTA DO ARTIGO 477 DA CLT", "parametros": {}},
            ],
        }

    jc = [v["nome_pjecalc"] for v in normalize_v2_json(_mk("justa_causa"))["verbas_principais"]]
    assert "AVISO PRÉVIO INDENIZADO" not in jc  # auto-removido
    assert "MULTA DE 40% DO FGTS" not in jc
    assert "SEGURO-DESEMPREGO" not in jc
    assert "FÉRIAS + 1/3" in jc  # NÃO remove (vencidas) — só FLAG no schema
    assert "MULTA DO ARTIGO 477 DA CLT" in jc  # 477 devida se não paga no prazo
    assert "SALDO DE SALÁRIO" in jc

    # sem_justa_causa → preserva tudo (rescisórias devidas)
    sjc = [v["nome_pjecalc"] for v in normalize_v2_json(_mk("sem_justa_causa"))["verbas_principais"]]
    assert "AVISO PRÉVIO INDENIZADO" in sjc and len(sjc) == 6

    # prompt instrui o campo + schema tem o campo
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "modalidade_rescisao" in ext
    assert "manteve a justa causa" in ext  # caso 'pediu indireta mas negada'
    sch = (REPO_ROOT / "docs" / "schema-v2" / "99-pydantic-models.py").read_text(encoding="utf-8")
    assert "modalidade_rescisao" in sch
    assert "Súmula 171 TST" in sch  # FLAG de revisão no validator


def test_inv37_fallback_manual_verba_expresso_nao_marcada():
    """#5 (VALOR PAGO NÃO TRIBUTÁVEL / verba Expresso não-marcada): quando uma
    verba Expresso não pode ser marcada (página vazia mesmo após F+R, ou alvo
    ausente da grade), ela DEVE ir para o fluxo Manual em vez de ser perdida
    silenciosamente (faltaria na liquidação). Mesmo padrão de inv8 (reroute
    INFORMADO+DESLIGAMENTO) e inv31 (reflexo sem checkbox → Manual)."""
    src = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    # acumulador de verbas não-marcadas
    assert "_verbas_expresso_falhadas" in src
    # batch: total_cbs==0 e naoEncontradas alimentam o acumulador
    assert "naoEncontradasIdx" in src
    # fase_verbas cria as falhadas via Manual e as remove do loop de parâmetros
    sec = src.split("def fase_verbas")[1].split("\n    def ")[0]
    assert "_verbas_expresso_falhadas" in sec
    assert "_lancar_verba_manual(v)" in sec
    assert "v.id not in _ids_falhadas" in sec


def test_inv38_fgts_por_fora_so_parcela_extrafolha():
    """#69 (Ariane, auditoria PJC 16/06/2026): no salário por fora o FGTS é
    deferido SÓ sobre a parcela extrafolha (item d); o FGTS do registrado já foi
    depositado. A IA invertia (registrado fgts=true, por fora=false) → FGTS sobre
    5.275 (R$ 21.254) em vez de sobre 1.800 (~R$ 7.776). Normalizer força: por
    fora=true, demais salariais=false; cs_inss preservado; sem histórico por
    fora não mexe."""
    from modules.json_normalizer import normalize_v2_json
    base = {
        "parametros_calculo": {
            "estado_uf": "CE", "municipio": "X",
            "data_admissao": "01/11/2021", "data_demissao": "08/04/2026",
            "data_ajuizamento": "20/04/2026",
            "data_inicio_calculo": "01/11/2021", "data_termino_calculo": "08/04/2026",
        },
        "historico_salarial": [
            {"nome": "SALÁRIO REGISTRADO", "incidencias": {"fgts": True, "cs_inss": True}},
            {"nome": "SALÁRIO PAGO POR FORA", "incidencias": {"fgts": False, "cs_inss": True}},
            {"nome": "ÚLTIMA REMUNERAÇÃO", "incidencias": {"fgts": True, "cs_inss": True}},
        ],
    }
    out = normalize_v2_json(base)
    inc = {h["nome"]: h["incidencias"] for h in out["historico_salarial"]}
    assert inc["SALÁRIO PAGO POR FORA"]["fgts"] is True
    assert inc["SALÁRIO REGISTRADO"]["fgts"] is False
    assert inc["ÚLTIMA REMUNERAÇÃO"]["fgts"] is False
    assert all(h["incidencias"]["cs_inss"] for h in out["historico_salarial"])  # INSS preservado
    # sem histórico por fora → não generaliza
    base2 = {"parametros_calculo": base["parametros_calculo"],
             "historico_salarial": [{"nome": "SALÁRIO BASE", "incidencias": {"fgts": True, "cs_inss": True}}]}
    assert normalize_v2_json(base2)["historico_salarial"][0]["incidencias"]["fgts"] is True
    # prompt instrui a regra
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "incidência SÓ sobre a parcela por fora" in ext
    assert "FGTS já recolhido" in ext or "FGTS já depositado" in ext


def test_inv39_retry_config_verba_execution_context_destroyed():
    """#71 (processo 0000610-31, 17/06/2026): a config de uma verba podia
    falhar com 'Execution context was destroyed' (page.evaluate corre contra a
    navegação Seam do sidebar click ainda em curso). ANTES o bot só logava e
    PULAVA para a próxima verba → a verba ficava sem base (13º CALCULADO sem
    histórico → liquidação bloqueada). Invariante: retry com re-anchor (até 3×)
    na config de verba; e wait_for_load_state após o sidebar click no helper."""
    src = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    # retry no loop de verbas
    assert "FIX #71" in src
    assert "_cfg_ok" in src
    assert "tentativa {_tent}/3" in src
    assert "NÃO configurada" in src and "pode liquidar sem base" in src
    # re-anchor + espera de navegação no helper
    assert 'wait_for_load_state(\n                "domcontentloaded"' in src or \
        'wait_for_load_state("domcontentloaded", timeout=8000)' in src


def test_inv40_13_proporcional_ano_rescisao_desligamento():
    """#72 (LUCAS 0000610-31): 13º proporcional do ano da rescisão com período
    SEM dezembro + ocorrencia=DEZEMBRO → ocorrência cai fora do período →
    liquidação travada ('ocorrências devem estar contidas no período'). Fix:
    normalizer troca para DESLIGAMENTO. 13º multi-ano (cruza dezembros) fica
    intocado. Prompt instrui a distinção."""
    from modules.json_normalizer import normalize_v2_json
    pc = {"estado_uf": "CE", "municipio": "X", "data_admissao": "13/01/2025",
          "data_demissao": "25/04/2026", "data_ajuizamento": "01/05/2026",
          "data_inicio_calculo": "13/01/2025", "data_termino_calculo": "25/05/2026"}

    def _13(pi, pf):
        return {"parametros_calculo": pc, "verbas_principais": [
            {"id": "v", "nome_pjecalc": "13º SALÁRIO", "parametros": {
                "caracteristica": "DECIMO_TERCEIRO_SALARIO",
                "ocorrencia_pagamento": "DEZEMBRO",
                "periodo_inicio": pi, "periodo_fim": pf}}]}

    # proporcional do ano da rescisão (sem dezembro) com CONTRATO multi-ano que
    # cruza dezembro → período expandido ao contrato + DEZEMBRO nativo (ver
    # inv42 para a janela). NÃO mais DESLIGAMENTO (aquela tentativa não movia a
    # ocorrência; ver task #72).
    p1 = normalize_v2_json(_13("01/01/2026", "25/04/2026"))["verbas_principais"][0]["parametros"]
    assert p1["ocorrencia_pagamento"] == "DEZEMBRO"
    assert p1["periodo_inicio"] == "13/01/2025"  # contrato
    # multi-ano (período já cruza dezembros) → preservado
    o2 = normalize_v2_json(_13("01/01/2024", "25/04/2026"))["verbas_principais"][0]["parametros"]["ocorrencia_pagamento"]
    assert o2 == "DEZEMBRO"
    # ano completo (tem dezembro) → preservado
    o3 = normalize_v2_json(_13("01/01/2025", "31/12/2025"))["verbas_principais"][0]["parametros"]["ocorrencia_pagamento"]
    assert o3 == "DEZEMBRO"


def test_inv41_regerar_final_sobrescrever_REVERTIDO():
    """#72 (LUCAS 0000610-31): a tentativa de SOBRESCREVER no Regerar final
    (quando há CALCULADO período-curto) foi REVERTIDA — validado em 3 runs que
    NÃO resolve o 13º proporcional do ano da rescisão (a característica
    DECIMO_TERCEIRO_SALARIO força a ocorrência para dezembro independentemente
    do Sobrescrever; o erro 'ocorrências devem estar contidas no período'
    persiste). O Sobrescrever global ainda regrediria RODRIGO 13º multi-ano
    (inv26). Mantido Manter (sem argumento). Invariante: o Regerar final NÃO
    pode passar sobrescrever=True condicional por CALCULADO período-curto."""
    src = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    # o gatilho condicional foi removido
    assert "_sobrescrever_final = any(" not in src
    assert "_regerar_ocorrencias_verbas(sobrescrever=_sobrescrever_final)" not in src
    # marcador do revert presente
    assert "REVERTIDO #72 (inv41" in src
    # o helper preserva o parâmetro (default False — sem mudança de comportamento)
    assert "def _regerar_ocorrencias_verbas(self, sobrescrever: bool = False)" in src


def test_inv42_13_proporcional_periodo_contrato_mais_janela():
    """#72 (LUCAS, orientação do usuário validada em run real): 13º proporcional
    do ano da rescisão deve apurar NATIVAMENTE — período expandido ao contrato
    (para a ocorrência cair num dezembro válido) + JANELA de ocorrências
    deferidas, e o bot DESATIVA as ocorrências de anos pagos fora da janela."""
    from modules.json_normalizer import normalize_v2_json
    pc = {"estado_uf": "CE", "municipio": "X", "data_admissao": "13/01/2025",
          "data_demissao": "25/04/2026", "data_ajuizamento": "01/05/2026",
          "data_inicio_calculo": "13/01/2025", "data_termino_calculo": "25/05/2026"}
    base = {"parametros_calculo": pc, "verbas_principais": [
        {"id": "v", "nome_pjecalc": "13º SALÁRIO", "parametros": {
            "caracteristica": "DECIMO_TERCEIRO_SALARIO", "ocorrencia_pagamento": "DEZEMBRO",
            "periodo_inicio": "01/01/2026", "periodo_fim": "25/04/2026"}}]}
    p = normalize_v2_json(base)["verbas_principais"][0]["parametros"]
    # período expandido ao contrato; janela = período deferido original; DEZEMBRO nativo
    assert p["periodo_inicio"] == "13/01/2025" and p["periodo_fim"] == "25/04/2026"
    assert p["janela_ocorrencias_inicio"] == "01/01/2026"
    assert p["janela_ocorrencias_fim"] == "25/04/2026"
    assert p["ocorrencia_pagamento"] == "DEZEMBRO"
    # contrato de ano único (sem dezembro em lugar nenhum) → fallback DESLIGAMENTO
    pc2 = dict(pc, data_admissao="01/02/2026", data_inicio_calculo="01/02/2026")
    base2 = {"parametros_calculo": pc2, "verbas_principais": [
        {"id": "v", "nome_pjecalc": "13º SALÁRIO", "parametros": {
            "caracteristica": "DECIMO_TERCEIRO_SALARIO", "ocorrencia_pagamento": "DEZEMBRO",
            "periodo_inicio": "01/02/2026", "periodo_fim": "25/04/2026"}}]}
    p2 = normalize_v2_json(base2)["verbas_principais"][0]["parametros"]
    assert p2["ocorrencia_pagamento"] == "DESLIGAMENTO"
    assert p2.get("janela_ocorrencias_inicio") is None
    # bot tem o método de filtro por janela
    src = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    assert "def _filtrar_ocorrencias_por_janela" in src
    assert "janela_ocorrencias_inicio" in src
    assert "_filtrar_ocorrencias_por_janela(_v)" in src


def test_inv43_loop_manual_resiliente_e_guard_anti_fantasma():
    """#73 (ONASSES 0000495-10, 18/06/2026): o loop de verbas Manual NÃO pode
    abortar a fase inteira por 'Execution context destroyed' numa única verba,
    e o bot NUNCA pode exportar um PJC-fantasma (cálculo sem verbas) reportando
    sucesso.

    Bug observado em run real: 'Execution context was destroyed' no loop Manual
    (sem try/except) → fase de Verbas abortada → bot liquidou/exportou um PJC de
    ~6KB SEM nenhuma verba, marcando 'sucesso'.

    Fix A: retry+re-anchor 3× por verba no loop Manual (espelha #71).
    Fix B: guard em fase_liquidar_e_exportar — conta verbas listadas e aborta
    (return None) se esperadas>0 e listadas==0.
    """
    src = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")

    # Fix A — o loop Manual deve ter retry de 3 tentativas com re-anchor.
    idx_loop = src.find("# 4b. Manual (uma por vez)")
    assert idx_loop > 0, "bloco do loop Manual não encontrado"
    bloco = src[idx_loop:idx_loop + 2200]
    assert "FIX #73" in bloco, "marcador do fix #73 ausente do loop Manual"
    assert "for _tent in range(1, 4):" in bloco, "retry 3× ausente do loop Manual"
    assert "_lancar_verba_manual(v)" in bloco
    assert '_navegar_menu("li_calculo_verbas")' in bloco, "re-anchor ausente"

    # Fix B — guard anti-PJC-fantasma na liquidação.
    idx_liq = src.find("def fase_liquidar_e_exportar")
    assert idx_liq > 0
    guard = src[idx_liq:idx_liq + 3000]
    assert "GUARD anti-PJC-fantasma" in guard, "guard anti-fantasma ausente"
    assert "capturar_snapshot_listagem_verbas" in guard
    # esperadas>0 e listadas==0 → return None (não exporta)
    assert "verbas_principais" in guard
    assert "ABORTANDO liquida" in guard
    assert "return None" in guard

    # Fix C — _lancar_verba_manual deve garantir o botão 'incluir' (escalando
    # para Fechar+Reabrir) antes de cliná-lo. Após o save de uma verba Manual
    # anterior a conv Seam fica stale e 'incluir' some → as verbas Manual
    # seguintes eram perdidas (PJC incompleto).
    assert "def _garantir_incluir_disponivel" in src, "helper de restauração de 'incluir' ausente"
    idx_man = src.find("def _lancar_verba_manual")
    assert idx_man > 0
    man = src[idx_man:idx_man + 600]
    assert "_garantir_incluir_disponivel()" in man, "_lancar_verba_manual não chama o guard de 'incluir'"
    idx_g = src.find("def _garantir_incluir_disponivel")
    gblock = src[idx_g:idx_g + 7200]
    # causa raiz: restaurar 'incluir' exige CLIQUE no sidebar (Seam @Begin),
    # não url-goto; e escalar para F+R como último recurso.
    assert "_navegar_menu_via_click" in gblock, "guard de 'incluir' deve usar click sidebar (Seam init)"
    assert "_fechar_e_reabrir_calculo" in gblock, "guard de 'incluir' não escala para F+R"
    # após o save Manual, re-capturar o conversationId (muda a cada save)
    man_full = src[idx_man:idx_man + 3600]
    assert "_capturar_conversation_id()" in man_full, "_lancar_verba_manual não re-captura conv após save"


def test_inv44_honorarios_base_bruto_e_incluir_reancora():
    """#74b (ONASSES 0000495-10, 18/06/2026): a página de Honorários ficava
    VAZIA porque (a) baseParaApuracao é obrigatória p/ honorário CALCULADO e a
    IA não a extraía → save falhava com 'Campo obrigatório: Base para Apuração';
    (b) após o 1º honorário o botão 'incluir' sumia → 2º sucumbencial recíproco
    perdido.

    Fix A (normalizer): default base_para_apuracao=BRUTO p/ honorário CALCULADO.
    Fix B (bot): default BRUTO no _selecionar + re-ancorar a listagem
    (_navegar_menu li_calculo_honorarios) antes de CADA 'incluir'.
    """
    # Fix A — normalizer
    from modules.json_normalizer import _norm_honorario
    h = {"tipo_honorario": "SUCUMBENCIAIS", "tipo_devedor": "RECLAMADO",
         "tipo_valor": "CALCULADO", "aliquota_pct": 7.5, "base_para_apuracao": None}
    assert _norm_honorario(dict(h))["base_para_apuracao"] == "BRUTO"
    # não sobrescreve quando já informado
    h2 = dict(h, base_para_apuracao="BRUTO_MENOS_CONTRIBUICAO_SOCIAL")
    assert _norm_honorario(dict(h2))["base_para_apuracao"] == "BRUTO_MENOS_CONTRIBUICAO_SOCIAL"

    # Fix B — bot
    src = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    idx = src.find("def fase_honorarios")
    assert idx > 0
    bloco = src[idx:idx + 9500]
    # re-ancora a listagem antes de cada incluir (dentro do loop de honorários)
    assert bloco.count('_navegar_menu("li_calculo_honorarios")') >= 2, \
        "fase_honorarios deve re-ancorar a listagem antes de cada 'incluir'"
    # default BRUTO no preenchimento da base
    assert 'h.base_para_apuracao or "BRUTO"' in bloco, \
        "fase_honorarios deve usar default BRUTO na baseParaApuracao"


def test_inv45_cap_periodo_fim_na_demissao():
    """#75 (processo demissão 05/11/2025, 19/06/2026): o 13º (verba única
    multi-ano) ficava com periodo_fim = data_termino_calculo (07/12/2025, aviso
    projetado) + ocorrência DEZEMBRO → o validador (PreviaCalculoV2 Regra 1)
    marcava completude=INCOMPLETO ('ocorrência ≠ Mensal incompatível com
    periodo_fim POSTERIOR à demissão') e a AUTOMAÇÃO NÃO INICIAVA.

    Fix: normalizer capa periodo_fim em data_demissao para ocorrências
    NÃO-MENSAIS (DESLIGAMENTO/DEZEMBRO/PERIODO_AQUISITIVO), preservando AVISO
    PRÉVIO (projeção legal Lei 12.506/2011).
    """
    from modules.json_normalizer import normalize_v2_json
    base = {
        "parametros_calculo": {
            "estado_uf": "CE", "municipio": "FORTALEZA",
            "data_admissao": "30/04/2021", "data_demissao": "05/11/2025",
            "data_inicio_calculo": "30/04/2021", "data_termino_calculo": "07/12/2025",
        },
        "verbas_principais": [
            {"id": "v13", "nome_pjecalc": "13º SALÁRIO", "parametros": {
                "caracteristica": "DECIMO_TERCEIRO_SALARIO",
                "ocorrencia_pagamento": "DEZEMBRO",
                "periodo_inicio": "30/04/2021", "periodo_fim": "07/12/2025"}},
            {"id": "vap", "nome_pjecalc": "AVISO PRÉVIO", "expresso_alvo": "AVISO PRÉVIO",
             "parametros": {"caracteristica": "AVISO_PREVIO",
                "ocorrencia_pagamento": "DESLIGAMENTO",
                "periodo_inicio": "05/11/2025", "periodo_fim": "05/12/2025"}},
        ],
    }
    out = normalize_v2_json(base)
    vs = {v["nome_pjecalc"]: v["parametros"] for v in out["verbas_principais"]}
    # 13º capado na demissão
    assert vs["13º SALÁRIO"]["periodo_fim"] == "05/11/2025"
    # aviso prévio preservado (projeção legal)
    assert vs["AVISO PRÉVIO"]["periodo_fim"] == "05/12/2025"
    # a função existe e está encadeada no normalize
    src = (REPO_ROOT / "modules" / "json_normalizer.py").read_text(encoding="utf-8")
    assert "_norm_cap_periodo_fim_na_demissao(data)" in src


def test_inv46_dano_moral_expresso_nao_manual():
    """#76 (WASHINGTON 0000614-68, orientação do usuário 19/06/2026): a
    INDENIZAÇÃO POR DANO MORAL deve ser lançada via EXPRESSO (verba canônica
    CNJ 1855) + INFORMADO + DESLIGAMENTO — NÃO re-roteada para Manual (cujo save
    não persistia: Assunto CNJ via fallback-by-text + Seam FlushMode.MANUAL).
    Está na lista de exceção do reroute INFORMADO+DESLIGAMENTO."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    idx = pw.find("_VERBAS_EXPRESSO_DEFAULT_DESLIGAMENTO = {")
    assert idx > 0
    bloco = pw[idx:idx + 1200]
    assert "INDENIZAÇÃO POR DANO MORAL" in bloco, \
        "dano moral deve estar na exceção do reroute (lançar via Expresso)"


def test_inv47_previa_editor_evolucao_salarial():
    """#77 (L'Oreal 0001858-66, orientação do usuário 19/06/2026): a prévia deve
    permitir registrar UM histórico salarial com a EVOLUÇÃO do valor ao longo do
    contrato (faixas competência→valor), não históricos separados por faixa.
    Schema (HistoricoSalarial.evolucao) suporta; o editor na prévia registra a
    evolução. O bot aplica essa evolução nas OCORRÊNCIAS de 1 único histórico
    (#80-L, ver test_inv15)."""
    tpl = (REPO_ROOT / "templates" / "previa_v2.html").read_text(encoding="utf-8")
    # editor de faixas no card de histórico
    assert "Evolução salarial" in tpl
    assert "function adicionarFaixaEvolucao" in tpl
    assert "function removerFaixaEvolucao" in tpl
    assert "function _sincEvolucao" in tpl
    # grava no campo canônico do schema
    assert ".evolucao[" in tpl
    # o bot aplica a evolução nas ocorrências de 1 histórico (não expande em N)
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    assert "_aplicar_evolucao_ocorrencias_historico" in pw


def test_inv48_regerar_seleciona_verbas():
    """#76c (WASHINGTON, diag DOM): o PJE-Calc EXIGE ≥1 verba selecionada antes
    do Regerar Ocorrências ('É necessário selecionar pelo menos uma Verba
    Principal ou Reflexo') — o bot nunca marcava, então TODO Regerar (Manter e
    Sobrescrever) falhava silenciosamente e o carimbo 'ocorrência alterada' do
    dano moral nunca limpava. Fix: marcar selecionarTodos antes do Regerar."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    idx = pw.find("def _regerar_com_modal_confirmacao")
    assert idx > 0
    fim = pw.find("\n    def ", idx + 10)
    bloco = pw[idx:fim]
    assert "selecionarTodos" in bloco, \
        "_regerar_com_modal_confirmacao deve marcar as verbas antes do Regerar"
    # a seleção vem ANTES do click no botão Regerar (seletor real do botão)
    assert bloco.find("selecionarTodos") < bloco.find("':regerarOcorrencias'")


def test_inv49_cap_periodo_inicio_prescricao():
    """#78 (FRANCISCA/L'Oréal 0001858-66): com prescricao_quinquenal=True, o
    PJE-Calc rejeita verba cujo periodo_inicio < piso prescricional (ajuizamento
    − 5a) → save falha → liquidação aborta com listagem vazia. O normalizer capa
    periodo_inicio (verba) e data_inicio_calculo no piso ANTES da prévia."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from modules.json_normalizer import normalize_v2_json
    payload = {
        "meta": {"versao": "2.0", "validacao": {"completude": "OK",
                 "campos_faltantes": [], "avisos": []}},
        "processo": {"numero_processo": "0001858-66.2025.5.07.0003",
                     "reclamante": {"nome": "X"}, "reclamado": {"nome": "Y"}},
        "parametros_calculo": {
            "data_admissao": "16/04/2018", "data_demissao": "02/09/2025",
            "data_ajuizamento": "24/11/2025", "data_inicio_calculo": "04/07/2020",
            "prescricao_quinquenal": True,
        },
        "verbas_principais": [{
            "nome_pjecalc": "HORAS EXTRAS 50%", "expresso_alvo": "HORAS EXTRAS 50%",
            "parametros": {"periodo_inicio": "04/07/2020", "periodo_fim": "02/09/2025",
                           "ocorrencia_pagamento": "MENSAL"},
        }],
    }
    out = normalize_v2_json(payload)
    # piso = 24/11/2025 − 5a = 24/11/2020
    assert out["parametros_calculo"]["data_inicio_calculo"] == "24/11/2020"
    assert out["verbas_principais"][0]["parametros"]["periodo_inicio"] == "24/11/2020"

    # com prescricao_quinquenal=False, NÃO capa (PJE-Calc não aplica piso)
    payload2 = {**payload, "parametros_calculo": {
        **payload["parametros_calculo"], "prescricao_quinquenal": False}}
    payload2["verbas_principais"] = [{
        "nome_pjecalc": "HORAS EXTRAS 50%", "expresso_alvo": "HORAS EXTRAS 50%",
        "parametros": {"periodo_inicio": "04/07/2020", "periodo_fim": "02/09/2025",
                       "ocorrencia_pagamento": "MENSAL"}}]
    out2 = normalize_v2_json(payload2)
    assert out2["verbas_principais"][0]["parametros"]["periodo_inicio"] == "04/07/2020"

    # o hook está registrado no pipeline
    nz = (REPO_ROOT / "modules" / "json_normalizer.py").read_text(encoding="utf-8")
    assert "_norm_cap_periodo_inicio_prescricao(data)" in nz


def test_inv50_reabertura_recentes_retry():
    """#78 (FRANCISCA 0001858-66): logo após o Fechar da 1ª verba Expresso, a
    lista 'Recentes' de principal.jsf às vezes ainda não renderizou → a detecção
    do select falhava na 1ª tentativa → reabertura falhava → a verba recém-salva
    ficava órfã (perdida). _reabrir_calculo_via_recentes deve RETRY o reload +
    detecção (espera crescente) antes de desistir."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    idx = pw.find("def _reabrir_calculo_via_recentes")
    assert idx > 0
    fim = pw.find("\n    def ", idx + 10)
    bloco = pw[idx:fim]
    # retry com reload de principal.jsf enquanto select não encontrado
    assert "while not _select_id" in bloco
    assert bloco.count("principal.jsf") >= 2  # goto inicial + goto no retry
    assert "_SELECT_RECENTES_JS" in bloco


def test_inv51_expresso_fechar_reabrir_pre_loop():
    """#79 (FRANCISCA HE 50%): o save Expresso de verbas que auto-geram reflexos
    (HORAS EXTRAS 50%) NÃO commita o principal quando feito na conversa Seam
    INICIAL (recém-criada) — só os reflexos órfãos sobram. A 2ª verba (conversa
    reaberta) persiste. Fix PREVENTIVO: _lancar_expresso faz Fechar+Reabrir ANTES
    do loop, p/ que mesmo a 1ª verba seja salva em conversa reaberta limpa. Um
    retry corretivo NÃO serve: os reflexos órfãos do save falho seriam
    duplicados (não há como removê-los re-lançando)."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    disp = pw[pw.find("def _lancar_expresso(self"):pw.find("def _lancar_expresso_batch")]
    assert 'pré-loop Expresso (#79)' in disp
    # o Fechar+Reabrir vem ANTES do dispatch p/ individual/batch
    assert disp.find("_fechar_e_reabrir_calculo") < disp.find("_lancar_expresso_individual")


def test_inv52_importada_cartao_native_click():
    """#80-A (0000715-08 HE 50%/INTERVALO): bot selecionava a coluna do cartão
    (Hs EXT) e clicava 'Incluir' via onclick-exec (new Function) — que NÃO
    dispara A4J.AJAX em headless Firefox/JSF 1.2 → coluna não entra no bean →
    tipoImportadadoDoCartaoDePonto=null → quantidade=0 (verba liquida R$0). Fix:
    NATIVE Playwright click no Incluir + verificação da coluna na listagem +
    retry."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    fn = pw[pw.find("def _vincular_cartao_ponto_quantidade"):pw.find("def _selecionar_primeira_opcao_cartao")]
    # Incluir via native click (force=True), não mais onclick-exec como primário
    assert "incluirCartaoDePontoQuantidade" in fn
    assert "click(force=True)" in fn, "Incluir deve usar native Playwright click"
    # verificação + retry da coluna
    assert "_label_presente" in fn
    assert "CONFIRMADA na listagem de quantidade" in fn


def test_inv53_ocorrencias_valores_mensais():
    """#80-C (0000715-08 DIFERENÇA SALARIAL): quando ocorrencias_override.modo=
    valores_mensais, o bot deve aplicar CADA valor mensal na ocorrência do mês
    correspondente (casado por dataInicial), em vez de jogar o total na 1ª
    linha. Sem isso, DIFERENÇA SALARIAL liquida com valor errado por mês."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    fn = pw[pw.find("def _configurar_ocorrencias_informado_inline"):pw.find("def _dump_dom_indenizacao")]
    assert "mes_to_valor" in fn
    assert "valores_mensais" in fn
    # casa por índice cronológico (periodo_inicio + i meses) — a grade inline não
    # expõe a data por linha; fallback DOM mantido
    assert "_add_meses" in fn
    assert fn.find("if mes_to_valor:") < fn.find("elif proporcionalizar:")
    # SALVAGUARDA: não zerar a verba se o casamento por mês falhar
    assert "casamento por mês falhou" in fn
    assert "valor_total na 1ª ocorrência" in fn


def test_inv54_listagem_vazia_recovery_proativo_pre_reflexos():
    """#80-D (0000715-08): após saves/Regerar a listagem de verbas volta VAZIA
    (Seam EPC stale). O loop de reflexos rodava nela e o FGTS sobre HE 50%
    falhava — a recovery Fechar+Reabrir só vinha depois (no click Parâmetros).
    Fix: detectar listagem vazia e Fechar+Reabrir PROATIVO ANTES dos reflexos,
    em _configurar_parametros_pos_expresso."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    fn = pw[pw.find("def _configurar_parametros_pos_expresso"):pw.find("def _configurar_parametros_pos_expresso")+14000]
    assert "#80-D listagem vazia pós-navegação" in fn
    # o recovery proativo vem ANTES do loop de reflexos
    assert fn.find("#80-D listagem vazia") < fn.find("for _r in getattr(v, \"reflexos\"")


def test_inv55_quantidade_informada_aguarda_render():
    """#80-E (GEOVANA 0000627-04): o radio tipoDaQuantidade=INFORMADA tem
    onchange=A4J que renderiza CONDICIONALMENTE o campo valorInformadoDaQuantidade.
    O native click dava timeout quando INFORMADA já era default, e sem o change
    o campo de valor não renderizava → HORAS EXTRAS 50% / ADICIONAL NOTURNO /
    INTERVALO saíam com quantidade=0 (capítulo Duração do Trabalho liquidava
    R$0). Fix: disparar 'change' via JS + aguardar o campo de valor ficar
    visível antes de preencher."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    fn = pw[pw.find("def _configurar_quantidade_radio"):pw.find("def _vincular_cartao_ponto_quantidade")]
    # dispara change via JS (não native click que dava timeout)
    assert "dispatchEvent(new Event('change'" in fn
    # espera o campo de valor renderizar antes de preencher
    assert "valorInformadoDaQuantidade" in fn
    assert fn.find("dispatchEvent(new Event('change'") < fn.find('state="visible", timeout=10000')


def test_inv56_seam_concurrent_request_timeout():
    """#80-D/G (GEOVANA, java.log): a 'listagem de verbas vazia' que travava
    A/C/E era na verdade a página de erro do LockTimeoutException no
    @Synchronized apresentadorVerbaDeCalculo — a verba-calculo.jsf falhava ao
    renderizar porque não conseguia o lock do bean (operação pesada o segura).

    ⚠ concurrent-request-timeout NÃO é a alavanca desse lock (verificado #80-G:
    o LockTimeout dispara mesmo com 120000 — o SynchronizationInterceptor usa o
    timeout da anotação @Synchronized, ~1000ms no bytecode). Mantém-se >=60000
    mesmo assim (inofensivo, cobre contenção de CONVERSA). O fix real é #80-G
    (bot-side, test_inv57). NÃO reverter p/ 5000."""
    cx = (REPO_ROOT / "pjecalc-dist" / "tomcat" / "webapps" / "pjecalc"
          / "WEB-INF" / "components.xml").read_text(encoding="latin-1")
    import re as _re
    m = _re.search(r'concurrent-request-timeout="(\d+)"', cx)
    assert m, "concurrent-request-timeout ausente no components.xml"
    assert int(m.group(1)) >= 60000, (
        f"concurrent-request-timeout={m.group(1)} curto demais — "
        f"causa LockTimeoutException na verba-calculo.jsf (#80-D)"
    )


def test_inv57_listagem_vazia_reload_leve_antes_de_fr():
    """#80-G (GEOVANA RAIZ DEFINITIVA): a 'listagem fantasma' é a página de
    erro do LockTimeoutException (@Synchronized apresentadorVerbaDeCalculo). O
    Fechar+Reabrir pesado dispara MAIS requisições concorrentes e REALIMENTA o
    lock (runs run_E/H: 0 'Parâmetros salvos' em ~600 linhas, loop infinito).
    Fix: ao detectar a listagem vazia, ESPERAR o lock liberar + RECARREGAR a
    MESMA URL (sem nova conversa), e só cair no F+R pesado se o reload leve
    falhar. Tanto no recovery PROATIVO (_configurar_parametros_pos_expresso)
    quanto no REATIVO (click de Parâmetros)."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    # marcador #80-G presente nos dois caminhos
    assert pw.count("#80-G") >= 2, "fix #80-G ausente em um dos recoveries"
    # PROATIVO: reload leve vem ANTES do Fechar+Reabrir proativo
    fn = pw[pw.find("def _configurar_parametros_pos_expresso"):
             pw.find("def _configurar_parametros_pos_expresso") + 14000]
    assert "reload leve" in fn
    assert fn.find("#80-G") < fn.find("Fechar+Reabrir proativo"), (
        "reload leve #80-G deve vir ANTES do F+R proativo"
    )
    # o reload leve NÃO chama Fechar+Reabrir (é o ponto: sem realimentar o lock)
    bloco_proativo = fn[fn.find("#80-G"):fn.find("Fechar+Reabrir proativo")]
    assert "_fechar_e_reabrir_calculo" not in bloco_proativo, (
        "o reload leve #80-G não pode chamar Fechar+Reabrir (realimenta o lock)"
    )


def test_inv58_aguardar_servidor_ocioso_antes_de_navegar():
    """#80-H (GEOVANA RAIZ COMUM — PREVENÇÃO): os 2 modos de 'listagem
    fantasma' (LockTimeout E morte da conversa Seam) têm causa COMUM — o bot
    NAVEGA para a listagem enquanto o servidor ainda finaliza a op pesada da
    verba anterior (save Expresso + Regerar Drools, lock 20–40s na VM pequena).
    O LockTimeout no render MATA a conversa → Recentes VAZIO = cálculo
    irreabrível (run_J: nOpts=0). Fix: gate _aguardar_servidor_ocioso ANTES da
    navegação à listagem em _configurar_parametros_pos_expresso — espera o
    networkidle estabilizar (sem requisições em voo) antes de navegar; não
    navega (zero risco de matar a conversa). NÃO remover: sem ele os fixes de
    valor #80-A/C/E ficam bloqueados (forms nunca renderizam)."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    assert "def _aguardar_servidor_ocioso" in pw, "helper #80-H ausente"
    fn = pw[pw.find("def _configurar_parametros_pos_expresso"):
             pw.find("def _configurar_parametros_pos_expresso") + 14000]
    # o gate é CHAMADO antes do sidebar click li_calculo_verbas
    assert "_aguardar_servidor_ocioso(" in fn, "gate #80-H não chamado na config de parâmetros"
    assert fn.find("_aguardar_servidor_ocioso(") < fn.find('_navegar_menu_via_click("li_calculo_verbas")'), (
        "o gate #80-H deve vir ANTES da navegação ao sidebar (prevenir navegar ocupado)"
    )


def test_inv59_reflexos_manual_deferidos_apos_principal():
    """#80-J (GEOVANA 0000627-04, reorder principal-antes-dos-reflexos):
    reflexos MANUAL (estrategia=MANUAL OU fallback 'sem checkbox') clicam
    Incluir e NAVEGAM para o form do reflexo, SAINDO da listagem. Se criados
    ANTES do click de Parâmetros do principal, o principal não é mais
    encontrado na listagem → quantidade da verba (HE 50%=157,5 / ADICIONAL=80)
    nunca setada (qtd=0 na liquidação, validado run_K/L/N). Fix:
    _configurar_reflexo aceita `coletar_manual_em` e DEFERE os Manual p/ uma
    lista; eles são criados DEPOIS do save do principal. Reflexos CHECKBOX
    (não navegam) seguem marcados antes do save (invariante de flush).
    VALIDADO run_O: HE 50%=157,5 / ADICIONAL=80 / INTERVALO=7,5 persistidos no
    PJC (CALCULO_103), totalErros=0. NÃO reverter."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    # _configurar_reflexo tem o parâmetro de coleta
    assert "def _configurar_reflexo(self, verba_principal, reflexo, coletar_manual_em=None)" in pw, (
        "_configurar_reflexo deve aceitar coletar_manual_em (#80-J)"
    )
    # o loop de reflexos da config de parâmetros COLETA os Manual
    fn = pw[pw.find("def _configurar_parametros_pos_expresso"):
             pw.find("def _OLD_configurar_parametros_pos_expresso")]
    assert "_manuais_deferidos = []" in fn
    assert "coletar_manual_em=_manuais_deferidos" in fn
    # os deferidos são criados DEPOIS (loop for _rm) — após a coleta
    assert "for _rm in _manuais_deferidos" in fn
    assert fn.find("coletar_manual_em=_manuais_deferidos") < fn.find("for _rm in _manuais_deferidos"), (
        "a coleta deve vir ANTES da criação dos Manual deferidos"
    )


def test_inv60_honorario_reclamante_sempre_cobrar():
    """#80-K (bug recorrente 27/06/2026): honorários sucumbenciais devidos PELO
    reclamante devem ser SEMPRE "Cobrar do reclamante" (TipoCobrancaReclamante
    .COBRAR), NUNCA "Descontar dos créditos" (DESCONTAR_CREDITO, default do
    bean). O radio tipoCobrancaReclamante só renderiza após o onchange A4J de
    tipoDeDevedor; a marcação cedo/não-persistida deixava o default DESCONTAR.
    Fix: esperar o radio renderizar + marcar COBRAR (por value 'COBRAR'/'C' OU
    label 'Cobrar do reclamante') via JS + VERIFICAR + retry. NÃO reverter."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    i = pw.find("#80-K")
    assert i > 0, "fix #80-K ausente"
    seg = pw[i:i+3700]
    # espera o radio renderizar antes de marcar
    assert "tipoCobrancaReclamante" in seg
    assert "wait_for_selector" in seg
    # marca por value COBRAR/C ou label "Cobrar do reclamante"
    assert "COBRAR" in seg and "Cobrar do reclamante".upper() in seg.upper()
    # verifica persistência (confirmado)
    assert "confirmado=" in seg


def test_inv61_base_historico_verba_click_nativo_verificado():
    """#80-M (0000712-53, 27/06/2026): a base CALCULADO/HISTORICO_SALARIAL da
    verba exige clicar `incluirBaseHistorico` (<a4j:commandLink>) p/ adicionar o
    histórico à tabela `listagemHistoricosDaVerba`. O JS `btn.click()` reportava
    sucesso mas o bean NÃO recebia (padrão DOM≠bean) → base vazia → liquidação
    'Falta selecionar pelo menos um Histórico Salarial...' (e a verba CALCULADO
    liquidava 0). Fix: click NATIVO Playwright + VERIFICAR a tabela por NOME do
    histórico (ground truth do bean) + retry ×3. NÃO reverter p/ JS btn.click()."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    i = pw.find("#80-M")
    assert i > 0, "fix #80-M ausente"
    seg = pw[i:i + 4200]
    # verifica a tabela por nome (ground truth do bean)
    assert "_tabela_tem_hist" in seg
    assert "listagemHistoricosDaVerba" in seg
    # click NATIVO via locator (não JS btn.click)
    assert ".first.click(timeout=" in seg
    assert "incluirBaseHistorico" in seg
    # retry + confirmação
    assert "CONFIRMADO na base da verba" in seg


def test_inv62_preencher_respeita_maxlength():
    """#80-O (0000712-53, 27/06/2026): _preencher seta inputs via JS
    `el.value=...`, que BYPASSA o maxlength que o browser imporia ao digitar.
    O campo `descricao` (Nome) da verba tem maxlength=50; verbas
    expresso_adaptado com nome longo (>50) eram setadas inteiras → o servidor
    rejeitava o SAVE por validação de tamanho, SILENCIOSAMENTE (rich:message
    fora do re-render) → form sem sucesso/erro → bot Cancelava → base/params
    descartados → liquidação bloqueada. Fix: _preencher lê o maxlength do campo
    e TRUNCA o valor. NÃO reverter."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    fn = pw[pw.find("def _preencher(self"):pw.find("def _preencher_data_richfaces")]
    assert "#80-O" in fn, "fix #80-O ausente em _preencher"
    assert 'get_attribute("maxlength")' in fn
    assert "truncado a maxlength" in fn
    # o truncamento ocorre ANTES do set via JS (el.value)
    assert fn.find("truncado a maxlength") < fn.find("el.value = valor")


def test_inv63_escala_inicio_hora_e_aguarda_habilitar():
    """#80-B (0000712-53, 27/06/2026): cartão ESCALA não apurava dias → verbas
    IMPORTADA_DO_CARTAO (INTERVALO) liquidavam qtd=0. Causa: o campo
    valorHoraInicioEscala ('Início Escala', size=6 timeMask = HORA, não data)
    é obrigatório e só HABILITA após o a4j onchange=mudarTipoEscala do select
    'escalas'. O bot (a) esperava só 800ms → campo disabled → _preencher pulava
    → save 'Campo obrigatório: Início Escala' → escala não salva → 0 dias; e
    (b) preenchia esc.inicio (uma DATA) num campo de HORA. Fix: esperar o A4J +
    o campo habilitar (wait_for_function !disabled) e preencher com a HORA de
    entrada do 1º turno (ex.: 19:00). NÃO reverter."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    fn = pw[pw.find('elif preenchimento == "ESCALA"'):pw.find('elif preenchimento == "ESCALA"') + 6000]
    assert "#80-B" in fn, "fix #80-B ausente"
    # usa a hora de entrada do 1º turno (não a data esc.inicio)
    assert "_hora_ini" in fn and "turnos" in fn and "entrada" in fn
    # aguarda o campo habilitar antes de preencher
    assert "!e.disabled" in fn or "e.disabled" in fn
    # preenche via press_sequentially (dispara onkeyup→atualizarListaEscala) — NÃO via _preencher
    assert "press_sequentially" in fn and "valorHoraInicioEscala" in fn


def test_inv64_honorario_credor_sem_documento():
    """#80-P (orientação do usuário 27/06/2026): honorários NÃO registram
    CPF/documento do credor — basta o NOME ('ADVOGADO DO RECLAMANTE/RECLAMADO').
    O credor sucumbencial é o advogado da parte contrária (genérico, sem CPF na
    sentença); preencher o documento era desnecessário e disparava 'Erro: 19'
    (validadorDinamico) quando o tipo ia sem número. Fix: a fase de honorários
    NÃO preenche tipoDocumentoFiscalCredor nem numeroDocumentoFiscalCredor —
    só nomeCredor. NÃO reverter."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    fn = pw[pw.find("def fase_honorarios"):pw.find("def fase_custas_judiciais")]
    # ainda preenche o NOME do credor
    assert '_preencher("nomeCredor"' in fn
    # mas NÃO preenche/marca o documento do credor
    assert '"tipoDocumentoFiscalCredor"' not in fn, "honorários NÃO deve marcar tipoDocumentoFiscalCredor"
    assert '"numeroDocumentoFiscalCredor"' not in fn, "honorários NÃO deve preencher numeroDocumentoFiscalCredor"
    assert "#80-P" in fn


def test_inv65_override_grade_usa_salvar_editavel():
    """#80-Q (MARIA THAYSNARA 0000632-89, 27/06/2026): _aplicar_ocorrencias_override
    usa _clicar("salvarEditavel") na Grade de Ocorrências, NÃO _clicar("salvar").
    Em modo Grade (operacao=VISUALIZACAO ou OUTRO), o botão renderizado é
    `id="salvarEditavel"` (apuracao-cartaodeponto.xhtml:1219).
    `id="salvar"` só existe em emModoFormulario!=VISUALIZACAO — nunca em Grade.
    Sem este fix, 100% dos saves da Grade falhavam silenciosamente com
    'Botão não encontrado: salvar' → dobras de plantão nunca persistiam. NÃO reverter."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    fn_start = pw.find("def _aplicar_ocorrencias_override")
    fn_end = pw.find("\n    def ", fn_start + 1)
    fn = pw[fn_start:fn_end]
    assert '_clicar("salvarEditavel")' in fn, (
        "REGRESSÃO: _aplicar_ocorrencias_override deve usar salvarEditavel (não salvar) na Grade"
    )
    assert '_clicar("salvar")' not in fn or fn.count('_clicar("salvar")') == 0, (
        "REGRESSÃO: _aplicar_ocorrencias_override voltou a usar _clicar('salvar') — Grade usa salvarEditavel"
    )


def test_inv66_reabrir_retry_antes_expresso():
    """#80-S (MARIA THAYSNARA 0000632-89, 27/06/2026): após apuração pesada de
    cartão (130+ overrides × 61 meses 12x36), o PJE-Calc recusa a reabertura via
    Recentes imediatamente após o Fechar — URL fica em principal.jsf em vez de
    navegar para calculo.jsf. Causa: servidor ainda processando Hibernate/Drools
    side-effects pós-apuração. A mesma reabertura funciona minutos depois.

    FIX: (1) _fechar_e_reabrir_calculo faz retry com delays 30s→90s quando Recentes
    não navega; (2) _lancar_expresso recusa prosseguir com BATCH se Reabrir ainda
    falhar após retries (redirecionando verbas para Manual fallback). Sem (2),
    11 verbas Expresso eram salvas em conv órfã não associada ao cálculo correto,
    resultando em cálculo com 0 verbas e listagem fantasma irrecuperável. NÃO reverter."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")

    # (1) _fechar_e_reabrir_calculo tem retry #80-S
    fn_fr_start = pw.find("def _fechar_e_reabrir_calculo")
    fn_fr_end = pw.find("\n    def ", fn_fr_start + 1)
    fn_fr = pw[fn_fr_start:fn_fr_end]
    assert "#80-S" in fn_fr, (
        "REGRESSÃO #80-S: _fechar_e_reabrir_calculo deve ter retry #80-S pós-falha Recentes"
    )
    assert "retry" in fn_fr and ("30" in fn_fr or "30000" in fn_fr), (
        "REGRESSÃO #80-S: retry deve ter delay de 30s antes de nova tentativa"
    )

    # (2) _lancar_expresso recusa prosseguir se Reabrir falhou
    fn_le_start = pw.find("def _lancar_expresso(")
    fn_le_end = pw.find("\n    def ", fn_le_start + 1)
    fn_le = pw[fn_le_start:fn_le_end]
    assert "#80-S" in fn_le, (
        "REGRESSÃO #80-S: _lancar_expresso deve abortar Expresso quando Reabrir falha definitivamente"
    )
    assert "_verbas_expresso_falhadas" in fn_le and "return" in fn_le, (
        "REGRESSÃO #80-S: _lancar_expresso deve redirecionar verbas para Manual e retornar ao falhar"
    )


def test_inv67_garantir_incluir_gate80h_e_recovery80g():
    """#80-U (MARIA THAYSNARA 0000632-89, 28/06/2026): 3 de 4 verbas Manual
    não criadas porque _garantir_incluir_disponivel não tinha gate #80-H nem
    recovery #80-G — LockTimeout ao navegar para verba-calculo.jsf causava
    página de erro sem 'incluir', o que escalava para F+R que também falhava
    (pre-nav de F+R → novo LockTimeout → Fechar não encontrado → Reabrir direto
    → servidor ainda ocupado → LockTimeout no próximo sidebar). Ciclo de F+Rs
    sem resolver → verbas perdidas.

    FIX: gate #80-H (_aguardar_servidor_ocioso) ANTES de cada sidebar click +
    recovery #80-G (reload leve) se LockTimeout ocorrer. Aplicado em helper
    _tentar_sidebar, usado tanto pré-F+R quanto pós-F+R. NÃO REVERTER."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")

    fn_start = pw.find("def _garantir_incluir_disponivel(")
    fn_end = pw.find("\n    def ", fn_start + 1)
    fn = pw[fn_start:fn_end]

    assert "#80-U" in fn, (
        "REGRESSÃO #80-U: _garantir_incluir_disponivel deve ter marcador #80-U"
    )
    assert "_aguardar_servidor_ocioso" in fn, (
        "REGRESSÃO #80-U: _garantir_incluir_disponivel deve chamar _aguardar_servidor_ocioso "
        "(gate #80-H) antes de sidebar click — sem isso LockTimeout mata a conv"
    )
    assert "wait_for_function" in fn, (
        "REGRESSÃO #80-U v2: _garantir_incluir_disponivel deve usar wait_for_function "
        "(espera positiva 45s) em vez de timeout fixo — timeout fixo de 6.8s insuficiente "
        "para Drools pesado server-side que não produz AJAX em voo"
    )
    assert "_tem_locktimeout" in fn or "Erro Interno no Servidor" in fn, (
        "REGRESSÃO #80-U: _garantir_incluir_disponivel deve detectar LockTimeout "
        "(recovery #80-G) após sidebar click"
    )
    assert "reload" in fn, (
        "REGRESSÃO #80-U: _garantir_incluir_disponivel deve fazer reload leve "
        "para recovery #80-G ao detectar LockTimeout"
    )


def test_inv68_export_recentes_reopen_pos_liquidacao():
    """#80-T (MARIA THAYSNARA 0000632-89, 28/06/2026): após a liquidação, a página
    é liquidacao.jsf e o conversationId é o da liquidação (ex.: 691). Nesse estado:
      • o sidebar click em li_operacoes_exportar NÃO navega para exportacao.jsf
        (a conv de liquidação não transiciona para a conv de exportação);
      • URL nav direto para exportacao.jsf?conv=<liquidação> RENDERIZA a página
        (tem_export_btn=True) mas ao clicar Exportar o servidor retorna
        'Erro: 6' (Erro inesperado) — a conv de liquidação não é estado Seam
        válido para exportação. Fases A/E/F de captura todas falham.

    FIX: pre-check detecta liquidacao.jsf → Recentes reopen (→ calculo.jsf com conv
    fresca em edit-mode) → sidebar Exportar (do calculo.jsf a conv É válida e o
    link navega corretamente para exportacao.jsf). Validado RUN 8: PJC 126.332
    bytes capturado via Fase A após 'recentes-pre+sidebar:li_operacoes_exportar'.
    NÃO reverter — sem o pre-check o export pós-liquidação falha com Erro: 6."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")

    # Localizar o bloco de export (pre-check vive logo antes da estratégia 1 sidebar)
    idx = pw.find("# PRE-CHECK: se estamos em liquidacao.jsf")
    assert idx != -1, (
        "REGRESSÃO #80-T: bloco de export deve ter PRE-CHECK para liquidacao.jsf"
    )
    bloco = pw[idx:idx + 2500]
    assert "#80-T" in bloco, (
        "REGRESSÃO #80-T: pre-check de export deve ter marcador #80-T"
    )
    assert "_reabrir_calculo_via_recentes" in bloco, (
        "REGRESSÃO #80-T: pre-check deve fazer Recentes reopen ANTES do sidebar "
        "Exportar quando em liquidacao.jsf (conv de liquidação não exporta — Erro: 6)"
    )
    assert "recentes-pre+sidebar" in bloco, (
        "REGRESSÃO #80-T: pre-check deve marcar nav_exp='recentes-pre+sidebar' "
        "ao navegar Exportar a partir da conv fresca reaberta"
    )


def test_inv69_verba_manual_aguarda_drools_pos_save():
    """#80-V (MARIA THAYSNARA 0000632-89, 28/06/2026): verba Manual cujo save NÃO
    emite 'operação realizada com sucesso' (ex.: FGTS com base complexa PISO DA
    CATEGORIA) deixa o Drools processando reflexos em background, segurando o
    @Synchronized apresentadorVerbaDeCalculo por >3 min. Sem espera, a próxima
    verba dispara LockTimeout e é perdida — RUN 5/7 ficavam em 13/16 verbas
    (TEMPO A DISPOSICAO, 13º PROPORCIONAL, FÉRIAS PROPORCIONAIS faltando).

    FIX: ao detectar ausência de mensagem de sucesso em _lancar_verba_manual,
    aguardar 90s (wait_for_timeout) para o Drools finalizar antes de prosseguir.
    Validado RUN 7/8: 16/16 verbas criadas. NÃO reverter."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")

    fn_start = pw.find("def _lancar_verba_manual(")
    fn_end = pw.find("\n    def ", fn_start + 1)
    fn = pw[fn_start:fn_end]

    assert "#80-V" in fn, (
        "REGRESSÃO #80-V: _lancar_verba_manual deve ter marcador #80-V"
    )
    assert "90000" in fn, (
        "REGRESSÃO #80-V: _lancar_verba_manual deve aguardar 90s (wait_for_timeout 90000) "
        "após detectar ausência de mensagem de sucesso — Drools segura o lock por >3 min"
    )
    # A espera deve estar atrelada ao ramo de 'mensagem de sucesso não detectada'
    idx_msg = fn.find("mensagem de sucesso não detectada")
    assert idx_msg != -1, "REGRESSÃO #80-V: ramo de sucesso-não-detectado deve existir"
    assert "90000" in fn[idx_msg:idx_msg + 600], (
        "REGRESSÃO #80-V: o wait de 90s deve estar DENTRO do ramo de 'sucesso não "
        "detectado' (não incondicional — não atrasar verbas que salvam normalmente)"
    )


def test_inv70_expresso_batch_espera_botao_e_roteia_manual():
    """#80-W (REGINALDO 0001876-87, 30/06/2026): no Expresso BATCH, logo após o
    Fechar+Reabrir pré-loop (#79), o botão lancamentoExpresso
    (rendered=#{apresentador.emModoListagem}) ainda não havia renderizado quando o
    bot procurou — e o `except` apenas fazia `return` SILENCIOSO. Resultado: as 8
    verbas nunca foram criadas, a listagem ficou VAZIA para sempre, e a liquidação
    abortou (cálculo travado em 'Confirmado', sem PJC).

    FIX (2 partes, NÃO REVERTER):
      1. Gate #80-H (_aguardar_servidor_ocioso) + wait-loop que re-navega via
         sidebar (resetando emModoListagem=true) até o botão ficar VISÍVEL antes
         de clicar — replicando a robustez já presente em _lancar_expresso_individual.
      2. Se o botão ainda não aparecer, rotear TODAS as verbas para o fallback
         Manual (_verbas_expresso_falhadas) em vez de `return` silencioso — assim
         as verbas são criadas e a liquidação não fica vazia."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")

    fn_start = pw.find("def _lancar_expresso_batch(")
    fn_end = pw.find("\n    def ", fn_start + 1)
    fn = pw[fn_start:fn_end]

    assert "#80-W" in fn, (
        "REGRESSÃO #80-W: _lancar_expresso_batch deve ter marcador #80-W"
    )
    assert "_aguardar_servidor_ocioso" in fn, (
        "REGRESSÃO #80-W: _lancar_expresso_batch deve chamar _aguardar_servidor_ocioso "
        "(gate #80-H) antes de procurar lancamentoExpresso (botão renderiza tarde pós-F+R)"
    )
    # O ramo de falha do clique NÃO pode ser um `return` silencioso — tem de rotear p/ Manual
    idx_fail = fn.find("click lancamentoExpresso falhou")
    assert idx_fail != -1, "REGRESSÃO #80-W: ramo de falha do clique deve existir"
    bloco_fail = fn[idx_fail:idx_fail + 400]
    assert "_verbas_expresso_falhadas = list(verbas)" in bloco_fail, (
        "REGRESSÃO #80-W: ao não encontrar lancamentoExpresso, _lancar_expresso_batch "
        "DEVE rotear TODAS as verbas para Manual (_verbas_expresso_falhadas = list(verbas)) "
        "em vez de `return` silencioso — senão a listagem fica vazia e a liquidação aborta"
    )


def test_inv71_execucao_limpa_cartao_vazio_antes_de_validar():
    """#80-X (REGINALDO 0001876-87, 30/06/2026): a re-execução
    (executar_v2_como_generator) validava o JSON CRU com PreviaCalculoV2, sem o
    normalize/limpeza que a confirmação aplica. Se o JSON salvo tiver
    cartao_de_ponto = {ocorrencias_override: []} (objeto vazio que a UI da prévia
    inicializa no boot), Pydantic exige data_inicial/data_final → "validação
    Pydantic falhou" e a automação nem inicia.

    FIX: aplicar _limpar_cartao_ponto_vazio (+ normalize_v2_json) ANTES do
    model_validate na execução, idêntico ao path de confirmação — re-execuções
    sempre coerentes. NÃO REVERTER."""
    src = (REPO_ROOT / "modules" / "webapp_v2.py").read_text(encoding="utf-8")

    fn_start = src.find("def executar_v2_como_generator(")
    assert fn_start != -1, "executar_v2_como_generator deve existir"
    fn_end = src.find("\ndef ", fn_start + 1)
    fn = src[fn_start:fn_end]

    idx_validate = fn.find("PreviaCalculoV2.model_validate")
    assert idx_validate != -1, "execução deve validar com PreviaCalculoV2"
    antes = fn[:idx_validate]
    assert "_limpar_cartao_ponto_vazio" in antes, (
        "REGRESSÃO #80-X: executar_v2_como_generator deve chamar "
        "_limpar_cartao_ponto_vazio ANTES do model_validate — senão cartao vazio "
        "{ocorrencias_override:[]} quebra a validação e a automação nem inicia"
    )
    assert "normalize_v2_json" in antes, (
        "REGRESSÃO #80-X: executar_v2_como_generator deve normalizar (normalize_v2_json) "
        "ANTES do model_validate, igual ao path de confirmação"
    )

    # Comportamento: cartao vazio → None
    import importlib
    mod = importlib.import_module("modules.webapp_v2")
    p = mod._limpar_cartao_ponto_vazio({"cartao_de_ponto": {"ocorrencias_override": []}})
    assert p["cartao_de_ponto"] is None, (
        "REGRESSÃO #80-X: _limpar_cartao_ponto_vazio deve transformar cartao vazio em None"
    )


def test_inv72_salario_base_nao_e_historico_default():
    """#80-Y (REGINALDO 0001876-87, 30/06/2026): "SALÁRIO BASE" NÃO pode estar em
    _HISTORICOS_DEFAULT. O commit e41b4ab (04/05/2026) assumia que o PJE-Calc
    auto-cria um histórico "SALÁRIO BASE" — FALSO. O PJE-Calc só auto-cria
    "ÚLTIMA REMUNERAÇÃO". Quando a prévia traz um histórico "SALÁRIO BASE" com
    valor real e verbas CALCULADO o referenciam (formula_calculado.base_calculo.
    historico_nome="SALÁRIO BASE", tipo=HISTORICO_SALARIAL — caso do 13º, FÉRIAS+1/3
    e HE de REGINALDO), pulá-lo deixava essas verbas SEM base salarial →
    liquidação bloqueada: "Falta selecionar pelo menos um Histórico Salarial" +
    "Campo obrigatório: Histórico Salarial" no save dos parâmetros.

    Removê-lo do skip faz o bot CRIAR o SALÁRIO BASE normalmente (fidelidade
    prévia↔automação). NÃO RE-ADICIONAR."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    import re
    m = re.search(r"_HISTORICOS_DEFAULT\s*=\s*\{(.*?)\}", pw, re.S)
    assert m, "_HISTORICOS_DEFAULT deve existir"
    corpo = m.group(1)
    assert "SALÁRIO BASE" not in corpo and "SALARIO BASE" not in corpo, (
        "REGRESSÃO #80-Y: 'SALÁRIO BASE' NÃO pode estar em _HISTORICOS_DEFAULT — "
        "o PJE-Calc não o auto-cria; pulá-lo deixa verbas CALCULADO sem base e "
        "bloqueia a liquidação. Ver caso REGINALDO 0001876-87."
    )
    # ÚLTIMA REMUNERAÇÃO DEVE permanecer (genuinamente auto-criada pelo PJE-Calc)
    assert "REMUNERA" in corpo, (
        "REGRESSÃO #80-Y: 'ÚLTIMA REMUNERAÇÃO' deve PERMANECER em _HISTORICOS_DEFAULT "
        "(é o histórico genuinamente auto-criado pelo PJE-Calc)"
    )


def test_inv73_form_nao_carregou_sempre_recupera():
    """#80-Z (REGINALDO 0001876-87, 30/06/2026): quando o form de Alteração da
    verba NÃO carrega (wait_for descricao falha), o recovery (LEVE goto + re-click,
    depois F+R) deve rodar SEMPRE — não só em wrong-page (principal.jsf). ANTES,
    quando a URL seguia em verba-calculo.jsf (form não renderizou por lock A4J
    transitório), caía num `return` SILENCIOSO ("de fato form não carregou") que
    PULAVA a verba sem ajustar parâmetros. Para CALCULADO (13º SALÁRIO de REGINALDO)
    isso deixava a base histórico sem selecionar → liquidação bloqueada com
    "Falta selecionar pelo menos um Histórico Salarial". NÃO REVERTER."""
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")

    fn_start = pw.find("def _configurar_parametros_pos_expresso(")
    assert fn_start != -1
    fn_end = pw.find("\n    def ", fn_start + 1)
    fn = pw[fn_start:fn_end]

    assert "#80-Z" in fn, (
        "REGRESSÃO #80-Z: _configurar_parametros_pos_expresso deve ter marcador #80-Z"
    )
    # O `return  # de fato form não carregou` (skip silencioso) NÃO pode voltar
    assert "de fato form não carregou" not in fn, (
        "REGRESSÃO #80-Z: o `return  # de fato form não carregou` foi removido — "
        "ele pulava a verba sem recovery quando o form não renderizava em "
        "verba-calculo.jsf. NÃO reintroduzir o gate wrong-page-only."
    )
    # #80-AA: o re-click pós-F+R deve esperar a listagem popular (linkParametrizar)
    assert "#80-AA" in fn, (
        "REGRESSÃO #80-AA: o recovery deve aguardar a listagem POPULAR "
        "(linkParametrizar presente) antes do re-click pós-F+R — senão o re-click "
        "roda com a listagem vazia (lock) e 'não acha' a verba (pulava o 13º)."
    )


def test_inv74_aviso_previo_divisor_30():
    """#80-AB (REGINALDO 0001876-87): AVISO PRÉVIO CALCULADO deve usar divisor=30
    (base diária, Lei 12.506/2011 — aviso proporcional 30 + 3/ano). A IA emitia
    divisor=1/quantidade=1 ("1 mês") → só 30 dias, perdendo os proporcionais
    (33 dias deferidos saíram 30). Camadas: prompt + normalizer.
    """
    import importlib
    norm = importlib.import_module("modules.json_normalizer")
    # (1) divisor=1/qtd=1 → divisor=30/qtd=30 (valor preservado)
    d = {"verbas_principais": [{"nome_pjecalc": "AVISO PRÉVIO", "parametros": {
        "caracteristica": "AVISO_PREVIO", "valor": "CALCULADO",
        "formula_calculado": {"divisor": {"tipo": "OUTRO_VALOR", "valor": 1},
                              "quantidade": {"tipo": "INFORMADA", "valor": 1}}}}]}
    norm._norm_aviso_previo_divisor_30(d)
    fc = d["verbas_principais"][0]["parametros"]["formula_calculado"]
    assert fc["divisor"]["valor"] == 30.0, "REGRESSÃO #80-AB: divisor do aviso deve virar 30"
    assert fc["quantidade"]["valor"] == 30.0, "REGRESSÃO #80-AB: qtd deve escalar p/ preservar valor"
    # (2) já correto (30/33) preservado
    d2 = {"verbas_principais": [{"nome_pjecalc": "AVISO PRÉVIO", "parametros": {
        "caracteristica": "AVISO_PREVIO", "valor": "CALCULADO",
        "formula_calculado": {"divisor": {"tipo": "OUTRO_VALOR", "valor": 30},
                              "quantidade": {"tipo": "INFORMADA", "valor": 33}}}}]}
    norm._norm_aviso_previo_divisor_30(d2)
    fc2 = d2["verbas_principais"][0]["parametros"]["formula_calculado"]
    assert fc2["divisor"]["valor"] == 30 and fc2["quantidade"]["valor"] == 33, (
        "REGRESSÃO #80-AB: aviso já com divisor=30 deve ser preservado")
    # prompt tem a regra
    prompt = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "AVISO PRÉVIO (DIVISOR = 30" in prompt, (
        "REGRESSÃO #80-AB: prompt deve ter o invariante do divisor=30 do aviso")


def test_inv75_dano_moral_sumula_439_false():
    """#80-AC (REGINALDO): INDENIZAÇÃO POR DANO MORAL — Súmula 439 do TST deve ser
    False. Camadas: normalizer força false; bot desmarca (defensivo); prompt instrui.
    """
    import importlib
    norm = importlib.import_module("modules.json_normalizer")
    d = {"verbas_principais": [{"nome_pjecalc": "INDENIZAÇÃO POR DANO MORAL",
                                "parametros": {"juros_aplicar_sumula_439": True}}]}
    norm._norm_dano_moral_sumula_439_false(d)
    assert d["verbas_principais"][0]["parametros"]["juros_aplicar_sumula_439"] is False, (
        "REGRESSÃO #80-AC: normalizer deve forçar juros_aplicar_sumula_439=False no dano moral")
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    assert "#80-AC" in pw and "Súmula 439" in pw, (
        "REGRESSÃO #80-AC: bot deve desmarcar Súmula 439 no dano moral (marcador #80-AC)")
    prompt = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "SÚMULA 439 TST" in prompt or "Súmula nº 439" in prompt, (
        "REGRESSÃO #80-AC: prompt deve instruir Súmula 439=false no dano moral")


def test_inv76_deducao_valor_devido_zero_valida():
    """#80-AD (DANIEL 0000030-98): verba de DEDUÇÃO (VALOR PAGO / DEVOLUÇÃO) tem
    valor_devido=0 e o valor em valor_pago.valor_brl. Antes, isso travava o
    /confirmar da prévia: (a) o validador exigia valor_devido.valor_informado_brl>0
    sem exceção; (b) ValorDevidoInformado tinha Field(gt=0); (c) o normalizer só
    migrava valor→valor_pago quando valor_pago estava vazio (a IA punha em ambos,
    com valor_devido.tipo=CALCULADO → parseava errado). Fix 3 pontos:
    normalizer canoniza (valor_devido INFORMADO/0), Field ge=0, validator isenta
    dedução (valor_pago>0). NÃO REVERTER."""
    import importlib
    N = importlib.import_module("modules.json_normalizer")
    W = importlib.import_module("modules.webapp_v2")
    # dedução com valor em AMBOS + tipo CALCULADO no valor_devido (caso DANIEL)
    d = {"verbas_principais": [{
        "nome_pjecalc": "DEDUCAO - ACERTO RESCISORIO", "expresso_alvo": "VALOR PAGO - NÃO TRIBUTÁVEL",
        "parametros": {"valor": "INFORMADO",
                       "valor_devido": {"tipo": "CALCULADO", "valor_informado_brl": 4061.13},
                       "valor_pago": {"tipo": "INFORMADO", "valor_brl": 4061.13}}}]}
    nd = N.normalize_v2_json(d)
    v = nd["verbas_principais"][0]["parametros"]
    assert v["valor_devido"]["tipo"] == "INFORMADO", "normalizer deve canonizar valor_devido p/ INFORMADO"
    assert v["valor_devido"]["valor_informado_brl"] == 0.0, "dedução: valor_devido deve ser 0"
    assert v["valor_pago"]["valor_brl"] == 4061.13, "valor da dedução fica em valor_pago"
    # ParametrosVerba aceita a dedução (valor_devido=0 + valor_pago>0)
    W._pm.ParametrosVerba.model_validate(v)  # não deve levantar
    # A validação de COMPLETUDE (meta.validacao) TAMBÉM deve isentar a dedução
    # (2ª camada — mesma regra). Guard estrutural no código do schema:
    schema_src = (REPO_ROOT / "docs" / "schema-v2" / "99-pydantic-models.py").read_text(encoding="utf-8")
    idx_compl = schema_src.find("def _validate_completude")
    assert idx_compl != -1
    bloco_compl = schema_src[idx_compl: idx_compl + 4000]
    assert "EXCEÇÃO DEDUÇÃO" in bloco_compl and "_eh_deducao" in bloco_compl, (
        "REGRESSÃO #80-AD: a validação de completude deve isentar verbas de "
        "dedução (valor_devido=0 + valor_pago>0) — senão a prévia fica INCOMPLETA")
    # regressão: INFORMADO sem valor nenhum (nem devido nem pago) ainda falha
    import pytest as _pt
    with _pt.raises(Exception):
        W._pm.ParametrosVerba.model_validate({
            "valor": "INFORMADO",
            "valor_devido": {"tipo": "INFORMADO", "valor_informado_brl": 0},
            "valor_pago": {"tipo": "INFORMADO", "valor_brl": 0}})


def test_inv77_divisor_cartao_para_carga_horaria():
    """#80-AF (DANIEL 0000030-98): divisor=IMPORTADA_DO_CARTAO em verba CALCULADO
    (ex.: ADICIONAL NOTURNO) trava o save ("Campo obrigatório: Cartão de Ponto" —
    o bot só vincula a coluna da QUANTIDADE) e gera "divisor zero". O divisor é a
    CARGA HORÁRIA mensal fixa. Normalizer coage → OUTRO_VALOR (carga do cartão ou
    220); quantidade segue IMPORTADA_DO_CARTAO. NÃO REVERTER."""
    import importlib
    N = importlib.import_module("modules.json_normalizer")
    # com carga horária no cartão → usa ela
    d = {
        "cartoes_de_ponto": [{"jornada_padrao": {"jornada_mensal_media": "181,00"}}],
        "verbas_principais": [{"nome_pjecalc": "ADICIONAL NOTURNO 20%", "parametros": {
            "valor": "CALCULADO",
            "formula_calculado": {
                "divisor": {"tipo": "IMPORTADA_DO_CARTAO", "valor": None},
                "quantidade": {"tipo": "IMPORTADA_DO_CARTAO", "valor": 1},
                "multiplicador": 0.20}}}],
    }
    N._norm_divisor_cartao_para_carga_horaria(d)
    fc = d["verbas_principais"][0]["parametros"]["formula_calculado"]
    assert fc["divisor"]["tipo"] == "OUTRO_VALOR" and fc["divisor"]["valor"] == 181.0
    assert fc["quantidade"]["tipo"] == "IMPORTADA_DO_CARTAO", "quantidade segue do cartão"
    # sem cartão → default 220
    d2 = {"verbas_principais": [{"nome_pjecalc": "X", "parametros": {
        "valor": "CALCULADO", "formula_calculado": {
            "divisor": {"tipo": "IMPORTADA_DO_CARTAO"}, "quantidade": {"tipo": "INFORMADA", "valor": 1}}}}]}
    N._norm_divisor_cartao_para_carga_horaria(d2)
    assert d2["verbas_principais"][0]["parametros"]["formula_calculado"]["divisor"]["valor"] == 220.0
    # prompt tem a regra
    prompt = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "NUNCA `divisor=IMPORTADA_DO_CARTAO`" in prompt
