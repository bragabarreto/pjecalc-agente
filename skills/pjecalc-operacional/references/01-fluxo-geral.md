# Fluxo Geral do Sistema PJe-Calc
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

O fluxo geral do PJe-Calc deve ser ensinado à máquina como **sequência obrigatória de dependências**, e não como simples visita a telas. O sistema tolera alguma navegação livre, mas o cálculo só se sustenta quando as bases estruturais são lançadas antes das verbas dependentes e quando as operações finais somente são executadas após revisão das incidências, das ocorrências e dos parâmetros de período [Aula 1] [Aula 2] [Aula 3] [Aula 4] [Vídeo complementar — Reforço geral].

## 1.1 Fluxo macro executável

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

## 1.2 Regras de dependência que a máquina deve respeitar

O sistema ensina, pelas próprias aulas e pelos alertas de liquidação, que determinados módulos não podem ser tratados isoladamente. O **Histórico Salarial** não é acessório; ele sustenta verbas, FGTS e contribuição social. O **Cartão de Ponto** não produz crédito sozinho; ele produz quantidades que precisam encontrar verbas já compatíveis. A liquidação, por sua vez, não deve ser lida apenas como etapa final, mas como **teste de consistência estrutural do cálculo** [Aula 1] [Aula 2] [Aula 3] [Aula 4] [Vídeo complementar — Cartão de Ponto].

| Dependência | Regra prática a ensinar | Origem |
|---|---|---|
| Histórico Salarial → Verbas | Não lançar verbas dependentes de base salarial sem histórico coerente | [Aula 1] [Aula 4] |
| Verba principal → Reflexos | Salvar a verba principal antes de expandir ou parametrizar reflexos | [Aula 2] |
| Alteração estrutural → Regerar | Mudanças de período, dobra, quantidade, divisor, multiplicador ou base exigem regeração | [Aula 2] [Aula 3] [Aula 4] |
| Parâmetros do Cálculo → Cenários especiais | Demissão, aviso prévio e maior remuneração alteram a lógica do cálculo por parcela | [Aula 1] [Vídeo complementar — Estabilidades] [Vídeo complementar — FGTS não depositado] |
| Liquidação → Validação | O relatório final deve ser lido para confirmar se a parametrização produziu o efeito jurídico pretendido | [Aula 4] [Vídeo complementar — Reflexos/Integração] [Vídeo complementar — FGTS não depositado] |

## 1.3 Tela Inicial, Tabelas e abertura do cálculo

A Tela Inicial funciona como ponto de entrada do fluxo. O vídeo geral reforça que a rotina adequada consiste em abrir o sistema, atualizar tabelas e só depois criar ou importar o cálculo. Essa ordem não é mero formalismo: as tabelas alimentam índices, verbas, faixas, feriados e outros elementos que repercutem nas páginas seguintes [Aula 1] [Vídeo complementar — Reforço geral].

| Item operacional | Conteúdo consolidado | Origem |
|---|---|---|
| Comandos iniciais demonstrados | **Criar novo cálculo**, **Buscar cálculo**, **Importar cálculo** | [Aula 1] [Vídeo complementar — Reforço geral] |
| Regra de ordem | Atualizar tabelas antes do primeiro cálculo ou antes de reutilizar ambiente desatualizado | [Vídeo complementar — Reforço geral] |
| Área adicional visível | Cálculos recentes, manual e tutorial | [Aula 1] |
| URL relativa | **[NÃO COBERTO NAS AULAS]** | [NÃO COBERTO NAS AULAS] |
| Mensagens literais de sucesso/erro | **[NÃO COBERTO NAS AULAS]** | [NÃO COBERTO NAS AULAS] |

## 1.4 Dados do Cálculo e Parâmetros do Cálculo

