# modules/extraction.py — Módulo de Extração Jurídica (NLP + regex + LLM)
# Manual Técnico PJE-Calc, Seção 2 e 3

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_EXTRACTION_TEMPERATURE,
    CLAUDE_MAX_TOKENS,
    CONFIDENCE_THRESHOLD_AUTO,
)
from modules.ingestion import normalizar_valor, normalizar_data, segmentar_sentenca


# ── Prompt principal para o Claude ───────────────────────────────────────────

_SYSTEM_PROMPT = """Você é um assistente especializado em Direito do Trabalho brasileiro.
Sua tarefa é extrair informações estruturadas de sentenças trabalhistas para preenchimento
do sistema PJE-Calc. Responda SOMENTE com JSON válido, sem texto adicional.
Siga rigorosamente o schema solicitado. Use null para campos não encontrados.
Para datas, use o formato DD/MM/AAAA. Para valores monetários, use float sem símbolo.
Para percentuais, use float (ex: 50% = 0.5). Inclua sempre um score de confiança
entre 0.0 e 1.0 para cada campo extraído."""

_SYSTEM_PROMPT_RELATORIO = """Você é um assistente especializado em Direito do Trabalho brasileiro.
Você receberá um relatório já estruturado e analisado de uma sentença trabalhista,
produzido por um sistema especializado de pré-processamento.
Sua tarefa é converter esse relatório diretamente para o schema JSON do PJE-Calc.
O relatório já identificou e classificou todas as verbas, parâmetros e reflexos —
preserve essa classificação sem alterações. Responda SOMENTE com JSON válido, sem texto adicional.
Use null para campos não encontrados no relatório.
Para datas, use DD/MM/AAAA. Para valores monetários, use float sem símbolo.
Para percentuais, use float (ex: 50% = 0.5, 10% = 0.1, 8% = 0.08).
Use confianca=0.95 para campos explicitamente presentes no relatório."""

_RELATORIO_PROMPT = """Converta o relatório estruturado abaixo diretamente para o schema JSON do PJE-Calc.

=== RELATÓRIO ESTRUTURADO DA SENTENÇA ===
{texto}

=== SCHEMA JSON ESPERADO ===
{{
  "processo": {{
    "numero": "string | null",
    "reclamante": "string | null",
    "reclamado": "string | null",
    "estado": "UF 2 letras | null",
    "municipio": "string | null",
    "vara": "string | null",
    "confianca": 0.0-1.0
  }},
  "contrato": {{
    "admissao": "DD/MM/AAAA | null",
    "demissao": "DD/MM/AAAA | null",
    "tipo_rescisao": "sem_justa_causa | justa_causa | pedido_demissao | distrato | morte | null",
    "regime": "Tempo Integral | Tempo Parcial | Trabalho Intermitente | null",
    "carga_horaria": "número inteiro (horas/mês) | null",
    "maior_remuneracao": "float | null",
    "ultima_remuneracao": "float | null",
    "ajuizamento": "DD/MM/AAAA | null",
    "confianca": 0.0-1.0
  }},
  "prescricao": {{
    "quinquenal": "true | false | null",
    "fgts": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "aviso_previo": {{
    "tipo": "Calculado | Informado | Nao Apurar | null",
    "prazo_dias": "número inteiro | null",
    "projetar": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "verbas_deferidas": [
    {{
      "nome_sentenca": "string — nome exato como aparece no relatório",
      "texto_original": "trecho do relatório que descreve esta verba",
      "tipo": "Principal | Reflexa | null",
      "caracteristica": "Comum | 13o Salario | Aviso Previo | Ferias | null",
      "ocorrencia": "Mensal | Dezembro | Periodo Aquisitivo | Desligamento | null",
      "periodo_inicio": "DD/MM/AAAA | null",
      "periodo_fim": "DD/MM/AAAA | null",
      "percentual": "float | null",
      "base_calculo": "Maior Remuneracao | Historico Salarial | Salario Minimo | Piso Salarial | Verbas | null",
      "valor_informado": "float | null",
      "incidencia_fgts": "true | false | null",
      "incidencia_inss": "true | false | null",
      "incidencia_ir": "true | false | null",
      "verba_principal_ref": "nome da verba principal se reflexa | null",
      "confianca": 0.0-1.0
    }}
  ],
  "fgts": {{
    "aliquota": "float (ex: 0.08) | null",
    "multa_40": "true | false | null",
    "multa_467": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "honorarios": {{
    "percentual": "float | null",
    "valor_fixo": "float | null",
    "parte_devedora": "Reclamado | Reclamante | Ambos | null",
    "periciais": "float | null",
    "confianca": 0.0-1.0
  }},
  "correcao_juros": {{
    "indice_correcao": "string | null",
    "base_juros": "Verbas | Credito Total | null",
    "taxa_juros": "Juros Padrao | Selic | null",
    "jam_fgts": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "contribuicao_social": {{
    "responsabilidade": "Empregador | Empregado | Ambos | null",
    "lei_11941": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "imposto_renda": {{
    "apurar": "true | false",
    "meses_tributaveis": "número inteiro | null",
    "dependentes": "número inteiro | null",
    "confianca": 0.0-1.0
  }},
  "campos_ausentes": ["lista de campos OBRIGATÓRIOS não encontrados — ver nota abaixo"],
  "alertas": ["lista de avisos relevantes extraídos do relatório"]
}}

IMPORTANTE:
- Verbas marcadas como 🔵 no relatório são CONDENAÇÕES PRINCIPAIS (tipo: "Principal")
- Verbas marcadas como 🔸 são REFLEXOS (tipo: "Reflexa")
- Preservar exatamente a classificação de principal/reflexo do relatório
- Para verbas reflexas, preencher "verba_principal_ref" com o nome da verba principal correspondente
- Usar confianca=0.95 para todos os campos presentes no relatório
- CAMPOS OPCIONAIS — NÃO incluir em campos_ausentes se não mencionados no relatório:
  prescricao.quinquenal, prescricao.fgts, honorarios.periciais, contrato.carga_horaria,
  imposto_renda.dependentes, imposto_renda.meses_tributaveis, aviso_previo.prazo_dias,
  contribuicao_social.lei_11941, fgts.multa_467
- Só incluir em campos_ausentes campos OBRIGATÓRIOS que estão faltando:
  processo.numero, processo.reclamante, processo.reclamado, processo.estado,
  contrato.admissao, contrato.ajuizamento

Retorne APENAS o JSON, sem markdown, sem explicações."""

