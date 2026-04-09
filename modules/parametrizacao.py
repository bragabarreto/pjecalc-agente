# modules/parametrizacao.py — Camada de Parametrização (Cérebro do Pipeline)
# Converte o JSON extraído pela extraction.py → parametrizacao.json
# consumido pela automação Playwright e pela prévia HTML.
#
# Posição no pipeline:
#   extraction.py → [ESTE MÓDULO] → playwright_pjecalc.py
#
# Baseado na skill pjecalc-parametrizacao (cérebro da liquidação).

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ── Tabela de verbas: tipo_verba → configuração PJE-Calc ─────────────────────
# Fonte: skill pjecalc-parametrizacao / references/verbas_map.md

_VERBAS_EXPRESSO: dict[str, dict] = {
    # Rescisórias
    "saldo_salario":              {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True},
    "aviso_previo_indenizado":    {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True,
                                   "reflexas": ["decimo_terceiro_proporcional"]},
    "aviso_previo_trabalhado":    {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True},
    "decimo_terceiro_proporcional": {"lancamento": "EXPRESSO", "incide_fgts": True, "incide_inss": True, "incide_ir": True},
    "13_salario_proporcional":    {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True},
    "13_salario_integral":        {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True},
    "ferias_proporcionais":       {"lancamento": "EXPRESSO", "incide_fgts": False, "incide_inss": True,  "incide_ir": True},
    "ferias_vencidas":            {"lancamento": "EXPRESSO", "incide_fgts": False, "incide_inss": True,  "incide_ir": True},
    "terco_constitucional_ferias": {"lancamento": "EXPRESSO", "incide_fgts": False, "incide_inss": True, "incide_ir": True},
    "multa_art_477_clt":          {"lancamento": "EXPRESSO", "incide_fgts": False, "incide_inss": False, "incide_ir": False},
    # Jornada
    "horas_extras":               {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True,
                                   "reflexas": ["dsr", "decimo_terceiro_proporcional", "ferias_proporcionais"]},
    "horas_extras_50":            {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True,
                                   "reflexas": ["dsr", "decimo_terceiro_proporcional", "ferias_proporcionais"]},
    "horas_extras_100":           {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True,
                                   "reflexas": ["dsr", "decimo_terceiro_proporcional", "ferias_proporcionais"]},
    "adicional_noturno":          {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True,
                                   "reflexas": ["dsr", "decimo_terceiro_proporcional", "ferias_proporcionais"]},
    "descanso_semanal_remunerado": {"lancamento": "EXPRESSO", "incide_fgts": True, "incide_inss": True,  "incide_ir": True},
    # Adicionais
    "adicional_insalubridade":    {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True,
                                   "reflexas": ["decimo_terceiro_proporcional", "ferias_proporcionais"]},
    "adicional_periculosidade":   {"lancamento": "EXPRESSO", "incide_fgts": True,  "incide_inss": True,  "incide_ir": True,
                                   "reflexas": ["decimo_terceiro_proporcional", "ferias_proporcionais"]},
    # Indenizatórias (sem incidências)
    "indenizacao_danos_morais":   {"lancamento": "EXPRESSO", "incide_fgts": False, "incide_inss": False, "incide_ir": False},
    "indenizacao_danos_materiais": {"lancamento": "EXPRESSO", "incide_fgts": False, "incide_inss": False, "incide_ir": False},
    "fgts_depositos_nao_recolhidos": {"lancamento": "EXPRESSO", "incide_fgts": False, "incide_inss": False, "incide_ir": False},
}

# Nomes alternativos (aliases) para resolver terminologia variada das sentenças
_ALIASES: dict[str, str] = {
    "horas extraordinárias": "horas_extras",
    "labor extraordinário": "horas_extras",
    "sobrejornada": "horas_extras",
    "he": "horas_extras",
    "décimo terceiro": "decimo_terceiro_proporcional",
    "gratificação natalina": "decimo_terceiro_proporcional",
    "13o": "decimo_terceiro_proporcional",
    "férias proporcionais + 1/3": "ferias_proporcionais",
    "férias vencidas + 1/3": "ferias_vencidas",
    "férias + 1/3": "ferias_proporcionais",
    "aviso indenizado": "aviso_previo_indenizado",
    "ap indenizado": "aviso_previo_indenizado",
    "insalubridade": "adicional_insalubridade",
    "labor insalubre": "adicional_insalubridade",
    "periculosidade": "adicional_periculosidade",
    "dano moral": "indenizacao_danos_morais",
    "danos morais": "indenizacao_danos_morais",
    "indenização moral": "indenizacao_danos_morais",
    "multa rescisória": "fgts_multa_40",
    "multa de 40%": "fgts_multa_40",
    "40% fgts": "fgts_multa_40",
    "multa 477": "multa_art_477_clt",
    "diferenças salariais": "diferencas_salariais",
    "repouso semanal": "descanso_semanal_remunerado",
    "dsr": "descanso_semanal_remunerado",
}


