# 9 Sub-fases da Automação Playwright — Código Real

Documentação do fluxo real implementado em `modules/playwright_pjecalc.py`.
IDs DOM estão em `references/dom-ids.md` desta skill.

---

## Classe `PJECalcPlaywright` — Inicialização

```python
pjc = PJECalcPlaywright(log_callback=sse_yield)
pjc.iniciar_browser(headless=True)  # Firefox obrigatório
```

O construtor recebe `log_callback` (função que recebe string) para enviar mensagens SSE
em tempo real. Após `iniciar_browser()`, o monitor AJAX **não** é injetado ainda —
isso acontece em `fase_login` / `_ir_para_novo_calculo()`.

### Decorator `@retry`

Todas as fases principais têm `@retry(max_tentativas=3)`. Em cada falha:
1. Tira screenshot em `screenshots/erro_{fase}_{tentativa}.png`
2. Detecta crash do Firefox → reinicia browser em thread nova
3. Detecta ViewExpiredException → reload da página
4. Aguarda backoff antes da próxima tentativa

---

## Sub-fase 1 — Login e Navegação para Novo Cálculo

**Função:** `_ir_para_novo_calculo()`

```python
# 1. Navegar para o menu "Novo" via clique (não URL direta — causa ViewState inválido)
self._clicar_menu_lateral("Novo")
self._page.wait_for_load_state("networkidle", timeout=12000)
self._aguardar_ajax()

# 2. Recuperação de erro: se detectar "Erro interno", volta para home e tenta novamente
body = self._page.locator("body").text_content()
if "Erro" in body and ("Servidor" in body or "inesperado" in body):
    self._page.locator("a:has-text('Tela Inicial')").first.click()
    self._clicar_menu_lateral("Novo")

# 3. Capturar base URL e conversationId do cálculo ativo
self._capturar_base_calculo()
```

**Login automático (`_verificar_e_fazer_login`):**
- Detecta página de login por `"logon" in url.lower()`
- Tenta credenciais em ordem: `PJECALC_USER/PJECALC_PASS` env vars → padrões conhecidos
- Lança `RuntimeError` se todas falharem (não faz fallback silencioso)

**Jamais usar "Cálculo Externo"** — esse fluxo serve apenas para atualizar cálculos
já existentes. Usar sempre "Novo" para primeira liquidação de sentença.

---

## Sub-fase 2 — Dados do Processo

**Função:** `fase_dados_processo(dados)` — `@retry(max_tentativas=3)`

### 2a — Cabeçalho e Aba "Dados do Processo"

```python
# Data de criação (hoje)
self._preencher_data("dataDeCriacao", hoje, obrigatorio=False)
# Fallback: tentar outros IDs (dataCriacao, dataDeAbertura, dataAbertura, dataCalculo)

# Número CNJ — campos individuais
num = _parsear_numero_processo(proc["numero"])
self._preencher("numero", num["numero"])   # 7 dígitos sequenciais
self._preencher("digito", num["digito"])   # 2 dígitos verificadores
self._preencher("ano", num["ano"])         # 4 dígitos
self._preencher("justica", num["justica"]) # "5" (fixo — Justiça do Trabalho)
self._preencher("regiao", num["regiao"])   # 2 dígitos (tribunal)
self._preencher("vara", num["vara"])       # 4 dígitos
```

### 2b — Aba "Parâmetros do Cálculo" — Estado e Município

```python
# Estado — índice numérico (CE=5, SP=24 etc.)
_UF_INDEX = {"CE": "5", "SP": "24", ...}  # 26 UFs
self._selecionar("estado", _UF_INDEX[uf])
self._aguardar_ajax()  # município é recarregado via AJAX após estado

# Aguardar opções de município (wait_for_function mais robusto que timeout fixo)
self._page.wait_for_function("""() => {
    const s = document.getElementById('formulario:municipio');
    return s && s.options.length > 1;
}""", timeout=10000)

# Município — 3 estratégias em cascata (JS direto no select)
self._page.evaluate("""(cidade) => {
    function norm(s) {
        return (s||'').toUpperCase()
            .normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
    }
    const sel = document.getElementById('formulario:municipio');
    const c = norm(cidade);
    // Estratégia 1: exato
    for (const o of sel.options)
        if (norm(o.text) === c) { sel.value = o.value; return true; }
    // Estratégia 2: startsWith
    for (const o of sel.options)
        if (norm(o.text).startsWith(c)) { sel.value = o.value; return true; }
    // Estratégia 3: includes
    for (const o of sel.options)
        if (norm(o.text).includes(c)) { sel.value = o.value; return true; }
    return false;
}""", cidade)
```

