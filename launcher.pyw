# launcher.pyw — Agente PJE-Calc
#
# Duplo clique para iniciar o servidor e abrir o aplicativo no browser.
# Roda silenciosamente (sem janela de terminal).
#
# Comportamento:
#   - Encerra o servidor anterior (se houver) via PID file.
#   - Inicia uvicorn com o código atual.
#   - Abre http://localhost:8000 no browser padrão.

import os
import socket
import subprocess
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent
PORT = 8000
PYTHON = BASE_DIR / "venv" / "Scripts" / "python.exe"
PID_FILE = BASE_DIR / "server.pid"


def _servidor_rodando() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            return True
    except OSError:
        return False


def _parar_servidor_anterior() -> None:
    """Encerra o processo uvicorn anterior usando o PID salvo."""
    if PID_FILE.exists():
        try:
            pid = PID_FILE.read_text().strip()
            subprocess.run(
                ["taskkill", "/F", "/PID", pid, "/T"],
                capture_output=True,
            )
        except Exception:
            pass
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    # Aguarda a porta liberar (até 5s)
    for _ in range(10):
        if not _servidor_rodando():
            break
        time.sleep(0.5)


def _iniciar_servidor() -> None:
    proc = subprocess.Popen(
        [
            str(PYTHON), "-m", "uvicorn",
            "webapp:app",
            "--host", "0.0.0.0",
            "--port", str(PORT),
        ],
        cwd=str(BASE_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    PID_FILE.write_text(str(proc.pid))
    # Aguarda o servidor ficar pronto (até 20s)
    for _ in range(40):
        time.sleep(0.5)
        if _servidor_rodando():
            return


def main() -> None:
    _parar_servidor_anterior()
    _iniciar_servidor()
    webbrowser.open(f"http://localhost:{PORT}")


main()
