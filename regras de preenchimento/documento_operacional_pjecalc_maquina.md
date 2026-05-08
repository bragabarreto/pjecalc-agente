# Manual operacional do PJe-Calc para execução por máquina

**Autor:** Manus AI

## Apresentação metodológica

Este manual foi reestruturado para cumprir um objetivo pedagógico-operacional mais específico do que a mera descrição do sistema: **ensinar uma máquina a operar o PJe-Calc Cidadão e a executar cálculos trabalhistas do início ao fim**, tanto no plano geral do fluxo do sistema quanto no plano particular do preenchimento de cada parcela relevante. Em razão disso, cada seção foi redigida para responder, de forma executável, às seguintes perguntas: **em que página entrar**, **o que preencher**, **em que ordem preencher**, **o que o sistema faz após cada ação**, **quando salvar**, **quando regerar**, **o que revisar antes de liquidar** e **como validar o resultado em relatório** [1] [2] [3] [4] [5] [6] [7] [8] [9] [10] [11].

A metodologia preserva a mesma cautela documental do material anterior. Sempre que um detalhe foi demonstrado por interface real, por slide legível ou por narração convergente do instrutor, ele foi consolidado com a marcação correspondente. Sempre que o corpus não demonstrou com segurança o label exato de um campo, o valor padrão de um seletor, a URL interna da página ou a mensagem literal do sistema, o ponto foi mantido como **[NÃO COBERTO NAS AULAS]**. Essa opção não reduz a utilidade do manual; ao contrário, evita inferências inseguras e torna o material mais confiável para uso como base de automação [1] [2] [3] [4].

## Convenção de marcação de origem

| Marcação | Significado |
|---|---|
| **[Aula 1]** | Informação extraída da Aula 1 do módulo principal |
| **[Aula 2]** | Informação extraída da Aula 2 do módulo principal |
| **[Aula 3]** | Informação extraída da Aula 3 do módulo principal |
| **[Aula 4]** | Informação extraída da Aula 4 do módulo principal |
| **[Vídeo complementar — Juros/Correção]** | Informação reforçada pelo vídeo específico sobre correção monetária e juros |
| **[Vídeo complementar — Reforço geral]** | Informação reforçada pelo vídeo de visão geral, instalação e primeiro cálculo |
| **[Vídeo complementar — Cartão de Ponto]** | Informação reforçada pelo vídeo específico de cartão de ponto |
| **[Vídeo complementar — OJ 394]** | Informação reforçada pelo vídeo específico sobre modulação dos reflexos do DSR |
| **[Vídeo complementar — Reflexos/Integração]** | Informação reforçada pelo vídeo específico sobre cálculo apenas de reflexos por integração de verba ao salário |
| **[Vídeo complementar — FGTS não depositado]** | Informação reforçada pelo vídeo específico sobre FGTS a recolher |
| **[Vídeo complementar — Estabilidades]** | Informação reforçada pelo vídeo específico sobre estabilidade gestante e acidentária |
| **[NÃO COBERTO NAS AULAS]** | Item exigido, mas não demonstrado com segurança suficiente |

## Escopo efetivamente analisado

| Fonte | Conteúdo central observado | Função neste manual |
|---|---|---|
| Aula 1 | Tela inicial, tabelas, criação do cálculo, dados do processo, parâmetros do cálculo, faltas, férias e histórico salarial | Base estrutural do fluxo |
| Aula 2 | Verbas, verbas reflexas, alteração de parâmetros, cartão de ponto, salário-família e seguro-desemprego | Lançamento de parcelas e apuração de quantidades |
| Aula 3 | FGTS, contribuição social, previdência privada, pensão alimentícia e imposto de renda | Encargos e incidências |
| Aula 4 | Multas e indenizações, honorários, custas, correção/juros, operações, liquidação, impressão e exportação | Fechamento técnico e saída do cálculo |
| Vídeo complementar — Juros/Correção | Configurações práticas da aba de correção monetária e juros | Aprofundamento da Seção 6 |
| Vídeo complementar — Reforço geral | Instalação, atualização de tabelas, primeiro cálculo e navegação | Reforço do fluxo geral |
| Vídeo complementar — Cartão de Ponto | Criação do cartão, programação semanal, grade de ocorrências e impressão do espelho | Detalhamento operacional da apuração de jornada |
| Vídeo complementar — OJ 394 | Fatiamento temporal dos reflexos do DSR sobre horas extras | Aprofundamento de reflexos e modulação |
| Vídeo complementar — Reflexos/Integração | Diferença salarial calculada apenas para gerar reflexos | Aprofundamento de parcelas que não compõem o principal |
| Vídeo complementar — FGTS não depositado | FGTS devido como obrigação de recolher, e não de pagar diretamente ao reclamante | Aprofundamento do cenário fundiário |
| Vídeo complementar — Estabilidades | Salário-estabilidade, férias e 13º do período estabilitário | Aprofundamento por cenário especial |

## SEÇÃO 1 — FLUXO GERAL DO SISTEMA

O fluxo geral do PJe-Calc deve ser ensinado à máquina como **sequência obrigatória de dependências**, e não como simples visita a telas. O sistema tolera alguma navegação livre, mas o cálculo só se sustenta quando as bases estruturais são lançadas antes das verbas dependentes e quando as operações finais somente são executadas após revisão das incidências, das ocorrências e dos parâmetros de período [1] [2] [3] [4] [6].

### 1.1 Fluxo macro executável

| Ordem | Página/módulo | Ação principal ensinável | Pré-requisito | Saída esperada |
|---|---|---|---|---|
| 1 | Tela Inicial | Criar, buscar ou importar cálculo | Sistema instalado e aberto | Cálculo ativo |
| 2 | Tabelas | Atualizar índices e bases auxiliares | Sistema aberto | Ambiente pronto para cálculo |
| 3 | Dados do Cálculo / Dados do Processo | Informar identificação do cálculo, localidade e marcos contratuais/processuais | Cálculo criado | Estrutura inicial gravada |
| 4 | Parâmetros do Cálculo | Definir datas estruturais, maior remuneração, aviso prévio e demais parâmetros-base | Dados iniciais preenchidos | Regras gerais do cálculo definidas |
| 5 | Faltas, Férias e Histórico Salarial | Alimentar bases fáticas e salariais | Parâmetros gerais coerentes | Suporte material para verbas e encargos |
| 6 | Verbas | Criar parcelas principais, reflexos e verbas manuais | Bases históricas e parâmetros já preenchidos | Rubricas configuradas |
| 7 | Cartão de Ponto | Apurar quantitativos de jornada, horas extras e adicional noturno, quando o caso exigir | Contrato e verbas correlatas já estruturados | Quantidades mensais consolidadas |
| 8 | FGTS, CS, IR, Previdência Privada, Pensão | Definir incidências, retenções e módulos acessórios | Verbas e bases já existentes | Encargos consistentes |
| 9 | Multas, Honorários, Correção/Juros | Parametrizar fechamento jurídico-financeiro | Parcela principal e encargos já configurados | Cálculo pronto para liquidação |
| 10 | Operações > Liquidar | Executar a apuração final | Todas as páginas anteriores revisadas | Alertas e resumo do cálculo |
| 11 | Erros/Alertas, Imprimir, Exportar | Validar, gerar relatórios e exportar o cálculo | Liquidação concluída | Saída auditável e reaproveitável |

### 1.2 Regras de dependência que a máquina deve respeitar

O sistema ensina, pelas próprias aulas e pelos alertas de liquidação, que determinados módulos não podem ser tratados isoladamente. O **Histórico Salarial** não é acessório; ele sustenta verbas, FGTS e contribuição social. O **Cartão de Ponto** não produz crédito sozinho; ele produz quantidades que precisam encontrar verbas já compatíveis. A liquidação, por sua vez, não deve ser lida apenas como etapa final, mas como **teste de consistência estrutural do cálculo** [1] [2] [3] [4] [7].

| Dependência | Regra prática a ensinar | Origem |
|---|---|---|
| Histórico Salarial → Verbas | Não lançar verbas dependentes de base salarial sem histórico coerente | [Aula 1] [Aula 4] |
| Verba principal → Reflexos | Salvar a verba principal antes de expandir ou parametrizar reflexos | [Aula 2] |
| Alteração estrutural → Regerar | Mudanças de período, dobra, quantidade, divisor, multiplicador ou base exigem regeração | [Aula 2] [Aula 3] [Aula 4] |
| Parâmetros do Cálculo → Cenários especiais | Demissão, aviso prévio e maior remuneração alteram a lógica do cálculo por parcela | [Aula 1] [Vídeo complementar — Estabilidades] [Vídeo complementar — FGTS não depositado] |
| Liquidação → Validação | O relatório final deve ser lido para confirmar se a parametrização produziu o efeito jurídico pretendido | [Aula 4] [Vídeo complementar — Reflexos/Integração] [Vídeo complementar — FGTS não depositado] |

### 1.3 Tela Inicial, Tabelas e abertura do cálculo

A Tela Inicial funciona como ponto de entrada do fluxo. O vídeo geral reforça que a rotina adequada consiste em abrir o sistema, atualizar tabelas e só depois criar ou importar o cálculo. Essa ordem não é mero formalismo: as tabelas alimentam índices, verbas, faixas, feriados e outros elementos que repercutem nas páginas seguintes [1] [6].

| Item operacional | Conteúdo consolidado | Origem |
|---|---|---|
| Comandos iniciais demonstrados | **Criar novo cálculo**, **Buscar cálculo**, **Importar cálculo** | [Aula 1] [Vídeo complementar — Reforço geral] |
| Regra de ordem | Atualizar tabelas antes do primeiro cálculo ou antes de reutilizar ambiente desatualizado | [Vídeo complementar — Reforço geral] |
| Área adicional visível | Cálculos recentes, manual e tutorial | [Aula 1] |
| URL relativa | **[NÃO COBERTO NAS AULAS]** | [NÃO COBERTO NAS AULAS] |
| Mensagens literais de sucesso/erro | **[NÃO COBERTO NAS AULAS]** | [NÃO COBERTO NAS AULAS] |

### 1.4 Dados do Cálculo e Parâmetros do Cálculo

Essas páginas definem a moldura do cálculo. A máquina deve aprender que não basta inserir datas de modo mecânico; algumas situações exigem leitura jurídica do cenário para que a data informada no sistema produza o efeito esperado. O exemplo mais sensível vem do vídeo de estabilidade, em que a data real da demissão não é a data que deve constar no sistema para fins de cálculo dos consectários do período estabilitário [1] [10].

| Campo/decisão | Regra operacional ensinável | Origem |
|---|---|---|
| Nome do cálculo | Informar identificação clara do cálculo | [Vídeo complementar — FGTS não depositado] |
| Estado/Município | Preencher conforme localidade da prestação de serviços | [Vídeo complementar — FGTS não depositado] |
| Admissão, Demissão e Ajuizamento | Inserir marcos temporais do caso | [Aula 1] [Vídeo complementar — FGTS não depositado] |
| Maior Remuneração | Preencher sempre que o cenário exigir base rescisória ou base de parcelas específicas | [Aula 1] [Vídeo complementar — Estabilidades] |
| Aviso Prévio Indenizado / Projetar Aviso Prévio | Marcar ou desmarcar conforme o cenário efetivo; em FGTS não depositado e no exemplo de estabilidade, a opção permaneceu desmarcada | [Vídeo complementar — FGTS não depositado] [Vídeo complementar — Estabilidades] |
| Armadilha crítica em estabilidade | Em cálculo de período estabilitário, preencher o campo **Demissão** com a **data final da estabilidade**, e não com a data real da dispensa | [Vídeo complementar — Estabilidades] |

### 1.5 Histórico Salarial, Férias e bases auxiliares

A Aula 1 trata o Histórico Salarial como núcleo de bases do cálculo. O manual deve ensinar a máquina a reconhecer que, sem histórico coerente, o sistema perde suporte para horas extras, diferença salarial, FGTS e contribuição social. Também deve ensinar que páginas como **Férias** e **Faltas** podem influenciar bases, quantidades e reflexos, mesmo quando não são lançadas como verbas autônomas na grade principal [1] [4].

| Página/módulo | Função executável | Efeito sobre o cálculo | Origem |
|---|---|---|---|
| Histórico Salarial | Criar bases remuneratórias e editá-las por competência | Alimenta verbas, FGTS e CS | [Aula 1] |
| Férias | Informar períodos, dobra, abono e situações de gozo | Afeta bases, quantidades e incidências | [Aula 1] |
| Faltas | Ajustar ausências com impacto no cálculo | Pode alterar bases e quantidades | [Aula 1] |
| Regeração após mudanças estruturais | Recalcular ocorrências derivadas de parâmetros-base | Evita alertas na liquidação | [Aula 4] |

### 1.6 Verbas e reflexos

A página **Verbas** deve ser ensinada à máquina como ambiente de duas operações diferentes. A primeira é a criação da verba principal, seja pelo **Expresso**, seja pelo modo **Manual**. A segunda é a abertura da árvore ou da área correspondente para selecionar reflexos, parametrizar linhas específicas e, quando necessário, renomear verbas para tornar o cálculo auditável [2] [8] [9].

| Operação | Regra prática | Origem |
|---|---|---|
| Incluir verba pelo Expresso | Selecionar a rubrica pertinente, salvar e depois abrir seus parâmetros | [Aula 2] [Vídeo complementar — OJ 394] [Vídeo complementar — Reflexos/Integração] |
| Parametrizar verba | Ajustar base, período, proporcionalização e composição do principal | [Aula 2] [Vídeo complementar — Reflexos/Integração] |
| Marcar reflexos | Primeiro salvar a verba principal; depois expandir ou exibir reflexos e marcar somente os deferidos | [Aula 2] [Vídeo complementar — OJ 394] |
| Renomear verbas | Alterar o nome para separar verbas com efeitos diferentes e facilitar auditoria | [Vídeo complementar — OJ 394] [Vídeo complementar — Estabilidades] |
| Regerar | Usar quando alterações estruturais afetarem ocorrências | [Aula 2] [Aula 4] |

