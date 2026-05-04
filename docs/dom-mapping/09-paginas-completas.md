# DOM Mapping — Páginas Completas (Etapa 1 + Etapa 2)

**Versão**: PJE-Calc 2.15.1  
**Auditado**: 2026-05-04 via Chrome MCP no cálculo 262818, navegação via menu lateral.

Este doc complementa `08-paginas-secundarias.md` com mapeamento empírico das
páginas que estavam pendentes (sessão Seam estabilizada após reabrir o cálculo
e navegar via `li#calculo_*`).

## Padrão de seletores do menu lateral

Todos os links do menu lateral seguem padrão:
```
li#calculo_NOME a   →  navega para a página correspondente
```

IDs confirmados no DOM:
- `li_calculo_dados_calculo`
- `li_calculo_faltas`
- `li_calculo_ferias`
- `li_calculo_historico_salarial`
- `li_calculo_verbas`
- `li_calculo_cartao_de_ponto`
- `li_calculo_salario_familia`
- `li_calculo_seguro_desemprego`
- `li_calculo_fgts`
- `li_calculo_inss`
- `li_calculo_previdencia_privada`
- `li_calculo_pensao_alimenticia`
- `li_calculo_irpf`
- `li_calculo_multas_e_indenizacoes`
- `li_calculo_honorarios`
- `li_calculo_custas_judiciais`
- `li_calculo_correcao_juros_multa`

⚠️ **Para a automação**: usar `document.getElementById('li_calculo_X').querySelector('a').click()`
em vez de simular click via coordinates — é mais robusto.

---

## 1. Contribuição Social — INSS (`inss/inss.jsf`)

**URL**: `/pjecalc/pages/calculo/inss/inss.jsf`

| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Apurar Contribuição Devida | `formulario:apurarInssSeguradoDevido` | checkbox | |
| Cobrar do Reclamante | `formulario:cobrarDoReclamanteDevido` | checkbox | |
| Corrigir Desconto Reclamante | `formulario:corrigirDescontoReclamante` | checkbox | |
| Apurar sobre Salários Pagos | `formulario:apurarSalariosPagos` | checkbox | |
| Alíquota Empregado | `formulario:aliquotaEmpregado` | radio | SEGURADO_EMPREGADO / EMPREGADO_DOMESTICO / FIXA |
| Alíquota Empregador | `formulario:aliquotaEmpregador` | radio | POR_ATIVIDADE_ECONOMICA / POR_PERIODO / FIXA |
| Alíquota Empresa Fixa (%) | `formulario:aliquotaEmpresaFixa` | text | (visível quando empregador=FIXA) |
| Alíquota RAT Fixa (%) | `formulario:aliquotaRatFixa` | text | |
| Alíquota Terceiros Fixa (%) | `formulario:aliquotaTerceirosFixa` | text | |
| Período Inicial Devidos | `formulario:periodoInicialDEVIDOSInputDate` | text | DD/MM/YYYY |
| Período Final Devidos | `formulario:periodoFinalDEVIDOSInputDate` | text | DD/MM/YYYY |
| Período Inicial Pagos | `formulario:periodoInicialPAGOSInputDate` | text | DD/MM/YYYY |
| Período Final Pagos | `formulario:periodoFinalPAGOSInputDate` | text | DD/MM/YYYY |
| Botão Salvar | `formulario:salvar` | button | |
| Botão "Ocorrências" → parametrizar-inss.jsf | `formulario:ocorrencias` | button | |

### 1b. parametrizar-inss.jsf

**URL**: `/pjecalc/pages/calculo/inss/parametrizar-inss.jsf`  
**Acesso**: clicar `formulario:ocorrencias` na página INSS.

