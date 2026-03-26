# modules/extraction.py — Módulo de Extração Jurídica (NLP + regex + LLM)
# Manual Técnico PJE-Calc, Seção 2 e 3

from __future__ import annotations

import base64
import concurrent.futures
import json
import logging
import re
import uuid
from datetime import datetime, date
from typing import Any

logger = logging.getLogger(__name__)

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_EXTRACTION_TEMPERATURE,
    CLAUDE_MAX_TOKENS,
    CONFIDENCE_THRESHOLD_AUTO,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    USE_GEMINI,
)
from modules.ingestion import normalizar_valor, normalizar_data, segmentar_sentenca


# ── Limpeza de JSON retornado pelo LLM ───────────────────────────────────────

def _sanitizar_chaves(obj: Any) -> Any:
    """
    Remove aspas extras de chaves JSON que o LLM pode gerar incorretamente.
    Ex: '"data_inicio"' → 'data_inicio'
    Processa recursivamente dicts e listas.
    """
    if isinstance(obj, dict):
        return {k.strip('"\'').strip(): _sanitizar_chaves(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitizar_chaves(item) for item in obj]
    return obj


def _limpar_e_parsear_json(texto: str) -> dict:
    """
    Tenta parsear JSON retornado pelo LLM com tolerância a erros comuns:
    - Remove blocos markdown ```json ... ```
    - Remove vírgulas antes de } ou ]  (trailing commas)
    - Extrai primeiro bloco { ... } caso haja texto em volta
    - Sanitiza chaves com aspas extras (ex: '"data_inicio"')
    """
    # 1. Remover blocos markdown
    texto = re.sub(r"^```(?:json)?\s*", "", texto.strip(), flags=re.MULTILINE)
    texto = re.sub(r"\s*```\s*$", "", texto, flags=re.MULTILINE)
    texto = texto.strip()

    # 2. Tentar parse direto
    try:
        return _sanitizar_chaves(json.loads(texto))
    except json.JSONDecodeError:
        pass

    # 3. Remover trailing commas  (,  seguida de espaços/newlines e } ou ])
    limpo = re.sub(r",\s*([}\]])", r"\1", texto)
    try:
        return _sanitizar_chaves(json.loads(limpo))
    except json.JSONDecodeError:
        pass

    # 4. Extrair o maior bloco JSON da resposta
    match = re.search(r"\{.*\}", limpo, re.DOTALL)
    if match:
        try:
            return _sanitizar_chaves(json.loads(match.group()))
        except json.JSONDecodeError:
            limpo = match.group()

    # 5. Tentar fechar JSON truncado — contar chaves/colchetes abertos e fechá-los
    try:
        parcial = limpo
        # Remover trailing incompleto (valor string cortado ou vírgula pendente)
        parcial = re.sub(r',\s*$', '', parcial.rstrip())
        parcial = re.sub(r':\s*"[^"]*$', ': null', parcial)  # string aberta no fim
        # Fechar estruturas abertas
        abre = parcial.count('{') - parcial.count('}')
        fecha_colchete = parcial.count('[') - parcial.count(']')
        if fecha_colchete > 0:
            parcial += ']' * fecha_colchete
        if abre > 0:
            parcial += '}' * abre
        return _sanitizar_chaves(json.loads(parcial))
    except json.JSONDecodeError:
        pass

    # 6. Sem recuperação possível — relançar com o texto limpo para logging
    return _sanitizar_chaves(json.loads(limpo))  # levanta JSONDecodeError com contexto útil


# ── Prompt principal para o Claude ───────────────────────────────────────────

_SYSTEM_PROMPT = """Você é um especialista em Direito do Trabalho brasileiro e no sistema PJE-Calc \
(Programa de Cálculos da Justiça do Trabalho — CNJ/TST).

Sua tarefa é analisar o conteúdo fornecido (sentença, documentos ou relatório) e extrair \
todas as informações necessárias para preenchimento preciso e completo do PJE-Calc, \
mapeando cada dado ao campo e enumeração exata do sistema.

Regras absolutas:
- Responda SOMENTE com JSON válido, sem markdown (sem ```json), sem texto antes ou depois
- Datas: DD/MM/AAAA
- Valores monetários: float sem símbolo (ex: 1518.00)
- Percentuais: float decimal (ex: 15% → 0.15; 8% → 0.08; 40% → 0.40)
- Use null para campos genuinamente ausentes no texto
- Quando a legislação define valor padrão e não há indicação contrária: aplique o padrão com confianca=0.85
- confianca por seção: 0.95 = extraído diretamente | 0.85 = inferido por lógica jurídica | 0.6 = incerto

## Terminologia específica TRT7 (7ª Região — Ceará/CE):
- "Vara do Trabalho de Fortaleza" / "VT de Fortaleza" / "1ª VT"... → estado="CE"
- "rescisão indireta" → tipo_rescisao="sem_justa_causa" (equiparada art. 483 CLT)
- "ruptura contratual por iniciativa do empregador" → "sem_justa_causa"
- "justa causa comprovada" = "justa causa reconhecida" → "justa_causa"
- "diferenças salariais" → verba COMUM, Mensal, incidencias salariais
- "DSR sobre horas extras" / "repouso semanal remunerado" → verba Reflexa de horas extras
- "multa normativa" / "multa art. 477 §8º" → verba COMUM Desligamento (sem incidências)

## Regras de reflexos (gerar automaticamente):
Se "horas extras" estiver nas verbas_deferidas → incluir também:
  - "Reflexo em DSR" (tipo=Reflexa, COMUM, Mensal, verba_principal_ref=nome horas extras)
  - "Reflexo em 13º Salário" (tipo=Reflexa, 13o Salario, Dezembro)
  - "Reflexo em Férias + 1/3" (tipo=Reflexa, Ferias, Periodo Aquisitivo)
  - incidência nas reflexas: fgts=true, inss=true, ir=true (exceto férias: fgts=false)"""

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
- "Autuado em:" / "Data de autuação:" / "Data de distribuição:" → processo.autuado_em (DD/MM/AAAA)
- "Valor da causa:" / "Valor atribuído à causa:" → processo.valor_causa (float; extrair de qualquer
  seção do documento, inclusive cabeçalho do processo, petição inicial ou relatório)

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
    {{"data_inicio": "01/01/2023", "data_fim": "31/08/2024", "valor": 1518.00}},
    {{"data_inicio": "01/09/2024", "data_fim": "28/02/2025", "valor": 1800.00}}
  ]
Se houver apenas um salário uniforme durante todo o contrato → historico_salarial = []

**FALTAS** → preenche "faltas":
Se a sentença mencionar faltas injustificadas ou justificadas, extrair:
  faltas: [
    {{"data_inicial": "DD/MM/AAAA", "data_final": "DD/MM/AAAA", "justificada": false, "descricao": ""}}
  ]
Se não mencionado → faltas = []

