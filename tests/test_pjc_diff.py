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


# ── #80-DP — entidade ADICIONADA sai com parâmetros; internalRef resolvido ───
#
# 0001156-86 (15/09/2026): o calculista desdobrou HORAS EXTRAS 50% em uma
# 2ª verba "HORAS EXTRAS 50% - REMUNERAÇÃO VARIÁVEL" (base COMISSOES, divisor
# IMPORTADA_DO_CARTAO=Hs Trabalhadas, multiplicador 0,5 — Súmula 340) + 10
# reflexos. O resumo dizia só "➕ Verba ADICIONADA manualmente: <nome>" — a
# IA não tinha como derivar a regra "base mista → duas verbas" do nome, e o
# aprendizado saiu com 0 regras.

def _verba_com_vinculos(nome: str, id_verba: str, hist_ref: str, cartao_ref: str | None,
                        divisor_tipo: str = "OUTRO_VALOR", divisor: str = "220",
                        mult: str = "1.5", variacao: str = "FIXA") -> str:
    cartao_divisor = f"""
      <cartoesDePontoDaVerbaDivisor><List><CartaoDePontoDaVerba>
        <id>78</id><tipoVinculoCartao>DIVISOR</tipoVinculoCartao>
        <cartaoDePonto><CartaoDePonto><internalRef>{cartao_ref}</internalRef></CartaoDePonto></cartaoDePonto>
      </CartaoDePontoDaVerba></List></cartoesDePontoDaVerbaDivisor>""" if cartao_ref else """
      <cartoesDePontoDaVerbaDivisor><List></List></cartoesDePontoDaVerbaDivisor>"""
    return f"""
    <parcelas><Calculada>
      <id>{id_verba}</id><versao>1</versao>
      <nome>{nome}</nome><descricao>{nome[:50]}</descricao>
      <tipoVariacaoParcela>{variacao}</tipoVariacaoParcela>
      <caracteristica>COMUM</caracteristica>
      <ocorrenciaDePagamento>MENSAL</ocorrenciaDePagamento>
      <periodoInicial>1752116400000</periodoInicial>
      <incidenciaFGTS>true</incidenciaFGTS>
      <comentarios>null</comentarios>
      <ativo>true</ativo>
      <formula><FormulaCalculada>
        <verbaDeCalculo><Calculada><internalRef>{id_verba}</internalRef></Calculada></verbaDeCalculo>
        <divisor><Divisor><tipo>{divisor_tipo}</tipo><outroValor>{divisor}</outroValor></Divisor></divisor>
        <multiplicador><Multiplicador><outroValor>{mult}</outroValor></Multiplicador></multiplicador>
        <quantidade><Quantidade><tipo>IMPORTADA_DO_CARTAO</tipo></Quantidade></quantidade>
      </FormulaCalculada></formula>
      <historicosDaVerbaDoValorDevido><List><HistoricoSalarialDaVerba>
        <id>77</id><tipoVinculoHistorico>BASE</tipoVinculoHistorico>
        <verbaDeCalculo><Calculada><internalRef>{id_verba}</internalRef></Calculada></verbaDeCalculo>
        <historicoSalarial><HistoricoSalarial><internalRef>{hist_ref}</internalRef></HistoricoSalarial></historicoSalarial>
      </HistoricoSalarialDaVerba></List></historicosDaVerbaDoValorDevido>{cartao_divisor}
      <ocorrencias><Ocorrencia><valorDevido>1</valorDevido></Ocorrencia></ocorrencias>
    </Calculada></parcelas>"""


_HISTORICOS_E_CARTOES = """
    <historicos>
      <HistoricoSalarial><id>501</id><nome>SALARIO BASE</nome><incidenciaINSS>true</incidenciaINSS>
        <incidenciaFGTS>true</incidenciaFGTS><tipoVariacaoParcela>FIXA</tipoVariacaoParcela><x>1</x></HistoricoSalarial>
      <HistoricoSalarial><id>502</id><nome>COMISSOES</nome><incidenciaINSS>true</incidenciaINSS>
        <incidenciaFGTS>true</incidenciaFGTS><tipoVariacaoParcela>VARIAVEL</tipoVariacaoParcela><x>1</x></HistoricoSalarial>
    </historicos>
    <cartoesDePonto><List>
      <CartaoDePonto><id>901</id><nome>Hs EXT</nome><versao>0</versao></CartaoDePonto>
      <CartaoDePonto><id>902</id><nome>Hs Trabalhadas</nome><versao>0</versao></CartaoDePonto>
    </List></cartoesDePonto>"""


