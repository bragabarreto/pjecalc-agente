# tests/test_pjc_diff.py — Plano 3 do Learning Engine (FATIA 1)
#
# Valida o diff estruturado PJC gerado ↔ PJC definitivo:
#   • parser param-level (verbas/reflexos/históricos/seções) na estrutura XStream
#   • exclusão de ruído (ids, hashes, ocorrências) e de valores DERIVADOS
#   • normalização de decimais XStream ("220.000...", "0E-25")
#   • definição ANINHADA de entidade vira "ref:<nome>" (não duplica árvore)
#   • diff: campo alterado / entidade adicionada-removida / idênticos
#   • persistência do relatório (executar_diff_e_persistir + carregar_relatorio)

from __future__ import annotations

import io
import zipfile

import pytest

from learning.pjc_diff import (
    carregar_relatorio,
    diff_pjc,
    executar_diff_e_persistir,
    parse_pjc_params,
    resumo_legivel,
)


def _pjc(xml_inner: str) -> bytes:
    """Monta um PJC sintético (ZIP com XML ISO-8859-1, raiz <Calculo>)."""
    xml = (
        "<?xml version='1.0' encoding='ISO-8859-1'?>"
        f"<Calculo><id>1</id><versao>3</versao>{xml_inner}</Calculo>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CALC.PJC", xml.encode("iso-8859-1", "replace"))
    return buf.getvalue()


def _verba_he(divisor: str = "220.0000000000000000000000000",
              qtd_tipo: str = "IMPORTADA_DO_CARTAO") -> str:
    return f"""
    <parcelas><Calculada>
      <id>137</id><versao>1</versao>
      <nome>HORAS EXTRAS 50%</nome><descricao>HORAS EXTRAS 50%</descricao>
      <caracteristica>COMUM</caracteristica>
      <ocorrenciaDePagamento>MENSAL</ocorrenciaDePagamento>
      <incidenciaFGTS>true</incidenciaFGTS>
      <ativo>true</ativo>
      <formula><FormulaCalculada>
        <divisor><Divisor><id>9</id><tipo>OUTRO_VALOR</tipo><outroValor>{divisor}</outroValor></Divisor></divisor>
        <multiplicador><Multiplicador><outroValor>1.5000000000000000000000000</outroValor></Multiplicador></multiplicador>
        <quantidade><Quantidade><tipo>{qtd_tipo}</tipo><valorInformado>0E-25</valorInformado></Quantidade></quantidade>
      </FormulaCalculada></formula>
      <ocorrencias><Ocorrencia><valorDevido>123.45</valorDevido></Ocorrencia></ocorrencias>
    </Calculada></parcelas>"""


def _reflexo(nome: str, ativo: str = "true") -> str:
    return f"""
    <reflexos><Reflexo>
      <id>9</id><versao>2</versao>
      <nome>{nome}</nome><descricao>{nome[:36]}</descricao>
      <caracteristica>COMUM</caracteristica>
      <ocorrenciaDePagamento>MENSAL</ocorrenciaDePagamento>
      <ativo>{ativo}</ativo>
      <baseVerba><BaseVerba><itens><List><ItemBaseVerba>
        <integralizar>SIM</integralizar>
        <verbaDeCalculo><Calculada>
          <id>137</id><versao>1</versao><nome>HORAS EXTRAS 50%</nome>
          <caracteristica>COMUM</caracteristica><ativo>true</ativo>
          <incidenciaFGTS>true</incidenciaFGTS><x1>a</x1><x2>b</x2>
        </Calculada></verbaDeCalculo>
      </ItemBaseVerba></List></itens></BaseVerba></baseVerba>
    </Reflexo></reflexos>"""


def test_parse_extrai_entidades_e_exclui_ruido():
    d = parse_pjc_params(_pjc(
        "<dataAdmissao>2024-01-02</dataAdmissao>"
        "<hashCodeLiquidacao>abc123</hashCodeLiquidacao>"
        + _verba_he()
        + _reflexo("RSR SOBRE HORAS EXTRAS 50%")
    ))
    assert "HORAS EXTRAS 50%" in d["verbas"]
    p = d["verbas"]["HORAS EXTRAS 50%"]["params"]
    # normalização decimal XStream
    assert p["formula.FormulaCalculada.divisor.Divisor.outroValor"] == "220"
    assert p["formula.FormulaCalculada.multiplicador.Multiplicador.outroValor"] == "1.5"
    assert p["formula.FormulaCalculada.quantidade.Quantidade.valorInformado"] == "0"
    # ruído excluído
    assert not any(k.split(".")[-1] in ("id", "versao") for k in p)
    assert not any("ocorrencias" in k for k in p), "ocorrências (valores derivados) devem ser excluídas"
    assert "hashCodeLiquidacao" not in d["parametros_calculo"]
    assert d["parametros_calculo"]["dataAdmissao"] == "2024-01-02"
    # definição aninhada da verba dentro do reflexo vira ref: (não duplica)
    r = d["reflexos"]["RSR SOBRE HORAS EXTRAS 50%"]["params"]
    ref_keys = [k for k, v in r.items() if str(v).startswith("ref:")]
    assert ref_keys and r[ref_keys[0]] == "ref:HORAS EXTRAS 50%"