### 1.7 Cartão de Ponto como módulo de produção de quantidades

As aulas-base já mostravam a função do Cartão de Ponto, mas o vídeo complementar permitiu reconstruir um fluxo operacional completo. A máquina deve aprender que o cartão não é um relatório passivo; ele é um módulo de configuração da jornada, replicação das marcações ao longo do contrato, edição de exceções e posterior validação por espelho diário [2] [7].

| Etapa | Ação executável | Comportamento esperado do sistema | Origem |
|---|---|---|---|
| 1 | Entrar em **Cartão de Ponto** e clicar em **Novo** | Sistema cria um novo cartão e espelha datas contratuais no período | [Vídeo complementar — Cartão de Ponto] |
| 2 | Escolher o critério de apuração | Sistema passa a interpretar excedentes diários/semanais conforme a parametrização | [Vídeo complementar — Cartão de Ponto] |
| 3 | Definir jornada padrão e enquadramento noturno | Sistema incorpora regras de jornada e, se for o caso, redução ficta | [Vídeo complementar — Cartão de Ponto] |
| 4 | Preencher **Programação Semanal** | Grade semanal é replicada para todo o contrato | [Vídeo complementar — Cartão de Ponto] |
| 5 | Abrir **Grade de Ocorrências** | Sistema permite ajustes finos dia a dia ou mês a mês | [Vídeo complementar — Cartão de Ponto] |
| 6 | Salvar e voltar | Quantidades ficam aptas a alimentar verbas correlatas | [Vídeo complementar — Cartão de Ponto] |
| 7 | Imprimir apenas o espelho diário para validar | Sistema gera PDF com horas trabalhadas e excedentes | [Vídeo complementar — Cartão de Ponto] |

### 1.8 FGTS, Contribuição Social e módulos acessórios

Os módulos de FGTS e Contribuição Social são páginas próprias, com lógica própria de ocorrências e revisão. O manual deve ensinar a máquina a não tratá-los como reflexos invisíveis. Eles podem exigir edição mensal, revisão de parâmetros, regeração e conferência por relatório [3] [4] [11].

| Módulo | Regra de operação | Origem |
|---|---|---|
| FGTS | Preencher parâmetros, revisar ocorrências mensais, salvar e regerar quando necessário | [Aula 3] |
| FGTS não depositado | Marcar **Recolher** quando o valor for obrigação de depósito e não crédito líquido ao reclamante | [Vídeo complementar — FGTS não depositado] |
| Contribuição Social | Parametrizar bases, abrir ocorrências, editar e regerar conforme mudanças | [Aula 3] |
| Previdência Privada | Só liquidar se pelo menos uma verba tiver a incidência correspondente marcada | [Aula 3] [Aula 4] |
| Pensão Alimentícia | Aplicar apenas sobre as verbas previamente marcadas com essa incidência | [Aula 3] |

### 1.9 Liquidação, alertas, impressão e exportação

O fluxo final deve ser apresentado como etapa de **teste, saneamento e validação**. A liquidação não é um simples botão de encerramento: ela revela se faltam bases salariais, se módulos acessórios ficaram sem incidência de origem ou se ocorrências dependentes não foram regeradas [4].

| Subetapa | Ação ensinável | Finalidade prática | Origem |
|---|---|---|---|
| Operações > Liquidar | Executar o cálculo consolidado | Gerar resumo e alertas | [Aula 4] |
| Erros e Alertas | Ler criticamente cada aviso | Identificar ausência de base, incidência ou regeração | [Aula 4] |
| Imprimir | Selecionar relatórios pertinentes | Validar matemática e composição do cálculo | [Aula 4] [Vídeo complementar — Cartão de Ponto] [Vídeo complementar — Reflexos/Integração] |
| Exportar | Gerar arquivo do cálculo | Reaproveitar o trabalho em outro ambiente ou petição | [Aula 4] |

## SEÇÃO 2 — PARCELAS/VERBAS — CATÁLOGO COMPLETO COM FOCO OPERACIONAL

Esta seção foi redigida com uma orientação diferente da versão anterior. Além de indicar o que se sabe sobre cada verba, ela procura ensinar **como a máquina deve lançá-la, validá-la e evitar armadilhas operacionais**, especialmente quando os vídeos complementares trouxeram demonstrações concretas de preenchimento [2] [7] [8] [9] [10] [11]. Nas rubricas não efetivamente demonstradas, a ficha permanece conservadora.

### 2.1 Ficha técnica — Horas Extras (50%, 75%, 100%)

As horas extras aparecem nas aulas-base como resultado de jornada apurada no Cartão de Ponto e como rubrica suscetível a alertas por ausência de histórico salarial suficiente. O vídeo da OJ 394 complementa o tema ao mostrar como os reflexos do DSR devem ser tratados de forma temporalmente fatiada quando houver modulação jurisprudencial [2] [4] [7] [8].

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **Hora extra 50%** aparece nominalmente; 75% e 100% não foram mostradas nominalmente | [Aula 4] |
| DISPONÍVEL NO EXPRESSO | **[NÃO COBERTO NAS AULAS]** | [NÃO COBERTO NAS AULAS] |
| CONFIGURAÇÃO GERAL | Quantidades podem ser produzidas no **Cartão de Ponto** e depois vinculadas à verba na página **Verbas** | [Aula 2] [Vídeo complementar — Cartão de Ponto] |
| BASE DE CÁLCULO | Depende de histórico salarial coerente; ausência dessa base gera alertas | [Aula 4] |
| REFLEXOS TÍPICOS | DSR/RSR, 13º, férias, aviso e FGTS, conforme cenário e parâmetros | [Aula 2] [Vídeo complementar — OJ 394] |
| ARMADILHA | Falta de histórico salarial completo pode gerar alerta na liquidação | [Aula 4] |

A forma operacional de preenchimento deve ser ensinada à máquina em dois blocos. No primeiro bloco, ela precisa parametrizar a jornada que produzirá a quantidade. No segundo, ela precisa decidir como essa quantidade será juridicamente repercutida. Em cenário comum, isso significa lançar a verba principal, marcar os reflexos devidos e liquidar. Em cenário sujeito à OJ 394, isso significa separar a repercussão do DSR em dois regimes temporais distintos [7] [8].

| Passo operacional | Ação executável | Observação |
|---|---|---|
| 1 | Criar ou revisar o Histórico Salarial correspondente | Sem base salarial, a verba pode falhar ou alertar |
| 2 | Em **Cartão de Ponto**, clicar em **Novo** e parametrizar jornada, descansos e horário noturno | A quantidade nasce aqui | 
| 3 | Salvar a **Programação Semanal** e revisar a **Grade de Ocorrências** | Ajustar exceções reais |
| 4 | Em **Verbas**, criar a verba de horas extras ou revisar a existente | Integrar quantidade e base |
| 5 | Expandir a árvore de reflexos e marcar somente os reflexos deferidos | Evitar repercussões indevidas |
| 6 | Se houver modulação da OJ 394, limitar o reflexo de DSR até 19/03/2023 e criar DSR autônomo a partir de 20/03/2023 | Não misturar regimes antigos e novos |
| 7 | Regerar e liquidar | Validar consistência do cálculo |

### 2.2 Ficha técnica — Adicional Noturno (20%)

O adicional noturno não foi exibido em ficha autônoma completa, mas o corpus permite ensinar uma regra operacional central: sua produção quantitativa depende de parametrização correta do Cartão de Ponto, inclusive quanto ao enquadramento da atividade e à redução ficta da hora noturna [2] [7].

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **Adicional Noturno** | [Aula 2] |
| DISPONÍVEL NO EXPRESSO | **[NÃO COBERTO NAS AULAS]** | [NÃO COBERTO NAS AULAS] |
| CONFIGURAÇÃO | A quantidade é vinculada à jornada lançada no Cartão de Ponto | [Aula 2] [Vídeo complementar — Cartão de Ponto] |
| PARÂMETROS ESPECÍFICOS | Escolha do tipo de atividade e marcação da redução ficta da hora noturna | [Vídeo complementar — Cartão de Ponto] |
| ARMADILHA | Deixar de marcar a redução ficta da hora noturna compromete a apuração jurídica correta do período noturno | [Vídeo complementar — Cartão de Ponto] |

### 2.3 Ficha técnica — Diferença Salarial

A diferença salarial, que no material original aparecia apenas como rubrica citada em alerta, pôde ser significativamente complementada pelo vídeo específico sobre **cálculo apenas de reflexos**. O ponto essencial que a máquina deve aprender é que a verba principal pode existir matematicamente para alimentar os reflexos e, ainda assim, ser excluída do total devido ao reclamante por meio da alteração do campo **Compor Principal** para **Não** [4] [9].

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **Diferença Salarial** | [Aula 4] [Vídeo complementar — Reflexos/Integração] |
| DISPONÍVEL NO EXPRESSO | Demonstrada no vídeo complementar como verba localizada via **Expresso** | [Vídeo complementar — Reflexos/Integração] |
| TIPO DE VALOR | Valor devido informado e valor pago calculado, para formação da base diferencial | [Vídeo complementar — Reflexos/Integração] |
| BASE DE CÁLCULO | Combinação entre **Valor Informado** e base calculada do salário efetivamente pago | [Vídeo complementar — Reflexos/Integração] |
| COMPOSIÇÃO DO PRINCIPAL | Deve ser ajustada para **Não** quando a verba servir apenas de base para reflexos | [Vídeo complementar — Reflexos/Integração] |
| REFLEXOS TÍPICOS | 13º, férias, aviso, FGTS e demais reflexos deferidos no caso | [Vídeo complementar — Reflexos/Integração] |

A forma de preenchimento operacional dessa verba é uma das mais importantes para a automação. Primeiro a máquina cria a verba-base. Depois parametriza **Valor Devido** como valor informado e **Valor Pago** como calculado, mantendo coerência na proporcionalização. Em seguida, altera **Compor Principal** para **Não**, expande a árvore de reflexos, marca apenas os reflexos deferidos e usa o PDF do resumo para validar se a verba-base ficou segregada em quadro próprio, sem somar no crédito final [9].

| Armadilha | Efeito | Solução operacional |
|---|---|---|
| Proporcionalização assimétrica entre valor devido e valor pago | Reflexos negativos em meses quebrados | Marcar proporcionalização de forma idêntica nos dois lados |
| FGTS sem aparecer no resumo | Reflexo fundiário omitido | Marcar o checkbox específico do FGTS na linha da verba principal |
| Verba-base somando no crédito final indevidamente | Pagamento do principal quando só se queria o reflexo | Ajustar **Compor Principal** para **Não** |

### 2.4 Ficha técnica — Salários Retidos / Não Pagos

A rubrica não foi individualmente demonstrada nas aulas-base, mas o vídeo sobre estabilidade revelou um caminho operacional útil: o uso da verba **SALÁRIO RETIDO** como base para construção de um salário devido em período específico, posteriormente renomeado conforme o cenário. Isso permite ao manual ensinar ao menos uma forma concreta de operação com essa família de verba, embora não autorize generalizar todos os seus campos para hipóteses não demonstradas [10].

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA | **SALÁRIO RETIDO** foi demonstrada como verba-base reutilizável em cenário de estabilidade | [Vídeo complementar — Estabilidades] |
| DISPONÍVEL NO EXPRESSO | Sim, no vídeo complementar | [Vídeo complementar — Estabilidades] |
| USO OPERACIONAL DEMONSTRADO | Renomear para **SALÁRIO ESTABILIDADE** e ajustar o período de incidência | [Vídeo complementar — Estabilidades] |
| BASE DE CÁLCULO | **Maior Remuneração** | [Vídeo complementar — Estabilidades] |
| PROPORCIONALIZAR | Deve ser marcado para meses fracionados | [Vídeo complementar — Estabilidades] |
| OBSERVAÇÃO | O corpus não demonstra todas as variantes de salários retidos fora do cenário estabilitário | [NÃO COBERTO NAS AULAS] |

### 2.5 Ficha técnica — FGTS + multa de 40%

O material principal já demonstrava que o FGTS possui página própria, com parâmetros e ocorrências. O vídeo complementar sobre FGTS não depositado permitiu acrescentar uma distinção operacional central: há cenários em que o FGTS deve aparecer no cálculo apenas como **obrigação de recolher**, e não como parcela paga diretamente ao reclamante. Quanto à multa de 40%, o corpus não mostrou passo a passo completo do seu acionamento em tela própria, razão pela qual esse ponto permanece conservadoramente marcado quando faltar demonstração suficiente [3] [11].

| Campo exigido | Conteúdo consolidado | Origem |
|---|---|---|
| NOME DA VERBA/MÓDULO | **FGTS** em página própria | [Aula 3] |
| TIPO DE FLUXO | Não é apenas reflexo; possui módulo próprio com parâmetros e ocorrências | [Aula 3] |
| DEPÓSITOS JÁ RECOLHIDOS | Podem ser informados mês a mês para dedução | [Aula 3] |
| FGTS NÃO DEPOSITADO | Marcar **Recolher** para converter o valor em obrigação de depósito | [Vídeo complementar — FGTS não depositado] |
| VALIDAÇÃO EM RELATÓRIO | O resumo deve mostrar **FGTS**, **DEDUÇÃO DE FGTS** e seção **DEPÓSITOS FGTS** quando o cenário for de recolhimento | [Vídeo complementar — FGTS não depositado] |
| MULTA DE 40% | **[NÃO COBERTO NAS AULAS COM PASSO A PASSO SUFICIENTE]** | [NÃO COBERTO NAS AULAS] |

### 2.6 Ficha técnica — Férias e 13º no período estabilitário

Os vídeos complementares de estabilidade agregaram um ganho operacional expressivo ao manual, porque mostraram não apenas a existência das verbas, mas a forma concreta de ajustar períodos, avos e nomes em cenário de indenização substitutiva. Isso transforma férias e 13º do período estabilitário em exemplo privilegiado de preenchimento por parcela [10].