Essas páginas definem a moldura do cálculo. A máquina deve aprender que não basta inserir datas de modo mecânico; algumas situações exigem leitura jurídica do cenário para que a data informada no sistema produza o efeito esperado. O exemplo mais sensível vem do vídeo de estabilidade, em que a data real da demissão não é a data que deve constar no sistema para fins de cálculo dos consectários do período estabilitário [Aula 1] [Vídeo complementar — Estabilidades].

| Campo/decisão | Regra operacional ensinável | Origem |
|---|---|---|
| Nome do cálculo | Informar identificação clara do cálculo | [Vídeo complementar — FGTS não depositado] |
| Estado/Município | Preencher conforme localidade da prestação de serviços | [Vídeo complementar — FGTS não depositado] |
| Admissão, Demissão e Ajuizamento | Inserir marcos temporais do caso | [Aula 1] [Vídeo complementar — FGTS não depositado] |
| Maior Remuneração | Preencher sempre que o cenário exigir base rescisória ou base de parcelas específicas | [Aula 1] [Vídeo complementar — Estabilidades] |
| Aviso Prévio Indenizado / Projetar Aviso Prévio | Marcar ou desmarcar conforme o cenário efetivo; em FGTS não depositado e no exemplo de estabilidade, a opção permaneceu desmarcada | [Vídeo complementar — FGTS não depositado] [Vídeo complementar — Estabilidades] |
| Armadilha crítica em estabilidade | Em cálculo de período estabilitário, preencher o campo **Demissão** com a **data final da estabilidade**, e não com a data real da dispensa | [Vídeo complementar — Estabilidades] |

## 1.5 Histórico Salarial, Férias e bases auxiliares

A Aula 1 trata o Histórico Salarial como núcleo de bases do cálculo. Sem histórico coerente, o sistema perde suporte para horas extras, diferença salarial, FGTS e contribuição social. Páginas como **Férias** e **Faltas** podem influenciar bases, quantidades e reflexos, mesmo quando não são lançadas como verbas autônomas na grade principal [Aula 1] [Aula 4].

| Página/módulo | Função executável | Efeito sobre o cálculo | Origem |
|---|---|---|---|
| Histórico Salarial | Criar bases remuneratórias e editá-las por competência | Alimenta verbas, FGTS e CS | [Aula 1] |
| Férias | Informar períodos, dobra, abono e situações de gozo | Afeta bases, quantidades e incidências | [Aula 1] |
| Faltas | Ajustar ausências com impacto no cálculo | Pode alterar bases e quantidades | [Aula 1] |
| Regeração após mudanças estruturais | Recalcular ocorrências derivadas de parâmetros-base | Evita alertas na liquidação | [Aula 4] |

## 1.6 Verbas e reflexos

A página **Verbas** deve ser ensinada à máquina como ambiente de duas operações diferentes. A primeira é a criação da verba principal, seja pelo **Expresso**, seja pelo modo **Manual**. A segunda é a abertura da árvore ou da área correspondente para selecionar reflexos, parametrizar linhas específicas e, quando necessário, renomear verbas para tornar o cálculo auditável [Aula 2] [Vídeo complementar — OJ 394] [Vídeo complementar — Reflexos/Integração].

| Operação | Regra prática | Origem |
|---|---|---|
| Incluir verba pelo Expresso | Selecionar a rubrica pertinente, salvar e depois abrir seus parâmetros | [Aula 2] [Vídeo complementar — OJ 394] [Vídeo complementar — Reflexos/Integração] |
| Parametrizar verba | Ajustar base, período, proporcionalização e composição do principal | [Aula 2] [Vídeo complementar — Reflexos/Integração] |
| Marcar reflexos | Primeiro salvar a verba principal; depois expandir ou exibir reflexos e marcar somente os deferidos | [Aula 2] [Vídeo complementar — OJ 394] |
| Renomear verbas | Alterar o nome para separar verbas com efeitos diferentes e facilitar auditoria | [Vídeo complementar — OJ 394] [Vídeo complementar — Estabilidades] |
| Regerar | Usar quando alterações estruturais afetarem ocorrências | [Aula 2] [Aula 4] |

