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
import re
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
# Agora com timestamp para auto-expiração (evita lock travado por crash)
_sessoes_automacao: dict[str, float] = {}  # sessao_id → timestamp de início
_LOCK_TIMEOUT_S = 900  # 15 minutos — automação não deve levar mais que isso
# Lock GLOBAL — apenas uma automação por vez (compartilha Firefox headless)
_automacao_global_lock: dict[str, float | str] = {}  # "ts" → timestamp, "sessao" → sessao_id

# ── Runners de automação desacoplados do SSE ──────────────────────────────────
# Cada runner vive independente da conexão SSE. Reconexões fazem "follow" do runner existente.
import threading as _threading_mod

class _AutomacaoRunner:
    """Estado compartilhado de uma automação em execução, desacoplado do SSE.
    Usa padrão position-based: logs acumulados em lista, leitores rastreiam sua posição.
    Múltiplos SSE readers podem coexistir sem consumir items uns dos outros."""
    __slots__ = ("logs", "done", "error_msg", "exec_dir", "started_at",
                 "_gen", "_thread", "_sessao_id", "_persist_enabled", "_cond")
    def __init__(self, sessao_id: str):
        self.logs: list[str] = []  # append-only — thread-safe para leitura com posição
        self._cond = _threading_mod.Condition()  # notifica readers quando há novos logs
        self.done = False
        self.error_msg: str | None = None
        self.exec_dir = None
        self.started_at = 0.0
        self._gen = None
        self._thread = None
        self._sessao_id = sessao_id
        self._persist_enabled = os.environ.get("CALCULATION_PERSISTENCE", "true").lower() == "true"

    def _append(self, msg: str):
        """Append thread-safe com notificação a todos os readers."""
        self.logs.append(msg)
        with self._cond:
            self._cond.notify_all()

    def wait_for_new(self, timeout: float = 15.0) -> bool:
        """Bloqueia até haver novos logs ou timeout. Retorna True se notificado."""
        with self._cond:
            return self._cond.wait(timeout=timeout)

    def start_thread(self, gen):
        """Inicia thread de automação que roda independente do SSE."""
        self._gen = gen
        self.started_at = __import__("time").time()

        def _run():
            try:
                while True:
                    try:
                        msg = next(self._gen)
                        self._append(msg)
                        if msg == "[FIM DA EXECUÇÃO]":
                            break
                    except StopIteration:
                        self._append("[FIM DA EXECUÇÃO]")
                        break
            except Exception as exc:
                self.error_msg = str(exc)
                self._append(f"ERRO: {exc}")
                self._append("[FIM DA EXECUÇÃO]")
            finally:
                self.done = True
                with self._cond:
                    self._cond.notify_all()
                self._cleanup()

        self._thread = _threading_mod.Thread(target=_run, daemon=True)
        self._thread.start()

    def _cleanup(self):
        """Cleanup pós-automação: libera locks, salva logs, atualiza DB."""
        import time as _t
        sid = self._sessao_id
        logger.info(f"Runner cleanup [{sid}]")

        # Salvar log acumulado
        if self.exec_dir and self._persist_enabled and self.logs:
            try:
                from infrastructure.calculation_store import CalculationStore
                CalculationStore().salvar_log(self.exec_dir, self.logs)
            except Exception:
                pass

        # Liberar locks
        _sessoes_automacao.pop(sid, None)
        _automacao_global_lock.clear()

        # Atualizar status no DB
        _db = SessionLocal()
        try:
            _calc = RepositorioCalculo(_db).buscar_sessao(sid)
            if _calc and _calc.status == "em_automacao":
                # Extrair caminho do .PJC se foi gerado (última ocorrência vence)
                _pjc_path: str | None = None
                for _m in self.logs:
                    if _m.startswith("PJC_GERADO:"):
                        _pjc_path = _m.split(":", 1)[1].strip()
                _has_error = any("ERRO" in m.upper() for m in self.logs[-5:])
                if _pjc_path:
                    # Fix: grava status E arquivo_pjc atomicamente via marcar_exportado.
                    # Antes, _cleanup só setava status — se SSE desconectasse antes do
                    # handler inline processar PJC_GERADO (webapp.py:1666), o campo
                    # arquivo_pjc ficava NULL e o endpoint /download/{sid}/pjc → 404.
                    RepositorioCalculo(_db).marcar_exportado(sid, _pjc_path)
                else:
                    _calc.status = "erro_automacao" if _has_error else "concluido"
                    _db.commit()
        except Exception as _exc:
            logger.warning(f"_cleanup DB update falhou [{sid}]: {_exc}")
        finally:
            _db.close()

    def stop(self):
        """Para a automação forçadamente (chamado pelo endpoint /api/parar)."""
        if self.done:
            return
        logger.info(f"Runner stop solicitado [{self._sessao_id}]")
        if self._gen:
            try:
                self._gen.close()  # dispara GeneratorExit → fecha browser
            except Exception:
                pass
        # Se gen.close() não setou done, forçar
        if not self.done:
            self._append("⏹ Automação interrompida pelo usuário.")
            self._append("[FIM DA EXECUÇÃO]")

_automacao_runners: dict[str, _AutomacaoRunner] = {}  # sessao_id → runner

def _limpar_runners_antigos():
    """Remove runners finalizados há mais de 5 minutos."""
    import time
    _limite = time.time() - 300
    _remover = [sid for sid, r in _automacao_runners.items()
                if r.done and r.started_at < _limite]
    for sid in _remover:
        _automacao_runners.pop(sid, None)
    if _remover:
        logger.info(f"Runners limpos: {_remover}")
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


# ── Startup: criar tabelas DB ─────────────────────────────────────────────────

