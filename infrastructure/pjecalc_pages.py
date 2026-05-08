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

    # Incidências (checkboxes do form). Labels reais na UI:
    #   "FGTS" / "Contribuição Social" / "Proporcionalizar Contribuição Social"
    fgts: bool = True
    inss: bool = True  # rotulado "Contribuição Social" no form
    proporcionalizar_cs: bool = False  # condicional — aparece quando inss=True

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
# 5. FGTS / INSS / IRPF / Cartão de Ponto / Faltas / Férias / Custas / Correção
# ============================================================================


class FGTS(BaseModel):
    """Página: FGTS (fgts.jsf)."""

    model_config = ConfigDict(extra="forbid")

    apurar: bool = True
    tipo_de_verba: Literal["NORMAL", "VERBA_RESCISORIA"] = "NORMAL"
    compor_principal: Literal["SIM", "NAO"] = "SIM"
    aliquota: Literal["8", "2", "INFORMADO"] = "8"  # %
    aliquota_informada: ValorBR = None
    multa_do_fgts: Literal["MULTA_DE_40", "MULTA_DE_20", "SEM_MULTA"] = "MULTA_DE_40"
    tipo_do_valor_da_multa: Literal["CALCULADO", "INFORMADO"] = "CALCULADO"
    multa_informada: ValorBR = None
    multa_do_artigo_467: bool = False
    incidencia_do_fgts: Literal[
        "VERBAS_REMUNERATORIAS",
        "VERBAS_REMUNERATORIAS_E_INDENIZATORIAS",
        "TODAS_AS_VERBAS",
    ] = "VERBAS_REMUNERATORIAS"


class ContribuicaoSocial(BaseModel):
    """Página: Contribuição Social / INSS (inss/inss.jsf).

    Schema reflete os campos visíveis na tela do PJE-Calc 2.15.1.
    """

    model_config = ConfigDict(extra="forbid")

    apurar: bool = True
    apurar_segurado_salarios_devidos: bool = True
    apurar_sobre_salarios_pagos: bool = False
    cobrar_do_reclamante: bool = True
    com_correcao_trabalhista: bool = True
    limitar_ao_teto: bool = True
    isencao_simples: bool = False
    simples_inicio: DataBR = None
    simples_fim: DataBR = None
    lei_11941: bool = False

    # Atividade econômica (CNAE)
    atividade_economica: Optional[str] = None  # código

    # Alíquotas
    aliquota_empresa: ValorBR = None  # %
    aliquota_sat: ValorBR = None  # %  (campo aliquotaSAT — antes era aliquota_rat)
    aliquota_terceiros: ValorBR = None  # %
    fap: ValorBR = None  # Fator Acidentário Previdenciário

    # Tipo de alíquota
    tipo_aliquota_segurado: Optional[Literal[
        "EMPREGADO", "DOMESTICO", "FIXA"
    ]] = None
    tipo_aliquota_empregador: Optional[Literal[
        "ATIVIDADE_ECONOMICA", "PERIODO", "FIXA"
    ]] = None

    # Períodos
    periodo_incidencia_pagos: Optional[str] = None
    periodo_incidencia_devidos: Optional[str] = None

    # Regime + multa/juros
    regime_caixa_competencia: Literal["CAIXA", "COMPETENCIA"] = "COMPETENCIA"
    multa_inss: bool = False
    juros_inss: bool = True

    # Índice de atualização (legado)
    indice_atualizacao: Optional[str] = None

    # Backward compat alias (lê aliquota_rat antigo, popula aliquota_sat)
    @property
    def aliquota_rat(self) -> Any:  # pragma: no cover
        return self.aliquota_sat


