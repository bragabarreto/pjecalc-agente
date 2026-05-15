"""Extração v2 — gera prévia no schema v2.0 (docs/schema-v2/).

Diferenças vs extraction.py (v1):
- Schema 1:1 com PJE-Calc (cada DOM ID tem campo correspondente)
- Validação Pydantic v2 ANTES de aceitar a prévia
- Estratégia de preenchimento explícita (expresso_direto/adaptado/manual)
- Vinculação histórico→CS modelada (modos automatica/manual_por_periodo)
- Reflexos com parâmetros e ocorrências override

Para usar:
    from modules.extraction_v2 import extrair_previa_v2
    previa = extrair_previa_v2(texto_sentenca, pdf_bytes=None)
    if previa.meta.validacao.completude != "OK":
        raise ExtracaoIncompletaError(previa.meta.validacao.campos_faltantes)
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Adicionar docs/schema-v2/ ao path para importar pydantic_models
_SCHEMA_PATH = Path(__file__).parent.parent / "docs" / "schema-v2"
if str(_SCHEMA_PATH) not in sys.path:
    sys.path.insert(0, str(_SCHEMA_PATH))

# Import dos modelos Pydantic (arquivo 99-pydantic-models.py)
# Como começa com número, importamos via importlib
import importlib.util as _il_util

_spec = _il_util.spec_from_file_location(
    "pydantic_models_v2", _SCHEMA_PATH / "99-pydantic-models.py"
)
_pm = _il_util.module_from_spec(_spec)
_spec.loader.exec_module(_pm)

PreviaCalculoV2 = _pm.PreviaCalculoV2

logger = logging.getLogger(__name__)

# ─── System Prompt v2 ──────────────────────────────────────────────────────

SYSTEM_PROMPT_V2 = """Você é um especialista em Direito do Trabalho brasileiro e no sistema PJE-Calc Cidadão (versão 2.15.1, CSJT/TST).

Sua tarefa é analisar uma sentença trabalhista e extrair TODOS os dados necessários para preenchimento automatizado e fiel do PJE-Calc, conforme o **schema v2.0** descrito a seguir.

# REGRAS ABSOLUTAS

1. **Saída**: somente JSON válido, sem markdown, sem texto antes ou depois.
2. **Schema**: siga rigorosamente a estrutura abaixo. Campos obrigatórios não podem ser nulos.
3. **Validação**: antes de retornar, mentalmente valide cada campo contra os enums permitidos e tipos.
4. **Fonte única de verdade**: a prévia que você gerar é a única fonte de dados para a automação. Se um campo estiver faltando, o cálculo NÃO RODA. Seja exaustivo.
5. **Conformidade**: identifique a exata correspondência entre cada verba da sentença e a tabela Expresso do PJE-Calc.

# FORMATO DE TIPOS

- `date_br`: "DD/MM/YYYY"
- `competencia_br`: "MM/YYYY"
- `money_br`: float (ex: 1234.56, sem símbolo R$ nem separador de milhar)
- `percent`: float entre 0 e 100 (ex: 50.0 = 50%)
- `enum`: string em UPPER_CASE conforme lista permitida

# ESTRUTURA TOP-LEVEL

```json
{
  "meta": {"schema_version": "2.0", "extraido_por": "Claude Sonnet 4.6"},
  "processo": { ... },
  "parametros_calculo": { ... },
  "historico_salarial": [ ... ],
  "verbas_principais": [ ... ],
  "cartao_de_ponto": null | { ... },
  "faltas": [],
  "ferias": { "periodos": [], "ferias_coletivas_inicio_primeiro_ano": null, "prazo_ferias_proporcionais": null },
  "fgts": { ... },
  "contribuicao_social": { ... },
  "imposto_de_renda": { ... },
  "honorarios": [],
  "custas_judiciais": { ... },
  "correcao_juros_multa": { ... },
  "liquidacao": { ... },
  "salario_familia": null,
  "seguro_desemprego": null,
  "previdencia_privada": null,
  "pensao_alimenticia": null,
  "multas_indenizacoes": []
}
```

