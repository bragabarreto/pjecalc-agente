---
name: systematic-debugging
description: Metodologia de debugging sistemático para Python, FastAPI, Playwright e Railway. Cobre análise de logs, reprodução de bugs, diagnóstico de race conditions, erros de automação JSF/RichFaces e falhas de deploy em cloud.
---

# Systematic Debugging Skill

## Metodologia: 5 Passos Antes de Tocar no Código

```
1. OBSERVAR   → Ler o erro completo, sem pular linhas
2. ISOLAR     → Reduzir ao mínimo reproduzível
3. HIPÓTESE   → Formular causa provável (1 por vez)
4. VERIFICAR  → Confirmar hipótese com log/teste, não com palpite
5. CORRIGIR   → Só então modificar código
```

**Nunca pule para o passo 5 sem completar os anteriores.**

---

## Análise de Logs de Erro

### Onde buscar logs neste projeto

| Fonte | Endpoint / Comando |
|---|---|
| Logs Playwright (SSE) | `GET /api/executar/{sessao_id}` — saída em tempo real |
| Logs Python webapp | `GET /api/logs/python` — últimas 300 linhas do logger |
| Logs Java / Tomcat | `GET /api/logs/java` e `GET /api/logs/tomcat` |
| Screenshot Xvfb | `GET /api/screenshot` |
| Processos ativos | `GET /api/ps` |
| Tomcat disponível | `GET /api/verificar_pjecalc` |

### Leitura de traceback Python

```
Sempre ler de baixo para cima:
  linha mais baixa  = erro imediato (o que explodiu)
  linhas do meio    = call stack (quem chamou o quê)
  linha mais alta   = onde o fluxo entrou
```

### Palavras-chave críticas neste projeto

| Mensagem | Diagnóstico |
|---|---|
| `Execution context was destroyed` | Página ainda navegando quando `evaluate()` foi chamado |
| `Target page, context or browser has been closed` | Browser crashou — `fechar()` foi chamado sem restart |
| `Playwright Sync API inside the asyncio loop` | Thread não tem loop próprio — `asyncio.set_event_loop(new_event_loop())` |
| `ViewExpiredException` / `ViewExpired` | JSF ViewState expirou — recarregar página |
| `503 Service Unavailable` | Proxy timeout: Python demorou >30s ou unhandled exception |
| `HTTP 500` no PJE-Calc | AJAX postback JSF falhou — geralmente blur disparado antes da hora |
| `networkidle timeout` | PJE-Calc travado em AJAX pendente |
| `StaleElementReferenceException` | DOM foi re-renderizado pelo RichFaces após AJAX |

---

## Reprodução Mínima

### Princípio
> O menor código que exibe o bug é o mais fácil de corrigir.

### Checklist de isolamento

- [ ] Bug ocorre com dados específicos ou com qualquer dado?
- [ ] Bug ocorre só na primeira execução ou em todas?
- [ ] Bug ocorre só em Railway/Docker ou também localmente?
- [ ] Bug ocorre em headless ou também em modo visível?
- [ ] Qual fase do Playwright falha? (1=dados, 2=histórico, 3=verbas…)
- [ ] O browser abre e carrega o PJE-Calc antes do erro?

### Reproduzir em isolamento (módulo playwright)

```python
# Testar fase específica sem rodar o pipeline completo
from modules.playwright_pjecalc import PJECalcPlaywright

agente = PJECalcPlaywright(log_cb=print)
agente.iniciar_browser(headless=False)  # visível para diagnóstico
# navegue manualmente até onde quer testar, então:
agente.fase_verbas(verbas_mapeadas_teste)
agente.fechar()
```

---

## Debugging de Race Conditions

Race conditions mais comuns neste projeto:

### 1. Navegação JSF ainda em progresso

**Sintoma:** `Execution context was destroyed`
**Causa:** `evaluate()` chamado enquanto JSF faz redirect/partial update
**Fix:**
```python
# Antes de qualquer evaluate() após navegação:
try:
    page.wait_for_load_state("networkidle", timeout=10000)
except Exception:
    page.wait_for_timeout(2000)
self._aguardar_ajax()
```

### 2. AJAX RichFaces não completou

**Sintoma:** Campos aparecem preenchidos na tela mas não são salvos
**Causa:** `blur` disparado prematuramente aciona postback AJAX que recarrega o campo
**Fix:**
```python
# NÃO usar .press("Tab") após fill() em campos JSF
# NÃO usar .dispatch_event("blur")
# Usar apenas:
loc.fill(valor)
loc.dispatch_event("input")
loc.dispatch_event("change")
# Depois aguardar AJAX antes de interagir com próximo campo
```

### 3. Thread asyncio vs sync_playwright

**Sintoma:** `Playwright Sync API inside the asyncio loop`
**Causa:** Thread herdou referência ao loop do uvicorn
**Fix:**
```python
# No início de qualquer thread que chama sync_playwright():
import asyncio
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.set_event_loop(asyncio.new_event_loop())
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())
```

### 4. PJE-Calc ainda inicializando

**Sintoma:** `ConnectionRefusedError` ou HTTP 404 em localhost:9257
**Causa:** Tomcat ainda não subiu (Railway demora 3-5 min)
**Fix:** O SSE endpoint em `webapp.py` já tem polling de até 600s — verificar `/api/logs/java` se persistir além disso.

---

