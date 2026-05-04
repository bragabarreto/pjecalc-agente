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

## ❌ Erro 2 — Proporcionalidade depende do tipo de base (VERIFICADO)

**No doc 01** classificado como `checkbox` único.

**CORRETO** (verificado empiricamente no DOM):

| `tipoDaBaseTabelada` | Elemento de proporcionalidade |
|---|---|
| `SALARIO_MINIMO` | checkbox `formulario:aplicarProporcionalidadeABase` |
| `MAIOR_REMUNERACAO` | checkbox `formulario:aplicarProporcionalidadeABase` |
| `SALARIO_DA_CATEGORIA` (Piso) | checkbox `formulario:aplicarProporcionalidadeABase` |
| `VALE_TRANSPORTE` | checkbox `formulario:aplicarProporcionalidadeABase` |
| `HISTORICO_SALARIAL` | **select `formulario:proporcionalizaHistorico`** (SIM/NAO) — checkbox NÃO existe |

**Os dois NÃO coexistem**: ao alternar entre HISTORICO_SALARIAL e outros tipos,
o PJE-Calc remove um e cria o outro via AJAX RichFaces.

⚠️ **Recomendação para Fase 5**: na prévia, usar campo único `proporcionalizar_base`
como string `"SIM"|"NAO"` (compatível com ambos). A automação detecta o tipo do
elemento ativo (`querySelector('[id$=\"proporcionalizaHistorico\"]') || [id$=\"aplicarProporcionalidadeABase\"]`)
e adapta a operação.

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

## ➕ Omissão 4 — Comportamento dinâmico dos demais radios (VERIFICADO)

Verificações empíricas no formulário Parâmetros pós-Expresso (verba ADICIONAL DE INSALUBRIDADE 20%):

### `tipoVariacaoDaParcela=VARIAVEL`
✅ **Verificado**: NÃO altera o DOM visível. Lista de campos idêntica ao modo FIXA.
Conclusão: VARIAVEL é apenas um marcador semântico para o cálculo (não há
"tabela de variações" no DOM — pode haver lógica server-side que difere).

### `tipoDaQuantidade=IMPORTADA_DO_CALENDARIO`
✅ **Verificado**: o campo `formulario:valorInformadoDaQuantidade` é
**REMOVIDO completamente** do DOM (não apenas desabilitado), e o checkbox
`aplicarProporcionalidadeAQuantidade` também some.
Surge no lugar: `formulario:tipoImportadaCalendario` (select para escolher
qual calendário importar).

### `tipoDaQuantidade=IMPORTADA_DO_CARTAO`
A verificar empiricamente (não testado nesta sessão). Padrão similar
provável: surge `formulario:tipoImportadaCartao` (select).

### `tipoDeDivisor != OUTRO_VALOR`
A verificar empiricamente. Comportamento provável: `outroValorDoDivisor`
some/desabilita.

### `tipoDoValorPago=CALCULADO`
A verificar empiricamente.

### `tipoDeVerba=REFLEXO`
✅ **Verificado**: o campo `geraReflexo` **CONTINUA presente E habilitado**
(minha hipótese anterior estava errada — não é desabilitado).
Os outros campos permanecem inalterados.

⚠️ **Para a Fase 4**: a UI da prévia deve replicar o comportamento dinâmico
exato do PJE-Calc — quando um campo some no PJE-Calc, deve sumir na prévia
(não apenas desabilitar) para evitar dados inválidos no schema.

⚠️ **Para a Fase 5**: a automação precisa lidar com ELEMENTO INEXISTENTE
(não disabled) ao alternar tipos. Selectors devem usar `if (el)` defensivamente.

## ⚠️ Confirmação 3 — Reflexos no painel "Exibir/Ocultar" (REVISTA)

**REVISÃO** (após teste empírico definitivo na conversação 3770):

Os checkboxes `formulario:listagem:N:listaReflexo:M:ativo` **existem no DOM
mesmo com o painel oculto**, MAS:

| Cenário | Resultado |
|---|---|
| `cb.click()` com painel OCULTO (offsetParent=null) | ❌ `checked` permanece `false`; AJAX não é processado |
| `cb.click()` com painel ABERTO (após clicar Exibir) | ✅ `checked=true`, AJAX submetido, estado **persiste após reload** |

**Conclusão**: a automação **PRECISA expandir o painel** antes de marcar reflexos.

### Como expandir o painel
O link "Exibir" tem estrutura:
```html
<span id="formulario:listagem:N:divDestinacoes">
  <span class="linkDestinacoes linkDetalhe exibirItemNNNNNN">Exibir</span>
</span>
```

**Selector correto** para clicar:
```javascript
document.querySelector(`#formulario\\:listagem\\:${N}\\:divDestinacoes .linkDestinacoes`).click()
```
Ou mais robusto (não depende do número de classe):
```javascript
[...document.querySelectorAll('span.linkDestinacoes')]
  .find(s => s.closest('[id$=":divDestinacoes"]')?.id === `formulario:listagem:${N}:divDestinacoes`)
  .click()
```

### Fluxo correto no agente
1. Para cada verba principal N que tem reflexos a marcar:
   - Click `linkDestinacoes` da linha N (abre painel)
   - Aguardar AJAX (RichFaces atualiza visibilidade)
   - Para cada reflexo M a marcar: `cb.click()` no checkbox `formulario:listagem:N:listaReflexo:M:ativo`
   - Aguardar AJAX entre cada click (cada checkbox tem `A4J.AJAX.Submit` próprio)
2. Não é necessário clicar "Ocultar" no fim — o estado persiste no servidor

### Verificação de persistência
Após reload da página, o `checked` do checkbox volta a refletir o estado do servidor.
O painel volta a ficar oculto (default), mas se for re-expandido, os reflexos
marcados aparecem corretamente.

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
| 3 (Exibir reflexos) | Confirmação revista | 🔴 Alta | `04-reflexos-painel.md` — PRECISA clicar Exibir antes de marcar |
| 5 (CALCULADO) | Omissão | 🟡 Média | `05-historico-salarial.md` |
| 6 (j_id85) | Esclarecimento | 🟢 Baixa | `03-ocorrencias-verba.md` |

**Conclusão**: Fase 1 fica oficialmente concluída APENAS com esta errata aplicada.
Os docs 01-05 servem como referência geral; este 06 prevalece em conflitos.