### 2c — Datas (admissão, demissão) e Remunerações

```python
# Datas: press_sequentially OBRIGATÓRIO — fill() é aceito no DOM mas rejeitado pelo servidor JSF
self._preencher_data("dataAdmissaoInputDate", "01/03/2022")
self._preencher_data("dataDemissaoInputDate", "03/12/2024")

# Remunerações
self._preencher("valorMaiorRemuneracao", "1518,00")
self._preencher("valorUltimaRemuneracao", "1518,00")
```

**Implementação de `_preencher_data()`:**
```python
loc.focus()
self._page.keyboard.press("Control+a")
self._page.keyboard.press("Delete")
digits_only = data.replace("/", "").replace("-", "")  # remove barras — máscara insere automaticamente
loc.press_sequentially(digits_only, delay=60)
loc.dispatch_event("input")
loc.dispatch_event("change")
loc.press("Escape")  # fecha popup RichFaces Calendar sem disparar blur AJAX
```

---

## Sub-fase 3 — Verbas

**Função:** `fase_verbas(verbas_mapeadas)` — `@retry(max_tentativas=2)`

### 3a — Lançamento Expresso

**Função:** `_tentar_expresso(predefinidas)` → `tuple[bool, list[str]]`

```
1. Clicar botão "Expresso" → navega para verbas-para-calculo.jsf
2. Para cada verba predefinida:
   a. Scroll JS para tornar a checkbox visível
   b. Localizar checkbox pelo texto da <td> pai (IDs dinâmicos não são confiáveis)
   c. Marcar checkbox
3. Clicar Salvar → aguardar AJAX
4. _capturar_base_calculo()  ← ATUALIZA conversationId + normaliza URL base
5. _configurar_reflexos_expresso(predefinidas)  ← chamada DENTRO de _tentar_expresso() (linha 2142)
   ⚠ NÃO é chamada separadamente em fase_verbas — acontece internamente no Expresso
```

De volta em `fase_verbas()`, após `_tentar_expresso()` retornar:
```
6. _pos_expresso_parametros_ocorrencias(predefinidas)  ← chamada em fase_verbas
7. _lancar_verbas_manual(personalizadas)
```

**Armadilha crítica — normalização de URL base:**
Após salvar o Expresso, a página fica em `.../calculo/verba/verbas-para-calculo.jsf`.
A regex de captura sem normalização produziria base `.../calculo/verba/`, causando 404
em todas as navegações subsequentes (FGTS, Honorários, Liquidar etc.).

```python
# Em _capturar_base_calculo() — fix obrigatório:
m_calculo = re.search(r'(https?://.+/calculo/)', base)
if m_calculo:
    base = m_calculo.group(1)  # sempre termina em /calculo/
```

### 3b — Configurar Reflexos Expresso

**Função:** `_configurar_reflexos_expresso(verbas)`

Para cada verba com reflexos definidos: localiza o botão "Verba Reflexa" ou link
"Exibir" na linha correspondente na listagem, clica, marca os reflexos cabíveis, salva.

### 3c — Parâmetros e Ocorrências por Verba

**Função:** `_pos_expresso_parametros_ocorrencias(predefinidas)`

Itera pelas verbas principais (filtra verbas reflexas — `eh_reflexa` ou `tipo == "Reflexa"`):

```python
for verba in predefinidas:
    if verba.get("eh_reflexa") or verba.get("tipo") == "Reflexa":
        continue
    nome = verba["nome_pjecalc"]
    self._configurar_parametros_verba(verba, nome)
    self._configurar_ocorrencias_verba(nome)
```

**`_configurar_parametros_verba(verba, nome_na_lista)`:**
1. Localiza botão "Parâmetros da Verba" na linha que contém `nome_na_lista` via JS:
   ```python
   page.evaluate("""(nome) => {
       const linhas = document.querySelectorAll('tr, li');
       for (const linha of linhas) {
           if (linha.textContent.includes(nome)) {
               const btn = linha.querySelector('[title*="Parâmetro"], [title*="parametro"], a[id*="param"]');
               if (btn) { btn.click(); return true; }
           }
       }
       return false;
   }""", nome_na_lista)
   ```
