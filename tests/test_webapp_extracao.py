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

    # aguardar o worker falhar com a chave fake. Janela generosa: o worker faz
    # uma chamada REAL à API (401) numa thread — sob carga do suite o
    # round-trip pode passar de 10s (flaky). 30s remove a intermitência.
    for _ in range(60):
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


def test_previas_pendentes_filtra_confirmadas(tmp_path, monkeypatch):
    """Home lista prévias v2 SALVAS mas não confirmadas (sem Calculo no banco).
    Confirmadas (sessao_id no set) são excluídas; .extracao.json é ignorado."""
    import modules.webapp_v2 as w2
    monkeypatch.setattr(w2, "_STORE_DIR", tmp_path)
    import json as _j
    (tmp_path / "sid-pendente.json").write_text(_j.dumps(
        {"processo": {"numero_processo": "0000030-98.2026.5.07.0003",
                      "reclamante": {"nome": "DANIEL"}, "reclamado": {"nome": "ACME"}}}))
    (tmp_path / "sid-confirmada.json").write_text(_j.dumps(
        {"processo": {"numero_processo": "0000001-11.2026.5.07.0003",
                      "reclamante": {"nome": "X"}}}))
    (tmp_path / "sid-pendente.extracao.json").write_text("{}")  # deve ser ignorado
    r = w2.listar_previas_pendentes({"sid-confirmada"})
    sids = {p["sessao_id"] for p in r}
    assert "sid-pendente" in sids, "prévia não confirmada deve aparecer"
    assert "sid-confirmada" not in sids, "confirmada (no banco) deve ser excluída"
    p = next(x for x in r if x["sessao_id"] == "sid-pendente")
    assert p["numero_processo"] == "0000030-98.2026.5.07.0003"
    assert p["reclamante"] == "DANIEL"
    assert p["url_previa"] == "/previa/v2/sid-pendente"


