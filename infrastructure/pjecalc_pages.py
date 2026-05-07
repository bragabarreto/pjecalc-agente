"""Pydantic v2 models — schema "réplica perfeita" do PJE-Calc Cidadão.

Fonte: docs/pjecalc-fields-catalog.json (gerado por scripts/cataloga_pjecalc.py).

Princípio: cada model tem campos com nomes EXATOS dos `id` do DOM (sufixo após
`formulario:`), Literal types para radios/selects (com valores exatos do DOM),
defaults vazios. A validação `extra="forbid"` garante que adicionar campo
desconhecido falhe — força fidelidade ao PJE-Calc.

Cada model representa UMA página ou sub-página. Estes models são consumidos
por:
  1. `templates/previa_v3/*.html` — render via macros Jinja
  2. `core/aplicador.py` — automação Playwright (1:1, sem inferência)
  3. `extraction.py` / `classification.py` — saída da IA

Convenções:
  - Datas em string DD/MM/YYYY (formato exato do DOM); validador converte/valida.
  - Valores monetários em string BR "1.234,56" para preservar formatação de
    submit; conversão para Decimal nos consumidores quando necessário.
  - Radios/selects: Literal com valores reais do DOM (preserva enums do backend).
  - Campos opcionais: None default ou string vazia conforme contrato JSF.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================================
# Helpers / validators reutilizáveis
# ============================================================================


_DATA_BR = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _validar_data_br(v: Optional[str]) -> Optional[str]:
    """Valida formato DD/MM/YYYY. Aceita None ou string vazia."""
    if v is None or v == "":
        return None
    if not _DATA_BR.match(v):
        raise ValueError(f"Data inválida: {v!r} — esperado DD/MM/YYYY")
    # Verifica data real
    try:
        datetime.strptime(v, "%d/%m/%Y")
    except ValueError as e:
        raise ValueError(f"Data inválida: {v!r} ({e})")
    return v


def _validar_decimal_br(v: Optional[str]) -> Optional[str]:
    """Valida formato '1.234,56' — aceita None/vazio."""
    if v is None or v == "":
        return None
    # Aceita "1234,56" e "1.234,56" e "1234.56"
    if not re.match(r"^\d{1,3}(\.\d{3})*(,\d+)?$|^\d+(\.\d+)?$", v):
        raise ValueError(f"Valor inválido: {v!r} — esperado formato BR (ex.: '1.234,56')")
    return v


# Tipos auxiliares
DataBR = Annotated[Optional[str], Field(default=None, description="Data em DD/MM/YYYY")]
ValorBR = Annotated[Optional[str], Field(default=None, description="Valor monetário BR (ex.: '1.234,56')")]


# ============================================================================
# 1. Dados do Processo
# ============================================================================


class DadosProcesso(BaseModel):
    """Página: 'Dados do Cálculo' (calculo.jsf).

    74 campos editáveis no PJE-Calc 2.15.1, organizados em 4 abas:
    1. Identificação do processo
    2. Reclamante (+ advogado)
    3. Reclamado (+ advogado)
    4. Parâmetros do Cálculo (datas, prescrição, remuneração)
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # ── Identificação ──
    numero: str = Field(default="", description="Número do processo (sem dígito/ano)")
    digito: str = Field(default="", description="Dígito verificador (2)")
    ano: str = Field(default="", description="Ano (4)")
    regiao: str = Field(default="", description="Tribunal regional (ex.: 07)")
    vara: str = Field(default="", description="Vara (ex.: 0003)")
    valor_da_causa: ValorBR = None
    autuado_em: DataBR = None

    # Estado / Município (selects — value real do DOM são códigos numéricos)
    estado: Optional[str] = Field(
        default=None,
        description="Código do estado (UF). Ver catálogo para mapping.",
    )
    municipio: Optional[str] = Field(
        default=None,
        description="Código do município. Depende do estado.",
    )

    # ── Reclamante ──
    reclamante_nome: str = Field(default="", description="Nome completo")
    documento_fiscal_reclamante: Optional[Literal["CPF", "CNPJ", "CEI"]] = None
    reclamante_numero_documento_fiscal: str = ""
    reclamante_tipo_documento_previdenciario: Optional[Literal["PIS", "PASEP", "NIT"]] = None
    reclamante_numero_documento_previdenciario: str = ""

    # Advogado do reclamante
    nome_advogado_reclamante: str = ""
    numero_oab_advogado_reclamante: str = ""
    tipo_documento_advogado_reclamante: Optional[Literal["CPF", "CNPJ", "CEI"]] = None
    numero_documento_advogado_reclamante: str = ""

    # ── Reclamado ──
    reclamado_nome: str = Field(default="", description="Nome do reclamado / razão social")
    tipo_documento_fiscal_reclamado: Optional[Literal["CPF", "CNPJ", "CEI"]] = None
    reclamado_numero_documento_fiscal: str = ""

    # Advogado do reclamado
    nome_advogado_reclamado: str = ""
    numero_oab_advogado_reclamado: str = ""
    tipo_documento_advogado_reclamado: Optional[Literal["CPF", "CNPJ", "CEI"]] = None
    numero_documento_advogado_reclamado: str = ""

    # ── Parâmetros do Cálculo ──
    data_admissao: DataBR = None
    data_demissao: DataBR = None
    data_ajuizamento: DataBR = None
    data_inicio_calculo: DataBR = None
    data_termino_calculo: DataBR = None

    # Prescrição
    prescricao_quinquenal: bool = False
    prescricao_fgts: bool = False

    # Remuneração-base
    valor_maior_remuneracao: ValorBR = None
    valor_ultima_remuneracao: ValorBR = None

    # Aviso Prévio
    apuracao_prazo_aviso_previo: Literal[
        "NAO_APURAR", "APURACAO_CALCULADA", "APURACAO_INFORMADA"
    ] = "NAO_APURAR"
    projeta_aviso_indenizado: bool = False

    # Outros parâmetros
    zera_valor_negativo: bool = False
    considera_feriado_estadual: bool = False
    considera_feriado_municipal: bool = False
    ponto_facultativo: Optional[str] = None  # código do ponto facultativo

    # Carga Horária
    valor_carga_horaria_padrao: ValorBR = None
    # Exceções de carga horária (lista de períodos com valor diferente)
    excecoes_carga_horaria: List[ExcecaoCargaHoraria] = Field(default_factory=list)

    # Sábado dia útil
    sabado_dia_util: bool = False
    excecoes_sabado: List[ExcecaoSabado] = Field(default_factory=list)

    # Comentários (textarea)
    comentarios: str = ""

    # ── Validators ──
    _v_autuado = field_validator("autuado_em", mode="before")(lambda cls, v: _validar_data_br(v))
    _v_admissao = field_validator("data_admissao", mode="before")(lambda cls, v: _validar_data_br(v))
    _v_demissao = field_validator("data_demissao", mode="before")(lambda cls, v: _validar_data_br(v))
    _v_ajuizamento = field_validator("data_ajuizamento", mode="before")(lambda cls, v: _validar_data_br(v))
    _v_inicio = field_validator("data_inicio_calculo", mode="before")(lambda cls, v: _validar_data_br(v))
    _v_termino = field_validator("data_termino_calculo", mode="before")(lambda cls, v: _validar_data_br(v))


