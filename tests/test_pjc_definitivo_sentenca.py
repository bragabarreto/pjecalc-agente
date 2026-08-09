# tests/test_pjc_definitivo_sentenca.py — #80-CF (28/07/2026)
#
# Upload do PJC DEFINITIVO com a opção "houve alteração no texto da sentença":
# o texto definitivo (colado ou arquivo) é persistido junto ao relatório de
# diff e entra no contexto da análise LLM — sem ele o aprendizado compararia o
# PJC corrigido contra a sentença ANTIGA (aprendendo correções que decorrem da
# mudança do título, não de erro da automação).

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest


def _pjc_bytes(cnj_limpo: str, descricao: str = "HORAS EXTRAS 50%",
               divisor: str = "220") -> bytes:
    """PJC sintético mínimo (ZIP + XML ISO-8859-1) com o CNJ no nome da entry."""
    xml = (
        "<Calculo><verbas><Set>"
        f"<Calculada><descricao>{descricao}</descricao>"
        f"<formula><FormulaCalculada><divisor><Divisor>"
        f"<outroValor>{divisor}</outroValor></Divisor></divisor>"
        "</FormulaCalculada></formula></Calculada>"
        "</Set></verbas></Calculo>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"PROCESSO_{cnj_limpo}_CALCULO_1_DATA_28072026.PJC",
                   xml.encode("iso-8859-1", "replace"))
    return buf.getvalue()


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    """TestClient com store de aprendizado isolado + sessão/cálculo falsos."""
    import webapp

    monkeypatch.setattr(webapp, "_APRENDIZADO_PJC_DIR", tmp_path / "aprendizado")
    import learning.pjc_aprendizado as PA
    monkeypatch.setattr(PA, "_APRENDIZADO_DIR", tmp_path / "aprendizado")

    cnj = "0000408-54.2026.5.07.0003"
    cnj_limpo = "".join(c for c in cnj if c.isdigit())
    gerado = tmp_path / "gerado.pjc"
    gerado.write_bytes(_pjc_bytes(cnj_limpo, divisor="220"))

    class _Proc:
        numero_processo = cnj

    class _Calc:
        id = 1
        processo = _Proc()
        arquivo_pjc = str(gerado)

    class _Repo:
        def __init__(self, db):
            pass

        def buscar_sessao(self, sid):
            return _Calc()

    monkeypatch.setattr(webapp, "RepositorioCalculo", _Repo)

    # background task da FATIA 2 não roda no teste (sem LLM)
    from fastapi.testclient import TestClient
    return TestClient(webapp.app), cnj_limpo, tmp_path / "aprendizado"


def _rel(store: Path, sessao: str) -> dict:
    return json.loads((store / f"{sessao}_diff.json").read_text(encoding="utf-8"))


def test_cf_sentenca_colada_persiste_e_entra_no_relatorio(app_client):
    client, cnj_limpo, store = app_client
    texto = "DISPOSITIVO RETIFICADO: horas extras com divisor 180 (jornada 12x36)."
    r = client.post(
        "/api/pjc-definitivo/sess-cf-1",
        files={"pjc": ("PROCESSO_%s_CALCULO_9.PJC" % cnj_limpo,
                       _pjc_bytes(cnj_limpo, divisor="180"), "application/octet-stream")},
        data={"sentenca_alterada": "true", "sentenca_texto": texto},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    sd = body["sentenca_definitiva"]
    assert sd["alterada"] is True and sd["chars"] == len(texto)
    assert (store / "sess-cf-1.sentenca_definitiva.txt").read_text(encoding="utf-8") == texto
    # o relatório regravado carrega o bloco (é o que o aprendizado lê depois)
    assert _rel(store, "sess-cf-1")["sentenca_definitiva"]["alterada"] is True


def test_cf_sentenca_arquivo_txt_extraido(app_client):
    client, cnj_limpo, store = app_client
    conteudo = "SENTENCA DEFINITIVA\n\nCondeno ao pagamento de horas extras."
    r = client.post(
        "/api/pjc-definitivo/sess-cf-2",
        files={
            "pjc": ("PROCESSO_%s_CALCULO_9.PJC" % cnj_limpo,
                    _pjc_bytes(cnj_limpo, divisor="180"), "application/octet-stream"),
            "sentenca_arquivo": ("sentenca_final.txt", conteudo.encode("utf-8"), "text/plain"),
        },
        data={"sentenca_alterada": "true"},
    )
    assert r.status_code == 200, r.text
    sd = r.json()["sentenca_definitiva"]
    assert sd["alterada"] is True and sd["chars"] > 0
    assert "sentenca_final.txt" in sd["origem"]
    salvo = (store / "sess-cf-2.sentenca_definitiva.txt").read_text(encoding="utf-8")
    assert "horas extras" in salvo.lower()


def test_cf_sem_alteracao_mantem_fluxo_antigo(app_client):
    """Compatibilidade: sem os campos novos o upload segue funcionando."""
    client, cnj_limpo, store = app_client
    r = client.post(
        "/api/pjc-definitivo/sess-cf-3",
        files={"pjc": ("PROCESSO_%s_CALCULO_9.PJC" % cnj_limpo,
                       _pjc_bytes(cnj_limpo, divisor="180"), "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    sd = r.json()["sentenca_definitiva"]
    assert sd["alterada"] is False
    assert not (store / "sess-cf-3.sentenca_definitiva.txt").exists()


def test_cf_alterada_sem_texto_avisa_e_nao_quebra(app_client):
    """Marcar alterada sem enviar texto não pode quebrar o aprendizado —
    registra aviso e segue com o contexto da prévia original."""
    client, cnj_limpo, store = app_client
    r = client.post(
        "/api/pjc-definitivo/sess-cf-4",
        files={"pjc": ("PROCESSO_%s_CALCULO_9.PJC" % cnj_limpo,
                       _pjc_bytes(cnj_limpo, divisor="180"), "application/octet-stream")},
        data={"sentenca_alterada": "true"},
    )
    assert r.status_code == 200, r.text
    sd = r.json()["sentenca_definitiva"]
    assert sd["alterada"] is True and sd["chars"] == 0
    assert "aviso" in _rel(store, "sess-cf-4")["sentenca_definitiva"]
