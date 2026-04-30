"""
Validações server-side conhecidas do PJE-Calc Cidadão.

Este módulo centraliza regras de negócio que o PJE-Calc impõe via validação
server-side (HTTP 500/400). Quando dados extraídos pela IA ou editados pelo
usuário violam essas regras, o Save da Fase 1 (ou outras) é rejeitado e a
automação inteira colapsa.

Aplicado em 3 camadas (defesa em profundidade):
  1. extraction.py — pós-processamento da IA (corrige extração indevida)
  2. webapp.py /editar — validação ao usuário editar prévia (alerta + ajuste)
  3. playwright_pjecalc.py — pré-Save (defesa final antes de submeter)

Validações conhecidas:
  - prescricao.quinquenal: requer (ajuizamento - admissao) >= 5 anos
  - prescricao.fgts: requer (ajuizamento - admissao) >= 5 anos
  - data_inicio_calculo: deve ser >= admissao (PJE-Calc rejeita retroativo)
  - data_fim_calculo: deve ser >= demissao
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def _parse_data(s: Any) -> date | None:
    """Parse data BR (DD/MM/AAAA) ou ISO (AAAA-MM-DD). Retorna None se inválido."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def validar_prescricao(
    admissao: Any,
    ajuizamento: Any,
    quinquenal: bool | None,
    fgts: bool | None,
) -> dict[str, Any]:
    """
    Valida regras de prescrição contra restrição server-side do PJE-Calc:

    "Não é possível selecionar prescrição quinquenal, pois o período entre a
    data de admissão e a data do ajuizamento é menor que cinco anos."

    A mesma regra se aplica à prescrição do FGTS.

    Retorna:
        dict com:
          - quinquenal: bool (corrigido para False se inválido)
          - fgts: bool (corrigido para False se inválido)
          - alerta: str | None (mensagem para o usuário se houve correção)
          - corrigido: bool (True se algum valor foi alterado)
    """
    _adm = _parse_data(admissao)
    _ajz = _parse_data(ajuizamento)

    # Sem datas → não conseguimos validar; preservar valores
    if not _adm or not _ajz:
        return {
            "quinquenal": bool(quinquenal) if quinquenal is not None else None,
            "fgts": bool(fgts) if fgts is not None else None,
            "alerta": None,
            "corrigido": False,
        }

    _dias = (_ajz - _adm).days
    _aplica_quinquenal = _dias >= 365 * 5  # 5 anos

    _q_orig = bool(quinquenal) if quinquenal is not None else False
    _f_orig = bool(fgts) if fgts is not None else False
    _q_novo = _q_orig and _aplica_quinquenal
    _f_novo = _f_orig and _aplica_quinquenal

    _corrigido = (_q_orig != _q_novo) or (_f_orig != _f_novo)
    _alerta = None
    if _corrigido:
        _anos = _dias / 365.25
        _alerta = (
            f"Prescrição quinquenal/FGTS desabilitada automaticamente: "
            f"contrato {admissao} → {ajuizamento} ({_anos:.1f} anos) é menor que "
            f"5 anos. PJE-Calc rejeitaria estes campos no Save (HTTP 500)."
        )

    return {
        "quinquenal": _q_novo,
        "fgts": _f_novo,
        "alerta": _alerta,
        "corrigido": _corrigido,
    }


def validar_data_inicio_calculo(
    data_inicio: Any,
    admissao: Any,
) -> dict[str, Any]:
    """
    PJE-Calc rejeita data_inicio_calculo anterior à admissão.

    Retorna dict com data corrigida (= admissao se inválida) e alerta.
    """
    _ini = _parse_data(data_inicio)
    _adm = _parse_data(admissao)

    if not _adm:
        return {"data_inicio_calculo": data_inicio, "alerta": None, "corrigido": False}

    if _ini and _ini < _adm:
        return {
            "data_inicio_calculo": _adm.strftime("%d/%m/%Y"),
            "alerta": (
                f"data_inicio_calculo {data_inicio} é anterior à admissão {admissao}; "
                f"ajustada para a admissão (PJE-Calc rejeita retroativo)."
            ),
            "corrigido": True,
        }
    if not _ini:
        return {
            "data_inicio_calculo": _adm.strftime("%d/%m/%Y"),
            "alerta": None,
            "corrigido": data_inicio is None,
        }
    return {"data_inicio_calculo": data_inicio, "alerta": None, "corrigido": False}


