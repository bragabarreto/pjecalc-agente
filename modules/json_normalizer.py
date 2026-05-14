"""Normalização de JSON legacy → schema v2 canônico.

Converte JSONs gerados por versões anteriores do prompt (Projeto Claude
Externo) para o formato canônico definido em ``docs/schema-v2/99-pydantic-models.py``.

Tratamentos cobertos (todos idempotentes — aplicar em JSON já canônico é no-op):

1. FGTS multa ``NAO_APURAR`` → ``ativa=false`` + ``CALCULADA/QUARENTA_POR_CENTO``
2. FGTS multa ``percentual=null`` → ``QUARENTA_POR_CENTO``
3. ``recolhimentos_existentes`` legacy (competencia/valor/observacao) → schema canônico
4. Honorários: traduz valores legacy do campo ``tipo`` para o enum ``tipo_honorario``
5. Honorários: traduz ``base_apuracao`` legacy ("BRUTO"/"LIQUIDO") para enum canônico
6. Correção/juros: ``IPCA_E``/``IPCA-E`` → ``IPCAE``
7. Datas ``MM/YYYY`` em ``parametros_calculo.data_inicio_calculo/data_termino_calculo``
   → ``DD/MM/YYYY``
"""
from __future__ import annotations

import calendar
import copy
from typing import Any


def _norm_fgts(fgts: dict[str, Any], *, parametros: dict | None = None) -> dict[str, Any]:
    multa = fgts.get("multa")
    if isinstance(multa, dict):
        tv = multa.get("tipo_valor")
        if tv == "NAO_APURAR":
            multa["ativa"] = False
            multa["tipo_valor"] = "CALCULADA"
            if not multa.get("percentual"):
                multa["percentual"] = "QUARENTA_POR_CENTO"
        if multa.get("percentual") is None:
            multa["percentual"] = "QUARENTA_POR_CENTO"

    recs = fgts.get("recolhimentos_existentes")
    if isinstance(recs, list):
        nrecs = []
        for r in recs:
            if not isinstance(r, dict):
                nrecs.append(r)
                continue
            nr = dict(r)
            # competencia (single) → competencia_inicio/fim
            if "competencia" in nr and "competencia_inicio" not in nr:
                nr["competencia_inicio"] = nr.pop("competencia")
                nr.setdefault("competencia_fim", nr["competencia_inicio"])
            # valor → valor_total_depositado_brl
            if "valor" in nr and "valor_total_depositado_brl" not in nr and "valor_depositado_brl" not in nr:
                nr["valor_total_depositado_brl"] = nr.pop("valor")
            # observacao → descricao
            if "observacao" in nr and "descricao" not in nr:
                nr["descricao"] = nr.pop("observacao")
            nr.setdefault("tipo", "DEPOSITO_REGULAR")
            nrecs.append(nr)
        fgts["recolhimentos_existentes"] = nrecs

    # Saldo a deduzir: se o JSON tem recolhimentos mas não tem saldos_a_deduzir,
    # auto-gerar a partir do total dos recolhimentos.
    # Usuário documentou (12/05/2026): a verba Expresso "VALOR PAGO" estava
    # representando incorretamente o saldo FGTS depositado. A forma certa é
    # preencher a seção "Saldo e/ou Saque" da página FGTS.
    saldos = fgts.get("saldos_a_deduzir")
    if not saldos and fgts.get("recolhimentos_existentes"):
        total = sum(
            r.get("valor_total_depositado_brl", 0) or 0
            for r in fgts["recolhimentos_existentes"]
            if isinstance(r, dict)
        )
        if total > 0:
            # Data: usar data_demissao se disponível, senão hoje
            data_extrato = None
            if parametros and isinstance(parametros, dict):
                data_extrato = parametros.get("data_demissao")
            if not data_extrato:
                from datetime import date as _date
                data_extrato = _date.today().strftime("%d/%m/%Y")
            fgts["saldos_a_deduzir"] = [{"data": data_extrato, "valor_brl": round(total, 2)}]
            fgts["deduzir_do_fgts"] = True
    return fgts


