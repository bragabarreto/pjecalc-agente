"""
FGTS + 13º salário — cálculo dos ajustes a aplicar na página "Ocorrências do FGTS".

Regra regulatória: o recolhimento do FGTS referente ao 13º salário ocorre na competência
de DEZEMBRO (ou no mês do desligamento, se antes de dezembro), conforme Lei 8.036/90 e
orientação normativa do FGTS. O PJE-Calc NÃO adiciona automaticamente o 13º à base do
FGTS — o usuário deve ajustar manualmente cada competência de dezembro (ou desligamento).

Este módulo calcula, a partir do histórico salarial e do contrato, a lista de ajustes que
a automação deve aplicar na página "Ocorrências do FGTS" (botão "Ocorrências" da aba FGTS,
rota /pages/calculo/parametrizar-fgts.jsf).

Convenção CLT para 13º proporcional (Lei 4.090/62 + 4.749/65):
- Mais de 14 dias trabalhados num mês → conta como MÊS INTEGRAL (avos).
- 13º proporcional = salário_mensal × avos / 12.

Estrutura de retorno:
    [
        {
            "competencia": "12/2022",           # MM/AAAA
            "ano": 2022,
            "mes": 12,
            "meses_trabalhados": 5,             # avos computados naquele ano
            "salario_base": 1200.00,            # salário vigente no mês de referência
            "valor_13o_proporcional": 500.00,   # R × avos / 12
            "motivo": "13º proporcional — 5/12 (admissão em 02/08/2022)",
        },
        ...
    ]

Uso:
    ajustes = calcular_ajustes_13o_fgts(
        historico_salarial=dados.get("historico_salarial", []),
        data_admissao=contrato["data_admissao"],
        data_demissao=contrato["data_demissao"],
        incidencia_ativa=dados.get("fgts", {}).get("incidencia_13o_dezembro", True),
    )
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Any


def _parse_data_br(s: str | None) -> date | None:
    """Converte 'DD/MM/AAAA' → date; tolera None/vazio."""
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _num(v: Any) -> float:
    """Converte para float, aceitando str com vírgula BR ou None."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    # Formato BR: "1.234,56" → "1234.56"
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(s)
    except ValueError:
        return 0.0


def _salario_em(historico: list[dict], ref: date) -> float:
    """Retorna o salário vigente em `ref` consultando o histórico.

    Considera apenas entradas com natureza salarial (nome contendo 'salário' / 'salario')
    ou sem natureza explícita — variáveis (comissões, prêmios) não entram na base do 13º
    proporcional para fins de FGTS (Súmula 14 TST trata de 13º variável de outra forma,
    mas a composição do FGTS usa o salário fixo do período).
    """
    candidatos: list[tuple[date, float]] = []
    for item in historico or []:
        if not isinstance(item, dict):
            continue
        nome = (item.get("nome") or "").lower()
        # Filtrar: aceitar linhas sem nome, linhas com 'salário' (base) e
        # excluir comissões/variáveis do cálculo do 13º proporcional.
        variavel = bool(item.get("variavel"))
        if variavel:
            continue
        if nome and "salár" not in nome and "salar" not in nome:
            # Exemplos a excluir: "Comissões", "Prêmio", "Adicional" quando variável.
            # Se o nome não for 'salário' e não for variável, entra mesmo assim
            # (p. ex. nomes genéricos). Mantemos generoso.
            pass
        di = _parse_data_br(item.get("data_inicio"))
        df = _parse_data_br(item.get("data_fim"))
        if not di:
            continue
        if di <= ref and (df is None or ref <= df):
            candidatos.append((di, _num(item.get("valor"))))
    if not candidatos:
        # Fallback: primeiro salário do histórico
        for item in historico or []:
            if isinstance(item, dict) and item.get("valor") is not None:
                return _num(item.get("valor"))
        return 0.0
    # Usa o mais recente vigente em `ref`
    candidatos.sort(key=lambda x: x[0])
    return candidatos[-1][1]


