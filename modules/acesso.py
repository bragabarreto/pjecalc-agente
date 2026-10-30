"""Controle de acesso e origem das requisições (30/10/2026).

Motivo: o app ficou exposto em IP público sem autenticação; cálculos de
terceiros apareciam no rol sem que houvesse como saber quem os criou.

1. ORIGEM: o IP de cada requisição vai para um ContextVar; quem cria o
   `Calculo` grava `origem_ip` a partir dele (`ip_atual()`).
2. SENHA (opt-in): com a env `APP_PASSWORD` definida, toda rota exige o
   cookie de sessão emitido por /login. Sem a env, o comportamento é o
   anterior (aberto) e o startup avisa no log.

A requisição de loopback sem cabeçalho de proxy (healthcheck do Docker,
chamadas internas) nunca é bloqueada.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from contextvars import ContextVar
from urllib.parse import quote

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse

logger = logging.getLogger(__name__)

_ip_ctx: ContextVar[str | None] = ContextVar("origem_ip", default=None)

COOKIE = "pjecalc_auth"
_ABERTAS = ("/login", "/logout", "/static/")
_LOOPBACK = {"127.0.0.1", "::1"}

router_acesso = APIRouter()


def ip_atual() -> str | None:
    """IP de origem da requisição em curso (None fora de uma requisição)."""
    return _ip_ctx.get()


def _senha() -> str:
    return os.environ.get("APP_PASSWORD", "")


def _token(senha: str) -> str:
    return hmac.new(senha.encode(), b"pjecalc-auth-v1", hashlib.sha256).hexdigest()


def _headers(scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])}


def _ip_do_scope(h: dict[str, str], scope) -> str:
    for nome in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        v = h.get(nome)
        if v:
            return v.split(",")[0].strip()[:64]
    cli = scope.get("client")
    return (cli[0] if cli else "")[:64]


def _cookie(h: dict[str, str], nome: str) -> str:
    for parte in h.get("cookie", "").split(";"):
        k, _, v = parte.strip().partition("=")
        if k == nome:
            return v
    return ""


class AcessoMiddleware:
    """ASGI puro (não bufferiza o SSE como o BaseHTTPMiddleware)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        h = _headers(scope)
        ip = _ip_do_scope(h, scope)
        _ip_ctx.set(ip)

        senha = _senha()
        path = scope.get("path", "")
        cli = (scope.get("client") or ("",))[0]
        interno = cli in _LOOPBACK and not any(
            x in h for x in ("x-forwarded-for", "cf-connecting-ip", "x-real-ip"))
        if (not senha or interno or path.startswith(_ABERTAS)
                or hmac.compare_digest(_cookie(h, COOKIE), _token(senha))):
            return await self.app(scope, receive, send)

        if scope["method"] == "GET" and "text/html" in h.get("accept", ""):
            alvo = path + (("?" + scope["query_string"].decode()) if scope.get("query_string") else "")
            resp = RedirectResponse(f"/login?next={quote(alvo, safe='')}", status_code=303)
        else:
            from fastapi.responses import JSONResponse
            resp = JSONResponse({"detail": "autenticação necessária"}, status_code=401)
        logger.info("acesso negado (sem login): %s %s ip=%s", scope["method"], path, ip)
        return await resp(scope, receive, send)


_PAGINA = """<!doctype html><html lang="pt-br"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entrar — Agente PJE-Calc</title>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f5f6fa;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0">
<form method="post" action="/login" style="background:#fff;padding:32px;border-radius:8px;
box-shadow:0 2px 8px rgba(0,0,0,.1);width:320px">
<h2 style="color:#1a3a6b;margin:0 0 16px">Agente PJE-Calc</h2>
{erro}
<input type="hidden" name="next" value="{next}">
<input type="password" name="senha" placeholder="Senha de acesso" autofocus required
style="width:100%;padding:10px;box-sizing:border-box;margin-bottom:12px;border:1px solid #ccc;border-radius:6px">
<button style="width:100%;padding:10px;background:#1a3a6b;color:#fff;border:0;border-radius:6px;
font-weight:600;cursor:pointer">Entrar</button></form></body></html>"""


def _next_seguro(n: str) -> str:
    return n if n.startswith("/") and not n.startswith("//") else "/"


@router_acesso.get("/login", response_class=HTMLResponse)
async def login_form(next: str = "/"):
    from html import escape
    return _PAGINA.format(erro="", next=escape(_next_seguro(next), quote=True))


@router_acesso.post("/login")
async def login(senha: str = Form(""), next: str = Form("/")):
    esperada = _senha()
    if esperada and hmac.compare_digest(senha.encode(), esperada.encode()):
        resp = RedirectResponse(_next_seguro(next), status_code=303)
        resp.set_cookie(COOKIE, _token(esperada), max_age=30 * 86400,
                        httponly=True, samesite="lax")
        return resp
    from html import escape
    return HTMLResponse(
        _PAGINA.format(erro='<p style="color:#721c24;background:#f8d7da;padding:8px;'
                            'border-radius:6px">Senha incorreta.</p>',
                       next=escape(_next_seguro(next), quote=True)),
        status_code=401)


@router_acesso.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp
