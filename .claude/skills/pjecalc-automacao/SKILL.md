# pjecalc-automacao — Automação Playwright até o .PJC

> **Autoridade arquitetural:** `pjecalc-transformacao`. Esta skill documenta a implementação
> real das Fases 4–6 do pipeline. Em caso de conflito com `pjecalc-transformacao`, ela prevalece.

## Regra inviolável

> **O arquivo .PJC APENAS pode ser gerado pelo PJe-Calc Cidadão via Playwright.**
>
> Gerar ZIP+XML externamente (Python gerando ISO-8859-1) é PROIBIDO. O PJe-Calc
> Institucional rejeita qualquer arquivo que não tenha sido exportado pelo próprio PJe-Calc.
> Se a exportação Playwright falhar — corrija a automação, não contorne gerando arquivo externo.

---

## Por que esta skill existe

A automação contra o PJe-Calc Cidadão (JSF/RichFaces, porta 9257) tem padrões não-óbvios
que causam falhas silenciosas quando ignorados:
- AJAX sem reset → falso positivo nas esperas seguintes
- URL base capturada errada → 404 em todas as seções pós-Expresso
- `fill()` em datas → campo vazio no servidor JSF (aceita no DOM mas rejeita no ViewState)
- Parâmetros e Ocorrências da verba ignorados → liquidação com valores padrão incorretos

Esta skill documenta o estado atual real do código (`modules/playwright_pjecalc.py`),
incluindo os fixes recentes e os padrões obrigatórios.

---

## Fluxo completo — Fases 4 a 6

```
JSON validado e confirmado (saída do pjecalc-processamento)
    │
    ▼ FASE 4 — Pré-verificações (webapp.py)
    │  6 checks sequenciais — ver references/fases-playwright.md#pre-verificacoes
    │  Qualquer falha → SSE ERRO_EXPORTAVEL e encerra
    │
    ▼ FASE 5 — Automação Playwright (modules/playwright_pjecalc.py)
    │  Firefox headless → PJe-Calc Cidadão localhost:9257
    │  9 sub-fases em ordem ESTRITA (ver Seção abaixo)
    │  SSE streama progresso em tempo real
    │
    ▼ FASE 6 — Exportação do .PJC
    │  PJe-Calc Liquidar → PJe-Calc Exportar → expect_download()
    │  Verificar integridade ZIP (calculo.xml presente, >= 1KB)
    │  SSE: DOWNLOAD_LINK_CALC:{url}
    ▼
    Arquivo .PJC válido pronto para importação no PJe-Calc Institucional
```

---

## Monitor AJAX Global — padrão obrigatório

Injetar ANTES de qualquer interação com o PJe-Calc:

```python
page.evaluate("""() => {
    window.__ajaxCompleto = true;
    if (typeof jsf !== 'undefined' && jsf.ajax) {
        jsf.ajax.addOnEvent(function(data) {
            if (data.status === 'begin') window.__ajaxCompleto = false;
            if (data.status === 'success' || data.status === 'complete')
                window.__ajaxCompleto = true;
        });
    }
}""")
```

Aguardar após cada ação AJAX:

```python
def _aguardar_ajax(page, timeout=15000):
    page.wait_for_function("() => window.__ajaxCompleto === true", timeout=timeout)
    # RESET OBRIGATÓRIO — sem isso, a próxima espera retorna imediatamente
    # com o 'true' da operação anterior (falso positivo em cascata AJAX)
    page.evaluate("() => { window.__ajaxCompleto = false; }")
```

---

## Navegação por URL — Section Map

`_calculo_url_base` deve sempre terminar em `/calculo/`.
A função `_capturar_base_calculo()` normaliza isso automaticamente.

```python
_URL_SECTION_MAP = {
    "Dados do Cálculo":    "calculo.jsf",
    "Histórico Salarial":  "historico-salarial.jsf",
    "Verbas":              "verba/verba-calculo.jsf",
    "FGTS":                "fgts.jsf",
    "Contribuição Social": "inss/inss.jsf",
    "Honorários":          "honorarios.jsf",
    "Imposto de Renda":    "irpf.jsf",
    "Multas e Indenizações": "multas-indenizacoes.jsf",
    "Liquidar":            "liquidacao.jsf",
}
# URL construída: {_calculo_url_base}{jsf_page}?conversationId={id}
```

**⚠ Armadilha crítica (fix ee5f582):**
Após salvar o Expresso, a página fica em `calculo/verba/verbas-para-calculo.jsf`.
Sem normalização, `_calculo_url_base` captura `.../calculo/verba/` → todos os paths
ficam dobrados → HTTP 404 em FGTS, Honorários, Liquidar, etc.

