# launcher.pyw — Agente PJE-Calc
#
# Duplo clique para iniciar o servidor e abrir o aplicativo no browser.
# Roda silenciosamente (sem janela de terminal).
#
# Comportamento:
#   - Se o servidor já estiver rodando em localhost:8000, apenas abre o browser.
#   - Se não estiver rodando, inicia o uvicorn em background e aguarda ficar pronto.

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent
PORT = 8000
PYTHON = BASE_DIR / "venv" / "Scripts" / "python.exe"


def _servidor_rodando() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            return True
    except OSError:
        return False


def _iniciar_servidor() -> None:
    subprocess.Popen(
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
    # Aguarda o servidor ficar pronto (até 20s)
    for _ in range(40):
        time.sleep(0.5)
        if _servidor_rodando():
            return


def main() -> None:
    if not _servidor_rodando():
        _iniciar_servidor()

    webbrowser.open(f"http://localhost:{PORT}")


main()
