# Schema JSON — Contrato pjecalc-agente

Schema completo do JSON que conecta a extração (Fases 1-2) com a automação (Fase 4-6).
Este é o schema real implementado — difere do CalcMACHINE em alguns campos.

---

## Estrutura completa

```json
{
  "processo": {
    "numero": "0000153-87.2026.5.07.0002",
    "numero_seq": "0000153",
    "digito_verificador": "87",
    "ano": "2026",
    "segmento": "5",
    "regiao": "07",
    "vara": "0002",
    "reclamante": "João da Silva",
    "cpf_reclamante": "000.000.000-00",
    "reclamado": "Empresa ABC Ltda",
    "cnpj_reclamado": "00.000.000/0000-00",
    "estado": "CE",
    "municipio": "FORTALEZA",
    "vara_nome": "3ª Vara do Trabalho de Fortaleza",
    "autuado_em": "20/01/2025",
    "valor_causa": 50000.00
  },

  "contrato": {
    "admissao": "01/03/2022",
    "demissao": "03/12/2024",
    "ajuizamento": "15/01/2025",
    "tipo_rescisao": "sem_justa_causa",
    "ultima_remuneracao": 1518.00,
    "maior_remuneracao": 1518.00,
    "carga_horaria": 220,
    "jornada_diaria": 8.0,
    "jornada_semanal": 44.0,
    "regime": "Tempo Integral"
  },

  "verbas_deferidas": [
    {
      "nome_sentenca": "SALDO DE SALÁRIO",
      "texto_original": "Período: 01/11/2024 a 03/12/2024",
      "tipo": "Principal",
      "caracteristica": "Comum",
      "ocorrencia": "Desligamento",
      "periodo_inicio": "01/11/2024",
      "periodo_fim": "03/12/2024",
      "percentual": null,
      "base_calculo": "Historico Salarial",
      "valor_informado": null,
      "incidencia_fgts": true,
      "incidencia_inss": true,
      "incidencia_ir": true,
      "sumula_439": false,
      "verba_principal_ref": null,
      "confianca": 0.95
    },
    {
      "nome_sentenca": "HORAS EXTRAS 50%",
      "tipo": "Principal",
      "caracteristica": "Comum",
      "ocorrencia": "Mensal",
      "periodo_inicio": "01/03/2022",
      "periodo_fim": "03/12/2024",
      "percentual": 0.50,
      "base_calculo": "Historico Salarial",
      "incidencia_fgts": true,
      "incidencia_inss": true,
      "incidencia_ir": true,
      "confianca": 0.95
    },
    {
      "nome_sentenca": "13º SALÁRIO PROPORCIONAL",
      "tipo": "Principal",
      "caracteristica": "13o Salario",
      "ocorrencia": "Dezembro",
      "periodo_inicio": "01/01/2024",
      "periodo_fim": "03/12/2024",
      "incidencia_fgts": true,
      "incidencia_inss": true,
      "incidencia_ir": true,
      "confianca": 0.95
    }
  ],

  "ferias": [
    {
      "situacao": "Vencidas",
      "periodo_inicio": "01/03/2022",
      "periodo_fim": "28/02/2023",
      "abono": false,
      "dobra": false
    },
    {
      "situacao": "Proporcionais",
      "periodo_inicio": "01/03/2024",
      "periodo_fim": "03/12/2024",
      "abono": false,
      "dobra": false
    }
  ],

  "historico_salarial": [
    {
      "nome": "Salário",
      "data_inicio": "01/03/2022",
      "data_fim": "31/08/2024",
      "valor": 1320.00,
      "incidencia_fgts": true,
      "incidencia_cs": true
    },
    {
      "nome": "Salário",
      "data_inicio": "01/09/2024",
      "data_fim": "03/12/2024",
      "valor": 1518.00,
      "incidencia_fgts": true,
      "incidencia_cs": true
    }
  ],

  "aviso_previo": {
    "tipo": "Calculado",
    "prazo_dias": null,
    "projetar": true,
    "confianca": 0.90
  },

  "fgts": {
    "aliquota": 0.08,
    "multa_40": true,
    "multa_467": false,
    "saldo_fgts": null,
    "confianca": 0.95
  },

  "honorarios": [
    {
      "tipo": "SUCUMBENCIAIS",
      "devedor": "RECLAMADO",
      "tipo_valor": "CALCULADO",
      "base_apuracao": "Condenação",
      "percentual": 0.15,
      "valor_informado": null,
      "apurar_ir": true
    }
  ],

  "honorarios_periciais": null,

  "contribuicao_social": {
    "apurar_segurado_salarios_devidos": true,
    "cobrar_do_reclamante": true,
    "com_correcao_trabalhista": false,
    "apurar_sobre_salarios_pagos": false,
    "lei_11941": null,
    "confianca": 0.85
  },

  "imposto_renda": {
    "apurar": true,
    "tributacao_exclusiva": false,
    "regime_de_caixa": false,
    "tributacao_em_separado": false,
    "deducao_inss": true,
    "deducao_honorarios_reclamante": false,
    "deducao_pensao_alimenticia": false,
    "valor_pensao": null,
    "meses_tributaveis": null,
    "dependentes": null,
    "confianca": 0.80
  },

  "correcao_juros": {
    "indice_correcao": "Tabela JT Unica Mensal",
    "base_juros": "Verbas",
    "taxa_juros": "Selic",
    "jam_fgts": false,
    "confianca": 0.85
  },

  "faltas": [],

  "campos_ausentes": [],
  "alertas": ["Dados extraídos de relatório estruturado (alta confiança)."]
}
```

