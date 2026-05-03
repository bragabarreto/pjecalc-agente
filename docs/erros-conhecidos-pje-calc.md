# Erros conhecidos do PJE-Calc — base de aprendizado

> Catálogo de erros já enfrentados pelo agente de automação, com causa, fix
> aplicado e prevenção. Use para evitar re-ocorrência e treinar o classificador.

---

## E01 — `hashCodeLiquidacao=null` no PJC exportado
**Sintoma**: Arquivo `.PJC` (~74 KB) é gerado mas, ao importar no PJE-Calc, aparece "arquivo inválido".

**Causa raiz**: O agente clicou Exportar **antes** de Liquidar com sucesso. PJE-Calc retornou um template ZIP com `<hashCodeLiquidacao>null</hashCodeLiquidacao>` e `<dataDeLiquidacao>null</dataDeLiquidacao>` — sempre rejeitado na importação.

**Detecção**: o XML interno (`calculo.xml`) com qualquer um dos dois campos `null`.

**Fix aplicado** (commit `8e019ca`): regra proibitiva `_validar_pjc_liquidado()` rejeita PJC sem hashCode/dataDeLiquidacao em todas as 4 fases de captura (A, E, D, _salvar_download). `gerar_pjc()` nativo Python levanta `RuntimeError`. webapp `/download/{sid}/pjc` valida antes de servir (HTTP 409 se inválido).

**Prevenção**: nunca tentar exportar sem confirmar mensagem JSF "Cálculo liquidado com sucesso".

---

## E02 — "Falta selecionar pelo menos um Histórico Salarial"
**Sintoma**: Liquidação bloqueia com erro em verbas variáveis (HE 50%, COMISSÃO, INTERVALO, AD NOTURNO, etc.).

**Causa raiz**: Para verbas com `tipoDaBaseTabelada=HISTORICO_SALARIAL` (default Expresso de variáveis), apenas **selecionar** o select `baseHistoricos` **NÃO basta**. É preciso clicar o link `formulario:incluirBaseHistorico` (title="Adicionar Base") para a base entrar na tabela "Bases Cadastradas".

**Fix aplicado** (commits `4f9d85c` → `f73beb2`): garantia em `_configurar_parametros_verba` que sempre adiciona ÚLTIMA REMUNERAÇÃO via `_selecionar_base_historicos` (idempotente — checa duplicatas) ANTES do loop de bases custom. `tipoDaBaseTabelada` é SELECT (não radio).

---

## E03 — Click em listagem JSF abre verba errada
**Sintoma**: Configurando "HORAS EXTRAS 50%" mas o agente abre Parâmetros de outra verba (DIFERENÇA SALARIAL ou MULTA 477).

**Causa raiz**: O JS evaluate iterava `document.querySelectorAll('tr')` que pega o `<tr>` PAI de toda a tabela; qualquer kw casa no textContent dele e o primeiro link `[id$=":j_id558"]` é o da 1ª linha. Ordem das verbas na listagem **não é alfabética**.

**Fix aplicado** (commit `4759c39`): match por **NOME EXATO** (3 estratégias em cascata: exato → inclusão mútua → palavras-chave). Click via Playwright `page.locator(id).click()` (não JS `link.click()`) para disparar o postback A4J.AJAX.Submit.

**Prevenção**: usar match por nome canônico ao identificar verbas, nunca por índice posicional.

---

## E04 — URL `verbas-para-calculo.jsf` não existe
**Sintoma**: Após salvar Lançamento Expresso, agente não conseguia voltar para a listagem de Verbas. `_configurar_parametros_verba` nem encontrava os links Parâmetros.

**Causa raiz**: O código tinha checagem `if "verbas-para-calculo" not in self._page.url` e fallback `goto verbas-para-calculo.jsf` — mas essa URL **não existe** no PJE-Calc 2.15.1. A URL correta é `verba-calculo.jsf` (singular).

**Fix aplicado** (commit `7829ba6`): aceitar ambas as formas; URL direta no fallback usa `verba-calculo.jsf`.

---

## E05 — Click em "Parâmetros" abria "Ocorrências"
**Sintoma**: Form de Parâmetros não tinha tipoDaBaseTabelada/baseHistoricos.

**Causa raiz**: Ordem dos ícones na linha JSF é **Parâmetros (1º) → Ocorrências (2º) → Excluir (3º)**. O fallback antigo clicava `iconLinks[1]` (= Ocorrências).

**Fix aplicado** (commit `8d593ca`): priorizar `title="Parâmetros da Verba"`. Último recurso usa `iconLinks[0]` (PRIMEIRO).

---

