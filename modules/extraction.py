# modules/extraction.py — Módulo de Extração Jurídica (NLP + regex + LLM)
# Manual Técnico PJE-Calc, Seção 2 e 3

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_EXTRACTION_TEMPERATURE,
    CLAUDE_MAX_TOKENS,
    CONFIDENCE_THRESHOLD_AUTO,
)
from modules.ingestion import normalizar_valor, normalizar_data, segmentar_sentenca


# ── Limpeza de JSON retornado pelo LLM ───────────────────────────────────────

def _limpar_e_parsear_json(texto: str) -> dict:
    """
    Tenta parsear JSON retornado pelo LLM com tolerância a erros comuns:
    - Remove blocos markdown ```json ... ```
    - Remove vírgulas antes de } ou ]  (trailing commas)
    - Extrai primeiro bloco { ... } caso haja texto em volta
    """
    # 1. Remover blocos markdown
    texto = re.sub(r"^```(?:json)?\s*", "", texto.strip(), flags=re.MULTILINE)
    texto = re.sub(r"\s*```\s*$", "", texto, flags=re.MULTILINE)
    texto = texto.strip()

    # 2. Tentar parse direto
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    # 3. Remover trailing commas  (,  seguida de espaços/newlines e } ou ])
    limpo = re.sub(r",\s*([}\]])", r"\1", texto)
    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        pass

    # 4. Extrair o maior bloco JSON da resposta
    match = re.search(r"\{.*\}", limpo, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 5. Sem recuperação possível — relançar com o texto limpo para logging
    return json.loads(limpo)  # levanta JSONDecodeError com contexto útil


# ── Prompt principal para o Claude ───────────────────────────────────────────

_SYSTEM_PROMPT = """Você é um assistente especializado em Direito do Trabalho brasileiro.
Sua tarefa é extrair informações estruturadas de sentenças trabalhistas para preenchimento
do sistema PJE-Calc. Responda SOMENTE com JSON válido, sem texto adicional.
Siga rigorosamente o schema solicitado. Use null para campos não encontrados.
Para datas, use o formato DD/MM/AAAA. Para valores monetários, use float sem símbolo.
Para percentuais, use float (ex: 50% = 0.5). Inclua sempre um score de confiança
entre 0.0 e 1.0 para cada campo extraído."""

_SYSTEM_PROMPT_RELATORIO = """Você é um especialista em Direito do Trabalho brasileiro e em conversão de dados jurídicos para o sistema PJE-Calc.
Receberá um relatório estruturado de sentença trabalhista produzido pelo sistema Calc-Machine.
Sua única tarefa é converter esse relatório para o schema JSON do PJE-Calc com máxima fidelidade.
Responda SOMENTE com JSON válido (sem markdown, sem texto extra, sem ```json).
Regras absolutas:
- Datas: DD/MM/AAAA
- Valores monetários: float sem símbolo (ex: 1518.00)
- Percentuais: float decimal (ex: 15% → 0.15; 8% → 0.08; 40% → 0.40)
- Use null para campos não encontrados
- Use confianca=0.95 para todos os campos presentes no relatório"""

_RELATORIO_PROMPT = """Converta o relatório abaixo para o schema JSON do PJE-Calc.

=== RELATÓRIO ESTRUTURADO ===
{texto}

=== GUIA DE LEITURA DO RELATÓRIO ===

**SEÇÃO 1 — INFORMAÇÕES PROCESSUAIS** → preenche "processo":
- "Processo nº:" → processo.numero (formato: NNNNNNN-DD.AAAA.J.RR.VVVV)
- "Vara/Juízo:" → processo.vara
- "Cidade/Comarca:" → processo.municipio
- "Estado:" → processo.estado (2 letras, ex: CE)
- "Reclamante:" → processo.reclamante (apenas nome, sem CPF)
- CPF do reclamante se explicitado → processo.cpf_reclamante (formato: "000.000.000-00")
- "Reclamada:" ou "Reclamado:" → processo.reclamado (apenas razão social/nome, sem CNPJ)
- CNPJ da reclamada se explicitado → processo.cnpj_reclamado (formato: "00.000.000/0000-00")
- "Data de Distribuição/Autuação:" ou "Data de Ajuizamento:" → contrato.ajuizamento

**SEÇÃO 2 — DADOS DO CONTRATO** → preenche "contrato":
- "Admissão:" → contrato.admissao (OBRIGATÓRIO)
- "Dispensa:" → contrato.demissao — use SOMENTE a data real da dispensa, NUNCA a data projetada com AP
  ("Término projetado do contrato (com AP):" é apenas informativo — NÃO usar para contrato.demissao)
- "Último Salário/Remuneração Base:" → contrato.ultima_remuneracao (valor do último mês; se múltiplos valores
  por período, usar o ÚLTIMO valor listado)
- "Maior Remuneração:" → contrato.maior_remuneracao (se não explícito, igual a ultima_remuneracao)
- "Função:" → ignorar (não há campo no schema)
- "Tipo de Dispensa:" → contrato.tipo_rescisao:
    "Sem justa causa" ou "dispensa imotivada" → "sem_justa_causa"
    "Com justa causa" → "justa_causa"
    "Pedido de demissão" → "pedido_demissao"
    "Rescisão indireta" → "sem_justa_causa" (tratada como sem justa causa no PJE-Calc)
    "Distrato" → "distrato"
- "Carga Horária:" → contrato.carga_horaria (inteiro; se não informado, não incluir em campos_ausentes)
- contrato.regime: se não explícito, inferir "Tempo Integral" para contratos padrão
- ⚠️ SE o relatório contiver uma "Nota sobre histórico salarial" indicando salários diferentes por período:
    → contrato.ultima_remuneracao = último valor do histórico (ex: R$ 1.518,00 para 2025)
    → contrato.maior_remuneracao = maior valor entre todos os períodos (ex: R$ 1.518,00)
    → Para TODAS as verbas salariais principais (diferenças, saldo, 13º, aviso prévio salarial):
      base_calculo = "Historico Salarial"
    → Incluir a nota de histórico como alerta
    → Preencher historico_salarial como lista de entradas por período

**HISTÓRICO SALARIAL DETALHADO** → preenche "historico_salarial":
Se houver tabela de evolução salarial (salários diferentes em períodos distintos):
  historico_salarial: [
    {"data_inicio": "01/01/2023", "data_fim": "31/08/2024", "valor": 1518.00},
    {"data_inicio": "01/09/2024", "data_fim": "28/02/2025", "valor": 1800.00}
  ]
Se houver apenas um salário uniforme durante todo o contrato → historico_salarial = []

**FALTAS** → preenche "faltas":
Se a sentença mencionar faltas injustificadas ou justificadas, extrair:
  faltas: [
    {"data_inicial": "DD/MM/AAAA", "data_final": "DD/MM/AAAA", "justificada": false, "descricao": ""}
  ]
Se não mencionado → faltas = []

**FÉRIAS** → preenche "ferias":
Se a sentença mencionar períodos de férias não gozadas ou situações específicas, extrair:
  ferias: [
    {"situacao": "Vencidas", "periodo_inicio": "DD/MM/AAAA", "periodo_fim": "DD/MM/AAAA",
     "abono": false, "dobra": false}
  ]
Situações: "Vencidas" | "Proporcionais" | "Gozadas"
Se não mencionado → ferias = []

**AVISO PRÉVIO** → preenche "aviso_previo":
- Se há condenação em aviso prévio indenizado calculado pela Lei 12.506/2011:
    aviso_previo.tipo = "Calculado", aviso_previo.projetar = true
- Se há número de dias explícito (ex: "33 dias"):
    aviso_previo.prazo_dias = 33 (campo opcional — não colocar em campos_ausentes)
- Se sem condenação em aviso prévio: aviso_previo.tipo = "Nao Apurar"

**SEÇÃO 3 — PARCELAS CONDENADAS** → preenche "verbas_deferidas":
- 🔵 CONDENAÇÃO PRINCIPAL N → tipo = "Principal"
- 🔸 Reflexo em [...] → tipo = "Reflexa", verba_principal_ref = nome_sentenca da verba 🔵 correspondente
- Para cada verba, extrair:
    nome_sentenca: texto do título da condenação (ex: "DIFERENÇAS SALARIAIS", "SALDO DE SALÁRIO")
    periodo_inicio / periodo_fim: de "Período:" ou "Período aquisitivo:" ou cálculo pelos parâmetros
    percentual: apenas se houver percentual explícito (ex: 1/3 = 0.3333, 40% = 0.40)
    valor_informado: apenas se houver "Valor fixado:" explícito (float)
    caracteristica:
      "13o Salario" se for 13º salário
      "Ferias" se for férias (vencidas, proporcionais)
      "Aviso Previo" se for aviso prévio
      "Comum" para demais (diferenças salariais, saldo, horas extras, adicionais, danos morais, etc.)
    ocorrencia:
      "Mensal" para verbas mensais (horas extras, adicionais, diferenças salariais mensais)
      "Dezembro" para 13º salário
      "Periodo Aquisitivo" para férias
      "Desligamento" para verbas pagas na rescisão (saldo de salário, aviso prévio, multas)
    base_calculo:
      "Historico Salarial" quando o salário varia por período (nota de histórico presente)
      "Maior Remuneracao" quando usa o maior salário fixo do contrato
      "Salario Minimo" quando explicitamente baseado no salário mínimo com valor único e fixo
      "Verbas" para reflexos (base = verba principal)
      "Piso Salarial" quando baseado em piso de categoria
    incidencia_fgts: true para parcelas salariais; false para indenizatórias (férias + 1/3, aviso prévio indenizado, danos morais, multas)
    incidencia_inss: true para parcelas salariais; false para indenizatórias
    incidencia_ir: false para parcelas indenizatórias; true para salariais tributáveis

**SEÇÃO 4 — FGTS E MULTA DE 40%** → preenche "fgts":
- "Alíquota FGTS:" → fgts.aliquota (ex: 8% → 0.08)
- "Multa de 40%: Sim" → fgts.multa_40 = true
- "Multa de 40%: Não" → fgts.multa_40 = false

**SEÇÃO 5 — MULTAS TRABALHISTAS**:
- "Multa art. 467 CLT — Deferida" → fgts.multa_467 = true (campo opcional)
- "Multa art. 467 CLT — Indeferida" → fgts.multa_467 = false

**SEÇÃO 6 — HONORÁRIOS ADVOCATÍCIOS** → preenche "honorarios":
- "Percentual total fixado:" → honorarios.percentual (ex: 15% → 0.15)
- "Sucumbência integral da reclamada" → honorarios.parte_devedora = "Reclamado"
- "Sucumbência recíproca" → honorarios.parte_devedora = "Ambos"
- "Sucumbência integral da reclamante" → honorarios.parte_devedora = "Reclamante"
- Honorários periciais: honorarios.periciais (campo opcional)

**SEÇÃO 7 — CORREÇÃO MONETÁRIA E JUROS** → preenche "correcao_juros":
Mapeamento dos critérios da sentença para PJE-Calc:
- Critérios da ADC 58 / TST (IPCA-E pré-judicial + SELIC judicial + IPCA/SELIC-IPCA pós-30/08/2024):
    correcao_juros.indice_correcao = "Tabela JT Unica Mensal"
    correcao_juros.taxa_juros = "Selic"
- Apenas SELIC (sem distinção de fases):
    correcao_juros.indice_correcao = "Selic"
    correcao_juros.taxa_juros = "Selic"
- IPCA-E + juros padrão:
    correcao_juros.indice_correcao = "IPCA-E"
    correcao_juros.taxa_juros = "Juros Padrao"
- Tabela única mensal sem especificação: indice_correcao = "Tabela JT Unica Mensal"
- correcao_juros.base_juros: "Verbas" (padrão) ou "Credito Total" se explicitado
- correcao_juros.jam_fgts: true se a sentença mencionar JAM (juros sobre atraso de FGTS)

**CONTRIBUIÇÕES PREVIDENCIÁRIAS** → preenche "contribuicao_social":
- contribuicao_social.responsabilidade: "Ambos" (padrão quando ambos devem recolher)
  "Empregador" quando só o empregador; "Empregado" quando só o empregado
- contribuicao_social.lei_11941: true se explícito na sentença (campo opcional)

**IMPOSTO DE RENDA** → preenche "imposto_renda":
- imposto_renda.apurar: true se a sentença determinar apuração de IR; false se não mencionar
- Campos dependentes/meses_tributaveis: opcionais, só preencher se explícitos

=== SCHEMA JSON ESPERADO ===
{{
  "processo": {{
    "numero": "string | null",
    "reclamante": "string | null",
    "cpf_reclamante": "string | null",
    "reclamado": "string | null",
    "cnpj_reclamado": "string | null",
    "estado": "UF 2 letras | null",
    "municipio": "string | null",
    "vara": "string | null",
    "confianca": 0.95
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
    "confianca": 0.95
  }},
  "prescricao": {{
    "quinquenal": "true | false | null",
    "fgts": "true | false | null",
    "confianca": 0.95
  }},
  "aviso_previo": {{
    "tipo": "Calculado | Informado | Nao Apurar | null",
    "prazo_dias": "número inteiro | null",
    "projetar": "true | false | null",
    "confianca": 0.95
  }},
  "verbas_deferidas": [
    {{
      "nome_sentenca": "string — nome exato da condenação no relatório",
      "texto_original": "parâmetros resumidos da verba",
      "tipo": "Principal | Reflexa",
      "caracteristica": "Comum | 13o Salario | Aviso Previo | Ferias",
      "ocorrencia": "Mensal | Dezembro | Periodo Aquisitivo | Desligamento",
      "periodo_inicio": "DD/MM/AAAA | null",
      "periodo_fim": "DD/MM/AAAA | null",
      "percentual": "float | null",
      "base_calculo": "Maior Remuneracao | Historico Salarial | Salario Minimo | Piso Salarial | Verbas | null",
      "valor_informado": "float | null",
      "incidencia_fgts": true,
      "incidencia_inss": true,
      "incidencia_ir": false,
      "verba_principal_ref": "nome_sentenca da verba principal se reflexa | null",
      "confianca": 0.95
    }}
  ],
  "fgts": {{
    "aliquota": "float | null",
    "multa_40": "true | false | null",
    "multa_467": "true | false | null",
    "confianca": 0.95
  }},
  "honorarios": {{
    "percentual": "float | null",
    "valor_fixo": "float | null",
    "parte_devedora": "Reclamado | Reclamante | Ambos | null",
    "periciais": "float | null",
    "confianca": 0.95
  }},
  "correcao_juros": {{
    "indice_correcao": "Tabela JT Unica Mensal | IPCA-E | Selic | TRCT | null",
    "base_juros": "Verbas | Credito Total | null",
    "taxa_juros": "Juros Padrao | Selic | null",
    "jam_fgts": "true | false | null",
    "confianca": 0.95
  }},
  "contribuicao_social": {{
    "responsabilidade": "Empregador | Empregado | Ambos | null",
    "lei_11941": "true | false | null",
    "confianca": 0.95
  }},
  "imposto_renda": {{
    "apurar": "true | false",
    "meses_tributaveis": "número inteiro | null",
    "dependentes": "número inteiro | null",
    "confianca": 0.95
  }},
  "historico_salarial": [
    {{"data_inicio": "DD/MM/AAAA", "data_fim": "DD/MM/AAAA", "valor": 0.00}}
  ],
  "faltas": [
    {{"data_inicial": "DD/MM/AAAA", "data_final": "DD/MM/AAAA", "justificada": false, "descricao": ""}}
  ],
  "ferias": [
    {{"situacao": "Vencidas | Proporcionais | Gozadas", "periodo_inicio": "DD/MM/AAAA",
      "periodo_fim": "DD/MM/AAAA", "abono": false, "dobra": false}}
  ],
  "campos_ausentes": [],
  "alertas": []
}}

REGRAS FINAIS:
- campos_ausentes: listar APENAS campos OBRIGATÓRIOS ausentes:
  processo.numero, processo.reclamante, processo.reclamado, processo.estado,
  contrato.admissao, contrato.ajuizamento
  NÃO incluir campos opcionais: prescricao.*, honorarios.periciais, contrato.carga_horaria,
  imposto_renda.dependentes, imposto_renda.meses_tributaveis, aviso_previo.prazo_dias,
  contribuicao_social.lei_11941, fgts.multa_467
- alertas: copiar todos os ⚠️ ALERTAS do relatório como strings no array
- Retornar APENAS JSON puro, sem markdown, sem texto antes ou depois"""

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
        resultado = _extrair_de_relatorio_estruturado(texto, sessao_id)
        # Se o mapeamento do relatório falhou, fazer fallback para extração normal
        if "_erro_llm" in resultado:
            logger.warning("Falha no relatório estruturado — iniciando extração direta como fallback")
        else:
            return resultado

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

    # Timeout explícito: 120s evita travar indefinidamente no Railway
    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)

    try:
        resposta = cliente.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,  # 4096 suficiente para JSON do schema; 8192 causava timeout
            temperature=0.0,  # mapeamento determinístico
            system=_SYSTEM_PROMPT_RELATORIO,
            messages=[{
                "role": "user",
                "content": _RELATORIO_PROMPT.format(texto=texto_relatorio[:18000]),
            }],
        )
        conteudo = resposta.content[0].text.strip()
        dados = _limpar_e_parsear_json(conteudo)
        dados = _validar_e_completar(dados)
        if "alertas" not in dados:
            dados["alertas"] = []
        dados["alertas"].insert(0, "Dados extraídos de relatório estruturado (alta confiança).")
        return dados

    except json.JSONDecodeError as e:
        logger.warning(f"JSON inválido no relatório estruturado: {e} — fazendo fallback para extração direta")
        return {"_erro_llm": str(e), "alertas": [f"Relatório com JSON inválido; usando extração direta: {e}"]}
    except Exception as e:
        logger.warning(f"Falha ao mapear relatório: {e}")
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

    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=90.0)

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
        return _limpar_e_parsear_json(conteudo)

    except Exception as e:
        logger.warning(f"Falha na extração via IA: {e}")
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
            "cpf_reclamante": None,
            "reclamado": regex.get("reclamado"),
            "cnpj_reclamado": None,
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
        "historico_salarial": [],
        "faltas": [],
        "ferias": [],
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