| Parcela | Forma de preenchimento operacional | Particularidade crítica | Origem |
|---|---|---|---|
| Salário-estabilidade | Criar a partir de **SALÁRIO RETIDO**, renomear, ajustar período do dia seguinte à dispensa real até o fim da estabilidade, basear na maior remuneração e marcar proporcionalização | A data de demissão do sistema deve coincidir com o fim da estabilidade | [Vídeo complementar — Estabilidades] |
| Férias do período estabilitário | Criar a verba **FÉRIAS**, renomear e lançar os avos manualmente na grade de ocorrências | O sistema exige contagem material dos meses/avos dentro da estabilidade | [Vídeo complementar — Estabilidades] |
| 13º do período estabilitário | Criar a verba **13º SALÁRIO**, renomear e lançar avos por ano civil nas ocorrências | O cálculo deve ser fracionado por exercício civil | [Vídeo complementar — Estabilidades] |

## SEÇÃO 3 — HISTÓRICO SALARIAL — OPERAÇÃO DETALHADA

O Histórico Salarial deve ser ensinado à máquina como o **módulo-base da base remuneratória**. Mesmo quando o corpus não demonstrou todos os labels internos com legibilidade absoluta, a lógica operacional ficou clara: é aqui que nascem as bases capazes de sustentar verbas, incidência de FGTS, contribuição social e cenários de diferença salarial ou recolhimento fundiário [1] [4] [9] [11].

| Item exigido no anexo | Conteúdo consolidado | Origem |
|---|---|---|
| Como criar um novo histórico | Há fluxo de criação de base histórica antes das verbas dependentes | [Aula 1] [Vídeo complementar — FGTS não depositado] |
| Campo Nome | Deve identificar a função da base, como **BASE DE FGTS** ou outra base remuneratória pertinente ao cenário | [Vídeo complementar — FGTS não depositado] |
| Tipo de valor informado vs calculado | O corpus não exibe integralmente essa página com todas as opções, mas demonstra bases fixas informadas e bases calculadas em verbas derivadas | [Vídeo complementar — Reflexos/Integração] [NÃO COBERTO NAS AULAS QUANTO À EXIBIÇÃO INTEGRAL DESTA PÁGINA] |
| Campo Valor | Foi demonstrado como valor mensal da base histórica no cenário de FGTS | [Vídeo complementar — FGTS não depositado] |
| Incidência no FGTS | Checkbox explicitamente mencionado na Aula 1 e operacionalizado no cenário de FGTS | [Aula 1] [Vídeo complementar — FGTS não depositado] |
| Incidência na CS | Checkbox explicitamente mencionado na Aula 1 | [Aula 1] |
| Grade de ocorrências | Existe e pode ser editada competência a competência | [Vídeo complementar — FGTS não depositado] |
| Múltiplos históricos e reajustes | **[NÃO COBERTO NAS AULAS COM PASSO A PASSO EXAUSTIVO]** | [NÃO COBERTO NAS AULAS] |

O ponto operacional mais importante que a máquina deve absorver é que o Histórico Salarial não é apenas um depósito de valores. Ele funciona como **fonte de verdade remuneratória**. Se essa fonte estiver incompleta, mal delimitada por período ou incoerente com a natureza da verba lançada, a liquidação tende a exibir alertas, especialmente em verbas como horas extras e diferença salarial [4] [9].

## SEÇÃO 4 — FGTS — CONFIGURAÇÃO COMPLETA

A página de FGTS deve ser tratada como módulo autônomo, dotado de parâmetros e ocorrências mensais próprias. O corpus principal já permitia afirmar isso. O vídeo complementar sobre FGTS não depositado acrescentou um cenário operacional completo, em que o sistema calcula o valor fundiário, mas o desloca do quadro de crédito líquido do reclamante para uma seção própria de depósitos a recolher [3] [4] [11].

| Item exigido no anexo | Conteúdo consolidado | Origem |
|---|---|---|
| Página FGTS | Existe página própria com bloco de parâmetros e grade de ocorrências mensais | [Aula 3] |
| Ocorrências do FGTS | Podem ser editadas para informar valores já recolhidos ou diferenças | [Aula 3] |
| Depósitos já recolhidos | Informados mês a mês para abatimento quando o cálculo tratar de diferenças | [Aula 3] |
| Salvar | Comando explicitamente mostrado/narrado | [Aula 3] |
| Regerar | Necessário quando alterações estruturais afetarem o período ou a base | [Aula 3] [Aula 4] |
| Checkbox **Recolher** | Deve ser marcado quando o FGTS é obrigação de depósito e não pagamento em pecúnia | [Vídeo complementar — FGTS não depositado] |
| Multa de 40% — passo a passo | **[NÃO COBERTO NAS AULAS COM SUFICIÊNCIA OPERACIONAL]** | [NÃO COBERTO NAS AULAS] |
| 13º no FGTS — passo a passo | **[NÃO COBERTO NAS AULAS]** | [NÃO COBERTO NAS AULAS] |

A rotina operacional do cenário de FGTS não depositado deve ser ensinada como fluxo fechado. Primeiro, a máquina preenche os Dados do Cálculo. Depois, cria uma base histórica específica, gera a grade mensal e deixa **FGTS Recolhido** desmarcado quando nada foi depositado. Em seguida, entra na aba **FGTS** e marca **Recolher**. Por fim, liquida e confere o resumo: o valor positivo do FGTS deve ser imediatamente compensado pela linha negativa **DEDUÇÃO DE FGTS**, e o total correspondente deve reaparecer em uma seção própria de **DEPÓSITOS FGTS**, com líquido do reclamante zerado quanto a essa rubrica [11].

## SEÇÃO 5 — CONTRIBUIÇÃO SOCIAL (INSS) — PARAMETRIZAÇÃO EXECUTÁVEL

A **Contribuição Social** deve ser ensinada à máquina como um módulo que converte parâmetros jurídicos e previdenciários em **ocorrências mensais editáveis**. A demonstração das aulas deixa claro que o sistema distingue **salários devidos** e **salários pagos**, admite parametrização de alíquotas e exige, em determinadas hipóteses, acesso à área de ocorrências seguido de **regeração** para consolidar o cenário efetivamente pretendido [3].

| Componente | Regra operacional ensinável | Origem |
|---|---|---|
| Base do segurado | Definir se a apuração será sobre salários devidos, pagos ou ambos, conforme o caso demonstrado | [Aula 3] |
| Base do empregador | Parametrizar alíquota por atividade econômica, por período ou de forma fixa | [Aula 3] |
| Cobrança do reclamante | Decidir se a cota do empregado será cobrada ou não | [Aula 3] |
| Ocorrências | Acessar a área própria para editar as bases mensais geradas | [Aula 3] |
| Alteração em lote | Usar quando a modificação atingir várias competências de forma uniforme | [Aula 3] |
| Regerar | Executar após mudança estrutural relevante nos parâmetros | [Aula 3] [Aula 4] |

O comportamento que a máquina deve aprender é o seguinte: primeiro parametriza-se a regra previdenciária. Depois inspecionam-se as **ocorrências** geradas. Em seguida, editam-se as bases se o caso concreto exigir ajuste fino. Por fim, salva-se e liquida-se novamente para validar se a contribuição apareceu coerentemente no resumo do cálculo. A máquina não deve presumir que a parametrização superior, sozinha, resolve todos os meses; as aulas mostram precisamente o contrário, isto é, a necessidade de revisão das competências geradas [3].

| Passo operacional | Ação executável | Verificação esperada |
|---|---|---|
| 1 | Entrar em **Contribuição Social** | Página previdenciária ativa |
| 2 | Definir bases e alíquotas | Regra geral de incidência montada |
| 3 | Acessar **Ocorrências** | Grade mensal disponível para revisão |
| 4 | Editar por lote ou linha a linha | Competências aderentes ao caso concreto |
| 5 | Regerar, se necessário | Parâmetros-base refletidos nas ocorrências |
| 6 | Liquidar e revisar o resumo | Encargo previdenciário consistente |

## SEÇÃO 6 — CORREÇÃO MONETÁRIA E JUROS — PARAMETRIZAÇÃO EXECUTÁVEL

A página **Correção, Juros e Multa** é uma das mais sensíveis para automação, porque nela a máquina deixa de apenas lançar fatos e passa a controlar a **temporalidade financeira do crédito**. As aulas-base e o vídeo específico sobre juros e correção mostram, de forma convergente, que o sistema separa **correção monetária** de **juros**, permite **combinar índices**, trabalha com **data de corte** e distingue a parametrização geral da parametrização específica por módulo ou categoria de verba [4] [5].

### 6.1 Estrutura lógica da página

| Área | Função executável | Origem |
|---|---|---|
| **Dados Gerais** | Definir regimes de correção, juros, combinação de índices e períodos sem incidência | [Aula 4] |
| **Dados Específicos** | Ajustar base dos juros e regras especiais para verbas e módulos acessórios | [Aula 4] |
| **Salvar** | Consolidar a parametrização antes de liquidar | [Aula 4] |

O ponto mais importante a ensinar é que a máquina não deve tratar juros e correção como sinônimos. O vídeo temático reforça que, em certos regimes, a fase pré-judicial pode usar **IPCA-E** para correção monetária e **TRD (juros simples)** para juros, ao passo que a fase posterior se associa à **SELIC** ou, em cenário mais recente, à composição **IPCA + taxa legal**, conforme o regime normativo escolhido [5].

### 6.2 Índices e regimes efetivamente demonstrados

| Regime/índice | Conteúdo operacional consolidado | Origem |
|---|---|---|
| Tabela Única da Justiça do Trabalho | Aparece como referência operacional sugerida na aula | [Aula 4] |
| IPCA-E | Demonstrado como índice utilizável na composição da correção monetária | [Aula 4] [Vídeo complementar — Juros/Correção] |
| TRD (juros simples) | Demonstrada no vídeo temático como componente da fase pré-judicial | [Vídeo complementar — Juros/Correção] |
| SELIC | Demonstrada como regime associado ao período posterior ao ajuizamento, conforme o cenário analisado | [Vídeo complementar — Juros/Correção] |
| IPCA + Taxa Legal | Demonstrado como lógica posterior no vídeo temático | [Vídeo complementar — Juros/Correção] |

### 6.3 Passo a passo executável para configuração

| Passo operacional | Ação executável | Armadilha a evitar |
|---|---|---|
| 1 | Entrar em **Correção, Juros e Multa** | Não liquidar com parâmetros padrão sem revisão |
| 2 | Em **Dados Gerais**, escolher o índice/regime principal | Não confundir correção monetária com juros |
| 3 | Se necessário, marcar a opção de combinar com outro índice | Não duplicar índices por sobreposição inadequada |
| 4 | Definir a data de corte quando houver mudança temporal de regime | Não deixar períodos híbridos sem marco definido |
| 5 | Em **Dados Específicos**, revisar a base dos juros e módulos especiais | Não presumir que todas as verbas usarão a mesma base automaticamente |
| 6 | Salvar | Sem salvar, a liquidação pode refletir parametrização antiga |
| 7 | Liquidar e inspecionar o relatório | Confirmar se a linha temporal jurídica foi respeitada |

### 6.4 Como a máquina deve validar o resultado

A validação não termina na tela de parâmetros. O comportamento correto é liquidar o cálculo e comparar o relatório final com a hipótese normativa escolhida. Se a parametrização buscava separar fases temporais, o resumo do cálculo e os demonstrativos devem evidenciar essa modulação. Se o cenário utilizava taxa legal combinada com outro índice, a máquina deve verificar se não ocorreu **dupla incidência de correção** sobre o mesmo período, risco expressamente destacado no vídeo temático [5].

| Critério de validação | O que conferir | Origem |
|---|---|---|
| Separação de fases | Existência de comportamento coerente entre pré e pós-ajuizamento | [Vídeo complementar — Juros/Correção] |
| Coerência entre juros e correção | Ausência de sobreposição indevida | [Vídeo complementar — Juros/Correção] |
| Compatibilidade com a liquidação | Resumo final refletindo a escolha feita na página | [Aula 4] |

## SEÇÃO 7 — ROTEIROS ESPECÍFICOS DE PREENCHIMENTO POR TEMA/PARCELA

O objetivo desta seção é transformar os pontos mais relevantes dos vídeos complementares em **rotinas diretamente executáveis pela máquina**. Em vez de apenas descrever a verba, o manual passa a indicar a sequência de páginas, decisões e verificações necessárias para reproduzir o resultado obtido no curso [7] [8] [9] [10] [11].

### 7.1 Roteiro executável — Cartão de Ponto, horas extras e adicional noturno

O vídeo específico de cartão de ponto mostrou um fluxo mais completo do que o apresentado no módulo principal. A máquina deve aprender que o cálculo de jornada nasce da combinação entre **programação semanal**, **ocorrências concretas**, **critérios de apuração** e **validação por espelho** [7].

| Ordem | Página/ação | Resultado operacional |
|---|---|---|
| 1 | Abrir **Cartão de Ponto** e clicar em **Novo** | Criação do cartão do período |
| 2 | Escolher o critério de apuração | Definição do modo de contabilização |
| 3 | Informar jornada padrão e descansos | Molde semanal do contrato |
| 4 | Ajustar parâmetro de adicional noturno e redução ficta, se cabível | Produção correta das horas noturnas |
| 5 | Gravar a **Programação Semanal** | Replicação do padrão no período |
| 6 | Revisar a **Grade de Ocorrências** | Correção de exceções reais |
| 7 | Salvar e imprimir o espelho do cartão | Validação visual da jornada apurada |
| 8 | Voltar a **Verbas** e conferir as rubricas dependentes de quantidade | Integração entre jornada e crédito |

### 7.2 Roteiro executável — Horas extras com modulação da OJ 394

O vídeo sobre a **OJ 394 da SDI-1 do TST** acrescenta um ensinamento operacional decisivo: em determinados períodos, o reflexo do DSR sobre horas extras deve ser tratado de forma distinta antes e depois do marco temporal considerado pelo instrutor. Por isso, a máquina deve abandonar a ideia de uma única verba genérica e trabalhar com **segmentação temporal e nominativa** [8].

