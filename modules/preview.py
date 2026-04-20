# modules/preview.py — Geração e Exibição da Prévia dos Parâmetros
# Manual Técnico PJE-Calc, Seção 5

from __future__ import annotations

from typing import Any


# ── Função principal ──────────────────────────────────────────────────────────

def gerar_previa(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
) -> str:
    """
    Gera a prévia formatada de todos os parâmetros para exibição ao usuário,
    na mesma sequência de páginas do PJE-Calc (Manual, Seção 5.1).
    """
    linhas: list[str] = []

    processo = dados.get("processo", {})
    contrato = dados.get("contrato", {})
    prescricao = dados.get("prescricao", {})
    aviso = dados.get("aviso_previo", {})
    fgts = dados.get("fgts", {})
    if isinstance(fgts, str):
        try:
            import json as _json
            fgts = _json.loads(fgts)
        except Exception:
            fgts = {}
    honorarios = dados.get("honorarios", [])
    correcao = dados.get("correcao_juros", {})
    contrib = dados.get("contribuicao_social", {})
    ir = dados.get("imposto_renda", {})
    campos_ausentes = dados.get("campos_ausentes", [])
    alertas = dados.get("alertas", [])

    todas_verbas = (
        verbas_mapeadas.get("predefinidas", [])
        + verbas_mapeadas.get("personalizadas", [])
        + verbas_mapeadas.get("nao_reconhecidas", [])
    )
    reflexas = verbas_mapeadas.get("reflexas_sugeridas", [])

    num_processo = processo.get("numero") or "—"
    reclamante = processo.get("reclamante") or "—"

    # Cabeçalho
    linhas += [
        "═" * 67,
        " PRÉVIA DO PREENCHIMENTO — PJE-CALC",
        f" Processo: {num_processo}",
        "═" * 67,
        "",
    ]

    # 1. Dados do Processo
    linhas += [
        "DADOS DO PROCESSO",
        f"   Reclamante  : {reclamante}",
        f"   Reclamado   : {processo.get('reclamado') or '—'}",
        f"   Estado/Mun. : {processo.get('estado') or '—'} / {processo.get('municipio') or '—'}",
        f"   Vara        : {processo.get('vara') or '—'}",
        "",
    ]

    # 2. Parâmetros do Cálculo
    regime = contrato.get("regime") or "Tempo Integral"
    carga = contrato.get("carga_horaria") or 220
    presc_q = "Marcada" if prescricao.get("quinquenal") else "Não marcada"
    presc_f = "Marcada" if prescricao.get("fgts") else "Não marcada"
    tipo_ap = aviso.get("tipo") or "—"
    projetar = "Sim" if aviso.get("projetar") else "Não"

    linhas += [
        "PARÂMETROS DO CÁLCULO",
        f"   Admissão      : {_fmt(contrato.get('admissao'))}",
        f"   Demissão      : {_fmt(contrato.get('demissao'))}",
        f"   Ajuizamento   : {_fmt(contrato.get('ajuizamento'))}",
        f"   Regime        : {regime}",
        f"   Carga Horária : {carga} h/mês",
        f"   Maior Remun.  : {_fmt_valor(contrato.get('maior_remuneracao'))}",
        f"   Ult. Remun.   : {_fmt_valor(contrato.get('ultima_remuneracao'))}",
        f"   Prescrição Quinquenal: {presc_q}",
        f"   Prescrição FGTS     : {presc_f}",
        f"   Aviso Prévio  : {tipo_ap} (projetar: {projetar})",
        "",
    ]

    # 2a. Histórico Salarial
    historico_salarial = dados.get("historico_salarial", [])
    linhas.append(f"HISTÓRICO SALARIAL ({len(historico_salarial)} registro(s))")
    if not historico_salarial:
        linhas.append("   Nenhum registro de histórico salarial identificado")
    else:
        for i, reg in enumerate(historico_salarial):
            nome = reg.get("nome") or "Salário"
            dt_inicio = _fmt(reg.get("data_inicio"))
            dt_fim = _fmt(reg.get("data_fim"))
            valor = _fmt_valor(reg.get("valor") or reg.get("salario"))
            _fgts_flag = "FGTS" if reg.get("incidencia_fgts", True) else ""
            _cs_flag = "CS" if reg.get("incidencia_cs", True) else ""
            incid = " | ".join(filter(None, [_fgts_flag, _cs_flag]))
            linhas.append(f"   [{i}] {nome}: {dt_inicio} a {dt_fim} — {valor} [{incid}]")
    linhas.append("")

    # 2b. Faltas
    faltas = dados.get("faltas", [])
    linhas.append(f"FALTAS ({len(faltas)} registro(s))")
    if not faltas:
        linhas.append("   Nenhuma falta identificada")
    else:
        for i, falta in enumerate(faltas):
            dt_inicio = _fmt(falta.get("data_inicial") or falta.get("data_inicio"))
            dt_fim = _fmt(falta.get("data_final") or falta.get("data_fim"))
            justificada = "Justificada" if falta.get("justificada") else "Injustificada"
            dias = falta.get("dias") or "—"
            linhas.append(f"   [{i}] {dt_inicio} a {dt_fim} — {dias} dia(s), {justificada}")
    linhas.append("")

    # 2c. Férias
    ferias = dados.get("ferias", [])
    linhas.append(f"FÉRIAS ({len(ferias)} registro(s))")
    if not ferias:
        linhas.append("   Nenhum período de férias identificado")
    else:
        for i, fer in enumerate(ferias):
            dt_inicio = _fmt(fer.get("periodo_inicio") or fer.get("data_inicio"))
            dt_fim = _fmt(fer.get("periodo_fim") or fer.get("data_fim"))
            situacao = fer.get("situacao") or "—"
            dias = fer.get("dias") or "—"
            linhas.append(f"   [{i}] {dt_inicio} a {dt_fim} — {dias} dia(s), {situacao}")
    linhas.append("")

    # 2d. Duração do Trabalho / Cartão de Ponto
    dur = dados.get("duracao_trabalho") or {}
    tipo_ap = dur.get("tipo_apuracao")
    if tipo_ap:
        forma = dur.get("forma_apuracao_pjecalc") or "—"
        adicional = dur.get("adicional_he_percentual")
        adic_str = f"{int(adicional * 100)}%" if adicional else "—"
        preen = dur.get("preenchimento_jornada") or "livre"
        escala = dur.get("escala_tipo") or ""
        preen_label = {"livre": "Livre", "programacao_semanal": "Programação Semanal", "escala": f"Escala ({escala})"}.get(preen, preen)
        linhas += [
            "DURAÇÃO DO TRABALHO / CARTÃO DE PONTO",
            f"   Tipo Apuração   : {tipo_ap}",
            f"   Forma PJE-Calc  : {forma}",
            f"   Adicional HE    : {adic_str}",
            f"   Preenchimento   : {preen_label}",
        ]
        if tipo_ap == "apuracao_jornada" and preen in ("programacao_semanal", "escala"):
            grade = dur.get("grade_semanal")
            if grade and isinstance(grade, dict):
                linhas.append("   Grade Semanal:")
                _labels = {"seg":"Seg","ter":"Ter","qua":"Qua","qui":"Qui",
                           "sex":"Sex","sab":"Sáb","dom":"Dom","feriado":"Fer"}
                for dia, label in _labels.items():
                    dia_data = grade.get(dia)
                    if dia_data and isinstance(dia_data, dict) and dia_data.get("turnos"):
                        turnos_str = " / ".join(
                            f"{t.get('entrada','?')}-{t.get('saida','?')}"
                            for t in dia_data["turnos"]
                        )
                        linhas.append(f"     {label}: {turnos_str}")
                    else:
                        linhas.append(f"     {label}: —")
            else:
                entrada = dur.get("jornada_entrada") or "—"
                saida = dur.get("jornada_saida") or "—"
                interv = dur.get("intervalo_minutos")
                interv_str = f"{interv} min" if interv else "—"
                linhas.append(f"   Horário         : {entrada} às {saida} (intervalo {interv_str})")
            dias_semana = []
            for d, label in [("seg","Seg"),("ter","Ter"),("qua","Qua"),
                             ("qui","Qui"),("sex","Sex"),("sab","Sáb"),("dom","Dom")]:
                v = dur.get(f"jornada_{d}")
                dias_semana.append(f"{label}={v}h" if v else f"{label}=—")
            linhas.append(f"   Jornada/dia     : {', '.join(dias_semana)}")
            linhas.append(f"   Semanal/Mensal  : {dur.get('jornada_semanal_cartao') or '—'}h / {dur.get('jornada_mensal_cartao') or '—'}h")
        elif tipo_ap == "apuracao_jornada":
            linhas.append("   (Modo Livre — jornada será preenchida manualmente após importação PJC)")
        elif tipo_ap == "quantidade_fixa":
            linhas.append(f"   HE/Mês          : {dur.get('qt_horas_extras_mes') or '—'}")
            linhas.append(f"   HE/Dia          : {dur.get('qt_horas_extras_dia') or '—'}")
        linhas.append("")
    else:
        linhas += [
            "DURAÇÃO DO TRABALHO / CARTÃO DE PONTO",
            "   Não extraído (sem condenação em horas extras ou dados insuficientes)",
            "",
        ]

    # 3. Verbas
    total_verbas = len(todas_verbas) + len(reflexas)
    linhas.append(f"VERBAS ({total_verbas} identificadas)")

    for i, verba in enumerate(todas_verbas, start=1):
        linhas += _formatar_verba(i, verba, eh_reflexa=False)

    for i, reflexa in enumerate(reflexas, start=len(todas_verbas) + 1):
        linhas += _formatar_reflexa(i, reflexa)

    linhas.append("")

    # 4. FGTS
    linhas += [
        "FGTS",
        f"   Alíquota  : {_fmt_pct(fgts.get('aliquota'))}",
        f"   Multa 40% : {'Sim' if fgts.get('multa_40') else 'Não'}",
        f"   Multa 467 : {'Sim' if fgts.get('multa_467') else 'Não'}",
        f"   FGTS s/ 13º em dezembro : {'Sim' if fgts.get('incidencia_13o_dezembro', True) else 'Não'}",
    ]
    _ajustes_13o = fgts.get("ajustes_ocorrencias_13o") or []
    if _ajustes_13o:
        linhas.append("   Ajustes Ocorrências FGTS (13º proporcional):")
        for a in _ajustes_13o:
            def _flt(x, default=0.0):
                try:
                    return float(x)
                except (TypeError, ValueError):
                    return default
            linhas.append(
                f"      • {a.get('competencia','—')}  "
                f"+R$ {_flt(a.get('valor_13o_proporcional')):.2f}  "
                f"({a.get('meses_trabalhados','?')}/12 de "
                f"R$ {_flt(a.get('salario_base')):.2f})"
            )
    linhas.append("")

    # 5. Contribuição Social
    linhas.append("CONTRIBUIÇÃO SOCIAL (INSS)")
    linhas.append(f"   Lei 11.941/2009                   : {'Sim' if contrib.get('lei_11941') else 'Não'}")
    linhas.append(f"   Apurar s/ salários devidos (seg.) : {'Sim' if contrib.get('apurar_segurado_salarios_devidos', True) else 'Não'}")
    linhas.append(f"   Cobrar do reclamante (cota empr.) : {'Sim' if contrib.get('cobrar_do_reclamante', True) else 'Não'}")
    linhas.append(f"   Com correção trabalhista           : {'Sim' if contrib.get('com_correcao_trabalhista', True) else 'Não'}")
    linhas.append(f"   Apurar s/ salários pagos          : {'Sim' if contrib.get('apurar_sobre_salarios_pagos', False) else 'Não'}")
    linhas.append("")

    # 6. Imposto de Renda
    if ir.get("apurar"):
        linhas += [
            "IMPOSTO DE RENDA",
            f"   Apurar                       : Sim",
            f"   Tributação exclusiva (RRA)   : {'Sim' if ir.get('tributacao_exclusiva') else 'Não'}",
            f"   Regime de caixa              : {'Sim' if ir.get('regime_de_caixa') else 'Não'}",
            f"   Tributação em separado       : {'Sim' if ir.get('tributacao_em_separado') else 'Não'}",
            f"   Dedução INSS                 : {'Sim' if ir.get('deducao_inss', True) else 'Não'}",
            f"   Dedução hon. reclamante      : {'Sim' if ir.get('deducao_honorarios_reclamante') else 'Não'}",
            f"   Dedução pensão alimentícia   : {'Sim' if ir.get('deducao_pensao_alimenticia') else 'Não'}",
        ]
        if ir.get("deducao_pensao_alimenticia") and ir.get("valor_pensao"):
            linhas.append(f"   Valor da pensão              : {_fmt_valor(ir.get('valor_pensao'))}")
        linhas += [
            f"   Meses tributáveis            : {ir.get('meses_tributaveis') or '—'}",
            f"   Dependentes                  : {ir.get('dependentes') or '0'}",
            "",
        ]

    # 7. Honorários Advocatícios
    linhas.append("HONORÁRIOS ADVOCATÍCIOS")
    if not honorarios:
        linhas.append("   Nenhum honorário identificado / indeferidos")
    else:
        for i, hon in enumerate(honorarios, start=1):
            devedor = hon.get("devedor") or "—"
            tipo = hon.get("tipo") or "SUCUMBENCIAIS"
            base = hon.get("base_apuracao") or "—"
            pct = hon.get("percentual")
            val = hon.get("valor_informado")
            ir_hon = hon.get("apurar_ir", False)
            linhas.append(f"   [{i}] Devedor: {devedor} | Tipo: {tipo}")
            linhas.append(f"       Base de apuração: {base}")
            if pct is not None:
                linhas.append(f"       Percentual: {_fmt_pct(pct)}")
            if val is not None:
                linhas.append(f"       Valor informado: {_fmt_valor(val)}")
            linhas.append(f"       Apurar IR: {'Sim' if ir_hon else 'Não'}")
    periciais = dados.get("honorarios_periciais")
    if periciais:
        linhas.append(f"   Periciais (laudo técnico): {_fmt_valor(periciais)}")
    linhas.append("")

    # 7a. Custas Processuais (CLT art. 789 — 2% do valor da condenação, mín. R$ 10,64)
    linhas.append("CUSTAS PROCESSUAIS  (CLT art. 789)")
    custas_resp = _inferir_responsavel_custas(honorarios, dados)
    if custas_resp == "Reclamado":
        linhas += [
            "   Reclamado : responsável pelo recolhimento das custas",
            "   Reclamante: isento (CLT art. 790-A, I)",
        ]
    elif custas_resp == "Reclamante":
        linhas += [
            "   Reclamante: responsável pelo recolhimento das custas",
            "   Reclamado : sem custas a recolher",
        ]
    elif custas_resp == "Ambos":
        linhas += [
            "   Sucumbência recíproca — custas divididas proporcionalmente:",
            "   Reclamante: 2% sobre o valor dos pedidos indeferidos",
            "   Reclamado : 2% sobre o valor da condenação",
        ]
    else:
        linhas.append("   Responsabilidade: a definir conforme dispositivo da sentença")
    valor_causa = processo.get("valor_causa")
    if valor_causa:
        try:
            estimativa = max(10.64, float(valor_causa) * 0.02)
            linhas.append(f"   Estimativa (base: valor da causa R$ {_fmt_valor(valor_causa)}): {_fmt_valor(estimativa)}")
        except (TypeError, ValueError):
            pass
    linhas.append("   (valor exato calculado pelo PJE-Calc sobre o total liquidado)")
    linhas.append("")

    # 8. Correção, Juros e Multa
    linhas += [
        "CORREÇÃO, JUROS E MULTA",
        f"   Índice Correção : {correcao.get('indice_correcao') or 'TUACDT'}",
        f"   Base dos Juros  : {correcao.get('base_juros') or 'Verbas'}",
        f"   Taxa de Juros   : {correcao.get('taxa_juros') or 'PADRAO'}",
        f"   JAM (FGTS)      : {'Sim' if correcao.get('jam_fgts') else 'Não'}",
        "",
    ]

    # Alertas e campos ausentes
    if campos_ausentes or alertas:
        linhas.append("─" * 67)

    if campos_ausentes:
        linhas.append("CAMPOS AGUARDANDO CONFIRMAÇÃO / PREENCHIMENTO:")
        for campo in campos_ausentes:
            linhas.append(f"   → {campo}")
        linhas.append("")

    if alertas:
        linhas.append("ALERTAS:")
        for alerta in alertas:
            linhas.append(f"   ! {alerta}")
        linhas.append("")

    # Menu de ação
    linhas += [
        "─" * 67,
        "  [C] Confirmar e iniciar preenchimento no PJE-Calc",
        "  [E] Editar um parâmetro específico",
        "  [A] Adicionar verba não listada",
        "  [X] Cancelar",
        "─" * 67,
    ]

    return "\n".join(linhas)