2. Aguarda AJAX → preenche campos:
   - `periodoInicialInputDate` / `periodoFinalInputDate` (datas com `press_sequentially`)
   - `outroValorDoMultiplicador` (percentual — ex: "0.50" para 50%)
   - `tipoDaBaseTabelada` (select — ver `_BASE_CALCULO_MAP`)
   - `valorInformadoDaQuantidade` (quantidade, se informada)
3. Clica Salvar → aguarda AJAX → retorna à listagem

**`_BASE_CALCULO_MAP`:**
```python
_BASE_CALCULO_MAP = {
    "Historico Salarial":  "HISTORICO_SALARIAL",
    "Maior Remuneracao":   "MAIOR_REMUNERACAO",
    "Salario Minimo":      "SALARIO_MINIMO",
    "Piso Salarial":       "SALARIO_DA_CATEGORIA",
    "Verbas":              None,  # reflexa — não usar tipoDaBaseTabelada
}
```

**`_configurar_ocorrencias_verba(nome_na_lista)`:**
1. Localiza botão "Ocorrências da Verba" na linha que contém `nome_na_lista` (mesma técnica JS)
2. Clica botão "Gerar Ocorrências" (`cmdGerarOcorrencias`) → aguarda AJAX
3. Clica Salvar → aguarda AJAX → retorna à listagem

### 3d — Lançamento Manual (verbas não disponíveis no Expresso)

Verbas sem equivalente no Expresso são lançadas individualmente:

```
1. Clicar botão "Manual" → abre verba-calculo.jsf (formulário de nova verba)
2. Preencher:
   → Nome (formulario:descricao)
   → Característica (radio formulario:caracteristicaVerba)
   → Ocorrência (radio formulario:ocorrenciaPagto)
   → Tipo (radio formulario:tipoDeVerba)
   → Incidências (checkboxes fgts, inss, irpf)
   → Período De / Período Até (press_sequentially + Escape)
   → Multiplicador (percentual)
   → Base de cálculo (select tipoDaBaseTabelada)
3. Clicar Salvar → aguardar AJAX → retornar à listagem
```

**Campos obrigatórios para verbas manuais:** `caracteristica`, `ocorrencia`, `base_calculo`.
Sem eles, a liquidação falha com HTTP 500.

---

## Sub-fase 4 — FGTS

**Função:** `fase_fgts(fgts)` — `@retry(max_tentativas=3)`

Navega para `fgts.jsf` via `_URL_SECTION_MAP`:
```python
url = f"{self._calculo_url_base}fgts.jsf?conversationId={self._calculo_conversation_id}"
self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
```

Campos preenchidos:
```python
# Destino — radio com sufixo numérico (ver dom-ids.md para seletor correto)
self._marcar_radio_js("tipoDeVerba", "PAGAR")  # ou DEPOSITAR

# Alíquota
self._marcar_radio_js("aliquota", "OITO_POR_CENTO")  # ou DOIS_POR_CENTO

# Multa 40%
self._marcar_checkbox("multa", fgts.get("multa_40", False))

# Compor Principal
self._marcar_radio_js("comporPrincipal", "SIM")

# Incidência (select)
self._selecionar("incidenciaDoFgts", "SOBRE_O_TOTAL_DEVIDO")

# Salvar
self._clicar_salvar()
```

---

## Sub-fase 5 — Contribuição Social / INSS

**Função:** `fase_contribuicao_social(cs)` — `@retry(max_tentativas=3)`

Navega para `inss/inss.jsf`. Preenche checkboxes via `get_by_label()` (mais estável):
```python
cs_dados = dados.get("contribuicao_social", {})
self._marcar_checkbox_label("Apurar segurado sobre salários devidos", cs_dados.get("apurar_segurado_salarios_devidos"))
self._marcar_checkbox_label("Cobrar do reclamante", cs_dados.get("cobrar_do_reclamante"))
self._marcar_checkbox_label("Com correção trabalhista", cs_dados.get("com_correcao_trabalhista"))
self._clicar_salvar()
```

---

## Sub-fase 6 — Honorários

**Função:** `fase_honorarios(hon_dados, periciais)` — `@retry(max_tentativas=3)`

Navega para `honorarios.jsf`. Para cada item em `dados["honorarios"]`:

```python
for hon in honorarios:
    self._clicar_novo()   # abre formulário de honorário
    self._aguardar_ajax()

    # Devedor: RECLAMADO / RECLAMANTE
    self._marcar_radio_js("devedor", hon["devedor"])

    # Tipo: SUCUMBENCIAIS / CONTRATUAIS
    self._selecionar("tipoHonorario", hon["tipo"])

    # Tipo valor: CALCULADO / INFORMADO
    self._marcar_radio_js("tipoValor", hon["tipo_valor"])

    # Base de apuração
    self._selecionar("baseApuracao", hon["base_apuracao"])

    # Percentual (apenas se CALCULADO)
    if hon.get("percentual"):
        self._preencher("percentual", str(hon["percentual"] * 100))  # 0.15 → "15"

    # Apurar IR
    self._marcar_checkbox("apurarIr", hon.get("apurar_ir", True))

    self._clicar_salvar()
    self._aguardar_ajax()
```

**PJE-Calc NÃO tem "Ambos"** — sucumbência recíproca = dois registros separados.

---

## Sub-fase 7 — Imposto de Renda

**Função:** `fase_irpf(ir)` — `@retry(max_tentativas=3)`

Navega para `irpf.jsf`. Se `ir.get("apurar") == False`, pula a fase inteiramente.

```python
ir_dados = dados.get("imposto_renda", {})
if not ir_dados.get("apurar"):
    return  # fase ignorada

# Checkboxes principais
self._marcar_checkbox_label("Tributação exclusiva", ir_dados.get("tributacao_exclusiva"))
self._marcar_checkbox_label("Regime de caixa", ir_dados.get("regime_de_caixa"))
self._marcar_checkbox_label("Dedução INSS", ir_dados.get("deducao_inss"))
self._marcar_checkbox_label("Dedução honorários reclamante", ir_dados.get("deducao_honorarios_reclamante"))
self._clicar_salvar()
```

---

## Sub-fase 8 — Multas e Indenizações

**Função:** `fase_multas_indenizacoes(multas)` — sem retry (operação composta)

Navega para `multas-indenizacoes.jsf`. Para cada item (dano moral, material, multa art. 477/467):

```python
for multa in multas:
    self._clicar_novo()
    self._preencher("descricao", multa["nome"])           # formulario:descricao
    self._marcar_radio("valor", multa.get("tipo", "INFORMADO"))  # INFORMADO / CALCULADO
    if multa.get("valor"):
        self._preencher("aliquota", _fmt_br(multa["valor"]))
    self._selecionar("credorDevedor", multa.get("devedor", "RECLAMADO"))
    self._clicar_salvar()
    self._aguardar_ajax()
```

---

## Sub-fase 9 — Liquidar + Exportar

**Função:** `fase_liquidar_exportar(sessao_id)` — `@retry(max_tentativas=3)`

### 9a — Liquidar (AJAX, sem download)

```python
# Navegar para Liquidar
self._clicar_menu_lateral("Liquidar")
self._page.wait_for_timeout(1000)

# Preencher data de liquidação (hoje)
_dt_campo = self._page.locator("input[id*='dataLiquidacao']")
if _dt_campo.count() > 0 and not _dt_campo.first.input_value():
    self._preencher_data("dataLiquidacao", date.today().strftime("%d/%m/%Y"), False)

# Clicar Liquidar
loc = self._page.locator("[id$='liquidar']").first
loc.click()
self._aguardar_ajax(timeout=60000)  # pode demorar mais em cálculos complexos

# Verificar mensagem de sucesso
body = self._page.locator("body").text_content()
if "Não foram encontradas pendências para a liquidação" in body:
    self._log("  ✓ Liquidação concluída com sucesso")
elif "não foi possível" in body or "existem pendências" in body:
    raise RuntimeError("Liquidação falhou — verificar pendências nos dados")
```

### 9b — Exportar (.PJC via expect_download)

```python
# Navegar para Exportar
self._clicar_menu_lateral("Exportar")
self._page.wait_for_timeout(1000)

# Capturar download
with self._page.expect_download(timeout=120000) as dl_info:
    self._clicar_botao("Exportar")  # ou _clicar_salvar() que tem fallbacks

dl = dl_info.value
dest = Path(OUTPUT_DIR) / (dl.suggested_filename or f"calculo_{sessao_id}.pjc")
dl.save_as(str(dest))
```

### 9c — Verificar integridade do .PJC

```python
tamanho = dest.stat().st_size
if tamanho < 1024:
    log("⚠ .PJC suspeito: apenas {tamanho} bytes")
else:
    with zipfile.ZipFile(str(dest)) as z:
        if "calculo.xml" not in z.namelist():
            log("⚠ .PJC sem calculo.xml")
        elif z.testzip() is not None:
            log("⚠ .PJC ZIP corrompido")
        else:
            log(f"✓ .PJC válido ({tamanho//1024}KB, calculo.xml presente)")
```

### 9d — Sinalizar via SSE

```python
yield f"data: DOWNLOAD_LINK_CALC:/download/{sessao_id}/pjc\n\n"
yield "data: [FIM DA EXECUÇÃO]\n\n"
```

---

## Orquestrador — `preencher_calculo()` (linha 3987)

Sequência real confirmada por inspeção direta do código. Chamado via `preencher_como_generator()`
(linha 4178) que envolve tudo num generator Python com keepalive SSE.

```python
# Inicialização
self._instalar_monitor_ajax()                    # linha 4040
self._verificar_e_fazer_login()                  # linha 4044
self._ir_para_novo_calculo()                     # linha 4046

# Fase 1-2: Dados + Parâmetros Gerais
self.fase_dados_processo(dados)                  # linha 4049
self.fase_parametros_gerais(params_gerais)       # linha 4061

# Fase 3: Histórico Salarial (ANTES de Verbas)
self.fase_historico_salarial(dados)              # linha 4065

# Fase 4: Verbas (Expresso → Reflexos → Parâmetros/Ocorrências → Manual)
self.fase_verbas(verbas_mapeadas)                # linha 4069

# Fase 5: Multas e Indenizações (condicional — só se dados["multas"] presente)
self.fase_multas_indenizacoes(_multas)           # linha 4075

# Fase 6-7: Encargos fiscais
self.fase_fgts(...)                              # linha 4079
self.fase_contribuicao_social(...)               # linha 4083

# Fase 8-10: Jornada, Faltas, Férias
self.fase_cartao_ponto(dados)                    # linha 4087
self.fase_faltas(dados)                          # linha 4090
self.fase_ferias(dados)                          # linha 4093

# Fase 11: Parâmetros de atualização (stub — só loga, não preenche)
self.fase_parametros_atualizacao(...)            # linha 4097

# Fase 12-13: Tributação e Honorários
self.fase_irpf(...)                              # linha 4101
self.fase_honorarios(...)                        # linha 4105

# Fase Final: Liquidar → Exportar → .PJC
self._clicar_liquidar()                          # linha 4117
```

**Keepalive SSE:** thread dedicada envia `"⏳ Processando…"` a cada 10s enquanto
o orquestrador roda. Sem keepalive, EventSource do frontend desconecta durante
operações longas (browser restart, AJAX pesado do PJE-Calc).

**Keepalive SSE:** thread dedicada envia `"⏳ Processando…"` a cada 10–15s enquanto
o orquestrador roda. Sem keepalive, EventSource do frontend desconecta durante
operações longas (browser restart, AJAX pesado do PJE-Calc).

---

## Ferramentas de diagnóstico

### `mapear_campos(nome_pagina)`
Cataloga todos os `input/select/textarea` da página atual, salva em
`data/logs/campos_{nome_pagina}.json`. Chamado automaticamente ao início de cada fase.

### `_verificar_secao_ativa(secao_esperada)`
Verifica se URL ou heading contém o nome da seção esperada (normaliza acentos antes de comparar).

### Screenshots automáticos
Em cada falha dentro do `@retry`, screenshot salvo em `screenshots/erro_{fase}_{n}.png`.

---

## Primitivas DOM — Referência Rápida

| Operação | Função | Notas |
|---|---|---|
| Preencher texto | `_preencher(field_id, valor)` | 4 níveis de seletor |
| Preencher data | `_preencher_data(field_id, "DD/MM/AAAA")` | press_sequentially obrigatório |
| Selecionar option | `_selecionar(field_id, valor)` | label → value |
| Marcar radio | `_marcar_radio(field_id, valor)` | fallback: `_marcar_radio_js()` |
| Marcar checkbox | `_marcar_checkbox(field_id, bool)` | |
| Clicar salvar | `_clicar_salvar()` | JS fallback automático |
| Clicar novo | `_clicar_novo()` | dentro do formulario atual |
| Navegar menu | `_clicar_menu_lateral(texto)` | JS invulnerável a visibilidade |
| Navegar por URL | `_page.goto(url_section_map[secao])` | requer conversationId atual |
| Aguardar AJAX | `_aguardar_ajax(timeout)` | RESET obrigatório após espera |
| Localizar elemento | `_localizar(field_id, label, tipo)` | hierarquia 4 níveis |
