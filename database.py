"""database.py — Shim de backward compatibility → infrastructure/database.py

Todos os ``from database import X`` existentes continuam funcionando sem alteração.
Os 3 novos modelos do Learning Engine (CorrecaoUsuario, RegrasAprendidas,
SessaoAprendizado) também ficam disponíveis via este shim.
"""
from __future__ import annotations

# ── Tentar carregar da infrastructure/ (novo pacote) ─────────────────────────
try:
    from infrastructure.database import *  # noqa: F401, F403
    from infrastructure.database import (  # noqa: F401
        Base,
        Processo,
        Calculo,
        Verba,
        InteracaoHITL,
        EntradaRastreabilidade,
        CorrecaoUsuario,
        RegrasAprendidas,
        SessaoAprendizado,
        RepositorioCalculo,
        SessionLocal,
        engine,
        get_db,
        criar_tabelas,
        DATABASE_URL,
    )
    _INFRASTRUCTURE_LOADED = True
except ImportError:
    _INFRASTRUCTURE_LOADED = False

# ── Fallback legado (infrastructure/ ainda não instalada) ────────────────────
if not _INFRASTRUCTURE_LOADED:
    import json
    import os
    from datetime import datetime
    from pathlib import Path
    from typing import Any

    from sqlalchemy import (
        Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
        create_engine as _ce, event,
    )
    from sqlalchemy.orm import (
        DeclarativeBase, Session, relationship, sessionmaker,
    )

    _DEFAULT_DB_PATH = Path(__file__).parent / "data" / "pjecalc_agent.db"
    _DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RAW_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")
    DATABASE_URL = (
        _RAW_URL.replace("postgres://", "postgresql://", 1)
        if _RAW_URL.startswith("postgres://")
        else _RAW_URL
    )
    _is_postgres = DATABASE_URL.startswith("postgresql")
    _connect_args = {} if _is_postgres else {"check_same_thread": False}
    engine = _ce(DATABASE_URL, connect_args=_connect_args)

    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, _):
        if not _is_postgres:
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    class Base(DeclarativeBase):
        pass

    class Processo(Base):
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

    class Calculo(Base):
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

        def dados(self) -> dict[str, Any]:
            return json.loads(self.dados_json) if self.dados_json else {}

        def verbas_mapeadas(self) -> dict[str, Any]:
            return json.loads(self.verbas_json) if self.verbas_json else {}

    class Verba(Base):
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

    class InteracaoHITL(Base):
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

    # Stubs mínimos dos novos modelos (para não quebrar imports no fallback)
    class CorrecaoUsuario(Base):
        __tablename__ = "correcoes_usuario"
        id = Column(Integer, primary_key=True)
        calculo_id = Column(Integer, ForeignKey("calculos.id"))
        sessao_id = Column(String(36), index=True)
        tipo_correcao = Column(String(50))
        entidade = Column(String(100))
        campo = Column(String(200))
        valor_antes = Column(Text)
        valor_depois = Column(Text)
        confianca_ia_antes = Column(Float)
        fonte_original = Column(String(50))
        contexto_json = Column(Text)
        incorporada_em_regra = Column(Boolean, default=False, index=True)
        sessao_aprendizado_id = Column(Integer)
        timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    class SessaoAprendizado(Base):
        __tablename__ = "sessoes_aprendizado"
        id = Column(Integer, primary_key=True)
        status = Column(String(30), default="pendente")
        num_correcoes_analisadas = Column(Integer, default=0)
        num_regras_geradas = Column(Integer, default=0)
        num_regras_atualizadas = Column(Integer, default=0)
        modelo_llm = Column(String(100))
        resumo = Column(Text)
        snapshot_json = Column(Text)
        erro_msg = Column(Text)
        iniciada_em = Column(DateTime, default=datetime.utcnow)
        concluida_em = Column(DateTime)

    class RegrasAprendidas(Base):
        __tablename__ = "regras_aprendidas"
        id = Column(Integer, primary_key=True)
        sessao_aprendizado_id = Column(Integer)
        tipo_regra = Column(String(50))
        condicao = Column(Text)
        acao = Column(Text)
        exemplos_json = Column(Text)
        confianca = Column(Float, default=0.7)
        aplicacoes = Column(Integer, default=0)
        acertos = Column(Integer, default=0)
        ativa = Column(Boolean, default=True)
        criado_em = Column(DateTime, default=datetime.utcnow)
        atualizado_em = Column(DateTime, default=datetime.utcnow)

        @property
        def taxa_acerto(self) -> int:
            if not self.aplicacoes:
                return 0
            return round((self.acertos / self.aplicacoes) * 100)

    class RepositorioCalculo:
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

        def criar_calculo(self, sessao_id, numero_processo, dados, verbas_mapeadas,
                          arquivo_sentenca=None, formato_sentenca=None):
            processo = self.obter_ou_criar_processo(numero_processo, dados)
            calculo = self.db.query(Calculo).filter_by(sessao_id=sessao_id).first()
            if not calculo:
                calculo = Calculo(sessao_id=sessao_id, processo_id=processo.id)
                self.db.add(calculo)
            cont = dados.get("contrato", {})
            calculo.admissao = cont.get("admissao")
            calculo.demissao = cont.get("demissao")
            calculo.ajuizamento = cont.get("ajuizamento")
            calculo.tipo_rescisao = cont.get("tipo_rescisao")
            calculo.dados_json = json.dumps(dados, ensure_ascii=False)
            calculo.verbas_json = json.dumps(verbas_mapeadas, ensure_ascii=False)
            calculo.arquivo_sentenca = arquivo_sentenca
            calculo.formato_sentenca = formato_sentenca
            calculo.atualizado_em = datetime.utcnow()
            self.db.flush()
            self._sincronizar_verbas(calculo, verbas_mapeadas)
            self.db.commit()
            return calculo

        def salvar_previa(self, sessao_id, previa_texto, previa_html=None):
            c = self._obter_calculo(sessao_id)
            c.previa_texto = previa_texto
            if previa_html:
                c.previa_html = previa_html
            c.status = "previa_gerada"
            c.atualizado_em = datetime.utcnow()
            self.db.commit()

        def confirmar_previa(self, sessao_id):
            c = self._obter_calculo(sessao_id)
            c.status = "confirmado"
            c.confirmado_em = datetime.utcnow()
            c.atualizado_em = datetime.utcnow()
            self.db.commit()

        def atualizar_dados(self, sessao_id, dados, verbas_mapeadas=None):
            c = self._obter_calculo(sessao_id)
            c.dados_json = json.dumps(dados, ensure_ascii=False)
            if verbas_mapeadas is not None:
                c.verbas_json = json.dumps(verbas_mapeadas, ensure_ascii=False)
                self._sincronizar_verbas(c, verbas_mapeadas)
            c.atualizado_em = datetime.utcnow()
            self.db.commit()

        def marcar_exportado(self, sessao_id, caminho_pjc):
            c = self._obter_calculo(sessao_id)
            c.arquivo_pjc = caminho_pjc
            c.status = "pjc_exportado"
            c.exportado_em = datetime.utcnow()
            c.atualizado_em = datetime.utcnow()
            self.db.commit()

        def registrar_interacao_hitl(self, sessao_id, entrada):
            c = self._obter_calculo(sessao_id)
            from sqlalchemy.orm import object_session
            interacao = InteracaoHITL(
                calculo_id=c.id,
                categoria=entrada.get("categoria"),
                mensagem=entrada.get("mensagem"),
            )
            self.db.add(interacao)
            self.db.commit()

        def registrar_rastreabilidade(self, sessao_id, entrada):
            c = self._obter_calculo(sessao_id)
            rastr = EntradaRastreabilidade(
                calculo_id=c.id,
                campo_pjecalc=entrada.get("campo_pjecalc"),
                valor=str(entrada.get("valor")) if entrada.get("valor") is not None else None,
                fonte=entrada.get("fonte"),
                confirmado_usuario=entrada.get("confirmado_usuario", False),
                pergunta_formulada=entrada.get("pergunta_formulada"),
                resposta_usuario=entrada.get("resposta_usuario"),
            )
            self.db.add(rastr)
            self.db.commit()

        def buscar_por_processo(self, numero_processo):
            return (
                self.db.query(Calculo).join(Processo)
                .filter(Processo.numero_processo == numero_processo)
                .order_by(Calculo.criado_em.desc()).all()
            )

        def buscar_previa(self, numero_processo):
            return (
                self.db.query(Calculo).join(Processo)
                .filter(Processo.numero_processo == numero_processo,
                        Calculo.previa_texto.isnot(None))
                .order_by(Calculo.criado_em.desc()).first()
            )

        def listar_processos(self, limit=50, offset=0):
            return (
                self.db.query(Processo)
                .order_by(Processo.atualizado_em.desc())
                .offset(offset).limit(limit).all()
            )

        def buscar_sessao(self, sessao_id):
            return self.db.query(Calculo).filter_by(sessao_id=sessao_id).first()

        def _obter_calculo(self, sessao_id):
            c = self.db.query(Calculo).filter_by(sessao_id=sessao_id).first()
            if not c:
                raise ValueError(f"Cálculo não encontrado: {sessao_id}")
            return c

        def _sincronizar_verbas(self, calculo, verbas_mapeadas):
            for v in list(calculo.verbas):
                self.db.delete(v)
            self.db.flush()
            for v in (verbas_mapeadas.get("predefinidas", [])
                      + verbas_mapeadas.get("personalizadas", [])
                      + verbas_mapeadas.get("nao_reconhecidas", [])):
                self.db.add(Verba(
                    calculo_id=calculo.id,
                    nome_sentenca=v.get("nome_sentenca"),
                    nome_pjecalc=v.get("nome_pjecalc"),
                    tipo=v.get("tipo"),
                    dados_json=json.dumps(v, ensure_ascii=False),
                ))

    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def criar_tabelas(bind=None):
        Base.metadata.create_all(bind=bind or engine)

    # criar_tabelas() chamado via app startup event no webapp.py
