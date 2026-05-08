# PJE-Calc DOM Reference

Gerado em: 2026-04-17T01:05:52.901451
URL base: http://localhost:9257/pjecalc

## Sidebar Navigation

| Texto | ID | Li ID |
|-------|-----|-------|
| Tela Inicial | `formulario:j_id38:0:j_id41:0:j_id46` | `li_tela_inicial` |
| Novo | `formulario:j_id38:0:j_id41:1:j_id46` | `li_calculo_novo` |
| Novo Cálculo Externo | `formulario:j_id38:0:j_id41:2:j_id46` | `li_calculo_externo_novo` |
| Buscar | `formulario:j_id38:0:j_id41:3:j_id46` | `li_calculo_buscar` |
| Importar | `formulario:j_id38:0:j_id41:4:j_id46` | `li_calculo_importar` |
| Relatório Consolidado | `formulario:j_id38:0:j_id41:5:j_id46` | `li_processo_relatorio` |
| Salário Mínimo | `formulario:j_id38:4:j_id41:0:j_id46` | `li_tabelas_salario_minimo` |
| Pisos Salariais | `formulario:j_id38:4:j_id41:1:j_id46` | `li_tabelas_salario_categoria` |
| Salário-família | `formulario:j_id38:4:j_id41:2:j_id46` | `li_tabelas_salario_familia` |
| Seguro-desemprego | `formulario:j_id38:4:j_id41:3:j_id46` | `li_tabelas_seguro_desemprego` |
| Vale-transporte | `formulario:j_id38:4:j_id41:4:j_id46` | `li_tabelas_vale_transporte` |
| Feriados e Pontos Facultativos | `formulario:j_id38:4:j_id41:5:j_id46` | `li_tabelas_feriado` |
| Verbas | `formulario:j_id38:4:j_id41:6:j_id46` | `li_tabelas_verbas` |
| Contribuição Social | `formulario:j_id38:4:j_id41:7:j_id46` | `li_tabelas_inss` |
| Imposto de Renda | `formulario:j_id38:4:j_id41:8:j_id46` | `li_tabela_irpf` |
| Custas Judiciais | `formulario:j_id38:4:j_id41:9:j_id46` | `li_tabelas_parametros_custas` |
| Correção Monetária | `formulario:j_id38:4:j_id41:10:j_id46` | `li_tabelas_indices_gerais` |
| Juros de Mora | `formulario:j_id38:4:j_id41:11:j_id46` | `li_tabelas_juros` |
| Atualização de Tabelas e Índices | `formulario:j_id38:4:j_id41:13:j_id46` | `li_tabelas_sincronizar` |

## Dados do Processo

- **JSF**: `calculo/calculo.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/calculo.jsf?conversationId=9#irTopoPagina`
- **Total elementos**: 134
- **Visiveis**: 52
- **Descricao**: Numero do processo, partes, documentos fiscais

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |
| `idCalculo` | Número * | `text` | - | `input:not([type='hidden'])[id$='idCalculo']` |
| `tipo` | Tipo * | `text` | 1 | `input:not([type='hidden'])[id$='tipo']` |
| `dataCriacao` | Data de Criação * | `text` | 1 | `input:not([type='hidden'])[id$='dataCriacao']` |
| `numero` | Número | `text` | 7 | `input:not([type='hidden'])[id$='numero']` |
| `digito` | Dígito | `text` | 2 | `input:not([type='hidden'])[id$='digito']` |
| `ano` | Ano | `text` | 4 | `input:not([type='hidden'])[id$='ano']` |
| `justica` | Justiça | `text` | 1 | `input:not([type='hidden'])[id$='justica']` |
| `regiao` | Tribunal | `text` | 2 | `input:not([type='hidden'])[id$='regiao']` |
| `vara` | Vara | `text` | 4 | `input:not([type='hidden'])[id$='vara']` |
| `valorDaCausa` | Valor da Causa | `text` | 16 | `input:not([type='hidden'])[id$='valorDaCausa']` |
| `autuadoEm` | Autuado em | `text` | 16 | `input:not([type='hidden'])[id$='autuadoEm']` |
| `reclamanteNome` | Nome | `text` | 150 | `input:not([type='hidden'])[id$='reclamanteNome']` |
| `reclamanteNumeroDocumentoFiscal` | Número | `text` | - | `input:not([type='hidden'])[id$='reclamanteNumeroDocumentoFiscal']` |
| `reclamanteNumeroDocumentoPrevidenciario` | Número | `text` | 11 | `input:not([type='hidden'])[id$='reclamanteNumeroDocumentoPrevidenciario']` |
| `nomeAdvogadoReclamante` | Nome | `text` | 150 | `input:not([type='hidden'])[id$='nomeAdvogadoReclamante']` |
| `numeroOABAdvogadoReclamante` | OAB | `text` | 9 | `input:not([type='hidden'])[id$='numeroOABAdvogadoReclamante']` |
| `numeroDocumentoAdvogadoReclamante` | Número | `text` | - | `input:not([type='hidden'])[id$='numeroDocumentoAdvogadoReclamante']` |
| `reclamadoNome` | Nome | `text` | 150 | `input:not([type='hidden'])[id$='reclamadoNome']` |
| `reclamadoNumeroDocumentoFiscal` | Número | `text` | - | `input:not([type='hidden'])[id$='reclamadoNumeroDocumentoFiscal']` |
| `nomeAdvogadoReclamado` | Nome | `text` | 150 | `input:not([type='hidden'])[id$='nomeAdvogadoReclamado']` |
| `numeroOABAdvogadoReclamado` | OAB | `text` | 9 | `input:not([type='hidden'])[id$='numeroOABAdvogadoReclamado']` |
| `numeroDocumentoAdvogadoReclamado` | Número | `text` | - | `input:not([type='hidden'])[id$='numeroDocumentoAdvogadoReclamado']` |

