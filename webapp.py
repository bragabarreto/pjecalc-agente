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
from typing import Annotated, Any, Optional

from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, Form, HTTPException,
    Request, UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
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
        # CRÍTICO: marcar done=True para permitir cleanup pelo _limpar_runners_antigos.
        # Sem isso, o runner fica em cache indefinidamente e novos /api/executar
        # entram em "follow mode" do runner morto, retornando logs antigos.
        self.done = True

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
from modules.preview import (
    gerar_previa,
    aplicar_edicao_usuario,
    aplicar_edicao_verba,
    adicionar_base_calculo,
    remover_base_calculo,
    editar_base_calculo,
    garantir_bases_default,
)

# ── Configuração da aplicação ─────────────────────────────────────────────────

app = FastAPI(
    title="Agente PJE-Calc",
    description="Automação de Liquidação de Sentenças Trabalhistas",
    version="1.0.0",
)

# ── Schema v2 router (Fase 5: nova arquitetura) ─────────────────────────────
try:
    from modules.webapp_v2 import router_v2
    app.include_router(router_v2)
    logging.getLogger(__name__).info("router_v2 registrado: /processar/v2, /previa/v2/{id}")
except Exception as _e:
    logging.getLogger(__name__).warning(f"Falha ao registrar router_v2: {_e}")

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

    Detecta automaticamente JSON v2 (gerado pelo Projeto Claude externo) e
    desvia para o pipeline /processar/v2 (sem passar por Gemini/extraction).
    """
    sessao_id = str(uuid.uuid4())

    # Salvar sentença principal em temp
    sufixo = Path(sentenca.filename or "sentenca.pdf").suffix.lower()
    tmp_dir = Path(tempfile.mkdtemp())
    tmp_path = tmp_dir / f"sentenca{sufixo}"
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(sentenca.file, f)

    # ─── AUTO-DETECÇÃO de JSON v2 ──────────────────────────────────────────
    # Se o arquivo é .json e tem meta.schema_version == "2.0", roteia direto
    # para o pipeline v2 (sem Gemini/extraction). O usuário não precisa
    # decidir qual rota usar — basta subir o JSON gerado pelo Projeto Claude.
    if sufixo == ".json":
        try:
            with open(tmp_path, "r", encoding="utf-8") as _fjson:
                _payload_v2 = json.load(_fjson)
            _is_v2 = (
                isinstance(_payload_v2, dict)
                and isinstance(_payload_v2.get("meta"), dict)
                and str(_payload_v2["meta"].get("schema_version")) == "2.0"
            )
            if _is_v2:
                logger.info(f"[{sessao_id}] JSON v2 detectado — desviando para /processar/v2")
                from modules.webapp_v2 import (
                    PreviaCalculoV2 as _PreviaV2,
                    _save_previa as _save_v2,
                )
                try:
                    _previa = _PreviaV2.model_validate(_payload_v2)
                except Exception as _e_v2:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "erro": "JSON v2 inválido",
                            "detalhe": str(_e_v2),
                            "_dica": (
                                "Atualize o System Prompt do Projeto Claude com "
                                "docs/prompt-projeto-claude-externo.md (versão atual)."
                            ),
                        },
                    )
                _save_v2(sessao_id, _previa.model_dump())
                # Redirecionar para a UI v2
                return RedirectResponse(
                    url=f"/previa/v2/{sessao_id}",
                    status_code=303,
                )
        except json.JSONDecodeError:
            pass  # arquivo .json mal-formado — segue para o pipeline antigo
        except Exception as _e_route:
            logger.warning(f"[{sessao_id}] Falha no roteamento v2: {_e_route} — usando v1")

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
    v: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Exibe a prévia dos parâmetros do cálculo para apreciação e correção.
    Prévia fica salva no banco vinculada ao número do processo.

    Query param `?v=3` redireciona para a prévia v3 (réplica perfeita do PJE-Calc).
    """
    # Roteamento por versão (Etapa 2B.7)
    if v == 3:
        return RedirectResponse(url=f"/previa_v3/{sessao_id}", status_code=303)

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


# ─────────────────────────────────────────────────────────────────────────────
# Prévia v3 — réplica perfeita do PJE-Calc Cidadão
# ─────────────────────────────────────────────────────────────────────────────

