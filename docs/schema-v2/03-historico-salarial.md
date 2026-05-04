# Schema — Histórico Salarial

**Mapeia para**: `historico-salarial.jsf` — modos INFORMADO e CALCULADO.

```json
{
  "historico_salarial": [
    {
      "nome": "ÚLTIMA REMUNERAÇÃO",
      "parcela": "FIXA",
      "incidencias": {
        "fgts": true,
        "cs_inss": true
      },
      "competencia_inicial": "09/2020",
      "competencia_final": "04/2025",
      "tipo_valor": "INFORMADO",
      "valor_brl": 1702.14,
      "calculado": null
    },
    {
      "nome": "SALÁRIO PAGO POR FORA",
      "parcela": "FIXA",
      "incidencias": {"fgts": true, "cs_inss": true},
      "competencia_inicial": "09/2020",
      "competencia_final": "04/2025",
      "tipo_valor": "INFORMADO",
      "valor_brl": 997.86,
      "calculado": null
    },
    {
      "nome": "SALÁRIO PROJETADO COM AUMENTO",
      "parcela": "VARIAVEL",
      "incidencias": {"fgts": true, "cs_inss": true},
      "competencia_inicial": "05/2025",
      "competencia_final": "04/2026",
      "tipo_valor": "CALCULADO",
      "valor_brl": null,
      "calculado": {
        "quantidade_pct": 1.10,
        "base_referencia": "ÚLTIMA REMUNERAÇÃO"
      }
    }
  ]
}
```

## Campos

| Campo | DOM ID | Tipo | Obrig | Notas |
|---|---|---|---|---|
| `nome` | `formulario:nome` | string | ✅ | Identificador (UPPER, sem acentos preferencialmente) |
| `parcela` | `formulario:tipoVariacaoDaParcela` | enum | ✅ | FIXA / VARIAVEL |
| `incidencias.fgts` | `formulario:fgts` | bool | ✅ | |
| `incidencias.cs_inss` | `formulario:inss` | bool | ✅ | |
| `competencia_inicial` | `formulario:competenciaInicialInputDate` | competencia_br | ✅ | MM/YYYY |
| `competencia_final` | `formulario:competenciaFinalInputDate` | competencia_br | ✅ | MM/YYYY |
| `tipo_valor` | `formulario:tipoValor` | enum | ✅ | INFORMADO / CALCULADO |
| `valor_brl` | `formulario:valorParaBaseDeCalculo` | money_br | quando INFORMADO | só INFORMADO |
| `calculado.quantidade_pct` | `formulario:quantidade` | percent | quando CALCULADO | ex: 1.10 = 110% |
| `calculado.base_referencia` | `formulario:baseDeReferencia` | string | quando CALCULADO | nome de outra entrada do histórico |

## Validações

1. `competencia_inicial` < `competencia_final`
2. Cobertura: união dos períodos DEVE incluir `data_inicio_calculo` até `data_termino_calculo`
3. Para verbas pós-rescisão (estabilidade, indenização Lei 9.029, dispensa discriminatória), o histórico DEVE continuar com `ÚLTIMA REMUNERAÇÃO` para meses pós-04/2025
4. Se `tipo_valor == CALCULADO` → `calculado.base_referencia` deve referenciar nome de outra entrada do histórico já cadastrada
5. Nome único: 2 entradas não podem ter o mesmo `nome`

## Defaults para extração

A IA deve extrair como mínimo 1 entrada `ÚLTIMA REMUNERAÇÃO` cobrindo todo o
período do cálculo (até `data_termino_calculo`). Se houver salário "por fora",
adicionar 2ª entrada `SALÁRIO PAGO POR FORA`. Se houver evolução salarial
(piso categoria, dissídio), criar entradas adicionais ou usar `CALCULADO`
com referência.
