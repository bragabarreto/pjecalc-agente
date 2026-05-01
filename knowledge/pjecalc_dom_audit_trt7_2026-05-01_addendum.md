# Addendum DOM Audit — PJE-Calc Institucional 2.15.1 (TRT7)

**Sessão**: 2026-05-01
**Calc base**: 262818 / processo 0000369-57.2026.5.07.0003
**Método**: Chrome MCP via tab Playwright/extensão
**Inclui**: novidades não cobertas no master `pjecalc_dom_audit_trt7_2026-05-01.md`.

## Mapa de IDs do menu lateral

Estrutura `formulario:j_id38:{grupo}:j_id41:{idx}:j_id46`:

| Grupo | idx | Item |
|-------|-----|------|
| 0 | 0 | Tela Inicial |
| 0 | 1 | Novo |
| 0 | 2 | Novo Cálculo Externo |
| 0 | 3 | Buscar |
| 0 | 4 | Importar |
| 0 | 5 | Relatório Consolidado |
| 0 | 6 | Dados do Cálculo |
| 0 | 7 | Faltas |
| 0 | 8 | Férias |
| 0 | 9 | Histórico Salarial |
| 0 | 10 | Verbas |
| 0 | 11 | Cartão de Ponto |
| 0 | 12 | Salário-família |
| 0 | 13 | Seguro-desemprego |
| 0 | 14 | FGTS |
| 0 | 15 | Contribuição Social |
| 0 | 16 | Previdência Privada |
| 0 | 17 | Pensão Alimentícia |
| 0 | 18 | Imposto de Renda |
| 0 | 19 | Multas e Indenizações |
| 0 | 20 | Honorários |
| 0 | 21 | Custas Judiciais |
| 0 | 22 | Correção, Juros e Multa |
| 2 | 0 | Liquidar |
| 2 | 1 | Imprimir |
| 2 | 2 | Fechar |
| 2 | 3 | Excluir |
| 2 | 4 | Exportar |
| 2 | 5 | Enviar para o PJe |
| 3 | 0 | Dados do Pagamento (Atualização) |
| 3 | 1 | Pensão Alimentícia (Atualização) |
| 3 | 2 | Multas e Indenizações (Atualização) |
| 3 | 3 | Honorários (Atualização) |
| 3 | 4 | Custas Judiciais (Atualização) |
| 3 | 5 | Liquidar Atualização |
| 3 | 6 | Imprimir Atualização |
| 3 | 7 | Enviar para o PJe (Atualização) |
| 4 | 0 | Salário Mínimo (Tabelas) |
| 4 | 1 | Pisos Salariais |
| 4 | 2 | Salário-família |
| 4 | 3 | Seguro-desemprego |
| 4 | 4 | Vale-transporte |
| 4 | 5 | Feriados e Pontos Facultativos |
| 4 | 6 | Verbas (catálogo) |
| 4 | 7 | Contribuição Social (alíquotas) |
| 4 | 8 | Imposto de Renda (alíquotas) |

## Novidades — defaults e enums confirmados

### FGTS (`fgts.jsf`)

Radios:
- `tipoDeVerba`: PAGAR* / DEPOSITAR
- `comporPrincipal`: SIM* / NAO
- `tipoDoValorDaMulta`: CALCULADA* / INFORMADA
- `multaDoFgts`: VINTE_POR_CENTO / **QUARENTA_POR_CENTO*** (40% rescisão sem justa causa)
- `aliquota`: DOIS_POR_CENTO / **OITO_POR_CENTO*** (8% padrão)

Checkboxes:
- `multa` (true*): apurar multa rescisória
- `multa10` (false*): Multa LC 110 (10%)
- `multaDoArtigo467` (false*): multa 467 — pagar 50% incontroversa
- `excluirAvisoDaMulta` (true*): exclui aviso prévio da base da multa
- `deduzirDoFGTS` (false*): deduzir saldo conta vinculada
- `incidenciaPensaoAlimenticia` (false*)

