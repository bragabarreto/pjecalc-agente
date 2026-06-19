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

    # base_para_apuracao OBRIGATÓRIA p/ honorário CALCULADO (ONASSES 0000495-10,
    # 18/06/2026): sem ela o PJE-Calc rejeita o save ("Campo obrigatório: Base
    # para Apuração") e o honorário não é registrado. A IA frequentemente omite.
    # Default BRUTO (valor bruto da condenação — base padrão dos sucumbenciais
    # "...% sobre o valor da condenação"). Fidelidade prévia↔automação: o
    # normalizer corrige ANTES da prévia, espelhando o que o bot aplica.
    _tv = str(h.get("tipo_valor") or "CALCULADO").upper()
    if "CALCULAD" in _tv and not (h.get("base_para_apuracao") or h.get("base_apuracao")):
        h["base_para_apuracao"] = "BRUTO"
    return h


def _norm_correcao(c: dict[str, Any]) -> dict[str, Any]:
    idx = c.get("indice_trabalhista")
    if isinstance(idx, str) and idx in ("IPCA_E", "IPCA-E"):
        c["indice_trabalhista"] = "IPCAE"
    return c


def _norm_correcao_caso_a_vs_b(data: dict[str, Any]) -> None:
    """Salvaguarda contra confusão da IA entre Caso A (cálculo TODO pós-Lei
    14.905) e Caso B (cálculo CRUZA 30/08/2024).

    Bug histórico (ALINE 02/06/2026): IA emitiu Caso A (sem combinações,
    IPCA + TAXA_LEGAL) para cálculo com data_inicio_calculo=14/04/2021
    (anterior a 30/08/2024) e data_ajuizamento=14/04/2026. Resultado: para
    o período 14/04/2021–29/08/2024 (~3 anos) o PJE-Calc aplicava IPCA +
    TAXA_LEGAL (regime Lei 14.905) quando o correto era IPCAE + SELIC
    (modelo TST E-ED-RR-20407 pré-Lei 14.905).

    Regra (per prompt e jurisprudência):
    - **Caso A** requer AMBAS data_inicio_calculo >= 30/08/2024
      E data_ajuizamento >= 30/08/2024.
    - **Caso B** = cálculo CRUZA 30/08/2024 (data_inicio_calculo
      < 30/08/2024 <= data_termino_calculo). Exige combinacao com
      indice_combinado=IPCA + data_inicio_combinacao=30/08/2024 +
      juros_combinacoes apropriadas.

    Esta função detecta cálculos que cruzam a data-corte e ajusta a config
    para Caso B se IA emitiu Caso A.
    """
    from datetime import datetime as _dt
    cjm = data.get("correcao_juros_multa")
    pc = data.get("parametros_calculo")
    if not isinstance(cjm, dict) or not isinstance(pc, dict):
        return
    ini_str = pc.get("data_inicio_calculo")
    fim_str = pc.get("data_termino_calculo") or pc.get("data_demissao")
    if not (isinstance(ini_str, str) and isinstance(fim_str, str)):
        return
    try:
        ini = _dt.strptime(ini_str, "%d/%m/%Y")
        fim = _dt.strptime(fim_str, "%d/%m/%Y")
    except Exception:
        return
    corte = _dt(2024, 8, 30)
    aju_str = pc.get("data_ajuizamento")
    aju = None
    if isinstance(aju_str, str):
        try:
            aju = _dt.strptime(aju_str, "%d/%m/%Y")
        except Exception:
            aju = None

    # ── 1) CORREÇÃO — combinação IPCA a partir de 30/08/2024 quando o
    # cálculo CRUZA a data-corte (Lei 14.905). Bug ALINE 02/06/2026.
    cruza_corte = ini < corte <= fim
    if cruza_corte and not bool(cjm.get("combinar_outro_indice")):
        cjm["indice_trabalhista"] = "IPCAE"
        cjm["combinar_outro_indice"] = True
        cjm["indice_combinado"] = "IPCA"
        cjm["data_inicio_combinacao"] = "30/08/2024"

    # ── 2) JUROS — modelo TST E-ED-RR-20407 (validado contra sentença THAÍS
    # 0000183-68, 10/06/2026): a FASE 1 (pré-judicial) usa juros do art. 39
    # caput da Lei 8.177/91 = TRD_SIMPLES; a TAXA_LEGAL entra como COMBINAÇÃO
    # a partir do AJUIZAMENTO (ou SELIC→TAXA_LEGAL se ajuizamento pré-corte).
    #
    # Bug histórico THAÍS (10/06/2026): regra anterior (commit 587f862) emitia
    # juros=TAXA_LEGAL SEM combinações quando ajuizamento >= 30/08/2024 —
    # aplicava taxa legal DESDE O VENCIMENTO de cada verba (fase pré-judicial),
    # quando o devido era TRD (≈0) até o ajuizamento. Usuário corrigia à mão.
    #
    # Nota sobre 587f862: aquele fix evitava o PJE-Calc auto-converter para
    # SEM_JUROS a combinação TAXA_LEGAL@ajuizamento REDUNDANTE com fase 1
    # TAXA_LEGAL. Com fase 1 = TRD_SIMPLES a combinação NÃO é redundante e
    # persiste corretamente (comprovado no PJC THAÍS: <juros>TRD_SIMPLES</juros>
    # + combinarOutroJuros TAXA_LEGAL@11/02/2025).
    #
    # Salvaguarda conservadora: só corrige quando a IA emitiu o padrão antigo
    # (juros=TAXA_LEGAL na fase 1). Outras tabelas (sentenças explícitas,
    # JUROS_PADRAO, SEM_JUROS...) são preservadas.
    if aju is not None and cjm.get("juros") == "TAXA_LEGAL":
        cjm["juros"] = "TRD_SIMPLES"
        cjm["aplicar_juros_fase_pre_judicial"] = True
        if aju >= corte:
            cjm["juros_combinacoes"] = [{
                "data_inicio": aju_str,
                "tabela": "TAXA_LEGAL",
                "descricao": f"Do ajuizamento ({aju_str}) — Lei 14.905/2024 (CC art. 406 §): IPCA + SELIC-IPCA",
            }]
        else:
            cjm["juros_combinacoes"] = [
                {
                    "data_inicio": aju_str,
                    "tabela": "SELIC",
                    "descricao": f"Fase 2 — ajuizamento ({aju_str}) até 29/08/2024 (SELIC engloba correção e juros)",
                },
                {
                    "data_inicio": "30/08/2024",
                    "tabela": "TAXA_LEGAL",
                    "descricao": "Fase 3 — Lei 14.905/2024 (CC art. 406 §) — IPCA + SELIC-IPCA a partir de 30/08/2024",
                },
            ]