### Radios

| ID Sufixo | Label | Value | Name | Seletor |
|-----------|-------|-------|------|---------|
| `0` | CPF | `CPF` | `formulario:documentoFiscalReclamante` | `input[type='radio'][id$='0']` |
| `1` | CNPJ | `CNPJ` | `formulario:documentoFiscalReclamante` | `input[type='radio'][id$='1']` |
| `2` | CEI | `CEI` | `formulario:documentoFiscalReclamante` | `input[type='radio'][id$='2']` |
| `0` | PIS | `PIS` | `formulario:reclamanteTipoDocumentoPrevidenciario` | `input[type='radio'][id$='0']` |
| `1` | PASEP | `PASEP` | `formulario:reclamanteTipoDocumentoPrevidenciario` | `input[type='radio'][id$='1']` |
| `2` | NIT | `NIT` | `formulario:reclamanteTipoDocumentoPrevidenciario` | `input[type='radio'][id$='2']` |
| `0` | CPF | `CPF` | `formulario:tipoDocumentoAdvogadoReclamante` | `input[type='radio'][id$='0']` |
| `1` | CNPJ | `CNPJ` | `formulario:tipoDocumentoAdvogadoReclamante` | `input[type='radio'][id$='1']` |
| `2` | CEI | `CEI` | `formulario:tipoDocumentoAdvogadoReclamante` | `input[type='radio'][id$='2']` |
| `0` | CPF | `CPF` | `formulario:tipoDocumentoFiscalReclamado` | `input[type='radio'][id$='0']` |
| `1` | CNPJ | `CNPJ` | `formulario:tipoDocumentoFiscalReclamado` | `input[type='radio'][id$='1']` |
| `2` | CEI | `CEI` | `formulario:tipoDocumentoFiscalReclamado` | `input[type='radio'][id$='2']` |
| `0` | CPF | `CPF` | `formulario:tipoDocumentoAdvogadoReclamado` | `input[type='radio'][id$='0']` |
| `1` | CNPJ | `CNPJ` | `formulario:tipoDocumentoAdvogadoReclamado` | `input[type='radio'][id$='1']` |
| `2` | CEI | `CEI` | `formulario:tipoDocumentoAdvogadoReclamado` | `input[type='radio'][id$='2']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `salvar` | Salvar | `input[id$='salvar']` |
| `cancelar` | Cancelar | `input[id$='cancelar']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |
| `incluirAdvogadoReclamante` |  | `a[id$='incluirAdvogadoReclamante']` |
| `incluirAdvogadoReclamado` |  | `a[id$='incluirAdvogadoReclamado']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:painelMensagens:j_id69** (classes: ['rich-messages'], headers: [], rows: 1)
- **formulario:j_id138** (classes: ['rich-tabpanel'], headers: ['Ação', 'Nome', 'Tipo Documento', 'Nº Documento', 'OAB', 'Ação', 'Nome', 'Tipo Documento', 'Nº Documento', 'OAB', 'Ação', 'Nome', 'Abrangência'], rows: 135)
- **formulario:tabDadosProcesso_shifted** (classes: [], headers: [], rows: 2)
- **formulario:tabParametrosCalculo_shifted** (classes: [], headers: [], rows: 2)
- **formulario:painelIdentificacao** (classes: [], headers: [], rows: 4)
- **formulario:documentoFiscalReclamante** (classes: ['labelInput'], headers: [], rows: 1)
- **formulario:reclamanteTipoDocumentoPrevidenciario** (classes: ['labelInput'], headers: [], rows: 1)
- **formulario:tipoDocumentoAdvogadoReclamante** (classes: [], headers: [], rows: 1)
- **formulario:listagemAdvogadoReclamante** (classes: ['rich-table'], headers: ['Ação', 'Nome', 'Tipo Documento', 'Nº Documento', 'OAB'], rows: 1)
- **formulario:tipoDocumentoFiscalReclamado** (classes: ['labelInput'], headers: [], rows: 1)
- **formulario:tipoDocumentoAdvogadoReclamado** (classes: [], headers: [], rows: 1)
- **formulario:listagemAdvogadoReclamado** (classes: ['rich-table'], headers: ['Ação', 'Nome', 'Tipo Documento', 'Nº Documento', 'OAB'], rows: 1)
- **formulario:dataAdmissao** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataDemissao** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataAjuizamento** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataInicioCalculo** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataTerminoCalculo** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataInicioExcecao** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataTerminoExcecao** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataInicioExcecaoSabado** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataTerminoExcecaoSabado** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:listagemPontosFacultativos** (classes: ['rich-table'], headers: ['Ação', 'Nome', 'Abrangência'], rows: 4)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **modalPPJEContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 7)
- **painelMensagensModalPPJE:j_id654** (classes: ['rich-messages'], headers: [], rows: 1)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Parametros do Calculo

- **JSF**: `calculo/calculo.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/calculo.jsf?conversationId=9#irTopoPagina`
- **Total elementos**: 134
- **Visiveis**: 50
- **Descricao**: Estado, municipio, datas, jornada, rescisao, aviso previo

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |
| `idCalculo` | Número * | `text` | - | `input:not([type='hidden'])[id$='idCalculo']` |
| `tipo` | Tipo * | `text` | 1 | `input:not([type='hidden'])[id$='tipo']` |
| `dataCriacao` | Data de Criação * | `text` | 1 | `input:not([type='hidden'])[id$='dataCriacao']` |
| `dataAdmissaoInputDate` | Admissão * | `text` | - | `input:not([type='hidden'])[id$='dataAdmissaoInputDate']` |
| `dataDemissaoInputDate` | Demissão | `text` | - | `input:not([type='hidden'])[id$='dataDemissaoInputDate']` |
| `dataAjuizamentoInputDate` | Ajuizamento * | `text` | - | `input:not([type='hidden'])[id$='dataAjuizamentoInputDate']` |
| `dataInicioCalculoInputDate` | Data Inicial | `text` | - | `input:not([type='hidden'])[id$='dataInicioCalculoInputDate']` |
| `dataTerminoCalculoInputDate` | Data Final | `text` | - | `input:not([type='hidden'])[id$='dataTerminoCalculoInputDate']` |
| `valorMaiorRemuneracao` | Maior Remuneração | `text` | 16 | `input:not([type='hidden'])[id$='valorMaiorRemuneracao']` |
| `valorUltimaRemuneracao` | Última Remuneração | `text` | 16 | `input:not([type='hidden'])[id$='valorUltimaRemuneracao']` |
| `valorCargaHorariaPadrao` | Padrão *: | `text` | 7 | `input:not([type='hidden'])[id$='valorCargaHorariaPadrao']` |
| `dataInicioExcecaoInputDate` | Início | `text` | - | `input:not([type='hidden'])[id$='dataInicioExcecaoInputDate']` |
| `dataTerminoExcecaoInputDate` | Fim | `text` | - | `input:not([type='hidden'])[id$='dataTerminoExcecaoInputDate']` |
| `valorCargaHoraria` | Exceção | `text` | 6 | `input:not([type='hidden'])[id$='valorCargaHoraria']` |
| `dataInicioExcecaoSabadoInputDate` | Início | `text` | - | `input:not([type='hidden'])[id$='dataInicioExcecaoSabadoInputDate']` |
| `dataTerminoExcecaoSabadoInputDate` | Fim | `text` | - | `input:not([type='hidden'])[id$='dataTerminoExcecaoSabadoInputDate']` |

