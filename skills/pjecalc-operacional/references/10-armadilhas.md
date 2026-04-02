# Armadilhas, Troubleshooting e Descobertas Operacionais
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

---

## 1. Armadilhas Gerais (Secao 9.1)

| Armadilha | Consequencia | Solucao operacional |
|---|---|---|
| Lancar verba sem base historica suficiente | Alertas e calculo inconsistente | Completar o **Historico Salarial** antes de liquidar |
| Alterar parametro estrutural sem regerar | Ocorrencias antigas permanecem ativas | Regerar antes da nova liquidacao |
| Marcar reflexos indiscriminadamente | Credito final indevido ou duplicado | Selecionar apenas reflexos efetivamente deferidos |
| Nao revisar o relatorio final | Erro conceitual passa despercebido | Imprimir e confrontar com a tese do caso |
| Nao segmentar regimes temporais | Mistura de criterios juridicos incompativeis | Criar verbas ou fases distintas quando necessario |

---

## 2. Armadilhas por Tema Especifico (Secao 9.2)

| Tema | Erro tipico | Correcao operacional |
|---|---|---|
| Cartao de Ponto | Programacao semanal sem revisao de excecoes | Editar a grade de ocorrencias antes de usar os quantitativos |
| OJ 394 | Manter DSR reflexo em periodo que exige tratamento autonomo | Separar temporalmente as rubricas |
| Diferenca salarial/reflexos | Esquecer de alterar **Compor Principal** | Ajustar para **Nao** quando a verba servir apenas de base |
| FGTS nao depositado | Liquidar como verba devida ao reclamante | Marcar **Recolher** e conferir a secao de depositos |
| Estabilidade | Usar a data real da dispensa como data de demissao do calculo | Ajustar para a data final do periodo estabilitario |

---

## 3. Armadilhas por Verba

### 3.1 Horas Extras (Secao 2.1)
| Armadilha | Efeito | Solucao |
|---|---|---|
| Falta de historico salarial completo | Alerta na liquidacao | Completar historico antes de lancar a verba |
| Nao vincular base de calculo com botao "+" (verde) | Erro ao salvar | Clicar no "+" para confirmar a base |
| Nao importar quantidades do Cartao de Ponto | Verba sem valores | Importar do Cartao e clicar "+" para confirmar |

### 3.2 Adicional Noturno (Secao 2.2)
| Armadilha | Efeito | Solucao |
|---|---|---|
| Nao marcar reducao ficta da hora noturna | Apuracao juridica incorreta do periodo noturno | Marcar obrigatoriamente a opcao de reducao ficta |
| Usar multiplicador 1,8 em vez de separar verbas | Bis in idem (incidencia tripla do adicional) | Calcular adicional noturno (20%) e HE noturna (mult 1,6) separadamente |

### 3.3 Diferenca Salarial (Secao 2.3)
| Armadilha | Efeito | Solucao operacional |
|---|---|---|
| Proporcionalizacao assimetrica entre valor devido e valor pago | Reflexos negativos em meses quebrados | Marcar proporcionalizacao de forma identica nos dois lados |
| FGTS sem aparecer no resumo | Reflexo fundiario omitido | Marcar o checkbox especifico do FGTS na linha da verba principal |
| Verba-base somando no credito final indevidamente | Pagamento do principal quando so se queria o reflexo | Ajustar **Compor Principal** para **Nao** |
| Nao marcar CS como recolhida no salario recebido | Calculo duplicado de INSS sobre a base ja paga | Ativar checkbox de recolhimento no Historico: Salario Recebido |
| Nome generico da verba | Dificuldade em auditar | Renomear especificando o paradigma ou norma coletiva |

### 3.4 FGTS + Multa de 40% (Secao 2.5)
| Armadilha | Efeito | Solucao |
|---|---|---|
| Tratar FGTS apenas como reflexo | Modulo proprio ignorado | Usar a pagina propria de FGTS com parametros e ocorrencias |
| Nao marcar Recolher em FGTS nao depositado | Valor aparece como credito liquido ao reclamante | Marcar **Recolher** e conferir secao DEPOSITOS FGTS |
| Nao conferir secao DEPOSITOS FGTS no resumo | Enquadramento juridico incorreto nao detectado | Verificar se liquido do reclamante ficou zerado para FGTS |

