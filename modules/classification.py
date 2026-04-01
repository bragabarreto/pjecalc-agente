# modules/classification.py — Classificação e Mapeamento de Verbas para o PJE-Calc
# Manual Técnico PJE-Calc, Seção 3

from __future__ import annotations

from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_EXTRACTION_TEMPERATURE


# ── Tabela de verbas pré-definidas no PJE-Calc (Manual, Seção 3.1) ────────────
# Formato: "nome_sentenca_normalizado" → configuração PJE-Calc

VERBAS_PREDEFINIDAS: dict[str, dict[str, Any]] = {
    # Chave: nome normalizado (minúsculo, sem acento)
    "saldo de salario": {
        "nome_pjecalc": "Saldo de Salário",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["maior_remuneracao", "periodo"],
    },
    "aviso previo indenizado": {
        "nome_pjecalc": "Aviso Prévio Indenizado",
        "caracteristica": "Aviso Previo",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["prazo_aviso_previo", "maior_remuneracao"],
    },
    "13 salario proporcional": {
        "nome_pjecalc": "13º Salário Proporcional",
        "caracteristica": "13o Salario",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "base_calculo"],
    },
    "decimo terceiro salario proporcional": {
        "nome_pjecalc": "13º Salário Proporcional",
        "caracteristica": "13o Salario",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "base_calculo"],
    },
    "ferias proporcionais": {
        "nome_pjecalc": "Férias Proporcionais + 1/3",
        "caracteristica": "Ferias",
        "ocorrencia": "Periodo Aquisitivo",
        "incidencia_fgts": False,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "situacao", "dobra"],
    },
    "ferias vencidas": {
        "nome_pjecalc": "Férias Vencidas + 1/3",
        "caracteristica": "Ferias",
        "ocorrencia": "Periodo Aquisitivo",
        "incidencia_fgts": False,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "situacao", "dobra"],
    },
    "horas extras": {
        "nome_pjecalc": "Horas Extras",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "divisor", "periodo", "cartao_ponto"],
        "reflexas_tipicas": [
            "RSR sobre Horas Extras",
            "13º s/ Horas Extras",
            "Férias + 1/3 s/ Horas Extras",
        ],
    },
    "adicional noturno": {
        "nome_pjecalc": "Adicional Noturno",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "periodo"],
        "reflexas_tipicas": [
            "RSR sobre Adicional Noturno",
            "13º s/ Adicional Noturno",
            "Férias + 1/3 s/ Adicional Noturno",
        ],
    },
    "adicional de insalubridade": {
        "nome_pjecalc": "Adicional de Insalubridade",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "base_calculo", "periodo"],
    },
    "adicional de periculosidade": {
        "nome_pjecalc": "Adicional de Periculosidade",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "multa art 477": {
        "nome_pjecalc": "Multa Art. 477 CLT",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["maior_remuneracao"],
    },
    "multa art 467": {
        "nome_pjecalc": "Multa Art. 467 CLT",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": [],
    },
    "vale transporte": {
        "nome_pjecalc": "Vale Transporte",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["linhas_onibus", "desconto_6"],
    },
    "salario familia": {
        "nome_pjecalc": "Salário-Família",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["num_dependentes"],
    },
    "dano moral": {
        "nome_pjecalc": "Indenização por Dano Moral",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "pagina_pjecalc": "Multas e Indenizações",
        "campos_criticos": ["valor_informado"],
    },
    "dano material": {
        "nome_pjecalc": "Indenização por Dano Material",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "pagina_pjecalc": "Multas e Indenizações",
        "campos_criticos": ["valor_informado"],
    },
}

# ── Tabela normalizada para lookup robusto ────────────────────────────────────
# _normalizar_chave() remove preposições ("de", "do", "da"), mas as chaves acima
# contêm essas preposições. Sem normalização, "saldo salario" (normalizado da
# sentença) não encontra a chave "saldo de salario". Solução: manter ambas formas.
_VERBAS_NORMALIZADAS: dict[str, dict[str, Any]] = {}
for _k, _v in VERBAS_PREDEFINIDAS.items():
    _VERBAS_NORMALIZADAS[_k] = _v  # chave original
    import unicodedata as _ud
    _norm = _ud.normalize("NFD", _k.lower())
    _norm = "".join(c for c in _norm if _ud.category(c) != "Mn")
    _norm = _norm.replace("º", "").replace("°", "").replace(".", "")
    for _stop in [" da ", " de ", " do ", " das ", " dos ", " a ", " o "]:
        _norm = _norm.replace(_stop, " ")
    _norm = _norm.strip()
    if _norm != _k:
        _VERBAS_NORMALIZADAS[_norm] = _v
