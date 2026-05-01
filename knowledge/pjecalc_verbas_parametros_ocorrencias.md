# Parâmetros e Ocorrências da Verba — Particularidades por Característica

Conferência via Chrome MCP no calc 262818 (TRT7 Institucional 2.15.1).
Documenta os DEFAULTS automáticos e estrutura específica de cada característica.

## Endpoints

- **Parâmetros da Verba**: link `formulario:listagem:N:j_id558` (ícone)
  - Abre form inline em `verba/verba-calculo.jsf` (mesma URL da listagem)
- **Ocorrências da Verba**: link `formulario:listagem:N:j_id559`
  - Navega para `parametrizar-ocorrencia.jsf?conversationId=N` (URL dedicada)
- **Excluir**: link `formulario:listagem:N:j_id560`

## Particularidades por Característica

### 1. **COMUM** (ex: SALDO DE SALÁRIO, MULTA 477, HORAS EXTRAS)

**Parâmetros (defaults automáticos):**
- `caracteristicaVerba` = COMUM
- `ocorrenciaPagto` = MENSAL ou DESLIGAMENTO (depende da verba específica)
- `tipoDaQuantidade` opções: INFORMADA (default), IMPORTADA_DO_CALENDARIO,
  IMPORTADA_DO_CARTAO_DE_PONTO, ... (4 opções)
- `tipoDeDivisor` opções: OUTRO_VALOR, CARGA_HORARIA (default), DIAS_UTEIS,
  IMPORTADA_DO_CARTAO (4 opções)
- `tipoDaBaseTabelada` default: HISTORICO_SALARIAL ou MAIOR_REMUNERACAO
- Incidências: dependem da natureza (rescisórias podem vir false)

**Ocorrências:**
- Para `ocorrenciaPagto=DESLIGAMENTO`: **1 linha única** (mês do desligamento)
- Para `ocorrenciaPagto=MENSAL`: **N linhas mensais** (uma por mês do período)

### 2. **DECIMO_TERCEIRO_SALARIO** (13º Salário)

**Parâmetros (defaults automáticos):**
- `caracteristicaVerba` = DECIMO_TERCEIRO_SALARIO
- `ocorrenciaPagto` = **DEZEMBRO** (auto-selecionado, demais desabilitados)
- `tipoDaQuantidade` = AVOS (auto-selecionado)
- `tipoDeDivisor` = OUTRO_VALOR
- `tipoDaBaseTabelada` = HISTORICO_SALARIAL
- Incidências: FGTS=true, INSS=true, IRPF=true (natureza salarial)

**Ocorrências:**
- N linhas para cada Dezembro do período + dezembro de cada ano completo
- Cada linha tem `termoDiv=12` (avos do 13º), `termoMult=1`, `termoQuant=12`
  (ou menor para anos proporcionais)
- Sistema calcula automaticamente a fração proporcional baseado em
  data_inicio/fim de cada ano

### 3. **AVISO_PREVIO** (Aviso Prévio Indenizado)

**Parâmetros (defaults automáticos):**
- `caracteristicaVerba` = AVISO_PREVIO
- `ocorrenciaPagto` = DESLIGAMENTO (auto-selecionado)
- `tipoDaQuantidade`: depende da config em `apuracaoPrazoDoAvisoPrevio`
  da Fase 1:
  - **APURACAO_CALCULADA** (Calculado) → Quantidade APURADA automaticamente
    pelo sistema (Lei 12.506/2011: 30 dias + 3/ano completo, máx 90)
  - **APURACAO_INFORMADA** (Informado) → quantidade digitada manualmente
  - **NAO_APURAR** → 30 dias fixos
- `tipoDeDivisor` = OUTRO_VALOR
- `tipoDaBaseTabelada` = MAIOR_REMUNERACAO (default)
- Incidências: FGTS=true, INSS=false, IRPF=false (natureza indenizatória)

**Ocorrências:**
- Linha única (DESLIGAMENTO)
- Quantidade = N (dias de aviso prévio); o sistema calcula valor por dia

### 4. **FERIAS** (Férias + 1/3)

**Parâmetros (defaults automáticos):**
- `caracteristicaVerba` = FERIAS
- `ocorrenciaPagto` = **PERIODO_AQUISITIVO** (auto-selecionado)
- `tipoDaQuantidade` opções **REDUZIDAS** para: INFORMADA, AVOS (apenas 2)
- `tipoDeDivisor` = OUTRO_VALOR
- `tipoDaBaseTabelada` = MAIOR_REMUNERACAO
- Incidências: FGTS=false, INSS=false, IRPF=false (natureza indenizatória)