@app.on_event("startup")
def _startup_criar_tabelas():
    """Cria tabelas no banco na inicialização do app (não mais em import time)."""
    try:
        from database import criar_tabelas
        criar_tabelas()
        logger.info("Tabelas do banco criadas/verificadas com sucesso")
    except Exception as e:
        logger.error(f"Falha ao criar tabelas: {e} — app continuará, mas DB pode falhar")


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

    # Nomes canônicos do Expresso para datalist de validação no front.
    # Fonte única de verdade: knowledge/catalogo_verbas_pjecalc.json.
    try:
        from learning.verba_strategies import _carregar_catalogo
        _catalogo = _carregar_catalogo()
        _expresso_nomes = [v.get("nome_pjecalc", "") for v in _catalogo.get("expresso", [])]
    except Exception:
        _expresso_nomes = []

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
            "expresso_nomes": _expresso_nomes,
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

        # Validações server-side PJE-Calc: corrige automaticamente combinações
        # inválidas (ex: prescrição quinquenal com contrato < 5 anos). O alerta
        # é incluído na resposta para que o frontend mostre ao usuário.
        _alertas_pjecalc = []
        try:
            from modules.pjecalc_validators import aplicar_validacoes_pjecalc
            _alertas_antes = list(dados.get("_alertas_validacao") or [])
            dados = aplicar_validacoes_pjecalc(dados)
            _alertas_pjecalc = [
                a for a in (dados.get("_alertas_validacao") or [])
                if a not in _alertas_antes
            ]
        except Exception as _ve:
            logger.debug(f"Validações PJE-Calc não aplicadas: {_ve}")

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
            "alertas_pjecalc": _alertas_pjecalc,
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