def _pjc_gerado_dk() -> bytes:
    return _pjc(_HISTORICOS_E_CARTOES + _verba_com_vinculos(
        "HORAS EXTRAS 50%", "10", hist_ref="501", cartao_ref=None))


def _pjc_definitivo_dk() -> bytes:
    return _pjc(
        _HISTORICOS_E_CARTOES
        + _verba_com_vinculos("HORAS EXTRAS 50%", "10", hist_ref="501", cartao_ref=None)
        + _verba_com_vinculos("HORAS EXTRAS 50% - REMUNERAÇÃO VARIÁVEL", "11",
                              hist_ref="502", cartao_ref="902",
                              divisor_tipo="IMPORTADA_DO_CARTAO", divisor="null",
                              mult="0.5", variacao="VARIAVEL")
    )


def test_dp_internalref_resolvido_para_nome_e_sem_autorreferencia():
    """`<HistoricoSalarial><internalRef>502</internalRef>` → `ref:COMISSOES`;
    item de vínculo keyed pelo nome vinculado; backref à própria verba some."""
    d = parse_pjc_params(_pjc_definitivo_dk())
    p = d["verbas"]["HORAS EXTRAS 50% - REMUNERAÇÃO VARIÁVEL"]["params"]
    k_hist = "historicosDaVerbaDoValorDevido.List.HistoricoSalarialDaVerba[COMISSOES].historicoSalarial.HistoricoSalarial"
    assert p[k_hist] == "ref:COMISSOES", p
    k_cart = "cartoesDePontoDaVerbaDivisor.List.CartaoDePontoDaVerba[HS TRABALHADAS].cartaoDePonto.CartaoDePonto"
    assert p[k_cart] == "ref:HS TRABALHADAS", p
    assert p["formula.FormulaCalculada.divisor.Divisor.tipo"] == "IMPORTADA_DO_CARTAO"
    assert p["formula.FormulaCalculada.multiplicador.Multiplicador.outroValor"] == "0.5"
    # backrefs à PRÓPRIA verba (item → dona, fórmula → verba) não são parâmetro
    assert not any(v == "ref:HORAS EXTRAS 50% - REMUNERAÇÃO VARIÁVEL" for v in p.values()), (
        "autorreferência deve ser removida — entre verba e desdobramento sempre 'difere'")


def test_dp_verba_adicionada_sai_com_parametros_e_desdobramento():
    rel = diff_pjc(_pjc_gerado_dk(), _pjc_definitivo_dk())
    assert rel["verbas"]["adicionadas"] == ["HORAS EXTRAS 50% - REMUNERAÇÃO VARIÁVEL"]
    det = rel["verbas"]["adicionadas_detalhe"]
    assert len(det) == 1 and det[0]["nome"] == "HORAS EXTRAS 50% - REMUNERAÇÃO VARIÁVEL"
    assert det[0]["tipo"] == "Calculada"
    assert det[0]["desdobramento_de"] == "HORAS EXTRAS 50%"
    # parâmetros relevantes: sem nulos/boilerplate, com o vínculo resolvido
    assert "comentarios" not in det[0]["params"]
    assert det[0]["params"]["formula.FormulaCalculada.multiplicador.Multiplicador.outroValor"] == "0.5"
    difs = {d["campo"]: d for d in det[0]["diferencas_vs_origem"]}
    assert difs["formula.FormulaCalculada.multiplicador.Multiplicador.outroValor"]["de"] == "1.5"
    assert difs["formula.FormulaCalculada.divisor.Divisor.tipo"]["para"] == "IMPORTADA_DO_CARTAO"
    assert difs["tipoVariacaoParcela"] == {"campo": "tipoVariacaoParcela", "de": "FIXA", "para": "VARIAVEL"}
    assert any("[COMISSOES]" in c for c in difs), "base histórico da verba nova deve aparecer"
    assert any("[SALARIO BASE]" in c for c in difs), "base histórico da verba de origem deve aparecer"

    linhas = resumo_legivel(rel)
    txt = "\n".join(linhas)
    assert "DESDOBRAMENTO de 'HORAS EXTRAS 50%'" in txt
    assert "MANTIDA no definitivo" in txt, "origem coexiste com o desdobramento (split, não rename)"
    assert "multiplicador.Multiplicador.outroValor: 1.5 → 0.5" in txt
    assert "Divisor.tipo: OUTRO_VALOR → IMPORTADA_DO_CARTAO" in txt
    assert "ref:COMISSOES" in txt and "ref:HS TRABALHADAS" in txt
    assert "demais" in txt and "iguais aos de 'HORAS EXTRAS 50%'" in txt
    # regressão: a linha antiga (só o nome) NÃO pode voltar
    assert not any(l.strip().endswith("ADICIONADA manualmente: HORAS EXTRAS 50% - REMUNERAÇÃO VARIÁVEL")
                   for l in linhas)