def _norm_multa_467_como_reflexo(data: dict[str, Any]) -> None:
    """Salvaguarda: MULTA DO ART. 467 emitida como VERBA PRINCIPAL autônoma.

    INVARIANTE PERMANENTE — NÃO REVERTER.

    Bug histórico (RODRIGO 0000447-51, 11/06/2026): IA emitiu MULTA 467 como
    verba principal (expresso_alvo=MULTA DO ARTIGO 477 + multiplicador 0.5).
    O Expresso não cria 2ª verba do mesmo alvo; os reflexos candidatos
    "MULTA DO ARTIGO 467 DA CLT SOBRE X" ficaram todos ativo=false e a multa
    FALTOU na liquidação (e, se criada, valeria 50% de 1 salário — errado).

    Correção: remover a verba autônoma e convertê-la em reflexos
    checkbox_painel sobre as verbas rescisórias estritas + multa_artigo_467
    no FGTS (multa 40% na base, padrão da jurisprudência).
    """
    verbas = data.get("verbas_principais")
    if not isinstance(verbas, list):
        return

    def _eh_467(v: dict) -> bool:
        blob = " ".join(
            str(v.get(k) or "")
            for k in ("nome_pjecalc", "nome_sentenca", "expresso_alvo")
        ).upper()
        return "467" in blob

    autonomas_467 = [v for v in verbas if isinstance(v, dict) and _eh_467(v)]
    if not autonomas_467:
        return

    # Verbas-alvo dos reflexos: rescisórias estritas (excluir multas,
    # indenizações, deduções e a própria 467/477).
    _EXCLUIR = ("MULTA", "INDENIZA", "DANO", "VALOR PAGO", "DEVOLU",
                "SEGURO", "FGTS", "HONORÁRIO", "HONORARIO")
    restantes = [v for v in verbas if isinstance(v, dict) and not _eh_467(v)]
    n_reflexos = 0
    for v in restantes:
        nome = str(v.get("nome_pjecalc") or v.get("expresso_alvo") or "").strip()
        if not nome or any(t in nome.upper() for t in _EXCLUIR):
            continue
        reflexos = v.setdefault("reflexos", [])
        if not isinstance(reflexos, list):
            continue
        alvo = f"MULTA DO ARTIGO 467 DA CLT SOBRE {nome}"
        if any(
            isinstance(r, dict) and (r.get("expresso_reflex_alvo") or "").upper() == alvo.upper()
            for r in reflexos
        ):
            continue
        reflexos.append({
            "id": f"r-{v.get('id') or nome[:8]}-467",
            "nome": f"Multa do Art. 467 sobre {nome}",
            "estrategia_reflexa": "checkbox_painel",
            "expresso_reflex_alvo": alvo,
            "parametros_override": None,
            "ocorrencias_override": None,
        })
        n_reflexos += 1

    # FGTS: multa 467 sobre a multa de 40% (base padrão)
    fgts = data.get("fgts")
    if isinstance(fgts, dict):
        fgts["multa_artigo_467"] = True

    # Remover as verbas autônomas 467
    data["verbas_principais"] = restantes
    import logging
    logging.getLogger(__name__).warning(
        "Normalizer: MULTA 467 emitida como verba autônoma — convertida em "
        "%d reflexo(s) checkbox_painel + fgts.multa_artigo_467=true "
        "(invariante RODRIGO 11/06/2026)",
        n_reflexos,
    )


def _norm_fgts_por_fora(data: dict[str, Any]) -> None:
    """Salário por fora (#69 — caso Ariane): a condenação de FGTS recai SÓ sobre
    a parcela extrafolha; o FGTS do salário registrado já foi depositado e está
    FORA da lide. Quando há histórico cujo nome indica 'por fora'/'extrafolha',
    força a incidência FGTS APENAS nele:
    - histórico por fora → incidencias.fgts = True;
    - demais históricos salariais (registrado / última remuneração / total) →
      incidencias.fgts = False.

    Safeguard determinístico: a IA frequentemente inverte (registrado=true,
    por fora=false) → FGTS sobre 5.275 (já pago) em vez de sobre 1.800. Só atua
    quando o padrão 'por fora' é detectado (presença do histórico). NÃO mexe em
    incidencias.cs_inss (INSS sobre a diferença é devido normalmente).
    """
    hist = data.get("historico_salarial")
    if not isinstance(hist, list) or not hist:
        return

    def _eh_por_fora(nome: str) -> bool:
        n = (nome or "").upper()
        return ("POR FORA" in n) or ("EXTRAFOLHA" in n) or ("EXTRA FOLHA" in n) \
            or ("EXTRA-FOLHA" in n)

    por_fora = [h for h in hist if isinstance(h, dict) and _eh_por_fora(h.get("nome", ""))]
    if not por_fora:
        return  # padrão não detectado → não mexe

    alterou = 0
    for h in hist:
        if not isinstance(h, dict):
            continue
        inc = h.get("incidencias")
        if not isinstance(inc, dict):
            inc = {}
            h["incidencias"] = inc
        desejado = _eh_por_fora(h.get("nome", ""))
        if inc.get("fgts") != desejado:
            inc["fgts"] = desejado
            alterou += 1

    if alterou:
        import logging
        logging.getLogger(__name__).warning(
            "Normalizer: salário por fora — incidência FGTS ajustada em %d "
            "histórico(s) (só a parcela extrafolha incide; registrado já "
            "depositado) — #69 Ariane", alterou,
        )


def _periodo_contem_dezembro(pi_str: str, pf_str: str) -> bool:
    """True se o intervalo [pi, pf] (DD/MM/YYYY) contém algum mês 12."""
    from datetime import datetime as _dt
    try:
        pi = _dt.strptime(pi_str, "%d/%m/%Y")
        pf = _dt.strptime(pf_str, "%d/%m/%Y")
    except Exception:
        return True  # na dúvida, não mexer
    y, m = pi.year, pi.month
    while (y, m) <= (pf.year, pf.month):
        if m == 12:
            return True
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return False