class ExcecaoCargaHoraria(BaseModel):
    """Período de exceção da carga horária padrão."""

    model_config = ConfigDict(extra="forbid")
    data_inicio: DataBR = None
    data_termino: DataBR = None
    valor_carga_horaria: ValorBR = None


class ExcecaoSabado(BaseModel):
    """Período de exceção da regra 'sábado dia útil'."""

    model_config = ConfigDict(extra="forbid")
    data_inicio: DataBR = None
    data_termino: DataBR = None


# ============================================================================
# 2. Histórico Salarial
# ============================================================================


class HistoricoSalarialEntry(BaseModel):
    """Entrada do Histórico Salarial (form Novo).

    Cada Entry gera N OcorrênciasMensais ao clicar 'Gerar Ocorrências'.
    """

    model_config = ConfigDict(extra="forbid")

    nome: str = Field(description="Nome (ex.: 'ÚLTIMA REMUNERAÇÃO', 'SALÁRIO PAGO POR FORA')")
    tipo_variacao_da_parcela: Literal["FIXA", "VARIAVEL"] = "FIXA"
    competencia_inicial: DataBR = None
    competencia_final: DataBR = None
    tipo_valor: Literal["INFORMADO", "CALCULADO"] = "INFORMADO"
    valor_para_base_de_calculo: ValorBR = None  # se INFORMADO

    # Incidências (checkboxes do form)
    fgts: bool = True
    inss: bool = True

    # Ocorrências mensais geradas
    ocorrencias: List[HistoricoSalarialOcorrencia] = Field(default_factory=list)


class HistoricoSalarialOcorrencia(BaseModel):
    """Linha mensal gerada do Histórico Salarial.

    Cada linha tem campos para valor base, valor sobre incidência CS,
    valor sobre incidência FGTS — preenchidos via 'Recuperar Devidos' ou
    manualmente.
    """

    model_config = ConfigDict(extra="forbid")

    indice: int = Field(description="0-based index da linha")
    competencia: str = Field(description="MM/YYYY do mês da ocorrência")
    ativo: bool = True
    valor: ValorBR = None
    valor_incidencia_cs: ValorBR = None  # CS sobre Salários Devidos
    valor_incidencia_fgts: ValorBR = None
    cs_recolhida: bool = False
    fgts_recolhido: bool = False


# ============================================================================
# 3. Verba — Parâmetros + Ocorrências
# ============================================================================


class BaseCalculoExtra(BaseModel):
    """Base de cálculo adicional incluída via 'Incluir Base'."""

    model_config = ConfigDict(extra="forbid")
    tipo_da_base_tabelada: Literal[
        "MAIOR_REMUNERACAO", "HISTORICO_SALARIAL", "SALARIO_DA_CATEGORIA", "SALARIO_MINIMO"
    ]
    base_historicos: Optional[str] = None  # nome do histórico se HISTORICO_SALARIAL
    integralizar: Optional[Literal["SIM", "NAO"]] = None
    proporcionalizar: Optional[Literal["SIM", "NAO"]] = None


class ParametrosVerba(BaseModel):
    """Página: 'Parâmetros da Verba' (form Manual ou pós-Expresso).

    ~30 campos editáveis. Caracteristica e ocorrenciaPagto têm interdependência:
    quando setCaracteristica é chamado, ocorrenciaPagto é setado automaticamente
    no default (COMUM→MENSAL, FERIAS→PERIODO_AQUISITIVO, etc.). Clicar
    explicitamente só quando diferir do default.
    """

    model_config = ConfigDict(extra="forbid")

    # Identificação
    descricao: str = Field(description="Nome da verba (ex.: 'HORAS EXTRAS 50%')")
    assuntos_cnj: str = Field(default="2581", description="Código CNJ (ex.: 2581 — Remuneração)")

    # Tipo
    tipo_de_verba: Literal["PRINCIPAL", "REFLEXA"] = "PRINCIPAL"
    tipo_variacao_da_parcela: Literal["FIXA", "VARIAVEL"] = "FIXA"

    # Característica + Ocorrência
    caracteristica_verba: Literal[
        "COMUM", "DECIMO_TERCEIRO_SALARIO", "AVISO_PREVIO", "FERIAS"
    ] = "COMUM"
    ocorrencia_pagto: Literal["MENSAL", "DEZEMBRO", "DESLIGAMENTO", "PERIODO_AQUISITIVO"] = "MENSAL"

    # Sumula 439 TST (juros desde ajuizamento)
    ocorrencia_ajuizamento: Literal["OCORRENCIAS_VENCIDAS", "OCORRENCIAS_VENCIDAS_E_VINCENDAS"] = (
        "OCORRENCIAS_VENCIDAS"
    )

    # Período
    periodo_inicial: DataBR = None
    periodo_final: DataBR = None

    # Reflexa (se tipo=REFLEXA)
    gera_reflexo: Optional[Literal["DEVIDO", "DIFERENCA"]] = None
    gerar_principal: Optional[Literal["DEVIDO", "DIFERENCA"]] = None
    compor_principal: Literal["SIM", "NAO"] = "SIM"  # se reflexa

    # Valor / Calculado
    valor: Literal["CALCULADO", "INFORMADO"] = "CALCULADO"
    valor_informado: ValorBR = None  # se valor=INFORMADO

    # Incidências
    irpf: bool = False
    inss: bool = True
    fgts: bool = True
    previdencia_privada: bool = False
    pensao_alimenticia: bool = False

    # Base de Cálculo (principal)
    tipo_da_base_tabelada: Optional[Literal[
        "MAIOR_REMUNERACAO", "HISTORICO_SALARIAL", "SALARIO_DA_CATEGORIA",
        "SALARIO_MINIMO", "VALOR_INFORMADO"
    ]] = None
    base_historicos: Optional[str] = None  # se HISTORICO_SALARIAL — nome do hist
    integralizar_base: Optional[Literal["SIM", "NAO"]] = None

    # Bases adicionais
    bases_calculo: List[BaseCalculoExtra] = Field(default_factory=list)

    # Divisor
    tipo_de_divisor: Literal[
        "INFORMADO", "CARGA_HORARIA", "DIAS_UTEIS", "IMPORTADO_CARTAO_PONTO"
    ] = "CARGA_HORARIA"
    outro_valor_do_divisor: ValorBR = None  # se INFORMADO

    # Multiplicador
    outro_valor_do_multiplicador: ValorBR = None

    # Quantidade
    tipo_da_quantidade: Literal[
        "INFORMADA", "IMPORTADA_CALENDARIO", "IMPORTADA_CARTAO_PONTO"
    ] = "INFORMADA"
    valor_informado_da_quantidade: ValorBR = None
    aplicar_proporcionalidade_quantidade: bool = False

    # Valor Pago (deduções)
    tipo_do_valor_pago: Literal["INFORMADO", "CALCULADO"] = "CALCULADO"
    valor_informado_pago: ValorBR = None
    aplicar_proporcionalidade_valor_pago: bool = False

    # Outros checkboxes
    zera_valor_negativo: bool = False
    excluir_falta_justificada: bool = False
    excluir_falta_nao_justificada: bool = False
    excluir_ferias_gozadas: bool = False
    dobra_valor_devido: bool = False
    aplicar_proporcionalidade_a_base: bool = False

    # Comentários
    comentarios: str = ""

    # Validators
    _v_p_ini = field_validator("periodo_inicial", mode="before")(lambda cls, v: _validar_data_br(v))
    _v_p_fim = field_validator("periodo_final", mode="before")(lambda cls, v: _validar_data_br(v))


