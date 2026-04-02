# Verbas via Menu Expresso -- Fichas Técnicas
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

Este arquivo reúne as fichas técnicas das verbas que são lançadas primariamente via menu **Expresso** no PJe-Calc: Horas Extras, Adicional Noturno, Insalubridade, Periculosidade e Adicional de Transferência.

---

## Horas Extras (50%, 75%, 100%)

**Seção 2.1 + Seção 11**

### Ficha técnica

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **Hora extra 50%** aparece nominalmente; 75% e 100% não foram mostradas nominalmente | [Aula 4] |
| DISPONÍVEL NO EXPRESSO | **[NÃO COBERTO NAS AULAS]** | [NÃO COBERTO NAS AULAS] |
| CONFIGURAÇÃO GERAL | Quantidades podem ser produzidas no **Cartão de Ponto** e depois vinculadas à verba na página **Verbas** | [Aula 2] [Vídeo complementar — Cartão de Ponto] |
| BASE DE CÁLCULO | Depende de histórico salarial coerente; ausência dessa base gera alertas | [Aula 4] |
| REFLEXOS TÍPICOS | DSR/RSR, 13o, férias, aviso e FGTS, conforme cenário e parâmetros | [Aula 2] [Vídeo complementar — OJ 394] |
| ARMADILHA | Falta de histórico salarial completo pode gerar alerta na liquidação | [Aula 4] |

### Passo a passo operacional

| Passo | Ação executável | Observação |
|---|---|---|
| 1 | Criar ou revisar o Histórico Salarial correspondente | Sem base salarial, a verba pode falhar ou alertar |
| 2 | Em **Cartão de Ponto**, clicar em **Novo** e parametrizar jornada, descansos e horário noturno | A quantidade nasce aqui |
| 3 | Salvar a **Programação Semanal** e revisar a **Grade de Ocorrências** | Ajustar exceções reais |
| 4 | Em **Verbas**, criar a verba de horas extras ou revisar a existente | Integrar quantidade e base |
| 5 | Vincular o **Histórico Salarial** como base de cálculo. Clicar no botão **"+" (verde)** para salvar | Sem o "+", ocorrerá erro |
| 6 | No campo quantidade, selecionar **"Importar do Cartão de Ponto"** e indicar a coluna de HE. Clicar no **"+" (verde)** | Confirmar a importação |
| 7 | Validar multiplicador (1.5 para 50%, 2.0 para 100%) | |
| 8 | Expandir a árvore de reflexos e marcar somente os reflexos deferidos | Evitar repercussões indevidas |
| 9 | Se houver modulação da OJ 394, limitar o reflexo de DSR até 19/03/2023 e criar DSR autônomo a partir de 20/03/2023 | [Vídeo complementar — OJ 394] Não misturar regimes antigos e novos |
| 10 | **Regerar** e liquidar | Validar consistência do cálculo |

### Armadilhas

| Armadilha | Consequência | Solução |
|---|---|---|
| Lançar HE sem base histórica | Alertas e cálculo inconsistente | Completar o Histórico Salarial antes |
| Não clicar no "+" verde ao vincular base ou quantidade | Campo não salvo, erro na liquidação | Sempre confirmar com o botão "+" |
| Manter DSR reflexo em período que exige tratamento autônomo (OJ 394) | Dupla repercussão | Separar temporalmente as rubricas |

---

## Adicional Noturno (20%)

**Seção 2.2 + Seção 12**

### Ficha técnica

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **Adicional Noturno** | [Aula 2] |
| DISPONÍVEL NO EXPRESSO | **[NÃO COBERTO NAS AULAS]** | [NÃO COBERTO NAS AULAS] |
| CONFIGURAÇÃO | A quantidade é vinculada à jornada lançada no Cartão de Ponto | [Aula 2] [Vídeo complementar — Cartão de Ponto] |
| PARÂMETROS ESPECÍFICOS | Escolha do tipo de atividade e marcação da redução ficta da hora noturna | [Vídeo complementar — Cartão de Ponto] |
| ARMADILHA | Deixar de marcar a redução ficta da hora noturna compromete a apuração jurídica correta do período noturno | [Vídeo complementar — Cartão de Ponto] |

### Configuração no Cartão de Ponto