A solução está em `_capturar_base_calculo()`:
```python
m_calculo = re.search(r'(https?://.+/calculo/)', base)
if m_calculo:
    base = m_calculo.group(1)  # normaliza para .../calculo/
```

---

## 13 Fases da Automação Playwright

> Sequência real confirmada por inspeção direta de `preencher_calculo()` (linha 3987).
> Detalhes de código em `references/fases-playwright.md`.
> IDs DOM confirmados em `references/dom-ids.md`.

### Fase 1 — Login e Navegação Inicial
```
→ _instalar_monitor_ajax()
→ _verificar_e_fazer_login()
→ _ir_para_novo_calculo() — menu "Novo" (NUNCA "Cálculo Externo")
```

### Fase 2 — Dados do Processo + Parâmetros Gerais
```
→ fase_dados_processo(): número CNJ, partes, estado, município, admissão, demissão, remuneração
→ fase_parametros_gerais(): data inicial de apuração, carga horária padrão
```

### Fase 3 — Histórico Salarial (historico-salarial.jsf)
```
→ Para cada entrada em dados["historico_salarial"]:
    → Clicar Novo → preencher nome, tipo variação, valor, competência inicial/final, FGTS/INSS
    → Clicar cmdGerarOcorrencias → aguardar AJAX → Salvar
```

### Fase 4 — Verbas (verba/verbas-para-calculo.jsf + verba/verba-calculo.jsf)

**4a — Lançamento Expresso:**
```
→ Clicar botão "Expresso" → verbas-para-calculo.jsf (checkboxes)
→ Marcar checkboxes das verbas predefinidas
→ Clicar Salvar → aguardar AJAX
→ _capturar_base_calculo() ← ATUALIZA conversationId e normaliza URL base
→ _configurar_reflexos_expresso() ← chamada DENTRO de _tentar_expresso() após salvar
```

**4b — Parâmetros e Ocorrências (pós-Expresso):**
```
→ _pos_expresso_parametros_ocorrencias() ← para CADA verba principal (não reflexa):
    • _configurar_parametros_verba(): período início/fim, percentual, base de cálculo
    • _configurar_ocorrencias_verba(): gerar ocorrências + salvar
```

**4c — Lançamento Manual (verbas não disponíveis no Expresso):**
```
→ Clicar botão "Manual" → verba-calculo.jsf (formulário)
→ Preencher nome, característica, ocorrência, tipo, incidências
→ Período De / Período Até: press_sequentially + Escape
→ Multiplicador (percentual), base de cálculo, divisor, quantidade
→ Clicar Salvar → aguardar AJAX → retornar à listagem
```

### Fase 5 — Multas e Indenizações (multas-indenizacoes.jsf) *(condicional)*
```
→ Apenas se dados["multas"] não vazio
→ Para cada item (dano moral, dano material, multa art. 477, multa art. 467):
    → Clicar "Novo" → nome, valor, tipo → Salvar
```

### Fase 6 — FGTS (fgts.jsf)
```
→ Destino: PAGAR ou DEPOSITAR
→ Alíquota: DOIS_POR_CENTO / OITO_POR_CENTO
→ Multa 40%: checkbox formulario:multa
→ Compor Principal: SIM/NAO
→ Incidência: select formulario:incidenciaDoFgts
→ Salvar
```

### Fase 7 — Contribuição Social / INSS (inss/inss.jsf)
```
→ Apurar segurado sobre salários devidos
→ Cobrar do reclamante
→ Com correção trabalhista
→ Salvar
```

### Fase 8 — Cartão de Ponto (cartaodeponto/apuracao-cartaodeponto.jsf)
```
→ Extrai jornada_diaria e jornada_semanal de dados["contrato"]
→ Clicar Novo → preencher jornada diária, jornada semanal, intervalo intrajornada
→ Salvar
```

### Fase 9 — Faltas
```
→ Apenas se dados["faltas"] não vazio
→ Para cada falta: data, tipo, motivo → Salvar
```

### Fase 10 — Férias (ferias.jsf)
```
→ Para cada período em dados["ferias"]:
    → Clicar Novo
    → situacao: VENCIDAS / PROPORCIONAIS / GOZADAS
    → periodo_inicio / periodo_fim (press_sequentially + Escape)
    → abono: checkbox
    → dobra: checkbox
    → Salvar
```

### Fase 11 — Parâmetros de Atualização (correcao-juros.jsf)
```
→ Stub — loga "Fase 6 — Parâmetros de atualização (preenchidos na Fase 1 — ignorado)"
→ Não realiza preenchimento adicional (parâmetros já configurados nos Dados do Processo)
```

### Fase 12 — Imposto de Renda (irpf.jsf)
```
→ Se dados["imposto_renda"]["apurar"] == False → pula fase
→ Tributação exclusiva, regime de caixa
→ Dedução INSS, honorários reclamante
→ Salvar
```

