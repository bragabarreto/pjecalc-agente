---
name: pjecalc-operacional
description: Regras operacionais para automação do PJE-Calc Cidadão — roteiros executáveis por parcela, regras de dependência entre módulos, fichas técnicas de cada verba com passo a passo de preenchimento, armadilhas e validação. Baseado em 11 videoaulas do Prof. Jorge Penna + manual CSJT.
---

# Skill: PJE-Calc Operacional — Regras para Processamento e Automação

## Objetivo

Esta skill ensina ao agente **como operar o PJE-Calc Cidadão** tanto no plano do **processamento de dados** (extração de sentenças/relatórios) quanto no plano da **automação de preenchimento** (Playwright). Cada seção responde: **em que página entrar**, **o que preencher**, **em que ordem**, **o que o sistema faz após cada ação**, **quando salvar/regerar** e **como validar o resultado**.

Complementa a skill `/pjecalc-preenchimento` (manual genérico) com **roteiros operacionais executáveis** por parcela.

---

## Regras Absolutas

1. **Firefox obrigatório** — Playwright usa `pw.firefox.launch()`. Chromium causa incompatibilidades.
2. **Nunca usar PJC nativo** — O `pjc_generator.py` gera templates pré-liquidação que o PJE-Calc rejeita. Sempre Liquidar → Exportar via interface.
3. **Histórico Salarial ANTES de Verbas** — Sem histórico, verbas como HE, diferença salarial e insalubridade falham.
4. **Botão Manual = id="incluir"** — NÃO clicar "Novo" (cria cálculo novo). Clicar "Manual" para criar verba manual.
5. **Campos obrigatórios em verbas manuais** — Preencher `caracteristica`, `ocorrencia`, `base_calculo`. Sem eles, liquidação HTTP 500.
6. **Gerar Ocorrências antes de Salvar** — No histórico salarial e em verbas com ocorrências mensais.
7. **Regerar após alterações estruturais** — Mudanças de período, base ou incidência exigem regeração.
8. **Reflexos NÃO são verbas manuais** — Reflexos (13o, férias, aviso, DSR, FGTS) são configurados clicando no botão **"Verba Reflexa"** à direita de cada verba principal na listagem `verbas-para-calculo.jsf`. NUNCA criar reflexo como verba manual autônoma.
9. **Multa FGTS 40% = checkbox na aba FGTS** — Em Cálculo > FGTS, o checkbox `multa` habilita a seção de multa. **Sequência obrigatória:** clicar checkbox `multa` → **aguardar AJAX** (o onchange re-renderiza campos) → selecionar `tipoDoValorDaMulta` (CALCULADA) → aguardar AJAX → selecionar `multaDoFgts` (QUARENTA_POR_CENTO). Sem o AJAX wait, os radios ficam `disabled`.
10. **Multa Art. 467 CLT = checkbox dentro da seção de Multa 40% no FGTS** — Aparece como sub-opção (`multaDoArtigo467`) dentro da seção de multa. **Dependente do checkbox `multa` estar marcado** (disabled se multa=false). Não é verba manual nem reflexo. A extração JSON deve preencher `fgts.multa_467: true`.
11. **Jornada Padrão ≠ Jornada Praticada no Cartão de Ponto** — "Jornada de Trabalho Padrão" = jornada CONTRATUAL (ex: 8h/dia CLT). A jornada efetivamente praticada (ex: 10h) vai na Grade de Ocorrências. HE = praticada − padrão. Se preencher padrão com praticada, HE = 0 (ERRO).
12. **valorCargaHorariaPadrao ≠ qtJornadaMensal** — São campos diferentes: `valorCargaHorariaPadrao` (Parâmetros do Cálculo) = `semanal × 5` (ex: 44h→220). `qtJornadaMensal` (Cartão de Ponto) = `semanal / 7 × 30` (ex: 44h→188,57). Não confundir.
13. **valorCargaHorariaPadrao obrigatório ANTES do Cartão de Ponto** — Sem este campo salvo, clicar "Novo" no Cartão de Ponto causa NPE (HTTP 500). Deve ser preenchido na aba Parâmetros do Cálculo.

---

## Fluxo Macro (Sequência de Dependências)

