# Resumos do Manual Oficial PJE-Calc v1.0

Fonte: Manual do Usuário PJe-Calc, CSJT/TRT8 (117 páginas)
Extraído: seções operacionalmente críticas para automação precisa

---

## Seção 1 — O que é o PJE-Calc

O **PJE-Calc** é o módulo de cálculos integrado ao PJE (Processo Judicial Eletrônico) para liquidação de sentença trabalhista. Desenvolvido pelo TRT8 e disponibilizado a todos os TRTs pelo CSJT.

**Versões:**
- PJE-Calc integrado: acessado dentro do PJE pelo servidor/advogado
- **PJE-Calc Cidadão**: versão standalone para download, usada por advogados e partes fora do PJE

**Arquivo de saída:** `.PJC` (ZIP contendo XML ISO-8859-1) — importável no PJE-Calc integrado

---

## Seção 2 — Tipos de Lançamento de Verbas

### Lançamento Expresso
- Para verbas predefinidas no sistema (catálogo completo)
- Formulário simplificado: período, base de cálculo, percentual
- O sistema calcula automaticamente incidências (FGTS, INSS, IR)
- **Usar sempre que possível** — menos erros, mais rápido

### Lançamento Manual
- Para verbas não previstas no catálogo Expresso
- Formulário completo: usuário define todas as incidências manualmente
- Necessário para: gratificações especiais, indenizações atípicas, verbas de CCT/ACT

### Lançamento de Reflexas
- Verbas que dependem de outras (ex: 13º sobre horas extras)
- Vinculadas à verba principal via campo "Verba Principal"
- Calculadas automaticamente pelo PJE-Calc ao liquidar

---

## Seção 3 — Parâmetros do Cálculo

### Dados Obrigatórios
1. Número do processo (formato: NNNNNNN-DD.AAAA.J.RR.VVVV)
2. Estado e Município da vara
3. Data de admissão e demissão
4. Tipo de rescisão
5. Maior remuneração (base de cálculo para rescisórias)
6. Pelo menos 1 verba

### Regime de trabalho
- Tempo Integral: divisor 220h/mês (padrão para horário de 44h/sem)
- Tempo Parcial (pré-Reforma): máx. 26h/sem, divisor proporcional
- Tempo Parcial Reforma (Lei 13.467/2017): máx. 30h sem horas extras ou 26h com horas extras

### Prescrição
- Campo "Prescrição Quinquenal": marcar TRUE para contratos vigentes/recentes
- FGTS: prescrição trintenária foi substituída por quinquenal (STF RE 709.212) — ainda marcar TRUE para período anterior
- O PJE-Calc ajusta automaticamente o período calculado com base na prescrição marcada

---

## Seção 4 — Correção Monetária e Juros (ADC 58/STF)

### Regra vigente (ADC 58, julgada em 18/12/2020)
Para empregadores privados:
- **Correção pré-judicial** (até a citação): IPCA-E
- **Correção judicial + juros** (após citação): SELIC simples

### Entidades da Fazenda Pública (EC 113/2021)
Para União, Estados, Municípios, autarquias, fundações públicas:
- Correção: Manual de Cálculos da Justiça Federal
- Precatórios: art. 100 CF + EC 113/2021
- Não se aplica SELIC para entidade pública

### Configuração no PJE-Calc
- Campo "Índice de Correção": selecionar "IPCA-E" (privado) ou "Manual de Cálculos da JF" (público)
- Campo "Taxa de Juros": "SELIC" (após EC 113/2021 para todos) ou "Juros Padrão" (1% a.m.)

---

## Seção 5 — FGTS

### Configuração
- **Alíquota**: 8% (padrão), 2% (aprendiz), 8% (doméstico)
- **Multa 40%**: marcar quando rescisão sem justa causa ou rescisão indireta
- **Multa 20%**: culpa recíproca ou força maior (muito raro)
- **Art. 467 CLT**: multa de 50% sobre parcelas rescisórias incontroversas não pagas

### Incidência por verba
- Incide: saldo de salário, horas extras, adicional noturno, adicional de insalubridade/periculosidade, aviso prévio indenizado (posição majoritária)
- Não incide: dano moral/material, multas art. 477/467, férias indenizadas, vale transporte

### Depósitos em atraso
- Informar em campo separado "FGTS Não Depositado" com período e valores
- Diferente das verbas — é calculado sobre a remuneração bruta dos períodos em atraso

---

## Seção 6 — Honorários Advocatícios

### Tipos (pós-Reforma Trabalhista)
- **Sucumbência** (art. 791-A CLT): 5% a 15% do valor da condenação
- **Honorários periciais**: valor fixo determinado na sentença

### Configuração no PJE-Calc
- **Aba "Honorários"**: apenas honorários advocatícios de sucumbência
- **Aba "Honorários Periciais"**: perito, engenheiro, médico, etc. — campo SEPARADO
- Parte devedora: pode ser reclamante, reclamado, ou ambos (sucumbência recíproca)
- Base de cálculo: "valor bruto" ou "valor líquido" conforme sentença

### Honorários anteriores à Reforma (antes de 11/11/2017)
- Apenas com assistência sindical (Súmula 219/TST e 329/TST)
- 15% sobre o valor da condenação (se deferidos)

---

## Seção 7 — Contribuição Previdenciária (INSS)

### Configuração
- Campo "Período para Apuração": meses individuais de apuração
- Empregado: tabela progressiva INSS (13,5% máx. após Reforma Previdenciária/2019)
- Empregador: 20% sobre parcelas salariais
- Prazo de recolhimento: via folha mensal simulada pelo PJE-Calc

### Verbas com incidência INSS
- Incide: saldo de salário, horas extras, adicionais, 13º, aviso prévio trabalhado
- Não incide: dano moral/material, multas, vale transporte, férias indenizadas (posição divergente)

---

## Seção 8 — Imposto de Renda

### Configuração
- Campo "Apurar IR": marcar TRUE quando a sentença determinar retenção
- "Regime de Caixa": tributação exclusiva na fonte, mês a mês
- "Meses tributáveis": número de meses para distribuição da base de cálculo
- Tabela progressiva IRPF: aplicada pelo PJE-Calc conforme ano-calendário

### Verbas sujeitas a IR
- Incide: saldo de salário, horas extras, adicionais, 13º, aviso prévio, comissões
- Não incide: dano moral (Súmula 498/STJ), indenizações, verbas de natureza indenizatória

---

## Seção 9 — Liquidação e Exportação

### Ordem de preenchimento recomendada
1. Parâmetros do Cálculo (dados do processo, contrato)
2. Histórico Salarial (se houver variações)
3. Faltas (se houver)
4. Verbas (Expresso primeiro, depois Manual)
5. FGTS
6. Contribuição Social (INSS)
7. Imposto de Renda
8. Honorários Advocatícios
9. Honorários Periciais
10. Multas e Indenizações (dano moral/material se não lançados como verbas)
11. Custas Processuais
12. Correção, Juros e Multa
13. Liquidar (Operações > Liquidar)
14. Exportar .PJC

### Liquidação
- Operações > Liquidar: confirmar para executar o cálculo
- Mensagem de sucesso: "Operação realizada com sucesso"
- Aguardar processamento AJAX antes de exportar

### Exportação
- Operações > Exportar: gera arquivo .PJC
- .PJC = ZIP contendo XML ISO-8859-1
- Importar no PJE integrado: Cálculos > Importar Cálculo Externo
