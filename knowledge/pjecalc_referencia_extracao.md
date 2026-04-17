# Referência PJe-Calc — Campos, Valores e Regras de Negócio

> Documento consolidado para uso como knowledge em projetos de extração de sentenças trabalhistas.
> Fonte: Manual Oficial PJe-Calc v1.0 (CSJT/TRT8) + Tutorial Oficial + Catálogo de Verbas.

---

## 1. Parâmetros do Cálculo

### Dados obrigatórios
- Número do processo (formato CNJ: NNNNNNN-DD.AAAA.J.RR.VVVV)
- Estado (UF 2 letras) e Município da vara
- Data de admissão e demissão
- Data de ajuizamento / autuação
- Tipo de rescisão
- Maior remuneração / última remuneração
- Pelo menos 1 verba deferida

### Tipo de rescisão (enum)
| Valor | Quando usar |
|-------|-------------|
| sem_justa_causa | Dispensa imotivada, rescisão indireta (art. 483 CLT) |
| justa_causa | Justa causa reconhecida |
| pedido_demissao | Pedido de demissão do empregado |
| distrato | Acordo para rescisão (art. 484-A CLT) |
| morte | Falecimento do empregado |

### Regime de trabalho
| Valor | Divisor | Descrição |
|-------|---------|-----------|
| Tempo Integral | 220h/mês | Padrão CLT — 44h/semana |
| Tempo Parcial | proporcional | Até 30h/sem sem HE ou 26h/sem com HE (Reforma) |
| Trabalho Intermitente | variável | Convocação por período (art. 443 §3º CLT) |

### Prescrição
- **Quinquenal**: PJe-Calc subtrai 5 anos do ajuizamento automaticamente
- **FGTS**: prescrição quinquenal (STF RE 709.212, substituiu trintenária)

---

## 2. Aviso Prévio

| Tipo | Quando | Projetar |
|------|--------|----------|
| Calculado | Lei 12.506/2011 — PJe-Calc calcula dias automaticamente | Sim |
| Informado | Sentença fixa número de dias (ex: "33 dias") | Sim |
| Nao Apurar | Sem condenação ou pedido de demissão | Não |

**Regra crítica**: a data de demissão deve ser a data REAL da dispensa. O PJe-Calc projeta automaticamente o período do AP para 13º e férias — nunca alterar a data de demissão para incluir a projeção.

Proporcionalidade (Lei 12.506/2011):
- 1 a 12 meses: 30 dias
- Cada ano completo além do primeiro: +3 dias
- Máximo: 90 dias

---

## 3. Histórico Salarial

**OBRIGATÓRIO** — mesmo salário uniforme = 1 entrada com período completo.

Campos por entrada:
| Campo | Tipo | Descrição |
|-------|------|-----------|
| nome | string | "Salário" (padrão), "Comissões", "Salário Pago", "Salário Devido", etc. |
| data_inicio | DD/MM/AAAA | Início da faixa |
| data_fim | DD/MM/AAAA | Fim da faixa |
| valor | float | Salário mensal integral (sistema proporcionaliza meses incompletos) |
| variavel | bool | true = varia mês a mês (comissões, gorjetas). false = fixo |
| incidencia_fgts | bool | true (padrão para salário) |
| incidencia_cs | bool | true (padrão — contribuição social/INSS) |

Situações especiais:
- Equiparação salarial → "Salário Pago" + "Salário Devido" como entradas separadas
- Reajustes → uma entrada por faixa salarial
- Comissões + fixo → entradas separadas com nomes distintos

---

## 4. Catálogo de Verbas

### 4.1 Verbas Lançamento Expresso (predefinidas no PJe-Calc)

