# DOM IDs Confirmados — PJE-Calc Cidadão v2.15.1

IDs verificados por inspeção DOM direta (console Firefox) em localhost:9257.
**Fonte de verdade** — não adivinhar IDs; se um campo não estiver aqui, inspecionar antes de implementar.

---

## parametros-do-calculo.jsf

| Campo | ID | Tipo | Valores / Notas |
|---|---|---|---|
| Estado | `formulario:estado` | select | Índices numéricos (CE=5, SP=24 etc.) |
| Município | `formulario:municipio` | select | Índices numéricos; texto em MAIÚSCULAS sem acento ("ACARAU" não "ACARAÚ"); primeiro option = noSelectionValue; recarregado por AJAX após estado |
| Admissão | `formulario:dataAdmissaoInputDate` | text | DD/MM/AAAA |
| Demissão | `formulario:dataDemissaoInputDate` | text | DD/MM/AAAA |
| Regime | `formulario:tipoDaBaseTabelada` | select | `INTEGRAL` / `PARCIAL` / `INTERMITENTE` |
| Carga Horária | `formulario:valorCargaHorariaPadrao` | text | |
| Maior Remuneração | `formulario:valorMaiorRemuneracao` | text | |
| Última Remuneração | `formulario:valorUltimaRemuneracao` | text | |
| Aviso Prévio | `formulario:apuracaoPrazoDoAvisoPrevio` | radio | `NAO_APURAR` / `APURACAO_CALCULADA` / `APURACAO_INFORMADA` |

**CNJ — campos individuais** (preenchidos separadamente):

| Campo | Seletor sugerido |
|---|---|
| Número sequencial (7 dígitos) | `[id$='numeroDoProcesso']` ou campo livre de texto |
| Dígito verificador | campo específico ao lado do número |
| Ano | campo específico |
| Segmento (fixo "5") | campo específico |
| Tribunal (região) | campo específico |
| Vara (4 dígitos) | campo específico |

---

## verba-calculo.jsf (Verbas — Novo/Alterar)

| Campo | ID | Tipo | Valores |
|---|---|---|---|
| Nome | `formulario:descricao` | text | |
| Parcela | `formulario:tipoVariacaoDaParcela` | radio | `FIXA` / `VARIAVEL` |
| Valor tipo | `formulario:valor` | radio | `CALCULADO` / `INFORMADO` |
| Característica | `formulario:caracteristicaVerba` | radio | `COMUM` / `DECIMO_TERCEIRO_SALARIO` / `AVISO_PREVIO` / `FERIAS` |
| Ocorrência | `formulario:ocorrenciaPagto` | radio | `DESLIGAMENTO` / `DEZEMBRO` / `MENSAL` / `PERIODO_AQUISITIVO` |
| Súmula 439 TST | `formulario:ocorrenciaAjuizamento` | radio | `OCORRENCIAS_VENCIDAS_E_VINCENDAS` (Sim) / `OCORRENCIAS_VENCIDAS` (Não) |
| Tipo verba | `formulario:tipoDeVerba` | radio | `PRINCIPAL` / `REFLEXO` |
| Compor Principal | `formulario:comporPrincipal` | radio | `SIM` / `NAO` |
| Gera Reflexo | `formulario:geraReflexo` | radio | `DEVIDO` / `DIFERENCA` |
| Gera Principal | `formulario:gerarPrincipal` | radio | `DEVIDO` / `DIFERENCA` |
| Base Cadastrada | `formulario:tipoDaBaseTabelada` | select | ver opções abaixo |
| Verba (reflexo) | `formulario:baseVerbaDeCalculo` | select | índices numéricos (0,1,2…) = posição da verba no cálculo |
| Integralizar | `formulario:integralizarBase` | select | `SIM` / `NAO` |
| Período De | `formulario:periodoInicialInputDate` | text | DD/MM/AAAA |
| Período Até | `formulario:periodoFinalInputDate` | text | DD/MM/AAAA |
| Multiplicador | `formulario:outroValorDoMultiplicador` | text | float decimal (ex: "0.50" para 50%) |
| Divisor tipo | `formulario:tipoDeDivisor` | radio | `OUTRO_VALOR` / `CARGA_HORARIA` / `DIAS_UTEIS` / `IMPORTADA_DO_CARTAO` |
| Divisor valor | `formulario:outroValorDoDivisor` | text | |
| Quantidade tipo | `formulario:tipoDaQuantidade` | radio | `INFORMADA` / `IMPORTADA_DO_CALENDARIO` / `IMPORTADA_DO_CARTAO` |
| Quantidade valor | `formulario:valorInformadoDaQuantidade` | text | |
| Valor Pago tipo | `formulario:tipoDoValorPago` | radio | `INFORMADO` / `CALCULADO` |
| Valor Pago valor | `formulario:valorInformadoPago` | text | |
| FGTS incidência | `formulario:fgts` | checkbox | |
| INSS/CS incidência | `formulario:inss` | checkbox | label visual: "Contribuição Social" |
| IRPF incidência | `formulario:irpf` | checkbox | |
| Previdência Privada | `formulario:previdenciaPrivada` | checkbox | |
| Pensão Alimentícia | `formulario:pensaoAlimenticia` | checkbox | |
| Zerar Negativo | `formulario:zeraValorNegativo` | checkbox | |
| Prop. Base | `formulario:aplicarProporcionalidadeABase` | checkbox | |
| Salvar | `formulario:salvar` | button | type="button" (não submit) |
| Cancelar | `formulario:cancelar` | button | |

