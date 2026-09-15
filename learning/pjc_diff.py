# learning/pjc_diff.py — Plano 3 do Learning Engine (FATIA 1)
#
# Diff estruturado entre o PJC GERADO pela automação e o PJC DEFINITIVO que o
# usuário corrigiu manualmente no PJE-Calc e incorporou ao processo.
#
# PRINCÍPIO CENTRAL — comparar PARÂMETROS, não valores recomputados: alterar 1
# parâmetro (ex.: divisor 220→180) recalcula centenas de ocorrências mensais.
# Se o diff comparasse valores, viraria ruído; o aprendizado precisa da CAUSA
# RAIZ. Por isso o subtree <ocorrencias> (valores derivados) é EXCLUÍDO e os
# campos de parâmetro (divisor, multiplicador, quantidade, base, característica,
# ocorrência de pagamento, incidências, períodos, ativo...) são comparados.
#
# Estrutura real do PJC (ZIP → XML ISO-8859-1, XStream):
#   <Calculo>                       raiz com escalares (datas, prescrição, ...)
#     ...<Calculada>/<Informada>    definições de verba principal (nome + params)
#     ...<Reflexo>                  reflexos (ativo, característica, fórmula)
#     ...<HistoricoSalarial>        históricos salariais
#     ...<Honorario>, <juros>, <Fgts>  seções globais
#   XStream serializa a PRIMEIRA ocorrência de um objeto por extenso e as
#   demais como <internalRef> — definições podem estar ANINHADAS (ex.: a verba
#   principal definida dentro do baseVerba de um Reflexo). O parser coleta
#   definições onde quer que estejam e, ao aplanar uma entidade, substitui
#   definições aninhadas por "ref:<nome>" (não duplica a árvore).

from __future__ import annotations

import json
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

# Tags de DEFINIÇÃO de entidade nomeada (verba/reflexo/histórico)
_TAGS_VERBA = {"Calculada", "Informada", "ImportadaDoCartaoDePonto"}
_TAG_REFLEXO = "Reflexo"
_TAG_HISTORICO = "HistoricoSalarial"
_TAGS_ENTIDADE = _TAGS_VERBA | {_TAG_REFLEXO, _TAG_HISTORICO}
# #80-DP: tags cuja REFERÊNCIA (`<Tag><internalRef>ID</internalRef></Tag>`) é
# resolvida para o NOME da definição — inclui o cartão de ponto (coluna
# "Hs EXT"/"Hs Trabalhadas"), que não é entidade diffada mas é o vínculo que
# diz de ONDE a verba importa quantidade/divisor.
_TAGS_REFERENCIAVEIS = _TAGS_ENTIDADE | {"CartaoDePonto"}

# Tags de RUÍDO — identidade interna, auditoria, hashes e valores derivados.
# ⚠ NÃO incluir 'ativo' (reflexo ativado/desativado é o parâmetro mais
# importante) nem 'valorInformado' (é parâmetro informado pelo usuário).
_TAGS_RUIDO = {
    "id", "versao", "internalRef", "externalRef",
    "hashCodeLiquidacao", "hashCalculoCorreto", "hashAtualizacaoCorreto",
    "dataCriacao", "atualizacao", "usuarioCriador", "dataDeLiquidacao",
    "ocorrencias",  # valores mensais RECOMPUTADOS — nunca diffar
    "gprec", "dadosEstruturados", "validado", "idSetor", "instancia",
    "processoInformadoManualmente", "verbaAlterada", "ordem",
    # Valores DERIVADOS do total da liquidação (recomputam a cada mudança de
    # qualquer parâmetro — comparar seria ruído; o PARÂMETRO é percentual/base):
    "valorBaseCustasCalculadas", "valorConhecimentoDoReclamado",
    "valorConhecimentoDoReclamante", "baseHonorario",
    "valorApurado", "valorDevidoTotal", "valorTotal", "totalGeral",
    # #80-BI: derivados recomputados pela liquidação (índices/taxas acumulados
    # até a data — mudam a cada re-liquidação sem NENHUMA edição do usuário).
    # O PARÂMETRO do usuário é o tipo/percentual/combinação, nunca o acumulado.
    "taxaDeJuros", "taxaDeJurosParaDataDemissao",
    "indiceMulta", "indiceAcumulado", "indiceAcumuladoDaMulta",
    "indiceCorrecaoCustasFixas", "informacaoUltimoIndice",
    "valorCorrigido", "valorCorrigidoParaIrpfDecimoTerceiro",
    "valorCorrigidoParaIrpfDemaisVerbas", "valorVerbaParaContribuicaoSocial",
    # #80-BI: backref da entidade ao cálculo e grade DIÁRIA da jornada
    # (centenas de linhas recomputadas — análogo a <ocorrencias>)
    "calculo", "ocorrenciasJornadaApuracaoCartao",
    # #80-DP: versão do PJE-Calc que exportou (2.14 → 2.16 não é correção) e
    # faixas/descontos de IRPF dos honorários — DERIVADOS da tabela do IR na
    # liquidação, não parâmetro do usuário.
    "versaoDoSistema",
    "valorDescontoSimplificadoIrpf", "valorParcelaFaixaReducaoIrpf",
    "valorTetoFaixaIsencaoIrpf", "valorTetoFaixaReducaoIrpf",
}