| Ordem | Ação executável | Finalidade |
|---|---|---|
| 1 | Criar ou revisar a verba principal de horas extras | Formar a base da repercussão |
| 2 | Renomear a verba ou criar desdobramento temporal, se necessário | Segregar regimes distintos |
| 3 | Marcar reflexo em DSR apenas para o período anterior ao marco temporal | Respeitar a modulação indicada |
| 4 | Para o período posterior, criar o DSR como verba autônoma, se esse for o critério adotado | Evitar dupla repercussão |
| 5 | Salvar, regerar e imprimir relatório comparativo | Validar o fatiamento temporal |

### 7.3 Roteiro executável — Diferença salarial apenas para gerar reflexos

O vídeo de **reflexos/integração** oferece um dos melhores exemplos de como ensinar lógica de cálculo à máquina. A essência do procedimento é criar uma verba-base que existe para **produzir reflexos**, mas não para compor diretamente o principal do crédito [9].

| Ordem | Ação executável | Resultado esperado |
|---|---|---|
| 1 | Em **Verbas**, localizar **Diferença Salarial** no modo **Expresso** | Verba-base disponível |
| 2 | Parametrizar o **Valor Devido** como valor informado | Formação da base teórica devida |
| 3 | Parametrizar o **Valor Pago** como valor calculado ou equivalente demonstrado | Formação do diferencial |
| 4 | Marcar a proporcionalização de forma simétrica | Evitar distorções em meses fracionados |
| 5 | Alterar **Compor Principal** para **Não** | Impedir que a verba-base some ao crédito principal |
| 6 | Abrir os reflexos e marcar somente os deferidos | Fazer a verba-base repercutir |
| 7 | Marcar FGTS específico se o caso exigir | Permitir a repercussão fundiária |
| 8 | Liquidar e conferir o PDF-resumo | Confirmar que só os reflexos aparecem como devido líquido |

### 7.4 Roteiro executável — FGTS não depositado

O vídeo específico de **FGTS não depositado** ensina à máquina que nem todo valor apurado deve ser tratado como pagamento direto ao reclamante. Em certos cenários, a rubrica deve se converter em obrigação de **recolhimento** [11].

| Ordem | Ação executável | Resultado esperado |
|---|---|---|
| 1 | Preencher **Dados do Cálculo** com marcos contratuais e processuais | Estrutura do caso criada |
| 2 | Criar base no **Histórico Salarial** com incidência no FGTS | Competências aptas ao cálculo fundiário |
| 3 | Gerar ou revisar ocorrências mensais | Grade histórica pronta |
| 4 | Entrar em **FGTS** | Módulo fundiário ativo |
| 5 | Informar que nada foi recolhido, quando esse for o caso | Diferença integral preservada |
| 6 | Marcar **Recolher** | Conversão em obrigação de depósito |
| 7 | Salvar e liquidar | Resumo consolidado |
| 8 | Conferir se o líquido da verba ao reclamante ficou zerado e se surgiu a seção **DEPÓSITOS FGTS** | Validação do enquadramento jurídico correto |

### 7.5 Roteiro executável — Salário-estabilidade, férias e 13º do período estabilitário

O vídeo de **estabilidade gestante e acidentária** é particularmente importante porque mostra uma engenharia operacional completa: a máquina precisa reorganizar as datas do caso, reutilizar verbas conhecidas, renomeá-las e ajustar o cálculo para um período indenizatório que não coincide com a data real da dispensa [10].

| Ordem | Ação executável | Resultado esperado |
|---|---|---|
| 1 | Em **Parâmetros do Cálculo**, informar como data de demissão o final do período estabilitário | Estrutura temporal correta do cálculo |
| 2 | Ajustar **Maior Remuneração** e opções de aviso conforme o cenário mostrado | Base rescisória coerente |
| 3 | Em **Verbas**, inserir **SALÁRIO RETIDO** e renomear para **SALÁRIO ESTABILIDADE** | Parcela-base do período estabilitário |
| 4 | Definir período do dia seguinte à dispensa real até o fim da estabilidade | Delimitação temporal correta |
| 5 | Marcar proporcionalização | Ajuste de meses fracionados |
| 6 | Inserir **FÉRIAS** e **13º SALÁRIO**, renomeando para refletir o período estabilitário | Parcelas derivadas criadas |
| 7 | Lançar avos manualmente nas ocorrências, separando exercícios civis quando necessário | Cálculo anual e proporcional correto |
| 8 | Liquidar e conferir o resumo | Validação da indenização substitutiva |

## SEÇÃO 8 — LIQUIDAÇÃO, RELATÓRIOS, IMPRESSÃO E EXPORTAÇÃO

A etapa final precisa ser ensinada à máquina como **ciclo de fechamento e auditoria**. Não basta apertar o botão de liquidar; é preciso saber o que revisar antes, o que interpretar depois e quais relatórios comparar com a parametrização feita nas etapas anteriores [4] [7] [9] [10] [11].

### 8.1 Checklist executável antes de liquidar

| Item de controle | O que a máquina deve verificar | Origem |
|---|---|---|
| Históricos salariais completos | Todas as verbas dependentes de base devem encontrar suporte histórico suficiente | [Aula 4] |
| Incidências marcadas | Módulos como previdência privada, pensão, FGTS e reflexos exigem marcações de origem | [Aula 3] [Aula 4] |
| Ocorrências regeradas | Mudanças estruturais em verbas, FGTS e CS exigem regeração | [Aula 2] [Aula 3] [Aula 4] |
| Parâmetros de correção e juros salvos | Evitar liquidação com configuração antiga | [Aula 4] [Vídeo complementar — Juros/Correção] |
| Cartão de Ponto validado | Quantidades coerentes antes da liquidação das verbas correlatas | [Vídeo complementar — Cartão de Ponto] |

### 8.2 Passo a passo para liquidar

| Passo | Ação executável | Origem |
|---|---|---|
| 1 | Entrar em **Operações** | [Aula 4] |
| 2 | Selecionar **Liquidar** | [Aula 4] |
| 3 | Informar a data da liquidação | [Aula 4] |
| 4 | Escolher o critério de acumulação dos índices | [Aula 4] |
| 5 | Confirmar a liquidação | [Aula 4] |

### 8.3 Como interpretar erros e alertas

A máquina deve distinguir **alerta** de **erro impeditivo**. O alerta pode sinalizar peculiaridade ou incompletude, mas nem sempre bloqueia a liquidação. O erro impeditivo, por sua vez, exige retorno à página de origem, normalmente acessível por navegação assistida a partir da própria mensagem de erro [4].

| Situação | Causa típica demonstrada | Resposta operacional |
|---|---|---|
| Alerta em hora extra 50% | Falta de valor histórico em alguma ocorrência necessária | Voltar ao histórico salarial e completar a base |
| Alerta em diferença salarial | Base histórica insuficiente ou parametrização incompleta | Revisar a verba-base e as ocorrências vinculadas |
| Erro na previdência privada | Nenhuma verba marcada com a incidência necessária | Voltar a **Verbas** e marcar a incidência correspondente |
| Pendência de regeração | Verbas, FGTS ou CS alterados sem regerar | Executar **Regerar** e liquidar novamente |

### 8.4 Relatórios que a máquina deve conferir

| Relatório/saída | Finalidade de conferência | Origem |
|---|---|---|
| Resumo da liquidação | Verificar composição do principal, reflexos, deduções e encargos | [Aula 4] |
| Espelho do Cartão de Ponto | Validar jornada, horas extras e adicional noturno | [Vídeo complementar — Cartão de Ponto] |
| Resumo da verba de diferença salarial/reflexos | Confirmar que a verba-base não compôs o principal e apenas alimentou reflexos | [Vídeo complementar — Reflexos/Integração] |
| Resumo do FGTS | Confirmar saldo líquido ao reclamante versus depósitos a recolher | [Vídeo complementar — FGTS não depositado] |
| Resumo das verbas estabilitárias | Confirmar salário, férias e 13º do período estabilitário | [Vídeo complementar — Estabilidades] |

### 8.5 Exportação

A exportação deve ser ensinada como operação distinta da impressão. Imprimir gera relatórios legíveis para conferência ou juntada. Exportar gera o **arquivo do cálculo**, reaproveitável em outro ambiente com PJe-Calc instalado [4].

| Operação | Finalidade | Origem |
|---|---|---|
| Imprimir | Produzir relatório para auditoria humana e processual | [Aula 4] |
| Exportar | Gerar arquivo do cálculo para reaproveitamento | [Aula 4] |
| Distinção crítica | Exportar não substitui imprimir e imprimir não substitui exportar | [Aula 4] |

## SEÇÃO 9 — DICAS OPERACIONAIS, ARMADILHAS E TROUBLESHOOTING

As aulas e vídeos complementares mostram que a maior parte dos erros nasce menos de falha matemática e mais de **quebra de sequência lógica**. A máquina precisa aprender que o PJe-Calc funciona como sistema dependente de bases, incidências e ocorrências. Quando um desses três eixos falha, a liquidação revela a inconsistência [2] [3] [4] [7] [9] [10] [11].

### 9.1 Armadilhas gerais

| Armadilha | Consequência | Solução operacional |
|---|---|---|
| Lançar verba sem base histórica suficiente | Alertas e cálculo inconsistente | Completar o **Histórico Salarial** antes de liquidar |
| Alterar parâmetro estrutural sem regerar | Ocorrências antigas permanecem ativas | Regerar antes da nova liquidação |
| Marcar reflexos indiscriminadamente | Crédito final indevido ou duplicado | Selecionar apenas reflexos efetivamente deferidos |
| Não revisar o relatório final | Erro conceitual passa despercebido | Imprimir e confrontar com a tese do caso |
| Não segmentar regimes temporais | Mistura de critérios jurídicos incompatíveis | Criar verbas ou fases distintas quando necessário |

### 9.2 Armadilhas por tema específico

| Tema | Erro típico | Correção operacional |
|---|---|---|
| Cartão de Ponto | Programação semanal sem revisão de exceções | Editar a grade de ocorrências antes de usar os quantitativos |
| OJ 394 | Manter DSR reflexo em período que exige tratamento autônomo | Separar temporalmente as rubricas |
| Diferença salarial/reflexos | Esquecer de alterar **Compor Principal** | Ajustar para **Não** quando a verba servir apenas de base |
| FGTS não depositado | Liquidar como verba devida ao reclamante | Marcar **Recolher** e conferir a seção de depósitos |
| Estabilidade | Usar a data real da dispensa como data de demissão do cálculo | Ajustar para a data final do período estabilitário |

### 9.3 Itens exigidos pelo anexo que permanecem não cobertos com segurança suficiente

Este manual foi ampliado de forma relevante pelos novos vídeos, mas ainda subsistem pontos que o corpus analisado não demonstrou integralmente. Esses pontos devem permanecer marcados como não cobertos para preservar a confiabilidade documental do treinamento da máquina.

| Item | Situação |
|---|---|
| URLs internas das páginas | **[NÃO COBERTO NAS AULAS]** |
| Labels integrais de todos os campos do lançamento manual | **[NÃO COBERTO NAS AULAS]** |
| Texto literal de todas as mensagens de sucesso | **[NÃO COBERTO NAS AULAS]** |
| Passo a passo completo de todas as multas legais possíveis | **[NÃO COBERTO NAS AULAS]** |
| Parametrização integral da multa de 40% do FGTS em todos os campos | **[NÃO COBERTO NAS AULAS]** |
| Catálogo exaustivo de todos os selects do sistema | **[NÃO COBERTO NAS AULAS]** |

Com base nas orientações técnicas do vídeo sobre verbas rescisórias e na estrutura do seu manual operacional, aqui está a nova seção em Markdown projetada para o aprendizado de máquina e automação do preenchimento no PJe-Calc.

---

### SEÇÃO 10 — APURAÇÃO DAS VERBAS RESCISÓRIAS (ROTEIRO DE AUTOMAÇÃO)

Esta seção detalha o fluxo lógico e as regras de preenchimento para a automação das verbas rescisórias, utilizando as melhores práticas para que o sistema (ou a máquina) execute a apuração de forma fidedigna.

#### 10.1 Configurações Estruturais e Parâmetros-Base
A automação deve iniciar pela moldura do cálculo, pois os dados inseridos aqui alimentarão automaticamente as verbas rescisórias subsequentes.

| Campo Operacional | Ação de Automação / Regra de Preenchimento | Fonte |
| :--- | :--- | :--- |
| **Data de Admissão** | Inserir a data de início do vínculo. | |
| **Data de Demissão** | Preencher com o **último dia efetivamente trabalhado**. Não projetar o aviso prévio nesta data. | |
| **Data de Ajuizamento** | Inserir a data de protocolo da ação para fins de prescrição e juros. | |
| **Limitar Cálculo** | Definir como a data da liquidação ou "hoje" para permitir o cálculo de verbas posteriores à demissão (ex: Danos Morais). | |
| **Maior Remuneração** | **Campo Crítico:** Inserir o maior salário base fixo acrescido da média de variáveis. Este valor servirá de base automática para Aviso Prévio, Multa 477 e Férias Indenizadas. | |
| **Aviso Prévio** | Marcar "Projetar aviso prévio indenizado" se for o caso, para que o sistema projete reflexos em 13º e férias. | |

#### 10.2 Histórico Salarial e Faltas
A máquina deve alimentar o histórico antes de gerar as verbas para garantir que o 13º e o FGTS tenham base de cálculo.

*   **Regra de Ouro para Automação:** Preencher sempre o **salário mensal cheio** no histórico, mesmo no mês da demissão. O PJe-Calc fará a proporcionalização automática com base nos dias trabalhados (Saldo de Salário).
*   **Faltas e Férias Gozadas:** Devem ser lançadas nas telas específicas antes das verbas, pois impactam o cálculo de proporcionalidade das férias e das horas extras.

