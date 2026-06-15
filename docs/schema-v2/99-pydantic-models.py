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
    """Opções no dropdown Quantidade da fórmula CALCULADO (manual §9.3).

    Variações por Característica:
    - COMUM: INFORMADA, IMPORTADA_DO_CALENDARIO, IMPORTADA_DO_CARTAO
    - DECIMO_TERCEIRO_SALARIO: AVOS (auto-selecionado, sistema apura)
    - FERIAS: AVOS (auto-selecionado, sistema apura)
    - AVISO_PREVIO + apuracao=NAO_APURAR: INFORMADA com valor 30
    - AVISO_PREVIO + apuracao=APURACAO_INFORMADA: INFORMADA com valor digitado
    - AVISO_PREVIO + apuracao=APURACAO_CALCULADA: APURADA (sistema calcula)
    """
    INFORMADA = "INFORMADA"
    IMPORTADA_DO_CALENDARIO = "IMPORTADA_DO_CALENDARIO"
    IMPORTADA_DO_CARTAO = "IMPORTADA_DO_CARTAO"
    AVOS = "AVOS"
    APURADA = "APURADA"


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

    @field_validator("numero", mode="before")
    @classmethod
    def _numero_ausente_vira_vazio(cls, v):
        """Sentenças frequentemente não trazem CPF/CNPJ das partes (caso
        Ariane 12/06/2026 — extração in-app travava na Etapa 2 com
        'Input should be a valid string'). Documento ausente → "" e o
        usuário completa na prévia (campo editável)."""
        return "" if v is None else v


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
    model_config = ConfigDict(extra="allow")  # tolera campos extras (ex: reclamado_subsidiario)
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


class JusticaGratuita(BaseModel):
    """Concessão de Justiça Gratuita por parte (fato extraído da sentença).

    Combinação com honorarios[].tipo_devedor=SUCUMBENCIAIS contra a mesma
    parte aciona auto-build do texto de suspensão de exigibilidade
    (art. 791-A § 4º CLT) pelo normalizer — preserva fidelidade
    prévia↔automação.
    """
    reclamante: bool = False
    reclamado: bool = False


class ParametrosCalculo(BaseModel):
    model_config = ConfigDict(extra="allow")
    estado_uf: str = Field(min_length=2, max_length=2)
    municipio: str
    data_admissao: str
    data_demissao: str
    data_ajuizamento: str
    data_inicio_calculo: str
    data_termino_calculo: str
    # Modalidade da rescisão — usada para enforce determinístico da Súmula 171
    # (justa causa / pedido de demissão excluem rescisórias). Opcional para
    # retrocompatibilidade; quando ausente, nenhuma exclusão é aplicada.
    modalidade_rescisao: Optional[
        Literal[
            "sem_justa_causa", "justa_causa", "pedido_demissao",
            "rescisao_indireta", "termino_contrato", "acordo", "outro",
        ]
    ] = None
    prescricao_quinquenal: bool = True
    prescricao_fgts: bool = False
    tipo_base_tabelada: TipoBaseTabelada = TipoBaseTabelada.INTEGRAL
    valor_maior_remuneracao_brl: float = Field(ge=0)
    valor_ultima_remuneracao_brl: float = Field(ge=0)
    apuracao_aviso_previo: ApuracaoAvisoPrevio
    # Dias do aviso prévio (obrigatório quando apuracao_aviso_previo=APURACAO_INFORMADA).
    # Lei 12.506/2011: 30 dias base + 3 dias por ano trabalhado, limite 90 dias.
    prazo_aviso_previo_dias: Optional[int] = None
    projeta_aviso_indenizado: bool = True
    limitar_avos: bool = False
    zerar_valor_negativo: bool = True
    considerar_feriado_estadual: bool = True
    considerar_feriado_municipal: bool = True
    carga_horaria: CargaHoraria = Field(default_factory=CargaHoraria)
    sabado_dia_util: bool = False
    excecoes_sabado: list[ExcecaoSabado] = Field(default_factory=list)
    pontos_facultativos_codigo: list[int] = Field(default_factory=list)
    justica_gratuita: JusticaGratuita = Field(default_factory=JusticaGratuita)
    """Concessão de JG (true/false por parte). Auto-build de comentarios_jg
    quando há sucumbenciais contra parte beneficiária."""
    comentarios_jg: Optional[str] = None
    """Override manual do texto. Quando null, normalizer auto-gera a partir
    de justica_gratuita + honorarios[]. Quando preenchido, sobrescreve."""


# ─── 3. Histórico Salarial ────────────────────────────────────────────────


class HistoricoSalarialIncidencias(BaseModel):
    fgts: bool = True
    cs_inss: bool = True


class HistoricoSalarialCalculado(BaseModel):
    quantidade_pct: float
    base_referencia: str


class EvolucaoValor(BaseModel):
    """Mudança de valor em uma competência específica dentro do MESMO componente.

    Usado em `HistoricoSalarial.evolucao` quando o componente salarial mantém
    a mesma natureza (ex.: SALÁRIO BASE) ao longo do contrato mas o VALOR
    varia (dissídios, reajustes negociados).

    Cada item representa: "a partir desta competência, o valor passa a ser X".
    O bot mapeia cada ocorrência mensal do histórico para o EvolucaoValor mais
    recente cuja `competencia ≤ data_ocorrencia`, e edita o valor da ocorrência.
    """
    competencia: str  # MM/YYYY — a partir desta competência o novo valor vigora
    valor_brl: float  # novo valor em reais


class HistoricoSalarial(BaseModel):
    nome: str
    parcela: TipoVariacaoParcela = TipoVariacaoParcela.FIXA
    incidencias: HistoricoSalarialIncidencias
    competencia_inicial: str  # MM/YYYY
    competencia_final: str  # MM/YYYY
    tipo_valor: TipoValor
    valor_brl: Optional[float] = None
    calculado: Optional[HistoricoSalarialCalculado] = None
    evolucao: Optional[list[EvolucaoValor]] = None
    # Quando preenchido: o MESMO componente tem valores diferentes ao longo
    # do período total. O bot cria UMA linha no PJE-Calc com valor_brl como
    # base, depois edita ocorrências mensais conforme o array `evolucao`.
    # Use APENAS quando todas as variações são do MESMO componente lógico
    # (ex.: SALÁRIO BASE com reajustes). Para COMPONENTES DIFERENTES (salário
    # + adicional), emita entradas separadas — cada uma pode ter sua evolução.

    @model_validator(mode="after")
    def _check_tipo_valor(self) -> "HistoricoSalarial":
        if self.tipo_valor == TipoValor.INFORMADO and self.valor_brl is None:
            raise ValueError("Histórico INFORMADO exige valor_brl")
        if self.tipo_valor == TipoValor.CALCULADO and self.calculado is None:
            raise ValueError("Histórico CALCULADO exige campo `calculado`")
        if self.evolucao and self.tipo_valor == TipoValor.CALCULADO:
            raise ValueError(
                "Histórico CALCULADO não admite `evolucao` — PJE-Calc resolve o valor "
                "por competência via tabela (SM, piso). Use evolucao apenas com INFORMADO."
            )
        if self.evolucao:
            for ev in self.evolucao:
                if ev.valor_brl is None or ev.valor_brl <= 0:
                    raise ValueError(f"evolucao[].valor_brl deve ser > 0 (got {ev.valor_brl})")
        return self


