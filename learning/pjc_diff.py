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


def _disc_item(ch: ET.Element, idx: int) -> str:
    """#80-BJ: chave natural de um item de coleção (descricao/nome/credor/…),
    fallback = posição entre irmãos da mesma tag."""
    for c in _CAMPOS_DISCRIMINADORES:
        v = (ch.findtext(c) or "").strip()
        if v and v.lower() != "null":
            return _norm_nome(v)[:48]
    return str(idx)


def _flatten(el: ET.Element, prefixo: str = "") -> dict[str, str]:
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
            tag_path = f"{ch.tag}[{_disc_item(ch, idx)}]"
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
        filhos = list(ch)
        if not filhos:
            v = _norm_valor(ch.text or "")
            if v != "":
                out[caminho] = v
        else:
            out.update(_flatten(ch, caminho))
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

    # 2. Entidades nomeadas — coletar DEFINIÇÕES onde quer que estejam;
    #    dedup por (categoria, nome) preferindo a definição mais completa.
    verbas: dict[str, dict] = {}
    reflexos: dict[str, dict] = {}
    historicos: dict[str, dict] = {}
    for el in _walk(root):
        if not _eh_definicao_entidade(el):
            continue
        nome = _norm_nome(el.findtext("nome") or "")
        params = _flatten(el)
        params.pop("nome", None)
        params.pop("descricao", None)  # descricao ~ nome truncado (#80-O)
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
            flat = _flatten(el)
            if flat:
                secoes[sec] = flat

    return {
        "parametros_calculo": parametros,
        "verbas": verbas,
        "reflexos": reflexos,
        "historicos": historicos,
        "secoes": secoes,
    }


def _diff_params(de: dict[str, str], para: dict[str, str]) -> list[dict]:
    """Diff campo a campo entre dois dicts aplainados."""
    campos = []
    for k in sorted(set(de) | set(para)):
        v1, v2 = de.get(k), para.get(k)
        if v1 != v2:
            campos.append({"campo": k, "de": v1, "para": v2})
    return campos


def _diff_entidades(ger: dict[str, dict], defn: dict[str, dict]) -> dict:
    """Diff de um grupo de entidades nomeadas (verbas/reflexos/históricos)."""
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
    return {"adicionadas": adicionadas, "removidas": removidas, "alteradas": alteradas}


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


def resumo_legivel(rel: dict[str, Any]) -> list[str]:
    """Linhas legíveis do relatório (para UI/log)."""
    linhas: list[str] = []
    if rel.get("resumo", {}).get("identicos"):
        return ["✓ PJC definitivo idêntico ao gerado — nenhuma correção manual detectada."]
    for grupo, rotulo in (("verbas", "Verba"), ("reflexos", "Reflexo"),
                          ("historicos", "Histórico")):
        g = rel.get(grupo, {})
        for n in g.get("adicionadas", []):
            linhas.append(f"➕ {rotulo} ADICIONADA manualmente: {n}")
        for n in g.get("removidas", []):
            linhas.append(f"➖ {rotulo} REMOVIDA manualmente: {n}")
        for alt in g.get("alteradas", []):
            for c in alt["campos"]:
                linhas.append(
                    f"✏️ {rotulo} '{alt['nome']}' — {c['campo']}: "
                    f"{c['de'] if c['de'] is not None else '(vazio)'} → "
                    f"{c['para'] if c['para'] is not None else '(removido)'}"
                )
    for c in rel.get("parametros_calculo", []):
        linhas.append(f"⚙️ Parâmetro do cálculo — {c['campo']}: {c['de']} → {c['para']}")
    for sec, campos in rel.get("secoes", {}).items():
        for c in campos:
            linhas.append(f"⚙️ {sec} — {c['campo']}: {c['de']} → {c['para']}")
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


def carregar_relatorio(sessao_id: str, store_dir) -> dict | None:
    from pathlib import Path
    p = Path(store_dir) / f"{sessao_id}_diff.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
