# Catálogo de Campos — PJE-Calc Cidadão (v2.15.1)

Gerado automaticamente por `scripts/cataloga_pjecalc.py`. Contém TODOS os campos editáveis de cada página, com IDs reais, tipos, opções e defaults — base para refatorar a prévia HTML como espelho fiel do PJE-Calc.

## 01_dados_processo — Dados do Cálculo

- URL: `http://localhost:9257/pjecalc/pages/calculo/calculo.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `idCalculo` 🔒 | text |  |  |  |
| `tipo` 🔒 | text |  |  |  |
| `dataCriacao` 🔒 | text |  |  |  |
| `numero`  | text | Número | 1234 |  |
| `digito`  | text | Dígito | 56 |  |
| `ano`  | text | Ano | 2025 |  |
| `justica` 🔒 | text | Justiça | 5 |  |
| `regiao`  | text | Tribunal | 7 |  |
| `vara`  | text | Vara | 1 |  |
| `valorDaCausa`  | text | Valor da Causa | 1.000,00 |  |
| `autuadoEm`  | text | Autuado em |  |  |
| `reclamanteNome`  | text | Nome | TESTE CATALOGO |  |
| `documentoFiscalReclamante:0`  | radio | CPF | CPF |  |
| `documentoFiscalReclamante:1`  | radio | CNPJ | CNPJ |  |
| `documentoFiscalReclamante:2`  | radio | CEI | CEI |  |
| `reclamanteNumeroDocumentoFiscal` 🔒 | text | Número |  |  |
| `reclamanteTipoDocumentoPrevidenciario:0`  | radio | PIS | PIS |  |
| `reclamanteTipoDocumentoPrevidenciario:1`  | radio | PASEP | PASEP |  |
| `reclamanteTipoDocumentoPrevidenciario:2`  | radio | NIT | NIT |  |
| `reclamanteNumeroDocumentoPrevidenciario` 🔒 | text | Número |  |  |
| `nomeAdvogadoReclamante`  | text | Nome |  |  |
| `numeroOABAdvogadoReclamante`  | text | OAB |  |  |
| `tipoDocumentoAdvogadoReclamante:0`  | radio | CPF | CPF |  |
| `tipoDocumentoAdvogadoReclamante:1`  | radio | CNPJ | CNPJ |  |
| `tipoDocumentoAdvogadoReclamante:2`  | radio | CEI | CEI |  |
| `numeroDocumentoAdvogadoReclamante` 🔒 | text | Número |  |  |
| `reclamadoNome`  | text | Nome | EMPRESA TESTE |  |
| `tipoDocumentoFiscalReclamado:0`  | radio | CPF | CPF |  |
| `tipoDocumentoFiscalReclamado:1`  | radio | CNPJ | CNPJ |  |
| `tipoDocumentoFiscalReclamado:2`  | radio | CEI | CEI |  |
| `reclamadoNumeroDocumentoFiscal` 🔒 | text | Número |  |  |
| `nomeAdvogadoReclamado`  | text | Nome |  |  |
| `numeroOABAdvogadoReclamado`  | text | OAB |  |  |
| `tipoDocumentoAdvogadoReclamado:0`  | radio | CPF | CPF |  |
| `tipoDocumentoAdvogadoReclamado:1`  | radio | CNPJ | CNPJ |  |
| `tipoDocumentoAdvogadoReclamado:2`  | radio | CEI | CEI |  |
| `numeroDocumentoAdvogadoReclamado` 🔒 | text | Número |  |  |
| `dataAdmissaoInputDate` 👻 | text |  |  |  |
| `dataDemissaoInputDate` 👻 | text |  |  |  |
| `dataAjuizamentoInputDate` 👻 | text |  |  |  |
| `dataInicioCalculoInputDate` 👻 | text |  |  |  |
| `dataTerminoCalculoInputDate` 👻 | text |  |  |  |
| `prescricaoQuinquenal` 👻 | checkbox | Aplicar Prescrição | on |  |
| `prescricaoFgts` 👻 | checkbox |  | on |  |
| `valorMaiorRemuneracao` 👻 | text | Maior Remuneração | 2.500,00 |  |
| `valorUltimaRemuneracao` 👻 | text | Última Remuneração | 2.500,00 |  |
| `projetaAvisoIndenizado` 👻 | checkbox |  | on |  |
| `limitarAvos` 🔒👻 | checkbox |  | on |  |
| `zeraValorNegativo` 👻 | checkbox |  | on |  |
| `consideraFeriadoEstadual` 👻 | checkbox |  | on |  |
| `consideraFeriadoMunicipal` 👻 | checkbox |  | on |  |
| `valorCargaHorariaPadrao` 👻 | text | Padrão *: | 220,00 |  |
| `dataInicioExcecaoInputDate` 👻 | text |  |  |  |
| `dataTerminoExcecaoInputDate` 👻 | text |  |  |  |
| `valorCargaHoraria` 👻 | text | Exceção |  |  |
| `sabadoDiaUtil` 👻 | checkbox |  | on |  |
| `dataInicioExcecaoSabadoInputDate` 👻 | text |  |  |  |
| `dataTerminoExcecaoSabadoInputDate` 👻 | text |  |  |  |
| `formularioModalPPJE:numero` 👻 | text | Número |  |  |
| `formularioModalPPJE:digito` 👻 | text | Dígito |  |  |
| `formularioModalPPJE:ano` 👻 | text | Ano |  |  |
| `formularioModalPPJE:justica` 🔒👻 | text | Justiça |  |  |
| `formularioModalPPJE:regiao` 👻 | text | Tribunal |  |  |
| `formularioModalPPJE:vara` 👻 | text | Vara |  |  |
| `formularioModalPPJE:inverterPartes` 👻 | checkbox |  | on |  |
| `selAcheFacil` 👻 | select-one |  |  |  |
| `estado` 👻 | select-one | Estado * | org.jboss.seam.ui.NoSelectionC | `org.jboss.seam.ui.NoSelectionConverter.noSelectionValue`=; `0`=AC; `1`=AL; `2`=AP; `3`=AM; `4`=BA;  |
| `municipio` 👻 | select-one | Município * | org.jboss.seam.ui.NoSelectionC | `org.jboss.seam.ui.NoSelectionConverter.noSelectionValue`= |
| `tipoDaBaseTabelada` 👻 | select-one |  | INTEGRAL | `INTERMITENTE`=Trabalho Intermitente; `INTEGRAL`=Tempo Integral; `PARCIAL`=Tempo Parcial |
| `apuracaoPrazoDoAvisoPrevio` 👻 | select-one | Prazo de Aviso Prévio | APURACAO_CALCULADA | `NAO_APURAR`=Não apurar; `APURACAO_CALCULADA`=Calculado; `APURACAO_INFORMADA`=Informado |
| `pontoFacultativo` 👻 | select-one | Ponto Facultativo | org.jboss.seam.ui.NoSelectionC | `org.jboss.seam.ui.NoSelectionConverter.noSelectionValue`=; `27`=SEXTA-FEIRA SANTA; `28`=CORPUS CHRI |
| `formularioModalPPJE:reclamantes` 🔒👻 | select-one |  |  |  |
| `formularioModalPPJE:reclamados` 🔒👻 | select-one |  |  |  |
| `comentarios` 👻 | textarea |  |  |  |

### Radios (grupos)

- `formulario:documentoFiscalReclamante`: `CPF`✓, `CNPJ`, `CEI`
- `formulario:reclamanteTipoDocumentoPrevidenciario`: `PIS`, `PASEP`, `NIT`
- `formulario:tipoDocumentoAdvogadoReclamante`: `CPF`, `CNPJ`, `CEI`
- `formulario:tipoDocumentoFiscalReclamado`: `CPF`, `CNPJ`✓, `CEI`
- `formulario:tipoDocumentoAdvogadoReclamado`: `CPF`, `CNPJ`, `CEI`

## 02_faltas_listing — Faltas

- URL: `http://localhost:9257/pjecalc/pages/calculo/falta.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `dataInicioPeriodoFaltaInputDate`  | text |  |  |  |
| `dataTerminoPeriodoFaltaInputDate`  | text |  |  |  |
| `faltaJustificada`  | checkbox |  | on |  |
| `reiniciaFerias`  | checkbox |  | on |  |
| `arquivo:file`  | file |  |  |  |
| `selAcheFacil` 👻 | select-one |  |  |  |
| `justificativaDaFalta`  | textarea |  |  |  |

## 03_ferias_listing — Férias

- URL: `http://localhost:9257/pjecalc/pages/calculo/ferias.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `arquivo:file`  | file |  |  |  |
| `inicioFeriasColetivasInputDate`  | text |  |  |  |
| `prazoFeriasProporcionais`  | text | Prazo das Férias Proporcionais |  |  |
| `selAcheFacil` 👻 | select-one |  |  |  |

## 04_historico_salarial_listing — Histórico Salarial

- URL: `http://localhost:9257/pjecalc/pages/calculo/historico-salarial.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 05_verbas_listing — Verbas

- URL: `http://localhost:9257/pjecalc/pages/calculo/verba/verba-calculo.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `tipoRegeracao:0`  | radio | Manter alterações realizadas nas ocorrên | true |  |
| `tipoRegeracao:1`  | radio | Sobrescrever alterações realizadas nas o | false |  |
| `formularioModalCNJ:assuntosCnjCNJ` 🔒👻 | text | Assunto CNJ * |  |  |
| `selAcheFacil` 👻 | select-one |  |  |  |

### Radios (grupos)

- `formulario:tipoRegeracao`: `true`, `false`

## 06_cartao_ponto — Cartão de Ponto

- URL: `http://localhost:9257/pjecalc/pages/cartaodeponto/apuracao-cartaodeponto.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 07_salario_familia — Salário-família