| Verba | Característica | Ocorrência | FGTS | INSS | IR |
|-------|---------------|------------|------|------|----|
| Saldo de Salário | Comum | Desligamento | Sim | Sim | Sim |
| Aviso Prévio Indenizado | Aviso Previo | Desligamento | Sim | Sim | Sim |
| 13º Salário Proporcional | 13o Salario | Desligamento | Sim | Sim | Sim |
| Férias Proporcionais + 1/3 | Ferias | Periodo Aquisitivo | Não | Sim | Sim |
| Férias Vencidas + 1/3 | Ferias | Periodo Aquisitivo | Não | Sim | Sim |
| Horas Extras | Comum | Mensal | Sim | Sim | Sim |
| Adicional Noturno | Comum | Mensal | Sim | Sim | Sim |
| Adicional de Insalubridade | Comum | Mensal | Sim | Sim | Sim |
| Adicional de Periculosidade | Comum | Mensal | Sim | Sim | Sim |
| Diferença Salarial | Comum | Mensal | Sim | Sim | Sim |
| Gratificação de Função | Comum | Mensal | Sim | Sim | Sim |
| Comissão | Comum | Mensal | Sim | Sim | Sim |
| Horas in Itinere | Comum | Mensal | Sim | Sim | Sim |
| Intervalo Intrajornada | Comum | Mensal | Sim | Sim | Sim |
| Intervalo Interjornada | Comum | Mensal | Sim | Sim | Sim |
| Adicional de Sobreaviso | Comum | Mensal | Sim | Sim | Sim |
| Adicional de Transferência 25% | Comum | Mensal | Sim | Sim | Sim |
| Multa Art. 477 CLT | Comum | Desligamento | Não | Não | Não |
| Vale Transporte | Comum | Mensal | Não | Não | Não |
| Salário-Família | Comum | Mensal | Não | Não | Não |
| Indenização por Dano Moral | Comum | Desligamento | Não | Não | Não |
| Indenização por Dano Material | Comum | Desligamento | Não | Não | Não |
| Indenização por Dano Estético | Comum | Desligamento | Não | Não | Não |
| Diárias - Integração ao Salário | Comum | Mensal | Sim | Sim | Sim |

### 4.2 Verbas de Lançamento Manual (NÃO existem no Expresso)

| Verba | Característica | Ocorrência | FGTS | INSS | IR |
|-------|---------------|------------|------|------|----|
| Intervalo do Art. 384 | Comum | Mensal | Sim | Sim | Sim |
| Multa Normativa / Cláusula Penal | Comum | Desligamento | Não | Não | Não |
| Indenização por Estabilidade | Comum | Desligamento | Não | Não | Não |
| Equiparação Salarial | Comum | Mensal | Sim | Sim | Sim |
| Reintegração / Salários do período | Comum | Mensal | Sim | Sim | Sim |

### 4.3 NÃO são verbas (tratamento especial)

| Item | Tratamento no PJe-Calc |
|------|----------------------|
| FGTS + Multa 40% | Aba FGTS — checkbox multa_40 |
| FGTS + Multa 20% | Aba FGTS — checkbox multa_40 + multa_20 |
| Multa art. 467 CLT | Aba FGTS — checkbox multa_467 + reflexa automática |
| FGTS não depositado | Aba FGTS — campo separado |
| Honorários periciais | Campo top-level separado |

---

## 5. Reflexos — Cascata por Verba Principal

### Horas Extras → 3 reflexas obrigatórias:
1. RSR sobre Horas Extras (Comum, Mensal, FGTS/INSS/IR = Sim)
2. 13º s/ Horas Extras (13o Salario, Dezembro, FGTS/INSS/IR = Sim)
3. Férias + 1/3 s/ Horas Extras (Ferias, Periodo Aquisitivo, FGTS=Não, INSS/IR=Sim)

### Adicional Noturno → 3 reflexas:
1. RSR sobre Adicional Noturno (Comum, Mensal)
2. 13º s/ Adicional Noturno (13o Salario, Dezembro)
3. Férias + 1/3 s/ Adicional Noturno (Ferias, Periodo Aquisitivo)

### Adicional de Insalubridade → 2 reflexas:
1. 13º s/ Insalubridade (13o Salario, Dezembro)
2. Férias + 1/3 s/ Insalubridade (Ferias, Periodo Aquisitivo)

### Adicional de Periculosidade → 2 reflexas:
1. 13º s/ Periculosidade
2. Férias + 1/3 s/ Periculosidade