def _avos_13o_no_ano(
    data_admissao: date,
    data_demissao: date,
    ano: int,
) -> tuple[int, int]:
    """Retorna (avos, mes_referencia) para um ano específico.

    - avos: número de meses contados como trabalhados em `ano`, usando a regra CLT
      dos 14 dias (>= 15 dias no mês → mês integral).
    - mes_referencia: mês em que o 13º é recolhido (12 = dezembro para anos normais;
      mês do desligamento se demissão ocorrer antes de dezembro daquele ano).
    """
    inicio_ano = date(ano, 1, 1)
    fim_ano = date(ano, 12, 31)

    periodo_ini = max(data_admissao, inicio_ano)
    periodo_fim = min(data_demissao, fim_ano)
    if periodo_ini > periodo_fim:
        return (0, 12)

    # Contar avos: para cada mês entre periodo_ini.month e periodo_fim.month,
    # contar como 1 se >= 15 dias trabalhados no mês.
    avos = 0
    m = periodo_ini.month
    y = periodo_ini.year
    while (y < periodo_fim.year) or (y == periodo_fim.year and m <= periodo_fim.month):
        ini_mes = date(y, m, 1)
        _, ultimo_dia = monthrange(y, m)
        fim_mes = date(y, m, ultimo_dia)
        dia_ini = max(periodo_ini, ini_mes)
        dia_fim = min(periodo_fim, fim_mes)
        dias_trabalhados = (dia_fim - dia_ini).days + 1
        if dias_trabalhados >= 15:
            avos += 1
        m += 1
        if m > 12:
            m = 1
            y += 1

    # Mês de referência: 12 se o contrato ainda estava ativo em dezembro daquele ano;
    # caso contrário, mês do desligamento.
    if data_demissao.year == ano and data_demissao.month < 12:
        mes_ref = data_demissao.month
    else:
        mes_ref = 12

    return (avos, mes_ref)


def calcular_ajustes_13o_fgts(
    historico_salarial: list[dict],
    data_admissao: str | None,
    data_demissao: str | None,
    incidencia_ativa: bool = True,
) -> list[dict]:
    """Calcula a lista de ajustes a aplicar na página Ocorrências do FGTS.

    Args:
        historico_salarial: lista de faixas salariais do contrato.
        data_admissao: 'DD/MM/AAAA' (obrigatório).
        data_demissao: 'DD/MM/AAAA' (obrigatório).
        incidencia_ativa: se False (sentença afastou FGTS sobre 13º) → retorna [].

    Returns:
        Lista de dicts com competência, avos, salário e valor do 13º a somar
        à base FGTS daquela competência.
    """
    if not incidencia_ativa:
        return []

    adm = _parse_data_br(data_admissao)
    dem = _parse_data_br(data_demissao)
    if not adm or not dem or adm > dem:
        return []

    ajustes: list[dict] = []
    for ano in range(adm.year, dem.year + 1):
        avos, mes_ref = _avos_13o_no_ano(adm, dem, ano)
        if avos <= 0:
            continue
        # Salário de referência: último dia do mês de referência (ou data_demissao)
        _, ultimo_dia = monthrange(ano, mes_ref)
        data_ref = min(dem, date(ano, mes_ref, ultimo_dia))
        salario_base = _salario_em(historico_salarial or [], data_ref)
        if salario_base <= 0:
            continue
        valor_13o = round(salario_base * avos / 12.0, 2)
        motivo_parts = []
        if ano == adm.year and adm.month > 1:
            motivo_parts.append(f"admissão em {adm.strftime('%d/%m/%Y')}")
        if ano == dem.year and dem.month < 12:
            motivo_parts.append(f"desligamento em {dem.strftime('%d/%m/%Y')}")
        motivo = f"13º proporcional — {avos}/12"
        if motivo_parts:
            motivo += " (" + ", ".join(motivo_parts) + ")"
        ajustes.append({
            "competencia": f"{mes_ref:02d}/{ano}",
            "ano": ano,
            "mes": mes_ref,
            "meses_trabalhados": avos,
            "salario_base": round(salario_base, 2),
            "valor_13o_proporcional": valor_13o,
            "motivo": motivo,
        })
    return ajustes