### 3.5 Ferias e 13o do Periodo Estabilitario (Secao 2.6)
| Armadilha | Efeito | Solucao |
|---|---|---|
| Data de demissao = data real da dispensa | Calculo do periodo estabilitario incorreto | Informar data final da estabilidade como data de demissao |
| Nao renomear verbas para contexto estabilitario | Auditoria confusa | Renomear SALARIO RETIDO → SALARIO ESTABILIDADE etc |
| Nao lancar avos manualmente nas ocorrencias | Sistema nao calcula corretamente ferias/13o fracionados | Contar meses/avos dentro da estabilidade e lancar por exercicio civil |

---

## 4. Armadilhas de Correcao Monetaria e Juros (Secao 6)

| Armadilha | Efeito | Solucao |
|---|---|---|
| Liquidar com parametros padrao sem revisao | Indices incorretos aplicados | Sempre revisar antes de liquidar |
| Confundir correcao monetaria com juros | Dupla incidencia ou omissao | Tratar como modulos separados |
| Duplicar indices por sobreposicao inadequada | Dupla correcao sobre mesmo periodo | Verificar combinacao de indices |
| Deixar periodos hibridos sem marco definido | Mistura de regimes temporais | Definir data de corte para mudanca de regime |
| Presumir que todas as verbas usam mesma base de juros | Calculo incorreto para verbas especificas | Revisar Dados Especificos por modulo |
| Nao salvar antes de liquidar | Liquidacao reflete parametrizacao antiga | Sempre salvar antes |

---

## 5. Armadilhas de Verbas Rescisórias (Secao 10)

| Armadilha | Efeito | Solucao |
|---|---|---|
| Projetar aviso previo na data de demissao | Datas erradas em todo o calculo | Preencher ultimo dia efetivamente trabalhado |
| Nao preencher Maior Remuneracao | Base rescisoria ausente para Aviso, Multa 477, Ferias | Inserir maior salario base + media de variaveis |
| Nao lancar salario cheio no historico | 13o e FGTS sem base | Preencher salario mensal cheio mesmo no mes da demissao |

---

## 6. Armadilhas do Adicional de Insalubridade (Secao 13)

| Armadilha | Efeito | Solucao |
|---|---|---|
| Nao marcar Proporcionalizar | Valores cheios em meses de admissao/demissao | Marcar obrigatoriamente |
| Nao regerar apos alteracao de periodo | Grade mensal desatualizada | Clicar em Regerar |

---

## 7. Armadilhas do Adicional de Periculosidade (Secao 5/14)

| Armadilha | Efeito | Solucao |
|---|---|---|
| Calcular DSR para mensalista | Pagamento em duplicidade | NAO calcular DSR a parte para mensalista (ja embutido) |
| Nao ter Historico Salarial preenchido | Base insuficiente para os 30% | Verificar historico antes de salvar a verba |
| Nao regerar Contribuicao Social | Aliquotas desatualizadas | Acessar CS > Ocorrencias > Regerar |

---

## 8. Armadilhas do Intervalo Intrajornada (Secao 12)

| Armadilha | Efeito | Solucao |
|---|---|---|
| Nao distinguir regime pre e pos-reforma | Calculo integral quando deveria ser parcial (ou vice-versa) | Selecionar criterio correto: Integral, Hibrido ou Periodo Suprimido |
| Nao regerar apos mudar criterio de apuracao | Quantidades antigas mantidas | Regerar Cartao de Ponto e Verba |
| Apurar intrajornada em jornada < 6h | Direito inexistente computado | Verificar se empregado trabalha mais de 6h diarias |

---

## 9. Armadilhas de Danos Morais (Secao 16)

| Armadilha | Efeito | Solucao |
|---|---|---|
| Usar data do desligamento como epoca propria | Juros e correcao incorretos | Usar data do arbitramento (sentenca/acordao) |
| Checkbox Sumula 439 incorreto | Juros do ajuizamento vs arbitramento trocados | Marcar = juros do ajuizamento; Desmarcar = juros do arbitramento |

---

## 10. Armadilhas de Danos Materiais / Pensionamento (Secao 17)

| Armadilha | Efeito | Solucao |
|---|---|---|
| Manter Sumula 439 marcada para dano material | Juros lineares desde ajuizamento em todas as parcelas | Desmarcar para permitir juros decrescentes |
| Nao aplicar redutor de valor presente em vincendas | Enriquecimento sem causa | Calcular PV ou aplicar redutor fixo (~30%) |

---

## 11. Armadilhas de Acumulo de Funcao (Secao 18)