def exibir_previa(dados: dict[str, Any], verbas_mapeadas: dict[str, Any]) -> None:
    """Exibe a prévia formatada no terminal com suporte a Rich se disponível."""
    texto = gerar_previa(dados, verbas_mapeadas)
    try:
        from rich.console import Console
        from rich.syntax import Syntax
        console = Console()
        console.print(texto)
    except ImportError:
        print(texto)


def _deep_set(obj: Any, path: str, valor: Any) -> None:
    """
    Define um valor em um caminho pontilhado com suporte a arrays.
    Exemplos:
      _deep_set(d, "processo.numero", "123")
      _deep_set(d, "duracao_trabalho.grade_semanal.seg.turnos[0].entrada", "07:00")
    Cria dicts intermediários se necessário.
    """
    import re as _re
    # Tokenizar: "a.b[0].c" → ["a", "b", "[0]", "c"]
    tokens: list[str | int] = []
    for part in path.split("."):
        # Separar array indices: "turnos[0]" → "turnos", 0
        m = _re.match(r'^(.+?)\[(\d+)\]$', part)
        if m:
            tokens.append(m.group(1))
            tokens.append(int(m.group(2)))
        else:
            tokens.append(part)

    cur = obj
    for i, token in enumerate(tokens[:-1]):
        next_token = tokens[i + 1]
        if isinstance(token, int):
            if isinstance(cur, list) and 0 <= token < len(cur):
                cur = cur[token]
            else:
                return  # index out of range
        else:
            if not isinstance(cur, dict):
                return
            if token not in cur or cur[token] is None:
                # Create intermediate container
                cur[token] = [] if isinstance(next_token, int) else {}
            cur = cur[token]

    last = tokens[-1]
    if isinstance(last, int):
        if isinstance(cur, list) and 0 <= last < len(cur):
            cur[last] = valor
    elif isinstance(cur, dict):
        cur[last] = valor


