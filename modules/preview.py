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
    honorarios = dados.get("honorarios", {})
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
        "",
    ]

    # 5. Contribuição Social
    resp_inss = contrib.get("responsabilidade") or "Ambos"
    linhas.append("CONTRIBUIÇÃO SOCIAL (INSS)")
    linhas.append(f"   Lei 11.941/2009  : {'Sim' if contrib.get('lei_11941') else 'Não'}")
    if resp_inss == "Ambos":
        linhas += [
            "   Reclamante (empregado)",
            "     → Cota-parte: alíquota progressiva tabela INSS (7,5% a 14%)",
            "     → Base: verbas salariais — apuração mês a mês pelo PJE-Calc",
            "   Reclamado (empregador)",
            "     → Cota patronal: 20% RGPS + RAT/FAP + contribuições a terceiros",
            "     → Base: mesmas verbas salariais",
            "     → Recolhimento: reclamado desconta cota do reclamante e recolhe ambas",
        ]
    elif resp_inss == "Empregador":
        linhas += [
            "   Reclamante (empregado) : sem responsabilidade INSS neste cálculo",
            "   Reclamado (empregador) : responsabilidade integral (patronal + cota do empregado)",
        ]
    elif resp_inss == "Empregado":
        linhas += [
            "   Reclamante (empregado) : recolhimento da cota-parte do empregado",
            "   Reclamado (empregador) : sem responsabilidade INSS neste cálculo",
        ]
    else:
        linhas.append(f"   Responsabilidade : {resp_inss}")
    linhas.append("")

    # 6. Imposto de Renda
    if ir.get("apurar"):
        linhas += [
            "IMPOSTO DE RENDA",
            f"   Apurar           : Sim",
            f"   Meses tributáveis: {ir.get('meses_tributaveis') or '—'}",
            f"   Dependentes      : {ir.get('dependentes') or '0'}",
            "   Reclamante (contribuinte)",
            "     → Suporta economicamente o IR sobre parcelas salariais tributáveis",
            "     → Tabela progressiva (0% a 27,5%) sobre rendimento mensal apurado",
            "   Reclamado (fonte pagadora)",
            "     → Deve reter e recolher o IR na fonte (DIRF/DARF)",
            "     → Responsabilidade solidária por omissão de retenção",
            "",
        ]

    # 7. Honorários Advocatícios
    parte_hon = honorarios.get("parte_devedora") or "—"
    pct_hon = honorarios.get("percentual")
    val_hon = honorarios.get("valor_fixo")
    linhas.append("HONORÁRIOS ADVOCATÍCIOS")
    if parte_hon == "Reclamado":
        linhas.append("   Reclamado (devedor — sucumbência integral ou parcial):")
        if pct_hon:
            linhas.append(f"     → {_fmt_pct(pct_hon)} sobre o valor da condenação")
        if val_hon:
            linhas.append(f"     → Valor fixo: {_fmt_valor(val_hon)}")
        if not pct_hon and not val_hon:
            linhas.append("     → Percentual/valor a apurar")
        linhas.append("   Reclamante : isento de honorários sucumbenciais")
    elif parte_hon == "Reclamante":
        linhas.append("   Reclamante (devedor — sucumbência nos pedidos indeferidos):")
        if pct_hon:
            linhas.append(f"     → {_fmt_pct(pct_hon)} sobre o valor dos pedidos indeferidos")
        if val_hon:
            linhas.append(f"     → Valor fixo: {_fmt_valor(val_hon)}")
        if not pct_hon and not val_hon:
            linhas.append("     → Percentual/valor a apurar")
        linhas.append("   Reclamado  : isento de honorários sucumbenciais")
    elif parte_hon == "Ambos":
        pct_reclamado = honorarios.get("percentual_reclamado") or pct_hon
        pct_reclamante = honorarios.get("percentual_reclamante") or pct_hon
        linhas.append("   Sucumbência recíproca — ambas as partes devem honorários:")
        linhas.append("   Reclamante (pedidos indeferidos):")
        if pct_reclamante:
            linhas.append(f"     → {_fmt_pct(pct_reclamante)} sobre o valor dos pedidos indeferidos")
        else:
            linhas.append("     → Percentual a apurar — preencher campo na prévia")
        linhas.append("   Reclamado (pedidos deferidos):")
        if pct_reclamado:
            linhas.append(f"     → {_fmt_pct(pct_reclamado)} sobre o valor da condenação")
        else:
            linhas.append("     → Percentual a apurar — preencher campo na prévia")
        linhas.append("   ⚠ Compensação vedada (cada parte paga ao advogado adverso)")
    else:
        linhas += [
            f"   Parte devedora: {parte_hon}",
            f"   Percentual    : {_fmt_pct(pct_hon)}",
            f"   Valor fixo    : {_fmt_valor(val_hon)}",
        ]
    if honorarios.get("periciais"):
        linhas.append(f"   Periciais (laudo técnico): {_fmt_valor(honorarios.get('periciais'))}")
    linhas.append("")

    # 7a. Custas Processuais (CLT art. 789 — 2% do valor da condenação, mín. R$ 10,64)
    linhas.append("CUSTAS PROCESSUAIS  (CLT art. 789)")
    custas_resp = _inferir_responsavel_custas(honorarios)
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
        f"   Índice Correção : {correcao.get('indice_correcao') or 'Tabela JT Única Mensal'}",
        f"   Base dos Juros  : {correcao.get('base_juros') or 'Verbas'}",
        f"   Taxa de Juros   : {correcao.get('taxa_juros') or 'Juros Padrão (1% a.m.)'}",
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


def aplicar_edicao_usuario(
    dados: dict[str, Any],
    campo: str,
    novo_valor: Any,
) -> dict[str, Any]:
    """
    Aplica a edição de um campo na estrutura de dados.
    campo no formato 'secao.subcampo' (ex: 'contrato.admissao').
    """
    partes = campo.split(".", 1)
    if len(partes) == 2:
        secao, subcampo = partes
        if secao in dados and isinstance(dados[secao], dict):
            dados[secao][subcampo] = novo_valor
    else:
        dados[campo] = novo_valor
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
    """
    todas = (
        verbas_mapeadas.get("predefinidas", [])
        + verbas_mapeadas.get("personalizadas", [])
        + verbas_mapeadas.get("nao_reconhecidas", [])
    )
    if 0 <= indice < len(todas):
        todas[indice][campo] = novo_valor
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


def _inferir_responsavel_custas(honorarios: dict[str, Any]) -> str:
    """
    Infere o responsável pelas custas processuais com base na parte devedora dos honorários.
    Honorários e custas seguem a sucumbência: quem perdeu paga ambos.
    Retorna "Reclamado", "Reclamante", "Ambos" ou "" (indefinido).
    """
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