## E06 — Reflexa não encontra Principal (`nome_pjecalc` ≠ `nome_sentenca`)
**Sintoma**: Reflexa configurada via Manual ("13º sobre Estabilidade") não conseguia vincular a Principal correspondente porque apontava para "INDENIZAÇÃO SUBSTITUTIVA DA ESTABILIDADE ACIDENTÁRIA" (`nome_sentenca`), mas no PJE-Calc a verba foi salva como "INDENIZAÇÃO POR DANO MATERIAL" (`nome_pjecalc` Expresso).

**Causa raiz**: Estabilidade gestante/acidentária usa Expresso "INDENIZAÇÃO POR DANO MATERIAL" (truque do vídeo Alacid Guerreiro). O agente buscava na listagem pelo `nome_sentenca` original — não casava.

**Fix aplicado** (commit `9ef6be7`):
- Validador aceita `verba_principal_ref` casando com qualquer dos 3 nomes (nome_pjecalc, nome_pjecalc_unico, nome_sentenca).
- Playwright resolve automaticamente: se `verba_principal_ref` casa nome_sentenca da Principal, substitui pelo nome_pjecalc real antes de procurar no select.
- Suporte a `nome_pjecalc_unico` para casos de colisão (2+ Principais com mesmo nome_pjecalc).

**Prevenção** (no Projeto Claude externo): seção 4.1 do prompt explica `nome_sentenca` vs `nome_pjecalc`. Reflexa **deve** usar `nome_pjecalc`.

---

## E07 — `dataTerminoCalculo` curta demais (verbas pós-rescisão)
**Sintoma**: Liquidação bloqueia com:
- *"As ocorrências da verba X devem estar contidas no período estabelecido na página parâmetro da verba"*
- *"As ocorrências do FGTS iniciam/terminam em data diferente da Data Final da limitação do Cálculo"*

**Causa raiz**: `dataTerminoCalculo` igual à data da rescisão. Verbas com período pós-contratual (Estabilidade Gestante até parto+5m, Acidentária até alta+12m, CIPA, salário-maternidade pós-rescisão, dispensa discriminatória) caem fora do limite.

**Fix aplicado** (commit `ec1a86a`):
- Auto-ajuste: antes de salvar Dados do Cálculo, calcula `MAX(periodo_fim)` de todas as verbas; se maior que `dataTerminoCalculo` informado → ajusta automaticamente.
- Log: `"AJUSTE auto dataTerminoCalculo: X → Y (provavelmente indenização de estabilidade)"`.

**Prevenção** (Projeto Claude): seção 1.1 do prompt orienta calcular fim do período estabilitário e marcar `data_termino_calculo` ≥ `MAX(periodo_fim)`.

---

## E08 — `ocorrencia ≠ Mensal` com período pós-rescisão
**Sintoma**: Form Manual rejeita salvar com:
> *"A data final não pode ser maior que a data demissão, para o caso de 'Ocorrências de Pagamento' diferentes de Mensal"*

**Caso real**: REMUNERAÇÃO EM DOBRO POR DISPENSA DISCRIMINATÓRIA classificada como `Desligamento` (LLM viu "DISPENSA"), mas pagamento Lei 9.029/95 art. 4º é **mensal** durante o período.

**Causa raiz**: Classificador automático (LLM no agente) interpretou erroneamente. PJE-Calc só permite `periodoFinal > data_demissao` quando ocorrência é Mensal.

**Verbas afetadas** (todas devem usar `Mensal`):
- REMUNERAÇÃO EM DOBRO POR DISPENSA DISCRIMINATÓRIA
- INDENIZAÇÃO SUBSTITUTIVA DA ESTABILIDADE GESTANTE
- INDENIZAÇÃO SUBSTITUTIVA DA ESTABILIDADE ACIDENTÁRIA
- SALÁRIO-MATERNIDADE PÓS-RESCISÃO
- INDENIZAÇÃO POR ESTABILIDADE CIPA / SINDICAL

**Fix aplicado** (commit `5d81a1f`):
- Validador da Prévia: erro bloqueante se `ocorrencia ≠ Mensal` AND `periodo_fim > data_demissao`.
- Auto-fix no Playwright: detecta inconsistência e força `ocorr_enum = MENSAL` antes de selecionar o radio. Log: `"AUTO-FIX ocorrência: X incompatível com periodo_fim Y > demissão Z. Forçando MENSAL"`.

---

## E09 — Multiplicador alterado depois de gerar ocorrências
**Sintoma**: Liquidador alerta:
> *"O parâmetro Multiplicador foi alterado após a geração das ocorrências da verba X"*

**Causa raiz**: Agente preenche periodoInicial/Final → clica "Gerar Ocorrências" → DEPOIS preenche multiplicador. As ocorrências geradas usam o multiplicador antigo (default).

