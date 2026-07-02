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

## Regra obrigatória — Divisor CLT para 13º e Férias + 1/3

> **Para 13º SALÁRIO e FÉRIAS + 1/3, o divisor é SEMPRE 12** (constante legal —
> CLT art. 130 / Constituição art. 7º XVII — 12 avos por ano/período aquisitivo).
>
> **Bug histórico (26/05/2026, descoberto via re-importação PJC Scarlette):**
> O exemplo no prompt do Projeto Claude externo (`docs/prompt-projeto-claude-externo.md`
> linha 534) ensinava `divisor.valor=1` para o 13º. IA replicava. PJE-Calc
> multiplicava o cálculo por 12 → erro grave de valor.
>
> ⚠️ **FIDELIDADE PRÉVIA↔AUTOMAÇÃO**: per regra arquitetural fundamental no
> topo deste CLAUDE.md, a prévia deve mostrar EXATAMENTE o que a automação
> aplica. Correções de valor NUNCA podem estar no bot — devem ocorrer no
> normalizer (ANTES da prévia) para que o usuário veja o valor correto ao
> revisar.
>
> **Defesas implementadas (3 CAMADAS, ordem prioridade):**
>
> 1. **Prompt externo (`docs/prompt-projeto-claude-externo.md`)** — primária:
>    exemplos corrigidos para `divisor=12` + bloco "DIVISOR CLT — INVARIANTE
>    PERMANENTE — NÃO REVERTER". IA não gera mais divisor=1.
>
> 2. **Normalizer (`modules/json_normalizer.py`, `normalize_v2_json`)** —
>    salvaguarda: se IA escapar a regra do prompt e gerar divisor != 12 para
>    13º/Férias, normalizer CORRIGE para 12 ANTES da prévia. Usuário vê o
>    valor correto. Bot apenas aplica o JSON validado.
>
> 3. **Prompt interno (`modules/extraction_v2.py`)** — fallback caso extração
>    interna seja usada em vez do projeto Claude externo.
>
> ⚠️ **NÃO mover correção para o bot** — viola fidelidade prévia↔automação.
> Bot APENAS aplica o JSON que passou pela prévia.
>
> Validado em `tests/test_invariantes_indenizacao.py::test_inv9_divisor_clt_no_normalizer`.

---

## Regra obrigatória — Histórico Salarial = SM ⇒ 1 entrada CALCULADO/SALARIO_MINIMO

> **Quando o salário é o mínimo vigente (ou múltiplo fixo dele: 1 SM, 2 SM, 1.5 SM…),
> emita UMA ÚNICA entrada em `historico_salarial`** com:
> ```json
> {
>   "nome": "SALARIO MINIMO",
>   "tipo_valor": "CALCULADO",
>   "calculado": {"quantidade_pct": 1.0, "base_referencia": "SALARIO_MINIMO"},
>   "competencia_inicial": "<início do contrato>",
>   "competencia_final": "<fim do contrato>"
> }
> ```
> PJE-Calc tem a **tabela oficial do SM por competência** (desde 01/1967) e aplica
> o valor certo de cada mês automaticamente — gera ocorrências mensais com o valor
> correto sem precisar segmentar.
>
> ⚠️ `quantidade_pct` é **MULTIPLICADOR**, NÃO percentual 0–100:
> - `1.0` = 100% = 1× SM (caso típico)
> - `1.10` = 110% = 1.10× SM
> - `0.50` = 50% = ½× SM
> - **NUNCA emitir `100.0`** — PJE-Calc interpretaria como **100 salários mínimos**
>   (R$ 141.200+).
>
> **Bug histórico (Mikaely 28/05/2026):** IA gerava `SALARIO MINIMO 2024 R$ 1.412` +
> `SALARIO MINIMO 2025 R$ 1.518` como duas entradas INFORMADO separadas, poluindo
> a listagem do histórico salarial no PJE-Calc. Validação end-to-end pós-fix:
> PJC v3 (`PROCESSO_00018490720255070003_..._141817.pjc`, 58 KB) tem **13 ocorrências
> mensais geradas a partir de 1 histórico só**, com valor evoluindo de R$ 1.412
> (08-12/2024) para R$ 1.518 (01-08/2025) automaticamente pela tabela oficial.
>
> ⚠️ **FIDELIDADE PRÉVIA↔AUTOMAÇÃO**: prévia mostra exatamente 1 entrada
> CALCULADO/SALARIO_MINIMO; bot apenas aplica.
>
> **Defesas implementadas (3 CAMADAS, ordem prioridade):**
>
> 1. **Prompt externo (`docs/prompt-projeto-claude-externo.md`)** — primária:
>    bloco "REGRA INVARIANTE — NÃO REVERTER — salário mínimo = 1 entrada CALCULADO"
>    + exemplo corrigido para `quantidade_pct: 1.0` com explicação "MULTIPLICADOR,
>    NÃO percentual 0–100". Anti-segmentação explícita ("NUNCA segmente em SM
>    2023, SM 2024…").
>
> 2. **Normalizer (`modules/json_normalizer.py`, `normalize_v2_json`)** —
>    salvaguarda 2 camadas:
>    - (a) Detecta N≥2 entradas INFORMADO com `valor_brl` ∈ tabela SM oficial
>      (1320 em 2023, 1412 em 2024, 1518 em 2025, 1622 em 2026, etc.) em
>      competências contíguas → consolida em 1 entrada CALCULADO/SALARIO_MINIMO
>      `quantidade_pct=1.0`.
>    - (b) Coerce `quantidade_pct ≥ 10` com `base_referencia ∈ {SALARIO_MINIMO,
>      SALARIO_DA_CATEGORIA}` para multiplicador correto (100.0 → 1.0;
>      150.0 → 1.5; 200.0 → 2.0).
>
> 3. **Prompt interno (`modules/extraction_v2.py`)** — fallback caso extração
>    interna seja usada em vez do projeto Claude externo. Mesmas regras.
>
> 4. **Bot (`modules/playwright_v2.py`, `fase_historico_salarial`)** — espera
>    AJAX após click `radio tipoValor=CALCULADO` (re-render condicional do form
>    que mostra `quantidade` + `baseDeReferencia`). Sem essa espera, bot pulava
>    os campos com "campo não existe — pulando" e o histórico saía sem
>    quantidade/base — PJE-Calc usava default ÚLTIMA REMUNERAÇÃO (corrompendo
>    o cálculo). Fix: `_aguardar_ajax(5000) + wait_for_timeout(800)` após radio,
>    + `wait_for_selector visible 8000ms` no input quantidade.
>
> ⚠️ **NÃO mover correção para o bot** (camadas 1-3) — viola fidelidade
> prévia↔automação. Bot APENAS aplica o JSON que passou pela prévia.
>
> Validado em `tests/test_invariantes_indenizacao.py::test_inv13_*` (4 testes:
> consolidação Mikaely, coerção 100→1, preservação de entradas mistas,
> presença do invariante no prompt) e `tests/test_prompt_invariants.py::test_historico_salario_minimo_calculado_consolidado`.

---

## Regra obrigatória — `_preencher` respeita `maxlength` (#80-O) — NÃO REVERTER

> **`_preencher` seta inputs via JS `el.value=...` (necessário p/ o bean JSF a4j
> receber), o que BYPASSA o `maxlength` que o browser imporia ao digitar.** Por
> isso `_preencher` LÊ o `maxlength` do campo e TRUNCA o valor antes de setar.
>
> **Bug (0000712-53):** o campo `descricao` (Nome da verba) tem `maxlength=50` +
> `required`. Verbas `expresso_adaptado` com nome >50 ("INDENIZAÇÃO — INTERVALO
> INTRAJORNADA (45 MIN/PLANTÃO + 50%)"=59) eram setadas inteiras → o servidor
> REJEITAVA o SAVE por validação de tamanho, **SILENCIOSAMENTE** (o `rich:message`
> do campo não entra no re-render a4j) → form sem sucesso E sem erro → o bot
> Cancelava → base histórico + parâmetros DESCARTADOS → liquidação bloqueada
> ("Falta selecionar Histórico Salarial" / "ocorrência com valor zero"). Explica
> por que verbas Expresso (nomes canônicos ≤50) salvam e adaptadas (>50) falham.
>
> ⚠️ **Diagnóstico de save bloqueado silenciosamente:** após salvar, página SEM
> "Operação realizada com sucesso" E SEM erro, permanecendo no form → suspeitar
> de validação silenciosa em campo fora do re-render (maxlength, required oculto).
>
> Validado (0000712-53, run4): descricao truncado a 50 → "✓ Parâmetros salvos"
> → totalErros=0 → PJC. Protegido por `test_inv62`. Relacionado: #80-M (base
> histórico da verba via click nativo + verificação da tabela, `test_inv61`).

## Regra obrigatória — Evolução salarial = OCORRÊNCIAS de 1 histórico, não N históricos (#80-L)