Selects:
- `incidenciaDoFgts`: SOBRE_O_TOTAL_DEVIDO* / outras

Saldos depositados (linha de adição):
- `competenciaInputDate`, `valor`, link `adicionarSaldo`

Período: `periodoInicial` / `periodoFinal` (auto-preenchidos com contrato).

### INSS / Contribuição Social (`inss/inss.jsf`)

Checkboxes:
- `apurarInssSeguradoDevido` (true*)
- `apurarSalariosPagos` (false*)
- `cobrarDoReclamanteDevido` (true*)
- `corrigirDescontoReclamante` (false*)

Radios:
- `aliquotaEmpregado`: SEGURADO_EMPREGADO* / EMPREGADO_DOMESTICO / FIXA
- `aliquotaEmpregador`: POR_ATIVIDADE_ECONOMICA / POR_PERIODO / **FIXA***

### Imposto de Renda (`irpf.jsf`)

Checkboxes:
- `apurarImpostoRenda` (true*)
- `regimeDeCaixa` (false*)
- `aposentadoMaiorQue65Anos` (false*)
- `cobrarDoReclamado` (false*)
- `incidirSobreJurosDeMora` (false*)
- `considerarTributacaoEmSeparado` (false*) / `considerarTributacaoExclusiva` (false*)
- `deduzirContribuicaoSocialDevidaPeloReclamante` (true*)
- `deduzirHonorariosDevidosPeloReclamante` (true*)
- `deduzirPensaoAlimenticia` (true*)
- `deduzirPrevidenciaPrivada` (true*)
- `possuiDependentes` (false*) / `quantidadeDependentes` (texto, "0")

### Correção, Juros e Multa (`parametros-atualizacao/parametros-atualizacao.jsf`)

Selects (catálogo completo):
- `indiceTrabalhista` (16 opções):
  TUACDT | TABELA_DEVEDOR_FAZENDA | TABELA_INDEBITO_TRIBUTARIO |
  TABELA_UNICA_JT_MENSAL | TABELA_UNICA_JT_DIARIO | TR | IGPM | INPC |
  IPC | IPCA* | IPCAE | IPCAETR | SELIC | SELIC_FAZENDA | SELIC_BACEN |
  SEM_CORRECAO
- `juros` (13 opções):
  JUROS_PADRAO | JUROS_POUPANCA | FAZENDA_PUBLICA |
  JUROS_MEIO_PORCENTO | JUROS_UM_PORCENTO | JUROS_ZERO_TRINTA_TRES |
  SELIC | SELIC_FAZENDA | SELIC_BACEN | TRD_SIMPLES* | TRD_COMPOSTOS |
  TAXA_LEGAL | SEM_JUROS
- `outroJuros` (14 opções, mesmo catálogo + NoSelection)
- `outroIndiceDeCorrecaoDasCustas` (17 opções)
- `outroIndiceDeCorrecaoDePrevidenciaPrivada` (17 opções)
- `baseDeJurosDasVerbas` (3 opções):
  VERBAS* | VERBA_INSS | VERBA_INSS_PP

Radios:
- `indiceDeCorrecaoDoFGTS`:
  UTILIZAR_INDICE_TRABALHISTA* / UTILIZAR_INDICE_JAM /
  UTILIZAR_INDICE_JAM_E_TRABALHISTA
- `indiceDeCorrecaoDePrevidenciaPrivada`:
  UTILIZAR_INDICE_TRABALHISTA* / UTILIZAR_OUTRO_INDICE
- `indiceDeCorrecaoDasCustas`:
  UTILIZAR_INDICE_TRABALHISTA* / UTILIZAR_OUTRO_INDICE
