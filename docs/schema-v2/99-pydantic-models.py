"""Modelos Pydantic v2 — Schema da Prévia v2.0

Implementação canônica do schema definido em docs/schema-v2/. Cada modelo
mapeia 1:1 para uma seção do PJE-Calc. Validação é executada na confecção
da prévia (extração) e antes de iniciar a automação.

Para usar:
    from docs.schema_v2.pydantic_models import PreviaCalculoV2
    previa = PreviaCalculoV2.model_validate(json_data)
    if previa.meta.validacao.completude != "OK":
        raise ValueError(previa.meta.validacao.campos_faltantes)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────


class DocumentoFiscalTipo(str, Enum):
    CPF = "CPF"
    CNPJ = "CNPJ"
    CEI = "CEI"


class DocumentoPrevidenciarioTipo(str, Enum):
    PIS = "PIS"
    PASEP = "PASEP"
    NIT = "NIT"


class TipoBaseTabelada(str, Enum):
    INTEGRAL = "INTEGRAL"
    PARCIAL = "PARCIAL"
    INTERMITENTE = "INTERMITENTE"


class ApuracaoAvisoPrevio(str, Enum):
    NAO_APURAR = "NAO_APURAR"
    APURACAO_CALCULADA = "APURACAO_CALCULADA"
    APURACAO_INFORMADA = "APURACAO_INFORMADA"


class TipoVariacaoParcela(str, Enum):
    FIXA = "FIXA"
    VARIAVEL = "VARIAVEL"


class TipoValor(str, Enum):
    INFORMADO = "INFORMADO"
    CALCULADO = "CALCULADO"


class CaracteristicaVerba(str, Enum):
    COMUM = "COMUM"
    DECIMO_TERCEIRO_SALARIO = "DECIMO_TERCEIRO_SALARIO"
    AVISO_PREVIO = "AVISO_PREVIO"
    FERIAS = "FERIAS"


class OcorrenciaPagamento(str, Enum):
    DESLIGAMENTO = "DESLIGAMENTO"
    DEZEMBRO = "DEZEMBRO"
    MENSAL = "MENSAL"
    PERIODO_AQUISITIVO = "PERIODO_AQUISITIVO"


class OcorrenciaAjuizamento(str, Enum):
    OCORRENCIAS_VENCIDAS_E_VINCENDAS = "OCORRENCIAS_VENCIDAS_E_VINCENDAS"
    OCORRENCIAS_VENCIDAS = "OCORRENCIAS_VENCIDAS"


class TipoVerba(str, Enum):
    PRINCIPAL = "PRINCIPAL"
    REFLEXO = "REFLEXO"


class GerarReflexo(str, Enum):
    DEVIDO = "DEVIDO"
    DIFERENCA = "DIFERENCA"


class SimNao(str, Enum):
    SIM = "SIM"
    NAO = "NAO"


class TipoBaseCalculo(str, Enum):
    MAIOR_REMUNERACAO = "MAIOR_REMUNERACAO"
    HISTORICO_SALARIAL = "HISTORICO_SALARIAL"
    SALARIO_DA_CATEGORIA = "SALARIO_DA_CATEGORIA"
    SALARIO_MINIMO = "SALARIO_MINIMO"
    VALE_TRANSPORTE = "VALE_TRANSPORTE"


class TipoDivisor(str, Enum):
    OUTRO_VALOR = "OUTRO_VALOR"
    CARGA_HORARIA = "CARGA_HORARIA"
    DIAS_UTEIS = "DIAS_UTEIS"
    IMPORTADA_DO_CARTAO = "IMPORTADA_DO_CARTAO"


class TipoQuantidade(str, Enum):
    INFORMADA = "INFORMADA"
    IMPORTADA_DO_CALENDARIO = "IMPORTADA_DO_CALENDARIO"
    IMPORTADA_DO_CARTAO = "IMPORTADA_DO_CARTAO"


class EstrategiaPreenchimento(str, Enum):
    EXPRESSO_DIRETO = "expresso_direto"
    EXPRESSO_ADAPTADO = "expresso_adaptado"
    MANUAL = "manual"


class EstrategiaReflexa(str, Enum):
    CHECKBOX_PAINEL = "checkbox_painel"
    MANUAL = "manual"


class ComportamentoReflexo(str, Enum):
    VALOR_MENSAL = "VALOR_MENSAL"
    MEDIA_PELO_VALOR = "MEDIA_PELO_VALOR"
    MEDIA_PELO_VALOR_CORRIGIDO = "MEDIA_PELO_VALOR_CORRIGIDO"
    MEDIA_PELA_QUANTIDADE = "MEDIA_PELA_QUANTIDADE"


# ─── 1. Processo ──────────────────────────────────────────────────────────


class DocumentoFiscal(BaseModel):
    tipo: DocumentoFiscalTipo
    numero: str


class DocumentoPrevidenciario(BaseModel):
    tipo: DocumentoPrevidenciarioTipo = DocumentoPrevidenciarioTipo.PIS
    numero: Optional[str] = None


class Advogado(BaseModel):
    nome: str
    oab: Optional[str] = None
    doc_fiscal_tipo: Optional[DocumentoFiscalTipo] = None
    doc_fiscal_numero: Optional[str] = None


class Parte(BaseModel):
    nome: str
    doc_fiscal: DocumentoFiscal
    doc_previdenciario: Optional[DocumentoPrevidenciario] = None
    advogados: list[Advogado] = Field(default_factory=list)


class Processo(BaseModel):
    numero_processo: str = Field(pattern=r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")
    valor_da_causa_brl: float = Field(gt=0)
    data_autuacao: str  # DD/MM/YYYY
    reclamante: Parte
    reclamado: Parte


# ─── 2. Parâmetros do Cálculo ─────────────────────────────────────────────


class ExcecaoCargaHoraria(BaseModel):
    data_inicio: str
    data_fim: str
    valor_carga_horaria: float


class CargaHoraria(BaseModel):
    padrao_mensal: float = 220.0
    excecoes: list[ExcecaoCargaHoraria] = Field(default_factory=list)


class ExcecaoSabado(BaseModel):
    data_inicio: str
    data_fim: str


class ParametrosCalculo(BaseModel):
    estado_uf: str = Field(min_length=2, max_length=2)
    municipio: str
    data_admissao: str
    data_demissao: str
    data_ajuizamento: str
    data_inicio_calculo: str
    data_termino_calculo: str
    prescricao_quinquenal: bool = True
    prescricao_fgts: bool = False
    tipo_base_tabelada: TipoBaseTabelada = TipoBaseTabelada.INTEGRAL
    valor_maior_remuneracao_brl: float = Field(ge=0)
    valor_ultima_remuneracao_brl: float = Field(ge=0)
    apuracao_aviso_previo: ApuracaoAvisoPrevio
    projeta_aviso_indenizado: bool = True
    limitar_avos: bool = False
    zerar_valor_negativo: bool = True
    considerar_feriado_estadual: bool = True
    considerar_feriado_municipal: bool = True
    carga_horaria: CargaHoraria = Field(default_factory=CargaHoraria)
    sabado_dia_util: bool = False
    excecoes_sabado: list[ExcecaoSabado] = Field(default_factory=list)
    pontos_facultativos_codigo: list[int] = Field(default_factory=list)
    comentarios_jg: Optional[str] = None


# ─── 3. Histórico Salarial ────────────────────────────────────────────────


class HistoricoSalarialIncidencias(BaseModel):
    fgts: bool = True
    cs_inss: bool = True


class HistoricoSalarialCalculado(BaseModel):
    quantidade_pct: float
    base_referencia: str


class HistoricoSalarial(BaseModel):
    nome: str
    parcela: TipoVariacaoParcela = TipoVariacaoParcela.FIXA
    incidencias: HistoricoSalarialIncidencias
    competencia_inicial: str  # MM/YYYY
    competencia_final: str  # MM/YYYY
    tipo_valor: TipoValor
    valor_brl: Optional[float] = None
    calculado: Optional[HistoricoSalarialCalculado] = None

    @model_validator(mode="after")
    def _check_tipo_valor(self) -> "HistoricoSalarial":
        if self.tipo_valor == TipoValor.INFORMADO and self.valor_brl is None:
            raise ValueError("Histórico INFORMADO exige valor_brl")
        if self.tipo_valor == TipoValor.CALCULADO and self.calculado is None:
            raise ValueError("Histórico CALCULADO exige campo `calculado`")
        return self


# ─── 4. Verbas Principais ─────────────────────────────────────────────────


class AssuntoCNJ(BaseModel):
    codigo: int
    label: str


class VerbaIncidencias(BaseModel):
    irpf: bool = False
    cs_inss: bool = False
    fgts: bool = False
    previdencia_privada: bool = False
    pensao_alimenticia: bool = False


class VerbaExclusoes(BaseModel):
    faltas_justificadas: bool = False
    faltas_nao_justificadas: bool = False
    ferias_gozadas: bool = False
    dobrar_valor_devido: bool = False


class ValorDevidoInformado(BaseModel):
    tipo: Literal["INFORMADO"] = "INFORMADO"
    valor_informado_brl: float = Field(gt=0)
    proporcionalizar: bool = False


class ValorDevidoCalculado(BaseModel):
    tipo: Literal["CALCULADO"] = "CALCULADO"


class BaseComposta(BaseModel):
    verba: str
    integralizar: SimNao = SimNao.SIM


class BaseCalculoVerba(BaseModel):
    tipo: TipoBaseCalculo
    historico_nome: Optional[str] = None
    proporcionaliza: Optional[SimNao] = None
    bases_compostas: list[BaseComposta] = Field(default_factory=list)


class DivisorVerba(BaseModel):
    tipo: TipoDivisor = TipoDivisor.OUTRO_VALOR
    valor: Optional[float] = None


class QuantidadeVerba(BaseModel):
    """Quantidade na fórmula CALCULADO.

    Tolerância: se `tipo=INFORMADA` mas `valor=None`, normalizamos para
    `tipo=CALCULADA` (sistema apura) com valor 0.
    """
    tipo: TipoQuantidade = TipoQuantidade.INFORMADA
    valor: Optional[float] = 1.0
    proporcionalizar: bool = False

    @model_validator(mode="after")
    def _normaliza_valor_null(self) -> "QuantidadeVerba":
        if self.valor is None:
            self.valor = 0.0
        return self


class FormulaCalculado(BaseModel):
    model_config = ConfigDict(extra="allow")

    base_calculo: Optional[BaseCalculoVerba] = None
    divisor: Optional[DivisorVerba] = None
    multiplicador: float = 1.0
    quantidade: Optional[QuantidadeVerba] = None


class ValorPagoVerba(BaseModel):
    tipo: TipoValor = TipoValor.INFORMADO
    valor_brl: float = 0.0
    proporcionalizar: bool = False


class OcorrenciaMensalOverride(BaseModel):
    mes: str  # MM/YYYY
    valor_devido: float
    valor_pago: float = 0.0
    quantidade: Optional[float] = None  # ex: HE 50% qtd horas/mês
    multiplicador: Optional[float] = None
    divisor: Optional[float] = None


class OcorrenciasOverride(BaseModel):
    """Override da tabela mensal de Ocorrências (parametrizar-ocorrencia.jsf).

    Modo `alteracao_em_lote` (default): aplica os valores no header do Lote
    e clica Alterar — propagando para todas as linhas ativas. Use quando
    valor é uniforme em todo o período.

    Modo `valores_mensais`: preenche cada linha individualmente. Use quando
    a sentença determina valores diferentes mês a mês.
    """

    modo: Literal["alteracao_em_lote", "valores_mensais"] = "alteracao_em_lote"
    valores_mensais: list[OcorrenciaMensalOverride] = Field(default_factory=list)
    # quando modo=alteracao_em_lote, usar campos do verba.parametros.valor_devido
    # (não há campos extras aqui)


class ParametrosVerba(BaseModel):
    """Parâmetros de uma verba principal.

    Todos os campos de classificação são Optional para tolerar o JSON gerado
    pelo Projeto Claude externo, que não inclui assunto_cnj, valor, caracteristica
    etc. (campos preenchidos automaticamente pelo PJE-Calc no modo Expresso).
    """
    model_config = ConfigDict(extra="allow")

    assunto_cnj: Optional[AssuntoCNJ] = None
    parcela: TipoVariacaoParcela = TipoVariacaoParcela.FIXA
    valor: Optional[TipoValor] = None
    incidencias: Optional[VerbaIncidencias] = None
    caracteristica: Optional[CaracteristicaVerba] = None
    ocorrencia_pagamento: Optional[OcorrenciaPagamento] = None
    ocorrencia_ajuizamento: OcorrenciaAjuizamento = OcorrenciaAjuizamento.OCORRENCIAS_VENCIDAS
    tipo: TipoVerba = TipoVerba.PRINCIPAL
    gerar_reflexa: GerarReflexo = GerarReflexo.DIFERENCA
    gerar_principal: GerarReflexo = GerarReflexo.DIFERENCA
    compor_principal: bool = True
    zerar_valor_negativo: bool = False
    periodo_inicio: Optional[str] = None
    periodo_fim: Optional[str] = None
    exclusoes: VerbaExclusoes = Field(default_factory=VerbaExclusoes)
    valor_devido: Optional[Union[ValorDevidoInformado, ValorDevidoCalculado]] = None
    formula_calculado: Optional[FormulaCalculado] = None
    valor_pago: ValorPagoVerba = Field(default_factory=ValorPagoVerba)
    comentarios: Optional[str] = None

    @model_validator(mode="after")
    def _check_valor_consistency(self) -> "ParametrosVerba":
        # Pular validação quando valor não foi especificado (modo Expresso)
        if self.valor is None:
            return self
        # Tolerância: se LLM gerou valor=CALCULADO mas formula_calculado é null
        # E valor_devido tem valor_informado_brl, normalizamos para INFORMADO.
        if (
            self.valor == TipoValor.CALCULADO
            and self.formula_calculado is None
            and isinstance(self.valor_devido, ValorDevidoInformado)
            and self.valor_devido.valor_informado_brl is not None
        ):
            self.valor = TipoValor.INFORMADO
        return self


class ParametrosReflexo(BaseModel):
    """Override opcional dos parâmetros de um reflexo (página doc 07).

    Para reflexos `estrategia_reflexa: "manual"`, os campos abaixo são usados
    pelo automator para criar a verba REFLEXO via Manual no PJE-Calc.
    """
    model_config = ConfigDict(extra="allow")  # tolera campos legacy/futuros

    # Núcleo: comportamento e fórmula
    comportamento_reflexo: Optional[ComportamentoReflexo] = None
    tratamento_fracao_mes: Optional[Literal["INTEGRALIZAR", "NAO_INTEGRALIZAR"]] = None
    outro_valor_divisor: Optional[float] = None
    outro_valor_multiplicador: Optional[float] = None
    # Override de classificação (necessário p/ reflexo manual)
    valor: Optional[TipoValor] = None
    caracteristica: Optional[CaracteristicaVerba] = None
    ocorrencia_pagamento: Optional[OcorrenciaPagamento] = None
    # Override de incidências e período
    incidencias: Optional[VerbaIncidencias] = None
    periodo_inicio: Optional[str] = None
    periodo_fim: Optional[str] = None
    comentarios: Optional[str] = None


class Reflexo(BaseModel):
    """Reflexo de uma verba principal (embutido em VerbaPrincipal.reflexos).

    `verba_principal_id` e `nome` são Optional pois o Projeto Claude externo
    os omite quando os reflexos estão aninhados dentro da verba principal.
    """
    model_config = ConfigDict(extra="allow")

    id: str
    verba_principal_id: Optional[str] = None  # implícito quando aninhado em VerbaPrincipal
    nome: Optional[str] = None
    estrategia_reflexa: EstrategiaReflexa = EstrategiaReflexa.CHECKBOX_PAINEL
    indice_reflexo_listagem: Optional[int] = None
    expresso_reflex_alvo: Optional[str] = None
    parametros_override: Optional[ParametrosReflexo] = None
    ocorrencias_override: Optional[OcorrenciasOverride] = None


class VerbaPrincipal(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    nome_sentenca: str
    estrategia_preenchimento: EstrategiaPreenchimento
    expresso_alvo: Optional[str] = None
    nome_pjecalc: Optional[str] = None  # pode ser omitido; cai-back para nome_sentenca
    parametros: ParametrosVerba
    ocorrencias_override: Optional[OcorrenciasOverride] = None
    reflexos: list[Reflexo] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_estrategia(self) -> "VerbaPrincipal":
        if self.estrategia_preenchimento != EstrategiaPreenchimento.MANUAL:
            if not self.expresso_alvo:
                raise ValueError(
                    f"Estratégia {self.estrategia_preenchimento} requer expresso_alvo"
                )
        return self


# ─── 5-19. Outras seções (modelos compactados) ────────────────────────────
# Para brevidade, modelos das seções 5-19 estão aqui em forma simplificada.
# Cada um é um BaseModel com campos correspondentes ao schema docs/schema-v2/.


class CartaoDePonto(BaseModel):
    """Ver doc 05-cartao-ponto.md para schema completo (63 campos)."""

    model_config = ConfigDict(extra="allow")  # permite campos extras durante implementação


class Falta(BaseModel):
    data_inicio: str
    data_fim: str
    justificada: bool = False
    reinicia_ferias: bool = False
    justificativa: Optional[str] = None


class GozoFerias(BaseModel):
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    dobra: bool = False


class PeriodoFerias(BaseModel):
    periodo_aquisitivo_inicio: str
    periodo_aquisitivo_fim: str
    periodo_concessivo_inicio: str
    periodo_concessivo_fim: str
    prazo_dias: int = 30
    situacao: Literal["INDENIZADAS", "GOZADAS", "PARCIAL_GOZADAS", "NAO_DIREITO"] = "INDENIZADAS"
    dobra: bool = False
    abono: bool = False
    dias_abono: int = 0
    gozo_1: GozoFerias = Field(default_factory=GozoFerias)
    gozo_2: Optional[GozoFerias] = None
    gozo_3: Optional[GozoFerias] = None


class FeriasSection(BaseModel):
    periodos: list[PeriodoFerias] = Field(default_factory=list)
    ferias_coletivas_inicio_primeiro_ano: Optional[str] = None
    prazo_ferias_proporcionais: Optional[int] = None  # default vem do PJE-Calc


class FGTSMulta(BaseModel):
    model_config = ConfigDict(extra="allow")

    ativa: bool = True
    tipo_valor: Optional[Literal["CALCULADA", "INFORMADA", "NAO_APURAR"]] = "CALCULADA"
    percentual: Optional[Literal["VINTE_POR_CENTO", "QUARENTA_POR_CENTO"]] = None
    excluir_aviso_da_multa: bool = False
    valor_informado_brl: Optional[float] = None


class RecolhimentoFGTS(BaseModel):
    """Linha de recolhimento FGTS já existente (puxado pelo botão Recuperar).

    Cada entrada representa um período em que o empregador depositou FGTS.
    A automação só edita esta tabela se o reclamante já fez saque do FGTS
    (multa rescisória prévia, doença grave, etc.) — caso raro.

    Aceita aliases legacy: `periodo_inicio` → `competencia_inicio`,
    `periodo_fim` → `competencia_fim`, `valor_depositado_brl` → `valor_total_depositado_brl`.
    Aceita também `competencia` (chave curta usada por alguns prompts).
    """
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tipo: Literal["DEPOSITO_REGULAR", "SAQUE", "MULTA_RESCISORIA"] = "DEPOSITO_REGULAR"
    competencia_inicio: Optional[str] = Field(default=None, alias="periodo_inicio")  # MM/YYYY
    competencia_fim: Optional[str] = Field(default=None, alias="periodo_fim")  # MM/YYYY
    valor_total_depositado_brl: Optional[float] = Field(default=None, ge=0, alias="valor_depositado_brl")
    fonte: Literal["INFORMADO_PELA_PARTE", "EXTRATO_FGTS_OFICIAL", "AUTOMATICO"] = "AUTOMATICO"
    descricao: Optional[str] = None


class FGTS(BaseModel):
    tipo_verba: Literal["PAGAR", "DEPOSITAR"] = "PAGAR"
    compor_principal: SimNao = SimNao.SIM
    multa: FGTSMulta = Field(default_factory=FGTSMulta)
    incidencia: str = "SOBRE_O_TOTAL_DEVIDO"
    multa_artigo_467: bool = False
    multa_10_lc110: bool = False
    contribuicao_social: bool = False
    incidencia_pensao_alimenticia: bool = False
    recolhimentos_existentes: list[RecolhimentoFGTS] = Field(default_factory=list)


class VinculacaoHistoricoIntervalo(BaseModel):
    """Vínculo de um intervalo de competências a um histórico salarial,
    para o cálculo da CS sobre Salários Devidos."""

    competencia_inicial: str  # MM/YYYY
    competencia_final: str  # MM/YYYY
    historico_nome: str  # nome do histórico (ex: "ÚLTIMA REMUNERAÇÃO")
    valor_base_brl: float = Field(ge=0)


class VinculacaoHistoricos(BaseModel):
    """Controle da vinculação histórico → CS (sub-página parametrizar-inss.jsf).

    Modo `automatica` (default): a automação clica Recuperar Devidos +
    Copiar Devidos→Pagos automaticamente. Funciona quando o histórico
    cobre todo o período.

    Modo `manual_por_periodo`: usuário define qual histórico cobre quais
    meses. A automação aplica via Alteração em Lote por intervalo.
    """

    modo: Literal["automatica", "manual_por_periodo"] = "automatica"
    intervalos: list[VinculacaoHistoricoIntervalo] = Field(default_factory=list)


class ContribuicaoSocial(BaseModel):
    apurar_segurado_devido: bool = True
    cobrar_do_reclamante_devido: bool = False
    corrigir_desconto_reclamante: bool = True
    apurar_salarios_pagos: bool = True
    aliquota_segurado: Literal["SEGURADO_EMPREGADO", "EMPREGADO_DOMESTICO", "FIXA"] = "SEGURADO_EMPREGADO"
    aliquota_empregador: Literal["POR_ATIVIDADE_ECONOMICA", "POR_PERIODO", "FIXA"] = "POR_ATIVIDADE_ECONOMICA"
    aliquota_empresa_fixa_pct: Optional[float] = None
    aliquota_rat_fixa_pct: Optional[float] = None
    aliquota_terceiros_fixa_pct: Optional[float] = None
    periodo_devidos: dict = Field(default_factory=dict)
    periodo_pagos: dict = Field(default_factory=dict)
    vinculacao_historicos_devidos: VinculacaoHistoricos = Field(default_factory=VinculacaoHistoricos)


class IRPFDeducoes(BaseModel):
    contribuicao_social: bool = True
    previdencia_privada: bool = False
    pensao_alimenticia: bool = False
    honorarios_devidos_pelo_reclamante: bool = True


class ImpostoDeRenda(BaseModel):
    apurar_irpf: bool = True
    incidir_sobre_juros_de_mora: bool = False
    cobrar_do_reclamado: bool = False
    considerar_tributacao_exclusiva: bool = False
    considerar_tributacao_em_separado_rra: bool = True
    regime_de_caixa: bool = False
    deducoes: IRPFDeducoes = Field(default_factory=IRPFDeducoes)
    aposentado_maior_65_anos: bool = False
    possui_dependentes: bool = False
    quantidade_dependentes: int = 0


class CredorHonorario(BaseModel):
    selecao_existente: Optional[str] = None
    nome: str
    doc_fiscal_tipo: DocumentoFiscalTipo = DocumentoFiscalTipo.CPF
    doc_fiscal_numero: str


class Honorario(BaseModel):
    """Honorário (advocatício/sucumbencial/pericial).

    Aceita aliases legacy do prompt: `tipo` → `tipo_honorario`,
    `devedor` → `tipo_devedor`, `percentual` → `aliquota_pct`,
    `base_apuracao` → `base_para_apuracao`. `id`, `descricao`, `credor`
    têm defaults para tolerância.
    """
    model_config = ConfigDict(populate_by_name=True)

    id: str = ""  # auto-preenchido se vazio
    tipo_honorario: str = Field(alias="tipo")  # ver enum no doc 11
    descricao: str = ""
    tipo_devedor: Literal[
        "RECLAMANTE", "RECLAMADO",
        "RECLAMANTE_ARCADO_PELA_UNIAO",  # casos de gratuidade judiciária
    ] = Field(alias="devedor")
    tipo_valor: TipoValor = TipoValor.CALCULADO
    aliquota_pct: Optional[float] = Field(default=None, alias="percentual")
    base_para_apuracao: Optional[str] = Field(default=None, alias="base_apuracao")
    credor: Optional[CredorHonorario] = None
    apurar_irrf: bool = False
    valor_informado_brl: Optional[float] = None
    comentarios: Optional[str] = None

    @model_validator(mode="after")
    def _autofill_id(self) -> "Honorario":
        if not self.id:
            import hashlib as _h
            base = f"{self.tipo_honorario}-{self.tipo_devedor}-{self.aliquota_pct or self.valor_informado_brl}"
            self.id = "h-" + _h.md5(base.encode()).hexdigest()[:8]
        return self


class CustasJudiciais(BaseModel):
    base_para_calculadas: Literal[
        "BRUTO_DEVIDO_AO_RECLAMANTE",
        "BRUTO_DEVIDO_AO_RECLAMANTE_MAIS_DEBITOS_RECLAMADO",
    ] = "BRUTO_DEVIDO_AO_RECLAMANTE"
    custas_conhecimento_reclamante: Literal["NAO_SE_APLICA", "CALCULADA_2_POR_CENTO", "INFORMADA"] = "NAO_SE_APLICA"
    custas_conhecimento_reclamado: Literal["NAO_SE_APLICA", "CALCULADA_2_POR_CENTO", "INFORMADA"] = "CALCULADA_2_POR_CENTO"
    custas_liquidacao: Literal["NAO_SE_APLICA", "CALCULADA_MEIO_POR_CENTO", "INFORMADA"] = "NAO_SE_APLICA"
    data_vencimento_fixas: Optional[str] = None
    qtd_atos: dict = Field(default_factory=dict)
    autos: list = Field(default_factory=list)
    armazenamentos: list = Field(default_factory=list)
    rd: list = Field(default_factory=list)
    rt: list = Field(default_factory=list)


class CorrecaoJurosMulta(BaseModel):
    """Ver doc 13 — modelo simplificado, expandir conforme implementação."""

    model_config = ConfigDict(extra="allow")
    indice_trabalhista: str = "IPCAE"
    juros: str = "TAXA_LEGAL"
    base_juros_verbas: Literal["VERBAS", "VERBA_INSS", "VERBA_INSS_PP"] = "VERBAS"


class Liquidacao(BaseModel):
    data_de_liquidacao: Optional[str] = None  # default: hoje
    indices_acumulados: Literal[
        "MES_SUBSEQUENTE_AO_VENCIMENTO",
        "MES_DO_VENCIMENTO",
        "MES_SUBSEQUENTE_E_MES_DO_VENCIMENTO",
    ] = "MES_SUBSEQUENTE_AO_VENCIMENTO"


# ─── Meta + Validação ─────────────────────────────────────────────────────


class Validacao(BaseModel):
    completude: Literal["OK", "INCOMPLETO", "ERRO"] = "OK"
    campos_faltantes: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)


class Meta(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    criado_em: str = Field(default_factory=lambda: datetime.now().isoformat())
    extraido_por: str = "Claude Sonnet 4.6"
    validacao: Validacao = Field(default_factory=Validacao)


# ─── Modelo Top-Level ─────────────────────────────────────────────────────


class PreviaCalculoV2(BaseModel):
    model_config = ConfigDict(extra="allow")  # tolera campos extras/futuros do Projeto Claude

    meta: Meta = Field(default_factory=Meta)
    processo: Processo
    parametros_calculo: ParametrosCalculo
    historico_salarial: list[HistoricoSalarial] = Field(min_length=1)
    verbas_principais: list[VerbaPrincipal] = Field(min_length=1)
    cartao_de_ponto: Optional[CartaoDePonto] = None
    faltas: list[Falta] = Field(default_factory=list)
    ferias: FeriasSection = Field(default_factory=FeriasSection)
    fgts: FGTS = Field(default_factory=FGTS)
    contribuicao_social: ContribuicaoSocial = Field(default_factory=ContribuicaoSocial)
    imposto_de_renda: ImpostoDeRenda = Field(default_factory=ImpostoDeRenda)
    honorarios: list[Honorario] = Field(default_factory=list)
    custas_judiciais: CustasJudiciais = Field(default_factory=CustasJudiciais)
    correcao_juros_multa: CorrecaoJurosMulta = Field(default_factory=CorrecaoJurosMulta)
    liquidacao: Liquidacao = Field(default_factory=Liquidacao)
    salario_familia: Optional[dict] = None
    seguro_desemprego: Optional[dict] = None
    previdencia_privada: Optional[dict] = None
    pensao_alimenticia: Optional[dict] = None
    multas_indenizacoes: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_completude(self) -> "PreviaCalculoV2":
        """Roda validações cruzadas e atualiza self.meta.validacao."""
        avisos: list[str] = []
        # 1. Histórico cobre período do cálculo
        if self.historico_salarial:
            ult_competencia_fim = max(h.competencia_final for h in self.historico_salarial)
            # comparação string MM/YYYY: converter para tupla (ano, mês)
            ano_termino, mes_termino = self.parametros_calculo.data_termino_calculo.split("/")[2], self.parametros_calculo.data_termino_calculo.split("/")[1]
            ult_mes, ult_ano = ult_competencia_fim.split("/")
            if (int(ult_ano), int(ult_mes)) < (int(ano_termino), int(mes_termino)):
                avisos.append(
                    f"Histórico salarial termina em {ult_competencia_fim} mas cálculo vai até {self.parametros_calculo.data_termino_calculo}"
                )

        # 2. Verbas com valor=INFORMADO têm valor preenchido
        for v in self.verbas_principais:
            if v.parametros.valor == TipoValor.INFORMADO:
                if not isinstance(v.parametros.valor_devido, ValorDevidoInformado):
                    self.meta.validacao.campos_faltantes.append(
                        f"verbas_principais[{v.id}].parametros.valor_devido.valor_informado_brl"
                    )

        if avisos:
            self.meta.validacao.avisos.extend(avisos)
        if self.meta.validacao.campos_faltantes:
            self.meta.validacao.completude = "INCOMPLETO"
        return self

    @model_validator(mode="after")
    def _verifica_ocorrencia_periodo_demissao(self) -> "PreviaCalculoV2":
        """Valida coerência entre ocorrencia_pagamento × periodo × data_demissao.

        Regras (PJE-Calc):
        1. **DESLIGAMENTO**: usado para verbas rescisórias.
           `periodo_fim` deve ser ≤ `data_demissao`. Se for > demissao,
           a verba é pós-contratual (estabilidade, dispensa discriminatória)
           e a ocorrência correta é MENSAL.
        2. **PERIODO_AQUISITIVO** (férias): exige `periodo_aquisitivo_*` na verba.
        3. **MENSAL** ou **DEZEMBRO**: períodos podem se estender após demissao
           (ex.: indenização de estabilidade), mas devem estar dentro do
           `data_termino_calculo`.

        Erros vão para `meta.validacao.campos_faltantes`. A automação só roda
        com `completude=OK`.
        """
        from datetime import datetime as _dt

        def _parse_br(s: Optional[str]) -> Optional[_dt]:
            if not s:
                return None
            try:
                return _dt.strptime(s, "%d/%m/%Y")
            except (ValueError, TypeError):
                return None

        d_dem = _parse_br(self.parametros_calculo.data_demissao)
        d_fim_calc = _parse_br(self.parametros_calculo.data_termino_calculo)
        d_adm = _parse_br(self.parametros_calculo.data_admissao)

        for v in self.verbas_principais:
            p = v.parametros
            d_pi = _parse_br(p.periodo_inicio)
            d_pf = _parse_br(p.periodo_fim)

            # Regra 1: DESLIGAMENTO + periodo_fim > demissao = ERRO
            if (
                p.ocorrencia_pagamento == OcorrenciaPagamento.DESLIGAMENTO
                and d_pf and d_dem and d_pf > d_dem
            ):
                self.meta.validacao.campos_faltantes.append(
                    f"verba[{v.id}] '{v.nome_pjecalc or v.nome_sentenca}': ocorrencia_pagamento=DESLIGAMENTO "
                    f"incompatível com periodo_fim={p.periodo_fim} POSTERIOR à "
                    f"data_demissao={self.parametros_calculo.data_demissao}. "
                    f"Use ocorrencia_pagamento=MENSAL para verbas pós-contratuais."
                )

            # Regra 2: periodo_inicio < data_admissao = ERRO
            if d_pi and d_adm and d_pi < d_adm:
                self.meta.validacao.campos_faltantes.append(
                    f"verba[{v.id}] '{v.nome_pjecalc or v.nome_sentenca}': periodo_inicio={p.periodo_inicio} "
                    f"ANTERIOR à data_admissao={self.parametros_calculo.data_admissao}."
                )

            # Regra 3: periodo_fim > data_termino_calculo = ERRO
            if d_pf and d_fim_calc and d_pf > d_fim_calc:
                self.meta.validacao.campos_faltantes.append(
                    f"verba[{v.id}] '{v.nome_pjecalc or v.nome_sentenca}': periodo_fim={p.periodo_fim} "
                    f"posterior à data_termino_calculo={self.parametros_calculo.data_termino_calculo}. "
                    f"Estenda data_termino_calculo ou ajuste periodo_fim."
                )

            # Regra 4: periodo_inicio > periodo_fim = ERRO
            if d_pi and d_pf and d_pi > d_pf:
                self.meta.validacao.campos_faltantes.append(
                    f"verba[{v.id}] '{v.nome_pjecalc or v.nome_sentenca}': periodo_inicio={p.periodo_inicio} "
                    f"posterior a periodo_fim={p.periodo_fim}."
                )

        if self.meta.validacao.campos_faltantes:
            self.meta.validacao.completude = "INCOMPLETO"
        return self

    @model_validator(mode="after")
    def _verifica_reflexos_vinculados(self) -> "PreviaCalculoV2":
        """Valida que todo reflexo aponta para uma verba principal existente.

        Regras:
        1. `reflexo.verba_principal_id` deve casar com algum `verbas_principais[i].id`.
        2. O reflexo deve estar listado em `verbas_principais[i].reflexos` daquela
           principal (consistência estrutural).
        3. IDs de reflexos devem ser únicos no arquivo todo.
        """
        principais_ids = {v.id for v in self.verbas_principais}
        reflexo_ids_globais: list[str] = []

        for v in self.verbas_principais:
            for r in v.reflexos:
                # Regra 1: FK válida (ignorar quando None — campo opcional)
                if r.verba_principal_id is not None and r.verba_principal_id not in principais_ids:
                    self.meta.validacao.campos_faltantes.append(
                        f"reflexo[{r.id}].verba_principal_id={r.verba_principal_id} "
                        f"não corresponde a nenhuma verba_principal"
                    )
                # Regra 2: consistência estrutural — reflexo dentro do bloco
                # da principal deve apontar para essa principal.
                elif r.verba_principal_id is not None and r.verba_principal_id != v.id:
                    self.meta.validacao.campos_faltantes.append(
                        f"reflexo[{r.id}] está aninhado em verba_principal[{v.id}] "
                        f"mas verba_principal_id={r.verba_principal_id} aponta para outra"
                    )
                # Regra 3: ID global único
                if r.id in reflexo_ids_globais:
                    self.meta.validacao.campos_faltantes.append(
                        f"reflexo.id={r.id} duplicado"
                    )
                reflexo_ids_globais.append(r.id)

        if self.meta.validacao.campos_faltantes:
            self.meta.validacao.completude = "INCOMPLETO"
        return self


# ─── Resolver forward refs (necessário quando carregado via importlib) ─────
# Quando o módulo é carregado via importlib.util.spec_from_file_location,
# Pydantic não tem acesso ao namespace global automático. Passamos explicitamente.
import sys as _sys
_ns = dict(globals())
# Garantir que o módulo está em sys.modules para resolução por nome
_modname = __name__
if _modname not in _sys.modules:
    _sys.modules[_modname] = _sys.modules.get("__main__") or type(_sys)(_modname)
    for _k, _v in _ns.items():
        setattr(_sys.modules[_modname], _k, _v)

# Rebuild em ordem topológica (bottom-up): rebuilds em filhos antes do pai
for _cls_name in list(_ns.keys()):
    _cls = _ns.get(_cls_name)
    if isinstance(_cls, type) and issubclass(_cls, BaseModel) and _cls is not BaseModel:
        try:
            _cls.model_rebuild(_types_namespace=_ns)
        except Exception:
            pass
