# Auditoria DOM PJE-Calc Institucional 2.15.1 (TRT7) — 2026-05-01

Varredura realizada via Claude in Chrome MCP em https://pje.trt7.jus.br/pjecalc.
Cálculos usados: 262818 (0000369-57.2026.5.07.0003) e 262928 (0000948-78.2021.5.07.0003).

## Mapa de Menu Lateral (`li[id^='li_']`)

```
li_calculo_dados_do_calculo       → calculo.jsf
li_calculo_faltas                 → falta.jsf
li_calculo_ferias                 → ferias.jsf
li_calculo_historico_salarial     → historico-salarial.jsf
li_calculo_verbas                 → verba/verba-calculo.jsf
li_calculo_cartao_ponto           → ../cartaodeponto/apuracao-cartaodeponto.jsf
li_calculo_salario_familia        → salario-familia.jsf
li_calculo_seguro_desemprego      → seguro-desemprego.jsf
li_calculo_fgts                   → fgts.jsf
li_calculo_inss                   → inss/inss.jsf
li_calculo_previdencia_privada    → previdencia-privada.jsf
li_calculo_pensao_alimenticia     → pensao-alimenticia.jsf
li_calculo_irpf                   → irpf.jsf
li_calculo_multas_e_indenizacoes  → multas-indenizacoes.jsf
li_calculo_honorarios             → honorarios.jsf
li_calculo_custas_judiciais       → custas-judiciais.jsf  ⚠️ NÃO 'custas/custas.jsf'
li_calculo_correcao_juros_multa   → parametros-atualizacao/parametros-atualizacao.jsf
                                    ⚠️ NÃO 'correcao_juros_e_multa' (sem '_e_')
li_operacoes_liquidar             → liquidacao.jsf
li_calculo_relatorios             → imprimir   ⚠️ NÃO 'calculo_imprimir'
li_operacoes_fechar               → fechar
li_operacoes_excluir              → excluir
li_operacoes_exportar             → exportacao.jsf
li_operacoes_validar              → "Enviar para o PJe"
```

## Dados do Cálculo (`calculo.jsf`)

### Aba "Dados do Cálculo":
- `formulario:numero`, `digito`, `ano`, `justica`, `regiao`, `vara` (textos)
- `formulario:processoInformadoManualmente:0/1` (radio: true/false)
- `formulario:autuadoEm`, `valorDaCausa`
- `formulario:reclamanteNome`, `reclamadoNome`
- `formulario:documentoFiscalReclamante:0/1/2` — CPF/CNPJ/CEI
- `formulario:tipoDocumentoFiscalReclamado:0/1/2` — CPF/CNPJ/CEI
- `formulario:reclamanteNumeroDocumentoFiscal`, `reclamadoNumeroDocumentoFiscal`

### Aba "Parâmetros do Cálculo":
- `formulario:estado` (select 5=CE), `municipio` (88=FORTALEZA)
- Datas: `dataAdmissaoInputDate`, `dataDemissaoInputDate`, `dataAjuizamentoInputDate`,
  `dataInicioCalculoInputDate`, `dataTerminoCalculoInputDate`
- Checkboxes: `prescricaoQuinquenal`, `prescricaoFgts`, `projetaAvisoIndenizado`,
  `limitarAvos`, `zeraValorNegativo`, `consideraFeriadoEstadual`,
  `consideraFeriadoMunicipal`, `sabadoDiaUtil`
- Selects: `tipoDaBaseTabelada` (INTEGRAL...), `apuracaoPrazoDoAvisoPrevio`
  (NAO_APURAR, APURACAO_CALCULADA, APURACAO_INFORMADA), `pontoFacultativo`
- Textos: `valorMaiorRemuneracao`, `valorUltimaRemuneracao`,
  `valorCargaHorariaPadrao`, `valorCargaHoraria`
- Datas exceção: `dataInicioExcecaoInputDate`, `dataTerminoExcecaoInputDate`,
  `dataInicioExcecaoSabadoInputDate`, `dataTerminoExcecaoSabadoInputDate`
