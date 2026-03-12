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

    # Busca direta
    config_pjec = VERBAS_PREDEFINIDAS.get(chave)

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
    """
    predefinidas: list[dict] = []
    personalizadas: list[dict] = []
    nao_reconhecidas: list[dict] = []
    reflexas_acumuladas: list[dict] = []

    for verba in verbas:
        resultado = classificar_verba(verba)

        if resultado.get("mapeada"):
            predefinidas.append(resultado)
            reflexas_acumuladas.extend(resultado.get("reflexas_sugeridas", []))
        elif resultado.get("sugestao_llm"):
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
    """Busca por substring nas chaves do dicionário de verbas."""
    # Palavras-chave relevantes presentes na chave buscada
    palavras = chave.split()

    melhor_match: dict[str, Any] | None = None
    melhor_score = 0

    for chave_ref, config in VERBAS_PREDEFINIDAS.items():
        palavras_ref = set(chave_ref.split())
        palavras_busca = set(palavras)
        intersecao = palavras_ref & palavras_busca
        if not intersecao:
            continue
        score = len(intersecao) / max(len(palavras_ref), len(palavras_busca))
        if score > melhor_score and score >= 0.5:
            melhor_score = score
            melhor_match = config

    return melhor_match


def _classificar_via_llm(verba: dict[str, Any]) -> dict[str, Any]:
    """
    Usa Claude para sugerir classificação de verba não reconhecida.
    Retorna a verba com campos 'sugestao_llm' e configuração sugerida.
    """
    if not ANTHROPIC_API_KEY:
        verba["sugestao_llm"] = None
        verba["nao_reconhecida"] = True
        return verba

    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Você é um especialista em PJE-Calc (sistema de cálculo trabalhista).
A seguinte verba foi extraída de uma sentença trabalhista e não foi reconhecida automaticamente:

Nome: {verba.get('nome_sentenca')}
Texto original: {verba.get('texto_original', '')[:300]}

Sugira como classificar esta verba no PJE-Calc com o seguinte JSON:
{{
  "nome_pjecalc": "nome a usar no campo Nome da verba",
  "caracteristica": "Comum | 13o Salario | Aviso Previo | Ferias",
  "ocorrencia": "Mensal | Dezembro | Periodo Aquisitivo | Desligamento",
  "incidencia_fgts": true/false,
  "incidencia_inss": true/false,
  "incidencia_ir": true/false,
  "tipo": "Principal | Reflexa",
  "compor_principal": true/false,
  "pagina_pjecalc": "Verbas | Multas e Indenizacoes",
  "assunto_cnj_sugerido": "descrição do assunto TPU mais adequado",
  "confianca": 0.0-1.0,
  "justificativa": "breve explicação"
}}
Responda APENAS com o JSON."""

    try:
        resposta = cliente.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            temperature=CLAUDE_EXTRACTION_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        import json, re
        conteudo = resposta.content[0].text.strip()
        conteudo = re.sub(r"^```(?:json)?\s*", "", conteudo)
        conteudo = re.sub(r"\s*```$", "", conteudo)
        sugestao = json.loads(conteudo)
        verba["sugestao_llm"] = sugestao
        verba.update(sugestao)
    except Exception as e:
        verba["sugestao_llm"] = None
        verba["nao_reconhecida"] = True
        verba["erro_classificacao"] = str(e)

    return verba