_EXTRACTION_PROMPT = """Analise a sentença trabalhista abaixo e extraia as informações
no formato JSON especificado.

=== SENTENÇA ===
{texto}

=== SCHEMA ESPERADO ===
{{
  "processo": {{
    "numero": "string | null",
    "reclamante": "string | null",
    "reclamado": "string | null",
    "estado": "UF 2 letras | null",
    "municipio": "string | null",
    "vara": "string | null",
    "confianca": 0.0-1.0
  }},
  "contrato": {{
    "admissao": "DD/MM/AAAA | null",
    "demissao": "DD/MM/AAAA | null",
    "tipo_rescisao": "sem_justa_causa | justa_causa | pedido_demissao | distrato | morte | null",
    "regime": "Tempo Integral | Tempo Parcial | Trabalho Intermitente | null",
    "carga_horaria": "número inteiro (horas/mês) | null",
    "maior_remuneracao": "float | null",
    "ultima_remuneracao": "float | null",
    "ajuizamento": "DD/MM/AAAA | null",
    "confianca": 0.0-1.0
  }},
  "prescricao": {{
    "quinquenal": "true | false | null",
    "fgts": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "aviso_previo": {{
    "tipo": "Calculado | Informado | Nao Apurar | null",
    "prazo_dias": "número inteiro | null",
    "projetar": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "verbas_deferidas": [
    {{
      "nome_sentenca": "string — nome exato como aparece na sentença",
      "texto_original": "trecho exato da sentença que originou esta verba",
      "tipo": "Principal | Reflexa | null",
      "caracteristica": "Comum | 13o Salario | Aviso Previo | Ferias | null",
      "ocorrencia": "Mensal | Dezembro | Periodo Aquisitivo | Desligamento | null",
      "periodo_inicio": "DD/MM/AAAA | null",
      "periodo_fim": "DD/MM/AAAA | null",
      "percentual": "float | null",
      "base_calculo": "Maior Remuneracao | Historico Salarial | Salario Minimo | Piso Salarial | Verbas | null",
      "valor_informado": "float | null",
      "incidencia_fgts": "true | false | null",
      "incidencia_inss": "true | false | null",
      "incidencia_ir": "true | false | null",
      "verba_principal_ref": "nome da verba principal se reflexa | null",
      "confianca": 0.0-1.0
    }}
  ],
  "fgts": {{
    "aliquota": "float (ex: 0.08) | null",
    "multa_40": "true | false | null",
    "multa_467": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "honorarios": {{
    "percentual": "float | null",
    "valor_fixo": "float | null",
    "parte_devedora": "Reclamado | Reclamante | Ambos | null",
    "periciais": "float | null",
    "confianca": 0.0-1.0
  }},
  "correcao_juros": {{
    "indice_correcao": "string — ex: Tabela JT Unica Mensal | IPCA-E | Selic | TRCT | null",
    "base_juros": "Verbas | Credito Total | null",
    "taxa_juros": "Juros Padrao | Selic | null",
    "jam_fgts": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "contribuicao_social": {{
    "responsabilidade": "Empregador | Empregado | Ambos | null",
    "lei_11941": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "imposto_renda": {{
    "apurar": "true | false",
    "meses_tributaveis": "número inteiro | null",
    "dependentes": "número inteiro | null",
    "confianca": 0.0-1.0
  }},
  "campos_ausentes": ["lista de campos OBRIGATÓRIOS não encontrados — ver nota abaixo"],
  "alertas": ["lista de avisos para o operador"]
}}

NOTA SOBRE campos_ausentes:
- CAMPOS OPCIONAIS — NÃO incluir em campos_ausentes se não mencionados na sentença:
  prescricao.quinquenal, prescricao.fgts, honorarios.periciais, contrato.carga_horaria,
  imposto_renda.dependentes, imposto_renda.meses_tributaveis, aviso_previo.prazo_dias,
  contribuicao_social.lei_11941, fgts.multa_467
- Só incluir em campos_ausentes campos OBRIGATÓRIOS que estão faltando:
  processo.numero, processo.reclamante, processo.reclamado, processo.estado,
  contrato.admissao, contrato.ajuizamento

Retorne APENAS o JSON, sem markdown, sem explicações."""