### Selects

| ID Sufixo | Label | Opcoes | Seletor |
|-----------|-------|--------|---------|
| `estado` | Estado * | org.jboss.seam.ui.NoSelectionConverter.noSelectionValue=, 0=AC, 1=AL, 2=AP, 3=AM... (+23) | `select[id$='estado']` |
| `municipio` | Município * | org.jboss.seam.ui.NoSelectionConverter.noSelectionValue=, 30=ABAIARA, 31=ACARAPE, 32=ACARAU, 33=ACOPIARA... (+180) | `select[id$='municipio']` |
| `tipoDaBaseTabelada` | Regime de Trabalho | INTERMITENTE=Trabalho Interm, INTEGRAL=Tempo Integral, PARCIAL=Tempo Parcial | `select[id$='tipoDaBaseTabelada']` |
| `apuracaoPrazoDoAvisoPrevio` | Prazo de Aviso Prévio | NAO_APURAR=Não apurar, APURACAO_CALCULADA=Calculado, APURACAO_INFORMADA=Informado | `select[id$='apuracaoPrazoDoAvisoPrevio']` |
| `pontoFacultativo` | Ponto Facultativo | org.jboss.seam.ui.NoSelectionConverter.noSelectionValue=, 27=SEXTA-FEIRA SAN, 28=CORPUS CHRISTI, 29=CARNAVAL | `select[id$='pontoFacultativo']` |