**Ocorrências:**
- N linhas (uma por período aquisitivo: 12 meses cada)
- Cada linha pode estar:
  - Ativa = férias devidas
  - Inativa = férias gozadas (não cabe pagamento)
- `termoDiv=12`, `termoMult=1`, `termoQuant=12` para período integral
- Sistema gera proporcional para período incompleto da rescisão

## Estrutura da Grade de Ocorrências

**URL:** `pages/calculo/parametrizar-ocorrencia.jsf?conversationId=N`

**Headers das colunas:**
1. Ativar Todos (checkbox global)
2. Data Inicial
3. Data Final
4. Valor (label "Calculado" — vem do tipoValor)
5. Divisor (`termoDiv`)
6. Multiplicador (`termoMult`)
7. Quantidade (`termoQuant`)
8. Dobra
9. Devido (`valorDevido`)
10. Pago * (`valorPago`)
11. Selecionar Todos

**IDs por linha (N = índice 0+):**
- `formulario:listagem:N:ativo` (checkbox)
- `formulario:listagem:N:dobra` (checkbox)
- `formulario:listagem:N:termoDiv` (text)
- `formulario:listagem:N:termoMult` (text)
- `formulario:listagem:N:termoQuant` (text)
- `formulario:listagem:N:valorDevido` (text)
- `formulario:listagem:N:valorPago` (text)
- `formulario:listagem:N:selecionar` (checkbox)

**Campos do form geral (params globais aplicados):**
- `formulario:dataInicialInputDate`, `dataFinalInputDate`
- `formulario:divisor`, `multiplicador`, `quantidade`
- `formulario:devido`, `pago`
- `formulario:dobra` (checkbox)
- `formulario:propDevido`, `propPago`, `propQuantidade` (proporcionalizar)
- Botões: `recuperar`, `cancelar`, `salvar`

## Aplicação Prática para Automação

### Quando NÃO precisa abrir Parâmetros/Ocorrências:
- Verba lançada via **Lançamento Expresso** com defaults adequados ao caso
- O PJE-Calc auto-preenche tudo baseado na característica + datas do contrato

### Quando precisa abrir Parâmetros:
- Verba **adaptada** (Expresso adaptado): mudar característica/ocorrência
- Mudar base de cálculo (HISTORICO → MAIOR_REMUNERACAO)
- Marcar/desmarcar incidências FGTS/INSS/IRPF específicas
- Configurar `tipoDeDivisor` ou `tipoDaQuantidade` customizado

### Quando precisa abrir Ocorrências:
- **Sentença restringe verba a período específico** (ex: HE só em
  meses com cartão de ponto)
- **Desativar meses**: férias gozadas, períodos sem trabalho
- **Customizar valor** por mês individualmente
- **Importar do cartão de ponto** (vincular ocorrências às horas
  efetivamente apuradas)

### Defaults a respeitar:
- 13º: ocorrência DEZEMBRO + AVOS (sistema calcula proporcional)
- Férias: PERIODO_AQUISITIVO + AVOS, somente INFORMADA/AVOS no select
- Aviso Prévio: DESLIGAMENTO + APURACAO_CALCULADA quando proporcional
  Lei 12.506/2011 (sistema apura 30+3/ano, máx 90)
- Saldo Salário, Multa 477: DESLIGAMENTO (1 ocorrência única)
- Horas Extras, Intervalo: MENSAL (N ocorrências mensais)

## Particularidades adicionais — Verbas variáveis (Expresso 2026-05-01)

Inspeção via Chrome MCP no calc 262818 com 8 verbas adicionadas via Expresso
(HE 50%, INTERVALO INTRAJORNADA, COMISSÃO, GORJETA, DIÁRIAS-INTEGRAÇÃO,
AD INSALUBRIDADE 20%, AD NOTURNO 20%, HORAS IN ITINERE).

### Campos novos descobertos (form Parâmetros)

Além dos já documentados (caracteristicaVerba, ocorrenciaPagto, tipoDaQuantidade,
tipoDeDivisor, tipoDaBaseTabelada), Parâmetros expõe:

- `formulario:tipoVariacaoDaParcela` (radio): **FIXA** | **VARIAVEL**
  - FIXA: AD INSALUBRIDADE/PERICULOSIDADE (parcela fixa mensal)
  - VARIAVEL: HE, INTERVALO, COMISSÃO, GORJETA, DIÁRIAS, AD NOTURNO, IN ITINERE
- `formulario:valor` (radio): CALCULADO* | INFORMADO
- `formulario:tipoDeVerba` (radio): PRINCIPAL* | REFLEXO
- `formulario:gerarPrincipal` / `formulario:geraReflexo` (radio): DEVIDO | DIFERENCA*
- `formulario:comporPrincipal` (radio): SIM* | NAO
  - **DIÁRIAS-INTEGRAÇÃO = NAO** (não compõe principal — só integra base)
- `formulario:tipoDoValorPago` (radio): INFORMADO* | CALCULADO
- `formulario:ocorrenciaAjuizamento` (radio):
  OCORRENCIAS_VENCIDAS_E_VINCENDAS | OCORRENCIAS_VENCIDAS*

### Campos de base de cálculo

- `formulario:tipoDaBaseTabelada` (select): MAIOR_REMUNERACAO | HISTORICO_SALARIAL* |
  SALARIO_DA_CATEGORIA (Piso Salarial) | SALARIO_MINIMO | VALE_TRANSPORTE
  - **AD INSALUBRIDADE 20% default = SALARIO_MINIMO** (não HISTORICO!)
- `formulario:baseHistoricos` (select): NoSelection* | ADICIONAL DE INSALUBRIDADE PAGO |
  SALÁRIO BASE | ÚLTIMA REMUNERAÇÃO
  - **CRÍTICO**: campo OBRIGATÓRIO quando `tipoDaBaseTabelada=HISTORICO_SALARIAL`
  - Se ficar em NoSelection, Liquidar falha com erro:
    `"Falta selecionar pelo menos um Histórico Salarial para apurar o Valor Devido"`
- `formulario:baseVerbaDeCalculo` (select): permite somar OUTRA verba à base
  (ex: HE com base sobre COMISSÃO + SALARIO BASE)
- `formulario:integralizarBase` (select): SIM* | NAO
  - AD INSALUBRIDADE 20% default = NAO
- `formulario:proporcionalizaHistorico` (select): SIM | NAO*
  - GORJETA default = SIM (única assim entre as testadas)

### Multiplicadores e divisores

- `formulario:outroValorDoMultiplicador` (texto livre):
  - HE 50%, INTERVALO INTRAJORNADA, IN ITINERE = "1,5"
  - GORJETA = "0,1" (10%)
  - AD INSALUBRIDADE 20%, AD NOTURNO 20% = "0,2" (20%)
  - COMISSÃO, DIÁRIAS = "1"
- `formulario:outroValorDoDivisor` (texto livre): default "1"
  (usado quando `tipoDeDivisor=OUTRO_VALOR`)
- `formulario:valorInformadoDaQuantidade` (texto livre): "0" ou "1"

### Incidências e exclusões (checkboxes)

- `formulario:fgts`, `formulario:inss`, `formulario:irpf`:
  - true (salarial): HE, INTERVALO, COMISSÃO, GORJETA, AD INSALUB, AD NOTURNO, IN ITINERE
  - **false (indenizatória): DIÁRIAS-INTEGRAÇÃO** (única assim)
- `formulario:previdenciaPrivada`, `formulario:pensaoAlimenticia`: false default
- `formulario:zeraValorNegativo`: false default
- `formulario:excluirFaltaJustificada`, `excluirFaltaNaoJustificada`,
  `excluirFeriasGozadas`: true default para verbas mensais
  - **DIÁRIAS-INTEGRAÇÃO = todas false** (não exclui nada)
  - **AD INSALUBRIDADE = excluirFaltaJustificada false** (paga mesmo nas faltas justif.)
- `formulario:dobraValorDevido`: false default
- `formulario:aplicarProporcionalidadeAQuantidade`:
  - true: HE, INTERVALO, AD NOTURNO (verbas com quantidade variável por mês)
  - false: COMISSÃO, GORJETA, DIÁRIAS, AD INSALUB
- `formulario:aplicarProporcionalidadeABase`: presente APENAS em AD INSALUBRIDADE
  (true default)
- `formulario:aplicarProporcionalidadeValorPago`: false default

