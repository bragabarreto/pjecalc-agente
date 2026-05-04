# Schema — Dados do Processo

**Mapeia para**: aba "Dados do Processo" da página `calculo.jsf`

```json
{
  "processo": {
    "numero_processo": "0000369-57.2026.5.07.0003",
    "valor_da_causa_brl": 79126.60,
    "data_autuacao": "17/03/2026",

    "reclamante": {
      "nome": "IRIS DE OLIVEIRA NOGUEIRA",
      "doc_fiscal": {
        "tipo": "CPF",
        "numero": "029.082.003-09"
      },
      "doc_previdenciario": {
        "tipo": "PIS",
        "numero": null
      },
      "advogados": [
        {
          "nome": "...",
          "oab": "12345/CE",
          "doc_fiscal_tipo": "CPF",
          "doc_fiscal_numero": "..."
        }
      ]
    },

    "reclamado": {
      "nome": "SOCIEDADE DE ASSISTÊNCIA E PROTEÇÃO À INFÂNCIA DE FORTALEZA",
      "doc_fiscal": {
        "tipo": "CNPJ",
        "numero": "07.253.784/0001-09"
      },
      "advogados": []
    }
  }
}
```

## Campos

| Campo prévia | DOM ID | Tipo | Obrig | Default | Validação |
|---|---|---|---|---|---|
| `numero_processo` | (split em `numero/digito/ano/justica/regiao/vara`) | string CNJ | ✅ | — | regex CNJ |
| `valor_da_causa_brl` | `formulario:valorDaCausa` | money_br | ✅ | — | > 0 |
| `data_autuacao` | `formulario:autuadoEm` | date_br | ✅ | — | válida |
| `reclamante.nome` | `formulario:reclamanteNome` | string | ✅ | — | não vazio |
| `reclamante.doc_fiscal.tipo` | `formulario:documentoFiscalReclamante` | enum CPF/CNPJ/CEI | ✅ | CPF | |
| `reclamante.doc_fiscal.numero` | `formulario:reclamanteNumeroDocumentoFiscal` | string | ✅ | — | regex por tipo |
| `reclamante.doc_previdenciario.tipo` | `formulario:reclamanteTipoDocumentoPrevidenciario` | enum PIS/PASEP/NIT | ❌ | PIS | |
| `reclamante.doc_previdenciario.numero` | `formulario:reclamanteNumeroDocumentoPrevidenciario` | string | ❌ | null | |
| `reclamante.advogados[].nome` | `formulario:nomeAdvogadoReclamante` (+ `incluirAdvogadoReclamante` para próximos) | string | ❌ | [] | |
| `reclamante.advogados[].oab` | `formulario:numeroOABAdvogadoReclamante` | string | ❌ | — | |
| `reclamado.nome` | `formulario:reclamadoNome` | string | ✅ | — | não vazio |
| `reclamado.doc_fiscal.tipo` | `formulario:tipoDocumentoFiscalReclamado` | enum CPF/CNPJ/CEI | ✅ | CNPJ | |
| `reclamado.doc_fiscal.numero` | `formulario:reclamadoNumeroDocumentoFiscal` | string | ✅ | — | regex por tipo |

## Decomposição do número CNJ

O JSF separa em 6 campos. A automação faz o split:

```
0000369-57.2026.5.07.0003
└──┬──┘ ┴┘ └┬─┘ ┴ └┬┘ └┬─┘
numero=369  ano  jus reg vara
       digito=57  =5  =07 =0003
```

A prévia armazena o número CNJ completo. A automação faz o split antes de
preencher cada DOM ID separado.