def aplicar_edicao_usuario(
    dados: dict[str, Any],
    campo: str,
    novo_valor: Any,
) -> dict[str, Any]:
    """
    Aplica a edição de um campo na estrutura de dados.

    Formatos suportados:
    - 'secao.subcampo'              → dados["secao"]["subcampo"] = novo_valor
    - 'honorarios[N].subcampo'      → dados["honorarios"][N]["subcampo"] = novo_valor
    - 'honorarios.add'              → append registro vazio à lista
    - 'honorarios.remove[N]'        → remove índice N da lista
    - 'historico_salarial[N].campo' → dados["historico_salarial"][N]["campo"] = novo_valor
    - 'historico_salarial.add'      → append registro vazio
    - 'historico_salarial.remove[N]'→ remove índice N
    - 'faltas[N].campo'             → dados["faltas"][N]["campo"] = novo_valor
    - 'faltas.add'                  → append registro vazio
    - 'faltas.remove[N]'            → remove índice N
    - 'ferias[N].campo'             → dados["ferias"][N]["campo"] = novo_valor
    - 'ferias.add'                  → append registro vazio
    - 'ferias.remove[N]'            → remove índice N
    - 'campo_simples'               → dados["campo_simples"] = novo_valor
    """
    import re as _re

    # Coerção de booleanos enviados como string pelo HTML (deve vir antes de tudo)
    if novo_valor == "true":
        novo_valor = True
    elif novo_valor == "false":
        novo_valor = False

    # honorarios[N].campo
    m = _re.match(r'^honorarios\[(\d+)\]\.(.+)$', campo)
    if m:
        idx = int(m.group(1))
        subcampo = m.group(2)
        lista = dados.get("honorarios", [])
        if 0 <= idx < len(lista):
            lista[idx][subcampo] = novo_valor
            dados["honorarios"] = lista
        return dados

    # honorarios.add
    if campo == "honorarios.add":
        lista = dados.get("honorarios", [])
        lista.append({
            "tipo": "SUCUMBENCIAIS",
            "devedor": novo_valor or "RECLAMADO",
            "tipo_valor": "CALCULADO",
            "base_apuracao": "BRUTO",
            "percentual": None,
            "valor_informado": None,
            "apurar_ir": False,
        })
        dados["honorarios"] = lista
        return dados

    # honorarios.remove[N]
    m = _re.match(r'^honorarios\.remove\[(\d+)\]$', campo)
    if m:
        idx = int(m.group(1))
        lista = dados.get("honorarios", [])
        if 0 <= idx < len(lista):
            lista.pop(idx)
            dados["honorarios"] = lista
        return dados

    # ── Arrays genéricos: historico_salarial, faltas, ferias ─────────────────

    _ARRAY_DEFAULTS: dict[str, dict[str, Any]] = {
        "historico_salarial": {
            "nome": "Salário",
            "data_inicio": None,
            "data_fim": None,
            "valor": None,
            "variavel": False,
            "tipo_valor": "INFORMADO",
            "incidencia_fgts": True,
            "incidencia_cs": True,
            "prop_fgts": False,
            "prop_cs": False,
            "fgts_recolhido": False,
            "cs_recolhida": False,
            "ocorrencias": [],
        },
        "faltas": {
            "data_inicial": None,
            "data_final": None,
            "justificada": False,
            "descricao": "",
        },
        "ferias": {
            "situacao": None,
            "periodo_inicio": None,
            "periodo_fim": None,
            "abono": False,
            "dobra": False,
        },
        "multas_indenizacoes": {
            "descricao": "",
            "credor_devedor": "RECLAMANTE_RECLAMADO",
            "tipo_valor": "CALCULADO",
            "base_calculo": "PRINCIPAL",
            "aliquota": None,
            "valor": None,
        },
    }

    _ARRAY_NAMES = "|".join(_ARRAY_DEFAULTS.keys())

    # array[N].campo
    m = _re.match(rf'^({_ARRAY_NAMES})\[(\d+)\]\.(.+)$', campo)
    if m:
        arr_name = m.group(1)
        idx = int(m.group(2))
        subcampo = m.group(3)
        lista = dados.get(arr_name, [])
        if 0 <= idx < len(lista):
            lista[idx][subcampo] = novo_valor
            dados[arr_name] = lista
        return dados

    # array.add
    m = _re.match(rf'^({_ARRAY_NAMES})\.add$', campo)
    if m:
        arr_name = m.group(1)
        lista = dados.get(arr_name, [])
        lista.append(dict(_ARRAY_DEFAULTS[arr_name]))
        dados[arr_name] = lista
        return dados

    # array.remove[N]
    m = _re.match(rf'^({_ARRAY_NAMES})\.remove\[(\d+)\]$', campo)
    if m:
        arr_name = m.group(1)
        idx = int(m.group(2))
        lista = dados.get(arr_name, [])
        if 0 <= idx < len(lista):
            lista.pop(idx)
            dados[arr_name] = lista
        return dados

    # Deep path: secao.sub.sub2.turnos[0].campo — suporta aninhamento arbitrário
    _deep_set(dados, campo, novo_valor)
    return dados