| Campo | DOM ID | Tipo |
|---|---|---|
| Data Inicial (lote) | `formulario:dataInicialInputDate` | text |
| Data Final (lote) | `formulario:dataFinalInputDate` | text |
| Salários Pagos (lote) | `formulario:salariosPago` | text |
| **Recuperar Devidos** | `formulario:recuperarDevidos` | button |
| **Copiar Devidos→Pagos** | `formulario:copiarDevidos` | button |
| Selecionar Todos (cabeçalho) | `formulario:selecionarTodos1` | checkbox |
| Linha N — Base Histórico Devido | `formulario:listagemOcorrenciasDevidos:N:baseHistoricoDevido` | text |
| Linha N — Selecionar | `formulario:listagemOcorrenciasDevidos:N:selecionarDevido` | checkbox |
| Botão Regerar | `formulario:regerar` | button |
| Salvar | `formulario:salvar` | button |
| Cancelar | `formulario:cancelar` | button |

---

## 2. Imposto de Renda (`irpf.jsf`)

**URL**: `/pjecalc/pages/calculo/irpf.jsf`

| Campo | DOM ID | Tipo |
|---|---|---|
| Apurar Imposto de Renda | `formulario:apurarImpostoRenda` | checkbox |
| Incidir sobre Juros de Mora | `formulario:incidirSobreJurosDeMora` | checkbox |
| Cobrar do Reclamado | `formulario:cobrarDoReclamado` | checkbox |
| Considerar Tributação Exclusiva | `formulario:considerarTributacaoExclusiva` | checkbox |
| Considerar Tributação em Separado (RRA) | `formulario:considerarTributacaoEmSeparado` | checkbox |
| Regime de Caixa | `formulario:regimeDeCaixa` | checkbox |
| Deduzir Contribuição Social | `formulario:deduzirContribuicaoSocialDevidaPeloReclamante` | checkbox |
| Deduzir Previdência Privada | `formulario:deduzirPrevidenciaPrivada` | checkbox |
| Deduzir Pensão Alimentícia | `formulario:deduzirPensaoAlimenticia` | checkbox |
| Deduzir Honorários | `formulario:deduzirHonorariosDevidosPeloReclamante` | checkbox |
| Aposentado > 65 anos | `formulario:aposentadoMaiorQue65Anos` | checkbox |
| Possui Dependentes | `formulario:possuiDependentes` | checkbox |
| Qtd Dependentes | `formulario:quantidadeDependentes` | text |
| Salvar | `formulario:salvar` | button |

---

## 3. Honorários (`honorarios.jsf`)

**URL**: `/pjecalc/pages/calculo/honorarios.jsf`

### Listagem
| Função | DOM ID |
|---|---|
| Botão Incluir (Novo) | `formulario:incluir` |

### Form Novo
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Tipo de Honorário | `formulario:tpHonorario` | select | ADVOCATICIOS, ASSISTENCIAIS, CONTRATUAIS, PERICIAIS_CONTADOR, PERICIAIS_DOCUMENTOSCOPIO, PERICIAIS_ENGENHEIRO, PERICIAIS_INTERPRETE, PERICIAIS_MEDICO, PERICIAIS_OUTROS, SUCUMBENCIAIS, LEILOEIRO |
| Descrição | `formulario:descricao` | text | |
| Tipo de Devedor | `formulario:tipoDeDevedor` | radio | RECLAMANTE / RECLAMADO |
| Tipo Valor | `formulario:tipoValor` | radio | INFORMADO / CALCULADO |
| Alíquota (%) | `formulario:aliquota` | text | |
| Base para Apuração | `formulario:baseParaApuracao` | select | BRUTO / BRUTO_MENOS_CONTRIBUICAO_SOCIAL / BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA |
| Seleção de Credores | `formulario:selecaoCredores` | select | (Preencher Dados / advogados cadastrados) |
| Nome Credor | `formulario:nomeCredor` | text | |
| Tipo Doc Credor | `formulario:tipoDocumentoFiscalCredor` | radio | CPF / CNPJ / CEI |
| Nº Doc Credor | `formulario:numeroDocumentoFiscalCredor` | text | |
| Apurar IRRF | `formulario:apurarIRRF` | checkbox | |
| Salvar | `formulario:salvar` | button | |

