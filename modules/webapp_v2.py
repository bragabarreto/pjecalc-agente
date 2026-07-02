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
# Persistência: usa volume Docker permanente em produção, fallback /tmp em dev.
# /app/data/calculations e mapeado para /opt/pjecalc-data/calculations no host
# via docker-compose, sobrevivendo a restart de container (deploy).
import os as _os_v2

_CANDIDATOS = [
    _os_v2.environ.get("PREVIA_V2_DIR"),
    "/app/data/calculations/previa_v2",   # volume Docker em producao
    "data/calculations/previa_v2",         # path relativo (dev local)
    "/tmp/pjecalc_previa_v2",              # fallback efêmero
]
_STORE_DIR = None
for _c in _CANDIDATOS:
    if not _c:
        continue
    try:
        _p = Path(_c)
        _p.mkdir(parents=True, exist_ok=True)
        # Teste de escrita
        _t = _p / ".write_test"
        _t.write_text("ok")
        _t.unlink()
        _STORE_DIR = _p
        break
    except Exception:
        continue
if _STORE_DIR is None:
    _STORE_DIR = Path("/tmp/pjecalc_previa_v2")
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
logging.getLogger(__name__).info(f"webapp_v2: _STORE_DIR = {_STORE_DIR}")


def _save_previa(sessao_id: str, data: dict) -> None:
    _PREVIA_STORE[sessao_id] = data
    (_STORE_DIR / f"{sessao_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def registrar_calculo_db(sessao_id: str, data: dict, status: str = "previa_gerada",
                         confirmar: bool = False) -> bool:
    """#80-AI — registra a prévia na LISTA PRINCIPAL desde a GERAÇÃO.

    Requisito do usuário (02/07/2026, caso RODRIGO ROCHA 0000905-05): "as
    prévias geradas devem estar sempre disponíveis para posterior automação,
    a partir da geração da prévia" — antes, o Processo/Calculo só era criado
    na CONFIRMAÇÃO, e prévias recém-geradas ficavam apenas na seção "Prévias
    pendentes" (fora da tabela principal de processos).

    Chamado em: (a) fim da Etapa 2 da extração IA e (b) /processar/v2, ambos
    com status="previa_gerada" (badge "Prévia" na home); (c) confirmação, com
    confirmar=True (atualiza dados_json + status + confirmado_em).
    Best-effort: nunca levanta.
    """
    try:
        from datetime import datetime
        from infrastructure.database import SessionLocal, Processo, Calculo
        proc = data.get("processo") if isinstance(data.get("processo"), dict) else {}
        numero = proc.get("numero_processo")
        if not numero:
            return False

        def _nome(v):
            if isinstance(v, dict):
                return v.get("nome") or ""
            return str(v or "")
        reclamante = _nome(proc.get("reclamante"))
        reclamado = _nome(proc.get("reclamado"))

        db = SessionLocal()
        try:
            proc_db = db.query(Processo).filter(Processo.numero_processo == numero).first()
            if not proc_db:
                proc_db = Processo(numero_processo=numero, reclamante=reclamante,
                                   reclamado=reclamado)
                db.add(proc_db)
                db.flush()
            calc = db.query(Calculo).filter(Calculo.sessao_id == sessao_id).first()
            if not calc:
                calc = Calculo(
                    sessao_id=sessao_id,
                    processo_id=proc_db.id,
                    status=status,
                    dados_json=json.dumps(data),
                    confirmado_em=datetime.utcnow() if confirmar else None,
                )
                db.add(calc)
            else:
                calc.dados_json = json.dumps(data)
                if confirmar:
                    calc.status = status
                    if not calc.confirmado_em:
                        calc.confirmado_em = datetime.utcnow()
                # sem confirmar: não rebaixar status já avançado
            db.commit()
            return True
        finally:
            db.close()
    except Exception as _e:
        logger.warning("registrar_calculo_db(%s, status=%s): %s", sessao_id, status, _e)
        return False


