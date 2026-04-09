"""
PJE-Calc DOM Selectors — Constantes extraidas manualmente do playwright_pjecalc.py.

Este arquivo sera SOBRESCRITO pelo DOM Auditor (tools/dom_auditor.py) quando executado
contra uma instancia real do PJE-Calc. Os seletores abaixo sao os CONHECIDOS ate agora,
baseados em inspecao manual do DOM (v2.15.1).

Convencao de seletores:
  - [id$='sufixo']  : sufixo do ID JSF (ignora prefixo dinamico formulario:j_idXXX:)
  - [id*='parcial'] : match parcial (para IDs com partes intermediarias variaveis)
  - input:not([type='hidden']) : evita match em campos ocultos do RichFaces

Uso:
    from knowledge.pjecalc_selectors import DadosProcesso, FGTS, Verbas
    page.locator(DadosProcesso.NUMERO).fill('1234567')
"""

from __future__ import annotations


# ============================================================================
# Dados do Processo (calculo.jsf — aba tabDadosProcesso)
# ============================================================================

class DadosProcesso:
    """Campos da aba 'Dados do Processo' em calculo.jsf"""
    JSF = "calculo/calculo.jsf"
    ABA = "tabDadosProcesso"

    # Tipo e data de criacao (cabecalho)
    TIPO = "[id$='tipo']"
    DATA_DE_CRIACAO = "[id$='dataDeCriacao'], [id$='dataCriacao'], [id$='dataDeAbertura']"
    DATA_CALCULO = "[id*='dataDe'], [id*='dataCria'], [id*='dataCalc']"

    # Numero do processo (6 campos separados)
    NUMERO = "[id$='numero']"
    DIGITO = "[id$='digito']"
    ANO = "[id$='ano']"
    JUSTICA = "[id$='justica']"
    REGIAO = "[id$='regiao']"
    VARA = "[id$='vara']"

    # Valor da causa e autuacao
    VALOR_DA_CAUSA = "[id$='valorDaCausa'], [id$='valorCausa']"
    AUTUADO_EM = "[id$='autuadoEm'], [id$='dataAutuacao']"

    # Partes
    RECLAMANTE_NOME = "[id$='reclamanteNome'], [id$='nomeReclamante']"
    RECLAMADO_NOME = "[id$='reclamadoNome'], [id$='nomeReclamado']"

    # Documentos fiscais
    DOC_FISCAL_RECLAMANTE = "[id$='documentoFiscalReclamante']"  # radio CPF/CNPJ
    RECLAMANTE_DOC_NUMERO = "[id$='reclamanteNumeroDocumentoFiscal'], [id$='cpfReclamante']"
    TIPO_DOC_FISCAL_RECLAMADO = "[id$='tipoDocumentoFiscalReclamado']"  # radio CPF/CNPJ
    RECLAMADO_DOC_NUMERO = "[id$='reclamadoNumeroDocumentoFiscal'], [id$='cnpjReclamado']"

    # Advogado
    NOME_ADVOGADO_RECLAMANTE = "[id$='nomeAdvogadoReclamante']"
    OAB_ADVOGADO_RECLAMANTE = "[id$='numeroOABAdvogadoReclamante']"

    # Botoes
    SALVAR = "[id$='salvar']"


# ============================================================================
# Parametros do Calculo (calculo.jsf — aba tabParametrosCalculo)
# ============================================================================