# ── Função principal ──────────────────────────────────────────────────────────

def extrair_dados_sentenca(
    texto: str,
    sessao_id: str | None = None,
    extras: list[dict] | None = None,
    is_relatorio: bool = False,
) -> dict[str, Any]:
    """
    Extrai todos os dados necessários para preenchimento do PJE-Calc.

    Dois modos:
    - is_relatorio=False (padrão): extração a partir de sentença bruta
        Fase 1: regex → Fase 2: LLM → Fase 3: merge → Fase 4: validação
    - is_relatorio=True: o texto já é um relatório estruturado (ex: saída do Projeto Claude)
        Pula regex; usa prompt especializado de mapeamento direto ao schema

    Parâmetros:
        extras: documentos complementares {"tipo", "conteudo", "contexto", "mime_type"}
        is_relatorio: True se o texto for um relatório pré-estruturado
    """
    sessao_id = sessao_id or str(uuid.uuid4())

    if is_relatorio:
        return _extrair_de_relatorio_estruturado(texto, sessao_id)

    # Segmentar sentença para focar no dispositivo
    blocos = segmentar_sentenca(texto)
    texto_principal = blocos.get("dispositivo") or texto
    texto_completo = texto

    # Fase 1: extração regex pré-processada
    dados_regex = _extrair_via_regex(texto_completo)

    # Fase 2: extração via LLM (Claude) — com extras
    dados_llm = _extrair_via_llm(texto_principal[:12000], extras=extras)

    # Fase 3: merge (LLM prevalece; regex preenche onde LLM retornou null)
    dados = _merge_extracao(dados_regex, dados_llm)

    # Fase 4: validação e identificação de campos ausentes
    dados = _validar_e_completar(dados)

    return dados


