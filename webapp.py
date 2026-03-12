# webapp.py — Interface Web do Agente PJE-Calc
# Acréscimo ao Manual Técnico v1.0 — 2026
#
# Framework: FastAPI + Jinja2 (HTML) + SQLAlchemy (banco de dados)
#
# USO:
#   uvicorn webapp:app --reload --port 8000
#   Acesse: http://localhost:8000

from __future__ import annotations

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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config import OUTPUT_DIR, CLOUD_MODE
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
        "index.html",
        {"request": request, "processos": processos, "agora": datetime.now()},
    )


@app.get("/novo", response_class=HTMLResponse)
async def pagina_novo_calculo(request: Request):
    """Formulário para iniciar novo cálculo."""
    return templates.TemplateResponse(
        "novo_calculo.html", {"request": request}
    )


@app.post("/processar")
async def processar_sentenca(
    request: Request,
    background_tasks: BackgroundTasks,
    sentenca: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Recebe o arquivo de sentença, extrai dados e inicia o processamento.
    O processamento pesado (extração via LLM) roda em background.
    """
    sessao_id = str(uuid.uuid4())

    # Salvar arquivo temporariamente
    sufixo = Path(sentenca.filename or "sentenca.pdf").suffix.lower()
    tmp_dir = Path(tempfile.mkdtemp())
    tmp_path = tmp_dir / f"sentenca{sufixo}"

    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(sentenca.file, f)

    # Processar em background
    background_tasks.add_task(
        _tarefa_processar_sentenca,
        sessao_id=sessao_id,
        caminho=tmp_path,
        formato=sufixo,
    )

    return JSONResponse({
        "sessao_id": sessao_id,
        "status": "processando",
        "mensagem": "Sentença recebida. Processando extração de dados...",
        "url_status": f"/status/{sessao_id}",
        "url_previa": f"/previa/{sessao_id}",
    })


@app.get("/status/{sessao_id}")
async def verificar_status(sessao_id: str, db: Session = Depends(get_db)):
    """Retorna o status atual do processamento de uma sessão."""
    repo = RepositorioCalculo(db)
    calculo = repo.buscar_sessao(sessao_id)
    if not calculo:
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
        "previa.html",
        {
            "request": request,
            "sessao_id": sessao_id,
            "calculo": calculo,
            "processo": calculo.processo,
            "dados": dados,
            "verbas_mapeadas": verbas_mapeadas,
            "previa_texto": previa_texto,
            "campos_ausentes": dados.get("campos_ausentes", []),
            "alertas": dados.get("alertas", []),
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

    if CLOUD_MODE:
        mensagem = (
            "Prévia confirmada e salva. "
            "Para preencher o PJE-Calc, execute a automação local na máquina "
            "onde o PJE-Calc está instalado."
        )
    else:
        background_tasks.add_task(_tarefa_automacao_pjecalc, sessao_id=sessao_id)
        mensagem = "Prévia confirmada. O PJE-Calc será preenchido automaticamente."

    return JSONResponse({
        "sucesso": True,
        "mensagem": mensagem,
        "cloud_mode": CLOUD_MODE,
        "url_status": f"/status/{sessao_id}",
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
        "processo.html",
        {
            "request": request,
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
    if not calculo or not calculo.arquivo_pjc:
        raise HTTPException(status_code=404, detail="Arquivo .pjc não disponível")

    caminho = Path(calculo.arquivo_pjc)
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo .pjc não encontrado no servidor")

    return FileResponse(
        path=str(caminho),
        filename=caminho.name,
        media_type="application/xml",
    )


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
        "tem_previa": calculo.previa_texto is not None,
        "arquivo_pjc": calculo.arquivo_pjc,
        "criado_em": calculo.criado_em.isoformat() if calculo.criado_em else None,
        "confirmado_em": calculo.confirmado_em.isoformat() if calculo.confirmado_em else None,
    }


# ── Tarefas em Background ─────────────────────────────────────────────────────

def _tarefa_processar_sentenca(
    sessao_id: str,
    caminho: Path,
    formato: str,
) -> None:
    """
    Tarefa de background: lê, extrai e classifica dados da sentença.
    Persiste resultado no banco de dados.
    """
    db = SessionLocal()
    try:
        repo = RepositorioCalculo(db)

        # Fase 1: Ingestão
        resultado = ler_documento(caminho)
        texto = resultado["texto"]

        # Fase 2: Extração
        dados = extrair_dados_sentenca(texto, sessao_id=sessao_id)

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
        # Marcar como erro no banco
        try:
            calculo = db.query(Calculo).filter_by(sessao_id=sessao_id).first()
            if calculo:
                calculo.status = "erro"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        # Limpar arquivo temporário
        try:
            shutil.rmtree(caminho.parent, ignore_errors=True)
        except Exception:
            pass


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