class ParametrosCalculo:
    """Campos da aba 'Parametros do Calculo' em calculo.jsf"""
    JSF = "calculo/calculo.jsf"
    ABA = "tabParametrosCalculo"

    # Localizacao
    ESTADO = "select[id$='estado']"  # select com indices numericos (0=AC, 1=AL, ...)
    MUNICIPIO = "select[id$='municipio']"  # carregado via AJAX apos selecao do estado

    # Datas do contrato
    DATA_ADMISSAO = "[id*='dataAdmissaoInputDate'], [id$='dataAdmissao']"
    DATA_DEMISSAO = "[id*='dataDemissaoInputDate'], [id$='dataDemissao']"
    DATA_AJUIZAMENTO = "[id*='dataAjuizamentoInputDate'], [id$='dataAjuizamento']"
    DATA_CITACAO = "[id*='dataCitacaoInputDate'], [id$='dataCitacao']"
    DATA_DISTRIBUICAO = "[id*='dataDistribuicaoInputDate'], [id$='dataDistribuicao']"
    DATA_PRESCRICAO = "[id*='dataPrescricaoInputDate'], [id$='dataPrescricao']"

    # Tipo de rescisao
    TIPO_RESCISAO = "[id$='tipoRescisao']"  # radio: SEM_JUSTA_CAUSA, COM_JUSTA_CAUSA, etc.
    MOTIVO_RESCISAO = "[id$='motivoRescisao']"

    # Aviso previo
    AVISO_PREVIO_TIPO = "[id$='tipoAvisoPrevio']"  # radio: TRABALHADO, INDENIZADO, etc.
    AVISO_PREVIO_DIAS = "[id$='diasAvisoPrevio']"
    DATA_AVISO = "[id$='dataAviso'], [id*='dataAvisoInputDate']"

    # Jornada basica
    CARGA_HORARIA = "[id$='cargaHoraria']"
    JORNADA_SEMANAL = "[id$='jornadaSemanal']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Parametros Gerais (parametros-gerais.jsf ou sub-tab)
# ============================================================================

class ParametrosGerais:
    """Campos de Parametros Gerais"""
    JSF = "calculo/parametros-gerais.jsf"

    DATA_INICIAL_APURACAO = "[id$='dataInicialApuracao'], [id$='dataInicio']"
    DATA_FINAL_APURACAO = "[id$='dataFinalApuracao'], [id$='dataFim']"
    CARGA_HORARIA_DIARIA = "[id$='cargaHorariaDiaria']"
    CARGA_HORARIA_SEMANAL = "[id$='cargaHorariaSemanal']"
    ZERAR_VALORES_NEGATIVOS = "input[type='checkbox'][id$='zerarValoresNegativos']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Historico Salarial (historico-salarial.jsf)
# ============================================================================

class HistoricoSalarial:
    """Campos do Historico Salarial"""
    JSF = "calculo/historico-salarial.jsf"

    # Campos do formulario de inclusao
    NOME = "[id$='nome']"
    COMPETENCIA_INICIAL = "[id*='competenciaInicialInputDate'], [id*='competenciaInicial']"
    COMPETENCIA_FINAL = "[id*='competenciaFinalInputDate'], [id*='competenciaFinal']"
    TIPO_VARIACAO = "[id$='tipoVariacao']"  # select
    TIPO_VALOR = "[id$='tipoValor']"  # select/radio
    VALOR_PARA = "[id$='valorPara'], [id$='valorParaBaseDeCalculo']"

    # Incidencias
    INCIDENCIA_FGTS = "[id$='incidenciaFgts'], [id*='fgts']"
    INCIDENCIA_CS = "[id$='incidenciaCs'], [id*='inss']"

    # Botoes
    GERAR_OCORRENCIAS = "a[id*='cmdGerarOcorrencias'], a[id*='GerarOcorrencias']"
    ADICIONAR = "a[id*='cmdAdicionarOcorrencia'], a[id*='Adicionar']"
    INCLUIR = "[id$='incluir'], [id$='novo']"
    SALVAR = "[id$='salvar']"

    # Tabela de listagem
    TABELA_LISTAGEM = "table[id*='listagemMC'], table[id*='listagem']"

    # Radio de regeracao
    TIPO_REGERACAO = "input[id$='tipoRegeracao'][type='radio']"
    REGERAR_OCORRENCIAS = "[id$='regerarOcorrencias']"


# ============================================================================
# Ferias (ferias.jsf)
# ============================================================================