```
1.  Dados do Processo + Parâmetros do Cálculo > Salvar
2.  Faltas > Salvar
3.  Férias > Salvar
4.  Histórico Salarial (bases remuneratórias) > Salvar
5.  Verbas (Expresso + Manual + Reflexos) > Salvar
6.  Cartão de Ponto (se houver jornada) > Salvar
7.  FGTS > Salvar
8.  Contribuição Social > Salvar
9.  Imposto de Renda > Salvar
10. Multas e Indenizações > Salvar
11. Honorários + Custas > Salvar
12. Correção Monetária e Juros > Salvar
13. Regerar Ocorrências (aba Verbas — se houve alterações nos parâmetros)
14. Operações → Liquidar → Validar → Exportar .PJC
```

> **Regra de ouro:** Clicar **Salvar** após CADA página. Sair sem salvar = perda total.
> Cada etapa depende das anteriores. Não liquidar sem revisar histórico, verbas e regerar.

---

## Referências Temáticas

| Ref | Arquivo | Conteúdo |
|-----|---------|----------|
| 01 | `references/01-fluxo-geral.md` | Fluxo macro, dependências, telas e regras de navegação |
| 02 | `references/02-historico-salarial.md` | Histórico como fonte de verdade; histórico duplo para diferenças |
| 03 | `references/03-verbas-expresso.md` | Fichas: insalubridade, periculosidade, HE, adicional noturno, aviso prévio |
| 04 | `references/04-verbas-manuais.md` | Fichas: diferença salarial, acúmulo, estabilidade, danos morais/materiais, salários retidos |
| 05 | `references/05-cartao-ponto.md` | Jornada, programação semanal, apuração, espelho, intrajornada |
| 06 | `references/06-fgts-inss-ir.md` | FGTS (incluindo não depositado), CS, IR, pensão, previdência |
| 07 | `references/07-correcao-juros.md` | Índices, combinações, data de corte, ADC 58, EC 113, Lei 14.905 |
| 08 | `references/08-honorarios-custas.md` | Honorários sucumbenciais, periciais, custas processuais |
| 09 | `references/09-liquidacao-exportacao.md` | Liquidar, alertas, imprimir, exportar .PJC válido |
| 10 | `references/10-armadilhas.md` | Troubleshooting: erros comuns, soluções, checklist pré-liquidação |

---

## Integração Processamento ↔ Automação

Para cada dado extraído da sentença, a tabela abaixo indica onde/como é usado no PJE-Calc:

| Dado Extraído | Usado em | Campo PJE-Calc | Observação |
|---------------|----------|----------------|------------|
| `contrato.admissao` | Parâmetros do Cálculo | `dataAdmissao` | Obrigatório |
| `contrato.demissao` | Parâmetros do Cálculo | `dataDemissao` | Em estabilidade: usar data final da estabilidade |
| `historico_salarial[].valor` | Histórico Salarial | `valorParaBaseDeCalculo` | Valor mensal integral |
| `historico_salarial[].nome` | Histórico Salarial | `nome` | "Salário", "Salário Pago", "Salário Devido" |
| `verbas_deferidas[].nome` | Verbas (Expresso/Manual) | `descricao` | Nome da verba |
| `verbas_deferidas[].caracteristica` | Verbas | select `caracteristica` | Comum, 13o Salário, Férias, Aviso Prévio |
| `verbas_deferidas[].ocorrencia` | Verbas | select `ocorrencia` | Mensal, Desligamento, Dezembro, Período Aquisitivo |
| `verbas_deferidas[].base_calculo` | Verbas | select base | Histórico Salarial, Maior Remuneração, Salário Mínimo |
| `fgts.aliquota` | FGTS | campo alíquota | 8% padrão |
| `correcao_juros.indice_correcao` | Correção/Juros | select índice | SELIC, IPCA-E, TR, Tabela JT |
| `honorarios[].percentual` | Honorários | campo percentual | Float (0.15 = 15%) |

---

## Fontes

Baseado em videoaulas do Prof. Jorge Penna (TRT8):
- Aulas 1-4 do Módulo 01 do PJE-Calc
- Vídeos complementares: Cartão de Ponto, OJ 394, Reflexos/Integração, FGTS não depositado, Estabilidades, Juros/Correção, Insalubridade, Periculosidade, Transferência, Diferenças Salariais, Danos Morais, Pensionamento, Acúmulo de Função, Honorários

Marcação `[NÃO COBERTO NAS AULAS]` preservada onde não houve demonstração suficiente.
