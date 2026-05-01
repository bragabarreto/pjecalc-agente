"""
PJE-Calc DOM Selectors — Constantes validadas por DOM Auditor + inspeção manual.

Validado em 2026-04-09 contra PJE-Calc v2.15.1 via tools/dom_auditor.py:
  - 20 páginas navegadas, 1250 elementos mapeados
  - 28 campos críticos de calculo.jsf: 100% match confirmado
  - 54 checkboxes Expresso confirmados por ID
  - Sidebar: 19 links com li_id confirmados

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

    # Tipo e data de criacao (cabecalho) — DOM confirmado
    TIPO = "[id$='tipo']"
    DATA_DE_CRIACAO = "[id$='dataDeCriacao'], [id$='dataCriacao'], [id$='dataDeAbertura']"
    # REMOVIDO: DATA_CALCULO = "[id*='dataDe'], [id*='dataCria'], [id*='dataCalc']"
    # Seletor muito ambiguo — [id*='dataDe'] casa com dataDemissao, dataDesligamento, etc.
    # Usar DATA_DE_CRIACAO acima (mais especifico) em vez deste.

    # Numero do processo (6 campos separados) — todos DOM confirmados
    NUMERO = "[id$='numero']"
    DIGITO = "[id$='digito']"
    ANO = "[id$='ano']"
    JUSTICA = "[id$='justica']"
    REGIAO = "[id$='regiao']"
    VARA = "[id$='vara']"

    # Valor da causa e autuacao — DOM confirmados
    VALOR_DA_CAUSA = "[id$='valorDaCausa']"
    AUTUADO_EM = "[id$='autuadoEm']"

    # Partes — DOM confirmados
    RECLAMANTE_NOME = "[id$='reclamanteNome']"
    RECLAMADO_NOME = "[id$='reclamadoNome']"

    # Documentos fiscais — radio CPF/CNPJ/CEI (DOM: radio_value=CPF,CNPJ,CEI)
    RECLAMANTE_DOC_NUMERO = "[id$='reclamanteNumeroDocumentoFiscal']"
    RECLAMANTE_DOC_PREVIDENCIARIO = "[id$='reclamanteNumeroDocumentoPrevidenciario']"
    RECLAMADO_DOC_NUMERO = "[id$='reclamadoNumeroDocumentoFiscal']"

    # Advogados — DOM confirmados
    NOME_ADVOGADO_RECLAMANTE = "[id$='nomeAdvogadoReclamante']"
    OAB_ADVOGADO_RECLAMANTE = "[id$='numeroOABAdvogadoReclamante']"
    DOC_ADVOGADO_RECLAMANTE = "[id$='numeroDocumentoAdvogadoReclamante']"
    NOME_ADVOGADO_RECLAMADO = "[id$='nomeAdvogadoReclamado']"
    OAB_ADVOGADO_RECLAMADO = "[id$='numeroOABAdvogadoReclamado']"
    DOC_ADVOGADO_RECLAMADO = "[id$='numeroDocumentoAdvogadoReclamado']"

    # Botoes
    SALVAR = "[id$='salvar']"


# ============================================================================
# Parametros do Calculo (calculo.jsf — aba tabParametrosCalculo)
# ============================================================================

class ParametrosCalculo:
    """Campos da aba 'Parametros do Calculo' em calculo.jsf"""
    JSF = "calculo/calculo.jsf"
    ABA = "tabParametrosCalculo"

    # Localizacao — DOM confirmados
    ESTADO = "select[id$='estado']"  # select: AC, AL, AP, AM, BA, CE(5), ...
    MUNICIPIO = "select[id$='municipio']"  # carregado via AJAX apos selecao do estado

    # Datas do contrato — DOM confirmados (suffix=xxxInputDate)
    DATA_ADMISSAO = "[id$='dataAdmissaoInputDate']"
    DATA_DEMISSAO = "[id$='dataDemissaoInputDate']"
    DATA_AJUIZAMENTO = "[id$='dataAjuizamentoInputDate']"
    # Aviso previo — DOM confirmados
    AVISO_PREVIO = "select[id$='apuracaoPrazoDoAvisoPrevio']"  # Não apurar/Calculado/Informado
    AVISO_PREVIO_DIAS = "[id$='diasAvisoPrevio']"

    # Jornada — DOM confirmados
    CARGA_HORARIA_PADRAO = "[id$='valorCargaHorariaPadrao']"  # "Padrão *:"
    CARGA_HORARIA_EXCECAO = "[id$='valorCargaHoraria']"  # "Exceção"
    REGIME_TRABALHO = "select[id$='tipoDaBaseTabelada']"  # Intermitente/Integral/Parcial

    # Remuneracao — DOM confirmados
    MAIOR_REMUNERACAO = "[id$='valorMaiorRemuneracao']"
    ULTIMA_REMUNERACAO = "[id$='valorUltimaRemuneracao']"

    # Data inicio calculo — DOM confirmados
    DATA_INICIO_CALCULO = "[id$='dataInicioCalculoInputDate']"
    DATA_INICIO_EXCECAO = "[id$='dataInicioExcecaoInputDate']"

    # Checkboxes gerais — DOM confirmados
    PRESCRICAO_QUINQUENAL = "input[type='checkbox'][id$='prescricaoQuinquenal']"
    PRESCRICAO_FGTS = "input[type='checkbox'][id$='prescricaoFgts']"
    PROJETAR_AVISO = "input[type='checkbox'][id$='projetaAvisoIndenizado']"  # default=checked
    LIMITAR_AVOS = "input[type='checkbox'][id$='limitarAvos']"
    ZERAR_NEGATIVO = "input[type='checkbox'][id$='zeraValorNegativo']"
    CONSIDERAR_FERIADO_ESTADUAL = "input[type='checkbox'][id$='consideraFeriadoEstadual']"  # default=checked
    CONSIDERAR_FERIADO_MUNICIPAL = "input[type='checkbox'][id$='consideraFeriadoMunicipal']"  # default=checked
    SABADO_DIA_UTIL = "input[type='checkbox'][id$='sabadoDiaUtil']"  # default=checked
    INVERTER_PARTES = "input[type='checkbox'][id$='inverterPartes']"

    # Ponto facultativo — DOM confirmado
    PONTO_FACULTATIVO = "select[id$='pontoFacultativo']"  # Sexta-feira Santa/Corpus Christi/Carnaval

    # Comentarios
    COMENTARIOS = "textarea[id$='comentarios']"

    # Data fim calculo — DOM confirmado
    DATA_FIM_CALCULO = "[id$='dataTerminoCalculoInputDate']"

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
    TIPO = "input[type='radio'][id$='tipo']"  # radio: FIXA / VARIAVEL
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
    """Campos do Cartao de Ponto — IDs confirmados via DOM TRT7 2.15.1 (calc 262928)"""
    JSF = "../cartaodeponto/apuracao-cartaodeponto.jsf"  # path relativo a /pages/calculo/

    # Tipo de apuracao (radio com 7 opções :0 a :6 confirmadas)
    # 0=NAO_APURAR, 1=DIARIA, 2=MAIS_FAVORAVEL (default), 3=SUMULA_85,
    # 4=PRIMEIRAS_SEPARADO, 5=SEMANAL, 6=MENSAL
    TIPO_APURACAO_HORAS_EXTRAS = "[id$='tipoApuracaoHorasExtras']"
    TIPO_ESCALA = "select[id$='tipoEscala']"  # legado (não confirmado em 2.15.1)

    # Jornada por dia da semana (HH:MM)
    JORNADA_SEGUNDA = "input[id$='valorJornadaSegunda']"
    JORNADA_TERCA = "input[id$='valorJornadaTerca']"
    JORNADA_QUARTA = "input[id$='valorJornadaQuarta']"
    JORNADA_QUINTA = "input[id$='valorJornadaQuinta']"
    JORNADA_SEXTA = "input[id$='valorJornadaSexta']"
    # Nota: sáb/dom usam "Diaria" no ID, diferente de seg-sex que usam "Jornada"
    JORNADA_SABADO = "input[id$='valorJornadaDiariaSabado'], input[id$='valorJornadaSabado']"
    JORNADA_DOMINGO = "input[id$='valorJornadaDiariaDom'], input[id$='valorJornadaDomingo']"

    # Totais
    QT_JORNADA_SEMANAL = "input[id$='qtJornadaSemanal']"
    QT_JORNADA_MENSAL = "input[id$='qtJornadaMensal']"

    # Intervalos intrajornada — ⚠️ TYPOS confirmados no DOM PJE-Calc:
    #   "intervalor" (com R extra após "intervalo") em vez de "intervalo"
    # O código deve usar o ID exatamente como aparece no servidor.
    # Confirmado via DOM TRT7 v2.15.1 (calc 262928, 2026-05-01)
    INTERVALO_INTRA_JORNADA_SUP_SEIS = "input[id$='intervalorIntraJornadaSupSeis']"  # checkbox
    VALOR_INTERVALO_SUP_SEIS = "input[id$='valorIntervalorIntraJornadaSupSeis']"
    # Variantes Sup4-6 (jornadas entre 4h e 6h) — sem typo
    INTERVALO_INTRA_JORNADA_SUP_QUATRO_SEIS = "input[id$='intervaloIntraJornadaSupQuatroSeis']"
    VALOR_INTERVALO_SUP_QUATRO_SEIS = "input[id$='valorIntervaloIntraJornadaSupQuatroSeis']"
    # Tolerância intervalo intrajornada
    TOLERANCIA_INTERVALO_INTRA = "input[id$='toleranciaIntervaloIntraJornadaSupSeis']"
    # Apuração supressão / excesso intervalo intrajornada
    APURAR_SUPRESSAO_INTRA_INTEGRAL = "input[id$='apurarSupressaoIntervaloIntraIntegral']"
    APURAR_SUPRESSAO_INTRA_REFORMA = "input[id$='apurarSupressaoIntervaloIntraReforma']"
    APURAR_EXCESSO_INTRA = "input[id$='apurarExcessoIntervaloIntra']"
    VALOR_INTERVALO_INTRA_MAXIMO = "input[id$='valorIntervaloIntrajornadaMaximo']"
    APURAR_APENAS_EXCESSO_ACIMA_JORNADA = "input[id$='apurarApenasExcessoAcimaJornada']"
    CONSIDERAR_FRACIONAMENTO_INTRA = "input[id$='considerarFracionamentoIntra']"

    # Intervalo interjornadas
    DESCANSO_ENTRE_JORNADAS = "input[id$='descansoEntreJornadas']"  # checkbox
    VALOR_DESCANSO_ENTRE_JORNADAS = "input[id$='valorDescansoEntreJornadas']"
    VALOR_DESCANSO_ENTRE_SEMANAS = "input[id$='valorDescansoEntreSemanas']"

    # Súmulas / Art. 253
    APURAR_SUPRESSAO_INTERVALO_384 = "input[id$='apurarSupressaoIntervalo384']"
    APURAR_SUPRESSAO_INTERVALO_72 = "input[id$='apurarSupressaoIntervalo72']"
    APURAR_SUPRESSAO_INTERVALO_ART253 = "input[id$='apurarSupressaoIntervaloArt253']"
    VALOR_TRABALHO_ART253 = "input[id$='valorTrabalhoArt253']"
    VALOR_DESCANSO_ART253 = "input[id$='valorDescansoArt253']"

    # Configuracoes / Feriados / Domingos
    CONSIDERAR_FERIADO = "input[id$='considerarFeriado']"  # checkbox (default true)
    EXTRA_FERIADO_SEPARADO = "input[id$='extraFeriadoSeparado']"  # checkbox
    EXTRA_DESCANSO_SEPARADO = "input[id$='extraDescansoSeparado']"  # checkbox
    EXTRA_SAB_DOM_SEPARADO = "input[id$='extraSabadoDomingoSeparado']"  # checkbox
    APURAR_FERIADOS_TRABALHADOS = "input[id$='apurarFeriadosTrabalhados']"
    APURAR_DOMINGOS_TRABALHADOS = "input[id$='apurarDomingosTrabalhados']"
    APURAR_SABADOS_DOMINGOS_TRABALHADOS = "input[id$='apurarSabadosDomingosTrabalhados']"
    JORNADA_DIARIA_FERIADO_TRABALHADO = "input[id$='jornadaDiariaFeriadoTrabalhado']"
    JORNADA_DIARIA_FERIADO_NAO_TRABALHADO = "input[id$='jornadaDiariaFeriadoNaoTrabalhado']"

    # Tolerância
    TOLERANCIA = "input[id$='tolerancia']"  # checkbox principal
    TOLERANCIA_POR_TURNO = "input[id$='toleranciaPorTurno']"
    TOLERANCIA_POR_DIA = "input[id$='toleranciaPorDia']"

    # Quantidades específicas
    QT_SUMULA_TST = "input[id$='qtsumulatst']"
    QT_HORA_SEPARADO = "input[id$='qthoraseparado']"

    # Horas noturnas — ⚠️ TYPO confirmado: "Apuracaro" em vez de "Apuracao"
    HORARIO_NOTURNO_APURACAO = "[id$='horarioNoturnoApuracaroCartao']"  # radio :0/:1/:2
    APURAR_HORAS_NOTURNAS = "input[id$='apurarHorasNoturnas']"  # checkbox
    APURAR_HORAS_EXTRAS_NOTURNAS = "input[id$='apurarHorasExtrasNoturnas']"
    REDUCAO_FICTA = "input[id$='considerarReducaoFictaDaHoraNoturna']"  # corrigido
    HORARIO_PRORROGADO = "input[id$='horarioProrrogadoSumula60']"  # corrigido (era 'horarioProrrogado')
    FORCAR_PRORROGACAO = "input[id$='forcarProrrogacao']"

    # Preenchimento
    PREENCHIMENTO_JORNADAS = "[id$='preenchimentoJornadasCartao']"  # radio :0/:1/:2

    # Horarios de entrada/saida por dia (legado/Cidadão; em TRT7 institucional não confirmado)
    # Formato: entrada{Dia}, saida{Dia} (ex: entradaSegunda, saidaSegunda)
    ENTRADA_PREFIX = "input[id$='entrada{dia}']"  # substituir {dia} por Segunda, Terca, etc.
    SAIDA_PREFIX = "input[id$='saida{dia}']"

    # Competencias
    COMPETENCIA_INICIAL = "[id$='competenciaInicialInputDate']"
    COMPETENCIA_FINAL = "[id$='competenciaFinalInputDate']"

    # Botoes
    INCLUIR = "input[id$='incluir']"
    FECHAR = "input[id$='fechar']"
    SALVAR = "input[id$='salvar']"


# ============================================================================
# Verbas — Listagem (verba/verba-calculo.jsf)
# ============================================================================

class VerbaListagem:
    """Campos da listagem de verbas — DOM confirmados"""
    JSF = "verba/verba-calculo.jsf"

    # Botoes de acesso — DOM: formulario:incluir, formulario:lancamentoExpresso
    BTN_MANUAL = "input[id$='incluir']"  # DOM: texto="Manual"
    BTN_EXPRESSO = "input[id$='lancamentoExpresso']"  # DOM: texto="Expresso"
    BTN_REGERAR = "input[id$='regerarOcorrencias']"  # DOM: texto="Regerar"

    # Assunto CNJ — DOM: dentro de modal formularioModalCNJ
    BTN_SELECIONAR_CNJ = "input[id$='btnSelecionarCNJ']"  # DOM: texto="Selecionar"
    ASSUNTO_CNJ_INPUT = "input[id$='assuntosCnjCNJ']"  # DOM: label="Assunto CNJ *"

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
    """Campos da pagina de parametros de uma verba.

    Confirmados via Chrome MCP no calc 262818 (TRT7 Inst 2.15.1, 2026-05-01).
    Form aparece inline em verba/verba-calculo.jsf?conversationId=N
    ao clicar no link suffix `j_id558` (tooltip 'Parâmetros da Verba')
    da listagem `formulario:listagem:N:j_id558`.
    """
    JSF = "verba/verba-calculo.jsf"

    # Links na listagem de verbas (suffixes confirmados)
    LINK_PARAMETROS = "a[id$='j_id558']"  # tooltip 'Parâmetros da Verba'
    LINK_OCORRENCIAS = "a[id$='j_id559']"  # tooltip 'Ocorrências da Verba'
    LINK_EXCLUIR = "a[id$='j_id560']"

    # Radios principais
    TIPO_VARIACAO_PARCELA = "input[type='radio'][name$=':tipoVariacaoDaParcela']"  # FIXA / VARIAVEL
    VALOR = "input[type='radio'][name$=':valor']"  # CALCULADO / INFORMADO
    CARACTERISTICA_VERBA = "input[type='radio'][name$=':caracteristicaVerba']"
    # COMUM / DECIMO_TERCEIRO_SALARIO / AVISO_PREVIO / FERIAS
    OCORRENCIA_PAGTO = "input[type='radio'][name$=':ocorrenciaPagto']"
    # DESLIGAMENTO / DEZEMBRO / MENSAL / PERIODO_AQUISITIVO
    OCORRENCIA_AJUIZAMENTO = "input[type='radio'][name$=':ocorrenciaAjuizamento']"
    # OCORRENCIAS_VENCIDAS_E_VINCENDAS / OCORRENCIAS_VENCIDAS
    TIPO_DE_VERBA = "input[type='radio'][name$=':tipoDeVerba']"  # PRINCIPAL / REFLEXO
    GERAR_PRINCIPAL = "input[type='radio'][name$=':gerarPrincipal']"  # DEVIDO / DIFERENCA
    GERAR_REFLEXO = "input[type='radio'][name$=':geraReflexo']"  # DEVIDO / DIFERENCA
    COMPOR_PRINCIPAL = "input[type='radio'][name$=':comporPrincipal']"  # SIM / NAO
    TIPO_DE_DIVISOR = "input[type='radio'][name$=':tipoDeDivisor']"
    # OUTRO_VALOR / CARGA_HORARIA / DIAS_UTEIS / IMPORTADA_DO_CARTAO
    TIPO_DA_QUANTIDADE = "input[type='radio'][name$=':tipoDaQuantidade']"
    # INFORMADA / IMPORTADA_DO_CALENDARIO / IMPORTADA_DO_CARTAO (e AVOS para 13º/Férias)
    TIPO_DO_VALOR_PAGO = "input[type='radio'][name$=':tipoDoValorPago']"
    # INFORMADO / CALCULADO

    # Selects de base de cálculo
    TIPO_DA_BASE_TABELADA = "select[id$=':tipoDaBaseTabelada']"
    # NoSelection / MAIOR_REMUNERACAO / HISTORICO_SALARIAL / SALARIO_DA_CATEGORIA
    # / SALARIO_MINIMO / VALE_TRANSPORTE
    BASE_HISTORICOS = "select[id$=':baseHistoricos']"
    # NoSelection / 0=ADICIONAL DE INSALUBRIDADE PAGO / 1=SALÁRIO BASE / 2=ÚLTIMA REMUNERAÇÃO
    # OBRIGATÓRIO selecionar quando tipoDaBaseTabelada=HISTORICO_SALARIAL,
    # senão Liquidar emite erro 'Falta selecionar pelo menos um Histórico Salarial'.
    BASE_VERBA_DE_CALCULO = "select[id$=':baseVerbaDeCalculo']"
    # NoSelection / N=verbas existentes (para somar à base de cálculo)
    INTEGRALIZAR_BASE = "select[id$=':integralizarBase']"  # SIM / NAO
    PROPORCIONALIZA_HISTORICO = "select[id$=':proporcionalizaHistorico']"  # SIM / NAO

    # Inputs texto
    OUTRO_VALOR_DIVISOR = "input[id$=':outroValorDoDivisor']"
    OUTRO_VALOR_MULTIPLICADOR = "input[id$=':outroValorDoMultiplicador']"
    VALOR_INFORMADO_QUANTIDADE = "input[id$=':valorInformadoDaQuantidade']"
    VALOR_INFORMADO_PAGO = "input[id$=':valorInformadoPago']"

    # Incidências (checkboxes)
    FGTS = "input[type='checkbox'][id$=':fgts']"
    INSS = "input[type='checkbox'][id$=':inss']"
    IRPF = "input[type='checkbox'][id$=':irpf']"
    PREVIDENCIA_PRIVADA = "input[type='checkbox'][id$=':previdenciaPrivada']"
    PENSAO_ALIMENTICIA = "input[type='checkbox'][id$=':pensaoAlimenticia']"
    ZERA_VALOR_NEGATIVO = "input[type='checkbox'][id$=':zeraValorNegativo']"
    DOBRA_VALOR_DEVIDO = "input[type='checkbox'][id$=':dobraValorDevido']"

    # Exclusões/proporcionalidades
    EXCLUIR_FALTA_JUSTIFICADA = "input[type='checkbox'][id$=':excluirFaltaJustificada']"
    EXCLUIR_FALTA_NAO_JUSTIFICADA = "input[type='checkbox'][id$=':excluirFaltaNaoJustificada']"
    EXCLUIR_FERIAS_GOZADAS = "input[type='checkbox'][id$=':excluirFeriasGozadas']"
    APLICAR_PROPORCIONALIDADE_QUANTIDADE = "input[type='checkbox'][id$=':aplicarProporcionalidadeAQuantidade']"
    APLICAR_PROPORCIONALIDADE_BASE = "input[type='checkbox'][id$=':aplicarProporcionalidadeABase']"
    APLICAR_PROPORCIONALIDADE_VALOR_PAGO = "input[type='checkbox'][id$=':aplicarProporcionalidadeValorPago']"

    # Reflexos (checkboxes na tabela de reflexos)
    CHECKBOX_REFLEXO = ('input[type="checkbox"][id*="listaReflexo"], '
                        'input[type="checkbox"][id*="reflexo"], '
                        'input[type="checkbox"][id*="Reflexo"], '
                        'input[type="checkbox"][id*="ativo"]')

    # Botões
    SALVAR = "input[id='formulario:salvar']"
    CANCELAR = "input[id='formulario:cancelar']"


class VerbaOcorrenciaGrade:
    """Grade de Ocorrências da verba (parametrizar-ocorrencia.jsf).

    URL dedicada: /pages/calculo/parametrizar-ocorrencia.jsf?conversationId=N
    Acessada pelo link `formulario:listagem:N:j_id559`.
    """
    JSF = "calculo/parametrizar-ocorrencia.jsf"

    # Coluna por linha N (índice 0+)
    ATIVO = "input[type='checkbox'][id$=':{N}:ativo']"
    DOBRA = "input[type='checkbox'][id$=':{N}:dobra']"
    TERMO_DIV = "input[type='text'][id$=':{N}:termoDiv']"  # divisor
    TERMO_MULT = "input[type='text'][id$=':{N}:termoMult']"  # multiplicador
    TERMO_QUANT = "input[type='text'][id$=':{N}:termoQuant']"  # quantidade (preencher!)
    VALOR_DEVIDO = "input[type='text'][id$=':{N}:valorDevido']"  # calculado pós-salvar
    VALOR_PAGO = "input[type='text'][id$=':{N}:valorPago']"
    SELECIONAR = "input[type='checkbox'][id$=':{N}:selecionar']"

    # Cabeçalho global
    ATIVAR_TODOS = "input[type='checkbox'][id$=':ativarTodos']"

    # Form geral (params globais aplicados a múltiplas linhas selecionadas)
    DATA_INICIAL = "[id$='dataInicialInputDate']"
    DATA_FINAL = "[id$='dataFinalInputDate']"
    DIVISOR_GLOBAL = "[id$='formulario:divisor']"
    MULT_GLOBAL = "[id$='formulario:multiplicador']"
    QUANT_GLOBAL = "[id$='formulario:quantidade']"
    DEVIDO_GLOBAL = "[id$='formulario:devido']"
    PAGO_GLOBAL = "[id$='formulario:pago']"
    DOBRA_GLOBAL = "input[type='checkbox'][id='formulario:dobra']"
    PROP_DEVIDO = "[id$='propDevido']"
    PROP_PAGO = "[id$='propPago']"
    PROP_QUANTIDADE = "[id$='propQuantidade']"
    BTN_RECUPERAR = "input[id$='recuperar']"
    BTN_CANCELAR = "input[id$='cancelar']"
    BTN_SALVAR = "input[id$='salvar']"


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
    JSF = "calculo/fgts.jsf"

    # Destino: PAGAR ou DEPOSITAR
    TIPO_DE_VERBA = "[id$='tipoDeVerba']"  # radio
    # Compor principal: SIM / NAO
    COMPOR_PRINCIPAL = "[id$='comporPrincipal']"  # radio
    # Aliquota: OITO_POR_CENTO / DOIS_POR_CENTO
    ALIQUOTA = "[id$='aliquota']"  # radio

    # Incidencia do FGTS (select)
    INCIDENCIA_DO_FGTS = "select[id$='incidenciaDoFgts']"

    # Multa rescisoria — SELECT com 3 opções (NAO_APURAR / CALCULADA / INFORMADA)
    MULTA = "select[id$='multa']"  # select (ativa campos dependentes conforme seleção)
    MULTA_DO_FGTS = "[id$='multaDoFgts']"  # radio VINTE_POR_CENTO / QUARENTA_POR_CENTO
    MULTA_DO_ARTIGO_467 = "input[type='checkbox'][id$='multaDoArtigo467']"  # checkbox
    MULTA_10 = "input[type='checkbox'][id$='multa10']"  # checkbox

    # Base da Multa (manual seção 13 — DEVIDO, DIFERENCA, SALDO, etc.)
    BASE_DA_MULTA = "select[id$='baseDaMulta'], select[id$='baseMulta']"
    # Excluir aviso da base da multa
    EXCLUIR_AVISO_DA_MULTA = "input[type='checkbox'][id$='excluirAvisoDaMulta']"
    # Pensao Alimenticia sobre FGTS (manual seção 13)
    PENSAO_ALIMENTICIA_FGTS = "input[type='checkbox'][id$='pensaoAlimenticiaFgts'], input[type='checkbox'][id$='pensaoAlimenticia']"

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
    JSF = "calculo/inss.jsf"

    # Checkboxes principais
    APURAR_SEGURADO_SALARIOS_DEVIDOS = "input[type='checkbox'][id$='apurarSeguradoSalariosDevidos']"
    COBRAR_DO_RECLAMANTE = "input[type='checkbox'][id$='cobrarDoReclamante']"
    COM_CORRECAO_TRABALHISTA = "input[type='checkbox'][id$='comCorrecaoTrabalhista']"
    APURAR_SOBRE_SALARIOS_PAGOS = "input[type='checkbox'][id$='apurarSobreSalariosPagos']"
    LEI_11941 = "input[type='checkbox'][id$='lei11941']"

    # Parametros das Ocorrencias
    CMD_PARAMETROS_OCORRENCIAS = "[id$='cmdParametrosOcorrencias'], [id$='parametrosOcorrencias']"
    ALIQUOTA_SEGURADO = "[id$='aliquotaSegurado'], [id$='tipoAliquotaSegurado']"  # radio
    ALIQUOTA_SEGURADO_FIXA = "[id$='aliquotaSeguradoFixa']"
    ALIQUOTA_EMPREGADOR = "[id$='tipoAliquotaEmpregador']"  # radio
    CONFIRMAR = "[id$='confirmar'], input[value='Confirmar']"

    # Periodos SIMPLES (isencao — manual seção 14)
    SIMPLES = "input[type='checkbox'][id$='simples'], input[type='checkbox'][id$='isencaoSimples']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Imposto de Renda / IRPF (irpf/irpf.jsf)
# ============================================================================

class ImpostoRenda:
    """Campos de Imposto de Renda"""
    JSF = "calculo/irpf.jsf"

    # Checkbox master (manual seção 17)
    APURAR = "input[type='checkbox'][id$='apurar'], input[type='checkbox'][id$='apurarIR']"
    # Incidir sobre juros de mora (manual seção 17)
    INCIDIR_SOBRE_JUROS = "input[type='checkbox'][id$='incidirSobreJurosDeMora'], input[type='checkbox'][id$='incidirJuros']"
    # Cobrar do reclamado (manual seção 17)
    COBRAR_DO_RECLAMADO = "input[type='checkbox'][id$='cobrarDoReclamado']"

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
    JSF = "calculo/honorarios/honorarios.jsf"

    # Formulario (apos clicar Novo)
    TIPO_DE_DEVEDOR = "select[id$='tipoDeDevedor'], select[id$='devedor'], select[id$='parteDevedora']"
    TIPO_HONORARIO = "select[id$='tipoHonorario'], select[id$='tipo']"
    DESCRICAO = "[id$='descricao'], [id$='descricaoHonorario']"
    TIPO_VALOR = "[id$='tipoValor']"  # radio CALCULADO/INFORMADO
    BASE_PARA_APURACAO = "select[id$='baseParaApuracao']"
    PERCENTUAL = "[id$='percentualHonorarios'], [id$='percentual']"
    VALOR_INFORMADO = "[id$='valorInformado'], [id$='valorFixo']"
    APURAR_IR = "input[type='checkbox'][id$='apurarIr'], input[type='checkbox'][id$='tributarIR']"

    # Incidir sobre juros (manual seção 19)
    INCIDIR_SOBRE_JUROS = "input[type='checkbox'][id$='incidirSobreJuros']"
    # Aplicar juros (manual seção 19)
    APLICAR_JUROS = "input[type='checkbox'][id$='aplicarJuros']"

    # Dados do Credor (manual seção 19)
    NOME_CREDOR = "[id$='nomeCredor'], [id$='nomeDoCredor']"
    DOC_FISCAL_CREDOR = "[id$='documentoFiscalCredor'], [id$='cpfCnpjCredor']"

    # Periciais
    HONORARIOS_PERICIAIS = "[id$='honorariosPericiais'], [id$='valorPericiais']"

    INCLUIR = "[id$='incluir']"
    SALVAR = "[id$='salvar']"


# ============================================================================
# Multas e Indenizacoes (multas-indenizacoes.jsf)
# ============================================================================

class MultasIndenizacoes:
    """Campos da pagina Multas e Indenizacoes"""
    JSF = "calculo/multas-indenizacoes.jsf"

    # Formulario (apos clicar Novo/Incluir)
    DESCRICAO = "[id$='descricao']"
    VALOR = "[id$='valor']"  # radio INFORMADO/CALCULADO
    ALIQUOTA = "[id$='aliquota']"  # valor numerico ou percentual
    CREDOR_DEVEDOR = "select[id$='credorDevedor']"
    TIPO_BASE_MULTA = "select[id$='tipoBaseMulta']"  # PRINCIPAL / VALOR_CAUSA / etc.

    INCLUIR = "[id$='incluir']"
    SALVAR = "[id$='salvar']"


# ============================================================================
# Salario-Familia (salario-familia.jsf)
# ============================================================================

class SalarioFamilia:
    """Campos da pagina Salario-Familia"""
    JSF = "calculo/salario-familia.jsf"

    APURAR = "input[type='checkbox'][id$='apurar']"
    COMPOR_PRINCIPAL = "[id$='comporPrincipal']"  # radio SIM/NAO
    QUANTIDADE_DE_FILHOS = "[id$='quantidadeDeFilhos']"
    REMUNERACAO_MENSAL = "[id$='remuneracaoMensal']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Seguro-Desemprego (seguro-desemprego.jsf)
# ============================================================================

class SeguroDesemprego:
    """Campos da pagina Seguro-Desemprego"""
    JSF = "calculo/seguro-desemprego.jsf"

    APURAR = "input[type='checkbox'][id$='apurar']"
    TIPO_SOLICITACAO = "[id$='tipoSolicitacao']"  # radio PRIMEIRA/SEGUNDA/DEMAIS
    EMPREGADO_DOMESTICO = "input[type='checkbox'][id$='empregadoDomestico']"
    COMPOR_PRINCIPAL = "[id$='comporPrincipal']"  # radio SIM/NAO
    QUANTIDADE_DE_PARCELAS = "[id$='quantidadeDeParcelas']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Previdencia Privada (previdencia-privada.jsf)
# ============================================================================

class PrevidenciaPrivada:
    """Campos da pagina Previdencia Privada"""
    JSF = "calculo/previdencia-privada.jsf"

    APURAR = "input[type='checkbox'][id$='apurar']"
    ALIQUOTA = "[id$='aliquota']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Pensao Alimenticia (pensao-alimenticia.jsf)
# ============================================================================

class PensaoAlimenticia:
    """Campos da pagina Pensao Alimenticia"""
    JSF = "calculo/pensao-alimenticia.jsf"

    APURAR = "input[type='checkbox'][id$='apurar']"
    ALIQUOTA = "[id$='aliquota']"
    INCIDIR_SOBRE_JUROS = "input[type='checkbox'][id$='incidirSobreJuros']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Correcao, Juros e Multa (correcao-juros.jsf / atualizacao.jsf)
# ============================================================================

class CorrecaoJurosMulta:
    """Campos de Correcao Monetaria, Juros de Mora e Multa"""
    JSF = "calculo/correcao-juros.jsf"

    # Indice de correcao
    INDICE_CORRECAO = "select[id$='indiceCorrecao'], select[id$='indiceTrabalhista']"

    # Combinar com outro indice (manual seção 21)
    COMBINAR_COM_OUTRO = "input[type='checkbox'][id$='combinarComOutro'], input[type='checkbox'][id$='combinarIndice']"
    SEGUNDO_INDICE = "select[id$='segundoIndice'], select[id$='outroIndice']"
    DATA_A_PARTIR_DE = "[id$='dataAPartirDe'], [id$='dataInicioSegundoIndice']"

    # Juros
    TAXA_JUROS = "select[id$='taxaJuros'], select[id$='juros']"
    DATA_INICIO_TAXA_LEGAL = "[id$='dataInicioTaxaLegal'], [id$='dataMarcoTaxaLegal']"
    BASE_DE_JUROS_DAS_VERBAS = "select[id$='baseDeJurosDasVerbas']"

    # Ignorar taxa negativa (manual seção 21)
    IGNORAR_TAXA_NEGATIVA = "input[type='checkbox'][id$='ignorarTaxaNegativa']"

    # Multa art. 523 CPC
    APLICAR_MULTA_523 = "input[type='checkbox'][id$='aplicarMulta523']"

    SALVAR = "[id$='salvar']"


# ============================================================================
# Custas Judiciais (custas.jsf)
# ============================================================================

class CustasJudiciais:
    """Campos de Custas Judiciais (custas/custas.jsf).

    Duas abas: Custas Devidas e Custas Recolhidas.
    Manual seção 20: salvar após preencher AMBAS as abas.
    """
    JSF = "calculo/custas-judiciais.jsf"

    # Aba Custas Devidas
    BASE_CUSTAS = "select[id$='baseCustas']"  # BRUTO_RECLAMANTE / BRUTO_MAIS_DEBITOS
    CUSTAS_RECLAMADO_CONHECIMENTO = "[id$='custasReclamadoConhecimento']"    # radio
    CUSTAS_RECLAMADO_LIQUIDACAO = "[id$='custasReclamadoLiquidacao']"        # radio
    CUSTAS_RECLAMANTE_CONHECIMENTO = "[id$='custasReclamanteConhecimento']"  # radio
    PERCENTUAL = "[id$='percentualCustas'], [id$='aliquota']"
    DEVEDOR = "select[id$='devedor']"

    # Aba Custas Recolhidas
    VENCIMENTO_CUSTAS = "[id$='vencimento'], [id$='dataVencimento']"
    VALOR_CUSTAS = "[id$='valorCustas'], [id$='valor']"

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
    """Seletores do menu lateral do PJE-Calc.

    O menu usa <li id='li_calculo_xxx'><a>...</a></li>.
    Seletores usam li_id confirmados por DOM Auditor.
    """

    # Tela inicial e operações gerais
    TELA_INICIAL = "li#li_tela_inicial a"
    NOVO = "li#li_calculo_novo a"
    CALCULO_EXTERNO = "li#li_calculo_externo_novo a"
    BUSCAR = "li#li_calculo_buscar a"
    IMPORTAR = "li#li_calculo_importar a"

    # Páginas do cálculo (visíveis após salvar)
    DADOS_DO_CALCULO = "li#li_calculo_dados a"
    HISTORICO_SALARIAL = "li#li_calculo_historico_salarial a"
    FERIAS = "li#li_calculo_ferias a"
    FALTAS = "li#li_calculo_faltas a"
    CARTAO_DE_PONTO = "li#li_calculo_cartao_ponto a"
    VERBAS = "li#li_calculo_verbas a"
    FGTS = "li#li_calculo_fgts a"
    CONTRIBUICAO_SOCIAL = "li#li_calculo_contribuicao_social a"
    IMPOSTO_RENDA = "li#li_calculo_imposto_renda a"
    HONORARIOS = "li#li_calculo_honorarios a"
    MULTAS = "li#li_calculo_multas a"
    CORRECAO_JUROS = "li#li_calculo_correcao_juros a"
    CUSTAS_JUDICIAIS = "li#li_calculo_custas a"
    SALARIO_FAMILIA = "li#li_calculo_salario_familia a"
    SEGURO_DESEMPREGO = "li#li_calculo_seguro_desemprego a"
    PENSAO_ALIMENTICIA = "li#li_calculo_pensao_alimenticia a"
    PREVIDENCIA_PRIVADA = "li#li_calculo_previdencia_privada a"

    # Operações finais
    OPERACOES = "li#li_calculo_operacoes a, li#li_operacoes a"
    LIQUIDAR = "li#li_calculo_liquidar a, li#li_operacoes_liquidar a"
    EXPORTAR = "li#li_calculo_exportar a, li#li_operacoes_exportar a"

    # Tabelas e relatórios
    RELATORIO_CONSOLIDADO = "li#li_processo_relatorio a"
    IMPRIMIR = "li#li_calculo_imprimir a"


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
    "multas_indenizacoes": MultasIndenizacoes,
    "salario_familia": SalarioFamilia,
    "seguro_desemprego": SeguroDesemprego,
    "previdencia_privada": PrevidenciaPrivada,
    "pensao_alimenticia": PensaoAlimenticia,
    "correcao_juros_multa": CorrecaoJurosMulta,
    "custas_judiciais": CustasJudiciais,
    "liquidacao": Liquidacao,
    "exportacao": Exportacao,
}