def _extrair_de_relatorio_estruturado(
    texto_relatorio: str,
    sessao_id: str,
) -> dict[str, Any]:
    """
    Converte um relatório já estruturado (ex: saída do Projeto Claude) diretamente
    ao schema JSON do PJE-Calc, sem reprocessar a sentença bruta.

    O relatório já identificou verbas, parâmetros e reflexos — o LLM apenas mapeia
    ao schema, preservando a classificação original.
    """
    if not ANTHROPIC_API_KEY:
        return _estrutura_vazia_com_regex({})

    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        resposta = cliente.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            temperature=0.0,  # mapeamento determinístico
            system=_SYSTEM_PROMPT_RELATORIO,
            messages=[{
                "role": "user",
                "content": _RELATORIO_PROMPT.format(texto=texto_relatorio[:20000]),
            }],
        )
        conteudo = resposta.content[0].text.strip()
        conteudo = re.sub(r"^```(?:json)?\s*", "", conteudo)
        conteudo = re.sub(r"\s*```$", "", conteudo)
        dados = json.loads(conteudo)
        dados = _validar_e_completar(dados)
        if "alertas" not in dados:
            dados["alertas"] = []
        dados["alertas"].insert(0, "Dados extraídos de relatório estruturado (alta confiança).")
        return dados

    except (json.JSONDecodeError, anthropic.APIError) as e:
        return {"_erro_llm": str(e), "alertas": [f"Falha ao mapear relatório: {e}"]}


# ── Extração via Regex ────────────────────────────────────────────────────────

def _extrair_via_regex(texto: str) -> dict[str, Any]:
    """Extração rápida de padrões comuns por regex."""
    resultado: dict[str, Any] = {}

    # Número do processo
    m = re.search(
        r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", texto
    )
    resultado["numero_processo"] = m.group(0) if m else None

    # Datas de admissão e demissão
    resultado["admissao"] = _buscar_data_contexto(
        texto, r"(?i)(admitido|admissão|admis\w+em|data de admiss)"
    )
    resultado["demissao"] = _buscar_data_contexto(
        texto, r"(?i)(demiti|dispensado|demiss[aã]o|rescis[aã]o|data de demiss)"
    )
    resultado["ajuizamento"] = _buscar_data_contexto(
        texto, r"(?i)(ajuizamento|proposta em|distribu[íi]da em|protocol)"
    )

    # Reclamante / Reclamado
    m = re.search(r"(?i)reclamante[:\s]+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÈÌÒÙÇ][^\n,]+)", texto)
    resultado["reclamante"] = m.group(1).strip() if m else None

    m = re.search(r"(?i)reclamad[oa][:\s]+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÈÌÒÙÇ][^\n,]+)", texto)
    resultado["reclamado"] = m.group(1).strip() if m else None

    # Estado (UF)
    m = re.search(
        r"(?i)vara\s+do\s+trabalho\s+(?:de\s+)?[^-\n]+-\s*([A-Z]{2})", texto
    )
    resultado["estado"] = m.group(1) if m else None

    # FGTS alíquota
    m = re.search(r"(?i)fgts\s*[,à]?\s*[aà]\s*alíquota\s+de?\s*(\d+(?:,\d+)?)\s*%", texto)
    if m:
        resultado["aliquota_fgts"] = float(m.group(1).replace(",", ".")) / 100
    else:
        resultado["aliquota_fgts"] = None

    # Multa 40%
    resultado["multa_40"] = bool(
        re.search(r"(?i)(multa\s+(?:de\s+)?40\s*%|art\.?\s*18.*§\s*1)", texto)
    )

    # Honorários
    m = re.search(
        r"(?i)honorários\s+advocatícios[^.]*?(\d+(?:,\d+)?)\s*%", texto
    )
    resultado["honorarios_percentual"] = (
        float(m.group(1).replace(",", ".")) / 100 if m else None
    )

    return resultado


def _buscar_data_contexto(texto: str, padrao_contexto: str) -> str | None:
    """Busca uma data próxima a um padrão de contexto."""
    for m in re.finditer(padrao_contexto, texto):
        trecho = texto[m.start(): m.start() + 150]
        data_m = re.search(
            r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})", trecho
        )
        if data_m:
            return normalizar_data(data_m.group(1))
    return None


# ── Extração via LLM ──────────────────────────────────────────────────────────