def aplicar_validacoes_pjecalc(
    dados: dict[str, Any],
    log_cb=None,
) -> dict[str, Any]:
    """
    Aplica TODAS as validações conhecidas do PJE-Calc no dict de dados extraídos.

    Modifica `dados` in-place E acumula mensagens em `dados['_alertas_validacao']`.
    Retorna o mesmo dict para encadeamento.

    Use em:
      - extraction.py: após extração da IA (limpa dados inconsistentes)
      - webapp.py /editar: após edição do usuário (alerta o usuário)
      - playwright_pjecalc.py: pré-Save Fase 1 (última defesa)
    """
    _log = log_cb or (lambda m: None)
    alertas = list(dados.get("_alertas_validacao") or [])

    contrato = dados.get("contrato") or {}
    presc = dados.get("prescricao") or {}

    _adm = contrato.get("admissao")
    _ajz = contrato.get("ajuizamento")

    # 1. Prescrição quinquenal/FGTS — depende de (ajuizamento - admissao) >= 5 anos
    if presc.get("quinquenal") or presc.get("fgts"):
        _r = validar_prescricao(
            admissao=_adm,
            ajuizamento=_ajz,
            quinquenal=presc.get("quinquenal"),
            fgts=presc.get("fgts"),
        )
        if _r["corrigido"]:
            presc["quinquenal"] = _r["quinquenal"]
            presc["fgts"] = _r["fgts"]
            alertas.append({
                "campo": "prescricao",
                "mensagem": _r["alerta"],
                "severidade": "warning",
            })
            _log(f"  ⚠ Validação PJE-Calc: {_r['alerta']}")
            dados["prescricao"] = presc

    # 2. data_inicio_calculo — deve ser >= admissao
    _r2 = validar_data_inicio_calculo(
        data_inicio=contrato.get("data_inicio_calculo"),
        admissao=_adm,
    )
    if _r2["corrigido"]:
        contrato["data_inicio_calculo"] = _r2["data_inicio_calculo"]
        if _r2["alerta"]:
            alertas.append({
                "campo": "contrato.data_inicio_calculo",
                "mensagem": _r2["alerta"],
                "severidade": "warning",
            })
            _log(f"  ⚠ Validação PJE-Calc: {_r2['alerta']}")
        dados["contrato"] = contrato

    if alertas:
        dados["_alertas_validacao"] = alertas

    return dados


# Helpers auxiliares para JS frontend (replicam regras em JavaScript)
JS_VALIDADOR_PRESCRICAO = """
function validarPrescricaoQuinquenal(admissao, ajuizamento) {
    // Retorna {valido: bool, mensagem: str}
    function parseDataBR(s) {
        if (!s) return null;
        const m = s.match(/^(\\d{2})\\/(\\d{2})\\/(\\d{4})$/);
        if (!m) return null;
        return new Date(parseInt(m[3]), parseInt(m[2])-1, parseInt(m[1]));
    }
    const adm = parseDataBR(admissao);
    const ajz = parseDataBR(ajuizamento);
    if (!adm || !ajz) return {valido: true, mensagem: ''};
    const dias = (ajz - adm) / (1000*60*60*24);
    if (dias < 365*5) {
        const anos = (dias / 365.25).toFixed(1);
        return {
            valido: false,
            mensagem: `Prescrição quinquenal não é aplicável: contrato ${admissao} → ${ajuizamento} (${anos} anos) é menor que 5 anos. PJE-Calc rejeitará este campo.`
        };
    }
    return {valido: true, mensagem: ''};
}
"""
