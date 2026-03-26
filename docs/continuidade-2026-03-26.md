# Continuidade da Sessão — 2026-03-26

Este documento registra o estado exato do projeto ao final da sessão de trabalho de 26/03/2026.
Para retomar: `git pull origin main` e leia este arquivo primeiro.

---

## Estado do repositório

Commit atual: `HEAD` — branch `main` sincronizado com GitHub (`bragabarreto/pjecalc-agente`)

### Commits desta sessão (do mais antigo ao mais recente)

| Commit | Descrição |
|---|---|
| `46010a9` | feat: extração PDF nativa, Structured Outputs e camada de parametrização |
| `b3254cb` | fix: crash honorarios list vs dict em database.criar_calculo |
| `99158eb` | fix: bloquear processamento sem IA + corrigir schema Structured Outputs |
| `cd9b78d` | fix: remover output_config + bloquear relatório sem IA |
| `6ff8461` | fix: remover gerar_pjc() síncrono de confirmar_previa() — **resolve Service Unavailable** |
| `6a308c4` | feat: skill pjecalc-preenchimento + docs continuidade (pull de outra máquina) |
| *(sessão atual)* | fix: Dockerfile add xvfb + iniciarPjeCalc.sh readiness check correto |

---

## O que foi implementado (acumulado)

### 1. Regra IA-only (bloqueante)
- `extraction.py`: `_erro_ia=True` em qualquer falha de LLM
- `webapp.py`: detecta e bloqueia com `status="erro_ia"`
- `novo_calculo.html`: mensagem clara ao usuário

### 2. Camada de parametrização (`modules/parametrizacao.py`)
- 11 passos: dados_processo, parametros_gerais, historico_salarial, verbas, fgts,
  contribuicao_social, imposto_renda, correcao_juros, honorarios, alertas
- ADC 58 — IPCA-E pré-judicial + SELIC judicial; detecta réu público (EC 113/2021)

### 3. D1 — Bootstrap bypass do Lancador Java
- `iniciarPjeCalc.sh` usa `org.apache.catalina.startup.Bootstrap` como Abordagem A
  (quando `tomcat/conf/server.xml` existe — sempre verdadeiro no container)
- `-Djava.awt.headless=true` elimina dependência de display virtual para o Java
- Fallback: `java -jar pjecalc.jar` (Lancador) se server.xml ausente

### 4. D2 — Automação sem intervenção manual (`playwright_pjecalc.py`)
- Login automático ou RuntimeError; verbas não reconhecidas → log de aviso (não bloqueia)

### 5. D4 — Validação HITL em `confirmar_previa` (`webapp.py`)
- HTTP 422 se: admissão/demissão/tipo_rescisão ausentes, zero verbas, confiança < 0.7

### 6. D7–D10 — Schema alinhado com UI real do PJE-Calc
- D7: honorários como lista de registros; D8: INSS como 4 checkboxes individuais
- D9: IRPF com campos reais; D10: baseCalculo via fuzzy match em runtime

### 7. Fix extraction pipeline
- Timeout 90s, max_tokens 4096; `output_config` removido (schema >16 union types)
- Relatório estruturado: falha retorna estrutura vazia, nunca cai em pipeline de sentença bruta

### 8. Fixes desta sessão (2026-03-26 retomada)
- **Dockerfile**: `xvfb` adicionado ao `apt-get install` (estava AUSENTE)
  → endpoint `/api/screenshot` agora funciona; fallback xdotool tem display válido
- **iniciarPjeCalc.sh**: readiness check corrigido de `xset q` (não instalado) para
  `xdotool getmouselocation` — Xvfb confirma disponibilidade em 1-2s em vez de 20s

---

## Estado atual do pipeline (o que funciona)

```
PDF/DOCX → ingestion.py → extraction.py (Claude API) → parametrizacao.py → prévia web → confirmar → /instrucoes
```

