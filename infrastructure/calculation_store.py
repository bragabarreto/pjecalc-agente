"""infrastructure/calculation_store.py — Persistência de resultados por processo.

Estrutura:
    /data/calculations/{numero_processo}/{timestamp}/
    ├── metadata.json          # dados do processo + status + timestamps
    ├── llm_extraction.json    # resposta bruta do LLM
    ├── parameters_sent.json   # dados enviados ao PJE-Calc
    ├── final_result.pjc       # arquivo PJC oficial
    ├── screenshots/           # prints de cada fase
    └── logs/                  # logs completos da sessão
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


class CalculationStore:
    """Gerencia diretórios de persistência por processo/execução."""

    def __init__(self, base_dir: Path | None = None):
        self._base = base_dir or Path(os.environ.get("DATA_DIR", "data")) / "calculations"

    def criar_execucao(self, numero_processo: str, sessao_id: str) -> Path:
        """Cria diretório para uma nova execução de cálculo.

        Returns:
            Path para o diretório da execução (ex: /data/calculations/0001686-52.2026.5.07.0003/20260330_102415/)
        """
        proc_dir = self._base / self._normalizar_processo(numero_processo)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        exec_dir = proc_dir / ts
        (exec_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        (exec_dir / "logs").mkdir(parents=True, exist_ok=True)

        # Salvar referência da sessão
        (exec_dir / ".sessao_id").write_text(sessao_id, encoding="utf-8")

        return exec_dir

    def salvar_metadados(self, exec_dir: Path, dados: dict[str, Any]) -> None:
        """Salva metadata.json com dados do processo e status."""
        meta = {
            "timestamp": datetime.now().isoformat(),
            "processo": dados.get("processo", {}),
            "contrato": dados.get("contrato", {}),
            "status": dados.get("_status", "em_andamento"),
            "alertas": dados.get("alertas", []),
        }
        (exec_dir / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def salvar_extracao_llm(self, exec_dir: Path, raw_response: dict[str, Any]) -> None:
        """Salva a resposta bruta do LLM (extração)."""
        (exec_dir / "llm_extraction.json").write_text(
            json.dumps(raw_response, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def salvar_parametros_enviados(self, exec_dir: Path, params: dict[str, Any]) -> None:
        """Salva os parâmetros que serão enviados ao PJE-Calc."""
        (exec_dir / "parameters_sent.json").write_text(
            json.dumps(params, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def copiar_pjc(self, exec_dir: Path, pjc_path: Path | str) -> Path:
        """Copia o arquivo .PJC gerado para o diretório de persistência.

        Returns:
            Path do PJC copiado.
        """
        src = Path(pjc_path)
        dest = exec_dir / "final_result.pjc"
        if src.exists():
            shutil.copy2(str(src), str(dest))
        return dest

    def salvar_screenshot(self, exec_dir: Path, fase: str, png_bytes: bytes) -> Path:
        """Salva screenshot de uma fase."""
        ss_dir = exec_dir / "screenshots"
        ss_dir.mkdir(parents=True, exist_ok=True)
        path = ss_dir / f"{fase}.png"
        path.write_bytes(png_bytes)
        return path

    def salvar_log(self, exec_dir: Path, log_lines: list[str]) -> None:
        """Salva log completo da sessão de automação."""
        log_dir = exec_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "automation.log").write_text(
            "\n".join(log_lines), encoding="utf-8",
        )

    def atualizar_status(self, exec_dir: Path, status: str, extras: dict[str, Any] | None = None) -> None:
        """Atualiza metadata.json com novo status."""
        meta_path = exec_dir / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = {}
        meta["status"] = status
        meta["atualizado_em"] = datetime.now().isoformat()
        if extras:
            meta.update(extras)
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _normalizar_processo(numero: str) -> str:
        """Normaliza número de processo para uso como nome de diretório."""
        return re.sub(r'[/\\<>:"|?*]', '-', numero.strip())
