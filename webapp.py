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
import os
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

# Buffer de log in-memory para diagnóstico em produção (GET /api/logs/python)
_python_log_buffer: list[str] = []
_MAX_LOG_LINES = 300

class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _python_log_buffer.append(self.format(record))
            if len(_python_log_buffer) > _MAX_LOG_LINES:
                del _python_log_buffer[:-_MAX_LOG_LINES]
        except Exception:
            pass

_buf_handler = _BufferHandler()
_buf_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.getLogger().addHandler(_buf_handler)

import time as _time
from config import OUTPUT_DIR, CLOUD_MODE, PJECALC_DIR, PJECALC_LOCAL_URL, PJECALC_TOMCAT_TIMEOUT

# ── Learning Engine (opcional — não bloqueia se módulo ausente) ───────────────
try:
    from learning.correction_tracker import CorrectionTracker
    from learning.rule_injector import RuleInjector
    _LEARNING_AVAILABLE = True
except ImportError:
    _LEARNING_AVAILABLE = False

# Sessões em processamento (em memória) — evita 404 enquanto background task roda
_sessoes_processando: dict[str, float] = {}  # sessao_id → timestamp de início
# Lock de automação — impede execuções paralelas para o mesmo sessao_id
_sessoes_automacao: set[str] = set()
from database import (
    Calculo, Processo, RepositorioCalculo, SessionLocal, get_db,
)
from modules.ingestion import ler_documento
from modules.extraction import extrair_dados_sentenca, extrair_dados_sentenca_pdf
from modules.classification import mapear_para_pjecalc
from modules.parametrizacao import gerar_parametrizacao
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
        "alertas": calculo.dados().get("alertas", []),
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
            "cloud_mode": CLOUD_MODE,
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

    try:
        # Capturar valor anterior para rastreamento de aprendizado
        valor_antes = _get_campo_valor(dados, campo)

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

        # Só sincroniza verbas (delete-all + re-insert) quando o campo editado é de verba.
        # Evita timeout no Railway causado por operação cara em todo edit de honorários/parâmetros.
        _verbas_mudaram = campo.startswith("verba")
        repo.atualizar_dados(sessao_id, dados, verbas_mapeadas if _verbas_mudaram else None)
        repo.salvar_previa(sessao_id, nova_previa, nova_previa_html)

        # Registrar correção para aprendizado contínuo
        if _LEARNING_AVAILABLE:
            try:
                secao = campo.split(".")[0] if "." in campo else campo
                confianca_ia = dados.get(secao, {}).get("confianca") if isinstance(dados.get(secao), dict) else None
                tracker = CorrectionTracker(db)
                tracker.record_field_correction(
                    sessao_id=sessao_id,
                    campo=campo,
                    valor_antes=valor_antes,
                    valor_depois=valor,
                    confianca_ia=confianca_ia,
                    contexto={"processo": dados.get("processo", {}).get("numero")},
                )
            except Exception as _e:
                logger.warning(f"learning_record_failed: {_e}")

        return JSONResponse({
            "sucesso": True,
            "campo": campo,
            "valor": valor,
            "previa_atualizada": nova_previa,
        })
    except Exception as exc:
        import logging, traceback
        logging.error("Erro ao editar campo '%s': %s\n%s", campo, exc, traceback.format_exc())
        return JSONResponse(
            {"sucesso": False, "erro": str(exc), "campo": campo},
            status_code=500,
        )


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

    try:
        # Capturar valor anterior para aprendizado
        todas_verbas = (
            verbas_mapeadas.get("predefinidas", []) + verbas_mapeadas.get("personalizadas", [])
        )
        verba_atual = todas_verbas[indice] if 0 <= indice < len(todas_verbas) else {}
        valor_antes = verba_atual.get(campo)
        verba_nome = verba_atual.get("nome_sentenca") or verba_atual.get("nome_pjecalc", "")

        verbas_mapeadas = aplicar_edicao_verba(verbas_mapeadas, indice, campo, valor)

        nova_previa = gerar_previa(dados, verbas_mapeadas)
        repo.atualizar_dados(sessao_id, dados, verbas_mapeadas)
        repo.salvar_previa(sessao_id, nova_previa, _previa_para_html(nova_previa))

        # Registrar correção de verba para aprendizado contínuo
        if _LEARNING_AVAILABLE:
            try:
                tracker = CorrectionTracker(db)
                tracker.record_verba_correction(
                    sessao_id=sessao_id,
                    verba_index=indice,
                    campo=campo,
                    valor_antes=valor_antes,
                    valor_depois=valor,
                    verba_nome=verba_nome,
                    confianca_ia=verba_atual.get("confidence"),
                )
            except Exception as _e:
                logger.warning(f"learning_verba_record_failed: {_e}")

        return JSONResponse({"sucesso": True, "indice": indice, "campo": campo, "valor": valor})
    except Exception as exc:
        import logging, traceback
        logging.error("Erro ao editar verba %d campo '%s': %s\n%s", indice, campo, exc, traceback.format_exc())
        return JSONResponse(
            {"sucesso": False, "erro": str(exc), "indice": indice, "campo": campo},
            status_code=500,
        )