| Fase | Status |
|---|---|
| Ingestão | ✅ OK |
| Extração via IA (PDF nativo + texto) | ✅ OK |
| Regra IA-only | ✅ OK |
| Parametrização (11 passos) | ✅ OK |
| Prévia web (campos editáveis inline) | ✅ OK |
| Confirmação + validação HITL | ✅ OK |
| Página instrucoes + botão "Executar Automação" | ✅ OK |
| Automação SSE (Playwright) | ⏳ EM ABERTO — Tomcat precisa subir no Railway |
| Download .PJC (lazy, gerador nativo) | ✅ OK (funcional como fallback) |

---

## Problemas em aberto

### A) Tomcat no Railway (problema principal)

**Status atual:** Bootstrap bypass implementado e no ar. Ainda não testado após o fix do Xvfb.

**O que fazer:**
1. Fazer deploy para Railway: `git push origin main`
2. Aguardar 2-3 min e acessar `GET /api/logs/java` e `GET /api/logs/tomcat`
3. Se Tomcat subiu → acessar `GET /api/verificar_pjecalc` → deve retornar `{"status":"ok"}`
4. Se ainda falha → copiar log para `docs/java-log-baseline.txt` e analisar

**Diagnóstico:**
```
GET /api/logs/java      # stdout+stderr do Java (erros de startup do Bootstrap)
GET /api/logs/tomcat    # catalina.out (deploy da webapp pjecalc/)
GET /api/screenshot     # screenshot do Xvfb :99 (agora funciona com xvfb instalado)
GET /api/ps             # processos em execução
GET /api/verificar_pjecalc  # testa se localhost:9257 responde
```

**Causa provável de falha:** Se o log ainda mostrar `[TRT8]` prefixes, o Bootstrap
não está sendo executado — verificar se `server.xml` existe e se o `_iniciar_java`
está caindo no fallback (java -jar).

### B) Automação Playwright (depende do Tomcat)

- 9 fases implementadas em `playwright_pjecalc.py`
- Não testado end-to-end (Tomcat nunca confirmado no Railway)
- Assim que Tomcat subir, testar via botão "Executar Automação" na página /instrucoes

---

## Como retomar

### Próximo passo imediato

```bash
git push origin main   # deploy para Railway
# aguardar 3-5 min, então:
# curl https://<seu-app>.railway.app/api/verificar_pjecalc
# curl https://<seu-app>.railway.app/api/logs/tomcat
```

Se Tomcat responder → testar automação completa (upload PDF → prévia → confirmar → executar).
Se Tomcat falhar → trazer o log para a sessão e diagnosticar.

### Contexto para o Claude Code na próxima sessão

> "Continua o projeto PJE-Calc agente. Leia `docs/continuidade-2026-03-26.md`.
> O deploy foi feito — trago os logs de `/api/logs/java` e `/api/logs/tomcat`.
> [colar logs aqui]"

---

## Arquivos-chave para referência rápida

| Arquivo | Papel |
|---|---|
| `CLAUDE.md` | Contexto completo do projeto — **ler primeiro** |
| `modules/extraction.py` | Extração via Claude API + regra IA-only |
| `modules/parametrizacao.py` | Cérebro do pipeline — 11 passos |
| `modules/playwright_pjecalc.py` | Automação PJE-Calc via Playwright (9 fases) |
| `modules/pjc_generator.py` | Gerador nativo .PJC (fallback) |
| `database.py` | ORM SQLAlchemy — entidades Processo, Calculo, InteracaoHITL |
| `webapp.py` | FastAPI — rotas principais + SSE executor |
| `iniciarPjeCalc.sh` | Startup do PJE-Calc no Railway (Bootstrap + Xvfb) |
| `docker-entrypoint.sh` | Ordem de inicialização: PJE-Calc bg → uvicorn imediato |
| `Dockerfile` | Build do container (xvfb agora incluído) |
| `docs/lancador-analysis.md` | Análise do Lancador Java (pontos de bloqueio) |
| `docs/decisions.md` | Registro de todas as decisões técnicas da sessão |
| `skills/pjecalc-preenchimento/` | Skill com guia campo-a-campo do PJE-Calc |