### Checkboxs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `prescricaoQuinquenal` | Aplicar Prescrição | `checkbox` | - | `input[type='checkbox'][id$='prescricaoQuinquenal']` |
| `prescricaoFgts` | Aplicar Prescrição | `checkbox` | - | `input[type='checkbox'][id$='prescricaoFgts']` |
| `projetaAvisoIndenizado` | Projetar Aviso Prévio Indeniza | `checkbox` | - | `input[type='checkbox'][id$='projetaAvisoIndenizado']` |
| `limitarAvos` | Limitar Avos ao Período do Cál | `checkbox` | - | `input[type='checkbox'][id$='limitarAvos']` |
| `zeraValorNegativo` | Zerar Valor Negativo (Padrão) | `checkbox` | - | `input[type='checkbox'][id$='zeraValorNegativo']` |
| `consideraFeriadoEstadual` | Considerar Feriados Estaduais | `checkbox` | - | `input[type='checkbox'][id$='consideraFeriadoEstadual']` |
| `consideraFeriadoMunicipal` | Considerar Feriados Municipais | `checkbox` | - | `input[type='checkbox'][id$='consideraFeriadoMunicipal']` |
| `sabadoDiaUtil` | Sábado como Dia Útil | `checkbox` | - | `input[type='checkbox'][id$='sabadoDiaUtil']` |

### Textareas

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `comentarios` | Comentários | `` | - | `textarea[id$='comentarios']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `salvar` | Salvar | `input[id$='salvar']` |
| `cancelar` | Cancelar | `input[id$='cancelar']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |
| `municipioErro` | Campo obrigatório: Município//<![CDATA[
 | `a[id$='municipioErro']` |