class Ferias:
    """Campos de Ferias"""
    JSF = "calculo/ferias.jsf"

    # Via Expresso: ferias + 1/3 sao configuradas automaticamente
    # Nao criar manual separado (CLAUDE.md regra)

    REGERAR_FERIAS = "[id$='regerarFerias']"
    SALVAR = "[id$='salvar']"


# ============================================================================
# Faltas (faltas.jsf)
# ============================================================================

class Faltas:
    """Campos de Faltas"""
    JSF = "calculo/faltas.jsf"

    INCLUIR = "input[id$='incluir'][value='Novo']"
    SALVAR = "[id$='salvar']"


# ============================================================================
# Cartao de Ponto (apuracao-cartaodeponto.xhtml)
# ============================================================================

class CartaoPonto:
    """Campos do Cartao de Ponto"""
    JSF = "calculo/apuracao-cartaodeponto.xhtml"

    # Tipo de apuracao
    TIPO_APURACAO_HORAS_EXTRAS = "[id$='tipoApuracaoHorasExtras']"  # radio HST/HJD/APH/NAP
    TIPO_ESCALA = "select[id$='tipoEscala']"

    # Jornada por dia da semana (HH:MM)
    JORNADA_SEGUNDA = "input[id$='valorJornadaSegunda']"
    JORNADA_TERCA = "input[id$='valorJornadaTerca']"
    JORNADA_QUARTA = "input[id$='valorJornadaQuarta']"
    JORNADA_QUINTA = "input[id$='valorJornadaQuinta']"
    JORNADA_SEXTA = "input[id$='valorJornadaSexta']"
    JORNADA_SABADO = "input[id$='valorJornadaSabado']"
    JORNADA_DOMINGO = "input[id$='valorJornadaDomingo']"

    # Totais
    QT_JORNADA_SEMANAL = "input[id$='qtJornadaSemanal']"
    QT_JORNADA_MENSAL = "input[id$='qtJornadaMensal']"

    # Intervalos
    INTERVALO_INTRA_JORNADA_SUP_SEIS = "input[id$='intervalorIntraJornadaSupSeis']"  # checkbox
    VALOR_INTERVALO_SUP_SEIS = "input[id$='valorIntervalorIntraJornadaSupSeis']"
    INTERVALO_INTRA_JORNADA_INF_SEIS = "input[id$='intervalorIntraJornadaInfSeis']"  # checkbox
    VALOR_INTERVALO_INF_SEIS = "input[id$='valorIntervalorIntraJornadaInfSeis']"

    # Configuracoes
    CONSIDERAR_FERIADO = "input[id$='considerarFeriado']"  # checkbox
    EXTRA_DESCANSO_SEPARADO = "input[id$='extraDescansoSeparado']"  # checkbox

    # Horas noturnas
    APURAR_HORAS_NOTURNAS = "input[id$='apurarHorasNoturnas']"  # checkbox
    INICIO_HORARIO_NOTURNO = "input[id$='inicioHorarioNoturno']"
    FIM_HORARIO_NOTURNO = "input[id$='fimHorarioNoturno']"
    REDUCAO_FICTA = "input[id$='reducaoFicta']"  # checkbox
    HORARIO_PRORROGADO = "input[id$='horarioProrrogado']"  # checkbox

    # Horarios de entrada/saida por dia
    # Formato: entrada{Dia}, saida{Dia} (ex: entradaSegunda, saidaSegunda)
    ENTRADA_PREFIX = "input[id$='entrada{dia}']"  # substituir {dia} por Segunda, Terca, etc.
    SAIDA_PREFIX = "input[id$='saida{dia}']"

    # Competencias
    COMPETENCIA_INICIAL = "[id*='competenciaInicial']"
    COMPETENCIA_FINAL = "[id*='competenciaFinal']"

    # Botoes
    INCLUIR = "input[id$='incluir']"
    FECHAR = "input[id$='fechar']"
    SALVAR = "input[id$='salvar']"