**Verbas afetadas**: HE 50%, COMISSÃO, MULTA 477, INDEN ADICIONAL, qualquer verba com multiplicador customizado.

**Fix pendente** (não implementado ainda): inverter ordem — preencher multiplicador ANTES de Gerar Ocorrências. OU: chamar `Regerar Ocorrências` depois de mudar o multiplicador.

**Prevenção temporária**: usar valores default da verba Expresso quando possível.

---

## E10 — HORAS EXTRAS 50% com `quantidade=0` em todas ocorrências
**Sintoma**: Liquidador alerta:
> *"Todas as ocorrências da verba HORAS EXTRAS 50% foram salvas com quantidade igual a zero"*

**Causa raiz**: Agente preenche Parâmetros mas não preenche `termoQuant` em cada linha mensal da grade Ocorrências (precisa do nº de horas extras por mês — ex: 30h/mês, 60h/mês, etc.).

**Fix pendente** (não implementado): após gerar ocorrências, iterar a grade e preencher `formulario:listagem:N:termoQuant` com o valor mensal.

**Prevenção temporária**: valor de horas extras pode ser editado manualmente após a automação.

---

## E11 — INDENIZAÇÃO POR DANO MORAL/MATERIAL sem `valor_devido` ≠ 0
**Sintoma**: Liquidador alerta:
> *"Para apurar a verba informada X deve existir pelo menos uma ocorrência com valor devido ou valor pago diferente de zero"*

**Causa raiz**: Indenizações em modo "Calculado" precisam de `valorParaBaseDeCalculo` ou `valorInformado` em cada linha mensal de Ocorrências. O agente preenche os Parâmetros mas não a grade.

**Fix pendente**: ao salvar Parâmetros de uma indenização Calculada com valor mensal, preencher cada linha da grade Ocorrências com `valor_mensal × proporção_dias`.

---

## E12 — Histórico Salarial sem valor para Contribuição Social
**Sintoma**: Liquidador alerta para cada histórico:
> *"O Histórico Salarial X não possui valor cadastrado para todas as ocorrências da Contribuição Social sobre Salários Devidos"*

**Causa raiz**: Aba **Contribuição Social** precisa ter os mesmos históricos vinculados, com valores. Agente preenche o histórico em "Histórico Salarial" mas não amarra na CS.

**Fix pendente**: navegação para Contribuição Social → vincular cada histórico → preencher mesmo valor mensal.

---

## E13 — FGTS com datas fora do período do cálculo
**Sintoma**: Liquidador alerta:
> *"As ocorrências do FGTS iniciam em data diferente da Data Inicial e/ou terminam em data diferente da Data Final da limitação do Cálculo"*

**Causa raiz**: Aba FGTS gera ocorrências baseadas em `dataInicioCalculo`/`dataTerminoCalculo`. Se essas datas mudaram entre o preenchimento do FGTS e a Liquidação (ex: auto-ajuste E07 atrasado), o FGTS fica com período antigo.

**Fix correlato**: o E07 corrige a causa raiz — se `dataTerminoCalculo` for setada corretamente DESDE o início, FGTS gera com período correto.

---

## Lista de erros pendentes (priorizados)

| # | Erro | Prioridade | Status |
|---|---|---|---|
| E01 | hashCodeLiquidacao=null | Crítica | ✅ Resolvido (8e019ca) |
| E02 | Falta histórico salarial | Crítica | ✅ Resolvido (f73beb2) |
| E03 | Click em verba errada | Crítica | ✅ Resolvido (4759c39) |
| E04 | URL plural inexistente | Crítica | ✅ Resolvido (7829ba6) |
| E05 | Click em Ocorrências em vez de Parâmetros | Crítica | ✅ Resolvido (8d593ca) |
| E06 | Reflexa nome_sentenca vs nome_pjecalc | Alta | ✅ Resolvido (9ef6be7) |
| E07 | dataTerminoCalculo curta | Alta | ✅ Resolvido (ec1a86a) |
| E08 | Ocorrência ≠ Mensal pós-rescisão | Alta | ✅ Resolvido (5d81a1f) |
| E09 | Multiplicador alterado após gerar ocorrências | Média | ✅ Resolvido (d4c0e7a) |
| E10 | HE 50% qtd=0 nas ocorrências | Média | ✅ Resolvido (d4c0e7a) |
| E11 | Indenização Calculada sem valor na grade | Média | ✅ Resolvido (d4c0e7a) |
| E12 | Histórico não vinculado à CS | Média | ✅ Resolvido (11c0fe9) |
| E13 | FGTS datas fora do cálculo | Baixa (deriva de E07) | ✅ Resolvido (deriva) |