### Cheat sheet — perfis de verba

| Verba                  | Variação | Divisor       | Mult | Base            | FGTS | Multi |
|------------------------|----------|---------------|------|-----------------|------|-------|
| HE 50%                 | VARIAVEL | CARGA_HORARIA | 1,5  | HISTORICO       | sim  | 1,5   |
| INTERVALO INTRAJORNADA | VARIAVEL | CARGA_HORARIA | 1,5  | HISTORICO       | sim  | 1,5   |
| HORAS IN ITINERE       | VARIAVEL | CARGA_HORARIA | 1,5  | HISTORICO       | sim  | 1,5   |
| AD NOTURNO 20%         | VARIAVEL | CARGA_HORARIA | 0,2  | HISTORICO       | sim  | 0,2   |
| AD INSALUB 20%         | FIXA     | OUTRO_VALOR   | 0,2  | SALARIO_MINIMO  | sim  | 0,2   |
| COMISSÃO               | VARIAVEL | OUTRO_VALOR   | 1    | HISTORICO       | sim  | 1     |
| GORJETA                | VARIAVEL | OUTRO_VALOR   | 0,1  | HISTORICO       | sim  | 0,1   |
| DIÁRIAS-INTEGRAÇÃO     | VARIAVEL | OUTRO_VALOR   | 1    | HISTORICO       | NÃO  | 1     |

### Estrutura da grade de Ocorrências (HE 50%)

URL: `parametrizar-ocorrencia.jsf?conversationId=N`

Para cada mês do contrato (1 linha por mês):
- `termoDiv` = "220" (carga horária mensal — divisor)
- `termoMult` = "1,5" (multiplicador da hora extra 50%)
- `termoQuant` = "0" (DEVE ser preenchido pelo usuário com nº horas extras)
- `dobra` = checkbox (default false)
- `valorDevido` = "" (calculado pelo sistema após salvar)
- `valorPago` = "0,00" (preencher se houve pagamento parcial)
- `selecionar` = checkbox

**ALERTA**: Se todas as ocorrências forem salvas com `termoQuant=0`,
PJE-Calc emite alerta "Todas as ocorrências da verba X foram salvas com
quantidade igual a zero" (não impede Liquidar mas zera o valor da verba).

**ALERTA**: Se mudar `valorInformadoDaQuantidade` em Parâmetros depois de
gerar Ocorrências, PJE-Calc emite alerta:
"O parâmetro Quantidade foi alterado após a geração das ocorrências da
verba X" — recomenda regerar.

## Pendências comuns na Liquidação

Acessível em `liquidacao.jsf` ao clicar Liquidar. Há 2 níveis:

- **Erro** (impede Liquidar)
- **Alerta** (não impede)

### Erros típicos descobertos

1. **"O Histórico Salarial ÚLTIMA REMUNERAÇÃO não possui valor cadastrado
   para todas as ocorrências da Contribuição Social sobre Salários Devidos."**
   - Causa: rescisória adicionada sem cadastro completo de Histórico Salarial
     ÚLTIMA REMUNERAÇÃO (mês a mês) na aba "Contribuição Social"
   - Fix: cadastrar histórico ÚLTIMA REMUNERAÇÃO na aba Contribuição Social
     OU mudar a base de CS para outro tipo

2. **"Falta selecionar pelo menos um Histórico Salarial para apurar o
   Valor Devido da Verba {NOME}."**
   - Causa: a verba NÃO tem nenhuma "Base Cadastrada" do tipo Histórico Salarial
   - **Fluxo correto (descoberta crítica 2026-05-01)**:
     1. Na página Parâmetros da verba, selecione `formulario:baseHistoricos`
        com uma das opções: `ÚLTIMA REMUNERAÇÃO`, `SALÁRIO BASE`,
        `ADICIONAL DE INSALUBRIDADE PAGO`.
     2. **Clique no link `formulario:incluirBaseHistorico`**
        (title='Adicionar Base'). Isso adiciona uma linha à tabela
        "Bases Cadastradas" da verba, com colunas:
        Histórico Salarial | Proporcionalizar | (link Excluir).
     3. Salve a verba.
   - **Apenas selecionar o select NÃO basta** — a Liquidação só reconhece
     bases que estejam efetivamente na tabela "Bases Cadastradas".
   - **CRÍTICO PARA AUTOMAÇÃO**: o Lançamento Expresso NÃO preenche
     bases automaticamente. A automação DEVE:
     - selecionar `formulario:baseHistoricos` (default seguro: ÚLTIMA REMUNERAÇÃO)
     - clicar `formulario:incluirBaseHistorico`
     - aguardar AJAX
     - clicar `formulario:salvar`
     Para cada verba com `tipoDaBaseTabelada=HISTORICO_SALARIAL`.

   **Verificação prévia**: antes de incluir, checar se a tabela
   "Bases Cadastradas" já tem uma linha com texto contendo `ÚLTIMA REMUNERAÇÃO`
   ou `SALÁRIO BASE` (heurística: linha com link de exclusão na coluna Ação).
   Se sim, pular para evitar duplicação.