#### 10.3 Lançamento de Verbas via Menu "Expresso"
Para fins de automação, o uso do menu "Expresso" é recomendado pela agilidade, seguido do ajuste fino nas "Ocorrências".

| Verba | Parâmetro de Ajuste na Automação | Fonte |
| :--- | :--- | :--- |
| **Aviso Prévio Indenizado** | O sistema calcula automaticamente os dias (30 + 3 por ano). Baseia-se na "Maior Remuneração". | |
| **13º Salário** | Selecionar os anos devidos. O proporcional do ano da saída já inclui a projeção do aviso se configurado nos parâmetros. | |
| **Férias + 1/3** | Selecionar apenas as opções "Simples" e "Proporcional" conforme o caso. | |
| **Saldo de Salário** | Refere-se aos dias trabalhados no mês da saída. O sistema apura automaticamente pelos dias entre o dia 1º e a data de demissão. | |
| **Salário Retido** | Usado para meses inteiros não pagos anteriores à demissão. Requer ajuste manual do período nas ocorrências. | |

#### 10.4 FGTS e Multa de 40%
A automação deve tratar o FGTS em seu módulo próprio, e não apenas como reflexo.

1.  **Incidências:** No Histórico Salarial e nas Verbas Rescisórias (13º, Saldo de Salário, Salário Retido), o campo de incidência em FGTS deve estar marcado.
2.  **Dedução:** Se houver valores já depositados, a máquina deve inserir o valor total para dedução no campo "Valor Pago/Depositado" para evitar enriquecimento sem causa.
3.  **Multa de 40%:** Deve ser marcada sobre o "Valor Devido" (que inclui o que deveria ter sido depositado e o que foi calculado no processo).

#### 10.5 Multas Rescisórias (Arts. 477 e 467 da CLT)
*   **Multa Art. 477:** Baseada na "Maior Remuneração" cadastrada nos parâmetros iniciais.
*   **Multa Art. 467:** Na automação, esta verba deve ser configurada como **Verba Reflexa**. A máquina deve selecionar as verbas de natureza rescisória (Aviso Prévio, 13º Prop, Férias Prop/Simples e a própria Multa de 40% do FGTS) para que o sistema aplique os 50% sobre elas.

#### 10.6 Abatimento de Valores Pagos (TRCT)
Para automatizar o abatimento de valores já pagos na rescisão e evitar cálculos em duplicidade:
*   **Ação:** Criar uma **Verba Negativa** no menu Expresso (Valor Pago não tributável).
*   **Preenchimento:** Informar o valor total pago no TRCT no campo "Valor Pago" para que ele seja subtraído do montante final bruto.

#### 10.7 Checklist de Validação para Automação (Troubleshooting)
A máquina deve validar os seguintes pontos antes de finalizar:
*   **Regeração:** Sempre que alterar datas ou bases salariais, executar o comando "Regerar" nas verbas e no FGTS.
*   **Salário Família:** Verificar se o salário base ultrapassa o teto; caso positivo, a verba aparecerá zerada corretamente.
*   **Juros e Correção:** Aplicar a modulação da Lei 14.905 (IPCA-E na fase pré-judicial e SELIC/Taxa Legal na fase judicial conforme as datas de corte).


### SEÇÃO 11 — APURAÇÃO DE HORAS EXTRAS (PASSO A PASSO CONSOLIDADO)

Esta seção consolida as diretrizes para que a máquina execute a **automação completa do cálculo de horas extras**, desde a preparação do ambiente até a validação final dos reflexos e liquidação.

#### 11.1 Preparação e Configurações Iniciais
Antes de iniciar o lançamento das horas, a máquina deve garantir que as bases estruturais estejam corretas para evitar alertas de erro na liquidação.

1.   **Dados do Cálculo:** Preencher obrigatoriamente Admissão, Demissão, Ajuizamento e a Localidade (Estado/Município).
2.  **Histórico Salarial:** Criar o histórico salarial (ex: Salário Base) para todo o período contratual. **Sem base salarial, o sistema não consegue apurar o valor da hora extra**, gerando alertas críticos.

#### 11.2 Produção de Quantidades via Cartão de Ponto
A máquina deve entender que o **Cartão de Ponto** é o módulo onde as quantidades de horas extras são geradas antes de serem vinculadas a uma verba.

*   **Critério de Apuração:** Selecionar o critério determinado (geralmente horas extras acima da **8ª diária ou 44ª semanal**, pelo critério mais favorável).
*   **Programação Semanal:** Preencher o horário padrão de entrada, saída e intervalo (ex: 09:00 às 19:00 com 1h de intervalo). O horário de intervalo é necessário para que o sistema não o compute como jornada integral.
*   **Grade de Ocorrências:** Salvar a programação para que o sistema replique os horários automaticamente por todo o período.
*   **Apuração do Cartão:** Acessar "Visualizar Cartão" e clicar em **Apurar**. O sistema calculará mensalmente as horas excedentes com base nos parâmetros inseridos.

#### 11.3 Configuração e Parametrização da Verba
Após gerar as quantidades no cartão, a máquina deve configurar a rubrica financeira na página de **Verbas**.

1.  **Seleção da Verba:** Escolher a rubrica correspondente (ex: **Horas Extras 50%**).
2.  **Base de Cálculo:** Vincular o **Histórico Salarial** criado anteriormente. É necessário clicar no botão **"+" (verde)** para que o sistema salve a base; caso contrário, ocorrerá erro.
3.  **Importação de Quantidades:** No campo de quantidade, selecionar a opção **"Importar do Cartão de Ponto"** e indicar a coluna de horas extras apuradas. Novamente, deve-se clicar no **"+" (verde)** para confirmar a importação.
4.  **Multiplicador:** Validar se o multiplicador está correto (ex: 1.5 para 50% ou 2.0 para 100%).
5.  **Regeração:** Após salvar, a máquina deve sempre **Regerar** a verba para que o sistema processe a combinação entre base salarial e quantidades.

#### 11.4 Reflexos e Regimes Especiais
A máquina deve configurar as repercussões jurídicas das horas extras de forma criteriosa.

*   **Reflexos Típicos:** Marcar os reflexos deferidos, como **DSR/RSR, 13º Salário, Férias + 1/3, Aviso Prévio e FGTS (com multa de 40%, se houver)**.
*   **Modulação da OJ 394 (SDI-1 do TST):** Se houver determinação judicial para aplicar a modulação da OJ 394, a máquina deve:
    *   Marcar o reflexo em DSR apenas para o período até **19/03/2023**.
    *   Para o período a partir de **20/03/2023**, criar o DSR como verba autônoma ou conforme o novo regime de repercussão para evitar cálculos indevidos.

#### 11.5 Finalização e Validação
Para concluir a operação, a máquina deve seguir o ciclo de fechamento técnico.

1.  **Correção e Juros:** Configurar os parâmetros de ADC 58/59 (IPCA-E na fase pré-judicial e SELIC a partir do ajuizamento, ou conforme legislação vigente).
2.  **Liquidação:** Executar a liquidação informando a data base do cálculo.
3.  **Auditoria de Relatórios:** A máquina deve conferir no relatório de **"Resumo da Liquidação"** e no **"Espelho do Cartão de Ponto"** se as horas extras e seus reflexos foram apurados corretamente em cada competência.
4.  **Tratamento de Alertas:** Caso surja um alerta de **"Base de cálculo insuficiente"**, a máquina deve retornar ao Histórico Salarial e verificar se há valores lançados para todos os meses do período de apuração das horas extras.

Com base nas diretrizes do vídeo e nas informações estruturais do documento operacional, apresento a seção consolidada para a automação da apuração de **Adicional Noturno** e **Horas Extras Noturnas** no PJe-Calc.

---

### SEÇÃO 12 — APURAÇÃO DE ADICIONAL NOTURNO E HORAS EXTRAS NOTURNAS (ROTEIRO DE AUTOMAÇÃO)

Esta seção detalha o fluxo lógico para que a máquina execute o cálculo do adicional noturno e das horas extras noturnas de forma separada, evitando o *bis in idem* e garantindo a correta aplicação da redução ficta.

#### 12.1 Configuração Quantitativa no Cartão de Ponto
A automação deve primeiro gerar os quantitativos antes de criar as verbas financeiras.

| Passo | Ação de Automação | Regra de Preenchimento / Observação | Fonte |
| :--- | :--- | :--- | :--- |
| **1** | **Ativar Apuração Noturna** | No Cartão de Ponto, marcar os seletores: **"Apurar Horas Noturnas"** e **"Apurar Horas Extras Noturnas"**. | |
| **2** | **Definir Horário Noturno** | Para empregado urbano, configurar das **22:00 às 05:00**. | |
| **3** | **Redução Ficta** | Marcar obrigatoriamente a opção de **redução ficta da hora noturna** (considerando a hora de 52 minutos e 30 segundos). | |
| **4** | **Jornada Diária** | Configurar o campo superior como **"Jornada Diária"** para que o sistema identifique corretamente o que extrapola a jornada e incide em horário noturno. | |
| **5** | **Grade de Ocorrências** | Salvar e apurar para que o sistema gere as colunas separadas de horas noturnas totais e horas extras noturnas. | |

#### 12.2 Configuração das Verbas (Metodologia Recomendada)
A máquina deve evitar o uso do multiplicador 1,8 (que soma o adicional de 20% com o de 50% em uma única verba), pois isso pode gerar erro de cálculo se o adicional noturno não for calculado sobre todas as horas da noite. **A recomendação técnica é calcular as verbas de forma separada**.

##### A. Verba: Adicional Noturno (20%)
| Campo Operacional | Configuração para Automação | Fonte |
| :--- | :--- | :--- |
| **Seleção** | Criar a verba **Adicional Noturno 20%** via menu Expresso. | |
| **Importação** | No campo quantidade, selecionar **"Importar do Cartão de Ponto"** -> **"Todas as Horas Noturnas"**. | |
| **Incidência** | Garantir que a base de cálculo seja o salário base (Histórico Salarial). | |

##### B. Verba: Horas Extras Noturnas (50%)
| Campo Operacional | Configuração para Automação | Fonte |
| :--- | :--- | :--- |
| **Seleção** | Criar uma verba de **Hora Extra 50%** (ou a alíquota deferida). | |
| **Multiplicador** | **Ação Crítica:** Alterar o multiplicador de 1,5 para **1,6**. | |
| **Justificativa** | O uso de **1,6** ocorre porque o adicional noturno (0,2) já está sendo pago separadamente sobre todas as horas. Usar 1,8 geraria pagamento em duplicidade (*bis in idem*). | |
| **Importação** | No campo quantidade, selecionar **"Importar do Cartão de Ponto"** -> **"Horas Extras Noturnas"**. | |

#### 12.3 Reflexos e Incidências
A automação deve seguir a regra de integração das verbas noturnas nas demais parcelas.

1.  **Base de Cálculo:** Ambas as verbas devem estar vinculadas ao **Histórico Salarial** coerente.
2.  **Reflexos:** Marcar os reflexos em **DSR/RSR, 13º Salário, Férias + 1/3, Aviso Prévio e FGTS**.
3.  **Atenção:** O adicional noturno deve compor a base de cálculo das horas extras; ao utilizar a metodologia de multiplicador **1,6** e calcular o adicional à parte, o sistema já realiza essa integração sem gerar erros matemáticos.

#### 12.4 Checklist de Validação (Troubleshooting)
*   **Regeração:** Após configurar as importações do cartão e os multiplicadores, a máquina deve executar o comando **"Regerar"**.
*   **Conferência de Relatório:** No **"Espelho do Cartão de Ponto"**, validar se a soma de "Horas Noturnas" e "Horas Extras Noturnas" reflete a jornada real após a redução ficta.
*   **Evitar Erro Comum:** Não inserir o adicional noturno na base de cálculo da hora extra se estiver usando o multiplicador 1,8, pois isso causaria incidência tripla do adicional. A metodologia de **verba separada com multiplicador 1,6** é a mais segura para automação.

## Conclusão operacional

O material reestruturado permite ensinar à máquina, com base documental mais robusta do que a versão inicial, **como operar o PJe-Calc Cidadão do início ao fim** e **como preencher parcelas específicas com suas particularidades operacionais**. O fluxo geral agora aparece como sequência de dependências executáveis, e os vídeos complementares permitiram transformar temas antes apenas indicados em **rotinas concretas de preenchimento**, especialmente em **Cartão de Ponto**, **horas extras com modulação da OJ 394**, **diferença salarial calculada apenas para gerar reflexos**, **FGTS não depositado** e **parcelas do período estabilitário** [7] [8] [9] [10] [11].

Ao mesmo tempo, o documento preserva a postura de **precisão conservadora** exigida desde o início. Onde houve demonstração suficiente, o manual descreve a página, a sequência, a decisão e a forma de validação. Onde o corpus não mostrou com segurança o detalhe da interface, a informação permanece expressamente marcada como **[NÃO COBERTO NAS AULAS]**. Essa combinação entre **exequibilidade** e **cautela documental** torna o manual mais útil para automação responsável e também mais confiável como base futura de skill operacional do PJe-Calc.

Com base nas informações extraídas do vídeo e na estrutura necessária para um documento operacional de automação no PJe Calc, organizei a seção sobre o adicional de periculosidade em Markdown. 

Este guia consolida os critérios legais de cálculo, as configurações de parâmetros e as distinções fundamentais entre trabalhadores mensalistas e horistas.

---

Com base no conteúdo do vídeo do Professor Jorge Penna e na estrutura do manual operacional existente, apresento a nova seção consolidada para a automação da apuração do **Adicional de Insalubridade** no PJe-Calc.

---

##### SEÇÃO 13 — APURAÇÃO DO ADICIONAL DE INSALUBRIDADE (ROTEIRO DE AUTOMAÇÃO)
Esta seção detalha o fluxo lógico para que a máquina execute o cálculo do adicional de insalubridade. Diferente de outras parcelas, esta verba geralmente **dispensa a dependência de um histórico salarial prévio**, pois utiliza o **salário mínimo** (já alimentado pelas tabelas do sistema) como base de cálculo padrão.