del _k, _v, _norm, _ud


# Mapeamento de reflexas típicas (Manual, Seção 3.4)
REFLEXAS_TIPICAS: dict[str, list[dict[str, Any]]] = {
    "Horas Extras": [
        {
            "nome": "RSR sobre Horas Extras",
            "comportamento_base": "Média pelo Valor Absoluto",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "13º s/ Horas Extras",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Horas Extras",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "Adicional Noturno": [
        {
            "nome": "RSR sobre Adicional Noturno",
            "comportamento_base": "Média pelo Valor Absoluto",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "13º s/ Adicional Noturno",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Adicional Noturno",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "Adicional de Insalubridade": [
        {
            "nome": "13º s/ Insalubridade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Insalubridade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
}


# ── Funções públicas ──────────────────────────────────────────────────────────

def classificar_verba(verba: dict[str, Any]) -> dict[str, Any]:
    """
    Mapeia uma verba extraída da sentença para a configuração PJE-Calc.
    Prioriza o Lançamento Expresso (verbas pré-definidas).
    Para verbas não reconhecidas, usa LLM para sugestão.

    Retorna o dicionário da verba enriquecido com campos PJE-Calc.
    """
    nome = verba.get("nome_sentenca", "")
    chave = _normalizar_chave(nome)

    # Busca direta (tabela normalizada cobre ambas formas)
    config_pjec = _VERBAS_NORMALIZADAS.get(chave)

    # Busca por similaridade (substrings)
    if not config_pjec:
        config_pjec = _buscar_por_similaridade(chave)

    if config_pjec:
        verba_mapeada = {**verba, **config_pjec}
        verba_mapeada["lancamento"] = "Expresso"
        verba_mapeada["mapeada"] = True
        verba_mapeada["confianca_mapeamento"] = 1.0
        # Sugerir reflexas típicas se aplicável
        reflexas = REFLEXAS_TIPICAS.get(config_pjec["nome_pjecalc"], [])
        verba_mapeada["reflexas_sugeridas"] = reflexas
    else:
        # Tentar via LLM
        verba_mapeada = _classificar_via_llm(verba)
        verba_mapeada["lancamento"] = "Manual"
        verba_mapeada["mapeada"] = False

    return verba_mapeada


def mapear_para_pjecalc(verbas: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Processa todas as verbas e retorna o mapa completo:
    {
        "predefinidas": [...],   # Lançamento Expresso
        "personalizadas": [...], # Lançamento Manual
        "nao_reconhecidas": [...],
        "reflexas_sugeridas": [...],
    }
    Otimização: verbas não reconhecidas são classificadas em UMA única chamada
    ao Claude (em lote), evitando N chamadas sequenciais.
    """
    predefinidas: list[dict] = []
    pendentes_llm: list[dict] = []   # verbas que precisam de classificação LLM
    reflexas_acumuladas: list[dict] = []

    # Passagem 1: classificar via dicionário (instantâneo)
    for verba in verbas:
        nome = verba.get("nome_sentenca", "")
        chave = _normalizar_chave(nome)
        config_pjec = _VERBAS_NORMALIZADAS.get(chave) or _buscar_por_similaridade(chave)
        if config_pjec:
            resultado = {**verba, **config_pjec}
            resultado["lancamento"] = "Expresso"
            resultado["mapeada"] = True
            resultado["confianca_mapeamento"] = 1.0
            resultado["reflexas_sugeridas"] = REFLEXAS_TIPICAS.get(config_pjec["nome_pjecalc"], [])
            predefinidas.append(resultado)
            reflexas_acumuladas.extend(resultado["reflexas_sugeridas"])
        else:
            pendentes_llm.append(verba)

    # Passagem 2: classificar não reconhecidas em UMA chamada LLM
    personalizadas: list[dict] = []
    nao_reconhecidas: list[dict] = []
    if pendentes_llm:
        classificadas = _classificar_lote_via_llm(pendentes_llm)
        for resultado in classificadas:
            resultado["lancamento"] = "Manual"
            resultado["mapeada"] = False
            if resultado.get("sugestao_llm"):
                personalizadas.append(resultado)
            else:
                nao_reconhecidas.append(resultado)

    # Deduplicar reflexas
    nomes_reflexas_vistos: set[str] = set()
    reflexas_unicas = []
    for r in reflexas_acumuladas:
        if r["nome"] not in nomes_reflexas_vistos:
            nomes_reflexas_vistos.add(r["nome"])
            reflexas_unicas.append(r)

    return {
        "predefinidas": predefinidas,
        "personalizadas": personalizadas,
        "nao_reconhecidas": nao_reconhecidas,
        "reflexas_sugeridas": reflexas_unicas,
    }


# ── Funções auxiliares ────────────────────────────────────────────────────────

def _normalizar_chave(nome: str) -> str:
    """Normaliza o nome da verba para busca no dicionário."""
    import unicodedata
    nome = unicodedata.normalize("NFD", nome.lower())
    nome = "".join(c for c in nome if unicodedata.category(c) != "Mn")
    nome = nome.replace("º", "").replace("°", "").replace(".", "")
    # Remover artigos e preposições irrelevantes
    for stop in [" da ", " de ", " do ", " das ", " dos ", " a ", " o "]:
        nome = nome.replace(stop, " ")
    return nome.strip()


def _buscar_por_similaridade(chave: str) -> dict[str, Any] | None:
    """Busca por similaridade de string (SequenceMatcher) nas verbas predefinidas."""
    from difflib import SequenceMatcher

    melhor_match: dict[str, Any] | None = None
    melhor_score = 0.0
    segundo_score = 0.0

    for chave_ref, config in _VERBAS_NORMALIZADAS.items():
        # Prefixo exato (ex: "ferias proporcionais" casa com "ferias proporcionais 1/3")
        if chave_ref.startswith(chave) or chave.startswith(chave_ref):
            score = 0.95
        else:
            score = SequenceMatcher(None, chave, chave_ref).ratio()

        if score > melhor_score:
            segundo_score = melhor_score
            melhor_score = score
            melhor_match = config
        elif score > segundo_score:
            segundo_score = score

    # Exigir alta similaridade E diferença clara do segundo candidato (sem ambiguidade)
    if melhor_score >= 0.75 and (melhor_score - segundo_score) >= 0.10:
        return melhor_match
    return None


def _classificar_lote_via_llm(verbas_nao_reconhecidas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Classifica todas as verbas não reconhecidas em UMA única chamada ao Claude.
    Evita N chamadas sequenciais (uma por verba) que causam lentidão excessiva.
    """
    if not verbas_nao_reconhecidas:
        return []

    if not ANTHROPIC_API_KEY:
        for v in verbas_nao_reconhecidas:
            v["sugestao_llm"] = None
            v["nao_reconhecida"] = True
        return verbas_nao_reconhecidas

    import json as _json, re as _re

    # Montar lista de verbas para o prompt
    itens = []
    for i, v in enumerate(verbas_nao_reconhecidas):
        itens.append(
            f'{i}. Nome: "{v.get("nome_sentenca", "")}" | '
            f'Texto: "{v.get("texto_original", "")[:200]}"'
        )
    lista_verbas = "\n".join(itens)

    prompt = f"""Você é especialista em PJE-Calc (cálculo trabalhista).
Classifique as verbas abaixo extraídas de uma sentença trabalhista.
Responda APENAS com um array JSON com {len(verbas_nao_reconhecidas)} objetos (um por verba, na mesma ordem):

{lista_verbas}

Schema de cada objeto:
{{
  "nome_pjecalc": "nome a usar no campo Nome",
  "caracteristica": "Comum | 13o Salario | Aviso Previo | Ferias",
  "ocorrencia": "Mensal | Dezembro | Periodo Aquisitivo | Desligamento",
  "incidencia_fgts": true/false,
  "incidencia_inss": true/false,
  "incidencia_ir": true/false,
  "tipo": "Principal | Reflexa",
  "compor_principal": true/false,
  "pagina_pjecalc": "Verbas | Multas e Indenizacoes",
  "confianca": 0.0-1.0,
  "justificativa": "breve explicação"
}}

Responda SOMENTE com o array JSON, sem markdown."""

    try:
        cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0)
        resposta = cliente.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024 * len(verbas_nao_reconhecidas),
            temperature=CLAUDE_EXTRACTION_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        conteudo = resposta.content[0].text.strip()
        conteudo = _re.sub(r"^```(?:json)?\s*", "", conteudo)
        conteudo = _re.sub(r"\s*```\s*$", "", conteudo)
        sugestoes = _json.loads(conteudo)
        if not isinstance(sugestoes, list):
            raise ValueError("Resposta não é uma lista")
        for i, v in enumerate(verbas_nao_reconhecidas):
            if i < len(sugestoes) and isinstance(sugestoes[i], dict):
                v["sugestao_llm"] = sugestoes[i]
                v.update(sugestoes[i])
            else:
                v["sugestao_llm"] = None
                v["nao_reconhecida"] = True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Classificação em lote falhou: {e}")
        for v in verbas_nao_reconhecidas:
            v["sugestao_llm"] = None
            v["nao_reconhecida"] = True

    return verbas_nao_reconhecidas