**Opções confirmadas para `formulario:tipoDaBaseTabelada`:**
`org.jboss.seam.ui.NoSelectionConverter.noSelectionValue` | `MAIOR_REMUNERACAO` | `HISTORICO_SALARIAL` | `SALARIO_DA_CATEGORIA` | `SALARIO_MINIMO` | `VALE_TRANSPORTE`

**⚠ Radios com sufixo numérico** (ex: `formulario:tipoDeVerba:0`):
- `[id$='tipoDeVerba']` NÃO casa (termina em `:0`)
- Usar: `table[id$='tipoDeVerba'] input[value='PRINCIPAL']`
- Ou: `input[type='radio'][name*='tipoDeVerba'][value='PRINCIPAL']`

---

## verbas-para-calculo.jsf (Lançamento Expresso)

- Checkboxes com IDs dinâmicos: `formulario:j_id82:ROW:j_id84:COL:selecionada`
- Buscar pelo texto da `<td>` pai de cada checkbox (sem elemento `:nome` estável)
- Scroll JS necessário — apenas ~27 das 60+ verbas são visíveis no viewport

**Mapa linha × coluna das verbas principais:**

| Linha:Col | Verba |
|---|---|
| 0:0 | 13º SALÁRIO |
| 0:1 | FÉRIAS + 1/3 |
| 0:2 | TÍQUETE-ALIMENTAÇÃO |
| 4:0 | ACORDO (VERBAS INDENIZATÓRIAS) |
| 4:1 | HORAS EXTRAS 100% |
| 7:0 | ADICIONAL INSALUBRIDADE 10% |
| 7:1 | INDENIZAÇÃO ADICIONAL |
| 9:0 | ADICIONAL INSALUBRIDADE 40% |
| 9:1 | INDENIZAÇÃO POR DANO ESTÉTICO |
| 10:0 | ADICIONAL PERICULOSIDADE 30% |
| 10:1 | INDENIZAÇÃO POR DANO MATERIAL |
| 11:0 | ADICIONAL PRODUTIVIDADE 30% |
| 11:1 | INDENIZAÇÃO POR DANO MORAL |
| 15:0 | ADICIONAL NOTURNO 20% |
| 15:1 | MULTA DO ARTIGO 477 DA CLT |
| 17:0 | AVISO PRÉVIO |
| 17:1 | PRÊMIO PRODUÇÃO |
| 21:0 | DIFERENÇA SALARIAL |
| 21:1 | SALDO DE EMPREITADA |
| 22:0 | DIÁRIAS INTEGRAÇÃO |
| 22:1 | SALDO DE SALÁRIO |
| 24:0 | FERIADO EM DOBRO |
| 24:1 | SALÁRIO RETIDO |

---

## historico-salario.jsf (Histórico Salarial — Novo)

| Campo | ID | Tipo | Notas |
|---|---|---|---|
| Nome | `formulario:nome` | text | |
| Parcela tipo | `formulario:tipoVariacaoDaParcela` | radio | `FIXA` / `VARIAVEL` |
| Valor tipo | `formulario:tipoValor` | radio | `INFORMADO` / `CALCULADO` |
| Valor | `formulario:valorParaBaseDeCalculo` | text | |
| FGTS | `formulario:fgts` | checkbox | |
| INSS | `formulario:inss` | checkbox | |
| Competência Inicial | `formulario:dataInicioInputDate` | text | MM/AAAA |
| Competência Final | `formulario:dataFinalInputDate` | text | MM/AAAA |

---

## fgts.jsf

**⚠ Radios com sufixo numérico** — mesma armadilha que `verba-calculo.jsf`.
Usar `name*=` ou `table[id$=] input[value=]`.

| Campo | ID tabela/name | Tipo | Valores |
|---|---|---|---|
| Destino | `formulario:tipoDeVerba` | radio | `PAGAR` / `DEPOSITAR` |
| Compor Principal | `formulario:comporPrincipal` | radio | `SIM` / `NAO` |
| Alíquota | `formulario:aliquota` | radio | `DOIS_POR_CENTO` / `OITO_POR_CENTO` |
| Tipo Valor Multa | `formulario:tipoDoValorDaMulta` | radio | `CALCULADA` / `INFORMADA` |
| Tipo Multa | `formulario:multaDoFgts` | radio | `VINTE_POR_CENTO` / `QUARENTA_POR_CENTO` |
| Incidência | `formulario:incidenciaDoFgts` | select | `SOBRE_O_TOTAL_DEVIDO` / `SOBRE_DEPOSITADO_SACADO` / `SOBRE_DIFERENCA` / `SOBRE_TOTAL_DEVIDO_MAIS_SAQUE_E_OU_SALDO` / `SOBRE_TOTAL_DEVIDO_MENOS_SAQUE_E_OU_SALDO` |
| Multa 40% | `formulario:multa` | checkbox | |
| Excluir Aviso da Multa | `formulario:excluirAvisoDaMulta` | checkbox | |
| Multa Art. 467 | `formulario:multaDoArtigo467` | checkbox | |
| Multa 10% | `formulario:multa10` | checkbox | |
| CS/INSS incidência | `formulario:contribuiçãoSocial` | checkbox | **ID com acento** (ç, ã) — diferente de verba manual |
| Pensão Alimentícia | `formulario:incidenciaPensaoAlimenticia` | checkbox | |
| Deduzir FGTS | `formulario:deduzirDoFGTS` | checkbox | |

