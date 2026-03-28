# modules/pjc_generator.py — Gerador Nativo de Arquivo .PJC
#
# O arquivo .PJC do PJE-Calc é um ZIP contendo XML (ISO-8859-1).
# Schema baseado em análise de 5 arquivos .PJC reais da 7ª Região TRT.
#
# Fluxo: parâmetros confirmados → XML → ZIP → import no PJE-Calc → Liquidar → .pjc final

from __future__ import annotations

import logging
import re
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)

# Timezone BRT (UTC-3) — PJE-Calc armazena datas como meia-noite BRT em ms
_BRT = timezone(timedelta(hours=-3))

# Versão do sistema usada para compatibilidade
_VERSAO_SISTEMA = "2.15.1"


# ── Conversão de datas ────────────────────────────────────────────────────────

def _data_ts(date_str: str | None) -> int | None:
    """Converte DD/MM/AAAA ou AAAA-MM-DD para Unix timestamp em milissegundos (BRT meia-noite)."""
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(date_str.strip(), fmt)
            d = d.replace(tzinfo=_BRT)
            return int(d.timestamp() * 1000)
        except ValueError:
            continue
    logger.warning(f"Formato de data não reconhecido: {date_str!r}")
    return None


def _ts_now() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _mes_ts(ano: int, mes: int) -> int:
    """Retorna timestamp do primeiro dia do mês (BRT) em ms."""
    d = datetime(ano, mes, 1, tzinfo=_BRT)
    return int(d.timestamp() * 1000)


# ── IDs determinísticos ───────────────────────────────────────────────────────

def _calc_id(sessao_id: str) -> int:
    """ID único determinístico 100000–999999."""
    return abs(hash(sessao_id)) % 900000 + 100000


# ── Parsing do número do processo ────────────────────────────────────────────

def _parsear_numero(numero: str | None) -> dict:
    """'0001686-52.2026.5.07.0003' → {numero, digito, ano, justica, regiao, vara}."""
    empty = {"numero": 0, "digito": 0, "ano": 0, "justica": 0, "regiao": 0, "vara": 0}
    if not numero:
        return empty
    m = re.match(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})", numero.strip())
    if not m:
        # Tentar sem formatação (apenas dígitos)
        digits = re.sub(r"[^\d]", "", numero)
        if len(digits) == 20:
            return {
                "numero": int(digits[0:7]),
                "digito": int(digits[7:9]),
                "ano": int(digits[9:13]),
                "justica": int(digits[13:14]),
                "regiao": int(digits[14:16]),
                "vara": int(digits[16:20]),
            }
        return empty
    return {
        "numero": int(m.group(1)),
        "digito": int(m.group(2)),
        "ano": int(m.group(3)),
        "justica": int(m.group(4)),
        "regiao": int(m.group(5)),
        "vara": int(m.group(6)),
    }


# ── Enums / mapeamentos ───────────────────────────────────────────────────────

def _regime_enum(regime: str | None) -> str:
    return {
        "Tempo Integral": "INTEGRAL",
        "Tempo Parcial": "PARCIAL",
        "Trabalho Intermitente": "INTERMITENTE",
    }.get(regime or "", "INTEGRAL")


def _aliquota_fgts_enum(aliquota: float | None) -> str:
    if aliquota is None:
        return "OITO_POR_CENTO"
    pct = round(aliquota * 100)
    return {2: "DOIS_POR_CENTO", 8: "OITO_POR_CENTO", 12: "DOZE_POR_CENTO"}.get(pct, "OITO_POR_CENTO")


def _indice_enum(indice: str | None) -> str:
    if not indice:
        return "IPCAE"
    s = indice.lower()
    if "tabela jt" in s or "jt unica" in s or "jt única" in s:
        return "IPCAE"
    if "ipca-e" in s or "ipcae" in s:
        return "IPCAE"
    if "selic" in s:
        return "SELIC"
    if "trct" in s:
        return "TRCT"
    if "tr" in s:
        return "TRD"
    if "ipca" in s:
        return "IPCA"
    return "IPCAE"


def _juros_enum(juros: str | None) -> str:
    if not juros:
        return "TRD_SIMPLES"
    j = juros.lower()
    if "selic" in j:
        return "SELIC"
    return "TRD_SIMPLES"


def _apuracao_aviso_enum(tipo: str | None) -> str:
    return {
        "Calculado": "APURACAO_CALCULADA",
        "Informado": "INFORMADO_DIAS",
        "Nao Apurar": "NAO_APURAR",
    }.get(tipo or "", "APURACAO_CALCULADA")


def _caracteristica_enum(c: str | None) -> str:
    return {
        "Comum": "COMUM",
        "13o Salario": "DECIMO_TERCEIRO_SALARIO",
        "Ferias": "FERIAS",
        "Aviso Previo": "AVISO_PREVIO",
    }.get(c or "", "COMUM")


def _ocorrencia_enum(o: str | None) -> str:
    return {
        "Mensal": "MENSAL",
        "Dezembro": "DEZEMBRO",
        "Periodo Aquisitivo": "PERIODO_AQUISITIVO",
        "Desligamento": "DESLIGAMENTO",
    }.get(o or "", "MENSAL")


def _compor_principal(v: bool | None) -> str:
    return "SIM" if v else "NAO"


def _bool_str(v: bool | None, default: bool = False) -> str:
    return "true" if (v if v is not None else default) else "false"


def _esc(s: str | None) -> str:
    """Escapa caracteres especiais XML e converte chars fora do ISO-8859-1 para entidades numéricas."""
    if not s:
        return ""
    import unicodedata
    s = unicodedata.normalize("NFC", str(s))
    s = (s.replace("&", "&amp;")
          .replace("<", "&lt;")
          .replace(">", "&gt;")
          .replace('"', "&quot;"))
    # Chars fora do Latin-1 (>255) → entidade numérica XML para evitar '?' no encode
    result = []
    for ch in s:
        if ord(ch) > 255:
            result.append(f"&#{ord(ch)};")
        else:
            result.append(ch)
    return "".join(result)


def _limpar_nome(nome: str | None) -> str:
    """Remove CPF/CNPJ embutidos no nome (ex: 'NOME ? CPF: 000.000.000-00')."""
    if not nome:
        return ""
    # Remove padrões: NOME ? CPF: xxx / NOME – CNPJ: xxx / NOME - CPF xxx
    nome = re.sub(
        r'\s*[?–—\-]+\s*(?:CPF|CNPJ)\s*[:\s]*[\d.\-/]+',
        '', nome, flags=re.IGNORECASE
    )
    return nome.strip()


# ── Gerador de meses entre duas datas ────────────────────────────────────────

def _meses_entre(adm_ts: int | None, dem_ts: int | None) -> list[tuple[int, int]]:
    """Retorna lista de (ano, mes) entre admissão e demissão."""
    if not adm_ts or not dem_ts:
        return []
    d_ini = datetime.fromtimestamp(adm_ts / 1000, tz=_BRT)
    d_fim = datetime.fromtimestamp(dem_ts / 1000, tz=_BRT)
    meses = []
    ano, mes = d_ini.year, d_ini.month
    while (ano, mes) <= (d_fim.year, d_fim.month):
        meses.append((ano, mes))
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
    return meses


# ── Seção: processo ───────────────────────────────────────────────────────────