def aplicar_edicao_verba(
    verbas_mapeadas: dict[str, Any],
    indice: int,
    campo: str,
    novo_valor: Any,
) -> dict[str, Any]:
    """
    Edita um campo de uma verba específica pelo índice (base 0).
    Percorre predefinidas → personalizadas → nao_reconhecidas em ordem.

    Quando o campo 'tipo' muda (Principal ↔ Reflexa), sincroniza com
    a estratégia de preenchimento e limpa/configura verba_principal_ref.
    """
    # Campos booleanos — o frontend envia strings "true"/"false".
    # PostgreSQL BOOLEAN rejeita string "false" → converter para bool nativo.
    _CAMPOS_BOOL = {
        "incidencia_fgts", "incidencia_inss", "incidencia_ir",
        "compor_principal", "mapeada",
    }
    if campo in _CAMPOS_BOOL and isinstance(novo_valor, str):
        novo_valor = novo_valor.strip().lower() in ("true", "1", "yes", "sim")

    todas = (
        verbas_mapeadas.get("predefinidas", [])
        + verbas_mapeadas.get("personalizadas", [])
        + verbas_mapeadas.get("nao_reconhecidas", [])
    )
    if 0 <= indice < len(todas):
        todas[indice][campo] = novo_valor

        # Sincronizar tipo ↔ estratégia de preenchimento
        if campo == "tipo":
            ep = todas[indice].get("estrategia_preenchimento", {})
            ep["tipo_verba"] = novo_valor
            ep["baseado_em"] = "usuario"
            todas[indice]["estrategia_preenchimento"] = ep

            # Limpar verba_principal_ref se mudou para Principal
            if novo_valor == "Principal":
                todas[indice].pop("verba_principal_ref", None)
                ep.pop("verba_principal_ref", None)

        # Sincronizar verba_principal_ref → estratégia
        elif campo == "verba_principal_ref":
            ep = todas[indice].get("estrategia_preenchimento", {})
            ep["verba_principal_ref"] = novo_valor
            ep["baseado_em"] = "usuario"
            todas[indice]["estrategia_preenchimento"] = ep

    return verbas_mapeadas


