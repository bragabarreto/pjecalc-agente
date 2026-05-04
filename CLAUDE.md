# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Regra obrigatória — Consultar manual antes de qualquer alteração

> **ANTES de corrigir, ajustar ou implementar qualquer funcionalidade relacionada ao PJE-Calc,
> SEMPRE consultar o manual oficial em `knowledge/pje_calc_official/manual_completo.md` e os
> excerpts em `knowledge/pje_calc_official/manual_excerpts.md`.**
>
> Isso inclui: preenchimento de campos, ordem de fases, fórmulas de cálculo, IDs de DOM,
> regras de salvamento, regeração de ocorrências, e qualquer aspecto operacional do PJE-Calc.
>
> Razão: muitos bugs foram causados por suposições incorretas que poderiam ter sido evitadas
> consultando a documentação oficial. O manual é a fonte da verdade.

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

### Deploy (Oracle Cloud)
```bash
# Push to main triggers auto-deploy via GitHub Actions
git push origin main

# Manual deploy
./deploy/oracle-cloud/deploy.sh 163.176.44.221 ~/Downloads/ssh-key-2026-03-31.key

# SSH into VM
ssh -i ~/Downloads/ssh-key-2026-03-31.key opc@163.176.44.221

# Production URL
http://163.176.44.221:8000

# Diagnostic endpoints (produção)
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
5. **Automação** (`modules/playwright_pjecalc.py`): Playwright **Firefox** headless conecta ao Tomcat local (`:9257`). Firefox é o navegador nativo do PJE-Calc Cidadão (RichFaces/JSF). Navega pelo menu **"Novo"** (não "Cálculo Externo") para primeira liquidação de sentença. Fases: dados processo → histórico salarial → verbas → FGTS → INSS → honorários → liquidar.
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

O gerador SSE em `executar_automacao_sse()` faz polling de Tomcat (até 600s) antes de iniciar o Playwright — necessário porque o Tomcat demora 2–5 min para subir.

### Infraestrutura Docker / Oracle Cloud
- **VM**: Oracle Cloud Free Tier ARM64, 5.5GB RAM, Oracle Linux 9
- **IP**: `163.176.44.221` — porta 8000 (app) + opcionalmente Caddy nas 80/443
- **Base**: `eclipse-temurin:8-jre-jammy` (Java 8 obrigatório para PJE-Calc).
- **Sequência de inicialização** (`docker-entrypoint.sh`): PJE-Calc em background → uvicorn **imediatamente** → Tomcat inicializa em background (~3–5 min).
- **PJE-Calc headless** (`iniciarPjeCalc.sh`): Xvfb `:99` + `xdotool` para auto-dismiss de dialogs Swing do Lancador. Java redireciona para `/opt/pjecalc/java.log`.
- **pjecalc-dist/**: distribuição do PJE-Calc Cidadão sem JRE e sem navegador. Contém `bin/pjecalc.jar` + `tomcat/webapps/pjecalc/`. Commitado no repositório (91MB).
- **Deploy**: GitHub Actions (push to main) ou manual via `deploy/oracle-cloud/deploy.sh`.
- **Secrets GitHub Actions**: `ORACLE_SSH_KEY`, `ORACLE_HOST`, `ORACLE_USER`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `POSTGRES_PASSWORD`.
- **Volumes persistentes**: `/opt/pjecalc-data/calculations`, `/opt/pjecalc-data/pjecalc-dados`, `/opt/pjecalc-data/postgres`.

## Regra de negócio obrigatória — IA-only

> **A prévia do cálculo NÃO pode ser gerada sem extração via IA.**
>
> Extração somente via regex produz dados incompletos e não confiáveis para fins de liquidação
> trabalhista. Quando a IA (Claude API) estiver indisponível (sem créditos, timeout, erro 400/500),
> o processamento deve ser BLOQUEADO imediatamente com status `erro_ia`.
>
> - `extraction.py`: `_erro_ia=True` retornado quando `_extrair_via_llm` ou `_extrair_via_llm_pdf` falham
> - `webapp.py`: ao receber `_erro_ia`, cria calculo com `status="erro_ia"` e encerra sem gerar prévia
> - `novo_calculo.html`: exibe mensagem clara ao usuário com link para adicionar créditos
>
> **Nunca remover este comportamento.** A confiabilidade da liquidação depende da extração por IA.

## Convenções críticas

- **Datas no PJE-Calc**: sempre `DD/MM/AAAA` (barras). Nunca ISO.
- **Valores monetários**: vírgula decimal padrão BR (`1.234,56`). Usar `_fmt_br()` em `playwright_pjecalc.py`.
- **Menu de navegação**: sempre usar **"Novo"** para primeira liquidação. "Cálculo Externo" serve apenas para atualizar cálculos já existentes.
- **CLOUD_MODE**: auto-detectado pela presença do módulo `playwright`. Forçar via env `CLOUD_MODE=true|false`. Controla exibição do painel de automação em `instrucoes.html`.
- **`requirements-cloud.txt`** vs **`requirements.txt`**: Docker usa `requirements-cloud.txt` (sem pyautogui/pywinauto/OCR). Local Windows usa `requirements.txt`.

## Nova estrutura de diretórios (refatoração 2026)

```
infrastructure/   # Infraestrutura base (config Pydantic v2, DB ORM, logging structlog, launcher psutil)
core/             # Núcleo do agente (LLMOrchestrator, BrowserManager, StateManager)
knowledge/        # Knowledge base oficial PJE-Calc (manual, tutorial, catálogo de verbas)
learning/         # Learning Engine — auto-aprimoramento via correções do usuário
```

`config.py` e `database.py` na raiz são shims de backward compatibility (1 linha cada) que reexportam de `infrastructure/`. Todos os imports existentes continuam funcionando sem mudança.

## LLM Routing (Claude vs Gemini)

| TaskType | Modelo primário | Motivo |
|----------|----------------|--------|
| `LEGAL_EXTRACTION` | Claude Sonnet 4.6 | Raciocínio jurídico, contexto longo |
| `LEGAL_EXTRACTION_PDF` | Claude Sonnet 4.6 | Visão multimodal + parsing |
| `VERBA_CLASSIFICATION` | Claude Sonnet 4.6 | Domínio trabalhista |
| `LEARNING_ANALYSIS` | Claude Sonnet 4.6 | Raciocínio complexo sobre padrões |
| `SCREENSHOT_ANALYSIS` | Gemini 2.5 Flash | Visão nativa, rápido |
| `CRASH_RECOVERY` | Gemini 2.5 Flash | Decisão rápida a partir de screenshot |
| `QUICK_VALIDATION` | Gemini 2.5 Flash | Baixa latência |

Implementado em `core/llm_orchestrator.py`. O orquestrador também injeta automaticamente o conteúdo de `knowledge/pje_calc_official/` e as `RegrasAprendidas` ativas nos system prompts.

## Learning Engine

A cada edição bem-sucedida na tela de Prévia:
1. `learning/correction_tracker.py` → `CorrectionTracker.record_field_correction()` salva a correção no DB (`CorrecaoUsuario`)
2. Ao atingir `LEARNING_FEEDBACK_THRESHOLD` (padrão: 10) correções não incorporadas → dispara `LearningEngine.run_learning_session()` como background task
3. O `LearningEngine` envia os pares (extração_original, correção) ao Claude → gera `RegrasAprendidas`
4. As regras são injetadas nos prompts futuros via `learning/rule_injector.py`

Dashboard em `/admin/aprendizado`. Trigger manual via `POST /api/aprendizado/executar`.

## Banco de dados — novos modelos (infrastructure/database.py)

Além dos 5 modelos existentes, 3 novos para o Learning Engine:
- `CorrecaoUsuario` — cada correção do usuário na prévia (campo, valor_antes, valor_depois, confiança_ia)
- `RegrasAprendidas` — regras geradas pelo LLM (condição, ação, confiança, aplicações/acertos)
- `SessaoAprendizado` — sessões periódicas de análise (status, N correções, N regras, resumo)

## Descobertas críticas (abril/2026)

### Arquivo .PJC — gerador nativo vs exportação PJE-Calc
O `pjc_generator.py` gera um template **pré-liquidação** (~52KB) que o PJE-Calc **rejeita** na importação.
Arquivos válidos são **pós-liquidação** (~60-560KB) exportados pelo próprio PJE-Calc via botão Exportar.
**Regra:** nunca usar o gerador nativo como resultado final. A automação deve completar a liquidação
e exportar via interface do PJE-Calc.

### Browser — Firefox obrigatório
O PJE-Calc Cidadão é desenvolvido para Firefox. Playwright usa Firefox (`self._pw.firefox.launch()`).
Chromium causa incompatibilidades em eventos AJAX do RichFaces, calendários e popups JSF.

### Verbas manuais — campos obrigatórios
Verbas criadas via botão "Manual" (`id="incluir"`) precisam ter `caracteristica`, `ocorrencia` e
`base_calculo` preenchidos. Sem eles, a liquidação falha com HTTP 500. O modo Expresso preenche
automaticamente esses campos.

### Verba Manual — fluxo Assunto CNJ via modal-árvore

Para criar verba via "Manual" (botão `incluir` da listagem com value="Manual"):

1. Click `incluir` → abre `verba-calculo.jsf` em "Novo" mode (breadcrumb `Cálculo > Verbas > Novo`).
2. Campo "Nome" (DOM id `formulario:descricao`) — digitar nome customizado.
3. Campo "Assunto CNJ" — **NÃO digitar livre**. Click no botão lupa 🔎 → abre modal árvore.
4. Modal mostra categorias hierárquicas (ex.: 2581 Remuneração, 2662 Férias, 1654 Contrato Individual...).
5. Expandir folder + selecionar código específico (ex.: 2792 Horas Extras dentro de 2581).
6. Click botão "Selecionar" no modal.
7. Preencher demais campos (período, base, fórmula, etc.).
8. **Salvar UMA VEZ** ao final (não é por seção).

Para `_configurar_parametros_pos_expresso` (verba já criada via Expresso): o assunto CNJ JÁ vem populado, **não precisa tocar**. Só renomear via campo "Nome" se for `expresso_adaptado`.

### Reflexos — fluxo correto (PJE-Calc Cidadão, confirmado pelo usuário)

Para configurar um reflexo (ex.: "Aviso Prévio sobre Horas Extras"):

1. **Marcar checkbox** do reflexo no painel "Exibir" da verba principal (após click em `linkDestinacoes`).
2. **Salvar** (a verba principal — checkbox sozinho não persiste).
3. **Voltar** à listagem e re-abrir "Exibir" da principal.
4. Agora o **botão "Parâmetros"** do reflexo está disponível — clicar para editar parâmetros específicos (período, base, etc.).

**Ocorrências do reflexo**: NÃO existe página própria. As ocorrências dos reflexos aparecem **dentro da página de Ocorrências da verba principal** (mesma tabela mensal). Para alterar valores específicos por mês de um reflexo, navegar para `parametrizar-ocorrencia.jsf` da PRINCIPAL — todas as ocorrências (principal + reflexos) estão na mesma tabela.

### Expresso — DOM real (verbas-para-calculo.jsf, v2.15.1, confirmado 04/05/2026)
- **54 verbas total**, distribuídas em **3 colunas × 18 linhas** — TODAS visíveis sem scroll.
- Checkboxes têm IDs no padrão `formulario:j_id82:N:j_id84:M:selecionada` (gerados por `<a4j:repeat>` aninhado).
- **NÃO usa `<label for="...">`** — o texto da verba está no `<td>` que contém o checkbox.
- Para identificar uma verba: `cb.closest('td').textContent.trim()` (NÃO procurar `label[for=cb.id]`).
- Match deve ser por **igualdade exata** do texto canônico contra `expresso_alvo` do JSON v2.
- Correção anterior do CLAUDE.md afirmava que "apenas ~27 verbas visíveis" e exigia scroll — INCORRETO no PJE-Calc Cidadão TRT7. Sem scroll necessário.
- (Nota: Multa 467 NÃO é verba Expresso — é checkbox FGTS `multaDoArtigo467` + reflexa automática na aba Verbas.)

### SSE stream — keepalive obrigatório
O SSE stream (endpoint `/api/executar/{sessao_id}`) precisa de keepalive a cada 10-15s para evitar
que o frontend (EventSource) desconecte durante operações longas (browser restart, AJAX pesado).
Thread de keepalive dedicada envia `"⏳ Processando…"` via queue.

### Histórico Salarial — extração obrigatória
O prompt de extração deve extrair histórico salarial SEMPRE (mesmo salário uniforme = 1 entrada).
Campos: nome, data_inicio, data_fim, valor, incidencia_fgts, incidencia_cs. O usuário pode
adicionar/remover entradas na prévia (botões + Adicionar / X Remover).

## Documentos de referência

@docs/diagnostico-falhas-automacao.md
@docs/analise-calc-machine-vs-agente.md

## Problema em aberto (Tomcat headless)

O Tomcat embarcado (`pjecalc.jar`) pode ter dificuldade para subir em ambientes headless. O Lancador Java (`Lancador.java:42`) executa validações de startup e pode mostrar `JOptionPane` dialogs (GUI Swing) que bloqueiam o thread principal. O Xvfb + xdotool tenta auto-dismissar, mas o Java pode não iniciar o Tomcat corretamente.

**Diagnóstico**: acessar `http://163.176.44.221:8000/api/logs/java` após deploy para ver o stdout/stderr completo do Java (capturado em `/opt/pjecalc/java.log`).

**Abordagens alternativas a considerar**:
1. Iniciar Tomcat diretamente (bypassar Lancador) usando `org.apache.catalina.startup.Bootstrap` com as JARs de `bin/lib/`
2. Criar Java agent (`-javaagent`) para interceptar e silenciar `JOptionPane.showMessageDialog()`
3. Patch do bytecode de `Lancador.class` para remover a chamada GUI