# ============================================================================
# Verbas — Listagem (verba/verba-calculo.jsf)
# ============================================================================

class VerbaListagem:
    """Campos da listagem de verbas"""
    JSF = "verba/verba-calculo.jsf"

    # Filtro
    FILTRO_NOME = "[id$='filtroNome'], [name*='filtroNome']"

    # Botoes de acesso
    BTN_EXPRESSO = "input[id*='btnExpresso']"
    BTN_MANUAL = "input[value='Manual'], input[value='manual']"
    BTN_NOVO = "[id$='incluir'], [id$='novo']"

    # Tabela de verbas
    TABELA = "table[id*='listagem'], table.list-check, .rich-table"
    LINHAS = "tr[id*='listagem'], tr.rich-table-row, tbody tr"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Verbas — Lancamento Expresso (verba/verbas-para-calculo.xhtml)
# ============================================================================

class VerbaExpresso:
    """Campos do Lancamento Expresso"""
    JSF = "verba/verbas-para-calculo.xhtml"

    # A tabela contem ~60 checkboxes com verbas pre-definidas
    # Cada checkbox: input[type="checkbox"][id$=":selecionada"]
    CHECKBOX_SELECIONADA = 'input[type="checkbox"][id$=":selecionada"]'

    # Container da tabela
    TABELA = '[id*="listagem"], table.list-check, .rich-table, .panelGrid, form'

    # Nome da verba na tabela (texto da celula <td> pai do checkbox)
    # NAO existe elemento [id*=":nome"] — o nome e o texto da celula

    SALVAR = "[id$='salvar'], [id$='btnSalvarExpresso']"


# ============================================================================
# Verbas — Manual (verba-calculo.jsf + formulario)
# ============================================================================

class VerbaManual:
    """Campos do formulario de verba manual"""
    JSF = "verba/verba-calculo.jsf"

    # Formulario (aparece apos clicar "Manual" ou "Incluir")
    DESCRICAO = "[id$=':descricao'], [id$='descricaoVerba'], [id$='nomeVerba']"
    CARACTERISTICA = "[id$='caracteristica']"  # select
    OCORRENCIA = "[id$='ocorrencia']"  # select
    BASE_CALCULO = "[id$='baseDeCalculo']"  # select (2 etapas: selecionar + confirmar)

    # Tipo de valor e valor
    TIPO_VALOR = "[id$='tipoValor']"  # radio CALCULADO/INFORMADO
    TIPO_DE_VERBA = "input[id$='tipoDeVerba:1']"  # radio direto (verba ao reclamante)
    VALOR = "[id$='valor']"

    # Incidencias
    FGTS = "[id$='fgts'], [id*='fgts']"  # checkbox
    CONTRIBUICAO_SOCIAL = "[id$='contribuicaoSocial'], [id*='inss']"  # checkbox
    IMPOSTO_RENDA = "[id$='impostoDeRenda'], [id*='irpf']"  # checkbox

    # Assunto CNJ (obrigatorio)
    ASSUNTOS_CNJ = 'input[id$="assuntosCnj"]:not([id*="modalCNJ"]):not([type="hidden"])'
    CODIGO_ASSUNTOS_CNJ = '[id$="codigoAssuntosCnj"]'

    # Modal CNJ
    MODAL_CNJ_INPUT = '[id*="modalCNJ"] input[type="text"], [id*="modalAssunto"] input[type="text"]'
    MODAL_CNJ_TREE = '[id*="modalCNJ"] tr:has-text("2581"), [id*="modalCNJ"] .rf-trn:has-text("2581")'
    MODAL_CNJ_SELECIONAR = '[id*="modalCNJ"] input[value="Selecionar"], [id*="modalCNJ"] [id$="btnSelecionarCNJ"]'
    MODAL_CNJ_FECHAR = '[id*="modalCNJ"] [id*="close"], [id*="modalCNJ"] input[value*="Fechar"]'

    # Popup sugestao CNJ
    POPUP_SUGESTAO = '.rf-su-popup:visible, .rich-sb-ext-decor:visible, [id*="assuntosCnj"][id*="suggest"]:visible'
    LUPA_CNJ = ('a[id*="assuntosCnj"][id*="btn"], img[id*="assuntosCnj"], '
                'input[id*="btnAssunto"], [id$="btnBuscarAssuntoCnj"]')

    SALVAR = "[id$='salvar']"
    CANCELAR = "[id$='cancelar']"


