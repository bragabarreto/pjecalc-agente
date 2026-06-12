"""Testes do fluxo de Extração IA in-app (modules/webapp_extracao.py).

Fase 1 implantada em 12/06/2026. Estes testes protegem:
1. o contrato das rotas /novo/ia, /processar/ia, /resumo/ia, /api/ia/*;
2. a regra IA-only (falha da API → fase 'erro', nunca fallback regex);
3. o prompt caching (cache_control no system e no prefixo de documentos);
4. a PRESERVAÇÃO do caminho do JSON externo (aditivo — /processar/v2
   intocado, fonte única do prompt em extraction_v2).

Nenhum teste chama a API real — chave fake produz 401, que é exatamente
o caminho de erro que validamos.
"""

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-fake")
os.environ.setdefault("EXTRACAO_IA_DIR", "/tmp/pjecalc_test_extracao_ia")

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from modules.webapp_extracao import router_extracao

    app = FastAPI()
    app.include_router(router_extracao)
    return TestClient(app)


def test_pagina_novo_ia_renderiza(client):
    r = client.get("/novo/ia")
    assert r.status_code == 200
    assert "form-ia" in r.text
    # link de preservação para o fluxo clássico do JSON externo
    assert "/novo" in r.text


def test_processar_ia_vazio_retorna_400(client):
    r = client.post("/processar/ia", data={})
    assert r.status_code == 400


def test_processar_ia_cria_sessao_e_erro_ia_only(client):
    """Com chave fake, o worker falha na API → fase 'erro' com mensagem.
    NUNCA pode haver resumo/prévia sem IA (regra IA-only)."""
    r = client.post("/processar/ia", data={"texto_sentenca": "SENTENÇA de teste."})
    assert r.status_code == 200
    sid = r.json()["sessao_id"]
    assert r.json()["url_resumo"] == f"/resumo/ia/{sid}"

    # página do resumo existe
    r2 = client.get(f"/resumo/ia/{sid}")
    assert r2.status_code == 200

    # aguardar o worker falhar com a chave fake
    for _ in range(20):
        d = client.get(f"/api/ia/{sid}/estado").json()
        if d["fase"] != "etapa1_processando":
            break
        time.sleep(0.5)
    assert d["fase"] == "erro"
    assert "Etapa 1" in (d["erro"] or "")
    assert d.get("resumo_md") is None  # IA-only: sem resumo sem IA


def test_estado_sessao_inexistente_404(client):
    assert client.get("/api/ia/nao-existe/estado").status_code == 404


def test_confirmar_em_fase_errada_409(client):
    r = client.post("/processar/ia", data={"texto_sentenca": "x"})
    sid = r.json()["sessao_id"]
    # fase ainda etapa1_processando (ou erro) — confirmar deve ser 409
    r2 = client.post(f"/api/ia/{sid}/confirmar")
    assert r2.status_code == 409


def test_extrair_json_tolerante():
    from modules.webapp_extracao import _extrair_json

    assert _extrair_json('{"a": 1}') == {"a": 1}
    assert _extrair_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extrair_json('Segue:\n{"a": {"b": 2}}\nFim.') == {"a": {"b": 2}}
    with pytest.raises(Exception):
        _extrair_json("sem json aqui")


def test_xlsx_para_markdown(tmp_path):
    from openpyxl import Workbook

    from modules.webapp_extracao import _xlsx_para_markdown

    wb = Workbook()
    ws = wb.active
    ws.title = "Salarios"
    ws.append(["mes", "valor"])
    ws.append(["jan/2024", 1412])
    p = tmp_path / "t.xlsx"
    wb.save(p)
    md = _xlsx_para_markdown(p)
    assert "Aba: Salarios" in md
    assert "| mes | valor |" in md
    assert "1412" in md


def test_prompt_caching_marcado():
    """Invariante de custo: cache_control no system prompt e no último
    bloco da 1ª mensagem (cacheia prefixo inteiro — 90% de desconto nas
    chamadas de correção/Etapa 2)."""
    from modules.webapp_extracao import _montar_messages

    estado = {"texto_colado": "sentença", "arquivos": [], "conversa": []}
    msgs = _montar_messages(estado)
    assert msgs[0]["content"][-1].get("cache_control") == {"type": "ephemeral"}

    src = (REPO_ROOT / "modules" / "webapp_extracao.py").read_text(encoding="utf-8")
    assert '"cache_control": {"type": "ephemeral"}' in src
    # fonte única do prompt — nunca copiar o texto do prompt para cá
    assert "SYSTEM_PROMPT_V2_EXTERNAL" in src
    assert "FLUXO OPERACIONAL" not in src


def test_preservacao_caminho_json_externo():
    """O fluxo in-app é ADITIVO: /processar/v2 e a auto-detecção .json do
    /processar permanecem como opção de entrada."""
    w2 = (REPO_ROOT / "modules" / "webapp_v2.py").read_text(encoding="utf-8")
    assert '@router_v2.post("/processar/v2")' in w2
    wapp = (REPO_ROOT / "webapp.py").read_text(encoding="utf-8")
    assert "JSON v2 detectado" in wapp          # auto-detecção .json preservada
    assert "router_extracao" in wapp            # novo router registrado
    novo = (REPO_ROOT / "templates" / "novo_calculo.html").read_text(encoding="utf-8")
    assert "Colar JSON" in novo                  # UI clássica preservada


def test_etapa2_desemboca_no_pipeline_v2():
    """Etapa 2 usa normalize_v2_json + PreviaCalculoV2 + _save_previa do
    webapp_v2 — mesmo pipeline do JSON externo, sem duplicação."""
    src = (REPO_ROOT / "modules" / "webapp_extracao.py").read_text(encoding="utf-8")
    assert "from modules.json_normalizer import normalize_v2_json" in src
    assert "from modules.webapp_v2 import PreviaCalculoV2, _save_previa" in src


def test_retry_json_invalido_presente():
    """Etapa 2 tem retry único de reemissão estrita quando o parse falha."""
    src = (REPO_ROOT / "modules" / "webapp_extracao.py").read_text(encoding="utf-8")
    assert "json_retry" in src
    assert "não era JSON válido" in src