def _xml_processo(proc: dict, calc_id: int) -> str:
    num = _parsear_numero(proc.get("numero"))
    return (
        f"<processo><Processo>"
        f"<id>{calc_id}</id><versao>0</versao>"
        f"<valorDaCausa>0.00</valorDaCausa>"
        f"<dataAutuacao>null</dataAutuacao>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<identificador><IdentificadorDoProcesso>"
        f"<numero>{num['numero']}</numero>"
        f"<ano>{num['ano']}</ano>"
        f"<justica>{num['justica']}</justica>"
        f"<regiao>{num['regiao']}</regiao>"
        f"<vara>{num['vara']}</vara>"
        f"<digito>{num['digito']}</digito>"
        f"</IdentificadorDoProcesso></identificador>"
        f"<reclamante><Reclamante>"
        f"<tipoDocumentoPrevidenciario>null</tipoDocumentoPrevidenciario>"
        f"<numeroDocumentoPrevidenciario>null</numeroDocumentoPrevidenciario>"
        f"<nome>{_esc(_limpar_nome(proc.get('reclamante', '')))}</nome>"
        f"<tipoDocumentoFiscal>null</tipoDocumentoFiscal>"
        f"<numeroDocumentoFiscal>null</numeroDocumentoFiscal>"
        f"</Reclamante></reclamante>"
        f"<reclamado><Reclamado>"
        f"<nome>{_esc(_limpar_nome(proc.get('reclamado', '')))}</nome>"
        f"<tipoDocumentoFiscal>null</tipoDocumentoFiscal>"
        f"<numeroDocumentoFiscal>null</numeroDocumentoFiscal>"
        f"</Reclamado></reclamado>"
        f"<advogadosReclamante><List></List></advogadosReclamante>"
        f"<advogadosReclamado><List></List></advogadosReclamado>"
        f"</Processo></processo>"
    )


# ── Fórmula por tipo de verba ────────────────────────────────────────────────

def _formula_calculada(verba: dict, vid: int, calc_id: int) -> str:
    """
    Gera o bloco <formula><FormulaCalculada> baseado na característica da verba.
    Segue os padrões observados em arquivos .pjc reais.
    """
    carac = _caracteristica_enum(verba.get("caracteristica"))
    ocorr = _ocorrencia_enum(verba.get("ocorrencia"))
    percentual = verba.get("percentual")
    valor_informado = verba.get("valor_informado")
    multiplicador = percentual if percentual is not None else 1.0

    # Determinar base tabelada
    if carac == "FERIAS":
        base_tipo = "MAIOR_REMUNERACAO"
        multiplicador = 1.3333333300
        divisor_val = 12.0
        qtd_tipo = "AVOS"
    elif carac == "DECIMO_TERCEIRO_SALARIO":
        base_tipo = "HISTORICO_SALARIAL"
        multiplicador = 1.0
        divisor_val = 12.0
        qtd_tipo = "AVOS"
    elif carac == "AVISO_PREVIO" and ocorr == "DESLIGAMENTO":
        base_tipo = "MAIOR_REMUNERACAO"
        multiplicador = 1.0
        divisor_val = 30.0
        qtd_tipo = "AVOS"
    elif valor_informado is not None:
        # Verba com valor fixo informado
        base_tipo = "HISTORICO_SALARIAL"
        divisor_val = 1.0
        qtd_tipo = "OUTRO_VALOR"
    else:
        base_tipo = "HISTORICO_SALARIAL"
        divisor_val = 1.0
        qtd_tipo = "AVOS"

    # Valor pago: usa valor_informado se disponível, senão 0
    val_pago_tipo = "INFORMADO"
    val_pago = f"{float(valor_informado):.25f}" if valor_informado is not None else "0E-25"
    # Se tem valor informado, o gerarPrincipal = VALOR_INFORMADO
    # e o divisor/multiplicador/qtd são secundários
    if valor_informado is not None:
        divisor_val = 1.0
        multiplicador = 1.0
        qtd_tipo = "OUTRO_VALOR"

    return (
        f"<formula><FormulaCalculada>"
        f"<dobra>false</dobra>"
        f"<id>{vid}</id><versao>0</versao>"
        f"<baseTabelada><BaseTabelada>"
        f"<tipo>{base_tipo}</tipo>"
        f"<aplicarProporcionalidade>false</aplicarProporcionalidade>"
        f"</BaseTabelada></baseTabelada>"
        f"<baseVerba><BaseVerba><itens><List></List></itens></BaseVerba></baseVerba>"
        f"<divisor><Divisor>"
        f"<id>{vid}</id>"
        f"<tipo>OUTRO_VALOR</tipo>"
        f"<outroValor>{divisor_val:.25f}</outroValor>"
        f"</Divisor></divisor>"
        f"<multiplicador><Multiplicador>"
        f"<outroValor>{multiplicador:.25f}</outroValor>"
        f"</Multiplicador></multiplicador>"
        f"<quantidade><Quantidade>"
        f"<id>{vid}</id>"
        f"<tipo>{qtd_tipo}</tipo>"
        f"<valorInformado>null</valorInformado>"
        f"<tipoImportadadoDoCartaoDePonto>null</tipoImportadadoDoCartaoDePonto>"
        f"<tipoImportadaCalendarioEnum>null</tipoImportadaCalendarioEnum>"
        f"<aplicarProporcionalidade>false</aplicarProporcionalidade>"
        f"</Quantidade></quantidade>"
        f"<verbaDeCalculo><Calculada><internalRef>{vid}</internalRef></Calculada></verbaDeCalculo>"
        f"<valorPago><ValorPago>"
        f"<id>{vid}</id>"
        f"<tipo>{val_pago_tipo}</tipo>"
        f"<valorInformado>{val_pago}</valorInformado>"
        f"<quantidade>null</quantidade>"
        f"<aplicarProporcionalidade>false</aplicarProporcionalidade>"
        f"<baseTabelada>null</baseTabelada>"
        f"</ValorPago></valorPago>"
        f"</FormulaCalculada></formula>"
    )


def _formula_reflexo(verba: dict, vid: int, calc_id: int) -> str:
    """Fórmula para verbas reflexas (FormulaReflexo)."""
    percentual = verba.get("percentual") or 1.0
    return (
        f"<formula><FormulaReflexo>"
        f"<id>{vid}</id><versao>0</versao>"
        f"<percentual>{float(percentual):.25f}</percentual>"
        f"<verbaDeCalculo><Calculada><internalRef>{vid}</internalRef></Calculada></verbaDeCalculo>"
        f"<valorPago><ValorPago>"
        f"<id>{vid}</id>"
        f"<tipo>INFORMADO</tipo>"
        f"<valorInformado>0E-25</valorInformado>"
        f"<quantidade>null</quantidade>"
        f"<aplicarProporcionalidade>false</aplicarProporcionalidade>"
        f"<baseTabelada>null</baseTabelada>"
        f"</ValorPago></valorPago>"
        f"</FormulaReflexo></formula>"
    )


# ── Seção: verbas (Calculada e Reflexo) ───────────────────────────────────────