@app.post("/previa/{sessao_id}/adicionar-verba")
async def adicionar_verba(
    sessao_id: str,
    estrategia: str = Form(...),  # "expresso_direto" | "expresso_adaptado" | "manual"
    nome_pjecalc: str = Form(...),
    nome_sentenca: str = Form(""),
    caracteristica: str = Form("Comum"),  # Comum | 13o Salario | Aviso Previo | Ferias
    ocorrencia: str = Form("Mensal"),     # Mensal | Dezembro | Periodo Aquisitivo | Desligamento
    base_calculo: str = Form("Historico Salarial"),
    percentual: str = Form(""),
    valor_informado: str = Form(""),
    incidencia_fgts: str = Form("true"),
    incidencia_inss: str = Form("true"),
    incidencia_ir: str = Form("true"),
    tipo: str = Form("Principal"),       # Principal | Reflexa
    verba_principal_ref: str = Form(""),  # nome da verba principal (se Reflexa)
    db: Session = Depends(get_db),
):
    """
    Adiciona uma nova verba à prévia. Suporta 3 estratégias:

    - **expresso_direto**: verba existe na tabela Expresso do PJE-Calc.
      Adicionada em verbas_mapeadas['predefinidas'] com mapeada=True.

    - **expresso_adaptado**: usa Expresso como base mas customiza nome/parâmetros.
      Adicionada em ['personalizadas'] com estrategia_preenchimento.tipo='expresso_adaptado'.

    - **manual**: criada via botão Manual no PJE-Calc, todos os campos editáveis.
      Adicionada em ['personalizadas'] com estrategia_preenchimento.tipo='manual'.

    Após inserção, aplica validações server-side (pjecalc_validators) e
    regenera a prévia.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    if estrategia not in ("expresso_direto", "expresso_adaptado", "manual"):
        return JSONResponse(
            {"sucesso": False, "erro": f"estrategia inválida: {estrategia}"},
            status_code=400,
        )

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()

    try:
        def _to_bool(s: str) -> bool:
            return str(s).strip().lower() in ("true", "1", "yes", "sim")

        def _to_float(s: str):
            try:
                return float(str(s).replace(",", ".").strip()) if s else None
            except Exception:
                return None

        # Construir verba completa
        nova_verba = {
            "nome_sentenca": nome_sentenca or nome_pjecalc,
            "nome_pjecalc": nome_pjecalc,
            "tipo": tipo,
            "caracteristica": caracteristica,
            "ocorrencia": ocorrencia,
            "base_calculo": base_calculo,
            "percentual": _to_float(percentual),
            "valor_informado": _to_float(valor_informado),
            "incidencia_fgts": _to_bool(incidencia_fgts),
            "incidencia_inss": _to_bool(incidencia_inss),
            "incidencia_ir": _to_bool(incidencia_ir),
            "verba_principal_ref": verba_principal_ref or None,
            "confianca": 1.0,  # adicionada manualmente pelo usuário → confiança máxima
            "mapeada": estrategia == "expresso_direto",
            "estrategia_preenchimento": {
                "tipo_verba": tipo,
                "tipo": estrategia,
                "baseado_em": "usuario",
                "verba_principal_ref": verba_principal_ref or None,
            },
        }

        # Categorizar pela estratégia
        if estrategia == "expresso_direto":
            verbas_mapeadas.setdefault("predefinidas", []).append(nova_verba)
        else:
            verbas_mapeadas.setdefault("personalizadas", []).append(nova_verba)

        # Aplicar validações server-side PJE-Calc (defesa em profundidade)
        try:
            from modules.pjecalc_validators import aplicar_validacoes_pjecalc
            dados = aplicar_validacoes_pjecalc(dados)
        except Exception as _ve:
            logger.debug(f"Validações PJE-Calc não aplicadas: {_ve}")

        # Regerar prévia + persistir
        nova_previa = gerar_previa(dados, verbas_mapeadas)
        repo.atualizar_dados(sessao_id, dados, verbas_mapeadas)
        repo.salvar_previa(sessao_id, nova_previa, _previa_para_html(nova_previa))

        # Rastreabilidade
        repo.registrar_rastreabilidade(sessao_id, {
            "campo_pjecalc": f"verba.adicionada.{estrategia}",
            "valor": nome_pjecalc,
            "fonte": "USUARIO",
            "confirmado_usuario": True,
            "pergunta_formulada": f"Usuário adicionou verba '{nome_pjecalc}' via estratégia '{estrategia}'",
            "resposta_usuario": nome_pjecalc,
        })

        return JSONResponse({
            "sucesso": True,
            "estrategia": estrategia,
            "nome_pjecalc": nome_pjecalc,
            "indice": (
                len(verbas_mapeadas.get("predefinidas", [])) - 1
                if estrategia == "expresso_direto"
                else None
            ),
        })
    except Exception as exc:
        import traceback
        logger.error(
            "Erro ao adicionar verba '%s' (%s): %s\n%s",
            nome_pjecalc, estrategia, exc, traceback.format_exc()
        )
        return JSONResponse(
            {"sucesso": False, "erro": str(exc)},
            status_code=500,
        )


@app.post("/previa/{sessao_id}/editar-estrategia")
async def editar_estrategia(
    sessao_id: str,
    indice: int = Form(...),
    campo: str = Form(...),
    valor: str = Form(...),
    db: Session = Depends(get_db),
):
    """Edita a estratégia de preenchimento de uma verba específica pelo índice.

    Campos editáveis:
    - estrategia: "expresso_direto" | "expresso_adaptado" | "manual"
    - nome_pjecalc: nome da verba no PJE-Calc
    - expresso_base: verba Expresso base (para adaptado)
    - parametros.caracteristica: Comum, 13o Salario, Aviso Previo, Ferias
    - parametros.ocorrencia: Mensal, Dezembro, Periodo Aquisitivo, Desligamento
    - parametros.base_calculo: livre
    - parametros.tipo_valor: CALCULADO, INFORMADO
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")

    verbas_mapeadas = calculo.verbas_mapeadas()
    todas_verbas = (
        verbas_mapeadas.get("predefinidas", [])
        + verbas_mapeadas.get("personalizadas", [])
    )

    if indice < 0 or indice >= len(todas_verbas):
        return JSONResponse(
            {"sucesso": False, "erro": f"Indice {indice} fora do intervalo (0-{len(todas_verbas)-1})"},
            status_code=400,
        )

    verba = todas_verbas[indice]
    estrategia_atual = verba.get("estrategia_preenchimento", {})

    # Capturar valor anterior para learning
    if campo == "estrategia":
        valor_antes = estrategia_atual.get("estrategia", "")
    elif campo.startswith("parametros."):
        sub_campo = campo.split(".", 1)[1]
        valor_antes = estrategia_atual.get("parametros", {}).get(sub_campo, "")
    else:
        valor_antes = estrategia_atual.get(campo, "")

    # Aplicar edição
    if not estrategia_atual:
        estrategia_atual = {
            "estrategia": "manual",
            "nome_pjecalc": verba.get("nome_pjecalc", ""),
            "confianca": 0.5,
            "baseado_em": "usuario",
            "parametros": {},
            "incidencias": {},
        }

    if campo == "estrategia":
        estrategia_atual["estrategia"] = valor
        estrategia_atual["baseado_em"] = "usuario"
    elif campo == "tipo_verba":
        # Sincronizar tipo da verba: salva na estratégia E no nível da verba
        estrategia_atual["tipo_verba"] = valor
        verba["tipo"] = valor  # Sincroniza com campo 'tipo' da verba (Seção 14)
        estrategia_atual["baseado_em"] = "usuario"
    elif campo == "verba_principal_ref":
        # Salvar referência à parcela principal (para reflexas)
        estrategia_atual["verba_principal_ref"] = valor
        verba["verba_principal_ref"] = valor  # Sincroniza com campo da verba
        estrategia_atual["baseado_em"] = "usuario"
    elif campo.startswith("parametros."):
        sub_campo = campo.split(".", 1)[1]
        estrategia_atual.setdefault("parametros", {})[sub_campo] = valor
        estrategia_atual["baseado_em"] = "usuario"
    else:
        estrategia_atual[campo] = valor
        estrategia_atual["baseado_em"] = "usuario"

    # Marcar confiança como 1.0 para edições do usuário
    estrategia_atual["confianca"] = 1.0
    verba["estrategia_preenchimento"] = estrategia_atual

    # Atualizar a verba na lista correta
    n_pred = len(verbas_mapeadas.get("predefinidas", []))
    if indice < n_pred:
        verbas_mapeadas["predefinidas"][indice] = verba
    else:
        verbas_mapeadas["personalizadas"][indice - n_pred] = verba

    # Persistir
    dados = calculo.dados()
    repo.atualizar_dados(sessao_id, dados, verbas_mapeadas)

    # Registrar correção para learning engine
    if _LEARNING_AVAILABLE:
        try:
            verba_nome = verba.get("nome_sentenca") or verba.get("nome_pjecalc", "")
            tracker = CorrectionTracker(db)
            tracker.record_verba_correction(
                sessao_id=sessao_id,
                verba_index=indice,
                campo=f"estrategia_preenchimento.{campo}",
                valor_antes=valor_antes,
                valor_depois=valor,
                verba_nome=verba_nome,
                confianca_ia=estrategia_atual.get("confianca"),
            )
        except Exception as _e:
            logger.warning(f"learning_estrategia_record_failed: {_e}")

    # Salvar na tabela EstrategiaVerba para aprendizado futuro
    # Quando o usuário muda a estratégia, o sistema aprende e usa
    # essa escolha para verbas similares em cálculos futuros.
    try:
        from infrastructure.database import EstrategiaVerba
        import unicodedata
        _nome_verba = verba.get("nome_sentenca") or verba.get("nome_pjecalc", "")
        _nome_norm = unicodedata.normalize("NFD", _nome_verba.lower())
        _nome_norm = "".join(c for c in _nome_norm if unicodedata.category(c) != "Mn")
        _nome_norm = _nome_norm.strip()

        # Buscar registro existente ou criar novo
        _ev = db.query(EstrategiaVerba).filter(
            EstrategiaVerba.nome_normalizado == _nome_norm,
        ).first()

        if _ev:
            _ev.estrategia = estrategia_atual.get("estrategia", "manual")
            _ev.expresso_nome = estrategia_atual.get("nome_pjecalc") or estrategia_atual.get("expresso_base")
            _ev.expresso_base = estrategia_atual.get("expresso_base")
            _ev.campos_alterados = json.dumps(estrategia_atual.get("campos_alterar", {}), ensure_ascii=False)
            _ev.parametros = json.dumps(estrategia_atual.get("parametros", {}), ensure_ascii=False)
            _ev.incidencias = json.dumps(estrategia_atual.get("incidencias", {}), ensure_ascii=False)
            # Marcar como bem-sucedida (usuário definiu = sucesso garantido)
            _ev.tentativas = max(_ev.tentativas, 1)
            _ev.sucessos = max(_ev.sucessos, 1)
        else:
            _ev = EstrategiaVerba(
                nome_verba=_nome_verba,
                nome_normalizado=_nome_norm,
                tipo=verba.get("tipo", "principal").lower(),
                estrategia=estrategia_atual.get("estrategia", "manual"),
                expresso_nome=estrategia_atual.get("nome_pjecalc") or estrategia_atual.get("expresso_base"),
                expresso_base=estrategia_atual.get("expresso_base"),
                campos_alterados=json.dumps(estrategia_atual.get("campos_alterar", {}), ensure_ascii=False),
                parametros=json.dumps(estrategia_atual.get("parametros", {}), ensure_ascii=False),
                incidencias=json.dumps(estrategia_atual.get("incidencias", {}), ensure_ascii=False),
                tentativas=1,
                sucessos=1,
            )
            db.add(_ev)
        db.commit()
        logger.info(f"estrategia_aprendida verba='{_nome_verba}' estrategia={estrategia_atual.get('estrategia')}")
    except Exception as _e:
        logger.warning(f"estrategia_verba_save_failed: {_e}")

    return JSONResponse({
        "sucesso": True,
        "indice": indice,
        "campo": campo,
        "valor": valor,
        "estrategia": estrategia_atual,
    })


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
    """Download do arquivo .pjc exportado pelo PJE-Calc Cidadão.

    REGRA DE OURO: Apenas arquivos .PJC gerados pelo próprio PJE-Calc Cidadão
    (via Liquidar + Exportar na automação) são válidos. Arquivos gerados pelo
    pjc_generator.py nativo são SEMPRE rejeitados pelo PJE-Calc institucional.
    Por isso, este endpoint NÃO gera PJC sob demanda — só serve arquivos que
    já foram exportados pela automação.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Fallback defensivo: se arquivo_pjc está vazio ou aponta para path inexistente,
    # varrer data/calculations/<processo>/ e data/calculations/<CNJ_com_prefixo>/
    # procurando o .PJC mais recente. Se encontrar, auto-vincula via marcar_exportado.
    if not calculo.arquivo_pjc or not Path(calculo.arquivo_pjc).exists():
        _pjc_encontrado: Path | None = None
        _dirs_busca: list[Path] = []
        if calculo.diretorio_calculo and Path(calculo.diretorio_calculo).exists():
            _dirs_busca.append(Path(calculo.diretorio_calculo))
        # Fallback: varredura em data/calculations/ por subpastas do processo
        _calc_base = Path("data/calculations")
        _cnj = calculo.processo.numero_processo if calculo.processo else None
        if _calc_base.exists() and _cnj:
            for _proc_dir in _calc_base.iterdir():
                if _proc_dir.is_dir() and _cnj in _proc_dir.name:
                    _dirs_busca.append(_proc_dir)
        for _d in _dirs_busca:
            if not _d.exists():
                continue
            _pjcs = sorted(_d.rglob("*.PJC"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not _pjcs:
                _pjcs = sorted(_d.rglob("*.pjc"), key=lambda p: p.stat().st_mtime, reverse=True)
            if _pjcs:
                _pjc_encontrado = _pjcs[0]
                break
        if _pjc_encontrado:
            repo.marcar_exportado(sessao_id, str(_pjc_encontrado))
            db.commit()
            calculo = repo.buscar_sessao(sessao_id)  # refresh
            logger.info(f"download_pjc auto-vinculou {_pjc_encontrado} → sessão {sessao_id}")
        else:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Arquivo .PJC ainda não disponível. "
                    "O arquivo .PJC válido só é gerado após a automação completar "
                    "a liquidação no PJE-Calc Cidadão e exportar o resultado. "
                    "Execute a automação primeiro em Instruções > Executar Automação."
                ),
            )

    caminho = Path(calculo.arquivo_pjc)
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


@app.get("/api/calc_file/{numero}/{execucao}/{filename}")
async def ler_calc_file(numero: str, execucao: str, filename: str):
    """Lê um arquivo de diagnóstico dentro de data/calculations/<numero>/<execucao>/.
    Uso: GET /api/calc_file/0000829-78.2025.5.07.0003/20260411_215236/fase_e_response_dump.html
    """
    base = Path("data/calculations")
    # Bloqueia path traversal — sanitizar cada componente
    safe_numero = Path(numero).name
    safe_exec = Path(execucao).name
    safe_file = Path(filename).name
    alvo = base / safe_numero / safe_exec / safe_file
    if not alvo.exists():
        return JSONResponse(
            {"erro": f"{alvo} não encontrado", "base_exists": base.exists()},
            status_code=404,
        )
    # Retorna como texto bruto
    try:
        content = alvo.read_text(encoding="iso-8859-1")
    except Exception:
        content = alvo.read_bytes().decode("iso-8859-1", errors="replace")
    return Response(content=content, media_type="text/plain; charset=iso-8859-1")


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


# ── DOM Auditor endpoint ────────────────────────────────────────────────────
_dom_audit_running = False
_dom_audit_result: dict | None = None

@app.get("/api/dom-audit")
async def executar_dom_audit():
    """Executa o DOM Auditor no PJE-Calc local e retorna o mapa JSON.
    Se já existe um resultado recente (<1h), retorna do cache.
    """
    global _dom_audit_running, _dom_audit_result

    if _dom_audit_running:
        return JSONResponse({"status": "running", "msg": "DOM audit já em execução"}, status_code=409)

    # Check cache
    dom_map_path = Path("knowledge/pjecalc_dom_map.json")
    if dom_map_path.exists():
        try:
            cached = json.loads(dom_map_path.read_text(encoding="utf-8"))
            age_hours = (datetime.now() - datetime.fromisoformat(cached.get("metadata", {}).get("gerado_em", "2000-01-01"))).total_seconds() / 3600
            if age_hours < 1 and not _dom_audit_result:
                return JSONResponse({"status": "cached", "age_hours": round(age_hours, 2), "data": cached})
        except Exception:
            pass

    if _dom_audit_result:
        return JSONResponse({"status": "done", "data": _dom_audit_result})

    # Start audit in background thread
    _dom_audit_running = True
    import threading
    def _run():
        global _dom_audit_running, _dom_audit_result
        try:
            from tools.dom_auditor import DOMAuditor
            auditor = DOMAuditor(
                base_url=PJECALC_LOCAL_URL,
                headless=True,
                output_dir="knowledge",
            )
            auditor.iniciar()
            try:
                result = auditor.auditar()
                auditor.gerar_saida()
                _dom_audit_result = result
                logger.info("DOM audit concluído: %d páginas, %d elementos",
                            result.get("metadata", {}).get("total_paginas", 0),
                            result.get("metadata", {}).get("total_elementos", 0))
            finally:
                auditor.fechar()
        except Exception as e:
            logger.error("DOM audit falhou: %s", e, exc_info=True)
            _dom_audit_result = {"erro": str(e)}
        finally:
            _dom_audit_running = False

    t = threading.Thread(target=_run, daemon=True, name="dom-auditor")
    t.start()
    return JSONResponse({"status": "started", "msg": "DOM audit iniciado. GET /api/dom-audit novamente para resultado."})

@app.get("/api/dom-audit/status")
async def dom_audit_status():
    """Verifica status do DOM audit."""
    if _dom_audit_running:
        return {"status": "running"}
    if _dom_audit_result:
        n_paginas = len(_dom_audit_result.get("paginas", {}))
        n_elementos = sum(
            len(p.get("elementos", []))
            for p in _dom_audit_result.get("paginas", {}).values()
        )
        return {"status": "done", "paginas": n_paginas, "elementos": n_elementos}
    return {"status": "idle"}


@app.get("/api/executar/{sessao_id}")
async def executar_automacao_sse(
    sessao_id: str,
    modo_oculto: bool = False,
    db: Session = Depends(get_db),
):
    """
    SSE endpoint — transmite logs da automação Playwright em tempo real.
    Automação roda em thread desacoplada do SSE. Reconexões fazem "follow" do runner existente.
    """
    from fastapi.responses import StreamingResponse as _SR
    import time as _time_mod

    # Limpeza oportunística de runners antigos (finalizados há >5 min)
    _limpar_runners_antigos()

    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # ── Follow mode: se já existe um runner ativo, reconectar sem reiniciar ──
    existing_runner = _automacao_runners.get(sessao_id)
    if existing_runner and not existing_runner.done:
        logger.info(f"SSE follow mode [{sessao_id}] — reconectando ao runner existente")
        return _SR(
            _sse_follow_runner(existing_runner, sessao_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Runner finalizado recentemente? Limpar para permitir nova execução ──
    if existing_runner and existing_runner.done:
        _automacao_runners.pop(sessao_id, None)

    # Lock GLOBAL — apenas uma automação por vez (Firefox headless é single-instance)
    if _automacao_global_lock.get("ts"):
        _global_age = _time_mod.time() - _automacao_global_lock["ts"]
        _global_sessao = _automacao_global_lock.get("sessao", "?")
        if _global_age < _LOCK_TIMEOUT_S and _global_sessao != sessao_id:
            async def _global_lock_sse():
                yield f"data: ERRO_EXPORTAVEL::Outra automação já em andamento (sessão {_global_sessao}). Aguarde o término.\n\n"
                yield "data: [FIM DA EXECUÇÃO]\n\n"
            return _SR(_global_lock_sse(), media_type="text/event-stream",
                       headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        elif _global_age >= _LOCK_TIMEOUT_S:
            _automacao_global_lock.clear()

    # Adquirir locks ANTES de criar o StreamingResponse (evita race condition
    # onde duas requests passam o check acima antes de qualquer uma adquirir)
    _sessoes_automacao[sessao_id] = _time_mod.time()
    _automacao_global_lock["ts"] = _time_mod.time()
    _automacao_global_lock["sessao"] = sessao_id

    def _liberar_locks():
        _sessoes_automacao.pop(sessao_id, None)
        _automacao_global_lock.clear()

    # Verificar que o usuário confirmou a prévia (HITL obrigatório)
    if not calculo.confirmado_em:
        _liberar_locks()
        async def _nao_confirmado_sse():
            yield "data: ERRO_EXPORTAVEL::Prévia não confirmada — revise os dados e clique Confirmar antes de executar.\n\n"
            yield "data: [FIM DA EXECUÇÃO]\n\n"
        return _SR(_nao_confirmado_sse(), media_type="text/event-stream",
                   headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()

    # Fix 4: validação dos dados antes de iniciar automação
    from modules.extraction import ValidadorSentenca
    _resultado_val = ValidadorSentenca(dados).validar()
    if not _resultado_val.valido:
        _liberar_locks()
        _erros_str = "; ".join(_resultado_val.erros[:3])
        async def _val_sse():
            yield f"data: ERRO_EXPORTAVEL::Dados inválidos — {_erros_str}\n\n"
            yield "data: [FIM DA EXECUÇÃO]\n\n"
        return _SR(_val_sse(), media_type="text/event-stream",
                   headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Fix 6: validação CNJ módulo 97 (aviso não bloqueante)
    # Algoritmo oficial CNJ (Resolução 65/2008):
    # Dado o número NNNNNNN-DD.AAAA.J.TR.OOOO, o dígito DD é calculado como:
    #   key = NNNNNNN + AAAA + J + TR + OOOO + "00"   (20 dígitos)
    #   DD  = 98 - (int(key) % 97)
    # J = 5 (Justiça do Trabalho). Valores válidos de DD: 01..98.
    def _validar_cnj(numero: str, digito: str, ano: str, regiao: str, vara: str) -> bool:
        try:
            key = numero + ano + "5" + regiao + vara + "00"
            resto = int(key) % 97
            return int(digito) == (98 - resto)
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

        # Locks já adquiridos no handler (antes do StreamingResponse)

        # Atualizar status no DB: confirmado → em_automacao
        _db_status = SessionLocal()
        try:
            _calc_status = RepositorioCalculo(_db_status).buscar_sessao(sessao_id)
            if _calc_status:
                _calc_status.status = "em_automacao"
                _db_status.commit()
        except Exception:
            pass
        finally:
            _db_status.close()

        _persist_enabled = os.environ.get("CALCULATION_PERSISTENCE", "true").lower() == "true"
        _exec_dir = None
        _runner_started = False  # track se o runner assumiu a responsabilidade dos locks

        try:
            # Emitir aviso CNJ se inválido
            if _cnj_aviso:
                yield f"data: {json.dumps({'msg': f'⚠ {_cnj_aviso}'})}\n\n"

            # ── Persistência por processo ──────────────────────────────
            if _persist_enabled:
                try:
                    from infrastructure.calculation_store import CalculationStore
                    _store = CalculationStore()
                    _num_proc = dados.get("processo", {}).get("numero", sessao_id)
                    _exec_dir = _store.criar_execucao(_num_proc, sessao_id)
                    _store.salvar_extracao_llm(_exec_dir, dados)
                    _store.salvar_parametros_enviados(_exec_dir, verbas_mapeadas)
                    _store.salvar_metadados(_exec_dir, {**dados, "_status": "automacao_iniciada"})
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

            # Aguardar PJE-Calc ficar disponível
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
                return  # finally block below will release locks

            # ── Criar runner desacoplado e iniciar automação em thread ──
            loop = asyncio.get_event_loop()
            parametrizacao_sse = dados.get("_parametrizacao") or {}
            gen = preencher_como_generator(
                dados, verbas_mapeadas, PJECALC_DIR, modo_oculto,
                parametrizacao=parametrizacao_sse,
                exec_dir=_exec_dir,
            )

            runner = _AutomacaoRunner(sessao_id)
            runner.exec_dir = _exec_dir
            _automacao_runners[sessao_id] = runner
            runner.start_thread(gen)
            _runner_started = True  # runner agora é responsável pelo cleanup dos locks

            # Agora apenas seguir o runner (mesmo código de follow)
            async for chunk in _sse_follow_runner(runner, sessao_id):
                yield chunk

        except Exception as _exc_sse:
            logger.exception(f"SSE gerador_sse exception [{sessao_id}]: {_exc_sse}")
            yield f"data: ERRO_EXPORTAVEL::Erro interno da automação: {_exc_sse}\n\n"
            yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"

        finally:
            # Se o runner NÃO foi criado, liberar locks aqui (senão o runner limpa sozinho)
            if not _runner_started:
                logger.info(f"gerador_sse cleanup (runner não iniciado) [{sessao_id}]")
                _sessoes_automacao.pop(sessao_id, None)
                _automacao_global_lock.clear()

    return _SR(
        gerador_sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/parar/{sessao_id}")
async def parar_automacao(sessao_id: str):
    """Para a automação em execução e limpa o runner."""
    runner = _automacao_runners.get(sessao_id)
    if not runner:
        return JSONResponse({"ok": False, "msg": "Nenhuma automação ativa para esta sessão."})
    if runner.done:
        return JSONResponse({"ok": True, "msg": "Automação já finalizada."})
    runner.stop()
    return JSONResponse({"ok": True, "msg": "Automação interrompida."})


async def _sse_follow_runner(runner: "_AutomacaoRunner", sessao_id: str):
    """
    Segue um runner existente: replay dos logs acumulados + stream novos.
    Se o SSE desconectar, o runner continua rodando em background.
    Usa padrão position-based: cada reader tem seu próprio cursor.
    """
    loop = asyncio.get_event_loop()
    pos = 0  # posição atual do cursor no runner.logs

    while True:
        # Ler todos os logs disponíveis a partir da posição atual
        current_logs = runner.logs[pos:]  # slice de lista é thread-safe em CPython
        if current_logs:
            for msg in current_logs:
                yield f"data: {json.dumps({'msg': msg})}\n\n"
                if msg.startswith("PROGRESS:"):
                    try:
                        parts = msg.split(":")[1].split("/")
                        yield f"data: {json.dumps({'type': 'progress', 'current': int(parts[0]), 'total': int(parts[1])})}\n\n"
                    except (IndexError, ValueError):
                        pass
                if msg.startswith("PJC_GERADO:"):
                    caminho = msg.split(":", 1)[1].strip()
                    db2 = SessionLocal()
                    try:
                        RepositorioCalculo(db2).marcar_exportado(sessao_id, caminho)
                        db2.commit()
                    finally:
                        db2.close()
                    if runner.exec_dir and runner._persist_enabled:
                        try:
                            from infrastructure.calculation_store import CalculationStore
                            CalculationStore().copiar_pjc(runner.exec_dir, caminho)
                            CalculationStore().atualizar_status(runner.exec_dir, "pjc_exportado")
                        except Exception:
                            pass
                    yield f"data: DOWNLOAD_LINK_CALC:/download/{sessao_id}/pjc\n\n"
                if msg == "[FIM DA EXECUÇÃO]":
                    return
            pos += len(current_logs)

        # Se runner terminou e já consumimos tudo
        if runner.done and pos >= len(runner.logs):
            yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
            return

        # Aguardar novos logs ou timeout (keepalive)
        got_new = await loop.run_in_executor(
            None, lambda: runner.wait_for_new(timeout=15)
        )
        if not got_new and not runner.done:
            yield ": keepalive\n\n"


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


# ── Admin: reset lock de automação ────────────────────────────────────────────

@app.post("/api/reset-lock/{sessao_id}")
async def reset_lock_automacao(sessao_id: str):
    """Libera lock de automação travado (para recuperação de falhas)."""
    _sessoes_automacao.pop(sessao_id, None)
    # Limpar lock global se pertence a esta sessão (ou forçar se sessao_id == "force")
    if _automacao_global_lock.get("sessao") == sessao_id or sessao_id == "force":
        _automacao_global_lock.clear()
    return {"sucesso": True, "msg": f"Lock liberado para {sessao_id}"}


@app.post("/api/vincular-pjc/{sessao_id}")
async def vincular_pjc(sessao_id: str, db: Session = Depends(get_db)):
    """Busca .PJC no diretório do cálculo e vincula ao registro no banco.

    Útil para sessões anteriores ao fix de PJC_GERADO (retroativo).
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Se já tem PJC vinculado e arquivo existe, retorna
    if calculo.arquivo_pjc and Path(calculo.arquivo_pjc).exists():
        return {"ok": True, "arquivo": calculo.arquivo_pjc, "msg": "Já vinculado"}

    # Buscar .PJC no diretório do cálculo ou em data/calculations/
    _dirs_busca = []
    if calculo.diretorio_calculo and Path(calculo.diretorio_calculo).exists():
        _dirs_busca.append(Path(calculo.diretorio_calculo))
    # Buscar em data/calculations/ por subpastas do processo
    _calc_base = Path("data/calculations")
    if _calc_base.exists():
        for _subdir in sorted(_calc_base.rglob("*.PJC")):
            _dirs_busca.append(_subdir)

    _pjc_encontrado = None
    for _item in _dirs_busca:
        if _item.is_file() and _item.suffix.upper() == ".PJC":
            _pjc_encontrado = _item
            break
        elif _item.is_dir():
            _pjcs = sorted(_item.glob("*.PJC"), reverse=True)
            if not _pjcs:
                _pjcs = sorted(_item.glob("*.pjc"), reverse=True)
            if _pjcs:
                _pjc_encontrado = _pjcs[0]
                break

    if not _pjc_encontrado:
        raise HTTPException(
            status_code=404,
            detail="Nenhum .PJC encontrado no diretório do cálculo"
        )

    repo.marcar_exportado(sessao_id, str(_pjc_encontrado))
    db.commit()
    return {
        "ok": True,
        "arquivo": str(_pjc_encontrado),
        "download": f"/download/{sessao_id}/pjc",
    }


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