# Sufixos de caminho DERIVADOS (recomputados a partir de percentual × base)
_SUFIXOS_DERIVADOS = ("Honorario.valor",)

# Seções globais (fora de verbas) cujo subtree de parâmetros interessa.
# ⚠ #80-BI (14/07/2026) — NOMES REAIS das tags XStream (auditados contra 2
# PJCs reais do Cidadão 2.15.1). A lista anterior usava nomes INEXISTENTES
# ("juros", "imposto", "contribuicao", "atualizacaoMonetaria") e OMITIA
# fgts/inss/irpf/cartoesDePonto/seguroDesemprego — edições manuais nessas
# seções NÃO entravam no aprendizado do PJC definitivo.
# NÃO incluir apuracoesCartaoDePonto / apuracoesDiariasCartaoDePonto /
# historicosValidacao* — são RESULTADO recomputado (análogo a <ocorrencias>).
# ⚠ CARTÃO DE PONTO: a DEFINIÇÃO (params que o usuário edita — forma de
# apuração, jornadas, intervalos, noturno, escala, tolerâncias) vive em
# `apuracoesCartaoDePonto`; `cartoesDePonto` são as COLUNAS APURADAS
# (Hs EXT/Intrajornada/Trabalhadas — resultado, não diffar). `apuracoesDeJuros`
# também é resultado (valores corrigidos por verba) — fora.
_SECOES_GLOBAIS = (
    "fgts", "inss", "irpf",
    "multas", "honorarios", "custasJudiciais",
    "parametrosDeAtualizacao",
    "apuracoesCartaoDePonto",
    "excecoesDoFechamentoDeCartaoDePonto", "excecoesDaCargaHoraria",
    "excecoesDoSabado",
    "seguroDesemprego", "pensaoAlimenticia", "previdenciaPrivada",
    "listaDeFerias", "faltas", "pagamentos",
    "salarioFamilia", "pontosFacultativos",
)