def _migrar_v2_para_v3(calculo) -> tuple[dict, list[str]]:
    """Migra dados v2 (legacy) para schema v3 Pydantic.

    Retorna (dados_v3_dict, warnings) onde:
      - dados_v3_dict: dict pronto para template Jinja (cada chave é uma
        instância de model Pydantic ou lista delas)
      - warnings: lista de strings com avisos sobre campos descartados/inferidos

    Esta função é usada tanto pelo GET (renderiza prévia) quanto pelo endpoint
    POST /api/migrar_v3 (formaliza e valida a migração).
    """
    from infrastructure.pjecalc_pages import (
        DadosProcesso, HistoricoSalarialEntry, HistoricoSalarialOcorrencia,
        Verba, ParametrosVerba, OcorrenciaVerba,
        FGTS, ContribuicaoSocial, ImpostoRenda, CartaoDePonto,
        ProgramacaoSemanalDia, Falta, FeriasEntry, CustasJudiciais,
        CorrecaoJuros, Honorario,
    )

    warnings: list[str] = []
    dados_v2 = calculo.dados() or {}
    proc_v2 = dados_v2.get("processo", {}) or {}
    contrato_v2 = dados_v2.get("contrato", {}) or {}
    aviso_v2 = dados_v2.get("aviso_previo", {}) or {}
    presc_v2 = dados_v2.get("prescricao", {}) or {}
    hs_v2 = dados_v2.get("historico_salarial") or []

    try:
        processo_v3 = DadosProcesso(
            numero=proc_v2.get("numero_seq") or proc_v2.get("numero", ""),
            digito=proc_v2.get("digito_verificador") or proc_v2.get("digito", ""),
            ano=proc_v2.get("ano", ""),
            regiao=proc_v2.get("regiao", ""),
            vara=proc_v2.get("vara", ""),
            valor_da_causa=proc_v2.get("valor_da_causa"),
            autuado_em=proc_v2.get("autuado_em") or proc_v2.get("data_autuacao"),
            estado=proc_v2.get("estado") or proc_v2.get("uf"),
            municipio=proc_v2.get("municipio") or proc_v2.get("cidade"),
            reclamante_nome=proc_v2.get("reclamante") or proc_v2.get("nome_reclamante", ""),
            documento_fiscal_reclamante=proc_v2.get("documento_fiscal_reclamante"),
            reclamante_numero_documento_fiscal=proc_v2.get("numero_documento_reclamante", ""),
            reclamado_nome=proc_v2.get("reclamado") or proc_v2.get("nome_reclamado", ""),
            tipo_documento_fiscal_reclamado=proc_v2.get("tipo_documento_reclamado"),
            reclamado_numero_documento_fiscal=proc_v2.get("numero_documento_reclamado", ""),
            data_admissao=contrato_v2.get("admissao") or contrato_v2.get("data_admissao"),
            data_demissao=contrato_v2.get("demissao") or contrato_v2.get("data_demissao"),
            data_ajuizamento=contrato_v2.get("ajuizamento") or contrato_v2.get("data_ajuizamento"),
            data_inicio_calculo=contrato_v2.get("data_inicio_calculo") or contrato_v2.get("inicio_calculo"),
            data_termino_calculo=contrato_v2.get("data_termino_calculo") or contrato_v2.get("fim_calculo"),
            valor_maior_remuneracao=str(contrato_v2.get("maior_remuneracao", ""))
                if contrato_v2.get("maior_remuneracao") is not None else None,
            valor_ultima_remuneracao=str(contrato_v2.get("ultima_remuneracao", ""))
                if contrato_v2.get("ultima_remuneracao") is not None else None,
            prescricao_quinquenal=bool(presc_v2.get("quinquenal", False)),
            prescricao_fgts=bool(presc_v2.get("fgts", False)),
            apuracao_prazo_aviso_previo=(
                "APURACAO_CALCULADA" if aviso_v2.get("tipo") == "Calculado"
                else "APURACAO_INFORMADA" if aviso_v2.get("tipo") == "Informado"
                else "NAO_APURAR"
            ),
            projeta_aviso_indenizado=bool(aviso_v2.get("projetar", False)),
        )
    except Exception as e:
        warnings.append(f"DadosProcesso: erro na migração — {e}")
        processo_v3 = DadosProcesso()

    # Histórico Salarial
    historico_v3 = []
    for h in hs_v2:
        try:
            ocs = []
            for i, oc in enumerate(h.get("ocorrencias", []) or []):
                if isinstance(oc, dict):
                    ocs.append(HistoricoSalarialOcorrencia(
                        indice=i,
                        competencia=oc.get("competencia") or oc.get("mes_ano") or "",
                        ativo=bool(oc.get("ativo", True)),
                        valor=str(oc.get("valor")) if oc.get("valor") is not None else None,
                        valor_incidencia_cs=str(oc.get("valor_incidencia_cs"))
                            if oc.get("valor_incidencia_cs") is not None else None,
                        valor_incidencia_fgts=str(oc.get("valor_incidencia_fgts"))
                            if oc.get("valor_incidencia_fgts") is not None else None,
                        cs_recolhida=bool(oc.get("cs_recolhida") or oc.get("contribuicoes_ja_recolhidas", False)),
                        fgts_recolhido=bool(oc.get("fgts_recolhido") or oc.get("fgts_ja_recolhido", False)),
                    ))
            historico_v3.append(HistoricoSalarialEntry(
                nome=h.get("nome", ""),
                tipo_variacao_da_parcela="VARIAVEL" if h.get("variavel") else "FIXA",
                competencia_inicial=h.get("data_inicio") or h.get("competencia_inicial"),
                competencia_final=h.get("data_fim") or h.get("competencia_final"),
                tipo_valor="INFORMADO" if (h.get("tipo_valor") == "Informado" or h.get("valor") is not None) else "CALCULADO",
                valor_para_base_de_calculo=str(h.get("valor")) if h.get("valor") is not None else None,
                fgts=bool(h.get("incidencia_fgts", True)),
                inss=bool(h.get("incidencia_cs", h.get("incidencia_inss", True))),
                ocorrencias=ocs,
            ))
        except Exception as e:
            warnings.append(f"Histórico '{h.get('nome', '?')}': {e}")

    # Verbas (com reflexos recursivos)
    verbas_v2 = dados_v2.get("verbas") or calculo.verbas_mapeadas() or []

    def _carac(s):
        if not s: return "COMUM"
        s = str(s).strip().lower()
        return {"comum":"COMUM","13o salario":"DECIMO_TERCEIRO_SALARIO","13o":"DECIMO_TERCEIRO_SALARIO",
                "decimo terceiro":"DECIMO_TERCEIRO_SALARIO","decimo terceiro salario":"DECIMO_TERCEIRO_SALARIO",
                "ferias":"FERIAS","férias":"FERIAS","aviso previo":"AVISO_PREVIO",
                "aviso prévio":"AVISO_PREVIO"}.get(s, "COMUM")

    def _ocorr(s):
        if not s: return "MENSAL"
        s = str(s).strip().lower()
        return {"mensal":"MENSAL","dezembro":"DEZEMBRO","desligamento":"DESLIGAMENTO",
                "periodo aquisitivo":"PERIODO_AQUISITIVO","período aquisitivo":"PERIODO_AQUISITIVO"}.get(s, "MENSAL")

    def _migrar_oc_verba(oc_v2: dict, indice: int) -> OcorrenciaVerba:
        return OcorrenciaVerba(
            indice=oc_v2.get("indice", indice) if isinstance(oc_v2, dict) else indice,
            ativo=bool((oc_v2 or {}).get("ativo", True)),
            termo_div=str((oc_v2 or {}).get("termo_div") or "") or None,
            termo_mult=str((oc_v2 or {}).get("termo_mult") or "") or None,
            termo_quant=str((oc_v2 or {}).get("termo_quant") or (oc_v2 or {}).get("quantidade") or "") or None,
            valor_devido=str((oc_v2 or {}).get("valor_devido") or (oc_v2 or {}).get("valor") or "") or None,
            dobra=bool((oc_v2 or {}).get("dobra", False)),
        )

    def _migrar_verba(v2: dict):
        if not isinstance(v2, dict):
            return None
        try:
            params = ParametrosVerba(
                descricao=v2.get("nome_pjecalc") or v2.get("nome_sentenca") or v2.get("nome", ""),
                assuntos_cnj=str(v2.get("assuntos_cnj") or v2.get("cnj_codigo") or "2581"),
                tipo_de_verba="REFLEXA" if (str(v2.get("tipo", "")).lower() == "reflexa" or v2.get("eh_reflexa")) else "PRINCIPAL",
                tipo_variacao_da_parcela="VARIAVEL" if v2.get("variavel") else "FIXA",
                caracteristica_verba=_carac(v2.get("caracteristica")),
                ocorrencia_pagto=_ocorr(v2.get("ocorrencia") or v2.get("ocorrencia_pagamento")),
                periodo_inicial=v2.get("periodo_inicio"),
                periodo_final=v2.get("periodo_fim"),
                valor=("INFORMADO" if v2.get("valor_informado") is not None else "CALCULADO"),
                valor_informado=str(v2.get("valor_informado")) if v2.get("valor_informado") is not None else None,
                fgts=bool(v2.get("incidencia_fgts", True)),
                inss=bool(v2.get("incidencia_inss", v2.get("incidencia_cs", True))),
                irpf=bool(v2.get("incidencia_ir", v2.get("incidencia_irpf", False))),
                outro_valor_do_multiplicador=str(v2.get("percentual") or "") or None,
                tipo_da_base_tabelada=(
                    "MAIOR_REMUNERACAO" if str(v2.get("base_calculo","")).lower() in ("maior remuneracao","maior_remuneracao")
                    else "HISTORICO_SALARIAL" if str(v2.get("base_calculo","")).lower() in ("historico salarial","historico_salarial")
                    else "SALARIO_MINIMO" if str(v2.get("base_calculo","")).lower() in ("salario minimo","salario_minimo")
                    else None
                ),
            )
            ocs = [_migrar_oc_verba(oc, i) for i, oc in enumerate(v2.get("ocorrencias") or [])]
            refs = []
            for r2 in (v2.get("reflexos") or v2.get("reflexas_sugeridas") or []):
                if isinstance(r2, str):
                    refs.append(Verba(parametros=ParametrosVerba(descricao=r2, tipo_de_verba="REFLEXA")))
                else:
                    rmig = _migrar_verba(r2)
                    if rmig:
                        rmig.parametros.tipo_de_verba = "REFLEXA"
                        refs.append(rmig)
            return Verba(
                parametros=params,
                ocorrencias=ocs,
                reflexos=refs,
                lancamento=("EXPRESSO" if (v2.get("lancamento") or "").lower() == "expresso" else
                            ("EXPRESSO" if v2.get("expresso_alvo") or v2.get("expresso_equivalente") else "MANUAL")),
                expresso_alvo=v2.get("expresso_alvo") or v2.get("expresso_equivalente") or v2.get("nome_pjecalc"),
            )
        except Exception as e:
            warnings.append(f"Verba '{v2.get('nome_pjecalc', '?')}': {e}")
            return None

    verbas_v3 = []
    if isinstance(verbas_v2, list):
        for v in verbas_v2:
            mig = _migrar_verba(v)
            if mig:
                verbas_v3.append(mig)
    elif isinstance(verbas_v2, dict):
        for grupo in ("predefinidas", "personalizadas", "manuais"):
            for v in (verbas_v2.get(grupo) or []):
                mig = _migrar_verba(v)
                if mig:
                    verbas_v3.append(mig)

    # FGTS / INSS / IR / Cartão / Faltas / Férias / Custas / Correção / Honorários
    fgts_v2 = dados_v2.get("fgts") or {}
    try:
        fgts_v3 = FGTS(
            apurar=bool(fgts_v2.get("apurar", True)),
            tipo_de_verba=fgts_v2.get("tipo_de_verba", "NORMAL"),
            compor_principal=fgts_v2.get("compor_principal", "SIM"),
            aliquota=str(fgts_v2.get("aliquota", "8")) if fgts_v2.get("aliquota") in ("8","2",8,2,"INFORMADO",8.0,2.0) or not fgts_v2.get("aliquota") else "8",
            multa_do_fgts=fgts_v2.get("multa") or fgts_v2.get("multa_do_fgts") or
                          ("MULTA_DE_40" if fgts_v2.get("multa_40") else
                           "MULTA_DE_20" if fgts_v2.get("multa_20") else "MULTA_DE_40"),
            multa_do_artigo_467=bool(fgts_v2.get("multa_467") or fgts_v2.get("fgts_multa_467", False)),
        )
    except Exception as e:
        warnings.append(f"FGTS: {e}")
        fgts_v3 = FGTS()

    inss_v2 = dados_v2.get("contribuicao_social") or dados_v2.get("inss") or {}
    try:
        inss_v3 = ContribuicaoSocial(
            apurar=bool(inss_v2.get("apurar", True)),
            indice_atualizacao=inss_v2.get("indice"),
            aliquota_rat=str(inss_v2.get("rat") or inss_v2.get("aliquota_rat", "")) or None,
            fap=str(inss_v2.get("fap") or "") or None,
        )
    except Exception as e:
        warnings.append(f"INSS: {e}")
        inss_v3 = ContribuicaoSocial()

    ir_v2 = dados_v2.get("imposto_renda") or {}
    try:
        ir_v3 = ImpostoRenda(
            apurar=bool(ir_v2.get("apurar", True)),
            quantidade_dependentes=int(ir_v2.get("dependentes") or ir_v2.get("quantidade_dependentes") or 0),
            meses_tributaveis=ir_v2.get("meses_tributaveis"),
            regime_tributacao=ir_v2.get("regime") or "MESES_TRIBUTAVEIS",
        )
    except Exception as e:
        warnings.append(f"IR: {e}")
        ir_v3 = ImpostoRenda()

    cp_v2 = dados_v2.get("cartao_ponto") or dados_v2.get("cartao_de_ponto") or {}
    try:
        prog_v3 = []
        for d in (cp_v2.get("programacao_semanal") or []):
            try:
                prog_v3.append(ProgramacaoSemanalDia(
                    dia=d.get("dia", "SEG"),
                    turno1_inicio=d.get("turno1_inicio"),
                    turno1_fim=d.get("turno1_fim"),
                    turno2_inicio=d.get("turno2_inicio"),
                    turno2_fim=d.get("turno2_fim"),
                ))
            except Exception:
                continue
        cp_v3 = CartaoDePonto(
            forma_de_apuracao=cp_v2.get("forma_apuracao") or cp_v2.get("forma_de_apuracao"),
            jornada_diaria_h=str(cp_v2.get("jornada_diaria_h") or "") or None,
            jornada_semanal_h=str(cp_v2.get("jornada_semanal_h") or cp_v2.get("carga_horaria") or "") or None,
            intervalo_intrajornada_min=cp_v2.get("intervalo_intrajornada_min") or cp_v2.get("intervalo_min"),
            programacao_semanal=prog_v3,
        )
    except Exception as e:
        warnings.append(f"Cartão de Ponto: {e}")
        cp_v3 = CartaoDePonto()

    faltas_v3 = []
    for f in (dados_v2.get("faltas") or []):
        try:
            faltas_v3.append(Falta(
                data_inicio=f.get("data_inicio"), data_fim=f.get("data_fim"),
                justificada=bool(f.get("justificada", False)),
                descontar_remuneracao=bool(f.get("descontar_remuneracao", True)),
                descontar_dsr=bool(f.get("descontar_dsr", True)),
            ))
        except Exception as e:
            warnings.append(f"Falta: {e}")

    ferias_v3 = []
    for fe in (dados_v2.get("ferias") or []):
        try:
            ferias_v3.append(FeriasEntry(
                periodo_aquisitivo_inicio=fe.get("periodo_aquisitivo_inicio") or fe.get("aquisitivo_inicio"),
                periodo_aquisitivo_fim=fe.get("periodo_aquisitivo_fim") or fe.get("aquisitivo_fim"),
                data_inicio_gozo=fe.get("data_inicio_gozo") or fe.get("gozo_inicio"),
                data_fim_gozo=fe.get("data_fim_gozo") or fe.get("gozo_fim"),
                abono_pecuniario=bool(fe.get("abono_pecuniario", False)),
                dobra=bool(fe.get("dobra", False)),
            ))
        except Exception as e:
            warnings.append(f"Férias: {e}")

    custas_v2 = dados_v2.get("custas") or dados_v2.get("custas_judiciais") or {}
    try:
        custas_v3 = CustasJudiciais(
            percentual=str(custas_v2.get("percentual") or "2"),
            responsavel=custas_v2.get("responsavel") or custas_v2.get("responsabilidade") or "RECLAMADO",
            valor_periciais=str(custas_v2.get("valor_periciais") or "") or None,
        )
    except Exception as e:
        warnings.append(f"Custas: {e}")
        custas_v3 = CustasJudiciais()

    cj_v2 = dados_v2.get("correcao_juros") or {}
    _ind_corr_map = {"IPCA-E": "IPCAE", "IPCAE": "IPCAE", "TR": "TR", "INPC": "INPC",
                     "SELIC": "SELIC", "IPCA": "IPCA", "TRD": "TRD"}
    _base_juros_map = {"verbas": "VERBA", "verba": "VERBA",
                       "principal": "PRINCIPAL", "bruto": "BRUTO"}
    _taxa_juros_map = {"trd_simples": "TRD_SIMPLES", "tr_simples": "TR_SIMPLES",
                       "trd simples": "TRD_SIMPLES", "tr simples": "TR_SIMPLES",
                       "selic": "SELIC", "taxa_legal": "TAXA_LEGAL", "taxa legal": "TAXA_LEGAL",
                       "tr_fgts": "TR_FGTS", "tr fgts": "TR_FGTS"}
    try:
        cj_v3 = CorrecaoJuros(
            indice_correcao=_ind_corr_map.get(cj_v2.get("correcao_indice") or cj_v2.get("indice"), "IPCAE"),
            taxa_juros=_taxa_juros_map.get(str(cj_v2.get("juros_taxa") or "").lower(), "TRD_SIMPLES"),
            base_juros=_base_juros_map.get(str(cj_v2.get("base_juros") or "").lower(), "VERBA"),
            aplicar_ec_113=bool(cj_v2.get("aplicar_ec_113", True)),
        )
    except Exception as e:
        warnings.append(f"Correção/Juros: {e}")
        cj_v3 = CorrecaoJuros()

    honorarios_v3 = []
    for h in (dados_v2.get("honorarios") or []):
        try:
            tipo_dev_raw = str(h.get("tipo_devedor") or h.get("devedor") or "RECLAMADO").upper()
            tipo_dev = "RECLAMADO" if tipo_dev_raw in ("RECLAMADO", "RÉU") else "RECLAMANTE"
            tp = h.get("tipo_honorario") or h.get("tipo") or "ADVOCATICIOS"
            tdc = h.get("tipo_documento_credor") or h.get("tipo_doc_credor") or "CPF"
            if tdc not in ("CPF", "CNPJ", "CEI"):
                tdc = "CPF"
            honorarios_v3.append(Honorario(
                descricao=h.get("descricao") or "Honorário",
                tp_honorario=tp if tp in ("ADVOCATICIOS","ASSISTENCIAIS","CONTRATUAIS",
                                          "PERICIAIS_CONTADOR","PERICIAIS_DOCUMENTOSCOPIO") else "ADVOCATICIOS",
                tipo_de_devedor=tipo_dev,
                aliquota=str(h.get("percentual") or h.get("aliquota") or ""),
                nome_credor=h.get("nome_credor") or "",
                tipo_documento_fiscal_credor=tdc,
                numero_documento_fiscal_credor=h.get("numero_documento_credor") or h.get("doc_credor") or "",
                apurar_irrf=bool(h.get("apurar_irrf", True)),
            ))
        except Exception as e:
            warnings.append(f"Honorário: {e}")

    return {
        "processo": processo_v3,
        "historico_salarial": historico_v3,
        "faltas": faltas_v3,
        "ferias": ferias_v3,
        "verbas": verbas_v3,
        "cartao_de_ponto": cp_v3,
        "fgts": fgts_v3,
        "contribuicao_social": inss_v3,
        "imposto_renda": ir_v3,
        "honorarios": honorarios_v3,
        "custas": custas_v3,
        "correcao_juros": cj_v3,
    }, warnings


