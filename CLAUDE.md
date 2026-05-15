# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## DISTINÇÃO ARQUITETURAL FUNDAMENTAL — Prévia vs. Estratégia de Preenchimento

> **Esta distinção é crítica e NUNCA pode ser violada. Qualquer confusão entre esses dois
> conceitos causa bugs graves na interface e na automação.**

### O que é a Prévia (`templates/previa_v2.html`)

A prévia é um **espelho fiel do PJE-Calc Cidadão**. Cada campo, label, opção de select e
estrutura de formulário na prévia deve corresponder **exatamente** ao que o PJE-Calc exibe
em sua interface. Nada a mais, nada a menos.

**Regra absoluta:** NUNCA adicionar à prévia qualquer conteúdo que não seja um campo real
do PJE-Calc. Isso inclui:
- ❌ Dicas de fluxo de trabalho ("💡 Para equiparação salarial, configure assim...")
- ❌ Explicações sobre estratégia jurídica ou contábil
- ❌ Orientações sobre como a IA vai preencher
- ❌ Campos inventados que não existem no PJE-Calc
- ❌ Guias, hints, alertas ou qualquer texto instrucional

A prévia existe para que o **usuário revise e edite os dados** antes de submeter à automação,
exatamente como faria olhando para a tela do PJE-Calc.

### O que é a Estratégia de Preenchimento

A estratégia de preenchimento é a **lógica que a IA usa para configurar os parâmetros do
PJE-Calc para cada situação jurídica específica**. Ela vive no JSON gerado pela extração
(`extraction.py` + `classification.py`), não na tela.

Exemplos de estratégia de preenchimento (NUNCA visíveis na prévia):
- Para equiparação salarial → DIFERENÇA SALARIAL com `base=historico_paradigma`,
  `valor_pago.tipo=CALCULADO`, `valor_pago.base_historico=historico_autor`
- Para DIÁRIAS - INTEGRAÇÃO AO SALÁRIO → `comporPrincipal=NAO`, `proporcionalizar=NAO`
- Para estabilidade pós-demissão → reflexos manuais (Férias+1/3, 13º, FGTS) com `integralizar=SIM`

A IA lê a sentença, compreende o caso jurídico e produz os valores corretos desses parâmetros
no JSON. A prévia simplesmente **exibe esses valores** para revisão humana antes de enviar
à automação.

### Separação de responsabilidades

```
Sentença (PDF/DOCX)
    │
    ▼
extraction.py + classification.py (IA)
    │  Lê a sentença, entende o caso, decide:
    │  • Quais verbas lançar
    │  • Qual base de cálculo usar para cada verba
    │  • Se usar valor_pago CALCULADO ou INFORMADO
    │  • Período, multiplicador, divisor, incidências
    │  → Produz JSON com estratégia de preenchimento
    │
    ▼
previa_v2.html (Espelho do PJE-Calc)
    │  Exibe os campos do JSON em formulários
    │  idênticos aos do PJE-Calc para revisão humana
    │  O usuário pode editar qualquer campo
    │  NÃO mostra dicas de estratégia — só campos
    │
    ▼
playwright_pjecalc.py (Automação)
    │  Usa o JSON (possivelmente editado na prévia)
    │  para preencher o PJE-Calc campo a campo
    │  Segue a estratégia definida no JSON
```

### Teste rápido: "Isso pertence à prévia ou à estratégia?"

**Pertence à prévia** (campo real do PJE-Calc):
- `tipoDaBaseTabelada`: seletor Maior Remuneração / Histórico Salarial / Piso Salarial
- `tipoDoValorPago`: INFORMADO | CALCULADO
- `integralizarBase`: Sim | Não
- `proporcionalizaHistorico`: Sim | Não
- `gerarPrincipal`: DEVIDO | DIFERENÇA
- `comporPrincipal`: SIM | NAO

**Pertence à estratégia** (lógica no JSON, invisível na prévia):
- "Para equiparação salarial, configure tipoDoValorPago=CALCULADO"
- "Para DIÁRIAS, use comporPrincipal=NAO"
- "Para estabilidade, crie reflexo manual de FGTS com integralizar=SIM"

---

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

O Learning Engine opera em **dois planos de aprendizado complementares**:

### Plano 1 — Correções na Prévia (reativo, campo a campo)

