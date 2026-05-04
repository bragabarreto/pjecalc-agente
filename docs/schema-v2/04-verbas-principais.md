# Schema — Verbas Principais (CORE)

**Mapeia para**: páginas Lançamento Manual / Expresso / Parâmetros da Verba.  
**Crítico**: este é o nó mais complexo da prévia. Cada verba traz TODOS os
parâmetros necessários para preenchimento sem inferência.

## Estratégia de preenchimento

Cada verba tem `estrategia_preenchimento`:

| Estratégia | Quando usar | Como o agente preenche |
|---|---|---|
| `expresso_direto` | Verba existe LITERAL no rol Expresso | Marca checkbox no Expresso, abre Parâmetros pós-Expresso para ajustar |
| `expresso_adaptado` | Verba não existe literal, mas similar pode ser adaptada | Marca checkbox de uma verba similar, abre Parâmetros e ALTERA `descricao` + parâmetros |
| `manual` | Verba muito específica, sem similar no Expresso | Click "Manual", preenche todos campos do form Novo |

⚠️ Para `expresso_direto` e `expresso_adaptado`, é OBRIGATÓRIO o campo
`expresso_alvo` (nome EXATO no rol Expresso).

## Estrutura completa

```json
{
  "verbas_principais": [
    {
      "id": "v01",
      "nome_sentenca": "Indenização por dano moral",
      "estrategia_preenchimento": "expresso_direto",
      "expresso_alvo": "INDENIZAÇÃO POR DANO MORAL",
      "nome_pjecalc": "INDENIZAÇÃO POR DANO MORAL",

      "parametros": {
        "assunto_cnj": {
          "codigo": 1855,
          "label": "Indenização por Dano Moral"
        },
        "parcela": "FIXA",
        "valor": "INFORMADO",

        "incidencias": {
          "irpf": false,
          "cs_inss": false,
          "fgts": false,
          "previdencia_privada": false,
          "pensao_alimenticia": false
        },

        "caracteristica": "COMUM",
        "ocorrencia_pagamento": "MENSAL",
        "ocorrencia_ajuizamento": "OCORRENCIAS_VENCIDAS",

        "tipo": "PRINCIPAL",
        "gerar_reflexa": "DIFERENCA",
        "gerar_principal": "DIFERENCA",
        "compor_principal": true,
        "zerar_valor_negativo": false,

        "periodo_inicio": "01/04/2025",
        "periodo_fim": "01/04/2025",

        "exclusoes": {
          "faltas_justificadas": false,
          "faltas_nao_justificadas": false,
          "ferias_gozadas": false,
          "dobrar_valor_devido": false
        },

        "valor_devido": {
          "tipo": "INFORMADO",
          "valor_informado_brl": 5000.00,
          "proporcionalizar": false
        },

        "formula_calculado": null,

        "valor_pago": {
          "tipo": "INFORMADO",
          "valor_brl": 0.00,
          "proporcionalizar": false
        },

        "comentarios": null
      },

      "ocorrencias_override": null,

      "reflexos": [
        {
          "id": "r01-01",
          "nome": "13º Salário sobre Indenização por Dano Moral",
          "estrategia_reflexa": "checkbox_painel",
          "indice_reflexo_listagem": null,
          "expresso_reflex_alvo": "13º SALÁRIO SOBRE INDENIZAÇÃO POR DANO MORAL",

          "parametros_override": null,
          "ocorrencias_override": null
        }
      ]
    }
  ]
}
```

## Campos do nó `parametros` (verba principal)

### Identificação
| Campo | DOM ID (Manual+Parâmetros) | Tipo | Obrig | Default | Notas |
|---|---|---|---|---|---|
| `assunto_cnj.codigo` | `formulario:codigoAssuntosCnj` | int | ✅ | — | Tabela CNJ |
| `assunto_cnj.label` | `formulario:assuntosCnj` | string | ✅ | — | Label visível |

