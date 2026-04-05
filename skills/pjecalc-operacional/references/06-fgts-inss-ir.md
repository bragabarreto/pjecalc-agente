# FGTS, Contribuicao Social (INSS) e Imposto de Renda -- Guia Operacional
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

---

## 1. Visao Geral dos Modulos de Encargos (Secao 1.8)

Os modulos de FGTS e Contribuicao Social sao paginas proprias, com logica propria de ocorrencias e revisao. O manual deve ensinar a maquina a nao trata-los como reflexos invisiveis. Eles podem exigir edicao mensal, revisao de parametros, regeracao e conferencia por relatorio [3] [4] [11].

| Modulo | Regra de operacao | Origem |
|---|---|---|
| FGTS | Preencher parametros, revisar ocorrencias mensais, salvar e regerar quando necessario | [Aula 3] |
| FGTS nao depositado | Marcar **Recolher** quando o valor for obrigacao de deposito e nao credito liquido ao reclamante | [Video complementar -- FGTS nao depositado] |
| Contribuicao Social | Parametrizar bases, abrir ocorrencias, editar e regerar conforme mudancas | [Aula 3] |
| Previdencia Privada | So liquidar se pelo menos uma verba tiver a incidencia correspondente marcada | [Aula 3] [Aula 4] |
| Pensao Alimenticia | Aplicar apenas sobre as verbas previamente marcadas com essa incidencia | [Aula 3] |

---

## 2. FGTS -- Configuracao Completa (Secao 4)

A pagina de FGTS deve ser tratada como modulo autonomo, dotado de parametros e ocorrencias mensais proprias. O corpus principal ja permitia afirmar isso. O video complementar sobre FGTS nao depositado acrescentou um cenario operacional completo, em que o sistema calcula o valor fundiario, mas o desloca do quadro de credito liquido do reclamante para uma secao propria de depositos a recolher [3] [4] [11].

| Item exigido no anexo | Conteudo consolidado | Origem |
|---|---|---|
| Pagina FGTS | Existe pagina propria com bloco de parametros e grade de ocorrencias mensais | [Aula 3] |
| Ocorrencias do FGTS | Podem ser editadas para informar valores ja recolhidos ou diferencas | [Aula 3] |
| Depositos ja recolhidos | Informados mes a mes para abatimento quando o calculo tratar de diferencas | [Aula 3] |
| Salvar | Comando explicitamente mostrado/narrado | [Aula 3] |
| Regerar | Necessario quando alteracoes estruturais afetarem o periodo ou a base | [Aula 3] [Aula 4] |
| Checkbox **Recolher** | Deve ser marcado quando o FGTS e obrigacao de deposito e nao pagamento em pecunia | [Video complementar -- FGTS nao depositado] |
| Multa de 40% -- passo a passo | Checkbox `multa` → **AGUARDAR AJAX** → `tipoDoValorDaMulta`=CALCULADA → AJAX → `multaDoFgts`=QUARENTA_POR_CENTO. Sem AJAX wait, radios ficam disabled. `multaDoArtigo467` depende de `multa` marcado. | [Confirmado por inspeção DOM fgts.xhtml] |
| 13o no FGTS -- passo a passo | **[NAO COBERTO NAS AULAS]** | [NAO COBERTO NAS AULAS] |

### 2.1 Roteiro Operacional -- FGTS Nao Depositado

A rotina operacional do cenario de FGTS nao depositado deve ser ensinada como fluxo fechado:

1. Primeiro, a maquina preenche os **Dados do Calculo**.
2. Depois, cria uma **base historica especifica**, gera a grade mensal e deixa **FGTS Recolhido** desmarcado quando nada foi depositado.
3. Em seguida, entra na aba **FGTS** e marca **Recolher**.
4. Por fim, liquida e confere o resumo: o valor positivo do FGTS deve ser imediatamente compensado pela linha negativa **DEDUCAO DE FGTS**, e o total correspondente deve reaparecer em uma secao propria de **DEPOSITOS FGTS**, com liquido do reclamante zerado quanto a essa rubrica [11].

---

## 3. Contribuicao Social (INSS) -- Parametrizacao Executavel (Secao 5)