### Fase 13 — Honorários (honorarios.jsf)
```
→ Para cada item em dados["honorarios"]:
    → Clicar "Novo" → formulário honorário
    → Devedor: RECLAMADO / RECLAMANTE
    → Tipo: SUCUMBENCIAIS / CONTRATUAIS
    → Tipo valor: CALCULADO / INFORMADO
    → Base de apuração: Condenação / Verbas Não Compõem Principal
    → Percentual (se CALCULADO)
    → Salvar → aguardar AJAX
```

### Fase Final — Liquidar + Exportar
```
→ Navegar para Liquidar (liquidacao.jsf)
→ Preencher data de liquidação (hoje)
→ Clicar Liquidar → aguardar mensagem de sucesso
    "Não foram encontradas pendências para a liquidação"
→ Navegar para Exportar
→ expect_download() → clicar Exportar
→ _salvar_download():
    • save_as(destino)
    • Verificar tamanho >= 1KB
    • zipfile.ZipFile: testzip() + "calculo.xml" in namelist()
    • Log: "✓ .PJC válido (XXXKB, calculo.xml presente)"
→ SSE: DOWNLOAD_LINK_CALC:/download/{sessao_id}/pjc
```

---

## Padrões obrigatórios JSF/RichFaces

### Datas — NUNCA usar fill()
```python
# CERTO
locator.focus()
locator.press_sequentially("01/03/2022", delay=50)
page.keyboard.press("Escape")  # fecha Calendar popup
locator.evaluate("el => el.blur()")
_aguardar_ajax(page)

# ERRADO — aceita no DOM mas não salva no servidor
locator.fill("01/03/2022")
```

### Seletores — hierarquia em 4 níveis
```python
# Nível 1 (mais robusto) — acessibilidade
page.get_by_label("Nome do Campo")

# Nível 2 — sufixo CSS (ignora prefixo dinâmico do JSF)
page.locator("[id$='fieldname']")

# Nível 3 — XPath fuzzy
page.locator("xpath=//input[contains(@id,'fieldname')]")

# Nível 4 — CSS com escape (último recurso)
page.locator("css=input#formulario\\:fieldname")
```

### Radios com sufixo numérico
```python
# IDs como formulario:tipoDeVerba:0 → NÃO usar [id$='tipoDeVerba'] (termina em :0)
# USAR:
page.locator("[name*='tipoDeVerba'][value='PAGAR']")
# OU:
page.locator("table[id$='tipoDeVerba'] input[value='PAGAR']")
```

### Botão Salvar
```python
# ID: formulario:salvar — type="button" (não submit)
page.locator("[id$='salvar']").click()
_aguardar_ajax(page)
```

---

## SSE Protocol

```
texto livre              → log de progresso (exibido no frontend)
DOWNLOAD_LINK_CALC:{url} → link do .PJC gerado
ERRO_EXPORTAVEL::{msg}   → erro com contexto (exibido em vermelho)
[FIM DA EXECUÇÃO]        → encerra o stream SSE
```

**Keepalive obrigatório:** enviar `"⏳ Processando…"` a cada 10–15s durante operações
longas. Sem keepalive, o EventSource do frontend desconecta.

---

## Troubleshooting

| Sintoma no log | Causa | Solução |
|---|---|---|
| `404` após salvar Expresso | `_calculo_url_base` incluía `/verba/` | Fix ee5f582 — `_capturar_base_calculo()` normaliza |
| `"só formulario:fechar"` | ConversationId expirado | `_clicar_menu_lateral()` com fallback URL |
| Parâmetros da verba não abrem | Botão de ação não localizado | Seletor JS por title/text — verificar log |
| `.PJC < 1KB` | Exportação não completou | Verificar botão Exportar no PJe-Calc; reiniciar |
| `.PJC sem calculo.xml` | Exportação incompleta (não liquidou) | Conferir se Liquidar retornou sucesso |
| Timeout em Liquidar | Tomcat sobrecarregado | Watchdog reinicia automaticamente; retry |
| `ViewExpiredException` | Sessão JSF expirou | Reload da página + reinjetar AJAX monitor |
| Município não selecionado | Nome com acento ou maiúscula | Match por includes já implementado |

---

## Relação com outras skills

| Quando preciso de... | Consulte |
|---|---|
| Arquitetura geral, regras invioláveis | `pjecalc-transformacao` |
| JSON de entrada desta automação | `pjecalc-processamento` |
| Campo a campo com screenshots | `pjecalc-preenchimento` |
| Diagnóstico quando falha | `pjecalc-agent-debugger` |
| IDs DOM confirmados por inspeção | `references/dom-ids.md` (esta skill) |
| 9 fases com código detalhado | `references/fases-playwright.md` (esta skill) |
