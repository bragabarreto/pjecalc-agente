"""Normalização de JSON legacy → schema v2 canônico.

Converte JSONs gerados por versões anteriores do prompt (Projeto Claude
Externo) para o formato canônico definido em ``docs/schema-v2/99-pydantic-models.py``.

Tratamentos cobertos (todos idempotentes — aplicar em JSON já canônico é no-op):

1. FGTS multa ``NAO_APURAR`` → ``ativa=false`` + ``CALCULADA/QUARENTA_POR_CENTO``
2. FGTS multa ``percentual=null`` → ``QUARENTA_POR_CENTO``
3. FGTS ``compor_principal`` bool → SimNao enum (``true``→``"SIM"``, ``false``→``"NAO"``)
4. FGTS ``multa`` bool → FGTSMulta dict (``true``→``{ativa:true,...}``, ``false``→``{ativa:false,...}``)
5. ``recolhimentos_existentes`` legacy (competencia/valor/observacao) → schema canônico
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
    # compor_principal: projeto externo gera bool; Pydantic espera "SIM"/"NAO"
    cp = fgts.get("compor_principal")
    if isinstance(cp, bool):
        fgts["compor_principal"] = "SIM" if cp else "NAO"

    # multa: projeto externo gera bool; Pydantic espera objeto FGTSMulta
    multa = fgts.get("multa")
    if isinstance(multa, bool):
        fgts["multa"] = {
            "ativa": multa,
            "tipo_valor": "CALCULADA",
            "percentual": "QUARENTA_POR_CENTO",
        }
        multa = fgts["multa"]

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

    # 4b. Cartão de Ponto — campos HH:MM nulos → default "00:00"
    cp = data.get("cartao_de_ponto")
    if isinstance(cp, dict):
        jp = cp.get("jornada_padrao")
        if isinstance(jp, dict):
            _JP_DEFAULTS: dict[str, str] = {
                "segunda_hhmm": "08:00",
                "terca_hhmm":   "08:00",
                "quarta_hhmm":  "08:00",
                "quinta_hhmm":  "08:00",
                "sexta_hhmm":   "08:00",
                "sabado_hhmm":  "00:00",
                "domingo_hhmm": "00:00",
            }
            for campo, default in _JP_DEFAULTS.items():
                if jp.get(campo) is None:
                    jp[campo] = default

    # 5. Enums de fórmula CALCULADO — mapear variantes geradas pelo Projeto Claude
    #    para os valores canônicos do Pydantic (idempotente).
    _DIVISOR_MAP = {
        "PADRAO_MENSAL": "OUTRO_VALOR",   # divisor=30 já deve estar em .valor
        "MENSAL":        "OUTRO_VALOR",
        "DIARIO":        "OUTRO_VALOR",
    }
    _QUANTIDADE_MAP = {
        "AVOS_CONTRATO":         "AVOS",
        "AVOS_PROPORCIONAL":     "AVOS",
        "CALCULADA":             "APURADA",
        "DIAS_UTEIS_TRABALHADOS": "INFORMADA",
        "DIAS_TRABALHADOS":      "INFORMADA",
        "DIAS_CORRIDOS":         "INFORMADA",
    }
    # base_calculo.tipo (TipoBaseTabelada): OUTRO_VALOR não é válido aqui —
    # o Projeto Claude usa OUTRO_VALOR quando não sabe qual base usar;
    # padronizar para HISTORICO_SALARIAL (base mais comum).
    _BASE_CALCULO_MAP = {
        "OUTRO_VALOR": "HISTORICO_SALARIAL",
        "SALARIO_BASE": "HISTORICO_SALARIAL",
    }
    for v in data.get("verbas_principais", []):
        if not isinstance(v, dict):
            continue
        for _key in ("parametros", "parametros_reflexo"):
            p = v.get(_key)
            if not isinstance(p, dict):
                continue
            fc = p.get("formula_calculado")
            if isinstance(fc, dict):
                div = fc.get("divisor")
                if isinstance(div, dict) and div.get("tipo") in _DIVISOR_MAP:
                    div["tipo"] = _DIVISOR_MAP[div["tipo"]]
                    # PADRAO_MENSAL implica divisor=30 se valor ainda não foi definido
                    if div["tipo"] == "OUTRO_VALOR" and div.get("valor") is None:
                        div["valor"] = 30.0
                qtd = fc.get("quantidade")
                if isinstance(qtd, dict) and qtd.get("tipo") in _QUANTIDADE_MAP:
                    qtd["tipo"] = _QUANTIDADE_MAP[qtd["tipo"]]
                bc = fc.get("base_calculo")
                if isinstance(bc, dict) and bc.get("tipo") in _BASE_CALCULO_MAP:
                    bc["tipo"] = _BASE_CALCULO_MAP[bc["tipo"]]

            # 6. Defensa contra `valor_informado_brl` negativo emitido pela IA.
            #    Em PJE-Calc, TODOS os valores monetários no JSON são positivos —
            #    o sistema trata sinais internamente (ex.: VALOR PAGO já é
            #    intrinsecamente uma dedução, mas o valor informado é positivo).
            #    Schema Pydantic exige Field(gt=0) → bloquearia o JSON.
            #    Aplicamos abs() defensivamente e idempotente.
            vd = p.get("valor_devido")
            if isinstance(vd, dict) and vd.get("tipo") == "INFORMADO":
                vi = vd.get("valor_informado_brl")
                if isinstance(vi, (int, float)) and vi < 0:
                    vd["valor_informado_brl"] = abs(vi)
            vp = p.get("valor_pago")
            if isinstance(vp, dict):
                vb = vp.get("valor_brl")
                if isinstance(vb, (int, float)) and vb < 0:
                    vp["valor_brl"] = abs(vb)

    # 6.bis Férias — normalizar valor "VENCIDAS" (não existe no enum) para
    # "INDENIZADAS" preservando o flag `dobra`. No PJE-Calc, "vencidas" significa
    # período concessivo expirado sem usufruto → direito à dobra (art. 137 CLT).
    # No nosso schema isso é representado por INDENIZADAS + dobra=true.
    # Idempotente.
    _ferias = data.get("ferias") or {}
    _periodos = _ferias.get("periodos") if isinstance(_ferias, dict) else None
    if isinstance(_periodos, list):
        for _p in _periodos:
            if not isinstance(_p, dict):
                continue
            _sit = (_p.get("situacao") or "").upper()
            if _sit == "VENCIDAS":
                _p["situacao"] = "INDENIZADAS"
                # Preservar dobra se já marcada; caso contrário, default True
                if "dobra" not in _p or _p.get("dobra") is None:
                    _p["dobra"] = True

    # 7. Honorários — `valor_informado_brl` negativo também recebe abs().
    for h in data.get("honorarios", []) or []:
        if not isinstance(h, dict):
            continue
        vi = h.get("valor_informado_brl")
        if isinstance(vi, (int, float)) and vi < 0:
            h["valor_informado_brl"] = abs(vi)

    # 8. Verbas de DEDUÇÃO (VALOR PAGO / DEVOLUÇÃO DESCONTOS):
    #    o valor da dedução pertence a `valor_pago.valor_brl`, NÃO a
    #    `valor_devido.valor_informado_brl`. Quando a IA inverte os campos
    #    (caso comum até o prompt ser atualizado), migrar automaticamente.
    #
    #    Também: na presença de QUALQUER verba dedução, o parâmetro global
    #    `parametros_calculo.zerar_valor_negativo` DEVE ser false — caso
    #    contrário a dedução é zerada no PJE-Calc.
    _NOMES_VERBAS_DEDUCAO = ("VALOR PAGO", "DEVOLUÇÃO DE DESCONTOS")
    tem_deducao = False
    for v in data.get("verbas_principais", []) or []:
        if not isinstance(v, dict):
            continue
        nome_pj = (v.get("nome_pjecalc") or "").upper()
        expr = (v.get("expresso_alvo") or "").upper()
        eh_deducao = any(t in nome_pj or t in expr for t in _NOMES_VERBAS_DEDUCAO)
        if not eh_deducao:
            continue
        tem_deducao = True
        p = v.get("parametros")
        if not isinstance(p, dict):
            continue
        vd = p.get("valor_devido") or {}
        vp = p.get("valor_pago") or {}
        vi = vd.get("valor_informado_brl") if isinstance(vd, dict) else None
        vp_atual = vp.get("valor_brl") if isinstance(vp, dict) else None
        # Migrar quando valor_devido tem valor > 0 e valor_pago está vazio/0
        if (
            isinstance(vi, (int, float)) and vi > 0
            and (vp_atual is None or vp_atual == 0)
        ):
            # Garantir vp como dict completo
            if not isinstance(vp, dict):
                vp = {}
            vp["tipo"] = "INFORMADO"
            vp["valor_brl"] = vi
            vp.setdefault("proporcionalizar", False)
            p["valor_pago"] = vp
            # Resetar valor_devido para 0 (mantém estrutura INFORMADO)
            if isinstance(vd, dict):
                vd["valor_informado_brl"] = 0.0
                vd.setdefault("tipo", "INFORMADO")
                vd.setdefault("proporcionalizar", False)
        # Garantir zerar_valor_negativo=False na própria verba
        if p.get("zerar_valor_negativo") is True:
            p["zerar_valor_negativo"] = False

    if tem_deducao:
        pc = data.get("parametros_calculo")
        if isinstance(pc, dict) and pc.get("zerar_valor_negativo") is True:
            pc["zerar_valor_negativo"] = False

    return data