### Verbas que NÃO geram reflexas:
- Dano moral/material/estético
- Multas (art. 467, 477, normativa)
- Aviso prévio indenizado (PJe-Calc projeta automaticamente para 13º e férias)
- Vale transporte, salário-família

**REGRA**: Uma parcela SÓ é reflexo se o dispositivo da sentença expressamente a vincular a outra principal. Parcelas condenadas autonomamente são PRINCIPAIS, mesmo que a doutrina presuma reflexo.

---

## 6. FGTS

| Campo | Valores | Regra |
|-------|---------|-------|
| aliquota | 0.08 (8% padrão), 0.02 (2% aprendiz) | — |
| multa_40 | true/false | true = sem justa causa ou rescisão indireta. INCOMPATÍVEL com justa_causa |
| multa_20 | true/false | Estabilidade provisória (CIPA, gestante). Quando true, multa_40 também = true |
| multa_467 | true/false | Parcelas rescisórias incontroversas não pagas (art. 467 CLT) |
| saldo_fgts | float ou null | Apenas se explícito na sentença — NÃO inferir |

### Incidência FGTS por verba
- **Incide**: saldo de salário, horas extras, adicionais (noturno, insalubridade, periculosidade), comissões, gratificações, aviso prévio indenizado
- **Não incide**: dano moral/material, multas (477, 467, normativa), vale transporte, férias indenizadas

---

## 7. Honorários Advocatícios

### Enums do PJe-Calc
| Campo | Valores aceitos |
|-------|----------------|
| tipo | SUCUMBENCIAIS (padrão), CONTRATUAIS |
| devedor | RECLAMANTE, RECLAMADO |
| tipo_valor | CALCULADO (percentual), INFORMADO (valor fixo) |
| base_apuracao | **BRUTO** (valor bruto da condenação — padrão), **BRUTO_MENOS_CONTRIBUICAO_SOCIAL** (bruto menos CS), **BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA** (bruto menos CS e PP) |

### Opções reais do PJE-Calc (DOM confirmado v2.15.1)
O campo `baseApuracao` na página `honorarios.jsf` tem exatamente 3 opções:
1. **Bruto** → `BRUTO`
2. **Bruto (-) Contribuição Social** → `BRUTO_MENOS_CONTRIBUICAO_SOCIAL`
3. **Bruto (-) Contribuição Social (-) Previdência Privada** → `BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA`

### Regras de base_apuracao
| Devedor | Tipo | Base padrão |
|---------|------|-------------|
| RECLAMADO | SUCUMBENCIAIS | BRUTO |
| RECLAMANTE | SUCUMBENCIAIS | BRUTO |
| Qualquer | CONTRATUAIS | BRUTO |

> Quando sentença determina dedução de CS antes de aplicar percentual → BRUTO_MENOS_CONTRIBUICAO_SOCIAL.
> NÃO existe opção "Ambos" — sucumbência recíproca = DOIS registros separados.
> Faixa "10% a 15%" → usar o menor valor (0.10).

### Justiça Gratuita e Honorários
Quando devedor tem justiça gratuita → exigibilidade SUSPENSA (art. 791-A, §4º, CLT).

### Honorários Periciais
Campo SEPARADO (não entra no array de honorários advocatícios). Valor float ou null.

---

## 8. Correção Monetária e Juros

### Enums do PJe-Calc — Correção Monetária (IndiceMonetarioEnum)
| Enum | Nome no PJe-Calc |
|------|-----------------|
| TUACDT | Tabela Única de Atualização e Conversão de Débitos Trabalhistas |
| TABELA_DEVEDOR_FAZENDA | Devedor Fazenda Pública |
| TABELA_INDEBITO_TRIBUTARIO | Repetição de Indébito Tributário |
| TABELA_UNICA_JT_MENSAL | Tabela JT Mensal |
| TABELA_UNICA_JT_DIARIO | Tabela JT Diária |
| TR | TR |
| IGPM | IGP-M |
| INPC | INPC |
| IPC | IPC |
| IPCA | IPCA |
| IPCAE | IPCA-E |
| IPCAETR | IPCA-E / TR |
| SELIC | SELIC (Receita Federal) |
| SELIC_FAZENDA | SELIC Simples |
| SELIC_BACEN | SELIC Composta |
| SEM_CORRECAO | Sem Correção |

