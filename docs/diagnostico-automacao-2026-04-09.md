# Diagnostico Completo da Automacao — 2026-04-09

Sessoes analisadas: 1dd2e1b0 (proc 0000227-53) e da070a28 (proc 0000259-58)
Log: /tmp/automacao_log_reconstituido.txt
Codigo: modules/playwright_pjecalc.py (7794 linhas)

---

## Tabela Resumo de Erros

| ID | Fase | Erro | Impacto | Causa Raiz | Prioridade |
|----|------|------|---------|------------|------------|
| E1 | 1 (Dados Processo) | "Existem erros no formulario" ao salvar | BLOQUEANTE | Tipo de Rescisao provavelmente nao selecionado (select default = vazio). _clicar_salvar() ignora resultado de erro. | P0 |
| E2 | 2a (Params Gerais) | "Existem erros no formulario" ao salvar | BLOQUEANTE | dataInicio=23/02/2021 — data de ajuizamento, nao de admissao. Manual exige data dentro do periodo contratual. | P0 |
| E3 | 2 (Hist. Salarial) | Botao incluir/Novo nao encontrado | DEGRADANTE | Apos salvar periodo 1, a pagina retorna para listagem mas o botao Incluir (formulario:incluir ou formulario:novo) nao e re-localizado. Apenas 1/3 periodos preenchidos. | P1 |
| E4a | 3 (Verbas Expresso) | "Erro: 2" ao salvar | DEGRADANTE | Expresso salvo sem que checkboxes fossem efetivamente registradas no modelo JSF (evento change nao disparado corretamente). | P1 |
| E4b | 3 (Verbas Manual) | HTTP 500 + formulario nao abre | BLOQUEANTE | ConversationId mudou de 6→46→56 (E5). Apos Expresso, formulario:incluir clica OK mas URL navega com conversationId expirado → HTTP 500. | P0 |
| E4c | 3 (Verbas Manual) | Verba nao registrada (campos vazios) | BLOQUEANTE | Ocorrencia, base_calculo, checkboxes FGTS/INSS/IRPF nao preenchidos. _preencher_radio_ou_select falha silenciosamente em campos cujo id JSF muda. | P1 |
| E5 | 3 (Verbas) | ConversationId muda 6→46→56 | BLOQUEANTE | Expresso save cria nova conversa JSF/Seam. Codigo captura novo ID mas _url_verbas_listing nao e atualizada antes das primeiras verbas manuais. | P0 |
| E6 | 4 (FGTS) | Formulario nao renderizou | COSMÉTICO | Re-abertura via Home + Menu FGTS corrigiu. Causa: AJAX incompleto apos fase Verbas com erros 500. | P2 |
| E7 | 8 (Honorarios) | "Existem erros no formulario" | DEGRADANTE | Campos obrigatorios de honorarios nao preenchidos: tipoHonorario, descricao, percentual. Manual exige Tipo + Descricao + Devedor + Valor. | P1 |
| E8 | 6 (Correcao/Juros) | "Erro inesperado. Erro: 1" | DEGRADANTE | Indice/taxa de juros setados em Fase 1 (Parametros) E de novo em Fase 6 — conflito ou campo nao encontrado na pagina correcao-juros.jsf. | P2 |
| E9 | Liquidacao | SESSAO REJEITADA / CNJ nao visivel | BLOQUEANTE | _verificar_calculo_correto() nao encontra numero CNJ na pagina. JA CORRIGIDO no ultimo commit (retorna True). | CORRIGIDO |

---

## Analise Detalhada

### E1 — Fase 1: "Existem erros no formulario"

**Log**: `Salvar: ERRO:A operação não pôde ser concluída. Existem erros no formulário.`

**Causa raiz**: O campo `tipoRescisao` (select dropdown na aba Parametros do Calculo) provavelmente nao e encontrado pelo seletor ou o valor nao e aceito. No codigo (linha 2629):
```python
self._selecionar("tipoRescisao", rescisao_map.get(...), obrigatorio=False)
self._selecionar("motivoDesligamento", rescisao_map.get(...), obrigatorio=False)
```
Como `obrigatorio=False`, a falha e silenciosa. Se nenhum dos dois IDs existir, o campo fica vazio e o PJE-Calc recusa salvar.

