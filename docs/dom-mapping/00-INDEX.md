# DOM Mapping PJE-Calc Institucional — Índice

**Versão PJE-Calc auditada**: 2.15.1  
**Data da auditoria**: 2026-05-04  
**Método**: inspeção direta via Chrome MCP em `pje.trt7.jus.br/pjecalc`  
**Cálculo de teste**: 262818 / 0000369-57.2026.5.07.0003

## Documentos

| # | Arquivo | Conteúdo |
|---|---|---|
| 01 | [verba-manual-novo.md](01-verba-manual-novo.md) | Lançamento Manual de Verba — formulário completo "Dados de Verba" com 30+ campos. Comportamento dinâmico em Valor=INFORMADO. |
| 02 | [verba-expresso.md](02-verba-expresso.md) | Lançamento Expresso — rol completo de 54 verbas + estratégia de classificação (direto/adaptado/manual). |
| 03 | [ocorrencias-verba.md](03-ocorrencias-verba.md) | Página Ocorrências da Verba — Alteração em Lote + tabela mensal (termoQuant, valorDevido, valorPago). |
| 04 | [reflexos-painel.md](04-reflexos-painel.md) | Painel de Reflexos pré-cadastrados na listagem de Verbas (`listaReflexo:M:ativo`). |
| 05 | [historico-salarial.md](05-historico-salarial.md) | Cadastro de Histórico Salarial — nome, parcela, incidências, competências, valor. |

## URLs principais

```
/pjecalc/pages/calculo/calculo.jsf?conversationId=N      → Dados do Cálculo
/pjecalc/pages/calculo/historico-salarial.jsf?...        → Histórico Salarial
/pjecalc/pages/calculo/verba/verba-calculo.jsf?...       → Listagem de Verbas (com Manual/Expresso/Regerar)
/pjecalc/pages/calculo/verba/verbas-para-calculo.jsf?... → Lançamento Expresso (checkboxes 54 verbas)
/pjecalc/pages/calculo/parametrizar-ocorrencia.jsf?...   → Ocorrências da Verba (tabela mensal)
```

## Padrões de ID JSF observados

| Padrão | Significado |
|---|---|
| `formulario:CAMPO` | campo direto do form principal (ex: `formulario:descricao`) |
| `formulario:CAMPO:N` | radio button com index (ex: `formulario:valor:0` = CALCULADO) |
| `formulario:listagem:N:CAMPO` | linha N de uma tabela na listagem |
| `formulario:listagem:N:listaReflexo:M:CAMPO` | reflexo M dentro da verba N |
| `formulario:j_id82:R:j_id84:C:CAMPO` | grid 2D dinâmico (Expresso) — buscar pelo `[id$=':selecionada']` |

## Mudanças necessárias na arquitetura do agente

### 1. Schema da prévia (Fase 2)
A prévia precisa replicar **toda** a estrutura DOM, separando por seções:
- `dados_processo` (já existe)
- `parametros_calculo` (já existe)
- `historico_salarial` (já existe — REVISAR para múltiplas entradas evolutivas)
- `verbas`: cada verba com **parametros completos** (~25 campos)
- `reflexos` vinculados a cada verba

### 2. Prompt de extração (Fase 3)
Forçar extração de:
- `valor_devido_mensal` quando o valor é informado pela sentença (indenizações)
- `quantidade_mensal_horas` para HE/intervalos
- `caracteristica` correta (COMUM/13o/Aviso/Férias)
- `estrategia_preenchimento` (expresso_direto/adaptado/manual)
- `expresso_alvo` (nome exato do rol)

### 3. HTML da prévia (Fase 4)
Card por verba expandível com TODOS os campos editáveis. Validador inline.

### 4. Automação (Fase 5)
Eliminar inferência. Ler tudo da prévia. Quando `valor=INFORMADO`, preencher
`formulario:valorInformadoDoDevido` na página Parâmetros. Quando há indenização
de período pós-contrato, replicar via `formulario:devido` na Alteração em Lote.

## Pontos críticos para a Fase 5

1. **Histórico Salarial deve cobrir todo o período do cálculo** (não só até a rescisão)
2. **Valor=INFORMADO requer `valorInformadoDoDevido`** — campo dinâmico que aparece
   APENAS quando o radio `valor:1` é selecionado
3. **Reflexos preferencialmente via `listaReflexo:M:ativo`** no painel da verba
   principal — só usar Manual quando não há checkbox disponível
4. **Característica determina ocorrência default**: COMUM→MENSAL, 13o→DEZEMBRO,
   AVISO→DESLIGAMENTO, FERIAS→PERIODO_AQUISITIVO
5. **Após qualquer mudança em parâmetros, Regerar (Sobrescrever)** as ocorrências —
   senão Liquidar reclama "Multiplicador alterado após geração"