### Parcela / Valor
| Campo | DOM ID | Tipo | Obrig | Default | Notas |
|---|---|---|---|---|---|
| `parcela` | `formulario:tipoVariacaoDaParcela` | enum | ✅ | FIXA | FIXA / VARIAVEL |
| `valor` | `formulario:valor` | enum | ✅ | CALCULADO | CALCULADO / **INFORMADO** |

### Incidências (5 checkboxes, multi-escolha)
| Campo | DOM ID | Tipo | Default |
|---|---|---|---|
| `incidencias.irpf` | `formulario:irpf` | bool | (depende da verba) |
| `incidencias.cs_inss` | `formulario:inss` | bool | (depende) |
| `incidencias.fgts` | `formulario:fgts` | bool | (depende) |
| `incidencias.previdencia_privada` | `formulario:previdenciaPrivada` | bool | false |
| `incidencias.pensao_alimenticia` | `formulario:pensaoAlimenticia` | bool | false |

### Característica e Ocorrência
| Campo | DOM ID | Tipo | Valores | Notas |
|---|---|---|---|---|
| `caracteristica` | `formulario:caracteristicaVerba` | enum | COMUM / DECIMO_TERCEIRO_SALARIO / AVISO_PREVIO / FERIAS | Determina ocorrência default |
| `ocorrencia_pagamento` | `formulario:ocorrenciaPagto` | enum | MENSAL / DEZEMBRO / DESLIGAMENTO / PERIODO_AQUISITIVO | Auto-derivado da característica |
| `ocorrencia_ajuizamento` | `formulario:ocorrenciaAjuizamento` | enum | OCORRENCIAS_VENCIDAS_E_VINCENDAS / OCORRENCIAS_VENCIDAS | Súmula 439 TST |

### Tipo e Reflexos
| Campo | DOM ID | Tipo | Default | Notas |
|---|---|---|---|---|
| `tipo` | `formulario:tipoDeVerba` | enum | PRINCIPAL | PRINCIPAL / REFLEXO. Em verba principal sempre PRINCIPAL |
| `gerar_reflexa` | `formulario:geraReflexo` | enum | DIFERENCA | DEVIDO / DIFERENCA |
| `gerar_principal` | `formulario:gerarPrincipal` | enum | DIFERENCA | DEVIDO / DIFERENCA |
| `compor_principal` | `formulario:comporPrincipal` | bool | true | |
| `zerar_valor_negativo` | `formulario:zeraValorNegativo` | bool | false | |

### Período
| Campo | DOM ID | Tipo | Notas |
|---|---|---|---|
| `periodo_inicio` | `formulario:periodoInicialInputDate` | date_br | DEVE ser ≥ data_inicio_calculo |
| `periodo_fim` | `formulario:periodoFinalInputDate` | date_br | DEVE ser ≤ data_termino_calculo |

### Exclusões
| Campo | DOM ID | Tipo |
|---|---|---|
| `exclusoes.faltas_justificadas` | `formulario:excluirFaltaJustificada` | bool |
| `exclusoes.faltas_nao_justificadas` | `formulario:excluirFaltaNaoJustificada` | bool |
| `exclusoes.ferias_gozadas` | `formulario:excluirFeriasGozadas` | bool |
| `exclusoes.dobrar_valor_devido` | `formulario:dobraValorDevido` | bool |

### Valor Devido — modo INFORMADO
Aparece quando `valor == INFORMADO`:
| Campo | DOM ID | Tipo | Notas |
|---|---|---|---|
| `valor_devido.tipo` | (derivado de `valor`) | enum | INFORMADO |
| `valor_devido.valor_informado_brl` | **`formulario:valorInformadoDoDevido`** | money_br | OBRIGATÓRIO quando informado |
| `valor_devido.proporcionalizar` | `formulario:aplicarProporcionalidadeAoValorDevido` | bool | |

