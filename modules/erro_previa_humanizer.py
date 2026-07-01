"""Humanizador de erros de validação da prévia (#80-AE).

Traduz erros técnicos (Pydantic ValidationError, prévia incompleta) em mensagens
CLARAS para o usuário — o que deu errado + como corrigir — em vez de despejar o
traceback/JSON cru. Usado quando um erro IMPEDE o início da automação:
  • POST /api/previa/v2/{id}/confirmar  (422)
  • executar_v2_como_generator          (ERRO: ...)

Formato de saída (estável, testável):
    {
      "titulo": "A prévia tem N problema(s) que impedem iniciar a automação",
      "erros": [
        {"entidade": "Verba 'DEDUÇÃO...' (item 9)",
         "campo": "valor_devido",
         "o_que": "...",
         "como_corrigir": "..."},
        ...
      ],
      "tecnico": "<mensagem crua p/ suporte>"
    }
"""
from __future__ import annotations

from typing import Any


def _nome_entidade(loc: tuple, payload: dict) -> str:
    """Descreve a entidade (verba/histórico/cartão/...) a partir do `loc` do erro."""
    if not loc:
        return "Prévia"
    raiz = loc[0]
    # verbas_principais[N] → "Verba 'NOME' (item N+1)"
    if raiz in ("verbas_principais", "verbas") and len(loc) >= 2 and isinstance(loc[1], int):
        idx = loc[1]
        try:
            v = (payload.get("verbas_principais") or payload.get("verbas") or [])[idx]
            nome = v.get("nome_pjecalc") or v.get("nome_sentenca") or v.get("expresso_alvo") or "?"
        except Exception:
            nome = "?"
        return f"Verba “{nome}” (item {idx + 1})"
    if raiz == "historico_salarial" and len(loc) >= 2 and isinstance(loc[1], int):
        idx = loc[1]
        try:
            h = (payload.get("historico_salarial") or [])[idx]
            nome = h.get("nome") or "?"
        except Exception:
            nome = "?"
        return f"Histórico salarial “{nome}” (item {idx + 1})"
    if raiz in ("cartao_de_ponto", "cartoes_de_ponto"):
        return "Cartão de ponto"
    if raiz == "honorarios":
        return "Honorários"
    if raiz == "correcao_juros_multa":
        return "Correção / Juros / Multa"
    if raiz == "processo":
        return "Dados do processo"
    if raiz == "parametros_calculo":
        return "Parâmetros do cálculo"
    return str(raiz).replace("_", " ").capitalize()


def _campo_legivel(loc: tuple) -> str:
    """Último segmento não-numérico e não-classe do loc → nome de campo amigável."""
    partes = [p for p in loc if isinstance(p, str)]
    # descartar nomes de classe do Union (ValorDevidoInformado, etc.)
    partes = [p for p in partes if not (p[:1].isupper() and any(c.islower() for c in p))]
    if not partes:
        return ""
    return partes[-1]


# (substring da msg técnica) → (o_que, como_corrigir). Primeira que casar vence.
_REGRAS: list[tuple[str, str, str]] = [
    (
        "valor=INFORMADO exige",
        "A verba está marcada como INFORMADO, mas não tem um Valor Devido maior "
        "que zero — e também não é uma dedução (que teria valor em Valor Pago).",
        "Abra esta verba na prévia e preencha o Valor Devido (> 0). Se a sentença "
        "fixou valor por dia/semana, mensalize. Se for cálculo pelo sistema, "
        "mude para CALCULADO e preencha base, divisor, multiplicador e quantidade.",
    ),
    (
        "valor=CALCULADO exige",
        "A verba está marcada como CALCULADO, mas falta a fórmula de cálculo "
        "(base, divisor, multiplicador e quantidade).",
        "Abra a verba e complete a fórmula (base de cálculo, divisor, "
        "multiplicador e quantidade). Se a sentença já fixou o valor, mude para "
        "INFORMADO e preencha o Valor Devido.",
    ),
    (
        "base_calculo.tipo é obrigatório",
        "A verba é CALCULADO mas não tem uma Base de Cálculo escolhida.",
        "Selecione a Base de Cálculo da verba (ex.: Maior Remuneração, "
        "Histórico Salarial, Salário Mínimo).",
    ),
    (
        "quantidade.tipo é obrigatório",
        "A verba é CALCULADO mas não tem o tipo de Quantidade definido.",
        "Defina a Quantidade da fórmula (ex.: Informada, Avos, "
        "Importada do Cartão).",
    ),
    (
        "Histórico INFORMADO exige valor_brl",
        "Um histórico salarial está como INFORMADO mas sem valor em reais.",
        "Preencha o valor (R$) desse histórico salarial, ou remova-o se não "
        "for necessário.",
    ),
    (
        "data_inicial",
        "O cartão de ponto está sem a Data Inicial (ou Final).",
        "Preencha as datas do cartão de ponto — ou, se a sentença NÃO tem "
        "cartão de ponto, remova o cartão da prévia.",
    ),
    (
        "prescri",
        "Há incoerência entre o período de uma verba e a prescrição quinquenal.",
        "Ajuste o período de início da verba para não ser anterior a 5 anos "
        "antes do ajuizamento, ou desmarque a prescrição quinquenal.",
    ),
]