**FÉRIAS** → preenche "ferias":
Se a sentença mencionar períodos de férias não gozadas ou situações específicas, extrair:
  ferias: [
    {{"situacao": "Vencidas", "periodo_inicio": "DD/MM/AAAA", "periodo_fim": "DD/MM/AAAA",
     "abono": false, "dobra": false}}
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

**SEÇÃO 6 — HONORÁRIOS ADVOCATÍCIOS** → preenche "honorarios" (LISTA de registros):
⚠️ O PJE-Calc NÃO tem opção "Ambos" — cada honorário é um registro separado por devedor.
- Sucumbência recíproca → gerar DOIS registros na lista:
    [{{"devedor": "RECLAMADO", "base_apuracao": "Condenação", ...}},
     {{"devedor": "RECLAMANTE", "base_apuracao": "Verbas Não Compõem Principal", ...}}]
- Sucumbência integral da reclamada → um registro com devedor="RECLAMADO"
- Sucumbência integral do reclamante → um registro com devedor="RECLAMANTE"
- Se indeferidos ou não mencionados → honorarios = []
- tipo: "SUCUMBENCIAIS" (padrão — condenação em honorários pelo juiz) | "CONTRATUAIS" (raro)
- tipo_valor: "CALCULADO" quando há percentual | "INFORMADO" quando há valor fixo em R$
- base_apuracao — depende do devedor + tipo:
    RECLAMADO + SUCUMBENCIAIS: "Condenação" (padrão — % sobre o valor da condenação) | "Renda Mensal"
    RECLAMANTE + SUCUMBENCIAIS: "Verbas Não Compõem Principal" (padrão — % sobre pedidos indeferidos) | "Condenação" | "Renda Mensal"
    CONTRATUAIS: "Condenação" | "Renda Mensal"
  ⚠️ Quando a sentença diz "sobre o valor da condenação" para AMBAS as partes →
     usar "Condenação" para os dois registros
- percentual: float decimal (ex: 0.15 para 15%); null se tipo_valor=INFORMADO
- valor_informado: float; null se tipo_valor=CALCULADO
- apurar_ir: true quando os honorários forem tributáveis (advogado pessoa física)

**SEÇÃO 7 — HONORÁRIOS PERICIAIS** → preenche "honorarios_periciais" (campo top-level — NÃO colocar dentro do array "honorarios"):
- Buscar "honorários periciais", "honorário do perito", "laudo pericial", "assistente técnico"
- Se deferidos com valor explícito: honorarios_periciais = float (ex: 5000.00)
- Se indeferidos ou não mencionados: honorarios_periciais = null

**SEÇÃO 8 — CORREÇÃO MONETÁRIA E JUROS** → preenche "correcao_juros":
Mapeamento dos critérios da sentença para os enums do PJE-Calc:

CASOS MAIS COMUNS:
1. ADC 58 / critérios TST (menção a "ADC 58", "Tabela JT Única Mensal", "IPCA-E até o ajuizamento
   e SELIC a partir do ajuizamento", ou simplesmente "critérios da Justiça do Trabalho"):
     indice_correcao = "Tabela JT Unica Mensal"
     taxa_juros = "Selic"

2. Apenas SELIC para tudo ("atualizado pela SELIC", "taxa SELIC", sem distinguir fases):
     indice_correcao = "Selic"
     taxa_juros = "Selic"

3. IPCA-E + juros legais de 1% ao mês ("IPCA-E mais juros de 1% ao mês", "IPCA-E + juros
   moratórios de 1% ao mês"):
     indice_correcao = "IPCA-E"
     taxa_juros = "Juros Padrao"

4. TR + juros de 1% ao mês ("TR", "TRCT", "correção pela TR mais 1% ao mês"):
     indice_correcao = "TRCT"
     taxa_juros = "Juros Padrao"

5. IPCA-E sem especificação de juros:
     indice_correcao = "IPCA-E"
     taxa_juros = "Juros Padrao"  (padrão quando índice é IPCA-E)

NOTA: "Juros Padrao" = 1% ao mês (juros legais trabalhistas clássicos)
      "Selic" = taxa SELIC acumulada (aplicável após ADC 58)

- correcao_juros.base_juros:
    "Verbas" = padrão (juros calculados verba a verba)
    "Credito Total" = apenas quando explicitamente mencionado "crédito total" ou "total da dívida"
- correcao_juros.jam_fgts: true se a sentença mencionar "JAM" ou "juros sobre atraso de FGTS"

**CONTRIBUIÇÕES PREVIDENCIÁRIAS** → preenche "contribuicao_social":
⚠️ PJE-Calc usa checkboxes individuais — NÃO um campo "responsabilidade":
- apurar_segurado_salarios_devidos: true quando há salários devidos com incidência de INSS (padrão true)
- cobrar_do_reclamante: true quando a cota do empregado deve ser descontada do crédito do reclamante
    → true quando "dedução na fonte", "cada parte arcará com sua quota", omissão (padrão legal)
    → false apenas quando sentença determina expressamente que "o empregador arcará com toda a contribuição"
- com_correcao_trabalhista: true para aplicar correção trabalhista ao INSS (padrão true)
- apurar_sobre_salarios_pagos: true quando há salários pagos a menor durante o contrato (raro — apenas se explícito)
- lei_11941: true se mencionar "Lei 11.941/2009" ou "regime de competência" previdenciário
  ⚠️ Padrão quando omitido: apurar_segurado_salarios_devidos=true, cobrar_do_reclamante=true, com_correcao_trabalhista=true, apurar_sobre_salarios_pagos=false

**IMPOSTO DE RENDA** → preenche "imposto_renda":
- apurar: true se há verbas tributáveis (salariais) ou sentença determina apuração de IR
- tributacao_exclusiva: true se a sentença mencionar "tributação exclusiva na fonte" / "RRA" / "rendimentos recebidos acumuladamente"
- regime_de_caixa: true se mencionar "regime de caixa" / "tributação mês a mês" / "pro rata"
- tributacao_em_separado: true se mencionar "tributação em separado" (raro)
- deducao_inss: true quando deve deduzir INSS da base do IR (padrão true quando apurar=true e há INSS)
- deducao_honorarios_reclamante: true quando honorários do reclamante deduzem da base do IR
- deducao_pensao_alimenticia: true se sentença mencionar pensão alimentícia como dedução do IR
- valor_pensao: float com o valor da pensão se deducao_pensao_alimenticia=true
- meses_tributaveis: número de meses tributáveis, se informado

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
    "valor_causa": "float | null",
    "autuado_em": "DD/MM/AAAA | null",
    "confianca": 0.95
  }},
  "contrato": {{
    "admissao": "DD/MM/AAAA | null",
    "demissao": "DD/MM/AAAA | null",
    "tipo_rescisao": "sem_justa_causa | justa_causa | pedido_demissao | distrato | morte | null",
    "regime": "Tempo Integral | Tempo Parcial | Trabalho Intermitente | null",
    "carga_horaria": "número inteiro (horas/mês) | null",
    "jornada_diaria": "float (horas/dia) | null",
    "jornada_semanal": "float (horas/semana) | null",
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
  "honorarios": [
    {{
      "tipo": "SUCUMBENCIAIS | CONTRATUAIS",
      "devedor": "RECLAMANTE | RECLAMADO",
      "tipo_valor": "CALCULADO | INFORMADO",
      "base_apuracao": "Condenação | Verbas Não Compõem Principal | Renda Mensal",
      "percentual": "float | null",
      "valor_informado": "float | null",
      "apurar_ir": "true | false"
    }}
  ],
  "honorarios_periciais": "float | null",
  "correcao_juros": {{
    "indice_correcao": "Tabela JT Unica Mensal | IPCA-E | Selic | TRCT | null",
    "base_juros": "Verbas | Credito Total | null",
    "taxa_juros": "Juros Padrao | Selic | null",
    "jam_fgts": "true | false | null",
    "confianca": 0.95
  }},
  "contribuicao_social": {{
    "apurar_segurado_salarios_devidos": "true | false",
    "cobrar_do_reclamante": "true | false",
    "com_correcao_trabalhista": "true | false",
    "apurar_sobre_salarios_pagos": "true | false",
    "lei_11941": "true | false | null",
    "confianca": 0.95
  }},
  "imposto_renda": {{
    "apurar": "true | false",
    "tributacao_exclusiva": "true | false | null",
    "regime_de_caixa": "true | false | null",
    "tributacao_em_separado": "true | false | null",
    "deducao_inss": "true | false | null",
    "deducao_honorarios_reclamante": "true | false | null",
    "deducao_pensao_alimenticia": "true | false | null",
    "valor_pensao": "float | null",
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

_EXTRACTION_PROMPT = """Analise o conteúdo abaixo (sentença trabalhista e/ou documentos complementares) \
e extraia TODOS os dados para preenchimento completo e preciso do PJE-Calc, \
seguindo rigorosamente o guia de extração e o schema JSON abaixo.

=== CONTEÚDO ===
{texto}

=== GUIA DE EXTRAÇÃO PARA PJE-CALC ===

**PROCESSO E PARTES** → preenche "processo":
- numero: formato CNJ — NNNNNNN-DD.AAAA.J.RR.VVVV (ex: "0001234-56.2023.5.07.0001")
- reclamante: nome completo do trabalhador (sem CPF inline)
- cpf_reclamante: CPF se explicitado, formato "000.000.000-00"
- reclamado: razão social/nome do empregador (sem CNPJ inline)
- cnpj_reclamado: CNPJ se explicitado, formato "00.000.000/0000-00"
- estado: UF de 2 letras da vara — buscar em "Vara do Trabalho de [cidade] - UF" ou cabeçalho
- vara: descrição da vara/juízo

**CONTRATO DE TRABALHO** → preenche "contrato":
- admissao: buscar "admitido em", "admissão:", "contratado em", "início do contrato"
- demissao: data REAL da dispensa — buscar "dispensado em", "rescisão em", "demitido em"
  ⚠️ NUNCA usar data de projeção com aviso prévio — apenas a data efetiva do desligamento
- tipo_rescisao:
    "sem justa causa" / "dispensa imotivada" / "rescisão imotivada" / "rescisão indireta" → "sem_justa_causa"
    "com justa causa" → "justa_causa"
    "pedido de demissão" → "pedido_demissao"
    "distrato" → "distrato"
    "falecimento" / "morte" → "morte"
- ultima_remuneracao: último salário pago (valor do último mês); se houve evolução salarial, usar o mais recente
- maior_remuneracao: maior salário recebido no contrato; se não diferenciado, igual à ultima_remuneracao
- ajuizamento: data de distribuição/autuação/protocolo da reclamação trabalhista
- regime: "Tempo Integral" (padrão), "Tempo Parcial" (jornada reduzida art. 58-A CLT), "Trabalho Intermitente"
- carga_horaria: horas/mês se informado; null se omitido (não incluir em campos_ausentes)
- jornada_diaria: horas por dia de trabalho (float) — extrair de "jornada de 8 horas", "8h diárias",
  "8 horas por dia", "jornada diária de 8h". Ex: 8.0, 6.0, 7.3 (use null se não mencionado)
- jornada_semanal: horas por semana (float) — extrair de "44 horas semanais", "44h/semana",
  "jornada semanal de 40h". Ex: 44.0, 40.0, 36.0 (use null se não mencionado)
  Se jornada_semanal não estiver explícita mas jornada_diaria sim: calcular como jornada_diaria × dias_por_semana
  (padrão: 6 dias para 44h/sem, 5 dias para 40h/sem, proporcional para outros)

**AVISO PRÉVIO** → preenche "aviso_previo":
- Deferido calculado pela Lei 12.506/2011: tipo="Calculado", projetar=true
- Deferido com dias fixos (ex: "aviso prévio de 30 dias"): tipo="Informado", prazo_dias=30, projetar=true
- Indeferido ou ausente: tipo="Nao Apurar", projetar=false

**HISTÓRICO SALARIAL** → preenche "historico_salarial":
- Preencher SOMENTE quando o salário mudou ao longo do contrato (evolução salarial)
- Cada entrada: data_inicio (DD/MM/AAAA), data_fim (DD/MM/AAAA), valor (float)
- Salário único durante todo o contrato → historico_salarial = []

**VERBAS DEFERIDAS** → preenche "verbas_deferidas" (SEÇÃO MAIS CRÍTICA):
Listar cada parcela condenada. Para cada verba:

nome_sentenca: nome exato da verba como aparece na sentença
  (ex: "SALDO DE SALÁRIO", "HORAS EXTRAS", "DÉCIMO TERCEIRO SALÁRIO", "DANOS MORAIS")
tipo:
  "Principal" → condenação direta
  "Reflexa" → repercussão de verba principal (ex: "Reflexo em 13º", "Reflexo em férias + 1/3")
caracteristica:
  "13o Salario" → 13º salário (proporcional, integral)
  "Ferias" → férias vencidas, proporcionais, 1/3 de férias
  "Aviso Previo" → verba salarial do aviso prévio
  "Comum" → todos os demais (horas extras, adicionais, diferenças, saldo, danos, multas)
ocorrencia:
  "Mensal" → verbas que se repetem mensalmente (horas extras, adicionais, diferenças salariais)
  "Dezembro" → 13º salário
  "Periodo Aquisitivo" → férias (ocorrem a cada período aquisitivo)
  "Desligamento" → verbas pagas na rescisão (saldo de salário, aviso, multas rescisórias)
base_calculo:
  "Historico Salarial" → verba calculada sobre o salário de cada mês (quando há evolução salarial)
  "Maior Remuneracao" → usa o maior salário do contrato
  "Salario Minimo" → baseada explicitamente no salário mínimo federal
  "Piso Salarial" → baseada no piso da categoria profissional
  "Verbas" → para verbas reflexas (base = verba principal)
  null → não especificado
incidências (aplicar a lógica trabalhista):
  Verbas salariais (diferenças, saldo, horas extras, adicionais, 13º):
    incidencia_fgts=true, incidencia_inss=true, incidencia_ir=true
  Férias + 1/3:
    incidencia_fgts=false, incidencia_inss=true, incidencia_ir=true
  Aviso prévio indenizado, danos morais, danos materiais, multas (art. 467, 477, 40%):
    incidencia_fgts=false, incidencia_inss=false, incidencia_ir=false
verba_principal_ref: para verbas reflexas, informar o nome_sentenca da verba principal

**FGTS** → preenche "fgts":
- aliquota: 0.08 (8%) para a maioria dos contratos; 0.02 (2%) para aprendizes
  Buscar "alíquota de X%" ou "FGTS à alíquota de X%"
- multa_40: true quando deferida "multa de 40%" / "multa rescisória" / "art. 18 §1º da Lei 8.036"
- multa_467: true quando deferida "multa do art. 467 CLT" (verbas rescisórias incontroversas)

**HONORÁRIOS ADVOCATÍCIOS** → preenche "honorarios" (LISTA de registros):
⚠️ O PJE-Calc NÃO tem opção "Ambos" — cada honorário é um registro separado por devedor.
- Sucumbência recíproca → gerar DOIS registros na lista:
    [{{"devedor": "RECLAMADO", "base_apuracao": "Condenação", ...}},
     {{"devedor": "RECLAMANTE", "base_apuracao": "Verbas Não Compõem Principal", ...}}]
- Sucumbência integral da reclamada → um registro com devedor="RECLAMADO"
- Sucumbência integral do reclamante → um registro com devedor="RECLAMANTE"
- Se indeferidos ou não mencionados → honorarios = []
- tipo: "SUCUMBENCIAIS" (padrão) | "CONTRATUAIS" (raro)
- tipo_valor: "CALCULADO" quando há percentual | "INFORMADO" quando há valor fixo em R$
- base_apuracao:
    RECLAMADO + SUCUMBENCIAIS: "Condenação" (padrão) | "Renda Mensal"
    RECLAMANTE + SUCUMBENCIAIS: "Verbas Não Compõem Principal" (padrão) | "Condenação" | "Renda Mensal"
    ⚠️ Quando sentença diz "sobre o valor da condenação" para AMBAS as partes → "Condenação" nos dois
- percentual: decimal (15% → 0.15); null se tipo_valor=INFORMADO
- valor_informado: float; null se tipo_valor=CALCULADO
- apurar_ir: true quando honorários são tributáveis

**HONORÁRIOS PERICIAIS** → preenche "honorarios_periciais" (campo top-level, SEPARADO da lista "honorarios"):
- Buscar "honorários periciais", "honorário do perito", "laudo pericial", "assistente técnico"
- Valor float ou null. NÃO colocar dentro de honorarios[].

**CORREÇÃO MONETÁRIA E JUROS** → preenche "correcao_juros":
Mapear EXATAMENTE para os enums disponíveis no PJE-Calc:

Caso 1 — ADC 58 / Tabela JT / critérios do TST:
  Indicadores: "ADC 58", "Tabela JT Única Mensal", "IPCA-E até o ajuizamento e SELIC a partir",
               "critérios da Justiça do Trabalho", "OJ 07 da SBDI-2", "Súmula 200"
  → indice_correcao = "Tabela JT Unica Mensal" | taxa_juros = "Selic"

Caso 2 — Apenas SELIC:
  Indicadores: "atualizado pela SELIC", "taxa SELIC", "correção pela SELIC" (sem distinção de fases)
  → indice_correcao = "Selic" | taxa_juros = "Selic"

Caso 3 — IPCA-E + juros de 1% ao mês:
  Indicadores: "IPCA-E mais juros de 1% ao mês", "IPCA-E e juros moratórios de 1%",
               "IPCA-E + juros legais", "IPCA-E acrescido de 1% ao mês"
  → indice_correcao = "IPCA-E" | taxa_juros = "Juros Padrao"

Caso 4 — TR / TRCT + juros de 1% ao mês:
  Indicadores: "TR mais 1% ao mês", "TRCT", "correção pela TR e juros de 1%"
  → indice_correcao = "TRCT" | taxa_juros = "Juros Padrao"

Caso 5 — IPCA-E sem especificação de juros:
  → indice_correcao = "IPCA-E" | taxa_juros = "Juros Padrao"

"Juros Padrao" = 1% ao mês (juros legais trabalhistas — art. 39 Lei 8.177/91)
"Selic" = taxa SELIC acumulada (aplicável desde ADC 58, 30/08/2021)
base_juros: "Verbas" (padrão — juros calculados verba a verba) ou
            "Credito Total" (apenas se a sentença mencionar explicitamente)
jam_fgts: true se mencionar "JAM" ou "juros sobre atraso no depósito do FGTS"

**CONTRIBUIÇÕES PREVIDENCIÁRIAS** → preenche "contribuicao_social":
⚠️ PJE-Calc usa checkboxes individuais — NÃO um campo "responsabilidade":
- apurar_segurado_salarios_devidos: true quando há salários devidos com incidência de INSS (padrão true)
- cobrar_do_reclamante: true quando a cota do empregado deve ser descontada do crédito do reclamante
    → true quando: omissão (padrão legal), "dedução na fonte", "cada parte arcará com sua quota"
    → false APENAS quando: sentença diz expressamente "empregador arcará com toda a contribuição"
- com_correcao_trabalhista: true para aplicar correção trabalhista ao INSS (padrão true)
- apurar_sobre_salarios_pagos: true apenas quando há salários pagos a menor (explícito; padrão false)
- lei_11941: true se mencionar "Lei 11.941/2009" ou "regime de competência" previdenciário
- ⚠️ Padrão quando omitido: todos os campos true exceto apurar_sobre_salarios_pagos=false

**IMPOSTO DE RENDA** → preenche "imposto_renda":
- apurar: true quando há verbas tributáveis (salários, horas extras, 13º, férias) ou sentença determina IR
    false apenas quando somente verbas indenizatórias (danos morais, aviso prévio indenizado, multas)
- tributacao_exclusiva: true se mencionar "tributação exclusiva na fonte" / "RRA" / "rendimentos recebidos acumuladamente"
- regime_de_caixa: true se mencionar "regime de caixa" / "tributação mês a mês" / "pro rata temporis do IR"
- tributacao_em_separado: true se mencionar "tributação em separado" (raro)
- deducao_inss: true quando deve deduzir INSS da base do IR (padrão true quando apurar=true e há INSS)
- deducao_honorarios_reclamante: true quando honorários sucumbenciais do reclamante deduzem da base do IR
- deducao_pensao_alimenticia: true se mencionar pensão alimentícia como dedução do IR
- valor_pensao: float com o valor da pensão alimentícia se deducao_pensao_alimenticia=true
- meses_tributaveis: número de meses tributáveis, se explicitado

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
    "valor_causa": "float | null",
    "autuado_em": "DD/MM/AAAA | null",
    "confianca": 0.0-1.0
  }},
  "contrato": {{
    "admissao": "DD/MM/AAAA | null",
    "demissao": "DD/MM/AAAA | null",
    "tipo_rescisao": "sem_justa_causa | justa_causa | pedido_demissao | distrato | morte | null",
    "regime": "Tempo Integral | Tempo Parcial | Trabalho Intermitente | null",
    "carga_horaria": "número inteiro (horas/mês) | null",
    "jornada_diaria": "float (horas/dia) | null",
    "jornada_semanal": "float (horas/semana) | null",
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
      "nome_sentenca": "string",
      "texto_original": "trecho ou parâmetros da verba",
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
      "confianca": 0.0-1.0
    }}
  ],
  "fgts": {{
    "aliquota": "float | null",
    "multa_40": "true | false | null",
    "multa_467": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "honorarios": [
    {{
      "tipo": "SUCUMBENCIAIS | CONTRATUAIS",
      "devedor": "RECLAMANTE | RECLAMADO",
      "tipo_valor": "CALCULADO | INFORMADO",
      "base_apuracao": "Condenação | Verbas Não Compõem Principal | Renda Mensal",
      "percentual": "float | null",
      "valor_informado": "float | null",
      "apurar_ir": "true | false"
    }}
  ],
  "honorarios_periciais": "float | null",
  "correcao_juros": {{
    "indice_correcao": "Tabela JT Unica Mensal | IPCA-E | Selic | TRCT | null",
    "base_juros": "Verbas | Credito Total | null",
    "taxa_juros": "Juros Padrao | Selic | null",
    "jam_fgts": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "contribuicao_social": {{
    "apurar_segurado_salarios_devidos": "true | false",
    "cobrar_do_reclamante": "true | false",
    "com_correcao_trabalhista": "true | false",
    "apurar_sobre_salarios_pagos": "true | false",
    "lei_11941": "true | false | null",
    "confianca": 0.0-1.0
  }},
  "imposto_renda": {{
    "apurar": "true | false",
    "tributacao_exclusiva": "true | false | null",
    "regime_de_caixa": "true | false | null",
    "tributacao_em_separado": "true | false | null",
    "deducao_inss": "true | false | null",
    "deducao_honorarios_reclamante": "true | false | null",
    "deducao_pensao_alimenticia": "true | false | null",
    "valor_pensao": "float | null",
    "meses_tributaveis": "número inteiro | null",
    "dependentes": "número inteiro | null",
    "confianca": 0.0-1.0
  }},
  "historico_salarial": [
    {{"data_inicio": "DD/MM/AAAA", "data_fim": "DD/MM/AAAA", "valor": 0.00}}
  ],
  "faltas": [],
  "ferias": [],
  "campos_ausentes": ["campos OBRIGATÓRIOS ausentes — ver regra abaixo"],
  "alertas": ["avisos relevantes para o operador"]
}}

REGRA campos_ausentes — incluir SOMENTE estes campos quando ausentes:
  processo.numero, processo.reclamante, processo.reclamado, processo.estado,
  contrato.admissao, contrato.ajuizamento
NÃO incluir campos opcionais: carga_horaria, cpf_reclamante, cnpj_reclamado,
  honorarios.periciais, imposto_renda.dependentes, imposto_renda.meses_tributaveis,
  aviso_previo.prazo_dias, contribuicao_social.lei_11941, fgts.multa_467,
  prescricao.*, processo.municipio, processo.vara

Retorne APENAS o JSON, sem markdown, sem explicações."""


# ── Função principal ──────────────────────────────────────────────────────────

def extrair_dados_sentenca(
    texto: str,
    sessao_id: str | None = None,
    extras: list[dict] | None = None,
    is_relatorio: bool = False,
    usar_gemini: bool | None = None,
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
        usar_gemini: True=forçar Gemini, False=forçar Claude, None=usar config global USE_GEMINI
    """
    sessao_id = sessao_id or str(uuid.uuid4())

    if is_relatorio:
        resultado = _extrair_de_relatorio_estruturado(texto, sessao_id)
        if "_erro_llm" not in resultado:
            return resultado
        # IA falhou no relatório — bloquear conforme regra de negócio
        logger.error("IA falhou no mapeamento do relatório — processamento bloqueado")
        return {
            "_erro_ia": True,
            "alertas": resultado.get("alertas", []) + [
                "BLOQUEADO: falha ao processar o relatório via IA. "
                "Verifique créditos da API Anthropic e reenvie o documento."
            ],
            "campos_ausentes": [],
            "verbas_deferidas": [],
            "historico_salarial": [],
            "faltas": [],
            "ferias": [],
            "honorarios": [],
        }

    # Segmentar sentença para focar no dispositivo
    blocos = segmentar_sentenca(texto)
    texto_principal = blocos.get("dispositivo") or texto
    texto_completo = texto

    # Fase 1: extração regex pré-processada
    dados_regex = _extrair_via_regex(texto_completo)

    # Fase 2: extração via LLM — Claude ou Gemini conforme configuração
    # Limites generosos: Claude Sonnet 4.6 suporta 200k tokens; Gemini 2.5 Flash 1M tokens
    _LIMITE_TOTAL = 28000
    _LIMITE_CABECALHO = 6000
    _LIMITE_DISPOSITIVO = 22000
    cabecalho = texto_completo[:_LIMITE_CABECALHO]
    dispositivo = texto_principal[-_LIMITE_DISPOSITIVO:]
    if cabecalho and dispositivo and cabecalho not in dispositivo:
        texto_para_llm = cabecalho + "\n\n[...trecho intermediário omitido...]\n\n" + dispositivo
    else:
        texto_para_llm = texto_completo[:_LIMITE_TOTAL]

    # usar_gemini: True=forçar Gemini, False=forçar Claude, None=usar config global
    _usar_gemini = USE_GEMINI if usar_gemini is None else usar_gemini

    if _usar_gemini and GEMINI_API_KEY:
        logger.info("Extração via Gemini (%s)", GEMINI_MODEL)
        dados_llm = _extrair_via_gemini(texto_para_llm, extras=extras)
        # Fallback para Claude se Gemini falhar
        if "_erro_llm" in dados_llm and ANTHROPIC_API_KEY:
            logger.warning("Gemini falhou — fallback para Claude")
            dados_llm = _extrair_via_llm(texto_para_llm, extras=extras)
    else:
        dados_llm = _extrair_via_llm(texto_para_llm, extras=extras)

    # IA indisponível → bloquear; prévia NÃO pode ser gerada sem extração por IA
    if "_erro_llm" in dados_llm:
        logger.error("IA indisponível — processamento bloqueado conforme regra de negócio")
        return {
            "_erro_ia": True,
            "alertas": dados_llm.get("alertas", []) + [
                "BLOQUEADO: extração via IA indisponível. "
                "Verifique créditos da API Anthropic e reprocesse o documento."
            ],
            "campos_ausentes": [],
            "verbas_deferidas": [],
            "historico_salarial": [],
            "faltas": [],
            "ferias": [],
            "honorarios": [],
        }

    # Fase 3: merge (LLM prevalece; regex preenche onde LLM retornou null)
    dados = _merge_extracao(dados_regex, dados_llm)

    # Fase 4: validação e identificação de campos ausentes
    dados = _validar_e_completar(dados)

    return dados


# ── JSON Schema para Structured Outputs (Claude output_config) ───────────────
# Garante que o modelo retorne JSON válido sem a necessidade de parsing tolerante.

_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "processo", "contrato", "prescricao", "aviso_previo",
        "verbas_deferidas", "fgts", "honorarios", "honorarios_periciais",
        "correcao_juros", "contribuicao_social", "imposto_renda",
        "historico_salarial", "faltas", "ferias", "campos_ausentes", "alertas",
    ],
    "properties": {
        "processo": {
            "type": "object", "additionalProperties": False,
            "required": ["numero","reclamante","cpf_reclamante","reclamado","cnpj_reclamado",
                         "estado","municipio","vara","valor_causa","autuado_em","confianca"],
            "properties": {
                "numero":         {"type": ["string","null"]},
                "reclamante":     {"type": ["string","null"]},
                "cpf_reclamante": {"type": ["string","null"]},
                "reclamado":      {"type": ["string","null"]},
                "cnpj_reclamado": {"type": ["string","null"]},
                "estado":         {"type": ["string","null"]},
                "municipio":      {"type": ["string","null"]},
                "vara":           {"type": ["string","null"]},
                "valor_causa":    {"type": ["number","null"]},
                "autuado_em":     {"type": ["string","null"]},
                "confianca":      {"type": "number"},
            },
        },
        "contrato": {
            "type": "object", "additionalProperties": False,
            "required": ["admissao","demissao","tipo_rescisao","regime","carga_horaria",
                         "jornada_diaria","jornada_semanal","maior_remuneracao",
                         "ultima_remuneracao","ajuizamento","confianca"],
            "properties": {
                "admissao":          {"type": ["string","null"]},
                "demissao":          {"type": ["string","null"]},
                "tipo_rescisao":     {"type": ["string","null"]},
                "regime":            {"type": ["string","null"]},
                "carga_horaria":     {"type": ["integer","null"]},
                "jornada_diaria":    {"type": ["number","null"]},
                "jornada_semanal":   {"type": ["number","null"]},
                "maior_remuneracao": {"type": ["number","null"]},
                "ultima_remuneracao":{"type": ["number","null"]},
                "ajuizamento":       {"type": ["string","null"]},
                "confianca":         {"type": "number"},
            },
        },
        "prescricao": {
            "type": "object", "additionalProperties": False,
            "required": ["quinquenal","fgts","confianca"],
            "properties": {
                "quinquenal": {"type": ["boolean","null"]},
                "fgts":       {"type": ["boolean","null"]},
                "confianca":  {"type": "number"},
            },
        },
        "aviso_previo": {
            "type": "object", "additionalProperties": False,
            "required": ["tipo","prazo_dias","projetar","confianca"],
            "properties": {
                "tipo":       {"type": ["string","null"]},
                "prazo_dias": {"type": ["integer","null"]},
                "projetar":   {"type": ["boolean","null"]},
                "confianca":  {"type": "number"},
            },
        },
        "verbas_deferidas": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["nome_sentenca","texto_original","tipo","caracteristica","ocorrencia",
                             "periodo_inicio","periodo_fim","percentual","base_calculo",
                             "valor_informado","incidencia_fgts","incidencia_inss","incidencia_ir",
                             "verba_principal_ref","confianca"],
                "properties": {
                    "nome_sentenca":     {"type": "string"},
                    "texto_original":    {"type": ["string","null"]},
                    "tipo":              {"type": "string"},
                    "caracteristica":    {"type": "string"},
                    "ocorrencia":        {"type": "string"},
                    "periodo_inicio":    {"type": ["string","null"]},
                    "periodo_fim":       {"type": ["string","null"]},
                    "percentual":        {"type": ["number","null"]},
                    "base_calculo":      {"type": ["string","null"]},
                    "valor_informado":   {"type": ["number","null"]},
                    "incidencia_fgts":   {"type": "boolean"},
                    "incidencia_inss":   {"type": "boolean"},
                    "incidencia_ir":     {"type": "boolean"},
                    "verba_principal_ref":{"type": ["string","null"]},
                    "confianca":         {"type": "number"},
                },
            },
        },
        "fgts": {
            "type": "object", "additionalProperties": False,
            "required": ["aliquota","multa_40","multa_467","confianca"],
            "properties": {
                "aliquota":   {"type": ["number","null"]},
                "multa_40":   {"type": ["boolean","null"]},
                "multa_467":  {"type": ["boolean","null"]},
                "confianca":  {"type": "number"},
            },
        },
        "honorarios": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["tipo","devedor","tipo_valor","base_apuracao",
                             "percentual","valor_informado","apurar_ir"],
                "properties": {
                    "tipo":           {"type": "string"},
                    "devedor":        {"type": "string"},
                    "tipo_valor":     {"type": "string"},
                    "base_apuracao":  {"type": "string"},
                    "percentual":     {"type": ["number","null"]},
                    "valor_informado":{"type": ["number","null"]},
                    "apurar_ir":      {"type": "boolean"},
                },
            },
        },
        "honorarios_periciais": {"type": ["number","null"]},
        "correcao_juros": {
            "type": "object", "additionalProperties": False,
            "required": ["indice_correcao","base_juros","taxa_juros","jam_fgts","confianca"],
            "properties": {
                "indice_correcao": {"type": ["string","null"]},
                "base_juros":      {"type": ["string","null"]},
                "taxa_juros":      {"type": ["string","null"]},
                "jam_fgts":        {"type": ["boolean","null"]},
                "confianca":       {"type": "number"},
            },
        },
        "contribuicao_social": {
            "type": "object", "additionalProperties": False,
            "required": ["apurar_segurado_salarios_devidos","cobrar_do_reclamante",
                         "com_correcao_trabalhista","apurar_sobre_salarios_pagos",
                         "lei_11941","confianca"],
            "properties": {
                "apurar_segurado_salarios_devidos": {"type": "boolean"},
                "cobrar_do_reclamante":             {"type": "boolean"},
                "com_correcao_trabalhista":         {"type": "boolean"},
                "apurar_sobre_salarios_pagos":      {"type": "boolean"},
                "lei_11941":                        {"type": ["boolean","null"]},
                "confianca":                        {"type": "number"},
            },
        },
        "imposto_renda": {
            "type": "object", "additionalProperties": False,
            "required": ["apurar","tributacao_exclusiva","regime_de_caixa","tributacao_em_separado",
                         "deducao_inss","deducao_honorarios_reclamante","deducao_pensao_alimenticia",
                         "valor_pensao","meses_tributaveis","dependentes","confianca"],
            "properties": {
                "apurar":                         {"type": "boolean"},
                "tributacao_exclusiva":            {"type": ["boolean","null"]},
                "regime_de_caixa":                {"type": ["boolean","null"]},
                "tributacao_em_separado":          {"type": ["boolean","null"]},
                "deducao_inss":                   {"type": ["boolean","null"]},
                "deducao_honorarios_reclamante":   {"type": ["boolean","null"]},
                "deducao_pensao_alimenticia":      {"type": ["boolean","null"]},
                "valor_pensao":                   {"type": ["number","null"]},
                "meses_tributaveis":              {"type": ["integer","null"]},
                "dependentes":                    {"type": ["integer","null"]},
                "confianca":                      {"type": "number"},
            },
        },
        "historico_salarial": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["data_inicio","data_fim","valor"],
                "properties": {
                    "data_inicio": {"type": "string"},
                    "data_fim":    {"type": "string"},
                    "valor":       {"type": "number"},
                },
            },
        },
        "faltas": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["data_inicial","data_final","justificada","descricao"],
                "properties": {
                    "data_inicial": {"type": "string"},
                    "data_final":   {"type": "string"},
                    "justificada":  {"type": "boolean"},
                    "descricao":    {"type": ["string","null"]},
                },
            },
        },
        "ferias": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["situacao","periodo_inicio","periodo_fim","abono","dobra"],
                "properties": {
                    "situacao":       {"type": "string"},
                    "periodo_inicio": {"type": "string"},
                    "periodo_fim":    {"type": "string"},
                    "abono":          {"type": "boolean"},
                    "dobra":          {"type": "boolean"},
                },
            },
        },
        "campos_ausentes": {"type": "array", "items": {"type": "string"}},
        "alertas":         {"type": "array", "items": {"type": "string"}},
    },
}


# ── Validador de consistência da sentença extraída ───────────────────────────

class ValidadorSentenca:
    """
    Valida consistência do JSON extraído da sentença trabalhista.
    Baseado no skill juridical-nlp-extractor.
    """

    @staticmethod
    def validar(dados: dict) -> tuple[bool, list[str]]:
        """Retorna (is_valid, lista_de_erros). Erros críticos devem bloquear o processamento."""
        erros: list[str] = []
        erros.extend(ValidadorSentenca._validar_datas(dados))
        erros.extend(ValidadorSentenca._validar_rescisao_verbas(dados))
        erros.extend(ValidadorSentenca._validar_valores(dados))
        return len(erros) == 0, erros

    @staticmethod
    def _parse_data(d: str | None) -> date | None:
        if not d:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(d, fmt).date()
            except ValueError:
                pass
        return None

    @staticmethod
    def _validar_datas(dados: dict) -> list[str]:
        erros = []
        cont = dados.get("contrato", {})
        adm = ValidadorSentenca._parse_data(cont.get("admissao"))
        dem = ValidadorSentenca._parse_data(cont.get("demissao"))
        if adm and dem:
            if dem < adm:
                erros.append(
                    f"CRÍTICO: data_demissao ({cont.get('demissao')}) anterior à "
                    f"data_admissao ({cont.get('admissao')})"
                )
            anos = (dem - adm).days / 365
            if anos > 50:
                erros.append(f"AVISO: contrato de {anos:.0f} anos — verificar datas")
        if adm and adm > date.today():
            erros.append(f"CRÍTICO: data_admissao no futuro ({cont.get('admissao')})")
        return erros

    @staticmethod
    def _validar_rescisao_verbas(dados: dict) -> list[str]:
        erros = []
        tipo = dados.get("contrato", {}).get("tipo_rescisao", "")
        verbas = {v.get("nome_sentenca", "").lower() for v in dados.get("verbas_deferidas", [])}
        if tipo == "justa_causa":
            if any("multa" in v and "40" in v for v in verbas):
                erros.append("INCONSISTÊNCIA: justa causa com multa 40% FGTS")
            if any("aviso prévio indenizado" in v for v in verbas):
                erros.append("INCONSISTÊNCIA: justa causa com aviso prévio indenizado")
        if tipo == "pedido_demissao":
            if any("multa" in v and "40" in v for v in verbas):
                erros.append("INCONSISTÊNCIA: pedido de demissão com multa 40% FGTS")
        return erros

    @staticmethod
    def _validar_valores(dados: dict) -> list[str]:
        erros = []
        for v in dados.get("verbas_deferidas", []):
            val = v.get("valor")
            if val is not None:
                if isinstance(val, (int, float)) and val < 0:
                    erros.append(f"CRÍTICO: valor negativo para {v.get('nome_sentenca')}: {val}")
                if isinstance(val, (int, float)) and val > 10_000_000:
                    erros.append(
                        f"AVISO: valor muito alto para {v.get('nome_sentenca')}: "
                        f"R$ {val:,.2f} — confirmar"
                    )
        return erros

    @staticmethod
    def itens_baixa_confianca(dados: dict, threshold: float = 0.70) -> list[dict]:
        """Retorna campos de seções com confiança abaixo do threshold."""
        incertos = []
        secoes = ["processo", "contrato", "fgts", "correcao_juros"]
        for sec in secoes:
            obj = dados.get(sec, {})
            if isinstance(obj, dict):
                conf = obj.get("confianca", 1.0)
                if isinstance(conf, (int, float)) and conf < threshold:
                    incertos.append({
                        "secao": sec,
                        "confianca": conf,
                        "acao": "revisão manual necessária",
                    })
        for v in dados.get("verbas_deferidas", []):
            conf = v.get("confianca", 1.0)
            if isinstance(conf, (int, float)) and conf < threshold:
                incertos.append({
                    "secao": f"verbas_deferidas[{v.get('nome_sentenca', '?')}]",
                    "confianca": conf,
                    "acao": "revisão manual necessária",
                })
        return incertos


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
        return {"_erro_llm": "ANTHROPIC_API_KEY não configurada",
                "alertas": ["ANTHROPIC_API_KEY não configurada — processamento impossível"]}

    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=90.0)

    try:
        kwargs: dict = dict(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            temperature=0.0,
            system=_SYSTEM_PROMPT_RELATORIO,
            messages=[{
                "role": "user",
                "content": _RELATORIO_PROMPT.format(texto=texto_relatorio[:25000]),
            }],
        )
        # Nota: output_config removido — schema de extração tem >16 union types (limite API Anthropic)
        # O parser tolerante _limpar_e_parsear_json cobre todos os casos de JSON malformado.
        resposta = cliente.messages.create(**kwargs)

        conteudo = resposta.content[0].text.strip()
        dados = _limpar_e_parsear_json(conteudo)
        dados = _validar_e_completar(dados)
        if "alertas" not in dados:
            dados["alertas"] = []
        dados["alertas"].insert(0, "Dados extraídos de relatório estruturado (alta confiança).")
        return dados

    except json.JSONDecodeError as e:
        logger.warning(f"JSON inválido no relatório estruturado: {e}")
        return {"_erro_llm": str(e), "alertas": [f"Relatório com JSON inválido: {e}"]}
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

    # Honorários — vários padrões de sentença
    hon_pct = None
    for pat in [
        r"(?i)honorários\s+(?:advocatícios|sucumbenciais)[^.;]{0,80}?(\d+(?:[,.]\d+)?)\s*%",
        r"(?i)(\d+(?:[,.]\d+)?)\s*%\s*(?:\([^)]+\)\s*)?(?:de\s+)?honorários",
        r"(?i)condeno[^.;]{0,60}honorários[^.;]{0,60}?(\d+(?:[,.]\d+)?)\s*%",
        r"(?i)(?:arbitro|fixo|fixar)\s+honorários[^.;]{0,60}?(\d+(?:[,.]\d+)?)\s*%",
        r"(?i)honorários[^.;]{0,40}?no\s+percentual\s+de\s+(\d+(?:[,.]\d+)?)\s*%",
    ]:
        m = re.search(pat, texto)
        if m:
            hon_pct = float(m.group(1).replace(",", ".")) / 100
            break
    resultado["honorarios_percentual"] = hon_pct

    # Parte devedora dos honorários
    if re.search(r"(?i)sucumb[êe]ncia\s+rec[íi]proca", texto):
        resultado["honorarios_parte_devedora"] = "Ambos"
    elif re.search(r"(?i)sucumb[êe]ncia\s+(?:integral\s+)?(?:da\s+)?reclamad[ao]", texto):
        resultado["honorarios_parte_devedora"] = "Reclamado"
    elif re.search(r"(?i)sucumb[êe]ncia\s+(?:integral\s+)?(?:do\s+|da\s+)?reclamante", texto):
        resultado["honorarios_parte_devedora"] = "Reclamante"
    else:
        resultado["honorarios_parte_devedora"] = None

    # Correção monetária e juros — detecção de padrões comuns
    txt_lower = texto.lower()
    if any(p in txt_lower for p in ["adc 58", "adc nº 58", "tabela jt", "tabela única mensal",
                                      "selic a partir", "ipca-e até o ajuizamento"]):
        resultado["indice_correcao"] = "Tabela JT Unica Mensal"
        resultado["taxa_juros"] = "Selic"
    elif re.search(r"(?i)selic\b.*(?:corre[çc][ãa]o|atualiza[çc][ãa]o)", texto) or \
         re.search(r"(?i)(?:corre[çc][ãa]o|atualiza[çc][ãa]o).*\bselic\b", texto):
        resultado["indice_correcao"] = "Selic"
        resultado["taxa_juros"] = "Selic"
    elif re.search(r"(?i)ipca[- ]?e\b.*juros\s+(?:de\s+)?1\s*%", texto) or \
         re.search(r"(?i)ipca[- ]?e\b.*juros\s+(?:de\s+)?um\s+por\s+cento", texto):
        resultado["indice_correcao"] = "IPCA-E"
        resultado["taxa_juros"] = "Juros Padrao"
    elif re.search(r"(?i)\btr\b.*juros\s+(?:de\s+)?1\s*%", texto) or \
         re.search(r"(?i)trct\b", texto):
        resultado["indice_correcao"] = "TRCT"
        resultado["taxa_juros"] = "Juros Padrao"
    elif re.search(r"(?i)ipca[- ]?e\b", texto):
        resultado["indice_correcao"] = "IPCA-E"
        resultado["taxa_juros"] = None
    else:
        resultado["indice_correcao"] = None
        resultado["taxa_juros"] = None

    # JAM-FGTS
    resultado["jam_fgts"] = bool(re.search(r"(?i)\bjam\b|juros\s+(?:sobre|do)\s+atraso.*fgts", texto))

    # Contribuição social — responsabilidade
    if re.search(r"(?i)responsabilidade\s+(?:de\s+)?ambas?\s+as?\s+partes?", texto):
        resultado["contrib_responsabilidade"] = "Ambos"
    elif re.search(r"(?i)(?:apenas|só|somente)\s+(?:o\s+)?empregador", texto):
        resultado["contrib_responsabilidade"] = "Empregador"
    elif re.search(r"(?i)dedu[çc][ãa]o\s+na\s+fonte|desconto\s+(?:do|no)\s+salário", texto):
        resultado["contrib_responsabilidade"] = "Ambos"
    else:
        resultado["contrib_responsabilidade"] = None

    # Lei 11.941/2009
    resultado["lei_11941"] = bool(re.search(r"(?i)lei\s+(?:n[oº°]?\s*)?11\.941", texto))

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
                trecho = extra["conteudo"][:8000]  # limite por documento
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

        content_blocks.append({
            "type": "text",
            "text": prompt_sentenca,
            "cache_control": {"type": "ephemeral"},
        })

        # Nota: output_config removido — schema tem >16 union types (limite API Anthropic)
        resposta = cliente.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            temperature=CLAUDE_EXTRACTION_TEMPERATURE,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content_blocks}],
        )
        conteudo = resposta.content[0].text.strip()
        return _limpar_e_parsear_json(conteudo)

    except Exception as e:
        logger.warning(f"Falha na extração via IA: {e}")
        return {"_erro_llm": str(e), "alertas": [f"Falha na extração via IA: {e}"]}


# ── Extração via Gemini (Google) ──────────────────────────────────────────────

def _extrair_via_gemini(
    texto: str,
    extras: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Usa Gemini 2.5 Flash para extração profunda de parâmetros jurídicos.
    Usa o novo SDK google-genai (substituto do descontinuado google-generativeai).
    Ativado quando GEMINI_API_KEY está configurada em .env.
    """
    if not GEMINI_API_KEY:
        return {}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Montar prompt completo
        secoes_extras: list[str] = []
        for i, extra in enumerate(extras or [], start=1):
            if extra.get("tipo") == "texto" and extra.get("conteudo"):
                ctx = extra.get("contexto", "").strip()
                ctx_str = f" [{ctx}]" if ctx else ""
                trecho = extra["conteudo"][:8000]
                secoes_extras.append(
                    f"=== DOCUMENTO ADICIONAL {i}{ctx_str} ===\n{trecho}"
                )

        prompt = _SYSTEM_PROMPT + "\n\n" + _EXTRACTION_PROMPT.format(texto=texto[:25000])
        if secoes_extras:
            prompt += (
                "\n\n" + "\n\n".join(secoes_extras) +
                "\n\nOs documentos adicionais acima complementam a sentença. "
                "Use-os para preencher ou corrigir campos ausentes ou com baixa confiança."
            )

        def _chamar_gemini():
            return client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=4096,
                ),
            )

        # Timeout de 30s: evita travar quando Railway não tem Gemini configurado
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_chamar_gemini)
            try:
                resp = fut.result(timeout=30)
            except concurrent.futures.TimeoutError:
                raise TimeoutError("Gemini API timeout após 30s — usando fallback Claude")
        return _limpar_e_parsear_json(resp.text)

    except Exception as e:
        logger.warning(f"Falha na extração via Gemini: {e}")
        return {"_erro_llm": str(e), "alertas": [f"Falha na extração via Gemini: {e}"]}


# ── Extração nativa de PDF via base64 ────────────────────────────────────────

_EXTRACTION_PROMPT_NATIVO = (
    "Extraia todos os dados desta sentença trabalhista para preenchimento completo do PJE-Calc. "
    "Inclua todas as verbas deferidas, datas, salários, honorários, INSS, IR e correção monetária. "
    "Siga rigorosamente o schema JSON retornado. "
    "Responda APENAS com o JSON no formato especificado — sem markdown, sem texto extra."
)


def _extrair_via_llm_pdf(
    pdf_bytes: bytes,
    extras: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Extração nativa de PDF: envia o arquivo diretamente ao Claude via base64.
    Não converte para texto antes — Claude lê o PDF nativamente (até 32 MB / 100 págs).
    Usa cache_control ephemeral no documento para multi-pass barato.
    Usa Structured Outputs para garantir JSON válido sem parsing tolerante.
    """
    if not ANTHROPIC_API_KEY:
        return {}

    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=90.0)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    content_blocks: list[dict] = [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_b64,
            },
            "cache_control": {"type": "ephemeral"},
        },
    ]

    # Documentos extras (imagens ou textos complementares)
    for extra in extras or []:
        if extra.get("tipo") == "imagem":
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": extra.get("mime_type", "image/jpeg"),
                    "data": extra["conteudo"],
                },
            })
        elif extra.get("tipo") == "texto" and extra.get("conteudo"):
            ctx = extra.get("contexto", "")
            content_blocks.append({
                "type": "text",
                "text": f"=== DOCUMENTO COMPLEMENTAR{(' [' + ctx + ']') if ctx else ''} ===\n{extra['conteudo'][:8000]}",
            })

    content_blocks.append({
        "type": "text",
        "text": _EXTRACTION_PROMPT_NATIVO,
    })

    try:
        # Nota: output_config removido — schema tem >16 union types (limite API Anthropic)
        resposta = cliente.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            temperature=0.0,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content_blocks}],
        )
        return _limpar_e_parsear_json(resposta.content[0].text.strip())
    except Exception as e:
        logger.warning(f"Falha na extração nativa de PDF: {e}")
        return {"_erro_llm": str(e), "alertas": [str(e)]}


def extrair_dados_sentenca_pdf(
    pdf_path: str,
    sessao_id: str | None = None,
    extras: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Ponto de entrada público para extração direta de PDF.
    Envia o PDF nativo ao Claude (sem conversão para texto).
    Aplica validação, migração de schema legado e multi-pass para campos incertos.
    """
    import os
    sessao_id = sessao_id or str(uuid.uuid4())

    pdf_bytes = open(pdf_path, "rb").read()
    dados = _extrair_via_llm_pdf(pdf_bytes, extras=extras)

    if "_erro_llm" in dados or dados.get("_erro_ia"):
        # IA indisponível → bloquear; não cair em extração via texto (produziria dados incompletos)
        logger.error("Extração nativa de PDF falhou — processamento bloqueado")
        return {
            "_erro_ia": True,
            "alertas": dados.get("alertas", []) + [
                "BLOQUEADO: extração via IA indisponível. "
                "Verifique créditos da API Anthropic e reprocesse o documento."
            ],
            "campos_ausentes": [],
            "verbas_deferidas": [],
            "historico_salarial": [],
            "faltas": [],
            "ferias": [],
            "honorarios": [],
        }

    dados = _validar_e_completar(dados)

    # Multi-pass para campos incertos (reusa cache ephemeral — custo baixo)
    incertos = ValidadorSentenca.itens_baixa_confianca(dados, threshold=0.70)
    if incertos and len(incertos) <= 5:
        logger.info(f"Multi-pass: refinando {len(incertos)} campos incertos…")
        tipos_incertos = [i["secao"] for i in incertos]
        prompt_refino = (
            f"Foque especificamente nestas seções com baixa confiança: {tipos_incertos}. "
            "Para cada uma, cite o trecho EXATO da sentença que fundamenta o valor extraído. "
            "Se não houver menção no documento, confirme explicitamente que não aparece."
        )
        content_refino: list[dict] = [
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(pdf_bytes).decode()},
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": prompt_refino},
        ]
        try:
            cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0)
            resp = cliente.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                temperature=0.0,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content_refino}],
            )
            logger.info(f"Multi-pass concluído: {resp.content[0].text[:200]}")
        except Exception as e:
            logger.warning(f"Multi-pass falhou (não crítico): {e}")

    # Validação final
    valido, erros = ValidadorSentenca.validar(dados)
    if erros:
        dados.setdefault("alertas", []).extend(erros)

    return dados


