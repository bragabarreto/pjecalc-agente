"""Senha opt-in (APP_PASSWORD) e IP de origem — modules/acesso.py."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import acesso


def _app():
    app = FastAPI()
    app.include_router(acesso.router_acesso)
    app.add_middleware(acesso.AcessoMiddleware)

    @app.get("/x")
    async def x():
        return {"ip": acesso.ip_atual()}

    return app


def test_sem_senha_app_aberto_e_ip_capturado(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    r = TestClient(_app()).get("/x", headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"})
    assert r.status_code == 200 and r.json()["ip"] == "1.2.3.4"


def test_com_senha_bloqueia_e_libera_apos_login(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "segredo")
    c = TestClient(_app(), follow_redirects=False)
    assert c.get("/x").status_code == 401
    r = c.get("/x", headers={"accept": "text/html"})
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")
    assert c.post("/login", data={"senha": "errada"}).status_code == 401
    ok = c.post("/login", data={"senha": "segredo", "next": "/x"})
    assert ok.status_code == 303 and acesso.COOKIE in ok.headers["set-cookie"]
    assert c.get("/x").json()["ip"] is not None  # cookie guardado pelo client


def test_open_redirect_bloqueado(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s")
    r = TestClient(_app(), follow_redirects=False).post(
        "/login", data={"senha": "s", "next": "//evil.com"})
    assert r.headers["location"] == "/"


def test_loopback_sem_proxy_nao_e_bloqueado(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s")
    r = TestClient(_app(), client=("127.0.0.1", 5000)).get("/x")
    assert r.status_code == 200
    r2 = TestClient(_app(), client=("127.0.0.1", 5000)).get(
        "/x", headers={"X-Forwarded-For": "8.8.8.8"})
    assert r2.status_code == 401
