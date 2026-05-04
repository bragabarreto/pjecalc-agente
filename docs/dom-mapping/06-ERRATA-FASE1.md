# Errata e Complementos — Fase 1

Após revisão preventiva (verificações adicionais via Chrome MCP), foram identificados
erros e omissões nos docs originais. Esta errata é a **fonte definitiva** —
prevalece sobre qualquer divergência nos demais arquivos.

## ❌ Erro 1 — Opções de `formulario:tipoDaBaseTabelada`

**No doc 01** estava: `(HISTORICO_SALARIAL, MAIOR_REMUNERACAO, ULTIMA_REMUNERACAO, INTEGRAL, etc.)`

**CORRETO** (6 opções, verificadas no DOM):
```
(vazio — placeholder Seam)
MAIOR_REMUNERACAO       — "Maior Remuneração"
HISTORICO_SALARIAL      — "Histórico Salarial"
SALARIO_DA_CATEGORIA    — "Piso Salarial"
SALARIO_MINIMO          — "Salário Mínimo"
VALE_TRANSPORTE         — "Vale Transporte"
```

⚠️ **NÃO existe `ULTIMA_REMUNERACAO`** como opção de `tipoDaBaseTabelada`.
Para usar a "ÚLTIMA REMUNERAÇÃO" como base, deve-se selecionar
`HISTORICO_SALARIAL` e depois escolher o histórico chamado "ÚLTIMA REMUNERAÇÃO"
no select dinâmico que aparece (`formulario:baseHistoricos`).

⚠️ **NÃO existe `INTEGRAL`** — havia confusão com o select `integralizarBase` (Sim/Não).

## ➕ Omissão 1 — Sub-select dinâmico `formulario:baseHistoricos`

Quando `tipoDaBaseTabelada=HISTORICO_SALARIAL`, aparece sub-select com a lista
**dos históricos efetivamente cadastrados** no cálculo:

| Campo Prévia | DOM ID | Tipo | Valores |
|---|---|---|---|
| `base_historico_nome` | `formulario:baseHistoricos` | select | (referência ao nome do histórico) |
| `proporcionaliza_historico` | `formulario:proporcionalizaHistorico` | select | SIM / NAO |

**Exemplo de options** (cálculo com 4 históricos cadastrados):
```
v="" t=""                                  (placeholder)
v="12" t="ADICIONAL DE INSALUBRIDADE PAGO"
v="13" t="GRATIFICACAO HABITUAL"
v="14" t="SALÁRIO BASE"
v="15" t="ÚLTIMA REMUNERAÇÃO"
```

⚠️ Os valores `v` são IDs internos do PJE-Calc — o que importa para o agente é o
**texto** do option (nome do histórico). A automação deve selecionar pelo texto.

## ➕ Omissão 2 — Botão "Adicionar Base" (`formulario:incluirBaseHistorico`)

Logo após o select `baseHistoricos`, há um ícone "+" verde:

```
formulario:incluirBaseHistorico  (anchor com title="Adicionar Base")
```

**Quando usar**: para adicionar **múltiplos históricos** como base composta da
fórmula (ex: "ÚLTIMA REMUNERAÇÃO" + "GRATIFICAÇÃO HABITUAL" somadas).

A automação atual já trata isso em `_adicionar_base_calculo_completa` no
`playwright_pjecalc.py`. Manter referência neste mapeamento.

## ❌ Erro 2 — `aplicarProporcionalidadeABase` é select, não checkbox

**No doc 01** estava classificado como `checkbox`.

**CORRETO**: na verdade é um **select** (`formulario:proporcionalizaHistorico` quando
HISTORICO_SALARIAL, ou checkbox `aplicarProporcionalidadeABase` em outros casos —
**a verificar** se existem dois nomes ou se foi confusão de versão).

⚠️ **Recomendação**: nas verificações da Fase 5, tratar `proporcionalizar_base`
como uma string `"SIM"|"NAO"` na prévia (compatível com select), e a automação
detecta o tipo do elemento e adapta (radio vs checkbox vs select).

## ➕ Omissão 3 — Modal "Selecionar Assuntos CNJ"

Botão observado mas não documentado:

```
btnSelecionarCNJ  (input button — abre modal de busca de Assuntos CNJ)
```

**Localização**: ao lado do campo `formulario:assuntosCnj`.

**Função**: abre dialog modal com tree-view dos Assuntos CNJ. O usuário busca
e seleciona; ao confirmar, o sistema preenche `formulario:codigoAssuntosCnj`
(número CNJ) + `formulario:assuntosCnj` (label).

⚠️ **Para automação**: preencher os dois campos diretamente via JS,
sem precisar abrir o modal. Já tratado pelo agente atual.