# ── Funções de migração (retrocompatibilidade) ────────────────────────────────

def _migrar_honorarios_legado(hon: dict) -> list[dict]:
    """
    Converte o schema antigo {percentual, parte_devedora, valor_fixo} para a lista de registros
    compatível com o PJE-Calc (sem opção "Ambos" — cada devedor é um registro separado).
    """
    if not hon or not isinstance(hon, dict):
        return []
    percentual = hon.get("percentual")
    valor_fixo = hon.get("valor_informado") or hon.get("valor_fixo")
    parte = (hon.get("parte_devedora") or "Reclamado").strip()
    tipo_valor = "CALCULADO" if percentual is not None else "INFORMADO"

    def _registro(devedor: str, base: str) -> dict:
        return {
            "tipo": hon.get("tipo") or "SUCUMBENCIAIS",
            "devedor": devedor,
            "tipo_valor": tipo_valor,
            "base_apuracao": base,
            "percentual": percentual,
            "valor_informado": valor_fixo,
            "apurar_ir": hon.get("apurar_ir", False),
        }

    if parte in ("Ambos", "ambos", "AMBOS"):
        return [
            _registro("RECLAMADO", "Condenação"),
            _registro("RECLAMANTE", "Verbas Não Compõem Principal"),
        ]
    if parte in ("Reclamante", "RECLAMANTE"):
        return [_registro("RECLAMANTE", "Verbas Não Compõem Principal")]
    # Padrão: Reclamado
    return [_registro("RECLAMADO", "Condenação")]


