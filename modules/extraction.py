# modules/extraction.py — Módulo de Extração Jurídica (NLP + regex + LLM)
# Manual Técnico PJE-Calc, Seção 2 e 3

from __future__ import annotations

import base64
import concurrent.futures
import json
import logging
import re
import uuid
from dataclasses import dataclass, field as _dc_field
from datetime import datetime, date
from typing import Any, TYPE_CHECKING

try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.llm_orchestrator import LLMOrchestrator

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
        resultado = _sanitizar_chaves(json.loads(parcial))
        # Marcar como auto-reparado para que downstream saiba que os dados podem estar incompletos
        logger.warning(
            f"JSON auto-reparado (fechamento de {abre} chaves + {fecha_colchete} colchetes). "
            "Dados podem estar incompletos."
        )
        if isinstance(resultado, dict):
            resultado["_json_auto_reparado"] = True
        return resultado
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
- "Cidade/Comarca:" → processo.municipio (APENAS nome da cidade, sem UF e sem sufixo de vara)
- "Estado:" → processo.estado (2 letras, ex: CE)
- "Reclamante:" → processo.reclamante (apenas nome, sem CPF)
- CPF do reclamante se explicitado → processo.cpf_reclamante (formato: "000.000.000-00")
- "Reclamada:" ou "Reclamado:" → processo.reclamado (apenas razão social/nome, sem CNPJ)
- CNPJ da reclamada se explicitado → processo.cnpj_reclamado (formato: "00.000.000/0000-00")
- "Data de Distribuição/Autuação:" ou "Data de Ajuizamento:" → contrato.ajuizamento E processo.autuado_em
- "Autuado em:" / "Data de autuação:" / "Data de distribuição:" → processo.autuado_em (DD/MM/AAAA)
  ⚠️ Se não houver campo "Autuado em" separado, usar a mesma data de ajuizamento para processo.autuado_em
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
Cada entrada representa uma BASE DE CÁLCULO no PJE-Calc com nome, período e valor mensal.
Pode haver MÚLTIPLOS históricos no mesmo processo (ex: "Salário" + "Salário Devido" para
equiparação salarial, "Adicional Noturno Pago" para diferenças, piso salarial da norma coletiva).

  historico_salarial: [
    {{"nome": "Salário", "data_inicio": "01/01/2023", "data_fim": "31/08/2024", "valor": 1518.00, "variavel": false, "incidencia_fgts": true, "incidencia_cs": true}},
    {{"nome": "Comissões", "data_inicio": "01/01/2023", "data_fim": "31/08/2024", "valor": 3500.00, "variavel": true, "incidencia_fgts": true, "incidencia_cs": true}}
  ]

- "nome": tipo da base ("Salário", "Comissões", "Salário Pago", "Salário Devido", "Adicional Noturno Pago", etc.)
  Se não especificado na sentença, usar "Salário".
- "variavel": true se a parcela varia mês a mês (comissões, horas extras, gorjetas, gratificações variáveis).
  false (default) para salário fixo. Se a sentença apresenta tabela com valores diferentes a cada mês
  para a mesma parcela, marcar variavel=true.
- "incidencia_fgts": true se a parcela incide para fins de FGTS (default: true para salário)
- "incidencia_cs": true se incide para Contribuição Social/INSS (default: true para salário)
- Se salário uniforme durante todo o contrato → historico_salarial com UMA entrada do período completo
- Se houver equiparação salarial, desvio de função ou piso normativo: criar entradas SEPARADAS
  com nomes distintos (ex: "Salário Pago" e "Salário Devido")

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
      IMPORTANTE: PRESERVAR o nome original da sentença em `nome_sentenca`. Exemplos que
      DEVEM mapear para a verba Expresso "HORAS EXTRAS 50%" (via classificador):
        - "HORAS EXTRAS (ALÉM 8ª DIÁRIA E 44ª SEMANAL)"
        - "HE 50%", "Horas Extraordinárias", "Horas Extras 50%"
      Sempre que a sentença mencionar "horas extras"/"HE"/"extraordinárias", marque a
      verba como Principal e NÃO como Reflexa. Os RSR/13º/Férias+1/3 sobre HE são
      reflexos e devem ser extraídos com tipo="Reflexa" e verba_principal_ref apontando
      para o nome_sentenca da HE principal.
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
    sumula_439: true se a sentença determinar juros desde o ajuizamento (Súmula 439 TST);
                false (padrão) se juros desde o arbitramento/vencimento (danos morais sem Súmula 439,
                danos materiais mensais, etc.). Aplicar apenas quando a sentença mencionar
                explicitamente a Súmula 439 ou "juros desde o ajuizamento".

**SEÇÃO 4 — FGTS E MULTA RESCISÓRIA** → preenche "fgts":
- "Alíquota FGTS:" → fgts.aliquota (ex: 8% → 0.08)
- "Multa de 40%: Sim" → fgts.multa_40 = true (demissão sem justa causa — padrão)
- "Multa de 40%: Não" → fgts.multa_40 = false
- "Multa de 20%" → fgts.multa_40 = true, fgts.multa_20 = true (estabilidade provisória: CIPA, gestante, acidentário, etc.)
  ATENÇÃO: quando a sentença determina multa de 20% (não 40%), marcar AMBOS multa_40=true (habilita a seção de multa no PJE-Calc) e multa_20=true (seleciona 20% em vez de 40%).
- saldo_fgts: saldo das contas FGTS do empregado, se informado na sentença (float; null se não mencionado)
- incidencia_13o_dezembro: true (padrão) — indica que o FGTS sobre o 13º deve ser recolhido na
  competência de dezembro (ou no mês do desligamento, se antes de dezembro). A base FGTS daquele
  mês será: salário mensal + 13º proporcional (nº meses trabalhados naquele ano / 12).
  O PJE-Calc não faz esse ajuste automaticamente — o agente adiciona depois via página "Ocorrências
  do FGTS". Emitir false somente se a sentença expressamente afastar incidência de FGTS sobre o 13º
  (hipótese muito rara).

**SEÇÃO 5 — MULTAS TRABALHISTAS**:
- "Multa art. 467 CLT — Deferida" → fgts.multa_467 = true (campo opcional)
- "Multa art. 467 CLT — Indeferida" → fgts.multa_467 = false

**SEÇÃO 5B — JUSTIÇA GRATUITA** → preenche "justica_gratuita":
- Buscar "benefício da justiça gratuita", "gratuidade judiciária", "assistência judiciária gratuita"
- justica_gratuita_reclamante: true quando deferida ao reclamante (autor)
- justica_gratuita_reclamado: true quando deferida ao reclamado (réu) — raro mas possível
- Se não mencionada ou indeferida: false
- IMPORTANTE para honorários: quando uma parte tem justiça gratuita, a exigibilidade dos
  honorários advocatícios a que ela foi condenada fica SUSPENSA (art. 791-A, §4º, CLT).

**SEÇÃO 6 — HONORÁRIOS ADVOCATÍCIOS** → preenche "honorarios" (LISTA de registros):
⚠️ O PJE-Calc NÃO tem opção "Ambos" — cada honorário é um registro separado por devedor.
- Sucumbência recíproca → gerar DOIS registros na lista:
    [{{"devedor": "RECLAMADO", "base_apuracao": "BRUTO", ...}},
     {{"devedor": "RECLAMANTE", "base_apuracao": "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL", ...}}]
- Sucumbência integral da reclamada → um registro com devedor="RECLAMADO"
- Sucumbência integral do reclamante → um registro com devedor="RECLAMANTE"
- Se indeferidos ou não mencionados → honorarios = []
- tipo: "SUCUMBENCIAIS" (padrão — condenação em honorários pelo juiz) | "CONTRATUAIS" (raro)
- tipo_valor: "CALCULADO" quando há percentual | "INFORMADO" quando há valor fixo em R$
- base_apuracao (usar valores EXATOS do select do PJE-Calc — copiar literalmente):
    RECLAMADO + SUCUMBENCIAIS: "BRUTO" (padrão — % sobre o valor da condenação)
                              | "BRUTO_MENOS_CONTRIBUICAO_SOCIAL"
                              | "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA"
    RECLAMANTE + SUCUMBENCIAIS: "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL" (padrão — % sobre Verbas que Não Compõem Principal)
                               | "BRUTO"
                               | "BRUTO_MENOS_CONTRIBUICAO_SOCIAL"
    CONTRATUAIS: "BRUTO" | "BRUTO_MENOS_CONTRIBUICAO_SOCIAL"
  ⚠️ Quando a sentença diz "sobre o valor da condenação" para AMBAS as partes →
     usar "BRUTO" para os dois registros
- percentual: float decimal (ex: 0.15 para 15%); null se tipo_valor=INFORMADO
- valor_informado: float; null se tipo_valor=CALCULADO
- apurar_ir: true quando os honorários forem tributáveis (advogado pessoa física)

**SEÇÃO 7 — HONORÁRIOS PERICIAIS** → preenche "honorarios_periciais" (campo top-level — NÃO colocar dentro do array "honorarios"):
- Buscar "honorários periciais", "honorário do perito", "laudo pericial", "assistente técnico"
- Se deferidos com valor explícito: honorarios_periciais = float (ex: 5000.00)
- Se indeferidos ou não mencionados: honorarios_periciais = null

**SEÇÃO 8 — CORREÇÃO MONETÁRIA E JUROS** → preenche "correcao_juros":
Mapeamento dos critérios da sentença para os enums do PJE-Calc:

CASOS MAIS COMUNS (em ordem de prevalência jurisprudencial):

1. ADC 58 + Lei 14.905/2024 — JURISPRUDÊNCIA MAJORITÁRIA ATUAL (E-ED-RR-20407-32.2015.5.04.0271):
   Indicadores: menção a "ADC 58", "E-ED-RR-20407", "Lei 14.905", "taxa legal",
   "IPCA-E na fase pré-judicial", "SELIC até 29/08/2024", "IPCA + taxa legal a partir de 30/08/2024",
   3 fases distintas (pré-judicial / ajuizamento-29.08.2024 / pós-30.08.2024),
   "art. 406 do CC", "SELIC - IPCA"
     lei_14905 = true
     indice_correcao = "IPCAE"
     indice_correcao_pos = "IPCA"
     taxa_juros = "TAXA_LEGAL"
     data_taxa_legal = "30/08/2024"
   ⚠️ PREENCHIMENTO NO PJe-Calc (a automação deve fazer combinações):
     CORREÇÃO: IPCAE até 29/08/2024 COMBINADO com IPCA a partir de 30/08/2024.
       Se admissão posterior a 30/08/2024 → usar somente IPCA.
     JUROS (depende da data de ajuizamento):
       Cenário A — Ajuizamento ANTES de 30/08/2024:
         - Pré-judicial: TRD_SIMPLES, combinado com SEM_JUROS a partir de 30/08/2024
         - Judicial Fase 1: SELIC do ajuizamento até 29/08/2024
         - Judicial Fase 2: TAXA_LEGAL a partir de 30/08/2024
       Cenário B — Ajuizamento DEPOIS de 30/08/2024:
         - Pré-judicial: TRD_SIMPLES
         - Judicial: TAXA_LEGAL a partir do ajuizamento