###### 13.1 Configuração e Lançamento via Menu "Expresso"
A automação deve localizar a rubrica e definir o grau de exposição logo na entrada, pois o sistema ajusta o multiplicador automaticamente com base na escolha.

| Passo | Ação de Automação | Regra de Preenchimento / Observação | Fonte |
| :--- | :--- | :--- | :--- |
| **1** | **Localizar Verba** | Acessar **Verbas** > **Expresso** e buscar por "Adicional de Insalubridade". | |
| **2** | **Definir Grau** | Selecionar a alíquota conforme o deferimento: **10% (mínimo)**, **20% (médio)** ou **40% (máximo)**. | |
| **3** | **Período de Apuração** | Informar o intervalo exato em que o autor esteve exposto ao agente insalubre. | |
| **4** | **Base de Cálculo** | Manter a seleção padrão de **"Salário Mínimo"**. | |
| **5** | **Proporcionalizar** | **Marcar obrigatoriamente** este campo para que o sistema apure o valor correto em meses de admissão, demissão ou afastamentos. | |
| **6** | **Salvar** | Gravar a verba para habilitar a edição de parâmetros e reflexos. | |

###### 13.2 Parâmetros Específicos e Reflexos
Após salvar a verba principal, a máquina deve realizar ajustes finos nos multiplicadores e selecionar as repercussões jurídicas.

*   **Multiplicador e Quantidade:**
    *   O **multiplicador** será preenchido automaticamente pelo sistema (0.10, 0.20 ou 0.40) conforme a verba escolhida no Expresso.
    *   O campo **Divisor** deve ser mantido como **1**.
    *   A **Quantidade** deve ser sempre informada como **1**.
*   **Reflexos Deferidos:**
    *   A máquina deve expandir a árvore de reflexos e marcar: **13º Salário**, **Férias + 1/3** e **Aviso Prévio**.
    *   **Dica Estratégica para Automação:** Se a configuração for para o cálculo do autor, deve-se marcar também o reflexo sobre a **Multa do Art. 477 da CLT**, pois esta tem como base a remuneração total.

###### 13.3 Ciclo de Regeneração e Validação
Como o adicional de insalubridade é sensível a mudanças de período e tabelas de salário mínimo, o procedimento de validação é crítico.

1.  **Regerar Ocorrências:** Sempre que houver alteração no período de exposição ou nas datas do cálculo, a máquina deve clicar no ícone de **"Regerar"** (tiquinho/check na listagem) para atualizar a grade mensal.
2.  **Auditoria em "Ocorrências":** A máquina deve acessar a tela de ocorrências da verba para validar se o sistema está buscando corretamente o valor do salário mínimo da época e aplicando o multiplicador (ex: Salário Mínimo x 0.20).
3.  **Checklist de Liquidação:** Antes de finalizar, verificar se a verba não gerou alertas de "Base de cálculo insuficiente", embora isso seja raro para esta rubrica, já que ela utiliza a tabela interna de salários mínimos do PJe-Calc.

---
*Nota: Esta seção consolida as instruções do vídeo "Como apurar o adicional de insalubridade no PJECALC em 5 minutos" com a metodologia pedagógica de automação para máquinas estabelecida no documento operacional.*

___________

## 5. Apuração de Adicional de Periculosidade

A seção de periculosidade deve ser preenchida após o cadastro básico do processo (Reclamante, Reclamado e Períodos) e a alimentação do **Histórico Salarial**, que servirá de base de cálculo.

### 5.1. Conceito e Base de Cálculo
O adicional de periculosidade é destinado a trabalhadores expostos a inflamáveis, explosivos, energia elétrica, segurança pessoal/patrimonial e atividades em motocicleta.
*   **Alíquota:** 30%.
*   **Base de Cálculo:** Incide exclusivamente sobre o **salário base**, salvo categorias específicas com previsões em acordos coletivos.

### 5.2. Lançamento da Verba (Passo a Passo)
1.  **Acessar Menu:** Vá em `Verbas` > `Expresso`.
2.  **Selecionar Verba:** Escolha `Adicional de Periculosidade 30%` e clique em `Salvar`.
3.  **Configurar Parâmetros:** 
    *   Verifique se as **incidências** (FGTS, INSS, IRRF) estão corretas conforme a condenação.
    *   **Período:** Informe o período exato de direito à verba (pode ser o período total do contrato ou um intervalo específico).
4.  **Reflexos:** 
    *   Se o pagamento for habitual, selecione a opção `Exibir` (ao lado da verba) e clique em `Adicionar reflexos`.
    *   Os reflexos comuns incluem: **13º Salário, Aviso Prévio e Férias + 1/3**.

### 5.3. Tratamento Diferenciado: Mensalista vs. Horista/Diarista
A automação deve seguir uma lógica condicional dependendo da forma de remuneração do reclamante para o cálculo do Descanso Semanal Remunerado (DSR):

| Tipo de Salário | Tratamento do DSR na Periculosidade |
| :--- | :--- |
| **Mensalista** | **Não calcular DSR à parte.** O DSR já está embutido no salário mensal e, consequentemente, no valor apurado da periculosidade. |
| **Horista / Diarista** | **Calcular DSR separadamente.** É necessário apurar o adicional sobre as horas trabalhadas e, em seguida, gerar o reflexo em DSR. |

#### 5.3.1. Automação do DSR para Horistas
Caso o trabalhador seja horista, utilize o seguinte "hack" de configuração no PJe Calc:
1.  Selecione a verba `Repouso Remunerado Comissionista` no menu Expresso.
2.  Renomeie a verba para `DSR sobre Periculosidade`.
3.  **Configuração da Base:** A base de cálculo deste DSR deve ser o próprio valor apurado do `Adicional de Periculosidade`.
4.  **Fórmula:** 
    *   **Divisor:** Dias Úteis.
    *   **Multiplicador:** 1.
    *   **Quantidade:** Importada do calendário (repousos e feriados do mês).

### 5.4. Contribuições Sociais e Atualização
Para finalizar a apuração da verba:
1.  Acesse `Contribuição Social` > `Ocorrências` > `Regerar`.
2.  Selecione a **Atividade Econômica (CNAE)** correta para o cálculo do SAT/RAT e preencha as alíquotas de "Terceiros" se houver condenação.
3.  Em `Correção Monetária e Juros`, configure os índices conforme a decisão judicial (ex: IPCA-E, SELIC ou TR) e salve.

---


Com base nas diretrizes do vídeo e na estrutura pedagógica do seu manual operacional, aqui está a nova seção consolidada para a automação da apuração do **Intervalo Intrajornada** no PJe-Calc. Esta seção foi desenhada para ser inserida imediatamente após o passo a passo de horas extras, mantendo a coerência entre temas correlatos.

---

##### SEÇÃO 12 — APURAÇÃO DE INTERVALO INTRAJORNADA (ROTEIRO DE AUTOMAÇÃO)
Esta seção detalha o fluxo lógico para que a máquina identifique o regime jurídico aplicável e execute o cálculo da supressão do intervalo para repouso e alimentação.

###### 12.1 Regras de Decisão Operacional (Critérios de Apuração)
A máquina deve selecionar um dos três caminhos interpretativos abaixo, conforme determinado na sentença ou comando do cálculo:

| Cenário Jurídico | Opção de Automação no PJe-Calc | Efeito no Cálculo | Origem |
| :--- | :--- | :--- | :--- |
| **Integral (Pré-Reforma)** | Marcar **"Apurar supressão do intervalo integral"** | Paga 1h cheia se houver qualquer violação (trabalho > 6h) | |
| **Híbrido (Transição)** | Marcar **"Apurar supressão... conforme Parágrafo 4º do Art. 71 da CLT"** | Apura integral até 10/11/2017 e apenas o período suprimido após 11/11/2017 | |
| **Período Suprimido** | **Desmarcar** ambas as opções anteriores | Apura apenas os minutos faltantes para completar a hora mínima em todo o período | |

###### 12.2 Fluxo de Execução no Cartão de Ponto
A automação do intervalo ocorre dentro do módulo de jornada, pois o sistema precisa confrontar a jornada trabalhada com a pausa concedida.

1.  **Configuração da Jornada:** No **Cartão de Ponto**, informar o horário padrão (ex: 07:30 às 12:00 e 12:30 às 16:30). O sistema detectará automaticamente que o intervalo gozado foi de apenas 30 minutos.
2.  **Parâmetro de Horas:** A máquina deve assegurar que o empregado trabalhe mais de 6 horas diárias para que o sistema gere o direito ao intervalo mínimo de 1 hora.
3.  **Seleção do Critério:** Marcar ou desmarcar as opções de supressão integral ou conforme o Art. 71 §4º na tela de parâmetros do Cartão de Ponto, de acordo com a tabela da Seção 12.1.
4.  **Apurar:** Salvar a **Programação Semanal** e clicar em **Apurar**. O sistema criará uma coluna específica de "Intrajornada" na grade de ocorrências.

###### 12.3 Integração com a Grade de Verbas
Diferente das horas extras comuns, a quantidade apurada no cartão deve ser vinculada à rubrica indenizatória correspondente.

*   **Vincular Quantidade:** Na página de **Verbas**, criar a rubrica de Intervalo Intrajornada (ou similar) e selecionar a opção **"Importar do Cartão de Ponto"**, indicando a coluna de horas de intrajornada apuradas.
*   **Adicional:** O cálculo deve observar o acréscimo do adicional de horas extraordinárias (mínimo de 50%).
*   **Natureza Jurídica:** Após a reforma trabalhista (11/11/2017), a verba passa a ter natureza estritamente indenizatória.

###### 12.4 Checklist de Validação para a Máquina
*   **Regeração:** Após qualquer alteração no critério de apuração (integral vs. suprimido), a máquina deve **Regerar** o Cartão de Ponto e a Verba para atualizar os reflexos.
*   **Divisor de Águas:** Validar no relatório se, a partir de **13/11/2017** (primeira segunda-feira após a vigência da reforma), o sistema reduziu a apuração de 1h para apenas os minutos suprimidos, caso a opção híbrida tenha sido marcada.
*   **Exceções ao Sábado:** Verificar se em jornadas reduzidas (como sábados de 4h) o sistema corretamente **não apura** o intervalo de 1h, pois a jornada é inferior a 6h.

---
**Nota de Configuração:** O PJe-Calc permite realizar essa distinção temporal (antes e depois da reforma) em um único cartão de ponto, eliminando a necessidade de criar cartões duplicados para o mesmo contrato.

**Nota para Automação:** A máquina deve sempre validar se o campo `Histórico Salarial` está preenchido antes de salvar a verba, pois o PJe Calc utiliza o valor registrado no histórico para calcular automaticamente os 30% da periculosidade.

Para integrar as informações do vídeo do Professor Jorge Penna ao manual operacional, as novas seções devem ser inseridas logo após a **Seção 11 — Apuração de Horas Extras**, respeitando a lógica de dependência do sistema e o formato de passo a passo para automação por máquina.

Abaixo, apresento a consolidação das informações para as três novas subseções solicitadas:

---

### 11.6 — DOMINGOS LABORADOS EM DOBRO (PAGAMENTO DO DIA)
Esta subseção trata do pagamento do dia de repouso trabalhado como uma unidade (dia), e não como horas extras excedentes.

| Etapa | Ação Executável (Automação) | Particularidade/Regra de Preenchimento | Fonte |
| :--- | :--- | :--- | :--- |
| **1** | **Cartão de Ponto** | No novo cartão, marcar o seletor: **"Apurar Domingos Trabalhados"**. | |
| **2** | **Grade de Ocorrências** | Marcar apenas os domingos em que houve labor efetivo. | |
| **3** | **Verbas (Expresso)** | Localizar a verba, salvar e renomear para **"Domingo em Dobro"**. | |
| **4** | **Configuração da Base** | Utilizar o salário mensal do Histórico Salarial. | |
| **5** | **Parâmetro de Divisor** | **Ação Crítica:** Alterar o divisor para **30** (para apurar o valor de um dia de salário). | |
| **6** | **Multiplicador** | Definir como **2** (correspondente à dobra). | |
| **7** | **Importação** | No campo quantidade, selecionar **"Importar do Cartão de Ponto"** -> **"Repousos Trabalhados"** (em dias). | |

### 11.7 — FERIADOS LABORADOS EM DOBRO (PAGAMENTO DO DIA)
Trata-se da apuração do valor do dia do feriado trabalhado, seguindo a mesma lógica do divisor diário.

| Etapa | Ação Executável (Automação) | Particularidade/Regra de Preenchimento | Fonte |
| :--- | :--- | :--- | :--- |
| **1** | **Cartão de Ponto** | No cartão de ponto, marcar o seletor: **"Apurar Feriados Trabalhados"**. | |
| **2** | **Grade de Ocorrências** | Marcar os feriados calendários que foram laborados. | |
| **3** | **Verbas (Expresso)** | Localizar a verba e renomear para **"Feriado em Dobro"**. | |
| **4** | **Parâmetro de Divisor** | **Ação Crítica:** Manter o divisor em **30**. O sistema deve calcular o valor de um dia e dobrá-lo. | |
| **5** | **Multiplicador** | Definir como **2**. | |
| **6** | **Importação** | No campo quantidade, selecionar **"Importar do Cartão de Ponto"** -> **"Feriados Trabalhados"** (em dias). | |

### 11.8 — HORAS EXTRAS 100% (DOMINGOS E FERIADOS)
Diferente das seções anteriores, esta apura as **horas extras** prestadas especificamente nesses dias, utilizando o divisor da carga horária mensal.