- `tipoDeMultaDosSalariosDevidosDoINSS`: URBANA* / RURAL
- `pagamentoDaMultaDosSalariosDevidosDoINSS`: INTEGRAL* / REDUZIDO
- `radioFormaAplicacaoSalarioPago`: MES_A_MES* / A_PARTIR_DE
- `tipoDeMultaDosSalariosPagosDoINSS`: URBANA* / RURAL
- `pagamentoDaMultaDosSalariosPagosDoINSS`: INTEGRAL* / REDUZIDO

Checkboxes ativas por padrão:
- `aplicarJurosFasePreJudicial` (true*)
- `aplicarMultaDosSalariosPagosDoINSS` (true*)
- `combinarOutroJuros` (true*)
- `correcaoDasCustas` (true*)
- `correcaoLei11941` (true*) / `correcaoLei11941Multa` (true*)
- `correcaoPrevidenciariaDosSalariosPagosDoINSS` (true*)
- `correcaoTrabalhistaDosSalariosDevidosDoINSS` (true*)
- `jurosPrevidenciariosDosSalariosPagosDoINSS` (true*)

Texto:
- `aplicarAteLei11941InputDate`: "05/03/2009" (data lei)
- `apartirDeOutroJurosInputDate`: vazio

### Honorários (`honorarios.jsf`)

Listagem com botões `formulario:incluir` (Novo) e por linha:
- `j_id244` (Visualizar)
- `j_id245` (Alterar)
- `j_id246` (Excluir)

Form de edição:
- `tpHonorario` (11 opções):
  ADVOCATICIOS | ASSISTENCIAIS | CONTRATUAIS |
  PERICIAIS_CONTADOR | PERICIAIS_DOCUMENTOSCOPIO | PERICIAIS_ENGENHEIRO |
  PERICIAIS_INTERPRETE | PERICIAIS_MEDICO | PERICIAIS_OUTROS |
  SUCUMBENCIAIS* | LEILOEIRO
- `baseParaApuracao` (4 opções):
  BRUTO* | BRUTO_MENOS_CONTRIBUICAO_SOCIAL |
  BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA
- `tipoDeDevedor` (radio): RECLAMANTE / RECLAMADO*
- `tipoValor` (radio): INFORMADO / CALCULADO*
- `tipoDocumentoFiscalCredor` (radio): CPF* / CNPJ / CEI
- `aliquota` (texto): default 7,50
- `descricao`, `nomeCredor`, `numeroDocumentoFiscalCredor`
- `apurarIRRF` (checkbox)

### Custas Judiciais (`custas-judiciais.jsf`)

Radios:
- `tipoDeCustasDeConhecimentoDoReclamante`:
  NAO_SE_APLICA* / CALCULADA_2_POR_CENTO / INFORMADA
- `tipoDeCustasDeConhecimentoDoReclamado`:
  NAO_SE_APLICA / CALCULADA_2_POR_CENTO* / INFORMADA
- `tipoDeCustasDeLiquidacao`:
  NAO_SE_APLICA* / CALCULADA_MEIO_POR_CENTO / INFORMADA

Selects:
- `baseParaCustasCalculadas`: BRUTO_DEVIDO_AO_RECLAMANTE* /
  BRUTO_DEVIDO_AO_RECLAMANTE_MAIS_OUTROS_DEBITOS
- `tipoDeAuto` (4 opções, NoSelection default)

Texto (todos vazios por padrão):
- `qtdeAgravosDeInstrumento`, `qtdeAgravosDePeticao`
- `qtdeAtosRurais`, `qtdeAtosUrbanos`
- `qtdeEmbargosArrematacao`, `qtdeEmbargosExecucao`, `qtdeEmbargosTerceiros`
- `qtdeImpugnacaoSentenca`, `qtdeRecursoRevista`
- `valorAvaliacaoArmazenamento`, `valorAvaliacaoAuto`
- `valorRD`, `valorRT`
- `dataInicio/TerminoArmazenamentoInputDate`
- `dataVencimentoAuto/CustasFixas/RD/RT InputDate`

### Multas e Indenizações (`multas-indenizacoes.jsf`)