- URL: `http://localhost:9257/pjecalc/pages/calculo/salario-familia.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 08_seguro_desemprego — Seguro-desemprego

- URL: `http://localhost:9257/pjecalc/pages/calculo/seguro-desemprego.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 09_fgts — FGTS

- URL: `http://localhost:9257/pjecalc/pages/calculo/fgts.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 10_inss — Contribuição Social (INSS)

- URL: `http://localhost:9257/pjecalc/pages/calculo/inss/inss.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 11_previdencia_privada — Previdência Privada

- URL: `http://localhost:9257/pjecalc/pages/calculo/previdencia-privada.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 12_pensao_alimenticia — Pensão Alimentícia

- URL: `http://localhost:9257/pjecalc/pages/calculo/pensao-alimenticia.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 13_irpf — Imposto de Renda

- URL: `http://localhost:9257/pjecalc/pages/calculo/irpf.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 14_multas_indenizacoes — Multas e Indenizações

- URL: `http://localhost:9257/pjecalc/pages/calculo/multas-indenizacoes.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 15_honorarios — Honorários

- URL: `http://localhost:9257/pjecalc/pages/calculo/honorarios.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 16_custas — Custas Judiciais

- URL: `http://localhost:9257/pjecalc/pages/calculo/custas-judiciais.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 17_correcao_juros — Correção, Juros e Multa