| Etapa | Ação Executável (Automação) | Particularidade/Regra de Preenchimento | Fonte |
| :--- | :--- | :--- | :--- |
| **1** | **Cartão de Ponto** | Marcar os seletores: **"Extras aos Domingos Inseparáveis"** e **"Extras aos Feriados Inseparáveis"**. | |
| **2** | **Jornada no Repouso** | Configurar a jornada diária nesses dias (ex: 8 horas) para que o sistema identifique o que é hora extra. | |
| **3** | **Verbas (Expresso)** | Selecionar rubrica de Hora Extra e configurar o adicional para **100%**. | |
| **4** | **Parâmetro de Divisor** | **Ação Crítica:** Utilizar a **Carga Horária** (ex: 220 ou 180), pois o objetivo é descobrir o valor da hora extra, e não do dia. | |
| **5** | **Multiplicador** | Definir como **2** (salário hora x 2). | |
| **6** | **Importação** | Selecionar **"Importar do Cartão de Ponto"** -> **"Horas Extras em Repousos e Feriados"** (em horas). | |

---

### Resumo Comparativo para a Máquina (Diferenciação de Cálculo)
Para garantir que a automação não confunda as verbas, a máquina deve validar os seguintes critérios antes da liquidação:

*   **Domingos e Feriados em Dobro:** O sistema deve dividir a base por **30** e multiplicar pela quantidade de **dias** trabalhados.
*   **Horas Extras 100%:** O sistema deve dividir a base pela **carga horária (220/180)** e multiplicar pela quantidade de **horas** extraordinárias apuradas naqueles dias.
*   **Regeração:** Após configurar as importações do cartão e os multiplicadores, a máquina deve obrigatoriamente executar o comando **"Regerar"** para atualizar as ocorrências.


Com base no conteúdo do vídeo e na estrutura do seu manual operacional, apresento a nova seção consolidada para a automação da apuração do **Adicional de Transferência** no PJe-Calc.

Esta seção foi desenhada para integrar o fluxo de dependências do sistema, partindo da premissa de que o **Histórico Salarial** já deve estar preenchido para servir de base de cálculo.

---

### SEÇÃO 14 — APURAÇÃO DE ADICIONAL DE TRANSFERÊNCIA (ROTEIRO DE AUTOMAÇÃO)
Esta seção detalha o fluxo lógico para que a máquina execute o cálculo do adicional de transferência (25%), garantindo a integração com a base salarial e a correta parametrização dos reflexos deferidos.

#### 14.1 Ficha Técnica — Adicional de Transferência
| Campo exigido | Conteúdo consolidado | Origem |
| :--- | :--- | :--- |
| **NOME DA VERBA** | **Adicional de Transferência** | |
| **DISPONÍVEL NO EXPRESSO** | Sim | |
| **ALÍQUOTA PADRÃO** | 25% | |
| **BASE DE CÁLCULO** | Salário Base (vinculado ao Histórico Salarial) | |
| **REFLEXOS TÍPICOS** | 13º Salário, Férias, Aviso Prévio, FGTS e Multa de 40% | |
| **INCIDÊNCIAS** | INSS e FGTS (segue a sorte da verba principal) | |

#### 14.2 Roteiro Executável de Preenchimento
A máquina deve seguir esta sequência para garantir que a verba apurada reflita o título executivo e possua base de cálculo íntegra.

| Ordem | Página/Ação | Resultado Operacional / Regra de Preenchimento | Fonte |
| :--- | :--- | :--- | :--- |
| **1** | **Histórico Salarial** | Certificar que o **Salário Base** está preenchido para todo o período da transferência. | |
| **2** | **Verbas > Expresso** | Localizar e salvar a rubrica **Adicional de Transferência**. | |
| **3** | **Parâmetros da Verba** | Validar o percentual de **25%** e selecionar o período (conforme deferido ou todo o contrato). | |
| **4** | **Configurar Reflexos** | Marcar: 13º Salário, Aviso Prévio, Férias e Multa de 40%. | |
| **5** | **Ajuste de Férias** | **Ação Crítica:** Verificar se houve gozo de férias. Se o contrato teve apenas férias indenizadas, desmarcar o reflexo sobre "férias gozadas" para evitar erro de base. | |
| **6** | **FGTS** | Marcar a incidência de FGTS nos reflexos para que o sistema gere a parcela acessória automaticamente. | |
| **7** | **Regerar** | Executar o comando "Regerar" na listagem de verbas para consolidar a grade mensal. | |

#### 14.3 Checklist de Validação e Troubleshooting
A máquina deve validar os pontos abaixo antes de prosseguir para a liquidação final:

*   **Proporcionalização:** Garantir que o campo "Proporcionalizar" esteja marcado para que o sistema calcule corretamente os meses de início e fim da transferência (meses "quebrados").
*   **Base de Cálculo Insuficiente:** Se a liquidação gerar alerta de base insuficiente, a máquina deve retornar ao **Histórico Salarial** e conferir se o valor do salário base foi inserido nas competências exatas da transferência.
*   **Conferência em Relatório:** No relatório **"Resumo da Liquidação"**, a máquina deve validar se o adicional de 25% incidiu mensalmente sobre o salário base e se os reflexos (13º, férias, aviso e FGTS) aparecem proporcionalmente no cálculo.

---
*Nota: Esta seção utiliza como fonte o vídeo complementar "Como apurar o Adicional de Transferência no Pje Calc" e segue a metodologia de automação por dependência lógica estabelecida nas seções anteriores do manual.*


Com base nas orientações do vídeo do Professor Jorge Penna e na consolidação com os roteiros técnicos já existentes no manual operacional (Seções 2.3 e 7.3), apresento a nova seção estruturada para a automação da apuração de **Diferenças Salariais**.

Esta seção ensina a máquina a executar o cálculo para cenários de **equiparação salarial, desvio de função, reajustes de CCT (Convenção Coletiva) e complementação de salário mínimo**.

---

### SEÇÃO 15 — APURAÇÃO DE DIFERENÇAS SALARIAIS (EQUIPARAÇÃO, DESVIO, PISO E SIMILARES)

Esta seção detalha a metodologia de "histórico duplo" para apurar diferenças salariais de qualquer natureza, garantindo a incidência correta de encargos e reflexos sobre o montante diferencial.

#### 15.1 — Preparação das Bases (Configuração dos Históricos Salariais)
Diferente de outras verbas, a diferença salarial exige que a máquina crie dois suportes materiais no **Histórico Salarial** antes de lançar a rubrica.

| Histórico a Criar | Regra de Preenchimento para a Máquina | Impacto Operacional | Origem |
| :--- | :--- | :--- | :--- |
| **Salário Recebido** | Lançar o valor efetivamente pago. Marcar a **Contribuição Social como "Recolhida"**. | Altera a alíquota de INSS devida pelo reclamante no cálculo final. | |
| **Salário Devido** | Lançar o valor correto (ex: piso da CCT ou salário do paradigma). **Não marcar** CS ou FGTS neste campo. | Serve como base teórica para a apuração da diferença na verba. | |

#### 15.2 — Parametrização da Verba via Menu "Expresso"
Após estruturar os históricos, a máquina deve configurar a rubrica financeira para realizar a subtração automática dos valores.

1.  **Localizar Verba:** No menu **Verbas**, utilizar o **Expresso** para selecionar **Diferença Salarial**.
2.  **Identificação:** Renomear a verba para identificar a causa (ex: *Diferença Salarial - Equiparação Paradigma* ou *Diferença Salarial - Piso CCT*).
3.  **Configuração da Base (Valor Devido):** Selecionar o **Histórico Salarial do "Salário Devido"**. Marcar **"Proporcionalizar: Sim"** para garantir o cálculo correto em meses fracionados e férias.
4.  **Configuração do Valor Pago:** Selecionar o **Histórico Salarial do "Salário Recebido"**. Marcar **"Proporcionalizar: Sim"**.
5.  **Decisão de Crédito (Compor Principal):**
    *   Se o objetivo for o pagamento do valor da diferença: Manter **"Compor Principal: Sim"**.
    *   Se a diferença servir apenas como base de cálculo para outros reflexos: Alterar para **"Compor Principal: Não"**.
6.  **Incidências:** Marcar **Imposto de Renda, Contribuição Social e FGTS** sobre a diferença apurada.

#### 15.3 — Reflexos e Multas Rescisórias
A máquina deve configurar as repercussões jurídicas de forma exaustiva para evitar perdas financeiras no cálculo.

*   **Reflexos Típicos:** Exibir e marcar **13º Salário, Aviso Prévio e Férias + 1/3**.
*   **Multa do Art. 477 da CLT:** Marcar obrigatoriamente como reflexo da diferença salarial, uma vez que a base de cálculo da multa é a remuneração total e não apenas o salário base.
*   **FGTS e Multa de 40%:** A diferença apurada gera reflexo direto em FGTS. No módulo **FGTS**, a máquina deve garantir que a multa de 40% esteja marcada sobre o valor apurado.

#### 15.4 — Ciclo de Regeneração e Validação
Como esta verba depende da interação entre dois históricos e a grade de verbas, o ciclo de fechamento é obrigatório.

1.  **Regerar:** Após salvar a parametrização, a máquina deve executar o comando **"Regerar"** para que o sistema processe as ocorrências mensais baseadas na subtração dos históricos.
2.  **Auditoria de Valores:** No relatório de **"Resumo da Liquidação"**, validar se o sistema está deduzindo o valor pago do valor devido (ex: R$ 2.000,00 - R$ 1.350,00 = R$ 650,00 de diferença mensal).
3.  **Checklist de Contribuição Social:** Verificar se o sistema apurou apenas a diferença da contribuição social, considerando a nova alíquota gerada pela soma do salário pago com a diferença devida.

#### 15.5 — Armadilhas de Automação a Evitar
| Armadilha | Efeito Errado | Solução Operacional |
| :--- | :--- | :--- |
| Esquecer de marcar "Proporcionalizar" em um dos lados | Diferença negativa ou inflada em meses incompletos. | Marcar **"Proporcionalizar: Sim"** tanto na base quanto no valor pago. |
| Não marcar CS como recolhida no salário recebido | Cálculo duplicado de INSS sobre a base já paga. | Ativar o checkbox de recolhimento no **Histórico: Salário Recebido**. |
| Nome genérico da verba | Dificuldade em auditar o cálculo em casos de múltiplas diferenças. | Renomear especificando o paradigma ou a norma coletiva. |

---
*Nota: Esta seção consolida as diretrizes de "Cálculo de Diferenças" com os parâmetros de "Reflexos e Integração" do manual original.*

Com base nas diretrizes do vídeo e na estrutura técnica do seu manual operacional, organizei a nova seção para a automação da apuração de **Indenização por Danos Morais** no PJe-Calc. Como o documento original mencionava apenas brevemente a necessidade de ajustar a data de liquidação para comportar essa verba, esta seção consolida o passo a passo completo para o preenchimento e parametrização.

---

##### SEÇÃO 16 — APURAÇÃO DE INDENIZAÇÃO POR DANOS MORAIS (ROTEIRO DE AUTOMAÇÃO)
Esta seção detalha o fluxo lógico para que a máquina execute o cálculo da indenização por danos morais, focando na definição da época própria e no controle da **Súmula 439 do TST** para alinhar os juros e a correção monetária à coisa julgada.

###### 16.1 Configurações Estruturais e Época Própria
Diferente das verbas trabalhistas típicas, o dano moral possui uma **época própria específica** que a máquina deve respeitar para evitar erros de cálculo.

| Parâmetro | Regra de Preenchimento / Ação de Automação | Fonte |
| :--- | :--- | :--- |
| **Época Própria** | Deve ser a **data em que o dano moral foi arbitrado** (data da sentença ou do acórdão que fixou o valor). | |
| **Data Final (na Verba)** | Inserir a data do arbitramento ou a data de hoje. O sistema exige o preenchimento para evitar erros de lançamento. | |
| **Referência Temporal** | O dano moral não se vincula à data do desligamento ou da prestação de serviço, mas sim à decisão judicial. | |

###### 16.2 Lançamento da Verba e Controle da Súmula 439
A automação deve realizar o ajuste no seletor da Súmula 439 conforme a determinação da sentença para definir o termo inicial dos juros.

| Cenário de Decisão (Coisa Julgada) | Ação de Automação no PJe-Calc | Efeito Jurídico/Financeiro | Fonte |
| :--- | :--- | :--- | :--- |
| **Juros a partir do Arbitramento** | **Desmarcar** o checkbox da Súmula 439. | Os juros e a correção (SELIC) contarão apenas da data da decisão. | |
| **Juros a partir do Ajuizamento** | **Manter marcada** a Súmula 439. | Os juros retroagirão à data do protocolo da ação, conforme o Art. 883 da CLT. | |

###### 16.3 Critérios de Atualização e Juros (Lei 14.905)
A máquina deve aplicar a lógica de atualização financeira observando os marcos legais de transição.

*   **Fase Judicial:** Utilizar a **SELIC** (Receita Federal) até 29/08/2024.
*   **Novo Regime (Lei 14.905):** A partir de **30/08/2024**, aplicar a combinação de **IPCA + Taxa Legal**.
*   **Aplicação de Ofício:** A atualização conforme a Lei 14.905 deve ser apurada de ofício pela máquina, preenchendo a brecha das ADCs 58 e 59.

###### 16.4 Checklist de Validação para a Máquina
1.  **Conferência da Época Própria:** Validar se a data inserida na verba corresponde exatamente ao dia da publicação da decisão que quantificou o prejuízo.
2.  **Validação de Juros:** Se a SELIC acumulada for de aproximadamente 15% (juros do ajuizamento) versus 7-8% (juros do arbitramento), confirmar se o checkbox da Súmula 439 está condizente com o comando da sentença.
3.  **Regeração:** Após configurar o valor e a data do arbitramento, a máquina deve executar o comando **"Regerar"** para consolidar a grade de juros e correção.
4.  **Resumo da Liquidação:** Verificar se a linha de juros da verba de dano moral apresenta a data correta (ajuizamento vs. arbitramento) conforme a parametrização adotada.

---

**Nota para Automação:** A máquina não precisa apurar o dano moral como "multa" para forçar os juros do arbitramento; basta o controle operacional de **marcar ou desmarcar a Súmula 439** dentro da aba da própria verba no PJe-Calc.

Com base nas informações do vídeo e na estrutura do manual operacional, apresento a nova seção consolidada para a automação da apuração de **Indenização por Danos Materiais (Pensionamento Mensal)**. 

