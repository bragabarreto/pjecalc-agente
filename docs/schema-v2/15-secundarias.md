# Schema — Páginas Secundárias (Etapa 2)

Todas estas seções são **opcionais**. Quando a sentença não menciona, valor `null`.

## 15. Salário-Família

```json
{
  "salario_familia": {
    "apurar": true,
    "compor_principal": "SIM",
    "data_inicial": "01/04/2025",
    "data_final": "01/04/2025",
    "qtd_filhos_menores_14": 2,
    "variacoes": [
      {"data_inicial": "01/01/2026", "qtd_filhos": 1}
    ],
    "tipo_salario_pago": "HISTORICO_SALARIAL",
    "historicos_salariais": ["ÚLTIMA REMUNERAÇÃO"],
    "verbas_compor_base": [
      {"verba": "ADICIONAL DE INSALUBRIDADE 20%", "integralizar": "SIM"}
    ]
  }
}
```

| Campo | DOM ID | Enum |
|---|---|---|
| `tipo_salario_pago` | `formulario:tipoSalarioPago` | NENHUM / MAIOR_REMUNERACAO / HISTORICO_SALARIAL |

## 16. Seguro-Desemprego

```json
{
  "seguro_desemprego": {
    "apurar": true,
    "apurar_empregado_domestico": false,
    "solicitacao": null,
    "valor": "CALCULADO",
    "compor_principal": "SIM",
    "numero_de_parcelas": 5,
    "tipo_salario_pago": "MAIOR_REMUNERACAO",
    "historicos_salariais": [],
    "verbas_compor_base": []
  }
}
```

## 17. Previdência Privada

```json
{
  "previdencia_privada": {
    "apurar": true,
    "aliquotas": [
      {
        "data_inicio": "01/01/2024",
        "data_fim": "01/04/2025",
        "aliquota_pct": 8.00
      }
    ]
  }
}
```

## 18. Pensão Alimentícia

```json
{
  "pensao_alimenticia": {
    "apurar": true,
    "aliquota_pct": 30.00,
    "incidir_sobre_juros": false
  }
}
```

## 19. Multas e Indenizações Avulsas

⚠️ **Não confundir** com a "Multa do art. 477 da CLT" que é uma verba Expresso.
Esta seção trata multas convencionais, multas contratuais, cláusula penal.

```json
{
  "multas_indenizacoes": [
    {
      "id": "mi01",
      "descricao": "Multa convencional Cláusula 50ª da CCT",
      "credor_devedor": "RECLAMADO_RECLAMANTE",
      "valor": "INFORMADO",
      "tipo_base_multa": "PRINCIPAL",
      "aliquota_pct": null,
      "valor_informado_brl": 1500.00
    }
  ]
}
```

| Campo | DOM ID | Enum |
|---|---|---|
| `credor_devedor` | `formulario:credorDevedor` | RECLAMANTE_RECLAMADO / **RECLAMADO_RECLAMANTE** / TERCEIRO_RECLAMANTE / TERCEIRO_RECLAMADO |
| `valor` | `formulario:valor` | INFORMADO / CALCULADO |
| `tipo_base_multa` | `formulario:tipoBaseMulta` | PRINCIPAL / PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL / PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA / VALOR_CAUSA |
