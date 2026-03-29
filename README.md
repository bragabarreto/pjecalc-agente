# PJECalc Agente

Agente inteligente de automação do **PJE-Calc Cidadão** (Programa de Cálculos da Justiça do Trabalho — CSJT/TST). Extrai dados de sentenças trabalhistas via LLM, classifica verbas automaticamente, preenche o PJE-Calc via Playwright e aprende continuamente com as correções do usuário.

```
PDF/DOCX → IA extrai → Humano revisa → Playwright preenche → .PJC exportado
```

---

## Arquitetura Multi-LLM

O agente usa dois modelos de linguagem com papéis distintos, orquestrados por `core/llm_orchestrator.py`:

| Tarefa | Modelo | Motivo |
|--------|--------|--------|
| Extração de sentença (texto) | **Claude Sonnet 4.6** | Raciocínio jurídico profundo, contexto longo |
| Extração de sentença (PDF nativo) | **Claude Sonnet 4.6** | Visão multimodal + parsing jurídico |
| Classificação de verbas (desconhecidas) | **Claude Sonnet 4.6** | Domínio trabalhista, precisão |
| Análise de sessão de aprendizado | **Claude Sonnet 4.6** | Raciocínio complexo sobre padrões |
| Análise de screenshot / crash recovery | **Gemini 2.5 Flash** | Visão nativa, rápido, barato |
| Validações rápidas | **Gemini 2.5 Flash** | Latência baixa |

**Fallback automático**: se o modelo primário falhar, o orquestrador tenta o modelo secundário antes de lançar erro.

---

## Learning Engine — Auto-aprimoramento

O agente **melhora sozinho** com o uso. A cada correção que o usuário faz na tela de Prévia:

1. **`CorrectionTracker`** registra a correção no banco (campo, valor anterior, valor corrigido, confiança da IA).
2. Ao atingir o limiar de correções (padrão: 10), uma **Sessão de Aprendizado** é disparada em background.
3. **`LearningEngine`** envia os pares (extração-original, correção-usuário) ao Claude para análise.
4. Claude gera **regras de mapeamento** (ex: "quando sentença menciona X, o campo Y deve ser Z").
5. As regras são persistidas no banco como `RegrasAprendidas` e injetadas nos prompts futuros via `RuleInjector`.

**Resultado**: quanto mais o usuário corrige, mais preciso o agente fica. Casos específicos de TRT, jurisprudências regionais e variações terminológicas são capturados automaticamente.

Acompanhe em `/admin/aprendizado`.

---

## Knowledge Base Oficial

Todo o conhecimento oficial do PJE-Calc está embutido nos prompts do LLM via `knowledge/pje_calc_official/`:

| Arquivo | Conteúdo |
|---------|---------|
| `system_prompt_base.txt` | Prompt base com regras completas do PJE-Calc, terminologia, enums e convenções |
| `verba_catalog_official.md` | Catálogo de 40+ verbas com configuração exata (incidências FGTS/INSS/IR, reflexas) |
| `manual_excerpts.md` | Resumos curados do Manual Oficial (117 págs., CSJT/TRT8) — seções operacionalmente críticas |
| `tutorial_rules.md` | Regras práticas do Tutorial Oficial — fluxo de preenchimento, prescrição, reflexas |

**Fontes oficiais:**
- Manual do Usuário PJe-Calc v1.0 (CSJT/TRT8, 117 páginas)
- Tutorial Oficial: pje.csjt.jus.br/manual/index.php/PJe-Calc-Tutorial
- Canal "Conhecendo o PJe-Calc" (Alacid Corrêa Guerreiro — Gestor Nacional)

---

## Pipeline de 6 Fases

```
1. Ingestão     modules/ingestion.py      PDF nativo, OCR fallback, DOCX, TXT
2. Extração     modules/extraction.py     Claude/Gemini → JSON estruturado, confiança 0–1
3. Classificação modules/classification.py  Verbas → PJE-Calc (catálogo + LLM batch)
4. Prévia       templates/previa.html     Todos os campos editáveis, HITL
5. Automação    modules/playwright_pjecalc.py  Playwright → PJE-Calc preenchido
6. Export       modules/export.py         .PJC (ZIP+XML) validado e exportado
```

---

## Quick Start

### Local (macOS/Linux)

```bash
# 1. Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate

# 2. Instalar dependências
pip install -r requirements.txt
playwright install chromium

# 3. Configurar variáveis de ambiente
cp .env.example .env
# Editar .env: ANTHROPIC_API_KEY=sk-ant-...
#              GEMINI_API_KEY=...  (opcional)

# 4. Subir o servidor
uvicorn webapp:app --reload --port 8000
# Acessar: http://localhost:8000
```

### Local (Windows)

```cmd
venv\Scripts\activate
uvicorn webapp:app --reload --port 8000
```

### Docker

```bash
docker build -t pjecalc-agent .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e GEMINI_API_KEY=... \
  -v pjecalc-dados:/app/data \
  pjecalc-agent
```

### Railway

Push para `main` → deploy automático. Ver `docs/` para configuração de variáveis no Railway.

---

## Variáveis de Ambiente