### Enums do PJe-Calc — Juros de Mora (JurosEnum)
| Enum | Nome no PJe-Calc |
|------|-----------------|
| JUROS_PADRAO | Juros Padrão |
| JUROS_POUPANCA | Juros Caderneta de Poupança |
| FAZENDA_PUBLICA | Juros Fazenda Pública |
| JUROS_MEIO_PORCENTO | Juros Simples 0,5% a.m. |
| JUROS_UM_PORCENTO | Juros Simples 1,0% a.m. |
| JUROS_ZERO_TRINTA_TRES | Juros Simples 0,0333333% a.d. |
| SELIC | SELIC (Receita Federal) |
| SELIC_FAZENDA | SELIC Simples |
| SELIC_BACEN | SELIC Composta |
| TRD_SIMPLES | TRD Juros Simples |
| TRD_COMPOSTOS | TRD Juros Compostos |
| TAXA_LEGAL | Taxa Legal |
| SEM_JUROS | Sem Juros |

### Campos de correção/juros
| Campo | Valores aceitos |
|-------|----------------|
| lei_14905 | true (regime Lei 14.905/2024 — exige combinações), false |
| indice_correcao | qualquer enum de Correção Monetária acima |
| indice_correcao_pos | **IPCA** (correção pós-30/08/2024 — somente quando lei_14905=true) |
| taxa_juros | qualquer enum de Juros de Mora acima |
| data_taxa_legal | DD/MM/AAAA (padrão 30/08/2024 — somente quando taxa_juros = TAXA_LEGAL) |
| base_juros | Verbas (padrão), Credito Total |

### Mapeamento da sentença → enums (em ordem de prevalência)
| Critério na sentença | Lei 14.905 | Correção | Correção pós | Juros |
|----------------------|-----------|----------|-------------|-------|
| **ADC 58 + Lei 14.905/2024** — E-ED-RR-20407, "taxa legal", "art. 406 CC" | **true** | IPCAE | **IPCA** | **TAXA_LEGAL** |
| ADC 58 / critérios JT SEM Lei 14.905 (pré-ago/2024) | false | TUACDT | — | SELIC |
| "SELIC" / "taxa SELIC" sem distinguir fases | false | SELIC | — | SELIC |
| EC 113/2021 / "SELIC a partir de dez/2021" | false | SELIC | — | SELIC |
| "IPCA-E + juros de 1% a.m." | false | IPCAE | — | JUROS_PADRAO |
| "TR" / "TRCT" + juros de 1% | false | TR | — | JUROS_PADRAO |

### Detalhamento — Lei 14.905/2024 (jurisprudência majoritária atual)

**Correção Monetária no PJe-Calc:**
- IPCAE até 29/08/2024, COMBINADO COM IPCA a partir de 30/08/2024
- Se admissão > 30/08/2024 → usar somente IPCA como índice único

**Juros de Mora — depende da data de ajuizamento:**

**Cenário A — Ajuizamento ANTES de 30/08/2024:**
- Fase pré-judicial: TRD_SIMPLES, combinado com SEM_JUROS a partir de 30/08/2024
- Judicial Fase 1: SELIC do ajuizamento até 29/08/2024
- Judicial Fase 2: TAXA_LEGAL a partir de 30/08/2024

**Cenário B — Ajuizamento DEPOIS de 30/08/2024:**
- Fase pré-judicial: TRD_SIMPLES
- Judicial: TAXA_LEGAL a partir do ajuizamento

> **NOTA**: O PJe-Calc exige que essas fases sejam configuradas via "Combinar com outro índice" tanto na correção quanto nos juros.
> JAM FGTS: marcar apenas se sentença mencionar "JAM" ou "juros sobre atraso no depósito FGTS".

---

## 9. Contribuição Social (INSS)

| Campo | Default | Quando alterar |
|-------|---------|---------------|
| apurar_segurado_salarios_devidos | true | — |
| cobrar_do_reclamante | true | false SOMENTE se sentença diz "empregador arca com toda a contribuição" |
| com_correcao_trabalhista | true | — |
| apurar_sobre_salarios_pagos | false | true se houver salários pagos a menor (explícito) |
| lei_11941 | null | true se mencionar "Lei 11.941/2009" ou "regime de competência" |