Listagem + botão `formulario:incluir`. Form:
- `credorDevedor` (4 opções):
  RECLAMANTE_RECLAMADO | RECLAMADO_RECLAMANTE |
  TERCEIRO_RECLAMANTE | TERCEIRO_RECLAMADO
- `tipoBaseMulta` (4 opções):
  PRINCIPAL | PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL |
  PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA |
  VALOR_CAUSA
- `valor` (radio): INFORMADO / CALCULADO*
- `aliquota`, `descricao` (texto)

### Histórico Salarial (`historico-salarial.jsf`)

Listagem 3 históricos default:
- ÚLTIMA REMUNERAÇÃO
- SALÁRIO BASE
- ADICIONAL DE INSALUBRIDADE PAGO

Botões: `formulario:incluir` (Novo), `formulario:visualizarOcorrencias` (Grade).

Grade de Ocorrências (`historico-salarial.jsf?conversationId=N` após
visualizarOcorrencias) = matriz mês × histórico:
- Headers: MÊS/ANO | ÚLTIMA REMUNERAÇÃO | SALÁRIO BASE | ADICIONAL DE INSALUBRIDADE PAGO
- IDs por linha: `formulario:listagem:{N}:linha1` (ÚLTIMA REM), `linha2`
  (SAL BASE), `linha3` (AD INSALUB PAGO)
- N = índice do mês (0 = primeiro mês)

### Férias (`ferias.jsf`)

Select:
- `situacao` (4 opções por período aquisitivo):
  GOZADAS | GOZADAS_PARCIALMENTE | INDENIZADAS | PERDIDAS

Por linha (período aquisitivo, índice 0+):
- `{N}:dataInicialDoPeriodoDeGozo1/2/3` + `dataFinalDoPeriodoDeGozo1/2/3`
- `{N}:prazo` (default "30")
- `{N}:quantidadeDiasAbono` (default "10")

Form geral:
- `formulario:inicioFeriasColetivasInputDate`
- `formulario:prazoFeriasProporcionais`
- `abono`, `dobraDoPeriodoDeGozo1/2/3`, `dobraGeral` (checkboxes)

### Faltas (`falta.jsf`)

Form de inclusão:
- `dataInicioPeriodoFaltaInputDate`, `dataTerminoPeriodoFaltaInputDate`
- `faltaJustificada` (checkbox, default true)
- `reiniciaFerias` (checkbox, default true) — reinicia período aquisitivo

Importação CSV:
- `arquivo:file` (input file)
- `formulario:confirmarImportacao` (botão)
- ATENÇÃO: importação substitui todas as faltas existentes.

### Pensão Alimentícia (`pensao-alimenticia.jsf`)

Mínima:
- `apurarPensaoAlimenticia` (checkbox, false*)
- `aliquota` (texto, vazio)
- `incidirSobreJuros` (checkbox, false*)

### Salário-Família (`salario-familia.jsf`)

- `apurarSalarioFamilia` (checkbox, false*)
- `comporPrincipal` (radio): SIM* / NAO
- `tipoSalarioPago` (radio): NENHUM / MAIOR_REMUNERACAO / HISTORICO_SALARIAL*
- `dataInicialInputDate` / `dataFinalInputDate` (competências)
- `quantFilhosMenores14Anos`
- Variação: `variacaoDataInicialInputDate` + `variacaoQuantFilhosMenores14Anos`

### Seguro-Desemprego (`seguro-desemprego.jsf`)

- `apurarSeguroDesemprego` (false*) / `apurarEmpregadoDomestico` (false*)
- `tipoSolicitacao` (radio): PRIMEIRA / SEGUNDA / DEMAIS
- `valor` (radio): INFORMADO / CALCULADO*
- `comporPrincipal` (radio): SIM* / NAO
- `tipoSalarioPago` (radio): NENHUM / MAIOR_REMUNERACAO / HISTORICO_SALARIAL*
- `numeroDeParcelas` (texto, "0")
- Histórico * (select): mesmas 3 opções de Histórico Salarial