### Alertas típicos descobertos

1. "Todas as ocorrências da verba {NOME} foram salvas com quantidade igual a zero."
   - Sinaliza verba zerada (lançamento incompleto)

2. "O parâmetro Quantidade foi alterado após a geração das ocorrências da verba {NOME}."
   - Sinaliza dessincronia entre Parâmetros e Ocorrências
   - Fix: re-gerar ocorrências (link "Recuperar" na grade)

## Reflexos auto-gerados pelo Lançamento Expresso

Inspeção via Chrome MCP no calc 262818 com 13 verbas (8 variáveis + 5 rescisórias).
A listagem de Verbas (verba-calculo.jsf) mostra cada verba PRINCIPAL com link
"Exibir" que expande as REFLEXAS associadas. Total observado: 86 linhas (13 mains
+ ~50 reflexas + linhas separadoras).

### Padrão por característica de verba

#### Verbas variáveis HABITUAIS (HE 50%, INTERVALO INTRAJORNADA, IN ITINERE, AD NOTURNO 20%, COMISSÃO, DIÁRIAS-INTEGRAÇÃO)

Reflexos auto-gerados (6 verbas reflexas cada):
1. AVISO PRÉVIO (×2 — provavelmente uma para indenizado, outra para trabalhado)
2. FÉRIAS + 1/3
3. MULTA DO ARTIGO 477 DA CLT
4. REPOUSO SEMANAL REMUNERADO E FERIADO ← exclusivo de habituais variáveis
5. 13º SALÁRIO

#### AD INSALUBRIDADE 20% (FIXA, base SALARIO_MINIMO)

Reflexos (5 verbas — SEM RSR porque é parcela fixa mensal):
1. AVISO PRÉVIO (×2)
2. FÉRIAS + 1/3
3. MULTA DO ARTIGO 477 DA CLT
4. 13º SALÁRIO

#### GORJETA (VARIAVEL, mas remunera diretamente — não habitual)

Reflexos (5 — SEM RSR):
1. AVISO PRÉVIO (×2)
2. FÉRIAS + 1/3
3. MULTA DO ARTIGO 477 DA CLT
4. 13º SALÁRIO

#### Verbas rescisórias (SALDO DE SALÁRIO, FÉRIAS + 1/3, AVISO PRÉVIO, 13º SALÁRIO)

Reflexos (apenas MULTA 467 ×2):
1. MULTA DO ARTIGO 467 DA CLT (×2 linhas — provavelmente principal + diferença)

#### MULTA DO ARTIGO 477 DA CLT

Sem reflexos (verba final).

### Implicações para a automação

1. **NÃO criar reflexas manualmente** para verbas adicionadas via Expresso —
   o PJE-Calc já gera automaticamente. Configurar reflexas manualmente
   resulta em duplicidade ou bug HTTP 500.

2. **Verificar se RSR é necessário**: para COMISSÃO/HE/INTERVALO/etc.
   o PJE-Calc gera RSR auto. Se a sentença pede explicitamente RSR,
   confirmar que já não foi gerado antes de criar manual.

3. **MULTA 467 inclui auto** sobre rescisórias. Se a sentença pede
   multa 467, basta marcar a checkbox em FGTS (`multaDoArtigo467`)
   ou confiar nas reflexas auto-geradas das verbas rescisórias.

4. **Por que AVISO PRÉVIO aparece 2× como reflexa**: hipótese — uma
   linha para AVISO PRÉVIO TRABALHADO e outra para AVISO PRÉVIO
   INDENIZADO (naturezas diferentes para fins de incidência).
   A confirmar inspecionando os Parâmetros de cada uma.