**BUG CRITICO em _clicar_salvar()** (linhas 1587-1589):
```python
loc.first.click(force=True)
_clicar_e_aguardar(sel)   # <-- resultado IGNORADO
return True               # <-- sempre retorna True!
```
O metodo `_clicar_e_aguardar` retorna `False` quando detecta erro, mas `_clicar_salvar` descarta esse retorno e sempre retorna `True`. Isso significa que `_salvar_com_deteccao_erros` nunca tenta corrigir erros porque acha que o save foi bem-sucedido.

**Solucao**:
1. Corrigir `_clicar_salvar` para propagar o retorno de `_clicar_e_aguardar`
2. Adicionar fallback para campo tipoRescisao com busca por opcoes do select

### E2 — Fase 2a: "Existem erros no formulario"

**Log**: `data dataInicio: 23/02/2021`

**Causa raiz**: O campo `data_inicial_apuracao` recebeu 23/02/2021 (5 anos antes da admissao 01/04/2025). Isso e provavel prescricao quinquenal retroativa do ajuizamento (23/02/2026 - 5 anos = 23/02/2021).

O manual diz (Secao 5.2): "Data Inicial / Data Final: Limita periodo do calculo quando verbas nao sao devidas por todo o contrato". A data de inicio de apuracao deve ser >= admissao. Se anterior a admissao, o PJE-Calc rejeita.

**Solucao**: Validar que `data_inicial_apuracao >= data_admissao`. Se nao, usar `max(data_inicial_apuracao, data_admissao)`.

### E3 — Historico Salarial: Apenas 1/3 periodos

**Log**: `Botao 'incluir'/'Novo' nao encontrado no Historico Salarial`

**Causa raiz**: Apos salvar o primeiro periodo, a pagina redireciona para a listagem do historico (`historico-salarial.jsf`). O botao "Incluir" (ou "Novo") neste contexto pode ter ID diferente: `formulario:novo` em vez de `formulario:incluir`, ou ser um link `<a>` em vez de `<input>`.

O codigo tenta `_clicar_botao_id("incluir")`, `_clicar_botao_id("btnNovoHistorico")`, `_clicar_botao_id("novo")` e depois um JS generico — mas apos o primeiro save + AJAX redirect, o DOM pode ter mudado e os IDs podem ter sufixos numericos diferentes.

**Solucao**: Apos salvar cada periodo, navegar explicitamente para `historico-salarial.jsf?conversationId=X` antes de tentar clicar "Incluir" novamente. Aguardar carregamento completo da listagem.

### E4a — Verbas Expresso: "Erro: 2"

**Log**: `Salvar: ERRO:Erro. Erro inesperado. Verifique o log do sistema. Erro: 2`

**Causa raiz**: O "Erro: 2" do PJE-Calc ocorre quando o modelo JSF nao reconhece as selecoes feitas via automacao. Os checkboxes do Expresso foram marcados via JS (`checked = true`), mas o evento `change` pode nao ter sido propagado corretamente ao modelo JSF do RichFaces.

A tabela Expresso usa `<a4j:repeat>` com checkboxes dentro de linhas. A marcacao via JS + `dispatchEvent(new Event('change'))` nem sempre aciona o `<a4j:support event="change">` do RichFaces que registra a selecao no bean server-side.

**Solucao**: Usar `click()` nativo do Playwright em vez de JS `checked=true` nos checkboxes Expresso. Se o checkbox nao e visivel (fora do viewport), scroll ate ele primeiro.

### E4b/E5 — ConversationId mudando + HTTP 500 verbas manuais

**Log**:
```
Parametros 'SALDO DE SALARIO': navegacao inesperada → calculo.jsf?conversationId=56
HTTP 500: verba-calculo.jsf?conversationId=46
```

**Causa raiz**: O Seam Framework (JSF) gera uma nova `conversationId` quando o usuario navega entre paginas. O save do Expresso criou conversationId=46 (era 6). A navegacao para parametros da verba criou conversationId=56.

O codigo captura o novo ID em `_capturar_base_calculo()` (linha 3502), mas `_url_verbas_listing` na funcao `_lancar_verbas_manual` e calculada no inicio da funcao (linha 4278-4284) e nao e re-calculada apos cada iteracao consistentemente. Apos o primeiro erro 500, a recuperacao navega para URL com ID expirado.

**Solucao**: Re-calcular URLs de navegacao no inicio de CADA iteracao de verba manual (nao apenas apos save).