def _xml_calculada(verba: dict, vid: int, calc_id: int, ordem: int,
                   adm_ts: int | None, dem_ts: int | None) -> str:
    nome = _esc(verba.get("nome_pjecalc") or verba.get("nome_sentenca") or "Verba")
    carac = _caracteristica_enum(verba.get("caracteristica"))
    ocorr = _ocorrencia_enum(verba.get("ocorrencia"))
    valor_informado = verba.get("valor_informado")
    gerar_principal = "VALOR_INFORMADO" if valor_informado is not None else "DIFERENCA"
    per_ini = verba.get("periodo_inicio")
    per_fim = verba.get("periodo_fim")
    p_ini_ts = _data_ts(per_ini) or adm_ts or 0
    p_fim_ts = _data_ts(per_fim) or dem_ts or 0

    return (
        f"<Calculada>"
        f"<id>{vid}</id><versao>0</versao>"
        f"<nome>{nome}</nome>"
        f"<descricao>{nome}</descricao>"
        f"<tipoVariacaoParcela>FIXA</tipoVariacaoParcela>"
        f"<incidenciaINSS>{_bool_str(verba.get('incidencia_inss'))}</incidenciaINSS>"
        f"<incidenciaIRPF>{_bool_str(verba.get('incidencia_ir'))}</incidenciaIRPF>"
        f"<incidenciaFGTS>{_bool_str(verba.get('incidencia_fgts'))}</incidenciaFGTS>"
        f"<incidenciaPrevidenciaPrivada>false</incidenciaPrevidenciaPrivada>"
        f"<incidenciaPensaoAlimenticia>false</incidenciaPensaoAlimenticia>"
        f"<caracteristica>{carac}</caracteristica>"
        f"<ocorrenciaDePagamento>{ocorr}</ocorrenciaDePagamento>"
        f"<jurosDoAjuizamento>OCORRENCIAS_VENCIDAS</jurosDoAjuizamento>"
        f"<gerarPrincipal>{gerar_principal}</gerarPrincipal>"
        f"<periodoInicial>{p_ini_ts}</periodoInicial>"
        f"<periodoFinal>{p_fim_ts}</periodoFinal>"
        f"<zeraValorNegativo>false</zeraValorNegativo>"
        f"<comentarios></comentarios>"
        f"<gerarReflexo>DIFERENCA</gerarReflexo>"
        f"<aplicarProporcionalidade>true</aplicarProporcionalidade>"
        f"<ativo>true</ativo>"
        f"<comporPrincipal>{_compor_principal(verba.get('compor_principal', True))}</comporPrincipal>"
        f"<verbaAlterada>false</verbaAlterada>"
        f"<salarioCategoriaValorDevido>null</salarioCategoriaValorDevido>"
        f"<salarioCategoriaValorPago>null</salarioCategoriaValorPago>"
        f"<excluirFaltaJustificada>false</excluirFaltaJustificada>"
        f"<excluirFaltaNaoJustificada>true</excluirFaltaNaoJustificada>"
        f"<excluirFeriasGozadas>true</excluirFeriasGozadas>"
        f"<ordem>{ordem}</ordem>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<assuntoCnj><AssuntoCnj></AssuntoCnj></assuntoCnj>"
        + _formula_calculada(verba, vid, calc_id) +
        f"<ocorrencias><List></List></ocorrencias>"
        f"<historicosDaVerbaDoValorDevido><List></List></historicosDaVerbaDoValorDevido>"
        f"<historicosDaVerbaDoValorPago><List></List></historicosDaVerbaDoValorPago>"
        f"<cartoesDePontoDaVerbaQuantidade><List></List></cartoesDePontoDaVerbaQuantidade>"
        f"<cartoesDePontoDaVerbaDivisor><List></List></cartoesDePontoDaVerbaDivisor>"
        f"<valesTransportesDoValorDevido><List></List></valesTransportesDoValorDevido>"
        f"<valesTransportesDoValorPago><List></List></valesTransportesDoValorPago>"
        f"</Calculada>"
    )


def _xml_reflexo(verba: dict, vid: int, calc_id: int, ordem: int,
                 adm_ts: int | None, dem_ts: int | None) -> str:
    nome = _esc(verba.get("nome_pjecalc") or verba.get("nome_sentenca") or "Reflexa")
    carac = _caracteristica_enum(verba.get("caracteristica"))
    ocorr = _ocorrencia_enum(verba.get("ocorrencia"))
    per_ini = verba.get("periodo_inicio")
    per_fim = verba.get("periodo_fim")
    p_ini_ts = _data_ts(per_ini) or adm_ts or 0
    p_fim_ts = _data_ts(per_fim) or dem_ts or 0

    return (
        f"<Reflexo>"
        f"<comportamentoDoReflexo>VALOR_MENSAL</comportamentoDoReflexo>"
        f"<periodoMediaReflexo>PERIODO_AQUISITIVO</periodoMediaReflexo>"
        f"<tratamentoDaFracaoDeMesDoReflexo>MANTER</tratamentoDaFracaoDeMesDoReflexo>"
        f"<id>{vid}</id><versao>0</versao>"
        f"<nome>{nome}</nome>"
        f"<descricao>{nome}</descricao>"
        f"<tipoVariacaoParcela>FIXA</tipoVariacaoParcela>"
        f"<incidenciaINSS>{_bool_str(verba.get('incidencia_inss'))}</incidenciaINSS>"
        f"<incidenciaIRPF>{_bool_str(verba.get('incidencia_ir'))}</incidenciaIRPF>"
        f"<incidenciaFGTS>{_bool_str(verba.get('incidencia_fgts'))}</incidenciaFGTS>"
        f"<incidenciaPrevidenciaPrivada>false</incidenciaPrevidenciaPrivada>"
        f"<incidenciaPensaoAlimenticia>false</incidenciaPensaoAlimenticia>"
        f"<caracteristica>{carac}</caracteristica>"
        f"<ocorrenciaDePagamento>{ocorr}</ocorrenciaDePagamento>"
        f"<jurosDoAjuizamento>OCORRENCIAS_VENCIDAS</jurosDoAjuizamento>"
        f"<gerarPrincipal>DIFERENCA</gerarPrincipal>"
        f"<periodoInicial>{p_ini_ts}</periodoInicial>"
        f"<periodoFinal>{p_fim_ts}</periodoFinal>"
        f"<zeraValorNegativo>false</zeraValorNegativo>"
        f"<comentarios></comentarios>"
        f"<gerarReflexo>NAO_APLICAR</gerarReflexo>"
        f"<aplicarProporcionalidade>true</aplicarProporcionalidade>"
        f"<ativo>true</ativo>"
        f"<comporPrincipal>{_compor_principal(verba.get('compor_principal', True))}</comporPrincipal>"
        f"<verbaAlterada>false</verbaAlterada>"
        f"<salarioCategoriaValorDevido>null</salarioCategoriaValorDevido>"
        f"<salarioCategoriaValorPago>null</salarioCategoriaValorPago>"
        f"<excluirFaltaJustificada>false</excluirFaltaJustificada>"
        f"<excluirFaltaNaoJustificada>true</excluirFaltaNaoJustificada>"
        f"<excluirFeriasGozadas>true</excluirFeriasGozadas>"
        f"<ordem>{ordem}</ordem>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<assuntoCnj><AssuntoCnj></AssuntoCnj></assuntoCnj>"
        + _formula_reflexo(verba, vid, calc_id) +
        f"<ocorrencias><List></List></ocorrencias>"
        f"<historicosDaVerbaDoValorDevido><List></List></historicosDaVerbaDoValorDevido>"
        f"<historicosDaVerbaDoValorPago><List></List></historicosDaVerbaDoValorPago>"
        f"<cartoesDePontoDaVerbaQuantidade><List></List></cartoesDePontoDaVerbaQuantidade>"
        f"<cartoesDePontoDaVerbaDivisor><List></List></cartoesDePontoDaVerbaDivisor>"
        f"<valesTransportesDoValorDevido><List></List></valesTransportesDoValorDevido>"
        f"<valesTransportesDoValorPago><List></List></valesTransportesDoValorPago>"
        f"</Reflexo>"
    )