A cada edição bem-sucedida na tela de Prévia:
1. `learning/correction_tracker.py` → `CorrectionTracker.record_field_correction()` salva a correção no DB (`CorrecaoUsuario`)
2. Ao atingir `LEARNING_FEEDBACK_THRESHOLD` (padrão: 10) correções não incorporadas → dispara `LearningEngine.run_learning_session()` como background task
3. O `LearningEngine` envia os pares (extração_original, correção) ao Claude → gera `RegrasAprendidas`
4. As regras são injetadas nos prompts futuros via `learning/rule_injector.py`

Esse plano captura **erros de extração**: o usuário corrigiu um campo porque a IA leu errado
a sentença (ex.: data de admissão errada, nome de verba trocado).

### Plano 2 — Estratégia de Preenchimento a partir de Cálculos Finalizados (generativo)

> **Este é o plano mais valioso a longo prazo.** Enquanto o Plano 1 corrige erros de leitura,
> o Plano 2 aprende **como configurar corretamente os parâmetros do PJE-Calc para cada
> verba em cada situação jurídica** — a estratégia de preenchimento — a partir de cálculos
> revisados, confirmados e exportados com sucesso pelo usuário.

**Gatilho:** quando um cálculo atinge `status = 'pjc_exportado'` → disparar
`EstrategiaEngine.extrair_estrategia(calculo)` como background task.

#### Granularidade: por verba + gatilho contextual (CRÍTICO)

> **A estratégia é sempre aprendida por verba individual, nunca por "tipo de processo".**
>
> Razão: um cálculo pode ter DIFERENÇA SALARIAL + ADICIONAL NOTURNO + DIÁRIAS. Num processo
> futuro, aparecem apenas DIFERENÇA SALARIAL + DIÁRIAS. O sistema deve aplicar as estratégias
> aprendidas para cada verba de forma independente — sem exigir que o contexto global do
> processo seja idêntico.

A unidade de aprendizado é o par `(nome_verba, gatilho_contexto)`:

| nome_verba | gatilho_contexto | parametros_aprendidos |
|---|---|---|
| DIFERENÇA SALARIAL | `{motivo: "equiparação_salarial"}` | gerarPrincipal=DIFERENCA, valor_pago=CALCULADO/historico_autor, base=historico_paradigma |
| DIFERENÇA SALARIAL | `{motivo: "desvio_de_funcao"}` | gerarPrincipal=DIFERENCA, valor_pago=INFORMADO, base=maior_remuneracao |
| DIÁRIAS - INTEGRAÇÃO AO SALÁRIO | `{}` (invariante — sempre igual) | comporPrincipal=NAO, proporcionalizar=NAO |
| ADICIONAL DE INSALUBRIDADE | `{grau: "medio"}` | base=SALARIO_MINIMO, mult=0.20 |
| ADICIONAL DE INSALUBRIDADE | `{grau: "maximo"}` | base=SALARIO_MINIMO, mult=0.40 |

**`gatilho_contexto`** é um dict com os sinais mínimos extraídos da sentença que são
específicos àquela verba — não ao processo como um todo. Verbas invariantes (DIÁRIAS) têm
`gatilho_contexto = {}`. Verbas dependentes de grau/motivo têm o sinal correspondente.

#### Identificação robusta do gatilho em novos processos

O problema central é: dado um novo processo, como saber que a DIFERENÇA SALARIAL desse caso
corresponde ao cenário `equiparação_salarial` e não a `desvio_de_funcao`?

**Abordagem híbrida (do mais rápido ao mais robusto):**

1. **Match direto por palavras-chave extraídas** (primeiro filtro, O(1)):
   O `extraction.py` já extrai o `motivo` de cada verba deferida. Se o JSON contiver
   `{verba: "DIFERENÇA SALARIAL", motivo: "equiparação salarial"}` → match exato com
   `{motivo: "equiparação_salarial"}`. Resolve a maioria dos casos.

2. **Julgamento LLM por similaridade semântica** (fallback para ambíguos):
   Quando o match direto não é conclusivo, o `rule_injector.py` envia ao Claude:
   - O trecho da sentença relativo àquela verba
   - As estratégias candidatas disponíveis para `nome_verba`
   - Pergunta: "Qual dessas estratégias se aplica a este caso? Ou nenhuma?"
   O LLM responde com o ID da estratégia ou `null` (aplicar defaults).

3. **Sem match → defaults neutros** (fallback final):
   Se nenhuma estratégia for identificada com confiança suficiente, o sistema usa os
   parâmetros padrão — nunca força uma estratégia errada.