def _normalizar_tipo_verba(nome: str | None) -> str:
    """Normaliza o tipo de verba para correspondência com _VERBAS_EXPRESSO."""
    if not nome:
        return ""
    chave = nome.lower().strip().replace(" ", "_").replace("-", "_")
    return _ALIASES.get(nome.lower().strip(), chave)


def _parse_data(d: str | None) -> date | None:
    if not d:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d, fmt).date()
        except ValueError:
            pass
    return None


# ── Passos de parametrização ─────────────────────────────────────────────────

def _passo_dados_processo(dados: dict) -> dict:
    proc = dados.get("processo", {})
    cont = dados.get("contrato", {})
    return {
        "numero_processo": proc.get("numero"),
        "vara": proc.get("vara"),
        "estado": proc.get("estado"),
        "municipio": proc.get("municipio"),
        "reclamante_nome": proc.get("reclamante") or cont.get("reclamante"),
        "reclamante_cpf": proc.get("cpf_reclamante"),
        "reclamada_nome": proc.get("reclamado") or cont.get("reclamado"),
        "reclamada_cnpj": proc.get("cnpj_reclamado"),
        "data_admissao": cont.get("admissao"),
        "data_demissao": cont.get("demissao"),
        "motivo_rescisao": cont.get("tipo_rescisao"),
        "maior_remuneracao": cont.get("maior_remuneracao") or cont.get("ultima_remuneracao"),
        "data_ajuizamento": cont.get("ajuizamento"),
    }


def _passo_parametros_gerais(dados: dict) -> dict:
    cont = dados.get("contrato", {})
    presc = dados.get("prescricao", {})

    ajuizamento = _parse_data(cont.get("ajuizamento"))
    data_inicial = None
    if ajuizamento:
        # Prescrição quinquenal: 5 anos antes do ajuizamento
        try:
            data_inicial = ajuizamento.replace(year=ajuizamento.year - 5)
        except ValueError:
            data_inicial = ajuizamento - timedelta(days=5 * 365)

    jornada_diaria = cont.get("jornada_diaria") or 8
    jornada_semanal = cont.get("jornada_semanal") or 44

    return {
        "prescricao_quinquenal": presc.get("quinquenal", True),
        "prescricao_fgts": presc.get("fgts", True),
        "data_inicial_apuracao": data_inicial.strftime("%d/%m/%Y") if data_inicial else None,
        "data_final_apuracao": cont.get("demissao"),
        "carga_horaria_diaria": jornada_diaria,
        "carga_horaria_semanal": jornada_semanal,
        "zerar_valores_negativos": True,
    }


def _passo_historico_salarial(dados: dict) -> list[dict]:
    historico = dados.get("historico_salarial", [])
    if not historico:
        return []
    return [
        {
            "nome": "Salário Base",
            "tipo": "FIXO",
            "periodos": [
                {
                    "data_inicio": h.get("data_inicio"),
                    "data_fim": h.get("data_fim"),
                    "valor": h.get("valor"),
                }
                for h in historico
            ],
            "incide_fgts": True,
            "incide_inss": True,
        }
    ]


def _passo_verbas(dados: dict) -> list[dict]:
    """
    Mapeia verbas_deferidas para o formato do PJE-Calc,
    decidindo Lançamento Expresso vs Manual para cada verba.
    """
    resultado = []
    for v in dados.get("verbas_deferidas", []):
        tipo = _normalizar_tipo_verba(v.get("tipo") or v.get("nome_sentenca"))
        config = _VERBAS_EXPRESSO.get(tipo, {})

        # Verba com valor fixado na sentença → Manual
        tem_valor_fixo = v.get("valor") is not None and float(v.get("valor", 0)) > 0
        lancamento = config.get("lancamento", "MANUAL")
        if tem_valor_fixo and lancamento == "EXPRESSO":
            lancamento = "MANUAL"  # sentença fixou valor — não calcular

        resultado.append({
            "nome_sentenca": v.get("nome_sentenca"),
            "nome_pjecalc": v.get("nome_sentenca"),  # será mapeado pelo classification.py
            "tipo": v.get("tipo"),
            "lancamento": lancamento,
            "caracteristica": v.get("caracteristica"),
            "ocorrencia": v.get("ocorrencia"),
            "base_calculo": v.get("base_calculo"),
            "incide_fgts": v.get("incidencia_fgts", config.get("incide_fgts", True)),
            "incide_inss": v.get("incidencia_inss", config.get("incide_inss", True)),
            "incide_ir": v.get("incidencia_ir", config.get("incide_ir", True)),
            "quantidade": v.get("quantidade"),
            "valor": v.get("valor"),
            "reflexas": config.get("reflexas", []),
            "confianca": v.get("confianca", 1.0),
        })
    return resultado


def _passo_fgts(dados: dict) -> dict:
    fgts = dados.get("fgts", {})
    return {
        "aliquota": fgts.get("aliquota", 0.08),
        "multa_40": fgts.get("multa_40", False),
        "multa_20": fgts.get("multa_20", False),
        "multa_467": fgts.get("multa_467", False),
        "depositos_nao_efetuados": fgts.get("depositos_nao_efetuados", False),
    }