| Armadilha | Efeito | Solucao |
|---|---|---|
| Nao marcar Proporcionalizar | Valores cheios em meses fracionados | Ativar proporcionalizacao |
| Base de calculo insuficiente | Alerta na liquidacao | Conferir Historico Salarial para todo o periodo do acumulo |
| Compor Principal = Sim quando deveria ser Nao | Pagamento indevido do principal | Verificar se titulo executivo limita a reflexos |

---

## 12. DESCOBERTAS OPERACIONAIS DA AUTOMACAO

Estas armadilhas foram identificadas durante o desenvolvimento e testes do pjecalc-agente e NAO constam do documento fonte original. Sao criticas para qualquer sistema de automacao.

### 12.1 HTTP 500 na Pagina de Verbas — Campos Obrigatorios Ausentes
**Problema:** Verbas criadas via botao "Manual" (`id="incluir"`) causam HTTP 500 na liquidacao.
**Causa:** Os campos `caracteristica`, `ocorrencia` e `base_calculo` nao sao preenchidos automaticamente no modo Manual.
**Solucao:** Usar o modo **Expresso** sempre que possivel. Se usar Manual, preencher obrigatoriamente os tres campos antes de salvar.

### 12.2 Tabela Paginada do Lancamento Expresso
**Problema:** A tabela do Lancamento Expresso (`verbas-para-calculo.xhtml`) usa `<a4j:repeat>` em layout de colunas. Apenas ~27 das 60+ verbas sao visiveis no viewport.
**Verbas ocultas tipicas:** "Saldo de Salario", "Ferias Proporcionais + 1/3", "Multa 477/467" ficam abaixo do scroll.
**Solucao:** Scroll via JavaScript + re-enumeracao dos elementos apos scroll.

### 12.3 Botao "Manual" vs "Novo" — Confusao de Interface
**Problema:** O botao "Manual" na pagina de Verbas cria uma verba em branco sem campos pre-configurados. O menu "Novo" na tela inicial cria um calculo novo.
**Regra:** Para verbas, preferir sempre o **Expresso**. O botao "Manual" so deve ser usado para verbas que nao existem no catalogo Expresso.

### 12.4 Arquivo PJC Nativo vs Exportacao PJE-Calc
**Problema:** O `pjc_generator.py` gera template pre-liquidacao (~52KB) que o PJE-Calc **rejeita** na importacao.
**Arquivos validos:** Pos-liquidacao (~60-560KB) exportados pelo botao Exportar do PJE-Calc.
**Regra:** NUNCA usar o gerador nativo como resultado final. A automacao deve completar a liquidacao e exportar via interface.

### 12.5 Firefox vs Chromium — Incompatibilidade do PJE-Calc
**Problema:** O PJE-Calc Cidadao foi desenvolvido para Firefox. Chromium causa incompatibilidades graves:
- Eventos AJAX do RichFaces nao disparam corretamente
- Calendarios JSF nao abrem ou nao respondem a cliques
- Popups JSF bloqueiam a execucao
**Regra:** Playwright deve usar **Firefox** exclusivamente (`self._pw.firefox.launch()`).

### 12.6 SSE Stream — Keepalive Obrigatorio
**Problema:** O SSE stream (endpoint `/api/executar/{sessao_id}`) desconecta durante operacoes longas (browser restart, AJAX pesado).
**Solucao:** Thread de keepalive dedicada envia mensagem a cada 10-15s via queue.

### 12.7 Historico Salarial — Extracao Obrigatoria
**Problema:** O prompt de extracao pode omitir historico salarial quando o salario e uniforme.
**Regra:** Extrair historico salarial SEMPRE (mesmo salario uniforme = 1 entrada). Campos: nome, data_inicio, data_fim, valor, incidencia_fgts, incidencia_cs.

---

## 13. Itens NAO Cobertos nas Aulas (Secao 9.3)

Estes itens permanecem como lacunas documentais. A automacao deve tratar com cautela.

| Item | Situacao |
|---|---|
| URLs internas das paginas | **[NAO COBERTO NAS AULAS]** |
| Labels integrais de todos os campos do lancamento manual | **[NAO COBERTO NAS AULAS]** |
| Texto literal de todas as mensagens de sucesso | **[NAO COBERTO NAS AULAS]** |
| Passo a passo completo de todas as multas legais possiveis | **[NAO COBERTO NAS AULAS]** |
| Parametrizacao integral da multa de 40% do FGTS em todos os campos | **[NAO COBERTO NAS AULAS]** |
| Catalogo exaustivo de todos os selects do sistema | **[NAO COBERTO NAS AULAS]** |