| Passo | Ação de Automação | Regra de Preenchimento |
|---|---|---|
| 1 | **Ativar Apuração Noturna** | No Cartão de Ponto, marcar: **"Apurar Horas Noturnas"** e **"Apurar Horas Extras Noturnas"** |
| 2 | **Definir Horário Noturno** | Para empregado urbano: **22:00 às 05:00** |
| 3 | **Redução Ficta** | Marcar obrigatoriamente a opção de **redução ficta da hora noturna** (hora de 52min30s) |
| 4 | **Jornada Diária** | Configurar campo superior como **"Jornada Diária"** |
| 5 | **Grade de Ocorrências** | Salvar e apurar para gerar colunas separadas de horas noturnas e HE noturnas |

### Configuração da verba Adicional Noturno 20%

| Campo | Configuração |
|---|---|
| Seleção | Criar via menu **Expresso** |
| Importação | Quantidade: **"Importar do Cartão de Ponto"** -> **"Todas as Horas Noturnas"** |
| Incidência | Base de cálculo = salário base (Histórico Salarial) |

### Configuração da verba Horas Extras Noturnas (50%)

| Campo | Configuração |
|---|---|
| Seleção | Criar verba de **Hora Extra 50%** (ou alíquota deferida) |
| Multiplicador | **Acao Critica:** Alterar de 1,5 para **1,6** |
| Justificativa | O adicional noturno (0,2) já está sendo pago separadamente. Usar 1,8 geraria *bis in idem* |
| Importação | Quantidade: **"Importar do Cartão de Ponto"** -> **"Horas Extras Noturnas"** |

### Reflexos

Ambas as verbas devem ter reflexos em: **DSR/RSR, 13o Salário, Férias + 1/3, Aviso Prévio e FGTS**.

### Armadilhas

| Armadilha | Consequência | Solução |
|---|---|---|
| Não marcar redução ficta | Apuração jurídica incorreta do período noturno | Marcar sempre a redução ficta |
| Usar multiplicador 1,8 em vez de verbas separadas | *Bis in idem* - incidência tripla do adicional | Usar verba separada com multiplicador **1,6** |

---

## Adicional de Insalubridade

**Seção 13**

### Ficha técnica

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **Adicional de Insalubridade** | |
| DISPONÍVEL NO EXPRESSO | Sim | |
| BASE DE CÁLCULO PADRÃO | **Salário Mínimo** (alimentado pelas tabelas do sistema) | |
| ALÍQUOTAS | **10% (mínimo)**, **20% (médio)**, **40% (máximo)** | |
| PARTICULARIDADE | Geralmente **dispensa** dependência de histórico salarial prévio | |

### Passo a passo (Lançamento via Expresso)

| Passo | Ação de Automação | Regra de Preenchimento |
|---|---|---|
| 1 | **Localizar Verba** | Acessar **Verbas** > **Expresso** e buscar "Adicional de Insalubridade" |
| 2 | **Definir Grau** | Selecionar: **10% (mínimo)**, **20% (médio)** ou **40% (máximo)** |
| 3 | **Período de Apuração** | Informar o intervalo exato de exposição ao agente insalubre |
| 4 | **Base de Cálculo** | Manter seleção padrão de **"Salário Mínimo"** |
| 5 | **Proporcionalizar** | **Marcar obrigatoriamente** para meses de admissão, demissão ou afastamentos |
| 6 | **Salvar** | Gravar para habilitar edição de parâmetros e reflexos |

### Parâmetros e reflexos

- **Multiplicador:** Preenchido automaticamente (0.10, 0.20 ou 0.40) conforme verba escolhida
- **Divisor:** Manter como **1**
- **Quantidade:** Sempre **1**
- **Reflexos deferidos:** Marcar **13o Salário**, **Férias + 1/3** e **Aviso Prévio**
- **Dica estratégica:** Se for cálculo do autor, marcar também reflexo sobre a **Multa do Art. 477 da CLT**

### Ciclo de regeneração e validação

1. **Regerar Ocorrências:** Sempre que alterar período de exposição ou datas do cálculo
2. **Auditoria em Ocorrências:** Validar se o sistema busca corretamente o salário mínimo da época e aplica o multiplicador
3. **Checklist de Liquidação:** Verificar se não há alertas de "Base de cálculo insuficiente" (raro para esta rubrica)

