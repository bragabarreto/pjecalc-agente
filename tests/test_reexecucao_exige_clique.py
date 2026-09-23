"""#80-DW (0001312-74, 23/09/2026): reconexão do SSE NÃO reinicia a automação.

Após o restart do container (deploy) o runner some da memória; o EventSource
da aba aberta reconectava em /api/executar/v2/<sessao> e, sem PJC no DB,
disparava um run NOVO sozinho — com a prévia que estivesse gravada naquele
momento (gerou um PJC com verba espúria). Agora: sem runner, sem PJC e COM
log persistido de execução anterior, o endpoint apenas informa que a
execução foi interrompida; só ?rerun=1 (botão ▶ Re-executar) refaz.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import webapp
    import modules.webapp_v2 as W2

    monkeypatch.setattr(W2, "_STORE_DIR", tmp_path)
    monkeypatch.setattr(webapp, "_automacao_runners", {})

    class _Proc:
        numero_processo = "0001312-74.2026.5.07.0003"

    class _Calc:
        id = 1
        processo = _Proc()
        arquivo_pjc = None
        status = "confirmado"

    class _Repo:
        def __init__(self, db):
            pass

        def buscar_sessao(self, sid):
            return _Calc()

    monkeypatch.setattr(webapp, "RepositorioCalculo", _Repo)

    chamadas: list[str] = []

    def _gen_fake(sessao_id: str):
        chamadas.append(sessao_id)
        yield "══ Automação v2 iniciada (FAKE) ══"
        yield "[FIM DA EXECUÇÃO]"

    monkeypatch.setattr(W2, "executar_v2_como_generator", _gen_fake)

    from fastapi.testclient import TestClient
    return TestClient(webapp.app), chamadas, tmp_path


def _msgs(texto: str) -> str:
    """Decodifica os payloads SSE (json.dumps escapa acentos como \\uXXXX)."""
    import json
    out = []
    for linha in texto.splitlines():
        if linha.startswith("data: "):
            raw = linha[6:]
            try:
                out.append(json.loads(raw).get("msg", raw))
            except Exception:
                out.append(raw)
    return "\n".join(out)


def _log_anterior(store: Path) -> None:
    d = store / "logs"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{SID}_automation.log").write_text("\n===== RUN 2026-09-23T19:32:46 =====\nFase 1\n", encoding="utf-8")


def test_dw_reconexao_sem_runner_nao_reinicia(client):
    """Log de execução anterior + sem runner + sem PJC ⇒ NÃO inicia; orienta o clique."""
    c, chamadas, store = client
    _log_anterior(store)
    r = c.get(f"/api/executar/v2/{SID}")
    assert r.status_code == 200
    body = _msgs(r.text)
    assert "INTERROMPIDA" in body and "Re-executar" in body, body
    assert "[FIM DA EXECUÇÃO]" in body
    assert chamadas == [], "REGRESSÃO #80-DW: reconexão do SSE reiniciou a automação sozinha"


def test_dw_primeira_execucao_continua_iniciando(client):
    """Sem log anterior (1ª execução pós-confirmação) ⇒ inicia normalmente."""
    c, chamadas, store = client
    r = c.get(f"/api/executar/v2/{SID}")
    assert r.status_code == 200
    assert chamadas == [SID], "1ª execução após confirmar deixou de iniciar"
    body = _msgs(r.text)
    assert "FAKE" in body and "[FIM DA EXECUÇÃO]" in body


def test_dw_rerun_explicito_reinicia(client):
    """Log anterior + ?rerun=1 (botão ▶ Re-executar) ⇒ refaz do zero."""
    c, chamadas, store = client
    _log_anterior(store)
    r = c.get(f"/api/executar/v2/{SID}?rerun=1")
    assert r.status_code == 200
    assert chamadas == [SID], "▶ Re-executar deixou de reiniciar a automação"


def test_dw_pagina_nao_reconecta_nativamente_com_rerun(client):
    """A página consome o ?rerun=1 uma vez e reconecta só na URL plana."""
    c, _, _ = client
    r = c.get(f"/instrucoes/v2/{SID}?rerun=1")
    assert r.status_code == 200
    html = r.text
    assert "history.replaceState" in html, "URL da página deve perder o ?rerun=1 após consumi-lo"
    assert "es.close();" in html and "new EventSource(SSE_URL)" in html, (
        "onerror deve desligar a reconexão nativa e reconectar na URL plana (sem rerun)")
    assert "new EventSource(SSE_URL + '?rerun=1')" in html
    # fonte: o endpoint continua com a guarda
    src = (REPO_ROOT / "webapp.py").read_text(encoding="utf-8")
    assert "ja_houve_execucao_v2(sessao_id)" in src, "REGRESSÃO #80-DW: guarda removida do endpoint v2"
