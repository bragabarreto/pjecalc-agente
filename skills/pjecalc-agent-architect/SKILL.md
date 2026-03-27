---
name: pjecalc-agent-architect
description: >
  Skill de arquitetura e refatoração do repositório pjecalc-agente — o agente de automação remota
  do PJE-Calc Cidadão. Use esta skill SEMPRE que o problema envolver: reestruturar o código do
  agente, eliminar código morto ou duplicado, resolver conflitos entre múltiplas estratégias de
  automação (automation.py vs playwright_pjecalc.py vs extensão), migrar de arquivos JSON para
  banco de dados, desacoplar o monólito Flask+Tomcat em microsserviços, otimizar o Dockerfile ou
  inicialização do Tomcat, planejar filas assíncronas (Celery/Redis), resolver problemas de
  escalabilidade no Railway, ou qualquer decisão arquitetural sobre como o agente deve ser
  organizado. Também use quando precisar entender a estrutura atual do repositório, mapear
  dependências entre módulos, ou planejar uma refatoração segura sem quebrar funcionalidades
  existentes. Se a conversa mencionar "refatorar o agente", "limpar o código", "arquitetura do
  pjecalc-agente", "microsserviços", "desacoplar", "código morto", "rotas órfãs", ou
  "escalabilidade do Railway", esta é a skill certa.
---

# PJE-Calc Agent Architect

Skill de arquitetura e refatoração para o repositório `pjecalc-agente`. O objetivo é transformar
o agente atual — funcional mas fragmentado — em uma base de código limpa, testável e escalável.

## Contexto: por que esta skill existe

O pjecalc-agente cresceu organicamente enquanto resolvia problemas difíceis (GUI Java headless,
JSF dinâmico, extração NLP de sentenças). O resultado é um código que funciona em partes, mas
sofre de fragmentação arquitetural: três estratégias de automação concorrentes, código morto
acumulado, acoplamento forte entre orquestração e automação, e dificuldade de escalar.

Esta skill NÃO trata de como preencher o PJE-Calc (use `pjecalc-preenchimento`), nem de como
debugar o Tomcat (use `pjecalc-agent-debugger`), nem de como escrever seletores JSF (use
`playwright-jsf-automator`). Esta skill trata de **como o código do agente deve ser organizado**.

---

## Mapa do repositório atual

```
pjecalc-agente/
├── webapp.py                  (1199 linhas) — FastAPI: rotas, SSE, lógica de negócio
├── config.py                  (113 linhas)  — Configurações globais + auto-detecção CLOUD_MODE
├── database.py                (525 linhas)  — SQLAlchemy: Processo, Calculo, InteracaoHITL
├── main.py                    (?)           — CLI standalone (modo local)
├── iniciarPjeCalc.sh          (207 linhas)  — Startup: Xvfb + xdotool + Bootstrap/Lancador
├── docker-entrypoint.sh       (54 linhas)   — Container: PJE-Calc bg → uvicorn imediato
├── Dockerfile                 (124 linhas)  — Multi-stage: agent-builder + imagem final
├── modules/
│   ├── ingestion.py           (302 linhas)  — PDF/DOCX → texto (pdfplumber + OCR)
│   ├── extraction.py          (2022 linhas) — Texto → JSON via Claude/Gemini API
│   ├── classification.py      (497 linhas)  — Verbas → mapeamento PJE-Calc
│   ├── parametrizacao.py      (328 linhas)  — JSON → instruções módulo a módulo
│   ├── preview.py             (422 linhas)  — Prévia editável (web)
│   ├── playwright_pjecalc.py  (2605 linhas) — ⭐ Automação principal (Playwright + JSF)
│   ├── automation.py          (729 linhas)  — ⚠️ Automação legada (pyautogui/playwright dual)
│   ├── playwright_script_builder.py (891 linhas) — ⚠️ Gera script standalone para download
│   ├── pjc_generator.py       (1083 linhas) — Gerador nativo de .PJC (ZIP+XML)
│   ├── human_loop.py          (465 linhas)  — HITL: pausa para validação humana
│   ├── document_collector.py  (467 linhas)  — Coleta de documentos
│   └── export.py              (301 linhas)  — Exportação de resultados
├── extension/                 — ⚠️ Extensão Chrome (terceira via de automação)
├── templates/                 — Jinja2: previa.html, instrucoes.html, etc.
├── tests/                     — Testes (cobertura limitada)
├── pjecalc-dist/              — PJE-Calc Cidadão empacotado (91MB, sem JRE)
└── dialog-suppressor/         — Java Agent para silenciar JOptionPane
```

### Legenda de status
- ⭐ = código principal, manter e melhorar
- ⚠️ = código problemático, candidato a remoção ou consolidação

---

## Diagnóstico: os 5 problemas estruturais

### 1. Três estratégias de automação concorrentes

O repositório tem três implementações diferentes tentando fazer a mesma coisa — preencher o
PJE-Calc. Cada uma usa seletores diferentes, fluxos diferentes, e até caminhos de navegação
diferentes ("Novo" vs "Cálculo Externo"):

| Implementação | Arquivo | Navegação | Resiliência |
|---|---|---|---|
| Playwright SSE (principal) | `playwright_pjecalc.py` | "Novo" ✓ | Alta (AJAX monitor, retry, crash recovery) |
| Script standalone | `playwright_script_builder.py` | "Cálculo Externo" ✗ | Baixa (seletores fixos, pausas manuais) |
| Extensão Chrome | `extension/content.js` | "Cálculo Externo" ✗ | Baixa (eventos DOM manuais) |

Além disso, `automation.py` é uma abstração legada que tenta unificar pyautogui e playwright,
mas na prática não é usada pelo fluxo principal.

**Ação**: Consolidar tudo em `playwright_pjecalc.py`. Remover `automation.py`,
`playwright_script_builder.py` e `extension/`. Se o usuário precisa de um script local,
gerar a partir do mesmo código-fonte, não de um builder separado.

### 2. webapp.py monolítico (1199 linhas)

O `webapp.py` concentra:
- Rotas HTTP (API + páginas)
- Lógica de processamento (background tasks)
- SSE streaming da automação
- Logging em buffer in-memory
- Gerenciamento de sessões em processamento

**Ação**: Extrair em módulos:
```
webapp.py          → Apenas definição de rotas e middleware
routes/
├── pages.py       → Rotas de páginas HTML (GET)
├── api.py         → API REST (POST/PATCH/DELETE)
├── diagnostics.py → Endpoints de diagnóstico (/api/logs/*, /api/ps, etc.)
└── sse.py         → Server-Sent Events para automação
services/
├── processing.py  → Background tasks (extração + classificação)
└── automation.py  → Orquestração da automação Playwright
```

### 3. Acoplamento Flask ↔ Tomcat no mesmo container

O container Docker empacota tudo junto: Python Agent (FastAPI), PJE-Calc (Tomcat Java), Xvfb,
Playwright Chromium. Isso cria problemas:

- Impossível escalar extração NLP independentemente da automação
- O Tomcat demora 2-5 minutos para subir, bloqueando qualquer automação
- Falha no Tomcat = falha de todo o serviço
- Imagem Docker pesada (~2GB) com Java + Python + Chromium + Xvfb

**Ação (curto prazo)**: Manter o monólito, mas desacoplar internamente. O webapp deve
funcionar 100% sem o Tomcat (extração, prévia, edição). A automação é uma feature
opcional que só roda se Tomcat estiver disponível.

**Ação (médio prazo)**: Separar em dois serviços:
```
┌─────────────────────────┐     ┌──────────────────────────┐
│ Serviço de Orquestração │     │ Worker de Automação      │
│ (Flask + LLM + Prévia)  │────▶│ (Playwright + PJE-Calc)  │
│ Leve, escala horizontal │     │ Pesado, pool fixo        │
│ Sem Java, sem Xvfb      │     │ Java + Xvfb + Chromium   │
└─────────────────────────┘     └──────────────────────────┘
         │                              │
         ▼                              ▼
    PostgreSQL                    Redis (fila)
```

