# Continuidade da Sessão — 2026-03-26

Este documento registra o estado exato do projeto ao final da sessão de trabalho de 26/03/2026.
Para retomar amanhã: `git pull origin main` e leia este arquivo primeiro.

---

## Estado do repositório

Commit atual: `6ff8461`
Branch: `main` — sincronizado com GitHub (`bragabarreto/pjecalc-agente`)

### Commits desta sessão (do mais antigo ao mais recente)

| Commit | Descrição |
|---|---|
| `46010a9` | feat: extração PDF nativa, Structured Outputs e camada de parametrização |
| `b3254cb` | fix: crash honorarios list vs dict em database.criar_calculo |
| `99158eb` | fix: bloquear processamento sem IA + corrigir schema Structured Outputs |
| `cd9b78d` | fix: remover output_config + bloquear relatório sem IA |
| `6ff8461` | fix: remover gerar_pjc() síncrono de confirmar_previa() — **resolve Service Unavailable** |

---

## O que foi implementado nesta sessão

### 1. Regra IA-only (bloqueante)
- Processamento SEM IA agora retorna `_erro_ia: True` e encerra sem gerar prévia
- Documentado em `CLAUDE.md` como "Regra de negócio obrigatória — IA-only"
- `extraction.py`: todos os 3 caminhos (`_extrair_via_llm`, `_extrair_via_llm_pdf`, `_extrair_de_relatorio_estruturado`) bloqueiam em falha
- `webapp.py`: detecta `_erro_ia`, cria cálculo com `status="erro_ia"` e encerra
- `novo_calculo.html`: exibe mensagem com link para adicionar créditos na Anthropic

### 2. Camada de parametrização (`modules/parametrizacao.py`)
- Implementa o "cérebro" do pipeline (skill `pjecalc-parametrizacao`)
- `gerar_parametrizacao(dados)` → 11 passos: dados_processo, parametros_gerais, historico_salarial, verbas, fgts, contribuicao_social, imposto_renda, correcao_juros, honorarios, alertas
- `_passo_parametros_gerais`: calcula prescrição quinquenal (ajuizamento - 5 anos), jornada, prescrição FGTS
- `_passo_verbas`: Lançamento EXPRESSO vs MANUAL por verba, reflexos automáticos
- `_passo_correcao_juros`: ADC 58 — IPCA-E pré-judicial + SELIC judicial; detecta réu público (EC 113/2021)
- `_gerar_alertas`: campos confiança < 0.7, inconsistências rescisão×verbas, etc.
- Integrado em `webapp.py` como Fase 2c — resultado salvo em `dados["_parametrizacao"]`

### 3. Fix database crash (honorários D7)
- `database.py` `criar_calculo()`: normaliza `honorarios` de `list[dict]` → `dict` antes de chamar `.get()`
- D7 mudou `honorarios` para lista de registros; `database.py` não havia sido atualizado

### 4. Fix output_config Anthropic (union types)
- Tentativa de usar Structured Outputs (`output_config`) falhou: limite de 16 union types, schema tinha 53
- Removido `output_config` de todos os 3 call sites — parser `_limpar_e_parsear_json()` é suficiente

### 5. Fix "Service Unavailable" após confirmar prévia (CRÍTICO)
- **Causa**: `gerar_pjc()` chamado sincronamente em `confirmar_previa()` → OOM no Railway
- **Fix**: Removido o bloco síncrono; `url_pjc` aponta para `/download/{sessao_id}/pjc` (geração lazy já existia no download route)
- **Fix template**: `instrucoes.html` linha 106 — `hon` agora normaliza `list[dict]` → `dict` (D7)

---

## Estado atual do pipeline (o que funciona)

```
PDF/DOCX → ingestion.py → extraction.py (Claude API) → parametrizacao.py → prévia web → confirmar → /instrucoes
```

- **Ingestão**: OK
- **Extração via IA**: OK — Claude API com prompt estruturado, confidence scores por campo
- **Regra IA-only**: OK — bloqueia quando API indisponível
- **Parametrização**: OK — gera passo_1..passo_10 + alertas
- **Prévia web** (`/previa/{sessao_id}`): OK — campos editáveis inline, salvo no banco
- **Confirmação** (`POST /previa/{sessao_id}/confirmar`): OK (corrigido nesta sessão) — redireciona para `/instrucoes/{sessao_id}`
- **Página instrucoes** (`/instrucoes/{sessao_id}`): OK — mostra parâmetros + botão "Executar Automação"
- **Automação SSE** (`GET /api/executar/{sessao_id}`): EM ABERTO — veja seção "Próximos passos"

---

## Problemas em aberto

### A) Tomcat não inicializa no Railway (problema principal)

O Tomcat embarcado (`pjecalc.jar`) não está subindo no Railway.

