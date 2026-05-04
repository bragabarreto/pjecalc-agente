# DOM Mapping — Painel de Reflexos (na listagem)

**URL**: `/pjecalc/pages/calculo/verba/verba-calculo.jsf` (listagem de verbas)  
**Acesso**: clicar no botão "Exibir" / "Ocultar" da última coluna ("Verba Reflexa")
de cada linha de verba principal.

## Estrutura

Cada verba principal tem um conjunto de reflexos pré-cadastrados pelo PJE-Calc.
Os checkboxes de cada reflexo seguem o padrão:
```
formulario:listagem:N:listaReflexo:M:ativo
```
- N = índice da verba principal na listagem (0..total-1)
- M = índice do reflexo na lista da verba principal (0..N_reflexos-1)

## Exemplos observados (verba ADICIONAL DE INSALUBRIDADE 20%, N=0)

| Reflexo | DOM ID |
|---|---|
| AVISO PRÉVIO SOBRE ADICIONAL DE INSALUBRIDADE 20% | `formulario:listagem:0:listaReflexo:0:ativo` |
| FÉRIAS + 1/3 SOBRE ADICIONAL DE INSALUBRIDADE 20% | `formulario:listagem:0:listaReflexo:1:ativo` |
| MULTA 477 SOBRE ADICIONAL DE INSALUBRIDADE 20% | `formulario:listagem:0:listaReflexo:2:ativo` |
| 13º SALÁRIO SOBRE ADICIONAL DE INSALUBRIDADE 20% | `formulario:listagem:0:listaReflexo:3:ativo` |

## Reflexos típicos por categoria de verba principal

### Adicionais (Insalubridade, Periculosidade, Noturno, Risco, Sobreaviso, etc.)
- AVISO PRÉVIO sobre X
- FÉRIAS + 1/3 sobre X
- MULTA 477 sobre X
- 13º SALÁRIO sobre X
- (alguns: REPOUSO SEMANAL REMUNERADO E FERIADO sobre X — quando aplicável)

### HORAS EXTRAS / HORAS IN ITINERE
- AVISO PRÉVIO sobre X
- FÉRIAS + 1/3 sobre X
- MULTA 477 sobre X
- 13º SALÁRIO sobre X
- REPOUSO SEMANAL REMUNERADO E FERIADO sobre X

### COMISSÃO / GORJETA / DIÁRIAS-INTEGRAÇÃO
- Mesmo padrão (varia)

### DIFERENÇA SALARIAL
- AVISO PRÉVIO sobre DIFERENÇA SALARIAL
- FÉRIAS + 1/3 sobre DIFERENÇA SALARIAL
- MULTA 477 sobre DIFERENÇA SALARIAL
- 13º SALÁRIO sobre DIFERENÇA SALARIAL

## Estratégia para a prévia

Para cada verba principal, a prévia deve listar os reflexos com:
```json
{
  "verba_principal_nome": "DIFERENÇA SALARIAL",
  "reflexos": [
    {
      "nome": "Aviso Prévio sobre Diferença Salarial",
      "estrategia_reflexa": "checkbox_painel",  // ← marcar formulario:listagem:N:listaReflexo:0:ativo
      "indice_reflexo_listagem": 0
    },
    {
      "nome": "Férias + 1/3 sobre Diferença Salarial",
      "estrategia_reflexa": "checkbox_painel",
      "indice_reflexo_listagem": 1
    }
  ]
}
```

**`estrategia_reflexa`**:
- `checkbox_painel` — marca o checkbox no painel da verba principal (preferência)
- `manual` — cria como verba Manual independente (raro, quando o reflexo não
  aparece automaticamente no painel — ex: reflexo sobre adicional adaptado)

## Limitação importante
O PJE-Calc **só pré-cadastra alguns reflexos** por verba. Se a sentença determina
um reflexo NÃO presente no painel (ex: "Multa do art. 467 sobre Indenização Adicional"),
ele deve ser criado como verba Manual independente — a prévia deve detectar isso e
marcar `estrategia_reflexa: "manual"`.
