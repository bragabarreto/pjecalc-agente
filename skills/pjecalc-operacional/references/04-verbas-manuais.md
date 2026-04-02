# Verbas Manuais e Especiais -- Fichas Técnicas
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

Este arquivo reúne as fichas técnicas das verbas que exigem configuração manual ou parametrização especial no PJe-Calc: Diferença Salarial, Salários Retidos, Estabilidade, Danos Morais, Danos Materiais e Acúmulo de Função.

---

## Diferença Salarial

**Seções 2.3, 7.3 e 15**

### Ficha técnica

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **Diferença Salarial** | [Aula 4] [Vídeo complementar — Reflexos/Integração] |
| DISPONÍVEL NO EXPRESSO | Sim, demonstrada no vídeo complementar | [Vídeo complementar — Reflexos/Integração] |
| TIPO DE VALOR | Valor devido informado e valor pago calculado, para formação da base diferencial | [Vídeo complementar — Reflexos/Integração] |
| BASE DE CÁLCULO | Combinação entre **Valor Informado** e base calculada do salário efetivamente pago | [Vídeo complementar — Reflexos/Integração] |
| COMPOSIÇÃO DO PRINCIPAL | Deve ser ajustada para **Não** quando a verba servir apenas de base para reflexos | [Vídeo complementar — Reflexos/Integração] |
| REFLEXOS TÍPICOS | 13o, férias, aviso, FGTS e demais reflexos deferidos no caso | [Vídeo complementar — Reflexos/Integração] |

### Pré-requisito: Histórico duplo (Seção 15.1)

Antes de lançar a verba, a máquina deve criar dois históricos salariais:

| Histórico | Preenchimento | Impacto |
|---|---|---|
| **Salário Recebido** | Valor efetivamente pago. Marcar **CS como "Recolhida"** | Altera alíquota de INSS devida |
| **Salário Devido** | Valor correto (piso CCT, paradigma, etc.). **Não marcar** CS ou FGTS | Base teórica para apuração da diferença |

### Passo a passo operacional

| Passo | Ação executável | Resultado esperado |
|---|---|---|
| 1 | Em **Verbas**, localizar **Diferença Salarial** no modo **Expresso** | Verba-base disponível |
| 2 | Renomear para identificar a causa (ex: *Diferença Salarial - Equiparação Paradigma*) | Facilitar auditoria |
| 3 | Parametrizar o **Valor Devido** = Histórico "Salário Devido". Marcar **"Proporcionalizar: Sim"** | Formação da base teórica devida |
| 4 | Parametrizar o **Valor Pago** = Histórico "Salário Recebido". Marcar **"Proporcionalizar: Sim"** | Formação do diferencial |
| 5 | Marcar incidências: **IR, Contribuição Social e FGTS** | |
| 6 | Decidir **Compor Principal**: **Sim** se diferença é devida; **Não** se servir apenas de base para reflexos | Impedir soma indevida ao crédito principal |
| 7 | Abrir os reflexos e marcar somente os deferidos: **13o, Aviso Prévio, Férias + 1/3** | |
| 8 | Marcar obrigatoriamente reflexo sobre **Multa do Art. 477 da CLT** | Base da multa = remuneração total |
| 9 | Marcar FGTS + Multa de 40% nos reflexos | |
| 10 | **Regerar** para processar ocorrências mensais | |
| 11 | Liquidar e conferir o PDF-resumo | Confirmar que a subtração (devido - pago) está correta |

### Armadilhas

| Armadilha | Efeito | Solução operacional |
|---|---|---|
| Proporcionalização assimétrica entre valor devido e valor pago | Reflexos negativos em meses quebrados | Marcar proporcionalização de forma idêntica nos dois lados |
| FGTS sem aparecer no resumo | Reflexo fundiário omitido | Marcar o checkbox específico do FGTS na linha da verba principal |
| Verba-base somando no crédito final indevidamente | Pagamento do principal quando só se queria o reflexo | Ajustar **Compor Principal** para **Não** |
| Não marcar CS como recolhida no salário recebido | Cálculo duplicado de INSS | Ativar checkbox de recolhimento no Histórico: Salário Recebido |
| Nome genérico da verba | Dificuldade em auditar múltiplas diferenças | Renomear especificando paradigma ou norma coletiva |

---

## Salários Retidos / Não Pagos

**Seção 2.4**

### Ficha técnica

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **SALÁRIO RETIDO** foi demonstrada como verba-base reutilizável em cenário de estabilidade | [Vídeo complementar — Estabilidades] |
| DISPONÍVEL NO EXPRESSO | Sim, no vídeo complementar | [Vídeo complementar — Estabilidades] |
| USO OPERACIONAL DEMONSTRADO | Renomear para **SALÁRIO ESTABILIDADE** e ajustar o período de incidência | [Vídeo complementar — Estabilidades] |
| BASE DE CÁLCULO | **Maior Remuneração** | [Vídeo complementar — Estabilidades] |
| PROPORCIONALIZAR | Deve ser marcado para meses fracionados | [Vídeo complementar — Estabilidades] |
| OBSERVAÇÃO | O corpus não demonstra todas as variantes de salários retidos fora do cenário estabilitário | [NÃO COBERTO NAS AULAS] |

