# Resumos do Manual Oficial PJE-Calc v1.0

Fonte: Manual do Usuário PJe-Calc, CSJT/TRT8 (117 páginas)
Extraído: seções operacionalmente críticas para automação precisa

---

## Seção 1 — O que é o PJE-Calc

O **PJE-Calc** é o módulo de cálculos integrado ao PJE (Processo Judicial Eletrônico) para liquidação de sentença trabalhista. Desenvolvido pelo TRT8 e disponibilizado a todos os TRTs pelo CSJT.

**Versões:**
- PJE-Calc integrado: acessado dentro do PJE pelo servidor/advogado
- **PJE-Calc Cidadão**: versão standalone para download, usada por advogados e partes fora do PJE

**Arquivo de saída:** `.PJC` (ZIP contendo XML ISO-8859-1) — importável no PJE-Calc integrado

---

## Seção 2 — Tipos de Lançamento de Verbas

### Lançamento Expresso
- Para verbas predefinidas no sistema (catálogo completo)
- Formulário simplificado: período, base de cálculo, percentual
- O sistema calcula automaticamente incidências (FGTS, INSS, IR)
- **Usar sempre que possível** — menos erros, mais rápido

### Lançamento Manual
- Para verbas não previstas no catálogo Expresso
- Formulário completo: usuário define todas as incidências manualmente
- Necessário para: gratificações especiais, indenizações atípicas, verbas de CCT/ACT

### Lançamento de Reflexas
- Verbas que dependem de outras (ex: 13º sobre horas extras)
- Vinculadas à verba principal via campo "Verba Principal"
- Calculadas automaticamente pelo PJE-Calc ao liquidar

---

## Seção 3 — Parâmetros do Cálculo

### Dados Obrigatórios
1. Número do processo (formato: NNNNNNN-DD.AAAA.J.RR.VVVV)
2. Estado e Município da vara
3. Data de admissão e demissão
4. Tipo de rescisão
5. Maior remuneração (base de cálculo para rescisórias)
6. Pelo menos 1 verba

### Regime de trabalho
- Tempo Integral: divisor 220h/mês (padrão para horário de 44h/sem)
- Tempo Parcial (pré-Reforma): máx. 26h/sem, divisor proporcional
- Tempo Parcial Reforma (Lei 13.467/2017): máx. 30h sem horas extras ou 26h com horas extras

### Prescrição
- Campo "Prescrição Quinquenal": marcar TRUE para contratos vigentes/recentes
- FGTS: prescrição trintenária foi substituída por quinquenal (STF RE 709.212) — ainda marcar TRUE para período anterior
- O PJE-Calc ajusta automaticamente o período calculado com base na prescrição marcada

---

## Seção 4 — Correção Monetária e Juros (ADC 58/STF)

### Regra vigente (ADC 58, julgada em 18/12/2020)
Para empregadores privados:
- **Correção pré-judicial** (até a citação): IPCA-E
- **Correção judicial + juros** (após citação): SELIC simples

### Entidades da Fazenda Pública (EC 113/2021)
Para União, Estados, Municípios, autarquias, fundações públicas:
- Correção: Manual de Cálculos da Justiça Federal
- Precatórios: art. 100 CF + EC 113/2021
- Não se aplica SELIC para entidade pública

### Configuração no PJE-Calc
- Campo "Índice de Correção": selecionar "IPCA-E" (privado) ou "Manual de Cálculos da JF" (público)
- Campo "Taxa de Juros": "SELIC" (após EC 113/2021 para todos) ou "Juros Padrão" (1% a.m.)

---

## Seção 5 — FGTS

### Configuração
- **Alíquota**: 8% (padrão), 2% (aprendiz), 8% (doméstico)
- **Multa 40%**: marcar quando rescisão sem justa causa ou rescisão indireta
- **Multa 20%**: culpa recíproca ou força maior (muito raro)
- **Art. 467 CLT**: multa de 50% sobre parcelas rescisórias incontroversas não pagas