### 4. Inicialização do Tomcat frágil

O `iniciarPjeCalc.sh` tenta duas abordagens em cascata:
- **A (Bootstrap direto)**: `org.apache.catalina.startup.Bootstrap start` — bypassa o Lancador
- **B (Lancador)**: `java -jar pjecalc.jar` — depende de Xvfb+xdotool para dismiss de dialogs

O Bootstrap direto (A) é a abordagem correta, mas pode falhar se:
1. O classpath não incluir todas as JARs necessárias
2. As system properties (`-Dcaminho.instalacao`, `-Dcatalina.home`) estiverem erradas
3. O banco H2 não estiver no path esperado pelo PJE-Calc

**Ação**: Investir no Bootstrap direto como único caminho. Usar `/api/logs/java` e
`/api/logs/tomcat` para diagnosticar. Se o Bootstrap não funcionar, a alternativa não é
voltar ao Lancador — é usar o `pjc-file-generator` para gerar .PJC sem Tomcat.

### 5. config.py com lógica de detecção misturada

O `config.py` mistura constantes legítimas (portas, timeouts) com lógica de detecção de ambiente
(`CLOUD_MODE` auto-detect, import de playwright para decidir modo). Isso dificulta testes e torna
o comportamento imprevisível.

**Ação**: Separar configuração de detecção:
```python
# config.py → apenas constantes e env vars
# runtime.py → detecção de ambiente, capabilities, feature flags
```

---

## Roteiro de refatoração (ordem recomendada)

A refatoração deve ser incremental — cada passo produz código que funciona e pode ser deployado.
Nunca fazer tudo de uma vez.

### Fase 1: Limpeza (1-2 dias)
1. **Remover código morto**: `automation.py`, `playwright_script_builder.py`, `extension/`
2. **Remover rotas órfãs** no webapp.py (identificar com `grep -n "def\|@app"`)
3. **Consolidar imports**: remover imports não utilizados
4. **Atualizar CLAUDE.md** para refletir a nova estrutura
5. **Rodar testes** existentes para garantir que nada quebrou

### Fase 2: Modularização do webapp (2-3 dias)
1. Extrair rotas em blueprints/routers FastAPI separados
2. Mover lógica de processamento para `services/`
3. Criar `services/tomcat.py` para encapsular polling e health check
4. Garantir que webapp funciona sem Tomcat (modo degradado gracioso)

### Fase 3: Robustez do Playwright (2-3 dias)
1. Substituir sleeps fixos por waits explícitos em `playwright_pjecalc.py`
2. Extrair cada fase (dados, salários, verbas, FGTS...) em métodos isolados e testáveis
3. Adicionar dry-run mode: executa toda a lógica sem browser para validar parâmetros
4. Implementar snapshot/restore para retomar automação do ponto de falha

### Fase 4: Desacoplamento (1 semana)
1. Introduzir fila de tarefas (Celery + Redis ou equivalente simples)
2. Separar Dockerfile em `Dockerfile.web` e `Dockerfile.worker`
3. Configurar docker-compose.yml para dev local com ambos os serviços
4. Migrar estado de `_sessoes_processando` (dict in-memory) para Redis/DB

### Fase 5: Observabilidade (ongoing)
1. Structured logging (JSON) em todos os módulos
2. Métricas de tempo por fase (extração, classificação, automação)
3. Dashboard de status das automações em andamento
4. Alertas quando Tomcat não sobe ou automação falha repetidamente

---

## Padrões de código para o agente refatorado

### Tratamento de erros por camada

```python
# Camada de serviço: captura e classifica erros
class AutomationError(Exception):
    """Erro recuperável na automação (retry possível)."""
    pass

class AutomationFatalError(Exception):
    """Erro fatal: requer intervenção humana."""
    pass

# Camada de rota: converte em HTTP response
@app.post("/api/executar/{sessao_id}")
async def executar(sessao_id: str):
    try:
        result = await automation_service.executar(sessao_id)
        return {"status": "ok", "pjc_path": result}
    except AutomationError as e:
        return JSONResponse(status_code=503, content={"error": str(e), "retry": True})
    except AutomationFatalError as e:
        return JSONResponse(status_code=500, content={"error": str(e), "retry": False})
```

