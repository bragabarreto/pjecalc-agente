# DOM Mapping PJE-Calc Institucional — Índice Final

**Versão**: PJE-Calc 2.15.1  
**Auditado em**: 2026-05-04 via Chrome MCP em `pje.trt7.jus.br/pjecalc`  
**Cálculo de teste**: 262818 / 0000369-57.2026.5.07.0003

## Documentos

| # | Arquivo | Conteúdo |
|---|---|---|
| 00 | INDEX.md (este) | Índice geral + URLs + padrões JSF |
| 01 | [verba-manual-novo.md](01-verba-manual-novo.md) | Lançamento Manual de Verba — formulário "Dados de Verba" + dinâmica Valor=INFORMADO |
| 02 | [verba-expresso.md](02-verba-expresso.md) | Lançamento Expresso — 54 verbas |
| 03 | [ocorrencias-verba.md](03-ocorrencias-verba.md) | Ocorrências da Verba — Alteração em Lote + tabela mensal |
| 04 | [reflexos-painel.md](04-reflexos-painel.md) | Painel de Reflexos pré-cadastrados |
| 05 | [historico-salarial.md](05-historico-salarial.md) | Histórico Salarial — modo INFORMADO |
| 06 | [ERRATA-FASE1.md](06-ERRATA-FASE1.md) | Erros e omissões corrigidos após verificações empíricas |
| 07 | [parametros-ocorrencias-reflexos.md](07-parametros-ocorrencias-reflexos.md) | Parâmetros do REFLEXO + sub-seção Reflexos em Ocorrências |
| 08 | [paginas-secundarias.md](08-paginas-secundarias.md) | Dados do Cálculo, Cartão de Ponto, Faltas, Férias, FGTS+parametrizar-fgts |
| 09 | [paginas-completas.md](09-paginas-completas.md) | INSS, IRPF, Honorários, Custas, Correção/Juros, Liquidação, Hist CALCULADO + Etapa 2 (5 opcionais) |

## URLs principais

```
/pjecalc/pages/principal.jsf                                         → Home
/pjecalc/pages/calculo/calculo.jsf?conversationId=N                  → Dados do Cálculo (2 tabs)
/pjecalc/pages/calculo/historico-salarial.jsf?...                    → Histórico Salarial
/pjecalc/pages/calculo/falta.jsf?...                                 → Faltas
/pjecalc/pages/calculo/ferias.jsf?...                                → Férias
/pjecalc/pages/cartaodeponto/apuracao-cartaodeponto.jsf?...          → Cartão de Ponto
/pjecalc/pages/calculo/verba/verba-calculo.jsf?...                   → Listagem de Verbas (Manual/Expresso/Regerar)
/pjecalc/pages/calculo/verba/verbas-para-calculo.jsf?...             → Lançamento Expresso (54 checkboxes)
/pjecalc/pages/calculo/parametrizar-ocorrencia.jsf?...               → Ocorrências da Verba
/pjecalc/pages/calculo/fgts.jsf?...                                  → FGTS
/pjecalc/pages/calculo/parametrizar-fgts.jsf?...                     → Parametrizar FGTS
/pjecalc/pages/calculo/inss/inss.jsf?...                             → Contribuição Social (INSS)
/pjecalc/pages/calculo/inss/parametrizar-inss.jsf?...                → Parametrizar INSS (Recuperar Devidos)
/pjecalc/pages/calculo/irpf.jsf?...                                  → Imposto de Renda
/pjecalc/pages/calculo/honorarios.jsf?...                            → Honorários
/pjecalc/pages/calculo/custas-judiciais.jsf?...                      → Custas Judiciais
/pjecalc/pages/calculo/parametros-atualizacao/parametros-atualizacao.jsf?... → Correção, Juros e Multa
/pjecalc/pages/calculo/liquidacao.jsf?...                            → Operações > Liquidar
/pjecalc/pages/calculo/multas-indenizacoes.jsf?...                   → Multas e Indenizações
/pjecalc/pages/calculo/salario-familia.jsf?...                       → Salário-Família
/pjecalc/pages/calculo/seguro-desemprego.jsf?...                     → Seguro-Desemprego
/pjecalc/pages/calculo/previdencia-privada.jsf?...                   → Previdência Privada
/pjecalc/pages/calculo/pensao-alimenticia.jsf?...                    → Pensão Alimentícia
```

## Padrão de IDs do menu lateral

```
li#calculo_dados_calculo         → Dados do Cálculo
li#calculo_faltas                → Faltas
li#calculo_ferias                → Férias
li#calculo_historico_salarial    → Histórico Salarial
li#calculo_verbas                → Verbas
li#calculo_cartao_de_ponto       → Cartão de Ponto
li#calculo_salario_familia       → Salário-Família
li#calculo_seguro_desemprego     → Seguro-Desemprego
li#calculo_fgts                  → FGTS
li#calculo_inss                  → Contribuição Social
li#calculo_previdencia_privada   → Previdência Privada
li#calculo_pensao_alimenticia    → Pensão Alimentícia
li#calculo_irpf                  → Imposto de Renda
li#calculo_multas_e_indenizacoes → Multas e Indenizações
li#calculo_honorarios            → Honorários
li#calculo_custas_judiciais      → Custas Judiciais
li#calculo_correcao_juros_multa  → Correção, Juros e Multa
```

**Para a automação**: `document.getElementById('li_calculo_X').querySelector('a').click()`
é mais robusto que click via coordenadas.

## Padrões de ID JSF observados

| Padrão | Significado |
|---|---|
| `formulario:CAMPO` | Campo direto do form principal |
| `formulario:CAMPO:N` | Radio button com index (ex: `formulario:valor:0`=CALCULADO, `:1`=INFORMADO) |
| `formulario:listagem:N:CAMPO` | Linha N de uma tabela |
| `formulario:listagem:N:listaReflexo:M:ATIVO` | Reflexo M dentro da verba N |
| `formulario:reflexos:N:listagem:M:CAMPO` | Sub-tabela de Ocorrências do reflexo |
| `formulario:j_id82:R:j_id84:C:selecionada` | Grid 2D dinâmico (Expresso) — buscar por `[id$=':selecionada']` |

## Cobertura final

✅ **17 páginas mapeadas** (todas as relevantes para refatoração da prévia/automação):
- 12 alta prioridade (Etapa 1)
- 5 média prioridade (Etapa 2)
- + 6 sub-páginas (parametrizar-fgts, parametrizar-inss, parametrizar-ocorrencia, etc.)
- + verbas (Manual/Expresso/Reflexos com Parâmetros próprios)

⚠️ **Não mapeadas** (intencional — fora do escopo):
- Tabelas administrativas (Salário Mínimo, Pisos Salariais)
- Operações de fim de fluxo (Imprimir, Fechar, Excluir)
- Atualização de cálculos (fluxo distinto da liquidação inicial)
