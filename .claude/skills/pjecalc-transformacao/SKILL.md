---
name: pjecalc-transformacao
description: >
  Guia de transformação do PJe-Calc Agente para replicar o CalcMACHINE v1.6.1. Use SEMPRE
  ao implementar ou refatorar o pjecalc-agente: arquitetura 3 camadas, pipeline sentença→.PJC,
  extração com IA (Claude), automação Playwright JSF, deploy Railway/Docker, SSE, validação.
  REGRA INVIOLÁVEL: .PJC só pode ser gerado pelo PJe-Calc Cidadão via Playwright — NUNCA
  gerar nativamente (Python/ZIP/XML). Use também quando a automação falhar e precisar de
  orientação baseada no CalcMACHINE em produção. Skill orquestradora central que coordena
  calcmachine-patterns, pjecalc-automator, playwright-jsf-automator e demais skills.
---

# PJe-Calc Agente — Guia de Transformação Baseado no CalcMACHINE

## Por que esta skill existe

O CalcMACHINE v1.6.1 (SuitePlus/EnsinoPlus) é a prova de que automatizar o PJe-Calc Cidadão
de ponta a ponta funciona em produção. Esta skill documenta **como transformar o pjecalc-agente**
para replicar essa arquitetura e esse sucesso, baseando-se na análise completa do CalcMACHINE
feita em abril/2026.

O pjecalc-agente precisa deixar de ser um conjunto de scripts avulsos e se tornar um sistema
com a mesma disciplina do CalcMACHINE: separação clara de camadas, validação antes de
automação, ordem estrita de preenchimento, e tratamento robusto de erros JSF.

---

## ⛔ REGRA INVIOLÁVEL: Geração de .PJC

**O arquivo .PJC só pode ser gerado pelo PJe-Calc Cidadão, executado via automação Playwright.**

Gerar .PJC de forma nativa (Python gerando ZIP+XML) é **PROIBIDO** neste projeto. O motivo é
prático e definitivo: o PJe-Calc Institucional (sistema do TRT para inserção do cálculo no
processo judicial) **somente aceita importação de arquivos gerados pelo próprio PJe-Calc ou
PJe-Calc Cidadão**, marcando como inválidos quaisquer outros — independentemente de o XML
estar sintaticamente correto.

Portanto:

- **NUNCA** implemente, sugira ou use a skill `pjc-file-generator` neste contexto
- **NUNCA** gere ZIP+XML ISO-8859-1 como fallback para .PJC
- **NUNCA** tente replicar o formato interno do .PJC para bypass
- Se a automação Playwright falhar na fase de exportação, **corrija a automação** — não tente
  contornar gerando o arquivo por fora
- O único caminho válido: Playwright abre PJe-Calc → preenche campos → clica Calcular →
  clica Exportar → coleta o .PJC gerado pelo PJe-Calc

Esta regra não tem exceções. Código que gere .PJC fora do PJe-Calc é código morto — o
arquivo resultante será rejeitado na importação.

---

## Arquitetura-Alvo: 3 Camadas

O pjecalc-agente deve adotar a mesma separação de responsabilidades do CalcMACHINE:

```
┌──────────────────────────────────────────────────────────┐
│  CAMADA 1 — FRONTEND                                     │
│  Responsabilidades:                                      │
│  • Receber sentença (texto/PDF upload)                   │
│  • Exibir formulário de revisão do JSON (HITL)           │
│  • Validação client-side (espelha backend)               │
│  • Monitor SSE de progresso em tempo real                │
│  • NÃO executa automação — apenas observa               │
│  Tecnologias sugeridas: React/Next.js ou HTML+JS simples │
└────────────────────────┬─────────────────────────────────┘
                         │ REST API (JSON)
                         ▼
┌──────────────────────────────────────────────────────────┐
│  CAMADA 2 — BACKEND                                      │
│  Responsabilidades:                                      │
│  • Extração com IA (Claude API, temperature=0)           │
│  • Validação completa do JSON                            │
│  • Persistência (banco de dados)                         │
│  • Automação SERVER-SIDE (Playwright → PJe-Calc)         │
│  • Streaming de progresso via SSE                        │
│  • Coleta e entrega do .PJC gerado pelo PJe-Calc        │
│  Tecnologia sugerida: FastAPI (Python) ou Flask          │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP (Playwright → localhost:9257)
                         ▼
┌──────────────────────────────────────────────────────────┐
│  CAMADA 3 — PJe-Calc Cidadão (JSF/Tomcat porta 9257)    │
│  • JavaServer Faces com ViewState + AJAX                 │
│  • IDs dinâmicos (j_idt42, javax.faces.ViewState)        │
│  • PrimeFaces para dropdowns e calendários               │
│  • Única fonte autorizada para geração de .PJC           │
└──────────────────────────────────────────────────────────┘
```

**Princípio central:** a automação roda no servidor, nunca no navegador do usuário. O frontend
é apenas interface de revisão e monitoramento.

