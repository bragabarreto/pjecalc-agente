# Schema — Honorários, Custas, Correção/Juros, Liquidação

## 11. Honorários

**Mapeia para**: `honorarios.jsf` (lista + form Novo)

```json
{
  "honorarios": [
    {
      "id": "h01",
      "tipo_honorario": "SUCUMBENCIAIS",
      "descricao": "Honorários sucumbenciais devidos pelo reclamado",
      "tipo_devedor": "RECLAMADO",
      "tipo_valor": "CALCULADO",
      "aliquota_pct": 10.00,
      "base_para_apuracao": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
      "credor": {
        "selecao_existente": null,
        "nome": "FULANO ADVOGADO",
        "doc_fiscal_tipo": "CPF",
        "doc_fiscal_numero": "..."
      },
      "apurar_irrf": false,
      "valor_informado_brl": null
    },
    {
      "id": "h02",
      "tipo_honorario": "PERICIAIS_MEDICO",
      "descricao": "Honorários periciais",
      "tipo_devedor": "RECLAMADO",
      "tipo_valor": "INFORMADO",
      "aliquota_pct": null,
      "base_para_apuracao": null,
      "credor": {
        "selecao_existente": null,
        "nome": "DR. JOÃO MÉDICO",
        "doc_fiscal_tipo": "CPF",
        "doc_fiscal_numero": "..."
      },
      "apurar_irrf": false,
      "valor_informado_brl": 2000.00
    }
  ]
}
```

| Campo | DOM ID | Enum |
|---|---|---|
| `tipo_honorario` | `formulario:tpHonorario` | ADVOCATICIOS / ASSISTENCIAIS / CONTRATUAIS / PERICIAIS_CONTADOR / PERICIAIS_DOCUMENTOSCOPIO / PERICIAIS_ENGENHEIRO / PERICIAIS_INTERPRETE / PERICIAIS_MEDICO / PERICIAIS_OUTROS / **SUCUMBENCIAIS** / LEILOEIRO |
| `tipo_devedor` | `formulario:tipoDeDevedor` | RECLAMANTE / **RECLAMADO** |
| `tipo_valor` | `formulario:tipoValor` | INFORMADO / **CALCULADO** |
| `base_para_apuracao` | `formulario:baseParaApuracao` | BRUTO / BRUTO_MENOS_CONTRIBUICAO_SOCIAL / BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA |

⚠️ **Honorário Sucumbencial do Reclamante** — quando o reclamante é parcialmente
sucumbente, criar 2 entradas:
1. `tipo_devedor=RECLAMADO`, devedor para advogado do reclamante
2. `tipo_devedor=RECLAMANTE`, devedor para advogado da contraparte ("ADVOGADO DA PARTE [reclamado]")

## 12. Custas Judiciais

**Mapeia para**: `custas-judiciais.jsf`

```json
{
  "custas_judiciais": {
    "base_para_calculadas": "BRUTO_DEVIDO_AO_RECLAMANTE",
    "custas_conhecimento_reclamante": "NAO_SE_APLICA",
    "custas_conhecimento_reclamado": "CALCULADA_2_POR_CENTO",
    "custas_liquidacao": "NAO_SE_APLICA",
    "data_vencimento_fixas": null,
    "qtd_atos": {
      "urbanos": 0,
      "rurais": 0,
      "agravos_instrumento": 0,
      "agravos_peticao": 0,
      "impugnacao_sentenca": 0,
      "embargos_arrematacao": 0,
      "embargos_execucao": 0,
      "embargos_terceiros": 0,
      "recurso_revista": 0
    },
    "autos": [],
    "armazenamentos": [],
    "rd": [],
    "rt": []
  }
}
```

| Campo | DOM ID | Enum |
|---|---|---|
| `base_para_calculadas` | `formulario:baseParaCustasCalculadas` | BRUTO_DEVIDO_AO_RECLAMANTE / BRUTO_DEVIDO_AO_RECLAMANTE_MAIS_DEBITOS_RECLAMADO |
| `custas_conhecimento_*` | `formulario:tipoDeCustasDeConhecimento*` | NAO_SE_APLICA / CALCULADA_2_POR_CENTO / INFORMADA |
| `custas_liquidacao` | `formulario:tipoDeCustasDeLiquidacao` | NAO_SE_APLICA / CALCULADA_MEIO_POR_CENTO / INFORMADA |

