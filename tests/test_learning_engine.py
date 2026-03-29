# tests/test_learning_engine.py — Testes do motor de aprendizado contínuo

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures de banco em memória ──────────────────────────────────────────────

@pytest.fixture()
def db_session():
    """Sessão SQLAlchemy em SQLite in-memory para isolamento total entre testes."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    # Criar tabelas usando o módulo infrastructure
    try:
        from infrastructure.database import Base
        Base.metadata.create_all(bind=engine)
    except ImportError:
        from database import Base
        Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def mock_orchestrator():
    """Orquestrador mock que retorna regras simples."""
    orch = MagicMock()
    orch.complete.return_value = {
        "regras": [
            {
                "tipo_regra": "mapeamento_verba",
                "condicao": "quando a sentença mencionar horas extras com adicional de 50%",
                "acao": "mapear para verba 'HORAS EXTRAS 50%' com ocorrencia=Mensal",
                "confianca": 0.85,
                "justificativa": "Adicional de 50% é o padrão CLT art. 7º XVI",
            }
        ],
        "resumo": "Padrão de horas extras com adicional de 50% identificado.",
    }
    return orch


# ── Testes: CorrectionTracker ─────────────────────────────────────────────────

class TestCorrectionTracker:
    def test_record_field_correction_creates_record(self, db_session):
        """record_field_correction() cria um CorrecaoUsuario no banco."""
        from learning.correction_tracker import CorrectionTracker
        from database import Calculo, Processo

        # Criar processo e cálculo mínimos
        proc = Processo(numero_processo="1234567-89.2023.5.07.0001", reclamante="João")
        db_session.add(proc)
        db_session.flush()
        calc = Calculo(
            sessao_id="sess-001",
            status="previa_gerada",
            dados_json="{}",
            verbas_json="{}",
            processo_id=proc.id,
        )
        db_session.add(calc)
        db_session.commit()

        tracker = CorrectionTracker(db_session)
        result = tracker.record_field_correction(
            sessao_id="sess-001",
            campo="contrato.admissao",
            valor_antes="01/01/2020",
            valor_depois="15/01/2020",
            confianca_ia=0.75,
        )

        assert result is not None
        assert result.campo == "contrato.admissao"
        assert result.incorporada_em_regra is False

    def test_get_unincorporated_count_returns_zero_initially(self, db_session):
        """Contador retorna 0 quando não há correções pendentes."""
        from learning.correction_tracker import CorrectionTracker

        tracker = CorrectionTracker(db_session)
        assert tracker.get_unincorporated_count() == 0

    def test_should_trigger_learning_false_below_threshold(self, db_session):
        """should_trigger_learning() retorna False quando abaixo do threshold."""
        from learning.correction_tracker import CorrectionTracker

        tracker = CorrectionTracker(db_session)
        # Sem correções registradas → abaixo do threshold padrão (10)
        assert tracker.should_trigger_learning() is False

    def test_record_verba_correction(self, db_session):
        """record_verba_correction() cria registro com tipo verba_mapeamento."""
        from learning.correction_tracker import CorrectionTracker
        from database import Calculo, Processo

        proc = Processo(numero_processo="7654321-00.2024.5.07.0001", reclamante="Maria")
        db_session.add(proc)
        db_session.flush()
        calc = Calculo(
            sessao_id="sess-002",
            status="previa_gerada",
            dados_json="{}",
            verbas_json="{}",
            processo_id=proc.id,
        )
        db_session.add(calc)
        db_session.commit()

        tracker = CorrectionTracker(db_session)
        result = tracker.record_verba_correction(
            sessao_id="sess-002",
            verba_index=0,
            campo="nome_pjecalc",
            valor_antes="HORAS EXTRAS",
            valor_depois="HORAS EXTRAS 50%",
            verba_nome="Horas Extras",
            confianca_ia=0.60,
        )

        assert result is not None
        assert result.tipo_correcao == "verba_mapeamento"
        assert result.entidade == "verba"


# ── Testes: LearningEngine ────────────────────────────────────────────────────

class TestLearningEngine:
    def test_group_corrections_by_type_entity(self, db_session):
        """_group_corrections() agrupa correções por tipo_correcao/entidade."""
        from learning.learning_engine import LearningEngine

        engine = LearningEngine(db_session, MagicMock())

        class FakeCorrecao:
            def __init__(self, tipo, entidade):
                self.tipo_correcao = tipo
                self.entidade = entidade

        correcoes = [
            FakeCorrecao("campo_valor", "contrato"),
            FakeCorrecao("campo_valor", "contrato"),
            FakeCorrecao("verba_mapeamento", "verba"),
        ]

        groups = engine._group_corrections(correcoes)

        assert "campo_valor/contrato" in groups
        assert len(groups["campo_valor/contrato"]) == 2
        assert "verba_mapeamento/verba" in groups

    def test_run_learning_session_no_corrections(self, db_session):
        """run_learning_session() retorna 'concluida' quando não há correções."""
        from learning.learning_engine import LearningEngine

        engine = LearningEngine(db_session, MagicMock())
        session = engine.run_learning_session()

        assert session.status == "concluida"
        assert session.num_correcoes_analisadas == 0
        assert session.num_regras_geradas == 0

    def test_find_similar_rule_below_threshold(self, db_session):
        """_find_similar_rule() retorna None quando sobreposição < 60%."""
        from learning.learning_engine import LearningEngine
        from database import RegrasAprendidas, SessaoAprendizado

        # Criar sessão e regra existente
        sess = SessaoAprendizado(status="concluida", iniciada_em=datetime.utcnow())
        db_session.add(sess)
        db_session.flush()
        regra = RegrasAprendidas(
            sessao_aprendizado_id=sess.id,
            tipo_regra="mapeamento_verba",
            condicao="quando mencionar férias vencidas período aquisitivo",
            acao="mapear para Férias Vencidas",
            confianca=0.80,
            ativa=True,
        )
        db_session.add(regra)
        db_session.commit()

        engine = LearningEngine(db_session, MagicMock())
        # Regra completamente diferente → não deve encontrar similar
        result = engine._find_similar_rule({
            "tipo_regra": "extracao_campo",
            "condicao": "número de processo formato CNJ",
        })
        assert result is None

    def test_save_rule_creates_record(self, db_session, mock_orchestrator):
        """_save_rule() persiste nova RegrasAprendidas no banco."""
        from learning.learning_engine import LearningEngine
        from database import SessaoAprendizado

        sess = SessaoAprendizado(status="em_andamento", iniciada_em=datetime.utcnow())
        db_session.add(sess)
        db_session.flush()
        db_session.commit()

        engine = LearningEngine(db_session, mock_orchestrator)
        rule_dict = {
            "tipo_regra": "mapeamento_verba",
            "condicao": "quando mencionar 'horas extras' com '50%'",
            "acao": "usar HORAS EXTRAS 50%",
            "confianca": 0.85,
        }
        result = engine._save_rule(rule_dict, sess.id)

        assert result is not None
        assert result.tipo_regra == "mapeamento_verba"
        assert abs(result.confianca - 0.85) < 0.001


# ── Testes: RuleInjector ──────────────────────────────────────────────────────

class TestRuleInjector:
    def test_get_active_rules_empty_db(self, db_session):
        """get_active_rules_for_prompt() retorna string vazia quando sem regras."""
        from learning.rule_injector import RuleInjector

        injector = RuleInjector(db_session)
        result = injector.get_active_rules_for_prompt("legal_extraction")
        assert result == ""

    def test_cache_invalidation(self, db_session):
        """invalidate_cache() limpa o cache interno."""
        from learning.rule_injector import RuleInjector
        import time

        injector = RuleInjector(db_session)
        # Forçar timestamp manualmente (simula cache populado)
        injector._cache_ts = time.monotonic()
        assert injector._cache_ts > 0

        injector.invalidate_cache()
        assert injector._cache_ts == 0
        assert injector._cache == []

    def test_filter_by_task_legal_extraction(self, db_session):
        """_filter_by_task() retorna apenas regras relevantes para o task_type."""
        from learning.rule_injector import RuleInjector
        from database import RegrasAprendidas, SessaoAprendizado

        sess = SessaoAprendizado(status="concluida", iniciada_em=datetime.utcnow())
        db_session.add(sess)
        db_session.flush()

        regras = [
            RegrasAprendidas(
                sessao_aprendizado_id=sess.id, tipo_regra="extracao_campo",
                condicao="c1", acao="a1", confianca=0.8, ativa=True,
            ),
            RegrasAprendidas(
                sessao_aprendizado_id=sess.id, tipo_regra="screenshot_hint",
                condicao="c2", acao="a2", confianca=0.8, ativa=True,
            ),
        ]
        for r in regras:
            db_session.add(r)
        db_session.commit()

        injector = RuleInjector(db_session)
        filtered = injector._filter_by_task(regras, "legal_extraction")

        # "extracao_campo" é relevante para legal_extraction; "screenshot_hint" não
        tipos = [r.tipo_regra for r in filtered]
        assert "extracao_campo" in tipos
        assert "screenshot_hint" not in tipos

    def test_record_rules_usage_increments_count(self, db_session):
        """record_rules_usage() incrementa o campo aplicacoes."""
        from learning.rule_injector import RuleInjector
        from database import RegrasAprendidas, SessaoAprendizado

        sess = SessaoAprendizado(status="concluida", iniciada_em=datetime.utcnow())
        db_session.add(sess)
        db_session.flush()
        regra = RegrasAprendidas(
            sessao_aprendizado_id=sess.id, tipo_regra="mapeamento_verba",
            condicao="c", acao="a", confianca=0.8, ativa=True, aplicacoes=0,
        )
        db_session.add(regra)
        db_session.commit()

        injector = RuleInjector(db_session)
        injector.record_rules_usage([regra.id])

        db_session.refresh(regra)
        assert regra.aplicacoes == 1