---

## Enums e valores aceitos

### processo.estado
Siglas UF: AC, AL, AP, AM, BA, CE, DF, ES, GO, MA, MT, MS, MG, PA, PB, PR, PE, PI, RJ, RN, RS, RO, RR, SC, SP, SE, TO

### contrato.tipo_rescisao
| Valor | Significado |
|---|---|
| `sem_justa_causa` | Demissão sem justa causa / imotivada |
| `justa_causa` | Demissão por justa causa |
| `pedido_demissao` | Pedido de demissão pelo empregado |
| `rescisao_indireta` | Rescisão indireta (falta grave do empregador) |
| `distrato` | Distrato (acordo entre as partes) |
| `morte` | Morte do empregado |
| `culpa_reciproca` | Culpa recíproca |
| `contrato_prazo` | Término de contrato por prazo determinado |

### contrato.regime
`Tempo Integral` | `Tempo Parcial` | `Intermitente`

### verbas_deferidas.caracteristica
`Comum` | `13o Salario` | `Aviso Previo` | `Ferias`

### verbas_deferidas.ocorrencia
`Mensal` | `Dezembro` | `Periodo Aquisitivo` | `Desligamento`

### verbas_deferidas.base_calculo
`Maior Remuneracao` | `Historico Salarial` | `Salario Minimo` | `Piso Salarial` | `Verbas`

### aviso_previo.tipo
`Calculado` | `Informado` | `Nao Apurar`

### honorarios.tipo
`SUCUMBENCIAIS` | `CONTRATUAIS`

### honorarios.devedor
`RECLAMADO` | `RECLAMANTE`

### honorarios.tipo_valor
`CALCULADO` | `INFORMADO`

### honorarios.base_apuracao
`Condenação` | `Verbas Não Compõem Principal` | `Renda Mensal`

### ferias.situacao
`Vencidas` | `Proporcionais` | `Gozadas`

### correcao_juros.indice_correcao
`Tabela JT Unica Mensal` | `IPCA-E` | `Selic` | `TRCT`

### correcao_juros.taxa_juros
`Juros Padrao` | `Selic`

---

## Diferenças vs CalcMACHINE

| Campo | CalcMACHINE | pjecalc-agente |
|---|---|---|
| `estado` | Índice numérico (0-26) | Sigla UF ("CE") |
| `municipio` | Texto | Texto (nome cidade apenas) |
| `remuneracao` | String "2163.00" | Float 2163.00 |
| Datas | ISO YYYY-MM-DD | DD/MM/AAAA |
| `honorarios` | String | Array de objetos |
| `ferias` | Array (simples) | Array com situacao/periodo |
| `saldo_fgts` | Não existe | float \| null |
| Booleanos | Strings "sim"/"não" | true/false nativos |
