"""Endpoints webapp para Schema v2.0 da prévia.

Estes endpoints complementam os existentes em webapp.py sem quebrá-los.
Para ativar, adicionar no `webapp.py`:

    from modules.webapp_v2 import router_v2
    app.include_router(router_v2)

Endpoints adicionados:
- POST  /processar/v2              recebe JSON v2 do Projeto Claude externo
- GET   /previa/v2/{sessao_id}     renderiza template previa_v2.html
- PATCH /api/previa/v2/{sessao_id}/salvar   auto-save de campos editados
- GET   /api/previa/v2/{sessao_id}/validar  roda validação Pydantic e retorna erros
- POST  /api/previa/v2/{sessao_id}/confirmar  marca prévia como confirmada e libera automação
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Importar models v2 via importlib (arquivo começa com número)
_SCHEMA_PATH = Path(__file__).parent.parent / "docs" / "schema-v2"
if str(_SCHEMA_PATH) not in sys.path:
    sys.path.insert(0, str(_SCHEMA_PATH))

import importlib.util as _il_util

_spec = _il_util.spec_from_file_location(
    "pydantic_models_v2", _SCHEMA_PATH / "99-pydantic-models.py"
)
_pm = _il_util.module_from_spec(_spec)
_spec.loader.exec_module(_pm)

PreviaCalculoV2 = _pm.PreviaCalculoV2

logger = logging.getLogger(__name__)

router_v2 = APIRouter(tags=["v2"])

# Templates
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ─── Storage simplificado (in-memory por agora) ────────────────────────────
# Em produção, isso deve ser persistido no banco. Por enquanto usa um dict
# em memória + arquivo JSON em /tmp para retomar sessões interrompidas.

_PREVIA_STORE: dict[str, dict] = {}
_STORE_DIR = Path("/tmp/pjecalc_previa_v2")
_STORE_DIR.mkdir(parents=True, exist_ok=True)


def _save_previa(sessao_id: str, data: dict) -> None:
    _PREVIA_STORE[sessao_id] = data
    (_STORE_DIR / f"{sessao_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_previa(sessao_id: str) -> dict | None:
    if sessao_id in _PREVIA_STORE:
        return _PREVIA_STORE[sessao_id]
    fp = _STORE_DIR / f"{sessao_id}.json"
    if fp.exists():
        data = json.loads(fp.read_text(encoding="utf-8"))
        _PREVIA_STORE[sessao_id] = data
        return data
    return None


# ─── POST /processar/v2 ────────────────────────────────────────────────────


@router_v2.post("/processar/v2")
async def processar_v2(payload: dict):
    """Recebe JSON v2 do Projeto Claude externo + cria sessão.

    Body esperado: o JSON da prévia conforme schema v2.0
    Retorna: {sessao_id, redirect_url}
    """
    try:
        # Validar via Pydantic (sanity check inicial)
        previa = PreviaCalculoV2.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Schema v2 inválido: {e}")

    sessao_id = str(uuid.uuid4())
    _save_previa(sessao_id, previa.model_dump())

    return JSONResponse({
        "sessao_id": sessao_id,
        "redirect_url": f"/previa/v2/{sessao_id}",
        "completude": previa.meta.validacao.completude,
        "campos_faltantes": previa.meta.validacao.campos_faltantes,
        "avisos": previa.meta.validacao.avisos,
    })


# ─── GET /previa/v2/{sessao_id} ────────────────────────────────────────────


@router_v2.get("/previa/v2/{sessao_id}", response_class=HTMLResponse)
async def previa_v2_view(sessao_id: str, request: Request):
    """Renderiza template previa_v2.html com os dados da sessão."""
    data = _load_previa(sessao_id)
    if not data:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    return templates.TemplateResponse(
        "previa_v2.html",
        {
            "request": request,
            "sessao_id": sessao_id,
            "previa_json": data,
        },
    )


# ─── PATCH /api/previa/v2/{sessao_id}/salvar ───────────────────────────────


@router_v2.patch("/api/previa/v2/{sessao_id}/salvar")
async def salvar_campos(sessao_id: str, payload: dict):
    """Auto-save de campos editados na UI da prévia.

    Body: prévia completa atualizada (substitui no storage).
    """
    if not _load_previa(sessao_id):
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    _save_previa(sessao_id, payload)
    return {"status": "saved"}


# ─── GET /api/previa/v2/{sessao_id}/validar ────────────────────────────────


@router_v2.get("/api/previa/v2/{sessao_id}/validar")
async def validar_previa(sessao_id: str):
    """Roda validação Pydantic e retorna erros estruturados."""
    data = _load_previa(sessao_id)
    if not data:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    try:
        previa = PreviaCalculoV2.model_validate(data)
        return {
            "valida": previa.meta.validacao.completude == "OK",
            "completude": previa.meta.validacao.completude,
            "campos_faltantes": previa.meta.validacao.campos_faltantes,
            "avisos": previa.meta.validacao.avisos,
        }
    except Exception as e:
        return {
            "valida": False,
            "completude": "ERRO",
            "erro_pydantic": str(e),
            "campos_faltantes": [],
            "avisos": [],
        }


# ─── POST /api/previa/v2/{sessao_id}/confirmar ────────────────────────────


@router_v2.post("/api/previa/v2/{sessao_id}/confirmar")
async def confirmar_previa(sessao_id: str, payload: dict):
    """Confirma prévia + valida + libera para automação.

    Em sucesso, salva e marca como pronta para automação.
    Em erro, retorna 422 com lista de pendências.
    """
    try:
        previa = PreviaCalculoV2.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Validação Pydantic falhou: {e}")

    if previa.meta.validacao.completude != "OK":
        raise HTTPException(
            status_code=422,
            detail={
                "completude": previa.meta.validacao.completude,
                "campos_faltantes": previa.meta.validacao.campos_faltantes,
                "avisos": previa.meta.validacao.avisos,
            },
        )

    # Salvar como confirmada
    data = previa.model_dump()
    data["meta"]["confirmada"] = True
    _save_previa(sessao_id, data)

    # TODO Fase 5: enfileirar automação aqui
    return {
        "status": "confirmada",
        "sessao_id": sessao_id,
        "redirect_url": f"/instrucoes/{sessao_id}",
    }


# ─── Helper: converter prévia v2 → v1 (compat com automação atual) ────────


def previa_v2_para_v1(previa_v2_dict: dict) -> dict:
    """Conversão lossy de schema v2 para v1 (legado).

    Útil enquanto a automação (módulo playwright_pjecalc.py) ainda consome
    formato v1. Após Fase 5, esta função será removida.
    """
    p = previa_v2_dict
    pc = p.get("parametros_calculo", {})
    proc = p.get("processo", {})

    return {
        "processo": {
            "numero": proc.get("numero_processo"),
            "reclamante": proc.get("reclamante", {}).get("nome"),
            "reclamado": proc.get("reclamado", {}).get("nome"),
            "estado": pc.get("estado_uf"),
            "municipio": pc.get("municipio"),
        },
        "contrato": {
            "admissao": pc.get("data_admissao"),
            "demissao": pc.get("data_demissao"),
            "ajuizamento": pc.get("data_ajuizamento"),
            "data_inicio_calculo": pc.get("data_inicio_calculo"),
            "data_termino_calculo": pc.get("data_termino_calculo"),
            "maior_remuneracao": pc.get("valor_maior_remuneracao_brl"),
            "ultima_remuneracao": pc.get("valor_ultima_remuneracao_brl"),
        },
        "verbas": p.get("verbas_principais", []),
        "historico_salarial": p.get("historico_salarial", []),
        "fgts": p.get("fgts", {}),
        "contribuicao_social": p.get("contribuicao_social", {}),
        "imposto_renda": p.get("imposto_de_renda", {}),
        "honorarios": p.get("honorarios", []),
        "custas_judiciais": p.get("custas_judiciais", {}),
        "correcao_juros": p.get("correcao_juros_multa", {}),
        # ... adapte conforme necessidade
    }