---

## 4. Custas Judiciais (`custas-judiciais.jsf`)

**URL**: `/pjecalc/pages/calculo/custas-judiciais.jsf`

| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Base para Custas Calculadas | `formulario:baseParaCustasCalculadas` | select | BRUTO_DEVIDO_AO_RECLAMANTE / BRUTO_DEVIDO_AO_RECLAMANTE_MAIS_DEBITOS_RECLAMADO |
| Custas Conhecimento Reclamante | `formulario:tipoDeCustasDeConhecimentoDoReclamante` | radio | NAO_SE_APLICA / CALCULADA_2_POR_CENTO / INFORMADA |
| Custas Conhecimento Reclamado | `formulario:tipoDeCustasDeConhecimentoDoReclamado` | radio | NAO_SE_APLICA / CALCULADA_2_POR_CENTO / INFORMADA |
| Custas Liquidação | `formulario:tipoDeCustasDeLiquidacao` | radio | NAO_SE_APLICA / CALCULADA_MEIO_POR_CENTO / INFORMADA |
| Data Vencimento Custas Fixas | `formulario:dataVencimentoCustasFixasInputDate` | text DD/MM/YYYY |
| Qtd Atos Urbanos | `formulario:qtdeAtosUrbanos` | text |
| Qtd Atos Rurais | `formulario:qtdeAtosRurais` | text |
| Qtd Agravos Instrumento | `formulario:qtdeAgravosDeInstrumento` | text |
| Qtd Agravos Petição | `formulario:qtdeAgravosDePeticao` | text |
| Qtd Impugnação Sentença | `formulario:qtdeImpugnacaoSentenca` | text |
| Qtd Embargos Arrematação | `formulario:qtdeEmbargosArrematacao` | text |
| Qtd Embargos Execução | `formulario:qtdeEmbargosExecucao` | text |
| Qtd Embargos Terceiros | `formulario:qtdeEmbargosTerceiros` | text |
| Qtd Recurso Revista | `formulario:qtdeRecursoRevista` | text |
| **Auto** Tipo | `formulario:tipoDeAuto` | select | REMICAO / ADJUDICACAO / ARREMATACAO |
| Data Vencimento Auto | `formulario:dataVencimentoAutoInputDate` | text |
| Valor Avaliação Auto | `formulario:valorAvaliacaoAuto` | text |
| Incluir Auto | `formulario:cmdIncluirAutos` | anchor (+) |
| **Armazenamento** Início | `formulario:dataInicioArmazenamentoInputDate` | text |
| Armazenamento Fim | `formulario:dataTerminoArmazenamentoInputDate` | text |
| Valor Avaliação Armazenamento | `formulario:valorAvaliacaoArmazenamento` | text |
| Incluir Armazenamento | `formulario:cmdIncluirArmazenamento` | anchor (+) |
| **RD** Data Vencimento | `formulario:dataVencimentoRDInputDate` | text |
| Valor RD | `formulario:valorRD` | text |
| Incluir RD | `formulario:cmdIncluirRD` | anchor (+) |
| **RT** Data Vencimento | `formulario:dataVencimentoRTInputDate` | text |
| Valor RT | `formulario:valorRT` | text |
| Incluir RT | `formulario:cmdIncluirRT` | anchor (+) |
| Salvar | `formulario:salvar` | button |

---

## 5. Correção, Juros e Multa (`parametros-atualizacao/parametros-atualizacao.jsf`)

**URL**: `/pjecalc/pages/calculo/parametros-atualizacao/parametros-atualizacao.jsf`