- `comentarios` (textarea), `salvar`, `cancelar`

## Verbas (`verba/verba-calculo.jsf`)

### Listagem (após Expresso/Manual):
- `formulario:listagem:N:verbaSelecionada` (checkbox principal)
- `formulario:listagem:N:j_id558` — link "Parâmetros da Verba"
- `formulario:listagem:N:j_id559` — link "Ocorrências da Verba"
- `formulario:listagem:N:j_id560` — link "Excluir"
- `formulario:listagem:N:listaReflexo:M:ativo` — checkbox reflexa (Multa 467, etc.)

### Botões topo:
- `formulario:incluir` (Manual)
- (Expresso, Regerar — outros botões)

## Histórico Salarial (`historico-salarial.jsf`)

### Listagem:
- `formulario:listagem:0:excluirHistorico` — link Excluir entrada (texto "Excluir")
- (entrada default "ÚLTIMA REMUNERAÇÃO" sempre presente quando
  valorUltimaRemuneracao tem valor — gerada AT EXPORT TIME server-side)

## FGTS (`fgts.jsf`)

⚠️ **`formulario:multa` é CHECKBOX, NÃO SELECT** (correção crítica)

- `formulario:tipoDeVerba:0=PAGAR, :1=DEPOSITAR (label "Recolher")`
- `formulario:comporPrincipal:0=SIM, :1=NAO`
- `formulario:multa` (checkbox — habilita campos condicionais)
- `formulario:tipoDoValorDaMulta:0=CALCULADA, :1=INFORMADA`
- `formulario:multaDoFgts:0=VINTE_POR_CENTO, :1=QUARENTA_POR_CENTO`
- `formulario:aliquota:0=DOIS_POR_CENTO, :1=OITO_POR_CENTO`
- `formulario:incidenciaDoFgts` (select):
  SOBRE_O_TOTAL_DEVIDO, SOBRE_DEPOSITADO_SACADO, SOBRE_DIFERENCA,
  SOBRE_TOTAL_DEVIDO_MAIS_SAQUE_E_OU_SALDO,
  SOBRE_TOTAL_DEVIDO_MENOS_SAQUE_E_OU_SALDO
- `formulario:excluirAvisoDaMulta`, `multaDoArtigo467`, `multa10`,
  `contribuiçãoSocial` (note ç não-ASCII no ID),
  `incidenciaPensaoAlimenticia` (checkboxes)
- Período: `periodoInicial`, `periodoFinal` (text)

## INSS (`inss/inss.jsf`)

- `formulario:apurarInssSeguradoDevido`, `cobrarDoReclamanteDevido`,
  `corrigirDescontoReclamante`, `apurarSalariosPagos` (checkboxes)
- `formulario:aliquotaEmpregado:0=SEGURADO_EMPREGADO, :1=EMPREGADO_DOMESTICO,
  :2=FIXA`
- `formulario:aliquotaEmpregador:0=POR_ATIVIDADE_ECONOMICA, :1=POR_PERIODO,
  :2=FIXA`

## IRPF (`irpf.jsf`)

Checkboxes:
- `apurarImpostoRenda` ("Apurar Imposto de Renda")
- `incidirSobreJurosDeMora`
- `cobrarDoReclamado`
- `considerarTributacaoExclusiva`, `considerarTributacaoEmSeparado`
- `regimeDeCaixa` ("Aplicar Regime de Caixa")
- `deduzirContribuicaoSocialDevidaPeloReclamante`

## Honorários (`honorarios.jsf`)

⚠️ **TRT7 Institucional NÃO tem `SUCUMBENCIAIS`** (versão Cidadão pode ter)

- `formulario:tpHonorario` (select):
  - ADVOCATICIOS (= sucumbenciais no TRT7), ASSISTENCIAIS, CONTRATUAIS
  - PERICIAIS_CONTADOR, PERICIAIS_DOCUMENTOSCOPIO, PERICIAIS_ENGENHEIRO,
    PERICIAIS_INTERPRETE, PERICIAIS_MEDICO