- URL: `http://localhost:9257/pjecalc/pages/calculo/parametros-atualizacao/parametros-atualizacao.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `selAcheFacil` 👻 | select-one |  |  |  |

## 04b_historico_salarial_form — Histórico Salarial — form Novo

- URL: `http://localhost:9257/pjecalc/pages/calculo/historico-salarial.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `arquivo:file`  | file |  |  |  |
| `nome`  | text | Nome * |  |  |
| `tipoVariacaoDaParcela:0`  | radio | Fixa | FIXA |  |
| `tipoVariacaoDaParcela:1`  | radio | Variável | VARIAVEL |  |
| `fgts`  | checkbox |  | on |  |
| `inss`  | checkbox |  | on |  |
| `competenciaInicialInputDate`  | text |  |  |  |
| `competenciaFinalInputDate`  | text |  |  |  |
| `tipoValor:0`  | radio | Informado | INFORMADO |  |
| `tipoValor:1`  | radio | Calculado | CALCULADO |  |
| `valorParaBaseDeCalculo`  | text | Valor * |  |  |
| `selAcheFacil` 👻 | select-one |  |  |  |

### Radios (grupos)

- `formulario:tipoVariacaoDaParcela`: `FIXA`✓, `VARIAVEL`
- `formulario:tipoValor`: `INFORMADO`✓, `CALCULADO`

## 02b_faltas_form — 02b_faltas_form

⚠️ Erro ao catalogar: `botão input[id$='incluir'] não encontrado`

## 03b_ferias_form — 03b_ferias_form

⚠️ Erro ao catalogar: `botão input[id$='incluir'] não encontrado`

## 05b_verbas_expresso — Verbas — Lançamento Expresso

- URL: `http://localhost:9257/pjecalc/pages/calculo/verba/verbas-para-calculo.jsf?conversationId=139`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `j_id82:0:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:0:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:0:j_id84:2:selecionada`  | checkbox |  | on |  |
| `j_id82:1:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:1:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:1:j_id84:2:selecionada`  | checkbox |  | on |  |
| `j_id82:2:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:2:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:2:j_id84:2:selecionada`  | checkbox |  | on |  |
| `j_id82:3:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:3:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:3:j_id84:2:selecionada`  | checkbox |  | on |  |
| `j_id82:4:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:4:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:5:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:5:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:6:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:6:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:7:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:7:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:8:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:8:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:9:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:9:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:10:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:10:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:11:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:11:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:12:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:12:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:13:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:13:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:14:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:14:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:15:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:15:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:16:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:16:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:17:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:17:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:18:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:18:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:19:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:19:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:20:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:20:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:21:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:21:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:22:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:22:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:23:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:23:j_id84:1:selecionada`  | checkbox |  | on |  |
| `j_id82:24:j_id84:0:selecionada`  | checkbox |  | on |  |
| `j_id82:24:j_id84:1:selecionada`  | checkbox |  | on |  |
| `selAcheFacil` 👻 | select-one |  |  |  |

## 05c_verbas_manual — Verbas — Manual (form)