| `incluirExcecaoCH` |  | `a[id$='incluirExcecaoCH']` |
| `incluirExcecaoSab` |  | `a[id$='incluirExcecaoSab']` |
| `cmdAdicionarPontoFacultativo` |  | `a[id$='cmdAdicionarPontoFacultativo']` |
| `excluirPontoFacultativo` |  | `a[id$='excluirPontoFacultativo']` |
| `excluirPontoFacultativo` |  | `a[id$='excluirPontoFacultativo']` |
| `excluirPontoFacultativo` |  | `a[id$='excluirPontoFacultativo']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:painelMensagens:j_id69** (classes: ['rich-messages'], headers: [], rows: 1)
- **formulario:j_id138** (classes: ['rich-tabpanel'], headers: ['Ação', 'Nome', 'Tipo Documento', 'Nº Documento', 'OAB', 'Ação', 'Nome', 'Tipo Documento', 'Nº Documento', 'OAB', 'Ação', 'Nome', 'Abrangência'], rows: 135)
- **formulario:tabDadosProcesso_shifted** (classes: [], headers: [], rows: 2)
- **formulario:tabParametrosCalculo_shifted** (classes: [], headers: [], rows: 2)
- **formulario:painelIdentificacao** (classes: [], headers: [], rows: 4)
- **formulario:documentoFiscalReclamante** (classes: ['labelInput'], headers: [], rows: 1)
- **formulario:reclamanteTipoDocumentoPrevidenciario** (classes: ['labelInput'], headers: [], rows: 1)
- **formulario:tipoDocumentoAdvogadoReclamante** (classes: [], headers: [], rows: 1)
- **formulario:listagemAdvogadoReclamante** (classes: ['rich-table'], headers: ['Ação', 'Nome', 'Tipo Documento', 'Nº Documento', 'OAB'], rows: 1)
- **formulario:tipoDocumentoFiscalReclamado** (classes: ['labelInput'], headers: [], rows: 1)
- **formulario:tipoDocumentoAdvogadoReclamado** (classes: [], headers: [], rows: 1)
- **formulario:listagemAdvogadoReclamado** (classes: ['rich-table'], headers: ['Ação', 'Nome', 'Tipo Documento', 'Nº Documento', 'OAB'], rows: 1)
- **formulario:dataAdmissao** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataDemissao** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataAjuizamento** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataInicioCalculo** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataTerminoCalculo** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataInicioExcecao** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataTerminoExcecao** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataInicioExcecaoSabado** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:dataTerminoExcecaoSabado** (classes: ['rich-calendar-exterior', 'rich-calendar-popup', 'undefined'], headers: [], rows: 9)
- **formulario:listagemPontosFacultativos** (classes: ['rich-table'], headers: ['Ação', 'Nome', 'Abrangência'], rows: 4)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **modalPPJEContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 7)
- **painelMensagensModalPPJE:j_id654** (classes: ['rich-messages'], headers: [], rows: 1)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Parametros Gerais

- **JSF**: `calculo/parametros-gerais.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/calculo/parametros-gerais.jsf?conversationId=9`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Data inicio apuracao, carga horaria, zerar negativos

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Historico Salarial - Listagem

- **JSF**: `calculo/historico-salarial.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/calculo/historico-salarial.jsf?conversationId=9`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Parcelas salariais, gerar ocorrencias

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Historico Salarial

- **JSF**: `calculo/historico-salarial.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/calculo/historico-salarial.jsf?conversationId=9`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Parcelas salariais, gerar ocorrencias

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Ferias

- **JSF**: `calculo/ferias.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/calculo/ferias.jsf?conversationId=9`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Periodos aquisitivos, situacao, dias gozados

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Faltas

- **JSF**: `calculo/faltas.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/calculo/faltas.jsf?conversationId=9`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Registro de ausencias

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Cartao de Ponto

- **JSF**: `calculo/apuracao-cartaodeponto.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/calculo/apuracao-cartaodeponto.jsf?conversationId=9`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Grade semanal, intervalos, horas extras/noturnas

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Verbas - Listagem

- **JSF**: `verba/verba-calculo.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/verba/verba-calculo.jsf?conversationId=9`
- **Total elementos**: 547
- **Visiveis**: 16
- **Descricao**: Tabela com verbas criadas, botoes Expresso/Manual/Novo

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Radios

| ID Sufixo | Label | Value | Name | Seletor |
|-----------|-------|-------|------|---------|
| `0` | Manter alterações realizadas n | `true` | `formulario:tipoRegeracao` | `input[type='radio'][id$='0']` |
| `1` | Sobrescrever alterações realiz | `false` | `formulario:tipoRegeracao` | `input[type='radio'][id$='1']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `incluir` | Manual | `input[id$='incluir']` |
| `lancamentoExpresso` | Expresso | `input[id$='lancamentoExpresso']` |
| `regerarOcorrencias` | Regerar | `input[id$='regerarOcorrencias']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:tipoRegeracao** (classes: ['labelInput'], headers: [], rows: 2)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **modalCNJContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 501)
- **formularioModalCNJ:arv:864::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1806::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1806:1932::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1806:2445::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1806:2445:55061::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1806:2523::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1806:2523:55062::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1806:55059::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1806:55060::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1806:55063::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1816::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1816:1807::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1816:55066::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1816:55067::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1816:55068::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1816:55069::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1844::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1844:5352::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1844:5354::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:1957::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2029::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2029:2031::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2029:2033::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2029:2037::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2133::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2233::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2233:55064::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2409::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2421::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2537::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2554::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2554:55071::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2554:55072::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2554:55073::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2554:55074::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:2670::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5272::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5272:1814::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5272:1822::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5272:2266::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5272:55057::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5272:55058::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5273::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5273:9487::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5273:9487:55075::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5273:9487:55076::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5273:9487:55331::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5273:9487:55332::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5273:9487:55333::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5273:9487:55334::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:5273:9487:55335::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:7647::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:55065::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1654:55070::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:1661::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:1661:55370::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:1663::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:1663:55358::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55097::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55098::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55099::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55100::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55101::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55102::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55102:55103::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55365::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55366::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55367::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55368::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2086:55369::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2116::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2139::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2140::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2140:55112::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2140:55371::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2140:55372::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2140:55373::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2140:55374::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2426::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2426:55376::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2426:55377::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:2426:55378::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:10581::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:10581:55379::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:10581:55380::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55095::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55095:55359::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55095:55360::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55095:55361::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55095:55362::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55095:55363::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55095:55364::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55104::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55105::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55105:55106::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55105:55106:55107::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55108::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55108:55109::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55108:55109:55110::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1658:55108:55111::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:1690::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:1691::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:1703::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:1705::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:1773::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:4435::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:4435:55007::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:4437::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:4438::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:4452::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:4452:55089::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:4452:55090::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:10564::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55008::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55009::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55087::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55088::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55091::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55091:55092::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55091:55093::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55091:55094::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55345::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55345:55346::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55347::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55348::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55348:55349::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55348:55349:55350::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55348:55349:55351::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55348:55352::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55348:55353::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55354::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55355::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55355:55356::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1695:55355:55357::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:2704::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:2704:55217::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:2704:55217:55426::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:2704:55425::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:2704:55427::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:2704:55428::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:2704:55428:55429::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:2704:55428:55430::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:5356::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:8805::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:8805:55424::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:8806::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:8807::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:1937:55423::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:1723::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:1724::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:2569::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:9051::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55213::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55214::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55215::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55215:55413::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55215:55414::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55415::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55416::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55417::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55418::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55419::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55420::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55421::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:1855:55422::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:8808::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:8808:8809::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:8808:55210::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:8808:55211::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:8808:55212::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:55209::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2567:55216::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1767::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1783::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1789::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1888::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1888:55151::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1888:55152::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1888:55153::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1888:55154::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1888:55155::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1888:55156::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1888:55157::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1888:55398::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1920::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:1920:55158::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:8817::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:8818::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:55160::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:55161::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:55162::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:55163::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:55164::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:55165::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:55166::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:55167::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2055:55168::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2117::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2215::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2273::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2331::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2331:55171::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2349::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2364::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2450::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2450:55375::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:1721::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:2275::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:2449::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:2452::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:2461::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:2463::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:2466::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:2468::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:2697::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:2697:55191::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:5269::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:8810::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:8812::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:8816::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55176::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55177::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55178::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55179::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55180::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55181::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55182::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55183::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55184::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55185::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55186::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55188::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2458:55189::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2477::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2493::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2506::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2506:55401::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2506:55402::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2540::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2583::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2583:55124::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2583:55126::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2583:55127::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2583:55128::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2583:55129::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2583:55388::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1666::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1666:55130::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1666:55131::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1666:55134::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1666:55135::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1666:55390::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1666:55391::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1666:55392::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1681::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1681:55136::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1681:55138::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1681:55139::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1681:55140::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1681:55393::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1681:55394::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:1681:55395::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:2604::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:55142::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:55143::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:55144::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:55145::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:55146::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:55147::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:55389::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2594:55396::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2606::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:2666::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:4442::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:4442:55173::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:4442:55174::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:4442:55175::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:4442:55399::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:8813::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:55148::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:55149::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:55150::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:55159::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:55169::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:55170::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:55172::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:55397::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2581:55400::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:1849::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:1904::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:1904:55193::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:1904:55194::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:1907::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:1907:55200::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:1907:55404::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2243::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2243:55203::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2435::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2478::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2478:2479::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2478:2480::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:1998::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:1998:55208::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:2210::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:2212::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:2641::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:2641:55409::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:2641:55410::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:2641:55411::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:2641:55412::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:8820::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:8821::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:8822::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2546:8823::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:1929::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:1965::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:1966::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:1976::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:1977::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:1978::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:1981::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:2657::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:2661::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:55205::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:55206::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:2656:55207::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:8824::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55192::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55195::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55196::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55197::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55198::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55199::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55202::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55204::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55403::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55405::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55405:55406::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55405:55407::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2620:55405:55408::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55011::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55012::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55013::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55014::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55015::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55015:55016::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55017::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55018::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55019::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55020::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55314::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:2624:55315::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2622:55010::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2662::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2662:2019::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2662:2019:55114::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2662:2021::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2662:2663::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2662:55113::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:2662:55115::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:2557::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:2558::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:2559::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:7629::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:7630::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:7631::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:7632::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:7633::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:7633:55381::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:55116::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:55117::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:55118::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:55119::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:55120::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:55121::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:55122::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7628:55123::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5276::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5276:55022::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5276:55023::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5277::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5278::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5279::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55025::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55026::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55026:55027::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55026:55028::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55026:55318::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55026:55319::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55029::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55030::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55312::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55316::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55317::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55320::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5280:55321::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5281::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5282::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5284::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5284:55042::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5286::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5287::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5288::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5288:55038::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5289::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5290::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5291::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5292::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5293::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5294::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5294:55325::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5294:55326::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5294:55327::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5295::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5296::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5297::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5297:55051::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5299::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5299:55329::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5299:55330::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:5301::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:7645::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:7646::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:7646:55328::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55021::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55024::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55031::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55032::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55034::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55035::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55036::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55037::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55039::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55040::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55041::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55043::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55044::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55045::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55047::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55048::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55049::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55050::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55052::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55053::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55322::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55322:55323::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:7644:55322:55324::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:10569::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:10570::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:10571::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:55225::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:55382::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:55383::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:55384::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:55385::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:55386::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:10568:55387::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55006::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55054::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55054:55055::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55054:55056::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55077::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55077:55344::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55078::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55078:55079::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55078:55080::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55078:55081::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55078:55082::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55218::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55218:55219::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55218:55220::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55336::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55336:55337::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55336:55338::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55336:55339::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55336:55340::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55341::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55341:55342::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **formularioModalCNJ:arv:864:55341:55343::_defaultNodeFace** (classes: ['rich-tree-node'], headers: [], rows: 1)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Verbas - Lancamento Expresso

- **JSF**: `verba/verbas-para-calculo.xhtml`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/verba/verbas-para-calculo.jsf?conversationId=39`
- **Total elementos**: 90
- **Visiveis**: 67
- **Descricao**: Tabela com ~60 checkboxes de verbas pre-definidas

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Checkboxs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | 13º SALÁRIO | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | FÉRIAS + 1/3 | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ABONO PECUNIÁRIO | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | GORJETA | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ACORDO (MERA LIBERALIDADE) | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | GRATIFICAÇÃO DE FUNÇÃO | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ACORDO (MULTA) | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | GRATIFICAÇÃO POR TEMPO DE SERV | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ACORDO (VERBAS INDENIZATÓRIAS) | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ACORDO (VERBAS REMUNERATÓRIAS) | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL DE HORAS EXTRAS 50% | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL DE INSALUBRIDADE 10% | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL DE INSALUBRIDADE 20% | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL DE INSALUBRIDADE 40% | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL DE PERICULOSIDADE 30 | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL DE PRODUTIVIDADE 30% | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL DE RISCO 40% | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL DE SOBREAVISO | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL DE TRANSFERÊNCIA 25% | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | ADICIONAL NOTURNO 20% | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | AJUDA DE CUSTO | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | AVISO PRÉVIO | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | CESTA BÁSICA | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | COMISSÃO | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | DEVOLUÇÃO DE DESCONTOS INDEVID | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | DIFERENÇA SALARIAL | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | DIÁRIAS - INTEGRAÇÃO AO SALÁRI | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | DIÁRIAS - PAGAMENTO | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` |  | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |
| `selecionada` | FERIADO EM DOBRO | `checkbox` | - | `input[type='checkbox'][id$='selecionada']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `salvar` | Salvar | `input[id$='salvar']` |
| `cancelar` | Cancelar | `input[id$='cancelar']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:listagem** (classes: ['list-check'], headers: [], rows: 25)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## FGTS

- **JSF**: `fgts/fgts.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/fgts/fgts.jsf?conversationId=39`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Tipo verba, aliquota, multas, incidencia

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Contribuicao Social (INSS)

- **JSF**: `inss/inss.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/inss/inss.jsf?conversationId=39`
- **Total elementos**: 36
- **Visiveis**: 13
- **Descricao**: Apurar segurado, cobrar reclamante, correcao trabalhista

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `salvar` | Salvar | `input[id$='salvar']` |
| `ocorrencias` | Ocorrências | `input[id$='ocorrencias']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Imposto de Renda (IRPF)