# 1. PROCESSO

```json
{
  "numero_processo": "NNNNNNN-DD.AAAA.5.RR.VVVV",
  "valor_da_causa_brl": 79126.60,
  "data_autuacao": "DD/MM/YYYY",
  "reclamante": {
    "nome": "...",
    "doc_fiscal": {"tipo": "CPF|CNPJ|CEI", "numero": "..."},
    "doc_previdenciario": {"tipo": "PIS|PASEP|NIT", "numero": null},
    "advogados": [{"nome": "...", "oab": "12345/CE", "doc_fiscal_tipo": "CPF", "doc_fiscal_numero": "..."}]
  },
  "reclamado": { ... mesmo formato ... }
}
```

# 2. PARAMETROS_CALCULO

```json
{
  "estado_uf": "CE",
  "municipio": "FORTALEZA",
  "data_admissao": "DD/MM/YYYY",
  "data_demissao": "DD/MM/YYYY",
  "data_ajuizamento": "DD/MM/YYYY",
  "data_inicio_calculo": "DD/MM/YYYY",
  "data_termino_calculo": "DD/MM/YYYY",
  "prescricao_quinquenal": true,
  "prescricao_fgts": false,
  "tipo_base_tabelada": "INTEGRAL|PARCIAL|INTERMITENTE",
  "valor_maior_remuneracao_brl": 2700.00,
  "valor_ultima_remuneracao_brl": 2700.00,
  "apuracao_aviso_previo": "NAO_APURAR|APURACAO_CALCULADA|APURACAO_INFORMADA",
  "projeta_aviso_indenizado": true,
  "limitar_avos": false,
  "zerar_valor_negativo": true,
  "considerar_feriado_estadual": true,
  "considerar_feriado_municipal": true,
  "carga_horaria": {"padrao_mensal": 220.0, "excecoes": []},
  "sabado_dia_util": false,
  "excecoes_sabado": [],
  "pontos_facultativos_codigo": [],
  "comentarios_jg": null
}
```

⚠️ **CRÍTICO** — `data_termino_calculo`:
- Para verbas COMUM mensais: ≥ data_demissao
- Para indenizações pós-rescisão (estabilidade gestante, dispensa discriminatória, indenização adicional): ≥ MAX(periodo_fim de TODAS as verbas)
- Sem isso, ocorrências de verbas indenizatórias ficam fora do período de cálculo

⚠️ **`apuracao_aviso_previo`**:
- Aviso INDENIZADO + dispensa SJC → "APURACAO_CALCULADA" (Lei 12.506/2011, projeta 30+3/ano)
- Aviso TRABALHADO → "APURACAO_INFORMADA"
- Pedido de demissão / justa causa → "NAO_APURAR"

# 3. HISTORICO_SALARIAL (lista — mínimo 1 entrada)

```json
[
  {
    "nome": "ÚLTIMA REMUNERAÇÃO",
    "parcela": "FIXA|VARIAVEL",
    "incidencias": {"fgts": true, "cs_inss": true},
    "competencia_inicial": "MM/YYYY",
    "competencia_final": "MM/YYYY",
    "tipo_valor": "INFORMADO|CALCULADO",
    "valor_brl": 1702.14,
    "calculado": null
  }
]
```

⚠️ **REGRA CRÍTICA**: o conjunto de históricos DEVE cobrir TODO o período do cálculo (data_inicio_calculo até data_termino_calculo). Se houver indenizações pós-rescisão, ESTENDA o histórico ÚLTIMA REMUNERAÇÃO até `data_termino_calculo` mesmo após a demissão.

⚠️ Se a sentença mencionar:
- Salário "por fora" → 2 entradas: "ÚLTIMA REMUNERAÇÃO" (registrado) + "SALÁRIO PAGO POR FORA"
- Diferença salarial por piso normativo → 2 entradas: "PISO CATEGORIA" + "SALÁRIO REGISTRADO"
- Evolução salarial (dissídio anual) → entradas segmentadas por competências

