# infrastructure/database.py — Camada de Persistência Completa do pjecalc-agente
# Inclui os 5 modelos originais + 3 novos modelos do Learning Engine

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    create_engine, event,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker


# ── Configuração do banco ─────────────────────────────────────────────────────

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "pjecalc_agent.db"
_DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_RAW_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")
DATABASE_URL = (
    _RAW_URL.replace("postgres://", "postgresql://", 1)
    if _RAW_URL.startswith("postgres://")
    else _RAW_URL
)

_is_postgres = DATABASE_URL.startswith("postgresql")
_connect_args = {} if _is_postgres else {"check_same_thread": False}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)


@event.listens_for(engine, "connect")
def _set_wal(dbapi_conn: Any, _: Any) -> None:
    if not _is_postgres:
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Modelos ORM ───────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Modelos originais (inalterados) ──────────────────────────────────────────

class Processo(Base):
    """
    Representa um processo trabalhista processado pelo agente.
    Chave natural: numero_processo.
    """
    __tablename__ = "processos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    numero_processo = Column(String(50), unique=True, nullable=False, index=True)
    reclamante = Column(String(200))
    reclamado = Column(String(200))
    estado = Column(String(2))
    municipio = Column(String(100))
    vara = Column(String(200))

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    calculos = relationship("Calculo", back_populates="processo", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Processo {self.numero_processo}>"


class Calculo(Base):
    """
    Representa um cálculo de liquidação associado a um processo.
    Pode haver múltiplos cálculos por processo (revisões, recursos etc.).
    """
    __tablename__ = "calculos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    processo_id = Column(Integer, ForeignKey("processos.id"), nullable=False)
    sessao_id = Column(String(36), unique=True, nullable=False, index=True)
    status = Column(String(30), default="em_andamento")

    admissao = Column(String(10))
    demissao = Column(String(10))
    ajuizamento = Column(String(10))
    tipo_rescisao = Column(String(50))
    regime_trabalho = Column(String(50))
    carga_horaria = Column(Integer)
    maior_remuneracao = Column(Float)
    ultima_remuneracao = Column(Float)

    aviso_previo_tipo = Column(String(30))
    prescricao_quinquenal = Column(Boolean)
    prescricao_fgts = Column(Boolean)
    fgts_aliquota = Column(Float)
    fgts_multa_40 = Column(Boolean)
    fgts_multa_467 = Column(Boolean)
    honorarios_percentual = Column(Float)
    honorarios_parte_devedora = Column(String(30))
    correcao_indice = Column(String(100))
    juros_taxa = Column(String(50))
    ir_apurar = Column(Boolean, default=False)
    ir_meses_tributaveis = Column(Integer)

    dados_json = Column(Text)
    verbas_json = Column(Text)
    previa_texto = Column(Text)
    previa_html = Column(Text)

    arquivo_sentenca = Column(String(500))
    formato_sentenca = Column(String(20))
    arquivo_pjc = Column(String(500))
    relatorio_pdf = Column(String(500))

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    confirmado_em = Column(DateTime)
    exportado_em = Column(DateTime)

    processo = relationship("Processo", back_populates="calculos")
    verbas = relationship("Verba", back_populates="calculo", cascade="all, delete-orphan")
    interacoes_hitl = relationship("InteracaoHITL", back_populates="calculo", cascade="all, delete-orphan")
    entradas_rastreabilidade = relationship("EntradaRastreabilidade", back_populates="calculo", cascade="all, delete-orphan")
    correcoes = relationship("CorrecaoUsuario", back_populates="calculo", cascade="all, delete-orphan")

    def dados(self) -> dict[str, Any]:
        return json.loads(self.dados_json) if self.dados_json else {}

    def verbas_mapeadas(self) -> dict[str, Any]:
        return json.loads(self.verbas_json) if self.verbas_json else {}

    def __repr__(self) -> str:
        return f"<Calculo {self.sessao_id} [{self.status}]>"


class Verba(Base):
    """Representa uma verba individual do cálculo."""
    __tablename__ = "verbas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    calculo_id = Column(Integer, ForeignKey("calculos.id"), nullable=False)

    nome_sentenca = Column(String(200))
    nome_pjecalc = Column(String(200))
    tipo = Column(String(20))
    caracteristica = Column(String(30))
    ocorrencia = Column(String(30))
    lancamento = Column(String(20))
    periodo_inicio = Column(String(10))
    periodo_fim = Column(String(10))
    percentual = Column(Float)
    base_calculo = Column(String(100))
    valor_informado = Column(Float)
    incidencia_fgts = Column(Boolean)
    incidencia_inss = Column(Boolean)
    incidencia_ir = Column(Boolean)
    compor_principal = Column(Boolean)
    verba_principal_ref = Column(String(200))
    confianca = Column(Float)
    mapeada = Column(Boolean, default=False)
    assunto_cnj = Column(String(300))
    pagina_pjecalc = Column(String(50))
    dados_json = Column(Text)

    calculo = relationship("Calculo", back_populates="verbas")

    def __repr__(self) -> str:
        return f"<Verba '{self.nome_pjecalc or self.nome_sentenca}'>"


class InteracaoHITL(Base):
    """Registra cada interação humano-agente durante o processamento."""
    __tablename__ = "interacoes_hitl"

    id = Column(Integer, primary_key=True, autoincrement=True)
    calculo_id = Column(Integer, ForeignKey("calculos.id"), nullable=False)

    timestamp = Column(DateTime, default=datetime.utcnow)
    categoria = Column(String(50))
    urgencia = Column(String(30))
    campo = Column(String(200))
    mensagem = Column(Text)
    opcoes_json = Column(Text)
    resposta_usuario = Column(Text)
    trecho_sentenca = Column(Text)

    calculo = relationship("Calculo", back_populates="interacoes_hitl")


class EntradaRastreabilidade(Base):
    """Rastreabilidade sentença → parâmetro → PJE-Calc."""
    __tablename__ = "rastreabilidade"

    id = Column(Integer, primary_key=True, autoincrement=True)
    calculo_id = Column(Integer, ForeignKey("calculos.id"), nullable=False)

    campo_pjecalc = Column(String(200))
    valor = Column(Text)
    fonte = Column(String(30))
    confianca = Column(Float)
    trecho_sentenca = Column(Text)
    pagina_pdf = Column(Integer)
    confirmado_usuario = Column(Boolean, default=False)
    pergunta_formulada = Column(Text)
    resposta_usuario = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

    calculo = relationship("Calculo", back_populates="entradas_rastreabilidade")


# ── Novos modelos — Learning Engine ──────────────────────────────────────────

class SessaoAprendizado(Base):
    """
    Representa uma sessão periódica de análise de correções.
    Cada sessão processa N correções acumuladas e gera M novas regras via LLM.
    """
    __tablename__ = "sessoes_aprendizado"

    id = Column(Integer, primary_key=True, autoincrement=True)

    status = Column(String(30), default="pendente", nullable=False)
    # pendente | em_andamento | concluida | erro

    num_correcoes_analisadas = Column(Integer)
    num_regras_geradas = Column(Integer)
    num_regras_atualizadas = Column(Integer)

    modelo_llm = Column(String(100))
    resumo = Column(Text)
    snapshot_json = Column(Text)         # JSON completo das regras da sessão
    erro_msg = Column(Text)              # mensagem de erro se status=erro

    iniciada_em = Column(DateTime, default=datetime.utcnow)
    concluida_em = Column(DateTime)

    regras = relationship("RegrasAprendidas", back_populates="sessao_aprendizado")

    def __repr__(self) -> str:
        return f"<SessaoAprendizado #{self.id} [{self.status}]>"


class RegrasAprendidas(Base):
    """
    Armazena regras de mapeamento geradas pelo LLM a partir de análise de correções.
    Estas regras são injetadas nos system prompts de extrações futuras.

    Ciclo de vida:
    - Criada em uma SessaoAprendizado com ativa=True
    - aplicacoes incrementa cada vez que é incluída num prompt
    - acertos incrementa quando o cálculo é confirmado sem nova correção no mesmo campo
    - Desativada manualmente ou quando substituída por regra mais precisa
    """
    __tablename__ = "regras_aprendidas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sessao_aprendizado_id = Column(Integer, ForeignKey("sessoes_aprendizado.id"), nullable=True)

    tipo_regra = Column(String(50), nullable=False, index=True)
    # mapeamento_verba | extracao_campo | classificacao_parametro | reflexa | correcao_juros

    condicao = Column(Text, nullable=False)    # quando esta regra se aplica
    acao = Column(Text, nullable=False)        # o que a regra prescreve
    exemplos_json = Column(Text)               # JSON: [{entrada, correcao, contexto}]

    confianca = Column(Float, default=0.7)
    aplicacoes = Column(Integer, default=0)
    acertos = Column(Integer, default=0)

    ativa = Column(Boolean, default=True, nullable=False, index=True)

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessao_aprendizado = relationship("SessaoAprendizado", back_populates="regras")

    @property
    def taxa_acerto(self) -> float:
        """Taxa de acerto da regra (0.0 se nunca aplicada)."""
        return self.acertos / self.aplicacoes if self.aplicacoes > 0 else 0.0

    def __repr__(self) -> str:
        return f"<RegrasAprendidas #{self.id} [{self.tipo_regra}] ativa={self.ativa}>"


class CorrecaoUsuario(Base):
    """
    Registra cada correção feita pelo usuário na tela de Prévia.
    Fonte primária de dados para o Learning Engine.

    Toda edição bem-sucedida em /previa/{sessao_id}/editar gera uma CorrecaoUsuario.
    O LearningEngine processa correções com incorporada_em_regra=False.
    """
    __tablename__ = "correcoes_usuario"

    id = Column(Integer, primary_key=True, autoincrement=True)
    calculo_id = Column(Integer, ForeignKey("calculos.id"), nullable=False)
    sessao_id = Column(String(36), index=True, nullable=False)

    tipo_correcao = Column(String(50), nullable=False)
    # campo_valor | verba_mapeamento | verba_incidencia | verba_adicionada | verba_removida

    entidade = Column(String(50))      # contrato | fgts | honorarios | verba | correcao_juros
    campo = Column(String(200))        # dotted path: "contrato.admissao", "verba[2].tipo"

    valor_antes = Column(Text)         # JSON-serializado
    valor_depois = Column(Text)        # JSON-serializado

    confianca_ia_antes = Column(Float)
    fonte_original = Column(String(30), default="EXTRACAO_AUTOMATICA")
    # EXTRACAO_AUTOMATICA | CLASSIFICACAO_LLM | USUARIO_ANTERIOR

    contexto_json = Column(Text)
    # JSON: {numero_processo, reclamante, tipo_rescisao, num_verbas, trt_regiao, ...}

    incorporada_em_regra = Column(Boolean, default=False, nullable=False, index=True)
    sessao_aprendizado_id = Column(Integer, ForeignKey("sessoes_aprendizado.id"), nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    calculo = relationship("Calculo", back_populates="correcoes")

    def __repr__(self) -> str:
        return f"<CorrecaoUsuario #{self.id} {self.campo} sessao={self.sessao_id}>"


# ── Criar tabelas ─────────────────────────────────────────────────────────────

def criar_tabelas() -> None:
    """Cria todas as tabelas no banco de dados (idempotente — safe em produção)."""
    Base.metadata.create_all(bind=engine)


# ── Repositório original (inalterado) ─────────────────────────────────────────

class RepositorioCalculo:
    """
    Camada de acesso a dados para cálculos PJE-Calc.
    Preservada integralmente do database.py original para backward compat.
    """

    def __init__(self, db: Session):
        self.db = db

    def obter_ou_criar_processo(self, numero: str, dados: dict[str, Any]) -> Processo:
        processo = self.db.query(Processo).filter_by(numero_processo=numero).first()
        if not processo:
            proc_dados = dados.get("processo", {})
            processo = Processo(
                numero_processo=numero,
                reclamante=proc_dados.get("reclamante"),
                reclamado=proc_dados.get("reclamado"),
                estado=proc_dados.get("estado"),
                municipio=proc_dados.get("municipio"),
                vara=proc_dados.get("vara"),
            )
            self.db.add(processo)
            self.db.flush()
        return processo

    def criar_calculo(
        self,
        sessao_id: str,
        numero_processo: str,
        dados: dict[str, Any],
        verbas_mapeadas: dict[str, Any],
        arquivo_sentenca: str | None = None,
        formato_sentenca: str | None = None,
    ) -> Calculo:
        """Cria ou atualiza um cálculo vinculado ao número do processo."""
        processo = self.obter_ou_criar_processo(numero_processo, dados)

        calculo = self.db.query(Calculo).filter_by(sessao_id=sessao_id).first()
        if not calculo:
            calculo = Calculo(sessao_id=sessao_id, processo_id=processo.id)
            self.db.add(calculo)

        cont = dados.get("contrato", {})
        fgts = dados.get("fgts", {})
        _hon_raw = dados.get("honorarios", {})
        if isinstance(_hon_raw, list):
            hon = _hon_raw[0] if _hon_raw else {}
        else:
            hon = _hon_raw if isinstance(_hon_raw, dict) else {}
        cj = dados.get("correcao_juros", {})
        presc = dados.get("prescricao", {})
        ap = dados.get("aviso_previo", {})
        ir = dados.get("imposto_renda", {})

        calculo.admissao = cont.get("admissao")
        calculo.demissao = cont.get("demissao")
        calculo.ajuizamento = cont.get("ajuizamento")
        calculo.tipo_rescisao = cont.get("tipo_rescisao")
        calculo.regime_trabalho = cont.get("regime")
        calculo.carga_horaria = cont.get("carga_horaria")
        calculo.maior_remuneracao = cont.get("maior_remuneracao")
        calculo.ultima_remuneracao = cont.get("ultima_remuneracao")
        calculo.aviso_previo_tipo = ap.get("tipo")
        calculo.prescricao_quinquenal = presc.get("quinquenal")
        calculo.prescricao_fgts = presc.get("fgts")
        calculo.fgts_aliquota = fgts.get("aliquota")
        calculo.fgts_multa_40 = fgts.get("multa_40")
        calculo.fgts_multa_467 = fgts.get("multa_467")
        calculo.honorarios_percentual = hon.get("percentual")
        calculo.honorarios_parte_devedora = hon.get("parte_devedora")
        calculo.correcao_indice = cj.get("indice_correcao")
        calculo.juros_taxa = cj.get("taxa_juros")
        calculo.ir_apurar = ir.get("apurar", False)
        calculo.ir_meses_tributaveis = ir.get("meses_tributaveis")
        calculo.dados_json = json.dumps(dados, ensure_ascii=False)
        calculo.verbas_json = json.dumps(verbas_mapeadas, ensure_ascii=False)
        calculo.arquivo_sentenca = arquivo_sentenca
        calculo.formato_sentenca = formato_sentenca
        calculo.atualizado_em = datetime.utcnow()

        self.db.flush()
        self._sincronizar_verbas(calculo, verbas_mapeadas)
        self.db.commit()
        return calculo

    def salvar_previa(self, sessao_id: str, previa_texto: str, previa_html: str | None = None) -> None:
        calculo = self._obter_calculo(sessao_id)
        calculo.previa_texto = previa_texto
        if previa_html:
            calculo.previa_html = previa_html
        calculo.status = "previa_gerada"
        calculo.atualizado_em = datetime.utcnow()
        self.db.commit()

    def confirmar_previa(self, sessao_id: str) -> None:
        calculo = self._obter_calculo(sessao_id)
        calculo.status = "confirmado"
        calculo.confirmado_em = datetime.utcnow()
        calculo.atualizado_em = datetime.utcnow()
        self.db.commit()

    def atualizar_dados(self, sessao_id: str, dados: dict[str, Any], verbas_mapeadas: dict[str, Any] | None = None) -> None:
        calculo = self._obter_calculo(sessao_id)
        calculo.dados_json = json.dumps(dados, ensure_ascii=False)
        if verbas_mapeadas is not None:
            calculo.verbas_json = json.dumps(verbas_mapeadas, ensure_ascii=False)
            self._sincronizar_verbas(calculo, verbas_mapeadas)
        calculo.atualizado_em = datetime.utcnow()
        self.db.commit()

    def marcar_exportado(self, sessao_id: str, caminho_pjc: str) -> None:
        calculo = self._obter_calculo(sessao_id)
        calculo.arquivo_pjc = caminho_pjc
        calculo.status = "pjc_exportado"
        calculo.exportado_em = datetime.utcnow()
        calculo.atualizado_em = datetime.utcnow()
        self.db.commit()

    def registrar_interacao_hitl(self, sessao_id: str, entrada: dict[str, Any]) -> None:
        calculo = self._obter_calculo(sessao_id)
        interacao = InteracaoHITL(
            calculo_id=calculo.id,
            categoria=entrada.get("categoria"),
            urgencia=entrada.get("urgencia"),
            campo=entrada.get("campo"),
            mensagem=entrada.get("mensagem"),
            opcoes_json=json.dumps(entrada.get("opcoes"), ensure_ascii=False) if entrada.get("opcoes") else None,
            resposta_usuario=entrada.get("resposta_usuario"),
            trecho_sentenca=entrada.get("trecho_sentenca"),
        )
        self.db.add(interacao)
        self.db.commit()

    def registrar_rastreabilidade(self, sessao_id: str, entrada: dict[str, Any]) -> None:
        calculo = self._obter_calculo(sessao_id)
        rastr = EntradaRastreabilidade(
            calculo_id=calculo.id,
            campo_pjecalc=entrada.get("campo_pjecalc"),
            valor=str(entrada.get("valor")) if entrada.get("valor") is not None else None,
            fonte=entrada.get("fonte"),
            confianca=entrada.get("confianca"),
            trecho_sentenca=entrada.get("trecho_sentenca"),
            pagina_pdf=entrada.get("pagina_pdf"),
            confirmado_usuario=entrada.get("confirmado_usuario", False),
            pergunta_formulada=entrada.get("pergunta_formulada"),
            resposta_usuario=entrada.get("resposta_usuario"),
        )
        self.db.add(rastr)
        self.db.commit()

    def buscar_por_processo(self, numero_processo: str) -> list[Calculo]:
        return (
            self.db.query(Calculo)
            .join(Processo)
            .filter(Processo.numero_processo == numero_processo)
            .order_by(Calculo.criado_em.desc())
            .all()
        )

    def buscar_previa(self, numero_processo: str) -> Calculo | None:
        return (
            self.db.query(Calculo)
            .join(Processo)
            .filter(
                Processo.numero_processo == numero_processo,
                Calculo.previa_texto.isnot(None),
            )
            .order_by(Calculo.criado_em.desc())
            .first()
        )

    def listar_processos(self, limit: int = 50, offset: int = 0) -> list[Processo]:
        return (
            self.db.query(Processo)
            .order_by(Processo.atualizado_em.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def buscar_sessao(self, sessao_id: str) -> Calculo | None:
        return self.db.query(Calculo).filter_by(sessao_id=sessao_id).first()

    def _obter_calculo(self, sessao_id: str) -> Calculo:
        calculo = self.db.query(Calculo).filter_by(sessao_id=sessao_id).first()
        if not calculo:
            raise ValueError(f"Cálculo não encontrado para sessão: {sessao_id}")
        return calculo

    def _sincronizar_verbas(self, calculo: Calculo, verbas_mapeadas: dict[str, Any]) -> None:
        for verba_existente in list(calculo.verbas):
            self.db.delete(verba_existente)
        self.db.flush()

        todas = (
            verbas_mapeadas.get("predefinidas", [])
            + verbas_mapeadas.get("personalizadas", [])
            + verbas_mapeadas.get("nao_reconhecidas", [])
        )
        for v in todas:
            verba_orm = Verba(
                calculo_id=calculo.id,
                nome_sentenca=v.get("nome_sentenca"),
                nome_pjecalc=v.get("nome_pjecalc"),
                tipo=v.get("tipo"),
                caracteristica=v.get("caracteristica"),
                ocorrencia=v.get("ocorrencia"),
                lancamento=v.get("lancamento"),
                periodo_inicio=v.get("periodo_inicio"),
                periodo_fim=v.get("periodo_fim"),
                percentual=v.get("percentual"),
                base_calculo=str(v.get("base_calculo")) if v.get("base_calculo") else None,
                valor_informado=v.get("valor_informado"),
                incidencia_fgts=v.get("incidencia_fgts"),
                incidencia_inss=v.get("incidencia_inss"),
                incidencia_ir=v.get("incidencia_ir"),
                compor_principal=v.get("compor_principal"),
                verba_principal_ref=v.get("verba_principal_ref"),
                confianca=v.get("confianca"),
                mapeada=v.get("mapeada", False),
                assunto_cnj=v.get("assunto_cnj_sugerido"),
                pagina_pjecalc=v.get("pagina_pjecalc", "Verbas"),
                dados_json=json.dumps(v, ensure_ascii=False),
            )
            self.db.add(verba_orm)


# ── Dependency injection helper (FastAPI) ─────────────────────────────────────

def get_db():
    """Gerador de sessão para uso com FastAPI Depends."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Inicialização ─────────────────────────────────────────────────────────────
criar_tabelas()