class OcorrenciaVerba(BaseModel):
    """Linha da tabela 'Ocorrências da Verba'.

    DOM: formulario:listagem:N:ativo / termoDiv / termoMult / termoQuant /
    valorDevido / dobra. A data é IMPLÍCITA pelo índice (linha 0 = 1º mês do
    período). Para verbas com ocorrencia_pagto=DESLIGAMENTO, apenas a última
    linha (índice máximo) deve estar ativa.
    """

    model_config = ConfigDict(extra="forbid")

    indice: int = Field(description="0-based index da linha")
    ativo: bool = True
    termo_div: ValorBR = None  # divisor da fórmula
    termo_mult: ValorBR = None  # multiplicador
    termo_quant: ValorBR = None  # quantidade (HE, dias)
    valor_devido: ValorBR = None  # valor manual (indenizações)
    dobra: bool = False


class Verba(BaseModel):
    """Verba completa: Parâmetros + lista de Ocorrências + lista de Reflexos.

    Reflexos são também `Verba` mas com `parametros.tipo_de_verba='REFLEXA'`.
    """

    model_config = ConfigDict(extra="forbid")

    parametros: ParametrosVerba
    ocorrencias: List[OcorrenciaVerba] = Field(default_factory=list)
    reflexos: List[Verba] = Field(default_factory=list)
    # Lançamento: 'EXPRESSO' (verba pré-definida do PJE-Calc) ou 'MANUAL'
    lancamento: Literal["EXPRESSO", "MANUAL"] = "EXPRESSO"
    expresso_alvo: Optional[str] = Field(
        default=None,
        description="Nome exato da verba no Lançamento Expresso (54 verbas pré-definidas)",
    )


# ============================================================================
# 4. Honorários
# ============================================================================


class Honorario(BaseModel):
    """Página: 'Honorários' (form Novo)."""

    model_config = ConfigDict(extra="forbid")

    descricao: str = Field(description="Descrição do honorário")
    tp_honorario: Literal[
        "ADVOCATICIOS", "ASSISTENCIAIS", "CONTRATUAIS",
        "PERICIAIS_CONTADOR", "PERICIAIS_DOCUMENTOSCOPIO"
    ]
    tipo_de_devedor: Literal["RECLAMANTE", "RECLAMADO"]
    tipo_valor: Literal["CALCULADO", "INFORMADO"] = "CALCULADO"
    aliquota: ValorBR = None  # %
    base_para_apuracao: Literal[
        "BRUTO",
        "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
        "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA",
        "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
    ] = "BRUTO"

    # Credor
    nome_credor: str
    tipo_documento_fiscal_credor: Literal["CPF", "CNPJ", "CEI"]
    numero_documento_fiscal_credor: str

    # Outros
    apurar_irrf: bool = True
    incidir_sobre_juros: bool = False
    aplicar_juros: bool = False


# ============================================================================
# 5. Forward references resolution
# ============================================================================


DadosProcesso.model_rebuild()
HistoricoSalarialEntry.model_rebuild()
Verba.model_rebuild()