# ── Auxiliares de formatação ──────────────────────────────────────────────────

def _fmt(valor: Any) -> str:
    return str(valor) if valor is not None else "—"


def _fmt_valor(valor: Any) -> str:
    if valor is None:
        return "—"
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(valor)


def _fmt_pct(valor: Any) -> str:
    if valor is None:
        return "—"
    try:
        return f"{float(valor) * 100:.1f}%"
    except (ValueError, TypeError):
        return str(valor)


def _inferir_responsavel_custas(honorarios: list | dict, dados: dict[str, Any] | None = None) -> str:
    """
    Infere o responsável pelas custas processuais com base nos honorários.
    Honorários e custas seguem a sucumbência: quem perdeu paga ambos.
    Retorna "Reclamado", "Reclamante", "Ambos" ou "" (indefinido).
    """
    # Schema novo: lista de registros
    if isinstance(honorarios, list):
        devedores = {h.get("devedor", "").upper() for h in honorarios}
        if "RECLAMADO" in devedores and "RECLAMANTE" in devedores:
            return "Ambos"
        if "RECLAMADO" in devedores:
            return "Reclamado"
        if "RECLAMANTE" in devedores:
            return "Reclamante"
        return ""
    # Schema legado: dict com parte_devedora
    parte = honorarios.get("parte_devedora") or ""
    if parte in ("Reclamado", "Reclamante", "Ambos"):
        return parte
    return ""