# ─── 4. Verbas Principais ─────────────────────────────────────────────────


class AssuntoCNJ(BaseModel):
    # codigo é Optional: pode vir null quando o agente externo não sabe ou
    # quando a verba não exige código específico (ex.: Saldo de Salário,
    # Aviso Prévio, Férias, 13º — verbas trabalhistas padrão).
    # Default 2581 (Remuneração, Verbas Indenizatórias e Benefícios) é
    # aplicado pelo bot quando codigo é None — categoria mais ampla que
    # cobre a maior parte das verbas trabalhistas.
    codigo: Optional[int] = None
    label: str = ""


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
    """Espelho do bloco 'Base de Cálculo' da Fórmula CALCULADO em verba-calculo.xhtml.

    Campos sub-bloco condicionais por `tipo`:
      - HISTORICO_SALARIAL → `historico_nome` (qual histórico salarial usar)
      - VALE_TRANSPORTE → `vale_transporte_nome` (qual VT cadastrado)
      - SALARIO_DA_CATEGORIA → `salario_categoria_nome` (qual piso)
      - MAIOR_REMUNERACAO / SALARIO_MINIMO → nenhum sub-campo
    """
    tipo: TipoBaseCalculo
    historico_nome: Optional[str] = None
    vale_transporte_nome: Optional[str] = None
    salario_categoria_nome: Optional[str] = None
    proporcionaliza: Optional[SimNao] = None
    bases_compostas: list[BaseComposta] = Field(default_factory=list)


class DivisorVerba(BaseModel):
    """Espelho do bloco 'Divisor' da Fórmula CALCULADO.

    Sub-campos condicionais:
      - OUTRO_VALOR → `valor` (float obrigatório)
      - IMPORTADA_DO_CARTAO → `tipo_cartao_ponto` (qual coluna/cartão usar)
    """
    tipo: TipoDivisor = TipoDivisor.OUTRO_VALOR
    valor: Optional[float] = None
    tipo_cartao_ponto: Optional[str] = None


class QuantidadeVerba(BaseModel):
    """Quantidade na fórmula CALCULADO.

    Sub-campos condicionais:
      - INFORMADA → `valor` (float; também aceita `valor_mensal` como alias legado)
      - IMPORTADA_DO_CALENDARIO → `tipo_importada_calendario` (qual coluna calendário)
      - IMPORTADA_DO_CARTAO → `tipo_cartao_ponto`

    Tolerância: se `tipo=INFORMADA` mas `valor=None`, normalizamos para 0.
    """
    tipo: TipoQuantidade = TipoQuantidade.INFORMADA
    valor: Optional[float] = 1.0
    proporcionalizar: bool = False
    tipo_importada_calendario: Optional[str] = None
    tipo_cartao_ponto: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _alias_valor_mensal(cls, data):
        # INVARIANTE PERMANENTE — alias valor_mensal (NÃO REVERTER).
        # Bug THAÍS 10/06/2026: prompt ensinava `valor_mensal`, schema só lia
        # `valor` (default 1.0) → quantidade 20 do SALDO DE SALÁRIO virou 1
        # silenciosamente (R$ 1.614,79 → R$ 53,83). Aceitar ambos os nomes.
        if isinstance(data, dict) and data.get("valor") is None:
            vm = data.get("valor_mensal")
            if vm is not None:
                data = {**data, "valor": vm}
        return data

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
    """Espelho do bloco 'Valor Pago' da página verba-calculo.xhtml.

    Visível somente quando a verba é `valor=CALCULADO` (bloco aparece após
    a fórmula). Tem dois modos:

    - **INFORMADO**: usuário digita `valor_brl` direto (valor já recebido pelo
      reclamante a título da verba).
    - **CALCULADO**: o sistema apura o pago a partir de um histórico salarial
      cadastrado (paradigma) — útil em equiparação salarial. Sub-campos:
        - `base_tipo`: HISTORICO_SALARIAL / MAIOR_REMUNERACAO / SALARIO_MINIMO /
          SALARIO_DA_CATEGORIA / VALE_TRANSPORTE
        - `base_historico_nome`: quando base_tipo=HISTORICO_SALARIAL
        - `base_vale_transporte_nome`: quando base_tipo=VALE_TRANSPORTE
        - `base_salario_categoria_nome`: quando base_tipo=SALARIO_DA_CATEGORIA
        - `proporcionaliza_historico`: SIM/NAO (apenas para HISTORICO_SALARIAL)
        - `quantidade_brl`: Quantidade do Valor Pago (multiplicador aplicado
          sobre a base, ex.: número de horas pagas)
    """
    tipo: TipoValor = TipoValor.INFORMADO
    valor_brl: float = 0.0
    proporcionalizar: bool = False
    # ── sub-campos quando tipo=CALCULADO ─────────────────────────────────
    base_tipo: Optional[TipoBaseCalculo] = None
    base_historico_nome: Optional[str] = None
    base_vale_transporte_nome: Optional[str] = None
    base_salario_categoria_nome: Optional[str] = None
    proporcionaliza_historico: Optional[SimNao] = None
    quantidade_brl: Optional[float] = None

    @field_validator("valor_brl", mode="before")
    @classmethod
    def _valor_brl_none_para_zero(cls, v):
        """valor_pago CALCULADO (base sobre histórico) emite valor_brl=null —
        o valor é apurado pelo PJE-Calc a partir do histórico, não digitado.
        Coerce None→0.0 (o bot usa base_historico_nome, não valor_brl, em
        modo CALCULADO). Caso Ariane DIFERENÇA SALARIAL (13/06/2026)."""
        return 0.0 if v is None else v


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
    model_config = ConfigDict(extra="ignore")  # ignora chaves desconhecidas que IA possa colocar

    modo: Literal["alteracao_em_lote", "valores_mensais"] = "alteracao_em_lote"
    valores_mensais: list[OcorrenciaMensalOverride] = Field(default_factory=list)
    # quando modo=alteracao_em_lote, usar campos do verba.parametros.valor_devido

    @model_validator(mode="before")
    @classmethod
    def _aceitar_formato_legado(cls, data):
        """Tolerância: a IA frequentemente confunde verba.ocorrencias_override
        (objeto com modo+valores_mensais) com cartao_de_ponto.ocorrencias_override
        (lista de OcorrenciaJornada {data, turnos}). Quando vier uma lista
        com itens contendo 'data' + 'turnos' (formato do cartão), descarta
        — esses overrides pertencem ao cartao_de_ponto, não à verba.
        Quando vier lista vazia, normaliza para objeto default."""
        if isinstance(data, list):
            if not data:
                return {}  # lista vazia → default
            primeiro = data[0] if data else {}
            if isinstance(primeiro, dict) and "turnos" in primeiro:
                # formato cartão de ponto colocado por engano aqui
                return {}  # descarta — deveria estar em cartao_de_ponto
            # Lista de items com {mes, valor_devido,...}? Tratar como valores_mensais
            if isinstance(primeiro, dict) and ("mes" in primeiro or "valor_devido" in primeiro):
                return {"modo": "valores_mensais", "valores_mensais": data}
            return {}
        return data
    # (não há campos extras aqui)