- `formulario:descricao` (text)
- `formulario:tipoDeDevedor:0=RECLAMANTE, :1=RECLAMADO`
- `formulario:tipoValor:0=INFORMADO, :1=CALCULADO`
- `formulario:baseParaApuracao` (select):
  BRUTO, BRUTO_MENOS_CONTRIBUICAO_SOCIAL,
  BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA
- `formulario:selecaoCredores`, `nomeCredor`, `numeroDocumentoFiscalCredor`
- `formulario:tipoDocumentoFiscalCredor:0=CPF, :1=CNPJ, :2=CEI`
- `formulario:apurarIRRF` (checkbox)

## Custas (`custas-judiciais.jsf`) ⚠️ não `custas/custas.jsf`

- `formulario:baseParaCustasCalculadas` (select):
  - BRUTO_DEVIDO_AO_RECLAMANTE
  - BRUTO_DEVIDO_AO_RECLAMANTE_MAIS_DEBITOS_RECLAMADO
- `formulario:tipoDeCustasDeConhecimentoDoReclamante:N` (radio):
  0=NAO_SE_APLICA, 1=CALCULADA_2_POR_CENTO, 2=INFORMADA
- `formulario:tipoDeCustasDeConhecimentoDoReclamado:N` (radio): mesmas opções
- `formulario:tipoDeCustasDeLiquidacao:N` (radio):
  0=NAO_SE_APLICA, 1=CALCULADA_MEIO_POR_CENTO, 2=INFORMADA
- `formulario:tipoDeAuto` (select): REMICAO, ADJUDICACAO, ARREMATACAO
- Quantidades: `qtdeAtosUrbanos`, `qtdeAtosRurais`, `qtdeAgravosDeInstrumento`,
  `qtdeAgravosDePeticao`, `qtdeImpugnacaoSentenca`, `qtdeEmbargosArrematacao`,
  `qtdeEmbargosExecucao`, `qtdeEmbargosTerceiros`, `qtdeRecursoRevista`
- Datas: `dataVencimentoCustasFixasInputDate`, `dataVencimentoAutoInputDate`,
  `dataInicioArmazenamentoInputDate`
- `valorAvaliacaoAuto`

## Correção/Juros (`parametros-atualizacao/parametros-atualizacao.jsf`)

- `formulario:indiceTrabalhista` (select):
  TUACDT, TABELA_DEVEDOR_FAZENDA, TABELA_INDEBITO_TRIBUTARIO,
  TABELA_UNICA_JT_MENSAL, TABELA_UNICA_JT_DIARIO,
  TR, IGPM, INPC, IPC, IPCA, IPCAE (⚠️ sem underscore!), IPCAETR,
  SELIC, SELIC_FAZENDA, SELIC_BACEN, SEM_CORRECAO
- `formulario:juros` (select):
  JUROS_PADRAO (⚠️ não 'PADRAO'), JUROS_POUPANCA, FAZENDA_PUBLICA,
  JUROS_MEIO_PORCENTO, JUROS_UM_PORCENTO, JUROS_ZERO_TRINTA_TRES,
  SELIC, SELIC_FAZENDA, SELIC_BACEN, TRD_SIMPLES, TRD_COMPOSTOS,
  TAXA_LEGAL, SEM_JUROS
- `formulario:outroJuros` (select): mesmas opções + NoSelectionConverter
- Checkboxes: `combinarOutroIndice`, `ignorarTaxaNegativa`,
  `aplicarJurosFasePreJudicial`, `combinarOutroJuros`
- `formulario:apartirDeOutroJurosInputDate` (data)
- `formulario:salvar`

## Multas e Indenizações (`multas-indenizacoes.jsf`)

- `formulario:descricao` (text)
- `formulario:credorDevedor` (select):
  RECLAMANTE_RECLAMADO, RECLAMADO_RECLAMANTE,
  TERCEIRO_RECLAMANTE, TERCEIRO_RECLAMADO
