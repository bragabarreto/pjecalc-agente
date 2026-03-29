# infrastructure/launcher.py — Watchdog de processo para deploy local
# Substitui launcher.pyw com controle robusto via psutil

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def _psutil_available() -> bool:
    try:
        import psutil  # noqa: F401
        return True
    except ImportError:
        return False


class WatchdogLauncher:
    """
    Watchdog para o servidor uvicorn em deploys locais (Windows, macOS, Linux).

    Uso típico (launcher.pyw no Windows):
        from infrastructure.launcher import WatchdogLauncher
        WatchdogLauncher().start()

    Ou via linha de comando:
        python -m infrastructure.launcher
    """

    PID_FILE = Path(__file__).parent.parent / "data" / "pjecalc_agent.pid"
    LOG_FILE = Path(__file__).parent.parent / "data" / "logs" / "launcher.log"

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        reload: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.reload = reload
        self._proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]

    # ── Interface pública ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Inicia o servidor. Se já estiver rodando, apenas exibe o PID."""
        if self._is_running():
            pid = self._read_pid()
            print(f"Servidor já está rodando (PID {pid}). Acesse http://localhost:{self.port}")
            return

        self._ensure_dirs()
        cmd = self._build_command()
        self._log(f"Iniciando: {' '.join(cmd)}")

        self._proc = subprocess.Popen(
            cmd,
            stdout=open(self.LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            cwd=str(Path(__file__).parent.parent),
        )
        self._write_pid(self._proc.pid)
        self._log(f"Servidor iniciado (PID {self._proc.pid})")
        print(f"Servidor iniciado. Acesse http://localhost:{self.port}")

    def stop(self) -> None:
        """Para o servidor graciosamente (SIGTERM → espera 5s → SIGKILL)."""
        pid = self._read_pid()
        if not pid:
            print("Nenhum servidor rodando.")
            return

        if _psutil_available():
            import psutil
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                self._log(f"Servidor encerrado (PID {pid})")
                print(f"Servidor encerrado (PID {pid}).")
            except psutil.NoSuchProcess:
                print(f"Processo {pid} não encontrado (já encerrado).")
        else:
            # Fallback sem psutil
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(5)
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

        self.PID_FILE.unlink(missing_ok=True)

    def health_check(self) -> bool:
        """Retorna True se o servidor está respondendo."""
        import urllib.request
        try:
            with urllib.request.urlopen(f"http://localhost:{self.port}/", timeout=3):
                return True
        except Exception:
            return False

    def status(self) -> str:
        """Retorna string de status: 'rodando (PID X)' ou 'parado'."""
        pid = self._read_pid()
        if not pid:
            return "parado"

        if _psutil_available():
            import psutil
            try:
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    return f"rodando (PID {pid})"
            except psutil.NoSuchProcess:
                pass

        return "parado (PID file desatualizado)"

    # ── Auxiliares privados ────────────────────────────────────────────────────

    def _is_running(self) -> bool:
        pid = self._read_pid()
        if not pid:
            return False
        if _psutil_available():
            import psutil
            try:
                proc = psutil.Process(pid)
                return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            except psutil.NoSuchProcess:
                return False
        # Fallback: verifica se o processo existe via os.kill(pid, 0)
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _read_pid(self) -> Optional[int]:
        try:
            return int(self.PID_FILE.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def _write_pid(self, pid: int) -> None:
        self.PID_FILE.write_text(str(pid))

    def _build_command(self) -> list[str]:
        reload_flag = ["--reload"] if self.reload else []
        return [
            sys.executable, "-m", "uvicorn",
            "webapp:app",
            "--host", self.host,
            "--port", str(self.port),
        ] + reload_flag

    def _ensure_dirs(self) -> None:
        self.PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, msg: str) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}\n"
        try:
            with open(self.LOG_FILE, "a") as f:
                f.write(line)
        except OSError:
            pass


# ── Uso direto via linha de comando ──────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PJECalc Agente — Launcher")
    parser.add_argument("action", choices=["start", "stop", "status", "health"], default="start", nargs="?")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    launcher = WatchdogLauncher(port=args.port, reload=args.reload)

    if args.action == "start":
        launcher.start()
    elif args.action == "stop":
        launcher.stop()
    elif args.action == "status":
        print(f"Status: {launcher.status()}")
    elif args.action == "health":
        ok = launcher.health_check()
        print(f"Health: {'OK' if ok else 'FALHOU'}")
        sys.exit(0 if ok else 1)