@app.get("/previa_v3/{sessao_id}", response_class=HTMLResponse)
async def exibir_previa_v3(
    request: Request,
    sessao_id: str,
    db: Session = Depends(get_db),
):
    """Exibe a prévia v3 — réplica perfeita do PJE-Calc."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    dados_v3, _warnings = _migrar_v2_para_v3(calculo)
    if _warnings:
        logger.info(f"Prévia v3 {sessao_id[:8]}: {len(_warnings)} avisos de migração")

    return templates.TemplateResponse(
        request, "previa_v3/index.html",
        {
            "sessao_id": sessao_id,
            "dados": dados_v3,
            "processo_numero": calculo.processo.numero_processo if calculo.processo else None,
            "reclamante_nome": dados_v3.get("processo").reclamante_nome,
        },
    )


@app.post("/api/migrar_v3/{sessao_id}")
async def migrar_para_v3(
    sessao_id: str,
    db: Session = Depends(get_db),
):
    """Migração explícita v2 → v3 com relatório.

    Diferente do GET (que migra on-the-fly silenciosamente), este endpoint:
      1. Roda a migração formalmente
      2. Valida o resultado com Pydantic v3 (model_dump faz model_rebuild)
      3. Retorna relatório com:
         - sucesso: bool
         - resumo: dict com contagens (verbas, ocorrências, reflexos, etc.)
         - warnings: lista de avisos de campos descartados/inferidos
         - schema_version: "3.0"
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        return JSONResponse(
            {"sucesso": False, "erro": "Sessão não encontrada"}, status_code=404
        )

    try:
        dados_v3, warnings = _migrar_v2_para_v3(calculo)
    except Exception as e:
        return JSONResponse(
            {"sucesso": False, "erro": f"Erro fatal na migração: {e}"},
            status_code=500,
        )

    # Validar serialização (model_dump força validação completa)
    erros_serializacao = []
    for chave, valor in dados_v3.items():
        try:
            if isinstance(valor, list):
                for item in valor:
                    if hasattr(item, "model_dump"):
                        item.model_dump()
            elif hasattr(valor, "model_dump"):
                valor.model_dump()
        except Exception as e:
            erros_serializacao.append(f"{chave}: {e}")

    resumo = {
        "verbas": len(dados_v3.get("verbas", [])),
        "verbas_principais": sum(
            1 for v in dados_v3.get("verbas", [])
            if v.parametros.tipo_de_verba == "PRINCIPAL"
        ),
        "verbas_reflexas": sum(
            1 for v in dados_v3.get("verbas", [])
            if v.parametros.tipo_de_verba == "REFLEXA"
        ),
        "verbas_com_reflexos": sum(
            1 for v in dados_v3.get("verbas", [])
            if len(v.reflexos) > 0
        ),
        "total_ocorrencias_verbas": sum(
            len(v.ocorrencias) for v in dados_v3.get("verbas", [])
        ),
        "historico_salarial_entries": len(dados_v3.get("historico_salarial", [])),
        "historico_salarial_ocorrencias": sum(
            len(h.ocorrencias) for h in dados_v3.get("historico_salarial", [])
        ),
        "honorarios": len(dados_v3.get("honorarios", [])),
        "faltas": len(dados_v3.get("faltas", [])),
        "ferias": len(dados_v3.get("ferias", [])),
        "cartao_ponto_dias": len(dados_v3.get("cartao_de_ponto").programacao_semanal),
    }

    return JSONResponse({
        "sucesso": len(erros_serializacao) == 0,
        "schema_version": "3.0",
        "sessao_id": sessao_id,
        "resumo": resumo,
        "warnings": warnings,
        "erros_serializacao": erros_serializacao,
        "url_previa_v3": f"/previa_v3/{sessao_id}",
    })