def _migrar_inss_legado(cs: dict) -> dict:
    """
    Converte o schema antigo {responsabilidade: "Ambos|Empregador|Empregado"}
    para booleans individuais compatíveis com os checkboxes do PJE-Calc.
    """
    resp = (cs.get("responsabilidade") or "Ambos").strip()
    novo = {k: v for k, v in cs.items() if k != "responsabilidade"}
    if resp in ("Ambos", "ambos"):
        novo.setdefault("apurar_segurado_salarios_devidos", True)
        novo.setdefault("cobrar_do_reclamante", True)
        novo.setdefault("com_correcao_trabalhista", True)
        novo.setdefault("apurar_sobre_salarios_pagos", False)
    elif resp in ("Empregador",):
        novo.setdefault("apurar_segurado_salarios_devidos", True)
        novo.setdefault("cobrar_do_reclamante", False)
        novo.setdefault("com_correcao_trabalhista", True)
        novo.setdefault("apurar_sobre_salarios_pagos", False)
    else:  # Empregado
        novo.setdefault("apurar_segurado_salarios_devidos", True)
        novo.setdefault("cobrar_do_reclamante", True)
        novo.setdefault("com_correcao_trabalhista", True)
        novo.setdefault("apurar_sobre_salarios_pagos", False)
    return novo


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

    # Honorários — migrar legado dict → list se necessário
    hon = llm.get("honorarios", [])
    if isinstance(hon, dict):
        hon = _migrar_honorarios_legado(hon)
        llm["honorarios"] = hon
    # Fallback regex: se LLM retornou lista vazia e regex detectou honorários
    if not hon and regex.get("honorarios_percentual") is not None:
        parte = regex.get("honorarios_parte_devedora") or "Reclamado"
        llm["honorarios"] = _migrar_honorarios_legado({
            "percentual": regex["honorarios_percentual"],
            "parte_devedora": parte,
        })

    # Correção monetária e juros — regex como fallback
    cj = llm.get("correcao_juros", {})
    if cj.get("indice_correcao") is None and regex.get("indice_correcao") is not None:
        cj["indice_correcao"] = regex["indice_correcao"]
    if cj.get("taxa_juros") is None and regex.get("taxa_juros") is not None:
        cj["taxa_juros"] = regex["taxa_juros"]
    if not cj.get("jam_fgts") and regex.get("jam_fgts"):
        cj["jam_fgts"] = True
    llm["correcao_juros"] = cj

    # Contribuição social — migrar legado "responsabilidade" → booleans se necessário
    cs = llm.get("contribuicao_social", {})
    if "responsabilidade" in cs:
        cs = _migrar_inss_legado(cs)
    if not cs.get("lei_11941") and regex.get("lei_11941"):
        cs["lei_11941"] = True
    llm["contribuicao_social"] = cs

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
        "honorarios": _migrar_honorarios_legado({
            "percentual": regex.get("honorarios_percentual"),
            "parte_devedora": regex.get("honorarios_parte_devedora"),
        }) if regex.get("honorarios_percentual") else [],
        "honorarios_periciais": None,
        "correcao_juros": {
            "indice_correcao": regex.get("indice_correcao"),
            "base_juros": "Verbas",
            "taxa_juros": regex.get("taxa_juros"),
            "jam_fgts": regex.get("jam_fgts") or None,
            "confianca": 0.5,
        },
        "contribuicao_social": {
            "apurar_segurado_salarios_devidos": True,
            "cobrar_do_reclamante": True,
            "com_correcao_trabalhista": True,
            "apurar_sobre_salarios_pagos": False,
            "lei_11941": regex.get("lei_11941") or None,
            "confianca": 0.5,
        },
        "imposto_renda": {
            "apurar": False,
            "tributacao_exclusiva": None,
            "regime_de_caixa": None,
            "tributacao_em_separado": None,
            "deducao_inss": None,
            "deducao_honorarios_reclamante": None,
            "deducao_pensao_alimenticia": None,
            "valor_pensao": None,
            "meses_tributaveis": None,
            "dependentes": None,
            "confianca": 0.5,
        },
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
    "honorarios_periciais",
    "contrato.carga_horaria",
    "imposto_renda.dependentes",
    "imposto_renda.meses_tributaveis",
    "aviso_previo.prazo_dias",
    "contribuicao_social.lei_11941",
    "fgts.multa_467",
    "processo.municipio",   # útil mas não bloqueia cálculo
    "processo.vara",
}


