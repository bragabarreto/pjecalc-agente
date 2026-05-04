# Schema — FGTS, INSS, IRPF

## 8. FGTS

**Mapeia para**: `fgts.jsf` + `parametrizar-fgts.jsf`

```json
{
  "fgts": {
    "tipo_verba": "PAGAR",
    "compor_principal": "SIM",
    "multa": {
      "ativa": true,
      "tipo_valor": "CALCULADA",
      "percentual": "QUARENTA_POR_CENTO",
      "excluir_aviso_da_multa": false,
      "valor_informado_brl": null
    },
    "incidencia": "SOBRE_O_TOTAL_DEVIDO",
    "multa_artigo_467": false,
    "multa_10_lc110": false,
    "contribuicao_social": false,
    "incidencia_pensao_alimenticia": false,
    "recolhimentos_existentes": [
      {
        "data_inicio": null,
        "data_fim": null,
        "aliquota": "OITO_POR_CENTO",
        "deduzir_do_fgts": false,
        "competencia": null,
        "valor_brl": null
      }
    ]
  }
}
```

| Campo | DOM ID | Enum |
|---|---|---|
| `tipo_verba` | `formulario:tipoDeVerba` | PAGAR / DEPOSITAR |
| `compor_principal` | `formulario:comporPrincipal` | SIM / NAO |
| `multa.tipo_valor` | `formulario:tipoDoValorDaMulta` | CALCULADA / INFORMADA |
| `multa.percentual` | `formulario:multaDoFgts` | VINTE_POR_CENTO / **QUARENTA_POR_CENTO** |
| `incidencia` | `formulario:incidenciaDoFgts` | **SOBRE_O_TOTAL_DEVIDO** / SOBRE_DEPOSITADO_SACADO / SOBRE_DIFERENCA / SOBRE_TOTAL_DEVIDO_MAIS_SAQUE_E_OU_SALDO / SOBRE_TOTAL_DEVIDO_MENOS_SAQUE_E_OU_SALDO |
| `multa_artigo_467` | `formulario:multaDoArtigo467` | bool |
| `recolhimentos_existentes[].aliquota` | `formulario:aliquota` | DOIS_POR_CENTO / **OITO_POR_CENTO** |

## 9. Contribuição Social (INSS)

**Mapeia para**: `inss/inss.jsf` + `inss/parametrizar-inss.jsf`

```json
{
  "contribuicao_social": {
    "apurar_segurado_devido": true,
    "cobrar_do_reclamante_devido": false,
    "corrigir_desconto_reclamante": true,
    "apurar_salarios_pagos": true,
    "aliquota_segurado": "SEGURADO_EMPREGADO",
    "aliquota_empregador": "POR_ATIVIDADE_ECONOMICA",
    "aliquota_empresa_fixa_pct": null,
    "aliquota_rat_fixa_pct": null,
    "aliquota_terceiros_fixa_pct": null,
    "periodo_devidos": {
      "inicio": null,
      "fim": null
    },
    "periodo_pagos": {
      "inicio": null,
      "fim": null
    }
  }
}
```

| Campo | DOM ID | Enum |
|---|---|---|
| `aliquota_segurado` | `formulario:aliquotaEmpregado` | **SEGURADO_EMPREGADO** / EMPREGADO_DOMESTICO / FIXA |
| `aliquota_empregador` | `formulario:aliquotaEmpregador` | **POR_ATIVIDADE_ECONOMICA** / POR_PERIODO / FIXA |

## 10. Imposto de Renda (IRPF)

**Mapeia para**: `irpf.jsf`

```json
{
  "imposto_de_renda": {
    "apurar_irpf": true,
    "incidir_sobre_juros_de_mora": false,
    "cobrar_do_reclamado": false,
    "considerar_tributacao_exclusiva": false,
    "considerar_tributacao_em_separado_rra": true,
    "regime_de_caixa": false,
    "deducoes": {
      "contribuicao_social": true,
      "previdencia_privada": false,
      "pensao_alimenticia": false,
      "honorarios_devidos_pelo_reclamante": true
    },
    "aposentado_maior_65_anos": false,
    "possui_dependentes": false,
    "quantidade_dependentes": 0
  }
}
```

| Campo | DOM ID | Tipo | Notas |
|---|---|---|---|
| `apurar_irpf` | `formulario:apurarImpostoRenda` | bool | |
| `considerar_tributacao_em_separado_rra` | `formulario:considerarTributacaoEmSeparado` | bool | RRA = Rendimentos Recebidos Acumuladamente — geralmente true em ações trabalhistas |
| `quantidade_dependentes` | `formulario:quantidadeDependentes` | int | só preenche se `possui_dependentes=true` |
