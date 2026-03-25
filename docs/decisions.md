# Decisões Técnicas — Agente PJE-Calc

## 2026-03-23 — FASE 1: Estratégia de Desbloqueio do Lancador

**Contexto:** O Tomcat embarcado do PJE-Calc não sobe no Railway. O log Java para em
`[TRT8] Configurando variaveis basicas.`. Decompilação do `pjecalc.jar` com CFR revelou
três pontos de bloqueio distintos.

**Decisão:** Implementar Java Agent (Opção A do plano) usando Javassist para interceptar
chamadas de JOptionPane em runtime, sem modificar o JAR original.

**Motivo:** O JAR original não deve ser modificado (commitado como distribuição oficial do TRT8).
O Java Agent intercept é transparente, pode ser ativado/desativado via flag JVM, e não
requer recompilação ou acesso ao código-fonte original.

**Bloqueios identificados:**
1. `JOptionPane.showMessageDialog` em `validarPastaInstalador()` → se H2 não encontrado, seguido de `System.exit(1)`
2. `JOptionPane.showConfirmDialog` em `iniciarAplicacao()` → se porta 9257 já em uso, seguido de `System.exit(1)`
3. `Janela.setDefaultCloseOperation(EXIT_ON_CLOSE)` → xdotool pode fechar a janela matando o JVM

**Alternativa documentada:** Se o Agent falhar, iniciar Tomcat diretamente via
`org.apache.catalina.startup.Bootstrap` com os system properties mapeados na FASE 1.

---

## 2026-03-23 — FASE 2: Implementação do Java Agent

**Decisão:** DialogSuppressorAgent transforma 4 métodos de JOptionPane via Javassist:
- `showMessageDialog` → `return` void (suprime completamente)
- `showConfirmDialog` → `return 0` (YES_OPTION, para continuar execução)
- `showOptionDialog` → `return 0` (primeira opção)
- `showInputDialog` → `return null` (sem input)

E transforma `JFrame.setDefaultCloseOperation` para converter `EXIT_ON_CLOSE (3)` → `DISPOSE_ON_CLOSE (2)`.

**Estratégia de System.exit:** Ao suprimir `showMessageDialog` e retornar imediatamente,
o `System.exit(1)` subsequente ainda executa. Para evitar isso, transformamos
`Lancador.validarPastaInstalador()` para remover o `System.exit(1)` — ou instalamos
um SecurityManager que bloqueia `System.exit(1)`.

**Decisão final:** Usar SecurityManager custom (`NoExitSecurityManager`) que lança uma
exceção runtime ao invés de matar o JVM. Isso permite que o fluxo continue mesmo
quando o dialog é suprimido. O SecurityManager é instalado ANTES do Lancador.main() rodar
(no premain do Agent).

**Risco aceitável:** SecurityManager pode bloquear operações legítimas. Monitorar via
`GET /api/logs/java` após deploy.

---

## 2026-03-24 — FASE 3: Correções Playwright por Playwright JSF Automator Skill

**Contexto:** Automação chegava na fase de verbas mas não detectava os campos do formulário.
Log mostrava `_form_abriu = False` mesmo após clicar em "Novo".

**Causa raiz identificada:** `no_viewport=True` em modo headless → elementos JSF reportam
`offsetParent === null` e `getBoundingClientRect() = {width:0, height:0}` → filtro de
visibilidade `e.offsetParent !== null` excluía TODOS os elementos → form nunca detectado.

**Decisões:**

1. Viewport explícito `{"width": 1920, "height": 1080}` substitui `no_viewport=True`
   — garante layout correto e `getBoundingClientRect()` funcional em headless.
2. Substituir `offsetParent !== null` por `getBoundingClientRect().width > 0 && height > 0`
   em todos os lugares JS (mapear_campos, fase_verbas) — confiável em headless e headed.
3. Adicionar `--no-sandbox --disable-dev-shm-usage` aos args do Chromium — obrigatórios
   em Docker (Railway usa container sem privilégios SUID sandbox).
4. Adicionar interceptores de rede (response ≥400 e console errors) para diagnóstico
   automático em produção via SSE log.

**Referência:** Playwright JSF Automator Skill §1 (setup), §2 (seleção robusta),
§3 (mapeamento automático), troubleshooting "Timeout: waiting for selector".

---

## 2026-03-25 — Correção Geral: Automação Sem Intervenção Manual

### D1 — Bootstrap bypass do Lancador Java (`iniciarPjeCalc.sh`)

**Decisão:** substituir `java -jar pjecalc.jar` por inicialização direta via
`org.apache.catalina.startup.Bootstrap -config tomcat/conf/server.xml start`,
adicionando todos os JARs de `bin/lib/` ao classpath.

**Motivo:** o `Lancador.java` exibe `JOptionPane` ao detectar banco H2 ausente
ou porta em uso. Esse diálogo bloqueia o thread no Railway/Docker mesmo com
Java Agent (race condition). Com Bootstrap direto + `-Djava.awt.headless=true`,
o processo Java nunca tenta criar janelas GUI, eliminando a classe inteira de falhas.

**Fallback:** se `tomcat/conf/server.xml` não existir, recai para `java -jar pjecalc.jar`
com Xvfb + xdotool + Java Agent (comportamento anterior).

---

### D2 — Remoção de `_aguardar_usuario` durante automação (`playwright_pjecalc.py`)

**Decisão:** dois pontos de bloqueio manual foram eliminados:

1. `_verificar_e_fazer_login`: agora lança `RuntimeError` se login automático falhar.
   Credenciais configuráveis via env vars `PJECALC_USER`/`PJECALC_PASS`.
2. `fase_verbas` (verbas não reconhecidas): substituído por log de aviso. Verbas não
   mapeadas devem ser resolvidas na PRÉVIA antes de confirmar.

**Motivo:** padrão Calc Machine — nenhuma intervenção manual durante automação.

---

### D3 — `_clicar_liquidar`: 6 estratégias antes de desistir (`playwright_pjecalc.py`)

**Decisão:** expandir para 6 estratégias incluindo navegação ao menu "Operações"
e varredura de links de download no DOM.

**Motivo:** Liquidar pode não estar visível sem navegar para Operações primeiro.
Se todas as estratégias falharem, o .PJC do gerador nativo (`pjc_generator.py`)
— gerado na confirmação — fica disponível. Nunca aguarda input humano.

---

### D4 — Validação HITL obrigatória em `confirmar_previa` (`webapp.py`)

**Decisão:** bloquear confirmação com HTTP 422 se: admissão/demissão/tipo_rescisão
ausentes, zero verbas, ou verbas com `confidence < 0.7` não corrigidas.

**Motivo:** o robô precisa de dados completos. Validação preventiva na prévia elimina
falhas de preenchimento no meio da automação.

---

### D6 — Prévia com campos por parte (honorários, INSS, IR, custas)

**Decisão:** quando a extração retorna `parte_devedora = "Ambos"` para honorários
ou `responsabilidade = "Ambos"` para INSS, a prévia HTML exibe seções expandidas
separadas por parte (Reclamante / Reclamado):

- **Honorários Ambos**: `toggleHonorarios()` esconde os campos únicos e exibe
  `honorarios.percentual_reclamado` (% s/ condenação) e
  `honorarios.percentual_reclamante` (% s/ pedidos indeferidos) — editáveis independentemente.
- **INSS Ambos**: painel informativo (não editável) com cota-parte de cada parte.
  Valores calculados automaticamente pelo PJE-Calc.
- **IR**: painel informativo sempre visível quando `apurar=true` — distingue
  reclamante (contribuinte) de reclamado (fonte pagadora).
- **Custas**: seção informativa nova em `preview.py` inferida da sucumbência.

**Motivo:** "Ambos" como campo único era ambíguo — o usuário não conseguia verificar
nem corrigir os parâmetros de cada parte antes de confirmar. Skill `calctrabalho-correcoes`
reforçou que cada devedor precisa ter campo próprio editável.

**Impacto na extração:** `honorarios.percentual_reclamado` e
`honorarios.percentual_reclamante` são campos novos — o LLM não os extrai ainda.
O usuário os preenche manualmente na prévia quando aplicável (sucumbência recíproca).
Para extração automática, ver TODO em `extraction.py`.

---

### D5 — Hospedagem e acionamento do PJE-Calc Cidadão

**Decisão:** manter PJE-Calc como serviço persistente no container Docker/Railway,
iniciado uma vez no `docker-entrypoint.sh`, acessado via `http://localhost:9257/pjecalc`.

**Motivo:** esse é exatamente o modelo do Calc Machine. O Playwright conecta ao Tomcat
local já em execução — não inicia/para o PJE-Calc por sessão. Bootstrap direto (D1)
torna esse startup muito mais confiável que `java -jar` + xdotool.

---

## 2026-03-25 — Paralelismo Total Prévia ↔ PJE-Calc Cidadão

### D7 — Honorários: schema dict → list de registros

**Decisão:** substituir `honorarios: {percentual, parte_devedora}` por
`honorarios: [{tipo, devedor, tipo_valor, base_apuracao, percentual, valor_informado, apurar_ir}]`.

**Motivo:** o PJE-Calc Cidadão (`honorarios.xhtml`) não tem campo "Ambos" — cada
honorário é um registro separado com `tipoDeDevedor=RECLAMANTE|RECLAMADO`. O campo
`baseParaApuracao` tem enums distintos por devedor+tipo (ex: RECLAMANTE+SUCUMBENCIAIS
aceita "Verbas Não Compõem Principal"; RECLAMADO não). O schema antigo tornava a prévia
e a automação incompatíveis com a UI real.

**Retrocompatibilidade:** `_migrar_honorarios_legado()` converte dicts antigos
(inclusive `parte_devedora="Ambos"`) em dois registros separados. Aplicada em
`_merge_extracao()`, `_validar_e_completar()` e `fase_honorarios()`.

**Impacto na automação:** `fase_honorarios` agora itera sobre a lista, clicando "Novo"
para cada registro adicional; usa `_extrair_opcoes_select("baseParaApuracao")` +
`_match_fuzzy()` para descobrir o enum real em runtime.

---

### D8 — INSS: responsabilidade dropdown → checkboxes individuais

**Decisão:** substituir `contribuicao_social.responsabilidade: "Ambos|Empregador|Empregado"`
por quatro booleans: `apurar_segurado_salarios_devidos`, `cobrar_do_reclamante`,
`com_correcao_trabalhista`, `apurar_sobre_salarios_pagos`.

**Motivo:** a aba "Contribuição Previdenciária" do PJE-Calc usa checkboxes individuais,
não um dropdown. O dropdown `responsabilidade` era abstração sem correspondência direta
na UI. Os checkboxes booleanos permitem prévia e automação idênticas ao formulário real.

**Retrocompatibilidade:** `_migrar_inss_legado()` converte o campo `responsabilidade`
para o conjunto de booleans equivalente. Padrão: todos `true` exceto `apurar_sobre_salarios_pagos`.

---

### D9 — IRPF: implementação completa de `fase_irpf`

**Decisão:** expandir o schema `imposto_renda` com os campos reais do PJE-Calc
(`tributacao_exclusiva`, `regime_de_caixa`, `tributacao_em_separado`, `deducao_inss`,
`deducao_honorarios_reclamante`, `deducao_pensao_alimenticia`, `valor_pensao`) e
implementar `fase_irpf` em `playwright_pjecalc.py` (era stub).

**Motivo:** o stub `"IRPF — ignorado"` significava que o IR nunca era preenchido,
produzindo cálculos incorretos para processos com verbas tributáveis. A prévia HTML
agora espelha exatamente os campos de `irpf.xhtml`.

---

### D10 — Verbas: preenchimento de `baseCalculo` via fuzzy match

**Decisão:** em `fase_verbas`, após preencher incidências, chamar
`_extrair_opcoes_select("baseCalculo")` + `_match_fuzzy(v["base_calculo"], opcoes)`
para selecionar a base de cálculo extraída da sentença no select real do PJE-Calc.

**Motivo:** o campo `base_calculo` era extraído pela IA (ex: "Historico Salarial",
"Maior Remuneracao") mas nunca preenchido na automação. O fuzzy match normaliza
strings (lower + sem acento) para tolerar variações de nomenclatura entre extração e
enums da UI.

**Mecanismo:** `_extrair_opcoes_select(field_suffix)` faz `document.querySelectorAll`
via JS em runtime; `_match_fuzzy` tenta match exato de label, depois de value, depois
substring. Log de aviso quando sem match.

---

## 2026-03-25 — Otimização de Extração + Camada de Parametrização

### D11 — Extração: PDF nativo via base64 (sem conversão para texto)

**Decisão:** Adicionar `extrair_dados_sentenca_pdf(pdf_path)` em `extraction.py` que envia
o PDF diretamente ao Claude como `document` base64, com `cache_control: ephemeral`.
`webapp.py` usa esta função para PDFs não-relatório; o caminho de texto
(`ler_documento` + `extrair_dados_sentenca`) permanece como fallback e para DOCX/TXT.

**Motivo:** Conversão prévia de PDF para texto perdia tabelas e formatação; a chamada
extra de `ler_documento` adicionava latência desnecessária. O PDF nativo é mais preciso
e elimina a pré-etapa de texto.

---

### D12 — Extração: Structured Outputs + ValidadorSentenca

**Decisão:** Adicionar `output_config` com JSON schema nas chamadas Claude em
`_extrair_via_llm()` e `_extrair_via_llm_pdf()`. Fallback transparente se o SDK
não suportar (SDK < 0.45). `_EXTRACTION_SCHEMA` define o schema correspondente.
Extrair `ValidadorSentenca` (antes inline em `_validar_e_completar`) em classe própria.

**Motivo:** Parse tolerante a JSON (6 estratégias de fallback) era fonte de lentidão
e falhas silenciosas. Structured Outputs garante JSON válido diretamente da API.
`ValidadorSentenca` reutilizável em múltiplos pontos do pipeline.

---

### D13 — Extração: timeout Gemini via ThreadPoolExecutor

**Decisão:** `_extrair_via_gemini()` agora usa `concurrent.futures.ThreadPoolExecutor`
com `fut.result(timeout=30)`. Timeout levanta `TimeoutError`, que aciona fallback para
Claude sem esperar o timeout HTTP do SDK.

**Motivo:** Se `GEMINI_API_KEY` estiver configurada no Railway mas o serviço Gemini
estiver indisponível, a chamada bloqueava o pipeline inteiro. Com 30s de timeout,
o fallback para Claude ocorre rapidamente.

---

### D14 — Parametrização: novo módulo `modules/parametrizacao.py`

**Decisão:** Criar `gerar_parametrizacao(dados: dict) -> dict` como camada intermediária
entre `extraction.py` e `playwright_pjecalc.py`. Implementa o "cérebro" da skill
`pjecalc-parametrizacao`: decide Lançamento Expresso/Manual por verba, calcula
`data_inicial_apuracao` da prescrição quinquenal, configura ADC 58 (IPCA-E + SELIC),
detecta Fazenda Pública e aplica EC 113/2021, gera alertas HITL.

**Motivo:** Lacuna arquitetural — a automação Playwright decidia on-the-fly
Expresso/Manual e índices de correção sem base estruturada, causando erros silenciosos.

**Persistência:** `dados["_parametrizacao"]` é salvo em `dados_json` pelo `criar_calculo`.
Recuperado em `executar_automacao_sse` via `dados.get("_parametrizacao")` e passado
para `preencher_calculo(parametrizacao=...)`.

---

### D15 — Playwright: `_ir_para_novo_calculo`, `fase_parametros_gerais`, screenshots

**Decisão:**

- Renomear `_ir_para_calculo_externo` → `_ir_para_novo_calculo` (nome enganoso — a
  função sempre navegou para "Novo", não "Cálculo Externo").
- Adicionar `fase_parametros_gerais(parametros)` entre `fase_dados_processo` e
  `fase_historico_salarial` — preenche `dataInicialApuracao`, `cargaHorariaDiaria/Semanal`,
  `zerarValoresNegativos` a partir de `passo_2_parametros_gerais` do parametrizacao.json.
- Adicionar `_screenshot_fase(nome)` — captura screenshot não-crítico após cada fase
  em `SCREENSHOTS_DIR/{timestamp}_{nome}.png`.
- `preencher_calculo` e `iniciar_e_preencher` aceitam `parametrizacao: dict | None`.

**Motivo:** Nome enganoso causava confusão ao revisar código. `fase_parametros_gerais`
preenche campos que `fase_dados_processo` não cobre. Screenshots facilitam debugging
de automações que falham silenciosamente em ambientes headless.