def _xml_verbas(verbas_mapeadas: dict, calc_id: int,
                adm_ts: int | None, dem_ts: int | None) -> str:
    partes: list[str] = []
    verba_id_base = calc_id * 100
    ordem = 0

    todos: list[dict] = (
        verbas_mapeadas.get("predefinidas", [])
        + verbas_mapeadas.get("personalizadas", [])
        + verbas_mapeadas.get("nao_reconhecidas", [])
    )
    # Reflexas sugeridas (FGTS, 13º sobre verbas, etc.)
    reflexas = verbas_mapeadas.get("reflexas_sugeridas", [])

    for verba in todos:
        vid = verba_id_base + ordem
        tipo = (verba.get("tipo") or "Principal").strip()
        if tipo == "Reflexa":
            partes.append(_xml_reflexo(verba, vid, calc_id, ordem, adm_ts, dem_ts))
        else:
            partes.append(_xml_calculada(verba, vid, calc_id, ordem, adm_ts, dem_ts))
        ordem += 1

    # Reflexas sugeridas automáticas
    for reflexa in reflexas:
        vid = verba_id_base + ordem
        partes.append(_xml_reflexo(reflexa, vid, calc_id, ordem, adm_ts, dem_ts))
        ordem += 1

    return f"<verbas><Set>{''.join(partes)}</Set></verbas>"


# ── Seção: histórico salarial ─────────────────────────────────────────────────

def _xml_historico_salarial(dados: dict, calc_id: int,
                             adm_ts: int | None, dem_ts: int | None) -> str:
    """
    Gera o histórico salarial mensal (BASE DE CÁLCULO) a partir de ultima_remuneracao.
    Cada mês entre admissão e demissão recebe o mesmo salário.
    """
    salario = dados.get("contrato", {}).get("ultima_remuneracao") \
        or dados.get("contrato", {}).get("maior_remuneracao")

    if not salario or not adm_ts or not dem_ts:
        return f"<historicosSalariais><Set></Set></historicosSalariais>"

    hist_id = calc_id * 10 + 9
    meses = _meses_entre(adm_ts, dem_ts)

    ocorrencias_xml = []
    for idx, (ano, mes) in enumerate(meses):
        oc_id = hist_id * 1000 + idx
        mes_ts = _mes_ts(ano, mes)
        ocorrencias_xml.append(
            f"<OcorrenciaDoHistoricoSalarial>"
            f"<id>{oc_id}</id><versao>0</versao>"
            f"<dataOcorrencia>{mes_ts}</dataOcorrencia>"
            f"<valor>{float(salario):.2f}</valor>"
            f"<recolhidoFGTS>false</recolhidoFGTS>"
            f"<recolhidoINSS>false</recolhidoINSS>"
            f"<incidenciaFGTS>true</incidenciaFGTS>"
            f"<incidenciaINSS>true</incidenciaINSS>"
            f"<historicoSalarial><HistoricoSalarial><internalRef>{hist_id}</internalRef>"
            f"</HistoricoSalarial></historicoSalarial>"
            f"</OcorrenciaDoHistoricoSalarial>"
        )

    return (
        f"<historicosSalariais><Set>"
        f"<HistoricoSalarial>"
        f"<id>{hist_id}</id><versao>0</versao>"
        f"<nome>BASE DE C&#193;LCULO</nome>"
        f"<tipoVariacaoParcela>FIXA</tipoVariacaoParcela>"
        f"<incidenciaFGTS>true</incidenciaFGTS>"
        f"<aplicarProporcionalidadeFGTS>true</aplicarProporcionalidadeFGTS>"
        f"<incidenciaINSS>true</incidenciaINSS>"
        f"<aplicarProporcionalidadeINSS>true</aplicarProporcionalidadeINSS>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<ocorrencias><List>{''.join(ocorrencias_xml)}</List></ocorrencias>"
        f"</HistoricoSalarial>"
        f"</Set></historicosSalariais>"
    )


# ── Seção: FGTS ───────────────────────────────────────────────────────────────

def _xml_fgts(fgts: dict, calc_id: int, fid: int,
              adm_ts: int | None, dem_ts: int | None) -> str:
    aliquota = _aliquota_fgts_enum(fgts.get("aliquota"))
    tem_multa = bool(fgts.get("multa_40"))
    multa_enum = "QUARENTA_POR_CENTO" if tem_multa else "NAO_SE_APLICA"

    return (
        f"<fgts><Fgts>"
        f"<id>{fid}</id><versao>0</versao>"
        f"<periodoInicial>{adm_ts or 0}</periodoInicial>"
        f"<periodoFinal>{dem_ts or 0}</periodoFinal>"
        f"<destinoDoFgts>DEPOSITAR</destinoDoFgts>"
        f"<aliquota>{aliquota}</aliquota>"
        f"<multa>{_bool_str(tem_multa)}</multa>"
        f"<excluirAvisoDaMulta>true</excluirAvisoDaMulta>"
        f"<tipoDoValorDaMulta>CALCULADA</tipoDoValorDaMulta>"
        f"<valorInformadoDaMulta>null</valorInformadoDaMulta>"
        f"<multaDoFgts>{multa_enum}</multaDoFgts>"
        f"<incidenciaDoFgts>SOBRE_O_TOTAL_DEVIDO</incidenciaDoFgts>"
        f"<multaDoArtigo467>{_bool_str(fgts.get('multa_467'))}</multaDoArtigo467>"
        f"<multa10>false</multa10>"
        f"<contribuicaoSocial05>false</contribuicaoSocial05>"
        f"<deduzirDoFGTS>false</deduzirDoFGTS>"
        f"<incidenciaPensaoAlimenticia>false</incidenciaPensaoAlimenticia>"
        f"<incidenciaPensaoAlimenticiaSobreMulta>false</incidenciaPensaoAlimenticiaSobreMulta>"
        f"<indiceMulta>1.0000000000000000000000000</indiceMulta>"
        f"<indiceMulta467>null</indiceMulta467>"
        f"<taxaDeJurosParaDataDemissao>0E-25</taxaDeJurosParaDataDemissao>"
        f"<comporPrincipal>SIM</comporPrincipal>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<operacoesDeFgts><Set></Set></operacoesDeFgts>"
        f"<ocorrencias><Set></Set></ocorrencias>"
        f"</Fgts></fgts>"
    )


# ── Seção: INSS ───────────────────────────────────────────────────────────────

def _xml_inss(cs: dict, calc_id: int, iid: int,
              adm_ts: int | None, dem_ts: int | None) -> str:
    resp = cs.get("responsabilidade", "Ambos")
    cobrar_reclamante = resp in ("Empregado", "Ambos", None)

    return (
        f"<inss><Inss>"
        f"<id>{iid}</id><versao>0</versao>"
        f"<tipoAliquotaSegurado>SEGURADO_EMPREGADO</tipoAliquotaSegurado>"
        f"<aliquotaSeguradoFixa>null</aliquotaSeguradoFixa>"
        f"<limitarTeto>false</limitarTeto>"
        f"<tipoAliquotaEmpregador>FIXA</tipoAliquotaEmpregador>"
        f"<aliquotaEmpresaFixa>20.0000</aliquotaEmpresaFixa>"
        f"<aliquotaRATFixa>2.0000</aliquotaRATFixa>"
        f"<aliquotaTerceirosFixa>null</aliquotaTerceirosFixa>"
        f"<apurarEmpresaPorAtividade>false</apurarEmpresaPorAtividade>"
        f"<apurarRATPorAtividade>false</apurarRATPorAtividade>"
        f"<apurarTerceirosPorAtividade>false</apurarTerceirosPorAtividade>"
        f"<apurarInssSobreSalariosPagos>false</apurarInssSobreSalariosPagos>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<aliquotasPorPeriodos><List></List></aliquotasPorPeriodos>"
        f"<periodosComOpcaoSimples><List></List></periodosComOpcaoSimples>"
        f"<inssSobreSalariosDevidos><InssSobreSalariosDevidos>"
        f"<id>{iid}</id><versao>0</versao>"
        f"<apurarInssSegurado>true</apurarInssSegurado>"
        f"<cobrarInssDoReclamante>{_bool_str(cobrar_reclamante)}</cobrarInssDoReclamante>"
        f"<corrigirDescontoReclamante>false</corrigirDescontoReclamante>"
        f"<dataInicioPeriodo>{adm_ts or 0}</dataInicioPeriodo>"
        f"<dataTerminoPeriodo>{dem_ts or 0}</dataTerminoPeriodo>"
        f"<ocorrencias></ocorrencias>"
        f"<ocorrenciasAtualizacao></ocorrenciasAtualizacao>"
        f"<inss></inss>"
        f"</InssSobreSalariosDevidos></inssSobreSalariosDevidos>"
        f"<inssSobreSalariosPagos><InssSobreSalariosPagos>"
        f"<id>{iid}</id><versao>0</versao>"
        f"<dataInicioPeriodo>{adm_ts or 0}</dataInicioPeriodo>"
        f"<dataTerminoPeriodo>{dem_ts or 0}</dataTerminoPeriodo>"
        f"<ocorrencias></ocorrencias>"
        f"<ocorrenciasAtualizacao></ocorrenciasAtualizacao>"
        f"<inss></inss>"
        f"</InssSobreSalariosPagos></inssSobreSalariosPagos>"
        f"</Inss></inss>"
    )


