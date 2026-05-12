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


def _norm_fgts(fgts: dict[str, Any]) -> dict[str, Any]:
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
    return fgts


_TIPO_HONORARIO_MAP = {
    "SUCUMBENCIAIS": "ADVOCATICIO_SUCUMBENCIAL",
    "SUCUMBENCIAL": "ADVOCATICIO_SUCUMBENCIAL",
    "CONTRATUAIS": "ADVOCATICIO_CONTRATUAIS",
    "CONTRATUAL": "ADVOCATICIO_CONTRATUAIS",
    "PERICIAIS": "PERICIAL",
    "PERICIAL": "PERICIAL",
}

_BASE_APURACAO_MAP = {
    "BRUTO": "BRUTO_DEVIDO_AO_RECLAMANTE",
    "LIQUIDO": "LIQUIDO_DEVIDO_AO_RECLAMANTE",
}


def _norm_honorario(h: dict[str, Any]) -> dict[str, Any]:
    # Apenas traduz valores se o campo ainda for legacy (não tipo_honorario explicit)
    if "tipo_honorario" not in h:
        tipo = h.get("tipo")
        if isinstance(tipo, str) and tipo in _TIPO_HONORARIO_MAP:
            h["tipo"] = _TIPO_HONORARIO_MAP[tipo]
    if "base_para_apuracao" not in h:
        base = h.get("base_apuracao")
        if isinstance(base, str) and base in _BASE_APURACAO_MAP:
            h["base_apuracao"] = _BASE_APURACAO_MAP[base]
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

    # Validação cruzada: data_termino_calculo deve ser <= data_demissao
    # (se houver demissão). Se for maior, usar data_demissao.
    dem = p.get("data_demissao")
    fim = p.get("data_termino_calculo")
    if isinstance(dem, str) and isinstance(fim, str) and len(dem) == 10 and len(fim) == 10:
        try:
            from datetime import datetime as _dt
            d_dem = _dt.strptime(dem, "%d/%m/%Y")
            d_fim = _dt.strptime(fim, "%d/%m/%Y")
            if d_fim > d_dem:
                p["data_termino_calculo"] = dem
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

    # 2. FGTS — multa + recolhimentos
    if isinstance(data.get("fgts"), dict):
        data["fgts"] = _norm_fgts(data["fgts"])

    # 3. Honorários — tipo + base_apuracao
    hons = data.get("honorarios")
    if isinstance(hons, list):
        data["honorarios"] = [
            _norm_honorario(dict(h)) if isinstance(h, dict) else h for h in hons
        ]

    # 4. Correção/juros — IPCA-E
    if isinstance(data.get("correcao_juros_multa"), dict):
        data["correcao_juros_multa"] = _norm_correcao(data["correcao_juros_multa"])

    return data