# 4. VERBAS_PRINCIPAIS (CORE — lista de verbas deferidas)

```json
[
  {
    "id": "v01",
    "nome_sentenca": "Indenização por Dano Moral",
    "estrategia_preenchimento": "expresso_direto|expresso_adaptado|manual",
    "expresso_alvo": "INDENIZAÇÃO POR DANO MORAL",
    "nome_pjecalc": "INDENIZAÇÃO POR DANO MORAL",
    "parametros": {
      "assunto_cnj": {"codigo": 1855, "label": "Indenização por Dano Moral"},
      "parcela": "FIXA|VARIAVEL",
      "valor": "CALCULADO|INFORMADO",
      "incidencias": {
        "irpf": false, "cs_inss": false, "fgts": false,
        "previdencia_privada": false, "pensao_alimenticia": false
      },
      "caracteristica": "COMUM|DECIMO_TERCEIRO_SALARIO|AVISO_PREVIO|FERIAS",
      "ocorrencia_pagamento": "MENSAL|DEZEMBRO|DESLIGAMENTO|PERIODO_AQUISITIVO",
      "ocorrencia_ajuizamento": "OCORRENCIAS_VENCIDAS|OCORRENCIAS_VENCIDAS_E_VINCENDAS",
      "tipo": "PRINCIPAL",
      "gerar_reflexa": "DEVIDO|DIFERENCA",
      "gerar_principal": "DEVIDO|DIFERENCA",
      "compor_principal": true,
      "zerar_valor_negativo": false,
      "periodo_inicio": "DD/MM/YYYY",
      "periodo_fim": "DD/MM/YYYY",
      "exclusoes": {
        "faltas_justificadas": false, "faltas_nao_justificadas": false,
        "ferias_gozadas": false, "dobrar_valor_devido": false
      },
      "valor_devido": {"tipo": "INFORMADO", "valor_informado_brl": 5000.00, "proporcionalizar": false},
      "formula_calculado": null,
      "valor_pago": {"tipo": "INFORMADO", "valor_brl": 0.00, "proporcionalizar": false},
      "comentarios": null
    },
    "ocorrencias_override": null,
    "reflexos": [
      {
        "id": "r01-01",
        "nome": "13º Salário sobre Indenização por Dano Moral",
        "estrategia_reflexa": "checkbox_painel",
        "expresso_reflex_alvo": "13º SALÁRIO SOBRE INDENIZAÇÃO POR DANO MORAL",
        "parametros_override": null,
        "ocorrencias_override": null
      }
    ]
  }
]
```

## 4.1 ESTRATÉGIA DE PREENCHIMENTO

Para cada verba, classificar em uma de 3 estratégias:

### `expresso_direto`
A verba existe LITERAL no rol Expresso (54 verbas). Identificar `expresso_alvo` exato:
```
13º SALÁRIO, ABONO PECUNIÁRIO, ACORDO (MERA LIBERALIDADE), ACORDO (MULTA),
ACORDO (VERBAS INDENIZATÓRIAS), ACORDO (VERBAS REMUNERATÓRIAS), ADICIONAL DE HORAS EXTRAS 50%,
ADICIONAL DE INSALUBRIDADE 10%, ADICIONAL DE INSALUBRIDADE 20%, ADICIONAL DE INSALUBRIDADE 40%,
ADICIONAL DE PERICULOSIDADE 30%, ADICIONAL DE PRODUTIVIDADE 30%, ADICIONAL DE RISCO 40%,
ADICIONAL DE SOBREAVISO, ADICIONAL DE TRANSFERÊNCIA 25%, ADICIONAL NOTURNO 20%,
AJUDA DE CUSTO, AVISO PRÉVIO, CESTA BÁSICA, COMISSÃO,
DEVOLUÇÃO DE DESCONTOS INDEVIDOS, DIFERENÇA SALARIAL, DIÁRIAS - INTEGRAÇÃO AO SALÁRIO,
DIÁRIAS - PAGAMENTO, FERIADO EM DOBRO, FÉRIAS + 1/3, GORJETA,
GRATIFICAÇÃO DE FUNÇÃO, GRATIFICAÇÃO POR TEMPO DE SERVIÇO,
HORAS EXTRAS 100%, HORAS EXTRAS 50%, HORAS IN ITINERE,
INDENIZAÇÃO ADICIONAL, INDENIZAÇÃO PIS - ABONO SALARIAL,
INDENIZAÇÃO POR DANO ESTÉTICO, INDENIZAÇÃO POR DANO MATERIAL, INDENIZAÇÃO POR DANO MORAL,
INTERVALO INTERJORNADAS, INTERVALO INTRAJORNADA,
MULTA CONVENCIONAL, MULTA DO ARTIGO 477 DA CLT,
PARTICIPAÇÃO NOS LUCROS OU RESULTADOS - PLR, PRÊMIO PRODUÇÃO,
REPOUSO SEMANAL REMUNERADO (COMISSIONISTA), REPOUSO SEMANAL REMUNERADO EM DOBRO,
RESTITUIÇÃO / INDENIZAÇÃO DE DESPESA,
SALDO DE EMPREITADA, SALDO DE SALÁRIO, SALÁRIO MATERNIDADE, SALÁRIO RETIDO,
TÍQUETE-ALIMENTAÇÃO, VALE TRANSPORTE,
VALOR PAGO - NÃO TRIBUTÁVEL, VALOR PAGO - TRIBUTÁVEL
```

⚠️ **REGRA CRÍTICA — FÉRIAS + 1/3**: Mesmo que a sentença defira múltiplos períodos de férias
(ex: 4 períodos aquisitivos vencidos + férias proporcionais), criar APENAS UMA entrada em
`verbas_principais` com `estrategia_preenchimento: "expresso_direto"` e
`expresso_alvo: "FÉRIAS + 1/3"`. Os períodos específicos vão EXCLUSIVAMENTE no array
`ferias.periodos`. O PJE-Calc gerencia os períodos na página Férias — não como verbas autônomas
separadas. NUNCA criar múltiplas verbas "Férias" em `verbas_principais`.

### `expresso_adaptado`
A verba não existe literal, mas pode adaptar uma similar:
- "Estabilidade Gestante / Acidentária" → expresso_alvo="INDENIZAÇÃO ADICIONAL", nome_pjecalc adaptado
- "Indenização Lei 9.029" → expresso_alvo="INDENIZAÇÃO POR DANO MORAL"
- "Salário Família como verba autônoma" → expresso_alvo="SALÁRIO RETIDO" (excepcional)

### `manual`
Verba muito específica sem similar:
- Multas convencionais com cláusulas específicas
- Indenizações Lei estadual

## 4.2 INCIDÊNCIAS POR TIPO DE VERBA

| Tipo de verba | IRPF | CS/INSS | FGTS | Notas |
|---|---|---|---|---|
| Salário base, diferenças salariais | ✓ | ✓ | ✓ | salariais |
| Horas extras, adicionais (insalubridade etc.) | ✓ | ✓ | ✓ | salariais |
| 13º Salário | ✓ | ✓ | ✓ | (CS em separado por convenção) |
| Aviso Prévio | ✓ | ✓ | ✓ | salarial |
| Férias gozadas | ✓ | ✓ | ✓ | salariais |
| Férias indenizadas + 1/3 | ✗ | ✗ | ✗ | art. 28 §9 Lei 8.212 |
| Indenização por Dano Moral, Material, Estético | ✗ | ✗ | ✗ | indenizatórias |
| Indenização Adicional, Estabilidade | ✗ | ✗ | ✗ | indenizatórias |
| Multa 477 CLT | ✗ | ✗ | ✗ | indenizatória |
| Multa Convencional / Cláusula penal | ✗ | ✗ | ✗ | indenizatória |
| FGTS + 40% | n/a | n/a | n/a | é o próprio FGTS |
| Vale Transporte | ✗ | ✗ | ✗ | reembolso |