## 1.7 Cartão de Ponto como módulo de produção de quantidades

O cartão não é um relatório passivo; ele é um módulo de configuração da jornada, replicação das marcações ao longo do contrato, edição de exceções e posterior validação por espelho diário [Aula 2] [Vídeo complementar — Cartão de Ponto].

| Etapa | Ação executável | Comportamento esperado do sistema | Origem |
|---|---|---|---|
| 1 | Entrar em **Cartão de Ponto** e clicar em **Novo** | Sistema cria um novo cartão e espelha datas contratuais no período | [Vídeo complementar — Cartão de Ponto] |
| 2 | Escolher o critério de apuração | Sistema passa a interpretar excedentes diários/semanais conforme a parametrização | [Vídeo complementar — Cartão de Ponto] |
| 3 | Definir jornada padrão e enquadramento noturno | Sistema incorpora regras de jornada e, se for o caso, redução ficta | [Vídeo complementar — Cartão de Ponto] |
| 4 | Preencher **Programação Semanal** | Grade semanal é replicada para todo o contrato | [Vídeo complementar — Cartão de Ponto] |
| 5 | Abrir **Grade de Ocorrências** | Sistema permite ajustes finos dia a dia ou mês a mês | [Vídeo complementar — Cartão de Ponto] |
| 6 | Salvar e voltar | Quantidades ficam aptas a alimentar verbas correlatas | [Vídeo complementar — Cartão de Ponto] |
| 7 | Imprimir apenas o espelho diário para validar | Sistema gera PDF com horas trabalhadas e excedentes | [Vídeo complementar — Cartão de Ponto] |

## 1.8 FGTS, Contribuição Social e módulos acessórios

Os módulos de FGTS e Contribuição Social são páginas próprias, com lógica própria de ocorrências e revisão. A máquina não deve tratá-los como reflexos invisíveis. Eles podem exigir edição mensal, revisão de parâmetros, regeração e conferência por relatório [Aula 3] [Aula 4] [Vídeo complementar — FGTS não depositado].

| Módulo | Regra de operação | Origem |
|---|---|---|
| FGTS | Preencher parâmetros, revisar ocorrências mensais, salvar e regerar quando necessário | [Aula 3] |
| FGTS não depositado | Marcar **Recolher** quando o valor for obrigação de depósito e não crédito líquido ao reclamante | [Vídeo complementar — FGTS não depositado] |
| Contribuição Social | Parametrizar bases, abrir ocorrências, editar e regerar conforme mudanças | [Aula 3] |
| Previdência Privada | Só liquidar se pelo menos uma verba tiver a incidência correspondente marcada | [Aula 3] [Aula 4] |
| Pensão Alimentícia | Aplicar apenas sobre as verbas previamente marcadas com essa incidência | [Aula 3] |

## 1.9 Liquidação, alertas, impressão e exportação

O fluxo final deve ser apresentado como etapa de **teste, saneamento e validação**. A liquidação não é um simples botão de encerramento: ela revela se faltam bases salariais, se módulos acessórios ficaram sem incidência de origem ou se ocorrências dependentes não foram regeradas [Aula 4].

| Subetapa | Ação ensinável | Finalidade prática | Origem |
|---|---|---|---|
| Operações > Liquidar | Executar o cálculo consolidado | Gerar resumo e alertas | [Aula 4] |
| Erros e Alertas | Ler criticamente cada aviso | Identificar ausência de base, incidência ou regeração | [Aula 4] |
| Imprimir | Selecionar relatórios pertinentes | Validar matemática e composição do cálculo | [Aula 4] [Vídeo complementar — Cartão de Ponto] [Vídeo complementar — Reflexos/Integração] |
| Exportar | Gerar arquivo do cálculo | Reaproveitar o trabalho em outro ambiente ou petição | [Aula 4] |
