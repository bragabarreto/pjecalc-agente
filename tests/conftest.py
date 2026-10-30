import pytest


@pytest.fixture(autouse=True)
def _sem_senha_nos_testes(monkeypatch):
    """TestClient chega como 'testclient' (não-loopback): sem isto o middleware
    de senha bloquearia todos os testes do webapp. test_acesso religa a proteção."""
    monkeypatch.setenv("APP_AUTH", "off")