# PJE-Calc TipoHonorarioEnum (descoberto via javap em pjecalc-negocio-2.14.0.jar):
#   ADVOCATICIOS, ASSISTENCIAIS, CONTRATUAIS, PERICIAIS_CONTADOR,
#   PERICIAIS_DOCUMENTOSCOPIO, PERICIAIS_ENGENHEIRO, PERICIAIS_INTERPRETE,
#   PERICIAIS_MEDICO, PERICIAIS_OUTROS, SUCUMBENCIAIS, LEILOEIRO
# Mapeamos valores legacy do agente externo para o nome canônico do PJE-Calc.
_TIPO_HONORARIO_MAP = {
    # Sucumbenciais
    "SUCUMBENCIAIS": "SUCUMBENCIAIS",
    "SUCUMBENCIAL": "SUCUMBENCIAIS",
    "ADVOCATICIO_SUCUMBENCIAL": "SUCUMBENCIAIS",
    "ADVOCATICIOS_SUCUMBENCIAIS": "SUCUMBENCIAIS",
    # Contratuais
    "CONTRATUAIS": "CONTRATUAIS",
    "CONTRATUAL": "CONTRATUAIS",
    "ADVOCATICIO_CONTRATUAIS": "CONTRATUAIS",
    "ADVOCATICIOS_CONTRATUAIS": "CONTRATUAIS",
    # Advocatícios genéricos
    "ADVOCATICIOS": "ADVOCATICIOS",
    "ADVOCATICIO": "ADVOCATICIOS",
    # Periciais
    "PERICIAIS": "PERICIAIS_OUTROS",
    "PERICIAL": "PERICIAIS_OUTROS",
    "PERICIAIS_OUTROS": "PERICIAIS_OUTROS",
    "PERICIAIS_CONTADOR": "PERICIAIS_CONTADOR",
    "PERICIAIS_MEDICO": "PERICIAIS_MEDICO",
    "PERICIAIS_ENGENHEIRO": "PERICIAIS_ENGENHEIRO",
    "PERICIAIS_INTERPRETE": "PERICIAIS_INTERPRETE",
    "PERICIAIS_DOCUMENTOSCOPIO": "PERICIAIS_DOCUMENTOSCOPIO",
    # Outros
    "ASSISTENCIAIS": "ASSISTENCIAIS",
    "LEILOEIRO": "LEILOEIRO",
}

# PJE-Calc BaseParaApuracaoDeHonorarioEnum (extraído via javap):
#   BRUTO, BRUTO_MENOS_CONTRIBUICAO_SOCIAL,
#   BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA,
#   VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL.
# Nota: BRUTO_DEVIDO_AO_RECLAMANTE é para Custas, NÃO para Honorários.
_BASE_APURACAO_MAP = {
    "BRUTO": "BRUTO",
    "BRUTO_DEVIDO_AO_RECLAMANTE": "BRUTO",  # legacy alias
    "LIQUIDO": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
    "LIQUIDO_DEVIDO_AO_RECLAMANTE": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
    "BRUTO_MENOS_CS": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
    "BRUTO_MENOS_CS_MENOS_PP": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA",
    "SOBRE_O_VALOR_DA_CAUSA": "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
}