# ─── Tabela detalhada de Ocorrências (Fase 2 — espelho parametrizar-ocorrencia.jsf) ──


class LinhaOcorrencia(BaseModel):
    """Uma linha da tabela mensal de Ocorrências da verba.

    Espelha as colunas da página parametrizar-ocorrencia.jsf (manual §9.9):
    Ativo?, Data Inicial, Data Final, Valor (CALCULADO/INFORMADO),
    Divisor, Multiplicador, Quantidade, Dobra, Devido, Pago.

    Cada ocorrência = 1 mês calendário, gerada automaticamente pelo
    PJE-Calc com base em (Período × Ocorrência de Pagamento).
    """
    model_config = ConfigDict(extra="allow")

    ativo: bool = True
    data_inicial: str  # DD/MM/YYYY
    data_final: str    # DD/MM/YYYY
    valor: TipoValor = TipoValor.CALCULADO
    divisor: Optional[float] = None
    multiplicador: Optional[float] = None
    quantidade: Optional[float] = None
    proporcionalizar_quantidade: bool = False
    dobra: bool = False
    devido_brl: Optional[float] = None   # quando valor=CALCULADO: o sistema calcula
    proporcionalizar_devido: bool = False
    pago_brl: float = 0.0
    proporcionalizar_pago: bool = False


class AlteracaoEmLote(BaseModel):
    """Bloco "Alteração em Lote" do topo da página de Ocorrências.

    Permite aplicar um conjunto de valores a TODAS as linhas dentro de um
    intervalo de datas, clicando "Alterar". Use quando o sentenciado tem
    valor uniforme em um sub-período (ex.: "férias 30 dias × 1,33").
    """
    model_config = ConfigDict(extra="allow")

    data_inicial: Optional[str] = None
    data_final: Optional[str] = None
    divisor: Optional[float] = None
    multiplicador: Optional[float] = None
    quantidade: Optional[float] = None
    proporcionalizar_quantidade: bool = False
    dobra: bool = False
    devido_brl: Optional[float] = None
    proporcionalizar_devido: bool = False
    pago_brl: Optional[float] = None
    proporcionalizar_pago: bool = False


class TabelaOcorrenciasMensais(BaseModel):
    """Tabela de Ocorrências da verba (página parametrizar-ocorrencia.jsf).

    Modo de uso:
    - `alteracoes_em_lote`: 0+ blocos a aplicar via header "Alteração em Lote"
      (mais eficiente quando o valor é uniforme em sub-período)
    - `linhas`: override mês a mês de linhas específicas (use quando ≥ 1
      ocorrência tem valor distinto da regra do lote)
    - `regerar_ao_abrir`: clicar "Regerar Ocorrências" antes de editar
      (necessário quando parâmetros da verba foram alterados)

    Os dois modos podem coexistir: lote define o padrão, linhas sobrescrevem
    exceções específicas.
    """
    model_config = ConfigDict(extra="allow")

    regerar_ao_abrir: bool = False
    sobrescrever_ao_regerar: bool = False  # "Manter alterações" vs "Sobrescrever"
    alteracoes_em_lote: list[AlteracaoEmLote] = Field(default_factory=list)
    linhas: list[LinhaOcorrencia] = Field(default_factory=list)


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
    juros_aplicar_sumula_439: bool = False  # "Juros - Aplicar Súmula nº 439 do TST"
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
        # Pular validação quando valor não foi especificado (modo Expresso
        # SEM customização — PJE-Calc usa defaults). Mas avisar via log se
        # alguma indicação de override está presente sem valor.
        if self.valor is None:
            return self
        # Tolerância benigna: LLM gerou valor=CALCULADO sem fórmula MAS tem
        # valor_informado_brl → normaliza para INFORMADO (provável engano).
        if (
            self.valor == TipoValor.CALCULADO
            and self.formula_calculado is None
            and isinstance(self.valor_devido, ValorDevidoInformado)
            and self.valor_devido.valor_informado_brl is not None
        ):
            self.valor = TipoValor.INFORMADO

        # CONSISTÊNCIA RÍGIDA — bloqueia liquidação errada por verba
        # mal-preenchida no JSON. Erros mais comuns observados em produção:
        #   1. valor=INFORMADO sem valor_devido.valor_informado_brl > 0
        #      → PJE-Calc fica com "Devido = 0,00" e pendência na liquidação
        #   2. valor=CALCULADO sem formula_calculado completo
        #      → PJE-Calc não consegue calcular, verba zerada
        if self.valor == TipoValor.INFORMADO:
            if not isinstance(self.valor_devido, ValorDevidoInformado) or not self.valor_devido.valor_informado_brl:
                raise ValueError(
                    "ParametrosVerba: valor=INFORMADO exige "
                    "`valor_devido.valor_informado_brl > 0`. "
                    "Aplicar mensalização (§4.4.bis do prompt) se a sentença "
                    "fixar valor diário/semanal."
                )
        elif self.valor == TipoValor.CALCULADO:
            f = self.formula_calculado
            if f is None:
                raise ValueError(
                    "ParametrosVerba: valor=CALCULADO exige `formula_calculado` "
                    "preenchido com base_calculo, divisor, multiplicador, quantidade. "
                    "Se a sentença não fornecer fórmula explícita, use "
                    "valor=INFORMADO com valor_informado_brl mensalizado."
                )
            if f.base_calculo is None or f.base_calculo.tipo is None:
                raise ValueError(
                    "ParametrosVerba: formula_calculado.base_calculo.tipo é obrigatório "
                    "quando valor=CALCULADO. Use um dos enums: MAIOR_REMUNERACAO, "
                    "HISTORICO_SALARIAL, SALARIO_DA_CATEGORIA, SALARIO_MINIMO, "
                    "VALE_TRANSPORTE."
                )
            if f.quantidade is None or f.quantidade.tipo is None:
                raise ValueError(
                    "ParametrosVerba: formula_calculado.quantidade.tipo é obrigatório "
                    "quando valor=CALCULADO. Use um dos enums: INFORMADA, "
                    "IMPORTADA_DO_CALENDARIO, IMPORTADA_DO_CARTAO, AVOS, APURADA."
                )
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
    # Override "antigo" (modo simples — lote ou mensal genérico)
    ocorrencias_override: Optional[OcorrenciasOverride] = None
    # Override "detalhado" (Fase 2 — espelha parametrizar-ocorrencia.jsf)
    tabela_ocorrencias: Optional[TabelaOcorrenciasMensais] = None
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


class CartaoDePontoApuracao(BaseModel):
    """Critérios de apuração de HE — mapeado para tipoApuracaoHorasExtras no DOM."""
    tipo: str = "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL"
    # Valores: NAO_APURAR_HORAS_EXTRAS | HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA |
    # HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL | HORAS_EXTRAS_CONFORME_SUMULA_85 |
    # APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO | HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL |
    # HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL
    qtsumulatst: Optional[str] = None       # HH:MM — para SUMULA_85 (default "02:00")
    qthoraseparado: Optional[str] = None    # HH:MM — para PRIMEIRAS_HE_EM_SEPARADO