2. ADC 58 / critérios TST SEM menção à Lei 14.905 (sentenças anteriores a ago/2024):
   Indicadores: "ADC 58", "Tabela JT Única Mensal", "IPCA-E até o ajuizamento e SELIC a partir",
   "critérios da Justiça do Trabalho" — SEM mencionar "taxa legal" ou "Lei 14.905"
     lei_14905 = false
     indice_correcao = "TUACDT"
     taxa_juros = "SELIC"

3. Apenas SELIC para tudo ("atualizado pela SELIC", "taxa SELIC", sem distinguir fases):
     lei_14905 = false
     indice_correcao = "SELIC"
     taxa_juros = "SELIC"

4. IPCA-E + juros legais de 1% ao mês ("IPCA-E mais juros de 1% ao mês", "IPCA-E + juros
   moratórios de 1% ao mês"):
     lei_14905 = false
     indice_correcao = "IPCAE"
     taxa_juros = "JUROS_PADRAO"

5. TR + juros de 1% ao mês ("TR", "TRCT", "correção pela TR mais 1% ao mês"):
     lei_14905 = false
     indice_correcao = "TR"
     taxa_juros = "JUROS_PADRAO"

6. IPCA-E sem especificação de juros:
     lei_14905 = false
     indice_correcao = "IPCAE"
     taxa_juros = "JUROS_PADRAO"  (padrão quando índice é IPCAE)

NOTA: JUROS_PADRAO = Juros Padrão = 1% ao mês (juros legais trabalhistas — art. 39 Lei 8.177/91)
      SELIC = SELIC (Receita Federal) = taxa SELIC acumulada (absorve correção + juros)
      TAXA_LEGAL = Taxa Legal = SELIC − IPCA (juros reais, Lei 14.905/2024, vigência 30/08/2024)
      IPCA = índice de correção pós-Lei 14.905 (substitui IPCA-E a partir de 30/08/2024)

- correcao_juros.lei_14905: true quando a sentença aplica o regime da Lei 14.905/2024 (habilita
    combinações de índices no PJe-Calc). false quando usa regimes anteriores.
- correcao_juros.indice_correcao_pos: índice de correção a partir de 30/08/2024 (somente quando
    lei_14905=true). Valores: "IPCA" (padrão Lei 14.905). Se admissão > 30/08/2024: usar "IPCA" como
    índice único e indice_correcao pode ser null.
- correcao_juros.data_taxa_legal: "DD/MM/AAAA" — data marco a partir da qual se aplica TAXA_LEGAL.
    Padrão: "30/08/2024" (vigência Lei 14.905/2024). Informar SOMENTE quando taxa_juros = "TAXA_LEGAL".
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

**CUSTAS JUDICIAIS** → preenche "custas_judiciais":
⚠️ OBRIGATÓRIO: SEMPRE retornar este objeto — NÃO é verba, é configuração do PJE-Calc para apuração
de custas processuais. Custas são calculadas pelo sistema sobre o valor bruto da condenação.
Mesmo que a sentença não mencione custas ou fixe valor específico, retornar com os defaults abaixo.
- base: "Bruto Devido ao Reclamante" (padrão) ou "Bruto Devido ao Reclamante + Outros Débitos"
- reclamado_conhecimento: "CALCULADA" (padrão 2%) | "INFORMADA" | "NAO_SE_APLICA"
  Se a sentença fixar valor de custas, usar "CALCULADA" (o PJE-Calc calcula 2% automaticamente)
- reclamado_liquidacao: "NAO_SE_APLICA" (padrão) | "CALCULADA" (0,5%) | "INFORMADA"
- reclamante_conhecimento: "NAO_SE_APLICA" (padrão) | "CALCULADA" | "INFORMADA"
- percentual: float (ex: 0.02 para 2%) — padrão 0.02
- devedor: "RECLAMADO" (padrão) ou "RECLAMANTE"
  Defaults: base="Bruto Devido ao Reclamante", reclamado_conhecimento="CALCULADA",
  reclamado_liquidacao="NAO_SE_APLICA", reclamante_conhecimento="NAO_SE_APLICA", percentual=0.02

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

**DURAÇÃO DO TRABALHO / CARTÃO DE PONTO** → preenche "duracao_trabalho":
Extrair SEMPRE que houver condenação em horas extras, adicional noturno, intervalo intrajornada
ou qualquer parcela que dependa de jornada de trabalho.

- tipo_apuracao: "apuracao_jornada" (horários fixados) | "quantidade_fixa" (HE mensais/diárias)
- forma_apuracao_pjecalc: "HJD" | "SEM" | "FAV" | "MEN" | "HST" | "APH" | "NAP"
  Regra: "apuracao_jornada" → "FAV" (default) | "quantidade_fixa" → "NAP" | null → "NAP"
- preenchimento_jornada: "programacao_semanal" | "escala" | "livre"
  Regra: horários por dia → "programacao_semanal" | "escala 12x36" → "escala" | senão → "livre"
- escala_tipo: "12x12" | "12x24" | "12x36" | "12x48" | "5x1" | "6x1" | "8x2" | "outra" | null

GRADE SEMANAL (Programação Semanal — pares Entrada/Saída por dia):
- grade_semanal: objeto com a grade de horários praticados para o Cartão de Ponto do PJE-Calc.
  Cada dia da semana ("seg", "ter", "qua", "qui", "sex", "sab", "dom", "feriado") contém "turnos" —
  lista de pares entrada/saída (máximo 6 pares por dia). Os intervalos (almoço, descanso) são
  representados pela LACUNA entre a saída de um turno e a entrada do seguinte.
  Dias de folga: null.
  Exemplo: "07h às 17h com 1h de intervalo, seg a sex" →
    seg: turnos=[{{"entrada":"07:00","saida":"12:00"}},{{"entrada":"13:00","saida":"17:00"}}]
    (intervalo 12:00-13:00 implícito pela lacuna entre turnos)
  Exemplo: "12x36 das 07h às 19h com 1h intervalo" → usar preenchimento_jornada="escala" em vez de grade
  ⚠️ Se intervalo explícito (ex: "1h intervalo"), DIVIDIR a jornada em 2 turnos.
    Se 2 intervalos → 3 turnos. Se sem intervalo → 1 turno contínuo.
  ⚠️ Distribuir o intervalo simetricamente no meio da jornada quando a sentença não especifica horário exato.
    Ex: 07:00-17:00 com 1h intervalo → turno1 07:00-12:00, turno2 13:00-17:00

CAMPOS LEGADO (mantidos para compatibilidade — preenchidos automaticamente se grade_semanal presente):
- jornada_entrada: horário de início global (string "HH:MM")
- jornada_saida: horário de término global (string "HH:MM")
- intervalo_minutos: duração do intervalo intrajornada em MINUTOS (int)
- jornada_seg a jornada_dom: horas BRUTAS no local por dia da semana (float)
  Calcular: (horario_saida - horario_entrada) para cada dia mencionado.
  ⚠️ Esses valores são horas BRUTAS (sem descontar intervalo) — o PJE-Calc desconta o intervalo

- qt_horas_extras_mes: para tipo="quantidade_fixa", total de HE mensais (float)
- qt_horas_extras_dia: para tipo="quantidade_fixa", HE diárias (float)
- jornada_semanal_cartao: total de horas semanais para o cartão de ponto (float)
- jornada_mensal_cartao: média mensal de horas (float)
- adicional_he_percentual: percentual do adicional de horas extras (float, ex: 0.50 para 50%)
- trabalha_feriados: bool
- trabalha_domingos: bool
- apurar_hora_noturna: bool — true se condenação em adicional noturno ou trabalho noturno
- hora_inicio_noturno: string "HH:MM" (default "22:00" urbano)
- hora_fim_noturno: string "HH:MM" (default "05:00" urbano)
- reducao_ficta: bool (default true)
- prorrogacao_horario_noturno: bool
- periodo_cartao_inicio: data início do período do cartão de ponto (DD/MM/AAAA)
- periodo_cartao_fim: data fim do período do cartão de ponto (DD/MM/AAAA)
- considerar_feriados: bool — considerar feriados no cartão de ponto
- supressao_intervalo_intrajornada: bool — se há condenação em supressão de intervalo
- confianca: 0.0-1.0

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
    "multa_20": "true | false | null",
    "multa_467": "true | false | null",
    "saldo_fgts": "float | null",
    "incidencia_13o_dezembro": "true | false (padrão true — FGTS do 13º é recolhido na competência de dezembro; base de dezembro = salário + 13º proporcional. Emitir false apenas se a sentença expressamente afastar incidência de FGTS sobre o 13º.)",
    "confianca": 0.95
  }},
  "honorarios": [
    {{
      "tipo": "SUCUMBENCIAIS | CONTRATUAIS",
      "devedor": "RECLAMANTE | RECLAMADO",
      "tipo_valor": "CALCULADO | INFORMADO",
      "base_apuracao": "BRUTO | BRUTO_MENOS_CONTRIBUICAO_SOCIAL | BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA | VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
      "percentual": "float | null",
      "valor_informado": "float | null",
      "apurar_ir": "true | false"
    }}
  ],
  "honorarios_periciais": "float | null",
  "justica_gratuita": {{
    "reclamante": "true | false",
    "reclamado": "true | false"
  }},
  "correcao_juros": {{
    "lei_14905": "true | false (true quando Lei 14.905/2024 se aplica — habilita combinações de índices)",
    "indice_correcao": "TUACDT | IPCAE | SELIC | TR | IPCA | IGPM | INPC | IPC | IPCAETR | SELIC_FAZENDA | SELIC_BACEN | TABELA_UNICA_JT_MENSAL | TABELA_UNICA_JT_DIARIO | SEM_CORRECAO | null",
    "indice_correcao_pos": "IPCA | null (índice pós-30/08/2024; somente quando lei_14905=true)",
    "base_juros": "Verbas | Credito Total | null",
    "taxa_juros": "TAXA_LEGAL | JUROS_PADRAO | SELIC | TRD_SIMPLES | TRD_COMPOSTOS | JUROS_UM_PORCENTO | JUROS_MEIO_PORCENTO | SELIC_FAZENDA | SELIC_BACEN | SEM_JUROS | null",
    "data_taxa_legal": "DD/MM/AAAA | null (padrão 30/08/2024; somente quando taxa_juros=TAXA_LEGAL)",
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
    {{"nome": "Salário", "data_inicio": "DD/MM/AAAA", "data_fim": "DD/MM/AAAA", "valor": 0.00, "variavel": false, "incidencia_fgts": true, "incidencia_cs": true}}
  ],
  "faltas": [
    {{"data_inicial": "DD/MM/AAAA", "data_final": "DD/MM/AAAA", "justificada": false, "descricao": ""}}
  ],
  "ferias": [
    {{"situacao": "Vencidas | Proporcionais | Gozadas", "periodo_inicio": "DD/MM/AAAA",
      "periodo_fim": "DD/MM/AAAA", "abono": false, "dobra": false}}
  ],
  "custas_judiciais": {{
    "base": "Bruto Devido ao Reclamante | Bruto Devido ao Reclamante + Outros Débitos | null",
    "reclamado_conhecimento": "CALCULADA | INFORMADA | NAO_SE_APLICA",
    "reclamado_liquidacao": "NAO_SE_APLICA | CALCULADA | INFORMADA",
    "reclamante_conhecimento": "NAO_SE_APLICA | CALCULADA | INFORMADA",
    "percentual": "float | null",
    "devedor": "RECLAMADO | RECLAMANTE | null"
  }},
  "duracao_trabalho": {{
    "tipo_apuracao": "apuracao_jornada | quantidade_fixa | null",
    "forma_apuracao_pjecalc": "FAV | HJD | SEM | MEN | HST | APH | NAP | null",
    "preenchimento_jornada": "programacao_semanal | escala | livre | null",
    "escala_tipo": "string | null",
    "grade_semanal": {{
      "seg": {{"turnos": [{{"entrada": "07:00", "saida": "12:00"}}, {{"entrada": "13:00", "saida": "17:00"}}]}},
      "ter": {{"turnos": [{{"entrada": "07:00", "saida": "12:00"}}, {{"entrada": "13:00", "saida": "17:00"}}]}},
      "qua": {{"turnos": [{{"entrada": "07:00", "saida": "12:00"}}, {{"entrada": "13:00", "saida": "17:00"}}]}},
      "qui": {{"turnos": [{{"entrada": "07:00", "saida": "12:00"}}, {{"entrada": "13:00", "saida": "17:00"}}]}},
      "sex": {{"turnos": [{{"entrada": "07:00", "saida": "12:00"}}, {{"entrada": "13:00", "saida": "17:00"}}]}},
      "sab": null,
      "dom": null,
      "feriado": null
    }},
    "jornada_entrada": "HH:MM | null",
    "jornada_saida": "HH:MM | null",
    "intervalo_minutos": "int | null",
    "jornada_seg": "float | null",
    "jornada_ter": "float | null",
    "jornada_qua": "float | null",
    "jornada_qui": "float | null",
    "jornada_sex": "float | null",
    "jornada_sab": "float | null",
    "jornada_dom": "float | null",
    "qt_horas_extras_mes": "float | null",
    "qt_horas_extras_dia": "float | null",
    "adicional_he_percentual": "float | null",
    "trabalha_feriados": "bool | null",
    "trabalha_domingos": "bool | null",
    "apurar_hora_noturna": "bool | null",
    "hora_inicio_noturno": "HH:MM | null",
    "hora_fim_noturno": "HH:MM | null",
    "reducao_ficta": "bool | null",
    "prorrogacao_horario_noturno": "bool | null",
    "periodo_cartao_inicio": "DD/MM/AAAA | null",
    "periodo_cartao_fim": "DD/MM/AAAA | null",
    "confianca": 0.85
  }},
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
- historico_salarial: NUNCA retornar array vazio se o relatório contiver tabela de salários,
  "Histórico Salarial", faixas salariais, ou salários por período. Extrair CADA faixa como uma
  entrada com nome, data_inicio, data_fim, valor, incidencia_fgts, incidencia_cs.
  Mesmo que haja um único salário durante o contrato, criar 1 entrada com período completo.
- ferias: OBRIGATÓRIO extrair se o relatório listar períodos aquisitivos de férias, férias
  vencidas ou proporcionais. Para CADA período listado criar uma entrada com:
    situacao: "Vencidas" (período completo não gozado) | "Proporcionais" (período incompleto)
    periodo_inicio / periodo_fim: datas do período aquisitivo (DD/MM/AAAA)
    abono: true se a sentença defere abono pecuniário / conversão de 1/3
    dobra: true se a sentença defere férias em dobro
  Exemplo: relatório lista "01/03/2022 a 28/02/2023 (Vencidas)" e "01/03/2023 a 28/02/2024 (Vencidas)"
  → ferias = [{situacao:"Vencidas", periodo_inicio:"01/03/2022", periodo_fim:"28/02/2023", abono:false, dobra:false},
              {situacao:"Vencidas", periodo_inicio:"01/03/2023", periodo_fim:"28/02/2024", abono:false, dobra:false}]
  NÃO deixar ferias=[] se houver qualquer menção a períodos de férias no relatório.
- honorarios: OBRIGATÓRIO extrair. Padrões do CalcMachine:
    "Honorários Advocatícios - Devedor: Reclamado - Percentual: X%"
    "Honorários: X% sobre o valor da condenação"
    "Honorários sucumbenciais de X%"
    "Honorários advocatícios: X%"
  Se o relatório tiver QUALQUER menção a honorários com percentual ou devedor identificado → incluir no array.
  Honorários do RECLAMADO com percentual: tipo="SUCUMBENCIAIS", tipo_valor="CALCULADO", base_apuracao="BRUTO".
  Percentual: "15%" → 0.15 | "10%" → 0.10 | "20%" → 0.20. Faixa "10% a 15%" → usar 0.10.
  NUNCA retornar honorarios=[] se o relatório listar "Honorários Advocatícios" com percentual ou valor.
- FGTS NÃO é verba_deferida: quando o relatório listar "DEPÓSITOS DE FGTS + MULTA DE 40%",
  "FGTS + Multa 40%", "FGTS + MULTA DE 40%" como condenação → NÃO incluir em verbas_deferidas;
  em vez disso definir fgts.multa_40 = true. Reflexos de FGTS (ex: "Reflexo em FGTS + Multa 40%")
  também NÃO são verbas — ignorar. FGTS tem aba própria no PJE-Calc.
- processo.numero: copiar o número EXATAMENTE como aparece no relatório (formato NNNNNNN-DD.AAAA.J.TT.OOOO),
  sem truncar nem alterar os 7 dígitos da sequência.
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
- municipio: APENAS o nome da cidade, sem UF, sem sufixo, sem número de vara
  (ex: "Fortaleza" e não "Fortaleza/CE", "Fortaleza - 3ª VT" ou "Fortaleza-CE")
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

**DURAÇÃO DO TRABALHO / CARTÃO DE PONTO** → preenche "duracao_trabalho":
Extrair SEMPRE que houver condenação em horas extras. Esta seção alimenta o Cartão de Ponto do PJE-Calc.

- tipo_apuracao: como a sentença define a jornada para apuração de horas extras:
    "apuracao_jornada" → a sentença fixa horários de entrada/saída por dia da semana
      (ex: "07h às 17h, seg a sex", "jornada das 08:00 às 18:00 com 1h de intervalo")
    "quantidade_fixa" → a sentença fixa quantidade mensal/diária de HE sem detalhar jornada
      (ex: "50 horas extras mensais", "2h extras por dia")
    null → não há condenação em horas extras ou informação insuficiente

- forma_apuracao_pjecalc: mapear para o enum do PJE-Calc (Manual seção 10.1):
    "NAP" → Não apurar horas extras
    "HJD" → Excedentes da jornada diária
    "SEM" → Excedentes da jornada semanal
    "FAV" → Critério mais favorável (compara diário vs semanal, usa maior)
    "MEN" → Excedentes da jornada mensal
    "HST" → Súmula 85 TST (com limite de compensação)
    "APH" → Primeiras HE em separado
    Regra: "apuracao_jornada" → "FAV" (default) | "quantidade_fixa" → "NAP" | null → "NAP"

- preenchimento_jornada: como preencher a grade de jornadas no PJE-Calc (Manual seção 10.1):
    "livre" → campos em branco para preenchimento manual posterior (default quando jornada vaga)
    "programacao_semanal" → grade fixa por dia da semana (quando sentença fixa horários claros seg-dom)
    "escala" → escala de trabalho pré-definida (12x36, 6x1, etc.)
    Regra: se sentença diz "escala 12x36" → "escala" | se fixa horários por dia → "programacao_semanal" | senão → "livre"

- escala_tipo: se preenchimento_jornada="escala", qual escala:
    "12x12" | "12x24" | "12x36" | "12x48" | "5x1" | "6x1" | "8x2" | "outra"
    Extrair de "escala 12x36", "regime 6x1", "escala de revezamento 5x1"
    null se preenchimento_jornada != "escala"

GRADE SEMANAL (Programação Semanal — pares Entrada/Saída por dia):
- grade_semanal: objeto com a grade de horários praticados para o Cartão de Ponto do PJE-Calc.
  Cada dia da semana ("seg", "ter", "qua", "qui", "sex", "sab", "dom", "feriado") contém "turnos" —
  lista de pares entrada/saída (máximo 6 pares por dia). Os intervalos (almoço, descanso) são
  representados pela LACUNA entre a saída de um turno e a entrada do seguinte.
  Dias de folga: null.
  Exemplo: "07h às 17h com 1h de intervalo, seg a sex" →
    seg: turnos=[{{"entrada":"07:00","saida":"12:00"}},{{"entrada":"13:00","saida":"17:00"}}]
    (intervalo 12:00-13:00 implícito pela lacuna entre turnos)
  ⚠️ Se intervalo explícito (ex: "1h intervalo"), DIVIDIR a jornada em 2 turnos.
    Se 2 intervalos → 3 turnos. Se sem intervalo → 1 turno contínuo.
  ⚠️ Distribuir o intervalo simetricamente no meio da jornada quando a sentença não especifica horário exato.
    Ex: 07:00-17:00 com 1h intervalo → turno1 07:00-12:00, turno2 13:00-17:00

CAMPOS LEGADO (mantidos para compatibilidade — preenchidos automaticamente se grade_semanal presente):
- jornada_entrada: horário de início global (string "HH:MM", ex: "07:00")
- jornada_saida: horário de término global (string "HH:MM", ex: "17:00")
- intervalo_minutos: duração do intervalo intrajornada em MINUTOS (int, ex: 60 para 1h)
  Extrair de "com 1h de intervalo", "intervalo de 30 minutos", "1 hora de almoço"
  Se não explícito: inferir 60 min para jornada ≥ 6h (art. 71 CLT), 15 min para 4h-6h
- jornada_seg a jornada_dom: horas BRUTAS no local por dia da semana (float)
  Calcular: (horario_saida - horario_entrada) para cada dia mencionado.
  Ex: "07h às 17h com 1h intervalo, seg a sex" → seg=10.0, ter=10.0, ..., sex=10.0, sab=0.0, dom=0.0
  ⚠️ Esses valores são horas BRUTAS no local (sem descontar intervalo) — o PJE-Calc desconta o intervalo

- qt_horas_extras_mes: para tipo="quantidade_fixa", total de HE mensais (float, ex: 50.0)
- qt_horas_extras_dia: para tipo="quantidade_fixa", HE diárias (float, ex: 1.0)

- jornada_semanal_cartao: total de horas semanais para o cartão de ponto (float)
  Calcular: soma de jornada_seg a jornada_dom (ex: 10×5 = 50.0)
- jornada_mensal_cartao: média mensal de horas (float)
  Calcular: jornada_semanal_cartao × 4.5 ou jornada_semanal_cartao × (30/7)

- adicional_he_percentual: percentual do adicional de horas extras (float, ex: 0.50 para 50%)
  Extrair de "adicional de 50%", "horas extras com adicional de 70%"
  Default: 0.50 (50%) se não especificado

- trabalha_feriados: bool — true se sentença indica labor em feriados
- trabalha_domingos: bool — true se jornada_dom > 0 ou sentença menciona trabalho dominical
- sabados_trabalhados: lista de datas específicas de sábados trabalhados (DD/MM/AAAA), se mencionados
  Ex: ["29/11/2025", "13/12/2025"] — extrair de "sábados 29/11 e 13/12" ou similar

- apurar_hora_noturna: bool — true se sentença condena em adicional noturno ou menciona trabalho noturno
  Extrair de "adicional noturno", "horas noturnas", "labor noturno", "22h às 05h"
- hora_inicio_noturno: string "HH:MM" — início do período noturno (default "22:00" para urbano)
  Rural: varia conforme atividade (pecuária "20:00", lavoura "21:00")
- hora_fim_noturno: string "HH:MM" — fim do período noturno (default "05:00" para urbano)
- reducao_ficta: bool — true se deve aplicar redução ficta (hora noturna = 52m30s). Default true
  Extrair de "sem redução ficta" → false, "com hora reduzida" → true
- prorrogacao_horario_noturno: bool — true se sentença menciona prorrogação do horário noturno
  (Súmula 60 TST: labor após 05h em continuidade a jornada noturna mantém adicional)
  Extrair de "prorrogação noturna", "Súmula 60", "trabalho após 05h"
- dias_especiais: lista de objetos para dias com jornada diferenciada:
  Ex: [{{"data": "23/12/2025", "horas_extras": 6.0, "descricao": "labor até 23h"}}]

- confianca: 0.0-1.0

**AVISO PRÉVIO** → preenche "aviso_previo":
- Deferido calculado pela Lei 12.506/2011: tipo="Calculado", projetar=true
- Deferido com dias fixos (ex: "aviso prévio de 30 dias"): tipo="Informado", prazo_dias=30, projetar=true
- Indeferido ou ausente: tipo="Nao Apurar", projetar=false

**HISTÓRICO SALARIAL** → preenche "historico_salarial":
Extrair SEMPRE o histórico salarial — é a base de cálculo do PJE-Calc.
Cada entrada representa uma BASE DE CÁLCULO com nome, período e valor mensal.

- Se salário único durante todo o contrato → 1 entrada com período completo (admissão a demissão)
- Se salário mudou ao longo do contrato → N entradas, uma por faixa salarial
- Se equiparação salarial, desvio de função ou piso normativo → criar bases SEPARADAS com nomes
  distintos (ex: "Salário Pago" e "Salário Devido", "Adicional Noturno Pago")
- Campos por entrada:
  - nome: tipo da base ("Salário", "Comissões", "Salário Pago", "Salário Devido", etc.) — default "Salário"
  - data_inicio (DD/MM/AAAA), data_fim (DD/MM/AAAA), valor (float mensal completo)
  - variavel: true se valores mudam a cada mês (comissões, horas extras, gorjetas). false (default) para salário fixo.
  - incidencia_fgts (bool, default true), incidencia_cs (bool, default true)

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
⚠️ FGTS NÃO é verba: "DEPÓSITOS DE FGTS + MULTA DE 40%", "FGTS + Multa 40%" → NÃO incluir em
verbas_deferidas; em vez disso definir fgts.multa_40 = true. Reflexos de FGTS também NÃO são verbas.

**FGTS** → preenche "fgts":
- aliquota: 0.08 (8%) para a maioria dos contratos; 0.02 (2%) para aprendizes
  Buscar "alíquota de X%" ou "FGTS à alíquota de X%"
- multa_40: true quando deferida "multa de 40%" / "multa rescisória" / "art. 18 §1º da Lei 8.036"
  Também true quando condenação em "FGTS + Multa 40%" aparecer na lista de verbas.
  TAMBÉM true quando multa de 20% é deferida (habilita a seção de multa no PJE-Calc).
- multa_20: true SOMENTE quando a sentença determina multa de 20% (estabilidade provisória:
  CIPA, gestante, acidentário, etc.). Quando multa_20=true, multa_40 TAMBÉM deve ser true.
  Se a sentença não menciona 20%, multa_20=false (default).
- multa_467: true quando deferida "multa do art. 467 CLT" (verbas rescisórias incontroversas)
- saldo_fgts: saldo das contas FGTS do trabalhador, se informado (ex: "saldo FGTS de R$ 1.200,00");
  null se não mencionado — NÃO inferir, apenas extrair se explícito
- incidencia_13o_dezembro: true (padrão) — o recolhimento do FGTS referente ao 13º salário
  ocorre na competência de dezembro (ou no mês do desligamento, se antes de dezembro). Portanto a
  base FGTS daquele mês deve conter: salário mensal + 13º proporcional. O agente faz esse ajuste
  automaticamente via página "Ocorrências do FGTS" após salvar os parâmetros. Emitir false apenas
  se a sentença expressamente afastar incidência de FGTS sobre 13º (hipótese rara).

**HONORÁRIOS ADVOCATÍCIOS** → preenche "honorarios" (LISTA de registros):
⚠️ O PJE-Calc NÃO tem opção "Ambos" — cada honorário é um registro separado por devedor.
- Sucumbência recíproca → gerar DOIS registros na lista:
    [{{"devedor": "RECLAMADO", "base_apuracao": "BRUTO", ...}},
     {{"devedor": "RECLAMANTE", "base_apuracao": "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL", ...}}]
- Sucumbência integral da reclamada → um registro com devedor="RECLAMADO"
- Sucumbência integral do reclamante → um registro com devedor="RECLAMANTE"
- Se indeferidos ou não mencionados → honorarios = []
- tipo: "SUCUMBENCIAIS" (padrão) | "CONTRATUAIS" (raro)
- tipo_valor: "CALCULADO" quando há percentual | "INFORMADO" quando há valor fixo em R$
- base_apuracao (VALORES EXATOS do select do PJE-Calc — nunca emitir abreviações):
    RECLAMADO + SUCUMBENCIAIS: "BRUTO" (padrão — % sobre valor da condenação)
                              | "BRUTO_MENOS_CONTRIBUICAO_SOCIAL"
                              | "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA"
    RECLAMANTE + SUCUMBENCIAIS: "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL" (padrão — % sobre Verbas que Não Compõem Principal)
                               | "BRUTO"
                               | "BRUTO_MENOS_CONTRIBUICAO_SOCIAL"
    CONTRATUAIS: "BRUTO" | "BRUTO_MENOS_CONTRIBUICAO_SOCIAL"
    ⚠️ Quando sentença diz "sobre o valor da condenação" para AMBAS as partes → "BRUTO" nos dois
- percentual: decimal (15% → 0.15); null se tipo_valor=INFORMADO
- valor_informado: float; null se tipo_valor=CALCULADO
- apurar_ir: true quando honorários são tributáveis

**HONORÁRIOS PERICIAIS** → preenche "honorarios_periciais" (campo top-level, SEPARADO da lista "honorarios"):
- Buscar "honorários periciais", "honorário do perito", "laudo pericial", "assistente técnico"
- Valor float ou null. NÃO colocar dentro de honorarios[].

**CORREÇÃO MONETÁRIA E JUROS** → preenche "correcao_juros":
Mapear EXATAMENTE para os enums disponíveis no PJE-Calc:

Caso 1 — ADC 58 + Lei 14.905/2024 (JURISPRUDÊNCIA MAJORITÁRIA ATUAL):
  Indicadores: "E-ED-RR-20407", "Lei 14.905", "taxa legal", "IPCA-E na fase pré-judicial",
               "SELIC até 29/08/2024", "IPCA + taxa legal a partir de 30/08/2024",
               3 fases distintas (pré-judicial / ajuizamento-29.08.2024 / pós-30.08.2024),
               "art. 406 do CC", "SELIC - IPCA"
  → lei_14905 = true
    indice_correcao = "IPCAE"
    indice_correcao_pos = "IPCA"
    taxa_juros = "TAXA_LEGAL"
    data_taxa_legal = "30/08/2024"
  ⚠️ PREENCHIMENTO NO PJe-Calc exige COMBINAÇÕES de índices:
    CORREÇÃO: IPCAE até 29/08/2024 COMBINADO COM IPCA a partir de 30/08/2024.
      Se admissão > 30/08/2024 → usar somente IPCA (campo indice_correcao = null, indice_correcao_pos = "IPCA").
    JUROS (cenário depende da data de ajuizamento vs 30/08/2024):
      Cenário A — Ajuizamento ANTES de 30/08/2024:
        Pré-judicial: TRD_SIMPLES combinado com SEM_JUROS a partir de 30/08/2024
        Judicial Fase 1: SELIC do ajuizamento até 29/08/2024
        Judicial Fase 2: TAXA_LEGAL a partir de 30/08/2024
      Cenário B — Ajuizamento DEPOIS de 30/08/2024:
        Pré-judicial: TRD_SIMPLES
        Judicial: TAXA_LEGAL a partir do ajuizamento

Caso 2 — ADC 58 / critérios TST SEM menção à Lei 14.905 (sentenças anteriores a ago/2024):
  Indicadores: "ADC 58", "Tabela JT Única Mensal", "IPCA-E até o ajuizamento e SELIC a partir",
               "critérios da Justiça do Trabalho" — SEM mencionar "taxa legal" ou "Lei 14.905"
  → lei_14905 = false | indice_correcao = "TUACDT" | taxa_juros = "SELIC"

Caso 3 — Apenas SELIC:
  Indicadores: "atualizado pela SELIC", "taxa SELIC", "correção pela SELIC" (sem distinção de fases)
  → lei_14905 = false | indice_correcao = "SELIC" | taxa_juros = "SELIC"

Caso 4 — IPCA-E + juros de 1% ao mês:
  Indicadores: "IPCA-E mais juros de 1% ao mês", "IPCA-E e juros moratórios de 1%",
               "IPCA-E + juros legais", "IPCA-E acrescido de 1% ao mês"
  → lei_14905 = false | indice_correcao = "IPCAE" | taxa_juros = "JUROS_PADRAO"

Caso 5 — TR / TRCT + juros de 1% ao mês:
  Indicadores: "TR mais 1% ao mês", "TRCT", "correção pela TR e juros de 1%"
  → lei_14905 = false | indice_correcao = "TR" | taxa_juros = "JUROS_PADRAO"

Caso 6 — IPCA-E sem especificação de juros:
  → lei_14905 = false | indice_correcao = "IPCAE" | taxa_juros = "JUROS_PADRAO"

JUROS_PADRAO = Juros Padrão = 1% ao mês (juros legais trabalhistas — art. 39 Lei 8.177/91)
SELIC = SELIC (Receita Federal) = taxa SELIC acumulada (absorve correção + juros)
TAXA_LEGAL = Taxa Legal = SELIC − IPCA (juros reais, Lei 14.905/2024, vigência 30/08/2024)
IPCA = índice de correção pós-Lei 14.905 (substitui IPCA-E a partir de 30/08/2024)
data_taxa_legal: "DD/MM/AAAA" — data marco para TAXA_LEGAL (padrão "30/08/2024"). Informar SOMENTE quando taxa_juros = "TAXA_LEGAL".
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
    "multa_20": "true | false | null",
    "multa_467": "true | false | null",
    "incidencia_13o_dezembro": "true | false (padrão true — FGTS do 13º é recolhido na competência de dezembro; base de dezembro = salário + 13º proporcional. Emitir false apenas se a sentença expressamente afastar incidência de FGTS sobre o 13º.)",
    "confianca": 0.0-1.0
  }},
  "honorarios": [
    {{
      "tipo": "SUCUMBENCIAIS | CONTRATUAIS",
      "devedor": "RECLAMANTE | RECLAMADO",
      "tipo_valor": "CALCULADO | INFORMADO",
      "base_apuracao": "BRUTO | BRUTO_MENOS_CONTRIBUICAO_SOCIAL | BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA | VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
      "percentual": "float | null",
      "valor_informado": "float | null",
      "apurar_ir": "true | false"
    }}
  ],
  "honorarios_periciais": "float | null",
  "justica_gratuita": {{
    "reclamante": "true | false",
    "reclamado": "true | false"
  }},
  "correcao_juros": {{
    "lei_14905": "true | false (true quando Lei 14.905/2024 se aplica)",
    "indice_correcao": "TUACDT | IPCAE | SELIC | TR | IPCA | IGPM | INPC | IPC | IPCAETR | SELIC_FAZENDA | SELIC_BACEN | TABELA_UNICA_JT_MENSAL | TABELA_UNICA_JT_DIARIO | SEM_CORRECAO | null",
    "indice_correcao_pos": "IPCA | null (somente quando lei_14905=true)",
    "base_juros": "Verbas | Credito Total | null",
    "taxa_juros": "TAXA_LEGAL | JUROS_PADRAO | SELIC | TRD_SIMPLES | TRD_COMPOSTOS | JUROS_UM_PORCENTO | JUROS_MEIO_PORCENTO | SELIC_FAZENDA | SELIC_BACEN | SEM_JUROS | null",
    "data_taxa_legal": "DD/MM/AAAA | null (padrão 30/08/2024; somente quando taxa_juros=TAXA_LEGAL)",
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
  "duracao_trabalho": {{
    "tipo_apuracao": "apuracao_jornada | quantidade_fixa | null",
    "forma_apuracao_pjecalc": "FAV | HJD | SEM | MEN | HST | APH | NAP | null",
    "preenchimento_jornada": "programacao_semanal | escala | livre | null",
    "escala_tipo": "string | null",
    "grade_semanal": {{
      "seg": {{"turnos": [{{"entrada": "07:00", "saida": "12:00"}}, {{"entrada": "13:00", "saida": "17:00"}}]}},
      "ter": "idem ou null",
      "qua": "idem ou null",
      "qui": "idem ou null",
      "sex": "idem ou null",
      "sab": "null se folga",
      "dom": "null se folga",
      "feriado": "null se folga"
    }},
    "jornada_entrada": "HH:MM | null",
    "jornada_saida": "HH:MM | null",
    "intervalo_minutos": "int | null",
    "jornada_seg": "float | null",
    "jornada_ter": "float | null",
    "jornada_qua": "float | null",
    "jornada_qui": "float | null",
    "jornada_sex": "float | null",
    "jornada_sab": "float | null",
    "jornada_dom": "float | null",
    "qt_horas_extras_mes": "float | null",
    "qt_horas_extras_dia": "float | null",
    "adicional_he_percentual": "float | null",
    "trabalha_feriados": "bool | null",
    "trabalha_domingos": "bool | null",
    "apurar_hora_noturna": "bool | null",
    "hora_inicio_noturno": "HH:MM | null",
    "hora_fim_noturno": "HH:MM | null",
    "reducao_ficta": "bool | null",
    "prorrogacao_horario_noturno": "bool | null",
    "periodo_cartao_inicio": "DD/MM/AAAA | null",
    "periodo_cartao_fim": "DD/MM/AAAA | null",
    "confianca": 0.0-1.0
  }},
  "historico_salarial": [
    {{"nome": "Salário", "data_inicio": "DD/MM/AAAA", "data_fim": "DD/MM/AAAA", "valor": 0.00, "variavel": false, "incidencia_fgts": true, "incidencia_cs": true}}
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

REGRA historico_salarial — NUNCA retornar array vazio:
- Se há salário mencionado (qualquer valor salarial), criar pelo menos 1 entrada
- Extrair CADA faixa salarial com nome, data_inicio, data_fim, valor, incidencia_fgts=true, incidencia_cs=true
- Se salário uniforme: 1 entrada com data_admissao a data_demissao e o valor salarial

REGRA ferias — se a sentença deferir férias (proporcionais, vencidas ou dobra):
- Extrair com situacao, periodo_inicio, periodo_fim, abono e dobra

Retorne APENAS o JSON, sem markdown, sem explicações."""


# ── Função principal ──────────────────────────────────────────────────────────

def extrair_dados_sentenca(
    texto: str,
    sessao_id: str | None = None,
    extras: list[dict] | None = None,
    is_relatorio: bool = False,
    usar_gemini: bool | None = None,
    orchestrator: "LLMOrchestrator | None" = None,
) -> dict[str, Any]:
    """
    Extrai todos os dados necessários para preenchimento do PJE-Calc.

    Dois modos:
    - is_relatorio=False (padrão): extração a partir de sentença bruta
        Fase 1: regex → Fase 2: LLM → Fase 3: merge → Fase 4: validação
    - is_relatorio=True: o texto já é um relatório estruturado (ex: saída do Projeto Claude)
        Pula regex; usa prompt especializado de mapeamento direto ao schema

    Args:
        texto: Texto da sentença ou relatório estruturado.
        sessao_id: UUID da sessão (gerado se não fornecido).
        extras: Documentos complementares {"tipo", "conteudo", "contexto", "mime_type"}.
        is_relatorio: True se o texto for um relatório pré-estruturado.
        usar_gemini: True=forçar Gemini, False=forçar Claude, None=usar config global USE_GEMINI.
        orchestrator: LLMOrchestrator opcional. Se fornecido, injeta knowledge base e regras
            aprendidas no prompt via orchestrator.complete(). Se None, usa a lógica direta atual.
    """
    sessao_id = sessao_id or str(uuid.uuid4())

    if is_relatorio:
        # LEGAL_EXTRACTION → Claude obrigatório (cf. LLM Routing em CLAUDE.md).
        # Gemini perde verbas críticas em relatórios estruturados (ex: Saldo de Salário,
        # Aviso Prévio, Multa 477, FGTS+40%). Só usar Gemini se explicitamente forçado.
        _usar_gemini_rel = usar_gemini if usar_gemini is not None else False
        resultado = _extrair_de_relatorio_estruturado(texto, sessao_id, usar_gemini=_usar_gemini_rel)
        if "_erro_llm" not in resultado:
            return resultado
        # IA falhou no relatório — bloquear conforme regra de negócio
        logger.error("IA falhou no mapeamento do relatório — processamento bloqueado")
        return {
            "_erro_ia": True,
            "alertas": resultado.get("alertas", []) + [
                "BLOQUEADO: falha ao processar o relatório via IA. "
                "Verifique créditos/chave da API e reenvie o documento."
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

    # LEGAL_EXTRACTION → Claude obrigatório (cf. LLM Routing em CLAUDE.md).
    # Gemini só se explicitamente forçado pelo chamador.
    _usar_gemini = usar_gemini if usar_gemini is not None else False

    if orchestrator is not None:
        # Orchestrator injeta knowledge base oficial + regras aprendidas no sistema
        try:
            from core.llm_orchestrator import TaskType
            dados_llm = orchestrator.complete(
                TaskType.LEGAL_EXTRACTION,
                texto_para_llm,
                inject_knowledge=True,
                inject_learned_rules=True,
            )
            if isinstance(dados_llm, str):
                dados_llm = {"_erro_llm": "resposta não-JSON do orchestrator"}
        except Exception as e:
            logger.warning("orchestrator_extraction_failed", error=str(e))
            dados_llm = {"_erro_llm": str(e)}
    elif _usar_gemini and GEMINI_API_KEY:
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
        _api_nome = "Gemini" if _usar_gemini else "Anthropic"
        return {
            "_erro_ia": True,
            "alertas": dados_llm.get("alertas", []) + [
                f"BLOQUEADO: extração via IA indisponível ({_api_nome}). "
                "Verifique créditos/chave da API e reprocesse o documento."
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
        "historico_salarial", "faltas", "ferias", "custas_judiciais",
        "duracao_trabalho", "justica_gratuita",
        "campos_ausentes", "alertas",
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
        "duracao_trabalho": {
            "type": ["object","null"],
            "additionalProperties": False,
            "properties": {
                "tipo_apuracao":          {"type": ["string","null"]},
                "forma_apuracao_pjecalc": {"type": ["string","null"]},
                "preenchimento_jornada":  {"type": ["string","null"]},
                "escala_tipo":            {"type": ["string","null"]},
                "grade_semanal": {
                    "type": ["object","null"],
                    "properties": {
                        **{
                            dia: {
                                "type": ["object","null"],
                                "properties": {
                                    "turnos": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "entrada": {"type": "string"},
                                                "saida":   {"type": "string"},
                                            },
                                        },
                                    },
                                },
                            }
                            for dia in ("seg","ter","qua","qui","sex","sab","dom","feriado")
                        },
                    },
                },
                "jornada_entrada":        {"type": ["string","null"]},
                "jornada_saida":          {"type": ["string","null"]},
                "intervalo_minutos":      {"type": ["integer","null"]},
                "jornada_seg":            {"type": ["number","null"]},
                "jornada_ter":            {"type": ["number","null"]},
                "jornada_qua":            {"type": ["number","null"]},
                "jornada_qui":            {"type": ["number","null"]},
                "jornada_sex":            {"type": ["number","null"]},
                "jornada_sab":            {"type": ["number","null"]},
                "jornada_dom":            {"type": ["number","null"]},
                "qt_horas_extras_mes":    {"type": ["number","null"]},
                "qt_horas_extras_dia":    {"type": ["number","null"]},
                "jornada_semanal_cartao": {"type": ["number","null"]},
                "jornada_mensal_cartao":  {"type": ["number","null"]},
                "adicional_he_percentual":{"type": ["number","null"]},
                "trabalha_feriados":      {"type": ["boolean","null"]},
                "trabalha_domingos":      {"type": ["boolean","null"]},
                "sabados_trabalhados":    {"type": ["array","null"], "items": {"type": "string"}},
                "dias_especiais":         {"type": ["array","null"], "items": {"type": "object"}},
                "apurar_hora_noturna":    {"type": ["boolean","null"]},
                "hora_inicio_noturno":    {"type": ["string","null"]},
                "hora_fim_noturno":       {"type": ["string","null"]},
                "reducao_ficta":          {"type": ["boolean","null"]},
                "prorrogacao_horario_noturno": {"type": ["boolean","null"]},
                "periodo_cartao_inicio":  {"type": ["string","null"]},
                "periodo_cartao_fim":     {"type": ["string","null"]},
                "considerar_feriados":    {"type": ["boolean","null"]},
                "supressao_intervalo_intrajornada": {"type": ["boolean","null"]},
                "confianca":              {"type": "number"},
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
                    "sumula_439":        {"type": ["boolean","null"]},
                    "verba_principal_ref":{"type": ["string","null"]},
                    "confianca":         {"type": "number"},
                },
            },
        },
        "fgts": {
            "type": "object", "additionalProperties": False,
            "required": ["aliquota","multa_40","multa_467","saldo_fgts","confianca"],
            "properties": {
                "aliquota":   {"type": ["number","null"]},
                "multa_40":   {"type": ["boolean","null"]},
                "multa_20":   {"type": ["boolean","null"]},
                "multa_467":  {"type": ["boolean","null"]},
                "saldo_fgts": {"type": ["number","null"]},
                "incidencia_13o_dezembro": {"type": ["boolean","null"]},
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
        "justica_gratuita": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "reclamante": {"type": "boolean"},
                "reclamado":  {"type": "boolean"},
            },
        },
        "correcao_juros": {
            "type": "object", "additionalProperties": False,
            "required": ["indice_correcao","base_juros","taxa_juros","jam_fgts","confianca"],
            "properties": {
                "lei_14905":          {"type": ["boolean","null"]},
                "indice_correcao":    {"type": ["string","null"]},
                "indice_correcao_pos":{"type": ["string","null"]},
                "base_juros":         {"type": ["string","null"]},
                "taxa_juros":         {"type": ["string","null"]},
                "data_taxa_legal":    {"type": ["string","null"]},
                "jam_fgts":           {"type": ["boolean","null"]},
                "confianca":          {"type": "number"},
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
                    "data_inicio":     {"type": "string"},
                    "data_fim":        {"type": "string"},
                    "valor":           {"type": "number"},
                    "nome":            {"type": ["string", "null"]},
                    "variavel":        {"type": ["boolean", "null"]},
                    "incidencia_fgts": {"type": ["boolean", "null"]},
                    "incidencia_cs":   {"type": ["boolean", "null"]},
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
        "multas_indenizacoes": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["descricao","tipo_valor","valor"],
                "properties": {
                    "descricao":  {"type": "string"},
                    "tipo_valor": {"type": "string"},  # "INFORMADO" ou "CALCULADO"
                    "valor":      {"type": ["number","null"]},
                    "percentual": {"type": ["number","null"]},
                    "base":       {"type": ["string","null"]},
                },
            },
        },
        "custas_judiciais": {
            "type": ["object","null"], "additionalProperties": False,
            "properties": {
                "base":                    {"type": ["string","null"]},
                "reclamado_conhecimento":   {"type": ["string","null"]},
                "reclamado_liquidacao":     {"type": ["string","null"]},
                "reclamante_conhecimento":  {"type": ["string","null"]},
                "percentual":              {"type": ["number","null"]},
                "devedor":                 {"type": ["string","null"]},
            },
        },
        "campos_ausentes": {"type": "array", "items": {"type": "string"}},
        "alertas":         {"type": "array", "items": {"type": "string"}},
    },
}


# ── Validador de consistência da sentença extraída ───────────────────────────

@dataclass
class ResultadoValidacao:
    """Resultado da validação — compatível com webapp.py Fix 4 (`.valido`, `.erros`)."""
    erros: list[str] = _dc_field(default_factory=list)
    avisos: list[str] = _dc_field(default_factory=list)

    @property
    def valido(self) -> bool:
        return len(self.erros) == 0


class ValidadorSentenca:
    """
    Valida consistência do JSON extraído da sentença trabalhista.
    Uso: ValidadorSentenca(dados).validar() → ResultadoValidacao
    """

    def __init__(self, dados: dict):
        self._dados = dados

    def validar(self) -> ResultadoValidacao:
        """Valida e retorna ResultadoValidacao com .valido, .erros e .avisos."""
        r = ResultadoValidacao()
        r.erros.extend(self._validar_datas(self._dados))
        r.erros.extend(self._validar_rescisao_verbas(self._dados))
        r.erros.extend(self._validar_valores(self._dados))
        return r

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
        # saldo_fgts não pode ser negativo
        saldo_fgts = dados.get("fgts", {}).get("saldo_fgts")
        if saldo_fgts is not None and isinstance(saldo_fgts, (int, float)) and saldo_fgts < 0:
            erros.append(f"CRÍTICO: saldo_fgts negativo ({saldo_fgts}) — verificar sentença")
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


def _desmembrar_cnj(numero_completo: str) -> dict | None:
    """
    Desmembra número CNJ completo (NNNNNNN-DD.AAAA.J.TT.OOOO) nos componentes
    necessários para validação módulo 97.

    Retorna dict com chaves: numero_seq (7 dígitos), digito_verificador, ano, segmento, regiao, vara.
    NÃO inclui "numero" para não sobrescrever o número completo em processo.numero.
    Retorna None se o formato não bater.
    """
    m = re.match(r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$", (numero_completo or "").strip())
    if not m:
        return None
    return {
        "numero_seq":         m.group(1),   # 7 dígitos — usado apenas na validação módulo 97
        "digito_verificador": m.group(2),
        "ano":                m.group(3),
        "segmento":           m.group(4),
        "regiao":             m.group(5),
        "vara":               m.group(6),
    }


def _extrair_de_relatorio_estruturado(
    texto_relatorio: str,
    sessao_id: str,
    usar_gemini: bool = False,
) -> dict[str, Any]:
    """
    Converte um relatório já estruturado (ex: saída do Projeto Claude) diretamente
    ao schema JSON do PJE-Calc, sem reprocessar a sentença bruta.

    O relatório já identificou verbas, parâmetros e reflexos — o LLM apenas mapeia
    ao schema, preservando a classificação original.

    usar_gemini: se True, usa Gemini (com fallback para Claude se falhar).
    """
    prompt_usuario = _RELATORIO_PROMPT.replace("{texto}", texto_relatorio[:25000])

    # ── Caminho Gemini ────────────────────────────────────────────────────────
    if usar_gemini and GEMINI_API_KEY:
        logger.info("Mapeamento de relatório via Gemini")
        try:
            from google import genai
            from google.genai import types
            import concurrent.futures

            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt_completo = f"{_SYSTEM_PROMPT_RELATORIO}\n\n{prompt_usuario}"

            def _chamar_gemini():
                return client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt_completo,
                    config=types.GenerateContentConfig(temperature=0.0),
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_chamar_gemini)
                resp = fut.result(timeout=60)

            dados = _limpar_e_parsear_json(resp.text)
            dados = _validar_e_completar(dados)
            if "alertas" not in dados:
                dados["alertas"] = []
            dados["alertas"].insert(0, "Dados extraídos de relatório estruturado via Gemini.")
            return dados

        except Exception as _ge:
            logger.warning(f"Gemini falhou no relatório — tentando Claude: {_ge}")
            # Fallback para Claude abaixo

    # ── Caminho Claude (padrão / fallback) ───────────────────────────────────
    if not ANTHROPIC_API_KEY:
        return {"_erro_llm": "ANTHROPIC_API_KEY não configurada",
                "alertas": ["ANTHROPIC_API_KEY não configurada — processamento impossível"]}

    # httpx_client com timeout por chunk (não por requisição total) — evita o erro
    # "Request timed out or interrupted" em relatórios longos (docs.anthropic.com/errors#long-requests)
    import httpx as _httpx
    _http = _httpx.Client(timeout=_httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0))
    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, http_client=_http)

    try:
        # Usar streaming para evitar timeout em respostas longas (relatório → JSON pode ser 4000+ tokens)
        # stream=True mantém a conexão viva durante toda a geração — sem timeout por inatividade
        conteudo_parts: list[str] = []
        with cliente.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=16384,  # sentenças com 10+ verbas + reflexos ultrapassam 6000 tokens
            temperature=0.0,
            system=_SYSTEM_PROMPT_RELATORIO,
            messages=[{
                "role": "user",
                "content": prompt_usuario,
            }],
        ) as stream:
            for chunk in stream.text_stream:
                conteudo_parts.append(chunk)

        conteudo = "".join(conteudo_parts).strip()
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
    # Caso 1: Lei 14.905/2024 + ADC 58 (jurisprudência majoritária atual — 3 fases)
    if any(p in txt_lower for p in ["taxa legal", "lei 14.905", "14905", "14.905/2024",
                                     "selic - ipca", "selic menos ipca",
                                     "art. 406", "e-ed-rr-20407"]) or \
       (re.search(r"(?i)30[/.]08[/.]2024", texto) and "selic" in txt_lower):
        resultado["lei_14905"] = True
        resultado["indice_correcao"] = "IPCAE"
        resultado["indice_correcao_pos"] = "IPCA"
        resultado["taxa_juros"] = "TAXA_LEGAL"
        resultado["data_taxa_legal"] = "30/08/2024"
    # Caso 2: ADC 58 sem Lei 14.905 (sentenças pré-ago/2024)
    elif any(p in txt_lower for p in ["adc 58", "adc nº 58", "tabela jt", "tabela única mensal",
                                      "selic a partir", "ipca-e até o ajuizamento"]):
        resultado["indice_correcao"] = "TUACDT"
        resultado["taxa_juros"] = "SELIC"
    elif re.search(r"(?i)selic\b.*(?:corre[çc][ãa]o|atualiza[çc][ãa]o)", texto) or \
         re.search(r"(?i)(?:corre[çc][ãa]o|atualiza[çc][ãa]o).*\bselic\b", texto):
        resultado["indice_correcao"] = "SELIC"
        resultado["taxa_juros"] = "SELIC"
    elif re.search(r"(?i)ipca[- ]?e\b.*juros\s+(?:de\s+)?1\s*%", texto) or \
         re.search(r"(?i)ipca[- ]?e\b.*juros\s+(?:de\s+)?um\s+por\s+cento", texto):
        resultado["indice_correcao"] = "IPCAE"
        resultado["taxa_juros"] = "JUROS_PADRAO"
    elif re.search(r"(?i)\btr\b.*juros\s+(?:de\s+)?1\s*%", texto) or \
         re.search(r"(?i)trct\b", texto):
        resultado["indice_correcao"] = "TR"
        resultado["taxa_juros"] = "JUROS_PADRAO"
    elif re.search(r"(?i)ipca[- ]?e\b", texto):
        resultado["indice_correcao"] = "IPCAE"
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
            max_tokens=16384,
            temperature=CLAUDE_EXTRACTION_TEMPERATURE,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content_blocks}],
        )
        conteudo = resposta.content[0].text.strip()
        return _limpar_e_parsear_json(conteudo)

    except anthropic.AuthenticationError as e:
        logger.error(f"Autenticação falhou (API key inválida): {e}")
        return {
            "_erro_llm": str(e), "_erro_ia": True, "_tipo_erro": "auth",
            "alertas": ["API key Anthropic inválida ou expirada. Verifique ANTHROPIC_API_KEY."],
        }
    except anthropic.RateLimitError as e:
        logger.warning(f"Rate limit atingido: {e}")
        return {
            "_erro_llm": str(e), "_tipo_erro": "rate_limited",
            "alertas": ["Limite de requisições atingido. Aguarde alguns minutos e tente novamente."],
        }
    except anthropic.APIConnectionError as e:
        logger.warning(f"Erro de conexão com API: {e}")
        return {
            "_erro_llm": str(e), "_tipo_erro": "transient",
            "alertas": [f"Erro de conexão com a API Anthropic: {e}"],
        }
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
    system_prompt_override: str | None = None,
) -> dict[str, Any]:
    """
    Extração nativa de PDF: envia o arquivo diretamente ao Claude via base64.
    Não converte para texto antes — Claude lê o PDF nativamente (até 32 MB / 100 págs).
    Usa cache_control ephemeral no documento para multi-pass barato.
    Usa Structured Outputs para garantir JSON válido sem parsing tolerante.

    Args:
        system_prompt_override: System prompt alternativo (ex: com knowledge base injetada).
            Se None, usa o _SYSTEM_PROMPT padrão do módulo.
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

    _system = system_prompt_override if system_prompt_override else _SYSTEM_PROMPT
    try:
        # Nota: output_config removido — schema tem >16 union types (limite API Anthropic)
        resposta = cliente.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16384,
            temperature=0.0,
            system=_system,
            messages=[{"role": "user", "content": content_blocks}],
        )
        return _limpar_e_parsear_json(resposta.content[0].text.strip())
    except anthropic.AuthenticationError as e:
        logger.error(f"PDF extração — API key inválida: {e}")
        return {
            "_erro_llm": str(e), "_erro_ia": True, "_tipo_erro": "auth",
            "alertas": ["API key Anthropic inválida ou expirada. Verifique ANTHROPIC_API_KEY."],
        }
    except anthropic.RateLimitError as e:
        logger.warning(f"PDF extração — rate limit: {e}")
        return {
            "_erro_llm": str(e), "_tipo_erro": "rate_limited",
            "alertas": ["Limite de requisições atingido. Aguarde e tente novamente."],
        }
    except anthropic.APIConnectionError as e:
        logger.warning(f"PDF extração — erro de conexão: {e}")
        return {
            "_erro_llm": str(e), "_tipo_erro": "transient",
            "alertas": [f"Erro de conexão com API Anthropic: {e}"],
        }
    except Exception as e:
        logger.warning(f"Falha na extração nativa de PDF: {e}")
        return {"_erro_llm": str(e), "alertas": [str(e)]}


def extrair_dados_sentenca_pdf(
    pdf_path: str,
    sessao_id: str | None = None,
    extras: list[dict] | None = None,
    orchestrator: "LLMOrchestrator | None" = None,
) -> dict[str, Any]:
    """
    Ponto de entrada público para extração direta de PDF.
    Envia o PDF nativo ao Claude (sem conversão para texto).
    Aplica validação, migração de schema legado e multi-pass para campos incertos.

    Args:
        pdf_path: Caminho para o arquivo PDF da sentença.
        sessao_id: UUID da sessão (gerado se não fornecido).
        extras: Documentos complementares {"tipo", "conteudo", "contexto", "mime_type"}.
        orchestrator: LLMOrchestrator opcional. Se fornecido, enriquece o system prompt
            com knowledge base oficial e regras aprendidas antes de chamar o Claude.
    """
    sessao_id = sessao_id or str(uuid.uuid4())

    # Enriquecer system prompt via orchestrator quando disponível
    _system_override: str | None = None
    if orchestrator is not None:
        try:
            from core.llm_orchestrator import TaskType
            _system_override = orchestrator._build_system_prompt(
                TaskType.LEGAL_EXTRACTION_PDF,
                _SYSTEM_PROMPT,
                inject_knowledge=True,
                inject_learned_rules=True,
            )
        except Exception as e:
            logger.warning("orchestrator_system_prompt_failed", error=str(e))

    pdf_bytes = open(pdf_path, "rb").read()
    dados = _extrair_via_llm_pdf(pdf_bytes, extras=extras, system_prompt_override=_system_override)

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
    _v = ValidadorSentenca(dados).validar()
    if _v.erros:
        dados.setdefault("alertas", []).extend(_v.erros)

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
            _registro("RECLAMADO", "BRUTO"),
            _registro("RECLAMANTE", "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL"),
        ]
    if parte in ("Reclamante", "RECLAMANTE"):
        return [_registro("RECLAMANTE", "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL")]
    # Padrão: Reclamado
    return [_registro("RECLAMADO", "BRUTO")]


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
            "multa_20": None,
            "multa_467": None,
            "saldo_fgts": None,
            "incidencia_13o_dezembro": True,
            "confianca": 0.5,
        },
        "honorarios": _migrar_honorarios_legado({
            "percentual": regex.get("honorarios_percentual"),
            "parte_devedora": regex.get("honorarios_parte_devedora"),
        }) if regex.get("honorarios_percentual") else [],
        "honorarios_periciais": None,
        "justica_gratuita": {"reclamante": False, "reclamado": False},
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


