# Registro de Erros (Não-Fatais) — Automação PJE-Calc

Documenta divergências entre o **schema/automação** e a **fidelidade absoluta** ao DOM real do PJE-Calc. Cada item exige correção para garantir liberalidade total dos campos/opções como percebidas pelo usuário no sistema oficial.

**Princípio**: o mapeamento das páginas (em `docs/dom-mapping/` e `docs/schema-v2/`) deve refletir 1:1 o que o usuário pode fazer no PJE-Calc — sem suposições, sem normalizações silenciosas.

---

## Sessão 96ef132d (0001512-18.2025.5.07.0003) — automação 04/05/2026 14:48-15:25

### E01 — FGTS: alíquota `OITO_POR_CENTO` não encontrada

**Local**: `modules/playwright_pjecalc.py` — Fase 4 (FGTS)
**Log**:
```
2026-05-04 15:10:18 [info]   → FGTS: preenchendo aliquota…
2026-05-04 15:10:44 [info]   ⚠ radio aliquota=OITO_POR_CENTO: não encontrado
2026-05-04 15:10:44 [info]   ⚠ aliquota=OITO_POR_CENTO: budget de 20s estourado — pulando
```

**Causa provável**: valor `OITO_POR_CENTO` esperado pelo código não existe no DOM (pode ser `8`, `0.08`, `OITO`, ou o campo é input numérico em vez de radio).

**Ação**: inspecionar via Chrome MCP a página `fgts.jsf` para listar os values reais dos radios e atualizar o schema/automação. Atualizar `docs/dom-mapping/` se faltava esse campo.

---

### E02 — FGTS: `incidenciaDoFgts` disabled

**Local**: `modules/playwright_pjecalc.py` — Fase 4 (FGTS)
**Log**:
```
2026-05-04 15:10:44 [info]   ⚠ select incidenciaDoFgts: disabled — tentando JS direto
2026-05-04 15:10:59 [info]   ✓ select incidenciaDoFgts: SOBRE_O_TOTAL_DEVIDO (via JS disabled override)
```

**Causa provável**: o select fica disabled enquanto outro campo upstream (provavelmente `tipoDeVerba` ou `comporPrincipal`) não dispara o AJAX que o habilita. Foi contornado via `disabled=false` via JS, mas isso pode não persistir o valor no servidor.

**Ação**: identificar a dependência exata (qual campo dispara o enable) e aguardar o AJAX antes de tentar selecionar. O override JS pode ter passado mas talvez o backend ignorou o valor — verificar no .PJC final se `incidenciaDoFgts` ficou como `SOBRE_O_TOTAL_DEVIDO`.

---

### E04 — IRPF: navegou mas URL ficou em parametrizar-inss

**Local**: Fase 7 (IRPF)
**Log**:
```
2026-05-04 15:17:08 [info]   ⚠ IRPF: URL inesperada (.../parametrizar-inss.jsf?conversationId=170) — tentando continuar
2026-05-04 15:17:34 [info]   ⚠ Salvar: mensagem de sucesso não detectada em 10s (prosseguindo)
```

**Causa provável**: o click no menu lateral "Imposto de Renda" não disparou a navegação JSF — possivelmente porque o cálculo estava preso em `parametrizar-inss.jsf` (sub-página de INSS) e o framework não saiu daquela vista. A automação seguiu, mas o "Salvar" foi no contexto errado.

**Ação**: depois de qualquer sub-página (parametrizar-inss, parametrizar-irpf), forçar `window.location` ou clicar no link "Voltar" antes de mudar de seção. Detectar: se URL contém `/parametrizar-` após click no menu, é falha de saída.

---

### E05 — Honorários: botão Novo não encontrado, ambos pulados

**Local**: Fase 8 (Honorários)
**Log**:
```
2026-05-04 15:17:50 [info]   ⚠ Honorários: URL inesperada (...parametrizar-inss.jsf...)
2026-05-04 15:18:50 [info]   ⚠ Botão Novo não encontrado — pulando honorário 1
2026-05-04 15:19:50 [info]   ⚠ Botão Novo não encontrado — pulando honorário 2
2026-05-04 15:20:06 [info]   ⚠ radio tipoValor=INFORMADO: não encontrado
2026-05-04 15:20:06 [info]   ⚠ Campo periciais não encontrado — preencher manualmente: 2.000,00
```

**Causa**: efeito cascata do E04 — a automação nunca saiu de `parametrizar-inss.jsf`, então a página de Honorários nunca carregou. Os elementos clicáveis listados no log são todos do menu lateral, não da seção Honorários.

**Ação**: corrigir E04 primeiro. Adicionar guard `assert "honorarios" in page.url` antes de tentar preencher honorários — se a URL é diferente, abortar a fase com pendência.

---

### E06 — Custas: múltiplos radios ausentes (cascata de E03)

**Local**: Fase 9 (Custas Judiciais)
**Log**:
```
⚠ select baseParaCustasCalculadas: não encontrado — selecione manualmente
✗ Base custas: FALHA ao selecionar 'BRUTO_DEVIDO_AO_RECLAMANTE'
⚠ radio custasReclamadoConhecimento=CALCULADA_2_POR_CENTO: não encontrado
⚠ radio custasReclamadoLiquidacao=NAO_SE_APLICA: não encontrado
⚠ radio custasReclamanteConhecimento=NAO_SE_APLICA: não encontrado
```

**Causa**: novamente cascata — automação preso em parametrizar-inss; e mesmo se chegasse a custas-judiciais.jsf, os values esperados (UPPER_SNAKE) parecem não bater com o DOM real.

**Ação**: além de E03, mapear via Chrome MCP os values reais de TODOS os radios em `custas-judiciais.jsf`.

---