class CartaoDePontoJornada(BaseModel):
    """Jornada diária padrão por dia da semana (HH:MM) + totais semanal/mensal."""
    segunda_hhmm: str = "08:00"
    terca_hhmm: str = "08:00"
    quarta_hhmm: str = "08:00"
    quinta_hhmm: str = "08:00"
    sexta_hhmm: str = "08:00"
    sabado_hhmm: str = "00:00"
    domingo_hhmm: str = "00:00"
    jornada_semanal: Optional[str] = None       # ex.: "44,00" → qtJornadaSemanal
    jornada_mensal_media: Optional[str] = None  # ex.: "188,57" → qtJornadaMensal


class CartaoDePontoDescanso(BaseModel):
    """Períodos de descanso — seções Descanso + Interjornadas + Intrajornada."""
    # Descanso semanal
    apurar_feriados_trabalhados: bool = False
    apurar_domingos_trabalhados: bool = False
    apurar_sabados_domingos: bool = False
    # Intervalos especiais (Art. 384, 72, 253 CLT)
    apurar_intervalo_384: bool = False
    apurar_intervalo_72: bool = False
    apurar_intervalo_insalubridade: bool = False
    tempo_trabalho_art253: str = "01:40"
    tempo_descanso_art253: str = "00:20"
    # Interjornadas
    descanso_entre_jornadas: bool = False
    valor_descanso_entre_jornadas: str = "11:00"   # select: 10:00|11:00|12:00|14:00|17:00
    valor_descanso_entre_semanas: str = "35:00"    # select: 35:00|11:00
    # Intrajornada >4h até 6h
    intervalo_sup_4h_6h: bool = False
    tolerancia_sup_4h_6h: str = "00:15"
    # Intrajornada >6h
    intervalo_sup_6h: bool = False
    valor_intervalo_sup_6h: str = "01:00"
    tolerancia_sup_6h: str = "00:05"
    # Outros intrajornada
    considerar_fracionamento: bool = False
    apurar_supressao_integral: bool = False
    apurar_supressao_reforma: bool = False          # §4º Art. 71 CLT
    apurar_excesso_sumula118: bool = False
    valor_intervalo_max_sumula118: str = "02:00"
    apurar_apenas_excesso_jornada: bool = False


class CartaoDePontoNoturno(BaseModel):
    """Horário noturno."""
    tipo_atividade: str = "ATIVIDADE_URBANA"  # ATIVIDADE_AGRICOLA|ATIVIDADE_PECUARIA|ATIVIDADE_URBANA
    apurar_horas_noturnas: bool = False
    apurar_horas_extras_noturnas: bool = False
    reducao_ficta: bool = True                      # default ligado no PJE-Calc
    horario_prorrogado_sumula60: bool = False
    forcar_prorrogacao: bool = False


class TurnoJornada(BaseModel):
    """Par entrada/saída de um turno (até 6 turnos por dia).

    Use HH:MM (ex: "07:00", "12:00"). String vazia "" = turno não trabalhado.
    """
    entrada: str = ""
    saida: str = ""


class JornadaDiaria(BaseModel):
    """Jornada de um dia (até 6 turnos entrada/saída).

    Exemplo seg-sex 7h-12h e 13h-18h (com 1h almoço):
        turnos = [{entrada:"07:00", saida:"12:00"}, {entrada:"13:00", saida:"18:00"}]
    """
    turnos: list[TurnoJornada] = Field(default_factory=list, max_length=6)


class ProgramacaoSemanal(BaseModel):
    """Programação semanal — jornadas por dia da semana + feriado.

    Mapeamento DOM (formulario:listagemProgramacao:N:entradaM/saidaM):
        N=0 → segunda, N=1 → terça, ..., N=6 → domingo, N=7 → feriado
        M=1..6 → turno 1..6

    Quando preenchimento="PROGRAMACAO", o PJE-Calc auto-replica essas jornadas
    para todas as semanas do período do cartão. Não trabalha = turnos vazios.
    """
    segunda:  JornadaDiaria = Field(default_factory=JornadaDiaria)
    terca:    JornadaDiaria = Field(default_factory=JornadaDiaria)
    quarta:   JornadaDiaria = Field(default_factory=JornadaDiaria)
    quinta:   JornadaDiaria = Field(default_factory=JornadaDiaria)
    sexta:    JornadaDiaria = Field(default_factory=JornadaDiaria)
    sabado:   JornadaDiaria = Field(default_factory=JornadaDiaria)
    domingo:  JornadaDiaria = Field(default_factory=JornadaDiaria)
    feriado:  JornadaDiaria = Field(default_factory=JornadaDiaria)


class TipoEscala(str, Enum):
    """Tipos pré-cadastrados de escala no PJE-Calc.

    OUTRA = escala custom (preenche tabela manualmente).
    """
    OUTRA                     = "OUTRA"
    DOZE_POR_DOZE             = "DOZE_POR_DOZE"
    DOZE_POR_VINTE_QUATRO     = "DOZE_POR_VINTE_QUATRO"
    DOZE_POR_TRINTA_E_SEIS    = "DOZE_POR_TRINTA_E_SEIS"
    DOZE_POR_QUARENTA_E_OITO  = "DOZE_POR_QUARENTA_E_OITO"
    CINCO_POR_UM              = "CINCO_POR_UM"
    SEIS_POR_UM               = "SEIS_POR_UM"
    OITO_DOIS                 = "OITO_DOIS"


class EscalaCartao(BaseModel):
    """Escala de trabalho — usar quando o ciclo NÃO é semanal.

    DOM:
      - formulario:escalas          → tipo
      - formulario:valorHoraInicioEscala → inicio (DD/MM/YYYY)
      - formulario:qtdDiasTrabalhados    → quantidade_dias (1..N)
      - formulario:listagemEscala:D:entradaM/saidaM → jornadas[D].turnos[M-1]
    """
    tipo: TipoEscala = TipoEscala.OUTRA
    inicio: str                                 # DD/MM/YYYY — data do dia 1 do ciclo
    quantidade_dias: int = Field(ge=1, default=1)
    jornadas: list[JornadaDiaria] = Field(default_factory=list)


class OcorrenciaJornada(BaseModel):
    """Override manual de jornada em uma data específica (Grade de Ocorrências).

    Use para JORNADAS IRREGULARES que não cabem em ProgramaçãoSemanal/Escala —
    p. ex.: sábados ALTERNADOS, semanas com plantão extraordinário, etc.

    Após o PJE-Calc preencher os defaults via Programação/Escala, esses overrides
    são aplicados na tela `visualizar-ocorrencias.jsf` (Grade de Ocorrências) por
    mês, sobrescrevendo o lançamento daquele dia específico.

    turnos=[] significa "apagar todos os turnos do dia" (dia não trabalhado).
    """
    data: str                                   # DD/MM/YYYY
    turnos: list[TurnoJornada] = Field(default_factory=list, max_length=6)


