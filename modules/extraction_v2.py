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
#
# ⚠️ INVARIANTES PERMANENTES — NÃO REVERTER (a menos que o usuário peça
# explicitamente). Cada invariante abaixo está documentada na string do
# prompt com o marcador "INVARIANTE PERMANENTE":
#
#   1. Verbas RECORRENTES (13º SALÁRIO, FÉRIAS + 1/3, AVISO PRÉVIO,
#      ADICIONAIS, DIFERENÇA SALARIAL, HORAS EXTRAS, COMISSÃO/GORJETA):
#      UMA ÚNICA entrada em `verbas_principais` com período total
#      (admissão → demissão) + `historico_salarial` segmentado por ano.
#      Validar via testes/test_prompt_invariants.py.
#
#   2. `data_termino_calculo` = MAX(periodo_fim) — não data_demissao.
#
#   3. Verbas DESLIGAMENTO: periodo_inicio = 1º dia do mês da demissão.
#
#   4. valor_informado_brl SEMPRE positivo (defesa também em normalizer).
#
#   5. Verbas DEDUÇÃO (VALOR PAGO/DEVOLUÇÃO): valor em valor_pago.valor_brl.
#
#   6. Histórico salarial CALCULADO: schema = {quantidade_pct, base_referencia}
#      (não base_calculo — esse é schema de verba).
#
# Se você for alterar o prompt, GARANTA que essas invariantes permanecem
# explícitas. O teste tests/test_prompt_invariants.py falha se alguma sumir.

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
  "contribuicao_social": null,   // OMITIR (= null) se a sentença NÃO mencionar regras específicas; defaults do PJE-Calc valem
  "imposto_de_renda": null,      // OMITIR (= null) se a sentença NÃO mencionar regras específicas; defaults do PJE-Calc valem
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

⚠ `doc_fiscal.numero`: quando o CPF/CNPJ NÃO constar na sentença nem nos
documentos anexados, emita `""` (string vazia — NUNCA null). O documento
fiscal das partes é OPCIONAL no PJE-Calc (não bloqueia o cálculo) — NÃO
listar como campo faltante nem como pendência. O usuário completa na prévia
só se quiser enviar o cálculo ao PJe depois.
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
  "modalidade_rescisao": "sem_justa_causa|justa_causa|pedido_demissao|rescisao_indireta|termino_contrato|acordo|outro",
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

⚠️ **`modalidade_rescisao` (OBRIGATÓRIO — determina as rescisórias)**: identifique
no DISPOSITIVO/fundamentação a modalidade EFETIVAMENTE reconhecida (não a pedida):
`justa_causa` | `sem_justa_causa` | `pedido_demissao` | `rescisao_indireta` |
`termino_contrato` | `acordo` | `outro`. Atenção: se a parte PEDIU rescisão
indireta/reversão da justa causa mas o juízo NEGOU (manteve a justa causa), use
`justa_causa`. Esse campo aciona a regra MODALIDADE DA RESCISÃO (Súmula 171) da
seção 4 — em `justa_causa`/`pedido_demissao` NÃO lance férias proporcionais/13º/
aviso/40% FGTS/seguro-desemprego.

⚠️ **REGRA CRÍTICA — `prescricao_quinquenal` (INVARIANTE PERMANENTE — NÃO REVERTER)**:

`prescricao_quinquenal = true` **APENAS** quando `(data_ajuizamento - data_admissao) ≥ 5 anos completos`.

Caso contrário, **OBRIGATORIAMENTE** `prescricao_quinquenal = false`.

**Razão técnica**: o PJE-Calc tem validador no save da Fase 2 que rejeita
explicitamente o checkbox com a mensagem *"Não é possível selecionar prescrição
quinquenal, pois o período entre a data de admissão e a data do ajuizamento é
menor que cinco anos."* Esse erro **bloqueia o save**, e como o cálculo nunca é
commitado ao DB, TODAS as fases subsequentes (Verbas, FGTS, Honorários, Custas,
Correção, Liquidar) trabalham em estado degenerado e falham em cascata.

**Razão jurídica**: prescrição quinquenal (CF art. 7º XXIX) só alcança verbas
anteriores ao último quinquênio. Em contratos < 5 anos, não há o que prescrever.

**Exemplos**:
- Contrato 04/2018–10/2024, ajuizamento 03/2026 → 7 anos e 11 meses → `true` ✓
- Contrato 04/2025–12/2025, ajuizamento 03/2026 → 10 meses → `false` (não `true`) ✓
- Contrato 01/2019–01/2024, ajuizamento 02/2024 → exatos 5 anos e 1 mês → `true` ✓

---

⚠️ **CRÍTICO — COERÊNCIA TEMPORAL DO CÁLCULO**:

### `data_termino_calculo` = MAX(periodo_fim de TODAS as verbas)

A data final do cálculo **DEVE coincidir com o termo final da parcela
mais projetada no tempo** — NUNCA é fixa em `data_demissao`.

Casos típicos que estendem além da demissão:
- **Aviso Prévio Indenizado** projeta o contrato (Lei 12.506/2011: 30+3/ano,
  máx 90). Ex.: 2 anos completos → +36 dias após data_demissao.
- **Estabilidade pós-contrato** (Gestante ADCT 10 II / Acidentária L8213
  art 118 / Lei 9.029) → meses ou anos.
- **Pensão Alimentícia / Vitalícia** → tempo todo da decisão.
- **Indenização Adicional Lei 7.238** → prazo do aviso.

Sem essa coerência: ocorrências projetadas saem do período, CS/IRPF zera,
liquidação pode ser rejeitada.

### Período de verbas com `ocorrencia_pagamento = DESLIGAMENTO`

Verbas rescisórias (Saldo Salário, Aviso Prévio, Multa 477, FGTS) devem ter:
- **`periodo_inicio` = 1º dia do mês da demissão** (NÃO a data da dispensa)
- `periodo_fim` = `data_demissao`

Razão: o PJE-Calc gera ocorrência para o MÊS inteiro. Se `periodo_inicio =
periodo_fim = data_demissao`, a ocorrência sai do período declarado e a
liquidação trava:
*"Todas as ocorrências da verba X devem estar contidas no período
estabelecido na página parâmetro da verba."*

**❌ ERRADO**: Multa 477 com `periodo_inicio=09/01/2026, periodo_fim=09/01/2026`
**✅ CERTO**:  Multa 477 com `periodo_inicio=01/01/2026, periodo_fim=09/01/2026`

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

⚠️ **`tipo_valor` do histórico salarial (NÃO confundir com schema de verba)**:

- **`CALCULADO`** (**preferido sempre que aplicável**): exige `calculado` com APENAS 2 campos:
  ```json
  "tipo_valor": "CALCULADO", "valor_brl": null,
  "calculado": {"quantidade_pct": 1.0, "base_referencia": "SALARIO_MINIMO"}
  ```
  - `quantidade_pct` (float): **MULTIPLICADOR**, NÃO percentual 0–100.
    - `1.0` = 100% = 1× referência (caso típico: salário = 1 SM)
    - `1.10` = 110% = 1.10× referência
    - `0.50` = 50% = ½× referência
    - **NUNCA emitir 100.0** — PJE-Calc interpretaria como **100 salários mínimos** (R$ 141.200+).
  - `base_referencia` (str): tabela cadastrada. Valores válidos: `SALARIO_MINIMO`,
    `SALARIO_DA_CATEGORIA` (piso), `MAIOR_REMUNERACAO`, `VALE_TRANSPORTE`.

  ❌ **NUNCA emitir** `calculado: {"base_calculo": {"tipo": "SALARIO_MINIMO"}}` —
  esse é o formato de **fórmula de verba**, NÃO de histórico salarial.

- **`INFORMADO`**: `valor_brl` direto em reais, `calculado: null`.
  ```json
  "tipo_valor": "INFORMADO", "valor_brl": 1320.00, "calculado": null
  ```
  Use somente quando o valor for **arbitrário** (não corresponde a uma tabela cadastrada).

⚠️ **REGRA INVARIANTE — NÃO REVERTER — evolução de valores = 1 entrada com `evolucao`**:

Quando a sentença indicar que o **MESMO componente salarial** (ex.: SALÁRIO BASE,
ADICIONAL DE PERICULOSIDADE) teve **valores diferentes ao longo do tempo**
(dissídio anual, reajuste negociado, evolução natural), emita **UMA ÚNICA entrada**
no `historico_salarial` cobrindo todo o período + campo `evolucao` listando
cada mudança de valor:

```json
{
  "nome": "SALÁRIO",
  "parcela": "FIXA",
  "incidencias": {"fgts": true, "cs_inss": true},
  "competencia_inicial": "04/2021",
  "competencia_final": "10/2024",
  "tipo_valor": "INFORMADO",
  "valor_brl": 2577.20,
  "calculado": null,
  "evolucao": [
    {"competencia": "04/2021", "valor_brl": 2577.20},
    {"competencia": "05/2021", "valor_brl": 2650.31},
    {"competencia": "07/2021", "valor_brl": 2928.00},
    {"competencia": "10/2022", "valor_brl": 3225.48},
    {"competencia": "08/2024", "valor_brl": 3479.32}
  ]
}
```

❌ **NUNCA segmente** o MESMO componente em N entradas como
"SALÁRIO ABRIL/2021", "SALÁRIO MAIO-JUN/2021" — polui o histórico do PJE-Calc.

✅ **SIM, separe** em N entradas quando há COMPONENTES DIFERENTES (cada um
pode ter sua própria `evolucao`):
- `SALÁRIO BASE` (1 entrada com sua evolução de valores)
- `ADICIONAL DE PERICULOSIDADE` (outra entrada com sua evolução)
- `COMISSÕES` (outra entrada)

Tabela de decisão:

| Cenário | Quantas entradas? | Usa `evolucao`? |
|---|---|---|
| Salário fixo durante todo contrato | 1 | não (`null`) |
| Salário com dissídios/reajustes (mesmo cargo) | 1 | **sim** |
| Salário mínimo (legal) durante todo contrato | 1 | não (use CALCULADO/SALARIO_MINIMO) |
| Salário base + adicional de insalubridade | 2 | cada uma pode ter `evolucao` |
| Salário + comissão variável mensal | 2 (uma fixa, uma com `evolucao` mensal) | sim na 2ª |

---

⚠️ **REGRA INVARIANTE — NÃO REVERTER — salário mínimo = 1 entrada CALCULADO**:

Quando a sentença indicar que o salário é o mínimo vigente (ou múltiplo fixo dele:
1 SM, 2 SM, 1.5 SM…), emita **UMA ÚNICA entrada** no `historico_salarial`:
- `tipo_valor: CALCULADO`
- `calculado.quantidade_pct: 1.0` (ou o múltiplo correto)
- `calculado.base_referencia: SALARIO_MINIMO`
- `competencia_inicial` = início do contrato (ou início do cálculo)
- `competencia_final` = fim do contrato (ou término do cálculo)

PJE-Calc tem a **tabela oficial do SM por competência** (desde 01/1967) e aplica
o valor certo de cada mês automaticamente — **NUNCA segmente em "SM 2023", "SM 2024",
"SM 2025"**. Isso cria múltiplos históricos desnecessários, polui a listagem e dificulta
a conferência humana.

Para piso normativo (categoria profissional) com valores tabelados: mesmo padrão, usar
`SALARIO_DA_CATEGORIA` como `base_referencia`.

Mesma lógica para evolução salarial — preferir 1 entrada cobrindo todo o período sempre
que possível. Só segmentar se a sentença trouxer valor **explicitamente diferente**
para um período específico (ex.: dissídio negociado em data X com valor R$ Y) que NÃO
corresponda a tabela cadastrada — nesse caso, INFORMADO segmentado.

# 4. VERBAS_PRINCIPAIS (CORE — lista de verbas deferidas)

⚠️ **REGRA CRÍTICA — SÓ VERBAS EFETIVAMENTE DEFERIDAS (INVARIANTE PERMANENTE — NÃO REVERTER)**:

Lance APENAS as verbas **efetivamente deferidas no DISPOSITIVO** (as alíneas
"julgar procedente" / "procedente em parte" / "condenar a reclamada a pagar").
O DISPOSITIVO é a fonte da verdade do que é devido — não a fundamentação isolada.

**NUNCA lance uma verba que a sentença MENCIONA como potencialmente devida e em
seguida NEGA, exclui ou declara inexistente.** Leia a fundamentação INTEIRA da
verba antes de lançá-la: uma parcela citada num parágrafo e afastada no seguinte
**NÃO é devida** e **NÃO gera verba**. O mesmo vale para tudo que o dispositivo
"julga improcedente" / "indefere".

Armadilhas concretas (NÃO repetir):
- **Verba citada e depois negada por inexistência factual.** Ex. (caso ARIANE
  0000566-12): a fundamentação diz "são devidas saldo de salário E **férias
  vencidas + 1/3**, se ainda não pagas"; o parágrafo seguinte esclarece "**não
  havia férias vencidas pendentes** — todos os períodos aquisitivos foram
  regularmente fruídos". → **NÃO lance FÉRIAS + 1/3 vencidas.** Saiu 0.
- **Dispositivo de improcedência (justa causa).** "Julgar improcedentes os
  pedidos de ... férias proporcionais + 1/3, 13º proporcional, aviso prévio,
  multa 40% FGTS, seguro-desemprego ..." → **nenhuma dessas vira verba.**
- **Reflexo ≠ verba autônoma.** "Cabem reflexos sobre férias + 1/3 e 13º
  [sobre a diferença/integração]" são REFLEXOS (checkbox_painel) da verba-base,
  **não** verbas FÉRIAS / 13º standalone. Lançá-las em duplicidade infla a
  condenação (a automação NÃO detecta — o PJE-Calc liquida assim mesmo).

Teste antes de incluir QUALQUER verba: "o DISPOSITIVO a deferiu como parcela
autônoma, OU ela é só reflexo de outra, OU foi mencionada e negada?" Só a
PRIMEIRA hipótese vira item em `verbas_principais`.

**MODALIDADE DA RESCISÃO determina as rescisórias (Súmula 171 TST / CLT art.
482):** identifique a modalidade no dispositivo/fundamentação ANTES de listar.
- **JUSTA CAUSA do empregado** OU **PEDIDO DE DEMISSÃO** → são INDEVIDOS (NÃO
  lance, salvo deferimento expresso e excepcional): férias PROPORCIONAIS + 1/3,
  13º PROPORCIONAL, aviso prévio (indenizado ou trabalhado), multa de 40% do
  FGTS, saque/liberação do FGTS, seguro-desemprego. PERMANECEM apenas: **saldo
  de salário**, **férias VENCIDAS + 1/3** (somente se existirem períodos
  aquisitivos completos NÃO gozados e NÃO pagos — se a sentença disser que
  foram fruídas, NÃO lance) e o que a sentença **expressamente** deferir
  (ex.: diferenças salariais e seus reflexos no curso do contrato).
