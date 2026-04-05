# Manual Completo do PJE-Calc -- Referencia para Automacao

Fonte: https://pje.csjt.jus.br/manual/index.php/PJE-Calc
Extraido: 2026-04-04
Objetivo: Referencia tecnica completa para automacao via Playwright

---

## Indice

1. [Apresentacao e Introducao](#1-apresentacao-e-introducao)
2. [Ferramenta](#2-ferramenta)
3. [Login e Pagina Inicial](#3-login-e-pagina-inicial)
4. [Calculo -- Buscar, Importar, Relatorio](#4-calculo--buscar-importar-relatorio)
5. [Novo Calculo -- Dados do Calculo](#5-novo-calculo--dados-do-calculo)
6. [Faltas](#6-faltas)
7. [Ferias](#7-ferias)
8. [Historico Salarial](#8-historico-salarial)
9. [Verbas](#9-verbas)
10. [Cartao de Ponto](#10-cartao-de-ponto)
11. [Salario-familia](#11-salario-familia)
12. [Seguro-desemprego](#12-seguro-desemprego)
13. [FGTS](#13-fgts)
14. [Contribuicao Social](#14-contribuicao-social)
15. [Previdencia Privada](#15-previdencia-privada)
16. [Pensao Alimenticia](#16-pensao-alimenticia)
17. [Imposto de Renda](#17-imposto-de-renda)
18. [Multas e Indenizacoes](#18-multas-e-indenizacoes)
19. [Honorarios](#19-honorarios)
20. [Custas Judiciais](#20-custas-judiciais)
21. [Correcao, Juros e Multa](#21-correcao-juros-e-multa)
22. [Operacoes do Calculo](#22-operacoes-do-calculo)
23. [Calculo Externo](#23-calculo-externo)
24. [Tabelas](#24-tabelas)
25. [Atualizacao](#25-atualizacao)

---

## 1. Apresentacao e Introducao

O PJe-Calc e o modulo de calculos trabalhistas integrado ao PJe (Processo Judicial Eletronico). Desenvolvido pelo TRT8 e disponibilizado a todos os TRTs pelo CSJT.

Versoes:
- **PJe-Calc integrado**: acessado dentro do PJe pelo servidor/advogado
- **PJe-Calc Cidadao**: versao standalone para download, usada por advogados e partes fora do PJe

Arquivo de saida: `.PJC` (ZIP contendo XML ISO-8859-1) -- importavel no PJe-Calc integrado.

---

## 2. Ferramenta

### 2.1 Caracteristicas

Sistema web baseado em Java (JSF/RichFaces), executado em Tomcat embarcado. Interface com menus laterais, formularios por abas, e operacoes AJAX para salvamento.

### 2.2 Estrutura

Menu principal:
- **Calculo**: Buscar, Importar, Relatorio Consolidado
- **Novo**: Criar novo calculo (fluxo principal para automacao)
- **Calculo Externo**: Para atualizar calculos ja existentes
- **Tabelas**: Consulta de tabelas de referencia
- **Operacoes**: Liquidar, Imprimir, Fechar, Excluir, Exportar, Enviar para PJe

### 2.3 Perfis de Acesso

1. **Calculista**: Perfil padrao. Acesso a todas as operacoes de calculo: criacao, exclusao, manutencao, consulta, configuracao, liquidacao, impressao de relatorios. Acesso somente leitura a tabelas nacionais e regionais.

2. **Gestor Regional**: Mesmo acesso que Calculista, mais leitura/escrita em tabelas regionais (pisos salariais, feriados estaduais/municipais, vale transporte). Somente leitura em tabelas nacionais.

3. **Gestor Nacional**: Mesmo acesso que Gestor Regional, mais leitura/escrita em tabelas nacionais (indices de correcao monetaria, tabelas de IR e contribuicao social, valores de salario minimo).

### 2.4 Requisitos de Ambiente

- Sistema Operacional: Windows 7 ou superior
- Navegador: **Firefox 6.0 ou superior** (OBRIGATORIO)
- Java Runtime: JRE versao 7 ou 8
- Leitor de Smart Card (se certificado armazenado em chip)
- Gerenciador de Certificados: SafeSign
- Login inicial no PJe necessario antes de acessar PJe-Calc

### 2.5 Como Acessar

URL padrao: `https://pje.trtXX.jus.br/pjecalc` (XX = numero do tribunal regional)
PJe-Calc Cidadao: aplicacao standalone com Tomcat embarcado em `localhost:9257`

---

## 3. Login e Pagina Inicial

### Login

Autenticacao via certificado digital ou usuario/senha do PJe. No PJe-Calc Cidadao, acesso direto sem autenticacao.

### Pagina Inicial

Exibe lista de calculos existentes organizados por orgao julgador. Acoes disponiveis: abrir, excluir, buscar.

**Regra critica**: Calculos sao organizados por orgao julgador. Modificacoes de calculos entre orgaos diferentes sao proibidas.

---

## 4. Calculo -- Buscar, Importar, Relatorio

### 4.1 Buscar Calculo

Pesquisa por numero do processo, nome das partes, ou periodo de criacao.

### 4.2 Importar Calculo

Importa arquivo `.PJC` (XML em formato ZIP). O arquivo deve ter sido exportado pelo proprio PJe-Calc apos liquidacao.

### 4.3 Relatorio Consolidado

Gera relatorio consolidado de todos os calculos de um processo.

---

## 5. Novo Calculo -- Dados do Calculo

Ao clicar em "Novo", o sistema abre a pagina "Dados do Calculo" com duas abas: **Dados do Processo** e **Parametros do Calculo**.

### 5.1 Dados do Processo

Duas opcoes de preenchimento:

**Manualmente**: O usuario digita:
- Numero do processo
- Valor da causa
- Partes (reclamante e reclamado)
- Advogados

**Obter do PJe**: O sistema consulta a base do PJe, importa dados das partes. Usuario seleciona reclamante e reclamado relevantes. Opcao "Inverter Partes" disponivel.

### 5.2 Parametros do Calculo

**Campos obrigatorios (marcados com asterisco *):**
- Estado
- Municipio
- Admissao (data)
- Ajuizamento (data)

**Campos adicionais:**

| Campo | Descricao |
|-------|-----------|
| Desligamento | Data de demissao/desligamento |
| Data Inicial / Data Final | Limita periodo do calculo quando verbas nao sao devidas por todo o contrato |
| Prescricao Quinquenal | Aplica prescricao quinquenal as verbas trabalhistas |
| Regime de Trabalho | Tempo Integral (30 dias ferias), Tempo Parcial (18 dias), Trabalho Intermitente (sem pagina de ferias) |
| Maior Remuneracao | Necessaria para Aviso Previo, ferias + 1/3, multa art. 477 CLT |
| Ultima Remuneracao | Gera automaticamente historico salarial com base no valor final, com incidencia de Contribuicao Social |

### 5.3 Aviso Previo

Tres opcoes de calculo:

1. **Nao Apurar**: Mantem quantidade padrao de 30 dias
2. **Calculado**: Sistema calcula conforme Lei 12.506/2011 = 30 dias + 3 dias por ano de servico (maximo 90 dias)
3. **Informado**: Quantidade definida pelo usuario sem interferencia do sistema

### 5.4 Carga Horaria e Calendario

- **Carga Horaria Padrao**: Padrao 220 horas mensais. Permite excecoes por periodos com taxas horarias alternativas.
- **Sabado como Dia Util**: Marcado por padrao. Desmarcar para excluir sabados.
- **Feriados Nacionais**: Considerados automaticamente.
- **Feriado Estadual / Municipal**: Opcoes para inclusao.
- **Pontos Facultativos**: Selecao de feriados opcionais nacionais, estaduais e municipais.

### 5.5 Comentarios

Campo de texto limitado a 255 caracteres. Exibido no relatorio Resumo do Calculo.

### 5.6 Salvamento

**CRITICO**: Apos completar e verificar ambas as abas, o usuario DEVE clicar no icone "Salvar". Navegar sem salvar = perda de dados.

---

## 6. Faltas

O usuario registra TODAS as faltas durante o contrato de trabalho, inclusive as anteriores ao periodo de calculo, pois afetam:
- Apuracao de ocorrencias de verbas
- Calculo do FGTS
- Calculo da Contribuicao Social
- Apuracao do periodo de ferias

### Campos por falta:

| Campo | Descricao |
|-------|-----------|
| Data Inicial | Inicio da falta |
| Data Final | Fim da falta |
| Classificacao | "justificadas" ou "nao justificada" |
| Descricao | Campo texto descritivo |

### Acoes:
- Clicar "Salvar" apos cada inclusao
- **Reiniciar Periodo Aquisitivo**: Marcar quando falta causa perda do direito a ferias e inicia novo periodo aquisitivo a partir da data de retorno (conforme CLT)
- **Importar**: Permite importar faltas de arquivo CSV externo com template disponivel

---

## 7. Ferias

O sistema gera automaticamente os dados de ferias a partir de:
- Datas de admissao e desligamento
- Regime de trabalho selecionado
- Registros de faltas injustificadas

### Conceitos:

**Periodo Aquisitivo**: Periodos sucessivos de um ano contados da data de admissao.

**Periodo Concessivo**: Periodos sucessivos de um ano contados do dia seguinte ao termino de cada periodo aquisitivo.

**Prazo (duracao)**: Varia conforme regime e faltas:

Regime Integral:
- Ate 5 faltas = 30 dias
- Ate 14 = 24 dias
- Ate 23 = 18 dias
- Ate 32 = 12 dias
- Acima de 32 = 0 dias (perdidas)

Regime Parcial (contrato encerrado antes de 11/10/2017):
- Ate 7 faltas = 18 dias
- Acima de 7 = 9 dias
- A partir de 11/11/2017: mesma regra do integral

### Situacao (Status) -- Sugestoes do Sistema:

| Status | Condicao |
|--------|----------|
| Gozadas | Periodo concessivo termina em/antes do desligamento |
| Indenizadas | Periodo concessivo termina apos desligamento |
| Perdidas | Mais de 32 faltas (regime integral) |

O usuario DEVE verificar e modificar os status sugeridos, marcar abonos, e informar periodos de gozo efetivos. O sistema permite ate tres periodos de gozo por ano aquisitivo.

### Dobra (pagamento em dobro):

Sistema auto-marca quando muda status para "Indenizadas" ou registra periodo de gozo que excede o periodo concessivo. Usuario deve verificar e desmarcar quando indevida.

### Ferias Coletivas:

Informar data de inicio para indicar ferias proporcionais. Clicar "Regerar Ferias" apos alteracao.

### Gozo Parcial:

Mudar status para "Gozadas Parcialmente" com periodo de gozo parcial gera automaticamente ocorrencia rescisoria para dias nao gozados.

### Importacao:

Permite importar de arquivo CSV externo.

**CRITICO**: Clicar "Salvar" apos modificacoes.

---

## 8. Historico Salarial

Armazena todas as bases de calculo para apuracao de: Verbas, Salario-familia, Seguro-desemprego, FGTS, Contribuicao Social.

### Criar Base:

1. Clicar "Novo"
2. Informar Nome da Base
3. Selecionar tipo: "fixa" ou "Variavel"
4. Marcar checkbox Incidencia FGTS (se aplicavel)
5. Marcar checkbox Incidencia Contribuicao Social
6. Verificar periodo sugerido pelo sistema
7. Escolher Tipo de Valor

### Tipo de Valor -- Opcao 1: Base Informada

Valores devem ser informados pelo valor mensal completo, mesmo se pago proporcionalmente (exceto bases variaveis como comissoes, horas extras, adicional noturno).

Campos:
- Competencia Inicial (mes/ano)
- Competencia Final (mes/ano)
- Valor
- Checkbox: FGTS ja recolhido
- Checkbox: Contribuicoes Sociais ja recolhidas
- Clicar icone "Gerar Ocorrencias"

### Tipo de Valor -- Opcao 2: Base Calculada

- Selecionar "Calculado"
- Informar Quantidade
- Selecionar referencia: Salario Minimo ou Piso Salarial
- Se Piso Salarial: escolher Categoria profissional
- Marcar checkboxes de ja recolhido
- Clicar "Gerar Ocorrencias"

### Acoes sobre Bases:

- **Editar**: Clicar icone editar, modificar, clicar "Salvar"
- **Excluir**: Clicar icone excluir, confirmar "Ok"
- **Importar**: CSV externo com template fornecido
- **Grade de Ocorrencias**: Visualizar e editar todas as bases simultaneamente

**CRITICO**: SEMPRE clicar "Salvar" apos informar todos os valores. Sair sem salvar = perda total.

---

## 9. Verbas

Armazena as verbas (parcelas) que compoem o calculo. Dois metodos de inclusao: **Lancamento Manual** e **Lancamento Expresso**.

### 9.1 Lancamento Manual

Clicar "Manual" para abrir pagina "Dados da Verba".

#### Parametros Comuns a Todas as Verbas:

| Parametro | Descricao | Opcoes |
|-----------|-----------|--------|
| Nome | Maximo 50 caracteres | Texto livre |
| Assunto CNJ | Tabela Unificada de Assuntos | Selecao de lista |
| Parcela | Classificacao | "Fixa" (valor fixo mensal) ou "Variavel" (varia com horas trabalhadas) |
| Valor | Forma de calculo | "Calculado" (formula) ou "Informado" (usuario digita) |
| Incidencia | Contribuicoes aplicaveis | FGTS, IRPF, Contribuicao Social, Previdencia Privada, Pensao Alimenticia |
| Caracteristica | Classificacao da verba | Comum, 13o Salario, Aviso Previo, Ferias |
| Ocorrencia | Frequencia de pagamento | Desligamento, Mensal, Dezembro, Periodo Aquisitivo |
| Juros | Aplicacao TST Sumula 439 | "Nao" (padrao) ou "Sim" |
| Tipo | Principal ou Reflexa | Principal: calculada sobre bases; Reflexa: calculada sobre verba principal |
| Gerar Verba Reflexa | Se verba serve como base para reflexas | "Devido" ou "Diferenca" |
| Gerar Verba Principal | Se verba serve como base para outras principais | "Devido" ou "Diferenca" |
| Compor Principal | Se soma ao principal devido | "Sim" (padrao) ou "Nao" |
| Zerar Valor Negativo | Tratamento de valores negativos | Checkbox |

#### Secao Inferior -- Valor Devido / Valor Pago:

**Valor Devido** e **Valor Pago** com campo **Comentarios** (255 caracteres).

### 9.2 Parametros do Valor Devido (Calculado / Comum / Mensal / Principal)

| Parametro | Descricao |
|-----------|-----------|
| Periodo | Sistema sugere: inicio = maior data entre (Admissao, Prescricao, Data Inicial) e fim = menor data entre (Desligamento, Data Final). Usuario pode ajustar. |
| Exclusoes | Checkboxes: Faltas Justificadas, Faltas Nao Justificadas, Ferias Gozadas |
| Dobrar Valor Devido | Checkbox para calculo em dobro |
| Base de Calculo | Fontes: bases de Parametros do Calculo (Maior Remuneracao, Ultima Remuneracao), bases do Historico Salarial, tabelas de Gestor (Salario Minimo, Piso Salarial, Vale Transporte), valores de outras verbas. Opcao "Proporcionalizar" para meses incompletos. |
| Divisor | 4 opcoes: Carga Horaria, Dias Uteis, Importar do Cartao de Ponto, Informado |
| Multiplicador | Valor com precisao de ate 8 casas decimais |
| Quantidade | 3 opcoes: Importar do Calendario, Importar do Cartao de Ponto, Informada (com opcao Proporcionalizar) |

### 9.3 Parametros Especificos por Caracteristica

**13o Salario (Dezembro / Principal)**:
- Divisor: "Informado" auto-selecionado, demais desabilitados
- Quantidade: "Avos" auto-selecionado (calcula automaticamente por ocorrencia)

**Aviso Previo (Desligamento / Principal)**:
- Divisor: "Informado" auto-selecionado
- Quantidade: depende da selecao em Parametros do Calculo:
  - "Nao Apurar" = Informada com valor 30
  - "Informado" = valor digitado pelo usuario
  - "Calculado" = "Apurada" (calculo automatico)

**Ferias (Periodo Aquisitivo / Principal)**:
- Divisor: "Informado" auto-selecionado
- Quantidade: "Avos" auto-selecionado

### 9.4 Verba Reflexa (Tipo Reflexa)

Base de Calculo = uma verba principal obrigatoria + opcionalmente outras reflexas da mesma principal com mesma Ocorrencia de Pagamento.

**Comportamento da Base (4 criterios)**:
1. **Valor Mensal**: Apuracao mensal dos valores das verbas selecionadas
2. **Media pelo Valor Absoluto**: Media dos valores absolutos (sem correcao monetaria)
3. **Media pelo Valor Corrigido**: Media dos valores corrigidos monetariamente
4. **Media pela Quantidade**: Media dos valores convertidos em Quantidade

**Tratamento de Fracao de Mes**:
- Valor Mensal: Manter ou Integralizar
- Quantidade/Media: Manter, Integralizar, Desprezar, ou Desprezar Menor que 15 Dias

### 9.5 Valor Informado

Substitui Base, Divisor, Multiplicador, Quantidade por campo unico "Devido". Opcao "Proporcionalizar" para meses incompletos.

### 9.6 Valor Pago

**Calculado**: Selecionar Base (Maior Remuneracao, Historico Salarial, Piso Salarial, Salario Minimo, Vale Transporte). Verificar Quantidade = 1. Opcao Proporcionalizar.

**Informado**: Digitar valor. Opcao Proporcionalizar.

### 9.7 Lancamento Expresso

Lista verbas Principais da tabela de Verbas do sistema. Usuario marca checkboxes das verbas desejadas e clica "Salvar".

**IMPORTANTE para automacao**: A tabela do Lancamento Expresso usa `<a4j:repeat>` em layout paginado. Apenas ~27 das 60+ verbas sao visiveis no viewport. Verbas como "Saldo de Salario", "Ferias Proporcionais + 1/3", "Multa 477" ficam abaixo do scroll. Scroll via JS + re-enumeracao necessarios. (Nota: Multa 467 NAO e verba Expresso — e checkbox FGTS `multaDoArtigo467` + reflexa automatica na aba Verbas.)

### 9.8 Listagem de Verbas

Apos inclusao (Manual ou Expresso), sistema retorna a pagina Verbas listando verbas Principais.

**Exibir Reflexas**: Clicar icone "Exibir" para ver reflexas de cada Principal. Marcar checkboxes para incluir no calculo.

**Acoes sobre Verbas Principais**:
1. **Ocorrencias da Verba**: Ver/modificar valores de ocorrencias
2. **Parametros da Verba**: Ver/modificar parametros de calculo
3. **Excluir**: Remove principal e TODAS as reflexas

### 9.9 Ocorrencias da Verba

Sistema gera automaticamente ocorrencias conforme Periodo e Ocorrencia de Pagamento. Cada ocorrencia = um mes calendario.

Todas iniciam como "Ativa". Usuario deve desmarcar as nao devidas.

Campos por ocorrencia: Valor, Divisor, Multiplicador, Quantidade, Dobra, Devido, Pago.

**Alteracao em Lote**: Informar intervalo de datas + valores + clicar "Alterar".

**Regerar Ocorrencias**: Necessario quando parametros que afetam ocorrencias sao modificados. Opcoes: "Manter alteracoes" ou "Sobrescrever".

**CRITICO**: Clicar "Salvar" apos TODAS as modificacoes.

---

## 10. Cartao de Ponto

Tres funcoes principais: Novo (Criterios de Apuracao), Grade de Ocorrencias, Visualizar Cartao.

### 10.1 Criterios de Apuracao

Acessado via icone "Novo".

#### Periodo
Sistema sugere criterio unico para todo o periodo de calculo. Permite multiplos periodos sem sobreposicao de dias.

#### Forma de Apuracao (Horas Extras) -- 9+ Opcoes:

| Opcao | Descricao |
|-------|-----------|
| Nao apurar horas extras | Selecionar quando verba HE nao esta no calculo |
| Excedentes da jornada diaria | HE = excesso diario |
| Excedentes da jornada semanal | HE = excesso semanal |
| Criterio mais favoravel | Compara diario vs semanal, usa maior |
| Excedentes da jornada mensal | HE = excesso mensal |
| Sumula 85 TST | Usuario define limite de compensacao diario. Apura HE separado. |
| Primeiras HE em separado | Usuario define limite de primeiras horas. Apura separado. |
| Considerar Feriados | Identifica feriados (habilita opcoes especificas) |
| Extras feriados em separado | Apura HE de feriados separadamente |
| Extras domingos em separado | Apura HE de domingos separadamente |
| Extras sabados/domingos em separado | Apura HE de sab/dom separadamente |
| Tolerancia por turno e por dia | Limites de tolerancia por turno e dia |

#### Jornada de Trabalho Padrao

Campos: Jornada Diaria (seg-dom), Semanal, Mensal. Sugeridos a partir dos Parametros do Calculo.

Checkboxes:
- "Considerar jornada diaria nos feriados trabalhados" (padrao: desmarcado = jornada zero em feriados)
- "Considerar jornada diaria nos feriados nao trabalhados" (padrao: desmarcado = desconto automatico)

#### Periodos de Descanso (10 opcoes)

- Apurar feriados trabalhados
- Apurar domingos trabalhados
- Apurar sabados e domingos trabalhados
- Supressao intervalo art. 253 CLT (100 min trabalho = 20 min descanso)
- Supressao intervalo art. 384 CLT (15 min entre jornada normal e extraordinaria)
- Supressao intervalo art. 72 CLT (90 min trabalho = 10 min descanso)
- Intervalo Interjornadas (35:00 ou 11:00)
- Intervalo Intrajornada jornada > 4h e <= 6h
- Intervalo Intrajornada jornada > 6h
- Considerar fracionamento do intervalo intrajornada
- Supressao integral ou conforme par. 4 art. 71 CLT

#### Horario Noturno (6 parametros)

Tipos de atividade:
- Agricola: 21:00 as 05:00
- Pecuaria: 20:00 as 04:00
- Urbana: 22:00 as 05:00

Opcoes: Apurar horas noturnas, Apurar HE noturnas, Reducao ficta (52.5 min), Horario Prorrogado Sumula 60 TST, Forcar prorrogacao.

#### Preenchimento de Jornadas (3 opcoes)

1. **Livre**: Campos em branco para preenchimento manual
2. **Programacao Semanal**: Grade por dia da semana. Auto-preenche exceto faltas e ferias.
3. **Escala**: Selecionar escala pre-registrada ou "Outra" com dias trabalhados.

### 10.2 Grade de Ocorrencias

**Aba Jornada**: Editar horarios de entrada/saida. Salvar "por mes".

**ALERTA**: Modificacoes manuais na Grade sao preservadas se usuario alterar Criterio de Apuracao, EXCETO se clicar "Regerar Ocorrencias" na Grade (sobrescreve tudo).

**Aba Importar Jornada**: Importar CSV com especificacoes:
- Primeira coluna: datas (dd/mm/aaaa)
- 12 colunas restantes: horas (hh:mm)
- 6 turnos por grade (entrada/saida cada)

### 10.3 Visualizar Cartao

**Apurar Cartao de Ponto**: Definir "Dia do Fechamento Mensal", adicionar excecoes, clicar "Apurar".

**ALERTA**: Apos modificar Criterio ou Grade, voltar aqui, clicar "Excluir", confirmar, e "Apurar" novamente.

**Importar arquivo externo**: CSV com ate 16 colunas:
- Primeira coluna: mes/ano (mm/aaaa, mm/aa, mmm/aa, mmm/aaaa)
- Colunas restantes: quantidades decimais (max 4 casas)

---

## 11. Salario-familia

### Parametros:

- Marcar checkbox **"Apurar Salario-familia"**
- **Compor Principal**: Padrao "sim". Mudar para "nao" se parcela serve apenas como base condicional.
- **Competencias**: Sistema sugere periodo completo. Usuario pode restringir.
- **Remuneracao Mensal**: Base = Salarios Pagos e/ou Salarios Devidos
  - Salarios Pagos: Nenhum, Maior Remuneracao, ou Historico Salarial (selecionar bases)
  - Salarios Devidos: Selecionar verbas para composicao da base
- **Quantidade de Filhos Menores de 14 Anos**: Informar quantidade. Para variacoes no periodo, informar competencia + nova quantidade + "Adicionar".

**CRITICO**: Clicar "Salvar" para confirmar.

---

## 12. Seguro-desemprego

### Parametros:

- Marcar checkbox **"Apurar Seguro-desemprego"**

**Valor Calculado**:
- **Tipo de solicitacao**: Se desligamento apos 28/02/2015 (MP 665/2014), selecionar: primeira, segunda, ou demais
- **Empregado Domestico**: Marcar checkbox para criterios da Lei 10.208/2001
- **Compor Principal**: Padrao "sim"
- **Quantidade de Parcelas**: Sistema sugere conforme contagem de solicitacoes e tempo de servico
- **Remuneracao Mensal**: Mesma estrutura do Salario-familia

**Valor Informado**:
- **Compor Principal**: Padrao "sim"
- **Valor Informado**: Digitar valor

**CRITICO**: Clicar "Salvar" para confirmar.

---

## 13. FGTS

Contem todos os parametros da parcela FGTS, exceto Base e Recolhido (definidos em Historico Salarial e Parametros da Verba).

### Parametros:

| Campo | Opcoes | Descricao |
|-------|--------|-----------|
| Destino | Pagar ao reclamante / Recolher em conta vinculada | Se pagar: compoe liquido devido. Se recolher: nao compoe. |
| Compor Principal | Sim / Nao | Padrao "sim" |
| Multa | Nao apurar / Calculada / Informada | |
| Percentual da Multa | 20% ou 40% | Somente se Calculada |
| Base da Multa | Devido, Diferenca, Saldo e/ou Saque, Devido (-) Saldo, Devido (+) Saldo | Somente se Calculada |
| Multa art. 467 CLT | Checkbox | Aplica multa de 50% sobre Multa do FGTS |
| Pensao Alimenticia sobre FGTS | Checkbox | Incide PA sobre FGTS |
| Pensao Alimenticia sobre Multa FGTS | Checkbox | Incide PA sobre Multa (disponivel se PA sobre FGTS marcado) |

### Saldo e/ou Saque

Registrar saldos da conta vinculada e/ou saques anteriores do empregado.

Campos: Data + Valor + "Adicionar"

Checkbox "Deduzir" habilitado apos >= 1 registro.

**CRITICO**: Clicar "Salvar" para confirmar.

---

## 14. Contribuicao Social

Contem todos os parametros da parcela, exceto Base e Recolhido (definidos em Historico Salarial e Parametros da Verba).

### Parametros Principais:

| Campo | Descricao |
|-------|-----------|
| Apurar Segurado | Padrao: marcado. Desmarcar se reclamante ja recolheu pelo teto |
| Cobrar do Reclamante | Padrao: marcado. Desmarcar se contribuicao sera cobrada da reclamada |
| CS sobre Salarios Pagos | Marcar apenas quando quiser apurar CS sobre salarios pagos durante contrato |

### Parametros das Ocorrencias (acessar via icone Ocorrencias + Regerar):

**Aliquota Segurado** (3 opcoes):
- Segurado Empregado: usa aliquotas da tabela CS
- Empregado Domestico: usa tabela domestico
- Fixa: usuario digita aliquota %. Opcao "Limitar ao Teto"

**Aliquota Empregador** (contribuicoes Empresa, SAT, Terceiros):
- Por Atividade Economica: buscar atividade por palavra-chave, selecionar, confirmar
- Por Periodo: informar competencias Inicio/Fim + aliquotas + "Adicionar"
- Fixa: digitar aliquota para cada contribuicao selecionada

**Periodo de Incidencia sobre Salarios Devidos**: Data Inicial e Data Final.

**Periodo de Incidencia sobre Salarios Pagos**: Data Inicial e Data Final.

**Periodos SIMPLES**: Periodos de isencao (empresa optante do SIMPLES). Informar Inicio/Fim + "Adicionar".

Apos alteracoes: clicar "Confirmar" para regerar ocorrencias.

### Ocorrencias da Contribuicao Social

Duas abas: **Salarios Devidos** e **Salarios Pagos**.

**Salarios Devidos**: Colunas = Ocorrencias (Mes/Ano), Salarios Pagos (Historico) [editavel], Tipo (Calculado/Informado).

**Salarios Pagos**: Colunas = Ocorrencias, Salarios Pagos (Historico) [editavel], Segurado/Empresa/SAT/Terceiros [editaveis = valores ja recolhidos], Tipo por coluna.

Recursos:
- Copiar valores entre abas
- Recuperar Valores Originais
- Alteracao em Lote

**CRITICO**: Clicar "Salvar" apos todas as alteracoes.

---

## 15. Previdencia Privada

Base de calculo definida pelo campo "incidencia Previdencia Privada" nos parametros das verbas.

### Parametros:

- Marcar checkbox **"Apurar Previdencia Privada"**
- **Aliquota por Periodo**: Sistema sugere periodo do calculo. Informar competencia Inicial/Final + aliquota % + "Adicionar". Repetir para multiplas aliquotas.

**CRITICO**: Clicar "Salvar" para confirmar.

---

## 16. Pensao Alimenticia

Base de calculo definida pelo campo "incidencia Pensao Alimenticia" nos parametros das verbas e pelos campos "incidir PA sobre FGTS" e "incidir PA sobre Multa FGTS" na pagina FGTS.

### Parametros:

- Marcar checkbox **"Apurar Pensao Alimenticia"**
- **Aliquota**: Percentual a aplicar sobre base de calculo
- **Incidir sobre Juros**: Padrao desmarcado. Marcar para incidir PA sobre juros de mora relativos a sua base.

**CRITICO**: Clicar "Salvar" para confirmar.

---

## 17. Imposto de Renda

Base de calculo definida pelo campo "incidencia IRPF" nos parametros das verbas.

### Regra de Calculo:

O sistema segue os artigos 12 e 12-A da Lei 7713/1988:
- Liquidacao anterior a 28/07/2010: tabela progressiva mensal vigente na data da liquidacao
- Liquidacao a partir de 28/07/2010: divide base em:
  - Rendimentos de anos-calendario anteriores ao da liquidacao (tabela progressiva acumulada)
  - Rendimentos do ano-calendario da liquidacao (tabela progressiva mensal)

### Parametros:

| Campo | Descricao |
|-------|-----------|
| Apurar Imposto de Renda | Checkbox obrigatorio |
| Incidir sobre Juros de Mora | Inclui juros de mora na base do IR |
| Cobrar do Reclamado | Quando reclamado responsavel pelo recolhimento |
| Tributacao Exclusiva | Apura IR separado sobre verbas com caracteristica 13o Salario |
| Tributacao em Separado | Apura IR separado sobre verbas com caracteristica Ferias |
| Aplicar Regime de Caixa | Aplica tabela mensal vigente na data da liquidacao sobre toda a base |

### Deducoes da Base:

| Deducao | Condicao |
|---------|----------|
| Contribuicao Social do Reclamante | Apenas se "Cobrar do Reclamante" estiver marcado na pagina CS |
| Previdencia Privada | Padrao: marcado |
| Pensao Alimenticia | Padrao: marcado |
| Honorarios Devidos pelo Reclamante | Apenas se Reclamante for devedor na pagina Honorarios |
| Aposentado Maior de 65 anos | Aplica desconto da tabela progressiva mensal |
| Dependentes | Informar numero. Desconto por dependente conforme tabela |

**CRITICO**: Clicar "Salvar" para confirmar.

---

## 18. Multas e Indenizacoes

Para multas e indenizacoes incidentes sobre valor da causa ou valor da condenacao.

Acesso: pagina Multas e Indenizacoes > icone "Novo".

### Parametros:

| Campo | Opcoes | Descricao |
|-------|--------|-----------|
| Descricao | Texto ate 60 caracteres | Nome da parcela |
| Credor/Devedor | Reclamante e Reclamado, Reclamado e Reclamante, Terceiro e Reclamante, Terceiro e Reclamado | Se Terceiro: campo para nome. Se "Terceiro e Reclamante": optar entre Descontar dos creditos ou Cobrar do reclamante |
| Valor | Calculado ou Informado | |

**Valor Calculado**:
- Base: Principal, Principal (-) CS, Principal (-) CS (-) PP
- Aliquota: informar percentual

**Valor Informado**:
- Vencimento: data a partir da qual atualizar
- Valor: valor monetario
- Indice de correcao: Utilizar indice trabalhista OU Utilizar outro Indice
- Juros: aplicar conforme Dados Gerais da pagina Correcao/Juros/Multa

**CRITICO**: Clicar "Salvar" apos preencher.

---

## 19. Honorarios

Acesso: pagina Honorarios > icone "Novo".

### Parametros:

| Campo | Opcoes |
|-------|--------|
| Tipo de Honorarios | Lista de rubricas do PJe-JT |
| Descricao | Texto ate 60 caracteres |
| Devedor | Reclamante ou Reclamado. Se Reclamante: Descontar dos creditos ou Cobrar |
| Tipo de Valor | Calculado ou Informado |

**Valor Calculado**:
- Aliquota: percentual sobre valor da condenacao
- Base: Bruto, Bruto (-) CS, Bruto (-) CS (-) PP

**Valor Informado**:
- Vencimento + Valor
- Indice de correcao: trabalhista ou outro
- Aplicar Juros: conforme Dados Gerais

**Honorarios de Sucumbencia** (devedor Reclamante):
- Campo "Base para Apuracao" permite optar por "Verbas que Nao Compoem o Principal"
- Sistema lista verbas nao-principal para usuario selecionar

**Dados do Credor**:
- Se advogado cadastrado: selecionar da lista
- Senao: informar Nome Completo, Tipo Documento Fiscal (CPF, CNPJ, CEI), numero

**Apurar Imposto de Renda sobre Honorarios**:
- Tipo: IRPF (tabela progressiva mensal) ou IRPJ (aliquota fixa 1,5%)
- Incidir sobre Juros: disponivel se Aplicar Juros e Apurar IR marcados

**CRITICO**: Clicar "Salvar" apos preencher.

---

## 20. Custas Judiciais

Pagina com duas abas: **Custas Devidas** e **Custas Recolhidas**.

### Aba Custas Devidas

**Base das Custas de Conhecimento e Liquidacao**:
- Bruto Devido ao Reclamante (Verbas + FGTS + Multas/Indenizacoes com correcao e juros)
- Bruto Devido ao Reclamante + Outros Debitos da Reclamada (CS, Honorarios, Multas)

**Custas do Reclamante - Conhecimento**:
- Padrao: "nao se aplica"
- Opcoes: Calculada 2% ou Informada (Vencimento + Valor)
- Minimo: R$10,64
- Se ajuizamento apos 10/11/2017: teto = 4x limite maximo beneficios previdencia
- Optar: Descontar dos creditos ou Cobrar do reclamante

**Custas do Reclamado**:

| Tipo | Padrao | Opcoes |
|------|--------|--------|
| Conhecimento | Calculada 2% | Calculada 2%, Informada, nao se aplica. Min R$10,64 |
| Liquidacao | nao se aplica | Calculada 0,5%, Informada. Max R$638,46 |
| Fixas | - | Tipos: Oficiais Zona Urbana/Rural, Agravo Instrumento/Peticao, Impugnacao, Embargos, Recurso de Revista. Informar Vencimento + Quantidade |
| Autos | - | Tipos: Adjudicacao, Arrematacao, Remissao. Vencimento + Valor do Bem |
| Armazenamento | - | Data Inicio + Valor do Bem. Data Termino = saida do deposito ou data da liquidacao |

### Aba Custas Recolhidas

Registrar valores ja recolhidos: Vencimento + Valor + "Adicionar".

**CRITICO**: Clicar "Salvar" apos preencher ambas as abas.

---

## 21. Correcao, Juros e Multa

Parametros de atualizacao para: Verbas, Salario-familia, Seguro-desemprego, FGTS, CS, PP, Custas.
(Honorarios e Multas/Indenizacoes: parametros definidos nas paginas proprias. PA e IR: sem parametros de atualizacao no modulo Calculo.)

### Aba Dados Gerais

Atualiza automaticamente: Verbas, Salario-familia, Seguro-desemprego.
Atualiza alternativamente (conforme Dados Especificos): FGTS, CS, PP, Custas.

**Indice Trabalhista** (opcoes):
- Tabela Unica da JT Diario
- Tabela Unica da JT Mensal
- TR
- IGP-M
- INPC
- IPC
- IPCA
- IPCA-E
- IPCA-E/TR

**Combinar com Outro Indice**: Marcar checkbox, selecionar segundo indice, informar data "A partir de".

**Ignorar Taxa Negativa**: Checkbox para usar apenas taxas >= 0%.

**Juros de Mora**:
- Padrao: Juros Simples 0,5% a.m. ate 26/02/1987, Capitalizados 1% a.m. ate 03/03/1991, Simples 1% a.m. a partir de 04/03/1991
- Fazenda Publica: Simples 0,5% a.m., limitados a 70% SELIC a partir de 04/05/2012
- Nao Aplicar Juros: informar periodos Inicio/Fim + "Adicionar"

### Aba Dados Especificos

**Base de Juros das Verbas**: Verba, Verba (-) CS, Verba (-) CS (-) PP

**FGTS**:
- Utilizar indice trabalhista (padrao)
- Utilizar indice JAM (ja inclui juros + correcao)
- Utilizar JAM + indice trabalhista (JAM ate demissao, trabalhista depois)

**Previdencia Privada**: Indice trabalhista ou outro indice. Checkbox Juros.

**Custas Judiciais**: Nao atualiza por padrao. Indice trabalhista ou outro. Checkbox Juros.

**Contribuicao Social -- Salarios Devidos**:

Opcoes combinaveis:
- **Lei 11.941/2009**: CS devidas a partir de data informada atualizadas com correcao/juros/multa desde prestacao servico. Opcao "Limitar multa".
- **Atualizacao Trabalhista**: CS devidas no dia 2 do mes seguinte a liquidacao. Apenas correcao monetaria. Checkbox Juros opcional.
- **Atualizacao Previdenciaria**: "Mes-a-mes" ou "A partir de" com juros e multa.
- **Ambas**: Trabalhista ate data informada, Previdenciaria a partir do dia 2 do mes seguinte.
- **Multa Previdenciaria**: Tipo Urbana/Rural. Pagamento Integral/Reduzido (reducao 50% entre 11/1999 e 11/2008).

**Contribuicao Social -- Salarios Pagos**: Mesma estrutura dos Salarios Devidos.

**CRITICO**: Clicar "Salvar" apos preencher ambas as abas.

---

## 22. Operacoes do Calculo

Aba Operacoes habilitada a partir de um calculo aberto (pelo menos Dados do Calculo salvos).

### 22.1 Liquidar

Processamento dos parametros estabelecidos para todas as parcelas.

**Campos**:
- **Data da Liquidacao**: Obrigatoria
- **Acumular Indices de Correcao** (3 opcoes):
  1. A partir do mes subsequente ao vencimento das verbas (todas as verbas)
  2. A partir do mes de vencimento das verbas (todas as verbas)
  3. Misto: mes subsequente para verbas mensais, mes de vencimento para verbas anuais e rescisorias

**Pendencias do Calculo**: Sistema verifica pendencias ao acessar pagina Liquidar:
- **Alerta**: Pendencia que nao impede liquidacao
- **Erro**: Pendencia que inviabiliza liquidacao

Pendencias listadas por pagina. Clicar em cada pendencia abre pagina correspondente para correcao.

**Executar**: Apos definir data, criterio de acumulacao e corrigir erros, clicar icone "Liquidar".

### 22.2 Imprimir

Gera Relatorio do Calculo composto de:
- Resumo Precatorio / RPV
- Resumo de Calculo
- Criterio de Calculo e Fundamentacao Legal
- Dados do Calculo
- Faltas e Ferias
- Cartao de Ponto Diario e Mensal
- Historico Salarial
- Verbas e Juros sobre Verbas
- Salario-familia, Seguro-desemprego
- FGTS, Contribuicao Social
- eSocial - Evento S-2500
- Previdencia Privada, Pensao Alimenticia
- Imposto de Renda
- Multas/Indenizacoes, Honorarios, Custas Judiciais

**Resumo de Calculo**: Composicao do Bruto Devido (verbas, FGTS, multas) + Creditos/Debitos do Reclamante + Debitos do Reclamado por credor.

### 22.3 Fechar

Fecha o calculo aberto. Pode ser acionado de qualquer pagina.

### 22.4 Excluir

Exclui calculo aberto. Mensagem de confirmacao (OK/Cancelar).

### 22.5 Exportar

**Procedimento**:
1. Abrir o calculo
2. Clicar operacao "Exportar"
3. Sistema abre pagina Exportar e cria arquivo XML
4. Clicar icone "Exportar"
5. Escolher diretorio para salvar arquivo .PJC

**IMPORTANTE**: O arquivo .PJC valido so e gerado APOS liquidacao. Arquivos pre-liquidacao sao rejeitados na importacao.

### 22.6 Enviar para o PJe

Exclusivo do PJe-Calc interno dos TRTs. PJe-Calc Cidadao NAO possui esta funcionalidade.

Procedimento (interno): Acessar pagina > digitar justificativa > "Consolidar Dados" > "Enviar para o PJe" > confirmar > assinar digitalmente (PIN).

---

## 23. Calculo Externo

Para atualizar calculos ja existentes (nao criados no PJe-Calc).

### 23.1 Dados do Calculo Externo

Duas abas: Dados do Processo e Parametros do Calculo Externo.

**Dados do Processo**: Opcional. Mesmo formato do Novo Calculo.

**Parametros do Calculo Externo** -- Campos obrigatorios:
- Data da Ultima Atualizacao
- Quantidade de meses dos rendimentos tributaveis

Parametros de correcao e juros: mesmo formato do Novo Calculo.

Parametros especificos:
- FGTS: Destino (pagar/recolher), Multa (calculada/informada), Contribuicao Social LC 110/2001
- Contribuicao Social: mesma estrutura do Novo Calculo
- Custas: mesma estrutura
- Imposto de Renda: mesma estrutura com deducoes

### 23.2 Parcelas Atualizaveis

Quatro abas conforme destinacao:

**Creditos do Reclamante**:
- Verbas Tributaveis (valor + juros de mora)
- Verbas Nao Tributaveis (valor + juros)
- FGTS (valor + juros)
- Multa/Indenizacao Devida ao Reclamante (+)
- Multa/Indenizacao Devida ao Reclamado (-)

**Descontos dos Creditos do Reclamante**:
- CS Segurado
- Previdencia Privada
- Pensao Alimenticia (aliquota + base + opcao juros)
- Multa/Indenizacao Devida a Terceiros
- Honorarios Devidos pelo Reclamante
- Custas de Conhecimento

**Outros Debitos do Reclamado**:
- CS Empregador (Empresa, SAT, Terceiros)
- CS Segurado (cobrar do reclamado)
- Previdencia Privada (juros)
- Honorarios
- Multa/Indenizacao
- Custas (Conhecimento, Liquidacao, Fixas, Autos, Armazenamento)

**Debitos do Reclamante**:
- Honorarios Devidos pelo Reclamado ao advogado do Reclamante

### 23.3 Operacoes do Calculo Externo

Mesmas operacoes: Fechar, Excluir, Exportar (sem Liquidar separado, sem Enviar para PJe).

---

## 24. Tabelas

Tabelas de referencia com valores historicos:

### 24.1 Salario Minimo
Valores desde janeiro/1967. Paginacao de 24 registros.

### 24.2 Piso Salarial
Valores por categoria profissional. Busca por Nome e/ou Estado.

### 24.3 Salario-familia
Tabela com valores historicos.

### 24.4 Seguro-desemprego
Tabela com valores historicos.

### 24.5 Vale Transporte
Linhas urbanas e interurbanas por estado.

### 24.6 Feriados e Pontos Facultativos
Nacionais, estaduais e municipais.

### 24.7 Verbas
Todas as Verbas Principais e Reflexas cadastradas. Busca por Nome, Valor, Tipo. Visualizar parametros sugeridos por verba.

### 24.8 Contribuicao Social
Duas abas: Segurado Empregado e Empregado Domestico. Faixas salariais, aliquotas e teto desde jan/1967 e jan/1973.

### 24.9 Imposto de Renda
IRPF: deducoes por dependente, aposentado > 65, faixas salariais, aliquotas, deducoes desde jan/1992.

### 24.10 Custas Judiciais
Tabela de custas.

### 24.11 Correcao Monetaria

Abas:
- **Tabela Unica TUACDT**: Taxas diarias, capitalizacao composta. Resolucao CSJT 08/2005, alterada pelo STF (ADC 58/59, ADI 5.867/6.021) para IPCA-E a partir de 01/01/2000.
- **Tabela Unica JT Mensal**: Taxas mensais e indices acumulados (vigencia anterior ao STF).
- **Tabela Unica JT Diaria**: Taxas diarias e indices acumulados.
- **UFIR**: Jan/1992 a dez/2000.
- **Coeficiente UFIR**: Para debitos previdenciarios anteriores a jan/1995.
- **IGP-M**: Desde jun/1989.
- **INPC**: Indice Nacional de Precos ao Consumidor.
- **IPC**: Indice de Precos ao Consumidor.
- **IPCA**: Indice de Precos ao Consumidor Amplo.
- **IPCA-E**: IPCA Especial.
- **TR**: Taxa Referencial.

Consulta: campos "Tabela de" (vigencia) e "A partir de" (inicio) + "Pesquisar".

### 24.12 Juros de Mora

Quatro tabelas:
- **Juros Padrao**: Composicao historica de taxas oficiais. Vigencia, Aliquota, Tipo (Simples/Composto), Tipo Quantidade (Inteiro/Fracao).
- **Juros Fazenda Publica**: Taxas para entes publicos.
- **Juros SELIC Contribuicao Social**: Taxas mensais acumuladas desde mar/1967.
- **Juros SELIC Imposto de Renda**: Taxas mensais acumuladas desde mar/1967.

---

## 25. Atualizacao

Disponivel apos calculo aberto e liquidado. Oito paginas:

### 25.1 Dados do Pagamento

Campos: Data do Pagamento, Valor Total do Pagamento, Folhas/IDs do processo.

Distribuicao entre tres abas:

**Creditos do Reclamante**: Principal, FGTS, Multas/Indenizacoes. Opcao "Apurar" (distribuicao proporcional) ou fixar valores. Opcao "Priorizar Pagamento de Juros".

**Recolher Descontos do Reclamante**: Checkbox habilitado se parte do valor retida. Descontos: Custas, Deposito FGTS, CS, PP, PA, IR, Multas/Indenizacoes Terceiros, Honorarios. Opcao "Apurar" ou fixar.

**Outros Debitos do Reclamado**: Preenchimento automatico (diferenca entre total e creditos do reclamante). Debitos: CS Empregador, CS Segurado, PP, Honorarios, Multas/Indenizacoes, Custas.

### 25.2 Pensao Alimenticia (Atualizacao)

Marcar "Apurar PA", estabelecer Data do Evento, Aliquota, Incidir sobre Juros, Identificacao, selecionar bases (Principal Tributavel, Nao Tributavel, FGTS).

### 25.3 Multas e Indenizacoes (Atualizacao)

Mesma estrutura da pagina original.

### 25.4 Honorarios (Atualizacao)

Mesma estrutura da pagina original.

### 25.5 Custas Judiciais (Atualizacao)

Mesma estrutura da pagina original.

### 25.6 Liquidar Atualizacao

Campos: Data de Liquidacao, Identificacao do Calculo (folhas/IDs), opcao de cobrar encargos sobre IR ou Honorarios nao recolhidos na epoca.

### 25.7 Imprimir Atualizacao

Mesma estrutura do Imprimir original.

### 25.8 Atualizacao Calculo Externo

Procedimento identico ao de Calculos Novos, exceto Pensao Alimenticia que segue formato especifico da atualizacao.

---

## Notas Criticas para Automacao

### Regras de Salvamento
- **TODA** pagina requer clique explicito em "Salvar" apos preenchimento
- Navegar sem salvar = PERDA TOTAL de dados da pagina
- Apos salvar, aguardar mensagem de sucesso ("Operacao realizada com sucesso")

### Campos Obrigatorios
- Marcados com asterisco (*)
- Periodo de calculo requer pelo menos Desligamento OU Data Final

### AJAX e JSF
- Maioria dos campos dispara requisicoes AJAX no blur
- Aguardar conclusao do AJAX antes de preencher proximo campo
- ViewState do JSF pode expirar se tempo entre acoes for muito longo

### Sequencia de Preenchimento Recomendada
1. Dados do Calculo (Dados do Processo + Parametros) > Salvar
2. Faltas > Salvar
3. Ferias (verificar sugestoes) > Salvar
4. Historico Salarial (criar bases) > Salvar
5. Verbas (Expresso e/ou Manual) > Salvar
6. Cartao de Ponto (se necessario) > Salvar
7. Salario-familia (se necessario) > Salvar
8. Seguro-desemprego (se necessario) > Salvar
9. FGTS > Salvar
10. Contribuicao Social > Salvar
11. Previdencia Privada (se necessario) > Salvar
12. Pensao Alimenticia (se necessario) > Salvar
13. Imposto de Renda > Salvar
14. Multas e Indenizacoes (se necessario) > Salvar
15. Honorarios > Salvar
16. Custas Judiciais > Salvar
17. Correcao, Juros e Multa > Salvar
18. Operacoes > Liquidar (definir data + criterio)
19. Operacoes > Exportar

### IDs de Elementos DOM Conhecidos

Referir ao arquivo `knowledge/pje_calc_official/tutorial_rules.md` e ao documento `docs/dom-ids-confirmed.md` para IDs reais confirmados por inspecao DOM.

### Verbas Expresso -- Paginacao

A tabela do Lancamento Expresso usa `<a4j:repeat>` com layout de colunas. Apenas ~27 verbas visiveis no viewport. Para acessar verbas abaixo do scroll, necessario:
1. Scroll via JavaScript (`element.scrollIntoView()`)
2. Re-enumeracao dos elementos apos scroll

### Firefox Obrigatorio

PJe-Calc desenvolvido para Firefox. Chromium causa incompatibilidades em:
- Eventos AJAX do RichFaces
- Calendarios (componente RichFaces Calendar)
- Popups JSF