class CartaoDePonto(BaseModel):
    """Cartão de Ponto — espelha o formulário Novo do PJE-Calc Cidadão v2.15.1.

    Mapeamento DOM: formulario:<campo> em cartaodeponto/apuracao-cartaodeponto.jsf
    """
    model_config = ConfigDict(extra="allow")

    # Período
    data_inicial: str                               # DD/MM/YYYY
    data_final: str                                 # DD/MM/YYYY

    # Formas de apuração
    apuracao: CartaoDePontoApuracao = Field(default_factory=CartaoDePontoApuracao)

    # Considerar Feriados
    considerar_feriados: bool = True
    extras_feriados_separado: bool = False
    extras_domingos_separado: bool = False
    extras_sabados_domingos_separado: bool = False

    # Tolerância geral
    tolerancia_ativa: bool = False
    tolerancia_por_turno: str = "00:05"
    tolerancia_por_dia: str = "00:10"

    # Jornada padrão (metadados gerais)
    jornada_padrao: CartaoDePontoJornada = Field(default_factory=CartaoDePontoJornada)

    # Jornada em feriados
    jornada_feriado_trabalhado: bool = False
    jornada_feriado_nao_trabalhado: bool = False

    # Períodos de descanso (seção Períodos de Descanso + Intervalo)
    descanso: Optional[CartaoDePontoDescanso] = None

    # Horário noturno
    noturno: Optional[CartaoDePontoNoturno] = None

    # Preenchimento de jornadas — controla qual modo de preenchimento usar
    preenchimento: str = "LIVRE"  # LIVRE | PROGRAMACAO | ESCALA

    # Tabela de jornadas (depende de `preenchimento`)
    programacao_semanal: Optional[ProgramacaoSemanal] = None  # se preenchimento=PROGRAMACAO
    escala: Optional[EscalaCartao] = None                     # se preenchimento=ESCALA

    # Overrides manuais por data (Grade de Ocorrências) — jornadas IRREGULARES
    ocorrencias_override: list[OcorrenciaJornada] = Field(default_factory=list)


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
    # Concessivo é opcional: para o período proporcional final (do último ano
    # da relação trabalhista) o período concessivo NÃO existe ainda — a
    # rescisão acontece antes. PJE-Calc aceita período concessivo vazio.
    periodo_concessivo_inicio: Optional[str] = None
    periodo_concessivo_fim: Optional[str] = None
    prazo_dias: int = 30
    situacao: Literal["INDENIZADAS", "GOZADAS", "PARCIAL_GOZADAS", "NAO_DIREITO"] = "INDENIZADAS"
    dobra: bool = False
    abono: bool = False
    dias_abono: int = 0
    gozo_1: Optional[GozoFerias] = None
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


class SaldoFGTSADeduzir(BaseModel):
    """Saldo do FGTS a deduzir (campo 'Saldo e/ou Saque' da página FGTS).

    Representa valor já depositado na conta vinculada do empregado que deve
    ser deduzido do que está sendo calculado. Diferente de
    `recolhimentos_existentes` (tabela de depósitos por competência), este é
    um único par data+valor (snapshot do extrato FGTS).

    Após preenchido, o checkbox 'Deduzir do FGTS' deve estar marcado.
    """
    data: str  # DD/MM/YYYY — data do extrato FGTS ou última atualização
    valor_brl: float = Field(ge=0)  # saldo total a deduzir


class FGTS(BaseModel):
    model_config = ConfigDict(extra="allow")
    tipo_verba: Literal["PAGAR", "DEPOSITAR"] = "PAGAR"
    compor_principal: SimNao = SimNao.SIM
    multa: FGTSMulta = Field(default_factory=FGTSMulta)
    incidencia: str = "SOBRE_O_TOTAL_DEVIDO"
    multa_artigo_467: bool = False
    multa_10_lc110: bool = False
    contribuicao_social: bool = False
    incidencia_pensao_alimenticia: bool = False
    recolhimentos_existentes: list[RecolhimentoFGTS] = Field(default_factory=list)
    # Saldo FGTS já depositado na conta vinculada — vai na seção
    # "Saldo e/ou Saque" da página FGTS, com checkbox "Deduzir do FGTS" marcado.
    # NÃO é uma verba Expresso "VALOR PAGO" (que é classificação incorreta).
    saldos_a_deduzir: list[SaldoFGTSADeduzir] = Field(default_factory=list)
    deduzir_do_fgts: bool = False  # marca o checkbox "Deduzir do FGTS"


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

    @model_validator(mode="after")
    def _exigir_aliquota_ou_valor(self) -> "Honorario":
        """PJE-Calc bloqueia liquidação quando honorário CALCULADO não tem
        alíquota OU honorário INFORMADO não tem valor. Rejeitar a prévia
        aqui evita falha tardia na automação."""
        if self.tipo_valor == TipoValor.CALCULADO and self.aliquota_pct is None:
            raise ValueError(
                f"Honorário {self.tipo_honorario}/{self.tipo_devedor} CALCULADO "
                "requer 'aliquota_pct' (percentual da sentença, ex: 0.15 para 15%)."
            )
        if self.tipo_valor == TipoValor.INFORMADO and not self.valor_informado_brl:
            raise ValueError(
                f"Honorário {self.tipo_honorario}/{self.tipo_devedor} INFORMADO "
                "requer 'valor_informado_brl' > 0."
            )
        return self


class CustasJudiciais(BaseModel):
    model_config = ConfigDict(extra="allow")  # tolera valor_informado_brl, base_calculo_informada_brl
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


# ─── Seções até agora subdimensionadas (schema=dict) — agora tipadas ─────


class VariacaoSalarioFamilia(BaseModel):
    """Variação na quantidade de filhos < 14 anos ao longo do contrato.

    PJE-Calc permite registrar mudanças: filho nascido, completou 14 anos, etc.
    """
    data_inicio: str  # DD/MM/YYYY
    quantidade_filhos: int


class SalarioFamilia(BaseModel):
    """Espelha página salario-familia.xhtml. Quando o JSON omitir = `null`,
    a fase é pulada e os defaults do PJE-Calc valem (apurar=False).
    Preencher apenas quando a sentença determinar a apuração.
    """
    apurar: bool = True
    compor_principal: bool = True
    quantidade_filhos_menores_14: int = 0
    tipo_salario_pago: Optional[Literal["NENHUM", "MAIOR_REMUNERACAO", "HISTORICO_SALARIAL"]] = None
    variacoes: list[VariacaoSalarioFamilia] = Field(default_factory=list)
    historico_salarial_nomes: list[str] = Field(default_factory=list)  # nomes das bases que compõem a remuneração mensal
    salarios_devidos_verbas: list[str] = Field(default_factory=list)  # nomes das verbas que compõem a remuneração mensal


class SeguroDesemprego(BaseModel):
    """Espelha página seguro-desemprego.xhtml."""
    apurar: bool = True
    apurar_empregado_domestico: bool = False
    compor_principal: bool = True
    numero_parcelas: Optional[int] = None
    solicitacao: Optional[Literal["PRIMEIRA", "SEGUNDA", "DEMAIS"]] = None
    tipo_valor: Optional[Literal["INFORMADO", "CALCULADO"]] = None
    valor_informado_brl: Optional[float] = None
    tipo_salario_pago: Optional[Literal["NENHUM", "MAIOR_REMUNERACAO", "HISTORICO_SALARIAL"]] = None
    historico_salarial_nomes: list[str] = Field(default_factory=list)
    salarios_devidos_verbas: list[str] = Field(default_factory=list)