### Previdência Privada (`previdencia-privada.jsf`)

- `apurarPrevidenciaPrivada` (false*)
- `aliquota` (texto)
- `dataInicioPeriodoInputDate` / `dataTerminoPeriodoInputDate`
  (auto: competência inicial/final do contrato)

### Dados do Pagamento — Atualização (`pagamento/pagamento.jsf`)

Form rico (35+ checkboxes) para registrar pagamentos parciais. Campos
agrupados em 3 categorias:
- **Sobre Principal**: apurarFgts, apurarPrincipal, apurarInssDezPorcento,
  apurarInssMeioPorcento, etc. + valores correspondentes
- **Débitos do Reclamante**: apurar*DebitosReclamante (custas, honorários, multas)
- **Outros Débitos do Reclamado**: apurar*OutrosDebitos (custas, honorários, multas)

Selects:
- `tipoHonorariosDebitosReclamante` / `tipoHonorariosOutrosDebitos`
  (apontam para honorários cadastrados)
- `tipoMultaDebitosReclamante` / `tipoMultaOutrosDebitos`
  (apontam para multas cadastradas)

Textos:
- `valorPagamento`, `dataPagamentoInputDate`, `identificacaoC`
- `valorCreditoReclamante` / `valorDebitosReclamante` / `valorOutrosDebitosReclamado`

Radios:
- `pagarPrecatorio` (false*) / `priorizarJuros` (false*) / `recolherDebitos` (false*)

### Múltiplos Históricos Salariais — confirmado e suportado

Validação Chrome MCP no calc 262818 (2026-05-01):

**O PJE-Calc permite criar históricos salariais customizados ALÉM dos 3 default**
(ÚLTIMA REMUNERAÇÃO, SALÁRIO BASE, ADICIONAL DE INSALUBRIDADE PAGO).

Fluxo confirmado:
1. `historico-salarial.jsf` → botão `formulario:incluir` (Novo)
2. Form com `formulario:nome` (texto livre), `tipoVariacaoDaParcela` (FIXA/VARIAVEL),
   `tipoValor` (INFORMADO/CALCULADO), `competenciaInicialInputDate`,
   `competenciaFinalInputDate`, `valorParaBaseDeCalculo`
3. **OBRIGATÓRIO** clicar `formulario:cmdGerarOcorrencias` ANTES de salvar.
   Sem isso, o save falha com: "Erro. Deve haver pelo menos um registro de Ocorrências."
4. Click `formulario:salvar`

Após criar histórico custom (ex: "GRATIFICACAO HABITUAL"), ele aparece no select
`baseHistoricos` da verba (Parâmetros), em ordem alfabética junto aos defaults:

```
opts: [
  '0=ADICIONAL DE INSALUBRIDADE PAGO',
  '1=GRATIFICACAO HABITUAL',  ← custom!
  '2=SALÁRIO BASE',
  '3=ÚLTIMA REMUNERAÇÃO'
]
```

**ATENÇÃO**: os `value` do select são índices DINÂMICOS — mudam quando se adiciona/
remove históricos. Por isso o matching da automação é feito SEMPRE por TEXTO
(case + acento-insensitive), nunca por value posicional.

**Cobertura no agente**:
- ✅ Prévia: `historico_salarial[]` é lista editável (add/remove/edit) com nome livre.
- ✅ Extração: prompt orienta LLM a emitir múltiplas entradas quando salário variar
  ou houver natureza salarial paralela.
- ✅ Automation: `fase_historico_salarial` itera entradas, deleta default ÚLTIMA REM,
  cria cada custom com Nome+Datas+Valor+Gerar Ocorrências+Salvar.
- ✅ Vinculação base→histórico: `bases_calculo[].historico_subtipo` aceita os 3 enums
  default OU nome custom em UPPERCASE; `_adicionar_base_calculo_completa` matcha
  por texto contendo (case-insensitive sem acentos).
