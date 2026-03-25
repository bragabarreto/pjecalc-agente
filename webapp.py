# webapp.py — Interface Web do Agente PJE-Calc
# Acréscimo ao Manual Técnico v1.0 — 2026
#
# Framework: FastAPI + Jinja2 (HTML) + SQLAlchemy (banco de dados)
#
# USO:
#   uvicorn webapp:app --reload --port 8000
#   Acesse: http://localhost:8000

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, Form, HTTPException,
    Request, UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import logging

logger = logging.getLogger("pjecalc_agent.webapp")

import time as _time
from config import OUTPUT_DIR, CLOUD_MODE, PJECALC_DIR

# Sessões em processamento (em memória) — evita 404 enquanto background task roda
_sessoes_processando: dict[str, float] = {}  # sessao_id → timestamp de início
from database import (
    Calculo, Processo, RepositorioCalculo, SessionLocal, get_db,
)
from modules.ingestion import ler_documento
from modules.extraction import extrair_dados_sentenca
from modules.classification import mapear_para_pjecalc
from modules.preview import gerar_previa, aplicar_edicao_usuario, aplicar_edicao_verba

# ── Configuração da aplicação ─────────────────────────────────────────────────

app = FastAPI(
    title="Agente PJE-Calc",
    description="Automação de Liquidação de Sentenças Trabalhistas",
    version="1.0.0",
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Servir arquivos estáticos se existirem
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Rotas principais ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def pagina_inicial(request: Request, db: Session = Depends(get_db)):
    """Página inicial — lista de processos e calculações recentes."""
    repo = RepositorioCalculo(db)
    processos = repo.listar_processos(limit=20)
    return templates.TemplateResponse(
        request, "index.html",
        {"processos": processos, "agora": datetime.now()},
    )


@app.get("/novo", response_class=HTMLResponse)
async def pagina_novo_calculo(request: Request):
    """Formulário para iniciar novo cálculo."""
    return templates.TemplateResponse(
        request, "novo_calculo.html", {}
    )


@app.post("/processar")
async def processar_sentenca(
    request: Request,
    background_tasks: BackgroundTasks,
    sentenca: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Recebe o arquivo de sentença e documentos complementares (até 10),
    extrai dados e inicia o processamento em background.
    """
    sessao_id = str(uuid.uuid4())

    # Salvar sentença principal em temp
    sufixo = Path(sentenca.filename or "sentenca.pdf").suffix.lower()
    tmp_dir = Path(tempfile.mkdtemp())
    tmp_path = tmp_dir / f"sentenca{sufixo}"
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(sentenca.file, f)

    # Coletar documentos extras do form (doc_arquivo_N, doc_imagem_N, doc_texto_N, doc_contexto_N)
    form = await request.form()
    extras: list[dict] = []
    _MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB por arquivo
    _IMG_MAX_PX = 1536               # redimensionar imagens para no máximo 1536px

    for i in range(10):
        contexto = str(form.get(f"doc_contexto_{i}", "")).strip()

        arq = form.get(f"doc_arquivo_{i}")
        img = form.get(f"doc_imagem_{i}")
        txt = form.get(f"doc_texto_{i}")

        if arq and hasattr(arq, "filename") and arq.filename:
            dados = await arq.read()
            if len(dados) > _MAX_FILE_BYTES:
                continue  # ignorar arquivos muito grandes
            suf = Path(arq.filename).suffix.lower()
            extra_path = tmp_dir / f"extra_{i}{suf}"
            extra_path.write_bytes(dados)
            del dados
            extras.append({"tipo": "arquivo", "caminho": str(extra_path), "contexto": contexto})

        elif img and hasattr(img, "filename") and img.filename:
            from PIL import Image as _PIL
            import io as _io
            dados = await img.read()
            if len(dados) > _MAX_FILE_BYTES:
                continue
            # Redimensionar para economizar memória e tokens do LLM
            try:
                pil_img = _PIL.open(_io.BytesIO(dados))
                pil_img.thumbnail((_IMG_MAX_PX, _IMG_MAX_PX), _PIL.Resampling.LANCZOS)
                buf = _io.BytesIO()
                fmt = "JPEG" if pil_img.mode in ("RGB", "L") else "PNG"
                if pil_img.mode == "RGBA":
                    pil_img = pil_img.convert("RGB")
                    fmt = "JPEG"
                pil_img.save(buf, format=fmt, quality=85)
                dados = buf.getvalue()
                mime = "image/jpeg" if fmt == "JPEG" else "image/png"
            except Exception:
                mime = getattr(img, "content_type", "image/jpeg")
            extra_path = tmp_dir / f"extra_img_{i}.jpg"
            extra_path.write_bytes(dados)
            del dados
            extras.append({
                "tipo": "imagem",
                "caminho": str(extra_path),
                "mime_type": mime,
                "contexto": contexto,
            })

        elif txt and str(txt).strip():
            extras.append({"tipo": "texto", "conteudo": str(txt).strip()[:8000], "contexto": contexto})

    # Detectar se é relatório estruturado (ex: saída do Projeto Claude)
    is_relatorio = str(form.get("input_type", "")).strip() == "relatorio"

    # Modelo de IA selecionado pelo usuário: "gemini" | "claude" | "" (padrão do config)
    modelo_ia = str(form.get("modelo_ia", "")).strip().lower()
    usar_gemini: bool | None = None
    if modelo_ia == "gemini":
        usar_gemini = True
    elif modelo_ia == "claude":
        usar_gemini = False

    # Registrar sessão em memória antes de iniciar background (evita 404 durante processamento)
    _sessoes_processando[sessao_id] = _time.time()

    # Processar em background
    background_tasks.add_task(
        _tarefa_processar_sentenca,
        sessao_id=sessao_id,
        caminho=tmp_path,
        formato=sufixo,
        extras=extras,
        is_relatorio=is_relatorio,
        usar_gemini=usar_gemini,
    )

    n_extras = len(extras)
    return JSONResponse({
        "sessao_id": sessao_id,
        "status": "processando",
        "mensagem": (
            f"Sentença recebida com {n_extras} documento(s) adicional(is). Processando..."
            if n_extras else "Sentença recebida. Processando extração de dados..."
        ),
        "url_status": f"/status/{sessao_id}",
        "url_previa": f"/previa/{sessao_id}",
    })


@app.get("/status/{sessao_id}")
async def verificar_status(sessao_id: str, db: Session = Depends(get_db)):
    """Retorna o status atual do processamento de uma sessão."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        # Enquanto background task ainda processa, retornar "processando" (não 404)
        if sessao_id in _sessoes_processando:
            return JSONResponse({"status": "processando", "sessao_id": sessao_id})
        return JSONResponse({"status": "nao_encontrado"}, status_code=404)

    return JSONResponse({
        "sessao_id": sessao_id,
        "status": calculo.status,
        "processo": calculo.processo.numero_processo if calculo.processo else None,
        "reclamante": calculo.processo.reclamante if calculo.processo else None,
        "atualizado_em": calculo.atualizado_em.isoformat() if calculo.atualizado_em else None,
        "tem_previa": calculo.previa_texto is not None,
        "url_previa": f"/previa/{sessao_id}" if calculo.previa_texto else None,
    })


@app.get("/previa/{sessao_id}", response_class=HTMLResponse)
async def exibir_previa_web(
    request: Request,
    sessao_id: str,
    db: Session = Depends(get_db),
):
    """
    Exibe a prévia dos parâmetros do cálculo para apreciação e correção.
    Prévia fica salva no banco vinculada ao número do processo.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)

    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()
    previa_texto = calculo.previa_texto or gerar_previa(dados, verbas_mapeadas)

    return templates.TemplateResponse(
        request, "previa.html",
        {
            "sessao_id": sessao_id,
            "calculo": calculo,
            "processo": calculo.processo,
            "dados": dados,
            "verbas_mapeadas": verbas_mapeadas,
            "previa_texto": previa_texto,
            "campos_ausentes": dados.get("campos_ausentes", []),
            "alertas": dados.get("alertas", []),
            "inconsistencias_criticas": dados.get("inconsistencias_criticas", []),
            "verbas": calculo.verbas,
            "status": calculo.status,
        },
    )


@app.post("/previa/{sessao_id}/editar")
async def editar_campo_previa(
    sessao_id: str,
    campo: str = Form(...),
    valor: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Permite edição de qualquer campo da prévia pelo usuário.
    Registra no log de rastreabilidade e regera a prévia.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()

    # Aplicar edição
    dados = aplicar_edicao_usuario(dados, campo, valor)

    # Registrar rastreabilidade
    repo.registrar_rastreabilidade(sessao_id, {
        "campo_pjecalc": campo,
        "valor": valor,
        "fonte": "USUARIO",
        "confirmado_usuario": True,
        "pergunta_formulada": f"Edição manual via interface web: {campo}",
        "resposta_usuario": valor,
    })

    # Regenerar prévia
    nova_previa = gerar_previa(dados, verbas_mapeadas)
    nova_previa_html = _previa_para_html(nova_previa)

    repo.atualizar_dados(sessao_id, dados, verbas_mapeadas)
    repo.salvar_previa(sessao_id, nova_previa, nova_previa_html)

    return JSONResponse({
        "sucesso": True,
        "campo": campo,
        "valor": valor,
        "previa_atualizada": nova_previa,
    })


@app.post("/previa/{sessao_id}/editar-verba")
async def editar_verba(
    sessao_id: str,
    indice: int = Form(...),
    campo: str = Form(...),
    valor: str = Form(...),
    db: Session = Depends(get_db),
):
    """Edita um campo de uma verba específica pelo índice."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()
    verbas_mapeadas = aplicar_edicao_verba(verbas_mapeadas, indice, campo, valor)

    nova_previa = gerar_previa(dados, verbas_mapeadas)
    repo.atualizar_dados(sessao_id, dados, verbas_mapeadas)
    repo.salvar_previa(sessao_id, nova_previa, _previa_para_html(nova_previa))

    return JSONResponse({"sucesso": True, "indice": indice, "campo": campo, "valor": valor})


@app.post("/previa/{sessao_id}/confirmar")
async def confirmar_previa(
    request: Request,
    sessao_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Confirma a prévia e inicia o preenchimento automatizado do PJE-Calc.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    repo.confirmar_previa(sessao_id)

    # Gerar .pjc (backup)
    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()
    url_pjc = None
    try:
        from modules.pjc_generator import gerar_pjc
        caminho_pjc = gerar_pjc(dados, verbas_mapeadas, sessao_id)
        repo.marcar_exportado(sessao_id, str(caminho_pjc))
        url_pjc = f"/download/{sessao_id}/pjc"
    except Exception as exc:
        logger.warning(f"Não foi possível gerar .pjc: {exc}")

    url_launcher = f"/download/{sessao_id}/launcher"
    url_script   = f"/download/{sessao_id}/script"

    # Sempre redireciona para instrucoes — automação Playwright é disparada
    # pelo botão "Executar Automação" nessa página (SSE /api/executar/{sessao_id}).
    # O caminho antigo (pyautogui background task) não é usado no Railway.
    return JSONResponse({
        "sucesso": True,
        "mensagem": "Parâmetros confirmados. Clique em 'Executar Automação' na próxima tela.",
        "cloud_mode": CLOUD_MODE,
        "url_launcher":   url_launcher,
        "url_script":     url_script,
        "url_pjc":        url_pjc,
        "url_parametros": f"/download/{sessao_id}/parametros",
        "url_instrucoes": f"/instrucoes/{sessao_id}",
        "url_status":     f"/status/{sessao_id}",
    })


@app.get("/processo/{numero_processo}", response_class=HTMLResponse)
async def pagina_processo(
    request: Request,
    numero_processo: str,
    db: Session = Depends(get_db),
):
    """
    Exibe todos os cálculos de um processo, com links para as prévias salvas.
    """
    repo = RepositorioCalculo(db)
    calculos = repo.buscar_por_processo(numero_processo)
    if not calculos:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    return templates.TemplateResponse(
        request, "processo.html",
        {
            "numero_processo": numero_processo,
            "calculos": calculos,
            "processo": calculos[0].processo if calculos else None,
        },
    )


@app.get("/processo/{numero_processo}/previa-atual", response_class=HTMLResponse)
async def previa_atual_processo(
    request: Request,
    numero_processo: str,
    db: Session = Depends(get_db),
):
    """Redireciona para a prévia mais recente do processo."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_previa(numero_processo)
    if not calculo:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma prévia encontrada para este processo"
        )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/previa/{calculo.sessao_id}")


@app.get("/download/{sessao_id}/pjc")
async def download_pjc(sessao_id: str, db: Session = Depends(get_db)):
    """Download do arquivo .pjc gerado."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Gerar sob demanda se ainda não foi gerado
    if not calculo.arquivo_pjc or not Path(calculo.arquivo_pjc).exists():
        try:
            from modules.pjc_generator import gerar_pjc
            dados = calculo.dados()
            verbas_mapeadas = calculo.verbas_mapeadas()
            caminho_pjc = gerar_pjc(dados, verbas_mapeadas, sessao_id)
            repo.marcar_exportado(sessao_id, str(caminho_pjc))
            calculo = repo.buscar_sessao(sessao_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Erro ao gerar .pjc: {exc}")

    caminho = Path(calculo.arquivo_pjc)
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo .pjc não encontrado no servidor")

    return FileResponse(
        path=str(caminho),
        filename=caminho.name,
        media_type="application/zip",
    )


@app.get("/download/{sessao_id}/launcher")
async def download_launcher(
    request: Request,
    sessao_id: str,
    db: Session = Depends(get_db),
):
    """
    Download do launcher .bat — duplo-clique para instalar e executar.
    O .bat baixa automaticamente o script .py do servidor e o executa.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    try:
        from modules.playwright_script_builder import gerar_launcher_bat
        base_url   = str(request.base_url).rstrip("/")
        script_url = f"{base_url}/download/{sessao_id}/script"
        dados      = calculo.dados()
        numero     = dados.get("processo", {}).get("numero", sessao_id[:8])
        caminho    = gerar_launcher_bat(script_url, sessao_id, numero)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Erro ao gerar launcher [{sessao_id}]: {exc}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar launcher: {exc}")

    return FileResponse(
        path=str(caminho),
        filename=caminho.name,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{caminho.name}"'},
    )


@app.get("/download/{sessao_id}/script")
async def download_script(sessao_id: str, db: Session = Depends(get_db)):
    """
    Gera e serve o script Python Playwright standalone para automação do PJE-Calc.
    O usuário baixa o script e executa localmente: python auto_pjecalc_XXX.py
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    try:
        from modules.playwright_script_builder import gerar_script
        dados = calculo.dados()
        verbas_mapeadas = calculo.verbas_mapeadas()
        caminho = gerar_script(dados, verbas_mapeadas, sessao_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Erro ao gerar script [{sessao_id}]: {exc}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar script: {exc}")

    return FileResponse(
        path=str(caminho),
        filename=caminho.name,
        media_type="text/x-python",
        headers={"Content-Disposition": f'attachment; filename="{caminho.name}"'},
    )


@app.get("/download/{sessao_id}/parametros")
async def download_parametros(sessao_id: str, db: Session = Depends(get_db)):
    """
    Download dos parâmetros confirmados em JSON.
    Usado para preencher o PJE-Calc localmente via script de automação.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()

    payload = {
        "sessao_id": sessao_id,
        "exportado_em": datetime.now().isoformat(),
        "processo": dados.get("processo", {}),
        "contrato": dados.get("contrato", {}),
        "prescricao": dados.get("prescricao", {}),
        "aviso_previo": dados.get("aviso_previo", {}),
        "fgts": dados.get("fgts", {}),
        "honorarios": dados.get("honorarios", {}),
        "correcao_juros": dados.get("correcao_juros", {}),
        "contribuicao_social": dados.get("contribuicao_social", {}),
        "imposto_renda": dados.get("imposto_renda", {}),
        "verbas_mapeadas": verbas_mapeadas,
    }

    numero = dados.get("processo", {}).get("numero", sessao_id[:8])
    nome_arquivo = f"pjecalc_{numero.replace('-','').replace('.','')}.json"

    from fastapi.responses import Response
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


@app.get("/instrucoes/{sessao_id}", response_class=HTMLResponse)
async def instrucoes_preenchimento(
    request: Request,
    sessao_id: str,
    db: Session = Depends(get_db),
):
    """
    Página com instruções passo a passo para preencher o PJE-Calc
    usando os parâmetros confirmados no agente.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    from urllib.parse import quote as url_quote

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()

    base_url = str(request.base_url).rstrip("/").replace("http://", "https://")
    pjecalc_url = (
        "http://localhost:9257/pjecalc/pages/principal.jsf"
        f"#agente-sessao={sessao_id}"
        f"&agente-server={url_quote(base_url, safe='')}"
    )

    try:
        return templates.TemplateResponse(
            request, "instrucoes.html",
            {
                "sessao_id": sessao_id,
                "calculo": calculo,
                "processo": calculo.processo,
                "dados": dados,
                "verbas_mapeadas": verbas_mapeadas,
                "base_url": base_url,
                "pjecalc_url": pjecalc_url,
                "cloud_mode": CLOUD_MODE,
            },
        )
    except Exception as exc:
        logger.exception(f"Erro ao renderizar instrucoes [{sessao_id}]: {exc}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar página de instruções: {exc}")


@app.get("/api/processos")
async def api_listar_processos(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """API REST — lista processos com paginação."""
    repo = RepositorioCalculo(db)
    processos = repo.listar_processos(limit=limit, offset=offset)
    return [
        {
            "numero": p.numero_processo,
            "reclamante": p.reclamante,
            "reclamado": p.reclamado,
            "calculos": len(p.calculos),
            "url": f"/processo/{p.numero_processo}",
        }
        for p in processos
    ]


@app.get("/api/calculo/{sessao_id}")
async def api_detalhe_calculo(sessao_id: str, db: Session = Depends(get_db)):
    """API REST — retorna dados completos de um cálculo."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    return {
        "sessao_id": calculo.sessao_id,
        "status": calculo.status,
        "processo": {
            "numero": calculo.processo.numero_processo,
            "reclamante": calculo.processo.reclamante,
            "reclamado": calculo.processo.reclamado,
        } if calculo.processo else None,
        "dados": calculo.dados(),
        "verbas": calculo.verbas_mapeadas(),
        "verbas_mapeadas": calculo.verbas_mapeadas(),   # alias para a extensão
        "tem_previa": calculo.previa_texto is not None,
        "arquivo_pjc": calculo.arquivo_pjc,
        "criado_em": calculo.criado_em.isoformat() if calculo.criado_em else None,
        "confirmado_em": calculo.confirmado_em.isoformat() if calculo.confirmado_em else None,
    }


@app.get("/download/extensao")
async def download_extensao():
    """
    Gera e serve o .zip da extensão Chrome/Firefox para instalação com um clique.
    O usuário extrai o zip e carrega a pasta no browser (modo desenvolvedor).
    """
    import io
    import zipfile

    extension_dir = Path(__file__).parent / "extension"
    if not extension_dir.exists():
        raise HTTPException(status_code=404, detail="Pasta extension/ não encontrada no servidor.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(extension_dir.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(extension_dir))
    buffer.seek(0)

    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=agente-pjecalc-extensao.zip"},
    )


# ── Automação Playwright local ────────────────────────────────────────────────

# Dicionário compartilhado: sessao_id → lista de mensagens de progresso
_automacao_log: dict[str, list[str]] = {}
_automacao_ativa: dict[str, bool] = {}


# ── Novos endpoints CalcMachine ────────────────────────────────────────────────

@app.get("/api/verificar_pjecalc")
async def verificar_pjecalc():
    """Verifica se localhost:9257 está respondendo (apenas checagem, sem iniciar)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("http://localhost:9257/pjecalc")
            if r.status_code in (200, 302, 404):
                return {"status": "ok", "codigo_http": r.status_code}
            return {"status": "erro", "codigo_http": r.status_code}
    except Exception as e:
        return {"status": "indisponivel", "detalhe": str(e)}


@app.get("/api/screenshot", response_class=HTMLResponse)
async def screenshot_xvfb():
    """Screenshot do display Xvfb :99 — mostra o que está na tela virtual."""
    import subprocess, base64, shutil
    tmp = "/tmp/xvfb_ss.png"
    # Tentar scrot
    if shutil.which("scrot"):
        subprocess.run(["scrot", "--display", ":99", tmp],
                       capture_output=True, timeout=8, env={**__import__("os").environ, "DISPLAY": ":99"})
    # Fallback: xwd | convert
    if not Path(tmp).exists() and shutil.which("xwd"):
        xwd = subprocess.run(["xwd", "-root", "-display", ":99", "-silent"],
                             capture_output=True, timeout=8)
        if xwd.returncode == 0 and shutil.which("convert"):
            subprocess.run(["convert", "xwd:-", tmp], input=xwd.stdout,
                           capture_output=True, timeout=8)
    if Path(tmp).exists():
        data = base64.b64encode(Path(tmp).read_bytes()).decode()
        Path(tmp).unlink(missing_ok=True)
        return f'<html><body style="background:#111"><img src="data:image/png;base64,{data}" style="max-width:100%;border:1px solid #555"></body></html>'
    return "<html><body>Screenshot não disponível — scrot não instalado ou display :99 sem janelas.</body></html>"


@app.get("/api/xwininfo")
async def xwininfo():
    """Lista janelas abertas no Xvfb :99."""
    import subprocess
    try:
        r = subprocess.run(["xwininfo", "-display", ":99", "-root", "-tree"],
                           capture_output=True, text=True, timeout=8)
        return {"janelas": r.stdout, "erro": r.stderr}
    except Exception as e:
        return {"janelas": "", "erro": str(e)}


@app.get("/api/logs/tomcat")
async def logs_tomcat(linhas: int = 80):
    """Retorna as últimas N linhas do catalina.out do Tomcat embarcado."""
    import subprocess
    catalina = Path("/opt/pjecalc/tomcat/logs/catalina.out")
    if not catalina.exists():
        return {"log": "(catalina.out não existe ainda — Tomcat ainda não iniciou)"}
    try:
        result = subprocess.run(
            ["tail", f"-{linhas}", str(catalina)],
            capture_output=True, timeout=5
        )
        texto = result.stdout.decode("iso-8859-1", errors="replace")
        return {"log": texto or "(vazio)"}
    except Exception as e:
        return {"log": f"Erro ao ler log: {e}"}


@app.get("/api/logs/java")
async def logs_java(linhas: int = 100):
    """Retorna stdout+stderr completo do processo Java (Lancador + Tomcat)."""
    import subprocess
    log = Path("/opt/pjecalc/java.log")
    if not log.exists():
        return {"log": "(java.log não existe — processo Java ainda não iniciou ou não está redirecionando saída)"}
    try:
        result = subprocess.run(["tail", f"-{linhas}", str(log)],
                                capture_output=True, timeout=5)
        texto = result.stdout.decode("iso-8859-1", errors="replace")
        return {"log": texto or "(vazio)"}
    except Exception as e:
        return {"log": f"Erro: {e}"}


@app.get("/api/ps")
async def listar_processos():
    """Lista processos em execução no container (diagnóstico)."""
    import subprocess
    result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
    return {"processos": result.stdout}


@app.get("/api/campos_log/{filename}")
async def ler_campos_log(filename: str):
    """Retorna o JSON de campos mapeados pelo Playwright (diagnóstico remoto).
    Uso: GET /api/campos_log/campos_verba_form  ou  /api/campos_log/campos_fase3_verbas
    Permite inspecionar os IDs reais dos campos HTML após um run de automação.
    """
    log_dir = Path("data/logs")
    safe = Path(filename).name  # bloqueia path traversal
    if not safe.endswith(".json"):
        safe += ".json"
    arq = log_dir / safe
    if not arq.exists():
        return JSONResponse(
            {"erro": f"{safe} não encontrado em data/logs/"},
            status_code=404,
        )
    return JSONResponse(json.loads(arq.read_text(encoding="utf-8")))


@app.get("/api/executar/{sessao_id}")
async def executar_automacao_sse(
    sessao_id: str,
    modo_oculto: bool = False,
    db: Session = Depends(get_db),
):
    """
    SSE endpoint — transmite logs da automação Playwright em tempo real.
    Padrão CalcMachine: generator Python → StreamingResponse text/event-stream.
    """
    from fastapi.responses import StreamingResponse

    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()

    async def gerador_sse():
        import httpx
        from modules.playwright_pjecalc import preencher_como_generator
        from database import SessionLocal

        # Aguardar Tomcat ficar pronto (pode estar ainda inicializando)
        TOMCAT_TIMEOUT = 600
        elapsed = 0
        while elapsed < TOMCAT_TIMEOUT:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get("http://localhost:9257/pjecalc")
                    if r.status_code in (200, 302, 404):
                        break
            except Exception:
                pass
            if elapsed == 0:
                yield f"data: {json.dumps({'msg': 'PJE-Calc ainda inicializando — aguardando Tomcat ficar pronto...'})}\n\n"
            elif elapsed % 30 == 0:
                yield f"data: {json.dumps({'msg': f'Aguardando Tomcat... ({elapsed}s)'})}\n\n"
            await asyncio.sleep(10)
            elapsed += 10
        else:
            yield f"data: {json.dumps({'msg': 'ERRO: PJE-Calc não ficou disponível após 10 min. Verifique os logs do servidor.'})}\n\n"
            yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
            return

        import queue as _queue

        loop = asyncio.get_event_loop()
        gen = preencher_como_generator(dados, verbas_mapeadas, PJECALC_DIR, modo_oculto)

        # Fila para desacoplar a thread do gerador do loop assíncrono.
        # Permite emitir keepalive SSE a cada 25s sem output do Playwright.
        fila: _queue.Queue = _queue.Queue()

        def _executar_gen():
            """Roda em thread executor — coloca mensagens na fila."""
            try:
                while True:
                    try:
                        msg = next(gen)
                        fila.put(("ok", msg))
                        if msg == "[FIM DA EXECUÇÃO]":
                            break
                    except StopIteration:
                        fila.put(("fim", None))
                        break
            except Exception as exc:
                fila.put(("erro", str(exc)))

        loop.run_in_executor(None, _executar_gen)

        while True:
            try:
                kind, value = await loop.run_in_executor(
                    None, lambda: fila.get(timeout=25)
                )
            except _queue.Empty:
                # Heartbeat: evita timeout de proxy/browser em automações longas
                yield f"data: {json.dumps({'keepalive': True})}\n\n"
                continue

            if kind == "ok":
                msg = value
                yield f"data: {json.dumps({'msg': msg})}\n\n"
                # Detectar .PJC gerado e persistir no banco
                if msg.startswith("PJC_GERADO:"):
                    caminho = msg.split(":", 1)[1].strip()
                    db2 = SessionLocal()
                    try:
                        RepositorioCalculo(db2).marcar_exportado(sessao_id, caminho)
                        db2.commit()
                    finally:
                        db2.close()
                    yield f"data: {json.dumps({'msg': 'DOWNLOAD_DISPONIVEL', 'url': f'/download/{sessao_id}/pjc'})}\n\n"
                if msg == "[FIM DA EXECUÇÃO]":
                    break
            elif kind == "fim":
                yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
                break
            elif kind == "erro":
                yield f"data: {json.dumps({'msg': f'ERRO na automação: {value}'})}\n\n"
                yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
                break

    return StreamingResponse(
        gerador_sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/preencher/{sessao_id}")
async def iniciar_preenchimento_playwright(
    sessao_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Inicia o preenchimento automático do PJE-Calc Cidadão via Playwright (local).
    Requer PJE-Calc instalado no diretório configurado em PJECALC_DIR.
    """
    if CLOUD_MODE:
        raise HTTPException(
            status_code=400,
            detail="Automação local indisponível em modo cloud. Use a extensão de browser.",
        )

    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    if _automacao_ativa.get(sessao_id):
        return JSONResponse({"ok": False, "mensagem": "Automação já em execução para esta sessão."})

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()

    _automacao_log[sessao_id] = []
    _automacao_ativa[sessao_id] = True

    background_tasks.add_task(
        _tarefa_playwright, sessao_id, dados, verbas_mapeadas
    )
    return JSONResponse({"ok": True, "mensagem": "Automação iniciada."})


@app.get("/api/preencher/{sessao_id}/progresso")
async def progresso_preenchimento(sessao_id: str, desde: int = 0):
    """
    SSE stream com o progresso da automação Playwright.
    O cliente passa `desde=N` para receber apenas mensagens a partir do índice N.
    """
    from fastapi.responses import StreamingResponse

    async def gerador():
        ultima_pos = desde
        idle_count = 0
        while True:
            msgs = _automacao_log.get(sessao_id, [])
            if len(msgs) > ultima_pos:
                for msg in msgs[ultima_pos:]:
                    yield f"data: {json.dumps({'idx': ultima_pos, 'msg': msg})}\n\n"
                    ultima_pos += 1
                idle_count = 0
            else:
                idle_count += 1
                # Encerra stream se automação concluída e nenhuma mensagem nova por 5s
                if not _automacao_ativa.get(sessao_id) and idle_count > 10:
                    yield "data: {\"fim\": true}\n\n"
                    break
            import asyncio
            await asyncio.sleep(0.5)

    return StreamingResponse(
        gerador(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Tarefas em Background ─────────────────────────────────────────────────────

def _tarefa_playwright(
    sessao_id: str,
    dados: dict,
    verbas_mapeadas: dict,
) -> None:
    """Executa a automação Playwright em thread separada."""
    from modules.playwright_pjecalc import iniciar_e_preencher

    def _cb(msg: str) -> None:
        _automacao_log.setdefault(sessao_id, []).append(msg)

    try:
        iniciar_e_preencher(
            dados=dados,
            verbas_mapeadas=verbas_mapeadas,
            pjecalc_dir=PJECALC_DIR,
            log_cb=_cb,
        )
    except Exception as exc:
        _cb(f"ERRO: {exc}")
        logger.exception(f"Erro na automação Playwright [{sessao_id}]: {exc}")
    finally:
        _automacao_ativa[sessao_id] = False


def _tarefa_processar_sentenca(
    sessao_id: str,
    caminho: Path,
    formato: str,
    extras: list[dict] | None = None,
    is_relatorio: bool = False,
    usar_gemini: bool | None = None,
) -> None:
    """
    Tarefa de background: lê, extrai e classifica dados da sentença.
    Aceita documentos extras (arquivos, imagens, textos colados) para enriquecer a extração.
    Persiste resultado no banco de dados.
    """
    import base64
    db = SessionLocal()
    try:
        repo = RepositorioCalculo(db)

        # Fase 1: Ingestão da sentença principal
        resultado = ler_documento(caminho)
        texto = resultado["texto"]

        # Fase 1b: Processar documentos extras
        extras_processados: list[dict] = []
        for extra in (extras or []):
            try:
                if extra["tipo"] == "texto":
                    extras_processados.append({
                        "tipo": "texto",
                        "conteudo": extra["conteudo"],
                        "contexto": extra.get("contexto", ""),
                    })
                elif extra["tipo"] == "arquivo":
                    res_extra = ler_documento(extra["caminho"])
                    extras_processados.append({
                        "tipo": "texto",
                        "conteudo": res_extra["texto"],
                        "contexto": extra.get("contexto", ""),
                    })
                elif extra["tipo"] == "imagem":
                    img_bytes = Path(extra["caminho"]).read_bytes()
                    extras_processados.append({
                        "tipo": "imagem",
                        "conteudo": base64.standard_b64encode(img_bytes).decode(),
                        "mime_type": extra.get("mime_type", "image/jpeg"),
                        "contexto": extra.get("contexto", ""),
                    })
            except Exception as e_extra:
                import logging
                logging.getLogger("pjecalc_agent.webapp").warning(
                    f"Falha ao processar documento extra: {e_extra}"
                )

        # Fase 2: Extração
        dados = extrair_dados_sentenca(
            texto,
            sessao_id=sessao_id,
            extras=extras_processados,
            is_relatorio=is_relatorio,
            usar_gemini=usar_gemini,
        )

        # Fase 3: Classificação
        verbas_mapeadas = mapear_para_pjecalc(dados.get("verbas_deferidas", []))

        # Número do processo
        numero = dados.get("processo", {}).get("numero") or f"SESS-{sessao_id[:8]}"

        # Fase 4: Salvar no banco
        repo.criar_calculo(
            sessao_id=sessao_id,
            numero_processo=numero,
            dados=dados,
            verbas_mapeadas=verbas_mapeadas,
            arquivo_sentenca=str(caminho),
            formato_sentenca=formato,
        )

        # Fase 5: Gerar e salvar prévia
        previa_texto = gerar_previa(dados, verbas_mapeadas)
        previa_html = _previa_para_html(previa_texto)
        repo.salvar_previa(sessao_id, previa_texto, previa_html)

    except Exception as e:
        import logging
        logging.getLogger("pjecalc_agent.webapp").error(
            f"Erro no processamento da sentença [{sessao_id}]: {e}", exc_info=True
        )
        try:
            calculo = db.query(Calculo).filter_by(sessao_id=sessao_id).first()
            if calculo:
                calculo.status = "erro"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        # Remover da lista de sessões em processamento
        _sessoes_processando.pop(sessao_id, None)
        # Limpar arquivos temporários e forçar GC para liberar memória
        try:
            shutil.rmtree(caminho.parent, ignore_errors=True)
        except Exception:
            pass
        import gc
        gc.collect()


def _tarefa_automacao_pjecalc(sessao_id: str) -> None:
    """
    Tarefa de background: executa automação de interface do PJE-Calc.
    Requer que o PJE-Calc esteja aberto na máquina do servidor.
    """
    from modules.automation import PJECalcAutomation
    from modules.human_loop import GestorHITL, CategoriaSituacao
    from modules.export import finalizar_calculo, notificar_conclusao
    from config import AUTOMATION_BACKEND

    db = SessionLocal()
    try:
        repo = RepositorioCalculo(db)
        calculo_orm = repo.buscar_sessao(sessao_id)
        if not calculo_orm:
            return

        dados = calculo_orm.dados()
        verbas_mapeadas = calculo_orm.verbas_mapeadas()
        gestor = GestorHITL(sessao_id=sessao_id)

        automation = PJECalcAutomation(backend=AUTOMATION_BACKEND)

        automation.criar_novo_calculo(dados)
        automation.preencher_parametros_calculo(dados)
        automation.preencher_verbas(verbas_mapeadas)
        automation.preencher_fgts(dados.get("fgts", {}))
        automation.preencher_contribuicao_social(dados.get("contribuicao_social", {}))
        automation.preencher_imposto_renda(dados.get("imposto_renda", {}))
        automation.preencher_honorarios(dados.get("honorarios", {}))
        automation.preencher_correcao_juros(dados.get("correcao_juros", {}))

        numero = calculo_orm.processo.numero_processo if calculo_orm.processo else sessao_id[:8]
        calculo_id = numero.replace("-", "").replace(".", "")
        caminho_pjc = finalizar_calculo(automation, gestor, calculo_id, dados)

        if caminho_pjc:
            repo.marcar_exportado(sessao_id, str(caminho_pjc))

        automation.fechar()

    except Exception as e:
        import logging
        logging.getLogger("pjecalc_agent.webapp").error(
            f"Erro na automação [{sessao_id}]: {e}", exc_info=True
        )
    finally:
        db.close()


# ── Utilitários ───────────────────────────────────────────────────────────────

def _previa_para_html(previa_texto: str) -> str:
    """Converte a prévia em texto puro para HTML simples."""
    linhas_html = []
    for linha in previa_texto.split("\n"):
        # Cabeçalhos de seção
        if linha.isupper() and linha.strip() and not linha.startswith("═") and not linha.startswith("─"):
            linhas_html.append(f"<h3>{linha.strip()}</h3>")
        # Separadores
        elif linha.startswith("═") or linha.startswith("─"):
            linhas_html.append("<hr>")
        # Campos de menu
        elif linha.strip().startswith("["):
            linhas_html.append(f"<div class='menu-item'>{linha}</div>")
        # Alertas
        elif linha.strip().startswith("!") or linha.strip().startswith("→"):
            linhas_html.append(f"<div class='alerta'>{linha}</div>")
        # Verbas
        elif "REFLEXA" in linha or "NAO RECONHECIDA" in linha:
            linhas_html.append(f"<div class='verba-reflexa'>{linha}</div>")
        elif linha.strip().startswith("┌") or linha.strip().startswith("├"):
            linhas_html.append(f"<div class='verba-header'>{linha}</div>")
        elif linha.strip().startswith("│"):
            linhas_html.append(f"<div class='verba-campo'>{linha}</div>")
        # Campos
        elif ":" in linha and not linha.strip().startswith("#"):
            partes = linha.split(":", 1)
            linhas_html.append(
                f"<div class='campo'>"
                f"<span class='label'>{partes[0]}</span>"
                f"<span class='valor'>{partes[1]}</span>"
                f"</div>"
            )
        else:
            linhas_html.append(f"<p>{linha}</p>" if linha.strip() else "<br>")

    return "\n".join([
        "<div class='previa-pjecalc'>",
        *linhas_html,
        "</div>",
    ])
