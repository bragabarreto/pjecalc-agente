# Correções da Auditoria Geral — 2026-04-09

Registro de todas as correções aplicadas após análise minuciosa do código.

## CRÍTICOS

- [x] **#1** JS injection sem escape em `_preencher()` e `_preencher_data()` — Corrigido: usar `page.evaluate("(el, v) => ...", valor)` com parâmetro separado em vez de f-string
- [x] **#2** `_clicar_novo()` em `fase_faltas()` → substituído por `_clicar_botao_id("incluir")`
- [x] **#3** `_skip_expresso` não inicializada → adicionado `_skip_expresso = False` antes do `if _nome_principal_ref`
- [x] **#4** `multas_indenizacoes` nunca extraído → adicionado ao `_EXTRACTION_SCHEMA` em extraction.py
- [x] **#5** `custas_judiciais` ausente do JSON Schema → adicionado ao `_EXTRACTION_SCHEMA` em extraction.py

## ALTOS

- [x] **#6** `_clicar_novo()` em `fase_multas_indenizacoes()` → substituído por `_clicar_botao_id("incluir")`
- [x] **#7** SidebarMenu sem "Custas Judiciais" → adicionado `CUSTAS_JUDICIAIS` e `CORRECAO_JUROS` a pjecalc_selectors.py + entradas no `_MENU_ID_MAP`
- [x] **#8** Classes de seletores não importadas → importadas: `ParametrosGerais`, `FeriasSelectors`, `FaltasSelectors`, `VerbaParametro`, `VerbaOcorrencia`, `IRSelectors`, `CustasSelectors`
- [x] **#9** Endpoints `/api/dom-audit` não existiam → adicionados `GET /api/dom-audit` e `GET /api/dom-audit/status` ao webapp.py

## MÉDIOS

- [x] **#10** `valorJornadaSabado`/`Dom` → seletores atualizados com fallback duplo: `valorJornadaDiariaSabado` + `valorJornadaSabado`
- [x] **#11** Multa 467 CLT como verba Expresso → adicionado filtro `_apenas_fgts` em `fase_verbas()` para excluir da lista de verbas
- [x] **#12** Verbas duplicadas no catálogo → removidas Dano Moral/Material/Estético da seção `expresso` (pertencem a Multas/Indenizações via `somente_manual`)
- [x] **#13** `DATA_CALCULO` com `[id*='dataDe']` ambíguo → removido (seletor morto, substituído por comentário)
- [x] **#14** Constantes importadas mas não usadas nas fases → por design: `_preencher(suffix)` e `page.locator(CSS)` coexistem. Não requer mudança.
- [x] **#15** blur não disparado em `_preencher()` → por design: blur intencional evita race condition AJAX. Comentário melhorado.
- [x] **#16** JS `evaluate()` com concatenação frágil → refatorado para passar seletores via parâmetro `{sucesso, erro}` ao JS

## BAIXOS

- [x] **#17** `a4j\:commandButton[id$='salvar']` seletor morto → removido
- [x] **#18** `justica_gratuita` não required → adicionado ao `required` do schema
- [ ] **#19** 5 páginas sem classe de seletores → será resolvido incrementalmente via DOM Auditor
- [ ] **#20** 20+ campos do manual sem seletores → será resolvido incrementalmente via DOM Auditor

## Arquivos modificados

| Arquivo | Alterações |
|---------|-----------|
| `modules/playwright_pjecalc.py` | #1, #2, #3, #6, #7, #8, #11, #14, #15, #16, #17 |
| `modules/extraction.py` | #4, #5, #18 |
| `knowledge/pjecalc_selectors.py` | #7, #10, #13 |
| `knowledge/catalogo_verbas_pjecalc.json` | #12 |
| `webapp.py` | #9 |

## Progresso

| Etapa | Status | Commit |
|-------|--------|--------|
| Críticos #1-#5 | CONCLUÍDO | pendente |
| Altos #6-#9 | CONCLUÍDO | pendente |
| Médios #10-#16 | CONCLUÍDO | pendente |
| Baixos #17-#18 | CONCLUÍDO | pendente |
| Baixos #19-#20 | ADIADO (DOM Auditor) | — |
