# tests/test_e2e_automacao_completa.py
#
# Teste end-to-end completo: JSON v2 (projeto Claude) → PreviaCalculo →
# AplicadorPJECalc → PJE-Calc TRT7 → liquidar → exportar → .PJC válido.
#
# Execução:
#   PJECALC_E2E=1 pytest tests/test_e2e_automacao_completa.py -v -s
#
# Pré-requisitos:
#   - Firefox com perfil TRT7 autenticado em ~/Library/...kku6n0pr.default-release
#   - pje.trt7.jus.br/pjecalc acessível
#   - ANTHROPIC_API_KEY não é necessária (sem extração LLM)

from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

FIREFOX_PROFILE = os.path.expanduser(
    "~/Library/Application Support/Firefox/Profiles/kku6n0pr.default-release"
)
PJECALC_URL = "https://pje.trt7.jus.br/pjecalc"
OUTPUT_DIR = Path("/tmp/pjecalc_testes")

e2e = pytest.mark.skipif(
    not os.getenv("PJECALC_E2E"),
    reason="Defina PJECALC_E2E=1 para executar automação real no TRT7",
)


# ---------------------------------------------------------------------------
# Conversor JSON v2 → PreviaCalculo
# ---------------------------------------------------------------------------

def _brl(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _parsear_numero_cnj(numero_cnj: str) -> dict:
    partes = numero_cnj.replace("-", ".").split(".")
    return {k: partes[i] if len(partes) > i else ""
            for i, k in enumerate(["numero", "digito", "ano", "ramo", "regiao", "vara"])}


def converter_json_v2_para_previa(j: dict):
    """Converte JSON v2 (projeto Claude) → PreviaCalculo (infrastructure/pjecalc_pages)."""
    from infrastructure.pjecalc_pages import (
        PreviaCalculo, DadosProcesso, HistoricoSalarialEntry,
        Verba, ParametrosVerba, FGTS, Honorario,
        ContribuicaoSocial, ImpostoRenda, CustasJudiciais, CorrecaoJuros,
        CorrecaoJurosTabelaAdicional, CartaoDePonto,
    )

    proc = j["processo"]
    par  = j["parametros_calculo"]
    rec  = proc["reclamante"]
    recdo= proc["reclamado"]
    partes = _parsear_numero_cnj(proc["numero_processo"])

    # ── DadosProcesso ─────────────────────────────────────────────────────
    dados_processo = DadosProcesso(
        numero=partes["numero"],
        digito=partes["digito"],
        ano=partes["ano"],
        regiao=partes["regiao"],
        vara=partes["vara"],
        autuado_em=proc.get("data_autuacao"),
        valor_da_causa=_brl(proc.get("valor_da_causa_brl", 0)),

        reclamante_nome=rec["nome"],
        documento_fiscal_reclamante=rec["doc_fiscal"]["tipo"],
        reclamante_numero_documento_fiscal=rec["doc_fiscal"]["numero"] or "",
        nome_advogado_reclamante=rec["advogados"][0]["nome"] if rec.get("advogados") else "",
        numero_oab_advogado_reclamante=rec["advogados"][0]["oab"] if rec.get("advogados") else "",

        reclamado_nome=recdo["nome"],
        tipo_documento_fiscal_reclamado=recdo["doc_fiscal"]["tipo"],
        reclamado_numero_documento_fiscal=recdo["doc_fiscal"]["numero"] or "",
        nome_advogado_reclamado=recdo["advogados"][0]["nome"] if recdo.get("advogados") else "",
        numero_oab_advogado_reclamado=recdo["advogados"][0]["oab"] if recdo.get("advogados") else "",

        estado=par.get("estado_uf"),
        municipio=par.get("municipio"),
        data_admissao=par.get("data_admissao"),
        data_demissao=par.get("data_demissao"),
        data_ajuizamento=par.get("data_ajuizamento"),
        data_inicio_calculo=par.get("data_inicio_calculo"),
        data_termino_calculo=par.get("data_termino_calculo"),

        prescricao_quinquenal=par.get("prescricao_quinquenal", False),
        prescricao_fgts=par.get("prescricao_fgts", False),
        valor_maior_remuneracao=_brl(par.get("valor_maior_remuneracao_brl", 0)),
        valor_ultima_remuneracao=_brl(par.get("valor_ultima_remuneracao_brl", 0)),

        apuracao_prazo_aviso_previo=par.get("apuracao_aviso_previo", "NAO_APURAR"),
        projeta_aviso_indenizado=par.get("projeta_aviso_indenizado", False),
        considera_feriado_estadual=par.get("considerar_feriado_estadual", False),
        considera_feriado_municipal=par.get("considerar_feriado_municipal", False),
        valor_carga_horaria_padrao=str(int(par.get("carga_horaria", {}).get("padrao_mensal", 220))),
        sabado_dia_util=par.get("sabado_dia_util", False),
    )

    # ── Histórico Salarial ────────────────────────────────────────────────
    historico = [
        HistoricoSalarialEntry(
            nome=h["nome"],
            tipo_variacao_da_parcela=h.get("parcela", "FIXA"),
            competencia_inicial=h["competencia_inicial"],
            competencia_final=h["competencia_final"],
            tipo_valor=h.get("tipo_valor", "INFORMADO"),
            valor_para_base_de_calculo=_brl(h["valor_brl"]),
            fgts=h["incidencias"]["fgts"],
            inss=h["incidencias"]["cs_inss"],
        )
        for h in j.get("historico_salarial", [])
    ]

    # ── Verbas ────────────────────────────────────────────────────────────
    _CARACT_MAP = {
        "COMUM": "COMUM",
        "DECIMO_TERCEIRO_SALARIO": "DECIMO_TERCEIRO_SALARIO",
        "FERIAS": "FERIAS",
        "AVISO_PREVIO": "AVISO_PREVIO",
    }
    _OCORR_MAP = {
        "MENSAL": "MENSAL",
        "DEZEMBRO": "DEZEMBRO",
        "DESLIGAMENTO": "DESLIGAMENTO",
        "PERIODO_AQUISITIVO": "PERIODO_AQUISITIVO",
    }
    _ESTRATEGIA_MAP = {
        "expresso_direto": "EXPRESSO",
        "expresso_adaptado": "EXPRESSO",
        "manual": "MANUAL",
    }

    def _converter_verba(v: dict, tipo_verba: str = "PRINCIPAL") -> Verba:
        p = v.get("parametros", {})
        inc = p.get("incidencias", {})
        vd  = p.get("valor_devido", {})
        fc  = p.get("formula_calculado") or {}
        div = fc.get("divisor", {})
        base= fc.get("base_calculo", {})
        estrategia = v.get("estrategia_preenchimento", "expresso_direto")
        lancamento = _ESTRATEGIA_MAP.get(estrategia, "EXPRESSO")

        # base de cálculo
        tipo_base = None
        base_hist = None
        if base.get("tipo") == "HISTORICO_SALARIAL":
            tipo_base = "HISTORICO_SALARIAL"
            base_hist = base.get("historico_nome")
        elif base.get("tipo") == "MAIOR_REMUNERACAO":
            tipo_base = "MAIOR_REMUNERACAO"

        # divisor
        tipo_div = "CARGA_HORARIA"
        outro_div = None
        if div.get("tipo") == "OUTRO_VALOR":
            tipo_div = "INFORMADO"
            outro_div = str(int(div.get("valor", 220)))

        # quantidade (Opção A: INFORMADA com valor mensal; Opção B: IMPORTADA_DO_CARTAO)
        quant = fc.get("quantidade") or {}
        _qtipo_map = {
            "INFORMADA": "INFORMADA",
            "IMPORTADA_DO_CARTAO": "IMPORTADA_CARTAO_PONTO",
            "IMPORTADA_CALENDARIO": "IMPORTADA_CALENDARIO",
        }
        tipo_quant = _qtipo_map.get(quant.get("tipo", "INFORMADA"), "INFORMADA")
        # valor_mensal é o campo canônico; "valor" é alias aceitável
        val_quant_raw = quant.get("valor_mensal") or quant.get("valor")
        val_quant = str(val_quant_raw).replace(".", ",") if val_quant_raw is not None else None

        # valor informado
        val_inf = None
        if vd.get("tipo") == "INFORMADO" and vd.get("valor_informado_brl"):
            val_inf = _brl(vd["valor_informado_brl"])

        caract = _CARACT_MAP.get(
            (v.get("parametros_override") or p).get("caracteristica", "COMUM"), "COMUM"
        )
        ocorr = _OCORR_MAP.get(
            (v.get("parametros_override") or p).get(
                "ocorrencia_pagamento",
                p.get("ocorrencia_pagamento", "MENSAL")
            ), "MENSAL"
        )

        params = ParametrosVerba(
            descricao=v.get("nome_pjecalc") or v.get("nome_sentenca") or v.get("nome", ""),
            assuntos_cnj=str((p.get("assunto_cnj") or {}).get("codigo", "2581")),
            tipo_de_verba=tipo_verba,
            caracteristica_verba=caract,
            ocorrencia_pagto=ocorr,
            periodo_inicial=p.get("periodo_inicio"),
            periodo_final=p.get("periodo_fim"),
            valor="INFORMADO" if val_inf else "CALCULADO",
            valor_informado=val_inf,
            irpf=inc.get("irpf", False),
            inss=inc.get("cs_inss", True),
            fgts=inc.get("fgts", True),
            tipo_da_base_tabelada=tipo_base,
            base_historicos=base_hist,
            tipo_de_divisor=tipo_div,
            outro_valor_do_divisor=outro_div,
            outro_valor_do_multiplicador=(
                str(fc.get("multiplicador")) if fc.get("multiplicador") else None
            ),
            tipo_da_quantidade=tipo_quant,
            valor_informado_da_quantidade=val_quant,
            dobra_valor_devido=(p.get("exclusoes") or {}).get("dobrar_valor_devido", False),
        )

        # Reflexos: checkbox_painel explícito OU ausente (padrão para Expresso)
        reflexos_verba: list[Verba] = []
        for r in v.get("reflexos", []):
            estrategia_r = r.get("estrategia_reflexa")
            is_checkbox = (
                estrategia_r == "checkbox_painel"
                or (estrategia_r is None and lancamento == "EXPRESSO")
            )
            if is_checkbox:
                r_params_over = r.get("parametros_override") or {}
                r_inc = r_params_over.get("incidencias", inc)
                r_caract = _CARACT_MAP.get(r_params_over.get("caracteristica", "COMUM"), "COMUM")
                r_ocorr = _OCORR_MAP.get(r_params_over.get("ocorrencia_pagamento", "MENSAL"), "MENSAL")
                rp = ParametrosVerba(
                    descricao=r.get("nome", r.get("expresso_reflex_alvo", "")),
                    assuntos_cnj="2581",
                    tipo_de_verba="REFLEXA",
                    caracteristica_verba=r_caract,
                    ocorrencia_pagto=r_ocorr,
                    periodo_inicial=p.get("periodo_inicio"),
                    periodo_final=p.get("periodo_fim"),
                    irpf=r_inc.get("irpf", False) if isinstance(r_inc, dict) else False,
                    inss=r_inc.get("cs_inss", True) if isinstance(r_inc, dict) else True,
                    fgts=r_inc.get("fgts", True) if isinstance(r_inc, dict) else True,
                )
                reflexos_verba.append(Verba(
                    parametros=rp,
                    lancamento="EXPRESSO",
                    expresso_alvo=r.get("expresso_reflex_alvo"),
                ))

        return Verba(
            parametros=params,
            lancamento=lancamento,
            expresso_alvo=v.get("expresso_alvo"),
            reflexos=reflexos_verba,
        )

    verbas = [_converter_verba(v) for v in j.get("verbas_principais", [])]

    # ── FGTS ──────────────────────────────────────────────────────────────
    fgts_j = j.get("fgts", {})
    multa_j = fgts_j.get("multa", {})
    _multa_map = {
        "QUARENTA_POR_CENTO": "MULTA_DE_40",
        "VINTE_POR_CENTO": "MULTA_DE_20",
    }
    fgts = FGTS(
        apurar=True,
        multa_do_fgts=_multa_map.get(multa_j.get("percentual", "QUARENTA_POR_CENTO"), "MULTA_DE_40"),
        multa_do_artigo_467=fgts_j.get("multa_artigo_467", False),
    )

    # ── Honorários ────────────────────────────────────────────────────────
    _BASE_HON_MAP = {
        "BRUTO": "BRUTO",
        "BRUTO_MENOS_CONTRIBUICAO_SOCIAL": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
        "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA":
            "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA",
    }
    _DEVEDOR_MAP = {"RECLAMANTE": "RECLAMANTE", "RECLAMADO": "RECLAMADO"}

    honorarios = []
    for h in j.get("honorarios", []):
        devedor = _DEVEDOR_MAP.get(h["devedor"], "RECLAMADO")
        # credor é o oposto do devedor
        if devedor == "RECLAMADO":
            credor_nome = rec["advogados"][0]["nome"] if rec.get("advogados") else rec["nome"]
            credor_doc_tipo = rec["advogados"][0].get("tipo_doc", "CPF") if rec.get("advogados") else "CPF"
            credor_doc_num  = rec["advogados"][0].get("cpf", "") if rec.get("advogados") else ""
        else:
            credor_nome = recdo["advogados"][0]["nome"] if recdo.get("advogados") else recdo["nome"]
            credor_doc_tipo = "CNPJ"
            credor_doc_num  = recdo["doc_fiscal"]["numero"] or ""

        honorarios.append(Honorario(
            descricao=f"Honorários sucumbenciais — {h['devedor']}",
            tp_honorario="ADVOCATICIOS",
            tipo_de_devedor=devedor,
            tipo_valor="CALCULADO" if h.get("tipo_valor") == "CALCULADO" else "INFORMADO",
            aliquota=str(h["percentual"]).replace(".", ","),
            base_para_apuracao=_BASE_HON_MAP.get(
                h.get("base_apuracao", "BRUTO"), "BRUTO"
            ),
            nome_credor=credor_nome,
            tipo_documento_fiscal_credor=credor_doc_tipo,
            numero_documento_fiscal_credor=credor_doc_num,
            apurar_irrf=True,
        ))

    # ── Contribuição Social ────────────────────────────────────────────────
    contribuicao_social = ContribuicaoSocial()

    # ── Imposto de Renda ─────────────────────────────────────────────────
    ir_j = j.get("imposto_de_renda", {})
    deduc = ir_j.get("deducoes", {})
    imposto_renda = ImpostoRenda(
        apurar=ir_j.get("apurar_irpf", True),
        deduzir_contribuicao_social=deduc.get("contribuicao_social", True),
        deduzir_honorarios_reclamante=deduc.get("honorarios_devidos_pelo_reclamante", True),
        quantidade_dependentes=ir_j.get("quantidade_dependentes", 0),
    )

    # ── Custas Judiciais ─────────────────────────────────────────────────
    custas_j = j.get("custas_judiciais", {})
    _CUSTAS_CONHECIMENTO_MAP = {
        "CALCULADA_2_POR_CENTO": "CALCULADA_2_POR_CENTO",
        "NAO_SE_APLICA": "NAO_SE_APLICA",
        "INFORMADA": "INFORMADA",
    }
    custas = CustasJudiciais(
        reclamado_conhecimento=_CUSTAS_CONHECIMENTO_MAP.get(
            custas_j.get("custas_conhecimento_reclamado", "CALCULADA_2_POR_CENTO"),
            "CALCULADA_2_POR_CENTO",
        ),
    )

    # ── Correção, Juros e Multa ───────────────────────────────────────────
    cj_j = j.get("correcao_juros_multa", {})
    _IDX_MAP = {
        "IPCA_E": "IPCAE", "IPCA": "IPCA", "TR": "TR",
        "INPC": "INPC", "IGP_M": "IGP_M", "SELIC_SIMPLES": "SELIC_SIMPLES",
        "SELIC_COMPOSTA": "SELIC_COMPOSTA", "SEM_CORRECAO": "SEM_CORRECAO",
        "IPCAE": "IPCAE",
    }
    _JUROS_MAP = {
        "TAXA_LEGAL": "TAXA_LEGAL", "TRD_SIMPLES": "TRD_SIMPLES",
        "SELIC_SIMPLES": "SELIC_SIMPLES", "SEM_JUROS": "SEM_JUROS",
        "PADRAO": "JUROS_PADRAO",
    }

    tabelas_adicionais: list[CorrecaoJurosTabelaAdicional] = []
    # Lei 14.905: pós-ajuizamento → TAXA_LEGAL como tabela adicional a partir da data de ajuizamento
    if cj_j.get("lei_14905") and cj_j.get("taxa_juros") == "TAXA_LEGAL":
        data_tl = cj_j.get("data_taxa_legal") or par.get("data_ajuizamento")
        if data_tl:
            tabelas_adicionais.append(CorrecaoJurosTabelaAdicional(
                tabela="TAXA_LEGAL",
                a_partir_de=data_tl,
            ))

    correcao_juros = CorrecaoJuros(
        indice_correcao=_IDX_MAP.get(cj_j.get("indice_correcao", "IPCAE"), "IPCAE"),
        taxa_juros=_JUROS_MAP.get(cj_j.get("taxa_juros", "TRD_SIMPLES"), "TRD_SIMPLES"),
        tabelas_juros_adicionais=tabelas_adicionais,
    )

    # ── Cartão de Ponto ───────────────────────────────────────────────────
    # Opção B: sentença define jornada → apurar via cartão de ponto.
    # Opção A (quantidade informada) não precisa de cartão de ponto.
    cp_j = j.get("cartao_de_ponto") or {}
    if cp_j:
        _CP_TIPO_MAP = {
            "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA":   "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA",
            "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL":   "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL",
            "HORAS_EXTRAS_CONFORME_SUMULA_85":             "HORAS_EXTRAS_CONFORME_SUMULA_85",
            "APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO":       "APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO",
            "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL":  "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL",
            "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL":   "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL",
            "NAO_APURAR_HORAS_EXTRAS":                     "NAO_APURAR_HORAS_EXTRAS",
        }
        apuracao_j = cp_j.get("apuracao") or {}
        jornada_j  = cp_j.get("jornada_padrao") or {}

        def _ddmm_para_mmaa(data_br: str) -> str:
            """DD/MM/AAAA → MM/AAAA (competência)."""
            if data_br and len(data_br) == 10:
                return data_br[3:5] + "/" + data_br[6:]
            return data_br or ""

        cartao_de_ponto = CartaoDePonto(
            apurar=True,
            tipo_apuracao_horas_extras=_CP_TIPO_MAP.get(
                apuracao_j.get("tipo", "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL"),
                "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL",
            ),
            competencia_inicial=_ddmm_para_mmaa(cp_j.get("data_inicial")),
            competencia_final=_ddmm_para_mmaa(cp_j.get("data_final")),
            valor_jornada_segunda=jornada_j.get("segunda_hhmm"),
            valor_jornada_terca=jornada_j.get("terca_hhmm"),
            valor_jornada_quarta=jornada_j.get("quarta_hhmm"),
            valor_jornada_quinta=jornada_j.get("quinta_hhmm"),
            valor_jornada_sexta=jornada_j.get("sexta_hhmm"),
            valor_jornada_sabado=jornada_j.get("sabado_hhmm"),
            valor_jornada_dom=jornada_j.get("domingo_hhmm"),
        )
    else:
        cartao_de_ponto = CartaoDePonto()

    return PreviaCalculo(
        processo=dados_processo,
        historico_salarial=historico,
        verbas=verbas,
        cartao_de_ponto=cartao_de_ponto,
        fgts=fgts,
        contribuicao_social=contribuicao_social,
        imposto_renda=imposto_renda,
        honorarios=honorarios,
        custas=custas,
        correcao_juros=correcao_juros,
    )


# ---------------------------------------------------------------------------
# Testes do conversor (sem Playwright — sempre rodam)
# ---------------------------------------------------------------------------

# JSON v2 importado do módulo de testes estruturais
def _get_json_v2():
    from tests.test_e2e_ficticio import JSON_V2_RICHARLEN
    return JSON_V2_RICHARLEN


class TestConversorJsonV2ParaPrevia:
    """Valida que o conversor produz um PreviaCalculo válido (sem API, sem browser)."""

    @pytest.fixture(scope="class")
    def previa(self):
        return converter_json_v2_para_previa(_get_json_v2())

    def test_previa_instanciada(self, previa):
        from infrastructure.pjecalc_pages import PreviaCalculo
        assert isinstance(previa, PreviaCalculo)

    def test_dados_processo_numero(self, previa):
        assert previa.processo.numero == "0001512"
        assert previa.processo.regiao == "07"

    def test_dados_processo_datas(self, previa):
        assert previa.processo.data_admissao == "02/09/2013"
        assert previa.processo.data_demissao == "01/04/2025"
        assert previa.processo.data_termino_calculo == "31/03/2026"

    def test_historico_3_entradas(self, previa):
        assert len(previa.historico_salarial) == 3
        assert previa.historico_salarial[0].nome == "SALÁRIO REGISTRADO"
        assert previa.historico_salarial[0].valor_para_base_de_calculo == "1.702,14"

    def test_verbas_count(self, previa):
        assert len(previa.verbas) == 7

    def test_he_expresso(self, previa):
        v01 = next(v for v in previa.verbas
                   if "HORA" in v.expresso_alvo.upper() if v.expresso_alvo)
        assert v01.lancamento == "EXPRESSO"
        assert v01.expresso_alvo == "HORAS EXTRAS 50%"

    def test_he_quantidade_mapeada(self, previa):
        """Opção A: quantidade mensal deve ser mapeada para ParametrosVerba."""
        v01 = next(v for v in previa.verbas if v.expresso_alvo == "HORAS EXTRAS 50%")
        assert v01.parametros.tipo_da_quantidade == "INFORMADA"
        assert v01.parametros.valor_informado_da_quantidade == "44,0"  # 44.0 → "44,0" (BR decimal)

    def test_cartao_ponto_nulo_quando_opcao_a(self, previa):
        """Opção A: cartao_de_ponto.apurar deve ser False (JSON sem cartao_de_ponto)."""
        assert previa.cartao_de_ponto.apurar is False

    def test_he_reflexos_checkpoint(self, previa):
        v01 = next(v for v in previa.verbas if v.expresso_alvo == "HORAS EXTRAS 50%")
        # reflexos checkbox_painel devem ter sido convertidos
        assert len(v01.reflexos) == 7

    def test_dano_moral_sem_incidencias(self, previa):
        dm = next(v for v in previa.verbas
                  if "DANO MORAL" in v.expresso_alvo.upper() if v.expresso_alvo)
        assert dm.parametros.irpf is False
        assert dm.parametros.fgts is False
        assert dm.parametros.valor_informado == "15.000,00"

    def test_fgts_multa_40(self, previa):
        assert previa.fgts.multa_do_fgts == "MULTA_DE_40"
        assert previa.fgts.multa_do_artigo_467 is False

    def test_honorarios_dois(self, previa):
        assert len(previa.honorarios) == 2
        rec  = next(h for h in previa.honorarios if h.tipo_de_devedor == "RECLAMADO")
        rte  = next(h for h in previa.honorarios if h.tipo_de_devedor == "RECLAMANTE")
        assert rec.aliquota == "12,9"
        assert rte.aliquota == "2,1"

    def test_correcao_ipcae(self, previa):
        assert previa.correcao_juros.indice_correcao == "IPCAE"

    def test_tabela_adicional_taxa_legal(self, previa):
        tabs = previa.correcao_juros.tabelas_juros_adicionais
        assert len(tabs) >= 1
        assert tabs[0].tabela == "TAXA_LEGAL"
        assert "2024" in (tabs[0].a_partir_de or "") or "2025" in (tabs[0].a_partir_de or "")


# ---------------------------------------------------------------------------
# E2E Playwright — automação completa contra TRT7
# ---------------------------------------------------------------------------

@e2e
class TestE2EAutomacaoCompleta:
    """
    Roda a automação completa:
      JSON v2 Richarlen → PreviaCalculo → AplicadorPJECalc.aplicar() →
      liquidar → exportar → salva .PJC em /tmp/pjecalc_testes/

    ATENÇÃO: cria um cálculo REAL no TRT7. Usar dados claramente fictícios
    (número de processo inexistente) para facilitar identificação e limpeza.
    """

    @pytest.fixture(scope="class")
    def browser_ctx(self):
        import shutil
        import tempfile
        from playwright.sync_api import sync_playwright

        src = Path(FIREFOX_PROFILE)
        if not src.exists():
            pytest.skip(f"Perfil Firefox não encontrado: {FIREFOX_PROFILE}")

        # Copia perfil para tmpdir para não conflitar com Firefox aberto
        tmp = tempfile.mkdtemp(prefix="pjecalc_e2e_profile_")
        shutil.copytree(str(src), tmp, dirs_exist_ok=True)
        # Remove lock e arquivos de compatibilidade (versão do perfil != Playwright Firefox)
        for f in (".parentlock", "lock", "compatibility.ini"):
            p = Path(tmp) / f
            if p.exists():
                p.unlink()

        try:
            with sync_playwright() as pw:
                ctx = pw.firefox.launch_persistent_context(
                    user_data_dir=tmp,
                    headless=True,
                    slow_mo=60,
                )
                yield ctx
                ctx.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @pytest.fixture(scope="class")
    def page(self, browser_ctx):
        p = browser_ctx.new_page()
        p.goto(PJECALC_URL, timeout=30000)
        p.wait_for_load_state("networkidle", timeout=20000)
        if "logon" in p.url or "login" in p.url:
            pytest.skip(
                "Sessão TRT7 expirada — faça login no Firefox e execute novamente."
            )
        return p

    @pytest.fixture(scope="class")
    def previa(self):
        return converter_json_v2_para_previa(_get_json_v2())

    @pytest.fixture(scope="class")
    def aplicador(self, page):
        from core.aplicador import AplicadorPJECalc
        logs: list[str] = []

        def log_cb(msg: str) -> None:
            print(f"  [APLIC] {msg}")
            logs.append(msg)

        ap = AplicadorPJECalc(page=page, base_url=PJECALC_URL, log_cb=log_cb)
        ap._logs = logs
        return ap

    # ── Fase 1: autenticação ──────────────────────────────────────────────

    def test_01_pjecalc_acessivel(self, page):
        assert "pjecalc" in page.url.lower() or "principal" in page.url.lower(), (
            f"PJE-Calc não carregou: {page.url}"
        )
        print(f"\n  URL: {page.url}")

    # ── Fase 2: dados do processo ─────────────────────────────────────────

    def test_02_dados_processo(self, page, aplicador, previa):
        ok = aplicador.aplicar_dados_processo(previa.processo)
        assert ok, f"aplicar_dados_processo falhou.\n" + "\n".join(aplicador._logs[-20:])
        print(f"\n  URL após Phase 1: {page.url}")

    def test_03_edit_mode_ativo(self, page):
        """Após Phase 1 + save, menu lateral deve mostrar seções."""
        edit_mode = page.evaluate("""() => {
            const ids = [...document.querySelectorAll('li[id^="li_calculo_"]')]
                .map(li => li.id);
            return {
                ids: ids,
                edit: ids.some(id => /li_calculo_(ferias|historico|verbas|fgts)/.test(id))
            };
        }""")
        print(f"\n  li_calculo_* IDs: {edit_mode['ids'][:6]}")
        assert edit_mode["edit"], (
            "FALHA: create-mode após Phase 1. "
            "_reabrir_calculo_recentes não funcionou.\n"
            f"IDs: {edit_mode['ids']}"
        )

    # ── Fase 3: histórico salarial ────────────────────────────────────────

    def test_04_historico_salarial(self, page, aplicador, previa):
        ok = aplicador.aplicar_historico_salarial(previa.historico_salarial)
        assert ok, "aplicar_historico_salarial falhou.\n" + "\n".join(aplicador._logs[-20:])
        print(f"\n  URL após Hist.Salarial: {page.url}")

    # ── Fase 4: FGTS ─────────────────────────────────────────────────────

    def test_05_fgts(self, page, aplicador, previa):
        ok = aplicador.aplicar_fgts(previa.fgts)
        assert ok, "aplicar_fgts falhou.\n" + "\n".join(aplicador._logs[-20:])

    # ── Fase 5: Contribuição Social ───────────────────────────────────────

    def test_06_inss(self, page, aplicador, previa):
        ok = aplicador.aplicar_inss(previa.contribuicao_social)
        assert ok, "aplicar_inss falhou.\n" + "\n".join(aplicador._logs[-20:])

    # ── Fase 6: Imposto de Renda ──────────────────────────────────────────

    def test_07_irpf(self, page, aplicador, previa):
        ok = aplicador.aplicar_irpf(previa.imposto_renda)
        assert ok, "aplicar_irpf falhou.\n" + "\n".join(aplicador._logs[-20:])

    # ── Fase 7: Honorários ────────────────────────────────────────────────

    def test_08_honorarios(self, page, aplicador, previa):
        ok = aplicador.aplicar_honorarios(previa.honorarios)
        assert ok, "aplicar_honorarios falhou.\n" + "\n".join(aplicador._logs[-20:])

    # ── Fase 8: Custas ────────────────────────────────────────────────────

    def test_09_custas(self, page, aplicador, previa):
        ok = aplicador.aplicar_custas(previa.custas)
        assert ok, "aplicar_custas falhou.\n" + "\n".join(aplicador._logs[-20:])

    # ── Fase 9: Correção e Juros ──────────────────────────────────────────

    def test_10_correcao_juros(self, page, aplicador, previa):
        ok = aplicador.aplicar_correcao_juros(previa.correcao_juros)
        assert ok, "aplicar_correcao_juros falhou.\n" + "\n".join(aplicador._logs[-20:])

    # ── Fase 10: Verbas (por último — Expresso reseta conv Seam) ─────────

    def test_11_verbas(self, page, aplicador, previa):
        ok = aplicador.aplicar_verbas(previa.verbas)
        assert ok, "aplicar_verbas falhou.\n" + "\n".join(aplicador._logs[-20:])
        print(f"\n  URL após Verbas: {page.url}")

    # ── Fase 11: Liquidar + Exportar ─────────────────────────────────────

    def test_12_liquidar_e_exportar(self, page, aplicador):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        pjc_bytes = aplicador.liquidar_e_exportar()

        assert pjc_bytes is not None, (
            "liquidar_e_exportar retornou None — "
            "verificar logs de liquidação:\n" + "\n".join(aplicador._logs[-30:])
        )

        # Validar que é um ZIP (PJC = ZIP com XML interno)
        assert pjc_bytes[:2] == b"PK", (
            f"Bytes inválidos — esperado ZIP (PK), obtido: {pjc_bytes[:4]!r}"
        )
        assert len(pjc_bytes) > 10_000, (
            f"Arquivo muito pequeno ({len(pjc_bytes)} bytes) — "
            "provavelmente é um pré-liquidação. PJC válido tem > 10KB."
        )

        # Salvar no disco
        out_path = OUTPUT_DIR / f"richarlen_{int(time.time())}.pjc"
        out_path.write_bytes(pjc_bytes)
        print(f"\n  ✓ .PJC salvo: {out_path} ({len(pjc_bytes):,} bytes)")

        # Inspecionar XML interno
        import zipfile, io
        with zipfile.ZipFile(io.BytesIO(pjc_bytes)) as zf:
            nomes = zf.namelist()
            print(f"  Arquivos no ZIP: {nomes}")
            assert any(n.endswith(".xml") or "calculo" in n.lower() for n in nomes), (
                f"ZIP não contém XML de cálculo: {nomes}"
            )

    # ── Resumo ────────────────────────────────────────────────────────────

    def test_13_resumo_logs(self, aplicador):
        """Imprime todos os logs da automação."""
        print("\n=== LOGS COMPLETOS DA AUTOMAÇÃO ===")
        for i, msg in enumerate(aplicador._logs, 1):
            print(f"  {i:03d}. {msg}")
        print("===================================")
        # Verificar que não houve falha crítica nos logs
        falhas = [m for m in aplicador._logs if "FALHA" in m.upper() or "ERRO" in m.upper()]
        if falhas:
            print(f"  AVISOS: {len(falhas)} mensagens de erro/falha detectadas")
            for f in falhas[-5:]:
                print(f"  → {f}")