### Incidência por verba
- Incide: saldo de salário, horas extras, adicional noturno, adicional de insalubridade/periculosidade, aviso prévio indenizado (posição majoritária)
- Não incide: dano moral/material, multas art. 477/467, férias indenizadas, vale transporte

### Depósitos em atraso
- Informar em campo separado "FGTS Não Depositado" com período e valores
- Diferente das verbas — é calculado sobre a remuneração bruta dos períodos em atraso

---

## Seção 6 — Honorários Advocatícios

### Tipos (pós-Reforma Trabalhista)
- **Sucumbência** (art. 791-A CLT): 5% a 15% do valor da condenação
- **Honorários periciais**: valor fixo determinado na sentença

### Configuração no PJE-Calc
- **Aba "Honorários"**: apenas honorários advocatícios de sucumbência
- **Aba "Honorários Periciais"**: perito, engenheiro, médico, etc. — campo SEPARADO
- Parte devedora: pode ser reclamante, reclamado, ou ambos (sucumbência recíproca)
- Base de cálculo: "valor bruto" ou "valor líquido" conforme sentença

### Honorários anteriores à Reforma (antes de 11/11/2017)
- Apenas com assistência sindical (Súmula 219/TST e 329/TST)
- 15% sobre o valor da condenação (se deferidos)

---

## Seção 7 — Contribuição Previdenciária (INSS)

### Configuração
- Campo "Período para Apuração": meses individuais de apuração
- Empregado: tabela progressiva INSS (13,5% máx. após Reforma Previdenciária/2019)
- Empregador: 20% sobre parcelas salariais
- Prazo de recolhimento: via folha mensal simulada pelo PJE-Calc

### Verbas com incidência INSS
- Incide: saldo de salário, horas extras, adicionais, 13º, aviso prévio trabalhado
- Não incide: dano moral/material, multas, vale transporte, férias indenizadas (posição divergente)

---

## Seção 8 — Imposto de Renda

### Configuração
- Campo "Apurar IR": marcar TRUE quando a sentença determinar retenção
- "Regime de Caixa": tributação exclusiva na fonte, mês a mês
- "Meses tributáveis": número de meses para distribuição da base de cálculo
- Tabela progressiva IRPF: aplicada pelo PJE-Calc conforme ano-calendário

### Verbas sujeitas a IR
- Incide: saldo de salário, horas extras, adicionais, 13º, aviso prévio, comissões
- Não incide: dano moral (Súmula 498/STJ), indenizações, verbas de natureza indenizatória

---

## Seção 9 — Liquidação e Exportação

### Ordem de preenchimento recomendada
1. Parâmetros do Cálculo (dados do processo, contrato)
2. Histórico Salarial (se houver variações)
3. Faltas (se houver)
4. Verbas (Expresso primeiro, depois Manual)
5. FGTS
6. Contribuição Social (INSS)
7. Imposto de Renda
8. Honorários Advocatícios
9. Honorários Periciais
10. Multas e Indenizações (dano moral/material se não lançados como verbas)
11. Custas Processuais
12. Correção, Juros e Multa
13. Liquidar (Operações > Liquidar)
14. Exportar .PJC

### Liquidação
- Operações > Liquidar: confirmar para executar o cálculo
- Mensagem de sucesso: "Operação realizada com sucesso"
- Aguardar processamento AJAX antes de exportar

### Exportação
- Operações > Exportar: gera arquivo .PJC
- .PJC = ZIP contendo XML ISO-8859-1
- Importar no PJE integrado: Cálculos > Importar Cálculo Externo

---

## Seção 8 — Cartão de Ponto

Fonte: Manual oficial PJE-Calc (pje.csjt.jus.br/manual) + Vídeo "Introdução ao Cartão de Ponto" (Fernanda Araujo)

### Visão Geral
O Cartão de Ponto é o módulo para apuração de horas extras, noturnas e intervalos.
Possui 3 botões principais: **Novo**, **Grade de Ocorrências**, **Visualizar Cartão**.