### Índices Trabalhistas e Juros
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Índice Trabalhista | `formulario:indiceTrabalhista` | select | TUACDT, TABELA_DEVEDOR_FAZENDA, TABELA_INDEBITO_TRIBUTARIO, TABELA_UNICA_JT_MENSAL, TABELA_UNICA_JT_DIARIO, TR, IGPM, INPC, IPC, IPCA, IPCAE, IPCAETR, SELIC, SELIC_FAZENDA, SELIC_BACEN, SEM_CORRECAO |
| Combinar Outro Índice | `formulario:combinarOutroIndice` | checkbox | |
| Ignorar Taxa Negativa | `formulario:ignorarTaxaNegativa` | checkbox | |
| Aplicar Juros Pré-judicial | `formulario:aplicarJurosFasePreJudicial` | checkbox | |
| Juros | `formulario:juros` | select | JUROS_PADRAO, JUROS_POUPANCA, FAZENDA_PUBLICA, JUROS_MEIO_PORCENTO, JUROS_UM_PORCENTO, JUROS_ZERO_TRINTA_TRES, SELIC, SELIC_FAZENDA, SELIC_BACEN, TRD_SIMPLES, TRD_COMPOSTOS, TAXA_LEGAL, SEM_JUROS |
| Combinar Outro Juros | `formulario:combinarOutroJuros` | checkbox | |
| Outro Juros | `formulario:outroJuros` | select | (mesmo set) |
| Aplicar a partir de | `formulario:apartirDeOutroJurosInputDate` | text |
| Adicionar Outro Juros | `formulario:addOutroJuros` | anchor |
| Excluir Dep N | `formulario:j_id150:N:excluirDep` | anchor |
| Base de Juros das Verbas | `formulario:baseDeJurosDasVerbas` | select | VERBAS / VERBA_INSS / VERBA_INSS_PP |

### FGTS
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Índice Correção FGTS | `formulario:indiceDeCorrecaoDoFGTS` | radio | UTILIZAR_INDICE_TRABALHISTA / UTILIZAR_INDICE_JAM / UTILIZAR_INDICE_JAM_E_TRABALHISTA |

### Previdência Privada
| Campo | DOM ID | Tipo |
|---|---|---|
| Aplicar Juros | `formulario:jurosDePrevidenciaPrivada` | checkbox |
| Índice Correção | `formulario:indiceDeCorrecaoDePrevidenciaPrivada` | radio (TRAB / OUTRO) |
| Outro Índice | `formulario:outroIndiceDeCorrecaoDePrevidenciaPrivada` | select |

### Custas
| Campo | DOM ID | Tipo |
|---|---|---|
| Correção das Custas | `formulario:correcaoDasCustas` | checkbox |
| Juros de Custas | `formulario:jurosDeCustas` | checkbox |
| Índice Correção Custas | `formulario:indiceDeCorrecaoDasCustas` | radio (TRAB / OUTRO) |
| Outro Índice Custas | `formulario:outroIndiceDeCorrecaoDasCustas` | select |

### Lei 11.941
| Campo | DOM ID | Tipo |
|---|---|---|
| Correção Lei 11941 | `formulario:correcaoLei11941` | checkbox |
| Aplicar até (data) | `formulario:aplicarAteLei11941InputDate` | text |
| Multa Lei 11941 | `formulario:correcaoLei11941Multa` | checkbox |
| Aplicar Multa até | `formulario:aplicarAteLei11941MultaInputDate` | text |

### INSS — Salários Devidos / Pagos
| Campo | DOM ID | Tipo |
|---|---|---|
| Correção Trabalhista Devidos | `formulario:correcaoTrabalhistaDosSalariosDevidosDoINSS` | checkbox |
| Juros Trabalhistas Devidos | `formulario:jurosTrabalhistasDosSalariosDevidosDoINSS` | checkbox |
| Correção Previdenciária Devidos | `formulario:correcaoPrevidenciariaDosSalariosDevidosDoINSS` | checkbox |
| Juros Previdenciários Devidos | `formulario:jurosPrevidenciariosDosSalariosDevidosDoINSS` | checkbox |
| Aplicar Multa Devidos | `formulario:aplicarMultaDosSalariosDevidosDoINSS` | checkbox |
| Tipo Multa Devidos | `formulario:tipoDeMultaDosSalariosDevidosDoINSS` | radio (URBANA / RURAL) |
| Pagamento Multa Devidos | `formulario:pagamentoDaMultaDosSalariosDevidosDoINSS` | radio (INTEGRAL / REDUZIDO) |
| (mesmos para Pagos) | `*DosSalariosPagosDoINSS` | | |
| Forma Aplicação Salário Pago | `formulario:radioFormaAplicacaoSalarioPago` | radio (MES_A_MES / A_PARTIR_DE) |
| Salvar | `formulario:salvar` | button |

