# DOM Mapping — Lançamento Manual de Verba

**URL**: `/pjecalc/pages/calculo/verba/verba-calculo.jsf` (após click em `formulario:incluir`)  
**Caminho**: Cálculo > Verbas > Novo  
**Versão PJE-Calc**: 2.15.1

## Botões da Listagem (verba-calculo.jsf — listagem)
| Função | ID | Tag | Value |
|---|---|---|---|
| Manual (novo) | `formulario:incluir` | input | "Manual" |
| Expresso | `formulario:lancamentoExpresso` | input | "Expresso" |
| Regerar | `formulario:regerarOcorrencias` | input | "Regerar" |
| Linha verba — Parâmetros | `formulario:listagem:N:j_id558` | a | title="Parâmetros da Verba" |
| Linha verba — Ocorrências | `formulario:listagem:N:j_id559` | a | title="Ocorrências da Verba" |
| Regerar — Manter alterações | radio `tipoRegeracao` value="true" | radio | "Manter" |
| Regerar — Sobrescrever | radio `tipoRegeracao` value="false" | radio | "Sobrescrever" |

## Formulário "Dados de Verba" (Novo Manual)

### Identificação
| Campo Prévia | DOM ID | Tipo | Valores | Obrigatório |
|---|---|---|---|---|
| `nome` | `formulario:descricao` | text | string | ✅ |
| `assunto_cnj_codigo` | `formulario:codigoAssuntosCnj` | hidden | número CNJ | ✅ |
| `assunto_cnj_label` | `formulario:assuntosCnj` | text | label visível | ✅ |

### Parcela
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `parcela` | `formulario:tipoVariacaoDaParcela:0/1` | radio | FIXA / VARIAVEL |

### Valor
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `valor` | `formulario:valor:0/1` | radio | CALCULADO / INFORMADO |

⚠️ **Quando Valor=INFORMADO**: a fórmula (Base/Divisor/Multiplicador/Quantidade) NÃO é
usada no cálculo. O valor é informado por OCORRÊNCIA (campo `valorDevido` na tabela
de Ocorrências da Verba). Por isso é OBRIGATÓRIO ter `valor_devido_mensal` na prévia
para que a automação preencha cada linha da tabela.

### Incidência (checkboxes — múltipla escolha)
| Campo Prévia | DOM ID | Tipo |
|---|---|---|
| `incidencia_irpf` | `formulario:irpf` | checkbox |
| `incidencia_cs` (INSS) | `formulario:inss` | checkbox |
| `incidencia_fgts` | `formulario:fgts` | checkbox |
| `incidencia_prev_privada` | `formulario:previdenciaPrivada` | checkbox |
| `incidencia_pensao` | `formulario:pensaoAlimenticia` | checkbox |

### Característica & Ocorrência de Pagamento
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `caracteristica` | `formulario:caracteristicaVerba:0..3` | radio | COMUM, DECIMO_TERCEIRO_SALARIO, AVISO_PREVIO, FERIAS |
| `ocorrencia` | `formulario:ocorrenciaPagto:0..3` | radio | DESLIGAMENTO, DEZEMBRO, MENSAL, PERIODO_AQUISITIVO |

⚠️ **Regra de derivação automática (PJE-Calc)**: ao selecionar Característica:
- COMUM → ocorrência default = MENSAL
- DECIMO_TERCEIRO_SALARIO → ocorrência default = DEZEMBRO
- AVISO_PREVIO → ocorrência default = DESLIGAMENTO
- FERIAS → ocorrência default = PERIODO_AQUISITIVO

### Juros / Súmula 439 TST
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `aplicar_sumula_439` | `formulario:ocorrenciaAjuizamento:0/1` | radio | OCORRENCIAS_VENCIDAS_E_VINCENDAS (Sim) / OCORRENCIAS_VENCIDAS (Não) |

### Tipo & Reflexo
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `tipo` | `formulario:tipoDeVerba:0/1` | radio | PRINCIPAL / REFLEXO |
| `gerar_reflexa` | `formulario:geraReflexo:0/1` | radio | DEVIDO / DIFERENCA |
| `gerar_principal` | `formulario:gerarPrincipal:0/1` | radio | DEVIDO / DIFERENCA |
| `compor_principal` | `formulario:comporPrincipal:0/1` | radio | SIM / NAO |
| `zerar_valor_negativo` | `formulario:zeraValorNegativo` | checkbox | on |