### Passo a passo (cenário rescisório)

| Passo | Ação |
|---|---|
| 1 | Acessar **Verbas > Expresso** e selecionar **Salário Retido** |
| 2 | Ajustar período nas ocorrências para os meses inteiros não pagos anteriores à demissão |
| 3 | Marcar incidências de FGTS conforme condenação |
| 4 | Regerar e liquidar |

---

## Estabilidade (Salário, Férias e 13o do período estabilitário)

**Seções 2.6 e 7.5**

### Ficha técnica

| Parcela | Forma de preenchimento operacional | Particularidade crítica | Origem |
|---|---|---|---|
| Salário-estabilidade | Criar a partir de **SALÁRIO RETIDO**, renomear, ajustar período do dia seguinte à dispensa real até o fim da estabilidade, basear na maior remuneração e marcar proporcionalização | A data de demissão do sistema deve coincidir com o fim da estabilidade | [Vídeo complementar — Estabilidades] |
| Férias do período estabilitário | Criar a verba **FÉRIAS**, renomear e lançar os avos manualmente na grade de ocorrências | O sistema exige contagem material dos meses/avos dentro da estabilidade | [Vídeo complementar — Estabilidades] |
| 13o do período estabilitário | Criar a verba **13o SALÁRIO**, renomear e lançar avos por ano civil nas ocorrências | O cálculo deve ser fracionado por exercício civil | [Vídeo complementar — Estabilidades] |

### Passo a passo completo

| Ordem | Ação executável | Resultado esperado |
|---|---|---|
| 1 | Em **Parâmetros do Cálculo**, informar como data de demissão o **final do período estabilitário** | Estrutura temporal correta do cálculo |
| 2 | Ajustar **Maior Remuneração** e opções de aviso conforme cenário | Base rescisória coerente |
| 3 | Em **Verbas**, inserir **SALÁRIO RETIDO** e renomear para **SALÁRIO ESTABILIDADE** | Parcela-base do período estabilitário |
| 4 | Definir período do dia seguinte à dispensa real até o fim da estabilidade | Delimitação temporal correta |
| 5 | Marcar proporcionalização | Ajuste de meses fracionados |
| 6 | Inserir **FÉRIAS** e **13o SALÁRIO**, renomeando para refletir o período estabilitário | Parcelas derivadas criadas |
| 7 | Lançar avos manualmente nas ocorrências, separando exercícios civis quando necessário | Cálculo anual e proporcional correto |
| 8 | Liquidar e conferir o resumo | Validação da indenização substitutiva |

### Armadilha crítica

Usar a data real da dispensa como data de demissão do cálculo. **Solução:** Ajustar para a data final do período estabilitário.

---

## Indenização por Danos Morais

**Seção 16**

### Ficha técnica

| Campo | Conteúdo | Origem |
|---|---|---|
| NOME DA VERBA | **Indenização por Dano Moral** | |
| ÉPOCA PRÓPRIA | Data em que o dano moral foi **arbitrado** (sentença ou acórdão) | |
| DATA FINAL (na verba) | Data do arbitramento ou data de hoje | |
| REFERÊNCIA TEMPORAL | Não se vincula à demissão ou prestação de serviço, mas à decisão judicial | |

### Controle da Súmula 439 do TST

| Cenário de Decisão | Ação no PJe-Calc | Efeito |
|---|---|---|
| **Juros a partir do Arbitramento** | **Desmarcar** o checkbox da Súmula 439 | Juros e correção (SELIC) contam da data da decisão |
| **Juros a partir do Ajuizamento** | **Manter marcada** a Súmula 439 | Juros retroagem à data do protocolo da ação (Art. 883 CLT) |

### Critérios de atualização e juros (Lei 14.905)

- **Fase Judicial:** Utilizar **SELIC** (Receita Federal) até 29/08/2024
- **Novo Regime (Lei 14.905):** A partir de **30/08/2024**, aplicar **IPCA + Taxa Legal**
- A atualização conforme a Lei 14.905 deve ser apurada de ofício

### Checklist de validação

1. Validar se a data inserida corresponde à publicação da decisão que quantificou o dano
2. Se SELIC acumulada for ~15% (ajuizamento) vs ~7-8% (arbitramento), confirmar checkbox da Súmula 439
3. Após configurar valor e data, executar **"Regerar"**
4. No Resumo da Liquidação, verificar se a linha de juros apresenta a data correta