def _campo_tem_valor(dados: dict[str, Any], chave: str) -> bool:
    """Verifica se um campo pontilhado (ex: 'processo.estado') tem valor não-nulo no dict."""
    partes = chave.split(".")
    obj = dados
    for p in partes:
        if not isinstance(obj, dict):
            return False
        obj = obj.get(p)
    return bool(obj)


def _validar_e_completar(dados: dict[str, Any]) -> dict[str, Any]:
    """
    Identifica campos obrigatórios ausentes e campos com baixa confiança.
    Preenche 'campos_ausentes' e 'alertas'.
    """
    # Filtrar campos_ausentes recebidos do LLM: manter apenas os que realmente estão vazios
    campos_ausentes_llm = dados.get("campos_ausentes", [])
    campos_ausentes = [c for c in campos_ausentes_llm if not _campo_tem_valor(dados, c)]
    alertas = dados.get("alertas", [])

    for secao, campo in _CAMPOS_OBRIGATORIOS:
        chave = f"{secao}.{campo}"
        valor = dados.get(secao, {}).get(campo)
        if not valor and chave not in campos_ausentes:
            campos_ausentes.append(chave)

    # Verificar confiança abaixo do limiar (honorarios é lista — não tem confianca própria)
    for secao in ["processo", "contrato", "fgts", "correcao_juros"]:
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

    # Aplicar padrões inteligentes para campos frequentemente não extraídos

    # Contribuição social: migrar legado "responsabilidade" → booleans; aplicar padrão legal
    cs = dados.get("contribuicao_social", {})
    if "responsabilidade" in cs:
        cs = _migrar_inss_legado(cs)
    # Aplicar padrão legal (empregado e empregador cada qual sua quota)
    cs.setdefault("apurar_segurado_salarios_devidos", True)
    cs.setdefault("cobrar_do_reclamante", True)
    cs.setdefault("com_correcao_trabalhista", True)
    cs.setdefault("apurar_sobre_salarios_pagos", False)
    dados["contribuicao_social"] = cs
    # Migrar honorários legado se necessário
    hon = dados.get("honorarios", {})
    if isinstance(hon, dict):
        dados["honorarios"] = _migrar_honorarios_legado(hon)

    # Correção/juros: se ausentes e há verbas deferidas, aplicar padrão ADC 58 com alerta
    cj = dados.get("correcao_juros", {})
    if not cj.get("indice_correcao") and dados.get("verbas_deferidas"):
        cj["indice_correcao"] = "Tabela JT Unica Mensal"
        cj["taxa_juros"] = "Selic"
        cj.setdefault("base_juros", "Verbas")
        dados["correcao_juros"] = cj
        alertas.append(
            "Índice de correção não identificado — aplicado padrão ADC 58 "
            "(Tabela JT Única Mensal + SELIC). Verifique na sentença."
        )

    # Remover campos opcionais que o LLM pode ter incluído indevidamente
    campos_ausentes = [c for c in campos_ausentes if c not in _CAMPOS_OPCIONAIS]

    dados["campos_ausentes"] = list(set(campos_ausentes))
    dados["alertas"] = alertas

    # ── Detecção de inconsistências críticas ──────────────────────────────────
    inconsistencias: list[str] = []

    cont = dados.get("contrato", {})
    admissao = cont.get("admissao")
    demissao = cont.get("demissao")
    tipo_rescisao = cont.get("tipo_rescisao") or ""

    # 1. Demissão anterior à admissão
    if admissao and demissao:
        try:
            from datetime import datetime
            fmt = "%d/%m/%Y"
            dt_adm = datetime.strptime(admissao, fmt)
            dt_dem = datetime.strptime(demissao, fmt)
            if dt_dem < dt_adm:
                inconsistencias.append(
                    f"Data de demissão ({demissao}) é anterior à admissão ({admissao}). "
                    "Verifique as datas na sentença."
                )
        except ValueError:
            pass  # datas em formato inesperado — ignorar comparação

    # 2. Justa causa + multa de 40% FGTS (incompatíveis juridicamente)
    if tipo_rescisao == "justa_causa":
        fgts = dados.get("fgts", {})
        if fgts.get("multa_40") is True:
            inconsistencias.append(
                "Tipo de rescisão 'justa_causa' incompatível com multa de 40% do FGTS. "
                "Multa 40% é devida apenas em dispensa sem justa causa (art. 18 §1º FGTS)."
            )

    # 3. Justa causa + aviso prévio indenizado (incompatíveis)
    if tipo_rescisao == "justa_causa":
        aviso = dados.get("aviso_previo", {})
        if aviso.get("tipo") == "indenizado":
            inconsistencias.append(
                "Tipo de rescisão 'justa_causa' incompatível com aviso prévio indenizado. "
                "Em justa causa, não há aviso prévio (art. 482 CLT)."
            )

    # 4. Pedido de demissão + multa de 40% FGTS (incompatíveis)
    if tipo_rescisao == "pedido_demissao":
        fgts = dados.get("fgts", {})
        if fgts.get("multa_40") is True:
            inconsistencias.append(
                "Tipo de rescisão 'pedido_demissao' incompatível com multa de 40% do FGTS. "
                "Multa 40% é devida apenas em dispensa sem justa causa."
            )

    dados["inconsistencias_criticas"] = inconsistencias

    return dados