def _mapear_regra(msg: str) -> tuple[str, str] | None:
    m = (msg or "")
    for chave, o_que, como in _REGRAS:
        if chave.lower() in m.lower():
            return o_que, como
    return None


def humanizar_validation_error(exc: Any, payload: dict | None = None) -> dict:
    """Converte um pydantic.ValidationError (ou Exception genérica) em estrutura
    amigável. Nunca levanta — na dúvida, devolve o texto técnico."""
    payload = payload if isinstance(payload, dict) else {}
    erros: list[dict] = []
    tecnico = str(exc)

    # pydantic v2 expõe .errors(); fallback para parse best-effort do texto
    lista = None
    try:
        lista = exc.errors()  # type: ignore[attr-defined]
    except Exception:
        lista = None

    if lista:
        vistos: set = set()
        for e in lista:
            loc = tuple(e.get("loc") or ())
            msg = e.get("msg") or ""
            # msg pydantic costuma vir "Value error, <nossa msg>"
            msg_limpa = msg.split("Value error,", 1)[-1].strip() if "Value error" in msg else msg
            entidade = _nome_entidade(loc, payload)
            campo = _campo_legivel(loc)
            regra = _mapear_regra(msg_limpa)
            # dedup por (entidade, campo, regra) — o Union gera erros repetidos
            chave_dedup = (entidade, campo, regra[0] if regra else msg_limpa[:40])
            if chave_dedup in vistos:
                continue
            vistos.add(chave_dedup)
            if regra:
                o_que, como = regra
            else:
                o_que = f"Campo inválido: {msg_limpa}" if msg_limpa else "Campo inválido."
                como = ("Revise este campo na prévia. Se não souber o valor "
                        "correto, ajuste conforme a sentença ou remova o item.")
            erros.append({
                "entidade": entidade,
                "campo": campo,
                "o_que": o_que,
                "como_corrigir": como,
            })
    else:
        # Sem .errors() — usar o texto cru, mas ainda tentar mapear uma regra
        regra = _mapear_regra(tecnico)
        erros.append({
            "entidade": "Prévia",
            "campo": "",
            "o_que": regra[0] if regra else f"Não foi possível validar a prévia: {tecnico[:200]}",
            "como_corrigir": regra[1] if regra else
                "Revise os campos destacados na prévia e tente confirmar novamente.",
        })

    n = len(erros)
    titulo = (f"A prévia tem {n} problema{'s' if n != 1 else ''} que "
              f"impede{'m' if n != 1 else ''} iniciar a automação")
    return {"titulo": titulo, "erros": erros, "tecnico": tecnico[:500]}


def humanizar_incompleta(campos_faltantes: list, avisos: list | None = None) -> dict:
    """Prévia sinalizada como INCOMPLETA (meta.validacao) → estrutura amigável."""
    faltantes = list(campos_faltantes or [])
    erros = [{
        "entidade": "Prévia",
        "campo": c,
        "o_que": f"Campo obrigatório ainda não preenchido: {c}",
        "como_corrigir": "Preencha este campo na prévia antes de iniciar a automação.",
    } for c in faltantes]
    n = len(erros)
    return {
        "titulo": (f"A prévia está incompleta — {n} pendência{'s' if n != 1 else ''} "
                   f"impede{'m' if n != 1 else ''} iniciar a automação"),
        "erros": erros,
        "avisos": list(avisos or []),
        "tecnico": "completude != OK",
    }
