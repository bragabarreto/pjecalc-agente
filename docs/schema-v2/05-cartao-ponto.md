# Schema — Cartão de Ponto

**Mapeia para**: `apuracao-cartaodeponto.jsf`

```json
{
  "cartao_de_ponto": {
    "data_inicial": "22/11/2024",
    "data_final": "15/03/2026",

    "apuracao": {
      "tipo": "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL",
      "qtd_sumula85_hhmm": "02:00",
      "qtd_hora_separado_hhmm": "02:00"
    },

    "extras_separados": {
      "considerar_feriado": true,
      "feriado_separado": false,
      "domingo_separado": false,
      "sabado_domingo_separado": false
    },

    "tolerancia": {
      "ativa": false,
      "por_turno_hhmm": "00:05",
      "por_dia_hhmm": "00:10"
    },

    "jornada_padrao": {
      "segunda_hhmm": "08:00",
      "terca_hhmm": "08:00",
      "quarta_hhmm": "08:00",
      "quinta_hhmm": "08:00",
      "sexta_hhmm": "08:00",
      "sabado_hhmm": "08:00",
      "domingo_hhmm": "00:00",
      "semanal_h": 44.0,
      "mensal_media_h": 188.57,
      "considerar_feriado_trabalhado": false,
      "considerar_feriado_nao_trabalhado": false
    },

    "descansos": {
      "apurar_feriados_trabalhados": false,
      "apurar_domingos_trabalhados": false,
      "apurar_sabados_domingos_trabalhados": false,
      "supressao_intervalo_art384": false,
      "supressao_intervalo_art72": false,
      "supressao_intervalo_art253": {
        "ativa": false,
        "valor_trabalho_hhmm": "01:40",
        "valor_descanso_hhmm": "00:20"
      },
      "intervalo_interjornadas": {
        "ativa": false,
        "entre_jornadas_h": 11,
        "entre_semanas_h": 35
      },
      "intra_jornada_4_a_6h": {
        "ativa": false,
        "valor_hhmm": "00:15"
      },
      "intra_jornada_acima_6h": {
        "ativa": false,
        "valor_hhmm": "01:00",
        "tolerancia_hhmm": "00:05"
      },
      "considerar_fracionamento_intra": false,
      "supressao_intra_integral": false,
      "supressao_intra_reforma": false,
      "excesso_intra_sumula118": {
        "ativo": false,
        "valor_max_hhmm": "02:00"
      },
      "apurar_apenas_excesso_jornada": false
    },

    "horario_noturno": {
      "atividade": "ATIVIDADE_URBANA",
      "apurar_horas_noturnas": false,
      "apurar_horas_extras_noturnas": false,
      "considerar_reducao_ficta": false,
      "horario_prorrogado_sumula60": false,
      "forcar_prorrogacao": false
    },

    "preenchimento": {
      "tipo": "PROGRAMACAO",
      "programacao_semanal": [
        {
          "dia_semana": "SEG",
          "turno1_inicio": "07:00",
          "turno1_fim": "12:00",
          "turno2_inicio": "13:00",
          "turno2_fim": "19:00"
        }
      ]
    }
  }
}
```

## Campos principais

Total: **63 campos** mapeados em `09-paginas-completas.md`. Os principais:

| Campo | DOM ID | Enum/Notas |
|---|---|---|
| `apuracao.tipo` | `formulario:tipoApuracaoHorasExtras` | NAO_APURAR / EXCEDENTES_DIARIA / **PELO_CRITERIO_MAIS_FAVORAVEL** / SUMULA_85 / APURA_PRIMEIRAS / EXCEDENTES_SEMANAL / EXCEDENTES_MENSAL |
| `horario_noturno.atividade` | `formulario:horarioNoturnoApuracaroCartao` | ATIVIDADE_AGRICOLA / ATIVIDADE_PECUARIA / **ATIVIDADE_URBANA** |
| `preenchimento.tipo` | `formulario:preenchimentoJornadasCartao` | LIVRE / **PROGRAMACAO** / ESCALA |
| `descansos.intervalo_interjornadas.entre_jornadas_h` | `formulario:valorDescansoEntreJornadas` (select) | 11 / 12 |

## Quando incluir

A prévia inclui `cartao_de_ponto` somente se a sentença determina apuração de
horas extras com base em jornada extraordinária. Se a sentença usa apuração
"informada" (quantidade fixa de HE/mês), `cartao_de_ponto = null`.