- URL: `http://localhost:9257/pjecalc/pages/calculo/verba/verba-calculo.jsf?conversationId=86#irTopoPagina`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `descricao`  | text |  |  |  |
| `assuntosCnj`  | text | Assuntos CNJ * |  |  |
| `tipoVariacaoDaParcela:0`  | radio | Fixa | FIXA |  |
| `tipoVariacaoDaParcela:1`  | radio | Variável | VARIAVEL |  |
| `valor:0`  | radio | Calculado | CALCULADO |  |
| `valor:1`  | radio | Informado | INFORMADO |  |
| `irpf`  | checkbox |  | on |  |
| `inss`  | checkbox |  | on |  |
| `fgts`  | checkbox |  | on |  |
| `previdenciaPrivada`  | checkbox |  | on |  |
| `pensaoAlimenticia`  | checkbox |  | on |  |
| `caracteristicaVerba:0`  | radio | Comum | COMUM |  |
| `caracteristicaVerba:1`  | radio | 13º Salário | DECIMO_TERCEIRO_SALARIO |  |
| `caracteristicaVerba:2`  | radio | Aviso Prévio | AVISO_PREVIO |  |
| `caracteristicaVerba:3`  | radio | Férias | FERIAS |  |
| `ocorrenciaPagto:0`  | radio | Desligamento | DESLIGAMENTO |  |
| `ocorrenciaPagto:1`  | radio | Dezembro | DEZEMBRO |  |
| `ocorrenciaPagto:2`  | radio | Mensal | MENSAL |  |
| `ocorrenciaPagto:3`  | radio | Período Aquisitivo | PERIODO_AQUISITIVO |  |
| `ocorrenciaAjuizamento:0`  | radio | Sim | OCORRENCIAS_VENCIDAS_E_VINCEND |  |
| `ocorrenciaAjuizamento:1`  | radio | Não | OCORRENCIAS_VENCIDAS |  |
| `tipoDeVerba:0`  | radio | Principal | PRINCIPAL |  |
| `tipoDeVerba:1`  | radio | Reflexa | REFLEXO |  |
| `geraReflexo:0`  | radio | Devido | DEVIDO |  |
| `geraReflexo:1`  | radio | Diferença | DIFERENCA |  |
| `gerarPrincipal:0`  | radio | Devido | DEVIDO |  |
| `gerarPrincipal:1`  | radio | Diferença | DIFERENCA |  |
| `comporPrincipal:0`  | radio | Sim | SIM |  |
| `comporPrincipal:1`  | radio | Não | NAO |  |
| `zeraValorNegativo`  | checkbox |  | on |  |
| `periodoInicialInputDate`  | text |  |  |  |
| `periodoFinalInputDate`  | text |  |  |  |
| `excluirFaltaJustificada`  | checkbox |  | on |  |
| `excluirFaltaNaoJustificada`  | checkbox |  | on |  |
| `excluirFeriasGozadas`  | checkbox |  | on |  |
| `dobraValorDevido`  | checkbox |  | on |  |
| `aplicarProporcionalidadeABase`  | checkbox |  | on |  |
| `tipoDeDivisor:0`  | radio | Informado * | OUTRO_VALOR |  |
| `tipoDeDivisor:1`  | radio | Carga Horária | CARGA_HORARIA |  |
| `tipoDeDivisor:2`  | radio | Dias Úteis | DIAS_UTEIS |  |
| `tipoDeDivisor:3`  | radio | Importada do Cartão de Ponto | IMPORTADA_DO_CARTAO |  |
| `outroValorDoDivisor`  | text |  |  |  |
| `outroValorDoMultiplicador`  | text |  |  |  |
| `tipoDaQuantidade:0`  | radio | Informada | INFORMADA |  |
| `tipoDaQuantidade:1`  | radio | Importada do Calendário | IMPORTADA_DO_CALENDARIO |  |
| `tipoDaQuantidade:2`  | radio | Importada do Cartão de Ponto | IMPORTADA_DO_CARTAO |  |
| `valorInformadoDaQuantidade`  | text |  |  |  |
| `aplicarProporcionalidadeAQuantidade`  | checkbox |  | on |  |
| `tipoDoValorPago:0`  | radio | Informado | INFORMADO |  |
| `tipoDoValorPago:1`  | radio | Calculado | CALCULADO |  |
| `valorInformadoPago`  | text | Valor | 0,00 |  |
| `aplicarProporcionalidadeValorPago`  | checkbox |  | on |  |
| `formularioModalCNJ:assuntosCnjCNJ` 🔒👻 | text | Assunto CNJ * |  |  |
| `selAcheFacil` 👻 | select-one |  |  |  |
| `tipoDaBaseTabelada`  | select-one |  | org.jboss.seam.ui.NoSelectionC | `org.jboss.seam.ui.NoSelectionConverter.noSelectionValue`=; `MAIOR_REMUNERACAO`=Maior Remuneração; ` |
| `baseVerbaDeCalculo`  | select-one |  | org.jboss.seam.ui.NoSelectionC | `org.jboss.seam.ui.NoSelectionConverter.noSelectionValue`= |
| `integralizarBase`  | select-one |  | SIM | `SIM`=Sim; `NAO`=Não |
| `comentarios`  | textarea |  |  |  |

### Radios (grupos)

- `formulario:tipoVariacaoDaParcela`: `FIXA`✓, `VARIAVEL`
- `formulario:valor`: `CALCULADO`✓, `INFORMADO`
- `formulario:caracteristicaVerba`: `COMUM`✓, `DECIMO_TERCEIRO_SALARIO`, `AVISO_PREVIO`, `FERIAS`
- `formulario:ocorrenciaPagto`: `DESLIGAMENTO`, `DEZEMBRO`, `MENSAL`✓, `PERIODO_AQUISITIVO`
- `formulario:ocorrenciaAjuizamento`: `OCORRENCIAS_VENCIDAS_E_VINCENDAS`, `OCORRENCIAS_VENCIDAS`✓
- `formulario:tipoDeVerba`: `PRINCIPAL`✓, `REFLEXO`
- `formulario:geraReflexo`: `DEVIDO`, `DIFERENCA`✓
- `formulario:gerarPrincipal`: `DEVIDO`, `DIFERENCA`✓
- `formulario:comporPrincipal`: `SIM`✓, `NAO`
- `formulario:tipoDeDivisor`: `OUTRO_VALOR`✓, `CARGA_HORARIA`, `DIAS_UTEIS`, `IMPORTADA_DO_CARTAO`
- `formulario:tipoDaQuantidade`: `INFORMADA`✓, `IMPORTADA_DO_CALENDARIO`, `IMPORTADA_DO_CARTAO`
- `formulario:tipoDoValorPago`: `INFORMADO`✓, `CALCULADO`

## 15b_honorarios_form — Honorários — form Novo

- URL: `http://localhost:9257/pjecalc/pages/calculo/honorarios.jsf?conversationId=86`