#### Ciclo de vida da confiança

```
EstrategiaAprendida nasce com confiança = 0.5  (1ª ocorrência)
    │
    ├─ Aplicada em novo caso → usuário não alterou os params na prévia
    │       → confiança += 0.1  (estratégia validada)
    │
    ├─ Aplicada em novo caso → usuário alterou os params na prévia
    │       → confiança -= 0.2  (estratégia inadequada para esse caso)
    │       → registrar a correção como CorrecaoUsuario (Plano 1 também aprende)
    │
    └─ confiança < 0.2 → estratégia arquivada (não injetada mais em prompts)
```

#### Pipeline do Plano 2

```
Cálculo exportado (pjc_exportado)
    │
    ▼
EstrategiaEngine.extrair_estrategia(calculo)
    │  Para cada verba no cálculo:
    │  • Extrai (nome_verba, params_usados, contexto_verba_na_sentença)
    │  • Verifica se já existe EstrategiaAprendida para esse par (nome, gatilho)
    │    → SIM: incrementa n_calculos_origem, ajusta confiança
    │    → NÃO: Claude analisa se os params são generalizáveis → cria nova entrada
    │
    ▼
EstrategiaAprendida (DB) — por verba
    │  • nome_verba: str          # ex.: "DIFERENÇA SALARIAL"
    │  • gatilho_contexto: dict   # ex.: {"motivo": "equiparação_salarial"}
    │  • parametros: dict         # params confirmados (base, divisor, mult, etc.)
    │  • confianca: float         # 0–1
    │  • n_calculos_origem: int
    │  • calculos_origem: list[str]   # sessao_ids
    │
    ▼
rule_injector.py (em extraction.py / classification.py)
    │  Para cada verba identificada na sentença:
    │  • Busca EstrategiasAprendidas com nome_verba == verba.nome
    │  • Tenta match de gatilho_contexto (direto ou LLM)
    │  • Injeta parametros como defaults no JSON de saída
    │  • IA pode sobrescrever se o caso apresentar sinais distintos
```

**Diferença fundamental entre os dois planos:**

| | Plano 1 — Correções | Plano 2 — Estratégia |
|---|---|---|
| **Gatilho** | Edição na Prévia | Exportação do PJC |
| **Sinal** | Erro corrigido | Acerto confirmado |
| **Aprende** | O que a IA leu errado | Como configurar certo |
| **Escopo** | Campo individual | Combinação de parâmetros por verba/cenário |
| **DB** | `CorrecaoUsuario` | `EstrategiaAprendida` |
| **Natureza** | Reativo | Generativo |

Dashboard em `/admin/aprendizado`. Trigger manual via `POST /api/aprendizado/executar`.

## Banco de dados — novos modelos (infrastructure/database.py)

Além dos 5 modelos existentes, **4 novos** para o Learning Engine:
- `CorrecaoUsuario` — cada correção do usuário na prévia (campo, valor_antes, valor_depois, confiança_ia) [Plano 1]
- `RegrasAprendidas` — regras de extração geradas pelo LLM a partir de correções (condição, ação, confiança, aplicações/acertos) [Plano 1]
- `SessaoAprendizado` — sessões periódicas de análise (status, N correções, N regras, resumo) [Plano 1]
- `EstrategiaAprendida` — padrões de parametrização do PJE-Calc extraídos de cálculos finalizados (cenario_juridico, nome_verba, parametros JSON, confiança, calculos_origem) [Plano 2]

## Descobertas críticas (abril/2026)

### Novo cálculo: Seam em modo "criação" após save — menu lateral incompleto

Ao iniciar um **novo cálculo** (`Cálculo > Novo`), mesmo após o Salvar da Fase 1 (URL passa a
ter `conversationId`), a **conversa Seam permanece em modo "criação"**. Nesse estado, o menu
lateral exibe apenas itens globais (`li_calculo_novo`) e nunca os itens per-seção
(`li_calculo_ferias`, `li_calculo_historico_salarial`, etc.) — porque o backing bean JSF ainda
não "abriu" o cálculo para edição.

Isso **não se aplica** a cálculos já existentes abertos via Recentes ou URL direta numa sessão
ativa — nesses casos o menu lateral já aparece completo desde o carregamento.