# ============================================================================
# Verbas — Parametros da Verba (verba-parametro.jsf)
# ============================================================================

class VerbaParametro:
    """Campos da pagina de parametros de uma verba"""
    JSF = "verba/verba-parametro.jsf"

    # Links de acao na listagem de verbas
    LINK_PARAMETRO = ('a[id*="parametro"], a[id*="alterar"], a[id*="editar"], '
                      'input[id*="parametro"], input[id*="alterar"]')
    LINK_ACAO = 'a[id*="acao"], input[id*="acao"]'

    # Reflexos (checkboxes na tabela de reflexos)
    CHECKBOX_REFLEXO = ('input[type="checkbox"][id*="listaReflexo"], '
                        'input[type="checkbox"][id*="reflexo"], '
                        'input[type="checkbox"][id*="Reflexo"], '
                        'input[type="checkbox"][id*="ativo"]')


# ============================================================================
# Verbas — Ocorrencias (verba-ocorrencia.jsf)
# ============================================================================

class VerbaOcorrencia:
    """Campos de ocorrencias de uma verba"""
    JSF = "verba/verba-ocorrencia.jsf"

    CMD_PARAMETROS_OCORRENCIAS = "[id$='cmdParametrosOcorrencias'], [id$='parametrosOcorrencias']"
    CONFIRMAR = "[id$='confirmar'], input[value='Confirmar']"


# ============================================================================
# FGTS (fgts/fgts.jsf)
# ============================================================================

class FGTS:
    """Campos da pagina FGTS"""
    JSF = "fgts/fgts.jsf"

    # Destino: PAGAR ou DEPOSITAR
    TIPO_DE_VERBA = "[id$='tipoDeVerba']"  # radio
    # Compor principal: SIM / NAO
    COMPOR_PRINCIPAL = "[id$='comporPrincipal']"  # radio
    # Aliquota: OITO_POR_CENTO / DOIS_POR_CENTO
    ALIQUOTA = "[id$='aliquota']"  # radio

    # Incidencia do FGTS (select)
    INCIDENCIA_DO_FGTS = "select[id$='incidenciaDoFgts']"

    # Multa rescisoria
    MULTA = "input[type='checkbox'][id$='multa']"  # checkbox master (ativa campos dependentes)
    TIPO_DO_VALOR_DA_MULTA = "[id$='tipoDoValorDaMulta']"  # radio CALCULADA/INFORMADA
    MULTA_DO_FGTS = "[id$='multaDoFgts']"  # radio VINTE_POR_CENTO / QUARENTA_POR_CENTO
    MULTA_DO_ARTIGO_467 = "input[type='checkbox'][id$='multaDoArtigo467']"  # checkbox
    MULTA_10 = "input[type='checkbox'][id$='multa10']"  # checkbox

    # Excluir aviso da base da multa
    EXCLUIR_AVISO_DA_MULTA = "input[type='checkbox'][id$='excluirAvisoDaMulta']"

    # Saldos depositados
    DEDUZIR_DO_FGTS = "input[type='checkbox'][id$='deduzirDoFGTS']"
    COMPETENCIA = "[id*='competenciaInputDate'], [id$='competencia']"
    VALOR = "[id$='valor']"
    BTN_ADICIONAR_SALDO = "[id*='btnAdicionarSaldo'], [id*='adicionarSaldo']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Contribuicao Social / INSS (inss/inss.jsf)