def _normalizar_grade_semanal(dados: dict[str, Any]) -> dict[str, Any]:
    """
    Normaliza duracao_trabalho: se grade_semanal ausente mas jornada_entrada/saida presentes,
    gera grade automaticamente. Recalcula jornada_seg..dom a partir da grade.
    """
    dur = dados.get("duracao_trabalho")
    if not dur or not isinstance(dur, dict):
        return dados

    grade = dur.get("grade_semanal")
    entrada_global = dur.get("jornada_entrada")
    saida_global = dur.get("jornada_saida")
    intervalo = dur.get("intervalo_minutos") or 0

    # Se grade_semanal ausente mas temos entrada/saída globais → gerar grade
    if not grade and entrada_global and saida_global:
        try:
            h_ent, m_ent = map(int, entrada_global.split(":"))
            h_sai, m_sai = map(int, saida_global.split(":"))
            total_min = (h_sai * 60 + m_sai) - (h_ent * 60 + m_ent)
            if total_min <= 0:
                total_min += 24 * 60  # jornada noturna cruzando meia-noite

            if intervalo > 0 and total_min > intervalo:
                # Dividir em 2 turnos com intervalo no meio
                meio_trabalho = (total_min - intervalo) // 2
                saida1_min = h_ent * 60 + m_ent + meio_trabalho
                entrada2_min = saida1_min + intervalo
                turnos = [
                    {"entrada": entrada_global, "saida": f"{saida1_min // 60:02d}:{saida1_min % 60:02d}"},
                    {"entrada": f"{entrada2_min // 60:02d}:{entrada2_min % 60:02d}", "saida": saida_global},
                ]
            else:
                turnos = [{"entrada": entrada_global, "saida": saida_global}]

            # Aplicar a dias que têm jornada > 0
            grade = {}
            for dia in ("seg", "ter", "qua", "qui", "sex", "sab", "dom"):
                horas_dia = dur.get(f"jornada_{dia}")
                if horas_dia and float(horas_dia) > 0:
                    grade[dia] = {"turnos": [dict(t) for t in turnos]}
                else:
                    grade[dia] = None
            grade["feriado"] = None
            dur["grade_semanal"] = grade
        except (ValueError, TypeError):
            pass  # formato inválido — não gerar grade

    # Se grade_semanal presente → recalcular campos legado
    grade = dur.get("grade_semanal")
    if grade and isinstance(grade, dict):
        for dia in ("seg", "ter", "qua", "qui", "sex", "sab", "dom"):
            dia_data = grade.get(dia)
            if dia_data and isinstance(dia_data, dict) and dia_data.get("turnos"):
                total = 0.0
                primeiro_entrada = None
                ultimo_saida = None
                for turno in dia_data["turnos"]:
                    ent = turno.get("entrada", "")
                    sai = turno.get("saida", "")
                    if not ent or not sai:
                        continue
                    try:
                        he, me = map(int, ent.split(":"))
                        hs, ms = map(int, sai.split(":"))
                        diff = (hs * 60 + ms) - (he * 60 + me)
                        if diff < 0:
                            diff += 24 * 60
                        total += diff / 60.0
                        if primeiro_entrada is None:
                            primeiro_entrada = ent
                        ultimo_saida = sai
                    except (ValueError, TypeError):
                        continue
                dur[f"jornada_{dia}"] = round(total, 2)
                # Atualizar entrada/saída globais com o primeiro dia que tiver turnos
                if primeiro_entrada and not dur.get("jornada_entrada"):
                    dur["jornada_entrada"] = primeiro_entrada
                if ultimo_saida and not dur.get("jornada_saida"):
                    dur["jornada_saida"] = ultimo_saida
            else:
                dur[f"jornada_{dia}"] = 0.0

        # Calcular intervalo_minutos a partir da grade (lacuna entre turnos do primeiro dia útil)
        if not dur.get("intervalo_minutos"):
            for dia in ("seg", "ter", "qua", "qui", "sex"):
                dia_data = grade.get(dia)
                if dia_data and isinstance(dia_data, dict):
                    turnos = dia_data.get("turnos", [])
                    if len(turnos) >= 2:
                        try:
                            sai1 = turnos[0].get("saida", "")
                            ent2 = turnos[1].get("entrada", "")
                            hs, ms = map(int, sai1.split(":"))
                            he, me = map(int, ent2.split(":"))
                            dur["intervalo_minutos"] = (he * 60 + me) - (hs * 60 + ms)
                        except (ValueError, TypeError):
                            pass
                        break

        # Recalcular totais semanais/mensais
        semanal = sum(dur.get(f"jornada_{d}", 0) or 0 for d in ("seg","ter","qua","qui","sex","sab","dom"))
        dur["jornada_semanal_cartao"] = round(semanal, 2)
        dur["jornada_mensal_cartao"] = round(semanal * 30 / 7, 2)

        # Se preenchimento_jornada não definido, inferir programacao_semanal
        if not dur.get("preenchimento_jornada"):
            dur["preenchimento_jornada"] = "programacao_semanal"

    dados["duracao_trabalho"] = dur
    return dados


