# Regras Práticas — Tutorial Oficial PJe-Calc

Fonte: Tutorial Oficial PJe-Calc — pje.csjt.jus.br/manual/index.php/PJe-Calc-Tutorial
         Canal "Conhecendo o PJe-Calc" (Alacid Corrêa Guerreiro — Gestor Nacional CSJT)

---

## Regra 1 — "Novo" vs "Cálculo Externo"

**Usar "Novo"** → SEMPRE para primeira liquidação de uma sentença
- Menu: Arquivo > Novo > Cálculo Trabalhista
- Preenche-se tudo do zero pela interface web
- Mais estável; formulário validado pelo sistema

**Usar "Cálculo Externo"** → APENAS para atualizar cálculo já existente no PJE
- Importa arquivo .PJC existente para edição
- Pode causar conflito de IDs JSF se usado indevidamente para cálculo novo

---

## Regra 2 — Histórico Salarial

**Quando preencher:**
- Quando o salário do empregado variou durante o contrato (promoções, acordos coletivos, dissídios)
- Quando a sentença menciona "diferenças salariais" por período

**Como preencher:**
- Data início → Data fim → Valor (salário bruto do período)
- Preencher em ordem cronológica (mais antigo primeiro)
- O último período se estende até a data de demissão

**Quando NÃO preencher:**
- Salário único durante todo o contrato → deixar campo em branco (PJE-Calc usa a maior remuneração informada)

---

## Regra 3 — Aviso Prévio e seus efeitos

**Aviso Prévio Indenizado:**
- A data de demissão fica na data real da dispensa
- O PJE-Calc projeta automaticamente o período do AP para cálculo de 13º e férias
- Incide FGTS (posição majoritária dos TRTs)
- NÃO alterar a data de demissão para incluir o período projetado do AP

**Aviso Prévio Trabalhado:**
- A data de demissão já inclui o período do AP
- O empregado trabalhou todo o período

**Cálculo proporcional (Lei 12.506/2011):**
- 1 a 12 meses: 30 dias
- 1 ano completo além do primeiro: +3 dias
- Máximo: 90 dias
- O PJE-Calc calcula automaticamente — informar apenas o tipo (Indenizado/Trabalhado)

---

## Regra 4 — Prescrição e período calculado

**Prescrição quinquenal:**
- O PJE-Calc subtrai automaticamente 5 anos da data de ajuizamento
- Verbas lançadas com período anterior serão truncadas

**Prescrição bienal:**
- Automática após rescisão — prazo de 2 anos para ajuizar
- Se a ação foi ajuizada após 2 anos da rescisão: verificar se a sentença reconheceu a prescrição

**FGTS:**
- Marcar TRUE — cobre os 30 anos anteriores à vigência da Súmula 362/TST (08/11/2010)

---

## Regra 5 — Verbas que geram reflexas (cascata completa)

### Horas Extras → gera 3 reflexas obrigatórias:
1. RSR sobre Horas Extras (Comum, Mensal, fgts/inss/ir=true)
2. 13º s/ Horas Extras (13o Salario, Desligamento, fgts/inss/ir=true)
3. Férias + 1/3 s/ Horas Extras (Ferias, Periodo Aquisitivo, fgts=false, inss/ir=true)

### Adicional Noturno → gera 3 reflexas:
1. RSR sobre Adicional Noturno
2. 13º s/ Adicional Noturno
3. Férias + 1/3 s/ Adicional Noturno

### Adicional de Insalubridade → gera 2 reflexas:
1. 13º s/ Insalubridade
2. Férias + 1/3 s/ Insalubridade
(RSR só se for adicionado como "Insalubridade Variável")

### Adicional de Periculosidade → gera 2 reflexas:
1. 13º s/ Periculosidade
2. Férias + 1/3 s/ Periculosidade

### Gratificação de Função → gera reflexas se a sentença determinar integração ao salário:
1. 13º s/ Gratificação
2. Férias s/ Gratificação

### Verbas que NÃO geram reflexas:
- Dano moral e material
- Multas (art. 467, art. 477, normativa)
- Aviso prévio indenizado (o PJE-Calc inclui automaticamente nos cálculos de 13º e férias)
- Vale transporte

---

## Regra 6 — Campos críticos por verba

**Horas Extras:**
- Percentual: 50% (padrão), 100% (jornada noturna/domingos), conforme sentença
- Divisor: 220 (44h/sem), 200 (40h/sem), 180 (36h/sem)
- Período: data início e fim das horas extras (conforme prescrição)
- Cartão de ponto: mencionar se há horas extras por semana específica

**Férias (vencidas e proporcionais):**
- Ávos: meses completos do período aquisitivo
- Situação: "Simples" ou "Em Dobro" (quando empregador concede férias vencidas com 1 ano de atraso)
- Dobra: true/false conforme sentença

**Adicional de Insalubridade:**
- Percentual: 10% (mínimo), 20% (médio), 40% (máximo)
- Base de cálculo: salário mínimo (padrão) ou salário contratual (verificar sentença)
- Período: conforme laudo pericial

---

## Regra 7 — Honorários e Custas

**Honorários advocatícios de sucumbência:**
- Percentual: 5% a 15% conforme sentença
- Base: "sobre o valor bruto da condenação" ou "sobre o valor líquido" — verificar
- Parte devedora: reclamado (mais comum), reclamante (quando pedido julgado improcedente), ambos (sucumbência recíproca)

**Honorários periciais:**
- Campo SEPARADO dos honorários advocatícios
- Informar: nome do perito, especialidade, valor fixo
- Parte devedora: quem perdeu a perícia (verificar sentença)

**Custas processuais (art. 789 CLT):**
- 2% do valor da condenação
- Mínimo: R$ 10,64 (atualizado por portaria CSJT)
- Máximo: R$ 4.000,00 (portaria CSJT)
- Parte devedora: reclamado na maioria dos casos

---

## Regra 8 — Erros comuns e como evitar

| Erro | Causa | Solução |
|---|---|---|
| Verba aparece com valor zerado | Base de cálculo não preenchida | Informar maior_remuneracao ou historico_salarial |
| FGTS não calculado | multa_40 marcado sem tipo_rescisao correto | Verificar tipo_rescisao = sem_justa_causa |
| Correção errada (INPC ao invés de IPCA-E) | Índice desatualizado | Selecionar IPCA-E (ADC 58) |
| 13º proporcional com valor incorreto | Ávos errados | Calcular: (meses no ano corrente) / 12 |
| Férias em dobro não calculadas | Situação = "Simples" | Alterar para "Em Dobro" se a sentença determinar |
| IR calculado sobre dano moral | Campo IR marcado para verba indenizatória | Não marcar IR para dano moral (Súmula 498/STJ) |