def test_dp_verba_adicionada_sem_origem_lista_todos_os_parametros():
    dfn = _pjc(_HISTORICOS_E_CARTOES + _verba_com_vinculos(
        "ADICIONAL NOTURNO", "12", hist_ref="501", cartao_ref="902", mult="0.2"))
    rel = diff_pjc(_pjc(_HISTORICOS_E_CARTOES), dfn)
    det = rel["verbas"]["adicionadas_detalhe"][0]
    assert "desdobramento_de" not in det
    txt = "\n".join(resumo_legivel(rel))
    assert "ADICIONAL NOTURNO (Calculada) — parâmetros:" in txt
    assert "multiplicador.Multiplicador.outroValor=0.2" in txt
    assert "periodoInicial=10/07/2025" in txt, "epoch-ms de data vira DD/MM/AAAA"


def test_dp_null_literal_equivale_a_ausente_e_ruido_derivado():
    """`comentarios: (vazio) → null` não é correção; versão do sistema e
    faixas de IRPF dos honorários são derivados."""
    base = _verba_he()
    ger = _pjc("<versaoDoSistema>2.14.0</versaoDoSistema>" + base)
    dfn = _pjc("<versaoDoSistema>2.16.0</versaoDoSistema>"
               + base.replace("<ativo>true</ativo>", "<ativo>true</ativo><comentarios>null</comentarios>")
               + "<honorarios><Set><Honorario><descricao>SUC</descricao><percentual>10</percentual>"
                 "<valorDescontoSimplificadoIrpf>607.2</valorDescontoSimplificadoIrpf>"
                 "</Honorario></Set></honorarios>")
    ger = _pjc("<versaoDoSistema>2.14.0</versaoDoSistema>" + base
               + "<honorarios><Set><Honorario><descricao>SUC</descricao><percentual>10</percentual>"
                 "</Honorario></Set></honorarios>")
    rel = diff_pjc(ger, dfn)
    assert rel["resumo"]["identicos"], rel
    # mas valor REAL → null continua sendo diff
    rel2 = diff_pjc(_pjc(_verba_he(divisor="220")), _pjc(_verba_he(divisor="null")))
    assert rel2["resumo"]["campos_alterados"] == 1


def test_dp_reprocessar_relatorio_preserva_metadados(tmp_path):
    ger_path = tmp_path / "gerado.pjc"
    ger_path.write_bytes(_pjc_gerado_dk())
    from learning.pjc_diff import reprocessar_relatorio
    import json as _json
    rel = executar_diff_e_persistir("s-dk", str(ger_path), _pjc_definitivo_dk(), tmp_path / "apr")
    # simula relatório de versão antiga (sem detalhe) + metadados do upload/aprendizado
    rel["verbas"].pop("adicionadas_detalhe")
    rel["sentenca_definitiva"] = {"alterada": True, "origem": "texto colado"}
    rel["aprendizado"] = {"regras_novas": 0, "resumo": "", "analisado_em": "2026-09-15T14:43:17Z"}
    (tmp_path / "apr" / "s-dk_diff.json").write_text(_json.dumps(rel), encoding="utf-8")

    novo = reprocessar_relatorio("s-dk", tmp_path / "apr")
    assert novo is not None and novo["verbas"]["adicionadas_detalhe"][0]["desdobramento_de"] == "HORAS EXTRAS 50%"
    assert novo["sentenca_definitiva"]["alterada"] is True
    assert novo["aprendizado"]["analisado_em"] == "2026-09-15T14:43:17Z"
    assert novo["sessao_id"] == "s-dk" and novo.get("reprocessado_em")
    assert carregar_relatorio("s-dk", tmp_path / "apr")["reprocessado_em"] == novo["reprocessado_em"]
    # sem o PJC gerado → None (nunca levanta)
    ger_path.unlink()
    assert reprocessar_relatorio("s-dk", tmp_path / "apr") is None