**Consequência para a automação:** `_clicar_menu_lateral` não encontra os `<li>` per-seção e
cai no fallback de URL direta (`goto(historico-salarial.jsf?conversationId=X)`). Se o Seam
rejeitar essa URL no modo "criação", as seções são **puladas silenciosamente**.

**Correção implementada** (em `fase_dados_processo`, após o save):
1. Verificar se menu lateral tem `li_calculo_ferias` ou `li_calculo_historico` no DOM.
2. Se não tiver: tentar `goto(calculo.jsf?conversationId=X)` (pode transicionar Seam).
3. Se ainda incompleto: `_reabrir_calculo_recentes()` — cria nova conversa Seam em edit mode
   via duplo-clique nos Recentes (mesmo mecanismo que um humano usaria).

**Atenção:** após `_reabrir_calculo_recentes()`, `fase_parametros_gerais` deve clicar
explicitamente na aba "Parâmetros do Cálculo" — já implementado nessa função.

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
5. Expandir folder + selecionar código específico. **Preferência padrão: clicar em `2581 - Remuneração, Verbas Indenizatórias e Benefícios`** (categoria mais ampla que cobre a maior parte das verbas trabalhistas). Refinar para subcódigos (2792 HE, 1666 Insalubridade, etc.) só quando a sentença for específica e o reflexo na liquidação se beneficiar.
6. Click botão "Selecionar" no modal.
7. Preencher demais campos (período, base, fórmula, etc.).
8. **Salvar UMA VEZ** ao final (não é por seção).

Para `_configurar_parametros_pos_expresso` (verba já criada via Expresso): o assunto CNJ JÁ vem populado, **não precisa tocar**. Só renomear via campo "Nome" se for `expresso_adaptado`.

### Verba Manual tipo REFLEXA — ⚠️ DOM NÃO MAPEADO (lacuna pendente)

> **Atenção:** os campos e o comportamento de `verba-calculo.jsf` quando o campo `tipo`
> é alterado de `PRINCIPAL` para `REFLEXA` **não foram inspecionados diretamente no DOM**.
> Esta é uma lacuna de conhecimento confirmada.

O que se sabe (via manual, não por inspeção):
- Ao selecionar Tipo=REFLEXA, o formulário provavelmente exibe um seletor da verba principal
  à qual o reflexo se vincula
- Alguns parâmetros podem ser herdados da principal (período, base) ou configuráveis
  independentemente
- A característica (`FERIAS`, `DECIMO_TERCEIRO_SALARIO`, `COMUM`) permanece configurável

O que **não se sabe** (requer inspeção DOM):
- ID do seletor de "verba principal vinculada"
- Quais campos somem / aparecem com Tipo=REFLEXA
- Se o campo "Assunto CNJ" permanece obrigatório
- Como o sistema valida o vínculo principal→reflexa no save

**Ação necessária:** inspecionar `verba-calculo.jsf` com Tipo=REFLEXA selecionado e
documentar os IDs e comportamentos aqui. Até isso ser feito, usar o **fluxo via painel
"Exibir"** (seção "Reflexos — fluxo correto" abaixo) que foi confirmado pelo usuário.

### Reflexos pós-contratuais (Estabilidade Gestante/Acidentária, Lei 9.029) — fórmulas confirmadas via vídeo (NotebookLM)

Para verbas pós-demissão (estabilidade, dispensa discriminatória), o PJE-Calc **NÃO** gera reflexos automáticos. Cada um é uma **verba Manual com Tipo=REFLEXO** vinculada à principal:

| Reflexo | Característica | Divisor | Multiplicador | Quantidade | Integralizar | Ajustar Ocorrências |
|---|---|---|---|---|---|---|
| **Férias + 1/3** | FERIAS | 12 | **1.33** | 12 | ✅ SIM | Desmarcar meses intermediários, manter só último |
| **13º Salário** | DECIMO_TERCEIRO_SALARIO | 12 | 1 | 12 | ✅ SIM | Mesmo ajuste |
| **FGTS** | COMUM | 100 | **8** (ou 11.2 com multa 40%) | — | — | Mantém mensal todo período |

**Armadilhas críticas**:
1. **Esquecer "Integralizar"** → sistema puxa proporcional em vez do salário integral
2. **Não ajustar Ocorrências** após save → 13º/Férias geram pagamento duplicado de meses cheios
3. **Esperar FGTS automático** após demissão → não acontece; precisa Manual obrigatoriamente