# ── Estratégias de Verbas Dashboard ──────────────────────────────────────────

@app.get("/admin/estrategias-verbas", response_class=HTMLResponse)
async def admin_estrategias_verbas(request: Request, db: Session = Depends(get_db)):
    """Dashboard de estratégias de preenchimento de verbas."""
    try:
        from learning.verba_strategies import VerbaStrategyEngine
        engine = VerbaStrategyEngine(db=db)
        estrategias = engine.obter_estatisticas()
    except Exception as exc:
        estrategias = []
        logger.warning(f"Erro ao carregar estratégias de verbas: {exc}")

    # Carregar catálogo para exibir verbas conhecidas
    try:
        from learning.verba_strategies import _carregar_catalogo
        catalogo = _carregar_catalogo()
    except Exception:
        catalogo = {"expresso": [], "adaptaveis": [], "somente_manual": []}

    # Estatísticas resumidas
    total_tentativas = sum(e.get("tentativas", 0) for e in estrategias)
    total_sucessos = sum(e.get("sucessos", 0) for e in estrategias)
    total_falhas = sum(e.get("falhas", 0) for e in estrategias)
    taxa_global = round(total_sucessos / total_tentativas * 100, 1) if total_tentativas > 0 else 0

    return templates.TemplateResponse(
        request, "estrategias_verbas.html",
        {
            "estrategias": estrategias,
            "catalogo": catalogo,
            "total_tentativas": total_tentativas,
            "total_sucessos": total_sucessos,
            "total_falhas": total_falhas,
            "taxa_global": taxa_global,
            "num_expresso": len(catalogo.get("expresso", [])),
            "num_adaptaveis": len(catalogo.get("adaptaveis", [])),
            "num_manual": len(catalogo.get("somente_manual", [])),
        },
    )