# ── Seção: IRPF ───────────────────────────────────────────────────────────────

def _xml_irpf(ir: dict, calc_id: int, irid: int) -> str:
    apurar = bool(ir.get("apurar", False))
    dependentes = int(ir.get("dependentes") or 0)
    possui_dep = dependentes > 0

    return (
        f"<irpf><Irpf>"
        f"<id>{irid}</id><versao>0</versao>"
        f"<apurarImpostoRenda>{_bool_str(apurar)}</apurarImpostoRenda>"
        f"<incidirSobreJurosDeMora>false</incidirSobreJurosDeMora>"
        f"<cobrarDoReclamado>false</cobrarDoReclamado>"
        f"<considerarTributacaoExclusiva>false</considerarTributacaoExclusiva>"
        f"<considerarTributacaoEmSeparado>false</considerarTributacaoEmSeparado>"
        f"<regimeDeCaixa>false</regimeDeCaixa>"
        f"<deduzirContribuicaoSocialDevidaPeloReclamante>true</deduzirContribuicaoSocialDevidaPeloReclamante>"
        f"<deduzirPrevidenciaPrivada>true</deduzirPrevidenciaPrivada>"
        f"<deduzirPensaoAlimenticia>true</deduzirPensaoAlimenticia>"
        f"<deduzirHonorariosDevidosPeloReclamante>true</deduzirHonorariosDevidosPeloReclamante>"
        f"<aposentadoMaiorQue65Anos>false</aposentadoMaiorQue65Anos>"
        f"<possuiDependentes>{_bool_str(possui_dep)}</possuiDependentes>"
        f"<quantidadeDependentes>{dependentes}</quantidadeDependentes>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<ocorrencias><Set></Set></ocorrencias>"
        f"<ocorrenciasAtualizacao><Set></Set></ocorrenciasAtualizacao>"
        f"<ocorrenciasPagamento><Set></Set></ocorrenciasPagamento>"
        f"</Irpf></irpf>"
    )


# ── Seção: honorários ─────────────────────────────────────────────────────────

def _xml_honorarios(hon: dict, calc_id: int, base_id: int) -> str:
    parts: list[str] = []
    hid = base_id

    percentual = hon.get("percentual")
    valor_fixo = hon.get("valor_fixo")
    periciais = hon.get("periciais")
    parte_devedora = {
        "Reclamado": "RECLAMADO",
        "Reclamante": "RECLAMANTE",
        "Ambos": "AMBOS",
    }.get(hon.get("parte_devedora") or "Reclamado", "RECLAMADO")

    if percentual is not None or valor_fixo is not None:
        tipo_valor = "CALCULADO" if percentual is not None else "INFORMADO"
        aliquota = float(percentual * 100) if percentual is not None else 0.0
        valor = float(valor_fixo or 0.0)
        parts.append(
            f"<Honorario>"
            f"<id>{hid}</id><versao>0</versao>"
            f"<descricao>HONOR&#193;RIOS ADVOCAT&#205;CIOS</descricao>"
            f"<tipoHonorario>ADVOCATICIOS</tipoHonorario>"
            f"<tipoDeDevedor>{parte_devedora}</tipoDeDevedor>"
            f"<nomeCredor>ADVOGADO DO RECLAMANTE</nomeCredor>"
            f"<tipoDocumentoFiscalCredor>CPF</tipoDocumentoFiscalCredor>"
            f"<numeroDocumentoFiscalCredor>null</numeroDocumentoFiscalCredor>"
            f"<apurarIRRF>false</apurarIRRF>"
            f"<tipoImpostoRenda>null</tipoImpostoRenda>"
            f"<tipoValor>{tipo_valor}</tipoValor>"
            f"<valor>{valor:.25f}</valor>"
            f"<valorJurosCalcExterno>null</valorJurosCalcExterno>"
            f"<dataVencimento>0</dataVencimento>"
            f"<tipoDeIndiceDeCorrecao>UTILIZAR_INDICE_TRABALHISTA</tipoDeIndiceDeCorrecao>"
            f"<outroIndiceDeCorrecao>null</outroIndiceDeCorrecao>"
            f"<aplicarJuros>false</aplicarJuros>"
            f"<dataApartirDeAplicarJuros>null</dataApartirDeAplicarJuros>"
            f"<aliquota>{aliquota:.2f}</aliquota>"
            f"<baseParaApuracao>BRUTO</baseParaApuracao>"
            f"<baseHonorario>0E-25</baseHonorario>"
            f"<indiceCorrecaoHonorario>1.0000000000000000000000000</indiceCorrecaoHonorario>"
            f"<taxaJurosHonorario>null</taxaJurosHonorario>"
            f"<valorInicialFaixaIrpf>null</valorInicialFaixaIrpf>"
            f"<valorFinalFaixaIrpf>null</valorFinalFaixaIrpf>"
            f"<valorAliquotaIrpf>null</valorAliquotaIrpf>"
            f"<valorDeducaoIrpf>null</valorDeducaoIrpf>"
            f"<valorImpostoRenda>0E-25</valorImpostoRenda>"
            f"<apurarIRPFSobreJuros>false</apurarIRPFSobreJuros>"
            f"<tipoCobrancaReclamante>DESCONTAR_CREDITO</tipoCobrancaReclamante>"
            f"<origemRegistro>CALCULO</origemRegistro>"
            f"<dataEvento>null</dataEvento>"
            f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
            f"<verbasSelecionadas><List></List></verbasSelecionadas>"
            f"</Honorario>"
        )
        hid += 1

    if periciais is not None and periciais > 0:
        parts.append(
            f"<Honorario>"
            f"<id>{hid}</id><versao>0</versao>"
            f"<descricao>HONOR&#193;RIOS PERICIAIS</descricao>"
            f"<tipoHonorario>PERICIAIS</tipoHonorario>"
            f"<tipoDeDevedor>{parte_devedora}</tipoDeDevedor>"
            f"<nomeCredor>PERITO</nomeCredor>"
            f"<tipoDocumentoFiscalCredor>CPF</tipoDocumentoFiscalCredor>"
            f"<numeroDocumentoFiscalCredor>null</numeroDocumentoFiscalCredor>"
            f"<apurarIRRF>false</apurarIRRF>"
            f"<tipoImpostoRenda>null</tipoImpostoRenda>"
            f"<tipoValor>INFORMADO</tipoValor>"
            f"<valor>{float(periciais):.25f}</valor>"
            f"<valorJurosCalcExterno>null</valorJurosCalcExterno>"
            f"<dataVencimento>0</dataVencimento>"
            f"<tipoDeIndiceDeCorrecao>UTILIZAR_INDICE_TRABALHISTA</tipoDeIndiceDeCorrecao>"
            f"<outroIndiceDeCorrecao>null</outroIndiceDeCorrecao>"
            f"<aplicarJuros>false</aplicarJuros>"
            f"<dataApartirDeAplicarJuros>null</dataApartirDeAplicarJuros>"
            f"<aliquota>0.00</aliquota>"
            f"<baseParaApuracao>BRUTO</baseParaApuracao>"
            f"<baseHonorario>0E-25</baseHonorario>"
            f"<indiceCorrecaoHonorario>1.0000000000000000000000000</indiceCorrecaoHonorario>"
            f"<taxaJurosHonorario>null</taxaJurosHonorario>"
            f"<valorInicialFaixaIrpf>null</valorInicialFaixaIrpf>"
            f"<valorFinalFaixaIrpf>null</valorFinalFaixaIrpf>"
            f"<valorAliquotaIrpf>null</valorAliquotaIrpf>"
            f"<valorDeducaoIrpf>null</valorDeducaoIrpf>"
            f"<valorImpostoRenda>0E-25</valorImpostoRenda>"
            f"<apurarIRPFSobreJuros>false</apurarIRPFSobreJuros>"
            f"<tipoCobrancaReclamante>DESCONTAR_CREDITO</tipoCobrancaReclamante>"
            f"<origemRegistro>CALCULO</origemRegistro>"
            f"<dataEvento>null</dataEvento>"
            f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
            f"<verbasSelecionadas><List></List></verbasSelecionadas>"
            f"</Honorario>"
        )

    return f"<honorarios><Set>{''.join(parts)}</Set></honorarios>"