---

## Pipeline Completo: 6 Fases

O pipeline transforma uma sentença trabalhista em arquivo .PJC pronto para importação:

```
Sentença (PDF/texto)
    │
    ▼
Fase 1 — Ingestão ............... Extrair texto do PDF/receber texto colado
    │
    ▼
Fase 2 — Extração com IA ........ Claude API → JSON estruturado
    │
    ▼
Fase 3 — Validação + HITL ....... Validar JSON + revisão humana obrigatória
    │
    ▼
Fase 4 — Pré-verificações ....... 6 checks antes de iniciar automação
    │
    ▼
Fase 5 — Automação Playwright ... 9 fases contra PJe-Calc (server-side)
    │
    ▼
Fase 6 — Exportação ............. PJe-Calc gera .PJC → backend coleta e entrega
```

Cada fase tem seu próprio arquivo de referência detalhado. Consulte-os conforme a
necessidade:

| Fase | Referência | Quando consultar |
|------|-----------|-----------------|
| 1-2 | `references/extracao-ia.md` | Implementar/corrigir extração de sentença com IA |
| 3 | `references/validacao-hitl.md` | Implementar validação ou interface de revisão |
| 4-5 | `references/automacao-playwright.md` | Implementar/depurar automação do PJe-Calc |
| 6 | `references/exportacao-pjc.md` | Entender como coletar o .PJC e entregar ao usuário |
| Todas | `references/ambiente-deploy.md` | Configurar ambiente local ou cloud (Railway/Docker) |
| Todas | `references/contrato-json.md` | Entender o formato JSON que conecta IA ↔ automação |

---

## Fatores Críticos de Sucesso

Estes são os 6 padrões que fazem o CalcMACHINE funcionar em produção e que o pjecalc-agente
**deve** replicar:

### 1. Monitor AJAX Global

O padrão mais importante. Sem ele, campos parecem preenchidos mas têm valor nulo no servidor JSF.

```javascript
// Injetar na página ANTES de qualquer interação
if (!window._ajaxCompleted) {
    window._ajaxCompleted = false;
    jsf.ajax.addOnEvent(function(data) {
        if (data.status === "success") window._ajaxCompleted = true;
        if (data.status === "begin") window._ajaxCompleted = false;
    });
}
```

```python
async def aguardar_ajax(page, timeout=10000):
    await page.wait_for_function("window._ajaxCompleted === true", timeout=timeout)
    await page.evaluate("window._ajaxCompleted = false")  # reset para próxima operação
```

Toda interação com o PJe-Calc deve seguir o ciclo: ação → aguardar_ajax() → próxima ação.

### 2. Ordem Estrita de Preenchimento (9 Fases)

Alterar a ordem causa erros de ViewState e campos com valor nulo no servidor:

1. **Login/Navegação** → injeta monitor AJAX
2. **Dados do Processo** → CNJ, partes, estado, município, datas, remuneração
3. **Configurações** → checkboxes booleanos (prescrição, aviso, FGTS, multas)
4. **Histórico Salarial** → se habilitado (array mês/valor)
5. **Verbas Rescisórias** → checkboxes das verbas deferidas
6. **Adicionais** → insalubridade/periculosidade com reflexos
7. **Verbas Mensais + Jornada** → gratificações, HE, adicional noturno
8. **Honorários + Danos + CS** → honorários (array), danos morais, contribuição social
9. **Calcular + Exportar** → executa cálculo, aguarda, exporta .PJC

### 3. press_sequentially para Datas

NUNCA usar `fill()` em campos de data PrimeFaces:

```python
async def preencher_data(page, locator, valor_ddmmyyyy):
    await page.locator(locator).focus()
    await page.locator(locator).press_sequentially(valor_ddmmyyyy, delay=50)
    await page.keyboard.press("Escape")  # fecha Calendar popup
    await page.locator(locator).evaluate("el => el.blur()")
    await aguardar_ajax(page)
```

### 4. Hierarquia de Seletores JSF (4 Níveis)

JSF gera IDs dinâmicos. Use fallback em cascata:

1. `page.get_by_label("Nome do Campo")` — acessibilidade (mais robusto)
2. `page.locator("[id$='fieldname']")` — sufixo CSS (ignora prefixo dinâmico)
3. `page.locator("xpath=//input[contains(@id, 'fieldname')]")` — XPath fuzzy
4. `page.locator("css=input#id_escapado")` — CSS com escape (último recurso)

### 5. Validação Completa ANTES da Automação

Nunca iniciar automação com dados inválidos. Validar:

- Campos obrigatórios: data_admissao, remuneracao, estado, municipio
- Consistência: data_demissao > data_admissao, data_final >= data_inicial
- Cruzamento: tipo rescisão × verbas (justa causa NÃO tem aviso prévio)
- CNJ: módulo 97 com segmento fixo "5" (Justiça do Trabalho)
- Prescrição quinquenal: data_inicial >= (ajuizamento - 5 anos)