class AliquotaPrevidenciaPeriodo(BaseModel):
    """Período de alíquota de Previdência Privada (pode haver múltiplos)."""
    aliquota_pct: float = Field(gt=0)
    data_inicio: str  # DD/MM/YYYY
    data_fim: Optional[str] = None


class PrevidenciaPrivada(BaseModel):
    """Espelha página previdencia-privada.xhtml.

    A base é definida nos Parâmetros das Verbas (checkbox
    Incidência Previdência Privada). Aqui só configura alíquotas e períodos.
    """
    apurar: bool = True
    aliquotas: list[AliquotaPrevidenciaPeriodo] = Field(default_factory=list)


class PensaoAlimenticia(BaseModel):
    """Espelha página pensao-alimenticia.xhtml.

    A base é definida nos Parâmetros das Verbas (checkbox
    Incidência Pensão Alimentícia).
    """
    apurar: bool = True
    aliquota_pct: float = Field(default=0.0, ge=0)
    incidir_sobre_juros: bool = False


class MultaIndenizacao(BaseModel):
    """Espelha página multas-indenizacoes.xhtml — item individual.

    Cada multa/indenização gerada por aviso/sentença que NÃO é verba
    trabalhista típica (essas vão em verbas_principais). Ex.: multa por
    descumprimento de obrigação, indenização por bem perdido.
    """
    descricao: str
    credor_devedor: Literal[
        "RECLAMANTE_RECLAMADO",  # credor=reclamante, devedor=reclamado (default)
        "RECLAMADO_RECLAMANTE",  # credor=reclamado, devedor=reclamante (sucumbência reversa)
        "TERCEIRO_RECLAMANTE",   # credor=terceiro, devedor=reclamante
        "TERCEIRO_RECLAMADO",    # credor=terceiro, devedor=reclamado
    ] = "RECLAMANTE_RECLAMADO"
    terceiro_nome: Optional[str] = None
    tipo_valor: Literal["CALCULADO", "INFORMADO"] = "INFORMADO"
    # CALCULADO
    aliquota_pct: Optional[float] = None
    tipo_base: Optional[Literal["PRINCIPAL", "PRINCIPAL_MENOS_CS", "PRINCIPAL_MENOS_CS_MENOS_PP"]] = None
    # INFORMADO
    valor_brl: Optional[float] = None
    data_vencimento: Optional[str] = None  # DD/MM/YYYY
    # Comuns
    correcao_monetaria: Literal["INDICE_TRABALHISTA", "OUTRO_INDICE"] = "INDICE_TRABALHISTA"
    outro_indice_correcao: Optional[str] = None
    aplicar_juros: bool = True
    data_juros_a_partir_de: Optional[str] = None  # DD/MM/YYYY
    tipo_cobranca_reclamante: Optional[Literal["COBRAR", "DESCONTAR"]] = None
    identificacao: Optional[str] = None  # ID do documento judicial

    @model_validator(mode="after")
    def _check_value_consistency(self) -> "MultaIndenizacao":
        if self.tipo_valor == "CALCULADO":
            if self.aliquota_pct is None or self.tipo_base is None:
                raise ValueError(
                    "MultaIndenizacao CALCULADO requer aliquota_pct + tipo_base"
                )
        else:  # INFORMADO
            if not self.valor_brl or self.valor_brl <= 0:
                raise ValueError(
                    "MultaIndenizacao INFORMADO requer valor_brl > 0"
                )
        return self


# ─── Correção, Juros e Multa (expandido) ──────────────────────────────────


class CorrecaoFGTS(BaseModel):
    """Sub-bloco FGTS em correcao_juros_multa (página liquidacao.xhtml)."""
    indice_correcao: Literal[
        "UTILIZAR_INDICE_TRABALHISTA",
        "UTILIZAR_INDICE_JAM",
        "UTILIZAR_INDICE_JAM_E_TRABALHISTA",
    ] = "UTILIZAR_INDICE_TRABALHISTA"


class CorrecaoPrevidenciaPrivada(BaseModel):
    """Sub-bloco Previdência Privada em correcao_juros_multa."""
    indice: Literal["INDICE_TRABALHISTA", "OUTRO_INDICE"] = "INDICE_TRABALHISTA"
    outro_indice: Optional[str] = None
    aplicar_juros: bool = False


class CorrecaoCustasJudiciais(BaseModel):
    """Sub-bloco Custas Judiciais em correcao_juros_multa."""
    indice: Optional[Literal["INDICE_TRABALHISTA", "OUTRO_INDICE"]] = None
    outro_indice: Optional[str] = None
    aplicar_juros: bool = False


class CorrecaoCS(BaseModel):
    """Atualização de CS sobre salários devidos/pagos.

    PJE-Calc oferece duas opções (que podem coexistir):
    - Trabalhista: correção pelo índice trabalhista, juros a partir do
      dia 2 do mês seguinte à liquidação.
    - Previdenciária: UFIR + SELIC desde a prestação do serviço.
    """
    trabalhista: bool = True
    previdenciaria: bool = False
    multa_previdenciaria_tipo: Optional[Literal["URBANA", "RURAL"]] = None
    multa_previdenciaria_modo: Optional[Literal["INTEGRAL", "REDUZIDO"]] = None


class FaseJuros(BaseModel):
    """Uma fase de juros — empilhável no botão '+' do PJE-Calc.

    Modelo jurídico ADC 58 + TST E-ED-RR-20407-32.2015.5.04.0271 + Lei 14.905/2024
    requer até 3 fases consecutivas:
      1. Pré-judicial: TAXA_LEGAL (art. 39 Lei 8.177)
      2. Ajuizamento → 29/08/2024: SELIC
      3. 30/08/2024 em diante: TAXA_LEGAL (= SELIC − IPCA, conforme CC art. 406
         pós Lei 14.905/2024)

    Cada FaseJuros vira uma linha no "Combinar com Outra Tabela de Juros"
    do PJE-Calc.
    """
    data_inicio: str
    """DD/MM/YYYY. Para a primeira fase (pré-judicial), usar string vazia
    "" ou a data_inicio_calculo."""
    tabela: Literal[
        "TAXA_LEGAL", "JUROS_PADRAO", "JUROS_POUPANCA", "JUROS_MEIO_PORCENTO",
        "JUROS_UM_PORCENTO", "JUROS_ZERO_TRINTA_TRES", "SELIC", "SELIC_FAZENDA",
        "SELIC_BACEN", "FAZENDA_PUBLICA", "SEM_JUROS", "TRD_SIMPLES", "TRD_COMPOSTOS",
    ]
    """Enum do PJE-Calc para a tabela de juros desta fase."""
    descricao: Optional[str] = None
    """Anotação livre (ex.: 'Fase pré-judicial — art. 39 Lei 8.177'). Não vai ao DOM."""