- ✅ Prévia bases: select `historico_subtipo` é DINÂMICO — lista os 3 default +
  todos os nomes únicos de `dados.historico_salarial[]` em optgroup "Customizados".

### Pisos Salariais — limitação conhecida

**A tabela `Pisos Salariais` (Tabelas &gt; Pisos Salariais — categoria) é
gerenciada centralmente no PJE-Calc**, não por usuário comum durante a
liquidação. URL: `/pages/salario-categoria/salario-categoria.jsf`. A
busca por categoria + estado retorna apenas pisos pré-cadastrados pela
administração do TRT (ex: "AUXÍLIO ALIMENTAÇÃO CAIXA ECONÔMICA FEDERAL CE").

**Implicações para a automação**:

- Quando uma `bases_calculo` da verba usa `tipo_base = SALARIO_DA_CATEGORIA`,
  o PJE-Calc consulta a tabela auxiliar pela categoria vinculada aos
  Dados do Cálculo (cabeçalho do processo).
- Se o piso da categoria não estiver na tabela para a competência, a
  Liquidação falha com mensagem específica.
- A automação NÃO cadastra pisos automaticamente (tabela admin-only).
- A Prévia exibe um warning amarelo abaixo da tabela de bases quando
  `SALARIO_DA_CATEGORIA` é selecionado, alertando o usuário a confirmar
  cadastro prévio do piso.

**Workaround**: usar `tipo_base = HISTORICO_SALARIAL` + valor do piso
no histórico salarial da verba quando a sentença referenciar piso
normativo de categoria não cadastrada.

### Tabelas (sub-páginas em `/pages/{tabela}/{tabela}.jsf`)

| Tabela | URL | Conteúdo |
|--------|-----|----------|
| Salário Mínimo | `/salariominimo/salario-minimo.jsf` | Histórico mensal SM |
| Pisos Salariais | `/salario-categoria/salario-categoria.jsf` | Tabela de pisos |
| Salário-família | `/salario-familia-tabela/salario-familia-tabela.jsf` | Faixas SF |
| Seguro-desemprego | `/seguro-desemprego-tabela/seguro-desemprego-tabela.jsf` | Faixas SD |
| Vale-transporte | `/vale-transporte/vale-transporte.jsf` | Tabela VT |
| Feriados e Pontos | `/feriado/feriado.jsf` | Buscar |
| Verbas (catálogo) | `/verba/verba.jsf` | Catálogo geral, NÃO confundir com `verba/verba-calculo.jsf` (verbas do cálculo) |
| Contribuição Social | `/contribuicao-social-tabela/...` | Alíquotas |
| Imposto de Renda | `/imposto-renda-tabela/...` | Alíquotas/faixas |

## Estado da automação após este mapeamento

Cobertura confirmada por inspeção:
- ✅ Verbas (Expresso, Manual, Parâmetros, Ocorrências)
- ✅ FGTS (multa, depósitos, multa 467)
- ✅ INSS / Contribuição Social
- ✅ IRPF
- ✅ Correção/Juros (16 índices, 13 juros)
- ✅ Honorários (11 tipos)
- ✅ Custas Judiciais
- ✅ Multas e Indenizações
- ✅ Histórico Salarial (grade matriz)
- ✅ Férias (situações)
- ✅ Faltas (inclusão + import CSV)
- ✅ Pensão Alimentícia
- ✅ Salário-família, Seguro-desemprego, Previdência Privada
- ✅ Dados do Pagamento (Atualização)
- ✅ 9 Tabelas auxiliares

Cobertura ainda a inspecionar (já documentada parcialmente em master):
- Cartão de Ponto (cobertura via `pjecalc_dom_audit_trt7_2026-05-01.md`)
- Atualização > Liquidar/Imprimir (similares a Liquidar/Imprimir do principal)
- Operações > Exportar / Enviar para o PJe / Imprimir