> **Quando um histórico salarial INFORMADO tem evolução de valores ao longo do
> tempo (`HistoricoSalarial.evolucao`), registrar UM ÚNICO histórico cobrindo o
> período todo e aplicar a evolução nas OCORRÊNCIAS MENSAIS — NUNCA criar N
> históricos separados (um por faixa/mês).**
>
> **Bug recorrente (0000712-53, 27/06/2026):** `_expandir_evolucao_historico`
> explodia a evolução em N históricos ("REMUNERACAO MENSAL" com 31 steps → 31
> históricos; "PISO SALARIAL" → 4). Poluía a listagem. A prévia estava correta
> (1 entrada por nome com `.evolucao`).
>
> **Modelo PJE-Calc** (`historico-salarial.xhtml`): 1 histórico = Competência
> Inicial/Final + valor base + botão "Gerar Ocorrências" (`cmdGerarOcorrencias`)
> + tabela `listagemMC` com coluna `valor` editável por mês
> (`formulario:listagemMC:N:valor`; mês em `...:N:data`).
>
> **Fix:** `fase_historico_salarial` itera a prévia DIRETO (sem expandir); após
> "Gerar Ocorrências", `_aplicar_evolucao_ocorrencias_historico` seta o valor de
> cada mês conforme o step vigente (cada step vale até a competência do próximo).
> Os valores são setados via JS sem disparar change (evita tempestade A4J em
> históricos longos); o Save full-form persiste todos. NÃO reverter para a
> expansão em N históricos.
>
> Validado (0000712-53, H2): REMUNERACAO MENSAL=1, PISO=1 (não 35); ocorrências
> com valores evoluindo (PISO 1.727,26 em 2024, 1.827,96 em 01/2025). Protegido
> por `test_inv15` (reescrito) + `test_inv47`.

---

## Regras obrigatórias — 5 fixes do caso THAÍS (0000183-68, 10/06/2026) — NÃO REVERTER

> Auditoria sentença→JSON→prévia→PJC do cálculo THAÍS revelou 5 bugs sistêmicos.
> Cada fix tem teste de invariante em `tests/test_invariantes_indenizacao.py`.

### 1. Alias `valor_mensal` → `valor` em quantidade INFORMADA (inv18)

O prompt ensinava `quantidade: {tipo: INFORMADA, valor_mensal: N}`; o schema
(`QuantidadeVerba`) só lia `valor` (default 1.0) → **quantidade N≠1 era perdida
silenciosamente** (SALDO DE SALÁRIO 20 dias virou 1 → R$ 53,83 em vez de
R$ 1.614,79). Defesas: (a) validator `_alias_valor_mensal` em
`docs/schema-v2/99-pydantic-models.py` aceita ambos; (b) exemplos do prompt
migrados para `valor` canônico.

### 2. Template prévia DEVE usar campos canônicos de juros (inv19)

`templates/previa_v2.html` gravava juros em aliases que o bot NÃO lê
(`juros_mora`, `aplicar_juros_pre_judicial`, `segundo_indice`,
`combinar_a_partir_de`, values errados de `base_juros_verbas`) → **edições do
usuário na prévia eram ignoradas pela automação** (violação da regra
arquitetural de fidelidade prévia↔automação). Campos renomeados para os
canônicos do schema; combinação de juros sincronizada com
`juros_combinacoes[]` via `sincronizarJurosCombinacoes()`.

### 3. Juros modelo TST: fase 1 = TRD_SIMPLES, TAXA_LEGAL via combinação (inv20)

**Supersede o commit `587f862`.** Para ajuizamento >= 30/08/2024, a regra
anterior emitia `juros=TAXA_LEGAL` sem combinações → taxa legal aplicada desde
o VENCIMENTO (fase pré-judicial), majorando juros. Modelo correto (sentença
THAÍS transcreve TST E-ED-RR-20407): fase 1 (pré-judicial) = `TRD_SIMPLES`
(art. 39 caput Lei 8.177/91, ≈0) + combinação `TAXA_LEGAL@<data_ajuizamento>`
(+ `SELIC@ajuizamento` antes, se ajuizamento pré-corte). A combinação NÃO é
redundante com TRD na fase 1 — PJE-Calc não a converte para SEM_JUROS
(motivo do 587f862; comprovado no PJC THAÍS). Defesas: prompt + normalizer
(`_norm_correcao_caso_a_vs_b`) + `_JUROS_MAP` com TRD_SIMPLES/TRD_COMPOSTOS/
SEM_JUROS + Literals do schema ampliados.

### 4. Fração DEFERIDA limita o período da verba (inv21)

"Verba única" ≠ "período do contrato inteiro". Sentença THAÍS deferiu APENAS
2/12 de 13º/2025 (R$ 403,70); IA emitiu período do contrato → PJE-Calc liquidou
7/12+12/12+2/12 = R$ 4.238,83 (**R$ 3.835 a maior que o título executivo**).
Período da verba = MENOR período que gera exatamente os avos deferidos.
Invariante no prompt (`FRAÇÃO DEFERIDA`).

### 5. Regerar Sobrescrever CONDICIONAL p/ período curto + log persistido