### Pré-requisitos (OBRIGATÓRIO antes de criar cartão)
1. **Dados do Cálculo** salvos: admissão, demissão, prescrição
2. **Carga Horária** definida em Parâmetros do Cálculo (220h, 180h, 150h mensal)
   - Isso altera automaticamente os limites diários (8h ou 6h) no cartão
3. Recomendável ter Histórico Salarial preenchido

### Fluxo de Preenchimento
1. Clicar **Novo** → abre formulário de Critérios de Apuração
2. Definir **Período** (datas início/fim que o cartão abrange)
3. Selecionar **Forma de Apuração** de horas extras
4. Preencher **Jornada de Trabalho Padrão** (seg-dom)
5. Configurar **Períodos de Descanso** (feriados, intervalos)
6. Configurar **Horário Noturno** (se aplicável)
7. Escolher modalidade de **Preenchimento de Jornadas**
8. Clicar **Salvar**
9. Ir para **Grade de Ocorrências** para editar jornadas dia a dia
10. Ir para **Visualizar Cartão** > **Apurar** para gerar quantidades mensais

### Formas de Apuração (radio tipoApuracaoHorasExtras)
| Código | Enum Java | Descrição |
|--------|-----------|-----------|
| NAP | NAO_APURAR_HORAS_EXTRAS | Não apurar horas extras |
| HJD | HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA | Excedentes da jornada diária (ex: 8ª hora) |
| FAV | HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL | Critério mais favorável ao trabalhador |
| HST | HORAS_EXTRAS_CONFORME_SUMULA_85 | Conforme Súmula 85 do TST |
| APH | APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO | Primeiras HE em separado |
| SEM | HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL | Excedentes da jornada semanal (ex: 44ª hora) |
| MEN | HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL | Excedentes da jornada mensal (ex: 220h) |

### Campos do Formulário (IDs confirmados)
- `competenciaInicial` / `competenciaFinal`: período do cartão (datas)
- `tipoApuracaoHorasExtras`: radio com enum Java
- `valorJornadaSegunda` a `valorJornadaDiariaDom`: jornada diária HH:MM
- `qtJornadaSemanal` / `qtJornadaMensal`: totais (decimal BR)
  **ATENÇÃO**: `qtJornadaMensal` = "Jornada Mensal Média", NÃO é a mesma coisa que
  `valorCargaHorariaPadrao` (Carga Horária Padrão, na aba Parâmetros do Cálculo).
  - **Jornada Mensal Média** = `jornada_semanal / 7 × 30` (ex: 44h/sem → 188,57; 36h/sem → 154,29)
  - **Carga Horária Padrão** = `jornada_semanal × 5` (ex: 44h/sem → 220; 36h/sem → 180)
  Tooltip oficial: "calculada dividindo a jornada semanal pelos 7 dias da semana
  e multiplicando o resultado pelos 30 dias do mês comercial. Não confundir com a carga horária padrão."
- `qtsumulatst`: quantidade HE para Súmula 85 (HH:MM)
- `intervalorIntraJornadaSupSeis` (checkbox) + `valorIntervalorIntraJornadaSupSeis`: intervalo >6h
- `intervalorIntraJornadaInfSeis` (checkbox) + `valorIntervalorIntraJornadaInfSeis`: intervalo ≤6h
- `considerarFeriado`: checkbox feriados
- `extraDescansoSeparado`: checkbox extras domingos separado
- `apurarHorasNoturnas`: checkbox horário noturno
- `inicioHorarioNoturno` / `fimHorarioNoturno`: horários (HH:MM)
- `reducaoFicta`: checkbox (hora noturna = 52m30s)
- `horarioProrrogado`: checkbox prorrogação noturna (Súmula 60 TST)
- `formulario:incluir`: botão Novo
- `formulario:salvar`: botão Salvar
- `formulario:visualizarOcorrencias`: botão Grade de Ocorrências
- `formulario:importarCartao`: botão Visualizar Cartão