---

## 6. Liquidação (`liquidacao.jsf`)

**URL**: `/pjecalc/pages/calculo/liquidacao.jsf`  
**Acesso**: menu lateral > Operações > Liquidar

| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Data de Liquidação | `formulario:dataDeLiquidacaoInputDate` | text | DD/MM/YYYY |
| Acumular Índices | `formulario:indicesAcumulados` | radio | MES_SUBSEQUENTE_AO_VENCIMENTO / MES_DO_VENCIMENTO / MES_SUBSEQUENTE_E_MES_DO_VENCIMENTO |
| **Botão Liquidar** | `formulario:liquidar` | button | |
| Lista Pendências (Erros) | `formulario:j_id115:0` | anchor | (link p/ pagina de erros) |
| Lista Pendências (Alertas) | `formulario:j_id115:1` | anchor | |
| Total de Erros | `formulario:totalErros` | text (readonly) | |
| Total de Alertas | `formulario:totalAlertas` | text (readonly) | |

⚠️ **Liquidar só funciona quando não há ERROS** (alertas não impedem).
A página exibe lista de pendências em uma tabela visual; cada item tem
texto descrevendo o problema (capturado anteriormente em fluxo de
auto-correção da automação).

---

## 7. Histórico Salarial — modo CALCULADO

**URL**: `/pjecalc/pages/calculo/historico-salarial.jsf` com `formulario:tipoValor:1` (CALCULADO) selecionado.

### Diferenças vs modo INFORMADO

| Modo | Campos extras |
|---|---|
| INFORMADO (default) | `formulario:valorParaBaseDeCalculo` (text — valor único) |
| **CALCULADO** | `formulario:quantidade` (text), `formulario:baseDeReferencia` (select), `formulario:cmdGerarOcorrencias` (anchor) |

### Como cadastrar histórico CALCULADO
1. Selecionar nome do histórico (`formulario:nome`)
2. Marcar `formulario:tipoValor:1` (CALCULADO)
3. Preencher `formulario:quantidade` (% ou multiplicador)
4. Selecionar `formulario:baseDeReferencia` (outra verba/histórico já cadastrado)
5. Click `formulario:cmdGerarOcorrencias` para gerar valores mensais
6. Salvar

⚠️ **Diferença importante**: o modo CALCULADO não usa "+" para adicionar
múltiplas bases — é apenas UMA base de referência por histórico. Para
histórico composto (ex: 100% Salário + 30% Gratificação), criar histórico
separado para cada componente.

---

## ETAPA 2 — Páginas de Média Prioridade

### 8. Salário-Família (`salario-familia.jsf`)

| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Apurar Salário-Família | `formulario:apurarSalarioFamilia` | checkbox | |
| Compor Principal | `formulario:comporPrincipal` | radio | SIM / NAO |
| Data Inicial | `formulario:dataInicialInputDate` | text | DD/MM/YYYY |
| Data Final | `formulario:dataFinalInputDate` | text | DD/MM/YYYY |
| Qtd Filhos < 14 anos | `formulario:quantFilhosMenores14Anos` | text | |
| Variação — Data Inicial | `formulario:variacaoDataInicialInputDate` | text | |
| Variação — Qtd Filhos | `formulario:variacaoQuantFilhosMenores14Anos` | text | |
| Adicionar Variação | `formulario:cmdAdicionarVariacao` | anchor (+) | |
| Tipo Salário Pago | `formulario:tipoSalarioPago` | radio | NENHUM / MAIOR_REMUNERACAO / HISTORICO_SALARIAL |
| Histórico Salarial | `formulario:historicoSalarial` | select | (selecionar nome do histórico) |
| Adicionar Histórico | `formulario:cmdAdicionarHistoricoSalarial` | anchor | |
| Verba (compor base) | `formulario:verba` | select | (verba do cálculo) |
| Integralizar | `formulario:integralizar` | select | SIM/NAO |
| Adicionar Salário Devido | `formulario:cmdAdicionarSalarioDevido` | anchor | |
| Salvar | `formulario:salvar` | button | |