def _norm_honorario(h: dict[str, Any], *, processo: dict | None = None) -> dict[str, Any]:
    # Normalizar tipo_honorario/tipo para enum canônico do PJE-Calc
    # (independe de se veio com alias "tipo" ou explicito "tipo_honorario").
    for key in ("tipo_honorario", "tipo"):
        if key in h:
            val = h[key]
            if isinstance(val, str) and val in _TIPO_HONORARIO_MAP:
                h[key] = _TIPO_HONORARIO_MAP[val]
    for key in ("base_para_apuracao", "base_apuracao"):
        if key in h:
            val = h[key]
            if isinstance(val, str) and val in _BASE_APURACAO_MAP:
                h[key] = _BASE_APURACAO_MAP[val]

    # Auto-credor: PJE-Calc exige nome+doc do credor obrigatório.
    # Se ausente, gerar a partir do oposto do devedor:
    #   devedor=RECLAMADO → credor = reclamante
    #   devedor=RECLAMANTE → credor = reclamado
    if not h.get("credor") and processo:
        devedor = h.get("tipo_devedor") or h.get("devedor")
        if devedor == "RECLAMADO":
            parte = processo.get("reclamante", {})
        elif devedor in ("RECLAMANTE", "RECLAMANTE_ARCADO_PELA_UNIAO"):
            parte = processo.get("reclamado", {})
        else:
            parte = None
        if parte and parte.get("nome"):
            df = parte.get("doc_fiscal") or {}
            h["credor"] = {
                "nome": parte["nome"],
                "doc_fiscal_tipo": df.get("tipo", "CPF"),
                "doc_fiscal_numero": df.get("numero", ""),
            }
    return h


def _norm_correcao(c: dict[str, Any]) -> dict[str, Any]:
    idx = c.get("indice_trabalhista")
    if isinstance(idx, str) and idx in ("IPCA_E", "IPCA-E"):
        c["indice_trabalhista"] = "IPCAE"
    return c


def _norm_data(s: str, *, is_fim: bool) -> str:
    """Normaliza MM/YYYY → DD/MM/YYYY. Mantém valor se já estiver em DD/MM/YYYY."""
    if not isinstance(s, str):
        return s
    if len(s) == 7 and s[2] == "/":
        try:
            mm = int(s[:2])
            yyyy = int(s[3:])
            if is_fim:
                last_day = calendar.monthrange(yyyy, mm)[1]
                return f"{last_day:02d}/{mm:02d}/{yyyy}"
            return f"01/{mm:02d}/{yyyy}"
        except (ValueError, TypeError):
            return s
    return s


def _norm_parametros(p: dict[str, Any]) -> dict[str, Any]:
    if "data_inicio_calculo" in p:
        p["data_inicio_calculo"] = _norm_data(p["data_inicio_calculo"], is_fim=False)
    if "data_termino_calculo" in p:
        p["data_termino_calculo"] = _norm_data(p["data_termino_calculo"], is_fim=True)

    # Validação cruzada: data_inicio_calculo deve ser >= data_admissao
    # (regra do PJE-Calc). Se não for, usar data_admissao como início.
    # Caso típico: usuário especificou MM/YYYY (ex: "08/2023") que virou
    # 01/08/2023 mas admissão foi 04/08/2023.
    adm = p.get("data_admissao")
    ini = p.get("data_inicio_calculo")
    if isinstance(adm, str) and isinstance(ini, str) and len(adm) == 10 and len(ini) == 10:
        try:
            from datetime import datetime as _dt
            d_adm = _dt.strptime(adm, "%d/%m/%Y")
            d_ini = _dt.strptime(ini, "%d/%m/%Y")
            if d_ini < d_adm:
                p["data_inicio_calculo"] = adm
        except ValueError:
            pass

    # Validação cruzada: prescrição quinquenal só é possível se período
    # entre admissão e ajuizamento for >= 5 anos.
    if p.get("prescricao_quinquenal") and isinstance(adm, str) and len(adm) == 10:
        aj = p.get("data_ajuizamento")
        if isinstance(aj, str) and len(aj) == 10:
            try:
                from datetime import datetime as _dt
                d_adm2 = _dt.strptime(adm, "%d/%m/%Y")
                d_aj = _dt.strptime(aj, "%d/%m/%Y")
                anos = (d_aj - d_adm2).days / 365.25
                if anos < 5:
                    p["prescricao_quinquenal"] = False
            except ValueError:
                pass

    # Validação cruzada: data_termino_calculo deve ser <= data_demissao + (projeção AP)
    # Quando projeta_aviso_indenizado=True, o cálculo legitimamente vai ALÉM
    # da data_demissao, até demissao + dias projetados (até 90 dias na Lei
    # 12.506/2011). NÃO comprimir nesse caso.
    # Quando projeta_aviso_indenizado=False, limitar a data_demissao + 90 dias
    # como safety (não exatamente demissao — alguns JSONs usam datas com
    # aviso prévio embutido).
    dem = p.get("data_demissao")
    fim = p.get("data_termino_calculo")
    projeta_ap = p.get("projeta_aviso_indenizado", False)
    if isinstance(dem, str) and isinstance(fim, str) and len(dem) == 10 and len(fim) == 10:
        try:
            from datetime import datetime as _dt, timedelta as _td
            d_dem = _dt.strptime(dem, "%d/%m/%Y")
            d_fim = _dt.strptime(fim, "%d/%m/%Y")
            # Lei 12.506/2011: até 90 dias de aviso prévio (30 base + 60 prop)
            # Margem de segurança: 100 dias para acomodar avos arredondados
            margem_max = _td(days=100 if projeta_ap else 100)
            limite = d_dem + margem_max
            if d_fim > limite:
                p["data_termino_calculo"] = dem  # comprimir ao demissao em caso extremo
        except ValueError:
            pass
    return p