### Incidência INSS por verba
- **Incide**: saldo de salário, horas extras, adicionais, 13º, aviso prévio trabalhado, comissões
- **Não incide**: dano moral/material, multas (477, 467), vale transporte, férias indenizadas (posição divergente)

---

## 10. Imposto de Renda

| Campo | Regra |
|-------|-------|
| apurar | true se verbas salariais tributáveis; false se somente indenizatórias |
| tributacao_exclusiva | true se "RRA" / "rendimentos recebidos acumuladamente" |
| regime_de_caixa | true se "regime de caixa" / "tributação mês a mês" |
| deducao_inss | true (padrão quando apurar=true e há INSS) |
| deducao_honorarios_reclamante | true quando honorários do reclamante deduzem base IR |
| deducao_pensao_alimenticia | true se sentença mencionar pensão alimentícia |

### Verbas sujeitas a IR
- **Incide**: saldo de salário, horas extras, adicionais, 13º, aviso prévio, comissões, férias
- **Não incide**: dano moral (Súmula 498/STJ), dano material, multas, verbas indenizatórias puras

---

## 11. Custas Processuais

| Campo | Default |
|-------|---------|
| base | Bruto Devido ao Reclamante |
| reclamado_conhecimento | CALCULADA (2%) |
| reclamado_liquidacao | NAO_SE_APLICA |
| reclamante_conhecimento | NAO_SE_APLICA |
| percentual | 0.02 |
| devedor | RECLAMADO |

---

## 12. Cartão de Ponto (Duração do Trabalho)

### Forma de Apuração de Horas Extras (enum)
| Código | Descrição |
|--------|-----------|
| NAP | Não apurar horas extras |
| HJD | Excedentes da jornada diária |
| SEM | Excedentes da jornada semanal |
| FAV | Critério mais favorável (compara diário vs semanal) |
| MEN | Excedentes da jornada mensal |
| HST | Conforme Súmula 85 TST |
| APH | Primeiras HE em separado |

### Preenchimento de Jornada
| Modalidade | Quando usar |
|------------|-------------|
| programacao_semanal | Sentença fixa horários por dia da semana |
| escala | Regime 12x36, 6x1, 5x1, etc. |
| livre | Jornada vaga ou preenchimento manual |

### Horário Noturno
| Categoria | Início | Fim |
|-----------|--------|-----|
| Urbano | 22:00 | 05:00 |
| Rural (pecuária) | 20:00 | 04:00 |
| Rural (lavoura) | 21:00 | 05:00 |

- **Redução ficta**: hora noturna = 52m30s (padrão = true)
- **Prorrogação** (Súmula 60 TST): labor após 05h em continuidade mantém adicional

### Jornada Padrão vs Praticada
- **Padrão** = jornada CONTRATADA (referência para cálculo de HE)
- **Praticada** = jornada EFETIVA (Grade de Ocorrências)
- **Horas Extras = Praticada − Padrão**

---

## 13. Erros Comuns

| Erro | Causa | Prevenção |
|------|-------|-----------|
| Verba com valor zero | Sem histórico salarial ou maior_remuneracao | Sempre preencher histórico |
| FGTS não calculado | multa_40 com justa_causa | Justa causa é incompatível com multa 40% |
| Correção errada | Índice desatualizado | Usar ADC 58: Tabela JT Unica Mensal + Selic |
| IR sobre dano moral | Campo IR marcado em verba indenizatória | Dano moral não incide IR (Súmula 498/STJ) |
| Férias em dobro não calculadas | Situação "Simples" ao invés de dobra=true | Verificar se sentença defere dobra |
| Aviso prévio com data errada | Data de demissão inclui projeção do AP | Usar data REAL da dispensa |
| FGTS incluído como verba | "FGTS + Multa 40%" tratado como condenação | FGTS é aba própria, não verba |
| Multa 467 como verba | Tratada como verba Expresso ou Manual | É checkbox na aba FGTS + reflexa automática |