def _norm_13_ocorrencia_proporcional(data: dict[str, Any]) -> None:
    """13º proporcional do ano da rescisão (#72 — LUCAS 0000610-31).

    Orientação do usuário (juiz, 17/06/2026, validada em run real): o 13º deve
    apurar NATIVAMENTE a partir dos parâmetros do cálculo (admissão→demissão); o
    PJE-Calc posiciona a ocorrência no dezembro de cada ano e aplica a regra dos
    15 dias para os avos. Quando o 13º deferido é só o PROPORCIONAL do ano da
    rescisão, a IA estreita o período (ex.: 01/01/2026→25/04/2026) — e como esse
    período NÃO contém dezembro, a ocorrência nativa cai fora e a liquidação
    trava ('ocorrências do 13º devem estar contidas no período').

    Correção (só quando caracteristica=DECIMO_TERCEIRO_SALARIO + período SEM
    dezembro):
    - Se o CONTRATO (admissão→demissão) CONTÉM um dezembro (contrato multi-ano,
      ex.: LUCAS adm 13/01/2025): EXPANDE o período do 13º ao contrato (apuração
      nativa posiciona a ocorrência em dez/ano-anterior) e grava a JANELA de
      ocorrências deferidas = período original (o bot desativa as ocorrências
      dos anos pagos fora da janela). ocorrência volta a DEZEMBRO (nativo).
    - Se o contrato TAMBÉM não tem dezembro (contrato de ano único, mid-year):
      fallback DESLIGAMENTO (best-effort — posiciona na rescisão).

    13º multi-ano cujo período JÁ cruza dezembros (THAÍS, inv21) fica intocado.
    """
    verbas = data.get("verbas_principais")
    if not isinstance(verbas, list):
        return
    pc = data.get("parametros_calculo") or {}
    adm = pc.get("data_admissao") if isinstance(pc, dict) else None
    dem = pc.get("data_demissao") if isinstance(pc, dict) else None
    import logging
    _log = logging.getLogger(__name__)
    for v in verbas:
        if not isinstance(v, dict):
            continue
        p = v.get("parametros")
        if not isinstance(p, dict):
            continue
        if p.get("caracteristica") != "DECIMO_TERCEIRO_SALARIO":
            continue
        pi, pf = p.get("periodo_inicio"), p.get("periodo_fim")
        if not pi or not pf or _periodo_contem_dezembro(pi, pf):
            continue  # período já contém dezembro → nativo OK (THAÍS/multi-ano)
        # período do 13º SEM dezembro (proporcional do ano da rescisão)
        if adm and dem and _periodo_contem_dezembro(adm, dem):
            # contrato multi-ano com dezembro → apuração nativa + janela deferida
            p["janela_ocorrencias_inicio"] = pi
            p["janela_ocorrencias_fim"] = pf
            p["periodo_inicio"] = adm
            p["periodo_fim"] = dem
            p["ocorrencia_pagamento"] = "DEZEMBRO"
            _log.warning(
                "Normalizer: 13º '%s' proporcional-rescisão — período expandido "
                "ao contrato %s→%s (apuração nativa) + janela deferida %s→%s "
                "(bot desativa anos pagos) — #72",
                v.get("nome_pjecalc"), adm, dem, pi, pf,
            )
        else:
            # contrato de ano único mid-year (sem dezembro em lugar nenhum)
            p["ocorrencia_pagamento"] = "DESLIGAMENTO"
            _log.warning(
                "Normalizer: 13º '%s' período %s→%s sem dezembro e contrato sem "
                "dezembro — fallback DESLIGAMENTO (#72)",
                v.get("nome_pjecalc"), pi, pf,
            )


def _norm_cap_periodo_fim_na_demissao(data: dict[str, Any]) -> None:
    """Coerência ocorrência×período (PJE-Calc / validador Regra 1) — #75.

    Para verbas com ocorrência NÃO-MENSAL (DESLIGAMENTO, DEZEMBRO,
    PERIODO_AQUISITIVO), o PJE-Calc REJEITA a liquidação quando `periodo_fim` é
    POSTERIOR à `data_demissao` ("A data final não pode ser maior que a data
    demissão, para 'Ocorrências de Pagamento' diferentes de Mensal"). O schema
    flagueia isso como completude=INCOMPLETO e a automação NÃO INICIA.

    EXCEÇÃO: AVISO PRÉVIO (projeção legal Lei 12.506/2011 — periodo_fim pode/deve
    passar da demissão). Mantido intocado.

    Bug (processo 0000953-… demissão 05/11/2025, 19/06/2026): o 13º (verba única
    multi-ano) ficava com `periodo_fim = data_termino_calculo` (07/12/2025 =
    aviso projetado) + ocorrência DEZEMBRO → bloqueio. As demais rescisórias já
    vinham capadas na demissão; só o 13º vazava a data_termino. Cap em
    `data_demissao` (= regra do prompt: "13º DEZEMBRO → periodo_fim = demissão").
    Fidelidade prévia↔automação: corrige ANTES da prévia.
    """
    pc = data.get("parametros_calculo") or {}
    dem = pc.get("data_demissao") if isinstance(pc, dict) else None
    if not dem:
        return
    from datetime import datetime as _dt
    import logging
    _log = logging.getLogger(__name__)
    try:
        d_dem = _dt.strptime(dem, "%d/%m/%Y")
    except (ValueError, TypeError):
        return
    _NAO_MENSAL = {"DESLIGAMENTO", "DEZEMBRO", "PERIODO_AQUISITIVO"}
    for v in data.get("verbas_principais") or []:
        if not isinstance(v, dict):
            continue
        p = v.get("parametros")
        if not isinstance(p, dict):
            continue
        if str(p.get("ocorrencia_pagamento") or "") not in _NAO_MENSAL:
            continue
        # AVISO PRÉVIO: projeção legal — não capar
        _carac = str(p.get("caracteristica") or "").upper()
        _alvo = (v.get("expresso_alvo") or "").upper()
        _nome = (v.get("nome_pjecalc") or "").upper()
        if "AVISO_PREVIO" in _carac or "AVISO PRÉVIO" in _alvo or "AVISO PREVIO" in _alvo \
           or "AVISO PRÉVIO" in _nome or "AVISO PREVIO" in _nome:
            continue
        pf = p.get("periodo_fim")
        if not pf:
            continue
        try:
            d_pf = _dt.strptime(pf, "%d/%m/%Y")
        except (ValueError, TypeError):
            continue
        if d_pf > d_dem:
            p["periodo_fim"] = dem
            _log.warning(
                "Normalizer: verba '%s' ocorr=%s periodo_fim=%s POSTERIOR à "
                "demissão=%s → cap em %s (#75 — PJE-Calc rejeita ≠ Mensal)",
                v.get("nome_pjecalc"), p.get("ocorrencia_pagamento"), pf, dem, dem,
            )