- **Dispensa SEM justa causa** / **rescisão indireta** → as rescisórias acima
  são devidas (conforme deferimento).
Não confunda "férias VENCIDAS" (adquiridas, devidas mesmo na justa causa se não
gozadas) com "férias PROPORCIONAIS" (indevidas na justa causa).

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

⚠️ **DOIS campos `ocorrencias_override` DIFERENTES** — NÃO CONFUNDIR:

| Onde aparece | Tipo | Quando usar | Formato |
|---|---|---|---|
| `verbas_principais[N].ocorrencias_override` | **OBJETO** `OcorrenciasOverride` ou `null` | sentença determina valores DIFERENTES por mês para a VERBA (raro) | `{"modo":"valores_mensais","valores_mensais":[{"mes":"06/2024","valor_devido":1500.00},...]}` |
| `cartao_de_ponto.ocorrencias_override` | **LISTA** de `OcorrenciaJornada` | sábados alternados/plantões — exceções da jornada (comum) | `[{"data":"15/06/2024","turnos":[{"entrada":"07:00","saida":"12:00"}]},...]` |

**Default para verbas**: `null` (não preencher; PJE-Calc gera ocorrências automáticas via Período + Ocorrência).
**Default para cartão**: `[]` (lista vazia) ou lista de dias específicos.

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

⚠️ **REGRA CRÍTICA — FÉRIAS + 1/3 (INVARIANTE PERMANENTE — NÃO REVERTER)**:
Mesmo que a sentença defira múltiplos períodos de férias
(ex: 4 períodos aquisitivos vencidos + férias proporcionais), criar APENAS UMA entrada em
`verbas_principais` com `estrategia_preenchimento: "expresso_direto"` e
`expresso_alvo: "FÉRIAS + 1/3"`. Os períodos específicos vão EXCLUSIVAMENTE no array
`ferias.periodos`. O PJE-Calc gerencia os períodos na página Férias — não como verbas autônomas
separadas. NUNCA criar múltiplas verbas "Férias" em `verbas_principais`.

⚠️ **REGRA CRÍTICA — 13º SALÁRIO (INVARIANTE PERMANENTE — NÃO REVERTER)**:
Mesmo que o contrato abranja vários anos com
remunerações diferentes (ex: 2023-2024-2025-2026), criar **APENAS UMA** entrada
`13º SALÁRIO` em `verbas_principais`, com:
- `periodo_inicio` = **início do período DEFERIDO na sentença** (ver regra da
  fração deferida abaixo — só usar a data de admissão quando a condenação
  abranger o contrato inteiro)
