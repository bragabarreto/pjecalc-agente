# Cartao de Ponto -- Guia Operacional Completo
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

---

## 1. Conceito e Papel no Fluxo

O Cartao de Ponto nao e um relatorio passivo; ele e um **modulo de configuracao da jornada**, replicacao das marcacoes ao longo do contrato, edicao de excecoes e posterior validacao por espelho diario [2] [7].

A maquina deve aprender que o cartao nao produz credito sozinho; ele produz **quantidades** que precisam encontrar verbas ja compativeis na pagina de Verbas [1] [2] [3] [4] [6].

---

## 2. Fluxo Basico do Cartao de Ponto (Secao 1.7)

| Etapa | Acao executavel | Comportamento esperado do sistema | Origem |
|---|---|---|---|
| 1 | Entrar em **Cartao de Ponto** e clicar em **Novo** | Sistema cria um novo cartao e espelha datas contratuais no periodo | [Video complementar -- Cartao de Ponto] |
| 2 | Escolher o criterio de apuracao | Sistema passa a interpretar excedentes diarios/semanais conforme a parametrizacao | [Video complementar -- Cartao de Ponto] |
| 3 | Definir jornada padrao e enquadramento noturno | Sistema incorpora regras de jornada e, se for o caso, reducao ficta | [Video complementar -- Cartao de Ponto] |
| 4 | Preencher **Programacao Semanal** | Grade semanal e replicada para todo o contrato | [Video complementar -- Cartao de Ponto] |
| 5 | Abrir **Grade de Ocorrencias** | Sistema permite ajustes finos dia a dia ou mes a mes | [Video complementar -- Cartao de Ponto] |
| 6 | Salvar e voltar | Quantidades ficam aptas a alimentar verbas correlatas | [Video complementar -- Cartao de Ponto] |
| 7 | Imprimir apenas o espelho diario para validar | Sistema gera PDF com horas trabalhadas e excedentes | [Video complementar -- Cartao de Ponto] |

---

## 3. Roteiro Executavel Completo (Secao 7.1)

O video especifico de cartao de ponto mostrou um fluxo mais completo do que o apresentado no modulo principal. A maquina deve aprender que o calculo de jornada nasce da combinacao entre **programacao semanal**, **ocorrencias concretas**, **criterios de apuracao** e **validacao por espelho** [7].

| Ordem | Pagina/acao | Resultado operacional |
|---|---|---|
| 1 | Abrir **Cartao de Ponto** e clicar em **Novo** | Criacao do cartao do periodo |
| 2 | Escolher o criterio de apuracao | Definicao do modo de contabilizacao |
| 3 | Informar jornada padrao e descansos | Molde semanal do contrato |
| 4 | Ajustar parametro de adicional noturno e reducao ficta, se cabivel | Producao correta das horas noturnas |
| 5 | Gravar a **Programacao Semanal** | Replicacao do padrao no periodo |
| 6 | Revisar a **Grade de Ocorrencias** | Correcao de excecoes reais |
| 7 | Salvar e imprimir o espelho do cartao | Validacao visual da jornada apurada |
| 8 | Voltar a **Verbas** e conferir as rubricas dependentes de quantidade | Integracao entre jornada e credito |

---

## 4. Producao de Quantidades via Cartao de Ponto (Secao 11.2)

A maquina deve entender que o **Cartao de Ponto** e o modulo onde as quantidades de horas extras sao geradas antes de serem vinculadas a uma verba.

*   **Criterio de Apuracao:** Selecionar o criterio determinado (geralmente horas extras acima da **8a diaria ou 44a semanal**, pelo criterio mais favoravel).
*   **Programacao Semanal:** Preencher o horario padrao de entrada, saida e intervalo (ex: 09:00 as 19:00 com 1h de intervalo). O horario de intervalo e necessario para que o sistema nao o compute como jornada integral.
*   **Grade de Ocorrencias:** Salvar a programacao para que o sistema replique os horarios automaticamente por todo o periodo.
*   **Apuracao do Cartao:** Acessar "Visualizar Cartao" e clicar em **Apurar**. O sistema calculara mensalmente as horas excedentes com base nos parametros inseridos.

---

## 5. Apuracao Noturna -- Configuracao no Cartao de Ponto (Secao 12.1)

A automacao deve primeiro gerar os quantitativos antes de criar as verbas financeiras.

| Passo | Acao de Automacao | Regra de Preenchimento / Observacao |
| :--- | :--- | :--- |
| **1** | **Ativar Apuracao Noturna** | No Cartao de Ponto, marcar os seletores: **"Apurar Horas Noturnas"** e **"Apurar Horas Extras Noturnas"**. |
| **2** | **Definir Horario Noturno** | Para empregado urbano, configurar das **22:00 as 05:00**. |
| **3** | **Reducao Ficta** | Marcar obrigatoriamente a opcao de **reducao ficta da hora noturna** (considerando a hora de 52 minutos e 30 segundos). |
| **4** | **Jornada Diaria** | Configurar o campo superior como **"Jornada Diaria"** para que o sistema identifique corretamente o que extrapola a jornada e incide em horario noturno. |
| **5** | **Grade de Ocorrencias** | Salvar e apurar para que o sistema gere as colunas separadas de horas noturnas totais e horas extras noturnas. |

---

## 6. Configuracao das Verbas Noturnas (Secao 12.2)

A maquina deve evitar o uso do multiplicador 1,8 (que soma o adicional de 20% com o de 50% em uma unica verba), pois isso pode gerar erro de calculo se o adicional noturno nao for calculado sobre todas as horas da noite. **A recomendacao tecnica e calcular as verbas de forma separada**.

### A. Verba: Adicional Noturno (20%)
| Campo Operacional | Configuracao para Automacao |
| :--- | :--- |
| **Selecao** | Criar a verba **Adicional Noturno 20%** via menu Expresso. |
| **Importacao** | No campo quantidade, selecionar **"Importar do Cartao de Ponto"** -> **"Todas as Horas Noturnas"**. |
| **Incidencia** | Garantir que a base de calculo seja o salario base (Historico Salarial). |

### B. Verba: Horas Extras Noturnas (50%)
| Campo Operacional | Configuracao para Automacao |
| :--- | :--- |
| **Selecao** | Criar uma verba de **Hora Extra 50%** (ou a aliquota deferida). |
| **Multiplicador** | **Acao Critica:** Alterar o multiplicador de 1,5 para **1,6**. |
| **Justificativa** | O uso de **1,6** ocorre porque o adicional noturno (0,2) ja esta sendo pago separadamente sobre todas as horas. Usar 1,8 geraria pagamento em duplicidade (*bis in idem*). |
| **Importacao** | No campo quantidade, selecionar **"Importar do Cartao de Ponto"** -> **"Horas Extras Noturnas"**. |

---

## 7. Reflexos e Incidencias das Verbas Noturnas (Secao 12.3)

1.  **Base de Calculo:** Ambas as verbas devem estar vinculadas ao **Historico Salarial** coerente.
2.  **Reflexos:** Marcar os reflexos em **DSR/RSR, 13o Salario, Ferias + 1/3, Aviso Previo e FGTS**.
3.  **Atencao:** O adicional noturno deve compor a base de calculo das horas extras; ao utilizar a metodologia de multiplicador **1,6** e calcular o adicional a parte, o sistema ja realiza essa integracao sem gerar erros matematicos.

---

## 8. Checklist de Validacao / Troubleshooting (Secao 12.4)

*   **Regeracao:** Apos configurar as importacoes do cartao e os multiplicadores, a maquina deve executar o comando **"Regerar"**.
*   **Conferencia de Relatorio:** No **"Espelho do Cartao de Ponto"**, validar se a soma de "Horas Noturnas" e "Horas Extras Noturnas" reflete a jornada real apos a reducao ficta.
*   **Evitar Erro Comum:** Nao inserir o adicional noturno na base de calculo da hora extra se estiver usando o multiplicador 1,8, pois isso causaria incidencia tripla do adicional. A metodologia de **verba separada com multiplicador 1,6** e a mais segura para automacao.

---

## 9. Preparacao Obrigatoria (Secao 11.1)

Antes de iniciar o lancamento das horas, a maquina deve garantir que as bases estruturais estejam corretas para evitar alertas de erro na liquidacao.

1.  **Dados do Calculo:** Preencher obrigatoriamente Admissao, Demissao, Ajuizamento e a Localidade (Estado/Municipio).
2.  **Historico Salarial:** Criar o historico salarial (ex: Salario Base) para todo o periodo contratual. **Sem base salarial, o sistema nao consegue apurar o valor da hora extra**, gerando alertas criticos.

---

## 10. Configuracao e Parametrizacao da Verba de Horas Extras (Secao 11.3)

Apos gerar as quantidades no cartao, a maquina deve configurar a rubrica financeira na pagina de **Verbas**.

1.  **Selecao da Verba:** Escolher a rubrica correspondente (ex: **Horas Extras 50%**).
2.  **Base de Calculo:** Vincular o **Historico Salarial** criado anteriormente. E necessario clicar no botao **"+" (verde)** para que o sistema salve a base; caso contrario, ocorrera erro.
3.  **Importacao de Quantidades:** No campo de quantidade, selecionar a opcao **"Importar do Cartao de Ponto"** e indicar a coluna de horas extras apuradas. Novamente, deve-se clicar no **"+" (verde)** para confirmar a importacao.
4.  **Multiplicador:** Validar se o multiplicador esta correto (ex: 1.5 para 50% ou 2.0 para 100%).
5.  **Regeracao:** Apos salvar, a maquina deve sempre **Regerar** a verba para que o sistema processe a combinacao entre base salarial e quantidades.

---

## 11. Reflexos e Regimes Especiais de Horas Extras (Secao 11.4)

A maquina deve configurar as repercussoes juridicas das horas extras de forma criteriosa.

*   **Reflexos Tipicos:** Marcar os reflexos deferidos, como **DSR/RSR, 13o Salario, Ferias + 1/3, Aviso Previo e FGTS (com multa de 40%, se houver)**.
*   **Modulacao da OJ 394 (SDI-1 do TST):** Se houver determinacao judicial para aplicar a modulacao da OJ 394, a maquina deve:
    *   Marcar o reflexo em DSR apenas para o periodo ate **19/03/2023**.
    *   Para o periodo a partir de **20/03/2023**, criar o DSR como verba autonoma ou conforme o novo regime de repercussao para evitar calculos indevidos.

---

## 12. Finalizacao e Validacao de Horas Extras (Secao 11.5)

1.  **Correcao e Juros:** Configurar os parametros de ADC 58/59 (IPCA-E na fase pre-judicial e SELIC a partir do ajuizamento, ou conforme legislacao vigente).
2.  **Liquidacao:** Executar a liquidacao informando a data base do calculo.
3.  **Auditoria de Relatorios:** A maquina deve conferir no relatorio de **"Resumo da Liquidacao"** e no **"Espelho do Cartao de Ponto"** se as horas extras e seus reflexos foram apurados corretamente em cada competencia.
4.  **Tratamento de Alertas:** Caso surja um alerta de **"Base de calculo insuficiente"**, a maquina deve retornar ao Historico Salarial e verificar se ha valores lancados para todos os meses do periodo de apuracao das horas extras.