# ============================================================================

class ContribuicaoSocial:
    """Campos de Contribuicao Social (INSS)"""
    JSF = "inss/inss.jsf"

    # Checkboxes principais
    APURAR_SEGURADO_SALARIOS_DEVIDOS = (
        "input[type='checkbox'][id$='apurarSeguradoSaláriosDevidos'], "
        "input[type='checkbox'][id$='apurarSeguradoSalariosDevidos']"
    )
    COBRAR_DO_RECLAMANTE = "input[type='checkbox'][id$='cobrarDoReclamante']"
    COM_CORRECAO_TRABALHISTA = "input[type='checkbox'][id$='comCorrecaoTrabalhista']"
    APURAR_SOBRE_SALARIOS_PAGOS = (
        "input[type='checkbox'][id$='apurarSobreSaláriosPagos'], "
        "input[type='checkbox'][id$='apurarSobreSalariosPagos']"
    )
    LEI_11941 = "input[type='checkbox'][id$='lei11941']"

    # Parametros das Ocorrencias
    CMD_PARAMETROS_OCORRENCIAS = "[id$='cmdParametrosOcorrencias'], [id$='parametrosOcorrencias']"
    ALIQUOTA_SEGURADO = "[id$='aliquotaSegurado'], [id$='tipoAliquotaSegurado']"  # radio
    ALIQUOTA_SEGURADO_FIXA = "[id$='aliquotaSeguradoFixa']"
    ALIQUOTA_EMPREGADOR = "[id$='tipoAliquotaEmpregador']"  # radio
    CONFIRMAR = "[id$='confirmar'], input[value='Confirmar']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Imposto de Renda / IRPF (irpf/irpf.jsf)
# ============================================================================

class ImpostoRenda:
    """Campos de Imposto de Renda"""
    JSF = "irpf/irpf.jsf"

    # Regime de tributacao
    TRIBUTACAO_EXCLUSIVA = "input[type='checkbox'][id$='tributacaoExclusiva'], input[type='checkbox'][id$='tributacaoExclusivaFonte']"
    REGIME_DE_CAIXA = "input[type='checkbox'][id$='regimeDeCaixa'], input[type='checkbox'][id$='regimeCaixa']"
    TRIBUTACAO_EM_SEPARADO = "input[type='checkbox'][id$='tributacaoEmSeparado']"

    # Deducoes
    DEDUCAO_INSS = "input[type='checkbox'][id$='deducaoInss'], input[type='checkbox'][id$='descontarInss']"
    DEDUCAO_HONORARIOS = "input[type='checkbox'][id$='deducaoHonorariosReclamante'], input[type='checkbox'][id$='descontarHonorarios']"
    DEDUCAO_PENSAO = "input[type='checkbox'][id$='deducaoPensaoAlimenticia'], input[type='checkbox'][id$='pensaoAlimenticia']"
    VALOR_PENSAO = "[id$='valorPensao'], [id$='valorDaPensao']"

    # Campos numericos
    NUMERO_DEPENDENTES = "[id$='numeroDeDependentes'], [id$='dependentes']"
    MESES_TRIBUTAVEIS = "[id$='mesesTributaveis']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Honorarios (honorarios/honorarios.jsf)
# ============================================================================

class Honorarios:
    """Campos de Honorarios"""
    JSF = "honorarios/honorarios.jsf"

    # Formulario (apos clicar Novo)
    TIPO_DE_DEVEDOR = "select[id$='tipoDeDevedor'], select[id$='devedor'], select[id$='parteDevedora']"
    TIPO_HONORARIO = "select[id$='tipoHonorario'], select[id$='tipo']"
    DESCRICAO = "[id$='descricao'], [id$='descricaoHonorario']"
    TIPO_VALOR = "[id$='tipoValor']"  # radio CALCULADO/INFORMADO
    BASE_PARA_APURACAO = "select[id$='baseParaApuracao']"
    PERCENTUAL = "[id$='percentualHonorarios'], [id$='percentual']"
    VALOR_INFORMADO = "[id$='valorInformado'], [id$='valorFixo']"
    APURAR_IR = "input[type='checkbox'][id$='apurarIr'], input[type='checkbox'][id$='tributarIR']"

    # Periciais
    HONORARIOS_PERICIAIS = "[id$='honorariosPericiais'], [id$='valorPericiais']"

    INCLUIR = "[id$='incluir']"
    SALVAR = "[id$='salvar']"