def _extrair_via_llm(
    texto: str,
    extras: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Usa a Claude API para extração profunda de parâmetros jurídicos.

    Documentos extras são incluídos no contexto:
    - "texto": adicionados ao prompt como seções de contexto
    - "imagem": enviados como blocos de imagem (visão multimodal)
    """
    if not ANTHROPIC_API_KEY:
        return {}

    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        # Montar blocos de conteúdo da mensagem
        content_blocks: list[dict] = []

        # Imagens vêm primeiro (melhor contextualização pelo Claude)
        secoes_extras: list[str] = []
        for i, extra in enumerate(extras or [], start=1):
            ctx = extra.get("contexto", "").strip()
            ctx_str = f" [{ctx}]" if ctx else ""

            if extra.get("tipo") == "imagem":
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": extra.get("mime_type", "image/jpeg"),
                        "data": extra["conteudo"],
                    },
                })
                secoes_extras.append(
                    f"=== DOCUMENTO ADICIONAL {i}{ctx_str} === (imagem enviada acima)"
                )
            elif extra.get("tipo") == "texto" and extra.get("conteudo"):
                trecho = extra["conteudo"][:4000]  # limite por documento
                secoes_extras.append(
                    f"=== DOCUMENTO ADICIONAL {i}{ctx_str} ===\n{trecho}"
                )

        # Prompt principal da sentença
        prompt_sentenca = _EXTRACTION_PROMPT.format(texto=texto)

        # Acrescentar extras ao prompt textual
        if secoes_extras:
            prompt_sentenca += (
                "\n\n" + "\n\n".join(secoes_extras) +
                "\n\nOs documentos adicionais acima complementam a sentença. "
                "Use-os para preencher ou corrigir campos ausentes ou com baixa confiança."
            )

        content_blocks.append({"type": "text", "text": prompt_sentenca})

        resposta = cliente.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            temperature=CLAUDE_EXTRACTION_TEMPERATURE,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content_blocks}],
        )
        conteudo = resposta.content[0].text.strip()

        # Remover eventuais blocos markdown
        conteudo = re.sub(r"^```(?:json)?\s*", "", conteudo)
        conteudo = re.sub(r"\s*```$", "", conteudo)

        return json.loads(conteudo)

    except (json.JSONDecodeError, anthropic.APIError) as e:
        return {"_erro_llm": str(e), "alertas": [f"Falha na extração via IA: {e}"]}


# ── Merge e Validação ─────────────────────────────────────────────────────────

def _merge_extracao(
    regex: dict[str, Any], llm: dict[str, Any]
) -> dict[str, Any]:
    """
    LLM prevalece; regex preenche campos que o LLM retornou null.
    """
    if not llm:
        return _estrutura_vazia_com_regex(regex)

    # Preencher processo
    proc = llm.get("processo", {})
    if not proc.get("numero"):
        proc["numero"] = regex.get("numero_processo")
    if not proc.get("reclamante"):
        proc["reclamante"] = regex.get("reclamante")
    if not proc.get("reclamado"):
        proc["reclamado"] = regex.get("reclamado")
    if not proc.get("estado"):
        proc["estado"] = regex.get("estado")
    llm["processo"] = proc

    # Preencher contrato
    cont = llm.get("contrato", {})
    if not cont.get("admissao"):
        cont["admissao"] = regex.get("admissao")
    if not cont.get("demissao"):
        cont["demissao"] = regex.get("demissao")
    if not cont.get("ajuizamento"):
        cont["ajuizamento"] = regex.get("ajuizamento")
    llm["contrato"] = cont

    # FGTS
    fgts = llm.get("fgts", {})
    if fgts.get("aliquota") is None and regex.get("aliquota_fgts") is not None:
        fgts["aliquota"] = regex["aliquota_fgts"]
    if fgts.get("multa_40") is None:
        fgts["multa_40"] = regex.get("multa_40")
    llm["fgts"] = fgts

    # Honorários
    hon = llm.get("honorarios", {})
    if hon.get("percentual") is None and regex.get("honorarios_percentual") is not None:
        hon["percentual"] = regex["honorarios_percentual"]
    llm["honorarios"] = hon

    return llm


def _estrutura_vazia_com_regex(regex: dict[str, Any]) -> dict[str, Any]:
    """Retorna estrutura mínima preenchida com dados do regex quando LLM falha."""
    return {
        "processo": {
            "numero": regex.get("numero_processo"),
            "reclamante": regex.get("reclamante"),
            "reclamado": regex.get("reclamado"),
            "estado": regex.get("estado"),
            "municipio": None,
            "vara": None,
            "confianca": 0.5,
        },
        "contrato": {
            "admissao": regex.get("admissao"),
            "demissao": regex.get("demissao"),
            "ajuizamento": regex.get("ajuizamento"),
            "tipo_rescisao": None,
            "regime": None,
            "carga_horaria": None,
            "maior_remuneracao": None,
            "ultima_remuneracao": None,
            "confianca": 0.5,
        },
        "prescricao": {"quinquenal": None, "fgts": None, "confianca": 0.5},
        "aviso_previo": {"tipo": None, "prazo_dias": None, "projetar": None, "confianca": 0.5},
        "verbas_deferidas": [],
        "fgts": {
            "aliquota": regex.get("aliquota_fgts"),
            "multa_40": regex.get("multa_40"),
            "multa_467": None,
            "confianca": 0.5,
        },
        "honorarios": {
            "percentual": regex.get("honorarios_percentual"),
            "valor_fixo": None,
            "parte_devedora": None,
            "periciais": None,
            "confianca": 0.5,
        },
        "correcao_juros": {
            "indice_correcao": None,
            "base_juros": None,
            "taxa_juros": None,
            "jam_fgts": None,
            "confianca": 0.5,
        },
        "contribuicao_social": {
            "responsabilidade": None,
            "lei_11941": None,
            "confianca": 0.5,
        },
        "imposto_renda": {"apurar": False, "meses_tributaveis": None, "dependentes": None, "confianca": 0.5},
        "campos_ausentes": [],
        "alertas": ["Extração via IA indisponível — dados obtidos somente via regex"],
    }


# ── Validação de campos obrigatórios ──────────────────────────────────────────

_CAMPOS_OBRIGATORIOS = [
    ("contrato", "admissao"),
    ("contrato", "ajuizamento"),
    ("processo", "reclamante"),
    ("processo", "reclamado"),
    ("processo", "estado"),
    ("processo", "municipio"),
]

_CAMPOS_CONDICIONAIS = [
    ("contrato", "demissao"),       # ou data_final obrigatória
    ("contrato", "maior_remuneracao"),  # necessária para Aviso Prévio e Multa 477
]

# Campos que NÃO devem aparecer em campos_ausentes se não mencionados na sentença
_CAMPOS_OPCIONAIS = {
    "prescricao.quinquenal",
    "prescricao.fgts",
    "honorarios.periciais",
    "contrato.carga_horaria",
    "imposto_renda.dependentes",
    "imposto_renda.meses_tributaveis",
    "aviso_previo.prazo_dias",
    "contribuicao_social.lei_11941",
    "fgts.multa_467",
    "processo.municipio",   # útil mas não bloqueia cálculo
    "processo.vara",
}


def _validar_e_completar(dados: dict[str, Any]) -> dict[str, Any]:
    """
    Identifica campos obrigatórios ausentes e campos com baixa confiança.
    Preenche 'campos_ausentes' e 'alertas'.
    """
    campos_ausentes = dados.get("campos_ausentes", [])
    alertas = dados.get("alertas", [])

    for secao, campo in _CAMPOS_OBRIGATORIOS:
        valor = dados.get(secao, {}).get(campo)
        if not valor:
            campos_ausentes.append(f"{secao}.{campo}")

    # Verificar confiança abaixo do limiar
    for secao in ["processo", "contrato", "fgts", "honorarios", "correcao_juros"]:
        conf = dados.get(secao, {}).get("confianca", 1.0)
        if conf is not None and conf < CONFIDENCE_THRESHOLD_AUTO:
            alertas.append(
                f"Seção '{secao}': confiança baixa ({conf:.0%}). Verificar antes de prosseguir."
            )

    # Verificar verbas com confiança baixa
    for i, verba in enumerate(dados.get("verbas_deferidas", [])):
        conf = verba.get("confianca", 1.0)
        if conf < CONFIDENCE_THRESHOLD_AUTO:
            alertas.append(
                f"Verba [{i+1}] '{verba.get('nome_sentenca', '?')}': "
                f"confiança baixa ({conf:.0%}). Confirme o preenchimento."
            )

    # Remover campos opcionais que o LLM pode ter incluído indevidamente
    campos_ausentes = [c for c in campos_ausentes if c not in _CAMPOS_OPCIONAIS]

    dados["campos_ausentes"] = list(set(campos_ausentes))
    dados["alertas"] = alertas

    return dados
