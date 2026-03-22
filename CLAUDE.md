# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Local development (Windows)
```bash
# Activate venv and run web server
venv\Scripts\activate
uvicorn webapp:app --reload --port 8000

# CLI mode (single sentence)
python main.py --sentenca path/to/sentenca.pdf

# Resume interrupted session
python main.py --sessao <UUID>
```

### Deploy (Railway)
```bash
# Push to main triggers auto-deploy
git push origin main

# Diagnostic endpoints (Railway)
GET /api/logs/java      # stdout+stderr do processo Java (Lancador + Tomcat)
GET /api/logs/tomcat    # catalina.out do Tomcat embarcado
GET /api/screenshot     # screenshot do display Xvfb :99
GET /api/ps             # processos em execução no container
GET /api/verificar_pjecalc  # testa se localhost:9257 responde
```

### Docker local
```bash
docker build -t pjecalc-agent .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=... \
  -v pjecalc-dados:/opt/pjecalc/.dados \
  pjecalc-agent
```

## Architecture

### Pipeline de 6 fases
```
PDF/DOCX → ingestion.py → extraction.py → classification.py → prévia web → playwright_pjecalc.py → .PJC
```

1. **Ingestão** (`modules/ingestion.py`): PDF nativo via pdfplumber; OCR pytesseract como fallback; normalização de encoding e datas.
2. **Extração** (`modules/extraction.py`): Prompt estruturado ao Claude API (temperature=0). Parse tolerante a JSON inválido. Fallback regex para datas/valores. Retorna confidence scores 0–1 por campo.
3. **Classificação** (`modules/classification.py`): Tabela `VERBAS_PREDEFINIDAS` com 40+ verbas trabalhistas mapeadas para PJE-Calc (nome exato, incidências FGTS/INSS/IR, reflexas). Claude resolve verbas não reconhecidas.
4. **Prévia web** (`templates/previa.html` + `webapp.py`): Todos os campos editáveis via `salvarCampo()` com PATCH inline. Estado persiste em banco antes de qualquer automação.
5. **Automação** (`modules/playwright_pjecalc.py`): Playwright Chromium headless conecta ao Tomcat local (`:9257`). Navega pelo menu **"Novo"** (não "Cálculo Externo") para primeira liquidação de sentença. Fases: dados processo → histórico salarial → verbas → FGTS → INSS → honorários → liquidar.
6. **Export** (`modules/pjc_generator.py`): Gerador nativo de `.PJC` = ZIP com XML ISO-8859-1. Timestamps em ms BRT (UTC-3). IDs determinísticos via hash da sessão.

### Banco de dados (`database.py`)
SQLite local / PostgreSQL em produção (detectado por `DATABASE_URL`). Entidades principais:
- `Processo` (1) → `Calculo` (N): processo trabalhista agrupa múltiplos cálculos.
- `Calculo`: estado (`em_andamento` → `previa_gerada` → `confirmado` → `pjc_exportado`), `sessao_id` UUID para retomada, dados do contrato e verbas como JSON.
- `InteracaoHITL`: log auditável de intervenções humanas.

### Web app (`webapp.py`)
FastAPI com Jinja2. Fluxo principal:
- `POST /processar` → background task (extração + classificação) → redireciona para `/previa/{sessao_id}`
- `POST /previa/{sessao_id}/confirmar` → persiste no banco, redireciona para `/instrucoes/{sessao_id}`
- `GET /api/executar/{sessao_id}` → **SSE stream** que executa `playwright_pjecalc.py` e transmite logs linha a linha
- `GET /api/verificar_pjecalc` → verifica disponibilidade do Tomcat local (polling antes de iniciar automação)

O gerador SSE em `executar_automacao_sse()` faz polling de Tomcat (até 600s) antes de iniciar o Playwright — necessário porque o Tomcat demora 2–5 min para subir no Railway.

### Infraestrutura Docker / Railway
- **Base**: `eclipse-temurin:8-jre-jammy` (Java 8 obrigatório para PJE-Calc).
- **Sequência de inicialização** (`docker-entrypoint.sh`): PJE-Calc em background → uvicorn **imediatamente** (Railway healthcheck passa) → Tomcat inicializa em background (~3–5 min).
- **PJE-Calc headless** (`iniciarPjeCalc.sh`): Xvfb `:99` + `xdotool` para auto-dismiss de dialogs Swing do Lancador. Java redireciona para `/opt/pjecalc/java.log`.
- **pjecalc-dist/**: distribuição do PJE-Calc Cidadão sem JRE e sem navegador. Contém `bin/pjecalc.jar` + `tomcat/webapps/pjecalc/`. Commitado no repositório (91MB).

## Convenções críticas

- **Datas no PJE-Calc**: sempre `DD/MM/AAAA` (barras). Nunca ISO.
- **Valores monetários**: vírgula decimal padrão BR (`1.234,56`). Usar `_fmt_br()` em `playwright_pjecalc.py`.
- **Menu de navegação**: sempre usar **"Novo"** para primeira liquidação. "Cálculo Externo" serve apenas para atualizar cálculos já existentes.
- **CLOUD_MODE**: auto-detectado pela presença do módulo `playwright`. Forçar via env `CLOUD_MODE=true|false`. Controla exibição do painel de automação em `instrucoes.html`.
- **`requirements-cloud.txt`** vs **`requirements.txt`**: Docker usa `requirements-cloud.txt` (sem pyautogui/pywinauto/OCR). Local Windows usa `requirements.txt`.

## Problema em aberto (Tomcat no Railway)

O Tomcat embarcado (`pjecalc.jar`) não está subindo no Railway. O Lancador Java (`Lancador.java:42`) executa validações de startup e pode mostrar `JOptionPane` dialogs (GUI Swing) que bloqueiam o thread principal. O Xvfb + xdotool tenta auto-dismissar, mas o Java ainda não está iniciando o Tomcat.

**Diagnóstico**: acessar `/api/logs/java` após deploy para ver o stdout/stderr completo do Java (capturado em `/opt/pjecalc/java.log`). O log para em `[TRT8] Configurando variaveis basicas.` — o que acontece depois é o que precisa ser descoberto.

**Abordagens alternativas a considerar**:
1. Iniciar Tomcat diretamente (bypassar Lancador) usando `org.apache.catalina.startup.Bootstrap` com as JARs de `bin/lib/`
2. Criar Java agent (`-javaagent`) para interceptar e silenciar `JOptionPane.showMessageDialog()`
3. Patch do bytecode de `Lancador.class` para remover a chamada GUI