### 9. Seguro-Desemprego (`seguro-desemprego.jsf`)

| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Apurar Seguro-Desemprego | `formulario:apurarSeguroDesemprego` | checkbox | |
| Apurar Empregado Doméstico | `formulario:apurarEmpregadoDomestico` | checkbox | |
| Solicitação | `formulario:solicitacao` | select | |
| Valor | `formulario:valor` | radio | INFORMADO / CALCULADO |
| Compor Principal | `formulario:comporPrincipal` | radio | SIM / NAO |
| Número de Parcelas | `formulario:numeroDeParcelas` | text | |
| Tipo Salário Pago | `formulario:tipoSalarioPago` | radio | NENHUM / MAIOR_REMUNERACAO / HISTORICO_SALARIAL |
| Histórico Salarial | `formulario:historicoSalarial` | select | |
| Adicionar Histórico | `formulario:cmdAdicionarHistoricoSalarial` | anchor | |
| Verba | `formulario:verba` | select | |
| Integralizar | `formulario:integralizar` | select | |
| Adicionar Salário Devido | `formulario:cmdAdicionarSalarioDevido` | anchor | |
| Salvar | `formulario:salvar` | button | |

### 10. Previdência Privada (`previdencia-privada.jsf`)

| Campo | DOM ID | Tipo |
|---|---|---|
| Apurar Previdência Privada | `formulario:apurarPrevidenciaPrivada` | checkbox |
| Data Início Período | `formulario:dataInicioPeriodoInputDate` | text DD/MM/YYYY |
| Data Término Período | `formulario:dataTerminoPeriodoInputDate` | text DD/MM/YYYY |
| Alíquota (%) | `formulario:aliquota` | text |
| Incluir Alíquota | `formulario:cmdIncluirAliquota` | anchor (+) |
| Salvar | `formulario:salvar` | button |

### 11. Pensão Alimentícia (`pensao-alimenticia.jsf`)

| Campo | DOM ID | Tipo |
|---|---|---|
| Apurar Pensão Alimentícia | `formulario:apurarPensaoAlimenticia` | checkbox |
| Alíquota (%) | `formulario:aliquota` | text |
| Incidir sobre Juros | `formulario:incidirSobreJuros` | checkbox |
| Salvar | `formulario:salvar` | button |

### 12. Multas e Indenizações (`multas-indenizacoes.jsf`)

#### Listagem
| Função | DOM ID |
|---|---|
| Botão Incluir | `formulario:incluir` |

#### Form Novo
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Descrição | `formulario:descricao` | text | |
| Credor / Devedor | `formulario:credorDevedor` | select | RECLAMANTE_RECLAMADO / RECLAMADO_RECLAMANTE / TERCEIRO_RECLAMANTE / TERCEIRO_RECLAMADO |
| Valor | `formulario:valor` | radio | INFORMADO / CALCULADO |
| Tipo Base Multa | `formulario:tipoBaseMulta` | select | PRINCIPAL / PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL / PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA / VALOR_CAUSA |
| Alíquota (%) | `formulario:aliquota` | text | |
| Salvar | `formulario:salvar` | button | |
| Cancelar | `formulario:cancelar` | button | |

⚠️ **Diferença vs Multa 477 (verba)**: a página "Multas e Indenizações"
trata multas convencionais avulsas (ex: multa contratual de cláusula
penal). A multa do art. 477 da CLT é lançada via Verbas Expresso (rol
de 54 verbas no doc 02), não aqui.