---

## Adicional de Periculosidade (30%)

**Seções 5.1 a 5.4**

### Ficha técnica

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **Adicional de Periculosidade 30%** | |
| DISPONÍVEL NO EXPRESSO | Sim | |
| ALÍQUOTA | 30% | |
| BASE DE CÁLCULO | Incide exclusivamente sobre o **salário base**, salvo categorias com previsão em ACT/CCT | |
| REFLEXOS TÍPICOS | 13o Salário, Aviso Prévio, Férias + 1/3 | |
| PRE-REQUISITO | Histórico Salarial deve estar preenchido | |

### Passo a passo

| Passo | Ação | Observação |
|---|---|---|
| 1 | Acessar **Verbas** > **Expresso** | |
| 2 | Selecionar **Adicional de Periculosidade 30%** e clicar em **Salvar** | |
| 3 | Verificar se **incidências** (FGTS, INSS, IRRF) estão corretas | Conforme a condenação |
| 4 | Informar o **período** exato de direito à verba | Pode ser todo o contrato ou intervalo específico |
| 5 | Exibir reflexos e clicar em **Adicionar reflexos** | Se pagamento habitual |
| 6 | Marcar reflexos: **13o Salário, Aviso Prévio, Férias + 1/3** | |

### Tratamento diferenciado: Mensalista vs. Horista

| Tipo de Salário | Tratamento do DSR na Periculosidade |
|---|---|
| **Mensalista** | **Não calcular DSR à parte.** O DSR já está embutido no salário mensal. |
| **Horista / Diarista** | **Calcular DSR separadamente.** Apurar adicional sobre horas trabalhadas e gerar reflexo em DSR. |

#### Hack para DSR de Horistas

1. Selecionar **Repouso Remunerado Comissionista** no menu Expresso
2. Renomear para **DSR sobre Periculosidade**
3. Base de cálculo = valor apurado do Adicional de Periculosidade
4. **Divisor:** Dias Úteis | **Multiplicador:** 1 | **Quantidade:** Importada do calendário (repousos e feriados)

### Contribuições Sociais e Atualização

1. Acessar **Contribuição Social** > **Ocorrências** > **Regerar**
2. Selecionar **Atividade Econômica (CNAE)** correta para SAT/RAT
3. Em **Correção Monetária e Juros**, configurar índices conforme decisão judicial

---

## Adicional de Transferência (25%)

**Seção 14**

### Ficha técnica

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **Adicional de Transferência** | |
| DISPONÍVEL NO EXPRESSO | Sim | |
| ALÍQUOTA PADRÃO | 25% | |
| BASE DE CÁLCULO | Salário Base (vinculado ao Histórico Salarial) | |
| REFLEXOS TÍPICOS | 13o Salário, Férias, Aviso Prévio, FGTS e Multa de 40% | |
| INCIDÊNCIAS | INSS e FGTS (segue a sorte da verba principal) | |

### Passo a passo

| Ordem | Página/Ação | Resultado / Regra |
|---|---|---|
| 1 | **Histórico Salarial** | Certificar que o **Salário Base** está preenchido para todo o período da transferência |
| 2 | **Verbas > Expresso** | Localizar e salvar a rubrica **Adicional de Transferência** |
| 3 | **Parâmetros da Verba** | Validar o percentual de **25%** e selecionar o período |
| 4 | **Configurar Reflexos** | Marcar: 13o Salário, Aviso Prévio, Férias e Multa de 40% |
| 5 | **Ajuste de Férias** | **Acao Critica:** Se o contrato teve apenas férias indenizadas, desmarcar o reflexo sobre "férias gozadas" |
| 6 | **FGTS** | Marcar incidência de FGTS nos reflexos |
| 7 | **Regerar** | Executar "Regerar" na listagem de verbas para consolidar a grade mensal |

### Checklist de validação

- **Proporcionalização:** Garantir que o campo "Proporcionalizar" esteja marcado para meses "quebrados"
- **Base de Cálculo Insuficiente:** Se a liquidação gerar alerta, retornar ao Histórico Salarial e conferir valores nas competências exatas da transferência
- **Conferência em Relatório:** No "Resumo da Liquidação", validar se o adicional de 25% incidiu mensalmente sobre o salário base e se os reflexos aparecem proporcionalmente