Esta seção deve ser inserida como um roteiro de automação, diferenciando o tratamento de parcelas vencidas e vincendas, e ajustando os parâmetros de juros para garantir o cálculo decrescente exigido por lei.

---

##### SEÇÃO 17 — INDENIZAÇÃO POR DANOS MATERIAIS (PENSIONAMENTO MENSAL)
Esta seção detalha o fluxo lógico para que a máquina execute o cálculo de pensões mensais decorrentes de danos materiais, distinguindo as parcelas já vencidas daquelas que vencerão no futuro (vincendas).

###### 17.1 Configurações Iniciais e Diferenciação de Prazos
Diferente das verbas contratuais, o marco inicial do pensionamento é a **data do dano** e não a data de admissão.
*   **Data Inicial:** Inserir a data do evento danoso conforme definido em sentença.
*   **Divisão de Parcelas:** A máquina deve identificar se a apuração engloba parcelas **vencidas** (do dano até a data do cálculo) ou **vincendas** (parcelas futuras a serem pagas antecipadamente).

###### 17.2 Roteiro de Automação — Parcelas Vencidas (Mensais)
Para as parcelas que já deveriam ter sido pagas, o sistema deve apurar o valor mensal atualizado com juros decrescentes.

| Passo | Ação de Automação | Regra de Preenchimento / Observação | Fonte |
| :--- | :--- | :--- | :--- |
| **1** | **Localizar Verba** | Acessar **Verbas > Expresso** e selecionar **Indenização por Dano Material**. | |
| **2** | **Período** | Informar da **data do dano** até a **data da liquidação**. | |
| **3** | **Valor** | Inserir o valor fixado (ex: R$ 1.000,00) ou percentual do salário. | |
| **4** | **Súmula 439 TST** | **Desmarcar** o checkbox da Súmula 439 (Danos Materiais). | |
| **5** | **Proporcionalizar** | Marcar "Sim" para ajustar meses fracionados no início/fim do período. | |

> **Nota Crítica para Automação:** Ao desmarcar a Súmula 439, a máquina garante que o **Juro de Mora seja decrescente**. Isso significa que a parcela que venceu há dois anos terá mais juros do que a que venceu há dois meses, evitando a aplicação linear desde o ajuizamento para todas as parcelas.

###### 17.3 Roteiro de Automação — Parcelas Vincendas (Pagamento Antecipado)
Se o juiz determinar o pagamento imediato de parcelas futuras (lucros cessantes/pensão em cota única), a máquina deve aplicar um **redutor de valor presente**.

1.  **Cálculo do Valor Presente:** Antes de inserir no PJe-Calc, a máquina deve calcular o valor atualizado das parcelas futuras para evitar enriquecimento sem causa.
    *   **Opção A (Redutor Fixo):** Aplicar um desconto direto (comumente 30%) sobre o total das parcelas.
    *   **Opção B (Fórmula Financeira):** Utilizar a fórmula de **Valor Presente (PV)**: `PV(taxa; nper; pgto)`, onde a taxa costuma ser a da poupança (ex: 0,5% a.m.).
2.  **Lançamento no PJe-Calc:**
    *   Criar nova verba de **Dano Material**.
    *   No campo **Valor**, inserir o montante já reduzido (Valor Presente).
    *   Informar a **data da liquidação** em ambos os campos de data (inicial e final) para que o sistema trate como valor único atual.

###### 17.4 Configuração de Juros e Correção Monetária
Para que a evolução dos juros ocorra corretamente na planilha de pensionamento mensal:
*   **Juros Simples:** No menu **Correção, Juros e Multa**, validar se os juros estão configurados como "Simples" (ou conforme a SELIC atual) para permitir a regressão mensal nas parcelas vencidas.
*   **Regeneração:** Após qualquer alteração no período de pensionamento, a máquina deve **Regerar** a verba para atualizar a grade de vencimentos mensais.

###### 17.5 Checklist de Validação (Troubleshooting)
*   **Conferência de Juros:** No relatório impresso, verificar se a coluna de juros apresenta **percentuais decrescentes** mês a mês (ex: 21%, 20%, 19...).
*   **Diferença de Danos Morais:** Validar que, diferentemente da Seção 16 (Danos Morais), os danos materiais por pensionamento **não** devem ter os juros calculados integralmente desde o ajuizamento, mas sim do vencimento de cada cota mensal.
*   **Limitação do Cálculo:** Verificar se a data final do pensionamento respeita os limites da sentença (ex: até completar 60 anos ou expectativa de vida).

--- 
*Nota: Esta seção consolida as instruções do vídeo "Como calcular pensão no PjeCalc" com os parâmetros de automação já estabelecidos nas Seções 1, 4 e 16 do manual operacional.* Acknowledge: Uma nova seção de apuração de indenização por danos materiais foi criada com base nas fontes fornecidas.


##### SEÇÃO 18 — APURAÇÃO DE ACÚMULO DE FUNÇÃO (PLUS SALARIAL)

Esta seção detalha o fluxo lógico para que a máquina execute a apuração do **plus salarial decorrente de acúmulo de função**, consolidando a metodologia de cálculo percentual sobre base fixa com as diretrizes de diferenças salariais já estabelecidas no manual. Diferente do desvio de função, que pode exigir histórico duplo, o acúmulo é tratado como uma **porcentagem apurada sobre uma base de cálculo específica** (geralmente o salário da função principal).

###### 18.1 Preparação e Configurações Iniciais
A automação deve garantir que o suporte material para a verba esteja configurado antes do lançamento da rubrica financeira.
*   **Histórico Salarial:** A máquina deve verificar se o **salário da função principal** (ex: porteiro) está lançado no histórico, pois ele servirá de base para a incidência do percentual.
*   **Período de Acúmulo:** Identificar nos parâmetros do cálculo ou na sentença o intervalo exato em que as funções foram acumuladas para delimitação da verba.

###### 18.2 Roteiro Executável de Preenchimento (Menu Expresso)
A máquina deve seguir a sequência abaixo para configurar a diferença salarial como um plus percentual.

| Passo | Ação de Automação | Regra de Preenchimento / Observação | Fonte |
| :--- | :--- | :--- | :--- |
| **1** | **Localizar Verba** | Acessar **Verbas > Expresso** e selecionar **Diferença Salarial**. | |
| **2** | **Renomear Verba** | Alterar o nome para **"Plus Salarial por Acúmulo de Função"** para facilitar a auditoria. | |
| **3** | **Período** | Informar o período inicial e final em que houve o acúmulo. | |
| **4** | **Incidências** | Marcar obrigatoriamente a incidência de **FGTS** (e demais conforme a condenação). | |
| **5** | **Base de Cálculo** | Buscar o **Histórico Salarial** do reclamante. Marcar **"Proporcionalizar: Sim"**. | |
| **6** | **Configurar Divisor** | Manter ou definir o divisor como **1**. | |
| **7** | **Multiplicador** | Inserir o percentual do plus (ex: **0,3** para 30% ou **0,4** para 40%). | |
| **8** | **Quantidade** | Definir a quantidade como **1**. | |
| **9** | **Valor Pago** | **Ação Crítica:** Manter este campo em branco (ou zero). Não deduzir nada, pois apura-se apenas a proporção diferencial. | |

###### 18.3 Reflexos e Regeração
Após salvar a parametrização do principal, a máquina deve configurar as repercussões nas demais parcelas do contrato.
1.  **Exibir Reflexos:** Acessar a árvore de reflexos da verba de acúmulo de função.
2.  **Seleção de Reflexos:** Marcar apenas os reflexos deferidos em sentença (ex: **13º Salário, Férias + 1/3, Aviso Prévio e FGTS**).
3.  **Regerar:** Executar o comando **"Regerar"** para que o sistema processe o cálculo da diferença mensal sobre a base histórica.

###### 18.4 Checklist de Validação e Troubleshooting
*   **Base de Cálculo Insuficiente:** Caso a liquidação gere alerta, a máquina deve retornar ao **Histórico Salarial** e confirmar se há valores para todo o período do acúmulo.
*   **Compor Principal:** Garantir que esta opção esteja como **"Sim"**, a menos que o título executivo determine que o acúmulo sirva apenas para base de outros reflexos sem pagamento do principal.
*   **Proporcionalização:** Validar se a marcação de proporcionalização está ativa para evitar valores cheios em meses de início ou fim de contrato.
*   **Conferência em Relatório:** No relatório de **"Resumo da Liquidação"**, confirmar se o sistema aplicou o multiplicador (ex: 0,3) sobre o valor do salário base em cada competência.

Com base nas orientações do vídeo e nas diretrizes fornecidas, organizei a seção de **Apuração de Honorários Advocatícios** para o documento operacional em Markdown. Este guia consolida o passo a passo técnico do sistema com as regras de negócio específicas para a automação.

---

### **8. Apuração de Honorários Advocatícios**

Esta seção descreve o procedimento para a configuração e cálculo dos honorários advocatícios no PJe Calc, devendo a automação seguir rigorosamente os parâmetros extraídos da sentença (arquivo JSON).

#### **8.1. Configuração Inicial**
1.  **Acesso:** No menu lateral do PJe Calc, clique na aba **Honorários**.
2.  **Novo Registro:** Clique no botão **Novo** para gerar uma nova verba de honorários.
3.  **Descrição:** Manter o padrão "Honorários Advocatícios" ou conforme especificado em sentença.
4.  **Tipo de Valor:** Selecionar a opção **Calculado**.
    *   *Nota:* Somente utilizar "Informado" caso o juiz tenha determinado um valor fixo específico, o que não é a regra geral.

#### **8.2. Definição de Alíquotas e Devedores**
O sistema deve preencher **rigorosamente** o percentual (alíquota) descrito na sentença, que geralmente varia entre 5% e 20%.

*   **Sucumbência Total:**
    *   **Devedor:** Definir como **Reclamado** (se a procedência for total) ou **Reclamante** (se a improcedência for total).
    *   **Alíquota:** Conforme determinado no título executivo.
*   **Sucumbência Recíproca:**
    *   Devem ser gerados dois registros de honorários distintos (um para o advogado do reclamante e outro para o do reclamado).
    *   **Base de Cálculo:** Em casos de sucumbência recíproca, a **base de cálculo para ambas as partes deve ser a mesma**.
    *   Se a base de cálculo for a condenação, deve-se selecionar obrigatoriamente a opção **Bruto** (Condenação Bruta).

#### **8.3. Base de Apuração e Credores**
1.  **Base de Apuração:** Selecionar a opção **Bruto devido ao reclamante**.
    *   *Evitar:* As opções de "Bruto devido ao reclamante + outros débitos do reclamado" a menos que expressamente determinado.
2.  **Credor:** Preencher os dados do advogado beneficiário.
3.  **Imposto de Renda:**
    *   A opção **Apurar Imposto de Renda** deve ser marcada apenas se houver orientação para retenção na fonte.
    *   Caso marcada, o preenchimento do **CPF/Documento Fiscal** torna-se obrigatório para a liquidação.

#### **8.4. Parâmetros Específicos e Justiça Gratuita**
Caso o processamento dos dados da sentença (via arquivo JSON) identifique que o **Reclamante é beneficiário da justiça gratuita**, a automação deve realizar o seguinte procedimento adicional:

1.  Navegar até a aba **Dados do Cálculo**.
2.  Acessar a sub-aba **Parâmetros do Cálculo**.
3.  No campo **Comentários**, inserir obrigatoriamente o texto:
    > *"SUSPENSA A EXIGIBILIDADE DA COBRANÇA DOS HONORÁRIOS DEVIDOS PELA PARTE BENEFICIÁRIA DA GRATUIDADE JUDICIÁRIA, POR FORÇA DO ART. 791-A, §4º DA CLT E ADI 5.766."*

#### **8.5. Finalização e Liquidação**
1.  Após o preenchimento, clicar em **Salvar**.
2.  Prosseguir para a aba **Operações** e clicar em **Liquidar**.
3.  Verificar se não há erros impeditivos e clicar em **Imprimir** para conferir o valor gerado na planilha de liquidação (Honorários Líquidos).


19. CUSTAS PROCESSUAIS
1 . ESCOLHER SEMPRE A BASE DE CÁLCULO "BRUTO DEVIDO AO RECLAMANTE"

## Referências

[1]: https://www.youtube.com/watch?v=TniyaPlJt9U "PJe CALC/2017 - MODULO 01 - AULA 01 de 04"
[2]: https://www.youtube.com/watch?v=opaU2zKjbnI "PJe CALC/2017 - MODULO 01 - AULA 02 de 04"
[3]: https://www.youtube.com/watch?v=MHKzBolmcsM "PJe CALC/2017 - MODULO 01 - AULA 03 de 04"
[4]: https://www.youtube.com/watch?v=NGxE9HGAPqA "PJe CALC/2017 - MODULO 01 - AULA 04 de 04"
[5]: https://www.youtube.com/watch?v=S7njnTou56A "Guia definitivo dos juros e correção monetária no PJe-Calc"
[6]: https://www.youtube.com/watch?v=6BzfYWsWs8s "PJe-Calc 2.8.0: do zero ao primeiro cálculo"
[7]: https://youtu.be/Qnr022uxsWM?si=qgxHTi1Uv43jbB5Z "Vídeo complementar sobre Cartão de Ponto"
[8]: https://youtu.be/hzLS9MkITOY?si=9nKwYRSg75zd71r7 "Vídeo complementar sobre OJ 394 da SDI-1 do TST"
[9]: https://youtu.be/C4aDET4v-QE?si=PzA2mEipFSBP4U_R "Vídeo complementar sobre cálculo apenas de reflexos e integração de verba ao salário"
[10]: https://youtu.be/_ljWabRrFJ0?si=2YOPkgLcraM43FGG "Vídeo complementar sobre estabilidade gestante e acidentária"
[11]: https://youtu.be/8p31fdWzQ7s?si=GhCKNH0A6dRw-5Pd "Vídeo complementar sobre FGTS não depositado"
