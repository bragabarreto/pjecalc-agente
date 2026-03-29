# learning/correction_tracker.py — Registra correções do usuário na prévia
#
# Chamado por webapp.py após cada edição bem-sucedida em /previa/{sessao_id}/editar.
# As correções registradas alimentam o LearningEngine.

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CorrectionTracker:
    """
    Rastreia e persiste correções feitas pelo usuário na tela de Prévia.

    Cada edição bem-sucedida em /previa/{sessao_id}/editar gera um registro
    CorrecaoUsuario no banco de dados. O LearningEngine consulta esses registros
    periodicamente para gerar novas regras de mapeamento.

    Args:
        db: Sessão SQLAlchemy ativa

    Example:
        # Em webapp.py, após editar campo:
        tracker = CorrectionTracker(db)
        tracker.record_field_correction(
            sessao_id=sessao_id,
            campo="contrato.admissao",
            valor_antes="01/01/2020",
            valor_depois="15/01/2020",
            confianca_ia=0.75,
            fonte_original="EXTRACAO_AUTOMATICA",
            contexto={"numero_processo": "...", "reclamante": "..."},
        )
        if tracker.should_trigger_learning():
            background_tasks.add_task(run_learning_session, db_session)
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Interface pública ──────────────────────────────────────────────────────

    def record_field_correction(
        self,
        sessao_id: str,
        campo: str,
        valor_antes: Any,
        valor_depois: Any,
        confianca_ia: Optional[float] = None,
        fonte_original: str = "EXTRACAO_AUTOMATICA",
        contexto: Optional[dict] = None,
    ) -> Any:
        """
        Registra uma correção de campo simples (não-verba).

        Args:
            sessao_id: UUID da sessão de cálculo
            campo: Dotted path do campo corrigido (ex: "contrato.admissao")
            valor_antes: Valor extraído pela IA (antes da correção)
            valor_depois: Valor corrigido pelo usuário
            confianca_ia: Confiança da extração original (0.0–1.0)
            fonte_original: Origem do valor antes ("EXTRACAO_AUTOMATICA" | "CLASSIFICACAO_LLM")
            contexto: Dict com contexto do processo para análise futura

        Returns:
            Instância CorrecaoUsuario salva
        """
        return self._save_correction(
            sessao_id=sessao_id,
            tipo_correcao="campo_valor",
            entidade=self._entidade_from_campo(campo),
            campo=campo,
            valor_antes=valor_antes,
            valor_depois=valor_depois,
            confianca_ia=confianca_ia,
            fonte_original=fonte_original,
            contexto=contexto,
        )

    def record_verba_correction(
        self,
        sessao_id: str,
        verba_index: int,
        campo: str,
        valor_antes: Any,
        valor_depois: Any,
        verba_nome: str = "",
        confianca_ia: Optional[float] = None,
    ) -> Any:
        """
        Registra uma correção em uma verba específica.

        Args:
            sessao_id: UUID da sessão
            verba_index: Índice da verba no array de verbas
            campo: Campo da verba corrigido (ex: "incidencia_fgts", "nome_pjecalc")
            valor_antes: Valor antes da correção
            valor_depois: Valor corrigido
            verba_nome: Nome da verba para contexto
            confianca_ia: Confiança do mapeamento original
        """
        campo_path = f"verba[{verba_index}].{campo}"
        return self._save_correction(
            sessao_id=sessao_id,
            tipo_correcao="verba_mapeamento" if campo in ("nome_pjecalc", "lancamento") else "verba_incidencia",
            entidade="verba",
            campo=campo_path,
            valor_antes=valor_antes,
            valor_depois=valor_depois,
            confianca_ia=confianca_ia,
            fonte_original="CLASSIFICACAO_LLM",
            contexto={"verba_nome": verba_nome, "verba_index": verba_index},
        )

    def record_verba_added(self, sessao_id: str, verba_dados: dict) -> Any:
        """Registra que o usuário adicionou uma verba manualmente."""
        return self._save_correction(
            sessao_id=sessao_id,
            tipo_correcao="verba_adicionada",
            entidade="verba",
            campo="verbas",
            valor_antes=None,
            valor_depois=verba_dados,
            contexto={"verba_nome": verba_dados.get("nome_sentenca", "")},
        )

    def record_verba_removed(self, sessao_id: str, verba_dados: dict) -> Any:
        """Registra que o usuário removeu uma verba."""
        return self._save_correction(
            sessao_id=sessao_id,
            tipo_correcao="verba_removida",
            entidade="verba",
            campo="verbas",
            valor_antes=verba_dados,
            valor_depois=None,
            contexto={"verba_nome": verba_dados.get("nome_sentenca", "")},
        )

    def get_unincorporated_count(self) -> int:
        """
        Retorna o número de correções ainda não processadas pelo LearningEngine.

        Returns:
            Contagem de CorrecaoUsuario com incorporada_em_regra=False
        """
        try:
            from infrastructure.database import CorrecaoUsuario
            return (
                self._db.query(CorrecaoUsuario)
                .filter(CorrecaoUsuario.incorporada_em_regra == False)
                .count()
            )
        except Exception as e:
            logger.warning("count_unincorporated_failed", error=str(e))
            return 0

    def should_trigger_learning(self) -> bool:
        """
        Retorna True se o limiar de correções para disparar uma sessão foi atingido.

        O limiar é configurado por LEARNING_FEEDBACK_THRESHOLD (padrão: 10).
        """
        try:
            from infrastructure.config import settings
            threshold = settings.learning_feedback_threshold
            if not settings.learning_enabled:
                return False
        except ImportError:
            threshold = 10

        count = self.get_unincorporated_count()
        return count >= threshold

    # ── Auxiliares privados ────────────────────────────────────────────────────

    def _save_correction(
        self,
        sessao_id: str,
        tipo_correcao: str,
        entidade: str,
        campo: str,
        valor_antes: Any,
        valor_depois: Any,
        confianca_ia: Optional[float] = None,
        fonte_original: str = "EXTRACAO_AUTOMATICA",
        contexto: Optional[dict] = None,
    ) -> Any:
        """Persiste uma CorrecaoUsuario no banco de dados."""
        try:
            from infrastructure.database import CorrecaoUsuario, Calculo

            # Buscar calculo_id
            calculo = self._db.query(Calculo).filter_by(sessao_id=sessao_id).first()
            if not calculo:
                logger.warning("correction_no_calculo", sessao_id=sessao_id)
                return None

            correcao = CorrecaoUsuario(
                calculo_id=calculo.id,
                sessao_id=sessao_id,
                tipo_correcao=tipo_correcao,
                entidade=entidade,
                campo=campo,
                valor_antes=json.dumps(valor_antes, ensure_ascii=False, default=str) if valor_antes is not None else None,
                valor_depois=json.dumps(valor_depois, ensure_ascii=False, default=str) if valor_depois is not None else None,
                confianca_ia_antes=confianca_ia,
                fonte_original=fonte_original,
                contexto_json=json.dumps(contexto, ensure_ascii=False) if contexto else None,
                incorporada_em_regra=False,
                timestamp=datetime.utcnow(),
            )
            self._db.add(correcao)
            self._db.commit()

            logger.debug(
                "correction_recorded",
                sessao_id=sessao_id,
                campo=campo,
                tipo=tipo_correcao,
            )
            return correcao

        except Exception as e:
            logger.error("correction_save_failed", sessao_id=sessao_id, error=str(e))
            try:
                self._db.rollback()
            except Exception:
                pass
            return None

    def _entidade_from_campo(self, campo: str) -> str:
        """Infere a entidade a partir do dotted path do campo."""
        prefix = campo.split(".")[0] if "." in campo else campo
        mapping = {
            "contrato": "contrato",
            "processo": "processo",
            "fgts": "fgts",
            "honorarios": "honorarios",
            "correcao_juros": "correcao_juros",
            "prescricao": "prescricao",
            "aviso_previo": "aviso_previo",
            "imposto_renda": "imposto_renda",
            "contribuicao_social": "contribuicao_social",
            "historico_salarial": "historico_salarial",
        }
        return mapping.get(prefix, prefix)