def listar_previas_pendentes(sessao_ids_confirmados: set | None = None,
                             limit: int = 30) -> list[dict]:
    """Lista prévias v2 SALVAS mas AINDA NÃO CONFIRMADAS (sem registro no banco).

    Fluxo de extração IA (/novo/ia): a prévia é gravada como arquivo
    `<sessao>.json` no _STORE_DIR ANTES de ser confirmada. Só ao confirmar é
    criado um `Calculo` no banco (que passa a aparecer na home). Prévias geradas
    e não confirmadas ficavam "invisíveis" — o usuário só as reencontrava se
    tivesse guardado a URL. Esta função enumera esses rascunhos para exibi-los
    numa seção "Prévias pendentes" da home.

    `sessao_ids_confirmados`: conjunto de sessao_ids que JÁ têm Calculo no banco
    (passado pela home) — usados para EXCLUIR da lista de pendentes.
    """
    confirmados = sessao_ids_confirmados or set()
    pend: list[dict] = []
    try:
        arquivos = sorted(
            [p for p in _STORE_DIR.glob("*.json")
             if not p.name.endswith(".extracao.json")],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
    except Exception:
        return []
    for p in arquivos:
        sid = p.stem
        if sid in confirmados:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        proc = d.get("processo") if isinstance(d.get("processo"), dict) else {}
        numero = proc.get("numero_processo") or "—"

        def _nome(v):
            if isinstance(v, dict):
                return v.get("nome") or "—"
            return str(v or "—")
        from datetime import datetime as _dt
        try:
            mtime = _dt.fromtimestamp(p.stat().st_mtime)
        except Exception:
            mtime = None
        pend.append({
            "sessao_id": sid,
            "numero_processo": numero,
            "reclamante": _nome(proc.get("reclamante")),
            "reclamado": _nome(proc.get("reclamado")),
            "atualizado_em": mtime,
            "url_previa": f"/previa/v2/{sid}",
        })
        if len(pend) >= limit:
            break
    return pend


def _save_snapshot_extracao(sessao_id: str, previa: dict) -> None:
    """Aprendizado FATIA 3 — grava as assinaturas das verbas EXTRAÍDAS (Etapa 2,
    antes da edição do usuário), para comparar com a prévia confirmada na
    captura. Best-effort: nunca levanta."""
    try:
        from learning.estrategia_parametrizacao import snapshot_assinaturas
        snap = snapshot_assinaturas(previa)
        (_STORE_DIR / f"{sessao_id}.extracao.json").write_text(
            json.dumps(snap, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _load_snapshot_extracao(sessao_id: str) -> dict | None:
    """Lê o snapshot de assinaturas da extração (FATIA 3). None se ausente."""
    try:
        p = _STORE_DIR / f"{sessao_id}.extracao.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _load_previa(sessao_id: str) -> dict | None:
    """Carrega prévia v2 priorizando memória → arquivo → DB (fallback).

    O fallback ao DB existe porque o volume de arquivos (_STORE_DIR) pode
    ser perdido em rebuilds/restarts, enquanto Calculo.dados_json no DB
    persiste no PostgreSQL/SQLite. Sem isso, processos antigos retornavam
    404 ao clicar em "Ver Prévia".
    """
    if sessao_id in _PREVIA_STORE:
        return _PREVIA_STORE[sessao_id]
    fp = _STORE_DIR / f"{sessao_id}.json"
    if fp.exists():
        data = json.loads(fp.read_text(encoding="utf-8"))
        _PREVIA_STORE[sessao_id] = data
        return data
    # Fallback: tentar recuperar do DB (Calculo.dados_json)
    try:
        from infrastructure.database import SessionLocal, Calculo as _Calc
        db = SessionLocal()
        try:
            calc = db.query(_Calc).filter_by(sessao_id=sessao_id).first()
            if calc and calc.dados_json:
                data = json.loads(calc.dados_json)
                # Reidrata cache em memória e arquivo (best-effort)
                _PREVIA_STORE[sessao_id] = data
                try:
                    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass  # se filesystem read-only, ignorar
                return data
        finally:
            db.close()
    except Exception as _e:
        logging.getLogger(__name__).warning(
            f"_load_previa: falha no fallback DB para {sessao_id}: {_e}"
        )
    return None


# ─── POST /processar/v2 ────────────────────────────────────────────────────


@router_v2.post("/processar/v2")
async def processar_v2(payload: dict):
    """Recebe JSON v2 do Projeto Claude externo + cria sessão.

    Body esperado: o JSON da prévia conforme schema v2.0
    Retorna: {sessao_id, redirect_url}
    """
    try:
        # Normalizar legacy → canônico antes de validar
        from modules.json_normalizer import normalize_v2_json
        payload = normalize_v2_json(payload)
        # Validar via Pydantic (sanity check inicial)
        previa = PreviaCalculoV2.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Schema v2 inválido: {e}")

    sessao_id = str(uuid.uuid4())
    _dump = previa.model_dump()
    _save_previa(sessao_id, _dump)
    # #80-AI: entrar na lista principal de processos DESDE a geração
    registrar_calculo_db(sessao_id, _dump, status="previa_gerada")

    return JSONResponse({
        "sessao_id": sessao_id,
        "redirect_url": f"/previa/v2/{sessao_id}",
        "completude": previa.meta.validacao.completude,
        "campos_faltantes": previa.meta.validacao.campos_faltantes,
        "avisos": previa.meta.validacao.avisos,
    })


# ─── GET /previa/v2/{sessao_id} ────────────────────────────────────────────


@router_v2.get("/instrucoes/v2/{sessao_id}", response_class=HTMLResponse)
async def instrucoes_v2(sessao_id: str, request: Request):
    """Página que acompanha a automação v2 via SSE.

    Conecta-se a /api/executar/v2/{sessao_id} e exibe os logs em tempo real.
    """
    html = f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><title>Automação v2 — {sessao_id[:8]}</title>
<style>
body {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; max-width: 1100px; margin: 1.5rem auto; padding: 0 1rem; }}
h1 {{ font-size: 1.1rem; }}
.status {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 0.85rem; font-weight: 600; }}
.status.running {{ background: #fff3cd; color: #856404; }}
.status.done {{ background: #d4edda; color: #155724; }}
.status.error {{ background: #f8d7da; color: #721c24; }}
#logs {{ background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; height: 60vh; overflow-y: auto; font-size: 0.82rem; line-height: 1.4; }}
.log-line {{ white-space: pre-wrap; word-break: break-word; }}
.log-line.warn {{ color: #ffd166; }}
.log-line.err {{ color: #ef476f; }}
.log-line.ok {{ color: #06d6a0; }}
button {{ padding: 6px 12px; font-size: 0.9rem; cursor: pointer; }}
.download-pjc {{ display:inline-block; margin-top:1rem; padding:10px 20px; background:#198754; color:#fff; text-decoration:none; border-radius:6px; font-weight:600; font-size:1rem; }}
.download-pjc:hover {{ background:#157347; }}
</style></head><body>
<h1>Automação v2 <span id="status" class="status running">⏳ iniciando…</span></h1>
<p>Sessão: <code>{sessao_id}</code> · <a href="/previa/v2/{sessao_id}">← voltar à prévia</a></p>
<div id="painel-area"></div>
<div id="logs"></div>
<div id="download-area"></div>
<p style="margin-top:1rem;">
  <button onclick="window.location.reload()">↻ Reconectar</button>
  <button onclick="fetch('/api/parar/{sessao_id}', {{method:'POST'}}).then(r=>r.json()).then(d=>alert(d.msg))">⏹ Parar</button>
  <a href="/api/erros-mapping/{sessao_id}" target="_blank"><button type="button">📋 Erros de mapping</button></a>
</p>
<script>
const logs = document.getElementById('logs');
const status = document.getElementById('status');
const downloadArea = document.getElementById('download-area');
const es = new EventSource('/api/executar/v2/{sessao_id}');
es.onmessage = (e) => {{
  let txt = e.data;
  try {{ const j = JSON.parse(txt); txt = j.msg || txt; }} catch(_) {{}}

  if (txt.startsWith('DOWNLOAD_LINK_CALC:')) {{
    const url = txt.split('DOWNLOAD_LINK_CALC:')[1].trim();
    downloadArea.innerHTML = '<a class="download-pjc" href="' + url + '">⬇ Baixar .PJC</a>';
    return;
  }}

  if (txt.startsWith('[MANUAL_EDIT_REQUIRED]')) {{
    try {{
      const payload = JSON.parse(txt.slice('[MANUAL_EDIT_REQUIRED]'.length).trim());
      exibirPainelEdicaoManual(payload);
    }} catch(e) {{ console.error('parse MANUAL_EDIT_REQUIRED', e); }}
    return;
  }}

  const div = document.createElement('div');
  div.className = 'log-line';
  if (/✗|ERRO|FALHA|Traceback/.test(txt)) {{ div.classList.add('err'); }}
  else if (/⚠|⏳/.test(txt)) {{ div.classList.add('warn'); }}
  else if (/✓|PJC_GERADO|concluí/i.test(txt)) {{ div.classList.add('ok'); }}
  div.textContent = txt;
  logs.appendChild(div);
  logs.scrollTop = logs.scrollHeight;
  if (txt.includes('[FIM DA EXECUÇÃO')) {{
    status.textContent = txt.includes('ERRO') ? '❌ erro' : '✓ concluído';
    status.className = 'status ' + (txt.includes('ERRO') ? 'error' : 'done');
    es.close();
  }}
}};
es.onerror = () => {{ status.textContent = '⚠ desconectado'; status.className = 'status error'; }};

function escapeHtml(s) {{ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function escapeAttr(s) {{ return escapeHtml(s).replace(/"/g,'&quot;'); }}

function exibirPainelEdicaoManual(payload) {{
  if (document.getElementById('painel-edicao-manual')) return;
  const url = payload.url || '#';
  const pendencias = payload.pendencias || [];
  const detalhes = payload.detalhes || [];
  const SESSAO_ID = '{sessao_id}';
  const painel = document.createElement('div');
  painel.id = 'painel-edicao-manual';
  painel.style = 'margin:16px 0; padding:16px; border:2px solid #d97706; background:#fffbeb; border-radius:8px; font-family:system-ui,sans-serif;';
  painel.innerHTML =
    '<h3 style="margin-top:0; color:#92400e;">⚠ Liquidação bloqueada — edição manual necessária</h3>' +
    '<p style="margin:8px 0;">A automação preencheu todos os campos do cálculo, mas a liquidação não pôde ser concluída após 2 tentativas. <strong>Esta é a última alternativa</strong>: abra o link abaixo para corrigir <em>apenas os parâmetros pendentes</em> diretamente no PJE-Calc Cidadão. Todos os demais dados já estão salvos.</p>' +
    '<div style="margin:12px 0;"><strong>Pendências reportadas pelo PJE-Calc:</strong><ul style="margin:6px 0 0 24px;">' +
    pendencias.map(p => '<li><code>' + escapeHtml(p) + '</code></li>').join('') +
    (detalhes.length ? '<li><details><summary>Detalhes (' + detalhes.length + ')</summary><ul>' + detalhes.map(d => '<li><small>' + escapeHtml(d) + '</small></li>').join('') + '</ul></details></li>' : '') +
    '</ul></div>' +
    '<a href="' + escapeAttr(url) + '" target="_blank" rel="noopener" style="display:inline-block; padding:10px 16px; background:#d97706; color:#fff; text-decoration:none; border-radius:6px; font-weight:700; margin:8px 0;">🔗 Abrir PJE-Calc para edição manual (nova aba)</a>' +
    '<hr style="margin:16px 0; border-color:#fde68a;">' +
    '<h4 style="margin-bottom:8px;">Após editar e liquidar manualmente:</h4>' +
    '<p style="font-size:0.92em; color:#57534e;">Descreva em linguagem natural quais campos você alterou no PJE-Calc para que a liquidação fosse possível. Essa descrição alimenta o aprendizado do sistema e evita que o mesmo erro ocorra em cálculos futuros.</p>' +
    '<textarea id="textarea-correcao-manual" rows="5" style="width:100%; padding:8px; border:1px solid #d4d4d8; border-radius:4px; font-family:inherit;" placeholder="Ex.: Mudei a alíquota do honorário sucumbencial de vazio para 10%. Marquei FGTS Multa 40%. Preenchi a data de vencimento como 26/11/2025."></textarea>' +
    '<div style="margin-top:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;">' +
    (payload.snapshot_capturado ? '<button id="btn-capturar-diff" type="button" style="padding:8px 16px; background:#15803d; color:#fff; border:0; border-radius:6px; font-weight:600; cursor:pointer;">🔄 Capturar mudanças do PJE-Calc (automático)</button>' : '') +
    '<button id="btn-salvar-correcao-manual" type="button" style="padding:8px 16px; background:#2563eb; color:#fff; border:0; border-radius:6px; font-weight:600; cursor:pointer;">Salvar descrição (texto livre)</button>' +
    '<span id="status-correcao-manual" style="color:#57534e; font-size:0.92em;"></span>' +
    '</div>' +
    '<div id="diff-resultado" style="margin-top:10px; font-size:0.9em;"></div>' +
    '<hr style="margin:16px 0; border-color:#fde68a;">' +
    '<h4 style="margin-bottom:8px;">📎 Anexar .PJC liquidado (após exportar do PJE-Calc)</h4>' +
    '<p style="font-size:0.92em; color:#57534e; margin:6px 0;">Quando você corrigir + liquidar + exportar o .PJC no PJE-Calc, faça upload aqui. ' +
    'O sistema valida automaticamente se o arquivo pertence a este processo e marca o cálculo como concluído.</p>' +
    '<form id="form-upload-pjc" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">' +
    '  <input type="file" id="input-pjc" accept=".PJC,.pjc,application/zip" style="padding:6px; border:1px solid #d4d4d8; border-radius:4px;">' +
    '  <button id="btn-upload-pjc" type="button" style="padding:8px 16px; background:#7c3aed; color:#fff; border:0; border-radius:6px; font-weight:600; cursor:pointer;">⬆ Enviar .PJC</button>' +
    '  <span id="status-upload-pjc" style="color:#57534e; font-size:0.92em;"></span>' +
    '</form>';
  document.getElementById('painel-area').appendChild(painel);
  painel.scrollIntoView({{behavior:'smooth', block:'start'}});
  const btnDiff = document.getElementById('btn-capturar-diff');
  if (btnDiff) {{
    btnDiff.addEventListener('click', async () => {{
      const st = document.getElementById('status-correcao-manual');
      const out = document.getElementById('diff-resultado');
      btnDiff.disabled = true;
      st.style.color = '#57534e';
      st.textContent = '🔄 Capturando estado do PJE-Calc (~15s)…';
      try {{
        const r = await fetch('/api/correcao_manual_diff/' + SESSAO_ID, {{method:'POST'}});
        const d = await r.json();
        if (r.ok) {{
          const diff = d.diff || {{}};
          const parts = [];
          if (diff.verbas_adicionadas?.length) parts.push('<strong>Verbas adicionadas (' + diff.verbas_adicionadas.length + '):</strong><ul>' + diff.verbas_adicionadas.map(x => '<li><code>' + escapeHtml(x) + '</code></li>').join('') + '</ul>');
          if (diff.verbas_removidas?.length) parts.push('<strong>Verbas removidas (' + diff.verbas_removidas.length + '):</strong><ul>' + diff.verbas_removidas.map(x => '<li><code>' + escapeHtml(x) + '</code></li>').join('') + '</ul>');
          if (diff.reflexos_adicionados?.length) parts.push('<strong>Reflexos ativados (' + diff.reflexos_adicionados.length + '):</strong> ' + diff.reflexos_adicionados.map(escapeHtml).join(', '));
          if (diff.reflexos_removidos?.length) parts.push('<strong>Reflexos desativados (' + diff.reflexos_removidos.length + '):</strong> ' + diff.reflexos_removidos.map(escapeHtml).join(', '));
          if (diff.valor_total_antes !== diff.valor_total_depois) parts.push('<strong>Total:</strong> ' + escapeHtml(diff.valor_total_antes||'-') + ' → ' + escapeHtml(diff.valor_total_depois||'-'));
          out.innerHTML = parts.length ? parts.join('<br>') : '<em>Nenhuma alteração detectada na listagem.</em>';
          st.textContent = '✓ ' + (d.msg || 'Capturado.');
          st.style.color = '#15803d';
        }} else {{
          st.textContent = 'Erro: ' + (d.detail || r.status);
          st.style.color = '#b91c1c';
          btnDiff.disabled = false;
        }}
      }} catch (e) {{
        st.textContent = 'Erro de rede: ' + e.message;
        st.style.color = '#b91c1c';
        btnDiff.disabled = false;
      }}
    }});
  }}
  document.getElementById('btn-salvar-correcao-manual').addEventListener('click', async () => {{
    const ta = document.getElementById('textarea-correcao-manual');
    const st = document.getElementById('status-correcao-manual');
    const btn = document.getElementById('btn-salvar-correcao-manual');
    const desc = (ta.value||'').trim();
    if (desc.length < 10) {{ st.textContent='Descrição muito curta (mínimo 10 caracteres).'; st.style.color='#b91c1c'; return; }}
    btn.disabled=true; st.style.color='#57534e'; st.textContent='Enviando ao Learning Engine…';
    try {{
      const r = await fetch('/api/correcao_manual/' + SESSAO_ID, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{descricao: desc}})}});
      const d = await r.json();
      if (r.ok) {{ st.textContent = '✓ ' + (d.msg || 'Correções registradas.'); st.style.color='#15803d'; ta.disabled=true; }}
      else {{ st.textContent = 'Erro: ' + (d.detail || r.status); st.style.color='#b91c1c'; btn.disabled=false; }}
    }} catch(e) {{ st.textContent='Erro de rede: '+e.message; st.style.color='#b91c1c'; btn.disabled=false; }}
  }});

  // ─── Upload manual de PJC (após correção manual no PJE-Calc) ────────
  const btnUpload = document.getElementById('btn-upload-pjc');
  btnUpload.addEventListener('click', async () => {{
    const inp = document.getElementById('input-pjc');
    const st = document.getElementById('status-upload-pjc');
    if (!inp.files || inp.files.length === 0) {{
      st.textContent = 'Selecione um arquivo .PJC primeiro.';
      st.style.color = '#b91c1c';
      return;
    }}
    const file = inp.files[0];
    if (file.size > 50 * 1024 * 1024) {{
      st.textContent = 'Arquivo muito grande (>50MB).';
      st.style.color = '#b91c1c';
      return;
    }}
    btnUpload.disabled = true;
    st.style.color = '#57534e';
    st.textContent = '⬆ Enviando ' + file.name + ' (' + Math.round(file.size/1024) + ' KB)…';
    try {{
      const fd = new FormData();
      fd.append('pjc', file);
      const r = await fetch('/api/upload-pjc/' + SESSAO_ID, {{method:'POST', body: fd}});
      const d = await r.json();
      if (r.ok) {{
        st.innerHTML = '✓ PJC anexado e validado. <a href="' + d.download + '">Baixar</a> · ' +
                       (d.tamanho_bytes ? Math.round(d.tamanho_bytes/1024) + ' KB' : '');
        st.style.color = '#15803d';
        inp.disabled = true;
        // Atualizar área de download principal
        if (downloadArea) {{
          downloadArea.innerHTML = '<a class="download-pjc" href="' + d.download + '">⬇ Baixar .PJC (anexado manualmente)</a>';
        }}
      }} else {{
        let msg = '';
        if (typeof d.detail === 'string') msg = d.detail;
        else if (d.detail && d.detail.msg) msg = d.detail.msg;
        else msg = JSON.stringify(d.detail || d).slice(0, 200);
        st.textContent = '❌ ' + msg;
        st.style.color = '#b91c1c';
        btnUpload.disabled = false;
      }}
    }} catch (e) {{
      st.textContent = 'Erro de rede: ' + e.message;
      st.style.color = '#b91c1c';
      btnUpload.disabled = false;
    }}
  }});
}}
</script>
</body></html>"""
    return HTMLResponse(html)


@router_v2.get("/previa/v2/{sessao_id}", response_class=HTMLResponse)
async def previa_v2_view(sessao_id: str, request: Request):
    """Renderiza template previa_v2.html com os dados da sessão."""
    data = _load_previa(sessao_id)
    if not data:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Starlette ≥ 0.27: assinatura nova (request, name, context).
    # A antiga (name, {"request": ...}) causa "unhashable type: 'dict'".
    return templates.TemplateResponse(
        request,
        "previa_v2.html",
        {
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


def _limpar_cartao_ponto_vazio(payload: dict) -> dict:
    """Se cartao_de_ponto for um dict sem dados úteis (sem datas, sem jornada,
    sem escala e sem overrides), descarta para None.

    Causa raiz: a UI da prévia v2 inicializa cartao_de_ponto como
    {preenchimento: 'LIVRE'} no boot, mesmo quando o JSON original tinha null.
    Ao confirmar, Pydantic exige data_inicial/data_final → erro 422.
    Esta limpeza idempotente desfaz o objeto vazio antes de validar.
    """
    cp = payload.get("cartao_de_ponto")
    if not isinstance(cp, dict):
        return payload
    # Indicadores de que o usuário realmente preencheu cartão de ponto
    tem_datas = bool(cp.get("data_inicial")) or bool(cp.get("data_final"))
    prog = cp.get("programacao_semanal") or {}
    tem_programacao = isinstance(prog, dict) and any(
        (d or {}).get("turnos") for d in prog.values() if isinstance(d, dict)
    )
    esc = cp.get("escala")
    tem_escala = isinstance(esc, dict) and (
        bool(esc.get("inicio")) or bool(esc.get("jornadas"))
    )
    tem_overrides = bool(cp.get("ocorrencias_override"))
    if not (tem_datas or tem_programacao or tem_escala or tem_overrides):
        payload["cartao_de_ponto"] = None
    return payload


@router_v2.post("/api/previa/v2/{sessao_id}/confirmar")
async def confirmar_previa(sessao_id: str, payload: dict):
    """Confirma prévia + valida + libera para automação.

    Em sucesso, salva e marca como pronta para automação.
    Em erro, retorna 422 com lista de pendências.
    """
    # CRÍTICO (22/05/2026): aplicar normalize_v2_json AQUI também — não só em
    # /processar/v2. Sem isso, edições do usuário ou re-submissões podem
    # introduzir inconsistências que o JSF rejeita (ex.: prescricao_quinquenal
    # marcada quando período <5 anos, causando erro de save Fase 2 e
    # propagando falhas para todas as fases subsequentes).
    from modules.json_normalizer import normalize_v2_json
    payload = normalize_v2_json(payload)
    payload = _limpar_cartao_ponto_vazio(payload)
    try:
        previa = PreviaCalculoV2.model_validate(payload)
    except Exception as e:
        # #80-AE: erro humanizado — o que deu errado + como corrigir (por verba).
        from modules.erro_previa_humanizer import humanizar_validation_error
        raise HTTPException(
            status_code=422,
            detail={"humanizado": humanizar_validation_error(e, payload),
                    "mensagem": f"Validação Pydantic falhou: {e}"},
        )

    if previa.meta.validacao.completude != "OK":
        from modules.erro_previa_humanizer import humanizar_incompleta
        raise HTTPException(
            status_code=422,
            detail={
                "completude": previa.meta.validacao.completude,
                "campos_faltantes": previa.meta.validacao.campos_faltantes,
                "avisos": previa.meta.validacao.avisos,
                "humanizado": humanizar_incompleta(
                    previa.meta.validacao.campos_faltantes,
                    previa.meta.validacao.avisos),
            },
        )

    # Salvar como confirmada
    data = previa.model_dump()
    data["meta"]["confirmada"] = True
    _save_previa(sessao_id, data)

    # Criar/atualizar registro no DB para que marcar_exportado funcione ao final
    # da automação. Com o registro na GERAÇÃO (#80-AI), aqui geralmente já
    # existe — atualiza status/dados/confirmado_em.
    registrar_calculo_db(sessao_id, data, status="confirmado", confirmar=True)

    return {
        "status": "confirmada",
        "sessao_id": sessao_id,
        "redirect_url": f"/instrucoes/v2/{sessao_id}",
        "sse_url": f"/api/executar/v2/{sessao_id}",
    }


# ─── Generator que roda PlaywrightAutomatorV2 e yields logs ───────────────


def executar_v2_como_generator(sessao_id: str):
    """Generator que roda a automação v2 e yields cada linha de log.

    Compatível com a infra `_AutomacaoRunner` do webapp.py: cada `yield`
    produz uma linha de log que vai para SSE.
    """
    import queue
    import threading
    import traceback

    data = _load_previa(sessao_id)
    if not data:
        yield f"ERRO: sessão {sessao_id} não encontrada"
        return

    # #80-X (REGINALDO 0001876-87, 30/06/2026): a re-execução validava o JSON
    # CRU, sem o normalize/limpeza que a confirmação aplica (linhas 518-519).
    # Se o JSON salvo tiver cartao_de_ponto = {ocorrencias_override: []} (objeto
    # vazio que a UI da prévia inicializa no boot), Pydantic exige
    # data_inicial/data_final → "validação Pydantic falhou" e a automação nem
    # inicia. Aplicar a MESMA limpeza/normalização aqui garante que a execução
    # valide exatamente como a confirmação — re-execuções sempre coerentes.
    try:
        from modules.json_normalizer import normalize_v2_json
        data = normalize_v2_json(data)
    except Exception as _e:
        yield f"  ⚠ normalize_v2_json (não-fatal): {_e}"
    data = _limpar_cartao_ponto_vazio(data)

    # Validar antes de iniciar
    try:
        previa = PreviaCalculoV2.model_validate(data)
    except Exception as e:
        # #80-AE: explicitar o que deu errado + como corrigir (por verba), em
        # vez de despejar o erro Pydantic cru no log SSE.
        from modules.erro_previa_humanizer import humanizar_validation_error
        h = humanizar_validation_error(e, data)
        yield f"❌ {h['titulo']}:"
        for it in h["erros"]:
            _ent = it.get("entidade") or "Prévia"
            yield f"  • {_ent}: {it.get('o_que', '')}"
            yield f"    → Como corrigir: {it.get('como_corrigir', '')}"
        yield "  ℹ Abra a prévia, corrija os itens acima e confirme novamente."
        return

    if previa.meta.validacao.completude != "OK":
        from modules.erro_previa_humanizer import humanizar_incompleta
        h = humanizar_incompleta(previa.meta.validacao.campos_faltantes,
                                 previa.meta.validacao.avisos)
        yield f"❌ {h['titulo']}:"
        for it in h["erros"][:20]:
            yield f"  • {it.get('o_que', '')}"
            yield f"    → {it.get('como_corrigir', '')}"
        yield "  ℹ Abra a prévia, preencha as pendências acima e confirme novamente."
        return

    # Importar o automator v2
    try:
        from modules.playwright_v2 import PlaywrightAutomatorV2
    except Exception as e:
        yield f"ERRO: PlaywrightAutomatorV2 indisponível: {e}"
        return

    # Queue para passar logs do thread do bot para o generator
    log_q: queue.Queue = queue.Queue()
    SENTINEL = object()
    pjc_path_holder: dict = {}

    def log_fn(msg: str) -> None:
        log_q.put(msg)

    def _executar_bot() -> None:
        try:
            with PlaywrightAutomatorV2(previa, log_fn=log_fn, sessao_id=sessao_id) as bot:
                pjc = bot.run()
                pjc_path_holder["pjc"] = pjc
                if pjc:
                    log_q.put(f"PJC_GERADO:{pjc}")
        except Exception as e:
            log_q.put(f"ERRO na automação v2: {e}")
            log_q.put(traceback.format_exc())
        finally:
            log_q.put(SENTINEL)

    t = threading.Thread(target=_executar_bot, daemon=True)
    t.start()

    # ⚠ Log persistido (fix THAÍS 10/06/2026): sem arquivo, o diagnóstico
    # pós-falha fica inferencial (o SSE só existe no stream do browser).
    # Grava cada linha em <store>/logs/<sessao_id>_automation.log.
    _log_file = None
    try:
        _logs_dir = _STORE_DIR / "logs"
        _logs_dir.mkdir(parents=True, exist_ok=True)
        _log_file = open(_logs_dir / f"{sessao_id}_automation.log", "a", encoding="utf-8")
        from datetime import datetime as _dt_log
        _log_file.write(f"\n===== RUN {_dt_log.now().isoformat()} =====\n")
    except Exception:
        _log_file = None

    def _persist(linha: str) -> None:
        if _log_file is not None:
            try:
                _log_file.write(linha + "\n")
                _log_file.flush()
            except Exception:
                pass

    try:
        for _hdr in (
            f"══ Automação v2 iniciada para sessão {sessao_id} ══",
            f"  Processo: {previa.processo.numero_processo}",
            f"  Reclamante: {previa.processo.reclamante.nome}",
            f"  Verbas: {len(previa.verbas_principais)} principais + "
            f"{sum(len(v.reflexos) for v in previa.verbas_principais)} reflexos",
        ):
            _persist(_hdr)
            yield _hdr

        # Drenar a queue
        while True:
            try:
                item = log_q.get(timeout=15)
            except queue.Empty:
                yield "⏳ Processando…"
                continue
            if item is SENTINEL:
                break
            _persist(str(item))
            yield item

        _persist("[FIM DA EXECUÇÃO]")
        yield "[FIM DA EXECUÇÃO]"
    finally:
        if _log_file is not None:
            try:
                _log_file.close()
            except Exception:
                pass


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