@app.get("/api/estrategias-verbas")
async def api_estrategias_verbas(db: Session = Depends(get_db)):
    """API: lista todas as estratégias de verbas com estatísticas."""
    try:
        from learning.verba_strategies import VerbaStrategyEngine
        engine = VerbaStrategyEngine(db=db)
        return JSONResponse({"estrategias": engine.obter_estatisticas()})
    except Exception as exc:
        return JSONResponse({"estrategias": [], "erro": str(exc)})


@app.get("/api/estrategias-verbas/exportar")
async def api_exportar_catalogo_verbas(db: Session = Depends(get_db)):
    """API: exporta catálogo de estratégias aprendidas (para compartilhar entre instâncias)."""
    try:
        from learning.verba_strategies import VerbaStrategyEngine
        engine = VerbaStrategyEngine(db=db)
        return JSONResponse({"catalogo": engine.exportar_catalogo()})
    except Exception as exc:
        return JSONResponse({"catalogo": [], "erro": str(exc)})


@app.post("/api/estrategias-verbas/importar")
async def api_importar_catalogo_verbas(request: Request, db: Session = Depends(get_db)):
    """API: importa catálogo de estratégias (para compartilhar entre instâncias)."""
    try:
        from learning.verba_strategies import VerbaStrategyEngine
        body = await request.json()
        catalogo = body.get("catalogo", [])
        engine = VerbaStrategyEngine(db=db)
        count = engine.importar_catalogo(catalogo)
        return JSONResponse({"importados": count})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── DOM Audit ─────────────────────────────────────────────────────────────────