## Debugging de Automação JSF/RichFaces

### Inspecionar DOM em tempo real

```python
# Listar todos os campos visíveis na página atual
campos = page.evaluate("""() =>
    [...document.querySelectorAll('input,select,textarea')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
    .map(e => ({id: e.id, name: e.name, type: e.type, value: e.value}))
""")

# Listar todos os botões e links
botoes = page.evaluate("""() =>
    [...document.querySelectorAll('a,button,input[type="submit"],input[type="button"]')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
    .map(e => ({id: e.id, txt: (e.textContent||e.value||'').trim().substring(0,40)}))
""")

# Verificar se AJAX está em progresso
ajax_ok = page.evaluate("() => window.__ajaxCompleto === true")
```

### Seletores robustos para JSF (IDs dinâmicos)

```python
# NUNCA: id exato (muda entre versões JSF)
page.locator("#formulario:j_id123:nomeVerba")  # frágil

# SEMPRE: sufixo de ID
page.locator("[id$='nomeVerba']")               # robusto
page.locator("[id*='btnSalvar']")               # contém
page.locator("input[id$=':dataAdmissao']")      # tipo + sufixo
```

### Verificar qual menu/aba está ativa

```python
url_atual = page.url
titulo = page.title()
heading = page.evaluate(
    "() => (document.querySelector('h1,h2,h3,legend,.tituloPagina')||{}).textContent?.trim()||''"
)
print(f"URL: {url_atual} | Heading: {heading}")
```

---

## Debugging de SSE / Streaming

### O heartbeat some ou a conexão cai

```python
# O gerador SSE tem keepalive a cada 25s:
yield f"data: {json.dumps({'keepalive': True})}\n\n"
# Se mesmo assim a conexão cai, verificar proxy timeout no Railway
# Adicionar header: X-Accel-Buffering: no
```

### Mensagens de log não chegam ao browser

**Diagnóstico:**
1. Verificar se `fila.put(msg)` está sendo chamado
2. Verificar se `_executar_gen` está em `run_in_executor`
3. Verificar se a thread não lançou exceção silenciosa

```python
# Em _executar_gen, capturar tudo:
except Exception as exc:
    fila.put(("erro", f"ERRO na thread: {type(exc).__name__}: {exc}"))
    import traceback
    fila.put(("erro", traceback.format_exc()))
```

---

## Debugging de Deploy Railway

### Checklist pós-deploy

```bash
# 1. Verificar se webapp está respondendo
curl https://<app>.railway.app/health

# 2. Verificar se Tomcat subiu
curl https://<app>.railway.app/api/verificar_pjecalc

# 3. Ver logs Java (onde o Tomcat para de subir)
curl https://<app>.railway.app/api/logs/java

# 4. Screenshot do Xvfb (confirmar que display virtual está OK)
curl https://<app>.railway.app/api/screenshot > screenshot.png

# 5. Processos em execução
curl https://<app>.railway.app/api/ps
```

### 503 Service Unavailable

| Causa | Diagnóstico | Fix |
|---|---|---|
| Python exception não capturada | `/api/logs/python` | Adicionar try/except retornando JSON 500 |
| Request demora >30s | Timeout de proxy Railway | Usar SSE ou background task |
| Uvicorn não subiu | Logs Railway | Verificar dependências e porta |

### Banco de dados em Railway

```python
# DATABASE_URL automático quando PostgreSQL addon está linked
# Verificar se migration rodou:
# railway run python -c "from database import Base, engine; Base.metadata.create_all(engine)"
```

---

## Padrões de Teste para Regressão

### Testar sem importar módulos com dependências pesadas

```python
# Testar via inspeção de código-fonte (evita importar anthropic, playwright, etc.)
import ast, inspect
source = open("modules/playwright_pjecalc.py").read()
tree = ast.parse(source)

# Verificar se método existe
method_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
assert "fase_verbas" in method_names

# Verificar se string crítica está no código
assert "btnExpresso" in source
assert "calculo-externo" not in source  # regra de negócio: nunca Cálculo Externo
```

### Estrutura recomendada de teste de regressão

```python
def test_regra_critica_nao_foi_quebrada():
    """Garante que regras do CLAUDE.md não foram violadas."""
    source = open("modules/playwright_pjecalc.py").read()
    # Nunca navegar para Cálculo Externo
    assert "/pages/calculo/calculo-externo.xhtml" not in source
    # Sempre usar btnExpresso para verbas predefinidas
    assert "btnExpresso" in source
```

---

## Debugging com Screenshots

```python
# Capturar screenshot em qualquer ponto da automação
page.screenshot(path="debug_snapshot.png", full_page=True)

# Via endpoint Railway:
# GET /api/screenshot → PNG do display Xvfb atual
```

---

## Anti-padrões a Evitar

```python
# ❌ Retentativas cega com sleep
for i in range(10):
    time.sleep(2)
    try_something()

# ✓ Aguardar condição específica
page.wait_for_selector("[id$='btnSalvar']", state="visible", timeout=10000)

# ❌ Ignorar exceção sem log
try:
    something()
except Exception:
    pass

# ✓ Logar sempre, ignorar quando inofensivo
try:
    something()
except Exception as e:
    self._log(f"  ⚠ something falhou (não crítico): {e}")

# ❌ Testar com mocks de banco/browser quando não é necessário
# ✓ Inspecionar código-fonte para testar regras de negócio
```