# ── Seção: custas judiciais ───────────────────────────────────────────────────

def _xml_custas(calc_id: int, cid: int) -> str:
    return (
        f"<custasJudiciais><CustasJudiciais>"
        f"<id>{cid}</id><versao>0</versao>"
        f"<baseParaCustasCalculadas>BRUTO_DEVIDO_AO_RECLAMANTE_MAIS_DEBITOS_RECLAMADO</baseParaCustasCalculadas>"
        f"<tipoDeCustasDeConhecimentoDoReclamante>NAO_SE_APLICA</tipoDeCustasDeConhecimentoDoReclamante>"
        f"<tipoDeCustasDeConhecimentoDoReclamado>CALCULADA_2_POR_CENTO</tipoDeCustasDeConhecimentoDoReclamado>"
        f"<dataVencimentoConhecimentoDoReclamado>0</dataVencimentoConhecimentoDoReclamado>"
        f"<valorConhecimentoDoReclamado>0E-25</valorConhecimentoDoReclamado>"
        f"<tipoDeCustasDeLiquidacao>NAO_SE_APLICA</tipoDeCustasDeLiquidacao>"
        f"<valorBaseCustasCalculadas>0E-25</valorBaseCustasCalculadas>"
        f"<indiceCorrecaoCustasConhecimentoReclamado>1.0000000000000000000000000</indiceCorrecaoCustasConhecimentoReclamado>"
        f"<pisoCustasConhecimentoReclamado>10.64</pisoCustasConhecimentoReclamado>"
        f"<tetoCustasConhecimentoReclamante>22583.24</tetoCustasConhecimentoReclamante>"
        f"<tetoCustasConhecimentoReclamado>22583.24</tetoCustasConhecimentoReclamado>"
        f"<tipoCobrancaReclamante>DESCONTAR_CREDITO</tipoCobrancaReclamante>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<autosJudiciais><Set></Set></autosJudiciais>"
        f"<custasFixasAtualizacao><Set></Set></custasFixasAtualizacao>"
        f"</CustasJudiciais></custasJudiciais>"
    )


# ── Seção: parâmetros de atualização ─────────────────────────────────────────

def _xml_parametros(cj: dict, cs: dict, calc_id: int) -> str:
    indice = _indice_enum(cj.get("indice_correcao"))
    juros = _juros_enum(cj.get("taxa_juros"))
    base_juros_raw = cj.get("base_juros", "Verbas")
    base_juros = "VERBA_INSS" if base_juros_raw == "Verbas" else "CREDITO_TOTAL"
    jam_fgts = _bool_str(cj.get("jam_fgts"))
    lei11941 = _bool_str(cs.get("lei_11941", True))

    return (
        f"<parametrosDeAtualizacao><ParametrosDeAtualizacao>"
        f"<id>{calc_id}</id><versao>0</versao>"
        f"<indiceTrabalhista>{indice}</indiceTrabalhista>"
        f"<outroIndiceTrabalhista>IPCA</outroIndiceTrabalhista>"
        f"<combinarOutroIndice>false</combinarOutroIndice>"
        f"<apartirDeOutroIndice>null</apartirDeOutroIndice>"
        f"<ignorarTaxaNegativa>false</ignorarTaxaNegativa>"
        f"<juros>{juros}</juros>"
        f"<jurosPadrao>null</jurosPadrao>"
        f"<aplicarJurosFasePreJudicial>true</aplicarJurosFasePreJudicial>"
        f"<combinarOutroJuros>true</combinarOutroJuros>"
        f"<apertirDe>null</apertirDe>"
        f"<baseDeJurosDasVerbas>{base_juros}</baseDeJurosDasVerbas>"
        f"<indiceDeCorrecaoDoFGTS>UTILIZAR_INDICE_TRABALHISTA</indiceDeCorrecaoDoFGTS>"
        f"<jurosDeFgtsComJam>{jam_fgts}</jurosDeFgtsComJam>"
        f"<indiceDeCorrecaoDePrevidenciaPrivada>UTILIZAR_INDICE_TRABALHISTA</indiceDeCorrecaoDePrevidenciaPrivada>"
        f"<jurosDePrevidenciaPrivada>false</jurosDePrevidenciaPrivada>"
        f"<indiceDeCorrecaoDasCustas>UTILIZAR_INDICE_TRABALHISTA</indiceDeCorrecaoDasCustas>"
        f"<jurosDeCustas>false</jurosDeCustas>"
        f"<correcaoTrabalhistaDosSalariosDevidosDoINSS>true</correcaoTrabalhistaDosSalariosDevidosDoINSS>"
        f"<jurosTrabalhistasDosSalariosDevidosDoINSS>false</jurosTrabalhistasDosSalariosDevidosDoINSS>"
        f"<correcaoPrevidenciariaDosSalariosDevidosDoINSS>false</correcaoPrevidenciariaDosSalariosDevidosDoINSS>"
        f"<jurosPrevidenciariosDosSalariosDevidosDoINSS>false</jurosPrevidenciariosDosSalariosDevidosDoINSS>"
        f"<aplicarMultaDosSalariosDevidosDoINSS>false</aplicarMultaDosSalariosDevidosDoINSS>"
        f"<tipoDeMultaDosSalariosDevidosDoINSS>URBANA</tipoDeMultaDosSalariosDevidosDoINSS>"
        f"<pagamentoDaMultaDosSalariosDevidosDoINSS>INTEGRAL</pagamentoDaMultaDosSalariosDevidosDoINSS>"
        f"<salarioDevidoFormaAplicacao>null</salarioDevidoFormaAplicacao>"
        f"<salarioPagoFormaAplicacao>MES_A_MES</salarioPagoFormaAplicacao>"
        f"<correcaoTrabalhistaDosSalariosPagosDoINSS>false</correcaoTrabalhistaDosSalariosPagosDoINSS>"
        f"<jurosTrabalhistasDosSalariosPagosDoINSS>false</jurosTrabalhistasDosSalariosPagosDoINSS>"
        f"<correcaoPrevidenciariaDosSalariosPagosDoINSS>true</correcaoPrevidenciariaDosSalariosPagosDoINSS>"
        f"<jurosPrevidenciariosDosSalariosPagosDoINSS>true</jurosPrevidenciariosDosSalariosPagosDoINSS>"
        f"<aplicarMultaDosSalariosPagosDoINSS>true</aplicarMultaDosSalariosPagosDoINSS>"
        f"<tipoDeMultaDosSalariosPagosDoINSS>URBANA</tipoDeMultaDosSalariosPagosDoINSS>"
        f"<pagamentoDaMultaDosSalariosPagosDoINSS>INTEGRAL</pagamentoDaMultaDosSalariosPagosDoINSS>"
        f"<correcaoDasCustas>true</correcaoDasCustas>"
        f"<lei11941>{lei11941}</lei11941>"
        f"<apartirDeLei11941>1236222000000</apartirDeLei11941>"
        f"<lei11941Pago>false</lei11941Pago>"
        f"<lei11941Multa>true</lei11941Multa>"
        f"<apartirDeLei11941Pago>1236222000000</apartirDeLei11941Pago>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<listaDeExcecaoDeJurosDaAtualizacao><Set></Set></listaDeExcecaoDeJurosDaAtualizacao>"
        f"<listaDeCombinacaoDeIndices><Set></Set></listaDeCombinacaoDeIndices>"
        f"<listaDeCombinacaoDeJuros><Set></Set></listaDeCombinacaoDeJuros>"
        f"<entePublico>null</entePublico>"
        f"</ParametrosDeAtualizacao></parametrosDeAtualizacao>"
    )


