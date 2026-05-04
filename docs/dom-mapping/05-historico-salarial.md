# DOM Mapping — Histórico Salarial

**URL**: `/pjecalc/pages/calculo/historico-salarial.jsf`  
**Caminho**: Cálculo > Histórico Salarial

## Página Listagem
| Função | DOM ID |
|---|---|
| Novo | `formulario:incluir` (input button "Novo") |
| Grade de Ocorrências | (link específico — a verificar) |

## Formulário "Novo Histórico Salarial"

### Importação CSV (alternativa)
| Campo | DOM ID | Tipo |
|---|---|---|
| Selecionar Arquivo CSV | `arquivo:file` | input file |
| Confirmar Importação | `j_id97` (input button) | button |

### Cadastro Manual
| Campo Prévia | DOM ID | Tipo | Valores |
|---|---|---|---|
| `nome` | `nome` | text | string (ex: "ÚLTIMA REMUNERAÇÃO", "SALÁRIO REGISTRADO") |
| `parcela` | `tipoVariacaoDaParcela:0/1` | radio | FIXA / VARIAVEL |
| `incidencia_fgts` | `fgts` | checkbox | on |
| `incidencia_cs` | `inss` | checkbox | on |
| `competencia_inicial` | `competenciaInicialInputDate` | text | MM/YYYY |
| `competencia_final` | `competenciaFinalInputDate` | text | MM/YYYY |
| `tipo_valor` | `tipoValor:0/1` | radio | INFORMADO / CALCULADO |
| `valor` | `valorParaBaseDeCalculo` | text | valor base (R$) — quando tipo_valor=INFORMADO |

### Botões
| Função | DOM ID |
|---|---|
| Salvar | `salvar` |
| Cancelar | `cancelar` |

## Notas

⚠️ **Note**: os IDs aqui NÃO têm prefixo `formulario:` quando inspecionados (ex: `nome`,
não `formulario:nome`). Entretanto, no DOM real os elementos estão dentro do
`<form id="formulario">` então o name segue padrão `formulario:nome`. A automação
atual usa selectors `[id$='nome']` que cobrem ambos os casos.

## Estratégia para a prévia

```json
"historico_salarial": [
  {
    "nome": "ÚLTIMA REMUNERAÇÃO",
    "parcela": "FIXA",
    "incidencia_fgts": true,
    "incidencia_cs": true,
    "competencia_inicial": "09/2020",
    "competencia_final": "04/2025",
    "tipo_valor": "INFORMADO",
    "valor": 1702.14
  },
  {
    "nome": "SALÁRIO PAGO POR FORA",
    "parcela": "FIXA",
    "incidencia_fgts": true,
    "incidencia_cs": true,
    "competencia_inicial": "09/2020",
    "competencia_final": "04/2025",
    "tipo_valor": "INFORMADO",
    "valor": 997.86
  }
]
```

A IA de extração deve identificar:
1. Há **um único valor** em todo o período? → 1 entrada com `tipo_valor=INFORMADO`
2. Há **diferentes valores ao longo do tempo** (evolução salarial)?
   → múltiplas entradas com `competencia_inicial`/`final` segmentadas
3. Existe **salário pago "por fora"** (parte não registrada)?
   → 2 entradas: uma "REGISTRADO" e outra "POR FORA"
4. Sentença determina **diferença salarial** com base em piso normativo?
   → 1 entrada "PISO CATEGORIA" + 1 entrada "REGISTRADO"

⚠️ **CRÍTICO**: o histórico salarial deve cobrir **todo o período do cálculo**
(do início ao termo), não apenas até a rescisão. Quando há indenizações pós-contrato
(estabilidade gestante, dispensa discriminatória), o histórico deve continuar com
`ÚLTIMA REMUNERAÇÃO` para os meses pós-rescisão. Sem isso, a CS sobre os meses
pós-contrato fica sem base de cálculo.