## ➕ Omissão 4 — Comportamento dinâmico dos demais radios

A revisão original só cobriu `valor:0/1`. Outros radios também alteram o DOM:

### `tipoVariacaoDaParcela=VARIAVEL`
- A verificar: campos adicionais para tabela de variações? (não testado)

### `tipoDaQuantidade != INFORMADA`
- Quando `IMPORTADA_DO_CALENDARIO`: campo `valorInformadoDaQuantidade` é desabilitado.
- Quando `IMPORTADA_DO_CARTAO`: campo `valorInformadoDaQuantidade` desabilitado +
  acrescenta input para qual cartão (a verificar).

### `tipoDeDivisor != OUTRO_VALOR`
- `outroValorDoDivisor` é desabilitado quando outro tipo escolhido.

### `tipoDoValorPago=CALCULADO`
- `valorInformadoPago` é desabilitado.

### `tipoDeVerba=REFLEXO`
- `geraReflexo` é desabilitado (faz sentido: se já é reflexo, não gera reflexo de reflexo).
- Pode aparecer campo "Verba Principal Vinculada" (`baseVerbaDeCalculo` torna-se obrigatório).

⚠️ **Para a Fase 4**: a UI da prévia deve adaptar visibilidade de campos
exatamente como o PJE-Calc faz, para refletir os mesmos shapes de dados
que o backend aceita. Validador inline deve seguir essas mesmas regras.

## ❌ Erro 3 — Reflexos no painel "Exibir/Ocultar"

**No doc 04** afirmei que era preciso clicar "Exibir" antes de marcar reflexos.

**CORRETO** (verificado): os checkboxes `formulario:listagem:N:listaReflexo:M:ativo`
**estão sempre presentes no DOM**, mesmo quando o painel parece "oculto" visualmente
(é apenas CSS `display:none`). O agente pode marcar diretamente via JS sem
precisar clicar "Exibir" primeiro.

⚠️ **Implicação**: o link "Exibir" / "Ocultar" é puramente visual (UX). A
automação não precisa interagir com ele.

## ➕ Omissão 5 — Múltiplas competências no Histórico Salarial (Calculado)

No doc 05 falei de "evolução salarial" mas não documentei como cadastrar
múltiplas bases dentro de UM ÚNICO histórico (modo `tipoValor=CALCULADO`).

Quando `tipoValor=CALCULADO`, aparece estrutura:
- Botão "+" para adicionar base
- Cada base tem: percentual + nome de outra verba/histórico

**Exemplo de uso**: histórico "REMUNERAÇÃO TOTAL" calculado como
"100% SALÁRIO BASE + 30% GRATIFICAÇÃO".

⚠️ **Para a Fase 2**: o schema do histórico precisa de:
```json
{
  "tipo_valor": "CALCULADO",
  "bases_calculadas": [
    {"percentual": 100, "referencia": "SALÁRIO BASE"},
    {"percentual": 30, "referencia": "GRATIFICAÇÃO HABITUAL"}
  ]
}
```

Quando `tipo_valor=INFORMADO`, mantém o formato atual com `valor` único.

## ➕ Omissão 6 — Cabeçalho `j_id85_input` na página Ocorrências

No doc 03 listei vários IDs mas não classifiquei `formulario:j_id85_input` (hidden input).

**Função**: é o input hidden do RichFaces InputDate para a "Data Inicial" do
header de Alteração em Lote. Sem importância para o agente — basta preencher
`formulario:dataInicialInputDate` (visível) e o RichFaces sincroniza.

## Resumo da revisão

| Item | Tipo | Severidade | Localização |
|---|---|---|---|
| 1 | Erro | 🔴 Alta | `01-verba-manual-novo.md` linha 94 |
| 1 (sub-select) | Omissão | 🔴 Alta | `01-verba-manual-novo.md` |
| 2 (botão +) | Omissão | 🟡 Média | `01-verba-manual-novo.md` |
| 2 (proporcionalidade) | Erro | 🟡 Média | `01-verba-manual-novo.md` linha 95 |
| 3 (modal CNJ) | Omissão | 🟢 Baixa | `01-verba-manual-novo.md` |
| 4 (radios dinâmicos) | Omissão | 🟡 Média | `01-verba-manual-novo.md` |
| 3 (Exibir reflexos) | Erro | 🟢 Baixa | `04-reflexos-painel.md` |
| 5 (CALCULADO) | Omissão | 🟡 Média | `05-historico-salarial.md` |
| 6 (j_id85) | Esclarecimento | 🟢 Baixa | `03-ocorrencias-verba.md` |

**Conclusão**: Fase 1 fica oficialmente concluída APENAS com esta errata aplicada.
Os docs 01-05 servem como referência geral; este 06 prevalece em conflitos.