### Período
| Campo | DOM ID | Tipo |
|---|---|---|
| `periodo_inicio` | `formulario:periodoInicialInputDate` | text DD/MM/YYYY |
| `periodo_fim` | `formulario:periodoFinalInputDate` | text DD/MM/YYYY |

### Exclusões
| Campo | DOM ID | Tipo |
|---|---|---|
| `excluir_faltas_just` | `formulario:excluirFaltaJustificada` | checkbox |
| `excluir_faltas_njust` | `formulario:excluirFaltaNaoJustificada` | checkbox |
| `excluir_ferias_gozadas` | `formulario:excluirFeriasGozadas` | checkbox |
| `dobrar_valor_devido` | `formulario:dobraValorDevido` | checkbox |

### Base de Cálculo (Fórmula)
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `base_tabelada` | `formulario:tipoDaBaseTabelada` | select | (HISTORICO_SALARIAL, MAIOR_REMUNERACAO, ULTIMA_REMUNERACAO, INTEGRAL, etc.) |
| `proporcionalizar_base` | `formulario:aplicarProporcionalidadeABase` | checkbox |
| `base_verba_calculo` | `formulario:baseVerbaDeCalculo` | select | (referência a outra verba) |
| `integralizar_base` | `formulario:integralizarBase` | select | (SIM/NAO) |

### Divisor
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `divisor_tipo` | `formulario:tipoDeDivisor:0..3` | radio | OUTRO_VALOR, CARGA_HORARIA, DIAS_UTEIS, IMPORTADA_DO_CARTAO |
| `divisor_valor` | `formulario:outroValorDoDivisor` | text | número |

### Multiplicador
| Campo | DOM ID | Tipo |
|---|---|---|
| `multiplicador` | `formulario:outroValorDoMultiplicador` | text número |

### Quantidade
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `quantidade_tipo` | `formulario:tipoDaQuantidade:0..2` | radio | INFORMADA, IMPORTADA_DO_CALENDARIO, IMPORTADA_DO_CARTAO |
| `quantidade_valor` | `formulario:valorInformadoDaQuantidade` | text |
| `proporcionalizar_quantidade` | `formulario:aplicarProporcionalidadeAQuantidade` | checkbox |

### Valor Pago (já pago)
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| `valor_pago_tipo` | `formulario:tipoDoValorPago:0/1` | radio | INFORMADO / CALCULADO |
| `valor_pago_valor` | `formulario:valorInformadoPago` | text |
| `proporcionalizar_valor_pago` | `formulario:aplicarProporcionalidadeValorPago` | checkbox |

### Outros
| Campo | DOM ID | Tipo |
|---|---|---|
| `comentarios` | `formulario:comentarios` | textarea |

### Botões
| Função | DOM ID |
|---|---|
| Salvar | `formulario:salvar` |
| Cancelar | `formulario:cancelar` |

## ⚠ Comportamento dinâmico — Valor=INFORMADO

Quando o radio `formulario:valor:1` (INFORMADO) é selecionado, o formulário muda:

**Some** (não renderiza):
- `tipoDeVerba` (radio Principal/Reflexa)
- Toda a seção Fórmula: `tipoDaBaseTabelada`, `aplicarProporcionalidadeABase`,
  `baseVerbaDeCalculo`, `integralizarBase`, `tipoDeDivisor`,
  `outroValorDoDivisor`, `outroValorDoMultiplicador`, `tipoDaQuantidade`,
  `valorInformadoDaQuantidade`, `aplicarProporcionalidadeAQuantidade`
- `dobraValorDevido`

**Aparece** (renderiza novo):
| Campo Prévia | DOM ID | Tipo | Descrição |
|---|---|---|---|
| `valor_devido_mensal` | `formulario:valorInformadoDoDevido` | text | Valor único replicado em todas ocorrências |
| `proporcionalizar_devido` | `formulario:aplicarProporcionalidadeAoValorDevido` | checkbox | Aplica proporcionalidade ao valor devido |

**Implicação para a prévia**:
Quando o usuário seleciona `valor=INFORMADO` no card da verba (caso típico de
**INDENIZAÇÃO POR DANO MORAL**, **INDENIZAÇÃO POR DANO MATERIAL**, **MULTAS**,
**INDENIZAÇÕES FIXAS**), o campo `valor_devido_mensal` torna-se OBRIGATÓRIO na
prévia. A automação preenche `valorInformadoDoDevido` com esse valor, e o
PJE-Calc replica em todas as ocorrências do período.

**Sem este valor preenchido**, a Liquidação rejeita com:
> "Para apurar a verba informada X deve existir pelo menos uma ocorrência
>  com valor devido ou valor pago diferente de zero."