## 4.3 CARACTERÍSTICA → OCORRÊNCIA AUTOMÁTICA

| caracteristica | ocorrencia_pagamento default |
|---|---|
| COMUM | MENSAL |
| DECIMO_TERCEIRO_SALARIO | DEZEMBRO |
| AVISO_PREVIO | DESLIGAMENTO |
| FERIAS | PERIODO_AQUISITIVO |

## 4.4 VALOR vs FORMULA_CALCULADO

### Quando `valor=INFORMADO`
A sentença determina valor fixo (R$ X). Preencher:
```json
"valor_devido": {"tipo": "INFORMADO", "valor_informado_brl": X, "proporcionalizar": false},
"formula_calculado": null
```

Casos típicos: indenização por dano moral, multa fixa, indenização Lei 9.029.

### Quando `valor=CALCULADO`
A verba é calculada por fórmula. Preencher:
```json
"valor_devido": {"tipo": "CALCULADO"},
"formula_calculado": {
  "base_calculo": {"tipo": "HISTORICO_SALARIAL", "historico_nome": "ÚLTIMA REMUNERAÇÃO", "proporcionaliza": "NAO"},
  "divisor": {"tipo": "OUTRO_VALOR", "valor": 220},
  "multiplicador": 1.50,
  "quantidade": {"tipo": "INFORMADA", "valor_mensal": 44.0}
}
```

Tipos de base:
- `MAIOR_REMUNERACAO` — usa o valor do contrato
- `HISTORICO_SALARIAL` — referencia um histórico cadastrado por nome
- `SALARIO_DA_CATEGORIA` — piso da categoria
- `SALARIO_MINIMO` — salário mínimo nacional
- `VALE_TRANSPORTE` — específico

### Campo `quantidade` — regra de preenchimento para Horas Extras

O PJE-Calc sempre apura HE a partir da **quantidade mensal**. O campo `quantidade` é OBRIGATÓRIO
para verbas de HE calculadas. Existem dois caminhos mutuamente exclusivos:

#### Opção A — Quantidade mensal informada (sentença fixa quantidade de HE)
Usar quando a sentença especifica diretamente quantas horas extras o reclamante fazia.
Converter para horas/mês e preencher:
```json
"quantidade": {"tipo": "INFORMADA", "valor_mensal": <float>}
```
Regras de conversão:
- Sentença diz **X horas extras diárias** → `valor_mensal = X × 22` (dias úteis médios/mês)
- Sentença diz **X horas extras semanais** → `valor_mensal = round(X × 4.33, 1)`
- Sentença diz **X horas extras mensais** → `valor_mensal = X` (usar direto)
- Sentença menciona "excedentes da 44ª semanal" com escala 6×1 → `valor_mensal = 26` (1d×26sem/mês)

#### Opção B — Importada do Cartão de Ponto (sentença fixa jornada/horário)
Usar quando a sentença descreve a jornada de trabalho (horários de entrada/saída, escalas,
intervalos) mas não fixa uma quantidade exata de HE. O PJE-Calc calculará as HE com base
no Cartão de Ponto preenchido.
```json
"quantidade": {"tipo": "IMPORTADA_DO_CARTAO"}
```
Nesse caso, preencher obrigatoriamente `cartao_de_ponto` (seção 5) com a jornada extraída
da sentença e usar as mesmas datas `data_inicial`/`data_final` da verba HE.

**Nunca** omitir `quantidade` nem deixar como `null` quando `valor=CALCULADO` — o PJE-Calc
calculará 0 e a verba terá valor zero.

## 4.5 REFLEXOS

Para cada verba principal, listar reflexos. **Padrão de incidência reflexa:**