**Nota:** A máquina **não precisa** apurar o dano moral como "multa" para forçar juros do arbitramento; basta o controle de marcar/desmarcar a Súmula 439.

---

## Indenização por Danos Materiais (Pensionamento Mensal)

**Seção 17**

### Ficha técnica

| Campo | Conteúdo |
|---|---|
| NOME DA VERBA | **Indenização por Dano Material** |
| MARCO INICIAL | Data do evento danoso (não a data de admissão) |
| DIVISÃO DE PARCELAS | Vencidas (do dano até data do cálculo) e Vincendas (futuras, antecipadas) |

### Passo a passo -- Parcelas vencidas (mensais)

| Passo | Ação de Automação | Regra |
|---|---|---|
| 1 | Acessar **Verbas > Expresso** e selecionar **Indenização por Dano Material** | |
| 2 | Período: da **data do dano** até a **data da liquidação** | |
| 3 | Inserir valor fixado ou percentual do salário | |
| 4 | **Desmarcar** o checkbox da Súmula 439 (Danos Materiais) | Garante juro de mora **decrescente** |
| 5 | Marcar "Proporcionalizar: Sim" para meses fracionados | |

> **Nota Critica:** Ao desmarcar a Súmula 439, a parcela que venceu há dois anos terá mais juros do que a que venceu há dois meses, evitando aplicação linear desde o ajuizamento.

### Passo a passo -- Parcelas vincendas (pagamento antecipado)

Se o juiz determinar pagamento imediato de parcelas futuras:

1. **Calcular Valor Presente** antes de inserir no PJe-Calc:
   - **Opção A (Redutor Fixo):** Desconto direto (~30%) sobre o total
   - **Opção B (Fórmula Financeira):** `PV(taxa; nper; pgto)`, taxa ~0,5% a.m.
2. **Lançamento:** Criar verba de Dano Material, inserir montante já reduzido, informar data da liquidação em ambos os campos de data (inicial e final)

### Configuração de juros

- **Juros Simples** no menu Correção, Juros e Multa para permitir regressão mensal
- **Regerar** após qualquer alteração no período de pensionamento

### Checklist de validação

- No relatório impresso, coluna de juros deve apresentar **percentuais decrescentes** mês a mês
- Diferentemente de Danos Morais (Seção 16), os danos materiais **não** devem ter juros desde o ajuizamento, mas desde o vencimento de cada cota mensal
- Verificar se a data final do pensionamento respeita limites da sentença

---

## Acúmulo de Função (Plus Salarial)

**Seção 18**

### Ficha técnica

| Campo | Conteúdo |
|---|---|
| NOME DA VERBA | **Plus Salarial por Acúmulo de Função** (renomear a partir de Diferença Salarial) |
| DISPONÍVEL NO EXPRESSO | Sim (via Diferença Salarial) |
| BASE DE CÁLCULO | Salário da função principal (Histórico Salarial) |
| MULTIPLICADOR | Percentual do plus (ex: 0,3 para 30%, 0,4 para 40%) |
| REFLEXOS TÍPICOS | 13o Salário, Férias + 1/3, Aviso Prévio, FGTS |

### Passo a passo

| Passo | Ação de Automação | Regra |
|---|---|---|
| 1 | Verificar **Histórico Salarial** do salário da função principal | Base para incidência do percentual |
| 2 | Acessar **Verbas > Expresso** e selecionar **Diferença Salarial** | |
| 3 | Renomear para **"Plus Salarial por Acúmulo de Função"** | Facilitar auditoria |
| 4 | Informar período inicial e final do acúmulo | |
| 5 | Marcar incidência de **FGTS** (e demais conforme condenação) | |
| 6 | Vincular **Histórico Salarial**. Marcar **"Proporcionalizar: Sim"** | |
| 7 | **Divisor:** 1 | |
| 8 | **Multiplicador:** Inserir o percentual do plus (ex: **0,3** para 30%) | |
| 9 | **Quantidade:** 1 | |
| 10 | **Valor Pago:** Manter em branco (zero). Não deduzir nada | Apura-se apenas a proporção diferencial |
| 11 | Exibir reflexos e marcar: **13o, Férias + 1/3, Aviso Prévio, FGTS** | Apenas os deferidos em sentença |
| 12 | **Regerar** | Processar cálculo da diferença mensal sobre base histórica |

### Checklist de validação

- **Base de Cálculo Insuficiente:** Retornar ao Histórico Salarial e confirmar valores para todo o período do acúmulo
- **Compor Principal:** Garantir **"Sim"**, exceto se o título executivo determine que sirva apenas para base de reflexos
- **Proporcionalização:** Validar se está ativa para evitar valores cheios em meses parciais
- **Conferência:** No "Resumo da Liquidação", confirmar se o multiplicador (ex: 0,3) foi aplicado sobre o salário base em cada competência