# ============================================================================
# Correcao, Juros e Multa (correcao-juros.jsf / atualizacao.jsf)
# ============================================================================

class CorrecaoJurosMulta:
    """Campos de Correcao Monetaria, Juros de Mora e Multa"""
    JSF = "correcao-juros.jsf"

    # Indice de correcao
    INDICE_CORRECAO = "select[id$='indiceCorrecao'], select[id$='indiceTrabalhista']"

    # Juros
    TAXA_JUROS = "select[id$='taxaJuros'], select[id$='juros']"
    DATA_INICIO_TAXA_LEGAL = "[id$='dataInicioTaxaLegal'], [id$='dataMarcoTaxaLegal']"
    BASE_DE_JUROS_DAS_VERBAS = "select[id$='baseDeJurosDasVerbas']"

    # Multa art. 523 CPC
    APLICAR_MULTA_523 = "input[type='checkbox'][id$='aplicarMulta523']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Custas Judiciais (custas.jsf)
# ============================================================================

class CustasJudiciais:
    """Campos de Custas Judiciais"""
    JSF = "custas.jsf"

    BASE_CUSTAS = "select[id$='baseCustas']"
    CUSTAS_RECLAMADO_CONHECIMENTO = "[id$='custasReclamadoConhecimento']"  # radio

    SALVAR = "[id$='salvar']"


# ============================================================================
# Liquidacao (liquidacao/liquidacao.xhtml)
# ============================================================================

class Liquidacao:
    """Campos e botoes da pagina de Liquidacao"""
    JSF = "liquidacao/liquidacao.xhtml"

    DATA_LIQUIDACAO = "input[id*='dataLiquidacao'], input[id*='dataDeLiquidacao']"
    BTN_LIQUIDAR = ("input[id$='liquidar'][value='Liquidar'], "
                    "input[value='Liquidar'], "
                    "[id$='incluir'][value='Liquidar']")
    LISTA_CALCULOS_RECENTES = ("select[class*='listaCalculosRecentes'], "
                               "select[name*='listaCalculosRecentes']")

    # Mensagens pos-liquidacao
    MENSAGEM_SUCESSO = ".rf-msgs-sum, .rf-msgs-det, .rich-messages"


# ============================================================================
# Exportacao (exportacao/exportacao.xhtml)
# ============================================================================

class Exportacao:
    """Campos e botoes da pagina de Exportacao"""
    JSF = "exportacao/exportacao.xhtml"

    BTN_EXPORTAR = ("[id$='exportar'], input[value='Exportar'], "
                    "input[id*='btnExportar'], button:has-text('Exportar')")
    LINK_EXPORTAR_MENU = "a[id*='menuExport'], a[id*='menuExporta']"


# ============================================================================
# Sidebar Menu — links de navegacao lateral
# ============================================================================