- **JSF**: `irpf/irpf.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/irpf/irpf.jsf?conversationId=39`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Tributacao, deducoes, dependentes

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Honorarios - Listagem

- **JSF**: `honorarios/honorarios.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/honorarios/honorarios.jsf?conversationId=39`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Tipo, devedor, percentual, base apuracao

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Honorarios

- **JSF**: `honorarios/honorarios.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/honorarios/honorarios.jsf?conversationId=39`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Tipo, devedor, percentual, base apuracao

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Correcao, Juros e Multa

- **JSF**: `correcao-juros.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/correcao-juros.jsf?conversationId=39`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Indice correcao, taxa juros, multa 523

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Multas e Indenizacoes - Listagem

- **JSF**: `multas-indenizacoes.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/multas-indenizacoes.jsf?conversationId=39`
- **Total elementos**: 35
- **Visiveis**: 12
- **Descricao**: Multa 477, multa 467, indenizacoes art. 9 Lei 7238

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `incluir` | Novo | `input[id$='incluir']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Multas e Indenizacoes

- **JSF**: `multas-indenizacoes.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/multas-indenizacoes.jsf?conversationId=39`
- **Total elementos**: 42
- **Visiveis**: 19
- **Descricao**: Multa 477, multa 467, indenizacoes art. 9 Lei 7238

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |
| `descricao` | Descrição * | `text` | 60 | `input:not([type='hidden'])[id$='descricao']` |
| `aliquota` | Alíquota (%) * | `text` | - | `input:not([type='hidden'])[id$='aliquota']` |

### Selects

| ID Sufixo | Label | Opcoes | Seletor |
|-----------|-------|--------|---------|
| `credorDevedor` | Credor/Devedor | RECLAMANTE_RECLAMADO=Reclamante e Re, RECLAMADO_RECLAMANTE=Reclamado e Rec, TERCEIRO_RECLAMANTE=Terceiro e Recl, TERCEIRO_RECLAMADO=Terceiro e Recl | `select[id$='credorDevedor']` |
| `tipoBaseMulta` | Base | PRINCIPAL=Principal, PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL=Principal (-) C, PRINCIPAL_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA=Principal (-) C, VALOR_CAUSA=Valor Corrigido | `select[id$='tipoBaseMulta']` |

### Radios

| ID Sufixo | Label | Value | Name | Seletor |
|-----------|-------|-------|------|---------|
| `0` | Informado | `INFORMADO` | `formulario:valor` | `input[type='radio'][id$='0']` |
| `1` | Calculado | `CALCULADO` | `formulario:valor` | `input[type='radio'][id$='1']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `salvar` | Salvar | `input[id$='salvar']` |
| `cancelar` | Cancelar | `input[id$='cancelar']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:valor** (classes: ['labelInput'], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Custas Judiciais

- **JSF**: `custas-judiciais.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/custas-judiciais.jsf?conversationId=39`
- **Total elementos**: 35
- **Visiveis**: 12
- **Descricao**: Custas judiciais, isencao

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `salvar` | Salvar | `input[id$='salvar']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Salario Familia