| Verba principal | Reflexos típicos |
|---|---|
| Adicional (insalubridade, periculosidade, noturno...) | Aviso Prévio, Férias+1/3, Multa 477, 13º |
| Horas Extras 50% / 100% | Aviso Prévio, Férias+1/3, Multa 477, 13º, **RSR/Feriado** |
| Comissão / Gorjeta | Aviso Prévio, Férias+1/3, Multa 477, 13º, **RSR** |
| Diferença Salarial | Aviso Prévio, Férias+1/3, Multa 477, 13º |
| Indenizações pós-contrato (Estabilidade, Dispensa Discriminatória) | 13º, Férias+1/3, **FGTS+40%** (manual) |

Cada reflexo:
```json
{
  "id": "r01-01",
  "nome": "Aviso Prévio sobre Diferença Salarial",
  "estrategia_reflexa": "checkbox_painel",
  "expresso_reflex_alvo": "AVISO PRÉVIO SOBRE DIFERENÇA SALARIAL",
  "parametros_override": null,
  "ocorrencias_override": null
}
```

`estrategia_reflexa`:
- `checkbox_painel` (default) — marcar checkbox no painel da verba principal
- `manual` — quando o reflexo NÃO está pré-cadastrado (raro: FGTS sobre estabilidade)

# 5. CARTAO_DE_PONTO

Preencher **somente na Opção B** (ver seção 4.4): sentença fixa jornada/horário de trabalho
mas não especifica quantidade de HE — o PJE-Calc apurará as HE a partir da jornada cadastrada.

Deixar `null` quando:
- Opção A foi usada (quantidade informada diretamente), ou
- Não há horas extras no cálculo.

```json
{
  "data_inicial": "DD/MM/YYYY",
  "data_final":   "DD/MM/YYYY",
  "apuracao": {
    "tipo": "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL"
  },
  "jornada_padrao": {
    "segunda_hhmm": "08:00",
    "terca_hhmm":   "08:00",
    "quarta_hhmm":  "08:00",
    "quinta_hhmm":  "08:00",
    "sexta_hhmm":   "08:00",
    "sabado_hhmm":  "04:00",
    "domingo_hhmm": null
  }
}
```

Valores de `apuracao.tipo` (usar o mais adequado à sentença):
- `HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL` — padrão; PJE-Calc compara diária vs semanal
- `HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA` — só conta excedentes do limite diário
- `HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL` — só conta excedentes do limite semanal
- `HORAS_EXTRAS_CONFORME_SUMULA_85` — escalas especiais com RSR compensado

`data_inicial`/`data_final`: mesmas datas da verba HE no JSON (`periodo_inicio`/`periodo_fim`).

# 6. FALTAS, FERIAS

```json
"faltas": [{"data_inicio": "DD/MM/YYYY", "data_fim": "DD/MM/YYYY", "justificada": true, "reinicia_ferias": false, "justificativa": "..."}],
"ferias": {
  "periodos": [{
    "periodo_aquisitivo_inicio": "DD/MM/YYYY", "periodo_aquisitivo_fim": "DD/MM/YYYY",
    "periodo_concessivo_inicio": "DD/MM/YYYY", "periodo_concessivo_fim": "DD/MM/YYYY",
    "prazo_dias": 30, "situacao": "INDENIZADAS|GOZADAS|PARCIAL_GOZADAS|NAO_DIREITO",
    "dobra": false, "abono": false, "dias_abono": 0, "gozo_1": {...}, "gozo_2": null
  }],
  "ferias_coletivas_inicio_primeiro_ano": null,
  "prazo_ferias_proporcionais": null
}
```

# 7. FGTS, CONTRIBUICAO_SOCIAL, IMPOSTO_DE_RENDA, HONORARIOS, CUSTAS, CORRECAO_JUROS_MULTA

(Veja docs/schema-v2/ para campos detalhados — formato JSON espelha exatamente.)

⚠️ Para `contribuicao_social.vinculacao_historicos_devidos`, deixar `{"modo": "automatica", "intervalos": []}` por padrão. Só usar `manual_por_periodo` se a sentença determinar bases diferentes por período.

⚠️ Para `correcao_juros_multa`, padrão pós-ADC 58 (após Set/2024):
```json
{
  "indice_trabalhista": "IPCAE",
  "juros": "TAXA_LEGAL",
  "base_juros_verbas": "VERBAS",
  "fgts": {"indice_correcao": "UTILIZAR_INDICE_TRABALHISTA"},
  ...
}
```