def _formatar_verba(idx: int, verba: dict[str, Any], eh_reflexa: bool) -> list[str]:
    nome = verba.get("nome_pjecalc") or verba.get("nome_sentenca") or "—"
    tipo = verba.get("tipo") or "Principal"
    caract = verba.get("caracteristica") or "—"
    ocorr = verba.get("ocorrencia") or "—"
    periodo_i = verba.get("periodo_inicio") or "—"
    periodo_f = verba.get("periodo_fim") or "—"
    base = verba.get("base_calculo") or "—"
    pct = _fmt_pct(verba.get("percentual"))
    conf = verba.get("confianca", 1.0)
    conf_str = f"[confiança: {conf:.0%}]" if conf < 0.85 else ""
    lancamento = verba.get("lancamento") or "Manual"
    nao_rec = " [NAO RECONHECIDA - revisar]" if verba.get("nao_reconhecida") else ""

    incid = []
    if verba.get("incidencia_fgts"):
        incid.append("FGTS")
    if verba.get("incidencia_inss"):
        incid.append("INSS")
    if verba.get("incidencia_ir"):
        incid.append("IR")
    incid_str = " | ".join(incid) if incid else "—"

    return [
        f"   ┌─ [{idx}] {nome}{nao_rec} {conf_str}",
        f"   │  Lançamento  : {lancamento}",
        f"   │  Tipo        : {tipo} | Característica: {caract}",
        f"   │  Ocorrência  : {ocorr}",
        f"   │  Período     : {periodo_i} a {periodo_f}",
        f"   │  Base calc.  : {base}",
        f"   │  Percentual  : {pct}",
        f"   │  Incidências : {incid_str}",
        "   │",
    ]


def _formatar_reflexa(idx: int, reflexa: dict[str, Any]) -> list[str]:
    nome = reflexa.get("nome") or "—"
    comport = reflexa.get("comportamento_base") or "—"
    return [
        f"   ├─ [{idx}] {nome} (REFLEXA SUGERIDA)",
        f"   │  Comportamento Base: {comport}",
        "   │",
    ]