### Campos editáveis

| ID | Tipo | Label | Default | Opções/Detalhes |
|---|---|---|---|---|
| `descricao`  | text | Descrição * | Honorários Advocatícios |  |
| `tipoDeDevedor:0`  | radio | Reclamante | RECLAMANTE |  |
| `tipoDeDevedor:1`  | radio | Reclamado | RECLAMADO |  |
| `tipoValor:0`  | radio | Informado | INFORMADO |  |
| `tipoValor:1`  | radio | Calculado | CALCULADO |  |
| `aliquota`  | text | Alíquota (%) * |  |  |
| `nomeCredor`  | text | Nome Completo * |  |  |
| `tipoDocumentoFiscalCredor:0`  | radio | CPF | CPF |  |
| `tipoDocumentoFiscalCredor:1`  | radio | CNPJ | CNPJ |  |
| `tipoDocumentoFiscalCredor:2`  | radio | CEI | CEI |  |
| `numeroDocumentoFiscalCredor`  | text | Número |  |  |
| `apurarIRRF`  | checkbox |  | on |  |
| `selAcheFacil` 👻 | select-one |  |  |  |
| `tpHonorario`  | select-one | Tipo de Honorário * | ADVOCATICIOS | `ADVOCATICIOS`=Honorários Advocatícios; `ASSISTENCIAIS`=Honorários Assistenciais; `CONTRATUAIS`=Hono |
| `baseParaApuracao`  | select-one | Base para Apuração * | org.jboss.seam.ui.NoSelectionC | `org.jboss.seam.ui.NoSelectionConverter.noSelectionValue`=; `BRUTO`=Bruto; `BRUTO_MENOS_CONTRIBUICAO |
| `selecaoCredores`  | select-one | Credor | org.jboss.seam.ui.NoSelectionC | `org.jboss.seam.ui.NoSelectionConverter.noSelectionValue`=Preencher Dados... |

### Radios (grupos)

- `formulario:tipoDeDevedor`: `RECLAMANTE`, `RECLAMADO`
- `formulario:tipoValor`: `INFORMADO`, `CALCULADO`✓
- `formulario:tipoDocumentoFiscalCredor`: `CPF`✓, `CNPJ`, `CEI`