def _norm_nome(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip().upper()


def _norm_valor(txt: str) -> str:
    """Normaliza um valor escalar p/ comparação estável: decimais XStream
    ("220.0000000000000000000000000", "0E-25", "1.50000...") → forma canônica."""
    t = (txt or "").strip()
    if not t:
        return ""
    try:
        d = Decimal(t)
        t_norm = format(d.normalize(), "f")
        return t_norm
    except (InvalidOperation, ValueError):
        return t


def _eh_definicao_entidade(el: ET.Element) -> bool:
    """True se o elemento é uma DEFINIÇÃO completa de verba/reflexo/histórico
    (tag de entidade + filho <nome> não-vazio + corpo com vários campos)."""
    if el.tag not in _TAGS_ENTIDADE:
        return False
    nome = el.findtext("nome") or ""
    return bool(nome.strip()) and len(list(el)) > 4


# #80-BJ: containers de coleção do XStream e campos que identificam cada item
_TAGS_COLECAO = {"Set", "List", "Map"}
_CAMPOS_DISCRIMINADORES = ("descricao", "nome", "nomeCredor",
                           "tipoDeOperacaoDoFgts", "competencia",
                           "sequencial", "data")


# #80-DP: wrappers de VÍNCULO cujo filho referencia uma entidade nomeada —
# em ordem de preferência p/ discriminar o item (o histórico/cartão vinculado
# identifica o item melhor que a verba dona, que é igual em todos os itens).
_WRAPPERS_VINCULO = ("historicoSalarial", "cartaoDePonto", "verbaDeCalculo")


def _nome_referenciado(el: ET.Element, refs: dict[str, str] | None) -> str | None:
    """Nome da entidade que `el` (tag referenciável) define ou referencia:
    definição inline → seu <nome>; `<internalRef>ID</internalRef>` → nome da
    definição de mesmo id (mapa `refs`). None se não resolver."""
    if el.tag not in _TAGS_REFERENCIAVEIS:
        return None
    nome = (el.findtext("nome") or "").strip()
    if nome:
        return _norm_nome(nome)
    iref = (el.findtext("internalRef") or "").strip()
    if refs and iref in refs:
        return refs[iref]
    return None


def _disc_item(ch: ET.Element, idx: int, refs: dict[str, str] | None = None) -> str:
    """#80-BJ: chave natural de um item de coleção (descricao/nome/credor/…);
    #80-DP: item de VÍNCULO (HistoricoSalarialDaVerba, CartaoDePontoDaVerba,
    ItemBaseVerba) é keyed pelo nome da entidade vinculada — assim
    "13º SALÁRIO ganhou COMISSOES na base" sai como
    `HistoricoSalarialDaVerba[COMISSOES].tipoVinculoHistorico: (vazio) → BASE`
    em vez de um índice opaco; fallback = posição entre irmãos da mesma tag."""
    for c in _CAMPOS_DISCRIMINADORES:
        v = (ch.findtext(c) or "").strip()
        if v and v.lower() != "null":
            return _norm_nome(v)[:48]
    for w in _WRAPPERS_VINCULO:
        wrap = ch.find(w)
        if wrap is None:
            continue
        for e in wrap:
            nome = _nome_referenciado(e, refs)
            if nome:
                return nome[:48]
    return str(idx)


def _mapa_refs(root: ET.Element) -> dict[str, str]:
    """#80-DP: id → nome de TODA definição referenciável (verba/reflexo/
    histórico/cartão). O XStream serializa a 1ª ocorrência por extenso e as
    demais como `<internalRef>ID</internalRef>` — sem o mapa, o vínculo da
    verba com seu histórico-base ("COMISSOES") e com a coluna do cartão
    ("Hs Trabalhadas") era DESCARTADO do diff, e a verba adicionada saía sem
    a informação mais importante para o aprendizado."""
    refs: dict[str, str] = {}
    for el in _walk(root):
        if el.tag in _TAGS_REFERENCIAVEIS:
            _id = (el.findtext("id") or "").strip()
            nome = (el.findtext("nome") or "").strip()
            if _id and nome and _id not in refs:
                refs[_id] = _norm_nome(nome)
    return refs


def _flatten(el: ET.Element, prefixo: str = "",
             refs: dict[str, str] | None = None) -> dict[str, str]:
    """Aplaina um subtree em {caminho: valor}, pulando ruído, substituindo
    definições ANINHADAS de entidade por 'ref:<nome>' (não duplica árvores).

    #80-BJ (0000054-29, 14/07/2026): itens de coleção (`<Set>` com N
    `<Honorario>`, operações de FGTS…) COLAPSAVAM no mesmo caminho aplainado —
    o último vencia. Honorário pericial ADICIONADO ao lado da sucumbência saía
    no diff como MUTAÇÃO da sucumbência ("descricao: SUCUMBÊNCIA → PERICIAIS",
    "aliquota: 9 → null") e o aprendizado não via a adição. Agora cada item de
    coleção é keyed por discriminador natural: `Set.Honorario[HONORÁRIOS
    PERICIAIS - ENGENHEIRO].aliquota`."""
    out: dict[str, str] = {}
    eh_colecao = el.tag in _TAGS_COLECAO
    idx_por_tag: dict[str, int] = {}
    for ch in el:
        if ch.tag in _TAGS_RUIDO:
            continue
        idx = idx_por_tag.get(ch.tag, 0)
        idx_por_tag[ch.tag] = idx + 1
        tag_path = ch.tag
        if eh_colecao and len(list(ch)) > 0:
            tag_path = f"{ch.tag}[{_disc_item(ch, idx, refs)}]"
        caminho = f"{prefixo}.{tag_path}" if prefixo else tag_path
        # #80-BJ: comparar sufixos derivados IGNORANDO os discriminadores
        # "[...]" — senão `Set.Honorario[X].valor` escapa do filtro e o valor
        # recomputado da alíquota vira ruído a cada re-liquidação.
        caminho_base = re.sub(r"\[[^\]]*\]", "", caminho)
        if any(caminho_base.endswith(s) for s in _SUFIXOS_DERIVADOS):
            continue
        if _eh_definicao_entidade(ch):
            out[caminho] = f"ref:{_norm_nome(ch.findtext('nome') or '')}"
            continue
        # #80-DP: referência (`<internalRef>`) a entidade definida noutro
        # ponto do XML → mesmo "ref:<nome>" da definição inline. Sem isto o
        # mesmo vínculo saía "ref:X" num PJC e (vazio) no outro (falso diff)
        # e o histórico-base da verba adicionada não aparecia.
        if ch.tag in _TAGS_REFERENCIAVEIS and not ch.findtext("nome"):
            nome_ref = _nome_referenciado(ch, refs)
            if nome_ref:
                out[caminho] = f"ref:{nome_ref}"
                continue
        filhos = list(ch)
        if not filhos:
            v = _norm_valor(ch.text or "")
            if v != "":
                out[caminho] = v
        else:
            out.update(_flatten(ch, caminho, refs))
    return out


def _walk(el: ET.Element):
    for ch in el:
        yield ch
        yield from _walk(ch)


def parse_pjc_params(pjc_bytes: bytes) -> dict[str, Any]:
    """Extrai a árvore de PARÂMETROS de um PJC.

    Retorna:
      {"parametros_calculo": {campo: valor},              # escalares da raiz
       "verbas":     {NOME: {"tipo": tag, "params": {...}}},
       "reflexos":   {NOME: {"params": {...}}},
       "historicos": {NOME: {"params": {...}}},
       "secoes":     {secao: {campo: valor}}}             # juros/honorários/...
    """
    z = zipfile.ZipFile(BytesIO(pjc_bytes))
    nome_interno = z.namelist()[0]
    xml_txt = z.read(nome_interno).decode("iso-8859-1", "replace")
    root = ET.fromstring(xml_txt.encode("iso-8859-1"),
                         parser=ET.XMLParser(encoding="iso-8859-1"))

    # 1. Escalares da raiz (parâmetros gerais do cálculo)
    parametros: dict[str, str] = {}
    for ch in root:
        if ch.tag in _TAGS_RUIDO or ch.tag in _SECOES_GLOBAIS:
            continue
        if len(list(ch)) == 0:
            v = _norm_valor(ch.text or "")
            if v != "":
                parametros[ch.tag] = v

    # #80-DP: mapa id → nome p/ resolver <internalRef> em vínculos
    refs = _mapa_refs(root)

    # 2. Entidades nomeadas — coletar DEFINIÇÕES onde quer que estejam;
    #    dedup por (categoria, nome) preferindo a definição mais completa.
    verbas: dict[str, dict] = {}
    reflexos: dict[str, dict] = {}
    historicos: dict[str, dict] = {}
    for el in _walk(root):
        if not _eh_definicao_entidade(el):
            continue
        nome = _norm_nome(el.findtext("nome") or "")
        params = _flatten(el, refs=refs)
        params.pop("nome", None)
        params.pop("descricao", None)  # descricao ~ nome truncado (#80-O)
        # #80-DP: backrefs da entidade a SI MESMA (item de vínculo → verba
        # dona, fórmula → verba) são identidade, não parâmetro — e entre uma
        # verba e seu desdobramento sempre "diferem" (ruído puro).
        auto = f"ref:{nome}"
        for k in [k for k, v in params.items() if v == auto]:
            params.pop(k)
        if el.tag in _TAGS_VERBA:
            alvo, extra = verbas, {"tipo": el.tag}
        elif el.tag == _TAG_REFLEXO:
            alvo, extra = reflexos, {}
        else:
            alvo, extra = historicos, {}
        existente = alvo.get(nome)
        if existente is None or len(params) > len(existente.get("params", {})):
            alvo[nome] = {**extra, "params": params}

    # 3. Seções globais
    secoes: dict[str, dict] = {}
    for sec in _SECOES_GLOBAIS:
        el = root.find(sec)
        if el is not None:
            flat = _flatten(el, refs=refs)
            if flat:
                secoes[sec] = flat

    return {
        "parametros_calculo": parametros,
        "verbas": verbas,
        "reflexos": reflexos,
        "historicos": historicos,
        "secoes": secoes,
    }


def _sem_valor(v) -> bool:
    return v is None or str(v).strip().lower() == "null"


def _diff_params(de: dict[str, str], para: dict[str, str]) -> list[dict]:
    """Diff campo a campo entre dois dicts aplainados.

    #80-DP: tag AUSENTE e tag com texto literal "null" são o MESMO estado
    (sem valor) — `comentarios: (vazio) → null` em 20 reflexos era ruído que
    diluía o sinal do prompt. O literal "null" é preservado nos valores
    (chaves de regra já persistidas dependem dele)."""
    campos = []
    for k in sorted(set(de) | set(para)):
        v1, v2 = de.get(k), para.get(k)
        if v1 != v2 and not (_sem_valor(v1) and _sem_valor(v2)):
            campos.append({"campo": k, "de": v1, "para": v2})
    return campos


# #80-DP: parâmetros SEM sinal p/ o aprendizado (vazios/nulos são omitidos
# na apresentação; estes são boilerplate idêntico em toda verba).
_PARAMS_BOILERPLATE = {
    "comentarios", "salarioCategoriaValorDevido", "salarioCategoriaValorPago",
    "zeraValorNegativo", "jurosDoAjuizamento",
}
_MIN_PREFIXO_ORIGEM = 6


def _params_relevantes(params: dict[str, str]) -> dict[str, str]:
    """Parâmetros de uma entidade que interessam ao aprendizado — o MESMO
    conjunto que o differ compara (ocorrências/derivados já excluídos no
    parse), menos nulos/vazios e boilerplate."""
    out: dict[str, str] = {}
    for k, v in params.items():
        if v is None or str(v).strip().lower() in ("", "null"):
            continue
        if k in _PARAMS_BOILERPLATE:
            continue
        out[k] = v
    return out


def _verba_origem(nome: str, ger: dict[str, dict]) -> str | None:
    """#80-DP: entidade do PJC GERADO da qual a ADICIONADA é desdobramento —
    o nome mais longo que é PREFIXO próprio do nome novo, com fronteira de
    palavra (`HORAS EXTRAS 50%` ⊂ `HORAS EXTRAS 50% - REMUNERAÇÃO VARIÁVEL`).
    Sem candidato → None."""
    alvo = _norm_nome(nome)
    melhor = None
    for cand in ger:
        c = _norm_nome(cand)
        if len(c) < _MIN_PREFIXO_ORIGEM or len(c) >= len(alvo):
            continue
        if not alvo.startswith(c):
            continue
        if alvo[len(c)].isalnum():  # "HE 5" ⊄ "HE 50%"
            continue
        if melhor is None or len(c) > len(_norm_nome(melhor)):
            melhor = cand
    return melhor


def _detalhe_entidade(nome: str, ent: dict, contraparte: dict[str, dict],
                      removida: bool = False) -> dict:
    """Detalhe de entidade ADICIONADA (contraparte = gerado) ou REMOVIDA
    (contraparte = definitivo): parâmetros relevantes + desdobramento."""
    det: dict[str, Any] = {
        "nome": nome,
        "tipo": ent.get("tipo"),
        "params": _params_relevantes(ent.get("params", {})),
    }
    if removida:
        return det
    origem = _verba_origem(nome, contraparte)
    if origem:
        p_orig = _params_relevantes(contraparte[origem].get("params", {}))
        difs = _diff_params(p_orig, det["params"])
        det["desdobramento_de"] = origem
        det["diferencas_vs_origem"] = difs
        det["params_iguais_a_origem"] = len(set(p_orig) & set(det["params"])) - len(
            [d for d in difs if d["de"] is not None and d["para"] is not None])
    return det


def _diff_entidades(ger: dict[str, dict], defn: dict[str, dict]) -> dict:
    """Diff de um grupo de entidades nomeadas (verbas/reflexos/históricos).

    #80-DP: entidades ADICIONADAS/REMOVIDAS saem com DETALHE (parâmetros
    relevantes + desdobramento). Só o nome não ensina nada — o aprendizado
    "base mista → duas verbas de HE (Súmula 340)" precisa ver base
    histórico, divisor IMPORTADA_DO_CARTAO, multiplicador 0,5 e reflexos."""
    adicionadas = sorted(set(defn) - set(ger))
    removidas = sorted(set(ger) - set(defn))
    alteradas = []
    for nome in sorted(set(ger) & set(defn)):
        campos = _diff_params(ger[nome].get("params", {}), defn[nome].get("params", {}))
        t1, t2 = ger[nome].get("tipo"), defn[nome].get("tipo")
        if t1 != t2:
            campos.insert(0, {"campo": "tipo_lancamento", "de": t1, "para": t2})
        if campos:
            alteradas.append({"nome": nome, "campos": campos})
    return {
        "adicionadas": adicionadas,
        "removidas": removidas,
        "alteradas": alteradas,
        "adicionadas_detalhe": [_detalhe_entidade(n, defn[n], ger) for n in adicionadas],
        "removidas_detalhe": [_detalhe_entidade(n, ger[n], defn, removida=True)
                              for n in removidas],
    }


def diff_pjc(pjc_gerado: bytes, pjc_definitivo: bytes) -> dict[str, Any]:
    """Diff estruturado PJC gerado ↔ PJC definitivo. Retorna relatório JSON-able."""
    ger = parse_pjc_params(pjc_gerado)
    defn = parse_pjc_params(pjc_definitivo)

    rel: dict[str, Any] = {
        "gerado_em": datetime.utcnow().isoformat() + "Z",
        "parametros_calculo": _diff_params(ger["parametros_calculo"],
                                           defn["parametros_calculo"]),
        "verbas": _diff_entidades(ger["verbas"], defn["verbas"]),
        "reflexos": _diff_entidades(ger["reflexos"], defn["reflexos"]),
        "historicos": _diff_entidades(ger["historicos"], defn["historicos"]),
        "secoes": {},
    }
    for sec in sorted(set(ger["secoes"]) | set(defn["secoes"])):
        campos = _diff_params(ger["secoes"].get(sec, {}), defn["secoes"].get(sec, {}))
        if campos:
            rel["secoes"][sec] = campos

    # Resumo p/ UI e para o log
    n_campos = (
        len(rel["parametros_calculo"])
        + sum(len(a["campos"]) for g in ("verbas", "reflexos", "historicos")
              for a in rel[g]["alteradas"])
        + sum(len(c) for c in rel["secoes"].values())
    )
    n_entidades = sum(
        len(rel[g]["adicionadas"]) + len(rel[g]["removidas"])
        for g in ("verbas", "reflexos", "historicos")
    )
    rel["resumo"] = {
        "campos_alterados": n_campos,
        "entidades_adicionadas_removidas": n_entidades,
        "identicos": n_campos == 0 and n_entidades == 0,
    }
    return rel


_RE_EPOCH_MS = re.compile(r"^-?\d{11,14}$")
_RE_CAMPO_DATA = re.compile(r"(periodo|data|competencia|vencimento)", re.I)


def _fmt_valor(campo: str, valor: Any) -> str:
    """Valor legível p/ o LLM: epoch-ms de campos de data → DD/MM/AAAA (BRT);
    None → marcador. `1775012400000` não ensina nada; `01/04/2026` ensina."""
    if valor is None:
        return "(vazio)"
    v = str(valor)
    if _RE_EPOCH_MS.match(v) and _RE_CAMPO_DATA.search(campo or ""):
        try:
            from datetime import timedelta, timezone
            dt = datetime.fromtimestamp(int(v) / 1000, tz=timezone(timedelta(hours=-3)))
            return dt.strftime("%d/%m/%Y")
        except (ValueError, OverflowError, OSError):
            return v
    return v


_PARAMS_POR_LINHA = 5


def _linhas_params(params: dict[str, str], recuo: str = "   · ") -> list[str]:
    itens = [f"{k}={_fmt_valor(k, v)}" for k, v in params.items()]
    return [recuo + "; ".join(itens[i:i + _PARAMS_POR_LINHA])
            for i in range(0, len(itens), _PARAMS_POR_LINHA)]


def _linhas_entidade_adicionada(rotulo: str, det: dict, removidas: list[str]) -> list[str]:
    """#80-DP: verba/reflexo/histórico ADICIONADO sai com seus parâmetros —
    como desdobramento da entidade de origem (diferenças lado a lado) quando
    há prefixo em comum com o gerado, senão com a lista completa."""
    nome, tipo = det["nome"], det.get("tipo")
    cab = f"➕ {rotulo} ADICIONADA manualmente: {nome}" + (f" ({tipo})" if tipo else "")
    origem = det.get("desdobramento_de")
    if not origem:
        return [cab + " — parâmetros:"] + _linhas_params(det.get("params", {}))
    situacao = ("REMOVIDA no definitivo — substituição"
                if _norm_nome(origem) in {_norm_nome(r) for r in removidas}
                else "MANTIDA no definitivo — coexistem")
    out = [f"{cab} — DESDOBRAMENTO de '{origem}' ({situacao})"]
    difs = det.get("diferencas_vs_origem") or []
    if difs:
        out.append(f"   · difere de '{origem}' em {len(difs)} parâmetro(s):")
        for d in difs:
            out.append(f"   · {d['campo']}: {_fmt_valor(d['campo'], d['de'])} → "
                       f"{_fmt_valor(d['campo'], d['para'])}")
    n_iguais = det.get("params_iguais_a_origem")
    if n_iguais:
        out.append(f"   · demais {n_iguais} parâmetro(s) iguais aos de '{origem}'")
    return out


def resumo_legivel(rel: dict[str, Any]) -> list[str]:
    """Linhas legíveis do relatório (para UI/log e p/ o prompt do aprendizado)."""
    linhas: list[str] = []
    if rel.get("resumo", {}).get("identicos"):
        return ["✓ PJC definitivo idêntico ao gerado — nenhuma correção manual detectada."]
    for grupo, rotulo in (("verbas", "Verba"), ("reflexos", "Reflexo"),
                          ("historicos", "Histórico")):
        g = rel.get(grupo, {})
        removidas = g.get("removidas", [])
        detalhes = {d.get("nome"): d for d in g.get("adicionadas_detalhe", [])
                    if isinstance(d, dict)}
        for n in g.get("adicionadas", []):
            det = detalhes.get(n)
            if det:
                linhas.extend(_linhas_entidade_adicionada(rotulo, det, removidas))
            else:  # relatório antigo (sem detalhe)
                linhas.append(f"➕ {rotulo} ADICIONADA manualmente: {n}")
        det_rem = {d.get("nome"): d for d in g.get("removidas_detalhe", [])
                   if isinstance(d, dict)}
        for n in removidas:
            linhas.append(f"➖ {rotulo} REMOVIDA manualmente: {n}")
            if det_rem.get(n, {}).get("params"):
                linhas.extend(_linhas_params(det_rem[n]["params"]))
        for alt in g.get("alteradas", []):
            for c in alt["campos"]:
                linhas.append(
                    f"✏️ {rotulo} '{alt['nome']}' — {c['campo']}: "
                    f"{_fmt_valor(c['campo'], c['de'])} → "
                    f"{_fmt_valor(c['campo'], c['para']) if c['para'] is not None else '(removido)'}"
                )
    for c in rel.get("parametros_calculo", []):
        linhas.append(f"⚙️ Parâmetro do cálculo — {c['campo']}: "
                      f"{_fmt_valor(c['campo'], c['de'])} → {_fmt_valor(c['campo'], c['para'])}")
    for sec, campos in rel.get("secoes", {}).items():
        for c in campos:
            linhas.append(f"⚙️ {sec} — {c['campo']}: "
                          f"{_fmt_valor(c['campo'], c['de'])} → {_fmt_valor(c['campo'], c['para'])}")
    return linhas


def executar_diff_e_persistir(
    sessao_id: str,
    pjc_gerado_path: str,
    pjc_definitivo_bytes: bytes,
    store_dir,
) -> dict[str, Any]:
    """Pipeline FATIA 1: lê o PJC gerado, diffa contra o definitivo, persiste
    o definitivo + relatório em `<store_dir>/` e retorna o relatório."""
    from pathlib import Path
    store = Path(store_dir)
    store.mkdir(parents=True, exist_ok=True)

    pjc_gerado = Path(pjc_gerado_path).read_bytes()
    rel = diff_pjc(pjc_gerado, pjc_definitivo_bytes)
    rel["sessao_id"] = sessao_id
    rel["pjc_gerado"] = {"arquivo": str(pjc_gerado_path), "bytes": len(pjc_gerado)}

    def_path = store / f"{sessao_id}_definitivo.pjc"
    def_path.write_bytes(pjc_definitivo_bytes)
    rel["pjc_definitivo"] = {"arquivo": str(def_path), "bytes": len(pjc_definitivo_bytes)}

    rel_path = store / f"{sessao_id}_diff.json"
    rel_path.write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "Plano 3 FATIA 1: diff PJC persistido p/ sessão %s — %d campo(s) alterado(s), "
        "%d entidade(s) add/rem",
        sessao_id, rel["resumo"]["campos_alterados"],
        rel["resumo"]["entidades_adicionadas_removidas"],
    )
    return rel