### E07 — Correção/Juros: 4 URLs candidatas resultam em 404

**Local**: Fase 6 (Correção, Juros e Multa)
**Log**:
```
⚠ HTTP 404: .../pages/calculo/correcao-juros.jsf
⚠ HTTP 404: .../pages/calculo/atualizacao.jsf
⚠ HTTP 404: .../pages/calculo/correcao-juros-e-multa.jsf
⚠ HTTP 404: .../pages/calculo/parametros-atualizacao.jsf
⚠ Correção/Juros: página não encontrada — pulando configuração de índices
```

**Causa**: o nome real do `.xhtml` da página de Correção não foi descoberto. Lista do menu lateral mostra item "Correção, Juros e Multa" (`formulario:j_id38:0:j_id41:22:j_id46`), mas o código tenta URLs adivinhadas.

**Ação**: clicar no `<a>` do item de menu via JSF (já existe `_navegar_menu("li_calculo_correcao_juros_multa")` no v2, ou inspecionar a URL real na nossa instalação). Mapear na inspeção DOM sistemática.

---

### E08 — Liquidar: campo `acumularIndices` ausente

**Local**: Fase Liquidar
**Log**: `⚠ Campo acumularIndices não encontrado na página de liquidação`

**Causa provável**: nome do campo divergente. O DOM real provavelmente usa `indicesAcumulados` (já documentado em `docs/dom-mapping/`), não `acumularIndices`.

**Ação**: padronizar para `indicesAcumulados` (ou descobrir nome real via Chrome MCP).

---

### E09 — FATAL: Liquidar destruiu contexto de execução JS

**Local**: `playwright_pjecalc.py:11723` em `_clicar_liquidar`
**Log**:
```
playwright._impl._errors.Error: Page.evaluate: Execution context was destroyed,
   most likely because of a navigation
2026-05-04 15:21:53 [error] Erro na automação (generator)
```

**Causa**: o click no botão Liquidar via `page.evaluate("""()=>{...}""")` disparou navegação JSF (POST→redirect) ANTES do evaluate retornar. O Playwright destrói o contexto JS quando há navigation, e a Promise pendente falha.

**Ação**:
1. Substituir `page.evaluate(...click())` por `page.locator(sel).click()` quando se sabe que o botão dispara navegação — Playwright trata melhor.
2. Ou, se precisa de evaluate, usar `page.evaluate(... ; return null)` e capturar a navegação com `page.expect_navigation()` no contexto.
3. Adicionar try/except para `Execution context was destroyed` como caso esperado quando o click DEVE provocar navegação — não é erro fatal, é o comportamento desejado.

---

### E03 — Custas: valor da prévia incompatível com value do DOM

**Local**: `modules/playwright_pjecalc.py` — Fase 9 (Custas Judiciais)
**Log**:
```
2026-05-04 15:20:22 [info]   ✗ Base custas: FALHA ao selecionar 'BRUTO_DEVIDO_AO_RECLAMANTE'
   — prévia indicava 'Bruto Devido ao Reclamante'
```

**Causa**: a prévia foi gerada com o **label** ("Bruto Devido ao Reclamante") em vez do **value** (`BRUTO_DEVIDO_AO_RECLAMANTE`). A extração não normalizou — ou normalizou com regra inversa.

**Ação**:
1. Em `extraction.py` (v1) e `extraction_v2.py`: o prompt deve gerar o **value canônico UPPER_SNAKE_CASE**, não o label.
2. Adicionar normalizador no schema Pydantic: `field_validator` que aceita label OU value e converte para value.
3. Documentar em `docs/schema-v2/13-custas.md` o domínio completo de values e seus labels.

---

## Pendências de mapeamento DOM (a serem inspecionadas)

Para garantir fidelidade absoluta, **toda página do PJE-Calc** precisa ter o domínio de values dos selects/radios/checkboxes documentado. Páginas onde já se observou divergência:

- [ ] `fgts.jsf` — alíquota (E01), incidenciaDoFgts (E02)
- [ ] `custas-judiciais.jsf` — baseParaCustasCalculadas (E03), custasReclamado/Reclamante×Conhecimento/Liquidação (E06)
- [ ] `imposto-de-renda.jsf` — saída de parametrizar-inss antes de navegar (E04)
- [ ] `honorarios.jsf` — campos `tipoValor`, `periciais`, botão "Novo" (E05)
- [ ] `correcao-juros-e-multa.jsf` (?) — URL real desconhecida; 4 chutes 404 (E07)
- [ ] `liquidacao.jsf` — campo `acumularIndices`/`indicesAcumulados` (E08), navegação destrutiva (E09)

Próxima ação preventiva: rodar inspeção sistemática via Chrome MCP em todas as páginas listadas em `docs/dom-mapping/00-INDEX.md`, capturando para cada `<select>`, `<input type=radio>`, `<input type=checkbox>`:
- nome do field
- value de cada opção
- label de cada opção
- AJAX listeners (qual campo upstream o habilita/oculta)

Salvar em `docs/dom-mapping/dominios-values.json` (estrutura: `{ pagina: { campo: [{value, label, depende_de}] } }`).

---

## Política de erros não-fatais

A automação atual usa `obrigatorio=False` em vários campos, o que **mascara bugs de mapeamento**. Sugestão para v2:

1. **Modo estrito**: erros de mapping (value não encontrado, select disabled) abortam a fase e disparam pendência na prévia.
2. **Modo tolerante**: continuam pulando, mas registram em `data/logs/erros_mapping_{sessao}.json` com:
   - fase, campo, valor_tentado, motivo (radio_nao_encontrado / select_disabled / dom_nao_existe)
   - estado do DOM no momento (HTML do form)
3. Endpoint `GET /api/erros-mapping/{sessao}` para revisão posterior.