_NORM_INDICE_CORRECAO = {
    "IPCA-E": "IPCAE", "IPCA-E/TR": "IPCAETR", "IGP-M": "IGPM",
    "Tabela JT Unica Mensal": "TUACDT", "Tabela JT Única Mensal": "TUACDT",
    "Tabela JT Mensal": "TABELA_UNICA_JT_MENSAL",
    "Selic": "SELIC", "TRCT": "TR",
    "TUACDT_DIARIO": "TABELA_UNICA_JT_DIARIO",
}

_NORM_TAXA_JUROS = {
    "Taxa Legal": "TAXA_LEGAL",
    "Juros Padrão": "JUROS_PADRAO", "Juros Padrao": "JUROS_PADRAO",
    "Selic": "SELIC",
    "TRD_CAPITALIZADOS": "TRD_COMPOSTOS",
    "JUROS_SIMPLES_05": "JUROS_MEIO_PORCENTO",
    "JUROS_SIMPLES_1": "JUROS_UM_PORCENTO",
}


def _normalizar_correcao_juros(dados: dict[str, Any]) -> dict[str, Any]:
    """Normaliza valores legados de correção/juros para enum names do PJe-Calc."""
    cj = dados.get("correcao_juros")
    if not cj or not isinstance(cj, dict):
        return dados
    for campo, mapa in [
        ("indice_correcao", _NORM_INDICE_CORRECAO),
        ("indice_correcao_pos", _NORM_INDICE_CORRECAO),
        ("segundo_indice", _NORM_INDICE_CORRECAO),
        ("taxa_juros", _NORM_TAXA_JUROS),
        ("segunda_tabela_juros", _NORM_TAXA_JUROS),
    ]:
        val = cj.get(campo)
        if val and val in mapa:
            cj[campo] = mapa[val]
    dados["correcao_juros"] = cj
    return dados


