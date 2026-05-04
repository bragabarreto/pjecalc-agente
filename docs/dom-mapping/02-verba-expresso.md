# DOM Mapping — Lançamento Expresso

**URL**: `/pjecalc/pages/calculo/verba/verbas-para-calculo.jsf`  
**Caminho**: Cálculo > Verbas > Lançamento Expresso

## Layout

Tabela 25 linhas × 3 colunas (8 entradas na última coluna). Cada checkbox tem ID:
```
formulario:j_id82:LINHA:j_id84:COLUNA:selecionada
```

⚠️ **Atenção**: o **prefixo numérico** `j_id82` e `j_id84` é dinâmico — pode mudar
entre versões. Sempre buscar por `[id$=':selecionada']` filtrando pelo texto do label.

## Lista canônica de verbas Expresso (54 itens)

```
13º SALÁRIO
ABONO PECUNIÁRIO
ACORDO (MERA LIBERALIDADE)
ACORDO (MULTA)
ACORDO (VERBAS INDENIZATÓRIAS)
ACORDO (VERBAS REMUNERATÓRIAS)
ADICIONAL DE HORAS EXTRAS 50%
ADICIONAL DE INSALUBRIDADE 10%
ADICIONAL DE INSALUBRIDADE 20%
ADICIONAL DE INSALUBRIDADE 40%
ADICIONAL DE PERICULOSIDADE 30%
ADICIONAL DE PRODUTIVIDADE 30%
ADICIONAL DE RISCO 40%
ADICIONAL DE SOBREAVISO
ADICIONAL DE TRANSFERÊNCIA 25%
ADICIONAL NOTURNO 20%
AJUDA DE CUSTO
AVISO PRÉVIO
CESTA BÁSICA
COMISSÃO
DEVOLUÇÃO DE DESCONTOS INDEVIDOS
DIFERENÇA SALARIAL
DIÁRIAS - INTEGRAÇÃO AO SALÁRIO
DIÁRIAS - PAGAMENTO
FERIADO EM DOBRO
FÉRIAS + 1/3
GORJETA
GRATIFICAÇÃO DE FUNÇÃO
GRATIFICAÇÃO POR TEMPO DE SERVIÇO
HORAS EXTRAS 100%
HORAS EXTRAS 50%
HORAS IN ITINERE
INDENIZAÇÃO ADICIONAL
INDENIZAÇÃO PIS - ABONO SALARIAL
INDENIZAÇÃO POR DANO ESTÉTICO
INDENIZAÇÃO POR DANO MATERIAL
INDENIZAÇÃO POR DANO MORAL
INTERVALO INTERJORNADAS
INTERVALO INTRAJORNADA
MULTA CONVENCIONAL
MULTA DO ARTIGO 477 DA CLT
PARTICIPAÇÃO NOS LUCROS OU RESULTADOS - PLR
PRÊMIO PRODUÇÃO
REPOUSO SEMANAL REMUNERADO (COMISSIONISTA)
REPOUSO SEMANAL REMUNERADO EM DOBRO
RESTITUIÇÃO / INDENIZAÇÃO DE DESPESA
SALDO DE EMPREITADA
SALDO DE SALÁRIO
SALÁRIO MATERNIDADE
SALÁRIO RETIDO
TÍQUETE-ALIMENTAÇÃO
VALE TRANSPORTE
VALOR PAGO - NÃO TRIBUTÁVEL
VALOR PAGO - TRIBUTÁVEL
```

## Botões
| Função | DOM ID | Tipo |
|---|---|---|
| Salvar | `formulario:salvar` | input button |
| Cancelar | `formulario:cancelar` | input button |

## Estratégia de Preenchimento (para nossa prévia)

Ao classificar uma verba da sentença, há 3 estratégias:

### 1. `expresso_direto`
A verba da sentença existe **literal ou semanticamente** no rol acima.

| Verba sentença | Verba Expresso (alvo) |
|---|---|
| "13º Salário Proporcional" | `13º SALÁRIO` |
| "Férias Vencidas + 1/3" | `FÉRIAS + 1/3` |
| "Diferença salarial entre real e CTPS" | `DIFERENÇA SALARIAL` |
| "Multa do art. 477" | `MULTA DO ARTIGO 477 DA CLT` |
| "Indenização por dano moral" | `INDENIZAÇÃO POR DANO MORAL` |
| "Horas extras 50%" | `HORAS EXTRAS 50%` |

### 2. `expresso_adaptado`
A verba não existe no rol Expresso, mas pode-se selecionar uma similar e
**adaptar nome/parâmetros** após o Expresso, via página de Parâmetros da Verba.

Exemplo: "Estabilidade Gestante" → selecionar `INDENIZAÇÃO ADICIONAL` no Expresso,
depois ajustar nome em Parâmetros para "Estabilidade Gestante - Lei 8.213/91".

### 3. `manual`
A verba é tão específica que nem adaptação resolve. Usar botão Manual e preencher
todos campos do formulário "Dados de Verba" (ver `01-verba-manual-novo.md`).

## Recomendação para a prévia

A prévia DEVE conter para cada verba principal:
```json
{
  "estrategia_preenchimento": "expresso_direto" | "expresso_adaptado" | "manual",
  "expresso_alvo": "INDENIZAÇÃO POR DANO MORAL",  // exigido p/ direto e adaptado
  "nome_pjecalc": "INDENIZAÇÃO POR DANO MORAL",   // após adaptação se for o caso
  ...
}
```

A IA de extração JÁ deve identificar o `expresso_alvo` correto consultando este rol.