### Distinção Crítica: Jornada Padrão vs Jornada Praticada

**"Jornada de Trabalho Padrão"** (campos `valorJornadaSegunda` a `valorJornadaDiariaDom`):
- É a jornada **CONTRATADA** (ex: 8h/dia para CLT 220h/mês, 6h para tempo parcial)
- Serve como **referência** para o cálculo de horas extras
- NÃO é a jornada efetivamente praticada

**"Grade de Ocorrências"** (aba separada, dia a dia):
- É a jornada **EFETIVAMENTE PRATICADA** (ex: 10h/dia, conforme cartão de ponto)
- Preenchida via Programação Semanal, Escala ou Livre

**Cálculo de Horas Extras**: `HE = praticada − padrão`
- Se a jornada padrão for preenchida com 10h e a praticada também for 10h → HE = 0 (ERRO!)
- Correto: padrão = 8h, praticada = 10h → HE = 2h por dia

### Preenchimento de Jornadas (Modalidades)
- **Programação Semanal**: define semana modelo, replica para todo período (mais comum)
- **Escala**: para regimes 12x36, 6x1 etc. (ciclo de dias trabalhados/folgas)
- **Livre**: preenchimento dia a dia, usado com cartões de ponto físicos

### Horário Noturno
- Urbano: 22h às 05h
- Rural (pecuária): 20h às 04h
- Rural (lavoura): 21h às 05h
- Redução Ficta: hora noturna = 52 minutos e 30 segundos
- Prorrogação (Súmula 60 TST): labor após 05h em continuidade mantém adicional noturno

### Períodos de Descanso (checkboxes)
- Considerar feriados (dias ou horas)
- Extras ao feriado em separado
- Apurar horas noturnas
- Intervalo do Art. 384 CLT (mulher)
- Intervalos para digitadores (Art. 72 CLT)
- Supressão de intervalo de insalubridade (Art. 253 CLT - frigoríficos)
- Intervalo interjornadas (11h)
- Jornada entre semanas (35h)
- Intervalo intrajornada (almoço)

---

## Seção 10 — Regras Críticas de Salvamento e Regeração

### Salvar obrigatório após cada aba
- **TODA** página requer clique explícito no botão "Salvar" após preenchimento
- Navegar para outra aba sem salvar = **PERDA TOTAL** dos dados preenchidos
- Após salvar, aguardar mensagem de sucesso ("Operação realizada com sucesso")

### Regerar Ocorrências (aba Verbas)
- **Quando**: Após alterar qualquer parâmetro que afeta as ocorrências (período, carga horária,
  prescrição, base de cálculo, divisor, multiplicador)
- **Botão**: `formulario:regerarOcorrencias` na listagem de verbas
- **Opções** (radio `tipoRegeracao`):
  - "Manter alterações realizadas nas ocorrências" (padrão seguro)
  - "Sobrescrever alterações realizadas nas ocorrências" (resetar tudo)
- **Confirma** via `window.confirm` antes de executar
- **Obrigatório antes de liquidar** quando houve alterações nos parâmetros

### Sequência de Preenchimento Recomendada
1. Dados do Cálculo (Dados do Processo + Parâmetros) > Salvar
2. Faltas > Salvar
3. Férias > Salvar
4. Histórico Salarial > Salvar
5. Verbas (Expresso e/ou Manual) > Salvar
6. Cartão de Ponto > Salvar
7. FGTS > Salvar
8. Contribuição Social > Salvar
9. Imposto de Renda > Salvar
10. Multas e Indenizações > Salvar
11. Honorários > Salvar
12. Custas Judiciais > Salvar
13. Correção, Juros e Multa > Salvar
14. **Regerar Ocorrências** (aba Verbas) — se houve alterações nos parâmetros
15. Operações > Liquidar
16. Operações > Exportar