def _validar_e_completar(dados: dict[str, Any]) -> dict[str, Any]:
    """
    Identifica campos obrigatórios ausentes e campos com baixa confiança.
    Preenche 'campos_ausentes' e 'alertas'.
    """
    # Normalizar valores legados de correção/juros para enum PJe-Calc
    dados = _normalizar_correcao_juros(dados)
    # Normalizar grade_semanal (gerar a partir de campos flat ou recalcular campos flat)
    dados = _normalizar_grade_semanal(dados)

    # Desmembrar CNJ se número completo disponível e partes ainda não extraídas
    _proc = dados.get("processo", {})
    if _proc.get("numero") and not _proc.get("digito_verificador"):
        _cnj_partes = _desmembrar_cnj(_proc["numero"])
        if _cnj_partes:
            _proc.update(_cnj_partes)
            dados["processo"] = _proc

    # Alerta se JSON foi auto-reparado (dados potencialmente incompletos)
    if dados.pop("_json_auto_reparado", False):
        dados.setdefault("alertas", []).append(
            "⚠ JSON da IA foi truncado e auto-reparado — campos podem estar incompletos. "
            "Revise todos os dados com atenção."
        )

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

    # Validar verba_principal_ref: reflexas devem referenciar uma principal existente
    _verbas = dados.get("verbas_deferidas", [])
    _nomes_principais = {v.get("nome_sentenca", "").strip().lower()
                         for v in _verbas if v.get("tipo", "").lower() != "reflexa"}
    for v in _verbas:
        ref = v.get("verba_principal_ref")
        if ref and ref.strip().lower() not in _nomes_principais:
            alertas.append(
                f"Verba reflexa '{v.get('nome_sentenca', '?')}' referencia principal "
                f"'{ref}' que não foi encontrada. Verifique o mapeamento."
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

    # Correção/juros: se ausentes e há verbas deferidas, aplicar padrão ADC 58 + Lei 14.905 com alerta
    cj = dados.get("correcao_juros", {})
    if not cj.get("indice_correcao") and dados.get("verbas_deferidas"):
        cj["lei_14905"] = True
        cj["indice_correcao"] = "IPCAE"
        cj["indice_correcao_pos"] = "IPCA"
        cj["taxa_juros"] = "TAXA_LEGAL"
        cj["data_taxa_legal"] = "30/08/2024"
        cj.setdefault("base_juros", "Verbas")
        dados["correcao_juros"] = cj
        alertas.append(
            "Índice de correção não identificado — aplicado padrão ADC 58 + Lei 14.905/2024 "
            "(IPCA-E→IPCA + Taxa Legal a partir de 30/08/2024). Verifique na sentença."
        )

    # Custas judiciais: garantir objeto com defaults (configuração do PJE-Calc, não verba)
    cust = dados.get("custas_judiciais")
    if not cust or not isinstance(cust, dict):
        cust = {}
    cust.setdefault("base", "Bruto Devido ao Reclamante")
    cust.setdefault("reclamado_conhecimento", "CALCULADA")
    cust.setdefault("reclamado_liquidacao", "NAO_SE_APLICA")
    cust.setdefault("reclamante_conhecimento", "NAO_SE_APLICA")
    dados["custas_judiciais"] = cust

    # Remover campos opcionais que o LLM pode ter incluído indevidamente
    campos_ausentes = [c for c in campos_ausentes if c not in _CAMPOS_OPCIONAIS]

    dados["campos_ausentes"] = list(set(campos_ausentes))

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

    # ── HITL triggers obrigatórios (skill pjecalc-transformacao §6) ──────────

    # Trigger 6: tipo rescisão ausente ou ambíguo
    if not cont.get("tipo_rescisao"):
        inconsistencias.append(
            "Tipo de rescisão ausente — automação requer revisão humana antes de prosseguir."
        )

    # Trigger 7: múltiplos reclamados (ex: "Empresa S/A e outros")
    reclamado_str = (dados.get("processo", {}).get("reclamado") or "").lower()
    if any(t in reclamado_str for t in ["e outros", "et al", "e outra", "e outr", " e cia", " e ltda"]):
        alertas.append(
            "Processo com possíveis múltiplos reclamados — verifique qual reclamado deve "
            "ser selecionado no PJe-Calc antes de automatizar."
        )

    # Trigger 8: "critério diverso" para FGTS/INSS mencionado em alertas da extração
    _alertas_texto = " ".join(dados.get("alertas", []) + alertas).lower()
    if "critério diverso" in _alertas_texto or "criterio diverso" in _alertas_texto:
        alertas.append(
            "Sentença menciona critério diverso para FGTS/INSS — revisar cálculo antes de automatizar."
        )

    dados["inconsistencias_criticas"] = inconsistencias
    # Propagar inconsistências como alertas visíveis na prévia
    alertas.extend(f"⚠ INCONSISTÊNCIA: {ic}" for ic in inconsistencias)
    dados["alertas"] = alertas

    return dados