- `periodo_fim` = data de demissão
- `caracteristica = "DECIMO_TERCEIRO_SALARIO"`. **`ocorrencia_pagamento`**:
  - `"DEZEMBRO"` quando o período DEFERIDO contém algum dezembro (13º de ano(s)
    completo(s) — a ocorrência é colocada em dezembro de cada ano);
  - **`"DESLIGAMENTO"`** quando o 13º deferido é SÓ o **proporcional do ano da
    rescisão** e o contrato termina no meio do ano (período SEM dezembro —
    ex.: 01/01/2026→25/04/2026). Com DEZEMBRO a ocorrência cairia fora do
    período e o PJE-Calc rejeita ('Todas as ocorrências da verba 13º SALÁRIO
    devem estar contidas no período'). DESLIGAMENTO coloca a ocorrência na
    data da rescisão, dentro do período. (Caso LUCAS 0000610-31, #72.)
- `quantidade.tipo = "AVOS"`
- `base_calculo.tipo = "HISTORICO_SALARIAL"` referenciando UM histórico (geralmente o mais recente,
  ex: "SALÁRIO MÍNIMO 2025-2026" ou "ÚLTIMA REMUNERAÇÃO")
- **`divisor.tipo = "OUTRO_VALOR"` e `divisor.valor = 12` (constante CLT — 12 avos por ano)**
- **`multiplicador = 1` e quantidade.tipo = "AVOS"** (PJE-Calc apura avos automaticamente)

⚠️ **REGRA CRÍTICA — FÉRIAS + 1/3 (DIVISOR CLT — INVARIANTE PERMANENTE — NÃO REVERTER)**:
- **`divisor.tipo = "OUTRO_VALOR"` e `divisor.valor = 12` (constante CLT — 12 avos por período aquisitivo)**
- **`multiplicador = 1.33` (1/3 adicional constitucional)** e quantidade.tipo = "AVOS"

⚠️ **REGRA CRÍTICA — AVISO PRÉVIO (DIVISOR = 30 — INVARIANTE PERMANENTE — NÃO REVERTER)**:
O aviso prévio indenizado é calculado em BASE DIÁRIA: `valor = base × dias / 30`.
Isso é obrigatório porque o aviso é PROPORCIONAL (Lei 12.506/2011: 30 dias + 3 por
ano completo — ex.: 1 ano ⇒ 33 dias; 2 anos ⇒ 36 dias; ...).
- **`divisor.tipo = "OUTRO_VALOR"` e `divisor.valor = 30` (SEMPRE 30 — base diária)**
- **`quantidade.tipo = "INFORMADA"` e `quantidade.valor = <nº EXATO de dias de aviso deferidos>`**
  (30 se contrato < 1 ano; 33 para 1 ano; 30+3×anos completos; ou o nº que a sentença fixar)
- **`multiplicador = 1`**, base = MAIOR_REMUNERACAO
- **NUNCA emitir `divisor.valor = 1` com `quantidade.valor = 1`** ("1 mês") — isso
  liquida só 30 dias e PERDE os dias proporcionais (bug REGINALDO 0001876-87:
  33 dias deferidos saíram como 30). O divisor 1 subestima o aviso e todos os
  seus reflexos.

⚠️ **REGRA CRÍTICA — MULTA DO ART. 467 DA CLT (INVARIANTE PERMANENTE — NÃO REVERTER)**:
A multa do art. 467 (50% sobre verbas incontroversas) **NUNCA é verba principal
autônoma** — ela NÃO existe no rol Expresso e lançá-la como verba própria de
"0.5 × salário" calcula um valor ERRADO (50% de 1 salário, não 50% das verbas).

**Bug histórico (RODRIGO 0000447-51, 11/06/2026):** IA emitiu MULTA 467 como
verba principal (`expresso_alvo: MULTA DO ARTIGO 477` + multiplicador 0.5) →
Expresso não criou a 2ª verba, os reflexos "MULTA 467 SOBRE X" ficaram todos
desmarcados e a multa simplesmente FALTOU na liquidação.

**Implementação correta** — a multa 467 entra em DOIS lugares:
1. **Reflexos** em cada verba rescisória estrita listada na sentença — para
   cada verba (SALDO DE SALÁRIO, AVISO PRÉVIO, 13º SALÁRIO, FÉRIAS + 1/3...),
   adicionar em `reflexos`:
   ```json
   {
     "id": "rNN-467",
     "nome": "Multa do Art. 467 sobre <VERBA>",
     "estrategia_reflexa": "checkbox_painel",
     "expresso_reflex_alvo": "MULTA DO ARTIGO 467 DA CLT SOBRE <NOME_PJECALC_DA_VERBA>",
     "parametros_override": null,
     "ocorrencias_override": null
   }
   ```
   (O PJE-Calc já cria esses candidatos automaticamente no painel "Exibir"
   de cada verba — o bot apenas MARCA o checkbox.)
2. **`fgts.multa_artigo_467: true`** quando a sentença incluir a multa de 40%
   do FGTS na base da multa 467 (caso típico).

Respeite a BASE da sentença: se ela exclui alguma verba (ex.: multa 477,
indenizações), NÃO adicionar o reflexo 467 naquela verba.

⚠️ **ATENÇÃO ESPECIAL**: para **13º SALÁRIO** e **FÉRIAS + 1/3**, o divisor é uma
**constante legal de 12** (CLT art. 130 / Constituição art. 7º XVII). NUNCA usar
`divisor.valor = 1` ou outro valor — o PJE-Calc multiplicaria o cálculo por 12,
gerando erro grave. O PJE-Calc Expresso default JÁ preenche `divisor=12` para
essas verbas; o JSON v2 deve REPETIR esse valor para garantir consistência.

⚠️ **REGRA CRÍTICA — INDENIZAÇÃO POR DANO MORAL / SÚMULA 439 TST (INVARIANTE PERMANENTE — NÃO REVERTER)**:
Nas verbas de **INDENIZAÇÃO POR DANO MORAL**, o campo
`parametros.juros_aplicar_sumula_439` deve ser **`false`** (opção "Juros — Aplicar
Súmula nº 439 do TST" DESMARCADA). Deixar `true` anteciparia os juros para a data
do ajuizamento de forma indevida para o padrão adotado. Emitir sempre `false`
(o normalizer também força false como salvaguarda).

O PJE-Calc **gera automaticamente** as ocorrências de 13º para cada ano (DEZEMBRO de cada ano
mais a ocorrência de DESLIGAMENTO no ano da rescisão), e a **base de cada ocorrência respeita
o `historico_salarial` vigente na competência** correspondente — você só precisa garantir que
o array `historico_salarial` cubra cada ano com o valor correto.

⚠️ **REGRA CRÍTICA — FRAÇÃO DEFERIDA limita o período (INVARIANTE PERMANENTE — NÃO REVERTER)**:
A regra de "verba única" NÃO significa "período = contrato inteiro". O período da
verba deve ser o **MENOR período que gera exatamente os avos/parcelas DEFERIDOS
na sentença**. A liquidação segue estritamente o título executivo.

**Bug histórico (THAÍS 0000183-68, 10/06/2026):** sentença deferiu APENAS
"13º salário proporcional de 2025, na fração de 2/12 (R$ 403,70)". A IA emitiu
`periodo 22/05/2023 → 20/01/2025` (contrato inteiro) → PJE-Calc liquidou
7/12 de 2023 + 12/12 de 2024 + 2/12 de 2025 = R$ 4.238,83 — **R$ 3.835,13 a
maior** que a condenação.

**✅ CERTO para aquela sentença:** `periodo_inicio: "01/01/2025"`,
`periodo_fim: "20/01/2025"` (gera apenas os 2/12 de 2025 com a projeção do AP).

Aplicação:
- Sentença defere "13º proporcional de YYYY (N/12)" → período = 01/01/YYYY até
  a demissão (ou a fração específica indicada).
- Sentença defere "13º de todo o período contratual" / "13º dos anos X, Y, Z"
  → período cobre exatamente esses anos.
- Mesma lógica vale para FÉRIAS (emitir em `ferias.periodos` SOMENTE os
  períodos aquisitivos deferidos) e qualquer verba recorrente parcialmente
  deferida.

**❌ ERRADO** (gera 4 verbas separadas + 4 históricos separados — INSS duplicado, listagem poluída, conferência inviável):
```
v04: 13º SALÁRIO período 09/02/2023 → 31/12/2023, histórico "SM 2023"  (INFORMADO R$ 1.320)
v05: 13º SALÁRIO período 01/01/2024 → 31/12/2024, histórico "SM 2024"  (INFORMADO R$ 1.412)
v06: 13º SALÁRIO período 01/01/2025 → 31/12/2025, histórico "SM 2025"  (INFORMADO R$ 1.518)
v07: 13º SALÁRIO período 01/01/2026 → 09/01/2026, histórico "SM 2026"  (INFORMADO R$ 1.622)
```

**✅ CERTO** (1 verba + **1 histórico** CALCULADO/SALARIO_MINIMO):
```
v04: 13º SALÁRIO período 09/02/2023 → 09/01/2026, histórico "SALARIO MINIMO"
+ historico_salarial: [
    {nome: "SALARIO MINIMO", competencia_inicial: "02/2023", competencia_final: "01/2026",
     tipo_valor: "CALCULADO", valor_brl: null,
     calculado: {quantidade_pct: 1.0, base_referencia: "SALARIO_MINIMO"}}
  ]
```

PJE-Calc resolve o valor de cada competência pela tabela oficial (R$ 1.320 em 2023,
R$ 1.412 em 2024, R$ 1.518 em 2025, R$ 1.622 em 2026 etc.). **NUNCA** segmente o
histórico por ano para o caso de salário mínimo — isso é redundante e poluente.

A mesma regra de **uma verba só com período total** vale para outras verbas de natureza
recorrente que se estendem por vários anos (Adicional Noturno, Adicional de Insalubridade,
Adicional de Periculosidade, Diferença Salarial, Horas Extras): SEMPRE uma só entrada com
período total + histórico_salarial **consolidado**.

### `expresso_adaptado`
A verba não existe literal, mas pode adaptar uma similar:
- "Estabilidade Gestante / Acidentária" → expresso_alvo="INDENIZAÇÃO ADICIONAL", nome_pjecalc adaptado
- "Indenização Lei 9.029" → expresso_alvo="INDENIZAÇÃO POR DANO MORAL"
- "Salário Família como verba autônoma" → expresso_alvo="SALÁRIO RETIDO" (excepcional)

⚠️ **REGRA — nome customizado quando o Expresso é genérico:**
Verbas Expresso com nomes amplos exigem `nome_pjecalc` específico (e estratégia
**`expresso_adaptado`**), porque o nome genérico não comunica qual é a verba real:
- "RESTITUIÇÃO / INDENIZAÇÃO DE DESPESA" → use `nome_pjecalc` específico da sentença:
  "RESTITUIÇÃO DE VALE-ALIMENTAÇÃO", "INDENIZAÇÃO USO VEÍCULO PRÓPRIO",
  "REEMBOLSO COMBUSTÍVEL", "RESTITUIÇÃO DE DESCONTOS INDEVIDOS", etc.
- "INDENIZAÇÃO POR DANO MATERIAL" → use `nome_pjecalc` específico:
  "DANO MATERIAL — DESPESAS MÉDICAS", "PERDAS E DANOS — VEÍCULO", etc.
- "INDENIZAÇÃO ADICIONAL" → use `nome_pjecalc` específico:
  "ESTABILIDADE GESTANTE", "ESTABILIDADE ACIDENTÁRIA",
  "INDENIZAÇÃO LEI 12.506/2011", etc.
- "MULTA CONVENCIONAL" → use `nome_pjecalc` específico:
  "MULTA CCT 2024 CLÁUSULA X", etc.

Quando `nome_pjecalc` for diferente do `expresso_alvo`, a estratégia DEVE ser
`expresso_adaptado` (NÃO `expresso_direto`). A automação renomeia o campo "Nome"
no PJE-Calc para refletir a verba real da condenação.

⚠️ **INVARIANTE PERMANENTE — `expresso_alvo` = NOME CANÔNICO EXATO — NÃO REVERTER**:
Em `expresso_direto` E `expresso_adaptado`, o campo `expresso_alvo` DEVE ser a
**cópia LITERAL do nome canônico** de uma das 54 verbas do rol Expresso do
PJE-Calc (como listadas acima) — é por esse nome que a automação localiza o
checkbox na tela de Lançamento Expresso. NUNCA coloque em `expresso_alvo`:
- ❌ o nome renomeado/adaptado (esse vai em `nome_pjecalc`);
- ❌ o nome da verba na sentença;
- ❌ variações, abreviações ou paráfrases do nome canônico.
No `expresso_adaptado` os dois campos coexistem: `expresso_alvo` = verba
canônica BASE (para achar o checkbox); `nome_pjecalc` = nome final desejado
(a automação renomeia DEPOIS de lançar). Se nenhuma das 54 servir de base,
use estratégia `manual` — não invente um `expresso_alvo`.

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

### ⚠️ REGRA CRÍTICA — `periodo_fim` vs `data_demissao`

**O PJE-Calc REJEITA a liquidação** com a mensagem _"A data final não pode
ser maior que a data demissão, para o caso de 'Ocorrências de Pagamento'
diferentes de Mensal"_ quando:

- `ocorrencia_pagamento ∈ {DESLIGAMENTO, DEZEMBRO, PERIODO_AQUISITIVO}` (ou seja: NÃO-MENSAL)
- E `periodo_fim > data_demissao`

**Como evitar:**

| Caso | Configuração correta |
|---|---|
| Verba rescisória dentro do contrato (Saldo Salário, 13º proporcional, Férias+1/3 proporcionais, Aviso Prévio Indenizado) | `periodo_fim ≤ data_demissao` |
| Avos de 13º do ano da demissão | `periodo_inicio = 01/01/{ano_demissão}`, `periodo_fim = data_demissao` |
| Avos de Férias do período aquisitivo aberto | `periodo_fim = data_demissao` |
| Aviso Prévio Indenizado projetado (Lei 12.506/2011) | EXCEÇÃO: pode estender até 90 dias após demissão |
| Verba pós-contratual (Estabilidade Gestante/Acidentária, Lei 9.029) | `ocorrencia_pagamento = MENSAL` (não DESLIGAMENTO) + `periodo_fim` ≤ data_termino_calculo |

**❌ ERRADO**: `13º SALÁRIO` com `ocorrencia=DEZEMBRO` + `periodo_fim=23/01/2026` (data ajuizamento, posterior à demissão 27/11/2025)
**✅ CERTO**: `13º SALÁRIO` com `ocorrencia=DEZEMBRO` + `periodo_fim=27/11/2025` (data demissão)

Se a sentença mandar pagar verba PÓS-demissão (ex.: estabilidade): use
`ocorrencia=MENSAL`, NÃO DESLIGAMENTO/DEZEMBRO/PERIODO_AQUISITIVO.

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
  "quantidade": {"tipo": "INFORMADA", "valor": 44.0}
}
```

**`base_calculo.tipo` — ENUM OBRIGATÓRIO (exatamente um destes 5 valores):**
| Valor | Quando usar |
|---|---|
| `MAIOR_REMUNERACAO` | Usa o valor do contrato (maior remuneração cadastrada) |
| `HISTORICO_SALARIAL` | Referencia um histórico cadastrado por nome (`historico_nome`) |
| `SALARIO_DA_CATEGORIA` | Piso da categoria profissional |
| `SALARIO_MINIMO` | Salário mínimo nacional |
| `VALE_TRANSPORTE` | Específico para vale-transporte |

⚠️ **PROIBIDO**: `OUTRO_VALOR`, `SALARIO_BASE`, `SALARIO_CONTRATUAL`, qualquer outro valor.
Se a sentença não indica claramente a base, usar `HISTORICO_SALARIAL`.

**`divisor.tipo` — ENUM OBRIGATÓRIO (exatamente um destes 4 valores):**
| Valor | Quando usar |
|---|---|
| `OUTRO_VALOR` | Divisor numérico explícito (preencher `valor` obrigatoriamente) |
| `CARGA_HORARIA` | PJE-Calc usa a carga horária mensal cadastrada |
| `DIAS_UTEIS` | PJE-Calc usa os dias úteis do período |
| `IMPORTADA_DO_CARTAO` | PJE-Calc calcula a partir do cartão de ponto |

⚠️ **PROIBIDO**: `PADRAO_MENSAL`, `MENSAL`, `DIARIO`, `HORAS_MENSAIS`, qualquer outro valor.

**`quantidade.tipo` — ENUM OBRIGATÓRIO (exatamente um destes 5 valores):**
| Valor | Quando usar |
|---|---|
| `INFORMADA` | Quantidade explícita fixada na sentença (preencher `valor` — ex.: 20 dias → `valor: 20.0`) |
| `IMPORTADA_DO_CALENDARIO` | PJE-Calc calcula a partir do calendário configurado |
| `IMPORTADA_DO_CARTAO` | PJE-Calc apura a partir do cartão de ponto |
| `AVOS` | Frações de período (ex: avos de 13º, avos de férias) |
| `APURADA` | PJE-Calc apura automaticamente com base nos parâmetros |

⚠️ **PROIBIDO**: `DIAS_UTEIS_TRABALHADOS`, `DIAS_TRABALHADOS`, `DIAS_CORRIDOS`,
`AVOS_CONTRATO`, `AVOS_PROPORCIONAL`, `CALCULADA`, qualquer outro valor.

### Campo `quantidade` — regra crítica de preenchimento para Horas Extras

O PJE-Calc sempre apura HE a partir da **quantidade MENSAL** (média de horas por mês).
O campo `quantidade.tipo` é **OBRIGATÓRIO** para HE CALCULADO e tem **duas alternativas
MUTUAMENTE EXCLUSIVAS**, escolhidas pela LEITURA da sentença:

---

#### ⚖️ ÁRVORE DE DECISÃO — INFORMADA × IMPORTADA_DO_CARTAO

```
Leia a parte da sentença sobre HE. Pergunte:
│
├── A sentença FIXA explicitamente a quantidade de HE?
│   (ex.: "2 HE diárias", "44ª semanal extrapolada", "10 HE/mês",
│         valor calculado direto pelo juiz como "30 HE/mês durante o contrato")
│   │
│   └── SIM → Opção A: `quantidade.tipo = "INFORMADA"` com `valor` MENSAL
│             ❌ NÃO preencha `cartao_de_ponto` (deixe null)
│
└── A sentença descreve uma JORNADA (horários, escala, intervalos)
    e cabe ao perito apurar as HE excedentes?
    (ex.: "trabalhava das 7h às 19h de seg a sáb, com 1h intervalo",
          "escala 12x36 noturna", "deveria ter intervalo de 1h e não tinha")
    │
    └── SIM → Opção B: `quantidade.tipo = "IMPORTADA_DO_CARTAO"`
              ✅ PREENCHA `cartao_de_ponto` (seção 5) com a jornada da sentença
              (mesmas datas data_inicial/data_final da verba HE)
```

**Regra de ouro**: a Opção A é **mais simples e robusta** — use sempre que a sentença
deixar a quantidade calculável. A Opção B é **necessária** quando há cartões a apurar,
intervalos descumpridos, escalas complexas, etc.

---

#### 🅰️ Opção A — Quantidade INFORMADA (sentença fixa qtd. de HE)

```json
"quantidade": {"tipo": "INFORMADA", "valor": <float>, "proporcionalizar": false}
```

**Tabela de conversão para horas/mês:**

| Como a sentença descreveu | Cálculo | Exemplo |
|---|---|---|
| `X horas extras DIÁRIAS` (jornada de 5d/sem) | `X × 22` | 2 HE/dia → 44 HE/mês |
| `X horas extras SEMANAIS` (calendário civil) | `round(X × 4.33, 1)` | 12 HE/sem → 51,9 HE/mês |
| `X horas extras MENSAIS` | `X` (uso direto) | 30 HE/mês → 30 |
| `X horas extras ANUAIS` | `round(X / 12, 1)` | 360/ano → 30/mês |
| Excedentes da **44ª semanal** com escala 6×1 (6h diárias + sáb) | escala já gera 4h sáb. Ajuste a divisor=44 e qtd=1 | — |
| Excedentes da **8ª diária** (Súmula 264/TST) em jornada de 8h+1 (9h totais) | 1h excedente × 22 = `22` | excedente padrão CLT |
| `excedentes da 220ª mensal` | sem extrapolação → **valor=0** ou usar Opção B | sem direito reconhecido |
| Sentença manda **"calcular como na inicial"** ou refere petição | EXTRAIR da petição/laudo. Se inalcançável → Opção B + cartão | — |
| Sentença dá **apenas a fórmula** sem qtd (ex.: divisor 220, mult. 50%) | quantidade ainda obrigatória → Opção B (mais seguro) | — |

**⚠️ NUNCA preencha `valor: 0` ou `valor: null`** em Opção A. Se a sentença não fixar
quantidade, use Opção B em vez de zerar (zero impede a apuração).

---

#### 🅱️ Opção B — IMPORTADA do Cartão de Ponto (sentença fixa jornada)

Use quando a sentença descreve **horários, intervalos, escalas ou ausência de registro
de ponto** — situações em que o PJE-Calc precisa apurar mensalmente a partir da
**Programação Semanal** ou **Escala** preenchida no Cartão de Ponto.

```json
"quantidade": {"tipo": "IMPORTADA_DO_CARTAO"}
```

**Obrigatório** preencher também `cartao_de_ponto` (§5) com:
- Mesma `data_inicial` / `data_final` da verba HE
- Jornada extraída (programação semanal OU escala) com entrada/saída por dia
- Intervalos (intra/inter)
- Adicional noturno (se aplicável)

**Casos típicos de Opção B:**

| Cenário | Como configurar |
|---|---|
| Jornada 7h-19h c/ 1h intervalo | Programação Semanal: turnos 07:00→12:00 e 13:00→19:00 |
| Escala 12×36 | Escala = `DOZE_POR_TRINTA_E_SEIS`, jornada 1 dia trabalho |
| 6×1 com sábado normal | Programação semanal com seg-sáb preenchidos |
| Intervalo intra suprimido | `cartao_de_ponto.intervalos.descanso_intra = false` |
| Adicional noturno deferido | `cartao_de_ponto.noturno.apurar = true` |

---

#### 📊 Como o PJE-Calc combina os campos da Fórmula

Quando `valor=CALCULADO`, o PJE-Calc aplica a fórmula:

```
((Base ÷ Divisor) × Multiplicador) × Quantidade
```

Para HE 50% padrão CLT:
- Base = HISTORICO_SALARIAL (ÚLTIMA REMUNERAÇÃO ou similar)
- Divisor = OUTRO_VALOR=220 (jornada mensal) OU CARGA_HORARIA (mesmo efeito)
- Multiplicador = 1.5 (50% adicional → adicional somado à hora normal)
- Quantidade = horas extras NO MÊS (via INFORMADA OU IMPORTADA_DO_CARTAO)

Se `Quantidade = 0`, a verba apura em zero → PJE-Calc emite alerta:
**_"Todas as ocorrências da verba HORAS EXTRAS 50% foram salvas com quantidade igual a zero"_**.

Esse é o erro mais comum quando a IA escolhe Opção A mas zera o valor por não
encontrar a quantidade na sentença. **Solução**: ou calcule a quantidade conforme
tabela acima, ou use Opção B + cartão de ponto.

**Nunca** omita `quantidade` nem deixe como `null` quando `valor=CALCULADO`.

## 4.4.bis REGRA DE MENSALIZAÇÃO (CRÍTICA — leia ANTES de preencher fórmulas)

O **PJE-Calc apura SEMPRE mês a mês**. Qualquer valor da sentença em base não-mensal
(diário, semanal, anual, por ocorrência) DEVE ser convertido para representação que o
PJE-Calc consiga apurar mensalmente. Isso é fonte de erros frequentes.

### Estratégia 1 — Mensalizar e usar `valor=INFORMADO` (mais simples, recomendado)
Faça a conta da sentença e informe o **valor mensal** já calculado:

```
Vale-transporte: R$ 8,40/dia × 22 dias úteis = R$ 184,80/mês
→ valor=INFORMADO, valor_devido.valor_informado_brl = 184.80
```

```
Ajuda de custo: R$ 100/semana
→ R$ 100 × 4,33 sem/mês = R$ 433,00/mês
→ valor=INFORMADO, valor_devido.valor_informado_brl = 433.00
```

```
Diárias: R$ 80/dia × 20 viagens/mês = R$ 1.600/mês
→ valor=INFORMADO, valor_devido.valor_informado_brl = 1600.00
```

### Estratégia 2 — Usar `valor=CALCULADO` com fórmula PJE-Calc
Use quando a sentença remete a um histórico salarial existente OU usa multiplicador
sobre base já cadastrada. **NUNCA** use CALCULADO com "valor fixo × dias úteis" se o valor
não vem de um histórico — isso não tem como ser preenchido na fórmula do PJE-Calc.

❌ ERRADO: "Vale-transporte R$ 8,40/dia × dias úteis" → CALCULADO com base inventada
✅ CERTO: "Vale-transporte R$ 8,40/dia × dias úteis" → INFORMADO com R$ 184,80/mês já calculado

A fórmula CALCULADO do PJE-Calc EXIGE que `base_calculo.tipo` seja um destes 5 enums fixos
(MAIOR_REMUNERACAO, HISTORICO_SALARIAL, SALARIO_DA_CATEGORIA, SALARIO_MINIMO,
VALE_TRANSPORTE). Não há suporte para "valor fixo arbitrário" como base.

## 4.4.ter TABELA DE DECISÃO POR TIPO DE VERBA

Para cada verba, escolha `valor` com base na natureza econômica:

| Verba | `valor` padrão | Como preencher |
|---|---|---|
| **SALDO DE SALÁRIO** | CALCULADO (regra) — **INFORMADO** (exceção, ver abaixo) | CALCULADO: base=HISTORICO_SALARIAL (última rem.), divisor=OUTRO_VALOR=30, multiplicador=1, quantidade=INFORMADA (dias trabalhados no mês da rescisão). **EXCEÇÃO obrigatória → INFORMADO** quando (a) a sentença FIXA o valor bruto do saldo (ex.: "R$ 1.886,67 = 8/30 de R$ 7.075,00"); OU (b) há valor já pago/depositado a deduzir (ConPag, adiantamento, depósito judicial); OU (c) a base inclui salário pago por fora (remuneração real = registrado + extrafolha). Ver §4.4.quater. |
| **13º SALÁRIO** | CALCULADO | sistema apura; base=HISTORICO_SALARIAL, **divisor=OUTRO_VALOR=12 (constante CLT)**, multiplicador=1, quantidade=AVOS |
| **FÉRIAS + 1/3** | CALCULADO | sistema apura; base=HISTORICO_SALARIAL, **divisor=OUTRO_VALOR=12 (constante CLT)**, multiplicador=1.33, quantidade=AVOS |
| **AVISO PRÉVIO** | CALCULADO | base=MAIOR_REMUNERACAO, **divisor=OUTRO_VALOR=30 (SEMPRE — base diária)**, multiplicador=1, quantidade=INFORMADA=<dias de aviso: 30 + 3/ano, Lei 12.506/2011>. NUNCA divisor=1. |
| **HORAS EXTRAS 50%/100%** | CALCULADO | base=HISTORICO_SALARIAL, divisor=CARGA_HORARIA (ou OUTRO_VALOR=220), multiplicador=1.5/2.0, quantidade=INFORMADA mensal OU IMPORTADA_DO_CARTAO |
| **ADICIONAL NOTURNO** | CALCULADO | base=HISTORICO_SALARIAL, multiplicador=0.20, **quantidade=IMPORTADA_DO_CARTAO** (horas noturnas), **divisor=OUTRO_VALOR = carga horária mensal FIXA** (ex.: 220, ou a jornada mensal do cartão). ⚠️ NUNCA `divisor=IMPORTADA_DO_CARTAO` — o divisor é a carga horária (base do valor-hora), não uma coluna do cartão; importá-lo gera "divisor zero" e trava o save. |
| **ADICIONAL INSALUBRIDADE** | CALCULADO | base=SALARIO_MINIMO (ou histórico se sentença disser), multiplicador=0.10/0.20/0.40, quantidade=INFORMADA=1 |
| **MULTA 477 CLT** | CALCULADO | base=MAIOR_REMUNERACAO, quantidade=INFORMADA=1, divisor=OUTRO_VALOR=1, multiplicador=1 |
| **VALE TRANSPORTE** | **INFORMADO** | mensalizar (R$/dia × dias úteis médios = 22). NÃO usar CALCULADO. |
| **RESTITUIÇÃO/INDENIZAÇÃO DE DESPESA** | **INFORMADO** | mensalizar o valor total da restituição se for recorrente; se for ocorrência única, valor_informado_brl com o total e periodo_inicio=periodo_fim no mês da despesa |
| **AJUDA DE CUSTO** | **INFORMADO** | mensalizar |
| **DIÁRIAS - INTEGRAÇÃO** | **INFORMADO** | mensalizar valor médio; ocorrência=MENSAL, comporPrincipal=NAO, proporcionalizar=NAO |
| **DIÁRIAS - PAGAMENTO** | **INFORMADO** | mensalizar |
| **CESTA BÁSICA / TÍQUETE-ALIMENTAÇÃO** | **INFORMADO** | mensalizar (valor mensal já pago/devido) |
| **GORJETA** | CALCULADO | base=HISTORICO_SALARIAL (gorjeta cadastrada) |
| **COMISSÃO** | CALCULADO | base=HISTORICO_SALARIAL (comissões cadastradas) ou INFORMADO se sentença fixar valor mensal |
| **DIFERENÇA SALARIAL** | CALCULADO | base=HISTORICO_SALARIAL (paradigma); ver §4.7 equiparação |
| **INDENIZAÇÃO POR DANO MORAL/MATERIAL** | **INFORMADO** | valor único da condenação |
| **MULTA CONVENCIONAL** | **INFORMADO** | valor único conforme CCT |
| **INDENIZAÇÃO ADICIONAL (Estabilidade)** | CALCULADO | base=MAIOR_REMUNERACAO, divisor=OUTRO_VALOR=1, multiplicador=1, quantidade=INFORMADA (meses de estabilidade); proporcionalizar=SIM |

## 4.4.quater SALDO DE SALÁRIO — INFORMADO quando há valor fixado/dedução/salário por fora — INVARIANTE PERMANENTE — NÃO REVERTER

SALDO DE SALÁRIO é **sempre** DESLIGAMENTO + período curto (fração do último
mês). Quando ele é CALCULADO com **base composta** (salário registrado +
salário pago por fora) e/ou tem **valor pago a deduzir** (depósito da ConPag,
adiantamento), o PJE-Calc Cidadão liquida ERRADO:

- a ocorrência única do DESLIGAMENTO resolve a base **só pelo histórico
  composto secundário** (perde o salário registrado): no caso ARIANE
  (0000566-12, 14/06/2026) a base saiu R$ 1.800 (só o "por fora") em vez de
  R$ 7.075 → saldo de R$ 480 em vez de R$ 1.886,67;
- a ocorrência não regenera com o divisor/quantidade do parâmetro (fica
  divisor=1/quantidade=1 default do Expresso) → alertas "parâmetro alterado
  após geração" e o valor pago (ConPag) não é aplicado.

**Regra (INVARIANTE):** emita SALDO DE SALÁRIO como **`valor: INFORMADO`**
SEMPRE que ocorrer QUALQUER destes:
1. a sentença **fixa o valor bruto** do saldo (ex.: "R$ 1.886,67 = 8/30 de
   R$ 7.075,00") → `valor_informado_brl` = esse bruto;
2. há **valor já pago/depositado** a deduzir (ConPag, depósito judicial,
   adiantamento) → `valor_pago: {tipo: INFORMADO, valor_brl: <valor pago>}`
   (NUNCA como verba de dedução separada);
3. a base do saldo inclui **salário pago por fora** (remuneração real =
   registrado + extrafolha).

Modelo canônico (caso ARIANE — saldo 8 dias, remuneração real R$ 7.075,
ConPag R$ 1.091,10):
```json
{
  "expresso_alvo": "SALDO DE SALÁRIO",
  "nome_pjecalc": "SALDO DE SALÁRIO",
  "parametros": {
    "valor": "INFORMADO",
    "caracteristica": "COMUM",
    "ocorrencia_pagamento": "DESLIGAMENTO",
    "periodo_inicio": "01/04/2026",
    "periodo_fim": "08/04/2026",
    "valor_devido": {"tipo": "INFORMADO", "valor_informado_brl": 1886.67},
    "valor_pago":  {"tipo": "INFORMADO", "valor_brl": 1091.10}
  }
}
```
Se a sentença NÃO fixar o bruto, calcule-o você: `(remuneração real / 30) ×
dias trabalhados no mês da rescisão`. `valor_informado_brl` é SEMPRE positivo;
o PJE-Calc abate o `valor_pago` internamente. O bot já roteia
INFORMADO+DESLIGAMENTO para o fluxo Manual (estável), evitando a fragilidade
do CALCULADO. **Saldo CALCULADO simples (single histórico, sem dedução)
permanece válido** — esta exceção só vale para os 3 gatilhos acima.

### Estratégia de preenchimento — campos OBRIGATÓRIOS por verba

Para que a automação preencha a página de Parâmetros do PJE-Calc Cidadão CORRETAMENTE,
cada verba (manual OU expressa) precisa ter os campos abaixo definidos no JSON.
O esquema espelha **integralmente** a página `verba-calculo.jsf` (Cálculo > Verbas > Alterar):

#### Bloco "Dados de Verba" (sempre visível):
- `parametros.assunto_cnj`: `{codigo: int, label: str}` (use 2581 - Remuneração... como default amplo)
- `parametros.parcela`: `FIXA` (default) ou `VARIAVEL`
- `parametros.valor`: `INFORMADO` ou `CALCULADO` (decide qual bloco aparece a seguir)
- `parametros.incidencias`: `{irpf, cs_inss, fgts, previdencia_privada, pensao_alimenticia}` (booleans)
- `parametros.caracteristica`: `COMUM` | `DECIMO_TERCEIRO_SALARIO` | `AVISO_PREVIO` | `FERIAS`
- `parametros.ocorrencia_pagamento`: `MENSAL` | `DEZEMBRO` | `DESLIGAMENTO` | `PERIODO_AQUISITIVO`
- `parametros.juros_aplicar_sumula_439`: false (default) — true só se sentença determinar

#### Geração de Reflexa/Principal:
- `parametros.tipo`: `PRINCIPAL` (verbas principais) ou `REFLEXO` (reflexos manuais)
- `parametros.gerar_reflexa`: `DIFERENCA` (default) ou `DEVIDO` — sobre o que os reflexos incidirão
- `parametros.gerar_principal`: `DIFERENCA` (default) ou `DEVIDO`
- `parametros.compor_principal`: true (default) ou false — incluir no Bruto Devido?
- `parametros.zerar_valor_negativo`: false (default) ou true

#### Bloco "Valor Devido" (sempre visível):
- `parametros.periodo_inicio` / `periodo_fim`: DD/MM/YYYY
- `parametros.exclusoes`: `{faltas_justificadas, faltas_nao_justificadas, ferias_gozadas, dobrar_valor_devido}` (booleans)
  - `dobrar_valor_devido`: só fica disponível quando `valor=CALCULADO` no PJE-Calc; marcar quando a sentença determinar (ex.: feriado em dobro, RSR em dobro)
- Se `valor=INFORMADO`:
  - `parametros.valor_devido`: `{tipo: "INFORMADO", valor_informado_brl: float > 0, proporcionalizar: bool}`
  - `proporcionalizar`: true se o valor informado é INTEGRAL e o PJE-Calc deve proporcionalizar meses incompletos (admissão/demissão no meio do mês)
  - `formula_calculado`: `null`
  - **⚠️ `valor_informado_brl` é SEMPRE POSITIVO.** Em PJE-Calc todos os valores monetários
    no JSON são positivos — o sistema trata sinais internamente. Mesmo quando a verba
    representa uma **DEDUÇÃO** (ex.: `VALOR PAGO - TRIBUTÁVEL`, `VALOR PAGO - NÃO TRIBUTÁVEL`,
    `DEVOLUÇÃO DE DESCONTOS INDEVIDOS`), o valor informado é positivo. Essas verbas são
    intrinsecamente subtrativas no modelo de dados do PJE-Calc — você NÃO informa o sinal.

  - **⚠️ REGRA CRÍTICA — Verbas de DEDUÇÃO usam `valor_pago.valor_brl`, NÃO `valor_devido`.**
    Para `VALOR PAGO - TRIBUTÁVEL`, `VALOR PAGO - NÃO TRIBUTÁVEL` e `DEVOLUÇÃO DE DESCONTOS
    INDEVIDOS`, o valor da dedução vai em `parametros.valor_pago.valor_brl` (positivo),
    enquanto `parametros.valor_devido.valor_informado_brl` fica **`0.0`**. O PJE-Calc apura
    `devido − pago` → saldo negativo que deduz do bruto. Adicionalmente, marque:
    - `parametros.zerar_valor_negativo: false` na verba
    - `parametros_calculo.zerar_valor_negativo: false` global (quando houver qualquer
      verba de dedução). Aceita-se o alerta não-bloqueante do PJE-Calc.

    **Exemplo correto** (dedução TRCT de R$ 1.496,23):
    ```json
    "parametros": {
      "valor": "INFORMADO",
      "zerar_valor_negativo": false,
      "valor_devido": {"tipo": "INFORMADO", "valor_informado_brl": 0.0, "proporcionalizar": false},
      "valor_pago":   {"tipo": "INFORMADO", "valor_brl": 1496.23, "proporcionalizar": false}
    }
    ```
    **NUNCA inverter** (`valor_devido=1496.23, valor_pago=0`) — geraria soma em vez de abate.

- Se `valor=CALCULADO`:
  - `parametros.valor_devido`: `{tipo: "CALCULADO"}`
  - `parametros.formula_calculado`: ver §4.4 (base_calculo + divisor + multiplicador + quantidade)
    - `base_calculo.bases_compostas`: lista de outras verbas a SOMAR na base (ex.: salário + adicional noturno). Vazio quando a base é só uma. Cada item: `{verba: "nome da verba", integralizar: "SIM"|"NAO"}`

#### Bloco "Valor Pago" (sempre visível — valor já recebido):
- `parametros.valor_pago`: `{tipo: "INFORMADO"|"CALCULADO", valor_brl: 0.00, proporcionalizar: bool}`
- Geralmente `INFORMADO` com `valor_brl: 0.00` (nada pago) — exceto em equiparação salarial (CALCULADO com base no histórico do paradigma)

⚠️ **REGRA CRÍTICA — Verbas COMPARATIVAS DE HISTÓRICO (INVARIANTE PERMANENTE — NÃO REVERTER)**:

Verbas que apuram a **diferença entre dois históricos salariais** exigem
configuração específica:
- **DIFERENÇA SALARIAL** (por equiparação, desvio de função, reajuste não
  concedido, piso da categoria, dissídio retroativo)
- **DIFERENÇA DE REMUNERAÇÃO** decorrente de mudança de função

O PJE-Calc apura a diferença fazendo `(Valor Devido) − (Valor Pago)`. Portanto:

- `formula_calculado.base_calculo`: histórico do **valor devido**
  (geralmente o salário superior — paradigma na equiparação, salário pleiteado
  no desvio, piso normativo)
- `valor_pago`: histórico do **valor pago** (geralmente o salário inferior —
  registro do reclamante, contrato vigente)

```json
"formula_calculado": {
  "base_calculo": {
    "tipo": "HISTORICO_SALARIAL",
    "historico_nome": "SALÁRIO DEVIDO",          ← histórico superior
    "proporcionaliza": "NAO",
    "bases_compostas": []
  },
  "divisor": {"tipo": "OUTRO_VALOR", "valor": 1},
  "multiplicador": 1.0,
  "quantidade": {"tipo": "INFORMADA", "valor": 1.0, "proporcionalizar": false}
},
"valor_pago": {
  "tipo": "CALCULADO",
  "base_tipo": "HISTORICO_SALARIAL",
  "base_historico_nome": "SALÁRIO PAGO",         ← histórico inferior
  "proporcionaliza_historico": "NAO",
  "quantidade_brl": null,
  "proporcionalizar": false,
  "valor_brl": null
}
```

E o array `historico_salarial` deve ter **AMBOS** cadastrados, cada um com o
nome usado nos campos acima:

```json
"historico_salarial": [
  {"nome": "SALÁRIO DEVIDO", "valor_brl": 1518.00, ...},
  {"nome": "SALÁRIO PAGO",   "valor_brl": 700.00,  ...}
]
```

Sem isso, o PJE-Calc rejeita a liquidação com:
> *"Falta selecionar pelo menos um Histórico Salarial para apurar o Valor
> Devido da Verba DIFERENÇA SALARIAL"*

#### Bloco "Comentários":
- `parametros.comentarios`: string opcional com observações jurídicas (até 255 chars)

**⚠️ NUNCA deixe um desses campos com `null` quando a sentença fornece a informação.**
A IA deve LER a sentença e preencher EXPLICITAMENTE cada campo. A automação não inventa
valores — ela reproduz o que está no JSON.

### Regra-chave: estrategia_preenchimento × `valor` da fórmula

A automação trata as 3 estratégias de forma diferente:

- **`expresso_direto`**: o PJE-Calc Expresso já configura `valor`, `base_calculo`,
  `divisor`, `multiplicador`, `quantidade` automaticamente. A automação **apenas
  ajusta período + (opcionalmente) valor_informado se valor=INFORMADO**. NÃO sobrescreve
  fórmula. Use quando a sentença SE ENCAIXA EXATAMENTE na verba Expresso padrão.

- **`expresso_adaptado`**: a automação reabre a verba criada pelo Expresso e
  reconfigura TODOS os parâmetros (nome, base, fórmula, valor). Use quando:
  - O nome da verba na sentença difere do canônico do Expresso (§4 nome customizado)
  - A fórmula da sentença difere da padrão do Expresso (ex.: divisor diferente,
    multiplicador diferente, base de cálculo diferente)
  - A sentença determina valor INFORMADO numa verba que o Expresso configura como CALCULADO
  - A sentença determina valor CALCULADO numa verba que o Expresso configura como INFORMADO

- **`manual`**: cria a verba do zero. Use quando não existe verba similar no Expresso.

**Decisão prática**: se vai usar `valor=INFORMADO` em VALE TRANSPORTE, RESTITUIÇÃO/
INDENIZAÇÃO DE DESPESA, ou outra verba que o Expresso padrão configura como
CALCULADO → use `estrategia_preenchimento=expresso_adaptado` (não _direto).

### Regra-chave: "Valor diário × dias úteis" → SEMPRE mensalize

Quando a sentença disser algo como `"R$ X/dia × dias úteis"` ou `"R$ Y/dia"` para vale-transporte,
diárias, ajuda de custo ou indenização de despesa, **NÃO TENTE TRADUZIR ISSO COMO FÓRMULA
CALCULADO**. Em vez disso:

1. Calcule o valor mensal: `valor_mensal = valor_diario × 22` (média mensal de dias úteis)
2. Use `valor=INFORMADO`, `valor_devido.valor_informado_brl = valor_mensal`
3. `formula_calculado = null`

O PJE-Calc aplicará esse valor a cada mês do período. Para sentenças que envolvem períodos
incompletos (admissão/demissão no meio do mês), o PJE-Calc proporcionaliza automaticamente
se `proporcionalizar=true`.

## 4.5 REFLEXOS

Para cada verba principal, listar reflexos. **Padrão de incidência reflexa:**

| Verba principal | Reflexos típicos |
|---|---|
| Adicional (insalubridade, periculosidade, noturno...) | Aviso Prévio, Férias+1/3, Multa 477, 13º |
| Horas Extras 50% / 100% | Aviso Prévio, Férias+1/3, Multa 477, 13º, **RSR/Feriado** |
| Comissão / Gorjeta | Aviso Prévio, Férias+1/3, Multa 477, 13º, **RSR** |
| Diferença Salarial | Aviso Prévio, Férias+1/3, Multa 477, 13º |
| Indenizações pós-contrato (Estabilidade, Dispensa Discriminatória) | 13º, Férias+1/3, **FGTS+40%** (manual) |

⚠️ **A tabela acima é REFERÊNCIA do que é POSSÍVEL — NÃO uma lista a emitir sempre.**
Emita cada reflexo **SOMENTE se a sentença determinar aquela incidência** sobre
aquela verba (fidelidade sentença→JSON). O painel Expresso do PJE-Calc oferece
vários candidatos (ex.: HE 50% mostra AVISO/FÉRIAS/MULTA 477/RSR/13º), mas eles
são OPÇÕES — o bot só marca os que você emitir. Ex.: **só inclua o reflexo
"MULTA DO ARTIGO 477 SOBRE HORAS EXTRAS" se o dispositivo mandar a multa 477
refletir sobre as horas extras**; se a sentença não determinar, NÃO emita.
Regra dos dois lados: (a) não INVENTE reflexo que a sentença não deferiu;
(b) não OMITA reflexo que ela deferiu.

⚠️ **INVARIANTE PERMANENTE — DISPOSITIVO prevalece sobre a fundamentação nos
reflexos (#80-BK, 0000092-41).** Quando o rol de reflexos do DISPOSITIVO
divergir do rol da fundamentação, use o do DISPOSITIVO (é o que transita em
julgado). Bug real: fundamentação do adicional noturno listava reflexos sem
RSR, mas o dispositivo (c.1) mandava HE **e** adicional noturno refletirem
"em RSR, aviso prévio, férias mais um terço, décimo terceiro, FGTS e multa de
40%" — a IA seguiu a fundamentação e OMITIU o RSR sobre o adicional noturno.
Leia o dispositivo verba a verba e confira o rol completo de cada uma.

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
- `manual` — quando o reflexo NÃO está pré-cadastrado no PJE-Calc

⚠️ **REGRA CRÍTICA — REFLEXOS DE VERBA IN-CONTRATO SÃO SEMPRE EXPRESSO (INVARIANTE PERMANENTE — NÃO REVERTER)**:
Para verba do CURSO do contrato (horas extras, adicionais, diferença salarial,
comissões etc.), TODOS os reflexos são `estrategia_reflexa: "checkbox_painel"`
(Expresso — o PJE-Calc pré-cadastra os candidatos no painel "Exibir"). O
lançamento MANUAL é EXCEÇÃO reservada a verba PÓS-CONTRATUAL (regra abaixo).
Duas armadilhas a EVITAR (bug RODRIGO ROCHA 0000905-05):
1. **`expresso_reflex_alvo` SEM qualificadores entre parênteses.** O rótulo do
   checkbox no painel NÃO tem "(COMISSIONISTA)", "(MENSALISTA)" etc. Emitir
   `"REPOUSO SEMANAL REMUNERADO SOBRE HORAS EXTRAS 50%"`, **nunca**
   `"REPOUSO SEMANAL REMUNERADO (COMISSIONISTA) SOBRE HORAS EXTRAS 50%"` — o
   parêntese quebra o match e o reflexo é perdido/lançado manualmente.
2. **NÃO emitir reflexo `"FGTS SOBRE <verba>"`.** FGTS NÃO é checkbox de reflexo
   no painel (os candidatos de HE são RSR/Aviso/Férias/13º/Multa477). O FGTS
   incide sobre a verba pela **seção FGTS** (`fgts.incidencia` =
   `SOBRE_O_TOTAL_DEVIDO` compõe todas as verbas na base). Um reflexo "FGTS
   sobre X" à parte é dupla contagem. Para garantir FGTS sobre a verba, deixe
   `fgts.incidencia: "SOBRE_O_TOTAL_DEVIDO"` (default) — não crie reflexo.
(O normalizer também saneia isso como salvaguarda — remove o parêntese e o
reflexo FGTS de verba in-contrato.)

⚠️ **REGRA CRÍTICA — REFLEXOS DE VERBA PÓS-CONTRATUAL (INVARIANTE PERMANENTE — NÃO REVERTER)**:
Para verba cujo período é POSTERIOR à demissão (indenização substitutiva de
estabilidade gestante/acidentária, Lei 9.029, indenização adicional), o PJE-Calc
**NÃO pré-cadastra candidatos de reflexo** no painel "Exibir". Os reflexos
(13º, Férias+1/3, FGTS) DEVEM ser emitidos com:
- `estrategia_reflexa: "manual"` (NUNCA `checkbox_painel` — o checkbox não existe);
- `parametros_override.caracteristica`: `"COMUM"` para TODOS (⚠️ FERIAS/
  DECIMO_TERCEIRO travam a ocorrência em DEZEMBRO/PERÍODO AQUISITIVO, que o
  PJE-Calc rejeita p/ período pós-demissão) + `ocorrencia_pagamento: "MENSAL"`;
- `parametros_override.periodo_inicio/periodo_fim` = período da verba principal.
Fórmulas aplicadas pelo bot (fluxo Manual Tipo=REFLEXO, ocorrência MENSAL =
avos mensais): Férias+1/3 → divisor 12 / mult 1,33 / qtd 1; 13º → divisor 12 /
mult 1 / qtd 1 (cada mês = um avo; acumulado = integral); FGTS → divisor 100 /
mult 8 (11,2 c/ multa 40%) / qtd 1.
(O normalizer também coage isso como salvaguarda — bug JANIELLY 0000706-46.)

# 5. CARTAO_DE_PONTO / CARTOES_DE_PONTO

⚠️ **REGRA INVARIANTE — NÃO REVERTER — SEM cartão: emitir EXATAMENTE `null`**:

Quando a sentença **NÃO mandar apurar jornada** (sem horários, sem escala, sem
intervalos), você DEVE emitir:
```json
"cartao_de_ponto": null,
"cartoes_de_ponto": []
```

❌ **NUNCA emitir stub** do tipo `{"ocorrencias_override": [], "preenchimento": "LIVRE"}`
sem `data_inicial`/`data_final` nem jornada. O Pydantic rejeita esse stub
com erro `Field required: data_inicial, data_final` → /confirmar 422 →
**impossível iniciar automação**.

❌ **NÃO inicializar** com defaults vazios "por garantia". Se há dúvida, deixe
`null`. O bot pula a Fase 5 silenciosamente quando cartão é `null` — comportamento
correto para sentenças sem HE-apurada-do-cartão.

Casos típicos de cartão `null`:
- Verbas só rescisórias (saldo, aviso, férias, 13º, multa 477)
- HE com `quantidade.tipo = INFORMADA` (valor fixo mensal dado pela sentença)
- Adicionais sem variação por jornada (insalubridade grau X, periculosidade)
- Indenizações por dano moral / material / arts. 9.029, 477, etc.

Casos onde cartão é OBRIGATÓRIO (não-null):
- HE com `quantidade.tipo = IMPORTADA_DO_CARTAO` (perito deve apurar)
- RSR / Intervalo intrajornada com apuração pelo cartão
- Adicional noturno com horários específicos a apurar

---

⚠️ **REGRA CRÍTICA — MULTI-PERÍODO (INVARIANTE PERMANENTE — NÃO REVERTER)**:

Se a sentença reconhecer **mais de uma dinâmica de jornada em períodos
distintos** (típico em casos de alteração unilateral de turno), emita
**`cartoes_de_ponto` como LISTA** com um item por período. Cada item tem
seu próprio `data_inicial`/`data_final` + jornada.

```json
"cartoes_de_ponto": [
  {
    "data_inicial": "10/04/2025",
    "data_final":   "21/09/2025",
    "preenchimento": "PROGRAMACAO",
    "programacao_semanal": { ... jornada do período 1 ... },
    ...
  },
  {
    "data_inicial": "22/09/2025",
    "data_final":   "01/12/2025",
    "preenchimento": "PROGRAMACAO",
    "programacao_semanal": { ... jornada do período 2 ... },
    ...
  }
]
```

Use `cartao_de_ponto` (singular) quando a sentença fixar UMA só jornada
em todo o período. O normalizer migra singular → lista[1] automaticamente.

**Exemplo Scarlette (sentença 26/05/2026)**:
> "Considera-se que a reclamante laborava: (i) de 10/04/2025 até a
> alteração de turno em setembro de 2025, às terças, quartas e quintas,
> das 17h às 22h, e aos domingos das 07h às 19h; (ii) a partir de
> 22/09/2025, das 05h às 10h, de segunda a sexta-feira."

→ DOIS cartões: período 1 (10/04→21/09) com jornada A, período 2
(22/09→01/12) com jornada B. NUNCA tente combinar tudo em um único
cartão com `ocorrencias_override` — o PJE-Calc apura por cartão.

---


Preencher **somente na Opção B** (ver seção 4.4): sentença fixa jornada/horário de trabalho
mas não especifica quantidade de HE — o PJE-Calc apurará as HE a partir da jornada cadastrada.

Deixar `null` quando:
- Opção A foi usada (quantidade informada diretamente), ou
- Não há horas extras no cálculo.

```json
{
  "data_inicial": "DD/MM/YYYY",
  "data_final": "DD/MM/YYYY",

  "apuracao": {
    "tipo": "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL",
    "qtsumulatst": null,
    "qthoraseparado": null
  },

  "considerar_feriados": true,
  "extras_feriados_separado": false,
  "extras_domingos_separado": false,
  "extras_sabados_domingos_separado": false,

  "tolerancia_ativa": false,
  "tolerancia_por_turno": "00:05",
  "tolerancia_por_dia": "00:10",

  "jornada_padrao": {
    "segunda_hhmm":        "08:00",
    "terca_hhmm":          "08:00",
    "quarta_hhmm":         "08:00",
    "quinta_hhmm":         "08:00",
    "sexta_hhmm":          "08:00",
    "sabado_hhmm":         "00:00",
    "domingo_hhmm":        "00:00",
    "jornada_semanal":     "44,00",
    "jornada_mensal_media": "188,57"
  },

  "jornada_feriado_trabalhado": false,
  "jornada_feriado_nao_trabalhado": false,

  "descanso": {
    "apurar_feriados_trabalhados": false,
    "apurar_domingos_trabalhados": false,
    "apurar_sabados_domingos": false,
    "apurar_intervalo_384": false,
    "apurar_intervalo_72": false,
    "apurar_intervalo_insalubridade": false,
    "tempo_trabalho_art253": "01:40",
    "tempo_descanso_art253": "00:20",
    "descanso_entre_jornadas": false,
    "valor_descanso_entre_jornadas": "11:00",
    "valor_descanso_entre_semanas": "35:00",
    "intervalo_sup_4h_6h": false,
    "tolerancia_sup_4h_6h": "00:15",
    "intervalo_sup_6h": false,
    "valor_intervalo_sup_6h": "01:00",
    "tolerancia_sup_6h": "00:05",
    "considerar_fracionamento": false,
    "apurar_supressao_integral": false,
    "apurar_supressao_reforma": false,
    "apurar_excesso_sumula118": false,
    "valor_intervalo_max_sumula118": "02:00",
    "apurar_apenas_excesso_jornada": false
  },

  "noturno": {
    "tipo_atividade": "ATIVIDADE_URBANA",
    "apurar_horas_noturnas": false,
    "apurar_horas_extras_noturnas": false,
    "reducao_ficta": true,
    "horario_prorrogado_sumula60": false,
    "forcar_prorrogacao": false
  },

  "preenchimento": "PROGRAMACAO",

  "programacao_semanal": {
    "segunda":  {"turnos": [{"entrada": "07:00", "saida": "12:00"}, {"entrada": "13:00", "saida": "18:00"}]},
    "terca":    {"turnos": [{"entrada": "07:00", "saida": "12:00"}, {"entrada": "13:00", "saida": "18:00"}]},
    "quarta":   {"turnos": [{"entrada": "07:00", "saida": "12:00"}, {"entrada": "13:00", "saida": "18:00"}]},
    "quinta":   {"turnos": [{"entrada": "07:00", "saida": "12:00"}, {"entrada": "13:00", "saida": "18:00"}]},
    "sexta":    {"turnos": [{"entrada": "07:00", "saida": "12:00"}, {"entrada": "13:00", "saida": "18:00"}]},
    "sabado":   {"turnos": []},
    "domingo":  {"turnos": []},
    "feriado":  {"turnos": []}
  },

  "escala": null,

  "ocorrencias_override": []
}
```

**`apuracao.tipo`** — escolher o mais adequado à sentença:
- `HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL` — padrão; PJE-Calc compara diária vs semanal
- `HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA` — excedentes do limite diário
- `HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL` — excedentes do limite semanal
- `HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL` — excedentes do limite mensal
- `HORAS_EXTRAS_CONFORME_SUMULA_85` — escalas especiais com RSR compensado
- `APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO` — primeiras HE em separado
- `NAO_APURAR_HORAS_EXTRAS` — sem apuração de HE

**`noturno.tipo_atividade`** ∈ {`ATIVIDADE_URBANA`, `ATIVIDADE_AGRICOLA`, `ATIVIDADE_PECUARIA`}

`data_inicial`/`data_final`: mesmas datas da verba HE (`periodo_inicio`/`periodo_fim`).

Preencher `descanso` e `noturno` somente quando a sentença mencionar expressamente
supressão de intervalos ou trabalho noturno. Caso contrário, deixar `null`.

## 5.1. PREENCHIMENTO DE JORNADA (CRÍTICO — sem isso o cartão não tem como ser gerado)

⚠️ **REGRA OBRIGATÓRIA**: quando a sentença fixa uma jornada (em qualquer formato), você
DEVE preencher os campos de jornada concreta. Não basta marcar `preenchimento`; é
necessário fornecer a tabela completa de horários (entrada/saída por turno) para que a
automação possa lançar os horários no PJE-Calc.

### Modo de preenchimento — `preenchimento` ∈ {`LIVRE`, `PROGRAMACAO`, `ESCALA`}

- **`LIVRE`** — nada é auto-gerado; usuário lança jornadas dia a dia na Grade. Usar
  somente quando o caso não comporta padrão semanal nem escala.
- **`PROGRAMACAO`** — padrão semanal (Seg..Dom + Feriado), o sistema replica em todas
  as semanas. **DEFAULT para sentenças com jornada regular** (90% dos casos).
- **`ESCALA`** — ciclo NÃO-semanal (12x36, 5x1, etc). Usar apenas para escalas reais.

### Quando usar `programacao_semanal` (modo PROGRAMACAO)

Preenche `programacao_semanal` com 8 chaves (segunda, terca, quarta, quinta, sexta,
sabado, domingo, feriado). Cada chave tem `turnos` — uma lista de pares
`{entrada, saida}` (HH:MM). Até 6 turnos por dia.

**Exemplos**:

a) Jornada regular seg-sex 7h-18h com 1h almoço:
```json
"programacao_semanal": {
  "segunda": {"turnos":[{"entrada":"07:00","saida":"12:00"},{"entrada":"13:00","saida":"18:00"}]},
  "terca":   {"turnos":[{"entrada":"07:00","saida":"12:00"},{"entrada":"13:00","saida":"18:00"}]},
  ... (replica para quarta, quinta, sexta) ...,
  "sabado":  {"turnos": []},
  "domingo": {"turnos": []},
  "feriado": {"turnos": []}
}
```

b) Jornada 8h sem intervalo (escala simples seg-sex):
```json
"segunda": {"turnos": [{"entrada":"08:00","saida":"17:00"}]}
```

c) Dia não trabalhado: `"turnos": []` (lista vazia).

### Quando usar `escala` (modo ESCALA)

A escala é um CICLO REPETIDO de dias. Exemplo 12x36 com 1 dia trabalhado:
```json
"preenchimento": "ESCALA",
"escala": {
  "tipo": "DOZE_POR_TRINTA_E_SEIS",
  "inicio": "01/01/2020",
  "quantidade_dias": 1,
  "jornadas": [
    {"turnos": [{"entrada":"07:00","saida":"19:00"}]}
  ]
}
```

`tipo` ∈ {`OUTRA`, `DOZE_POR_DOZE`, `DOZE_POR_VINTE_QUATRO`, `DOZE_POR_TRINTA_E_SEIS`,
`DOZE_POR_QUARENTA_E_OITO`, `CINCO_POR_UM`, `SEIS_POR_UM`, `OITO_DOIS`}.

`inicio` = data do dia 1 do ciclo (DD/MM/YYYY).
`quantidade_dias` = nº de dias do ciclo (1, 2, 3, ...). Para `OUTRA`, defina manualmente.

### `ocorrencias_override` — JORNADAS IRREGULARES (sábados alternados, plantões, etc)

⚠️ **APRENDIZADO CHAVE — jornada regular × irregular**:

- **JORNADA REGULAR**: padrão repete a cada semana (ex: seg-sex 7h-18h, ou ciclo 12x36).
  → use `programacao_semanal` (PROGRAMACAO) ou `escala` (ESCALA). Tudo é resolvido pelo
  preenchimento automático do PJE-Calc.

- **JORNADA IRREGULAR**: padrão semanal mas com EXCEÇÕES por data (ex: sábados
  ALTERNADOS, semanas com horas extras pontuais, plantões).
  → **passo 1**: cadastre o padrão dominante em `programacao_semanal`/`escala`.
  → **passo 2**: liste as exceções em `ocorrencias_override` com a data exata e os
  turnos corretos. Esses overrides serão aplicados na Grade de Ocorrências mês a mês.

**Exemplo concreto** (seg-sex 7h-18h + sábados alternados 7h-15h):
```json
"preenchimento": "PROGRAMACAO",
"programacao_semanal": {
  "segunda": {"turnos":[{"entrada":"07:00","saida":"12:00"},{"entrada":"13:00","saida":"18:00"}]},
  ... (replica para terça-sexta) ...,
  "sabado":  {"turnos": []},
  "domingo": {"turnos": []},
  "feriado": {"turnos": []}
},
"ocorrencias_override": [
  {"data": "05/01/2020", "turnos":[{"entrada":"07:00","saida":"12:00"},{"entrada":"13:00","saida":"15:00"}]},
  {"data": "19/01/2020", "turnos":[{"entrada":"07:00","saida":"12:00"},{"entrada":"13:00","saida":"15:00"}]},
  ...
]
```

Liste TODOS os sábados (ou dias específicos) com a jornada exata. Apagar dia inteiro:
`turnos: []`.

### Decisão rápida

| Sentença diz... | preenchimento | tabela | overrides |
|---|---|---|---|
| "seg-sex 8h-17h" | PROGRAMACAO | programacao_semanal | — |
| "seg-sex 7-18 + sáb 7-12" | PROGRAMACAO | programacao_semanal (sáb=7-12) | — |
| "seg-sex 7-18 + sáb ALTERNADOS 7-15" | PROGRAMACAO | programacao_semanal (sáb=[]) | ocorrencias_override (cada sáb trabalhado) |
| "escala 12x36" | ESCALA | escala (DOZE_POR_TRINTA_E_SEIS) | — |
| "jornada variável" (sem padrão) | LIVRE | — | ocorrencias_override (todos os dias) |

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

## FGTS — schema obrigatório

```json
{
  "fgts": {
    "tipo_verba": "PAGAR",
    "compor_principal": "SIM",
    "multa": {
      "ativa": true,
      "tipo_valor": "CALCULADA",
      "percentual": "QUARENTA_POR_CENTO",
      "excluir_aviso_da_multa": false
    },
    "incidencia": "SOBRE_O_TOTAL_DEVIDO",
    "multa_artigo_467": false,
    "multa_10_lc110": false,
    "contribuicao_social": false,
    "recolhimentos_existentes": []
  }
}
```

### Saldo do EXTRATO FGTS → dedução — INVARIANTE PERMANENTE (#80-BN, 0001972-05)

Quando os autos trazem **extrato do FGTS** (ou a sentença manda deduzir os
depósitos já existentes na conta vinculada), o saldo vai na seção própria do
FGTS — "Saldo e/ou Saque" — via:

```json
"fgts": {
  ...,
  "saldos_a_deduzir": [{"data": "12/01/2026", "valor_brl": 2314.10}],
  "deduzir_do_fgts": true
}
```

- `data` = data do extrato (DD/MM/AAAA); `valor_brl` = saldo total do extrato.
- **NUNCA** coloque o saldo do extrato em `recolhimentos_existentes` (essa é a
  tabela de depósitos POR COMPETÊNCIA, raramente editada) — bug real: a IA
  emitiu o saldo lá e a dedução foi PERDIDA na automação.
- **NUNCA** represente o saldo FGTS como verba "VALOR PAGO" (classificação
  incorreta já documentada).

⚠️ **CRÍTICO — `compor_principal`** ∈ {`"SIM"`, `"NAO"`} (strings, NUNCA boolean).

**REGRA UNIVERSAL** (vale para FGTS e QUALQUER verba que tenha esse campo):

`compor_principal = "NAO"` SOMENTE quando a verba **não vai compor o montante da
condenação**, mas a sua apuração é necessária para **calcular outras verbas/reflexos**.

📌 **"Salário por fora" / extrafolha — INVARIANTE PERMANENTE — NÃO REVERTER
(caso Ariane 0000566-12 + cálculo MANUAL de referência 263753, 14/06/2026):**

A forma correta (VALIDADA contra cálculo manual de calculista, planilha PJC
263753) modela a DIFERENÇA SALARIAL com o **valor da parcela extrafolha DIRETO**
— NÃO como devido(total) − pago(registrado):

1. **Histórico salarial "SALÁRIO PAGO POR FORA" = a própria parcela por fora**:
   o VALOR desse histórico é a parcela extrafolha mensal (a diferença em si —
   ex.: R$ 1.800,00/mês), com `proporcionaliza: "SIM"`. As DEMAIS verbas
   (SALDO, MULTA 477, etc.) usam "ÚLTIMA REMUNERAÇÃO" com a remuneração total.
2. **DIFERENÇA SALARIAL** (`estrategia_preenchimento: "expresso_adaptado"`,
   `expresso_alvo: "DIFERENÇA SALARIAL"`, `valor: CALCULADO`):
   - `formula_calculado.base_calculo`: `tipo: HISTORICO_SALARIAL`,
     `historico_nome: "SALÁRIO PAGO POR FORA"`, `proporcionaliza: "SIM"`
   - `divisor: {tipo: OUTRO_VALOR, valor: 1}`, `multiplicador: 1`,
     `quantidade: {tipo: INFORMADA, valor: 1}`
   - **`valor_pago: {tipo: INFORMADO, valor_brl: 0.0}`** — NÃO CALCULADO sobre
     registrado. O valor da verba JÁ É a parcela por fora.
   - `compor_principal: "NAO"` (serve só de base p/ reflexos).
   - Fórmula resultante: `((SALÁRIO PAGO POR FORA / 1) × 1 × 1)` = a parcela.
3. **Reflexos** (FÉRIAS+1/3, 13º, AVISO conforme deferido) →
   `estrategia_reflexa: "checkbox_painel"`, `compor_principal: "SIM"`. O reflexo
   lê o VALOR da verba-base (= a parcela por fora) e calcula certo.

⚠️ **NUNCA** modele como `valor_devido` sobre SALÁRIO TOTAL **menos**
`valor_pago` CALCULADO sobre SALÁRIO REGISTRADO: o *net* dá a diferença, MAS a
verba carrega o **devido BRUTO** (o total), e o reflexo de **FÉRIAS** lê esse
bruto e **infla 30×** (bug Ariane #65 — base 54.000 em vez de 1.800; o 13º não
tem essa sensibilidade e sai certo, mascarando o erro). O valor da verba-base
DEVE ser a própria parcela por fora (histórico direto, `valor_pago` INFORMADO 0).
Comprovado: planilha manual 263753 com FÉRIAS reflexo = R$ 11.742 (correto).

4. **FGTS — incidência SÓ sobre a parcela por fora (INVARIANTE — caso Ariane,
   item d da sentença)**: a condenação de FGTS recai EXCLUSIVAMENTE sobre a
   diferença (o "por fora") — o FGTS do salário registrado JÁ foi depositado no
   curso do contrato e está FORA da lide. Portanto:
   - histórico **"SALÁRIO PAGO POR FORA"** → **`incidencias.fgts: true`** (é a
     base da diferença de FGTS deferida);
   - históricos **"SALÁRIO REGISTRADO"**, **"ÚLTIMA REMUNERAÇÃO"** e qualquer
     histórico do salário total/registrado → **`incidencias.fgts: false`**
     (FGTS já recolhido; incidir aqui SUPERESTIMA o FGTS — bug Ariane: R$ 21.254
     sobre 5.275 em vez de ~R$ 7.776 sobre 1.800);
   - verba **DIFERENÇA SALARIAL** → **`incidencias.fgts: false`** (evita DUPLICAR
     a base, já que o histórico por fora já incide).
   Regra geral do FGTS por histórico: incide só o componente cujo FGTS NÃO foi
   recolhido (a parcela sonegada). O que foi pago regularmente NÃO entra.

📌 **Em todos os outros casos**: `compor_principal: "SIM"` (default).
- FGTS sobre verbas rescisórias da condenação → SIM
- Saldo de salário, 13º, férias, AVISO, horas extras, multa 477 → SIM
- Qualquer verba que represente crédito real do reclamante → SIM

❌ **NUNCA use "NAO"** só porque a verba é FGTS, salário variável, etc. O critério
é EXCLUSIVAMENTE se o valor compõe o montante final OU se serve só de base.

Outras regras FGTS:
- `tipo_verba`: `"PAGAR"` (default — pagamento direto ao reclamante via execução).
  `"DEPOSITAR"` apenas se sentença determinar depósito em conta vinculada.
- `multa` é um **objeto**, **NUNCA** boolean. Se dispensa sem justa causa → `ativa: true`, `percentual: "QUARENTA_POR_CENTO"`. Se justa causa / pedido demissão → `ativa: false`.
- `multa.percentual` ∈ {`"QUARENTA_POR_CENTO"`, `"VINTE_POR_CENTO"`}

(Para custas_judiciais e correcao_juros_multa, o formato JSON espelha exatamente a estrutura do schema.)

⚠️ **Contribuição Social e IRPF — política padrão: OMITIR (= null)**:
- O PJE-Calc tem defaults sensatos prontos: apurar segurado, alíquota SEGURADO_EMPREGADO, empregador POR_ATIVIDADE_ECONOMICA, IRPF apurado com tributação separada RRA, deduções padrão.
- **NÃO preencher** `contribuicao_social` e `imposto_de_renda` quando a sentença NÃO determinar nada específico (caso da maioria das sentenças).
- **Preencher APENAS quando** a sentença determinar explicitamente: regime de caixa (IR), CS pelo empregador FIXA com alíquotas próprias, dependentes (com `possui_dependentes: true` + `quantidade_dependentes: N`), aposentado maior de 65, RRA aplicado de modo distinto, vinculação manual de históricos de CS, etc.
- Quando preencher, manter apenas os campos relevantes; os demais ficam com os defaults do schema.

⚠️ Para `contribuicao_social.vinculacao_historicos_devidos` (quando preencher CS), deixar `{"modo": "automatica", "intervalos": []}` por padrão. Só usar `manual_por_periodo` se a sentença determinar bases diferentes por período.

⚠️ **REGRA CRÍTICA — `correcao_juros_multa` (INVARIANTE PERMANENTE — NÃO REVERTER)**:

**Modelo jurídico obrigatório**: ADC 58 (STF, vinculante) + TST E-ED-RR-20407-32.2015.5.04.0271
(SDI-1, j. 24/10/2024, DEJT 08/11/2024) + Lei 14.905/2024 (vigência 30/08/2024).

### Detecção do modelo a aplicar — leia a sentença

A IA deve LER a seção da sentença sobre Correção/Juros e detectar:

| Trecho da sentença | Modelo a aplicar |
|---|---|
| "ADC 58", "decisão vinculante STF", "IPCA-E pré-judicial e SELIC ajuizamento" | **Modelo TST** (3 fases conforme datas — ver tabela abaixo) |
| Sentença explícita E-ED-RR-20407 ou Lei 14.905/2024 | **Modelo TST** |
| Silente ou genérica ("correção monetária e juros legais") | **Modelo TST** (default jurisprudencial vigente) |
| TR / Súmula 200/TST / juros 1% até 2017 | Modelo antigo (só usar se sentença for explícita; raro) |

### Modelo TST — mapeamento para `correcao_juros_multa`

Considerando `data_ajuizamento` da causa e a data de corte **30/08/2024** (vigência Lei 14.905):

⚠️ **DECISÃO CASO A vs CASO B — VERIFICAR AS DUAS CONDIÇÕES**:

```
SE  data_inicio_calculo >= 30/08/2024
E   data_ajuizamento     >= 30/08/2024  ← AMBAS, simultaneamente
ENTÃO Caso A (sem combinações)
SENÃO Caso B (cálculo cruza 30/08/2024 — exige combinações)
```

❌ **ERRO RECORRENTE**: aplicar Caso A só porque `data_ajuizamento >= 30/08/2024`.
A `data_inicio_calculo` (prescrição quinquenal) frequentemente é vários anos
anterior à data-corte — nesse caso é OBRIGATÓRIO Caso B. Exemplo ALINE
(01/06/2026): ajuizamento 14/04/2026 (pós-corte) mas `data_inicio_calculo`
14/04/2021 (anterior ao corte por 3 anos) → **Caso B**, não Caso A.

⚠️ **JUROS — INVARIANTE PERMANENTE — NÃO REVERTER (validado contra sentença
THAÍS 0000183-68, 10/06/2026)**: a tabela `juros` (FASE 1) é a dos juros da
**fase pré-judicial** = art. 39 *caput* da Lei 8.177/91 = **`TRD_SIMPLES`** —
NUNCA `TAXA_LEGAL` na fase 1. A TAXA_LEGAL entra como **combinação a partir
do ajuizamento**. Emitir `juros: "TAXA_LEGAL"` sem combinações aplica taxa
legal desde o VENCIMENTO de cada verba (fase pré-judicial), majorando
indevidamente os juros — o devido na fase pré-judicial é TRD (≈0).

**Caso A — `data_ajuizamento` >= 30/08/2024 E `data_inicio_calculo` >= 30/08/2024**
(Scarlette: ajuizamento 04/03/2026, cálculo inicia 10/04/2025 — TUDO pós-30/08/2024):
```json
{
  "indice_trabalhista": "IPCA",
  "combinar_outro_indice": false,
  "juros": "TRD_SIMPLES",
  "aplicar_juros_fase_pre_judicial": true,
  "juros_combinacoes": [
    {
      "data_inicio": "<data_ajuizamento>",
      "tabela": "TAXA_LEGAL",
      "descricao": "Do ajuizamento — Lei 14.905/2024 (CC art. 406 §): IPCA + SELIC-IPCA"
    }
  ],
  "base_juros_verbas": "VERBAS",
  "fgts": {"indice_correcao": "UTILIZAR_INDICE_TRABALHISTA"}
}
```
Correção IPCA direto (sem combinação — todo o período é pós-corte). Juros:
TRD_SIMPLES no vencimento→ajuizamento; TAXA_LEGAL do ajuizamento em diante.
A combinação NÃO é redundante com a fase 1 (TRD ≠ TAXA_LEGAL) e persiste
corretamente no PJE-Calc.

**Caso B — cálculo CRUZA 30/08/2024** (período inicia antes da data-corte da
Lei 14.905 — ex.: THAÍS, contrato desde 22/05/2023, ajuizamento 11/02/2025):
```json
{
  "indice_trabalhista": "IPCAE",
  "combinar_outro_indice": true,
  "indice_combinado": "IPCA",
  "data_inicio_combinacao": "30/08/2024",
  "juros": "TRD_SIMPLES",
  "aplicar_juros_fase_pre_judicial": true,
  "juros_combinacoes": [],
  "base_juros_verbas": "VERBAS",
  "fgts": {"indice_correcao": "UTILIZAR_INDICE_TRABALHISTA"}
}
```
`juros_combinacoes` do Caso B depende da data do AJUIZAMENTO:
- **Ajuizamento >= 30/08/2024** (THAÍS): UMA fase —
  `[{"data_inicio": "<data_ajuizamento>", "tabela": "TAXA_LEGAL"}]`
  (a fase SELIC nunca existe: o ajuizamento já é pós-corte).
- **Ajuizamento < 30/08/2024** (ações antigas): DUAS fases —
  `[{"data_inicio": "<data_ajuizamento>", "tabela": "SELIC"},
    {"data_inicio": "30/08/2024", "tabela": "TAXA_LEGAL"}]`.

### IMPORTANTE — Dano Moral
Quando a sentença menciona explicitamente que o modelo "aplica-se inclusive à
indenização por danos morais" (jurisprudência TST recente), nada muda no
`correcao_juros_multa` (que já é global ao cálculo). Apenas confirma que a
INDENIZAÇÃO POR DANO MORAL deve marcar `incidencias` SEM `cs_inss/irpf/fgts`
e ter `juros_aplicar_sumula_439=false` (já é o padrão).

### Enums permitidos

`indice_trabalhista`: `IPCAE` | `IPCA` | `IPCAETR` | `TR` | `IGPM` | `INPC` |
`IPC` | `TUACDT` (legado) | `TABELA_UNICA_JT_MENSAL` | `TABELA_UNICA_JT_DIARIO` |
`SELIC` | `SELIC_FAZENDA` | `SELIC_BACEN` | `SEM_CORRECAO`

`juros` (fase 1) e `juros_combinacoes[].tabela`: `TAXA_LEGAL` | `SELIC` |
`SELIC_FAZENDA` | `SELIC_BACEN` | `JUROS_PADRAO` | `JUROS_POUPANCA` |
`JUROS_MEIO_PORCENTO` | `JUROS_UM_PORCENTO` | `JUROS_ZERO_TRINTA_TRES` |
`FAZENDA_PUBLICA` | `SEM_JUROS`

### Bug histórico (Scarlette 25/05/2026 — NÃO REPETIR)

A IA gerou `{indice_trabalhista: "TUACDT", juros: "SELIC"}` (sem combinações).
Ficou: Tabela Única + SELIC global. **ERRADO** vs. ADC 58/TST.
Sempre usar IPCA/IPCAE + combinações conforme tabela acima.

## HONORÁRIOS — regras obrigatórias

### Devedor do honorário
`tipo_devedor`: `RECLAMADO` ou `RECLAMANTE`.

⚠️ Quando `tipo_devedor = "RECLAMANTE"`, preencher sempre:
```json
"forma_cobranca": "COBRAR"
```
**NUNCA** usar `"DESCONTAR"` — o sistema sempre cobra diretamente do reclamante.

### Credor dos honorários SUCUMBENCIAIS
Para `tipo_honorario = "SUCUMBENCIAIS"`, o credor é **sempre o advogado da parte contrária**:
- `tipo_devedor = "RECLAMANTE"` → `credor.nome = "ADVOGADO DO RECLAMADO"`
- `tipo_devedor = "RECLAMADO"` → `credor.nome = "ADVOGADO DO RECLAMANTE"`

`credor.doc_fiscal_tipo`: usar `"CNPJ"` quando desconhecido (escritório de advocacia).
`credor.doc_fiscal_numero`: deixar `""` quando não informado na sentença.

### Tipos válidos de honorário
`tipo_honorario` ∈ {`SUCUMBENCIAIS`, `ADVOCATICIOS`, `ASSISTENCIAIS`, `CONTRATUAIS`,
`PERICIAIS_MEDICO`, `PERICIAIS_CONTADOR`, `PERICIAIS_ENGENHEIRO`, `PERICIAIS_OUTROS`}

### Honorários PERICIAIS — INVARIANTE PERMANENTE (#80-BL, 0000092-41)
Quando a sentença fixar honorários periciais ("Honorários periciais, no
importe de R$ X, pela reclamada, nos termos do art. 790-B da CLT"), emita um
honorário próprio com:
- `tipo_honorario` conforme a especialidade do perito (engenheiro → `PERICIAIS_ENGENHEIRO`)
- `tipo_valor = "INFORMADO"` e `valor_informado_brl` = **EXATAMENTE o valor
  FIXADO na sentença** — nunca arredonde nem infira de outro documento
  (bug real: sentença fixou R$ 1.500,00 e a extração emitiu 1000)
- `tipo_devedor` = quem a sentença onera (art. 790-B: em regra o sucumbente
  no objeto da perícia; com JG do autor, a reclamada)
- `credor.nome` = o NOME do perito quando constar da sentença/laudo

### Sucumbência parcial — Justiça Gratuita (JG)

⚠️ **POLÍTICA — preencha APENAS FATOS, não o texto do comentário** (26/05/2026):

Quando a sentença concede o benefício da Justiça Gratuita a alguma parte,
marque em `parametros_calculo.justica_gratuita`:

```json
"parametros_calculo": {
  ...,
  "justica_gratuita": {
    "reclamante": true,   // true se a sentença concede JG ao reclamante
    "reclamado": false    // true se a sentença concede JG ao reclamado (raro)
  },
  "comentarios_jg": null   // DEIXE NULL — o normalizer auto-gera o texto
}
```

E preencha normalmente os honorários sucumbenciais em `honorarios` com o
`tipo_devedor` correto. O normalizer detectará a interseção (parte JG ∩
parte condenada em sucumbenciais) e auto-gerará o texto canônico de
suspensão de exigibilidade (art. 791-A § 4º CLT) ANTES da prévia, garantindo:

- Concordância de gênero correta (usa "parte reclamante/reclamada" + "beneficiária")
- Nome completo conforme `processo.reclamante.nome` / `processo.reclamado.nome`
- Idempotência: você verá o texto pronto na prévia exatamente como vai na automação

Critérios para `justica_gratuita.reclamante = true`:
- Sentença menciona "benefício da justiça gratuita", "gratuidade da justiça",
  "assistência judiciária gratuita" deferida ao reclamante (autor)

Critérios para `justica_gratuita.reclamado = true`:
- Sentença menciona o mesmo para o reclamado (geralmente pessoa física hipossuficiente)

⚠️ **`comentarios_jg`** deve ser `null` em 99% dos casos. Só preencha manualmente
se quiser SOBRESCREVER o texto auto-gerado pelo normalizer (raro). Quando
preencher, use o formato canônico:

```
Suspensão de exigibilidade dos honorários sucumbenciais devidos pela
<parte reclamante|parte reclamada> - <NOME>, beneficiária da Justiça
Gratuita (art. 791-A, § 4º, da CLT).
```

⚠️ **NOTA — usar HÍFEN comum `-`, não travessão Unicode `—` (em-dash)**:
PJE-Calc 2.15.1 usa Latin-1; o em-dash U+2014 não existe nesse encoding e
fica convertido para "¿". O hífen `-` (U+002D) é seguro em todos encodings.

❌ **NUNCA** use formato com gênero do indivíduo:
- ~~"devidos pelo Reclamante, beneficiário"~~ — quebra concordância se a parte for mulher
- ~~"parte beneficiária"~~ — genérico, não identifica qual parte

Se não há JG concedida na sentença, deixar `justica_gratuita: {reclamante: false, reclamado: false}`
(ou omitir o campo — Pydantic usa default) e `comentarios_jg: null`.

# 8. SEÇÕES OPCIONAIS — política "skip por omissão"

Todas as seções abaixo são **opcionais**. Quando a sentença NÃO determinar
nada específico, **deixe `null`** (ou lista vazia). A automação pula a fase
e os defaults nativos do PJE-Calc valem 100%. **Só preencha quando a
sentença/CCT determinar explicitamente** algum desses pontos.

## 8.1 Salário-família — `salario_familia`
Preencher quando a sentença determinar:
```json
"salario_familia": {
  "apurar": true,
  "compor_principal": true,
  "quantidade_filhos_menores_14": 2,
  "tipo_salario_pago": "MAIOR_REMUNERACAO",  // ou NENHUM | HISTORICO_SALARIAL
  "variacoes": [{"data_inicio": "01/06/2023", "quantidade_filhos": 3}],  // se houve mudança
  "historico_salarial_nomes": [],  // nomes dos históricos que compõem remuneração
  "salarios_devidos_verbas": []    // nomes das verbas devidas que compõem remuneração
}
```

## 8.2 Seguro-desemprego — `seguro_desemprego`

**INVARIANTE PERMANENTE — NÃO REVERTER (12/06/2026): seguro-desemprego SÓ é
apurado quando a sentença condenar em INDENIZAÇÃO SUBSTITUTIVA (conversão
do benefício em dinheiro — ex.: "indenização equivalente às parcelas do
seguro-desemprego", "conversão em pecúnia").**

Quando a sentença determina APENAS a **habilitação** no programa, a
**expedição de ordem/ofício/alvará judicial** ou a **entrega das guias**
(CD/SD), NÃO há condenação pecuniária — o benefício será pago pelo órgão
gestor, fora da liquidação. Nesses casos: `"seguro_desemprego": null`.

Preencher SOMENTE no caso de indenização substitutiva:
```json
"seguro_desemprego": {
  "apurar": true,
  "apurar_empregado_domestico": false,
  "compor_principal": true,
  "numero_parcelas": 4,
  "solicitacao": "PRIMEIRA",     // PRIMEIRA | SEGUNDA | DEMAIS
  "tipo_valor": "CALCULADO",     // CALCULADO | INFORMADO
  "valor_informado_brl": null    // só quando tipo_valor=INFORMADO
}
```

## 8.3 Previdência Privada — `previdencia_privada`
Preencher quando a sentença determinar incidência de PP sobre as verbas:
```json
"previdencia_privada": {
  "apurar": true,
  "aliquotas": [
    {"aliquota_pct": 12.00, "data_inicio": "01/01/2020", "data_fim": null}
  ]
}
```
(A base de incidência é definida no checkbox `previdencia_privada` de cada verba.)

## 8.4 Pensão Alimentícia — `pensao_alimenticia`
Preencher quando houver decisão judicial determinando incidência:
```json
"pensao_alimenticia": {
  "apurar": true,
  "aliquota_pct": 20.00,
  "incidir_sobre_juros": false
}
```

## 8.5 Multas e Indenizações — `multas_indenizacoes`
Lista de multas/indenizações que NÃO são verbas trabalhistas típicas
(astreintes, multa CCT específica, indenização por extravio de bem, etc.).
Multa 477/CLT NÃO entra aqui — vai em `verbas_principais`. Multa 467/CLT TAMBÉM NÃO entra aqui — ela NUNCA é verba autônoma (ver regra crítica na seção 4.1: reflexos + checkbox do FGTS).

```json
"multas_indenizacoes": [
  {
    "descricao": "Multa CCT 2024 cláusula 15",
    "credor_devedor": "RECLAMANTE_RECLAMADO",  // ou RECLAMADO_RECLAMANTE | TERCEIRO_*
    "terceiro_nome": null,                     // só quando credor=TERCEIRO
    "tipo_valor": "CALCULADO",                 // ou INFORMADO
    "aliquota_pct": 50.0,                      // só CALCULADO
    "tipo_base": "PRINCIPAL",                  // só CALCULADO: PRINCIPAL | PRINCIPAL_MENOS_CS | PRINCIPAL_MENOS_CS_MENOS_PP
    "valor_brl": null,                         // só INFORMADO
    "data_vencimento": null,                   // só INFORMADO
    "correcao_monetaria": "INDICE_TRABALHISTA",
    "outro_indice_correcao": null,
    "aplicar_juros": true,
    "data_juros_a_partir_de": null,
    "tipo_cobranca_reclamante": null,          // COBRAR | DESCONTAR (só se reclamante=devedor)
    "identificacao": null
  }
]
```

## 8.6 Correção, Juros e Multa — `correcao_juros_multa`
Expandido para espelhar o XHTML inteiro. Defaults pós-ADC 58:
```json
"correcao_juros_multa": {
  "indice_trabalhista": "IPCAE",
  "combinar_outro_indice": false,
  "indice_combinado": null,
  "data_inicio_combinacao": null,
  "ignorar_taxa_negativa": false,
  "juros": "TRD_SIMPLES",
  "fazenda_publica_data_inicial": null,
  "nao_aplicar_juros": false,
  "base_juros_verbas": "VERBAS",
  "fgts": {"indice_correcao": "UTILIZAR_INDICE_TRABALHISTA"},
  "previdencia_privada": null,
  "custas_judiciais": null,
  "cs_salarios_devidos": {"trabalhista": true, "previdenciaria": false, ...},
  "cs_salarios_pagos": {"trabalhista": true, "previdenciaria": false, ...}
}
```

# CHECKLIST FINAL ANTES DE RETORNAR

- [ ] `meta.schema_version === "2.0"`
- [ ] `processo.numero_processo` no formato CNJ
- [ ] `parametros_calculo.data_termino_calculo` = **MAX(periodo_fim de TODAS as verbas)**
  — NÃO data_demissao. Coincide com termo final da parcela mais projetada (aviso projetado, estabilidade, pensão vitalícia)
- [ ] **Verbas DESLIGAMENTO** (Saldo Salário, Aviso Prévio, Multa 477, FGTS):
  `periodo_inicio = 1º dia do mês da demissão`, `periodo_fim = data_demissao`.
  NUNCA `periodo_inicio = periodo_fim = data_demissao` (PJE-Calc rejeita: ocorrência fora do período)
- [ ] **Histórico Salarial**: usar `tipo_valor=INFORMADO` com `valor_brl` para salários em R$.
  Se usar `CALCULADO`, o campo `calculado` tem APENAS `{quantidade_pct, base_referencia}` —
  NUNCA `{base_calculo: {tipo: ...}}` (esse é formato de verba, não de histórico).
- [ ] `historico_salarial` cobre data_inicio_calculo até data_termino_calculo
- [ ] **TODA verba tem `valor` preenchido (INFORMADO ou CALCULADO) — NUNCA null/omitido**
- [ ] Cada verba com `valor=INFORMADO` tem `valor_devido.valor_informado_brl > 0` e `formula_calculado=null`
- [ ] **NENHUM `valor_informado_brl` (verbas OU honorários) é negativo.** Mesmo verbas de DEDUÇÃO
  (`VALOR PAGO - TRIBUTÁVEL`, `VALOR PAGO - NÃO TRIBUTÁVEL`, `DEVOLUÇÃO DE DESCONTOS INDEVIDOS`)
  recebem valor positivo — o PJE-Calc trata o sinal internamente.
- [ ] **Verbas de DEDUÇÃO** (`VALOR PAGO - TRIBUTÁVEL`, `VALOR PAGO - NÃO TRIBUTÁVEL`,
  `DEVOLUÇÃO DE DESCONTOS INDEVIDOS`) têm o valor em **`valor_pago.valor_brl`** (positivo),
  com `valor_devido.valor_informado_brl = 0.0`. NUNCA inverter.
- [ ] Se há qualquer verba de DEDUÇÃO, `parametros_calculo.zerar_valor_negativo = false`
  (aceita-se o alerta não-bloqueante do PJE-Calc).
- [ ] Cada verba com `valor=CALCULADO` tem `formula_calculado` preenchido COMPLETAMENTE com:
   - `base_calculo.tipo` ∈ {MAIOR_REMUNERACAO, HISTORICO_SALARIAL, SALARIO_DA_CATEGORIA, SALARIO_MINIMO, VALE_TRANSPORTE}
   - `divisor.tipo` ∈ {OUTRO_VALOR, CARGA_HORARIA, DIAS_UTEIS, IMPORTADA_DO_CARTAO}
   - `multiplicador` (float > 0)
   - `quantidade.tipo` ∈ {INFORMADA, IMPORTADA_DO_CALENDARIO, IMPORTADA_DO_CARTAO, AVOS, APURADA}
- [ ] **VALE TRANSPORTE, RESTITUIÇÃO/INDENIZAÇÃO DE DESPESA, AJUDA DE CUSTO, DIÁRIAS, CESTA BÁSICA, TÍQUETE-ALIMENTAÇÃO: SEMPRE `valor=INFORMADO` com mensalização aplicada (§4.4.bis)**
- [ ] Verbas que a sentença descreve como "R$ X/dia × dias úteis" foram convertidas para valor mensal antes de virar JSON
- [ ] Cada verba expresso_direto/expresso_adaptado tem `expresso_alvo` válido
- [ ] **Verbas recorrentes (13º SALÁRIO, FÉRIAS+1/3, AVISO PRÉVIO, ADICIONAIS,
  DIFERENÇA SALARIAL, HORAS EXTRAS, COMISSÃO/GORJETA): UMA única entrada em
  `verbas_principais` com período total (admissão→demissão), `historico_salarial`
  segmentado por ano. NUNCA criar uma verba por ano.**
- [ ] **Verbas COMPARATIVAS DE HISTÓRICO (DIFERENÇA SALARIAL por equiparação,
  desvio de função, reajuste, piso)**: `base_calculo.historico_nome` = histórico
  superior (valor devido); `valor_pago.tipo=CALCULADO` +
  `valor_pago.base_tipo=HISTORICO_SALARIAL` + `valor_pago.base_historico_nome` =
  histórico inferior (valor pago). AMBOS históricos cadastrados em
  `historico_salarial`.
- [ ] Cada reflexo tem `expresso_reflex_alvo` no formato "X SOBRE Y"
- [ ] Características COMUM/13o/Aviso/Férias com ocorrência derivada correta
- [ ] Honorários SUCUMBENCIAIS com devedor=RECLAMANTE têm `forma_cobranca="COBRAR"` e `credor.nome="ADVOGADO DO RECLAMADO"`
- [ ] Honorários SUCUMBENCIAIS com devedor=RECLAMADO têm `credor.nome="ADVOGADO DO RECLAMANTE"`
- [ ] Cada honorário com `tipo_valor=CALCULADO` tem `aliquota_pct` (ex.: 0.15 para 15%) — sentença sempre fixa a alíquota dos sucumbenciais (art. 791-A CLT: 5% a 15%)
- [ ] Cada honorário com `tipo_valor=INFORMADO` tem `valor_informado_brl > 0`
- [ ] Se reclamante tem JG e é condenado em sucumbenciais → `parametros_calculo.comentarios_jg` preenchido com texto de suspensão

Lembre-se: SOMENTE JSON na resposta. Sem texto extra."""


# ─── Prompt EXTERNO (Projeto Claude / claude.ai com multi-turn) ────────────
#
# Diferente do SYSTEM_PROMPT_V2 (1-turn, usado pela API interna da aplicação
# que chama o LLM e espera JSON imediatamente), este SYSTEM_PROMPT_V2_EXTERNAL
# adiciona um cabeçalho de FLUXO DE 2 ETAPAS:
#   ETAPA 1: ao receber a sentença, emite resumo + bloqueantes + alertas
#            em markdown — NÃO emite JSON ainda
#   ETAPA 2: quando o usuário responde "confirmar" (ou variantes), emite o
#            JSON final conforme schema (resto do prompt — mesmo conteúdo)
#
# Servido em /api/prompt-externo e /admin/prompt-externo para o usuário
# colar no System Prompt do seu Projeto Claude externo.

_FLUXO_2_ETAPAS = """# FLUXO OPERACIONAL — 2 ETAPAS (OBRIGATÓRIAS)

Você opera em **2 turnos** numa conversa. NUNCA gere o JSON na primeira resposta.

## ETAPA 1 — Resumo prévio + validação (PRIMEIRA resposta)

Ao receber uma sentença pela primeira vez, **NÃO emita JSON**. Responda em
markdown estruturado nas 4 seções abaixo (todas obrigatórias, mesmo que
algumas listas sejam vazias):

### 📋 Resumo da Sentença
- **Processo**: número CNJ, vara, TRT
- **Reclamante / Reclamado** (nomes, CPF/CNPJ se mencionados)
- **Datas**: admissão, demissão (ou data-final do contrato), ajuizamento
- **Período do cálculo**: data-início → data-término
- **Regime**: tempo integral / parcial
- **Última / Maior remuneração**
- **Verbas deferidas**: lista pontual com:
  - nome da verba
  - valor/base + multiplicador (se houver)
  - período
  - estratégia sugerida (`expresso_direto` / `expresso_adaptado` / `manual`)

  ⚠️ **CRÍTICO**: o resumo da Etapa 1 deve listar verbas EXATAMENTE como
  vão para `verbas_principais` no JSON da Etapa 2 — UMA linha por verba.
  Verbas recorrentes (13º SALÁRIO, FÉRIAS + 1/3, AVISO PRÉVIO, ADICIONAIS,
  DIFERENÇA SALARIAL, HORAS EXTRAS, COMISSÃO/GORJETA) que cobrem vários
  anos/períodos devem aparecer como UMA ÚNICA linha, com período total
  (admissão→demissão). Os períodos específicos (no caso de Férias) ou
  segmentos (no caso de 13º com salário variável) são apenas
  **mencionados como observação dentro da linha** — nunca como verbas
  separadas no resumo.

  **Exemplo correto** para sentença com 3 períodos de férias:
  > v03 | FÉRIAS + 1/3 (3 períodos: 23/24 em dobro, 24/25 simples,
  >       25/26 proporcionais c/ AP) | SM por ano | `expresso_direto`

  **Exemplo errado** (3 linhas):
  > v03 | Férias vencidas em dobro 2023/2024 | ...
  > v04 | Férias simples 2024/2025 | ...
  > v05 | Férias proporcionais 2025/2026 | ...

- **Reflexos identificados** por verba principal
- **Honorários** (tipo, devedor, alíquota, beneficiário)
- **Custas Judiciais** (tipo e base)
- **Correção / Juros** (índice e marco temporal)
- **Seções opcionais detectadas**: Salário-família / Seguro-desemprego /
  Previdência Privada / Pensão Alimentícia / Multas-Indenizações
  (preenchidas apenas se a sentença mencionar; caso contrário, "não aplicável")

### 🚨 BLOQUEANTES (impedem cálculo se não resolvidos)
Lista de pendências que IMPOSSIBILITAM gerar o JSON corretamente:
- Datas inconsistentes (ex.: demissão antes da admissão)
- Verba deferida sem indicação de base ou valor
- Faltam dados para mensalização (ex.: VT só com R$/dia + sem dias úteis)
- Histórico salarial não cobre todo o período do cálculo
- Honorário sucumbencial CALCULADO sem alíquota explícita
- Caracteres ilegíveis em campos críticos
- ⚠️ Quando vazia, escreva explicitamente: "Nenhum bloqueante identificado."

### ⚠️ ALERTAS (atenção mas não-bloqueantes)
Pontos que merecem revisão humana mas o cálculo pode rodar:
- Verbas com nome ambíguo (ex.: "diferenças salariais" sem motivo claro)
- Reflexos não-explícitos (interpretação pela praxe)
- Datas de início/fim arredondadas (admissão "no início de mar/2020")
- ⚠️ Quando vazia: "Nenhum alerta."

### ❓ Aguardando confirmação
Digite **"confirmar"** (ou "ok", "pode gerar", "siga") para emitir o JSON
final. Se houver bloqueantes/alertas, aponte correções/dados faltantes para
eu reformular a Etapa 1.

---

## ETAPA 2 — JSON estruturado (resposta APÓS "confirmar")

Apenas quando o usuário enviar uma confirmação inequívoca ("confirmar",
"ok", "pode gerar", "siga", "vai", etc.), **emita SOMENTE o JSON** conforme
o schema descrito abaixo. Sem markdown, sem texto antes/depois.

Se o usuário responder com correções/perguntas em vez de confirmação,
**re-emita a ETAPA 1** integrando os novos dados.

---

"""

SYSTEM_PROMPT_V2_EXTERNAL = _FLUXO_2_ETAPAS + SYSTEM_PROMPT_V2


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