**Verba principal (Estabilidade)**:
- Modo: Expresso "INDENIZAÇÃO ADICIONAL" (ou "INDENIZAÇÃO POR DANO MATERIAL" — facilidade)
- Característica: COMUM, Ocorrência: MENSAL
- Base: Maior Remuneração (do histórico) com **Proporcionalizar=SIM** (calcula pontas corretamente)
- Período: dia+1 da demissão até fim da garantia

Citações do vídeo (via NotebookLM):
- "O pjt cal ele não apura fundo de garantia após a demissão de forma automática" (00:02:10)
- "A importância de integralizar lá no reflexo: ele puxa de forma automática o valor total" (00:04:15)

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

### Exportar .PJC — captura via listener pré-clique (confirmado 12/05/2026)

O fluxo real de exportação no PJE-Calc (verificado inspecionando `exportacao.xhtml`):

1. Clicar botão "Exportar" (`a4j:commandButton id="exportar"`) → AJAX re-render (text/xml, ~28KB)
2. O AJAX re-render inclui `<s:span rendered="#{downloadDisponivel}">` com `linkDownloadArquivo`
   e um **`<script>` inline** que auto-dispara `jsfcljs(form, {'formulario:linkDownloadArquivo':...}, '')`
   **imediatamente** durante o processamento do re-render (antes de qualquer código Python poder reagir)
3. O browser executa o script → POST para exportacao.jsf → ZIP bytes → Playwright emite evento `"download"`

**CRÍTICO**: registrar `page.on("download", ...)` e `page.on("response", ...)` **ANTES** de clicar
Exportar. O auto-jsfcljs dispara durante o AJAX, o evento `download` já foi emitido antes que qualquer
polling nosso execute. O código antigo (Fase A com `expect_response`, Fase B/E com poll por
`linkDownloadArquivo`) perdia o evento por chegar tarde.

Implementação correta (em `_exportar_pjc()`):
```python
_dl_data: list[bytes] = []
self._page.on("download", lambda dl: _dl_data.append(pathlib.Path(dl.path()).read_bytes()))
self._page.on("response", _on_response)  # também captura ZIP via HTTP
try:
    btn.click(force=True)
    self._page.wait_for_timeout(15000)
finally:
    self._page.remove_listener("download", _on_download)
    self._page.remove_listener("response", _on_response)
```

Validado: capturou `PROCESSO_..._CALCULO_71_DATA_12052026_HORA_005357.PJC` (8065 bytes) ✅

### Seam EPC FlushMode.MANUAL — cálculos novos NÃO persistem no H2 local (confirmado 12/05/2026)

**Descoberta crítica**: no PJE-Calc Cidadão com banco H2 local, cálculos criados via automação
("Cálculo > Novo") **nunca aparecem em Buscar/Recentes na mesma sessão** — ou em sessões posteriores.

**Causa raiz**: Seam 2 usa `FlushMode.MANUAL` para o Extended Persistence Context (EPC). A transação
JTA abrange **toda a conversa Seam** (não por request). Nenhuma entidade é commitada no H2 até que
`@End` seja disparado explicitamente.

`@End` só ocorre quando um bean retorna um navigation outcome mapeado em `pages.xml` com
`<end-conversation before-redirect="true"/>` — exemplos: `if-outcome="exportacao"` (chamado por
`apresentadorExportacao.iniciar()`), `if-outcome="calculo"`, etc.

**Em modo "criação"** (nova conversa Seam após "Cálculo > Novo"):
- O sidebar NÃO renderiza `li_operacoes_exportar` → `iniciar()` não pode ser chamado pelo menu
- Force-POST do component ID `formulario:j_id38:2:j_id41:4:j_id46` não funciona (JSF bloqueia
  ações de componentes não renderizados)
- Clicar links globais (`li_calculo_novo`, `li_tela_inicial`, `li_tabelas_*`) cria **novas conversas**
  mas NÃO faz flush do EPC da conversa pai

**Consequência para testes locais**: o fluxo Criar Novo → Preencher → Liquidar → Exportar só pode
ser validado end-to-end em produção (TRT7) com PostgreSQL. O H2 local retém tudo na memória JTA
sem commit.

**O que funciona localmente**: abrir cálculo existente via Recentes (duplo-clique) → edit mode → Exportar.
A conversa Seam em edit mode chama `iniciar()` corretamente via `li_operacoes_exportar`.

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