# Chaves do relatório que NÃO vêm do diff (metadados do upload/aprendizado)
_CHAVES_PRESERVADAS = ("sessao_id", "pjc_gerado", "pjc_definitivo",
                       "sentenca_definitiva", "aprendizado")


def reprocessar_relatorio(sessao_id: str, store_dir,
                          pjc_gerado_path: str | None = None) -> dict | None:
    """#80-DP: re-diffa a partir dos arquivos já persistidos (PJC gerado +
    `<sessao>_definitivo.pjc`), preservando os metadados do upload — p/ que
    relatórios gerados por versões anteriores do differ ganhem o detalhe das
    entidades adicionadas antes de uma reanálise. None se faltar arquivo."""
    from pathlib import Path
    store = Path(store_dir)
    rel_antigo = carregar_relatorio(sessao_id, store)
    if rel_antigo is None:
        return None
    ger_path = Path(pjc_gerado_path or (rel_antigo.get("pjc_gerado") or {}).get("arquivo") or "")
    def_path = store / f"{sessao_id}_definitivo.pjc"
    if not ger_path.is_file() or not def_path.is_file():
        logger.warning("reprocessar_relatorio(%s): arquivo ausente (gerado=%s definitivo=%s)",
                       sessao_id, ger_path, def_path)
        return None
    rel = diff_pjc(ger_path.read_bytes(), def_path.read_bytes())
    for k in _CHAVES_PRESERVADAS:
        if k in rel_antigo:
            rel[k] = rel_antigo[k]
    rel["reprocessado_em"] = datetime.utcnow().isoformat() + "Z"
    (store / f"{sessao_id}_diff.json").write_text(
        json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    return rel


def carregar_relatorio(sessao_id: str, store_dir) -> dict | None:
    from pathlib import Path
    p = Path(store_dir) / f"{sessao_id}_diff.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