@app.post("/previa/{sessao_id}/confirmar")
async def confirmar_previa(
    request: Request,
    sessao_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    ÚNICO portão de entrada para a automação (padrão Calc Machine).
    Valida todos os campos obrigatórios e verbas de baixa confiança ANTES de
    confirmar. A automação só é liberada com dados completos e revisados.
    Intervenção manual do usuário é permitida APENAS nesta etapa (prévia).
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # ── Validação HITL obrigatória ─────────────────────────────────────────────
    dados = calculo.dados()
    contrato = dados.get("contrato", {})
    verbas_mapeadas = calculo.verbas_mapeadas()
    todas_verbas = (
        verbas_mapeadas.get("predefinidas", [])
        + verbas_mapeadas.get("personalizadas", [])
    )

    erros: list[str] = []

    # Campos de contrato obrigatórios para o PJE-Calc calcular corretamente
    if not contrato.get("admissao"):
        erros.append("Data de admissão é obrigatória.")
    if not contrato.get("demissao"):
        erros.append("Data de rescisão (demissão) é obrigatória.")
    if not contrato.get("tipo_rescisao"):
        erros.append("Tipo de rescisão é obrigatório.")

    # Pelo menos uma verba deve estar presente
    if not todas_verbas:
        erros.append("Nenhuma verba encontrada — revise a sentença antes de confirmar.")

    # Verbas com confiança abaixo de 0.7 precisam ser corrigidas antes da automação
    verbas_baixa_confianca = [
        v.get("nome_sentenca") or v.get("nome_pjecalc", "?")
        for v in todas_verbas
        if v.get("confidence", 1.0) < 0.7
    ]
    if verbas_baixa_confianca:
        erros.append(
            f"Corrija as verbas com baixa confiança antes de confirmar: "
            f"{', '.join(verbas_baixa_confianca)}"
        )

    if erros:
        return JSONResponse(
            {
                "sucesso": False,
                "erros": erros,
                "mensagem": (
                    "Dados incompletos ou com baixa confiança. "
                    "Corrija os campos indicados na prévia antes de confirmar."
                ),
            },
            status_code=422,
        )

    # ── Campos validados — confirmar e prosseguir ─────────────────────────────
    repo.confirmar_previa(sessao_id)

    # .pjc gerado sob demanda via /download/{sessao_id}/pjc (lazy generation)
    # Não gerar aqui — evita OOM no Railway durante o request HTTP de confirmação.
    url_pjc = f"/download/{sessao_id}/pjc"

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


@app.post("/previa/{sessao_id}/aceitar-e-executar")
async def aceitar_e_executar(
    request: Request,
    sessao_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Confirma prévia + redireciona para instrucoes com autostart=true.

    Atalho que combina confirmação + início imediato da automação.
    Reutiliza a validação de confirmar_previa().
    """
    # Reusa a lógica de validação de confirmar_previa
    result = await confirmar_previa(request, sessao_id, background_tasks, db)
    data = json.loads(result.body.decode())

    if not data.get("sucesso"):
        return result

    # Redireciona para instrucoes com autostart
    return JSONResponse({
        **data,
        "url_instrucoes": f"/instrucoes/{sessao_id}?autostart=true",
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
        f"{PJECALC_LOCAL_URL}/pages/principal.jsf"
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


# ── Endpoints de automação (SSE CalcMachine) ──────────────────────────────────

@app.get("/api/verificar_pjecalc")
async def verificar_pjecalc():
    """Verifica se o PJE-Calc está respondendo (apenas checagem, sem iniciar)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(PJECALC_LOCAL_URL)
            if r.status_code in (200, 302, 404):
                return {"disponivel": True, "status": "ok", "codigo_http": r.status_code}
            return {"disponivel": False, "status": "erro", "codigo_http": r.status_code}
    except Exception as e:
        return {"disponivel": False, "status": "indisponivel", "detalhe": str(e)}


_pjecalc_iniciando: bool = False  # flag global simples para evitar duplo start


@app.post("/api/iniciar_pjecalc")
async def iniciar_pjecalc_endpoint(background_tasks: BackgroundTasks):
    """
    Inicia o PJE-Calc Cidadão em background (sem bloquear a resposta HTTP).
    Retorna imediatamente; o cliente deve chamar /api/verificar_pjecalc para
    acompanhar quando estiver pronto.
    """
    global _pjecalc_iniciando
    import httpx
    # Checar se já está rodando
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(PJECALC_LOCAL_URL)
            if r.status_code in (200, 302, 404):
                return {"status": "ja_rodando", "msg": "PJE-Calc já está disponível."}
    except Exception:
        pass

    if _pjecalc_iniciando:
        return {"status": "iniciando", "msg": "PJE-Calc já está sendo iniciado, aguarde."}

    _pjecalc_iniciando = True

    def _start():
        global _pjecalc_iniciando
        try:
            from modules.playwright_pjecalc import iniciar_pjecalc
            iniciar_pjecalc(PJECALC_DIR, timeout=180, log_cb=None)
        except Exception as exc:
            logger.warning(f"iniciar_pjecalc em background: {exc}")
        finally:
            _pjecalc_iniciando = False

    background_tasks.add_task(_start)
    return {
        "status": "iniciando",
        "msg": f"PJE-Calc sendo iniciado a partir de {PJECALC_DIR}. "
               "Aguarde ~30s e clique em Verificar.",
    }


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
    # Candidatos: Docker (/opt/pjecalc/java.log) ou local macOS (pjecalc-dist/pjecalc.log)
    candidatos = [
        Path("/opt/pjecalc/java.log"),
        Path(__file__).parent / "pjecalc-dist" / "pjecalc.log",
    ]
    log = next((p for p in candidatos if p.exists()), None)
    if log is None:
        return {"log": "(java.log não existe — processo Java ainda não iniciou ou não está redirecionando saída)"}
    try:
        result = subprocess.run(["tail", f"-{linhas}", str(log)],
                                capture_output=True, timeout=5)
        texto = result.stdout.decode("iso-8859-1", errors="replace")
        return {"log": texto or "(vazio)"}
    except Exception as e:
        return {"log": f"Erro: {e}"}


@app.get("/api/logs/python")
async def logs_python(linhas: int = 100):
    """Últimos N logs do processo uvicorn/Python (exceções, erros, warnings)."""
    return {"log": "\n".join(_python_log_buffer[-linhas:]) or "(sem logs registrados ainda)"}


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

    from fastapi.responses import StreamingResponse as _SR

    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Fix 5: Check 6 — impedir execuções paralelas para o mesmo sessao_id
    if sessao_id in _sessoes_automacao:
        async def _lock_sse():
            yield "data: ERRO_EXPORTAVEL::Automação já em andamento para esta sessão. Aguarde o término.\n\n"
            yield "data: [FIM DA EXECUÇÃO]\n\n"
        return _SR(_lock_sse(), media_type="text/event-stream",
                   headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()

    # Fix 4: validação dos dados antes de iniciar automação
    from modules.extraction import ValidadorSentenca
    _resultado_val = ValidadorSentenca(dados).validar()
    if not _resultado_val.valido:
        _erros_str = "; ".join(_resultado_val.erros[:3])
        async def _val_sse():
            yield f"data: ERRO_EXPORTAVEL::Dados inválidos — {_erros_str}\n\n"
            yield "data: [FIM DA EXECUÇÃO]\n\n"
        return _SR(_val_sse(), media_type="text/event-stream",
                   headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Fix 6: validação CNJ módulo 97 (aviso não bloqueante)
    def _validar_cnj(numero: str, digito: str, ano: str, regiao: str, vara: str) -> bool:
        try:
            num = numero + ano + "5" + regiao + vara + "00"
            resto = int(num) % 97
            return int(digito) == (97 - resto)
        except Exception:
            return True
    _processo = dados.get("processo", {})
    _cnj_aviso = None
    if all(_processo.get(c) for c in ["numero_seq", "digito_verificador", "ano", "regiao", "vara"]):
        if not _validar_cnj(
            str(_processo["numero_seq"]), str(_processo.get("digito_verificador", "")),
            str(_processo["ano"]), str(_processo["regiao"]), str(_processo["vara"])
        ):
            _cnj_aviso = "CNJ: dígito verificador inválido — verifique o número do processo"

    async def gerador_sse():
        import httpx
        from modules.playwright_pjecalc import preencher_como_generator
        from database import SessionLocal

        # Fix 5: registrar lock de automação — liberado no finally
        _sessoes_automacao.add(sessao_id)

        # Fix 6: emitir aviso CNJ se inválido
        if _cnj_aviso:
            yield f"data: {json.dumps({'msg': f'⚠ {_cnj_aviso}'})}\n\n"

        # ── Persistência por processo ──────────────────────────────
        _exec_dir = None
        _log_acumulado: list[str] = []
        _persist_enabled = os.environ.get("CALCULATION_PERSISTENCE", "true").lower() == "true"
        if _persist_enabled:
            try:
                from infrastructure.calculation_store import CalculationStore
                _store = CalculationStore()
                _num_proc = dados.get("processo", {}).get("numero", sessao_id)
                _exec_dir = _store.criar_execucao(_num_proc, sessao_id)
                _store.salvar_extracao_llm(_exec_dir, dados)
                _store.salvar_parametros_enviados(_exec_dir, verbas_mapeadas)
                _store.salvar_metadados(_exec_dir, {**dados, "_status": "automacao_iniciada"})
                # Salvar referência no banco
                db3 = SessionLocal()
                try:
                    _calc = RepositorioCalculo(db3).buscar_sessao(sessao_id)
                    if _calc:
                        _calc.diretorio_calculo = str(_exec_dir)
                        db3.commit()
                finally:
                    db3.close()
            except Exception as _e:
                logger.warning(f"calculation_store_init_failed: {_e}")
                _exec_dir = None

        # Aguardar PJE-Calc ficar disponível.
        _tomcat_timeout = PJECALC_TOMCAT_TIMEOUT
        _pjecalc_url = PJECALC_LOCAL_URL
        elapsed = 0
        _ultimo_status_log = -30
        while elapsed < _tomcat_timeout:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(_pjecalc_url)
                    if r.status_code in (200, 302):
                        yield f"data: {json.dumps({'msg': f'PJE-Calc pronto (HTTP {r.status_code}) — iniciando Playwright…'})}\n\n"
                        break
                    if r.status_code == 404:
                        if elapsed - _ultimo_status_log >= 30:
                            yield f"data: {json.dumps({'msg': f'Tomcat ativo — aguardando deploy da webapp… ({elapsed}s)'})}\n\n"
                            _ultimo_status_log = elapsed
            except Exception:
                if elapsed - _ultimo_status_log >= 30:
                    yield f"data: {json.dumps({'msg': f'Aguardando PJE-Calc… ({elapsed}s/{_tomcat_timeout}s)'})}\n\n"
                    _ultimo_status_log = elapsed
            await asyncio.sleep(10)
            elapsed += 10
        else:
            _msg_erro = (
                f"ERRO: PJE-Calc não respondeu em {_pjecalc_url} após {_tomcat_timeout}s. "
            )
            if _tomcat_timeout <= 60:
                _msg_erro += "Abra o PJE-Calc Cidadão e aguarde carregar antes de iniciar a automação."
            else:
                _msg_erro += "Verifique /api/logs/java para diagnóstico."
            yield f"data: {json.dumps({'msg': _msg_erro})}\n\n"
            yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
            return

        import queue as _queue

        loop = asyncio.get_event_loop()
        parametrizacao_sse = dados.get("_parametrizacao") or {}
        gen = preencher_como_generator(
            dados, verbas_mapeadas, PJECALC_DIR, modo_oculto,
            parametrizacao=parametrizacao_sse,
            exec_dir=_exec_dir,
        )

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
                    None, lambda: fila.get(timeout=15)
                )
            except _queue.Empty:
                # SSE comment keepalive — mantém conexão HTTP viva sem disparar onmessage
                yield ": keepalive\n\n"
                continue

            if kind == "ok":
                msg = value
                _log_acumulado.append(msg)
                yield f"data: {json.dumps({'msg': msg})}\n\n"

                # Parse PROGRESS messages para barra de progresso
                if msg.startswith("PROGRESS:"):
                    try:
                        parts = msg.split(":")[1].split("/")
                        yield f"data: {json.dumps({'type': 'progress', 'current': int(parts[0]), 'total': int(parts[1])})}\n\n"
                    except (IndexError, ValueError):
                        pass

                # Detectar .PJC gerado e persistir
                if msg.startswith("PJC_GERADO:"):
                    caminho = msg.split(":", 1)[1].strip()
                    db2 = SessionLocal()
                    try:
                        RepositorioCalculo(db2).marcar_exportado(sessao_id, caminho)
                        db2.commit()
                    finally:
                        db2.close()
                    # Copiar PJC para diretório de persistência
                    if _exec_dir and _persist_enabled:
                        try:
                            from infrastructure.calculation_store import CalculationStore
                            CalculationStore().copiar_pjc(_exec_dir, caminho)
                            CalculationStore().atualizar_status(_exec_dir, "pjc_exportado")
                        except Exception:
                            pass
                    # Fix 7: protocolo SSE CalcMACHINE
                    yield f"data: DOWNLOAD_LINK_CALC:/download/{sessao_id}/pjc\n\n"
                if msg == "[FIM DA EXECUÇÃO]":
                    break
            elif kind == "fim":
                yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
                break
            elif kind == "erro":
                # Fix 7: usar ERRO_EXPORTAVEL para erros com contexto
                yield f"data: ERRO_EXPORTAVEL::Automação: {value}\n\n"
                _log_acumulado.append(f"ERRO: {value}")
                yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
                break

        # Salvar log acumulado no diretório de persistência
        if _exec_dir and _persist_enabled and _log_acumulado:
            try:
                from infrastructure.calculation_store import CalculationStore
                CalculationStore().salvar_log(_exec_dir, _log_acumulado)
            except Exception:
                pass

        # Fix 5: liberar lock de automação
        _sessoes_automacao.discard(sessao_id)

    return StreamingResponse(
        gerador_sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _get_campo_valor(dados: dict, campo: str) -> Any:
    """Retorna o valor atual de um campo pelo dotted path (ex: 'contrato.admissao')."""
    partes = campo.split(".", 1)
    if len(partes) == 1:
        return dados.get(campo)
    secao, resto = partes
    sub = dados.get(secao)
    if isinstance(sub, dict):
        return _get_campo_valor(sub, resto)
    return None


# ── Learning Dashboard ────────────────────────────────────────────────────────

@app.get("/admin/aprendizado", response_class=HTMLResponse)
async def admin_aprendizado(request: Request, db: Session = Depends(get_db)):
    """Dashboard de aprendizado: sessões e regras ativas."""
    if not _LEARNING_AVAILABLE:
        return HTMLResponse("<h1>Módulo de aprendizado não disponível</h1>", status_code=503)

    try:
        from infrastructure.database import SessaoAprendizado, RegrasAprendidas
        sessoes = (
            db.query(SessaoAprendizado)
            .order_by(SessaoAprendizado.iniciada_em.desc())
            .limit(20)
            .all()
        )
        regras = (
            db.query(RegrasAprendidas)
            .filter(RegrasAprendidas.ativa == True)
            .order_by(RegrasAprendidas.confianca.desc())
            .all()
        )
        tracker = CorrectionTracker(db)
        correcoes_pendentes = tracker.get_unincorporated_count()
    except Exception as exc:
        return HTMLResponse(f"<h1>Erro ao carregar aprendizado: {exc}</h1>", status_code=500)

    return templates.TemplateResponse(
        request, "aprendizado.html",
        {
            "sessoes": sessoes,
            "regras": regras,
            "correcoes_pendentes": correcoes_pendentes,
        },
    )


@app.post("/api/aprendizado/executar")
async def executar_aprendizado(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Dispara uma sessão de aprendizado manualmente."""
    if not _LEARNING_AVAILABLE:
        raise HTTPException(status_code=503, detail="Módulo de aprendizado não disponível")

    tracker = CorrectionTracker(db)
    count = tracker.get_unincorporated_count()
    background_tasks.add_task(_executar_sessao_aprendizado)

    return JSONResponse({
        "iniciado": True,
        "correcoes_pendentes": count,
        "mensagem": f"Sessão de aprendizado iniciada com {count} correção(ões) pendente(s).",
    })


@app.get("/api/aprendizado/status")
async def status_aprendizado(db: Session = Depends(get_db)):
    """Retorna contagem de correções pendentes e threshold para UI do painel."""
    if not _LEARNING_AVAILABLE:
        return JSONResponse({"pendentes": 0, "threshold": 10})
    try:
        from infrastructure.config import settings
        threshold = settings.learning_feedback_threshold
    except Exception:
        threshold = 10
    try:
        tracker = CorrectionTracker(db)
        pendentes = tracker.get_unincorporated_count()
    except Exception:
        pendentes = 0
    return JSONResponse({"pendentes": pendentes, "threshold": threshold})


@app.delete("/api/aprendizado/regra/{rule_id}")
async def desativar_regra(rule_id: int, db: Session = Depends(get_db)):
    """Desativa uma regra aprendida."""
    if not _LEARNING_AVAILABLE:
        raise HTTPException(status_code=503, detail="Módulo de aprendizado não disponível")

    injector = RuleInjector(db)
    ok = injector.deactivate_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return JSONResponse({"desativada": True, "rule_id": rule_id})


# ── Tarefas em Background ─────────────────────────────────────────────────────

def _executar_sessao_aprendizado() -> None:
    """Tarefa background: executa uma sessão de aprendizado via LearningEngine."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        from learning.learning_engine import LearningEngine
        from core.llm_orchestrator import LLMOrchestrator
        from infrastructure.config import settings
        orchestrator = LLMOrchestrator(settings)
        engine = LearningEngine(db, orchestrator)
        session = engine.run_learning_session()
        logger.info(
            "learning_session_completed_background",
            session_id=getattr(session, "id", None),
            new_rules=getattr(session, "num_regras_geradas", 0),
        )
    except Exception as exc:
        logger.error(f"Sessão de aprendizado em background falhou: {exc}", exc_info=True)
    finally:
        db.close()


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

        # Fase 2: Extração — PDF nativo (sem conversão para texto) ou fallback via texto
        if formato == "pdf" and not is_relatorio:
            # Envia o PDF diretamente ao Claude via base64 (mais rápido e preciso)
            dados = extrair_dados_sentenca_pdf(
                str(caminho),
                sessao_id=sessao_id,
                extras=extras_processados,
            )
            # Se Claude falhou e usuário escolheu Gemini, extrair texto e tentar via Gemini
            if (dados.get("_erro_llm") or dados.get("_erro_ia")) and usar_gemini:
                resultado_txt = ler_documento(caminho)
                dados = extrair_dados_sentenca(
                    resultado_txt["texto"],
                    sessao_id=sessao_id,
                    extras=extras_processados,
                    usar_gemini=True,
                )
        else:
            # DOCX, TXT ou relatório estruturado: extrai texto primeiro
            resultado = ler_documento(caminho)
            texto = resultado["texto"]
            dados = extrair_dados_sentenca(
                texto,
                sessao_id=sessao_id,
                extras=extras_processados,
                is_relatorio=is_relatorio,
                usar_gemini=usar_gemini,
            )

        # Fase 2b: IA bloqueada → salvar calculo com status erro_ia e encerrar
        if dados.get("_erro_ia"):
            numero = f"SESS-{sessao_id[:8]}"
            repo.criar_calculo(
                sessao_id=sessao_id,
                numero_processo=numero,
                dados=dados,
                verbas_mapeadas={},
            )
            calculo = db.query(Calculo).filter_by(sessao_id=sessao_id).first()
            if calculo:
                calculo.status = "erro_ia"
                db.commit()
            logger.error(f"Sessão {sessao_id}: IA indisponível — processamento encerrado")
            return

        # Fase 2c: Parametrização — converte dados brutos → instruções módulo a módulo
        try:
            parametrizacao = gerar_parametrizacao(dados)
            # Propagar alertas da parametrização para os dados
            for alerta in parametrizacao.get("alertas", []):
                dados.setdefault("alertas", [])
                if alerta not in dados["alertas"]:
                    dados["alertas"].append(alerta)
        except Exception as e_param:
            import logging
            logging.getLogger("pjecalc_agent.webapp").warning(
                f"Parametrização falhou (não crítico): {e_param}"
            )
            parametrizacao = {}

        # Persistir parametrização incorporando em dados (salvo via dados_json)
        if parametrizacao:
            dados["_parametrizacao"] = parametrizacao

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
