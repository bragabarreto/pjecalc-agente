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