class CorrecaoJurosMulta(BaseModel):
    """Espelha página liquidacao.xhtml (Correção, Juros e Multa).

    Modelo expandido com TODOS os campos do JSF (antes era apenas 3).
    """

    model_config = ConfigDict(extra="allow")

    # Aba "Dados Gerais"
    indice_trabalhista: str = "IPCAE"
    """Tabela_Unica_JTDiario | Tabela_Unica_JTMensal | TR | IGP-M | INPC | IPC | IPCA | IPCAE | IPCAETR | etc."""
    combinar_outro_indice: bool = False
    indice_combinado: Optional[str] = None
    data_inicio_combinacao: Optional[str] = None
    ignorar_taxa_negativa: bool = False

    juros: Literal[
        "TAXA_LEGAL", "JUROS_PADRAO", "JUROS_POUPANCA", "JUROS_MEIO_PORCENTO",
        "JUROS_UM_PORCENTO", "JUROS_ZERO_TRINTA_TRES", "SELIC", "SELIC_FAZENDA",
        "SELIC_BACEN", "FAZENDA_PUBLICA", "SEM_JUROS", "TRD_SIMPLES", "TRD_COMPOSTOS",
    ] = "TAXA_LEGAL"
    """Tabela de juros da FASE 1 (pré-judicial, ou única se juros_combinacoes
    estiver vazio). Quando há mais de uma fase, preencher juros_combinacoes
    com as FASES 2+ (cada uma com sua data_inicio)."""
    fazenda_publica_data_inicial: Optional[str] = None
    nao_aplicar_juros: bool = False
    aplicar_juros_fase_pre_judicial: bool = True
    """Se True, juros aplicam DESDE o vencimento da verba (modelo CLT).
    Se False, juros aplicam SÓ a partir do ajuizamento (modelo Fazenda Pública)."""

    juros_combinacoes: list[FaseJuros] = Field(default_factory=list)
    """Fases adicionais de juros (botão '+' do PJE-Calc). Cada fase substitui
    a tabela vigente a partir da `data_inicio`. Modelo TST E-ED-RR-20407
    (ajuizamento >= 30/08/2024):
      juros = "TAXA_LEGAL"  (fase 1: pré-jud)
      juros_combinacoes = [
        {data_inicio: "<data_ajuizamento>", tabela: "SELIC"},
        {data_inicio: "30/08/2024", tabela: "TAXA_LEGAL"}
      ]

    Modelo simplificado (caso Scarlette, ajuizamento POSTERIOR a 30/08/2024):
      juros = "TAXA_LEGAL"
      juros_combinacoes = [
        {data_inicio: "<data_ajuizamento>", tabela: "SELIC"}
      ]
    (PJE-Calc trata Lei 14.905 internamente com TAXA_LEGAL pós-30/08/2024.)
    """

    # Aba "Dados Específicos"
    base_juros_verbas: Literal["VERBAS", "VERBA_INSS", "VERBA_INSS_PP"] = "VERBAS"
    fgts: CorrecaoFGTS = Field(default_factory=CorrecaoFGTS)
    previdencia_privada: Optional[CorrecaoPrevidenciaPrivada] = None
    custas_judiciais: Optional[CorrecaoCustasJudiciais] = None
    cs_salarios_devidos: CorrecaoCS = Field(default_factory=CorrecaoCS)
    cs_salarios_pagos: CorrecaoCS = Field(default_factory=CorrecaoCS)


