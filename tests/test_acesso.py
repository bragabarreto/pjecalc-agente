"""Senha provisória + troca no 1º acesso + IP de origem — modules/acesso.py."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import acesso

PROV = "provisoria-de-teste"


def _app():
    app = FastAPI()
    app.include_router(acesso.router_acesso)
    app.add_middleware(acesso.AcessoMiddleware)

    @app.get("/x")
    async def x():
        return {"ip": acesso.ip_atual()}

    return app


def _cli(monkeypatch, tmp_path, **kw):
    monkeypatch.setenv("ACESSO_DIR", str(tmp_path))
    monkeypatch.delenv("APP_AUTH", raising=False)
    monkeypatch.setenv("APP_PASSWORD", PROV)
    acesso._falhas.clear()
    return TestClient(_app(), follow_redirects=False, **kw)


def test_auth_off_app_aberto_e_ip_capturado(monkeypatch, tmp_path):
    c = _cli(monkeypatch, tmp_path)
    monkeypatch.setenv("APP_AUTH", "off")
    r = c.get("/x", headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"})
    assert r.status_code == 200 and r.json()["ip"] == "1.2.3.4"


def test_bloqueia_sem_login(monkeypatch, tmp_path):
    c = _cli(monkeypatch, tmp_path)
    assert c.get("/x").status_code == 401
    r = c.get("/x", headers={"accept": "text/html"})
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")
    assert c.post("/login", data={"senha": "errada"}).status_code == 401


def test_provisoria_obriga_troca_e_depois_libera(monkeypatch, tmp_path):
    c = _cli(monkeypatch, tmp_path)
    ok = c.post("/login", data={"senha": PROV, "next": "/x"})
    assert ok.status_code == 303 and ok.headers["location"] == "/senha"
    # logado com provisória: tudo redireciona para /senha
    assert c.get("/x").headers["location"] == "/senha"
    assert c.get("/senha").status_code == 200
    # validações
    base = {"atual": PROV}
    assert c.post("/senha", data={**base, "nova": "curta", "confirmar": "curta"}).status_code == 400
    assert c.post("/senha", data={**base, "nova": "umaSenhaBoa123", "confirmar": "outra"}).status_code == 400
    assert c.post("/senha", data={"atual": "x", "nova": "umaSenhaBoa123",
                                  "confirmar": "umaSenhaBoa123"}).status_code == 400
    r = c.post("/senha", data={**base, "nova": "umaSenhaBoa123", "confirmar": "umaSenhaBoa123"})
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert c.get("/x").status_code == 200           # cookie novo vale
    assert "umaSenhaBoa123" not in (tmp_path / "acesso.json").read_text()  # só hash
    # a provisória já não entra
    assert TestClient(_app(), follow_redirects=False).post(
        "/login", data={"senha": PROV}).status_code == 401


def test_troca_posterior_invalida_sessoes_antigas(monkeypatch, tmp_path):
    c = _cli(monkeypatch, tmp_path)
    c.post("/login", data={"senha": PROV})
    c.post("/senha", data={"atual": PROV, "nova": "primeiraSenha1", "confirmar": "primeiraSenha1"})
    outro = TestClient(_app(), follow_redirects=False)
    outro.post("/login", data={"senha": "primeiraSenha1"})
    assert outro.get("/x").status_code == 200
    c.post("/senha", data={"atual": "primeiraSenha1", "nova": "segundaSenha22", "confirmar": "segundaSenha22"})
    assert c.get("/x").status_code == 200           # quem trocou continua
    assert outro.get("/x").status_code == 401       # a outra sessão caiu


def test_forca_bruta_bloqueia(monkeypatch, tmp_path):
    c = _cli(monkeypatch, tmp_path)
    for _ in range(5):
        assert c.post("/login", data={"senha": "x"}).status_code == 401
    assert c.post("/login", data={"senha": PROV}).status_code == 429


def test_open_redirect_bloqueado(monkeypatch, tmp_path):
    c = _cli(monkeypatch, tmp_path)
    c.post("/login", data={"senha": PROV})
    c.post("/senha", data={"atual": PROV, "nova": "umaSenhaBoa123", "confirmar": "umaSenhaBoa123"})
    c2 = TestClient(_app(), follow_redirects=False)
    r = c2.post("/login", data={"senha": "umaSenhaBoa123", "next": "//evil.com"})
    assert r.headers["location"] == "/"


def test_loopback_sem_proxy_nao_e_bloqueado(monkeypatch, tmp_path):
    _cli(monkeypatch, tmp_path)
    c = TestClient(_app(), client=("127.0.0.1", 5000))
    assert c.get("/x").status_code == 200
    assert c.get("/x", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 401


def test_sem_app_password_gera_provisoria_aleatoria_no_log(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("ACESSO_DIR", str(tmp_path))
    monkeypatch.delenv("APP_AUTH", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    with caplog.at_level("WARNING"):
        cred = acesso._credenciais()
    assert cred["provisoria"] and "aleatória" in caplog.text
    gerada = caplog.text.split("aleatória: ")[1].split(" ")[0]
    assert acesso._confere(gerada, cred)