class SidebarMenu:
    """Seletores do menu lateral do PJE-Calc"""

    DADOS_DO_CALCULO = "a[id*='menuCalculo']"
    HISTORICO_SALARIAL = "a[id*='menuHistoricoSalarial']"
    VERBAS = "a[id*='menuVerbas']"
    FGTS = "a[id*='menuFGTS']"
    HONORARIOS = "a[id*='menuHonorarios']"
    LIQUIDAR = "a[id*='menuLiquidar']"
    FALTAS = "a[id*='menuFaltas']"
    FERIAS = "a[id*='menuFerias']"
    NOVO = "a[id*='menuNovo']"
    OPERACOES = "a[id*='menuOperacoes']"
    IMPRIMIR = "a[id*='menuImprimir']"
    CONTRIBUICAO_SOCIAL = "a[id*='menuContribuicaoSocial']"
    IMPOSTO_RENDA = "a[id*='menuImpostoRenda']"
    MULTAS = "a[id*='menuMultas']"
    CARTAO_DE_PONTO = "a[id*='menuCartao'], a[id*='CartaoPonto'], a[id*='cartaoDePonto']"
    SALARIO_FAMILIA = "a[id*='menuSalarioFamilia']"
    SEGURO_DESEMPREGO = "a[id*='menuSeguroDesemprego']"
    PENSAO_ALIMENTICIA = "a[id*='menuPensaoAlimenticia']"
    PREVIDENCIA_PRIVADA = "a[id*='menuPrevidenciaPrivada']"
    EXPORTAR = "a[id*='menuExport']"


# ============================================================================
# Mensagens JSF / RichFaces
# ============================================================================

class Mensagens:
    """Seletores de mensagens de sucesso/erro do JSF/RichFaces"""

    SUCESSO = ".rf-msgs-sum, .rich-messages-label"
    ERRO = ".rf-msgs-sum-err, .rf-msg-err, .rf-msgs-det"
    ERRO_CAMPO = ".rf-inpt-fld-err, input.error, select.error"
    INFO = ".rf-msgs-inf, .rich-messages-info"
    # Detalhes de erro (tooltips etc)
    TOOLTIP_ERRO = '.rf-tt-cntr:not([style*="display: none"])'


# ============================================================================
# Botoes comuns reutilizados em varias paginas
# ============================================================================

class Comum:
    """Seletores comuns reutilizados em varias paginas"""

    SALVAR = "[id$='salvar']"
    NOVO = "[id$='novo'], [id$='novoBt'], [id$='novoBtn'], input[value='Novo']"
    INCLUIR = "[id$='incluir']"
    CANCELAR = "[id$='cancelar']"
    FECHAR = "[id$='fechar']"
    CONFIRMAR = "[id$='confirmar'], input[value='Confirmar']"
    EXCLUIR = "[id$='excluir']"

    # Autocomplete / suggestion box
    SUGGESTION_BOX = ".rf-au-lst, .rf-su-lst, [id*='suggestionBox']"

    # Pagina inicial
    LINK_PAGINA_INICIAL = "a:has-text('Tela Inicial'), a:has-text('Página Inicial')"

    # Overlay do agente
    OVERLAY_AGENTE = "#pjecalc-agente-overlay"

    # Login (se exibido)
    CAMPO_USUARIO = ("input[name*='usuario'], input[id*='usuario'], "
                     "input[type='text'][name*='j_'], input[name*='j_username']")


# ============================================================================
# Mapa de todas as classes para lookup programatico
# ============================================================================

TODAS_PAGINAS = {
    "dados_processo": DadosProcesso,
    "parametros_calculo": ParametrosCalculo,
    "parametros_gerais": ParametrosGerais,
    "historico_salarial": HistoricoSalarial,
    "ferias": Ferias,
    "faltas": Faltas,
    "cartao_ponto": CartaoPonto,
    "verba_listagem": VerbaListagem,
    "verba_expresso": VerbaExpresso,
    "verba_manual": VerbaManual,
    "verba_parametro": VerbaParametro,
    "verba_ocorrencia": VerbaOcorrencia,
    "fgts": FGTS,
    "contribuicao_social": ContribuicaoSocial,
    "imposto_renda": ImpostoRenda,
    "honorarios": Honorarios,
    "correcao_juros_multa": CorrecaoJurosMulta,
    "custas_judiciais": CustasJudiciais,
    "liquidacao": Liquidacao,
    "exportacao": Exportacao,
}