@app.get("/api/migrar_v3/{sessao_id}/preview")
async def preview_migracao_v3(
    sessao_id: str,
    db: Session = Depends(get_db),
):
    """Preview da migração — retorna JSON v3 completo (todos os campos),
    sem persistir. Útil para export do JSON v3 / debugging."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        return JSONResponse({"erro": "Sessão não encontrada"}, status_code=404)

    try:
        dados_v3, warnings = _migrar_v2_para_v3(calculo)
    except Exception as e:
        return JSONResponse({"erro": f"Migração falhou: {e}"}, status_code=500)

    payload: dict = {"_warnings": warnings, "schema_version": "3.0"}
    for chave, valor in dados_v3.items():
        if isinstance(valor, list):
            payload[chave] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in valor
            ]
        elif hasattr(valor, "model_dump"):
            payload[chave] = valor.model_dump()
        else:
            payload[chave] = valor

    return JSONResponse(payload)


@app.post("/previa_v3/{sessao_id}/editar")
async def editar_campo_previa_v3(
    sessao_id: str,
    campo: str = Form(...),
    valor: str = Form(""),
    db: Session = Depends(get_db),
):
    """Salva uma edição inline de campo na prévia v3.

    Por ora persiste no `dados_json` v2 do calculo (migração reversa).
    Etapa 2B.6 vai criar coluna dedicada `dados_v3_json` e migração formal.

    Notação dot:
      - "processo.numero" → dados.processo.numero
      - "verbas[0].parametros.descricao" → dados.verbas[0].parametros.descricao
      - "verbas[0].add" → adicionar item à lista
      - "verbas[0].remove[2]" → remover índice 2
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        return JSONResponse(
            {"sucesso": False, "erro": "Sessão não encontrada"}, status_code=404
        )

    # Por ora, persistência minimal — apenas processo.* mapeia de volta para
    # dados_v2.processo / dados_v2.contrato / dados_v2.prescricao / aviso_previo.
    dados = calculo.dados() or {}
    proc = dados.setdefault("processo", {})
    contrato = dados.setdefault("contrato", {})
    presc = dados.setdefault("prescricao", {})
    aviso = dados.setdefault("aviso_previo", {})

    # Mapping campo v3 → caminho v2
    _MAP_V3_TO_V2 = {
        "processo.numero": ("processo", "numero_seq"),
        "processo.digito": ("processo", "digito_verificador"),
        "processo.ano": ("processo", "ano"),
        "processo.regiao": ("processo", "regiao"),
        "processo.vara": ("processo", "vara"),
        "processo.valor_da_causa": ("processo", "valor_da_causa"),
        "processo.autuado_em": ("processo", "autuado_em"),
        "processo.estado": ("processo", "estado"),
        "processo.municipio": ("processo", "municipio"),
        "processo.reclamante_nome": ("processo", "reclamante"),
        "processo.documento_fiscal_reclamante": ("processo", "documento_fiscal_reclamante"),
        "processo.reclamante_numero_documento_fiscal": ("processo", "numero_documento_reclamante"),
        "processo.reclamante_tipo_documento_previdenciario": ("processo", "tipo_documento_previdenciario_reclamante"),
        "processo.reclamante_numero_documento_previdenciario": ("processo", "numero_documento_previdenciario_reclamante"),
        "processo.nome_advogado_reclamante": ("processo", "nome_advogado_reclamante"),
        "processo.numero_oab_advogado_reclamante": ("processo", "oab_advogado_reclamante"),
        "processo.tipo_documento_advogado_reclamante": ("processo", "tipo_documento_advogado_reclamante"),
        "processo.numero_documento_advogado_reclamante": ("processo", "numero_documento_advogado_reclamante"),
        "processo.reclamado_nome": ("processo", "reclamado"),
        "processo.tipo_documento_fiscal_reclamado": ("processo", "tipo_documento_reclamado"),
        "processo.reclamado_numero_documento_fiscal": ("processo", "numero_documento_reclamado"),
        "processo.nome_advogado_reclamado": ("processo", "nome_advogado_reclamado"),
        "processo.numero_oab_advogado_reclamado": ("processo", "oab_advogado_reclamado"),
        "processo.tipo_documento_advogado_reclamado": ("processo", "tipo_documento_advogado_reclamado"),
        "processo.numero_documento_advogado_reclamado": ("processo", "numero_documento_advogado_reclamado"),
        "processo.data_admissao": ("contrato", "admissao"),
        "processo.data_demissao": ("contrato", "demissao"),
        "processo.data_ajuizamento": ("contrato", "ajuizamento"),
        "processo.data_inicio_calculo": ("contrato", "data_inicio_calculo"),
        "processo.data_termino_calculo": ("contrato", "data_termino_calculo"),
        "processo.valor_maior_remuneracao": ("contrato", "maior_remuneracao"),
        "processo.valor_ultima_remuneracao": ("contrato", "ultima_remuneracao"),
        "processo.prescricao_quinquenal": ("prescricao", "quinquenal"),
        "processo.prescricao_fgts": ("prescricao", "fgts"),
        "processo.projeta_aviso_indenizado": ("aviso_previo", "projetar"),
        "processo.zera_valor_negativo": ("processo", "zera_valor_negativo"),
        "processo.considera_feriado_estadual": ("processo", "considera_feriado_estadual"),
        "processo.considera_feriado_municipal": ("processo", "considera_feriado_municipal"),
        "processo.valor_carga_horaria_padrao": ("processo", "valor_carga_horaria_padrao"),
        "processo.sabado_dia_util": ("processo", "sabado_dia_util"),
        "processo.comentarios": ("processo", "comentarios"),
    }

    # Conversões de tipo
    valor_normalizado: Any = valor
    if valor in ("true", "false"):
        valor_normalizado = (valor == "true")
    elif valor == "" or valor == "null":
        valor_normalizado = None

    # apuracao_prazo_aviso_previo precisa map reversa
    if campo == "processo.apuracao_prazo_aviso_previo":
        if valor_normalizado == "APURACAO_CALCULADA":
            aviso["tipo"] = "Calculado"
        elif valor_normalizado == "APURACAO_INFORMADA":
            aviso["tipo"] = "Informado"
        else:
            aviso["tipo"] = None
        repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
        return JSONResponse({"sucesso": True})

    if campo in _MAP_V3_TO_V2:
        bloco_nome, atributo = _MAP_V3_TO_V2[campo]
        bloco = dados.setdefault(bloco_nome, {})
        bloco[atributo] = valor_normalizado
        repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
        return JSONResponse({"sucesso": True})

    # ── Histórico Salarial (sub-etapa 2B.3) ──
    # Padrões aceitos:
    #   historico_salarial.add                          → adicionar entry vazia
    #   historico_salarial.remove[N]                    → remover entry N
    #   historico_salarial[N].<campo>                   → editar campo da entry N
    #   historico_salarial[N].ocorrencias.add           → adicionar ocorrência
    #   historico_salarial[N].ocorrencias.remove[M]     → remover ocorrência M
    #   historico_salarial[N].ocorrencias[M].<campo>    → editar campo da ocorrência
    if campo.startswith("historico_salarial"):
        import re as _re
        hs_list = dados.setdefault("historico_salarial", [])

        # Normalização: campos v3 → chaves v2 do dict de cada entry
        _MAP_HS_FIELD = {
            "nome": "nome",
            "tipo_variacao_da_parcela": "tipo_variacao_da_parcela",
            "competencia_inicial": "data_inicio",
            "competencia_final": "data_fim",
            "tipo_valor": "tipo_valor",
            "valor_para_base_de_calculo": "valor",
            "fgts": "incidencia_fgts",
            "inss": "incidencia_cs",
        }
        _MAP_OC_FIELD = {
            "competencia": "competencia",
            "ativo": "ativo",
            "valor": "valor",
            "valor_incidencia_cs": "valor_incidencia_cs",
            "valor_incidencia_fgts": "valor_incidencia_fgts",
            "cs_recolhida": "cs_recolhida",
            "fgts_recolhido": "fgts_recolhido",
        }

        # 1. add / remove de entry
        if campo == "historico_salarial.add":
            hs_list.append({"nome": "", "data_inicio": "", "data_fim": "", "valor": None,
                            "incidencia_fgts": True, "incidencia_cs": True, "ocorrencias": []})
            repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
            return JSONResponse({"sucesso": True})

        m = _re.match(r"^historico_salarial\.remove\[(\d+)\]$", campo)
        if m:
            idx = int(m.group(1))
            if 0 <= idx < len(hs_list):
                hs_list.pop(idx)
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})
            return JSONResponse({"sucesso": False, "erro": f"índice {idx} fora de range"}, status_code=400)

        # 2. add / remove de ocorrência: historico_salarial[N].ocorrencias.add
        m = _re.match(r"^historico_salarial\[(\d+)\]\.ocorrencias\.add$", campo)
        if m:
            hi = int(m.group(1))
            if 0 <= hi < len(hs_list):
                ocs = hs_list[hi].setdefault("ocorrencias", [])
                ocs.append({"competencia": "", "ativo": True, "valor": None,
                            "valor_incidencia_cs": None, "valor_incidencia_fgts": None,
                            "cs_recolhida": False, "fgts_recolhido": False})
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

        m = _re.match(r"^historico_salarial\[(\d+)\]\.ocorrencias\.remove\[(\d+)\]$", campo)
        if m:
            hi, oi = int(m.group(1)), int(m.group(2))
            if 0 <= hi < len(hs_list):
                ocs = hs_list[hi].get("ocorrencias", [])
                if 0 <= oi < len(ocs):
                    ocs.pop(oi)
                    repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                    return JSONResponse({"sucesso": True})

        # 3. editar campo da ocorrência: historico_salarial[N].ocorrencias[M].<campo>
        m = _re.match(r"^historico_salarial\[(\d+)\]\.ocorrencias\[(\d+)\]\.(\w+)$", campo)
        if m:
            hi, oi, attr = int(m.group(1)), int(m.group(2)), m.group(3)
            if 0 <= hi < len(hs_list):
                ocs = hs_list[hi].setdefault("ocorrencias", [])
                while len(ocs) <= oi:
                    ocs.append({})
                v2_attr = _MAP_OC_FIELD.get(attr, attr)
                ocs[oi][v2_attr] = valor_normalizado
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

        # 4. editar campo da entry: historico_salarial[N].<campo>
        m = _re.match(r"^historico_salarial\[(\d+)\]\.(\w+)$", campo)
        if m:
            hi, attr = int(m.group(1)), m.group(2)
            if 0 <= hi < len(hs_list):
                v2_attr = _MAP_HS_FIELD.get(attr, attr)
                # Caso especial: tipo_variacao_da_parcela vira flag 'variavel' booleano
                if attr == "tipo_variacao_da_parcela":
                    hs_list[hi]["variavel"] = (valor_normalizado == "VARIAVEL")
                else:
                    hs_list[hi][v2_attr] = valor_normalizado
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

        return JSONResponse(
            {"sucesso": False, "erro": f"Padrão '{campo}' não reconhecido em historico_salarial.*"},
            status_code=400,
        )

    # ── Verbas (sub-etapa 2B.4) ──
    # Padrões aceitos:
    #   verbas.add / verbas.remove[N]
    #   verbas[N].lancamento / .expresso_alvo
    #   verbas[N].parametros.<campo>
    #   verbas[N].ocorrencias.add / .remove[M]
    #   verbas[N].ocorrencias[M].<campo>
    #   verbas[N].reflexos.add / .remove[M]
    #   verbas[N].reflexos[M].lancamento / .expresso_alvo
    #   verbas[N].reflexos[M].parametros.<campo>
    #   verbas[N].reflexos[M].ocorrencias.add / .remove[K]
    #   verbas[N].reflexos[M].ocorrencias[K].<campo>
    if campo.startswith("verbas"):
        import re as _re

        # Verbas podem estar em dados.verbas (v3 nativo) OU em verbas_mapeadas
        # (v2 legacy — coluna verbas_json separada).
        # Estratégia: usar dados.verbas como source of truth para v3.
        # Na primeira edição, migra verbas_mapeadas → dados.verbas.
        verbas_atual = dados.get("verbas")
        if not isinstance(verbas_atual, list):
            # Carregar de verbas_mapeadas e achatar
            vm = calculo.verbas_mapeadas() or {}
            if isinstance(vm, dict):
                verbas_flat = []
                for grupo in ("predefinidas", "personalizadas", "manuais"):
                    verbas_flat.extend(vm.get(grupo) or [])
                verbas_atual = verbas_flat
            elif isinstance(vm, list):
                verbas_atual = list(vm)
            else:
                verbas_atual = []
            dados["verbas"] = verbas_atual

        _MAP_PV_TO_V2 = {
            "descricao": "nome_pjecalc",
            "assuntos_cnj": "assuntos_cnj",
            "tipo_de_verba": "tipo",
            "tipo_variacao_da_parcela": "_tipo_variacao",
            "caracteristica_verba": "caracteristica",
            "ocorrencia_pagto": "ocorrencia",
            "ocorrencia_ajuizamento": "_ocorrencia_ajuizamento",
            "periodo_inicial": "periodo_inicio",
            "periodo_final": "periodo_fim",
            "gera_reflexo": "_gera_reflexo",
            "gerar_principal": "_gerar_principal",
            "compor_principal": "_compor_principal",
            "valor": "_valor_tipo",
            "valor_informado": "valor_informado",
            "irpf": "incidencia_ir",
            "inss": "incidencia_inss",
            "fgts": "incidencia_fgts",
            "previdencia_privada": "_previdencia_privada",
            "pensao_alimenticia": "_pensao_alimenticia",
            "tipo_da_base_tabelada": "_tipo_base_tabelada",
            "base_historicos": "_base_historicos",
            "integralizar_base": "_integralizar_base",
            "tipo_de_divisor": "_tipo_divisor",
            "outro_valor_do_divisor": "_valor_divisor",
            "outro_valor_do_multiplicador": "percentual",
            "tipo_da_quantidade": "_tipo_quantidade",
            "valor_informado_da_quantidade": "quantidade",
            "aplicar_proporcionalidade_quantidade": "_prop_quantidade",
            "tipo_do_valor_pago": "_tipo_valor_pago",
            "valor_informado_pago": "_valor_pago",
            "aplicar_proporcionalidade_valor_pago": "_prop_valor_pago",
            "zera_valor_negativo": "_zera_valor_negativo",
            "excluir_falta_justificada": "_excluir_falta_justificada",
            "excluir_falta_nao_justificada": "_excluir_falta_nao_justificada",
            "excluir_ferias_gozadas": "_excluir_ferias_gozadas",
            "dobra_valor_devido": "_dobra_valor_devido",
            "aplicar_proporcionalidade_a_base": "_prop_base",
            "comentarios": "_comentarios",
        }

        _MAP_OCV_TO_V2 = {
            "ativo": "ativo", "termo_div": "termo_div", "termo_mult": "termo_mult",
            "termo_quant": "termo_quant", "valor_devido": "valor_devido", "dobra": "dobra",
        }

        _verba_vazia = lambda: {
            "nome_pjecalc": "", "tipo": "Principal", "caracteristica": "Comum",
            "ocorrencia": "Mensal", "ocorrencias": [], "reflexos": [],
        }

        def _navegar_verba(idx: int, sub_indices: list[int] = None):
            """Retorna (verba_dict, lista_pai). sub_indices = [reflexo_idx, ...]."""
            if not (0 <= idx < len(verbas_atual)):
                return None, None
            verba = verbas_atual[idx]
            pai = verbas_atual
            if sub_indices:
                for ri in sub_indices:
                    refs = verba.setdefault("reflexos", [])
                    if not (0 <= ri < len(refs)):
                        return None, None
                    pai = refs
                    verba = refs[ri]
            return verba, pai

        # 1. verbas.add
        if campo == "verbas.add":
            verbas_atual.append(_verba_vazia())
            repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
            return JSONResponse({"sucesso": True})

        # 2. verbas.remove[N]
        m = _re.match(r"^verbas\.remove\[(\d+)\]$", campo)
        if m:
            i = int(m.group(1))
            if 0 <= i < len(verbas_atual):
                verbas_atual.pop(i)
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

        # 3-9. verbas[N].* — múltiplos padrões
        m = _re.match(r"^verbas\[(\d+)\](.+)$", campo)
        if m:
            vi = int(m.group(1))
            resto = m.group(2)
            verba, _ = _navegar_verba(vi)
            if verba is None:
                return JSONResponse({"sucesso": False, "erro": f"verba[{vi}] não existe"}, status_code=400)

            # 3. verbas[N].lancamento
            if resto == ".lancamento":
                verba["lancamento"] = valor_normalizado
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})
            # 4. verbas[N].expresso_alvo
            if resto == ".expresso_alvo":
                verba["expresso_alvo"] = valor_normalizado
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

            # 5. verbas[N].parametros.<campo>
            mp = _re.match(r"^\.parametros\.(\w+)$", resto)
            if mp:
                attr = mp.group(1)
                v2_attr = _MAP_PV_TO_V2.get(attr, attr)
                # Casos especiais (mapping reverso de Literal v3 → v2 PT-BR)
                if attr == "tipo_de_verba":
                    verba["tipo"] = "Reflexa" if valor_normalizado == "REFLEXA" else "Principal"
                elif attr == "caracteristica_verba":
                    _rev = {"COMUM":"Comum","DECIMO_TERCEIRO_SALARIO":"13o Salario",
                            "AVISO_PREVIO":"Aviso Previo","FERIAS":"Ferias"}
                    verba["caracteristica"] = _rev.get(valor_normalizado, valor_normalizado)
                elif attr == "ocorrencia_pagto":
                    _rev = {"MENSAL":"Mensal","DEZEMBRO":"Dezembro","DESLIGAMENTO":"Desligamento",
                            "PERIODO_AQUISITIVO":"Periodo Aquisitivo"}
                    verba["ocorrencia"] = _rev.get(valor_normalizado, valor_normalizado)
                elif attr == "tipo_da_base_tabelada":
                    _rev = {"MAIOR_REMUNERACAO":"Maior Remuneracao","HISTORICO_SALARIAL":"Historico Salarial",
                            "SALARIO_DA_CATEGORIA":"Salario da Categoria","SALARIO_MINIMO":"Salario Minimo",
                            "VALOR_INFORMADO":"Valor Informado"}
                    verba["base_calculo"] = _rev.get(valor_normalizado, valor_normalizado)
                else:
                    verba[v2_attr] = valor_normalizado
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

            # 6. verbas[N].ocorrencias.add
            if resto == ".ocorrencias.add":
                ocs = verba.setdefault("ocorrencias", [])
                ocs.append({"indice": len(ocs), "ativo": True, "termo_div": None,
                            "termo_mult": None, "termo_quant": None, "valor_devido": None, "dobra": False})
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

            # 7. verbas[N].ocorrencias.remove[M]
            mr = _re.match(r"^\.ocorrencias\.remove\[(\d+)\]$", resto)
            if mr:
                oi = int(mr.group(1))
                ocs = verba.get("ocorrencias", [])
                if 0 <= oi < len(ocs):
                    ocs.pop(oi)
                    repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                    return JSONResponse({"sucesso": True})

            # 8. verbas[N].ocorrencias[M].<campo>
            mo = _re.match(r"^\.ocorrencias\[(\d+)\]\.(\w+)$", resto)
            if mo:
                oi = int(mo.group(1))
                attr = mo.group(2)
                ocs = verba.setdefault("ocorrencias", [])
                while len(ocs) <= oi:
                    ocs.append({})
                v2_attr = _MAP_OCV_TO_V2.get(attr, attr)
                ocs[oi][v2_attr] = valor_normalizado
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

            # 9. verbas[N].reflexos.add / .remove[M] / [M].xxx (recursivo)
            if resto == ".reflexos.add":
                refs = verba.setdefault("reflexos", [])
                refs.append({"nome_pjecalc": "", "tipo": "Reflexa", "caracteristica": "Comum",
                             "ocorrencia": "Mensal", "ocorrencias": [], "reflexos": []})
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

            mrr = _re.match(r"^\.reflexos\.remove\[(\d+)\]$", resto)
            if mrr:
                ri = int(mrr.group(1))
                refs = verba.get("reflexos", [])
                if 0 <= ri < len(refs):
                    refs.pop(ri)
                    repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                    return JSONResponse({"sucesso": True})

            # 10. verbas[N].reflexos[M].xxx (delegar recursivo: aplicar a cada nível)
            mrf = _re.match(r"^\.reflexos\[(\d+)\](.+)$", resto)
            if mrf:
                ri = int(mrf.group(1))
                resto2 = mrf.group(2)
                refs = verba.setdefault("reflexos", [])
                while len(refs) <= ri:
                    refs.append({"nome_pjecalc":"","tipo":"Reflexa","caracteristica":"Comum",
                                 "ocorrencia":"Mensal","ocorrencias":[],"reflexos":[]})
                ref = refs[ri]
                # Re-aplicar a lógica acima sobre o reflexo (parâmetros + ocorrências)
                if resto2 == ".lancamento":
                    ref["lancamento"] = valor_normalizado
                elif resto2 == ".expresso_alvo":
                    ref["expresso_alvo"] = valor_normalizado
                else:
                    mp2 = _re.match(r"^\.parametros\.(\w+)$", resto2)
                    if mp2:
                        attr = mp2.group(1)
                        if attr == "tipo_de_verba":
                            ref["tipo"] = "Reflexa" if valor_normalizado == "REFLEXA" else "Principal"
                        elif attr == "caracteristica_verba":
                            _rev = {"COMUM":"Comum","DECIMO_TERCEIRO_SALARIO":"13o Salario",
                                    "AVISO_PREVIO":"Aviso Previo","FERIAS":"Ferias"}
                            ref["caracteristica"] = _rev.get(valor_normalizado, valor_normalizado)
                        elif attr == "ocorrencia_pagto":
                            _rev = {"MENSAL":"Mensal","DEZEMBRO":"Dezembro","DESLIGAMENTO":"Desligamento",
                                    "PERIODO_AQUISITIVO":"Periodo Aquisitivo"}
                            ref["ocorrencia"] = _rev.get(valor_normalizado, valor_normalizado)
                        else:
                            ref[_MAP_PV_TO_V2.get(attr, attr)] = valor_normalizado
                    else:
                        # ocorrências do reflexo
                        if resto2 == ".ocorrencias.add":
                            roc = ref.setdefault("ocorrencias", [])
                            roc.append({"indice": len(roc), "ativo": True, "termo_mult": None,
                                        "termo_quant": None, "valor_devido": None})
                        else:
                            mor = _re.match(r"^\.ocorrencias\.remove\[(\d+)\]$", resto2)
                            if mor:
                                rooi = int(mor.group(1))
                                roc = ref.get("ocorrencias", [])
                                if 0 <= rooi < len(roc):
                                    roc.pop(rooi)
                            else:
                                moo = _re.match(r"^\.ocorrencias\[(\d+)\]\.(\w+)$", resto2)
                                if moo:
                                    rooi = int(moo.group(1))
                                    attr = moo.group(2)
                                    roc = ref.setdefault("ocorrencias", [])
                                    while len(roc) <= rooi:
                                        roc.append({})
                                    roc[rooi][_MAP_OCV_TO_V2.get(attr, attr)] = valor_normalizado
                                else:
                                    return JSONResponse(
                                        {"sucesso": False, "erro": f"Padrão recursivo '{resto2}' não reconhecido"},
                                        status_code=400,
                                    )
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

        return JSONResponse(
            {"sucesso": False, "erro": f"Padrão '{campo}' não reconhecido em verbas.*"},
            status_code=400,
        )

    # ── Páginas auxiliares (sub-etapa 2B.5) ──
    # Handler genérico para FGTS, INSS, IR, Custas, Correção, Cartão de Ponto,
    # Honorários, Faltas, Férias. Suporta:
    #   <secao>.<campo>                — escalar
    #   <secao>.<lista>.add            — adicionar item à lista
    #   <secao>.<lista>.remove[N]      — remover item N
    #   <secao>[N].<campo>             — para listas top-level (faltas, ferias, honorarios)
    #   <secao>[N].<lista>.add/remove  — listas aninhadas
    #
    # Mapeia para secao v2 equivalente (ex.: cartao_de_ponto → cartao_ponto)
    _SECAO_V3_TO_V2 = {
        "fgts": "fgts",
        "contribuicao_social": "contribuicao_social",
        "imposto_renda": "imposto_renda",
        "cartao_de_ponto": "cartao_ponto",
        "custas": "custas",
        "correcao_juros": "correcao_juros",
        "honorarios": "honorarios",
        "faltas": "faltas",
        "ferias": "ferias",
    }

    def _vazio_auxiliar(secao: str) -> dict:
        templates_v = {
            "honorarios": {"descricao":"","tp_honorario":"ADVOCATICIOS","tipo_de_devedor":"RECLAMADO",
                           "tipo_valor":"CALCULADO","aliquota":None,"nome_credor":"",
                           "tipo_documento_fiscal_credor":"CPF","numero_documento_fiscal_credor":""},
            "faltas": {"data_inicio":None,"data_fim":None,"justificada":False,
                       "descontar_remuneracao":True,"descontar_dsr":True},
            "ferias": {"periodo_aquisitivo_inicio":None,"periodo_aquisitivo_fim":None,
                       "data_inicio_gozo":None,"data_fim_gozo":None,
                       "abono_pecuniario":False,"dobra":False},
        }
        return templates_v.get(secao, {})

    import re as _re
    primeiro_seg = campo.split(".")[0].split("[")[0]
    if primeiro_seg in _SECAO_V3_TO_V2:
        v2_key = _SECAO_V3_TO_V2[primeiro_seg]
        is_lista = primeiro_seg in ("honorarios", "faltas", "ferias")

        # Pattern 1: <secao>.<campo escalar>
        m_simple = _re.match(rf"^{primeiro_seg}\.(\w+)$", campo)
        if m_simple and not is_lista:
            attr = m_simple.group(1)
            bloco = dados.setdefault(v2_key, {})
            bloco[attr] = valor_normalizado
            repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
            return JSONResponse({"sucesso": True})

        # Pattern 2: <secao>.<lista>.add (cartao_de_ponto.programacao_semanal.add)
        m_listadd = _re.match(rf"^{primeiro_seg}\.(\w+)\.add$", campo)
        if m_listadd and not is_lista:
            attr = m_listadd.group(1)
            bloco = dados.setdefault(v2_key, {})
            lst = bloco.setdefault(attr, [])
            if attr == "programacao_semanal":
                lst.append({"dia": "SEG", "turno1_inicio": None, "turno1_fim": None,
                            "turno2_inicio": None, "turno2_fim": None})
            else:
                lst.append({})
            repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
            return JSONResponse({"sucesso": True})

        # Pattern 3: <secao>.<lista>.remove[N]
        m_listrem = _re.match(rf"^{primeiro_seg}\.(\w+)\.remove\[(\d+)\]$", campo)
        if m_listrem and not is_lista:
            attr = m_listrem.group(1)
            i = int(m_listrem.group(2))
            bloco = dados.setdefault(v2_key, {})
            lst = bloco.get(attr) or []
            if 0 <= i < len(lst):
                lst.pop(i)
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

        # Pattern 4: <secao>.<lista>[N].<campo>
        m_listidx = _re.match(rf"^{primeiro_seg}\.(\w+)\[(\d+)\]\.(\w+)$", campo)
        if m_listidx and not is_lista:
            attr_lst = m_listidx.group(1)
            i = int(m_listidx.group(2))
            attr_item = m_listidx.group(3)
            bloco = dados.setdefault(v2_key, {})
            lst = bloco.setdefault(attr_lst, [])
            while len(lst) <= i:
                lst.append({})
            lst[i][attr_item] = valor_normalizado
            repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
            return JSONResponse({"sucesso": True})

        # Pattern 5: <listapadrao>.add (top-level: honorarios.add, faltas.add)
        if campo == f"{primeiro_seg}.add" and is_lista:
            lst = dados.setdefault(v2_key, [])
            lst.append(_vazio_auxiliar(primeiro_seg))
            repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
            return JSONResponse({"sucesso": True})

        # Pattern 6: <listapadrao>.remove[N]
        m_topr = _re.match(rf"^{primeiro_seg}\.remove\[(\d+)\]$", campo)
        if m_topr and is_lista:
            i = int(m_topr.group(1))
            lst = dados.setdefault(v2_key, [])
            if 0 <= i < len(lst):
                lst.pop(i)
                repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
                return JSONResponse({"sucesso": True})

        # Pattern 7: <listapadrao>[N].<campo>
        m_topidx = _re.match(rf"^{primeiro_seg}\[(\d+)\]\.(\w+)$", campo)
        if m_topidx and is_lista:
            i = int(m_topidx.group(1))
            attr = m_topidx.group(2)
            lst = dados.setdefault(v2_key, [])
            while len(lst) <= i:
                lst.append(_vazio_auxiliar(primeiro_seg))
            lst[i][attr] = valor_normalizado
            repo.atualizar_dados(sessao_id, dados, calculo.verbas_mapeadas())
            return JSONResponse({"sucesso": True})

        return JSONResponse(
            {"sucesso": False, "erro": f"Padrão '{campo}' não reconhecido em '{primeiro_seg}.*'"},
            status_code=400,
        )

    # Campo não-mapeado
    return JSONResponse(
        {"sucesso": False, "erro": f"Campo '{campo}' ainda não mapeado v3→v2"},
        status_code=400,
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


@app.delete("/previa/{sessao_id}/verba/{indice}")
async def remover_verba_endpoint(
    sessao_id: str,
    indice: int,
    db: Session = Depends(get_db),
):
    """Remove uma verba do índice global da prévia (predefinidas + personalizadas
    + nao_reconhecidas). Útil para descartar verbas órfãs ou desnecessárias.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()
    try:
        # Encontrar a verba pelo índice global e removê-la do grupo correto
        _grupos = ("predefinidas", "personalizadas", "nao_reconhecidas")
        _offset = 0
        _removida = None
        for _g in _grupos:
            _lst = verbas_mapeadas.get(_g) or []
            if indice - _offset < len(_lst):
                _removida = _lst.pop(indice - _offset)
                verbas_mapeadas[_g] = _lst
                break
            _offset += len(_lst)
        if _removida is None:
            return JSONResponse({"sucesso": False, "erro": f"índice {indice} fora de range"}, status_code=400)
        nova_previa = gerar_previa(dados, verbas_mapeadas)
        repo.atualizar_dados(sessao_id, dados, verbas_mapeadas)
        repo.salvar_previa(sessao_id, nova_previa, _previa_para_html(nova_previa))
        return JSONResponse({"sucesso": True, "indice": indice,
                             "nome": (_removida.get("nome_pjecalc") or _removida.get("nome_sentenca") or "?")})
    except Exception as exc:
        import logging, traceback
        logging.error("remover_verba erro: %s\n%s", exc, traceback.format_exc())
        return JSONResponse({"sucesso": False, "erro": str(exc)}, status_code=500)


@app.post("/previa/{sessao_id}/verba/{indice}/base")
async def add_base_verba(
    sessao_id: str,
    indice: int,
    db: Session = Depends(get_db),
):
    """Adiciona uma base de cálculo padrão (HE-style) à verba `indice`.

    Defaults: tipo_base=HISTORICO_SALARIAL, historico_subtipo=ULTIMA_REMUNERACAO,
    divisor=CARGA_HORARIA, multiplicador=1.5, integralizar=true.
    Após criação, o usuário edita campos via PATCH.
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()
    try:
        verbas_mapeadas = adicionar_base_calculo(verbas_mapeadas, indice)
        nova_previa = gerar_previa(dados, verbas_mapeadas)
        repo.atualizar_dados(sessao_id, dados, verbas_mapeadas)
        repo.salvar_previa(sessao_id, nova_previa, _previa_para_html(nova_previa))
        # Retornar a base recém-criada para o frontend
        todas = (
            verbas_mapeadas.get("predefinidas", [])
            + verbas_mapeadas.get("personalizadas", [])
            + verbas_mapeadas.get("nao_reconhecidas", [])
        )
        verba = todas[indice] if 0 <= indice < len(todas) else {}
        bases = verba.get("bases_calculo") or []
        return JSONResponse(
            {"sucesso": True, "indice": indice, "base_idx": len(bases) - 1, "base": bases[-1] if bases else None}
        )
    except Exception as exc:
        import logging, traceback
        logging.error("add_base_verba erro: %s\n%s", exc, traceback.format_exc())
        return JSONResponse({"sucesso": False, "erro": str(exc)}, status_code=500)


@app.delete("/previa/{sessao_id}/verba/{indice}/base/{base_idx}")
async def del_base_verba(
    sessao_id: str,
    indice: int,
    base_idx: int,
    db: Session = Depends(get_db),
):
    """Remove a base de cálculo `base_idx` da verba `indice`."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()
    try:
        verbas_mapeadas = remover_base_calculo(verbas_mapeadas, indice, base_idx)
        nova_previa = gerar_previa(dados, verbas_mapeadas)
        repo.atualizar_dados(sessao_id, dados, verbas_mapeadas)
        repo.salvar_previa(sessao_id, nova_previa, _previa_para_html(nova_previa))
        return JSONResponse({"sucesso": True, "indice": indice, "base_idx": base_idx})
    except Exception as exc:
        import logging, traceback
        logging.error("del_base_verba erro: %s\n%s", exc, traceback.format_exc())
        return JSONResponse({"sucesso": False, "erro": str(exc)}, status_code=500)


@app.post("/previa/{sessao_id}/verba/{indice}/base/{base_idx}/editar")
async def edit_base_verba(
    sessao_id: str,
    indice: int,
    base_idx: int,
    campo: str = Form(...),
    valor: str = Form(...),
    db: Session = Depends(get_db),
):
    """Edita um campo de uma base de cálculo da verba.

    Campos suportados: tipo_base, historico_subtipo, proporcionalizar (bool),
    verba_compor (str|null), integralizar (bool), divisor, multiplicador (float),
    outro_valor_divisor (float).
    """
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    dados = calculo.dados()
    verbas_mapeadas = calculo.verbas_mapeadas()
    try:
        verbas_mapeadas = editar_base_calculo(verbas_mapeadas, indice, base_idx, campo, valor)
        nova_previa = gerar_previa(dados, verbas_mapeadas)
        repo.atualizar_dados(sessao_id, dados, verbas_mapeadas)
        repo.salvar_previa(sessao_id, nova_previa, _previa_para_html(nova_previa))
        return JSONResponse(
            {"sucesso": True, "indice": indice, "base_idx": base_idx, "campo": campo, "valor": valor}
        )
    except Exception as exc:
        import logging, traceback
        logging.error("edit_base_verba erro: %s\n%s", exc, traceback.format_exc())
        return JSONResponse({"sucesso": False, "erro": str(exc)}, status_code=500)


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
    # ── Parâmetros avançados Manual / Adaptado (mapa DOM PJE-Calc 2.15.1) ──
    incidencia_prev_priv: str = Form("false"),
    incidencia_pensao: str = Form("false"),
    tipo_variacao_parcela: str = Form(""),       # FIXA | VARIAVEL
    tipo_valor: str = Form(""),                  # CALCULADO | INFORMADO
    compor_principal: str = Form(""),            # SIM | NAO
    ocorrencia_ajuizamento: str = Form(""),      # OCORRENCIAS_VENCIDAS | _E_VINCENDAS
    tipo_base_tabelada: str = Form(""),          # MAIOR_REMUNERACAO | HISTORICO_SALARIAL | ...
    base_historico: str = Form(""),              # ÚLTIMA REMUNERAÇÃO | SALÁRIO BASE | ...
    proporcionaliza_historico: str = Form(""),   # SIM | NAO
    integralizar_base: str = Form(""),           # SIM | NAO
    tipo_divisor: str = Form(""),                # CARGA_HORARIA | DIAS_UTEIS | OUTRO_VALOR | IMPORTADA_DO_CARTAO
    multiplicador: str = Form(""),               # ex: 1,5
    tipo_quantidade: str = Form(""),             # INFORMADA | IMPORTADA_DO_CALENDARIO | IMPORTADA_DO_CARTAO_DE_PONTO
    quantidade_informada: str = Form(""),
    zera_negativo: str = Form("false"),
    dobra_valor_devido: str = Form("false"),
    excluir_falta_justificada: str = Form("true"),
    excluir_falta_nao_justificada: str = Form("true"),
    excluir_ferias_gozadas: str = Form("true"),
    aplicar_prop_quantidade: str = Form("false"),
    aplicar_prop_base: str = Form("false"),
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
            "incidencia_previdencia_privada": _to_bool(incidencia_prev_priv),
            "incidencia_pensao_alimenticia": _to_bool(incidencia_pensao),
            "verba_principal_ref": verba_principal_ref or None,
            "confianca": 1.0,  # adicionada manualmente pelo usuário → confiança máxima
            "mapeada": estrategia == "expresso_direto",
            "estrategia_preenchimento": {
                "tipo_verba": tipo,
                "tipo": estrategia,
                "baseado_em": "usuario",
                "verba_principal_ref": verba_principal_ref or None,
                # parametros aplicados pelo Playwright no form Manual / Parâmetros
                "parametros": {
                    k: v for k, v in {
                        "tipo_variacao_parcela": tipo_variacao_parcela or None,
                        "tipo_valor": tipo_valor or None,
                        "compor_principal": compor_principal or None,
                        "ocorrencia_ajuizamento": ocorrencia_ajuizamento or None,
                        "tipo_base_tabelada": tipo_base_tabelada or None,
                        "base_historico": base_historico or None,
                        "proporcionaliza_historico": proporcionaliza_historico or None,
                        "integralizar_base": integralizar_base or None,
                        "tipo_divisor": tipo_divisor or None,
                        "multiplicador": multiplicador or None,
                        "tipo_quantidade": tipo_quantidade or None,
                        "quantidade_informada": quantidade_informada or None,
                        "zera_valor_negativo": _to_bool(zera_negativo),
                        "dobra_valor_devido": _to_bool(dobra_valor_devido),
                        "excluir_falta_justificada": _to_bool(excluir_falta_justificada),
                        "excluir_falta_nao_justificada": _to_bool(excluir_falta_nao_justificada),
                        "excluir_ferias_gozadas": _to_bool(excluir_ferias_gozadas),
                        "aplicar_prop_quantidade": _to_bool(aplicar_prop_quantidade),
                        "aplicar_prop_base": _to_bool(aplicar_prop_base),
                    }.items() if v not in (None, "")
                },
            },
        }

        # Categorizar pela estratégia
        if estrategia == "expresso_direto":
            verbas_mapeadas.setdefault("predefinidas", []).append(nova_verba)
        else:
            verbas_mapeadas.setdefault("personalizadas", []).append(nova_verba)

        # Auto-popular bases_calculo default — garante que a Prévia mostre
        # fielmente o que a automação aplicará na tabela "Bases Cadastradas"
        # do PJE-Calc, mesmo quando o usuário/IA não especificou base.
        try:
            verbas_mapeadas = garantir_bases_default(verbas_mapeadas)
        except Exception as _e_b:
            logger.debug(f"garantir_bases_default não aplicado: {_e_b}")

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
                # indice global = predefinidas vêm primeiro, depois personalizadas
                len(verbas_mapeadas.get("predefinidas", [])) - 1
                if estrategia == "expresso_direto"
                else (
                    len(verbas_mapeadas.get("predefinidas", []))
                    + len(verbas_mapeadas.get("personalizadas", []))
                    - 1
                )
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
        # CORREÇÃO 2026-05-03: sincronizar parametros.X com verba.X (campo raiz)
        # Validador e Playwright leem verba.ocorrencia / verba.caracteristica
        # / verba.base_calculo / verba.percentual diretamente. Sem este sync,
        # editar via UI ("Mensal") não atualiza o campo raiz e o validador
        # continua reclamando do valor antigo ("Desligamento").
        _SYNC_RAIZ = {
            "ocorrencia": "ocorrencia",
            "caracteristica": "caracteristica",
            "base_calculo": "base_calculo",
            "tipo_valor": "tipo_valor",
            "multiplicador": "multiplicador",
            "divisor": "divisor",
            "quantidade": "quantidade",
            "percentual": "percentual",
        }
        if sub_campo in _SYNC_RAIZ:
            verba[_SYNC_RAIZ[sub_campo]] = valor
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


@app.get("/api/previa/{sessao_id}/validar")
async def validar_previa_endpoint(sessao_id: str, db: Session = Depends(get_db)):
    """Valida a Prévia sem confirmar — retorna erros e avisos de forma
    estruturada para exibição na UI antes do clique em Confirmar."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    try:
        from modules.previa_validator import validar_previa
        res = validar_previa(calculo.dados(), calculo.verbas_mapeadas())
        return JSONResponse(res.to_dict())
    except Exception as exc:
        import logging, traceback
        logging.error("validar_previa erro: %s\n%s", exc, traceback.format_exc())
        return JSONResponse(
            {"valido": False, "erros": [{"severidade": "erro", "secao": "_sistema",
                                          "campo": "_validador", "mensagem": str(exc)}],
             "avisos": []},
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

    # ── Validador completo da Prévia ──────────────────────────────────────────
    # Identifica problemas que fariam a automação Playwright falhar OU a
    # Liquidação do PJE-Calc bloquear com pendências do tipo "Erro".
    # Política: erros bloqueantes IMPEDEM a confirmação. Avisos são informativos.
    try:
        from modules.previa_validator import validar_previa
        _val = validar_previa(dados, verbas_mapeadas)
        # Adiciona erros do validador ao bloqueio
        for e in _val.erros:
            erros.append(f"[{e['secao']}] {e['mensagem']}")
        # Avisos não bloqueiam, mas serão retornados para exibição
        avisos_validador = _val.avisos
    except Exception as _e_val:
        logger.warning(f"validador_previa_falhou: {_e_val}")
        avisos_validador = []

    if erros:
        return JSONResponse(
            {
                "sucesso": False,
                "erros": erros,
                "avisos": avisos_validador,
                "mensagem": (
                    "Prévia inválida — corrija os erros indicados antes de confirmar. "
                    "Sem isso, a automação falhará no PJE-Calc."
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


def _validar_pjc_para_download(pjc_path: str | Path) -> tuple[bool, str]:
    """REGRA PROIBITIVA: valida hashCodeLiquidacao e dataDeLiquidacao do PJC
    antes de servir. Arquivos com NULL nesses campos são templates inválidos
    (gerados nativamente ou exportados antes de liquidar). Espelha
    `_validar_pjc_liquidado` do playwright_pjecalc.py.
    """
    try:
        p = Path(str(pjc_path))
        if not p.exists():
            return (False, "arquivo inexistente")
        if p.stat().st_size < 1024:
            return (False, f"tamanho suspeito ({p.stat().st_size} bytes)")
        import zipfile as _zf, re as _re
        try:
            with _zf.ZipFile(str(p), 'r') as _z:
                if "calculo.xml" not in _z.namelist():
                    return (False, "ZIP sem calculo.xml")
                xml_bytes = _z.read("calculo.xml")
        except _zf.BadZipFile:
            return (False, "não é ZIP válido")
        try:
            xml_str = xml_bytes.decode("iso-8859-1", errors="replace")
        except Exception:
            xml_str = xml_bytes.decode("utf-8", errors="replace")
        m_hash = _re.search(r"<hashCodeLiquidacao>([^<]*)</hashCodeLiquidacao>", xml_str)
        hv = (m_hash.group(1) if m_hash else "").strip()
        if not hv or hv.lower() == "null":
            return (False, "hashCodeLiquidacao=null (PJC NÃO LIQUIDADO)")
        m_data = _re.search(r"<dataDeLiquidacao>([^<]*)</dataDeLiquidacao>", xml_str)
        dv = (m_data.group(1) if m_data else "").strip()
        if not dv or dv.lower() == "null":
            return (False, "dataDeLiquidacao=null (PJC NÃO LIQUIDADO)")
        return (True, "ok")
    except Exception as _e:
        return (False, f"erro validação: {_e}")


@app.get("/download/{sessao_id}/pjc")
async def download_pjc(sessao_id: str, db: Session = Depends(get_db)):
    """Download do arquivo .pjc exportado pelo PJE-Calc Cidadão.

    REGRA DE OURO PROIBITIVA: Apenas arquivos .PJC gerados pelo próprio
    PJE-Calc Cidadão (via Liquidar + Exportar na automação) são válidos.
    Arquivos com hashCodeLiquidacao=null ou dataDeLiquidacao=null são
    bloqueados — sempre rejeitados pelo PJE-Calc institucional.
    Geração nativa em Python (pjc_generator.py) está PROIBIDA por regra
    de negócio (2026-05-03) e levanta RuntimeError se invocada.
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
            # VALIDAÇÃO PROIBITIVA antes de auto-vincular
            _ok, _motivo = _validar_pjc_para_download(_pjc_encontrado)
            if not _ok:
                logger.warning(
                    f"download_pjc REJEITADO {_pjc_encontrado} → sessão {sessao_id}: {_motivo}"
                )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Arquivo .PJC encontrado mas REJEITADO ({_motivo}). "
                        "PJCs sem hashCodeLiquidacao/dataDeLiquidacao são templates "
                        "pré-liquidação inválidos — não foram gerados pelo PJE-Calc "
                        "Cidadão após Liquidar com sucesso. Re-execute a automação."
                    ),
                )
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
    # Validação final mesmo para arquivo já vinculado (defesa em profundidade)
    _ok_final, _motivo_final = _validar_pjc_para_download(caminho)
    if not _ok_final:
        logger.warning(
            f"download_pjc REJEITADO arquivo vinculado {caminho} → sessão {sessao_id}: {_motivo_final}"
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Arquivo .PJC vinculado é INVÁLIDO ({_motivo_final}). "
                "Foi gerado sem liquidação real do PJE-Calc Cidadão — bloqueado "
                "pela regra de negócio. Re-execute a automação até concluir a "
                "Liquidação com sucesso."
            ),
        )
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


@app.get("/api/pendencias/{sessao_id}")
async def api_pendencias(sessao_id: str, db: Session = Depends(get_db)):
    """Retorna o último relatório de pendências (JSON) para a sessão.

    Quando a Liquidação falha, a automação salva um arquivo
    `PENDENCIAS_<numProcesso>_<timestamp>.json` na OUTPUT_DIR. Este endpoint
    localiza o mais recente para a sessão e devolve o conteúdo.
    """
    import json as _json
    import glob as _glob
    from config import OUTPUT_DIR
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo or not calculo.processo:
        raise HTTPException(status_code=404, detail="Sessão/processo não encontrado")
    _num = calculo.processo.numero_processo or ""
    _num_limpo = _num.replace("-", "").replace(".", "").replace("/", "")
    _padrao = str(Path(OUTPUT_DIR) / f"PENDENCIAS_{_num_limpo}_*.json")
    _arquivos = sorted(_glob.glob(_padrao))
    if not _arquivos:
        return {
            "tem_pendencias": False,
            "processo": _num,
            "mensagem": "Nenhum relatório de pendências encontrado para este processo.",
        }
    _ultimo = _arquivos[-1]
    try:
        _payload = _json.loads(Path(_ultimo).read_text(encoding="utf-8"))
        _payload["tem_pendencias"] = True
        _payload["arquivo"] = Path(_ultimo).name
        return _payload
    except Exception as _e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler relatório: {_e}")


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


# ─── Item 8: erros de mapping DOM (modo tolerante) ─────────────────────────

import re as _re_em

# Padrões de erro de mapping detectáveis no log
_PADROES_ERRO_MAPPING = [
    # (tipo, regex, severidade)
    ("radio_nao_encontrado",
     r"⚠ radio (\w+)=([^\s:]+):? não encontrado", "warning"),
    ("radio_budget_estourado",
     r"⚠ (\w+)=([^\s:]+):? budget de \d+s estourado", "warning"),
    ("select_disabled",
     r"⚠ select (\w+):? disabled — tentando JS direto", "warning"),
    ("select_nao_encontrado",
     r"⚠ select ([\w-]+):? não encontrado", "warning"),
    ("campo_nao_encontrado",
     r"⚠ Campo (\w+) não encontrado", "warning"),
    ("dom_id_nao_encontrado",
     r"⚠ ([\w_:]+) não existe — pulando", "info"),
    ("url_inesperada",
     r"⚠ (\w+): URL inesperada \(([^)]+)\)", "warning"),
    ("botao_nao_encontrado",
     r"⚠ Botão Novo não encontrado.* honorário (\d+)", "error"),
    ("falha_select_value",
     r"✗ ([\w_]+):? FALHA ao selecionar '(\w+)' — prévia indicava '([^']+)'", "error"),
    ("salvar_sem_sucesso",
     r"⚠ Salvar: mensagem de sucesso não detectada", "warning"),
    ("http_404",
     r"⚠ HTTP 404: ([^\s]+)", "warning"),
    ("execution_destroyed",
     r"Execution context was destroyed", "info"),
]


def _parsear_erros_mapping(logs: list[str]) -> list[dict]:
    """Extrai erros de mapping DOM a partir de uma lista de linhas de log.

    Retorna lista de dicts: {tipo, severidade, fase, campo, valor, raw_log, linha}
    """
    erros = []
    fase_atual = "?"
    for i, linha in enumerate(logs):
        # Tentar capturar fase atual
        m_fase = _re_em.search(r"Fase (\d+[a-z]?)\s*[—-]\s*([^…]+)", linha)
        if m_fase:
            fase_atual = f"{m_fase.group(1)} ({m_fase.group(2).strip()})"
            continue
        for tipo, padrao, sev in _PADROES_ERRO_MAPPING:
            m = _re_em.search(padrao, linha)
            if m:
                grupos = m.groups()
                erros.append({
                    "tipo": tipo,
                    "severidade": sev,
                    "fase": fase_atual,
                    "campo": grupos[0] if grupos else "",
                    "valor_tentado": grupos[1] if len(grupos) > 1 else None,
                    "raw_log": linha.strip()[-300:],
                    "linha": i,
                })
                break
    return erros


@app.get("/api/erros-mapping/{sessao_id}")
async def erros_mapping(sessao_id: str):
    """Retorna erros de mapping DOM detectados durante a automação.

    Útil para identificar discrepâncias entre o schema/automação e o DOM real
    do PJE-Calc. Cada erro inclui tipo, severidade, fase, campo e log bruto.
    """
    # Tentar runner em memória primeiro
    runner = _automacao_runners.get(sessao_id)
    logs: list[str] = []
    fonte = "n/a"
    if runner and runner.logs:
        logs = list(runner.logs)
        fonte = "runner_memory"
    else:
        # Fallback: ler do CalculationStore
        try:
            from infrastructure.calculation_store import CalculationStore
            store = CalculationStore()
            calc = store.buscar_por_sessao(sessao_id)
            if calc:
                log_path = Path(calc.exec_dir) / "automacao.log"
                if log_path.exists():
                    logs = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    fonte = "exec_dir_log"
        except Exception:
            pass

    if not logs:
        raise HTTPException(status_code=404, detail="Logs da sessão não encontrados")

    erros = _parsear_erros_mapping(logs)

    # Agrupar por tipo
    resumo: dict[str, int] = {}
    for e in erros:
        resumo[e["tipo"]] = resumo.get(e["tipo"], 0) + 1

    return {
        "sessao_id": sessao_id,
        "fonte": fonte,
        "total_erros": len(erros),
        "resumo_por_tipo": resumo,
        "erros": erros,
        "modo_estrito": os.environ.get("MAPPING_STRICT", "false").lower() == "true",
        "_dica": "Set MAPPING_STRICT=true em ambiente de teste para abortar a fase no primeiro erro de mapping (em vez de seguir tolerante).",
    }


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


# ─── SSE v2: executa PlaywrightAutomatorV2 a partir de prévia v2 ─────────


@app.get("/api/executar/v2/{sessao_id}")
async def executar_automacao_v2_sse(sessao_id: str, request: Request):
    """SSE que executa PlaywrightAutomatorV2 e transmite logs linha-a-linha.

    Usa o mesmo padrão (`_AutomacaoRunner`) do v1, mas o generator vem do
    schema v2 (modules.webapp_v2.executar_v2_como_generator).
    """
    from starlette.responses import StreamingResponse as _SR_v2
    from modules.webapp_v2 import executar_v2_como_generator

    async def gerador_sse_v2():
        # Verificar se já existe runner — reutilizar (ex.: F5 do navegador)
        existing = _automacao_runners.get(sessao_id)
        if existing and not existing.done:
            async for chunk in _sse_follow_runner(existing, sessao_id):
                yield chunk
            return

        # Criar generator + runner
        try:
            gen = executar_v2_como_generator(sessao_id)
        except Exception as e:
            yield f"data: ERRO_EXPORTAVEL::Falha ao iniciar generator v2: {e}\n\n"
            yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
            return

        runner = _AutomacaoRunner(sessao_id)
        _automacao_runners[sessao_id] = runner
        runner.start_thread(gen)

        async for chunk in _sse_follow_runner(runner, sessao_id):
            yield chunk

    return _SR_v2(
        gerador_sse_v2(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/executar/v3/{sessao_id}")
async def executar_automacao_v3_sse(sessao_id: str, request: Request):
    """SSE que executa o Aplicador puro v3 (core.aplicador.AplicadorPJECalc).

    Diferente dos endpoints v1/v2:
      - Lê PreviaCalculo (JSON v3 validado por Pydantic)
      - SEM auto-fix, SEM inferência: aplica EXATAMENTE o que está no JSON
      - Etapa 2C em desenvolvimento — fases 1, 5 (Verbas) e 7 (FGTS) implementadas;
        demais fases passam silenciosamente (placeholder)
    """
    from starlette.responses import StreamingResponse as _SR_v3
    import queue as _q
    import threading as _th
    from playwright.sync_api import sync_playwright

    async def gerador_sse_v3():
        # Carregar prévia v3 da sessão
        from database import SessionLocal
        _db = SessionLocal()
        try:
            calculo = RepositorioCalculo(_db).buscar_sessao(sessao_id)
            if not calculo:
                yield f"data: {json.dumps({'msg': 'Sessão não encontrada'})}\n\n"
                yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
                return
            dados_v3, warnings = _migrar_v2_para_v3(calculo)
            if warnings:
                for w in warnings[:5]:
                    yield f"data: {json.dumps({'msg': f'⚠ migração v2→v3: {w[:150]}'})}\n\n"
        finally:
            _db.close()

        msg_q: "_q.Queue[str]" = _q.Queue()
        done = _th.Event()

        def log_cb(msg: str) -> None:
            msg_q.put(msg)

        def runner():
            try:
                with sync_playwright() as pw:
                    browser = pw.firefox.launch(headless=True)
                    page = browser.new_page()
                    page.goto("http://localhost:9257/pjecalc/pages/principal.jsf", timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=15000)
                    # Click "Novo"
                    page.evaluate("""() => {
                        const links = [...document.querySelectorAll('a')];
                        for (const a of links) {
                            if ((a.textContent||'').trim() === 'Novo') { a.click(); return; }
                        }
                    }""")
                    page.wait_for_url("**/calculo*.jsf*", timeout=20000)
                    page.wait_for_load_state("networkidle", timeout=10000)

                    # Capturar conversation_id do click 'Novo'
                    conv_id = None
                    if "conversationId=" in page.url:
                        conv_id = page.url.split("conversationId=")[1].split("&")[0]
                        log_cb(f"  ℹ conv_id capturado: {conv_id}")

                    from core.aplicador import AplicadorPJECalc
                    aplicador = AplicadorPJECalc(page, log_cb=log_cb)
                    if conv_id:
                        aplicador._conv_id = conv_id
                    relatorio = aplicador.aplicar(dados_v3)
                    log_cb(f"✓ Aplicador concluído: sucesso={relatorio['sucesso']}")
                    if relatorio.get("fase_falhou"):
                        log_cb(f"⚠ Fase falhou: {relatorio['fase_falhou']}")
                    for m in relatorio.get("mensagens", []):
                        log_cb(m)
                    browser.close()
            except Exception as e:
                log_cb(f"✗ ERRO no runner v3: {e}")
            finally:
                done.set()

        # PreviaCalculo Pydantic
        from infrastructure.pjecalc_pages import PreviaCalculo
        try:
            # Serializar para dict + reconstruir model (validação completa)
            payload = {}
            for k, v in dados_v3.items():
                if isinstance(v, list):
                    payload[k] = [item.model_dump() if hasattr(item, "model_dump") else item for item in v]
                elif hasattr(v, "model_dump"):
                    payload[k] = v.model_dump()
                else:
                    payload[k] = v
            previa = PreviaCalculo(**payload)
            dados_v3 = previa  # passar Pydantic para o aplicador
        except Exception as e:
            yield f"data: {json.dumps({'msg': f'⚠ Validação PreviaCalculo: {e}'})}\n\n"
            yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"
            return

        thread = _th.Thread(target=runner, daemon=True)
        thread.start()

        yield f"data: {json.dumps({'msg': 'Aplicador v3 iniciado'})}\n\n"
        while not done.is_set() or not msg_q.empty():
            try:
                msg = msg_q.get(timeout=2)
                yield f"data: {json.dumps({'msg': msg})}\n\n"
            except _q.Empty:
                yield f"data: {json.dumps({'keepalive': True})}\n\n"

        yield f"data: {json.dumps({'msg': '[FIM DA EXECUÇÃO]'})}\n\n"

    return _SR_v3(
        gerador_sse_v3(),
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
    # CRÍTICO: também pop o runner cacheado para permitir nova execução fresca.
    # Sem isso, se o runner antigo está done=False (caso de stop sem cleanup),
    # qualquer novo /api/executar entra em "follow mode" e retorna logs do morto.
    _runner_removido = _automacao_runners.pop(sessao_id, None)
    return {
        "sucesso": True,
        "msg": f"Lock liberado para {sessao_id}",
        "runner_removido": _runner_removido is not None,
    }


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