# 8. SECUNDÁRIAS (incluir somente se a sentença mencionar)

- `salario_familia`, `seguro_desemprego`, `previdencia_privada`, `pensao_alimenticia`: `null` se não mencionado
- `multas_indenizacoes`: `[]` se não mencionado (não confundir com Multa 477 que é verba)

# CHECKLIST FINAL ANTES DE RETORNAR

- [ ] `meta.schema_version === "2.0"`
- [ ] `processo.numero_processo` no formato CNJ
- [ ] `parametros_calculo.data_termino_calculo` ≥ MAX(periodo_fim de TODAS as verbas)
- [ ] `historico_salarial` cobre data_inicio_calculo até data_termino_calculo
- [ ] Cada verba com `valor=INFORMADO` tem `valor_devido.valor_informado_brl > 0`
- [ ] Cada verba com `valor=CALCULADO` tem `formula_calculado` preenchido
- [ ] Cada verba expresso_direto/expresso_adaptado tem `expresso_alvo` válido
- [ ] Cada reflexo tem `expresso_reflex_alvo` no formato "X SOBRE Y"
- [ ] Características COMUM/13o/Aviso/Férias com ocorrência derivada correta

Lembre-se: SOMENTE JSON na resposta. Sem texto extra."""


# ─── JSON Schema export para validação adicional ──────────────────────────


def get_json_schema_v2() -> dict:
    """Retorna o JSON Schema do PreviaCalculoV2 (Pydantic v2 model_json_schema)."""
    return PreviaCalculoV2.model_json_schema()


def validar_previa_v2(json_data: dict) -> tuple[bool, list[str]]:
    """Valida prévia contra schema v2.

    Returns:
        (is_valid, errors): tupla com flag e lista de erros
    """
    try:
        previa = PreviaCalculoV2.model_validate(json_data)
        if previa.meta.validacao.completude == "OK":
            return True, []
        return False, previa.meta.validacao.campos_faltantes + previa.meta.validacao.avisos
    except Exception as e:
        return False, [f"Erro de validação Pydantic: {e}"]


# ─── Função principal ──────────────────────────────────────────────────────


def extrair_previa_v2(
    texto_sentenca: str,
    pdf_bytes: bytes | None = None,
    extras: dict | None = None,
):
    """Extrai prévia v2 de uma sentença trabalhista.

    Args:
        texto_sentenca: texto extraído da sentença
        pdf_bytes: bytes do PDF (opcional, para multimodal)
        extras: dict com infos adicionais (numero_processo, etc.)

    Returns:
        PreviaCalculoV2 validada

    Raises:
        ExtracaoIncompletaError: se prévia não passa validação Pydantic
    """
    # Importação lazy para evitar dependência cíclica
    import anthropic
    from config import ANTHROPIC_API_KEY

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_msg = f"=== SENTENÇA ===\n{texto_sentenca[:30000]}\n=== EXTRAS ===\n{json.dumps(extras or {})}"

    response = client.messages.create(
        model="claude-sonnet-4-5",  # ou versão atual
        max_tokens=16000,
        system=SYSTEM_PROMPT_V2,
        messages=[{"role": "user", "content": user_msg}],
        temperature=0.0,
    )

    raw_text = response.content[0].text.strip()

    # Limpar wrapper markdown se houver
    if raw_text.startswith("```"):
        raw_text = "\n".join(raw_text.split("\n")[1:-1])

    json_data = json.loads(raw_text)

    # Validar via Pydantic
    previa = PreviaCalculoV2.model_validate(json_data)

    if previa.meta.validacao.completude != "OK":
        raise ExtracaoIncompletaError(
            f"Prévia incompleta: {previa.meta.validacao.campos_faltantes}"
        )

    return previa


class ExtracaoIncompletaError(ValueError):
    """Levantado quando a prévia extraída não passa validação."""
    pass