_dom_audit_result: dict | None = None
_dom_audit_running: bool = False

@app.get("/api/dom-audit")
async def api_dom_audit(background_tasks: BackgroundTasks):
    """Inicia auditoria DOM do PJE-Calc em background. Retorna status."""
    global _dom_audit_running, _dom_audit_result
    if _dom_audit_running:
        return JSONResponse({"status": "running", "message": "Auditoria já em andamento"})
    _dom_audit_running = True
    _dom_audit_result = None

    def _run_audit():
        global _dom_audit_running, _dom_audit_result
        try:
            from tools.dom_auditor import DOMAuditor
            auditor = DOMAuditor()
            _dom_audit_result = auditor.auditar()
            auditor.gerar_saida()
        except Exception as exc:
            _dom_audit_result = {"error": str(exc)}
        finally:
            _dom_audit_running = False

    import threading
    t = threading.Thread(target=_run_audit, daemon=True)
    t.start()
    return JSONResponse({"status": "started", "message": "Auditoria DOM iniciada em background"})

@app.get("/api/dom-audit/status")
async def api_dom_audit_status():
    """Retorna status da auditoria DOM."""
    if _dom_audit_running:
        return JSONResponse({"status": "running"})
    if _dom_audit_result is None:
        return JSONResponse({"status": "idle", "message": "Nenhuma auditoria executada"})
    if "error" in _dom_audit_result:
        return JSONResponse({"status": "error", "error": _dom_audit_result["error"]})
    pages = _dom_audit_result.get("pages", {})
    total = sum(len(p.get("elements", [])) for p in pages.values())
    return JSONResponse({
        "status": "done",
        "pages": len(pages),
        "total_elements": total,
    })


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
            # Propagar alerta de OCR com baixa confiança
            if resultado.get("_ocr_baixa_confianca"):
                _conf = resultado.get("_ocr_confianca_media", 0)
                dados.setdefault("alertas", []).append(
                    f"⚠ OCR com confiança baixa ({_conf}%). "
                    "O texto extraído pode conter erros — revise todos os campos."
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

        # Fase 2d: FGTS + 13º dezembro — calcular ajustes das Ocorrências do FGTS
        # Regra regulatória (Lei 8.036/90): FGTS sobre 13º é recolhido na competência
        # de dezembro (ou mês do desligamento). O PJE-Calc não faz esse ajuste
        # automaticamente — o agente calcula aqui, mostra na prévia para HITL, e
        # aplica via automação na página Ocorrências do FGTS.
        try:
            from modules.fgts_13o_calculator import calcular_ajustes_13o_fgts
            _fgts = dados.setdefault("fgts", {})
            _contrato = dados.get("contrato", {}) or {}
            _incidencia_ativa = _fgts.get("incidencia_13o_dezembro", True)
            if _incidencia_ativa is None:
                _incidencia_ativa = True
            _ajustes_13o = calcular_ajustes_13o_fgts(
                historico_salarial=dados.get("historico_salarial", []) or [],
                data_admissao=_contrato.get("data_admissao"),
                data_demissao=_contrato.get("data_demissao"),
                incidencia_ativa=bool(_incidencia_ativa),
            )
            _fgts["ajustes_ocorrencias_13o"] = _ajustes_13o
            _fgts["incidencia_13o_dezembro"] = bool(_incidencia_ativa)
        except Exception as e_fgts13:
            import logging
            logging.getLogger("pjecalc_agent.webapp").warning(
                f"Cálculo FGTS+13º falhou (não crítico): {e_fgts13}"
            )

        # Fase 3: Classificação
        verbas_mapeadas = mapear_para_pjecalc(dados.get("verbas_deferidas", []))

        # Número do processo — normalizar para padrão CNJ puro (ignora prefixos como "ATSum ")
        _numero_raw = dados.get("processo", {}).get("numero") or f"SESS-{sessao_id[:8]}"
        _cnj_m = re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", _numero_raw)
        numero = _cnj_m.group(0) if _cnj_m else _numero_raw
        if numero != _numero_raw:
            dados.setdefault("processo", {})["numero"] = numero  # normalizar também nos dados

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
        logger.error(
            f"Erro no processamento da sentença [{sessao_id}]: {e}", exc_info=True
        )
        try:
            calculo = db.query(Calculo).filter_by(sessao_id=sessao_id).first()
            if calculo:
                calculo.status = "erro"
                calculo.previa_texto = f"ERRO: {str(e)[:500]}"
                db.commit()
            else:
                # Calculo ainda não existia — criar registro de erro para o usuário ver
                numero = f"SESS-{sessao_id[:8]}"
                repo.criar_calculo(
                    sessao_id=sessao_id,
                    numero_processo=numero,
                    dados={"_erro": str(e)[:500]},
                    verbas_mapeadas={},
                )
                calculo = db.query(Calculo).filter_by(sessao_id=sessao_id).first()
                if calculo:
                    calculo.status = "erro"
                    calculo.previa_texto = f"ERRO: {str(e)[:500]}"
                    db.commit()
        except Exception as db_err:
            logger.error(f"Falha ao salvar erro no banco [{sessao_id}]: {db_err}")
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