# ── Seções simples ────────────────────────────────────────────────────────────

def _xml_previdencia(calc_id: int) -> str:
    return (
        f"<previdenciaPrivada><PrevidenciaPrivada>"
        f"<id>{calc_id}</id><versao>0</versao>"
        f"<apurarPrevidenciaPrivada>false</apurarPrevidenciaPrivada>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<aliquotas><Set></Set></aliquotas>"
        f"<ocorrencias><Set></Set></ocorrencias>"
        f"</PrevidenciaPrivada></previdenciaPrivada>"
    )


def _xml_pensao(calc_id: int) -> str:
    return (
        f"<pensaoAlimenticia><PensaoAlimenticia>"
        f"<id>{calc_id}</id><versao>0</versao>"
        f"<apurarPensaoAlimenticia>false</apurarPensaoAlimenticia>"
        f"<aliquota>null</aliquota>"
        f"<incidirSobreJuros>false</incidirSobreJuros>"
        f"<valorBaseVerbas>0.00</valorBaseVerbas>"
        f"<valorBaseVerbasTributaveis>0.00</valorBaseVerbasTributaveis>"
        f"<valorBaseFgts>0.00</valorBaseFgts>"
        f"<valorBaseMultaDoFgts>0.00</valorBaseMultaDoFgts>"
        f"<origemRegistro>CALCULO</origemRegistro>"
        f"<percPrincipalTributavel>null</percPrincipalTributavel>"
        f"<percPrincipalNaoTributavel>null</percPrincipalNaoTributavel>"
        f"<incidirSobrePrincipalTributavel>true</incidirSobrePrincipalTributavel>"
        f"<incidirSobrePrincipalNaoTributavel>false</incidirSobrePrincipalNaoTributavel>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"</PensaoAlimenticia></pensaoAlimenticia>"
    )


def _xml_secoes_vazias(calc_id: int) -> str:
    """Seções vazias que vêm ANTES de fgts/inss (ordem exata dos arquivos válidos)."""
    return (
        f"<listaDeFerias><Set></Set></listaDeFerias>"
        f"<apuracoesDeJuros><List></List></apuracoesDeJuros>"
        f"<excecoesDaCargaHoraria><Set></Set></excecoesDaCargaHoraria>"
        f"<excecoesDoSabado><Set></Set></excecoesDoSabado>"
        f"<faltas><Set></Set></faltas>"
    )


def _xml_secoes_pos_calculo(calc_id: int) -> str:
    """Seções vazias que vêm APÓS custasJudiciais (ordem exata dos arquivos válidos)."""
    return (
        f"<seguroDesemprego><SeguroDesemprego>"
        f"<id>{calc_id}</id><versao>0</versao>"
        f"<apurarSeguroDesemprego>false</apurarSeguroDesemprego>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<itensHistoricoSalarialDeSegudoDesemprego><List></List></itensHistoricoSalarialDeSegudoDesemprego>"
        f"<itensSalarioDevidoDeSeguroDesemprego><List></List></itensSalarioDevidoDeSeguroDesemprego>"
        f"</SeguroDesemprego></seguroDesemprego>"
        f"<salarioFamilia><SalarioFamilia>"
        f"<id>{calc_id}</id><versao>0</versao>"
        f"<apurarSalarioFamilia>false</apurarSalarioFamilia>"
        f"<calculo><Calculo><internalRef>{calc_id}</internalRef></Calculo></calculo>"
        f"<variacaoQuantidadesFilhos><List></List></variacaoQuantidadesFilhos>"
        f"<itensHistoricoSalarial><List></List></itensHistoricoSalarial>"
        f"<itensSalarioDevido><List></List></itensSalarioDevido>"
        f"</SalarioFamilia></salarioFamilia>"
        f"<pontosFacultativos><Set></Set></pontosFacultativos>"
        f"<historicosValidacao><List></List></historicosValidacao>"
        f"<historicosValidacaoAtualizacao><List></List></historicosValidacaoAtualizacao>"
        f"<cartoesDePonto><Set></Set></cartoesDePonto>"
        f"<pagamentos><Set></Set></pagamentos>"
        f"<apuracoesCartaoDePonto><List></List></apuracoesCartaoDePonto>"
        f"<apuracoesDiariasCartaoDePonto><List></List></apuracoesDiariasCartaoDePonto>"
        f"<excecoesDoFechamentoDeCartaoDePonto><Set></Set></excecoesDoFechamentoDeCartaoDePonto>"
    )


# ── Montagem do XML completo ──────────────────────────────────────────────────