| Variável | Obrigatória | Default | Descrição |
|----------|-------------|---------|-----------|
| `ANTHROPIC_API_KEY` | **Sim** | — | Chave da API Claude (Anthropic) |
| `GEMINI_API_KEY` | Não | — | Chave da API Gemini (Google). Omitir para usar só Claude |
| `DATABASE_URL` | Não | SQLite local | `postgresql://...` para produção |
| `PJECALC_LOCAL_URL` | Não | `http://localhost:9257/pjecalc` | URL do Tomcat PJE-Calc |
| `PJECALC_TOMCAT_TIMEOUT` | Não | `600` | Segundos aguardando Tomcat subir |
| `CLOUD_MODE` | Não | auto-detect | `true` desativa automação Playwright |
| `DATA_DIR` | Não | `./data` | Diretório de dados persistentes |
| `PORT` | Não | `8000` | Porta HTTP (Railway injeta automaticamente) |
| `LEARNING_ENABLED` | Não | `true` | Ativa/desativa Learning Engine |
| `LEARNING_FEEDBACK_THRESHOLD` | Não | `10` | Correções para disparar sessão de aprendizado |
| `LEARNING_RETRAINING_INTERVAL_HOURS` | Não | `24` | Intervalo mínimo entre sessões de aprendizado |

---

## Estrutura de Diretórios

```
pjecalc-agente/
├── webapp.py                  # FastAPI — entrada principal (uvicorn webapp:app)
├── main.py                    # CLI — modo terminal
├── config.py                  # Shim de backward compat → infrastructure/config.py
├── database.py                # Shim de backward compat → infrastructure/database.py
│
├── infrastructure/            # Infraestrutura base
│   ├── config.py              # Pydantic v2 BaseSettings com validação de API keys
│   ├── database.py            # SQLAlchemy ORM — 8 modelos (5 core + 3 learning)
│   ├── logging_config.py      # structlog (JSON prod / colorido dev)
│   └── launcher.py            # Watchdog psutil para deploy local
│
├── core/                      # Núcleo do agente
│   ├── llm_orchestrator.py    # Roteamento Claude/Gemini + injeção de knowledge
│   ├── browser_manager.py     # Playwright lifecycle + tenacity + crash recovery
│   └── state_manager.py       # Máquina de estado tipada (AgentState dataclass)
│
├── knowledge/                 # Base de conhecimento oficial PJE-Calc
│   ├── knowledge_base.py      # KnowledgeBase — serve conteúdo aos prompts
│   └── pje_calc_official/
│       ├── system_prompt_base.txt   # Prompt base completo com regras PJE-Calc
│       ├── verba_catalog_official.md # Catálogo de 40+ verbas
│       ├── manual_excerpts.md        # Resumos do Manual Oficial
│       └── tutorial_rules.md         # Regras práticas do Tutorial
│
├── learning/                  # Sistema de aprendizado contínuo
│   ├── correction_tracker.py  # Registra correções do usuário
│   ├── learning_engine.py     # Analisa correções e gera novas regras via LLM
│   └── rule_injector.py       # Injeta regras aprendidas nos prompts
│
├── modules/                   # Módulos do pipeline
│   ├── ingestion.py           # Leitura de documentos (PDF/DOCX/TXT/OCR)
│   ├── extraction.py          # Extração via LLM (aceita LLMOrchestrator opcional)
│   ├── classification.py      # Mapeamento de verbas → PJE-Calc
│   ├── parametrizacao.py      # Transformação extraction → schema PJE-Calc
│   ├── preview.py             # Geração de prévia editável
│   ├── human_loop.py          # HITL — supervisão e incerteza
│   ├── playwright_pjecalc.py  # Automação Playwright com tenacity
│   ├── automation.py          # Automação PyAutoGUI (modo desktop)
│   ├── pjc_generator.py       # Geração nativa de arquivo .PJC
│   └── export.py              # Finalização e exportação
│
├── templates/                 # Templates Jinja2
│   ├── previa.html            # Prévia editável (human-in-the-loop)
│   ├── aprendizado.html       # Dashboard de aprendizado
│   └── ...
│
├── tests/                     # Suite de testes
├── docs/                      # Documentação técnica
├── pjecalc-dist/              # Distribuição PJE-Calc Cidadão (91MB, bundled)
└── data/                      # Dados persistentes (DB, logs, outputs, learning)
    └── learning/              # Snapshots JSON das sessões de aprendizado
```

---

## Endpoints de Diagnóstico

```
GET  /api/logs/java       # stdout+stderr do processo Java (Lancador + Tomcat)
GET  /api/logs/tomcat     # catalina.out do Tomcat embarcado
GET  /api/logs/python     # buffer de logs Python em memória
GET  /api/screenshot      # screenshot do display Xvfb :99
GET  /api/ps              # processos em execução no container
GET  /api/verificar_pjecalc  # testa se localhost:9257 responde

GET  /admin/aprendizado   # dashboard de sessões e regras aprendidas
POST /api/aprendizado/executar  # dispara sessão de aprendizado manualmente
```

---

## Regra de Negócio — Extração IA-Only

> **A prévia do cálculo NÃO pode ser gerada sem extração via IA.**
>
> Extração somente por regex produz dados incompletos para fins de liquidação trabalhista.
> Quando a IA estiver indisponível (sem créditos, timeout, erro 400/500), o processamento
> é **bloqueado imediatamente** com status `erro_ia`.

Nunca remover este comportamento.

---

## Referências

- [Manual Técnico PJE-Calc v1.0 (CSJT/TRT8)](https://www.trt6.jus.br/portal/sites/default/files/documents/manual_do_usuario_-_pje-calc_0.pdf)
- [Tutorial Oficial PJe-Calc](https://pje.csjt.jus.br/manual/index.php/PJe-Calc-Tutorial)
- [PJe-Calc Cidadão (TRT8)](https://www.trt8.jus.br/pjecalc-cidadao)
- [CLAUDE.md](CLAUDE.md) — Guia para desenvolvimento com Claude Code
- [docs/diagnostico-falhas-automacao.md](docs/diagnostico-falhas-automacao.md)
- [docs/analise-calc-machine-vs-agente.md](docs/analise-calc-machine-vs-agente.md)