- **JSF**: `salario-familia.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/salario-familia.jsf?conversationId=39`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Apurar, competencias, quantidade filhos

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Seguro Desemprego

- **JSF**: `seguro-desemprego.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/seguro-desemprego.jsf?conversationId=39`
- **Total elementos**: 35
- **Visiveis**: 12
- **Descricao**: Apurar seguro desemprego

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `salvar` | Salvar | `input[id$='salvar']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Pensao Alimenticia

- **JSF**: `pensao-alimenticia.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/pensao-alimenticia.jsf?conversationId=39`
- **Total elementos**: 35
- **Visiveis**: 12
- **Descricao**: Percentual, beneficiario

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `salvar` | Salvar | `input[id$='salvar']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Previdencia Privada

- **JSF**: `previdencia-privada.jsf`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/previdencia-privada.jsf?conversationId=39`
- **Total elementos**: 35
- **Visiveis**: 12
- **Descricao**: Percentual previdencia privada

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `salvar` | Salvar | `input[id$='salvar']` |

### Links

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `j_id46` | Tela Inicial | `a[id$='j_id46']` |
| `j_id46` | Novo | `a[id$='j_id46']` |
| `j_id46` | Novo Cálculo Externo | `a[id$='j_id46']` |
| `j_id46` | Buscar | `a[id$='j_id46']` |
| `j_id46` | Importar | `a[id$='j_id46']` |
| `j_id46` | Relatório Consolidado | `a[id$='j_id46']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Liquidar