- `formulario:valor:0=INFORMADO, :1=CALCULADO`
- `formulario:tipoBaseMulta` (select):
  PRINCIPAL, PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL,
  PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA, VALOR_CAUSA
- `formulario:aliquota` (text)

## Salário-Família (`salario-familia.jsf`)

- `apurarSalarioFamilia` (checkbox)
- `formulario:comporPrincipal:0=SIM, :1=NAO`
- `dataInicialInputDate`, `dataFinalInputDate`
- `quantFilhosMenores14Anos` (text)
- `formulario:tipoSalarioPago:0=NENHUM, :1=MAIOR_REMUNERACAO, :2=HISTORICO_SALARIAL`
- `formulario:historicoSalarial` (select condicional)
- `formulario:verba` (select)
- `formulario:integralizar` (select SIM/NAO)

## Seguro-Desemprego (`seguro-desemprego.jsf`)

- `apurar` (checkbox)
- `formulario:solicitacao` (select): PRIMEIRA, SEGUNDA, DEMAIS
- `formulario:valor:0=INFORMADO, :1=CALCULADO`
- `formulario:comporPrincipal:0=SIM, :1=NAO`
- `numeroDeParcelas` (text)
- `formulario:tipoSalarioPago:0/1/2` (mesmas que Salário-Família)
- `formulario:historicoSalarial` (select condicional)

## Previdência Privada (`previdencia-privada.jsf`)

- `apurar` (checkbox)
- Datas (período)
- `formulario:aliquota` (text)
- `formulario:salvar`

## Pensão Alimentícia (`pensao-alimenticia.jsf`)

- `apurar` (checkbox)
- `formulario:aliquota` (text)
- `formulario:incidirSobreJuros` (checkbox)
- `formulario:salvar`

## Faltas (`falta.jsf`)

- `dataInicioPeriodoFaltaInputDate`, `dataTerminoPeriodoFaltaInputDate`
- `faltaJustificada` (checkbox)
- `reiniciaFerias` (checkbox)
- `formulario:arquivo:file` (upload), `confirmarImportacao` (submit)

## Férias (`ferias.jsf`)

- IDs dinâmicos pattern `j_id106:N:*`:
  - `prazo` (text)
  - `situacao` (select):
    GOZADAS, GOZADAS_PARCIALMENTE, INDENIZADAS, PERDIDAS
    ⚠️ NÃO existe "PROPORCIONAIS" — proporcionais geradas auto pela rescisão
  - `dobraGeral`, `abono` (checkbox)
  - `quantidadeDiasAbono` (text)
  - `dataInicialDoPeriodoDeGozo1/2/3` (text)
  - `dataFinalDoPeriodoDeGozo1/2/3` (text)
- `inicioFeriasColetivasInputDate` (text)
- `regerarFeriasColetivas` (button)

## Cartão de Ponto (`../cartaodeponto/apuracao-cartaodeponto.jsf`)

- `formulario:incluir` (button — adicionar entrada)
- `formulario:visualizarOcorrencias` (button)
- `formulario:importarCartao` (button)

## Liquidação (`liquidacao.jsf`)

- `formulario:dataDeLiquidacaoInputDate` (text)
- `formulario:indicesAcumulados:0=MES_SUBSEQUENTE_AO_VENCIMENTO,
  :1=MES_DO_VENCIMENTO, :2=MES_SUBSEQUENTE_E_MES_DO_VENCIMENTO`
- `formulario:liquidar` (button)
- `formulario:totalErros` (text — útil para diagnóstico)
- `formulario:totalAlertas` (text)
- Tabela "Pendências do Cálculo" com legenda Erro/Alerta

## Operações

- `li_operacoes_liquidar`, `_fechar`, `_excluir`, `_exportar`, `_validar`
  (Validar = "Enviar para o PJe")
- Atualização de pagamento aparece apenas após liquidar (li_pagamento_*)
