# Revisão Geral de Código — 08/04/2026

Revisão sistemática do codebase pjecalc-agente para identificar e corrigir falhas que comprometem a funcionalidade.

---

## Correções já aplicadas

### Commit `056d422` — Desacoplamento SSE ↔ Automação

**Causa raiz**: cada reconexão SSE matava o Playwright e reiniciava a automação do zero, criando múltiplas instâncias paralelas de Firefox (~500MB cada).

| Arquivo | Mudança |
|---------|---------|
| `webapp.py` | Classe `_AutomacaoRunner` — automação roda em thread independente do SSE |
| `webapp.py` | `_sse_follow_runner()` — reconexões fazem "follow" com replay de logs (padrão position-based com `threading.Condition`) |
| `webapp.py` | Locks e cleanup gerenciados pelo runner, não pelo SSE generator |
| `templates/instrucoes.html` | Frontend limpa log antes de reconectar (backend faz replay completo) |

### Commit `fbcd5ac` — 8 falhas da revisão geral

| # | Sev. | Arquivo | Problema | Correção |
|---|------|---------|----------|----------|
| 1 | CRÍTICO | `webapp.py` | Locks nunca liberados quando Tomcat timeout ou exceção pré-runner | Adicionado `finally` block com flag `_runner_started` |
| 2 | CRÍTICO | `playwright_pjecalc.py:1585` | `_clicar_salvar()` ignorava retorno de `_clicar_e_aguardar()` — sempre retornava True | Agora propaga `return _clicar_e_aguardar(sel)` |
| 3 | ALTO | `webapp.py` + `instrucoes.html` | Botão "Parar" só fechava SSE no browser; runner continuava em background | Endpoint `POST /api/parar/{sessao_id}` + frontend chama o servidor |
| 4 | ALTO | `webapp.py` | Runners finalizados nunca removidos do dict (memory leak) | `_limpar_runners_antigos()` remove runners >5min, chamado oportunisticamente |
| 5 | ALTO | `webapp.py:1212` | `SessionLocal()` sem `finally` — sessão DB vazava em exceção | `_db_status.close()` agora em `finally` block |
| 6 | MÉDIO | `playwright_pjecalc.py:2541` | Detecção de erro H2 buscava "500" em texto (falsos positivos com preços/IDs) | Substituído por markers específicos: `HTTP Status 500`, `javax.faces`, `java.lang.Exception` |
| 7 | MÉDIO | `extraction.py:2681-2756` | Inconsistências críticas detectadas mas nunca adicionadas aos alertas | `alertas.extend()` das inconsistências antes de `dados["alertas"] = alertas` |
| 8 | MÉDIO | `previa.html` + `novo_calculo.html` | Reload 300ms perdia edições; formulário de upload não restaurado em erro | Delay 1200ms; botão "Tentar novamente" restaura o formulário |

---

## Correções pendentes

### P1 — JSON corrompido passa silenciosamente (CRÍTICO) ✅ CORRIGIDO
- **Arquivo**: `modules/extraction.py:54-107`
- **Problema**: `_limpar_e_parsear_json()` tem 6 camadas de fallback com `except: pass`. A camada 5 auto-fecha chaves/colchetes em JSON truncado, podendo gerar dados semanticamente errados (ex: `verba_principal_ref: null`).
- **Impacto**: dados corrompidos passam para a automação sem nenhum alerta.
- **Correção proposta**: adicionar log de warning quando fallbacks são usados; validar campos obrigatórios no JSON parseado; marcar confiança como "baixa" quando auto-repair é necessário.

### P2 — `[FIM DA EXECUÇÃO]` inalcançável em GeneratorExit (ALTO) ✅ CORRIGIDO
- **Arquivo**: `modules/playwright_pjecalc.py:7605-7616`
- **Problema**: quando SSE desconecta, `except GeneratorExit` faz `return` sem nunca chegar ao `yield "[FIM DA EXECUÇÃO]"`. Com o runner desacoplado, o impacto é menor (runner já seta `done=True` no `finally`), mas o generator pode não limpar o browser corretamente.
- **Correção proposta**: mover cleanup e sinalização para o `finally` block do generator.

### P3 — OCR com baixa confiança não bloqueia (ALTO) ✅ CORRIGIDO
- **Arquivo**: `modules/ingestion.py:114-118`
- **Problema**: quando confiança OCR é baixa, um alerta é adicionado mas processamento continua com texto degradado → LLM extrai dados incorretos.
- **Correção proposta**: se confiança média < threshold, marcar `_ocr_baixa_confianca=True` e propagar para extração, que deve tratar como `_erro_ia` ou no mínimo baixar a confiança geral.

### P4 — Pool de conexões DB não configurado (MÉDIO) ✅ CORRIGIDO
- **Arquivo**: `infrastructure/database.py:33`
- **Correção**: `pool_pre_ping=True` para todos os engines; PostgreSQL também com `pool_size=10, max_overflow=20, pool_recycle=3600`.

### P5 — `verba_principal_ref` órfã não validada (MÉDIO) ✅ CORRIGIDO
- **Arquivo**: `modules/extraction.py` — `_validar_e_completar()`
- **Correção**: loop valida que toda verba reflexa com `verba_principal_ref` tem a principal correspondente na lista. Gera alerta se órfã.

### P6 — `_apenas_fgts` flag não enforced (MÉDIO) ✅ CORRIGIDO
- **Arquivo**: `modules/classification.py` — `mapear_para_pjecalc()`
- **Correção**: verbas com `_apenas_fgts=True` (ex: Multa Art. 467) são filtradas ANTES de entrar na lista de predefinidas. Log informativo emitido.

### P7 — Race condition lock check vs. runner creation (BAIXO)
- **Arquivo**: `webapp.py`
- **Problema**: lock check no handler (síncrono) vs. lock acquisition no generator (lazy). Janela teórica para duplicação se duas requests chegam simultaneamente.
- **Impacto**: baixo com `--workers 1` (single-threaded). Relevante apenas se escalar.
- **Correção proposta**: mover lock acquisition para antes do `return StreamingResponse()`.

### P8 — `criar_tabelas()` em import time (BAIXO)
- **Arquivo**: `infrastructure/database.py:583`
- **Problema**: tabelas criadas no import do módulo. Se DB não disponível, crash no startup. Race condition com múltiplos workers.
- **Impacto**: baixo com `--workers 1`.
- **Correção proposta**: mover para lifecycle event do FastAPI.

---

## Contexto arquitetural

### Pipeline de automação (fluxo normal)
```
PDF/DOCX → ingestion.py → extraction.py → classification.py
         → prévia web (HITL) → playwright_pjecalc.py → PJE-Calc → .PJC
```

### Novo fluxo SSE (pós-correção)
```
Frontend → GET /api/executar/{id}
  ├─ Runner não existe → cria runner + follow
  └─ Runner existe e ativo → follow mode (replay logs + stream novos)

Runner (thread independente):
  └─ Playwright preenche PJE-Calc → logs → done=True → cleanup (locks, DB, logs)

Frontend desconecta → runner continua → frontend reconecta → follow mode
```