class Liquidacao(BaseModel):
    """Espelha liquidacao.xhtml (Operações > Liquidar)."""
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
    historico_salarial: list[HistoricoSalarial] = Field(default_factory=list)
    # verbas_principais pode estar vazia — caso típico: condenação só de FGTS
    # depósitos em atraso, que vai via fgts.saldos_a_deduzir (não como verba).
    verbas_principais: list[VerbaPrincipal] = Field(default_factory=list)
    cartao_de_ponto: Optional[CartaoDePonto] = None
    """Cartão de ponto único (formato legacy). Use cartoes_de_ponto quando
    a sentença reconhece >1 período de jornada distintos. Normalizer
    migra singular para list[1] automaticamente."""
    cartoes_de_ponto: list[CartaoDePonto] = Field(default_factory=list)
    """Lista de cartões de ponto (1+ cartões para múltiplos períodos de
    jornada distintos). Cada item tem seu próprio data_inicial/data_final
    + jornada. Quando preenchido, sobrescreve cartao_de_ponto singular.
    Bot cria N cartões via 'Novo' na listagem do PJE-Calc.

    Exemplo (Scarlette 27/05/2026): sentença reconhece 2 períodos:
    período 1 (10/04→21/09): jornada A; período 2 (22/09→01/12): jornada B.
    → cartoes_de_ponto = [<cartão_p1>, <cartão_p2>]
    """
    faltas: list[Falta] = Field(default_factory=list)
    ferias: FeriasSection = Field(default_factory=FeriasSection)
    fgts: FGTS = Field(default_factory=FGTS)
    # CS e IRPF: opcionais por design — quando o JSON OMITE estes campos, a
    # automação PULA as fases correspondentes e os defaults nativos do
    # PJE-Calc valem 100% (apurar segurado, alíquota empregado SEGURADO_
    # EMPREGADO, empregador POR_ATIVIDADE_ECONOMICA, IRPF com tributação
    # separada RRA, etc.). A IA só deve preencher quando a sentença
    # determinar EXPLICITAMENTE algo diferente.
    contribuicao_social: Optional[ContribuicaoSocial] = None
    imposto_de_renda: Optional[ImpostoDeRenda] = None
    honorarios: list[Honorario] = Field(default_factory=list)
    custas_judiciais: CustasJudiciais = Field(default_factory=CustasJudiciais)
    correcao_juros_multa: CorrecaoJurosMulta = Field(default_factory=CorrecaoJurosMulta)
    liquidacao: Liquidacao = Field(default_factory=Liquidacao)
    # 5 seções com schema TIPADO (antes eram Optional[dict]). Política
    # "skip por omissão": JSON `null` → fase pulada, defaults PJE-Calc
    # valem 100%. IA só preenche quando a sentença determinar.
    salario_familia: Optional[SalarioFamilia] = None
    seguro_desemprego: Optional[SeguroDesemprego] = None
    previdencia_privada: Optional[PrevidenciaPrivada] = None
    pensao_alimenticia: Optional[PensaoAlimenticia] = None
    multas_indenizacoes: list[MultaIndenizacao] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_completude(self) -> "PreviaCalculoV2":
        """Roda validações cruzadas e atualiza self.meta.validacao."""
        # Resetar estado de validação (payload pode trazer erros de execuções anteriores)
        self.meta.validacao.campos_faltantes = []
        self.meta.validacao.avisos = []
        self.meta.validacao.completude = "OK"
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

        # 2. Verbas com valor=INFORMADO têm valor preenchido (> 0)
        # Sem isso, o PJE-Calc rejeita liquidação com "Para apurar a verba informada
        # X deve existir pelo menos uma ocorrência com valor diferente de zero"
        for v in self.verbas_principais:
            p = v.parametros
            if p.valor == TipoValor.INFORMADO:
                if not isinstance(p.valor_devido, ValorDevidoInformado):
                    self.meta.validacao.campos_faltantes.append(
                        f"verbas_principais[{v.id}] '{v.nome_sentenca}': "
                        f"valor=INFORMADO requer valor_devido com valor_informado_brl > 0"
                    )
                elif p.valor_devido.valor_informado_brl <= 0:
                    self.meta.validacao.campos_faltantes.append(
                        f"verbas_principais[{v.id}] '{v.nome_sentenca}': "
                        f"valor_informado_brl deve ser > 0 (atual: {p.valor_devido.valor_informado_brl}). "
                        f"PJE-Calc rejeita liquidação de verba INFORMADO sem valor."
                    )
            elif p.valor == TipoValor.CALCULADO:
                # CALCULADO requer formula_calculado com base+divisor+multiplicador+quantidade
                if not p.formula_calculado:
                    self.meta.validacao.campos_faltantes.append(
                        f"verbas_principais[{v.id}] '{v.nome_sentenca}': "
                        f"valor=CALCULADO requer formula_calculado completa"
                    )
                else:
                    f = p.formula_calculado
                    # Quantidade obrigatória + coerência com cartão de ponto
                    if f.quantidade:
                        q = f.quantidade
                        # INFORMADA com valor 0 ou null → PJE-Calc apura zero
                        # e emite alerta "todas as ocorrências de HE foram
                        # salvas com quantidade igual a zero". Bloqueante.
                        if (
                            q.tipo == TipoQuantidade.INFORMADA
                            and (q.valor is None or q.valor <= 0)
                        ):
                            self.meta.validacao.campos_faltantes.append(
                                f"verbas_principais[{v.id}] '{v.nome_sentenca}': "
                                f"quantidade.tipo=INFORMADA exige valor > 0. "
                                f"Use a tabela de conversão (X HE/dia × 22 = mensal). "
                                f"Se a sentença NÃO fixar quantidade, use "
                                f"quantidade.tipo=IMPORTADA_DO_CARTAO e preencha cartao_de_ponto."
                            )
                        # IMPORTADA_DO_CARTAO exige cartao_de_ponto OU cartoes_de_ponto preenchido
                        # (cartoes_de_ponto = lista — suporte multi-período Scarlette 27/05/2026)
                        if (
                            q.tipo == TipoQuantidade.IMPORTADA_DO_CARTAO
                            and self.cartao_de_ponto is None
                            and not self.cartoes_de_ponto
                        ):
                            self.meta.validacao.campos_faltantes.append(
                                f"verbas_principais[{v.id}] '{v.nome_sentenca}': "
                                f"quantidade.tipo=IMPORTADA_DO_CARTAO exige cartao_de_ponto "
                                f"(ou cartoes_de_ponto para multi-período) preenchido "
                                f"(seção 5 do prompt). Sem o cartão, PJE-Calc não tem como "
                                f"apurar HE mês a mês."
                            )

        # 4. Justa causa / pedido de demissão (Súmula 171) — FLAG de revisão
        # para FÉRIAS/13º standalone. NÃO removemos aqui (férias VENCIDAS são
        # devidas mesmo na justa causa) — o normalizer já auto-removeu o que é
        # inequivocamente indevido (aviso/40%FGTS/saque/seguro); aqui só
        # sinalizamos o ambíguo para o revisor confirmar.
        _mod = getattr(self.parametros_calculo, "modalidade_rescisao", None)
        if _mod in ("justa_causa", "pedido_demissao"):
            for v in self.verbas_principais:
                nome = (v.nome_pjecalc or v.nome_sentenca or "").upper()
                eh_ferias = nome.startswith("FÉRIAS") or nome.startswith("FERIAS")
                eh_13 = nome.startswith("13") or "DÉCIMO TERCEIRO" in nome or "DECIMO TERCEIRO" in nome
                if eh_ferias or eh_13:
                    avisos.append(
                        f"⚠ Rescisão por {_mod.replace('_', ' ')}: a verba "
                        f"'{v.nome_pjecalc or v.nome_sentenca}' é tipicamente "
                        f"INDEVIDA (Súmula 171 TST) — só permanece se for FÉRIAS "
                        f"VENCIDAS não gozadas. CONFIRME no dispositivo antes de liquidar."
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

            # AVISO PRÉVIO INDENIZADO projeta o contrato por 30+3/ano (Lei 12.506/2011)
            # → periodo_fim PODE/DEVE ser data_demissao + N dias (N até 90).
            # Excluir essas verbas da Regra 1 e validar separadamente o limite legal.
            is_aviso_previo = (
                p.caracteristica == CaracteristicaVerba.AVISO_PREVIO
                or (v.expresso_alvo and "AVISO PRÉVIO" in v.expresso_alvo.upper())
                or (v.nome_pjecalc and "AVISO PRÉVIO" in v.nome_pjecalc.upper())
            )

            # Regra 1: ocorrências NÃO-MENSAIS (DESLIGAMENTO, DEZEMBRO,
            # PERIODO_AQUISITIVO) + periodo_fim > demissao = ERRO bloqueante.
            # Mensagem JSF exata do PJE-Calc:
            # "A data final não pode ser maior que a data demissão, para o
            #  caso de 'Ocorrências de Pagamento' diferentes de Mensal"
            # EXCEÇÃO: AVISO_PREVIO (projeção legal Lei 12.506/2011 §3.5)
            nao_mensais = {
                OcorrenciaPagamento.DESLIGAMENTO,
                OcorrenciaPagamento.DEZEMBRO,
                OcorrenciaPagamento.PERIODO_AQUISITIVO,
            }
            if (
                p.ocorrencia_pagamento in nao_mensais
                and d_pf and d_dem and d_pf > d_dem
                and not is_aviso_previo
            ):
                self.meta.validacao.campos_faltantes.append(
                    f"verba[{v.id}] '{v.nome_pjecalc or v.nome_sentenca}': "
                    f"ocorrencia_pagamento={p.ocorrencia_pagamento.value} "
                    f"incompatível com periodo_fim={p.periodo_fim} POSTERIOR à "
                    f"data_demissao={self.parametros_calculo.data_demissao}. "
                    f"PJE-Calc rejeita liquidação. Para verbas pós-contratuais "
                    f"(estabilidade, dispensa discriminatória) use ocorrencia=MENSAL. "
                    f"Para 13º/Férias/Rescisórias dentro do contrato, ajuste "
                    f"periodo_fim≤data_demissao."
                )

            # Regra 1.1: AVISO PRÉVIO — limite legal de 90 dias (Lei 12.506/2011)
            if is_aviso_previo and d_pf and d_dem and d_pf > d_dem:
                delta_dias = (d_pf - d_dem).days
                if delta_dias > 90:
                    self.meta.validacao.campos_faltantes.append(
                        f"verba[{v.id}] AVISO PRÉVIO: projeção de {delta_dias} dias excede o "
                        f"máximo legal de 90 dias (Lei 12.506/2011 — 30 dias base + 3 dias por "
                        f"ano completo, limite 90). Ajuste periodo_fim."
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