### Injeção de dependências para testabilidade

```python
# Em vez de importar globais:
from config import PJECALC_DIR  # ❌ difícil de testar

# Usar injeção:
class TomcatService:
    def __init__(self, pjecalc_dir: Path, port: int = 9257):
        self.pjecalc_dir = pjecalc_dir
        self.port = port

    async def health_check(self) -> bool:
        ...
```

### Feature flags em vez de CLOUD_MODE booleano

```python
# Em vez de:
if CLOUD_MODE:  # ❌ binário, não expressa capacidades

# Usar capabilities:
@dataclass
class RuntimeCapabilities:
    has_playwright: bool
    has_tomcat: bool
    has_xvfb: bool
    has_llm_api: bool  # Claude ou Gemini

    @classmethod
    def detect(cls) -> "RuntimeCapabilities":
        ...
```

---

## Checklist de validação pós-refatoração

Antes de cada merge, verificar:

- [ ] `uvicorn webapp:app` sobe sem erros (sem Tomcat)
- [ ] Upload de PDF → prévia funciona (modo sem automação)
- [ ] Edição de campos na prévia persiste no banco
- [ ] Se Tomcat estiver rodando: automação SSE funciona end-to-end
- [ ] Testes existentes passam (`pytest tests/`)
- [ ] Docker build completa sem erros
- [ ] Endpoints de diagnóstico respondem (`/api/logs/*`, `/api/ps`)

---

## Scripts prontos (diretório `scripts/`)

A skill inclui scripts executáveis para tarefas comuns de refatoração. Execute-os diretamente
com Python — não é necessário instalar dependências extras.

### `scripts/find_dead_code.py` — Localizar código morto

Analisa o repositório e identifica funções/classes não referenciadas, rotas possivelmente
órfãs e módulos não importados. Gera um relatório com candidatos a remoção.

```bash
python scripts/find_dead_code.py /caminho/para/pjecalc-agente
```

Exemplo de saída (testado contra o repo real — encontrou 65 candidatos):
- 49 funções não referenciadas
- 4 classes não referenciadas
- 9 rotas possivelmente órfãs
- 3 módulos não importados por ninguém

### `scripts/health_check.py` — Verificar ambiente completo

Health check de todos os componentes: Python, Java, Tomcat, banco, API keys, Playwright,
Xvfb, disco. Útil para diagnosticar por que o agente não funciona em um ambiente novo.

```bash
python scripts/health_check.py                      # Verifica tudo
python scripts/health_check.py --component tomcat    # Só Tomcat
python scripts/health_check.py --json                # Saída JSON para integração
```

### `scripts/split_webapp.py` — Dividir webapp.py em módulos

Analisa o webapp.py monolítico e gera uma proposta de divisão em FastAPI routers separados
(pages, api, diagnostics, sse). Gera os arquivos prontos para revisão.

```bash
python scripts/split_webapp.py webapp.py --dry-run   # Apenas mostra o plano
python scripts/split_webapp.py webapp.py --output nova_estrutura/
```

---

## Relação com outras skills

| Situação | Skill a usar |
|---|---|
| Quero reestruturar o código do agente | **Esta skill** |
| Quero preencher campos no PJE-Calc | `pjecalc-preenchimento` |
| Quero parametrizar verbas de uma sentença | `pjecalc-parametrizacao` |
| Quero automatizar via Playwright | `pjecalc-automator` + `playwright-jsf-automator` |
| O Tomcat não sobe no Docker | `java-headless-docker` → `pjecalc-agent-debugger` |
| Quero gerar .PJC sem o PJE-Calc | `pjc-file-generator` |
| Quero extrair dados de sentença | `juridical-nlp-extractor` |
| Quero entender o pjecalc.jar | `jar-reverse-engineer` |
