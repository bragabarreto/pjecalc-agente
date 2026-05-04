# Schema — Faltas e Férias

## 6. Faltas

**Mapeia para**: `falta.jsf`

```json
{
  "faltas": [
    {
      "data_inicio": "15/03/2024",
      "data_fim": "20/03/2024",
      "justificada": true,
      "reinicia_ferias": false,
      "justificativa": "Atestado médico"
    }
  ]
}
```

| Campo | DOM ID | Tipo | Notas |
|---|---|---|---|
| `data_inicio` | `formulario:dataInicioPeriodoFaltaInputDate` | date_br | |
| `data_fim` | `formulario:dataTerminoPeriodoFaltaInputDate` | date_br | |
| `justificada` | `formulario:faltaJustificada` | bool | |
| `reinicia_ferias` | `formulario:reiniciaFerias` | bool | |
| `justificativa` | `formulario:justificativaDaFalta` | string | |

A automação usa `formulario:cmdIncluirFalta` (anchor +) para adicionar cada falta.

## 7. Férias

**Mapeia para**: `ferias.jsf`

```json
{
  "ferias": [
    {
      "periodo_aquisitivo_inicio": "22/11/2024",
      "periodo_aquisitivo_fim": "21/11/2025",
      "periodo_concessivo_inicio": "22/11/2025",
      "periodo_concessivo_fim": "22/11/2026",
      "prazo_dias": 30,
      "situacao": "INDENIZADAS",
      "dobra": false,
      "abono": false,
      "dias_abono": 10,
      "gozo_1": {
        "data_inicio": null,
        "data_fim": null,
        "dobra": false
      },
      "gozo_2": {
        "data_inicio": null,
        "data_fim": null,
        "dobra": false
      },
      "gozo_3": null
    }
  ],
  "ferias_coletivas_inicio_primeiro_ano": null,
  "prazo_ferias_proporcionais": null
}
```

| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `ferias[].situacao` | (select por linha) | enum | INDENIZADAS / GOZADAS / PARCIAL_GOZADAS / NAO_DIREITO |
| `ferias[].prazo_dias` | (input por linha) | int | 30 / 24 / 18 / 12 / 6 |
| `ferias[].dias_abono` | (input por linha) | int | 0..10 (1/3 de prazo) |
| `ferias_coletivas_inicio_primeiro_ano` | `formulario:inicioFeriasColetivasInputDate` | date_br | nullable |
| `prazo_ferias_proporcionais` | `formulario:prazoFeriasProporcionais` | int | **OPCIONAL** — null = usa default do PJE-Calc baseado em jornada+faltas |

⚠️ **Tooltip do `prazo_ferias_proporcionais`** (capturado empiricamente):
> "Preencha esse campo somente se deseja informar um valor de prazo de férias
> proporcionais. Se desejar utilizar o valor padrão, que depende do regime de
> trabalho e do número de faltas não justificadas, mantenha o campo em branco."

## Validações

1. `data_inicio` < `data_fim` em todos os períodos
2. `periodo_aquisitivo_fim` ≤ `data_demissao` (caso encerrado) ou `data_termino_calculo` (caso vincendo)
3. Se `situacao == GOZADAS` ou `PARCIAL_GOZADAS` → pelo menos `gozo_1.data_inicio` preenchido
4. Se `dobra == true` → indica férias dobradas (art. 137 CLT)
5. `dias_abono` máximo = ⌊prazo_dias / 3⌋