class ImpostoRenda(BaseModel):
    """Página: Imposto de Renda (irpf.jsf).

    Campos reais conforme screenshot da tela do PJE-Calc 2.15.1:
      - "Apurar Imposto de Renda" (checkbox principal)
      - 5 checkboxes de configuração: Incidir sobre Juros de Mora,
        Cobrar do Reclamado, Tributação Exclusiva, Tributação em Separado,
        Aplicar Regime de Caixa
      - Bloco "Deduzir da Base do Imposto de Renda": 4 checkboxes
        (Contribuição Social, Previdência Privada, Pensão Alimentícia,
        Honorários devidos pelo Reclamante)
      - Aposentado maior de 65 Anos (checkbox)
      - Dependentes (checkbox + input numérico)
    """

    model_config = ConfigDict(extra="forbid")

    apurar: bool = True

    # Configurações de tributação / cobrança
    incidir_sobre_juros_de_mora: bool = False
    cobrar_do_reclamado: bool = False
    tributacao_exclusiva: bool = False
    tributacao_em_separado: bool = False
    aplicar_regime_de_caixa: bool = False

    # Deduzir da Base do IR (todos default True na UI)
    deduzir_contribuicao_social: bool = True
    deduzir_previdencia_privada: bool = True
    deduzir_pensao_alimenticia: bool = True
    deduzir_honorarios_reclamante: bool = True

    # Aposentado / Dependentes
    aposentado_maior_65: bool = False
    quantidade_dependentes: int = 0

    # Compat (legado v2)
    regime_tributacao: Optional[Literal[
        "MESES_TRIBUTAVEIS", "RRA", "REGIME_GERAL"
    ]] = None
    meses_tributaveis: Optional[int] = None
    deducoes: ValorBR = None
    pensao_alimenticia: ValorBR = None  # valor da pensão para dedução


class ProgramacaoSemanalDia(BaseModel):
    """Configuração de jornada por dia da semana."""

    model_config = ConfigDict(extra="forbid")

    dia: Literal["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SAB"]
    turno1_inicio: Optional[str] = None  # HH:MM
    turno1_fim: Optional[str] = None
    turno2_inicio: Optional[str] = None
    turno2_fim: Optional[str] = None


class CartaoDePonto(BaseModel):
    """Página: Cartão de Ponto."""

    model_config = ConfigDict(extra="forbid")

    forma_de_apuracao: Optional[Literal[
        "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL",
        "HORAS_EXTRAS_PELA_JORNADA_REAL",
        "HORAS_EXTRAS_PELA_JORNADA_PADRAO",
    ]] = None
    jornada_diaria_h: ValorBR = None
    jornada_semanal_h: ValorBR = None
    intervalo_intrajornada_min: Optional[int] = None
    programacao_semanal: List[ProgramacaoSemanalDia] = Field(default_factory=list)


class Falta(BaseModel):
    """Lançamento de falta."""

    model_config = ConfigDict(extra="forbid")

    data_inicio: DataBR = None
    data_fim: DataBR = None
    justificada: bool = False
    descontar_remuneracao: bool = True
    descontar_dsr: bool = True


class FeriasEntry(BaseModel):
    """Lançamento de Férias gozadas."""

    model_config = ConfigDict(extra="forbid")

    periodo_aquisitivo_inicio: DataBR = None
    periodo_aquisitivo_fim: DataBR = None
    data_inicio_gozo: DataBR = None
    data_fim_gozo: DataBR = None
    abono_pecuniario: bool = False
    dobra: bool = False