def test_diff_detecta_parametro_alterado_e_normaliza():
    ger = _pjc(_verba_he(divisor="220.0000000000000000000000000"))
    dfn = _pjc(_verba_he(divisor="180"))
    rel = diff_pjc(ger, dfn)
    alt = rel["verbas"]["alteradas"]
    assert len(alt) == 1 and alt[0]["nome"] == "HORAS EXTRAS 50%"
    campos = {c["campo"]: c for c in alt[0]["campos"]}
    k = "formula.FormulaCalculada.divisor.Divisor.outroValor"
    assert campos[k]["de"] == "220" and campos[k]["para"] == "180"
    assert not rel["resumo"]["identicos"]

    # mesma verba com decimais equivalentes → idênticos (sem falso-positivo)
    rel2 = diff_pjc(ger, _pjc(_verba_he(divisor="220")))
    assert rel2["resumo"]["identicos"], "normalização decimal deve evitar falso diff"


def test_diff_reflexo_ativado_e_entidade_adicionada_removida():
    ger = _pjc(_verba_he() + _reflexo("MULTA 477 SOBRE HE", ativo="true"))
    dfn = _pjc(_verba_he() + _reflexo("MULTA 477 SOBRE HE", ativo="false")
               + _reflexo("RSR SOBRE HE", ativo="true"))
    rel = diff_pjc(ger, dfn)
    # multa desativada manualmente → campo ativo true→false
    alts = {a["nome"]: a for a in rel["reflexos"]["alteradas"]}
    assert "MULTA 477 SOBRE HE" in alts
    ativo = [c for c in alts["MULTA 477 SOBRE HE"]["campos"] if c["campo"] == "ativo"]
    assert ativo and ativo[0]["de"] == "true" and ativo[0]["para"] == "false"
    # RSR adicionado manualmente
    assert rel["reflexos"]["adicionadas"] == ["RSR SOBRE HE"]
    linhas = "\n".join(resumo_legivel(rel))
    assert "ADICIONADA" in linhas and "ativo" in linhas


def test_diff_valores_derivados_excluidos():
    sec = lambda base, valor: (
        f"<honorarios><Set><Honorario><percentual>7.5</percentual>"
        f"<baseHonorario>{base}</baseHonorario><valor>{valor}</valor>"
        f"</Honorario></Set></honorarios>"
    )
    rel = diff_pjc(_pjc(_verba_he() + sec("7953.89", "596.54")),
                   _pjc(_verba_he() + sec("54805.9", "4110.44")))
    assert rel["resumo"]["identicos"], (
        "baseHonorario/Honorario.valor são DERIVADOS do total — não podem gerar diff")
    # mas o PARÂMETRO percentual gera:
    rel2 = diff_pjc(_pjc(_verba_he() + sec("1", "1").replace("7.5", "7.5")),
                    _pjc(_verba_he() + sec("1", "1").replace("7.5", "10")))
    assert any(c["campo"].endswith("percentual") for c in rel2["secoes"].get("honorarios", []))


def test_persistencia_relatorio(tmp_path):
    ger_path = tmp_path / "gerado.pjc"
    ger_path.write_bytes(_pjc(_verba_he(divisor="220")))
    rel = executar_diff_e_persistir(
        "sess-1", str(ger_path), _pjc(_verba_he(divisor="180")), tmp_path / "apr")
    assert rel["resumo"]["campos_alterados"] == 1
    assert (tmp_path / "apr" / "sess-1_definitivo.pjc").exists()
    rel2 = carregar_relatorio("sess-1", tmp_path / "apr")
    assert rel2 and rel2["sessao_id"] == "sess-1"
    assert carregar_relatorio("sess-nada", tmp_path / "apr") is None