def _passo_correcao_juros(dados: dict) -> dict:
    """
    Aplica regra ADC 58/STF: IPCA-E pré-judicial + SELIC judicial.
    Detecta réu público via nome da reclamada (heurística básica).
    """
    cj = dados.get("correcao_juros", {})
    proc = dados.get("processo", {})
    reclamada = (proc.get("reclamado") or "").lower()

    fazenda_publica = any(
        kw in reclamada
        for kw in ["estado", "município", "municip", "prefeitura", "governo",
                   "secretaria", "autarquia", "fundação", "ipesp", "iprem"]
    )

    if cj:
        return {**cj, "fazenda_publica": fazenda_publica}

    # Configuração padrão ADC 58 — ente privado
    return {
        "fazenda_publica": fazenda_publica,
        "fase_pre_judicial": "IPCA_E",
        "juros_pre_judicial": "1_PORCENTO_AM",
        "fase_judicial": "SELIC_SIMPLES",
        "juros_judicial": "SELIC_RECEITA_FEDERAL",
        "_alerta": "Configuração ADC 58 aplicada automaticamente — verificar se o juízo adotou esta abordagem.",
    }


def _gerar_alertas(dados: dict) -> list[str]:
    """Gera alertas para revisão humana."""
    alertas: list[str] = list(dados.get("alertas", []))

    cont = dados.get("contrato", {})
    tipo_rescisao = cont.get("tipo_rescisao", "")
    verbas = dados.get("verbas_deferidas", [])

    # Campos com baixa confiança
    from modules.extraction import ValidadorSentenca
    incertos = ValidadorSentenca.itens_baixa_confianca(dados, threshold=0.70)
    for i in incertos:
        alertas.append(f"Baixa confiança em {i['secao']} ({i['confianca']:.0%}) — revisar antes de confirmar.")

    # Inconsistências rescisão × verbas
    nomes_verbas = [v.get("nome_sentenca", "").lower() for v in verbas]
    if tipo_rescisao == "justa_causa":
        if any("multa" in n and "40" in n for n in nomes_verbas):
            alertas.append("INCONSISTÊNCIA: Justa causa com multa 40% FGTS — verificar sentença.")
        if any("aviso prévio indenizado" in n for n in nomes_verbas):
            alertas.append("INCONSISTÊNCIA: Justa causa com aviso prévio indenizado — verificar sentença.")

    # Dano moral sem verificação de data
    if any("dano moral" in n or "danos morais" in n for n in nomes_verbas):
        alertas.append(
            "Dano moral presente: verificar data de arbitramento para SELIC (Súmula 439 TST)."
        )

    # Honorários com base ambígua
    honorarios = dados.get("honorarios", [])
    if isinstance(honorarios, list):
        for h in honorarios:
            if isinstance(h, dict) and not h.get("base_apuracao"):
                alertas.append("Honorários sem base de apuração definida — preencher na prévia.")

    # FGTS com multa diferente de 40%
    fgts = dados.get("fgts", {})
    if fgts.get("multa_percentual") and fgts.get("multa_percentual") not in (0.40, 40, 0.20, 20):
        alertas.append(
            f"FGTS com multa {fgts.get('multa_percentual')} — verificar culpa recíproca ou caso especial."
        )

    # Correção monetária: alertar sobre divergência entre TRTs
    if not dados.get("correcao_juros", {}).get("tabela_determinada_sentenca"):
        alertas.append(
            "Correção pós-ADC 58: configuração IPCA-E + SELIC aplicada automaticamente. "
            "Verificar se o TRT regional adota esta abordagem específica."
        )

    return alertas


# ── Função principal ──────────────────────────────────────────────────────────

def gerar_parametrizacao(dados: dict) -> dict:
    """
    Converte output de extraction.py → parametrizacao.json.

    Este é o 'cérebro' do pipeline — transforma dados brutos extraídos da sentença
    em instruções precisas de preenchimento para cada módulo do PJE-Calc.

    Segue o schema da skill pjecalc-parametrizacao.
    """
    return {
        "meta": {
            "modo_calculo": "NOVO",
            "versao": "1.0",
        },
        "passo_1_dados_processo":   _passo_dados_processo(dados),
        "passo_2_parametros_gerais": _passo_parametros_gerais(dados),
        "passo_3_historico_salarial": _passo_historico_salarial(dados),
        "passo_5_verbas":            _passo_verbas(dados),
        "passo_6_fgts":              _passo_fgts(dados),
        "passo_7_contribuicao_social": dados.get("contribuicao_social", {}),
        "passo_8_imposto_renda":     dados.get("imposto_renda", {}),
        "passo_9_correcao_juros":    _passo_correcao_juros(dados),
        "passo_10_honorarios":       dados.get("honorarios", []),
        "passo_11_custas_judiciais": dados.get("custas_judiciais", {}),
        "alertas":                   _gerar_alertas(dados),
    }
