# Schema — Parâmetros do Cálculo

**Mapeia para**: aba "Parâmetros do Cálculo" da página `calculo.jsf`

```json
{
  "parametros_calculo": {
    "estado_uf": "CE",
    "municipio": "FORTALEZA",

    "data_admissao": "02/09/2013",
    "data_demissao": "01/04/2025",
    "data_ajuizamento": "25/09/2025",
    "data_inicio_calculo": "25/09/2020",
    "data_termino_calculo": "01/04/2025",

    "prescricao_quinquenal": true,
    "prescricao_fgts": false,

    "tipo_base_tabelada": "INTEGRAL",
    "valor_maior_remuneracao_brl": 2700.00,
    "valor_ultima_remuneracao_brl": 2700.00,

    "apuracao_aviso_previo": "APURACAO_CALCULADA",
    "projeta_aviso_indenizado": true,
    "limitar_avos": false,
    "zerar_valor_negativo": true,

    "considerar_feriado_estadual": true,
    "considerar_feriado_municipal": true,

    "carga_horaria": {
      "padrao_mensal": 220.00,
      "excecoes": [
        {
          "data_inicio": "01/01/2024",
          "data_fim": "30/06/2024",
          "valor_carga_horaria": 200.00
        }
      ]
    },

    "sabado_dia_util": false,
    "excecoes_sabado": [
      {
        "data_inicio": "01/12/2024",
        "data_fim": "31/12/2024"
      }
    ],

    "pontos_facultativos_codigo": [211, 212, 213],

    "comentarios_jg": null
  }
}
```

## Campos

| Campo prévia | DOM ID | Tipo | Obrig | Default | Notas |
|---|---|---|---|---|---|
| `estado_uf` | `formulario:estado` | string UF | ✅ | (do processo) | "CE", "SP", etc. |
| `municipio` | `formulario:municipio` | string | ✅ | — | UPPER, ASCII, sem acentos |
| `data_admissao` | `formulario:dataAdmissaoInputDate` | date_br | ✅ | — | |
| `data_demissao` | `formulario:dataDemissaoInputDate` | date_br | ✅ | — | |
| `data_ajuizamento` | `formulario:dataAjuizamentoInputDate` | date_br | ✅ | — | |
| `data_inicio_calculo` | `formulario:dataInicioCalculoInputDate` | date_br | ✅ | (calculado) | usualmente data ajuizamento - 5 anos |
| `data_termino_calculo` | `formulario:dataTerminoCalculoInputDate` | date_br | ✅ | — | DEVE cobrir todas verbas (incluso indenizações pós-rescisão) |
| `prescricao_quinquenal` | `formulario:prescricaoQuinquenal` | bool | ❌ | true | |
| `prescricao_fgts` | `formulario:prescricaoFgts` | bool | ❌ | false | |
| `tipo_base_tabelada` | `formulario:tipoDaBaseTabelada` | enum | ❌ | INTEGRAL | INTEGRAL / PARCIAL / INTERMITENTE |
| `valor_maior_remuneracao_brl` | `formulario:valorMaiorRemuneracao` | money_br | ✅ | — | maior remuneração do período |
| `valor_ultima_remuneracao_brl` | `formulario:valorUltimaRemuneracao` | money_br | ✅ | — | última remuneração antes da rescisão |
| `apuracao_aviso_previo` | `formulario:apuracaoPrazoDoAvisoPrevio` | enum | ✅ | (depende) | NAO_APURAR / APURACAO_CALCULADA / APURACAO_INFORMADA |
| `projeta_aviso_indenizado` | `formulario:projetaAvisoIndenizado` | bool | ❌ | true | quando aviso é indenizado |
| `limitar_avos` | `formulario:limitarAvos` | bool | ❌ | false | |
| `zerar_valor_negativo` | `formulario:zeraValorNegativo` | bool | ❌ | true | |
| `considerar_feriado_estadual` | `formulario:consideraFeriadoEstadual` | bool | ❌ | true | |
| `considerar_feriado_municipal` | `formulario:consideraFeriadoMunicipal` | bool | ❌ | true | |
| `carga_horaria.padrao_mensal` | `formulario:valorCargaHorariaPadrao` | number | ✅ | 220 | em horas |
| `carga_horaria.excecoes[].data_inicio` | `formulario:dataInicioExcecaoInputDate` + `incluirExcecaoCH` | date_br | ❌ | [] | |
| `carga_horaria.excecoes[].data_fim` | `formulario:dataTerminoExcecaoInputDate` | date_br | ❌ | — | |
| `carga_horaria.excecoes[].valor_carga_horaria` | `formulario:valorCargaHoraria` | number | ❌ | — | |
| `sabado_dia_util` | `formulario:sabadoDiaUtil` | bool | ❌ | false | |
| `excecoes_sabado[].data_inicio` | `formulario:dataInicioExcecaoSabadoInputDate` + `incluirExcecaoSab` | date_br | ❌ | [] | |
| `excecoes_sabado[].data_fim` | `formulario:dataTerminoExcecaoSabadoInputDate` | date_br | ❌ | — | |
| `pontos_facultativos_codigo[]` | `formulario:pontoFacultativo` + `cmdAdicionarPontoFacultativo` | int[] | ❌ | [] | códigos da tabela do PJE-Calc (ex: 211=Sexta Santa) |
| `comentarios_jg` | `formulario:comentarios` | string | ❌ | null | usado para anotar JG, observações |

## Validações cruzadas

1. `data_admissao` < `data_demissao` < `data_ajuizamento`
2. `data_inicio_calculo` ≥ `data_ajuizamento - 5 anos` (se prescrição quinquenal)
3. `data_termino_calculo` ≥ `data_demissao` (sempre)
4. `data_termino_calculo` ≥ `MAX(periodo_fim)` de todas as verbas (especialmente indenizações pós-rescisão)
5. `valor_maior_remuneracao_brl` ≥ `valor_ultima_remuneracao_brl` (logicamente)
6. Se `apuracao_aviso_previo == APURACAO_CALCULADA`, `projeta_aviso_indenizado` deve ser `true` para aviso indenizado SJC

## Default de `apuracao_aviso_previo`

| Tipo de rescisão | apuracao_aviso_previo |
|---|---|
| Sem justa causa, aviso INDENIZADO | `APURACAO_CALCULADA` (Lei 12.506/2011) |
| Sem justa causa, aviso TRABALHADO | `APURACAO_INFORMADA` (com data efetiva trabalhada) |
| Pedido de demissão / culpa recíproca | `NAO_APURAR` |
| Justa causa do empregado | `NAO_APURAR` |
| Rescisão indireta | `APURACAO_CALCULADA` |
