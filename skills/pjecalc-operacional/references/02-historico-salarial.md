# Histórico Salarial -- Operação Detalhada
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

O Histórico Salarial deve ser ensinado à máquina como o **módulo-base da base remuneratória**. Mesmo quando o corpus não demonstrou todos os labels internos com legibilidade absoluta, a lógica operacional ficou clara: é aqui que nascem as bases capazes de sustentar verbas, incidência de FGTS, contribuição social e cenários de diferença salarial ou recolhimento fundiário [Aula 1] [Aula 4] [Vídeo complementar — Reflexos/Integração] [Vídeo complementar — FGTS não depositado].

## Campos e configuração do Histórico Salarial

| Item exigido | Conteúdo consolidado | Origem |
|---|---|---|
| Como criar um novo histórico | Há fluxo de criação de base histórica antes das verbas dependentes | [Aula 1] [Vídeo complementar — FGTS não depositado] |
| Campo Nome | Deve identificar a função da base, como **BASE DE FGTS** ou outra base remuneratória pertinente ao cenário | [Vídeo complementar — FGTS não depositado] |
| Tipo de valor informado vs calculado | O corpus não exibe integralmente essa página com todas as opções, mas demonstra bases fixas informadas e bases calculadas em verbas derivadas | [Vídeo complementar — Reflexos/Integração] [NÃO COBERTO NAS AULAS QUANTO À EXIBIÇÃO INTEGRAL DESTA PÁGINA] |
| Campo Valor | Foi demonstrado como valor mensal da base histórica no cenário de FGTS | [Vídeo complementar — FGTS não depositado] |
| Incidência no FGTS | Checkbox explicitamente mencionado na Aula 1 e operacionalizado no cenário de FGTS | [Aula 1] [Vídeo complementar — FGTS não depositado] |
| Incidência na CS | Checkbox explicitamente mencionado na Aula 1 | [Aula 1] |
| Grade de ocorrências | Existe e pode ser editada competência a competência | [Vídeo complementar — FGTS não depositado] |
| Múltiplos históricos e reajustes | **[NÃO COBERTO NAS AULAS COM PASSO A PASSO EXAUSTIVO]** | [NÃO COBERTO NAS AULAS] |

## Papel do Histórico Salarial como fonte de verdade

O ponto operacional mais importante que a máquina deve absorver é que o Histórico Salarial não é apenas um depósito de valores. Ele funciona como **fonte de verdade remuneratória**. Se essa fonte estiver incompleta, mal delimitada por período ou incoerente com a natureza da verba lançada, a liquidação tende a exibir alertas, especialmente em verbas como horas extras e diferença salarial [Aula 4] [Vídeo complementar — Reflexos/Integração].

## Regra de ouro para automação

Preencher sempre o **salário mensal cheio** no histórico, mesmo no mês da demissão. O PJe-Calc fará a proporcionalização automática com base nos dias trabalhados (Saldo de Salário).

**Faltas e Férias Gozadas:** Devem ser lançadas nas telas específicas antes das verbas, pois impactam o cálculo de proporcionalidade das férias e das horas extras.

## Histórico duplo para Diferenças Salariais (Seção 15.1)

Diferente de outras verbas, a diferença salarial exige que a máquina crie **dois suportes materiais** no Histórico Salarial antes de lançar a rubrica.

| Histórico a Criar | Regra de Preenchimento para a Máquina | Impacto Operacional | Origem |
|---|---|---|---|
| **Salário Recebido** | Lançar o valor efetivamente pago. Marcar a **Contribuição Social como "Recolhida"**. | Altera a alíquota de INSS devida pelo reclamante no cálculo final. | |
| **Salário Devido** | Lançar o valor correto (ex: piso da CCT ou salário do paradigma). **Não marcar** CS ou FGTS neste campo. | Serve como base teórica para a apuração da diferença na verba. | |

### Armadilhas do histórico duplo

| Armadilha | Efeito | Solução |
|---|---|---|
| Não marcar CS como recolhida no salário recebido | Cálculo duplicado de INSS sobre a base já paga | Ativar o checkbox de recolhimento no **Histórico: Salário Recebido** |
| Não preencher proporcionalização simétrica | Diferença negativa ou inflada em meses incompletos | Marcar **"Proporcionalizar: Sim"** tanto na base quanto no valor pago |

## Dependências que partem do Histórico Salarial

| Módulo dependente | Como usa o histórico | Consequência se ausente |
|---|---|---|
| Verbas (Horas Extras, Diferença Salarial, etc.) | Base de cálculo para valor da hora ou diferencial | Alertas na liquidação, cálculo inconsistente |
| FGTS | Base para cálculo de depósitos devidos | Módulo fundiário sem suporte de base |
| Contribuição Social | Base para alíquotas previdenciárias | Encargo previdenciário incorreto |
| Periculosidade / Transferência | Incidência de 30% ou 25% sobre salário base | Alerta de base insuficiente |
| Acúmulo de Função | Multiplicador aplicado sobre salário da função principal | Plus salarial sem base de cálculo |