### E4c — Verbas manuais: campos nao preenchidos

**Log**:
```
Verba 'Aviso Previo Indenizado - Diferencas': ocorrencia 'Desligamento' NÃO preenchida
Verba 'Aviso Previo Indenizado - Diferencas': base_calculo nao preenchida
radio valor=CALCULADO: nao encontrado
checkbox FGTS nao encontrado
```

**Causa raiz**: Os campos do formulario manual de verbas usam IDs JSF gerados (ex: `formulario:j_id_xxx:caracteristicaVerba`). A funcao `_preencher_radio_ou_select` busca por sufixo do ID, mas:
1. O radio `valor` (CALCULADO/INFORMADO) tem ID `formulario:valor:0` / `formulario:valor:1` — o seletor busca `[id*='valor']` que match multiplos elementos
2. Os checkboxes FGTS/INSS/IRPF podem ter IDs como `formulario:fgts`, `formulario:inss` etc. mas no formulario de verba manual os IDs podem ser diferentes: `formulario:j_id_xxx:incidenciaFGTS`
3. `_sel_por_opcoes` e a estrategia correta (identificar select pelas opcoes), mas os radios nao tem essa logica equivalente

**Solucao**: Implementar logica de fallback por label/conteudo para radios (similar a `_sel_por_opcoes` para selects). Para checkboxes, buscar por label text em vez de apenas por ID.

### E7 — Honorarios: "Existem erros no formulario"

**Log**: `Salvar: ERRO:A operação não pôde ser concluída. Existem erros no formulário.`

**Causa raiz**: O manual (Secao 19) diz que os campos obrigatorios sao:
- Tipo de Honorarios (rubrica do PJe-JT)
- Descricao (ate 60 caracteres)
- Devedor (Reclamante ou Reclamado)
- Tipo de Valor (Calculado ou Informado)

O codigo tenta preencher `tipoDeDevedor`, `tipoHonorario`, `tipoValor` — mas nao preenche `descricao` (campo obrigatorio de texto). Alem disso, se `tipo_valor=CALCULADO`, o campo `percentual` e obrigatorio (5-15% para sucumbencia).

**Solucao**: Adicionar preenchimento do campo `descricao` com texto default (ex: "Honorarios Sucumbenciais") e garantir que percentual seja preenchido quando tipo_valor=CALCULADO.

### E8 — Correcao/Juros: "Erro inesperado. Erro: 1"

**Causa raiz**: O "Erro: 1" do PJE-Calc geralmente indica campo obrigatorio nao preenchido ou valor incompativel. Na Fase 6, os indices ja foram parcialmente setados na Fase 1 (linhas 2690-2714) — o que pode causar conflito no modelo JSF quando a pagina correcao-juros.jsf e salva com valores diferentes.

Outra possibilidade: o campo `dataInicioTaxaLegal` (30/08/2024) e setado mas a Taxa Legal nao esta disponivel como opcao no dropdown `taxaJuros` da versao do PJE-Calc em uso.

**Solucao**: Nao setar indices na Fase 1 (Parametros do Calculo) — deixar para Fase 6 exclusivamente. Verificar se o valor TAXA_LEGAL existe no dropdown antes de seta-lo.

---

## Prioridades de Implementacao

### P0 — Bloqueantes (impedem liquidacao)

1. **FIX _clicar_salvar()**: Propagar retorno de _clicar_e_aguardar para que _salvar_com_deteccao_erros consiga detectar e corrigir erros
2. **FIX conversationId em verbas manuais**: Re-calcular URLs no inicio de cada iteracao
3. **FIX Fase 2a dataInicio**: Validar data_inicial >= admissao

### P1 — Degradantes (perdem dados)

4. **FIX Historico Salarial multiplos periodos**: Navegar para listagem apos cada save
5. **FIX Verbas Expresso checkboxes**: Usar click() nativo em vez de JS checked=true
6. **FIX Verbas Manual campos obrigatorios**: Fallback por label para radios/checkboxes
7. **FIX Honorarios**: Preencher campo descricao obrigatorio

### P2 — Cosmeticos/Menores

8. FIX Fase 6: Nao duplicar configuracao de indices (ja feita em Fase 1)
9. FIX FGTS re-render: Ja tem retry funcional

---

## Codigo Modificado

Ver commit associado para implementacao das correcoes P0 e P1.