**Diagnóstico atual** (`docs/lancador-analysis.md`):
- Log para em `[TRT8] Configurando variaveis basicas.`
- Lancador Java pode exibir `JOptionPane` (GUI Swing) que bloqueia o thread principal
- `iniciarPjeCalc.sh` usa Xvfb + xdotool para auto-dismiss, mas não está funcionando

**Abordagens a tentar** (em ordem de preferência):
1. Java Agent (`dialog-suppressor.jar`) — intercepta `JOptionPane` via Javassist sem modificar o JAR
2. Bootstrap bypass — iniciar Tomcat diretamente via `org.apache.catalina.startup.Bootstrap`
3. xdotool aprimorado — adicionar `fluxbox`, aumentar polling, alternar Enter/Escape

**Como diagnosticar**:
```
GET /api/logs/java    # stdout+stderr completo do Java
GET /api/screenshot   # screenshot do Xvfb :99
GET /api/ps           # processos em execução
```

### B) Automação Playwright (fases incompletas)

O módulo `modules/playwright_pjecalc.py` existe e tem 9 fases, mas:
- Depende do Tomcat estar rodando (problema A acima)
- Não foi testado end-to-end (Tomcat nunca subiu no Railway)
- Seletores JSF ainda não foram mapeados com PJE-Calc real rodando

**Fases implementadas** (a verificar quando Tomcat subir):
1. `fase_dados_processo` — número, vara, município, datas
2. `fase_parametros_gerais` — prescrição, data inicial apuração, jornada
3. `fase_historico_salarial` — salários por período
4. `fase_verbas` — verbas deferidas (EXPRESSO/MANUAL por verba via parametrizacao)
5. `fase_fgts` — multa 40%, saldo depositado
6. `fase_contribuicao_social` — INSS 4 checkboxes individuais
7. `fase_cartao_ponto` — (pode não existir em todas as versões)
8. `fase_irpf` — imposto de renda RRA
9. `fase_honorarios` — percentual, base, por parte
10. Liquidar → exportar → download `.PJC`

### C) Gerador `.PJC` (fallback)

`modules/pjc_generator.py` existe mas tem simplificações (valorDaCausa=0, dataAutuacao=null).
Não foi validado com round-trip no PJE-Calc real.
Deve ser calibrado após a automação Playwright funcionar (comparar XML gerado vs. exportado pelo PJE-Calc).

---

## Como retomar amanhã

### Setup na outra máquina

```bash
git clone https://github.com/bragabarreto/pjecalc-agente.git
cd pjecalc-agente/pjecalc_agent
# ou, se já clonou:
git pull origin main
```

**Variáveis de ambiente necessárias** (Railway já tem, local precisa de .env):
```
ANTHROPIC_API_KEY=...     # obrigatório — sem créditos bloqueia tudo
GEMINI_API_KEY=...        # opcional — fallback (tem timeout longo se falhar)
DATABASE_URL=...          # opcional — sem isso usa SQLite local
```

### Próximo passo recomendado: resolver Tomcat (Problema A)

1. Fazer deploy no Railway e acessar `GET /api/logs/java`
2. Copiar log completo para `docs/java-log-baseline.txt`
3. Escolher abordagem: Java Agent (preferida) ou Bootstrap bypass
4. Referência: `docs/lancador-analysis.md` + skill `pjecalc-orchestrate` (Fase 2)

### Contexto para o Claude Code na próxima sessão

Diga ao Claude Code:
> "Continua o projeto PJE-Calc agente. Leia `docs/continuidade-2026-03-26.md` e o CLAUDE.md.
> O Tomcat não está subindo no Railway — o log para em '[TRT8] Configurando variaveis basicas.'.
> Preciso resolver isso para que a automação Playwright funcione. Use a skill /pjecalc-orchestrate Fase 2."

---

## Arquivos-chave para referência rápida

| Arquivo | Papel |
|---|---|
| `CLAUDE.md` | Contexto completo do projeto — **ler primeiro** |
| `modules/extraction.py` | Extração via Claude API + regra IA-only |
| `modules/parametrizacao.py` | Cérebro do pipeline — skill pjecalc-parametrizacao |
| `modules/playwright_pjecalc.py` | Automação PJE-Calc via Playwright (9 fases) |
| `modules/pjc_generator.py` | Gerador nativo .PJC (fallback) |
| `database.py` | ORM SQLAlchemy — entidades Processo, Calculo, InteracaoHITL |
| `webapp.py` | FastAPI — rotas principais + SSE executor |
| `iniciarPjeCalc.sh` | Startup do PJE-Calc no Railway (Xvfb + xdotool) |
| `docker-entrypoint.sh` | Ordem de inicialização: PJE-Calc bg → uvicorn imediato |
| `docs/lancador-analysis.md` | Análise do Lancador Java (bloqueio no Railway) |
| `docs/diagnostico-falhas-automacao.md` | Diagnóstico de falhas na automação |