def _norm_cap_periodo_inicio_prescricao(data: dict[str, Any]) -> None:
    """Coerência período×prescrição quinquenal (PJE-Calc) — #78.

    Quando `prescricao_quinquenal=True`, o PJE-Calc REJEITA o save de parâmetros
    de qualquer verba cujo `periodo_inicio` seja ANTERIOR ao piso prescricional
    (data_ajuizamento − 5 anos): "A data de início informada não pode ser
    anterior à data da prescrição quinquenal (5 anos antes da Data do
    Ajuizamento)". O save falha, a verba fica desconfigurada, e na liquidação a
    listagem vem vazia → guard anti-fantasma aborta a exportação.

    Bug (FRANCISCA/L'Oréal 0001858-66, ajuizamento 24/11/2025, 19/06/2026): HORAS
    EXTRAS 50% e INTERVALO INTRAJORNADA vinham com periodo_inicio=04/07/2020 <
    piso 24/11/2020 → save rejeitado → 2 verbas, listagem vazia → abort. O mesmo
    valha p/ `data_inicio_calculo` (a IA o setou 04/07/2020, inconsistente com o
    piso).

    Fix: capar `data_inicio_calculo` e cada `periodo_inicio` (verba + reflexo) no
    piso prescricional ANTES da prévia (fidelidade prévia↔automação). O período
    anterior ao piso é prescrito (não calculável); o usuário revê na prévia. Só
    age quando prescricao_quinquenal=True (se False, PJE-Calc não aplica o piso).
    """
    pc = data.get("parametros_calculo") or {}
    if not isinstance(pc, dict) or not pc.get("prescricao_quinquenal"):
        return
    aju = pc.get("data_ajuizamento")
    if not aju:
        return
    from datetime import datetime as _dt
    import logging
    _log = logging.getLogger(__name__)
    try:
        d_aju = _dt.strptime(aju, "%d/%m/%Y")
    except (ValueError, TypeError):
        return
    # Piso = ajuizamento − 5 anos (mesma data, ano−5). 29/02 → 28/02.
    try:
        piso = d_aju.replace(year=d_aju.year - 5)
    except ValueError:
        piso = d_aju.replace(year=d_aju.year - 5, day=28)
    piso_str = piso.strftime("%d/%m/%Y")

    def _cap(container: dict, campo: str, rotulo: str) -> None:
        val = container.get(campo)
        if not val:
            return
        try:
            d_val = _dt.strptime(val, "%d/%m/%Y")
        except (ValueError, TypeError):
            return
        if d_val < piso:
            container[campo] = piso_str
            _log.warning(
                "Normalizer: %s=%s ANTERIOR ao piso prescricional=%s "
                "(ajuizamento %s − 5a) → cap em %s (#78)",
                rotulo, val, piso_str, aju, piso_str,
            )

    # data_inicio_calculo do cálculo
    _cap(pc, "data_inicio_calculo", "data_inicio_calculo")
    # periodo_inicio de cada verba principal + seus reflexos
    for v in data.get("verbas_principais") or []:
        if not isinstance(v, dict):
            continue
        p = v.get("parametros")
        if isinstance(p, dict):
            _cap(p, "periodo_inicio", f"verba '{v.get('nome_pjecalc')}'")
        for r in v.get("reflexos") or []:
            if isinstance(r, dict) and isinstance(r.get("parametros"), dict):
                _cap(r["parametros"], "periodo_inicio",
                     f"reflexo '{r.get('nome_pjecalc')}' de '{v.get('nome_pjecalc')}'")


def _norm_justa_causa_exclui_rescisorias(data: dict[str, Any]) -> None:
    """Súmula 171 TST / CLT art. 482 (#68 — safeguard determinístico).

    Na JUSTA CAUSA do empregado ou no PEDIDO DE DEMISSÃO, AUTO-remove de
    `verbas_principais` as rescisórias INEQUIVOCAMENTE indevidas — aviso prévio
    (qualquer), multa/indenização de 40% do FGTS, saque/liberação do FGTS como
    verba, e seguro-desemprego.

    NÃO toca em:
    - FÉRIAS / 13º (férias VENCIDAS são devidas mesmo na justa causa — o schema
      apenas FLAGA para revisão);
    - MULTA 477/467 (devidas se as rescisórias não forem pagas no prazo);
    - DIFERENÇA SALARIAL e demais verbas do curso do contrato.

    Só atua quando `modalidade_rescisao` foi extraída (campo opcional) — sem
    ela, nenhuma exclusão é aplicada (retrocompatível).

    Motivo (Ariane 0000566-12, 15/06/2026): a extração alucina rescisórias
    indevidas em ~25% das vezes nessa modalidade; o prompt sozinho não zera.
    """
    pc = data.get("parametros_calculo")
    if not isinstance(pc, dict):
        return
    if pc.get("modalidade_rescisao") not in ("justa_causa", "pedido_demissao"):
        return
    verbas = data.get("verbas_principais")
    if not isinstance(verbas, list):
        return

    def _indevida(v: dict) -> bool:
        nome = " ".join(
            str(v.get(k) or "")
            for k in ("nome_pjecalc", "nome_sentenca", "expresso_alvo")
        ).upper()
        if "AVISO" in nome and ("PRÉVIO" in nome or "PREVIO" in nome):
            return True
        if ("40" in nome or "QUARENTA" in nome) and "FGTS" in nome:
            return True
        if "FGTS" in nome and ("SAQUE" in nome or "LIBERA" in nome):
            return True
        if "SEGURO" in nome and "DESEMPREGO" in nome:
            return True
        return False

    restantes = [v for v in verbas if not (isinstance(v, dict) and _indevida(v))]
    removidas = len(verbas) - len(restantes)
    if removidas:
        data["verbas_principais"] = restantes
        import logging
        logging.getLogger(__name__).warning(
            "Normalizer: rescisão '%s' — %d verba(s) rescisória(s) indevida(s) "
            "removida(s) (Súmula 171: aviso/40%%FGTS/saque/seguro)",
            pc.get("modalidade_rescisao"), removidas,
        )


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


def _build_comentarios_jg(parte_lower: str, nome_rec: str, nome_red: str) -> str:
    """Constrói texto canônico de suspensão JG.

    Formato canônico (concordância sempre feminina via "parte"):
      "Suspensão de exigibilidade dos honorários sucumbenciais devidos pela
       parte <reclamante|reclamada> — <NOME>, beneficiária da Justiça
       Gratuita (art. 791-A, § 4º, da CLT)."

    parte_lower ∈ {"reclamante", "reclamado", "ambos"}
    """
    if parte_lower == "ambos":
        return (
            f"Suspensão de exigibilidade dos honorários sucumbenciais devidos "
            f"pela parte reclamante - {nome_rec} e pela parte reclamada - {nome_red}, "
            f"ambas beneficiárias da Justiça Gratuita (art. 791-A, § 4º, da CLT)."
        )
    nome_alvo = nome_rec if parte_lower == "reclamante" else nome_red
    return (
        f"Suspensão de exigibilidade dos honorários sucumbenciais devidos "
        f"pela parte {parte_lower} - {nome_alvo}, beneficiária da Justiça "
        f"Gratuita (art. 791-A, § 4º, da CLT)."
    )


