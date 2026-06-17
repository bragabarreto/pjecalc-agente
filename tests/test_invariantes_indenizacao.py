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


def test_inv15_bot_expande_evolucao():
    """Bot expande hist.evolucao em N entradas internamente (path seguro:
    PJE-Calc continua recebendo N linhas como antes, prévia mostra 1).
    """
    pw = (REPO_ROOT / "modules" / "playwright_v2.py").read_text(encoding="utf-8")
    assert "_expandir_evolucao_historico" in pw
    # Bot precisa CHAMAR essa expansão antes do loop principal
    assert "historicos_para_processar" in pw or "expandir_evolucao_historico(self.previa" in pw


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

    # proporcional do ano da rescisão (sem dezembro) → DESLIGAMENTO
    o1 = normalize_v2_json(_13("01/01/2026", "25/04/2026"))["verbas_principais"][0]["parametros"]["ocorrencia_pagamento"]
    assert o1 == "DESLIGAMENTO"
    # multi-ano (cruza dezembros) → preservado
    o2 = normalize_v2_json(_13("01/01/2024", "25/04/2026"))["verbas_principais"][0]["parametros"]["ocorrencia_pagamento"]
    assert o2 == "DEZEMBRO"
    # ano completo (tem dezembro) → preservado
    o3 = normalize_v2_json(_13("01/01/2025", "31/12/2025"))["verbas_principais"][0]["parametros"]["ocorrencia_pagamento"]
    assert o3 == "DEZEMBRO"
    # prompt instrui a regra
    ext = (REPO_ROOT / "modules" / "extraction_v2.py").read_text(encoding="utf-8")
    assert "proporcional do ano da" in ext and "DESLIGAMENTO" in ext
    assert "período SEM dezembro" in ext or "período sem dezembro" in ext.lower()


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