---

## inss/inss.jsf (Contribuição Social)

| Campo | Seletor sugerido | Tipo |
|---|---|---|
| Apurar segurado sobre salários devidos | `[id$='apurarSegurado']` ou by label | checkbox |
| Cobrar do reclamante | `[id$='cobrarDoReclamante']` ou by label | checkbox |
| Com correção trabalhista | `[id$='comCorrecaoTrabalhista']` ou by label | checkbox |
| Apurar sobre salários pagos | `[id$='apurarSobreSalariosPagos']` ou by label | checkbox |
| Salvar | `formulario:salvar` | button |

---

## honorarios.jsf

| Campo | Seletor sugerido | Tipo | Valores |
|---|---|---|---|
| Novo | `[id$='novo']` ou botão "Novo" | button | Abre formulário de honorário |
| Devedor | `[id$='devedor']` ou by label | select/radio | `RECLAMADO` / `RECLAMANTE` |
| Tipo | `[id$='tipoHonorario']` ou by label | select/radio | `SUCUMBENCIAIS` / `CONTRATUAIS` |
| Tipo valor | `[id$='tipoValor']` ou by label | radio | `CALCULADO` / `INFORMADO` |
| Base de apuração | `[id$='baseApuracao']` ou by label | select | `Condenação` / `Verbas Não Compõem Principal` / `Renda Mensal` |
| Percentual | `[id$='percentual']` ou by label | text | float decimal |
| Apurar IR | `[id$='apurarIr']` ou by label | checkbox | |
| Salvar | `formulario:salvar` | button | |

---

## irpf.jsf (Imposto de Renda)

| Campo | Seletor sugerido | Tipo |
|---|---|---|
| Apurar IR | `[id$='apurar']` ou by label | checkbox/radio |
| Tributação exclusiva | `[id$='tributacaoExclusiva']` ou by label | checkbox |
| Regime de caixa | `[id$='regimeCaixa']` ou by label | checkbox |
| Tributação em separado | `[id$='tributacaoEmSeparado']` ou by label | checkbox |
| Dedução INSS | `[id$='deducaoInss']` ou by label | checkbox |
| Dedução honorários reclamante | `[id$='deducaoHonorarios']` ou by label | checkbox |
| Salvar | `formulario:salvar` | button |

---

## multas-indenizacoes.jsf (Novo)

| Campo | ID | Tipo | Notas |
|---|---|---|---|
| Nome | `formulario:descricao` | text | |
| Valor tipo | `formulario:valor` | radio | `INFORMADO` / `CALCULADO` |
| Alíquota/Valor | `formulario:aliquota` | text | |
| Credor/Devedor | `formulario:credorDevedor` | select | |
| Base Multa | `formulario:tipoBaseMulta` | select | `PRINCIPAL` / `VALOR_CAUSA` / etc. |
| Salvar | `formulario:salvar` | button | |

---

## liquidacao.jsf (Liquidar)

| Campo | Seletor | Notas |
|---|---|---|
| Data de liquidação | `input[id*='dataLiquidacao']` | DD/MM/AAAA — fill com data de hoje |
| Botão Liquidar | `[id$='liquidar']` ou botão "Liquidar" | Dispara AJAX longo |
| Mensagem sucesso | texto "Não foram encontradas pendências para a liquidação" | Aguardar após clicar |
| Mensagem erro | texto "não foi possível" ou "existem pendências" | Indica problema nos dados |

---

## Padrões de seleção para radios com sufixo numérico

```python
# IDs reais: formulario:tipoDeVerba:0, formulario:tipoDeVerba:1
# [id$='tipoDeVerba'] NÃO funciona (ID termina com :0, não com tipoDeVerba)

# Correto — por table wrapper:
page.locator("table[id$='tipoDeVerba'] input[value='PAGAR']")

# Correto — por name contains:
page.locator("input[type='radio'][name*='tipoDeVerba'][value='PAGAR']")

# Correto — JS puro (mais robusto):
page.evaluate("""() => {
    const r = [...document.querySelectorAll('input[type="radio"]')]
        .find(el => el.name.includes('tipoDeVerba') && el.value === 'PAGAR');
    if (r) { r.click(); r.dispatchEvent(new Event('change', {bubbles:true})); }
}""")
```