def test_home_passa_previas_pendentes_ao_template():
    """A home coleta sessao_ids confirmados e passa previas_pendentes ao index."""
    wapp = (REPO_ROOT / "webapp.py").read_text(encoding="utf-8")
    assert "listar_previas_pendentes" in wapp
    assert "previas_pendentes" in wapp
    idx = (REPO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert "Prévias pendentes" in idx and "Revisar / Confirmar" in idx


def test_recovery_sessoes_orfas(tmp_path, monkeypatch):
    """#80-AH: startup recupera sessões mortas por reinício do container."""
    import json as _j
    import modules.webapp_extracao as we
    monkeypatch.setattr(we, "_STORE_DIR", tmp_path)
    # caso 1: etapa1_processando COM resumo → resumo_pronto
    (tmp_path / "s1").mkdir()
    (tmp_path / "s1" / "estado.json").write_text(_j.dumps(
        {"fase": "etapa1_processando", "resumo_md": "# Resumo completo"}))
    # caso 2: etapa1_processando SEM resumo → erro claro
    (tmp_path / "s2").mkdir()
    (tmp_path / "s2" / "estado.json").write_text(_j.dumps(
        {"fase": "etapa1_processando", "resumo_md": ""}))
    # caso 3: etapa2_processando → resumo_pronto + aviso
    (tmp_path / "s3").mkdir()
    (tmp_path / "s3" / "estado.json").write_text(_j.dumps(
        {"fase": "etapa2_processando", "resumo_md": "# R"}))
    # caso 4: fase normal não é tocada
    (tmp_path / "s4").mkdir()
    (tmp_path / "s4" / "estado.json").write_text(_j.dumps(
        {"fase": "previa_pronta", "resumo_md": "# R"}))
    we._recuperar_sessoes_orfas()
    e1 = _j.loads((tmp_path / "s1" / "estado.json").read_text())
    e2 = _j.loads((tmp_path / "s2" / "estado.json").read_text())
    e3 = _j.loads((tmp_path / "s3" / "estado.json").read_text())
    e4 = _j.loads((tmp_path / "s4" / "estado.json").read_text())
    assert e1["fase"] == "resumo_pronto"
    assert e2["fase"] == "erro" and "reinício" in e2["erro"]
    assert e3["fase"] == "resumo_pronto" and "confirmar" in e3["aviso_recuperacao"]
    assert e4["fase"] == "previa_pronta"


def test_previa_entra_na_lista_principal_desde_geracao():
    """#80-AI: prévia registrada no banco (status previa_gerada) NA GERAÇÃO —
    Etapa 2 da extração IA e /processar/v2 chamam registrar_calculo_db; a
    confirmação atualiza (confirmar=True) em vez de criar."""
    w2 = (REPO_ROOT / "modules" / "webapp_v2.py").read_text(encoding="utf-8")
    assert "def registrar_calculo_db" in w2
    assert 'registrar_calculo_db(sessao_id, _dump, status="previa_gerada")' in w2, (
        "/processar/v2 deve registrar na geração")
    assert 'registrar_calculo_db(sessao_id, data, status="confirmado", confirmar=True)' in w2, (
        "confirmação deve atualizar via helper")
    ext = (REPO_ROOT / "modules" / "webapp_extracao.py").read_text(encoding="utf-8")
    assert 'registrar_calculo_db(sessao_id, _previa_dump, status="previa_gerada")' in ext, (
        "Etapa 2 da extração deve registrar na geração")


# ─── 18/09/2026 — erros em linguagem natural + documentos na correção ─────


def test_traduzir_erro_validacao_nomeia_verba():
    """ValidationError do Pydantic vira lista legível: a verba é citada pelo
    NOME (não por índice/campo técnico) e não sobra URL do pydantic."""
    from modules.webapp_extracao import _explicacao_deterministica, _traduzir_erro_validacao
    from modules.webapp_v2 import PreviaCalculoV2

    payload = {
        "processo": {}, "parametros_calculo": {},
        "verbas_principais": [{
            "id": "v01", "nome_sentenca": "horas extras", "nome_pjecalc": "HORAS EXTRAS 50%",
            "estrategia_preenchimento": "expresso_direto", "parametros": {},
        }],
    }
    with pytest.raises(Exception) as ei:
        PreviaCalculoV2.model_validate(payload)
    trad = _traduzir_erro_validacao(ei.value, payload)
    assert "Verba «HORAS EXTRAS 50%»" in trad
    assert "requer expresso_alvo" in trad
    assert "Dados do processo" in trad and "informação obrigatória ausente" in trad
    assert "pydantic.dev" not in trad and "verbas_principais.0" not in trad
    assert _explicacao_deterministica(ei.value, payload).startswith("O JSON gerado foi rejeitado")
    # exceção não-Pydantic: cai na descrição humana, nunca em traceback
    assert "erro de software" in _explicacao_deterministica(TypeError("unexpected keyword"), None)


def test_descrever_excecao_em_linguagem_natural():
    from modules.webapp_extracao import _descrever_excecao
    assert "sobrecarregada" in _descrever_excecao(RuntimeError("Error code: 529 - overloaded_error"))
    assert "erro de software" in _descrever_excecao(
        TypeError("Messages.create() got an unexpected keyword argument 'temperature'"))


def test_erro_etapa2_explicado_pela_ia_na_mesma_conversa(monkeypatch, client):
    """JSON rejeitado pela validação → o sistema pergunta à IA (turnos `auto`)
    o que falta e expõe `erro_explicacao` em linguagem natural; o bruto vai
    em `erro_tecnico`; os turnos auto NÃO aparecem como 'correção enviada'."""
    import modules.json_normalizer as jn
    import modules.webapp_extracao as wx

    sid = "teste-erro-etapa2"
    wx._sessao_dir(sid)
    wx._save_estado(sid, {
        "fase": "resumo_pronto", "texto_colado": "SENTENÇA de teste.", "arquivos": [],
        "resumo_md": "### resumo", "conversa": [{"role": "assistant", "texto": "### resumo"}],
    })
    json_ruim = json.dumps({
        "processo": {}, "parametros_calculo": {},
        "verbas_principais": [{"id": "v01", "nome_sentenca": "horas extras",
                               "estrategia_preenchimento": "expresso_direto", "parametros": {}}],
    })
    chamadas: list[str] = []

    def fake_chamar(messages, max_tokens):
        ultimo = messages[-1]["content"]
        ultimo = ultimo if isinstance(ultimo, str) else ultimo[-1]["text"]
        chamadas.append(ultimo[:40])
        if ultimo == "confirmar":
            return json_ruim, {}
        if "MENSAGEM AUTOMÁTICA" in ultimo:
            assert "Verba «horas extras»" in ultimo  # a tradução vai junto no pedido
            return "### O que deu errado\nFalta a base das horas extras.\n### O que preciso de você\n- contracheques", {}
        raise AssertionError(f"chamada inesperada: {ultimo[:60]}")

    monkeypatch.setattr(wx, "_chamar_claude", fake_chamar)
    monkeypatch.setattr(jn, "normalize_v2_json", lambda p, **kw: p)
    wx._worker_etapa2(sid)

    est = wx._load_estado(sid)
    assert est["fase"] == "erro_etapa2"
    assert est["erro_explicacao"].startswith("### O que deu errado")
    assert "ValidationError" in est["erro_tecnico"]
    assert "rejeitado pela validação" in est["erro"]
    autos = [t for t in est["conversa"] if t.get("auto")]
    assert [t["role"] for t in autos] == ["user", "assistant"]
    assert len(chamadas) == 2

    d = client.get(f"/api/ia/{sid}/estado").json()
    assert d["erro_explicacao"] == est["erro_explicacao"]
    assert d["correcoes"] == []  # turnos auto e 'confirmar' não contam


def test_corrigir_aceita_documentos_e_falha_nao_mata_sessao(client, tmp_path):
    """Correção via multipart com anexo: o arquivo vira bloco do PRÓPRIO turno
    (prefixo em cache intacto). Falha da API na correção NÃO derruba a sessão:
    volta a `resumo_pronto` com aviso e o anexo fica pendente p/ reenvio."""
    import modules.webapp_extracao as wx

    import shutil
    sid = "teste-corrigir-docs"
    shutil.rmtree(wx._STORE_DIR / sid, ignore_errors=True)  # idempotente entre runs
    wx._sessao_dir(sid)
    wx._save_estado(sid, {
        "fase": "resumo_pronto", "texto_colado": "SENTENÇA.", "arquivos": [],
        "resumo_md": "### resumo", "conversa": [{"role": "assistant", "texto": "### resumo"}],
    })
    r = client.post(
        f"/api/ia/{sid}/corrigir",
        data={"correcoes": "o salário de 03/2024 é R$ 2.000", "doc_contexto_0": "contracheques 2024"},
        files={"doc_arquivo_0": ("contracheque.txt", b"SALARIO 2000,00", "text/plain")},
    )
    assert r.status_code == 200 and r.json()["n_arquivos"] == 1

    for _ in range(60):  # worker falha com a chave fake (401)
        d = client.get(f"/api/ia/{sid}/estado").json()
        if d["fase"] != "etapa1_processando":
            break
        time.sleep(0.5)
    assert d["fase"] == "resumo_pronto", d
    assert d["resumo_md"] == "### resumo"
    assert "NÃO foi aplicada" in (d["aviso"] or "")
    assert d["correcao_pendente"] == "o salário de 03/2024 é R$ 2.000"
    assert d["erro"] is None

    est = wx._load_estado(sid)
    pend = est["correcao_pendente"]
    assert len(pend["arquivos"]) == 1 and Path(pend["arquivos"][0]["caminho"]).is_file()
    assert pend["arquivos"][0]["contexto"] == "contracheques 2024"
    assert all(not t.get("arquivos") for t in est["conversa"])  # turno falho saiu do histórico

    # o turno com anexo vira content-list: [bloco do documento..., texto]
    est["conversa"].append(pend)
    msgs = wx._montar_messages(est)
    ult = msgs[-1]
    assert ult["role"] == "user" and isinstance(ult["content"], list)
    assert "=== DOCUMENTO: contracheque.txt (contracheques 2024) ===" in ult["content"][0]["text"]
    assert "SALARIO 2000,00" in ult["content"][0]["text"]
    assert ult["content"][-1]["text"].startswith("o salário de 03/2024")
    assert "Anexei 1 documento" in ult["content"][-1]["text"]
    assert msgs[0]["content"][-1].get("cache_control")  # prefixo em cache intocado

    # JSON (forma original) continua aceito e reaproveita o anexo pendente
    r2 = client.post(f"/api/ia/{sid}/corrigir", json={"correcoes": "de novo"})
    assert r2.status_code == 200 and r2.json()["n_arquivos"] == 1

    # a 2ª tentativa também falha (chave fake) → anexo volta a ficar pendente;
    # com anexo pendente, correção SEM texto é aceita (reenvio só dos documentos)
    for _ in range(60):
        d = client.get(f"/api/ia/{sid}/estado").json()
        if d["fase"] != "etapa1_processando":
            break
        time.sleep(0.5)
    assert d["fase"] == "resumo_pronto" and d["correcao_pendente"] == "de novo"
    est = wx._load_estado(sid)
    est.pop("correcao_pendente")
    wx._save_estado(sid, est)
    # sem texto, sem documento e sem pendência → 400
    assert client.post(f"/api/ia/{sid}/corrigir", json={"correcoes": ""}).status_code == 400