class CustasJudiciais(BaseModel):
    """Página: Custas Judiciais (custas-judiciais.jsf).

    Estrutura real do PJE-Calc 2.15.1: 3 radios separados (Reclamado-Conhecimento,
    Reclamado-Liquidação, Reclamante-Conhecimento), cada um com 3 opções
    NAO_SE_APLICA / CALCULADA_* / INFORMADA + campos condicionais.
    """

    model_config = ConfigDict(extra="forbid")

    # Reclamado — Conhecimento (radio na tela)
    reclamado_conhecimento: Literal[
        "NAO_SE_APLICA", "CALCULADA_2_POR_CENTO", "INFORMADA"
    ] = "CALCULADA_2_POR_CENTO"
    valor_reclamado_conhecimento: ValorBR = None  # se INFORMADA
    vencimento_reclamado_conhecimento: DataBR = None  # se INFORMADA

    # Reclamado — Liquidação (radio na tela)
    reclamado_liquidacao: Literal[
        "NAO_SE_APLICA", "CALCULADA_MEIO_POR_CENTO", "INFORMADA"
    ] = "NAO_SE_APLICA"
    valor_reclamado_liquidacao: ValorBR = None  # se INFORMADA
    vencimento_reclamado_liquidacao: DataBR = None  # se INFORMADA

    # Reclamante — Conhecimento (radio na tela)
    reclamante_conhecimento: Literal[
        "NAO_SE_APLICA", "CALCULADA_2_POR_CENTO", "INFORMADA"
    ] = "NAO_SE_APLICA"
    valor_reclamante_conhecimento: ValorBR = None  # se INFORMADA
    vencimento_reclamante_conhecimento: DataBR = None  # se INFORMADA

    # Base de cálculo + parâmetros gerais
    base_para_custas: Optional[Literal[
        "BRUTO_DEVIDO_AO_RECLAMANTE",
        "BRUTO_DEVIDO_AO_RECLAMANTE_MAIS_DEBITOS_RECLAMADO",
    ]] = None
    percentual: ValorBR = "2"  # 2% padrão (campo percentualCustas)
    valor_periciais: ValorBR = None  # honorários periciais

    # ── Custas Fixas (1 vencimento + 9 checkboxes de tipos) ──
    custas_fixas_vencimento: DataBR = None
    custas_fixas_atos_oj_urbana: bool = False
    custas_fixas_atos_oj_rural: bool = False
    custas_fixas_agravo_instrumento: bool = False
    custas_fixas_agravo_peticao: bool = False
    custas_fixas_impugnacao_sentenca: bool = False
    custas_fixas_embargos_arrematacao: bool = False
    custas_fixas_embargos_execucao: bool = False
    custas_fixas_embargos_terceiros: bool = False
    custas_fixas_recurso_revista: bool = False

    # ── Autos 5% (lista) ──
    autos_5pct: List["CustasAuto5pct"] = Field(default_factory=list)
    # ── Armazenamento 0,1% (lista) ──
    armazenamento_0_1pct: List["CustasArmazenamento"] = Field(default_factory=list)

    # ── Tab "Custas Recolhidas" ──
    recolhidas_reclamado_vencimento: DataBR = None
    recolhidas_reclamado_valor: ValorBR = None
    recolhidas_reclamante_vencimento: DataBR = None
    recolhidas_reclamante_valor: ValorBR = None


class CustasAuto5pct(BaseModel):
    """Linha do bloco 'Autos 5%' em Custas Judiciais > Custas Devidas."""
    model_config = ConfigDict(extra="forbid")
    tipo_de_auto: Optional[str] = None  # select obrigatório (catálogo PJE-Calc)
    vencimento: DataBR = None
    valor_do_bem: ValorBR = None


class CustasArmazenamento(BaseModel):
    """Linha do bloco 'Armazenamento 0,1%' em Custas Judiciais."""
    model_config = ConfigDict(extra="forbid")
    inicio: DataBR = None
    termino: DataBR = None
    valor_do_bem: ValorBR = None


