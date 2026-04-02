# Correcao Monetaria e Juros -- Guia Operacional
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

---

## 1. Visao Geral (Secao 6)

A pagina **Correcao, Juros e Multa** e uma das mais sensiveis para automacao, porque nela a maquina deixa de apenas lancar fatos e passa a controlar a **temporalidade financeira do credito**. As aulas-base e o video especifico sobre juros e correcao mostram, de forma convergente, que o sistema separa **correcao monetaria** de **juros**, permite **combinar indices**, trabalha com **data de corte** e distingue a parametrizacao geral da parametrizacao especifica por modulo ou categoria de verba [4] [5].

**Regra fundamental:** A maquina nao deve tratar juros e correcao como sinonimos. O video tematico reforca que, em certos regimes, a fase pre-judicial pode usar **IPCA-E** para correcao monetaria e **TRD (juros simples)** para juros, ao passo que a fase posterior se associa a **SELIC** ou, em cenario mais recente, a composicao **IPCA + taxa legal**, conforme o regime normativo escolhido [5].

---

## 2. Estrutura Logica da Pagina (Secao 6.1)

| Area | Funcao executavel | Origem |
|---|---|---|
| **Dados Gerais** | Definir regimes de correcao, juros, combinacao de indices e periodos sem incidencia | [Aula 4] |
| **Dados Especificos** | Ajustar base dos juros e regras especiais para verbas e modulos acessorios | [Aula 4] |
| **Salvar** | Consolidar a parametrizacao antes de liquidar | [Aula 4] |

---

## 3. Indices e Regimes Efetivamente Demonstrados (Secao 6.2)

| Regime/indice | Conteudo operacional consolidado | Origem |
|---|---|---|
| Tabela Unica da Justica do Trabalho | Aparece como referencia operacional sugerida na aula | [Aula 4] |
| IPCA-E | Demonstrado como indice utilizavel na composicao da correcao monetaria | [Aula 4] [Video complementar -- Juros/Correcao] |
| TRD (juros simples) | Demonstrada no video tematico como componente da fase pre-judicial | [Video complementar -- Juros/Correcao] |
| SELIC | Demonstrada como regime associado ao periodo posterior ao ajuizamento, conforme o cenario analisado | [Video complementar -- Juros/Correcao] |
| IPCA + Taxa Legal | Demonstrado como logica posterior no video tematico | [Video complementar -- Juros/Correcao] |

---

## 4. Passo a Passo Executavel para Configuracao (Secao 6.3)

| Passo operacional | Acao executavel | Armadilha a evitar |
|---|---|---|
| 1 | Entrar em **Correcao, Juros e Multa** | Nao liquidar com parametros padrao sem revisao |
| 2 | Em **Dados Gerais**, escolher o indice/regime principal | Nao confundir correcao monetaria com juros |
| 3 | Se necessario, marcar a opcao de combinar com outro indice | Nao duplicar indices por sobreposicao inadequada |
| 4 | Definir a data de corte quando houver mudanca temporal de regime | Nao deixar periodos hibridos sem marco definido |
| 5 | Em **Dados Especificos**, revisar a base dos juros e modulos especiais | Nao presumir que todas as verbas usarao a mesma base automaticamente |
| 6 | Salvar | Sem salvar, a liquidacao pode refletir parametrizacao antiga |
| 7 | Liquidar e inspecionar o relatorio | Confirmar se a linha temporal juridica foi respeitada |

---

## 5. Combinacao de Indices e Data de Corte

O sistema permite combinar indices para refletir mudancas legislativas ao longo do tempo. A maquina deve:

1. **Identificar o regime normativo** aplicavel ao caso (ex: ADC 58/59).
2. **Definir a data de corte** que separa as fases (tipicamente a data do ajuizamento).
3. **Configurar em Dados Gerais** o indice da fase pre-judicial (ex: IPCA-E para correcao + TRD para juros).
4. **Marcar a combinacao** com o indice da fase pos-ajuizamento (ex: SELIC ou IPCA + Taxa Legal).
5. **Verificar que nao ha sobreposicao** -- risco expressamente destacado no video tematico [5].

---

## 6. Validacao do Resultado (Secao 6.4)

A validacao nao termina na tela de parametros. O comportamento correto e liquidar o calculo e comparar o relatorio final com a hipotese normativa escolhida. Se a parametrizacao buscava separar fases temporais, o resumo do calculo e os demonstrativos devem evidenciar essa modulacao. Se o cenario utilizava taxa legal combinada com outro indice, a maquina deve verificar se nao ocorreu **dupla incidencia de correcao** sobre o mesmo periodo, risco expressamente destacado no video tematico [5].

| Criterio de validacao | O que conferir | Origem |
|---|---|---|
| Separacao de fases | Existencia de comportamento coerente entre pre e pos-ajuizamento | [Video complementar -- Juros/Correcao] |
| Coerencia entre juros e correcao | Ausencia de sobreposicao indevida | [Video complementar -- Juros/Correcao] |
| Compatibilidade com a liquidacao | Resumo final refletindo a escolha feita na pagina | [Aula 4] |

---

## 7. Cenarios Tipicos de Configuracao

### 7.1 ADC 58/59 (cenario mais comum pos-2020)
- **Fase pre-judicial (ate ajuizamento):** IPCA-E (correcao) + juros simples de 1% a.m. (TRD)
- **Fase pos-ajuizamento:** SELIC (que embute correcao + juros)
- **Data de corte:** Data do ajuizamento da acao

### 7.2 Regime com IPCA + Taxa Legal
- **Fase pre-judicial:** IPCA-E (correcao) + juros conforme legislacao
- **Fase pos-ajuizamento:** IPCA + Taxa Legal
- **Data de corte:** Data do ajuizamento ou conforme determinacao judicial

### 7.3 Armadilhas Criticas
- **Dupla incidencia:** Ao usar SELIC (que ja embute juros), nao configurar juros separados para o mesmo periodo.
- **Parametros padrao:** Nunca liquidar sem revisar os parametros padrao da pagina -- eles podem nao corresponder ao regime normativo do caso concreto.
- **Periodos hibridos:** Sempre definir a data de corte explicitamente quando houver mudanca de regime temporal.