### 6. Retry com Diagnóstico

3 tentativas por fase, backoff exponencial (2s, 4s, 6s):

- Detecta Chromium crash (Target closed) → reinicia browser + reinjeta monitor AJAX
- Detecta ViewExpired → reload da página
- Captura screenshot em cada erro → `screenshots/erro_fase{N}_{timestamp}.png`

---

## SSE (Server-Sent Events) para Progresso

O CalcMACHINE streama progresso via SSE — o pjecalc-agente deve fazer o mesmo:

```python
# Backend (FastAPI)
from fastapi.responses import StreamingResponse

async def executar_automacao_stream(json_dados: dict):
    async def gerar_eventos():
        yield f"data: Iniciando automação...\n\n"

        for fase_num, fase_nome in FASES:
            yield f"data: [Fase {fase_num}/9] {fase_nome}\n\n"
            await executar_fase(fase_num, json_dados)
            yield f"data: ✓ Fase {fase_num} concluída\n\n"

        yield f"data: DOWNLOAD_LINK_PJC:{caminho_pjc}\n\n"
        yield f"data: [FIM DA EXECUÇÃO]\n\n"

    return StreamingResponse(gerar_eventos(), media_type="text/event-stream")
```

Mensagens especiais (protocolo SSE):

- Texto livre → log de progresso
- `DOWNLOAD_LINK_CALC:{url}` → link do .PJC gerado
- `DOWNLOAD_LINK_PDF:{url}` → link do relatório PDF
- `ERRO_EXPORTAVEL::{detalhe}` → erro com contexto
- `[FIM DA EXECUÇÃO]` → sinaliza término

---

## Extração com IA: Claude em vez de Gemini

O CalcMACHINE usa Gemini 2.5 Flash. O pjecalc-agente usa Claude com vantagens:

- **Structured Outputs** com Pydantic models para extração tipada
- **temperature=0** para determinismo
- **Rastreabilidade**: campo `texto_referencia` com trecho exato da sentença
- **Confidence scores** por campo para HITL automático (< 0.7 → pausa)
- Ver `references/extracao-ia.md` para prompts, modelos e exemplos

---

## Correção Monetária (ADC 58/STF + Lei 14.905/2024)

| Período | Correção | Juros |
|---------|----------|-------|
| Até 24/03/2015 | TR | 1% a.m. |
| 25/03/2015 a 10/11/2017 | IPCA-E | 1% a.m. |
| 11/11/2017 a 20/12/2020 | TR | 1% a.m. |
| Após 21/12/2020 (ADC 58) | IPCA-E | SELIC |
| Após ago/2024 (Lei 14.905) | IPCA-E | SELIC (base alterada) |

Para processos com trânsito em julgado após agosto/2024, verifique o regime aplicável na
sentença antes de parametrizar.

---

## Relação com Outras Skills

Esta skill **orquestra** as demais — ela define O QUE fazer e QUANDO consultar cada uma:

| Preciso de... | Consulte |
|---------------|----------|
| Padrões JSF do CalcMACHINE em produção | `calcmachine-patterns` |
| Pipeline de 6 fases, estruturas de dados, HITL | `pjecalc-automator` |
| Padrões genéricos Playwright para JSF | `playwright-jsf-automator` |
| Mapeamento verbas → módulos PJe-Calc | `pjecalc-parametrizacao` |
| Manual de preenchimento campo a campo | `pjecalc-preenchimento` |
| Extração NLP de sentenças trabalhistas | `juridical-nlp-extractor` |
| Docker/Railway para Java headless | `java-headless-docker` |
| Diagnóstico quando automação falha | `pjecalc-agent-debugger` |
| Decompilação de JARs do PJe-Calc | `jar-reverse-engineer` |

**NUNCA consulte `pjc-file-generator`** — geração nativa de .PJC é proibida neste projeto.

---

## Checklist de Transformação

Use esta lista para acompanhar o progresso da transformação:

- [ ] **Arquitetura 3 camadas** implementada (frontend separado do backend)
- [ ] **Extração com IA** (Claude API, temperature=0, Pydantic models)
- [ ] **Validação completa** antes da automação (todas as regras)
- [ ] **Interface HITL** para revisão humana do JSON
- [ ] **Monitor AJAX global** injetado antes de qualquer interação
- [ ] **Ordem de preenchimento** respeitada (9 fases sequenciais)
- [ ] **press_sequentially** para todos os campos de data
- [ ] **Hierarquia de seletores** em 4 níveis implementada
- [ ] **Retry com diagnóstico** (3 tentativas, screenshot, ViewExpired)
- [ ] **SSE** para streaming de progresso em tempo real
- [ ] **Exportação .PJC** somente via PJe-Calc Cidadão (Playwright)
- [ ] **Deploy cloud** funcional (Railway/Docker, Bootstrap Direto)
- [ ] **Testes** cobrindo cada fase do pipeline