def normalize_v2_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Normaliza JSON v2 legacy para o formato canônico.

    Idempotente: aplicar várias vezes não muda o resultado. Não muta o
    payload original — retorna deep-copy normalizado.
    """
    if not isinstance(payload, dict):
        return payload
    data = copy.deepcopy(payload)

    # 1. Parâmetros — datas MM/YYYY
    if isinstance(data.get("parametros_calculo"), dict):
        data["parametros_calculo"] = _norm_parametros(data["parametros_calculo"])

    # 2. FGTS — multa + recolhimentos + saldo a deduzir
    if isinstance(data.get("fgts"), dict):
        params = data.get("parametros_calculo")
        data["fgts"] = _norm_fgts(data["fgts"], parametros=params if isinstance(params, dict) else None)

    # 2b. Filtrar verbas Expresso que representam SALDO FGTS (errôneamente
    # classificadas como verba). O agente externo às vezes coloca o saldo a
    # deduzir como verba 'VALOR PAGO - NÃO TRIBUTÁVEL' (Expresso), mas isso é
    # incorreto — o saldo deve ir em fgts.saldos_a_deduzir, não como verba.
    # Detectamos pelo nome_pjecalc + presence de recolhimentos no fgts.
    verbas = data.get("verbas_principais")
    if isinstance(verbas, list) and data.get("fgts", {}).get("saldos_a_deduzir"):
        novas_verbas = []
        for v in verbas:
            if isinstance(v, dict):
                nome = (v.get("nome_pjecalc") or "").upper()
                expr = (v.get("expresso_alvo") or "").upper()
                # Detectar verbas que são na verdade saldo FGTS
                if "FGTS DEP" in nome and "ATRASO" in nome:
                    continue  # pular - saldo já vai via fgts.saldos_a_deduzir
                if "VALOR PAGO" in expr and "TRIBUT" in expr and "FGTS DEP" in nome:
                    continue
            novas_verbas.append(v)
        # Só substituir se algo foi filtrado (preserva lista quando não há match)
        if len(novas_verbas) < len(verbas):
            data["verbas_principais"] = novas_verbas

    # 3. Honorários — tipo + base_apuracao + auto-credor
    hons = data.get("honorarios")
    if isinstance(hons, list):
        proc = data.get("processo") or {}
        data["honorarios"] = [
            _norm_honorario(dict(h), processo=proc) if isinstance(h, dict) else h
            for h in hons
        ]

    # 4. Correção/juros — IPCA-E
    if isinstance(data.get("correcao_juros_multa"), dict):
        data["correcao_juros_multa"] = _norm_correcao(data["correcao_juros_multa"])

    return data