def _montar_xml(dados: dict, verbas_mapeadas: dict, calc_id: int) -> str:
    cont = dados.get("contrato", {})
    proc = dados.get("processo", {})
    fgts = dados.get("fgts", {})
    hon  = dados.get("honorarios", {})
    # parametrizacao.py retorna honorarios como lista; converter para dict legado
    if isinstance(hon, list):
        hon_dict: dict = {}
        for _h in hon:
            _tipo = _h.get("tipo", "SUCUMBENCIAIS")
            if _tipo in ("SUCUMBENCIAIS", "CONTRATUAIS"):
                hon_dict["percentual"]      = _h.get("percentual")
                hon_dict["valor_fixo"]      = _h.get("valor_informado")
                hon_dict["parte_devedora"]  = {
                    "RECLAMADO":  "Reclamado",
                    "RECLAMANTE": "Reclamante",
                    "AMBOS":      "Ambos",
                }.get(_h.get("devedor", "RECLAMADO"), "Reclamado")
            elif _tipo == "PERICIAIS":
                hon_dict["periciais"] = _h.get("valor_informado") or _h.get("percentual")
        hon = hon_dict
    cj   = dados.get("correcao_juros", {})
    cs   = dados.get("contribuicao_social", {})
    ir   = dados.get("imposto_renda", {})
    avp  = dados.get("aviso_previo", {})
    pres = dados.get("prescricao", {})

    adm_ts  = _data_ts(cont.get("admissao"))
    dem_ts  = _data_ts(cont.get("demissao"))
    aju_ts  = _data_ts(cont.get("ajuizamento"))
    now_ts  = _ts_now()

    carga_horaria = cont.get("carga_horaria") or 220
    maior_rem = cont.get("maior_remuneracao") or cont.get("ultima_remuneracao") or 0.0
    ultima_rem = cont.get("ultima_remuneracao")

    regime = _regime_enum(cont.get("regime"))
    apuracao_aviso = _apuracao_aviso_enum(avp.get("tipo"))
    prazo_aviso = int(avp.get("prazo_dias") or 0)
    projetar_aviso = _bool_str(avp.get("projetar"))
    presc_fgts = _bool_str(pres.get("fgts")) if pres.get("fgts") is not None else "true"
    presc_quiq = _bool_str(pres.get("quinquenal")) if pres.get("quinquenal") is not None else "true"
    indice_acum = "MES_SUBSEQUENTE_E_MES_DO_VENCIMENTO"

    # IDs das seções
    fid   = calc_id * 10 + 1
    iid   = calc_id * 10 + 2
    irid  = calc_id * 10 + 3
    cid   = calc_id * 10 + 4
    hon_base = calc_id * 10 + 5

    xml_parts = [
        '<?xml version="1.0" encoding="ISO-8859-1"?>',
        f"<Calculo>",
        f"<id>{calc_id}</id>",
        f"<versao>3</versao>",
        f"<atualizacao>null</atualizacao>",
        f"<hashCodeLiquidacao>null</hashCodeLiquidacao>",
        f"<dataCriacao>{now_ts}</dataCriacao>",
        f"<dataAdmissao>{adm_ts or 0}</dataAdmissao>",
        f"<dataDemissao>{dem_ts or 0}</dataDemissao>",
        f"<dataAjuizamento>{aju_ts or 0}</dataAjuizamento>",
        f"<valorUltimaRemuneracao>{f'{float(ultima_rem):.2f}' if ultima_rem else 'null'}</valorUltimaRemuneracao>",
        f"<valorMaiorRemuneracao>{float(maior_rem):.2f}</valorMaiorRemuneracao>",
        f"<dataInicioCalculo>null</dataInicioCalculo>",
        f"<dataTerminoCalculo>{dem_ts or 0}</dataTerminoCalculo>",
        f"<valorCargaHorariaPadrao>{float(carga_horaria):.4f}</valorCargaHorariaPadrao>",
        f"<sabadoDiaUtil>true</sabadoDiaUtil>",
        f"<projetaAvisoIndenizado>{projetar_aviso}</projetaAvisoIndenizado>",
        f"<consideraFeriadoEstadual>true</consideraFeriadoEstadual>",
        f"<prescricaoFgts>{presc_fgts}</prescricaoFgts>",
        f"<prescricaoQuinquenal>{presc_quiq}</prescricaoQuinquenal>",
        f"<limitarAvosAoPeriodoDoCalculo>false</limitarAvosAoPeriodoDoCalculo>",
        f"<zeraValorNegativo>false</zeraValorNegativo>",
        f"<consideraFeriadoMunicipal>true</consideraFeriadoMunicipal>",
        f"<tipoCalculo>ADVOGADO</tipoCalculo>",
        f"<prazoFeriasProporcional>null</prazoFeriasProporcional>",
        f"<dataDeLiquidacao>null</dataDeLiquidacao>",
        f"<regimeDoContrato>{regime}</regimeDoContrato>",
        f"<indicesAcumulados>{indice_acum}</indicesAcumulados>",
        f"<usuarioCriador>offline</usuarioCriador>",
        f"<apuracaoPrazoDoAvisoPrevio>{apuracao_aviso}</apuracaoPrazoDoAvisoPrevio>",
        f"<prazoAvisoInformado>{prazo_aviso if apuracao_aviso == 'INFORMADO_DIAS' else 'null'}</prazoAvisoInformado>",
        f"<ativo>true</ativo>",
        f"<processoInformadoManualmente>false</processoInformadoManualmente>",
        f"<comentarios></comentarios>",
        f"<idSetor>0</idSetor>",
        f"<instancia>null</instancia>",
        f"<validado>false</validado>",
        f"<hashCalculoCorreto>true</hashCalculoCorreto>",
        f"<hashAtualizacaoCorreto>false</hashAtualizacaoCorreto>",
        f"<diaFechamentoMes>31</diaFechamentoMes>",
        f"<calculoExterno>false</calculoExterno>",
        f"<parcelasAtualizaveisCreditosReclamante>null</parcelasAtualizaveisCreditosReclamante>",
        f"<parcelasAtualizaveisDescontoCreditosReclamante>null</parcelasAtualizaveisDescontoCreditosReclamante>",
        f"<parcelasAtualizaveisOutrosDebitosReclamado>null</parcelasAtualizaveisOutrosDebitosReclamado>",
        f"<parcelasAtualizaveisDebitosReclamante>null</parcelasAtualizaveisDebitosReclamante>",
        f"<versaoDoSistema>{_VERSAO_SISTEMA}</versaoDoSistema>",
        _xml_processo(proc, calc_id),
        "<municipio><Municipio></Municipio></municipio>",
        _xml_verbas(verbas_mapeadas, calc_id, adm_ts, dem_ts),
        _xml_historico_salarial(dados, calc_id, adm_ts, dem_ts),
        _xml_secoes_vazias(calc_id),           # listaDeFerias, apuracoesDeJuros, excecoesDaCargaHoraria, excecoesDoSabado, faltas
        _xml_fgts(fgts, calc_id, fid, adm_ts, dem_ts),
        _xml_inss(cs, calc_id, iid, adm_ts, dem_ts),
        _xml_previdencia(calc_id),
        _xml_pensao(calc_id),
        _xml_parametros(cj, cs, calc_id),
        "<multas><Set></Set></multas>",
        _xml_honorarios(hon, calc_id, hon_base),
        _xml_irpf(ir, calc_id, irid),
        _xml_custas(calc_id, cid),
        _xml_secoes_pos_calculo(calc_id),      # seguroDesemprego, salarioFamilia, pontosFacultativos, ...
        "</Calculo>",
    ]

    return "".join(xml_parts)


# ── Função pública ────────────────────────────────────────────────────────────

def gerar_pjc(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
    sessao_id: str,
) -> Path:
    """
    Gera um arquivo .PJC (ZIP+XML ISO-8859-1) a partir dos parâmetros confirmados.

    O arquivo pode ser importado no PJE-Calc (Arquivo → Importar Cálculo).
    Após a importação, o usuário deve:
    1. Revisar parâmetros no PJE-Calc
    2. Clicar Operações → Validar
    3. Clicar Operações → Liquidar
    4. Clicar Operações → Exportar (para o .pjc final com valores calculados)
    5. Juntar o .pjc exportado nos autos do PJe

    Retorna o caminho do arquivo .PJC gerado.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    calc_id = _calc_id(sessao_id)
    numero = dados.get("processo", {}).get("numero") or sessao_id[:8]
    numero_limpo = re.sub(r"[^\d]", "", numero)[:20]

    nome_base = f"PROCESSO_{numero_limpo}_CALCULO_{calc_id}_DATA_{datetime.now().strftime('%d%m%Y')}_HORA_{datetime.now().strftime('%H%M%S')}"
    caminho_pjc = OUTPUT_DIR / f"{nome_base}.PJC"

    xml_str = _montar_xml(dados, verbas_mapeadas, calc_id)
    xml_bytes = xml_str.encode("iso-8859-1", errors="xmlcharrefreplace")

    with zipfile.ZipFile(caminho_pjc, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{nome_base}.PJC", xml_bytes)

    logger.info(f"Arquivo .PJC gerado: {caminho_pjc} ({caminho_pjc.stat().st_size:,} bytes)")
    return caminho_pjc
