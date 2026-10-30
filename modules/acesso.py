"""Controle de acesso e origem das requisições (30/10/2026).

Motivo: o app ficou exposto em IP público sem autenticação; cálculos de
terceiros apareciam no rol sem que houvesse como saber quem os criou.

1. ORIGEM: o IP de cada requisição vai para um ContextVar; quem cria o
   `Calculo` grava `origem_ip` a partir dele (`ip_atual()`).
2. SENHA: toda rota exige o cookie emitido por /login. A senha fica em
   `acesso.json` (PBKDF2, volume persistente). Na 1ª execução nasce uma senha
   PROVISÓRIA (env `APP_PASSWORD`; sem ela, aleatória escrita no log) que obriga a
   troca em /senha; depois, /senha permite alterar quando quiser (e invalida
   as sessões antigas). `APP_AUTH=off` desliga a proteção.

A requisição de loopback sem cabeçalho de proxy (healthcheck do Docker,
chamadas internas) nunca é bloqueada.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from contextvars import ContextVar
from urllib.parse import quote

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse

logger = logging.getLogger(__name__)

_ip_ctx: ContextVar[str | None] = ContextVar("origem_ip", default=None)

COOKIE = "pjecalc_auth"
_ABERTAS = ("/login", "/logout", "/static/")
_PROVISORIA_OK = ("/senha", "/login", "/logout", "/static/")
_LOOPBACK = {"127.0.0.1", "::1"}

router_acesso = APIRouter()


def ip_atual() -> str | None:
    """IP de origem da requisição em curso (None fora de uma requisição)."""
    return _ip_ctx.get()


MIN_SENHA = 10


def _arquivo() -> Path:
    """Credenciais num volume persistente (sobrevivem ao deploy)."""
    base = os.environ.get("ACESSO_DIR")
    if base:
        d = Path(base)
    else:
        d = next((Path(c) for c in ("/app/data/calculations", "data/calculations")
                  if Path(c).is_dir()), Path("data/calculations"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "acesso.json"


def _hash(senha: str, sal: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, 200_000).hex()


def _gravar(senha: str, provisoria: bool, segredo: str | None = None) -> dict:
    sal = secrets.token_bytes(16)
    cred = {"sal": sal.hex(), "hash": _hash(senha, sal), "provisoria": provisoria,
            "segredo": segredo or secrets.token_hex(32)}
    arq = _arquivo()
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(cred))
    os.chmod(tmp, 0o600)
    tmp.replace(arq)
    return cred


def _credenciais() -> dict | None:
    """None = proteção desligada (APP_AUTH=off). Cria a provisória no 1º uso."""
    if os.environ.get("APP_AUTH", "").lower() in ("off", "0", "false"):
        return None
    try:
        return json.loads(_arquivo().read_text())
    except Exception:
        inicial = os.environ.get("APP_PASSWORD")
        if inicial:
            logger.warning("acesso: senha PROVISÓRIA (APP_PASSWORD) criada — troque no 1º acesso")
        else:
            inicial = secrets.token_urlsafe(9)
            logger.warning("acesso: APP_PASSWORD ausente — senha PROVISÓRIA aleatória: %s "
                           "(troque no 1º acesso)", inicial)
        return _gravar(inicial, provisoria=True)


def _confere(senha: str, cred: dict) -> bool:
    return hmac.compare_digest(_hash(senha, bytes.fromhex(cred["sal"])), cred["hash"])


def _token(cred: dict) -> str:
    """Amarrado ao hash: trocar a senha invalida todas as sessões antigas."""
    return hmac.new(cred["segredo"].encode(), cred["hash"].encode(),
                    hashlib.sha256).hexdigest()


_falhas: dict[str, list[float]] = {}


def _bloqueado(ip: str) -> bool:
    agora = time.time()
    _falhas[ip] = [t for t in _falhas.get(ip, []) if agora - t < 300]
    return len(_falhas[ip]) >= 5


def _falhou(ip: str) -> None:
    _falhas.setdefault(ip, []).append(time.time())


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

        cred = _credenciais()
        path = scope.get("path", "")
        cli = (scope.get("client") or ("",))[0]
        interno = cli in _LOOPBACK and not any(
            x in h for x in ("x-forwarded-for", "cf-connecting-ip", "x-real-ip"))
        if not cred or interno or path.startswith(_ABERTAS):
            return await self.app(scope, receive, send)
        if hmac.compare_digest(_cookie(h, COOKIE), _token(cred)):
            if cred.get("provisoria") and not path.startswith(_PROVISORIA_OK):
                resp = RedirectResponse("/senha", status_code=303)
                return await resp(scope, receive, send)
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


def _erro(msg: str) -> str:
    return (f'<p style="color:#721c24;background:#f8d7da;padding:8px;'
            f'border-radius:6px">{msg}</p>')


def _cookie_resp(resp, cred: dict):
    resp.set_cookie(COOKIE, _token(cred), max_age=30 * 86400,
                    httponly=True, samesite="lax")
    return resp


@router_acesso.get("/login", response_class=HTMLResponse)
async def login_form(next: str = "/"):
    from html import escape
    return _PAGINA.format(erro="", next=escape(_next_seguro(next), quote=True))


@router_acesso.post("/login")
async def login(senha: str = Form(""), next: str = Form("/")):
    from html import escape
    cred = _credenciais()
    ip = ip_atual() or ""
    if cred is None:
        return RedirectResponse(_next_seguro(next), status_code=303)
    if _bloqueado(ip):
        return HTMLResponse(_PAGINA.format(
            erro=_erro("Muitas tentativas. Aguarde alguns minutos."),
            next=escape(_next_seguro(next), quote=True)), status_code=429)
    if _confere(senha, cred):
        _falhas.pop(ip, None)
        alvo = "/senha" if cred.get("provisoria") else _next_seguro(next)
        return _cookie_resp(RedirectResponse(alvo, status_code=303), cred)
    _falhou(ip)
    return HTMLResponse(_PAGINA.format(
        erro=_erro("Senha incorreta."),
        next=escape(_next_seguro(next), quote=True)), status_code=401)


@router_acesso.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


_PAGINA_SENHA = """<!doctype html><html lang="pt-br"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alterar senha — Agente PJE-Calc</title>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f5f6fa;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0">
<form method="post" action="/senha" style="background:#fff;padding:32px;border-radius:8px;
box-shadow:0 2px 8px rgba(0,0,0,.1);width:340px">
<h2 style="color:#1a3a6b;margin:0 0 8px">Alterar senha</h2>
{aviso}{msg}
<style>input{{width:100%;padding:10px;box-sizing:border-box;margin-bottom:12px;
border:1px solid #ccc;border-radius:6px}}</style>
<input type="password" name="atual" placeholder="Senha atual" required autofocus>
<input type="password" name="nova" placeholder="Nova senha (mín. {minimo} caracteres)" required minlength="{minimo}">
<input type="password" name="confirmar" placeholder="Repita a nova senha" required>
<button style="width:100%;padding:10px;background:#1a3a6b;color:#fff;border:0;border-radius:6px;
font-weight:600;cursor:pointer">Salvar nova senha</button>
<p style="text-align:center;margin:14px 0 0;font-size:.9em">
{voltar}<a href="/logout" style="color:#1a3a6b">Sair</a></p></form></body></html>"""


def _pagina_senha(cred: dict, msg: str = "") -> str:
    prov = cred.get("provisoria")
    return _PAGINA_SENHA.format(
        aviso=('<p style="color:#856404;background:#fff3cd;padding:8px;border-radius:6px">'
               'Senha provisória: defina uma senha própria para continuar.</p>') if prov else "",
        msg=msg, minimo=MIN_SENHA,
        voltar="" if prov else '<a href="/" style="color:#1a3a6b">Voltar</a> · ')


@router_acesso.get("/senha", response_class=HTMLResponse)
async def senha_form():
    cred = _credenciais()
    if cred is None:
        return RedirectResponse("/", status_code=303)
    return _pagina_senha(cred)


@router_acesso.post("/senha")
async def senha_alterar(atual: str = Form(""), nova: str = Form(""),
                        confirmar: str = Form("")):
    cred = _credenciais()
    if cred is None:
        return RedirectResponse("/", status_code=303)
    ip = ip_atual() or ""

    def volta(msg: str, codigo: int = 400):
        return HTMLResponse(_pagina_senha(cred, _erro(msg)), status_code=codigo)

    if _bloqueado(ip):
        return volta("Muitas tentativas. Aguarde alguns minutos.", 429)
    if not _confere(atual, cred):
        _falhou(ip)
        return volta("Senha atual incorreta.")
    if len(nova) < MIN_SENHA:
        return volta(f"A nova senha precisa ter ao menos {MIN_SENHA} caracteres.")
    if nova != confirmar:
        return volta("A confirmação não confere com a nova senha.")
    if nova == atual:
        return volta("Escolha uma senha diferente da atual.")
    novo = _gravar(nova, provisoria=False)  # novo segredo: derruba sessões antigas
    logger.info("acesso: senha alterada ip=%s", ip)
    return _cookie_resp(RedirectResponse("/", status_code=303), novo)