SALÁRIO RETIDO (Expresso, CALCULADO+MENSAL, período 1 mês em contrato de 20
meses): ocorrências do contrato inteiro ficavam fora do período após o ajuste
("descompasso"); Regerar Manter não as remove. Fix: no Regerar pós-parâmetros,
`sobrescrever=True` SOMENTE quando `_verba_periodo_curto(v)` (subconjunto
estrito do cálculo) E `_ocorrencias_editadas=False` (Regerar é global —
apagaria valorDevido de INFORMADO já editado), com re-anchor da listagem
pós-Sobrescrever (salvaguarda contra regressão `312839e` "listagem vazia
mid-loop"). Log SSE agora persiste em `<store>/logs/<sessao>_automation.log`
(`modules/webapp_v2.py`) — sem ele este diagnóstico foi inferencial.

---

## Regras obrigatórias — 4 fixes do caso RODRIGO (0000447-51, 11/06/2026) — NÃO REVERTER

> Primeiro cálculo com log SSE persistido (`<store>/logs/<sessao>_automation.log`)
> — diagnóstico direto, não inferencial. Testes inv22–25.

### 1. Bot NÃO sintetiza comentário de JG (inv22)

Fallback "JG auto-detectado" assumia que o DEVEDOR dos sucumbenciais era o
beneficiário da JG sem consultar `justica_gratuita` → inventou "parte
reclamado — beneficiária da JG" quando o deferimento era só do autor. Bot
agora aplica APENAS `pc.comentarios_jg` da prévia; a síntese (interseção
JG ∩ devedor) é exclusiva do normalizer (`_norm_comentarios_jg`), ANTES da
prévia. `comentarios_jg=None` na prévia = "não anotar nada".

### 2. Combinações da Fase 13 verificadas contra a listagem renderizada (inv23)

Log mostrava "✓ click addOutroJuros/addOutroIndice" mas o bean JSF recebia o
DEFAULT do select — combinação de juros persistida como `SEM_JUROS@ajuizamento`
e combinação de índice nem criada (`combinarOutroIndice=false` no PJC). Causa
provável: re-render A4J do `rich:calendar` resetava o select antes do add.
Fix: helper `_add_combinacao_verificada` — data PRIMEIRO, select por ÚLTIMO,
add, e **verificação da `rich:dataTable` re-renderizada** (`listagemJurosCombinados`
/ `listagemIndicesCombinados` — ground truth do bean) com retry ×3 + remoção
de linhas "Sem Juros"/erradas da mesma data (preserva fases legítimas).
O "✓" do log agora significa CONFIRMADO no bean.

### 3. `_BASE_JUROS_MAP` com enum real (inv24)

Map anterior gerava values inexistentes ("VERBA", "VERBA_MENOS_CS") → timeout
30s. Enum real extraído de `BaseDeJurosDasVerbasEnum` (JAR pjecalc-negocio):
`VERBAS | VERBA_INSS | VERBA_INSS_PP` (= schema v2, identidade).

### 4c. Honorário do RECLAMANTE = SEMPRE "Cobrar do reclamante" (#80-K, 27/06/2026)

Honorário sucumbencial devido **pelo reclamante** (sucumbência recíproca) deve
ser SEMPRE `TipoCobrancaReclamanteEnum.COBRAR` ("Cobrar do reclamante"), NUNCA
`DESCONTAR_CREDITO` ("Descontar dos créditos"). Bug recorrente: o bot deixava o
DEFAULT do bean (DESCONTAR_CREDITO). O radio `formulario:tipoCobrancaReclamante`
(honorarios.xhtml:118) só renderiza após o onchange A4J de `tipoDeDevedor`
(painel `pnlParametrosReclamante` rendered=#{...eq 'RECLAMANTE'}); marcar cedo/sem
verificar deixava o default. Fix: `wait_for_selector` + marcar COBRAR por value
('COBRAR'/'C') OU label ('Cobrar do reclamante') via JS + VERIFICAR + retry ×3.
`<s:selectItems>` desses enums usa o NOME da constante como value (confirmado:
tipoValor='CALCULADO', tipoDeDevedor='RECLAMANTE'). Validado run_P GEOVANA: PJC
`devedor=RECLAMANTE cobranca=COBRAR`. Protegido por `test_inv60`. NÃO reverter.

### 4b. Reflexos 467 — persistência e ordem (ciclo v4–v16, 12/06/2026)

Invariantes consolidados em 13 runs end-to-end (cada um reverte um modo de
falha observado em PJC real):

1. **Reflexos são marcados DENTRO de `_configurar_parametros_pos_expresso`**,
   após o anchor `wait_for(linkParametrizar > 0)` e ANTES do save. Fora desse
   anchor a listagem vem VAZIA pós-reabertura Seam mesmo com re-navegação ×3
   (v7/v8); sem save posterior o checkbox morre no Fechar+Reabrir — o
   checkbox vive na conversa Seam (FlushMode.MANUAL) e só o save de
   parâmetros flusha (v4/v5; Regerar NÃO flusha).
2. **Checkbox com verificação**: Playwright `.check()` + re-leitura pós-AJAX
   + retry ×3 com reabertura do painel Exibir ("✓ CONFIRMADO" = no bean).
3. **NÃO fazer ajustes de reflexo no meio do loop de verbas** — corrompe o
   estado Seam das verbas seguintes (v12). Ajustes finos (período/base do
   13º multi-ano) ficam em sub-fase própria APÓS o loop.
4. **Validação de PJC**: ocorrências do reflexo são SOMENTE as do elemento
   filho direto `ocorrencias` — `iter()` desce no XStream aninhado e captura
   as ocorrências da verba PRINCIPAL referenciada (falso-positivo de
   "ocorrência espúria" que custou 2 iterações).

**Resultado final (run v21, 12/06/2026)**: 4/4 reflexos ativos com TODOS os
valores exatos — SALDO 759,00 / AVISO 834,90 / FÉRIAS 1.602,34 / 13º
multi-ano 1.201,75 (2 ocorrências anuais: 695,75 + 506,00); total multa 467
= 4.397,99; juros/correção 100% (TRD_SIMPLES + TAXA_LEGAL, IPCAE + IPCA,
base VERBAS); liquidação 0 erros.

**Reflexo sobre 13º MULTI-ANO — RESOLVIDO (v17–v20, 12/06/2026, inv26)**:
o reflexo criado pelo Expresso vem com característica COMUM + ocorrência
DESLIGAMENTO → a base da ocorrência única soma só o avo do ano da rescisão
(RODRIGO: 506,00 em vez de 1.201,75). Cadeia de descobertas:

1. **Edição via grade é INVIÁVEL** (dump v17, fase `soma_zero`): em verba
   CALCULADO os inputs `valorDevido` da grade ficam VAZIOS (coluna renderiza
   o texto "Calculado") — não há números para somar.
   `_corrigir_valor_reflexo_na_grade` mantida apenas como referência para
   verbas INFORMADO; NÃO chamá-la para CALCULADO.
2. **Fix correto**: espelhar característica + ocorrência de pagamento da
   PRINCIPAL no form do reflexo (`_ajustar_periodo_reflexo`) — o PJE-Calc
   passa a gerar 1 ocorrência do reflexo por ano com a base do avo daquele
   ano. SEM edição manual de valores (fidelidade prévia↔automação).
3. **⚠ SUBMIT ÚNICO obrigatório (v18/v19)**: clicar cada radio
   sequencialmente NÃO funciona — o a4j:support valida o form INTERMEDIÁRIO
   e o servidor REJEITA ("As verbas 13º SALÁRIO, utilizadas como base de
   cálculo, são incompatíveis com a característica/ocorrência de pagamento
   selecionados"), re-renderizando com o valor antigo. DECIMO_TERCEIRO +
   DEZEMBRO é inalcançável por cliques. Fix comprovado por diag direto no
   servidor: marcar AMBOS via JS `checked` SEM disparar onchange (nenhum
   A4J intermediário); o Salvar full-form valida a combinação final e
   persiste no bean (verificado por reabertura do form).
4. Períodos primeiro (o fill dos rich:calendar dispara A4J); radios JS por
   último (inertes); salvar; Regerar Manter.

Protegido em `tests/test_invariantes_indenizacao.py::test_inv26_*`.

### 4. MULTA 467 NUNCA é verba principal autônoma (inv25)

IA emitiu MULTA 467 como verba própria (`expresso_alvo=MULTA 477` + mult 0.5)
→ Expresso não cria 2ª verba do mesmo alvo, reflexos candidatos "MULTA 467
SOBRE X" ficaram todos `ativo=false` e a multa FALTOU na liquidação. Forma
correta: **reflexos checkbox_painel** `MULTA DO ARTIGO 467 DA CLT SOBRE <verba>`
nas verbas rescisórias estritas + `fgts.multa_artigo_467=true`. Defesas:
prompt (regra crítica §4.1) + normalizer (`_norm_multa_467_como_reflexo` —
remove a verba autônoma, injeta reflexos, exclui MULTA/INDENIZAÇÃO/DEDUÇÕES).

---

## Regra obrigatória — Regerar Ocorrências após cada alteração

> **TODA alteração de parâmetro ou ocorrência de qualquer verba DEVE ser
> seguida de "Regerar Ocorrências" para que o PJE-Calc recompute downstream.**
>
> Comportamento documentado pelo usuário (25/05/2026): "toda vez que houve
> alteracao em algum parametro ou ocorrencia de qualquer verba é preciso regerar".
>
> Implementação: helper `_regerar_com_modal_confirmacao(sobrescrever, ...)` em
> `modules/playwright_v2.py`. Chamado em 4 pontos:
>
> 1. **Após cada save de parâmetros** (em `_configurar_parametros_pos_expresso`,
>    pós `✓ Parâmetros 'XXX' salvos`) — `sobrescrever=False`
> 2. **PROATIVO antes de linkOcorrencias** de verba INFORMADO+DESLIGAMENTO
>    (em `_configurar_ocorrencias_informado_inline`) — `sobrescrever=True`
> 3. **Após cada save de ocorrências** (em `_configurar_ocorrencias_informado_inline`,
>    pós `✓ Ocorrências de 'XXX' salvas`) — `sobrescrever=False`
> 4. **Final de fase 4** (`_regerar_ocorrencias_verbas`) — `sobrescrever=False`
>
> O helper trata corretamente o `<rich:modalPanel>` "Confirmação" com botões
> Ok/Cancelar que o botão `regerarOcorrencias` abre — **NÃO usar `page.on("dialog")`**
> porque é um modal HTML, não dialog nativo do browser. Bug histórico
> documentado em commit `e9dd13f` (25/05/2026): bot anterior deixava o modal
> aberto, bloqueando navegação subsequente (`linkOcorrencias` falhava).
>
> **Sobrescrever vs Manter:**
> - `sobrescrever=True` → descarta ocorrências antigas. Usar em PROATIVO antes
>   de linkOcorrencias de INFORMADO+DESLIGAMENTO+período curto (ocorrências
>   default do Expresso ficam fora do range)
> - `sobrescrever=False` → preserva edições manuais nas ocorrências. Usar
>   após save de parâmetros (queremos atualizar apenas o que mudou) e após
>   save de ocorrências (preservar valorDevido recém-editado)

---

## Regra obrigatória — Preservar progresso conquistado

> **TODA correção, refatoração ou melhoria DEVE preservar os avanços já alcançados.**
>
> Antes de remover/alterar código (especialmente recoveries, fallbacks, F+R, retries,
> ou qualquer lógica "defensiva"), valide:
>
> 1. **Identifique o avanço que aquele código representa** — qual cenário ele resolve?
>    Há git blame, comentário INVARIANTE ou regra em CLAUDE.md citando-o?
> 2. **Verifique se o cenário foi realmente resolvido pela mudança nova** — não basta
>    "achar" que está coberto. Rode um teste do cenário específico.
> 3. **Quando remover algo que servia de safety net, adicione uma proteção equivalente**
>    (assertion, monitoring, fallback alternativo) — ou explicitamente documente o
>    risco aceito + cenário em que falha.
> 4. **Em commits que removem código, citar os avanços específicos preservados** —
>    "Removido X porque novo Y cobre o caso Z testado no commit ABC".
>
> Razão: por meses esta automação foi construída via cascata de fixes incrementais.
> Cada Opção (B/C/D/F/Recovery LEVE/Recovery wrong-page/etc.) resolve uma falha
> específica observada num teste real. Remover sem cuidado faz regredir para o estado
> documentado na história de bugs. **A regressão é o inimigo silencioso.**

## Invariantes do bot — NÃO REVERTER (descobertas 25/05/2026 via DOM forense)

> Esta seção lista 7 invariantes do bot v2 descobertos via DOM dump forense
> da sessão Scarlette INDENIZAÇÃO POR DANO MORAL. Cada invariante foi validado
> por teste real e existe para impedir bug-regressão concreto.
>
> **Validação automática:** `tests/test_invariantes_indenizacao.py` (grep-based)
> falha em CI se qualquer dos 7 invariantes for revertido. Rode antes de editar
> `modules/playwright_v2.py`:
>
> ```bash
> pytest tests/test_invariantes_indenizacao.py -v
> ```

### Invariante 1 — Modal `rich:modalPanel` "Confirmação" do Regerar

**Bug histórico (commit `e9dd13f`):** Bot anterior usava
`self._page.once("dialog", lambda d: d.accept())` para o Regerar Ocorrências.
Mas o JSF `<rich:modalPanel>` "Confirmação" (com botões Ok/Cancelar) é overlay
HTML — NÃO um dialog nativo do browser. Modal ficava aberta, bloqueando
qualquer navegação subsequente.

**Fix:** método `_regerar_com_modal_confirmacao(sobrescrever, ...)` em
`modules/playwright_v2.py`. Localiza botão "Ok" no DOM (`offsetParent !== null`),
clica via onclick-exec ou native.

**Marcador no código:** `INVARIANTE PERMANENTE — modal Confirmação Regerar` deve
permanecer em `_regerar_com_modal_confirmacao`.

### Invariante 2 — Matcher EXATO POR TD em linkOcorrencias

**Bug histórico (commit `36fe24e`):** Matcher anterior usava
`tr.textContent.includes("INDENIZAÇÃO")`. PJE-Calc tem `<tr>` outermost de
layout que envolve sidebar+main e contém TODO texto da página. Match retornava
esse TR + primeira `a.linkOcorrencias` dentro = row 0 (13º SALÁRIO).

**Fix:** iterar `linksMain = [...a.linkOcorrencias].filter(a => !id.includes(':listaReflexo:'))`.
Para cada link, ler tds da MESMA linha (`a.closest('tr').querySelectorAll('td')`).
Match só se `td.textContent.trim() === alvo` (igualdade exata).

**Marcador no código:** comentário `# Bug histórico (...)` no início do helper.

### Invariante 3 — Native Playwright click em linkOcorrencias (não onclick-exec)

**Bug histórico (commit `1908b8d`):** Per CLAUDE.md já documentado para
linkParametrizar — `new Function(onclickStr).call(a, ev)` não dispara A4J.AJAX
de forma confiável em headless Firefox + JSF 1.2. Native `locator.click(force=True)`
dispara evento real do browser com event.target correto.

**Fix:** localizar id via JS (rapidez), clicar via `self._page.locator(f"a#{esc}").click(force=True)`.

### Invariante 4 — Regerar após CADA save (parâmetro OU ocorrência)

**Regra do usuário (25/05/2026, commit `cdd6c00`):** "toda vez que houve
alteracao em algum parametro ou ocorrencia de qualquer verba é preciso regerar".

**Fix:** chamadas em 4 pontos com `sobrescrever` apropriado — ver seção
"Regra obrigatória — Regerar Ocorrências após cada alteração" acima.

### Invariante 5 — Cascade A→B→C→D em linkOcorrencias

**Bug histórico (commit `2c9e60e`):** Strategy A (onclick-exec) sozinha NÃO
navegava para `parametrizar-ocorrencia.jsf` em PJE-Calc Cidadão H2 local.
Strategy B (native click) NAVEGOU pela primeira vez no DOM forense.

**Fix:** cascade defensivo com sucesso = `inputs valorDevido > 0`:
1. A onclick-exec
2. B native Playwright click(force=True)  ← funciona na maioria dos casos
3. C jsfcljs(form, {linkId}, '') — POST completo via helper PJE-Calc
4. D form.submit() com hidden input — bypass AJAX

Entre strategies, se URL ≠ verba-calculo.jsf, re-navega para listagem.
Se NENHUMA funciona, cai no recovery existente (Regerar+retry).

### Invariante 6 — Filtro DESLIGAMENTO desmarca ocorrências fora do período

**Bug histórico (commit `66228e6`):** PJE-Calc gera ocorrências MENSAIS para
o contrato inteiro (e.g. 9 rows apr-dec/2025), IGNORANDO o
ocorrencia_pagamento=DESLIGAMENTO do verba. Sobrescrever Regerar limpa
valorDevido mas mantém a estrutura de 9 rows.

**Fix (portado de `modules/playwright_pjecalc.py` v1):** para
ocorrencia_pagamento=DESLIGAMENTO + n > 1:
1. Iterar `input[type="checkbox"][id*=":listagem:"][id$=":ativo"]`
2. Ordenar por índice (`:listagem:N:ativo`)
3. Desmarcar TODAS exceto a última (mês de demissão)
4. Distribuição de valor: `[0,0,...,valor_total]` (última linha)

### Invariante 7 — Forensic DOM dump em 4 fases de INDENIZAÇÃO

**Justificativa:** Sem o dump, foi impossível identificar:
- onclick-exec não navegava (eduardo via `url_after`)
- matcher pegava row errada (`row_tds` no metadata)
- 9 rows existem mesmo após Sobrescrever (limite arquitetural H2)

**Fix:** `_dump_dom_indenizacao(verba, fase)` em pontos pre_click /
post_click / pre_recovery / post_recovery. Endpoints `/api/diag/dumps` e
`/api/diag/dump/{filename}` permitem inspeção.

Manter mesmo após INDENIZAÇÃO estar resolvida — é safety net para verbas
similares (futuras INFORMADO+DESLIGAMENTO+período curto).

---

## Melhorias pendentes — NÃO são limites arquiteturais

> Estas são pendências de investigação ativa. NÃO documentar como
> "limite arquitetural aceito" — são problemas reais a serem resolvidos.

### MP-1: INDENIZAÇÃO INFORMADO+DESLIGAMENTO+período curto — ✅ RESOLVIDO via H3

**Estado FINAL (25/05/2026, test 39, commit `6c66afe`):** ✅ 0 erros, **PJC exportado**.

**Solução adotada (H3 — Re-routing para Manual):**

Em `fase_verbas` (modules/playwright_v2.py), antes do split expresso/manual:
- Detecta verbas INFORMADO+DESLIGAMENTO
- Move da lista expresso para a lista manual
- `_lancar_verba_manual` cria com ocorrencia_pagamento=DESLIGAMENTO desde T0
- Sem alteração pós-geração → sem alert "param alterado APÓS geração"

**Hipóteses anteriores fracassadas (NÃO repetir — alert é temporalmente estrutural):**
1. ❌ Sobrescrever pós-params (`312839e` revertido `ac0c712`) — listagem vazia mid-loop.
2. ❌ Skip Regerar pós-params (`23f69ae` revertido `5bca99e`) — alert persiste mesmo
   sem o Regerar Manter, e mesmo com PROATIVO Sobrescrever depois. Comprova que
   o alert é gravado no momento do lançamento Expresso inicial (T0 com default MENSAL).

**Invariante novo (NÃO REVERTER):** o re-routing INFORMADO+DESLIGAMENTO → Manual
em `fase_verbas` deve ser preservado. Removê-lo regride INDENIZAÇÃO para o estado
"1 erro restante — manual edit required". Protegido em
`tests/test_invariantes_indenizacao.py::test_inv8_reroute_informado_desligamento_para_manual`.

### MP-2: HORAS EXTRAS 50% — quantidade=0 em modo INFORMADA

Já descrito acima na seção principal. Mantido como pendência ativa.

## Regra obrigatória — Apresentação do prompt do Projeto Claude externo

> **Quando o usuário solicitar a versão atualizada do prompt do Projeto Claude
> externo (ex.: "me dá o prompt externo", "arquivo integral atualizado",
> "para colar no projeto"), Claude DEVE entregar:**
>
> 1. **Formato com as 2 ETAPAS prévias** — `SYSTEM_PROMPT_V2_EXTERNAL` =
>    `_FLUXO_2_ETAPAS + SYSTEM_PROMPT_V2` (definido em `modules/extraction_v2.py`).
>    Começa com `# FLUXO OPERACIONAL — 2 ETAPAS (OBRIGATÓRIAS)` e contém:
>    - Etapa 1: resumo prévio + validação em markdown (PRIMEIRA resposta)
>    - Etapa 2: JSON estruturado (resposta APÓS "confirmar")
>
> 2. **Integral** — TODAS as ~1444 linhas (do "# FLUXO OPERACIONAL" até
>    "Lembre-se: SOMENTE JSON na resposta. Sem texto extra."). NUNCA versão
>    resumida, NUNCA por capítulos, NUNCA "blocos para colar separadamente".
>
> 3. **Atualizado** — versão renderizada DINAMICAMENTE a partir da fonte:
>    ```python
>    from modules.extraction_v2 import SYSTEM_PROMPT_V2_EXTERNAL
>    ```
>    Garante que reflete TODAS as últimas correções (divisor CLT,
>    prescricao_quinquenal, verba única, etc.).
>
> 4. **Pronto para colar** — o texto deve poder ser copiado/colado DIRETAMENTE
>    nas Instructions do Projeto Claude no Anthropic Console, sem
>    pré-processamento, sem markdown decorativo de apresentação, sem
>    comentários do Claude entre as linhas.
>
> **Implementação recomendada:**
> ```bash
> python3 -c "
> from modules.extraction_v2 import SYSTEM_PROMPT_V2_EXTERNAL
> print(SYSTEM_PROMPT_V2_EXTERNAL)
> " > /tmp/prompt-externo-atualizado.md
> ```
> ou via endpoint: `curl -s http://147.15.26.201:8000/api/prompt-externo`.
>
> **Por que renderizar dinamicamente**: o prompt vive como código Python
> (`_FLUXO_2_ETAPAS + SYSTEM_PROMPT_V2`). Apresentar via cópia estática de
> `docs/prompt-projeto-claude-externo.md` corre risco de defasagem se este
> arquivo .md ficar desatualizado em relação ao `modules/extraction_v2.py`
> (fonte da verdade do que o sistema USA).

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

## Invariantes do Prompt (NÃO REVERTER)

O prompt da IA externa (`SYSTEM_PROMPT_V2_EXTERNAL` em `modules/extraction_v2.py`)
contém **invariantes permanentes** marcados com `INVARIANTE PERMANENTE — NÃO REVERTER`.
Esses invariantes foram aprendidos em diagnóstico de bugs reais e cada um existe
para impedir a recorrência de um problema concreto:

| Invariante | Causa raiz que motivou |
|---|---|
| **Verba ÚNICA para 13º SALÁRIO / FÉRIAS+1/3 / AVISO / ADICIONAIS / DIF SALARIAL / HE / COMISSÃO/GORJETA** | IA gerava verba por ano → PJE-Calc duplicava INSS, conferência inviável |
| **`data_termino_calculo` = MAX(periodo_fim)** — não `data_demissao` | Aviso projetado, estabilidade pós-contrato e pensão vitalícia exigem cobertura |
| **Verbas DESLIGAMENTO: `periodo_inicio` = 1º dia do mês da demissão** | PJE-Calc gera ocorrência mensal — ocorrência fora do período declarado trava liquidação |
| **`valor_informado_brl` SEMPRE positivo** (mesmo em deduções) | PJE-Calc trata sinais internamente |
| **Verbas DEDUÇÃO (VALOR PAGO/DEVOLUÇÃO) usam `valor_pago.valor_brl`** | Se posto em `valor_devido`, soma em vez de abater |
| **Histórico salarial CALCULADO: schema = `{quantidade_pct, base_referencia}`** | IA confundia com schema de verba (`base_calculo.tipo`) |
| **Etapa 1 do resumo consolida verbas recorrentes** | IA listava períodos como itens separados no resumo, induzindo JSON errado |
| **`prescricao_quinquenal=true` SÓ se contrato ≥5 anos** | JSF rejeitava save da Fase 2 — cálculo nunca commitava no DB — cascata de falhas em todas as fases pós Fase 2 (Scarlette 22/05/2026) |

### Validação automática

`tests/test_prompt_invariants.py` valida que cada invariante está presente no prompt.
**Roda em CI e bloqueia merge** se algum invariante desaparecer. Antes de editar o
prompt, rode:

```bash
pytest tests/test_prompt_invariants.py -v
```

Se um teste falhar após sua edição, **não é o teste que está errado** — é a edição
que removeu uma proteção. Restaure o invariante ou justifique explicitamente a
remoção com o usuário.

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
./deploy/oracle-cloud/deploy.sh 147.15.26.201 ~/Downloads/ssh-key-2026-03-31.key

# SSH into VM
ssh -i ~/Downloads/ssh-key-2026-03-31.key opc@147.15.26.201

# Production URL
http://147.15.26.201:8000

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

### Caminhos de entrada (3 — TODOS preservados, NUNCA remover um em favor de outro)

| Caminho | Rota | Quem extrai | Status |
|---|---|---|---|
| **Extração IA in-app** | `/novo/ia` → `/processar/ia` | API Anthropic no próprio app (Sonnet 4.6, `SYSTEM_PROMPT_V2_EXTERNAL`) | padrão desde 12/06/2026 |
| **JSON do Projeto Claude externo** | `/novo` (colar/subir .json) → `/processar/v2` | usuário no claude.ai (Projeto com o prompt das Instructions) | preservado como opção |
| **Pipeline v1 legado** | `/processar` (PDF/DOCX direto) | `extraction.py` interno | legado |

### Extração IA in-app (`modules/webapp_extracao.py`, 12/06/2026)

Replica o fluxo do Projeto Claude externo dentro do app:

```
/novo/ia (colar sentença OU PDF/DOCX/TXT/MD + até 10 docs: PDF, fotos,
          MD/TXT, XLSX→markdown, textos colados com contexto)
    │ POST /processar/ia → worker thread → API Anthropic
    ▼
Etapa 1: resumo de validação em markdown (/resumo/ia/{id}, polling)
    │ usuário corrige (texto livre, iterativo) e/ou confirma
    ▼
Etapa 2: JSON v2 → normalize_v2_json → PreviaCalculoV2 → _save_previa
    ▼
/previa/v2/{id} — DAQUI EM DIANTE é 100% o pipeline v2 existente
```

**Invariantes (protegidos em `tests/test_webapp_extracao.py`):**
- **Fonte única do prompt**: importa `SYSTEM_PROMPT_V2_EXTERNAL` de
  `extraction_v2.py` — NUNCA copiar o texto do prompt para o módulo.
  Correções de prompt entram em vigor no deploy, sem recolar nada.
- **Prompt caching**: `cache_control ephemeral` no system E no último
  bloco da 1ª mensagem (prefixo inteiro: prompt + sentença + documentos).
  Correções/Etapa 2 leem o cache a 10% do preço de entrada (medido:
  39.6k tokens de cache_read por chamada no caso THAÍS). NÃO remover.
- **IA-only**: falha da API → fase `erro` com mensagem; sem fallback regex.
- **Aditivo**: `/processar/v2`, a auto-detecção `.json` no `/processar` e
  a UI de colar JSON permanecem intocados.
- Etapa 2 tem retry único de reemissão estrita se o JSON vier inválido.
- Sessões de extração têm TTL de 7 dias (anexos até 150MB/sessão).
- Usage (input/output/cache) persistido por etapa em `estado["usage"]` e
  exposto em `GET /api/ia/{id}/estado` (custo visível na tela do resumo).
- Regra SD (inv27): seguro-desemprego SÓ com indenização substitutiva.

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
- **IP**: `147.15.26.201` — porta 8000 (app) + opcionalmente Caddy nas 80/443
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

### ⚠️ INVARIANTE PERMANENTE — Match de verba no linkParametrizar (NUNCA mais quebrar)

> **Bug catastrófico descoberto 21/05/2026**: o match anterior fazia
> `tr.textContent.includes(nome_verba)` — pegava QUALQUER TR contendo o texto.
> Isso era catastrófico porque HE 50% tem reflexos como "FÉRIAS + 1/3 SOBRE
> HORAS EXTRAS 50%". Bot buscando "FÉRIAS + 1/3" matchava o TR de HE 50%,
> clicava no linkParametrizar dele e renomeava descricao → **HE 50% virava
> FÉRIAS + 1/3 no DB**. Listagem mostrava 2× FÉRIAS+1/3 e HE 50% sumia.

**Invariantes obrigatórios** (em `_configurar_parametros_pos_expresso`):

1. **Match EXATO no texto da célula** (não no TR inteiro):
   - Iterar `linkParametrizar` sem `:listaReflexo:` (só linhas de verba principal)
   - Para cada link, pegar `td` da row pai, comparar `td.textContent === alvo`
   - REJEITAR matches por substring/includes — só igualdade exata
   - Excluir texto "Exibir"/"Ocultar" dos links de detalhe

2. **NÃO renomear descricao para EXPRESSO_DIRETO**:
   - Verbas Expresso já vêm com nome canônico (54 nomes mapeados no PJE-Calc)
   - Mexer em descricao só faz sentido para EXPRESSO_ADAPTADO (rename intencional)
     ou MANUAL (form vazio precisa do nome)
   - Tocar descricao em EXPRESSO_DIRETO é desperdício — e em caso de match
     errado, corrompe a verba

3. **Salvaguarda de descricao no início de `_preencher_form_parametros_verba`**:
   - Para `com_identificacao=False` (pós-Expresso), LER `input[id$=':descricao']`
     atual ANTES de qualquer edição
   - Verificar que bate (case-insensitive) com `expresso_alvo` ou `nome_pjecalc`
   - Se divergir: **ABORTAR a edição** (return imediato, sem salvar) com log
     `🛑 ABORTANDO edição — form mostra verba ERRADA`
   - Evita corromper o DB silenciosamente

**Justificativa do usuário** (literal, 21/05/2026):
> "esses erros de falta de match não podem ocorrer, já que há um mapeamento
> completo das verbas de lançamento expresso contidas no pje calc (54 verbas)
> ... a necessidade de alterar nome da parcela somente ocorre qdo se trata
> de lancamento expresso adaptado, ou escrever o nome conforme condenação,
> no caso de lancamento manual ... torne perene os ajustes para que esse
> problema não retorne"

### ⚠️ HORAS EXTRAS 50% — quantidade=0 em modo INFORMADA (limite arquitetural)

> **NÃO RE-TENTAR as estratégias abaixo — todas falharam e algumas introduziram regressões graves.**

**Sintoma**: liquidação de HORAS EXTRAS 50% gera alerta não-bloqueante (`quantidade=0`) quando
o JSON especifica `quantidade.tipo=INFORMADA` com `valor` fixo (ex.: "20" horas/mês). O .PJC
liquida e exporta com sucesso, mas o usuário deve ajustar manualmente no PJE-Calc após import.

**Causa raiz identificada** (após investigação profunda): no PJE-Calc Cidadão local (H2),
o link `linkParametrizar` da listagem de verbas aciona `alterarVerba(verba)` via
`actionListener`, mas **a navegação para o form de Alteração não renderiza** mesmo após:
- `actionListener` executar com sucesso (`operacao=ALTERACAO` setado no bean)
- AJAX retornar 200 OK com `panelFormulario` no payload
- `panelFormulario.ajaxRendered=true` no template

O TRT7 em produção (PostgreSQL + JBoss real) renderiza o form normalmente — confirmado via
vídeo do usuário em 19/05/2026. O comportamento divergente sugere problema específico do
ambiente headless (H2 + Tomcat embarcado + Seam EPC).

**Estratégias TENTADAS e descartadas** (não repetir):
1. ❌ **GET refresh** em verba-calculo.jsf após linkParametrizar → quebrou Fase 5 com
   "Execution context destroyed because of a navigation"
2. ❌ **Post-processing do .PJC** mudando `<tipo>INFORMADA</tipo>` para
   `IMPORTADA_DO_CARTAO_DE_PONTO` → causou NPE em `Quantidade.resolverValor` no import
3. ❌ **Roteamento via fluxo Manual** (em vez de Expresso) → usuário rejeitou explicitamente
   ("use o lancamento expresso... o calcmachine consegue fazer")
4. ❌ **`<a4j:keepAlive beanName="apresentadorVerbaDeCalculo" />`** em verba-calculo.xhtml →
   introduziu `StaleObjectStateException` do Hibernate (versionamento otimista falha)
5. ❌ **Marcar `verbaSelecionada` antes de linkParametrizar** (Seam @DataModelSelection) →
   sem efeito
6. ❌ **Remover sidebar pré-click** (assumindo que bean SESSION-scoped não precisa init) →
   sem efeito, e na verdade o sidebar pre-click é necessário pra evitar NPE em
   `prepararMinicrudsDasBasesCadastradas:841` (verbaDeCalculoVO null)
7. ❌ **Combo "tudo junto"** (sidebar + native click + keepAlive) → herdou regressão do #4
8. ❌ **Patches no bytecode `ApresentadorVerbaDeCalculo.class`** → escopo grande demais, frágil
9. ❌ **`<f:setPropertyActionListener>` + reRender explícito em linkParametrizar**
   (Opção A — commit `3ee0645`, revertido em `d3735b5`/`e6eec53` em 20/05/2026) →
   **REGRESSÃO MASSIVA**: TODOS os saves de TODAS as fases passaram a falhar
   (`sucesso=False` em Fase 1 Dados, 8x Expresso, Honorários, Liquidar). Comparação
   com SSE v52 confirma: pré-patch tinha `sucesso=True` em tudo; pós-patch tudo falha.
   Causa raiz provável: `<f:setPropertyActionListener>` é **JSF 2.0**, mas PJE-Calc usa
   **JSF 1.2 + Seam 2.2** — a tag não existe nessa versão; Facelets pode estar abortando
   o parse do XHTML inteiro, fazendo `verba-calculo.jsf` retornar página vazia/NPE,
   o que cascateou para perda total do contexto Seam EPC em todas as fases.
   Não repetir tags JSF 2.0 (`<f:setPropertyActionListener>`, `<f:viewParam>`, etc.).
   Se precisar do efeito do `setPropertyActionListener`, usar a alternativa Seam:
   `<s:setPropertyActionListener>` (do namespace `http://jboss.com/products/seam/taglib`).
10. ❌ **`_navegar_menu` (URL direta) em vez de `_navegar_menu_via_click`** para evitar
    sidebar click após Fechar+Reabrir (commit `9419a23`, revertido em `cca2583` em
    20/05/2026) → Trouxe de volta o NPE em `prepararMinicrudsDasBasesCadastradas:841`
    que o sidebar click prevenia. URL direta NÃO chama `iniciar()` do bean Seam; só o
    sidebar click invoca o factory `@Begin` que popula `verbaDeCalculoVO`. Sem isso,
    `alterar()` lê `registroSelecionado` mas o bean explode em `prepararMinicruds`.
    **Conclusão**: o sidebar pré-click é arquiteturalmente necessário (já documentado
    como WIN preservado). Não tentar trocar por URL direta.

**Fixes mantidos que funcionam parcialmente** (Fechar+Reabrir + JS click):
- ✅ **Fechar+Reabrir pós-Expresso** (commit `96107f0`) — força @End da conv, garante
  que as 5 verbas Expresso são commitadas ao DB antes de tentar Ajustar parâmetros.
  Sem isso, a conv da última save só "via" 1 verba.
- ✅ **JS `element.click()` em vez de Playwright force=true** (commit `460d33a`) — o
  click puro do DOM dispara o `onclick` handler natural do browser, processando o
  AJAX corretamente. `force=true` tinha comportamento sutil errado em headless.

**Estado atual aceito (atualizado 20/05/2026)**: bot completa ciclo Sentença→PJC→
reimport→Liquidação. PJC tem todas as 5 verbas Expresso, FGTS, CS, Honorários,
Custas, Correção, etc. **Único alerta cosmético remanescente: HE 50% Quantidade fica
INFORMADA=0 em vez de IMPORTADA_DO_CARTAO**. Usuário ajusta manualmente (1 campo,
~30s). Tentar resolver arquitetonicamente até agora sempre arrisca regressões.

**Wins PRESERVADOS** que devem ser mantidos (não reverter):
- ✅ **H2 TCP server mode** (`jdbc:h2:tcp://localhost:9092/./pjecalc`) em `context.xml` +
  `iniciarPjeCalc.sh` — resolveu vários problemas de EPC do Seam
- ✅ **Native Playwright click** em `_configurar_parametros_pos_expresso` (vs JS onclick exec)
  — respeita `return false` do `A4J.AJAX.Submit`, evita `#irTopoPagina` quebrar AJAX
- ✅ **Sidebar pré-click** (`_navegar_menu_via_click("li_calculo_verbas")`) ANTES de
  linkParametrizar — evita NPE em `prepararMinicrudsDasBasesCadastradas` (bean precisa init)

**Estado atual aceito**: ~92% funcional. PJC liquida, exporta e importa. O alerta HE 50%
qtd=0 é cosmético — o usuário ajusta manualmente após import (1 campo, 30s). Tentar resolver
arquitetonicamente arrisca quebrar fases já funcionais.

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

### Verba Manual tipo REFLEXO — ✅ DOM MAPEADO (#80-AG, JANIELLY 0000706-46, 02/07/2026)

> Lacuna resolvida via `verba-calculo.xhtml` + diagnóstico #80-N em runs reais.
> Implementado em `_criar_reflexo_manual` / `_vincular_verba_principal_no_reflexo`
> (`modules/playwright_v2.py`). Protegido por `test_inv78`. **NÃO REVERTER.**

**DOM real do form Tipo=REFLEXO:**
- **Vínculo com a principal é OBRIGATÓRIO** — mini-crud "Verba \*":
  - select `formulario:baseVerbaDeCalculo` (opções = `listaTodasAsVerbas`,
    `s:convertEntity` → value é a entidade; casar pela **label** = nome da verba;
    tem `a4j:support ajaxSingle onchange` — a seleção só chega ao bean com
    **evento nativo** (`select_option` do Playwright); `dispatchEvent` JS NÃO
    dispara o A4J confiável → bean vazio → "Adicionar Base" adiciona NADA)
  - a4j:commandLink `formulario:incluirItemProp` ("Adicionar Base",
    `immediate=true` — não valida o form incompleto) → **native click**
  - tabela do mini-crud com `excluirItem` por linha — **verificar** que o item
    entrou (ground truth do bean) antes de prosseguir
  - Sem ≥1 item: save falha **silenciosamente** com "Campo obrigatório: Verba"
    (`formulario:baseVerbaDeCalculoErro`)
- ⚠️ **O radio `tipoDeVerba` LIMPA a lista** (`actionListener
  itensDaBaseVerba.clear()`) — vincular SEMPRE **depois** de Tipo=REFLEXO.
- ⚠️ **`integralizarBase` (select SIM/NAO) dispara A4J que re-renderiza o form**
  — sem `wait_for_selector` no `tipoDaQuantidade` depois dele, os campos
  seguintes e o botão `salvar` "somem" mid-fill (13º da JANIELLY).
- Assunto CNJ permanece obrigatório (lupa→modal, default 2581).
- Característica (`FERIAS`/`DECIMO_TERCEIRO_SALARIO`/`COMUM`) configurável —
  o bot aplica default por tipo do reflexo quando o override não define.

**Regras do fluxo (bot):** criação com retry ×3 re-abrindo o form; gate #80-H
pré-form; save verificado (`_aguardar_operacao_sucesso` + dump #80-N das
mensagens JSF); sucesso SÓ com a verba **confirmada na listagem**
(`_verificar_verba_na_listagem`, nome truncado a 50 — #80-O). Log "criado"
baseado apenas no click é proibido.

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

### H2 TCP server mode OBRIGATÓRIO — resolve Seam EPC + persistência (confirmado 19/05/2026)

**Descoberta crítica e RESOLUÇÃO definitiva**: H2 em modo **embedded** (default — `jdbc:h2:.dados/pjecalc`)
mantém um file-lock single-process que **rompe** o ciclo Seam EPC + JTA durante a automação
RPA (que executa múltiplas requisições JSF longas em sequência).

**Sintomas em embedded**:
- Cálculos novos criados via "Cálculo > Novo" não aparecem em Recentes
- Saves intermediários (verbas, FGTS, CS) não chegam à DB
- Liquidar abre conv fresca que lê estado stale → pendências falsas
- `h2 Shell` externo retorna: `"Database may be already in use: Locked by another process.
  Possible solutions: ... use the server mode"`

**Solução** (commits `142a2a9`):

1. `iniciarPjeCalc.sh` — iniciar H2 TCP server (porta 9092) ANTES do Tomcat subir:
   ```bash
   nohup java -cp "$H2_JAR" org.h2.tools.Server \
       -tcp -tcpPort 9092 -tcpAllowOthers \
       -baseDir "$PJECALC_DIR/.dados" &
   ```
2. `webapps/pjecalc/META-INF/context.xml` — DataSource via TCP:
   ```xml
   <Resource ... url="jdbc:h2:tcp://localhost:9092/./pjecalc" ... maxActive="20"/>
   ```

**Validação end-to-end (19/05/2026)** — sessão `cecf7937` com bot v45:
- Liquidação: `pendencia=False, sucesso=True`
- .PJC exportado: 12841 bytes
- Reimportação no PJE-Calc Cidadão: "Operação realizada com sucesso"

**NUNCA voltar para H2 embedded** em ambiente de automação. TCP server permite múltiplas conexões,
libera o file-lock e o Seam EPC se comporta corretamente com transações conv-scoped duradouras.

Bonus: o TCP mode permite diagnóstico externo via `h2 Shell` sem matar o Tomcat:
```bash
java -cp h2-1.3.154.jar org.h2.tools.Shell \
    -url "jdbc:h2:tcp://localhost:9092/./pjecalc" -user pjecalc -password "/pjecalc/"
```

### SSE stream — keepalive obrigatório
O SSE stream (endpoint `/api/executar/{sessao_id}`) precisa de keepalive a cada 10-15s para evitar
que o frontend (EventSource) desconecte durante operações longas (browser restart, AJAX pesado).
Thread de keepalive dedicada envia `"⏳ Processando…"` via queue.

### Histórico Salarial — extração obrigatória
O prompt de extração deve extrair histórico salarial SEMPRE (mesmo salário uniforme = 1 entrada).
Campos: nome, data_inicio, data_fim, valor, incidencia_fgts, incidencia_cs. O usuário pode
adicionar/remover entradas na prévia (botões + Adicionar / X Remover).

### Cartão de Ponto — Jornada regular × irregular (confirmado 17/05/2026)

**Decisão fundamental ao extrair sentença com Cartão de Ponto**:

| Tipo de jornada | Característica | `preenchimento` | Onde lançar |
|---|---|---|---|
| **REGULAR semanal** | Padrão repete a cada semana (ex: seg-sex 7h-18h) | `PROGRAMACAO` | `programacao_semanal` (8 dias × 6 turnos) |
| **REGULAR em escala** | Ciclo não-semanal (12x36, 5x1, etc) | `ESCALA` | `escala` (tipo + início + qtd_dias + jornadas) |
| **IRREGULAR** | Padrão semanal MAS com exceções (sábados alternados, plantões) | `PROGRAMACAO` ou `ESCALA` + `ocorrencias_override` | Padrão dominante na tabela + cada exceção em `ocorrencias_override` |
| **TOTALMENTE LIVRE** | Sem padrão (cada dia diferente) | `LIVRE` | `ocorrencias_override` listando cada dia |

**Mapeamento DOM confirmado** (v2.15.1):
- Programação: `formulario:listagemProgramacao:{D}:entradaM` / `:saidaM` onde D=0..7 (Seg..Feriado), M=1..6
- Escala: `formulario:escalas` (select), `formulario:valorHoraInicioEscala` (⚠ **HORA**, não data — size=6 timeMask), `formulario:qtdDiasTrabalhados`, `formulario:listagemEscala:{D}:entradaM`/`:saidaM`
- Tipos de escala (enum): `OUTRA`, `DOZE_POR_DOZE`, `DOZE_POR_VINTE_QUATRO`, `DOZE_POR_TRINTA_E_SEIS`, `DOZE_POR_QUARENTA_E_OITO`, `CINCO_POR_UM`, `SEIS_POR_UM`, `OITO_DOIS`

**Fluxo da automação**:
1. Salvar parâmetros do cartão (período, apuração, descanso, noturno, tolerância)
2. Preencher tabela Programação OU Escala conforme `preenchimento`
3. Salvar (PJE-Calc replica padrão para todo o período)
4. Para overrides: navegar Grade de Ocorrências → selecionar Mês/Ano → ajustar linhas pelas datas → salvar mês a mês

### ESCALA fixa (12x36 etc.) — #80-B (0000712-53, 27/06/2026) — NÃO REVERTER

> **Cadeia de A4J dependente**: o `select escalas` (onchange=`mudarTipoEscala`)
> HABILITA `valorHoraInicioEscala`; este ("Início Escala", size=6 timeMask = **HORA**,
> obrigatório) tem `onkeyup`=`atualizarListaEscala` que **AUTO-COMPUTA os turnos**
> da escala fixa a partir da hora de início (a tabela `listagemEscala` mostra os
> turnos DISABLED — auto, NÃO preencher). `qtdDiasTrabalhados` só é editável p/
> escala OUTRA.
>
> **Sem o fix**: o bot esperava só 800ms (campo disabled → pulado → "Campo
> obrigatório: Início Escala"), preenchia a DATA (esc.inicio) num campo de HORA,
> e setava via JS (`_preencher`) que NÃO dispara `onkeyup` → turnos não
> auto-computavam → "A jornada deve ter pelo menos um período de lançamento" →
> escala não salva → apuração 0 dias → verbas `IMPORTADA_DO_CARTAO` (INTERVALO)
> liquidavam qtd=0.
>
> **Fix**: aguardar o campo habilitar (`wait_for_function !disabled`); valor = HORA
> de entrada do 1º turno (ex.: "19:00"), não a data; **digitar via teclado real**
> (`press_sequentially`) p/ disparar o `onkeyup`+auto-compute; NÃO preencher os
> turnos. Validado run6: liquidação `painel_sucesso=True`, 0 erros, 0 alertas.
> `test_inv63`.

## Documentos de referência

@docs/diagnostico-falhas-automacao.md
@docs/analise-calc-machine-vs-agente.md

### INDENIZAÇÃO POR DANO MORAL (Expresso + INFORMADO + DESLIGAMENTO) — ✅ RESOLVIDO (#76c, 19/06/2026, inv48)

**Sintoma original**: para verbas com `valor=INFORMADO` (ex.: dano moral arbitrado em R$X) e
`ocorrencia_pagamento=DESLIGAMENTO`, a liquidação reclamava (totalErros=1):
- "O parâmetro Ocorrência de Pagamento foi alterado na página Verbas, após a geração
  das ocorrências da verba INDENIZAÇÃO POR DANO MORAL" (o **carimbo**).

**CAUSA RAIZ (descoberta via diag DOM direto na WASHINGTON 0000614-68)**: o botão Regerar
Ocorrências (`formulario:regerarOcorrencias`) **EXIGE ≥1 verba SELECIONADA** (checkbox
`formulario:listagem:selecionarTodos` ou `:N:verbaSelecionada`) antes do clique. Sem
seleção, o Ok do modal Confirmação retorna **"Erro. É necessário selecionar pelo menos
uma Verba Principal ou Reflexo"** e NÃO regenera nada. O bot
(`_regerar_com_modal_confirmacao`) **nunca marcava a verba** → TODO Regerar (Manter E
Sobrescrever) era **no-op silencioso**. O carimbo do dano moral só limpa via Sobrescrever
(regenera as ocorrências com a ocorrência DESLIGAMENTO já gravada nos parâmetros) — que
nunca rodava. As demais verbas funcionavam por não dependerem do Regerar (nascem corretas
do Expresso).

**FIX (#76c)**: `_regerar_com_modal_confirmacao` agora marca `selecionarTodos` (JS click)
ANTES de clicar Regerar. Combinado com:
1. **Routing Expresso** (#76): INDENIZAÇÃO POR DANO MORAL fica em
   `_VERBAS_EXPRESSO_DEFAULT_DESLIGAMENTO` (NÃO faz reroute p/ Manual) — entra via
   Expresso, parâmetros ajustados p/ `ocorrencia_pagamento=DESLIGAMENTO` +
   `valor=INFORMADO` (R$X) + `juros_aplicar_sumula_439=false`.
2. **Sobrescrever período curto** pós-parâmetros (agora executa) → limpa o carimbo.
3. **Inline ocorrências** seta `valorDevido=R$X` na ocorrência única DESLIGAMENTO.

**Validado end-to-end (run WASHINGTON 19/06/2026)**: dano moral R$5.000, DESLIGAMENTO,
totalErros=0, PJC exportado (CALCULO_102) com `ocorrenciaDePagamento=DESLIGAMENTO` +
`constante/valor=5000` + `devido=5000`. Protegido em
`tests/test_invariantes_indenizacao.py::test_inv48_regerar_seleciona_verbas`.

⚠️ **NÃO reverter** a seleção de verba no Regerar — sem ela TODOS os Regerar do bot
(Manter e Sobrescrever, em todas as verbas) voltam a ser no-op silencioso, regredindo
não só o dano moral mas qualquer correção que dependa de Regerar.

### Verba Expresso com reflexos auto-gerados (HORAS EXTRAS 50%) — ✅ RESOLVIDO (#79, 19/06/2026, inv51)

**Sintoma**: ao lançar HORAS EXTRAS 50% como 1ª verba via Expresso, o cálculo
liquidava SEM ela — no DB sobravam só os 5 reflexos candidatos órfãos
(`discriminador=R`, `ativo=N`: RSR/AVISO/FÉRIAS/13º/MULTA477) e o PRINCIPAL
`HORAS EXTRAS 50%` (C) não existia. A 2ª verba (INTERVALO, save leve) persistia.

**CAUSA RAIZ (diag DOM + consulta direta H2)**: o save Expresso de HORAS EXTRAS
50% faz o PJE-Calc auto-gerar 5 reflexos candidatos — save PESADO. Quando feito
na **conversa Seam INICIAL** (recém-criada na Fase 1), esse save NÃO commita o
principal (só os reflexos). A 2ª verba persiste porque é salva numa conversa
REABERTA (após o Fechar+Reabrir da 1ª). Comprovado: re-save da HE 50% em conversa
reaberta retorna `sucesso=True` e o H2 passa a ter o principal.

**FIX PREVENTIVO (#79)**: `_lancar_expresso` faz `_fechar_e_reabrir_calculo`
ANTES do loop, de modo que TODA verba (inclusive a 1ª) seja salva em conversa
reaberta limpa. Um retry CORRETIVO seria inviável: o save falho já deixa os 5
reflexos órfãos no DB, que um re-lançamento NÃO remove (duplicaria reflexos) —
por isso previne-se a falha na origem.

**Validado end-to-end (FRANCISCA 0001858-66, 22/06/2026)**: H2 confirma
`HORAS EXTRAS 50% | C | ativo=S | 2020-11-24 → 2025-09-02` (período capado pela
prescrição #78) + INTERVALO ativo; liquidação `totalErros=0`; PJC exportado com
ambas as verbas. A visibilidade da HE 50% na listagem do param-phase é resolvida
pela recovery "listagem vazia" já existente (Fechar+Reabrir → encontra a verba).
Protegido em `tests/test_invariantes_indenizacao.py::test_inv51_*`.

⚠️ **NÃO reverter** o Fechar+Reabrir pré-loop Expresso — sem ele a 1ª verba com
reflexos auto-gerados (HE 50%, ADICIONAIS, etc.) volta a sumir da liquidação.

### "Listagem de verbas fantasma" = LockTimeout no @Synchronized — ✅ RESOLVIDO (#80-D/G/H/I, 27/06/2026, GEOVANA 0000627-04, inv56–58)

**Sintoma (meses de fragilidade):** na fase de parâmetros, a listagem de verbas
vinha "vazia", disparando recoveries (Fechar+Reabrir) que NÃO convergiam (runs
com 0 "Parâmetros salvos" em ~600–1144 linhas SSE). Travava os fixes de valor
#80-A/C/E (forms nunca renderizavam).

**RAIZ (java.log + DIAG-#80-F + log persistido):** a "listagem vazia" é a página
**"Erro Interno no Servidor"** do
`org.jboss.seam.core.LockTimeoutException: could not acquire lock on
@Synchronized component: apresentadorVerbaDeCalculo`. `verba-calculo.xhtml`
renderiza via `#{apresentadorVerbaDeCalculo.verbaDeCalculoVO}` (@Synchronized, 1
req por vez). O bot NAVEGA à listagem/form enquanto o servidor ainda finaliza a
op pesada da verba anterior (save Expresso c/ reflexos + Regerar Drools, 20–40s
na VM pequena). O timeout do lock é o da **ANOTAÇÃO `@Synchronized` (~1000ms no
bytecode)** — `concurrent-request-timeout` do `<core:manager>` NÃO o afeta
(verificado: LockTimeout dispara mesmo com 120000). O LockTimeout no render
**MATA a conversa Seam** → redirect `principal.jsf` com **Recentes VAZIO
(nOpts=0) = cálculo IRREABRÍVEL** (perda total — por isso o recovery reativo
nunca convergia).

**Fix DEFINITIVO = PREVENÇÃO (não recovery):**
- **#80-H** (`_aguardar_servidor_ocioso`): esperar o networkidle ESTABILIZAR (2
  ciclos sem requisição em voo) ANTES de navegar — não navega = não mata a
  conversa. Chamado 2× em `_configurar_parametros_pos_expresso`: pré-listagem
  (antes do sidebar `li_calculo_verbas`) e pré-FORM (após o loop de reflexos,
  antes do click de Parâmetros). `test_inv58`.
- **#80-G** (rede de segurança p/ contenção residual com conversa VIVA): ao
  detectar a página de erro, poll 4s até ~84s recarregando a MESMA URL (sem nova
  conversa); bail imediato se redirecionar p/ principal.jsf. `test_inv57`.
- **#80-I**: reflexos MANUAL (RSR/FGTS criados como verba) navegam para o form do
  reflexo, SAINDO da listagem. Re-ancorar na listagem após o loop de reflexos se
  não houver `linkParametrizar` — senão o match exact-cell do PRINCIPAL falha e a
  quantidade da verba (HE 50%=157,5 / ADICIONAL=80) nunca é setada.
- **#80-E / _marcar_radio Estratégia 2**: JS por seletor (`page.evaluate`)
  robusto a detachment do A4J — o `locator.click(force=True)` dava timeout 30s
  "element detached" e engolia o dispatchEvent (afetava tipoDaQuantidade,
  multaDoFgts=40%, geraReflexo).
- **#80-J (reorder — RESOLVE o qtd=0 de HE 50%/ADICIONAL)**: reflexos MANUAL
  (RSR/FGTS, explícito OU fallback "sem checkbox") clicam Incluir e NAVEGAM p/
  o form do reflexo, SAINDO da listagem. Se criados ANTES do click de
  Parâmetros do principal, o principal não é mais encontrado → quantidade
  (157,5/80) nunca setada. Fix: `_configurar_reflexo(coletar_manual_em=lista)`
  DEFERE os Manual; o principal é configurado/salvo com o bot ANCORADO na
  listagem; os Manual deferidos são criados DEPOIS. Reflexos CHECKBOX (não
  navegam) seguem antes do save (invariante de flush). `test_inv59`.

**Validado end-to-end (run_K/L/N/O, GEOVANA):** liquidação `totalErros=0` + PJC
exportado em TODAS; "✓ #80-G listagem recuperada via reload leve (10 verbas) —
sem F+R" (conversa VIVA graças ao #80-H). **run_O (#80-J): PJC CALCULO_103 tem
`HORAS EXTRAS 50% valorInformado=157.5`, `ADICIONAL NOTURNO 80.0`,
`INTERVALO 7.5` — quantidades de cartão 100% fiéis ao JSON.** Alertas
remanescentes não-bloqueantes: CS histórico ÚLTIMA REMUNERAÇÃO (limite MP),
característica do reflexo Férias+1/3 sobre HE, e "Quantidade alterada após
geração" do INTERVALO (cosmético, ajustável via Regerar).

⚠️ **NÃO reverter** os gates `_aguardar_servidor_ocioso` nem o re-ancoramento
#80-I — sem eles a "listagem fantasma" e a morte-de-conversa (cálculo
irreabrível) voltam, regredindo a GEOVANA e qualquer cálculo pesado (3+ verbas de
cartão + reflexos). `concurrent-request-timeout=120000` é mantido (inofensivo,
cobre contenção de CONVERSA — NÃO é a alavanca do lock @Synchronized).

## Limitações conhecidas (19/05/2026) — não-bloqueantes

Após resolução do bug Seam EPC via H2 TCP, o bot completa o ciclo end-to-end
Sentença → JSON → PJC → reimportação → Liquidação. Mas restam **2 alertas**
não-bloqueantes que afetam **precisão de valores específicos**:

### 1. HORAS EXTRAS 50% — quantidade = 0 (alerta RN50 Drools)

**Sintoma**: PJC exportado tem a verba HE 50% com `<Quantidade><tipo>INFORMADA</tipo>
<valorInformado>0E-25</valorInformado></Quantidade>`. Após reimportação no
PJE-Calc, gera alerta "Todas as ocorrências da verba HORAS EXTRAS 50% foram
salvas com quantidade igual a zero."

**Causa raiz**: o bot clica `linkParametrizar` da verba para ajustar
`tipoDaQuantidade=IMPORTADA_DO_CARTAO` + selecionar coluna `Hs EXT`, mas o
JSF retorna "Target component for id listagem not found" (view-state stale
após Recentes reabertura). O form de Alteração não carrega — bot pula o
ajuste e a verba fica com defaults Expresso.

**Tentativas que NÃO funcionam** (registrar para evitar repetir):
- Retry de click com timeout maior → form continua sem carregar
- GET refresh em `verba-calculo.jsf` antes do click → **QUEBRA a Fase 5** com
  "Execution context was destroyed" (revertido em commit `e4a2835`)
- Editar XML do PJC pós-export para mudar `tipo` para `IMPORTADA_DO_CARTAO_DE_PONTO`
  → NPE em `Quantidade.resolverValor()` ao Liquidar reimportado (revertido em `b4b4792`)

**Status atual**: PJC liquida com sucesso após reimport (HE 50% só fica com
valor 0). Usuário pode ajustar manualmente no PJE-Calc real ou aceitar.

### 2. Histórico Salarial ÚLTIMA REMUNERAÇÃO — CS sem valor por ocorrência (alerta)

**Sintoma**: alerta "O Histórico Salarial ÚLTIMA REMUNERAÇÃO não possui valor
cadastrado para todas as ocorrências da Contribuição Social sobre Salários
Devidos." Não bloqueia liquidação.

**Status atual**: o bot marca `inss=true` + `proporcionalizarINSS=true` +
preenche `valorParaBaseDeCalculo`, mas não consegue setar `incideINSS` em cada
ocorrência mensal individualmente (mesma issue de view-state JSF).

### 3. Hibernate ConstraintViolation `IIDCALCULO NULL` (Fase 10b)

Log Tomcat eventual:
```
NULL not allowed for column "IIDCALCULO"
insert into TBSEGURODESEMPREGO (...)
```

Fase 10b Seguro-Desemprego tenta persistir entidade quando FK ainda não foi
flushed. **Não afeta** o PJC final (cálculo principal já commitado antes).

### Resumo da funcionalidade

| Critério | Estado |
|---|---|
| Sentença → Prévia → PJC | ✅ |
| PJC reimporta no PJE-Calc | ✅ "Operação realizada com sucesso" |
| Liquidação após reimport | ✅ "Operação realizada com sucesso" |
| Verbas com `valor=INFORMADO` | ✅ valorInformadoDoDevido aplicado |
| Verbas Expresso simples (13º, AVISO, SALDO, etc.) | ✅ defaults corretos |
| Cartão de Ponto apurado | ✅ |
| Histórico Salarial CS+proporcionalizarINSS | ✅ |
| HE 50% com tipoDaQuantidade=IMPORTADA_DO_CARTAO | ❌ usa default Expresso (qtd=0) |
| CS incideINSS por ocorrência mensal | ❌ não setado |
| Cobertura de senças diversas | ⚠ Testado apenas com 1 (cecf7937 — Paulo Roberto) |

## Problema em aberto (Tomcat headless)

O Tomcat embarcado (`pjecalc.jar`) pode ter dificuldade para subir em ambientes headless. O Lancador Java (`Lancador.java:42`) executa validações de startup e pode mostrar `JOptionPane` dialogs (GUI Swing) que bloqueiam o thread principal. O Xvfb + xdotool tenta auto-dismissar, mas o Java pode não iniciar o Tomcat corretamente.

**Diagnóstico**: acessar `http://147.15.26.201:8000/api/logs/java` após deploy para ver o stdout/stderr completo do Java (capturado em `/opt/pjecalc/java.log`).

**Abordagens alternativas a considerar**:
1. Iniciar Tomcat diretamente (bypassar Lancador) usando `org.apache.catalina.startup.Bootstrap` com as JARs de `bin/lib/`
2. Criar Java agent (`-javaagent`) para interceptar e silenciar `JOptionPane.showMessageDialog()`
3. Patch do bytecode de `Lancador.class` para remover a chamada GUI