### Valor Devido — modo CALCULADO (Fórmula)
Aparece quando `valor == CALCULADO`. O nó `formula_calculado` substitui `valor_devido.valor_informado_brl`:
```json
"formula_calculado": {
  "base_calculo": {
    "tipo": "HISTORICO_SALARIAL",
    "historico_nome": "ÚLTIMA REMUNERAÇÃO",
    "proporcionaliza": "NAO",
    "bases_compostas": [
      {"verba": "ADICIONAL DE INSALUBRIDADE 20%", "integralizar": "SIM"}
    ]
  },
  "divisor": {
    "tipo": "OUTRO_VALOR",
    "valor": 220
  },
  "multiplicador": 1.50,
  "quantidade": {
    "tipo": "INFORMADA",
    "valor": 22.00,
    "proporcionalizar": false
  }
}
```

| Campo | DOM ID | Tipo | Notas |
|---|---|---|---|
| `formula_calculado.base_calculo.tipo` | `formulario:tipoDaBaseTabelada` | enum | MAIOR_REMUNERACAO / HISTORICO_SALARIAL / SALARIO_DA_CATEGORIA / SALARIO_MINIMO / VALE_TRANSPORTE |
| `formula_calculado.base_calculo.historico_nome` | `formulario:baseHistoricos` | string | só quando tipo=HISTORICO_SALARIAL |
| `formula_calculado.base_calculo.proporcionaliza` | `formulario:proporcionalizaHistorico` | enum SIM/NAO | só HISTORICO_SALARIAL |
| `formula_calculado.base_calculo.bases_compostas[]` | `formulario:incluirBaseHistorico` (botão +) | array | bases adicionais |
| `formula_calculado.base_calculo.bases_compostas[].verba` | `formulario:baseVerbaDeCalculo` | string | nome da verba referência |
| `formula_calculado.base_calculo.bases_compostas[].integralizar` | `formulario:integralizarBase` | enum SIM/NAO | |
| `formula_calculado.divisor.tipo` | `formulario:tipoDeDivisor` | enum | OUTRO_VALOR / CARGA_HORARIA / DIAS_UTEIS / IMPORTADA_DO_CARTAO |
| `formula_calculado.divisor.valor` | `formulario:outroValorDoDivisor` | number | só OUTRO_VALOR |
| `formula_calculado.multiplicador` | `formulario:outroValorDoMultiplicador` | number | (1.50 = 50%) |
| `formula_calculado.quantidade.tipo` | `formulario:tipoDaQuantidade` | enum | INFORMADA / IMPORTADA_DO_CALENDARIO / IMPORTADA_DO_CARTAO |
| `formula_calculado.quantidade.valor` | `formulario:valorInformadoDaQuantidade` | number | só INFORMADA |
| `formula_calculado.quantidade.proporcionalizar` | `formulario:aplicarProporcionalidadeAQuantidade` | bool | |

### Valor Pago
| Campo | DOM ID | Tipo |
|---|---|---|
| `valor_pago.tipo` | `formulario:tipoDoValorPago` | enum INFORMADO/CALCULADO |
| `valor_pago.valor_brl` | `formulario:valorInformadoPago` | money_br |
| `valor_pago.proporcionalizar` | `formulario:aplicarProporcionalidadeValorPago` | bool |

### Outros
| Campo | DOM ID | Tipo |
|---|---|---|
| `comentarios` | `formulario:comentarios` | string |

## Override de Ocorrências (raro)

`ocorrencias_override` permite especificar valores mês a mês (sentenças com tabela
explícita). Quando `null`, o agente usa o valor uniforme + Lote.

```json
"ocorrencias_override": {
  "modo": "valores_mensais",
  "valores": [
    {"mes": "04/2025", "valor_devido": 5000.00, "valor_pago": 0.00},
    {"mes": "05/2025", "valor_devido": 5000.00, "valor_pago": 0.00}
  ]
}
```

## Reflexos

Cada verba principal tem 0..N reflexos. Estrutura:

```json
{
  "id": "r01-01",
  "nome": "13º Salário sobre Indenização por Dano Moral",
  "estrategia_reflexa": "checkbox_painel",
  "indice_reflexo_listagem": null,
  "expresso_reflex_alvo": "13º SALÁRIO SOBRE INDENIZAÇÃO POR DANO MORAL",
  "parametros_override": null,
  "ocorrencias_override": null
}
```

