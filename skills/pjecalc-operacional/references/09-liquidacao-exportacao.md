# Liquidacao, Exportacao e Validacao Final
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

---

## 1. Visao Geral

O fluxo final deve ser tratado como etapa de **teste, saneamento e validacao**. A liquidacao nao e um simples botao de encerramento: ela revela se faltam bases salariais, se modulos acessorios ficaram sem incidencia de origem ou se ocorrencias dependentes nao foram regeradas [Aula 4].

| Subetapa | Acao ensinavel | Finalidade pratica | Origem |
|---|---|---|---|
| Operacoes > Liquidar | Executar o calculo consolidado | Gerar resumo e alertas | [Aula 4] |
| Erros e Alertas | Ler criticamente cada aviso | Identificar ausencia de base, incidencia ou regeracao | [Aula 4] |
| Imprimir | Selecionar relatorios pertinentes | Validar matematica e composicao do calculo | [Aula 4] |
| Exportar | Gerar arquivo do calculo | Reaproveitar o trabalho em outro ambiente ou peticao | [Aula 4] |

---

## 2. Checklist Executavel ANTES de Liquidar

| Item de controle | O que a maquina deve verificar | Origem |
|---|---|---|
| Historicos salariais completos | Todas as verbas dependentes de base devem encontrar suporte historico suficiente | [Aula 4] |
| Incidencias marcadas | Modulos como previdencia privada, pensao, FGTS e reflexos exigem marcacoes de origem | [Aula 3] [Aula 4] |
| Ocorrencias regeradas | Mudancas estruturais em verbas, FGTS e CS exigem regeracao | [Aula 2] [Aula 3] [Aula 4] |
| Parametros de correcao e juros salvos | Evitar liquidacao com configuracao antiga | [Aula 4] [Video complementar — Juros/Correcao] |
| Cartao de Ponto validado | Quantidades coerentes antes da liquidacao das verbas correlatas | [Video complementar — Cartao de Ponto] |

### Checklist resumido para automacao
```
[ ] Historico Salarial preenchido para todo o periodo
[ ] Todas as verbas com base de calculo vinculada
[ ] Incidencias de FGTS, CS, IR marcadas nas verbas corretas
[ ] Ocorrencias regeradas apos qualquer alteracao estrutural
[ ] Correcao monetaria e juros configurados e salvos
[ ] Cartao de Ponto apurado (se houver horas extras)
[ ] Honorarios configurados (se houver)
[ ] Custas configuradas (se houver)
```

---

## 3. Passo a Passo para Liquidar

| Passo | Acao executavel | Origem |
|---|---|---|
| 1 | Entrar em **Operacoes** | [Aula 4] |
| 2 | Selecionar **Liquidar** | [Aula 4] |
| 3 | Informar a data da liquidacao | [Aula 4] |
| 4 | Escolher o criterio de acumulacao dos indices | [Aula 4] |
| 5 | Confirmar a liquidacao | [Aula 4] |

### Mensagem esperada
Apos liquidacao bem-sucedida, o sistema exibe mensagem de sucesso (ex: "Operacao realizada com sucesso") e disponibiliza o resumo. **[NÃO COBERTO NAS AULAS]** quanto ao texto literal exato.

---

## 4. Interpretacao de Erros e Alertas

A maquina deve distinguir **alerta** de **erro impeditivo**. O alerta pode sinalizar peculiaridade ou incompletude, mas nem sempre bloqueia a liquidacao. O erro impeditivo exige retorno a pagina de origem [Aula 4].

| Situacao | Causa tipica demonstrada | Resposta operacional |
|---|---|---|
| Alerta em hora extra 50% | Falta de valor historico em alguma ocorrencia necessaria | Voltar ao historico salarial e completar a base |
| Alerta em diferenca salarial | Base historica insuficiente ou parametrizacao incompleta | Revisar a verba-base e as ocorrencias vinculadas |
| Erro na previdencia privada | Nenhuma verba marcada com a incidencia necessaria | Voltar a **Verbas** e marcar a incidencia correspondente |
| Pendencia de regeracao | Verbas, FGTS ou CS alterados sem regerar | Executar **Regerar** e liquidar novamente |

---

## 5. Relatorios que a Maquina Deve Conferir

| Relatorio/saida | Finalidade de conferencia | Origem |
|---|---|---|
| Resumo da liquidacao | Verificar composicao do principal, reflexos, deducoes e encargos | [Aula 4] |
| Espelho do Cartao de Ponto | Validar jornada, horas extras e adicional noturno | [Video complementar — Cartao de Ponto] |
| Resumo da verba de diferenca salarial/reflexos | Confirmar que a verba-base nao compos o principal e apenas alimentou reflexos | [Video complementar — Reflexos/Integracao] |
| Resumo do FGTS | Confirmar saldo liquido ao reclamante versus depositos a recolher | [Video complementar — FGTS nao depositado] |
| Resumo das verbas estabilitarias | Confirmar salario, ferias e 13o do periodo estabilitario | [Video complementar — Estabilidades] |

---

## 6. Exportacao

A exportacao deve ser tratada como operacao distinta da impressao [Aula 4].

| Operacao | Finalidade | Origem |
|---|---|---|
| Imprimir | Produzir relatorio para auditoria humana e processual | [Aula 4] |
| Exportar | Gerar arquivo do calculo (.PJC) para reaproveitamento | [Aula 4] |
| Distincao critica | Exportar nao substitui imprimir e imprimir nao substitui exportar | [Aula 4] |

### Fluxo de exportacao para automacao
```
1. Apos liquidacao bem-sucedida
2. Menu Operacoes → Exportar
3. Sistema gera arquivo .PJC (ZIP com XML ISO-8859-1)
4. Salvar o arquivo exportado
```

---

## 7. DESCOBERTA CRITICA: Arquivo .PJC Nativo vs Exportado pelo PJE-Calc

> **REGRA ABSOLUTA:** Nunca usar o gerador nativo (`pjc_generator.py`) como resultado final.

| Caracteristica | Gerador Nativo (pjc_generator.py) | Exportacao PJE-Calc (botao Exportar) |
|---|---|---|
| **Tamanho** | ~52 KB | 60-560 KB |
| **Estado** | Pre-liquidacao (template) | Pos-liquidacao (calculo completo) |
| **Validade** | **REJEITADO** na importacao pelo PJE-Calc | Aceito e funcional |
| **Conteudo** | Dados parciais, formulas genericas, valores zerados | Calculo integral com indices, verbas e liquidacao |

### Por que o nativo falha
- Zera o valor da causa (`valorDaCausa = 0.00`)
- Ignora a data de autuacao (`dataAutuacao = null`)
- Oculta documentos fiscais
- Infere formulas de verbas de maneira generica
- NAO contem dados de liquidacao (juros, correcao, totais)

### Regra para automacao
A automacao **deve completar a liquidacao dentro do PJE-Calc** e exportar via botao Exportar da interface. O arquivo resultante (pos-liquidacao) e o unico formato valido para uso em peticoes e importacao em outras instancias.