- **JSF**: `liquidacao/liquidacao.xhtml`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/liquidacao/liquidacao.xhtml?conversationId=39`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Botao de liquidacao, data, lista calculos recentes

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)

## Exportar

- **JSF**: `exportacao/exportacao.xhtml`
- **URL**: `http://localhost:9257/pjecalc/pages/calculo/exportacao/exportacao.xhtml?conversationId=39`
- **Total elementos**: 17
- **Visiveis**: 6
- **Descricao**: Botao de download .PJC

### Inputs

| ID Sufixo | Label | Tipo | MaxLen | Seletor |
|-----------|-------|------|--------|---------|
| `searchText` |  | `text` | - | `input:not([type='hidden'])[id$='searchText']` |
| `searchTextBt` | Pesquisar
										
									 | `image` | - | `input:not([type='hidden'])[id$='searchTextBt']` |
| `zoomNormalBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomNormalBt']` |
| `zoomMedioBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomMedioBt']` |
| `zoomGdeBt` |  | `image` | - | `input:not([type='hidden'])[id$='zoomGdeBt']` |

### Buttons

| ID Sufixo | Texto | Seletor |
|-----------|-------|---------|
| `fechar` |  | `input[id$='fechar']` |

### Tabelas

- **tbPesquisa** (classes: [], headers: [], rows: 1)
- **formulario:msgAguardeContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
- **skinPanelContentTable** (classes: ['rich-mp-content-table'], headers: [], rows: 2)