def _norm_comentarios_jg(data: dict[str, Any]) -> dict[str, Any]:
    """Sintetiza `parametros_calculo.comentarios_jg` a partir dos fatos do JSON.

    Política (26/05/2026, user feedback): IA preenche apenas FATOS no JSON
    (concessão de JG + honorários sucumbenciais). Normalizer DEDUZ e SINTETIZA
    o texto canônico de suspensão de exigibilidade ANTES da prévia, para
    preservar fidelidade prévia↔automação.

    Lógica:
    1. Se comentarios_jg já vem preenchido pelo usuário, valida concordância
       e normaliza para formato canônico (compat. com legacy "pelo Reclamante,
       beneficiário").
    2. Se comentarios_jg é null/vazio, AUTO-GERA a partir de:
       - parametros_calculo.justica_gratuita.{reclamante, reclamado}
       - honorarios[*] onde tipo_honorario=SUCUMBENCIAIS
       - processo.reclamante.nome / processo.reclamado.nome
       Só gera quando há INTERSEÇÃO (parte JG ∩ parte com sucumbenciais).

    Idempotente.
    """
    import re as _re
    pc = data.get("parametros_calculo")
    if not isinstance(pc, dict):
        return data

    proc = data.get("processo") or {}
    nome_rec = ((proc.get("reclamante") or {}).get("nome") or "").strip()
    nome_red = ((proc.get("reclamado")  or {}).get("nome") or "").strip()

    txt = pc.get("comentarios_jg")
    if txt and isinstance(txt, str) and (
        "Suspensão de exigibilidade" in txt or "suspensão de exigibilidade" in txt
    ):
        # Caso 1: texto já existe — extrair parte + reescrever em formato canônico
        parte_lower = None
        if _re.search(r"\bpelo\s+Reclamante|\bdo\s+Reclamante|\bReclamante,\s*benefici", txt):
            parte_lower = "reclamante"
        elif _re.search(r"\bpelo\s+Reclamado|\bdo\s+Reclamado|\bReclamado,\s*benefici", txt):
            parte_lower = "reclamado"
        elif "ambas" in txt.lower() or "ambos" in txt.lower():
            parte_lower = "ambos"
        elif "parte reclamante" in txt.lower() and "parte reclamada" in txt.lower():
            parte_lower = "ambos"
        elif "parte reclamante" in txt.lower():
            parte_lower = "reclamante"
        elif "parte reclamada" in txt.lower():
            parte_lower = "reclamado"
        if parte_lower is None:
            return data  # preserva original (formato desconhecido)
        pc["comentarios_jg"] = _build_comentarios_jg(parte_lower, nome_rec, nome_red)
        return data

    # Caso 2: comentarios_jg null/vazio → auto-gerar a partir dos FATOS
    jg = pc.get("justica_gratuita") or {}
    if not isinstance(jg, dict):
        return data
    jg_rec = bool(jg.get("reclamante", False))
    jg_red = bool(jg.get("reclamado", False))
    if not (jg_rec or jg_red):
        return data  # ninguém é beneficiário — sem comentário

    # Verificar interseção com sucumbenciais
    suc_rec = False
    suc_red = False
    for hon in data.get("honorarios", []) or []:
        if not isinstance(hon, dict): continue
        if hon.get("tipo_honorario") != "SUCUMBENCIAIS": continue
        dev = hon.get("tipo_devedor", "")
        if dev == "RECLAMANTE": suc_rec = True
        elif dev == "RECLAMADO": suc_red = True

    aplica_rec = jg_rec and suc_rec
    aplica_red = jg_red and suc_red
    if aplica_rec and aplica_red:
        parte_lower = "ambos"
    elif aplica_rec:
        parte_lower = "reclamante"
    elif aplica_red:
        parte_lower = "reclamado"
    else:
        return data  # JG concedida mas sem sucumbenciais contra essa parte

    pc["comentarios_jg"] = _build_comentarios_jg(parte_lower, nome_rec, nome_red)
    return data


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

    # 1b. Comentários JG — concordância "parte reclamante/reclamada — NOME, beneficiária"
    data = _norm_comentarios_jg(data)

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

    # 3b. Verbas — normalizar valor_pago CALCULADO:
    # IA às vezes emite `historico_nome` em vez de `base_historico_nome`,
    # e omite `base_tipo`. Sem essas chaves, o bot não aciona o painel de
    # Base do Valor Pago, e o JSF rejeita o save com "Campo obrigatório:
    # Base do Valor Pago" — fazendo Liquidação travar com "Falta selecionar
    # pelo menos um Histórico Salarial para apurar o Valor Devido da Verba X".
    verbas = data.get("verbas_principais")
    if isinstance(verbas, list):
        for v in verbas:
            if not isinstance(v, dict):
                continue
            params = v.get("parametros")
            if not isinstance(params, dict):
                continue
            vp = params.get("valor_pago")
            if not isinstance(vp, dict):
                continue
            if (vp.get("tipo") or "").upper() == "CALCULADO":
                # 1) historico_nome → base_historico_nome (mantém ambos por compat)
                hist_legacy = vp.get("historico_nome")
                if hist_legacy and not vp.get("base_historico_nome"):
                    vp["base_historico_nome"] = hist_legacy
                # 2) Se tem histórico mas sem base_tipo, inferir HISTORICO_SALARIAL
                if vp.get("base_historico_nome") and not vp.get("base_tipo"):
                    vp["base_tipo"] = "HISTORICO_SALARIAL"
                # 3) proporcionalizar (bool) → proporcionaliza_historico (SimNao)
                prop = vp.get("proporcionalizar")
                if prop is not None and not vp.get("proporcionaliza_historico"):
                    vp["proporcionaliza_historico"] = "SIM" if prop else "NAO"

    # 4. Correção/juros — IPCA-E
    if isinstance(data.get("correcao_juros_multa"), dict):
        data["correcao_juros_multa"] = _norm_correcao(data["correcao_juros_multa"])

    # Salvaguarda: detectar cálculo que CRUZA 30/08/2024 (Lei 14.905) e
    # corrigir config se IA emitiu Caso A indevidamente (deveria ser Caso B).
    _norm_correcao_caso_a_vs_b(data)

    # Salvaguarda: MULTA 467 emitida como verba principal autônoma →
    # converter em reflexos checkbox_painel + multa_artigo_467 no FGTS.
    _norm_multa_467_como_reflexo(data)

    # Salvaguarda Súmula 171 (#68): na justa causa / pedido de demissão,
    # remover rescisórias INEQUIVOCAMENTE indevidas (aviso/40%FGTS/saque/seguro).
    # FÉRIAS/13º NÃO são tocados (vencidas podem ser devidas) — o schema FLAGA
    # para revisão.
    _norm_justa_causa_exclui_rescisorias(data)

    # Salvaguarda #72: 13º proporcional do ano da rescisão (período sem
    # dezembro) → ocorrência DESLIGAMENTO (senão a ocorrência DEZEMBRO cai fora
    # do período e a liquidação trava).
    _norm_13_ocorrencia_proporcional(data)

    # Salvaguarda #75: ocorrência NÃO-MENSAL com periodo_fim POSTERIOR à
    # demissão → cap em data_demissao (PJE-Calc rejeita; bloqueia automação).
    # APÓS o _norm_13 (que pode setar DEZEMBRO) — o cap é a última palavra.
    _norm_cap_periodo_fim_na_demissao(data)

    # Salvaguarda #78: com prescricao_quinquenal=True, periodo_inicio (verba/
    # reflexo) e data_inicio_calculo NÃO podem ser anteriores ao piso
    # prescricional (ajuizamento − 5a) — PJE-Calc rejeita o save da verba e a
    # liquidação aborta com listagem vazia. Cap no piso ANTES da prévia.
    _norm_cap_periodo_inicio_prescricao(data)

    # Salvaguarda salário por fora (#69): FGTS incide SÓ sobre a parcela
    # extrafolha (o registrado já foi depositado). Corrige a inversão comum da
    # IA (registrado=true / por fora=false).
    _norm_fgts_por_fora(data)

    # 4b. Cartão de Ponto — sanitização + migração + defaults
    #
    # 4b.0 SANITIZAÇÃO ANTI-STUB (bug recorrente, ALINE 01/06/2026):
    # IA frequentemente emite stub `{ocorrencias_override:[], preenchimento:'LIVRE'}`
    # sem datas/jornada quando a sentença NÃO tem cartão de ponto. O Pydantic
    # rejeita esse stub (data_inicial/data_final required) → /confirmar 422.
    # Anular ANTES de qualquer outra migração — defesa em 2ª camada (prompt
    # é a 1ª) para garantir fidelidade prévia↔automação.
    def _cartao_e_stub_vazio(cp: object) -> bool:
        """True se cartão não tem nenhum dado útil de jornada."""
        if not isinstance(cp, dict) or not cp:
            return False  # null/empty já tratados separado
        # Campos OBRIGATÓRIOS de um cartão real
        if cp.get("data_inicial") or cp.get("data_final"):
            return False
        # Programação semanal com algum dia preenchido
        ps = cp.get("programacao_semanal")
        if isinstance(ps, dict):
            for dia, conf in ps.items():
                if isinstance(conf, dict) and conf.get("turnos"):
                    return False
        # Escala configurada (tipo != OUTRA ou tem jornadas com turnos)
        esc = cp.get("escala")
        if isinstance(esc, dict):
            tipo = esc.get("tipo")
            if tipo and tipo != "OUTRA":
                return False
            jornadas = esc.get("jornadas") or []
            for j in jornadas:
                if isinstance(j, dict) and j.get("turnos"):
                    return False
        # Jornada padrão com algum dia > 00:00
        jp = cp.get("jornada_padrao")
        if isinstance(jp, dict):
            for k, v in jp.items():
                if k.endswith("_hhmm") and v and v not in ("00:00", "0", ""):
                    return False
        # Ocorrências override com pelo menos 1 dia
        oo = cp.get("ocorrencias_override")
        if isinstance(oo, list) and any(isinstance(o, dict) and o.get("data") for o in oo):
            return False
        # Tudo vazio → stub
        return True
    cp_singular = data.get("cartao_de_ponto")
    if _cartao_e_stub_vazio(cp_singular):
        data["cartao_de_ponto"] = None
        cp_singular = None
    cp_lista_pre = data.get("cartoes_de_ponto") or []
    cp_lista_filtrada = [c for c in cp_lista_pre if not _cartao_e_stub_vazio(c)]
    if len(cp_lista_filtrada) != len(cp_lista_pre):
        data["cartoes_de_ponto"] = cp_lista_filtrada
    # 4b.1 Migração singular → lista: se IA enviou cartao_de_ponto (singular)
    # e cartoes_de_ponto está vazio, migrar para list[1].
    # Suporta multi-período (Scarlette: 2 jornadas distintas em 2 períodos).
    cp_lista = data.get("cartoes_de_ponto") or []
    if cp_singular and not cp_lista:
        if isinstance(cp_singular, dict) and cp_singular:  # não-vazio
            data["cartoes_de_ponto"] = [cp_singular]
            cp_lista = [cp_singular]
    # Após migração, processar TODOS os cartões para defaults HH:MM
    _JP_DEFAULTS: dict[str, str] = {
        "segunda_hhmm": "08:00", "terca_hhmm": "08:00", "quarta_hhmm": "08:00",
        "quinta_hhmm":  "08:00", "sexta_hhmm": "08:00",
        "sabado_hhmm":  "00:00", "domingo_hhmm": "00:00",
    }
    for cp_item in cp_lista:
        if not isinstance(cp_item, dict):
            continue
        jp = cp_item.get("jornada_padrao")
        if isinstance(jp, dict):
            for campo, default in _JP_DEFAULTS.items():
                if jp.get(campo) is None:
                    jp[campo] = default
    # Compat: também aplicar ao singular (caso bot legacy ainda leia)
    if isinstance(cp_singular, dict):
        jp = cp_singular.get("jornada_padrao")
        if isinstance(jp, dict):
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
        _nome_verba = (v.get("nome_pjecalc") or v.get("expresso_alvo") or "").upper()
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
                # ⚠ INVARIANTE CLT (26/05/2026, fidelidade prévia↔automação):
                # 13º SALÁRIO e FÉRIAS + 1/3 têm divisor=12 SEMPRE (constante
                # legal — CLT art. 130 / CF art. 7º XVII). Se IA externa gerar
                # outro valor (bug Scarlette: divisor=1), normalizer CORRIGE
                # AQUI — antes da prévia — para preservar fidelidade
                # prévia↔automação. Bot apenas aplica o que está na prévia.
                if isinstance(div, dict) and div.get("valor") is not None:
                    _is_13o = "13" in _nome_verba and "SAL" in _nome_verba
                    _is_ferias = "FÉRIAS + 1/3" in _nome_verba or "FERIAS + 1/3" in _nome_verba
                    if _is_13o or _is_ferias:
                        try:
                            if float(div["valor"]) != 12.0:
                                div["valor"] = 12
                                div["tipo"] = "OUTRO_VALOR"
                        except (TypeError, ValueError):
                            pass
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

    # 6.ante Coerência temporal das verbas e data_termino_calculo.
    #
    # Regras:
    #   (a) Verbas com ocorrencia_pagamento DESLIGAMENTO (Saldo de Salário,
    #       Multa 477, Aviso Prévio etc) devem ter periodo_inicio = 1º dia
    #       do mês da demissão. PJE-Calc gera ocorrências para o mês inteiro
    #       e RECUSA a liquidação se a ocorrência ficar fora do período
    #       declarado. Bot às vezes coloca periodo_inicio = periodo_fim =
    #       data_demissao, gerando inconsistência.
    #
    #   (b) data_termino_calculo deve ser ≥ MAX(periodo_fim) entre todas as
    #       verbas. Caso usuário/IA tenha colocado data_demissao mas haja
    #       Aviso Prévio Indenizado projetado (Lei 12.506/2011: até +90 dias),
    #       estabilidade, pensão vitalícia etc, a data fica curta e ocorrências
    #       projetadas saem do período de cálculo.
    pc_cal = data.get("parametros_calculo") or {}
    data_demissao_str = pc_cal.get("data_demissao") if isinstance(pc_cal, dict) else None
    def _parse_br(s: str | None):
        if not s or not isinstance(s, str):
            return None
        try:
            d, m, y = s.split("/")
            return (int(y), int(m), int(d))
        except Exception:
            return None
    def _format_br(triple):
        return f"{triple[2]:02d}/{triple[1]:02d}/{triple[0]:04d}"
    demi_tuple = _parse_br(data_demissao_str)

    _OCORRENCIAS_DESLIG = {"DESLIGAMENTO"}
    max_fim = None  # tupla (y,m,d) — usada para regra (b)
    for v in data.get("verbas_principais", []) or []:
        if not isinstance(v, dict):
            continue
        p = v.get("parametros") or {}
        if not isinstance(p, dict):
            continue
        ocor = p.get("ocorrencia_pagamento")
        pi = p.get("periodo_inicio")
        pf = p.get("periodo_fim")
        # (a) Ajustar periodo_inicio para 1º do mês da demissão quando
        # ocor=DESLIGAMENTO e periodo_inicio==data_demissao (==periodo_fim).
        if (
            ocor in _OCORRENCIAS_DESLIG
            and demi_tuple is not None
            and pi == data_demissao_str
            and pf == data_demissao_str
        ):
            primeiro_mes = (demi_tuple[0], demi_tuple[1], 1)
            p["periodo_inicio"] = _format_br(primeiro_mes)
        # (a.bis) REVERTIDO 24/05/2026: tentativa de expandir periodo_fim
        # para último dia do mês violou validação 'periodo_fim ≤ data_demissao
        # para DESLIGAMENTO'. Solução alternativa: o bot faz Regerar Ocorrências
        # antes de tentar setar valorDevido (em _configurar_ocorrencias_informado_inline).
        # Período declarado 01/12-01/12 fica preservado.
        # (b) Calcular max_fim de todas as verbas
        pf_atual = p.get("periodo_fim")
        pf_t = _parse_br(pf_atual)
        if pf_t and (max_fim is None or pf_t > max_fim):
            max_fim = pf_t

    # (b) Garantir data_termino_calculo >= max_fim.
    dt_termino_str = pc_cal.get("data_termino_calculo") if isinstance(pc_cal, dict) else None
    dt_termino_t = _parse_br(dt_termino_str)
    if max_fim and (dt_termino_t is None or dt_termino_t < max_fim):
        if isinstance(pc_cal, dict):
            pc_cal["data_termino_calculo"] = _format_br(max_fim)

    # 6.ante.bis Histórico Salarial CALCULADO mal-formado.
    #
    # IA às vezes confunde o schema de histórico salarial CALCULADO (que tem
    # apenas quantidade_pct + base_referencia) com o de verba CALCULADO (que
    # tem base_calculo, divisor, multiplicador, quantidade).
    #
    # Quando emite `calculado: {"base_calculo": {"tipo": "SALARIO_MINIMO"}}`,
    # o Pydantic rejeita por falta de quantidade_pct e base_referencia.
    #
    # Conversão idempotente: extrair tipo do base_calculo erroneamente
    # aninhado e reescrever como {quantidade_pct: 1.0, base_referencia: "TIPO"}.
    # quantidade_pct=1.0 = 1× referência = 100% (MULTIPLICADOR, não percentual 0-100).
    _hist = data.get("historico_salarial")
    if isinstance(_hist, list):
        for h in _hist:
            if not isinstance(h, dict):
                continue
            calc = h.get("calculado")
            if not isinstance(calc, dict):
                continue
            # Detectar formato errado: tem base_calculo mas falta quantidade_pct/base_referencia
            if (
                "base_calculo" in calc
                and ("quantidade_pct" not in calc or "base_referencia" not in calc)
            ):
                bc = calc.get("base_calculo")
                tipo = None
                if isinstance(bc, dict):
                    tipo = bc.get("tipo") or bc.get("base")
                if tipo:
                    calc["base_referencia"] = str(tipo)
                if "quantidade_pct" not in calc:
                    calc["quantidade_pct"] = 1.0
                # Limpar campo errado para evitar confusão futura
                calc.pop("base_calculo", None)
            # Salvaguarda: se IA emitiu quantidade_pct=100.0 com base SALARIO_MINIMO/
            # SALARIO_DA_CATEGORIA (clássico bug "100% interpretado como 100×"),
            # corrigir para 1.0. Casos legítimos de múltiplos > 10 não existem
            # nesse contexto (ninguém recebe 100 salários mínimos como salário base).
            qpct = calc.get("quantidade_pct")
            base = (calc.get("base_referencia") or "").upper()
            if (
                isinstance(qpct, (int, float))
                and qpct >= 10.0
                and base in ("SALARIO_MINIMO", "SALARIO_DA_CATEGORIA")
            ):
                # Heurística: 100.0 → 1.0; 150.0 → 1.5; 200.0 → 2.0
                calc["quantidade_pct"] = float(qpct) / 100.0

    # 6.bis Histórico Salarial — CONSOLIDAÇÃO de entradas duplicadas por valor de SM
    # tabelado em períodos contíguos. Defesa em 2ª camada caso prompt falhe.
    #
    # Quando a IA emite N entradas tipo "SALARIO MINIMO 2024" R$ 1412 + "SALARIO
    # MINIMO 2025" R$ 1518 + ..., o normalizer detecta que os valores batem com
    # a tabela oficial do salário mínimo (R$ 1.320 em 2023, R$ 1.412 em 2024,
    # R$ 1.518 em 2025, R$ 1.622 em 2026) e consolida em UMA entrada CALCULADO
    # com base SALARIO_MINIMO + quantidade_pct=1.0. PJE-Calc resolve o valor de
    # cada competência pela tabela oficial.
    #
    # Heurística: se TODAS as entradas têm valor_brl ∈ {SM oficial por ano} e
    # períodos contíguos, consolidar.
    SM_OFICIAL = {
        2018: 954.00, 2019: 998.00, 2020: 1045.00, 2021: 1100.00,
        2022: 1212.00, 2023: 1320.00, 2024: 1412.00, 2025: 1518.00,
        2026: 1622.00,
    }
    def _competencia_ano(comp: str | None) -> int | None:
        try:
            return int((comp or "").split("/")[-1])
        except Exception:
            return None
    if isinstance(_hist, list) and len(_hist) >= 2:
        # Considerar apenas entradas INFORMADO com valor que bate com SM oficial
        candidatas: list[dict] = []
        for h in _hist:
            if not isinstance(h, dict):
                continue
            if (h.get("tipo_valor") or "").upper() != "INFORMADO":
                continue
            val = h.get("valor_brl")
            if not isinstance(val, (int, float)):
                continue
            ano = _competencia_ano(h.get("competencia_inicial"))
            if ano is None or ano not in SM_OFICIAL:
                continue
            # tolerância 1 centavo
            if abs(float(val) - SM_OFICIAL[ano]) > 0.01:
                continue
            candidatas.append(h)
        # Só consolidar se TODAS as entradas históricas forem SM-tabelado
        if len(candidatas) == len(_hist) and len(candidatas) >= 2:
            comp_inicial = candidatas[0].get("competencia_inicial")
            comp_final = candidatas[-1].get("competencia_final")
            # Preservar incidências e parcela da primeira (defaults razoáveis)
            inc = candidatas[0].get("incidencias") or {"fgts": True, "cs_inss": True}
            parcela = candidatas[0].get("parcela") or "FIXA"
            consolidada = {
                "nome": "SALARIO MINIMO",
                "parcela": parcela,
                "incidencias": inc,
                "competencia_inicial": comp_inicial,
                "competencia_final": comp_final,
                "tipo_valor": "CALCULADO",
                "valor_brl": None,
                "calculado": {
                    "quantidade_pct": 1.0,
                    "base_referencia": "SALARIO_MINIMO",
                },
            }
            data["historico_salarial"] = [consolidada]

    # 6.ter Histórico Salarial — CONSOLIDAÇÃO por NOME CANÔNICO + EVOLUÇÃO
    #
    # Quando a IA emite N entradas adjacentes que representam o MESMO
    # componente lógico com valores diferentes em períodos contíguos (ex.:
    # ALINE 01/06/2026: "SALÁRIO ABRIL/2021" R$ 2577 + "SALÁRIO MAIO-JUN/2021"
    # R$ 2650 + "SALÁRIO JUL/2021-SET/2022" R$ 2928 + …), consolidar em UMA
    # entrada com campo `evolucao` listando as mudanças de valor por competência.
    #
    # Heurística:
    #  1) Normalizar nome (strip date markers "/AAAA", "AGO-SET/2024", anos soltos)
    #  2) Agrupar entradas ADJACENTES com mesmo nome canônico, mesmo tipo_valor
    #     (INFORMADO), mesmas incidências, mesma parcela, períodos contíguos
    #  3) Se grupo ≥ 2 entradas → 1 entrada consolidada com evolucao[]
    import re as _re_evol
    def _canonical_nome(nome: str | None) -> str:
        s = (nome or "").upper().strip()
        # Remove sufixos de data: "ABRIL/2021", "MAIO-JUN/2021", "JUL/2021-SET/2022",
        # "AGO-SET/2024", "OUT/2022-JUL/2024", anos soltos "2024", "2025"
        # Substitui padrões MES/AAAA e MES-MES/AAAA
        meses = (
            "JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ|"
            "JANEIRO|FEVEREIRO|MARCO|MARÇO|ABRIL|MAIO|JUNHO|JULHO|"
            "AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO"
        )
        pad_intervalo = _re_evol.compile(
            rf"\b({meses})(/\d{{2,4}})?(\s*-\s*({meses}))?(/\d{{2,4}})?\b"
        )
        s = pad_intervalo.sub("", s)
        # Anos soltos (2018-2030)
        s = _re_evol.sub(r"\b20\d{2}\b", "", s)
        # Múltiplos espaços/traços/barras residuais
        s = _re_evol.sub(r"[\s\-/]+", " ", s).strip()
        return s

    def _competencia_a_int(comp: str | None) -> int | None:
        try:
            m, a = (comp or "").split("/")
            return int(a) * 12 + int(m)
        except Exception:
            return None

    def _comp_seguinte(comp: str | None) -> str | None:
        n = _competencia_a_int(comp)
        if n is None:
            return None
        n += 1
        return f"{n % 12 or 12:02d}/{(n - 1) // 12}"

    # Re-fetch após a consolidação SM (6.bis) — `data["historico_salarial"]`
    # pode ter mudado, mas `_hist` ainda referencia a lista antiga.
    _hist_atual = data.get("historico_salarial")
    if isinstance(_hist_atual, list) and len(_hist_atual) >= 2:
        novo: list[dict] = []
        i = 0
        while i < len(_hist_atual):
            h_atual = _hist_atual[i] if isinstance(_hist_atual[i], dict) else None
            if not h_atual or (h_atual.get("tipo_valor") or "").upper() != "INFORMADO":
                if h_atual:
                    novo.append(h_atual)
                i += 1
                continue
            nome_canon = _canonical_nome(h_atual.get("nome"))
            inc = h_atual.get("incidencias") or {}
            parcela = h_atual.get("parcela") or "FIXA"
            grupo = [h_atual]
            j = i + 1
            while j < len(_hist_atual):
                h_prox = _hist_atual[j] if isinstance(_hist_atual[j], dict) else None
                if not h_prox:
                    break
                # Só agrupa se: mesmo nome canônico, mesmo tipo INFORMADO,
                # mesmas incidências, mesma parcela, e período contíguo.
                if (h_prox.get("tipo_valor") or "").upper() != "INFORMADO":
                    break
                if _canonical_nome(h_prox.get("nome")) != nome_canon:
                    break
                if (h_prox.get("incidencias") or {}) != inc:
                    break
                if (h_prox.get("parcela") or "FIXA") != parcela:
                    break
                # Contiguidade: competencia_final do grupo + 1 == competencia_inicial do próximo
                esperado = _comp_seguinte(grupo[-1].get("competencia_final"))
                if esperado != h_prox.get("competencia_inicial"):
                    break
                grupo.append(h_prox)
                j += 1
            if len(grupo) >= 2:
                # Consolida em 1 entrada com evolucao[]
                evolucao = [
                    {"competencia": g["competencia_inicial"], "valor_brl": float(g["valor_brl"])}
                    for g in grupo
                ]
                consolidada = {
                    "nome": nome_canon or "SALARIO",
                    "parcela": parcela,
                    "incidencias": inc,
                    "competencia_inicial": grupo[0]["competencia_inicial"],
                    "competencia_final": grupo[-1]["competencia_final"],
                    "tipo_valor": "INFORMADO",
                    "valor_brl": float(grupo[0]["valor_brl"]),
                    "calculado": None,
                    "evolucao": evolucao,
                }
                novo.append(consolidada)
                i = j
            else:
                novo.append(h_atual)
                i += 1
        if len(novo) != len(_hist_atual):
            data["historico_salarial"] = novo

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