## 13. Correção, Juros e Multa

**Mapeia para**: `parametros-atualizacao/parametros-atualizacao.jsf`

```json
{
  "correcao_juros_multa": {
    "indice_trabalhista": "IPCAE",
    "combinar_outro_indice": false,
    "ignorar_taxa_negativa": true,
    "aplicar_juros_pre_judicial": false,
    "juros": "TAXA_LEGAL",
    "combinar_outro_juros": false,
    "outro_juros": null,
    "outro_juros_a_partir_de": null,
    "base_juros_verbas": "VERBAS",

    "fgts": {
      "indice_correcao": "UTILIZAR_INDICE_TRABALHISTA"
    },
    "previdencia_privada": {
      "aplicar_juros": false,
      "indice_correcao": "UTILIZAR_INDICE_TRABALHISTA",
      "outro_indice": null
    },
    "custas": {
      "correcao_ativa": true,
      "juros_ativos": true,
      "indice_correcao": "UTILIZAR_INDICE_TRABALHISTA",
      "outro_indice": null
    },
    "lei_11941": {
      "correcao_ativa": false,
      "aplicar_ate": null,
      "multa_ativa": false,
      "aplicar_multa_ate": null
    },
    "inss_devidos": {
      "correcao_trabalhista": true,
      "juros_trabalhistas": true,
      "correcao_previdenciaria": false,
      "juros_previdenciarios": false,
      "multa": {
        "aplicar": false,
        "tipo": "URBANA",
        "pagamento": "INTEGRAL"
      }
    },
    "inss_pagos": {
      "correcao_trabalhista": false,
      "juros_trabalhistas": false,
      "correcao_previdenciaria": false,
      "juros_previdenciarios": false,
      "forma_aplicacao_salario_pago": "MES_A_MES",
      "multa": {
        "aplicar": false,
        "tipo": "URBANA",
        "pagamento": "INTEGRAL"
      }
    }
  }
}
```

| Campo | DOM ID | Enum |
|---|---|---|
| `indice_trabalhista` | `formulario:indiceTrabalhista` | TUACDT / TABELA_DEVEDOR_FAZENDA / TABELA_INDEBITO_TRIBUTARIO / TABELA_UNICA_JT_MENSAL / TABELA_UNICA_JT_DIARIO / TR / IGPM / INPC / IPC / **IPCAE** / IPCAETR / SELIC / SELIC_FAZENDA / SELIC_BACEN / SEM_CORRECAO |
| `juros` | `formulario:juros` | JUROS_PADRAO / JUROS_POUPANCA / FAZENDA_PUBLICA / JUROS_MEIO_PORCENTO / JUROS_UM_PORCENTO / JUROS_ZERO_TRINTA_TRES / SELIC / SELIC_FAZENDA / SELIC_BACEN / TRD_SIMPLES / TRD_COMPOSTOS / **TAXA_LEGAL** / SEM_JUROS |
| `base_juros_verbas` | `formulario:baseDeJurosDasVerbas` | **VERBAS** / VERBA_INSS / VERBA_INSS_PP |
| `fgts.indice_correcao` | `formulario:indiceDeCorrecaoDoFGTS` | UTILIZAR_INDICE_TRABALHISTA / UTILIZAR_INDICE_JAM / UTILIZAR_INDICE_JAM_E_TRABALHISTA |

⚠️ **Pós ADC 58/2020 + IN TST 41**: padrão atual é IPCAE até Set/2024 + Selic
após (combinar_outro_juros=true). Pode variar por jurisprudência regional.

## 14. Liquidação

**Mapeia para**: `liquidacao.jsf`

```json
{
  "liquidacao": {
    "data_de_liquidacao": "04/05/2026",
    "indices_acumulados": "MES_SUBSEQUENTE_AO_VENCIMENTO"
  }
}
```

| Campo | DOM ID | Enum |
|---|---|---|
| `data_de_liquidacao` | `formulario:dataDeLiquidacaoInputDate` | date_br (default: hoje) |
| `indices_acumulados` | `formulario:indicesAcumulados` | **MES_SUBSEQUENTE_AO_VENCIMENTO** / MES_DO_VENCIMENTO / MES_SUBSEQUENTE_E_MES_DO_VENCIMENTO |

A liquidação é o passo final automático — nenhum dado da sentença afeta diretamente.