A **Contribuicao Social** deve ser ensinada a maquina como um modulo que converte parametros juridicos e previdenciarios em **ocorrencias mensais editaveis**. A demonstracao das aulas deixa claro que o sistema distingue **salarios devidos** e **salarios pagos**, admite parametrizacao de aliquotas e exige, em determinadas hipoteses, acesso a area de ocorrencias seguido de **regeracao** para consolidar o cenario efetivamente pretendido [3].

| Componente | Regra operacional ensinavel | Origem |
|---|---|---|
| Base do segurado | Definir se a apuracao sera sobre salarios devidos, pagos ou ambos, conforme o caso demonstrado | [Aula 3] |
| Base do empregador | Parametrizar aliquota por atividade economica, por periodo ou de forma fixa | [Aula 3] |
| Cobranca do reclamante | Decidir se a cota do empregado sera cobrada ou nao | [Aula 3] |
| Ocorrencias | Acessar a area propria para editar as bases mensais geradas | [Aula 3] |
| Alteracao em lote | Usar quando a modificacao atingir varias competencias de forma uniforme | [Aula 3] |
| Regerar | Executar apos mudanca estrutural relevante nos parametros | [Aula 3] [Aula 4] |

### 3.1 Passo a Passo Executavel -- Contribuicao Social

O comportamento que a maquina deve aprender e o seguinte: primeiro parametriza-se a regra previdenciaria. Depois inspecionam-se as **ocorrencias** geradas. Em seguida, editam-se as bases se o caso concreto exigir ajuste fino. Por fim, salva-se e liquida-se novamente para validar se a contribuicao apareceu coerentemente no resumo do calculo. A maquina nao deve presumir que a parametrizacao superior, sozinha, resolve todos os meses; as aulas mostram precisamente o contrario, isto e, a necessidade de revisao das competencias geradas [3].

| Passo operacional | Acao executavel | Verificacao esperada |
|---|---|---|
| 1 | Entrar em **Contribuicao Social** | Pagina previdenciaria ativa |
| 2 | Definir bases e aliquotas | Regra geral de incidencia montada |
| 3 | Acessar **Ocorrencias** | Grade mensal disponivel para revisao |
| 4 | Editar por lote ou linha a linha | Competencias aderentes ao caso concreto |
| 5 | Regerar, se necessario | Parametros-base refletidos nas ocorrencias |
| 6 | Liquidar e revisar o resumo | Encargo previdenciario consistente |

---

## 4. Imposto de Renda (IR)

O Imposto de Renda e listado no fluxo macro como parte do passo 8 junto com FGTS, CS, Previdencia Privada e Pensao: "Definir incidencias, retencoes e modulos acessorios" [1] [2] [3] [4].

**[NAO COBERTO NAS AULAS COM SUFICIENCIA OPERACIONAL]** -- O corpus analisado (Aulas 1-4 e videos complementares) nao demonstrou com passo a passo exaustivo a configuracao do modulo de Imposto de Renda no PJe-Calc. O IR e mencionado como modulo acessorio que deve ser configurado apos as verbas e bases ja existirem, mas os detalhes operacionais de preenchimento (tela, campos, ocorrencias) nao foram cobertos com seguranca suficiente para gerar roteiro executavel.

### 4.1 Regras Conhecidas sobre IR

- O IR faz parte do conjunto de encargos que so devem ser configurados **apos verbas e bases ja existirem** (Passo 8 do fluxo macro).
- A incidencia de IR e marcada por verba, da mesma forma que FGTS e CS.
- O modulo de IR deve ser revisado antes da liquidacao, seguindo a mesma logica de parametrizacao + ocorrencias + regeracao dos demais encargos.

---

## 5. Regras de Dependencia Criticas

| Dependencia | Regra pratica | Origem |
|---|---|---|
| Historico Salarial -> FGTS/CS | Nao configurar encargos sem historico salarial coerente | [Aula 1] [Aula 4] |
| Verbas -> Incidencias | As verbas devem ter as incidencias de FGTS, CS, IR e Pensao marcadas antes de configurar os modulos | [Aula 2] [Aula 3] |
| Alteracao estrutural -> Regerar | Mudancas de periodo, base ou parametro exigem regeracao dos modulos de encargos | [Aula 3] [Aula 4] |
| Liquidacao -> Validacao | O relatorio final deve ser lido para confirmar se FGTS, CS e IR foram apurados corretamente | [Aula 4] [Video complementar -- FGTS nao depositado] |