class CorrecaoJuros(BaseModel):
    """Página: Correção, Juros e Multa (parametros-atualizacao.jsf).

    Conforme dropdowns reais do PJE-Calc 2.15.1 (screenshots):
      Tab "Dados Gerais":
        - Correção Monetária: Índice Trabalhista (16 opções), Combinar
          com Outro Índice, Ignorar Taxa Negativa
        - Juros de Mora: Aplicar Juros Pré-Judicial, Tabela de Juros
          (13 opções), Combinar com Outra Tabela (lista de
          tabelas adicionais)
      Tab "Dados Específicos" (não capturado ainda)
    """

    model_config = ConfigDict(extra="forbid")

    # ── Correção Monetária (select Índice Trabalhista) ──
    indice_correcao: Literal[
        "TUACDT",  # Tabela Única de Atualização e Conversão de Débitos Trabalhistas
        "DEVEDOR_FAZENDA_PUBLICA",
        "REPETICAO_INDEBITO",
        "TJT_MENSAL",
        "TJT_DIARIA",
        "TR",
        "IGP_M",
        "INPC",
        "IPC",
        "IPCA",
        "IPCAE",
        "IPCAE_TR",
        "SELIC_RECEITA",
        "SELIC_SIMPLES",
        "SELIC_COMPOSTA",
        "SEM_CORRECAO",
    ] = "IPCA"
    combinar_com_outro_indice: bool = False
    ignorar_taxa_negativa: bool = False

    # ── Juros de Mora ──
    aplicar_juros_pre_judicial: bool = True
    taxa_juros: Literal[
        "JUROS_PADRAO",
        "CADERNETA_POUPANCA",
        "FAZENDA_PUBLICA",
        "SIMPLES_0_5_AM",
        "SIMPLES_1_AM",
        "SIMPLES_0_0333333_AD",
        "SELIC_RECEITA",
        "SELIC_SIMPLES",
        "SELIC_COMPOSTA",
        "TRD_SIMPLES",
        "TRD_COMPOSTOS",
        "TAXA_LEGAL",
        "SEM_JUROS",
    ] = "TRD_SIMPLES"
    combinar_outra_tabela_juros: bool = False
    # Lista de tabelas adicionais (ex.: Taxa Legal a partir de 25/09/2025)
    tabelas_juros_adicionais: List["CorrecaoJurosTabelaAdicional"] = Field(default_factory=list)

    # ── Compat (campos legados ainda usados por v2) ──
    base_juros: Literal["VERBA", "PRINCIPAL", "BRUTO"] = "VERBA"
    aplicar_ec_113: bool = True
    sumula_439_juros_desde_ajuizamento: bool = False


class CorrecaoJurosTabelaAdicional(BaseModel):
    """Linha de combinar com outra tabela de juros (e.g. Taxa Legal a partir
    de uma data marco — Lei 14.905/2024 → 30/08/2024)."""
    model_config = ConfigDict(extra="forbid")
    tabela: Literal[
        "JUROS_PADRAO", "CADERNETA_POUPANCA", "FAZENDA_PUBLICA",
        "SIMPLES_0_5_AM", "SIMPLES_1_AM", "SIMPLES_0_0333333_AD",
        "SELIC_RECEITA", "SELIC_SIMPLES", "SELIC_COMPOSTA",
        "TRD_SIMPLES", "TRD_COMPOSTOS", "TAXA_LEGAL", "SEM_JUROS",
    ]
    a_partir_de: DataBR = None


# ============================================================================
# 6. PreviaCalculo — agregador raiz (todas as páginas)
# ============================================================================


class PreviaCalculo(BaseModel):
    """Raiz da prévia v3 — agrega TODAS as páginas do PJE-Calc.

    Esta é a estrutura que o JSON v3 final tem. Cada campo é uma página/seção
    do PJE-Calc Cidadão. Consumida pelo aplicador (`core/aplicador.py`).
    """

    model_config = ConfigDict(extra="forbid")

    processo: DadosProcesso = Field(default_factory=DadosProcesso)
    historico_salarial: List[HistoricoSalarialEntry] = Field(default_factory=list)
    faltas: List[Falta] = Field(default_factory=list)
    ferias: List[FeriasEntry] = Field(default_factory=list)
    verbas: List[Verba] = Field(default_factory=list)
    cartao_de_ponto: CartaoDePonto = Field(default_factory=CartaoDePonto)
    fgts: FGTS = Field(default_factory=FGTS)
    contribuicao_social: ContribuicaoSocial = Field(default_factory=ContribuicaoSocial)
    imposto_renda: ImpostoRenda = Field(default_factory=ImpostoRenda)
    honorarios: List[Honorario] = Field(default_factory=list)
    custas: CustasJudiciais = Field(default_factory=CustasJudiciais)
    correcao_juros: CorrecaoJuros = Field(default_factory=CorrecaoJuros)


# ============================================================================
# 7. Forward references resolution
# ============================================================================


DadosProcesso.model_rebuild()
HistoricoSalarialEntry.model_rebuild()
Verba.model_rebuild()
CartaoDePonto.model_rebuild()
PreviaCalculo.model_rebuild()