| Campo | Tipo | Notas |
|---|---|---|
| `id` | string | identificador único (rXX-YY) |
| `nome` | string | nome da reflexa na sentença |
| `estrategia_reflexa` | enum | `checkbox_painel` (preferencial) / `manual` |
| `indice_reflexo_listagem` | int? | index M no `listaReflexo:M:ativo` (preenchido pelo agente em runtime) |
| `expresso_reflex_alvo` | string | nome do reflexo no painel |
| `parametros_override` | object? | se diferente do default — campos do doc 07 (comportamentoDoReflexo, etc.) |
| `ocorrencias_override` | object? | só se sentença tem valores específicos |

### Estratégia `checkbox_painel`
1. Agente abre listagem de Verbas
2. Click `formulario:listagem:N:divDestinacoes .linkDestinacoes` (Exibir)
3. Click `formulario:listagem:N:listaReflexo:M:ativo` (marca checkbox)
4. Aguarda AJAX
5. Se `parametros_override` não-null → click `formulario:listagem:N:listaReflexo:M:j_id573` (Parametrizar) → preenche overrides → Salva
6. Se `ocorrencias_override` não-null → abre Ocorrências da Verba principal → seção `formulario:reflexos:N:listagem:M:*` → preenche

### Estratégia `manual`
Quando o reflexo NÃO existe no painel pré-cadastrado (raro). Cria como verba
Manual independente com `tipo=REFLEXO` e `baseVerbaDeCalculo` apontando para a
verba principal.

## Override de parâmetros do reflexo (`parametros_override`)

Pode incluir QUALQUER campo dos parâmetros do reflexo (doc 07). Defaults vêm
do PJE-Calc:

```json
"parametros_override": {
  "comportamento_reflexo": "VALOR_MENSAL",
  "tratamento_fracao_mes": "INTEGRALIZAR",
  "outro_valor_divisor": 30,
  "outro_valor_multiplicador": 1.00
}
```

## Validações cruzadas

1. `valor == INFORMADO` → `valor_devido.valor_informado_brl` é OBRIGATÓRIO
2. `valor == CALCULADO` → `formula_calculado` é OBRIGATÓRIO
3. `formula_calculado.base_calculo.tipo == HISTORICO_SALARIAL` → `historico_nome` deve referenciar entrada de `historico_salarial`
4. `caracteristica == AVISO_PREVIO` → `ocorrencia_pagamento` default = `DESLIGAMENTO`
5. `caracteristica == DECIMO_TERCEIRO_SALARIO` → `ocorrencia_pagamento` default = `DEZEMBRO`
6. `caracteristica == FERIAS` → `ocorrencia_pagamento` default = `PERIODO_AQUISITIVO`
7. `caracteristica == COMUM` → `ocorrencia_pagamento` default = `MENSAL`
8. `expresso_alvo` deve ser nome EXATO de uma das 54 verbas Expresso (ver doc 02)
9. `reflexos[].expresso_reflex_alvo` deve seguir padrão "X SOBRE Y" onde Y = nome_pjecalc da verba principal

## Tabela de keywords para auto-classificar `caracteristica`

| Keywords no nome | caracteristica auto-derivada |
|---|---|
| "13", "decimo terceiro", "13º" | DECIMO_TERCEIRO_SALARIO |
| "aviso previo", "aviso prévio" | AVISO_PREVIO |
| "ferias", "férias" + "1/3" / "+ 1/3" | FERIAS |
| (resto) | COMUM |

## Exemplos completos

