# core/state_manager.py — Máquina de estado tipada para sessões do agente
#
# Eleva o dict raw do GestorHITL (human_loop.py) para um dataclass tipado.
# Mantém backward compat: o dict original ainda funciona via .to_dict() / .from_dict()

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """
    Estado completo de uma sessão de processamento do pjecalc-agente.

    Compatível com o formato dict salvo pelo GestorHITL.salvar_estado().
    """
    sessao_id: str
    fase_atual: str = "inicio"
    # inicio | ingestao | extracao | classificacao | previa | automacao | concluido | erro

    # Dados extraídos
    dados: dict[str, Any] = field(default_factory=dict)
    verbas_mapeadas: dict[str, Any] = field(default_factory=dict)

    # Rastreabilidade
    arquivo_sentenca: Optional[str] = None
    formato_sentenca: Optional[str] = None
    alertas: list[str] = field(default_factory=list)
    campos_ausentes: list[str] = field(default_factory=list)

    # Histórico de fases concluídas
    fases_concluidas: list[str] = field(default_factory=list)

    # Timestamps
    criado_em: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    atualizado_em: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Interações HITL registradas
    interacoes: list[dict[str, Any]] = field(default_factory=list)

    # Metadados extras (extensível)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict compatível com o formato legado do GestorHITL."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentState":
        """Desserializa a partir de dict (format legado ou novo)."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)


class StateManager:
    """
    Gerencia persistência e recuperação do estado de sessões.

    Eleva as funções salvar_estado/carregar_estado do GestorHITL para
    uma classe com:
    - Escrita atômica (escreve em .tmp e renomeia)
    - Diff entre estados para identificar correções do usuário
    - Integração com o Learning Engine

    Args:
        sessions_dir: Diretório onde os arquivos JSON de estado são salvos
    """

    def __init__(self, sessions_dir: Optional[Path] = None) -> None:
        if sessions_dir is None:
            try:
                from infrastructure.config import settings
                sessions_dir = settings.sessions_dir
            except ImportError:
                sessions_dir = Path("data/logs/sessions")
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Interface pública ──────────────────────────────────────────────────────

    def checkpoint(self, state: AgentState) -> Path:
        """
        Persiste o estado atual em disco (escrita atômica via .tmp).

        Args:
            state: Estado atual da sessão

        Returns:
            Caminho do arquivo salvo
        """
        state.atualizado_em = datetime.utcnow().isoformat()
        path = self._state_path(state.sessao_id)
        tmp_path = path.with_suffix(".tmp")

        try:
            tmp_path.write_text(
                json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.rename(path)
            logger.debug("state_checkpoint", sessao_id=state.sessao_id, fase=state.fase_atual)
        except OSError as e:
            logger.error("state_checkpoint_failed", sessao_id=state.sessao_id, error=str(e))
            raise

        return path

    def recover(self, sessao_id: str) -> Optional[AgentState]:
        """
        Carrega o estado mais recente de uma sessão.

        Args:
            sessao_id: UUID da sessão

        Returns:
            AgentState se encontrado, None caso contrário
        """
        path = self._state_path(sessao_id)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            state = AgentState.from_dict(data)
            logger.debug("state_recovered", sessao_id=sessao_id, fase=state.fase_atual)
            return state
        except Exception as e:
            logger.error("state_recovery_failed", sessao_id=sessao_id, error=str(e))
            return None

    def diff(
        self,
        state_before: AgentState,
        state_after: AgentState,
    ) -> list[dict[str, Any]]:
        """
        Compara dois estados e retorna lista de diferenças (campo, antes, depois).

        Usado pelo Learning Engine para detectar correções feitas pelo usuário
        entre a extração automática e a confirmação da prévia.

        Args:
            state_before: Estado após extração automática
            state_after: Estado após edições do usuário

        Returns:
            Lista de diffs: [{campo, valor_antes, valor_depois}, ...]
        """
        diffs: list[dict[str, Any]] = []
        self._diff_dict(
            state_before.dados,
            state_after.dados,
            prefix="dados",
            diffs=diffs,
        )
        return diffs

    def delete(self, sessao_id: str) -> None:
        """Remove o arquivo de estado de uma sessão concluída."""
        path = self._state_path(sessao_id)
        path.unlink(missing_ok=True)

    # ── Auxiliares privados ────────────────────────────────────────────────────

    def _state_path(self, sessao_id: str) -> Path:
        return self._dir / f"{sessao_id}_estado.json"

    def _diff_dict(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        prefix: str,
        diffs: list[dict[str, Any]],
    ) -> None:
        """Recursivamente compara dois dicts e acumula diferenças."""
        all_keys = set(before.keys()) | set(after.keys())
        for key in all_keys:
            full_path = f"{prefix}.{key}"
            v_before = before.get(key)
            v_after = after.get(key)

            if isinstance(v_before, dict) and isinstance(v_after, dict):
                self._diff_dict(v_before, v_after, full_path, diffs)
            elif v_before != v_after:
                diffs.append({
                    "campo": full_path,
                    "valor_antes": v_before,
                    "valor_depois": v_after,
                })