### Verba expresso_direto + Valor=CALCULADO (HE 50%)
```json
{
  "id": "v02",
  "nome_sentenca": "Horas extras 50% e reflexos",
  "estrategia_preenchimento": "expresso_direto",
  "expresso_alvo": "HORAS EXTRAS 50%",
  "nome_pjecalc": "HORAS EXTRAS 50%",
  "parametros": {
    "valor": "CALCULADO",
    "caracteristica": "COMUM",
    "ocorrencia_pagamento": "MENSAL",
    "periodo_inicio": "25/09/2020",
    "periodo_fim": "01/04/2025",
    "incidencias": {"irpf": true, "cs_inss": true, "fgts": true, "previdencia_privada": false, "pensao_alimenticia": false},
    "formula_calculado": {
      "base_calculo": {"tipo": "HISTORICO_SALARIAL", "historico_nome": "ÚLTIMA REMUNERAÇÃO", "proporcionaliza": "NAO"},
      "divisor": {"tipo": "OUTRO_VALOR", "valor": 220},
      "multiplicador": 1.50,
      "quantidade": {"tipo": "INFORMADA", "valor": 22.00, "proporcionalizar": false}
    },
    "valor_devido": {"tipo": "CALCULADO"}
  },
  "reflexos": [
    {"nome": "Aviso Prévio sobre HE 50%", "estrategia_reflexa": "checkbox_painel", "expresso_reflex_alvo": "AVISO PRÉVIO SOBRE HORAS EXTRAS 50%"},
    {"nome": "Férias + 1/3 sobre HE 50%", "estrategia_reflexa": "checkbox_painel", "expresso_reflex_alvo": "FÉRIAS + 1/3 SOBRE HORAS EXTRAS 50%"},
    {"nome": "13º sobre HE 50%", "estrategia_reflexa": "checkbox_painel", "expresso_reflex_alvo": "13º SALÁRIO SOBRE HORAS EXTRAS 50%"},
    {"nome": "RSR/Feriado sobre HE 50%", "estrategia_reflexa": "checkbox_painel", "expresso_reflex_alvo": "REPOUSO SEMANAL REMUNERADO E FERIADO SOBRE HORAS EXTRAS 50%"}
  ]
}
```

### Verba expresso_adaptado (Estabilidade Gestante)
```json
{
  "id": "v03",
  "nome_sentenca": "Indenização Estabilidade Gestante",
  "estrategia_preenchimento": "expresso_adaptado",
  "expresso_alvo": "INDENIZAÇÃO ADICIONAL",
  "nome_pjecalc": "INDENIZAÇÃO ESTABILIDADE GESTANTE - ART 10 II ADCT",
  "parametros": {
    "valor": "CALCULADO",
    "caracteristica": "COMUM",
    "ocorrencia_pagamento": "MENSAL",
    "periodo_inicio": "02/04/2025",
    "periodo_fim": "01/09/2025",
    "incidencias": {"irpf": true, "cs_inss": true, "fgts": true, "previdencia_privada": false, "pensao_alimenticia": false},
    "formula_calculado": {
      "base_calculo": {"tipo": "MAIOR_REMUNERACAO"},
      "divisor": {"tipo": "OUTRO_VALOR", "valor": 1},
      "multiplicador": 1.00,
      "quantidade": {"tipo": "INFORMADA", "valor": 1.00}
    }
  },
  "reflexos": [
    {"nome": "13º Salário sobre Estabilidade Gestante", "estrategia_reflexa": "checkbox_painel"},
    {"nome": "Férias + 1/3 sobre Estabilidade Gestante", "estrategia_reflexa": "checkbox_painel"},
    {"nome": "FGTS + 40% sobre Estabilidade", "estrategia_reflexa": "manual"}
  ]
}
```

### Verba manual (Multa Convencional rara)
```json
{
  "id": "v04",
  "nome_sentenca": "Multa convencional cláusula 50ª da CCT",
  "estrategia_preenchimento": "manual",
  "expresso_alvo": null,
  "nome_pjecalc": "MULTA CONVENCIONAL CCT 50ª",
  "parametros": {
    "valor": "INFORMADO",
    "caracteristica": "COMUM",
    "ocorrencia_pagamento": "DESLIGAMENTO",
    "periodo_inicio": "01/04/2025",
    "periodo_fim": "01/04/2025",
    "valor_devido": {"tipo": "INFORMADO", "valor_informado_brl": 1500.00}
  }
}
```
