# Indenização Estabilidade (Gestante / Acidentária) — Estratégia PJE-Calc

> Fonte: vídeo "Como apurar uma estabilidade gestante no Pje Calc." (canal O Universo dos Cálculos Trabalhistas — Charles Henrique Hillebrand) — 5:28
> URL: https://youtu.be/IZJdwbZH9vo
> Indexado em NotebookLM: https://notebooklm.google.com/notebook/831264b3-a37d-4f4b-a4aa-d9bbac46333f
> Aplicável a Estabilidade Gestante (CF art. 10 II 'b' ADCT) e Estabilidade Acidentária (Lei 8.213/91 art. 118).

## 1. Fluxo no PJE-Calc Cidadão

1. Menu **Verbas** → clicar **"Indenização por dano material"** (verba já existe na lista — escolhida por facilidade de configuração)
2. Abrir **Parâmetros da Verba**
3. **Reflexos NÃO são automáticos** — criar cada um (13º, Férias+1/3, FGTS) via botão **Manual**, marcando "Verba Reflexa" e vinculando à Estabilidade

> Citação: *"Eu costumo utilizar aqui a indenização por dano material tá. Para mim é mais fácil"* (00:30)

## 2. Verba Principal — Estabilidade

| Campo | Valor |
|---|---|
| Nome | "Indenização por dano material" (no PJE-Calc Expresso) ou Manual com nome livre |
| Tipo | Indenização (indenizatória) |
| Modo de criação | Selecionada na lista; configurações em **"Calculado"** |
| Característica | Indenizatória |
| Ocorrência de Pagamento | **Mensal** (durante todo o período estabilitário) |
| Base de Cálculo | **Maior Remuneração** com **proporcionalização** ativa |
| Multiplicador | 1 |
| Divisor | 1 |
| Quantidade | 1 (já proporcionalizado nos parâmetros) |
| Período | **(data demissão + 1 dia)** até **(parto + 5 meses)** ou **(alta INSS + 12 meses)** |

## 3. Reflexos (todos manuais)

### 3.1 Férias + 1/3
| Campo | Valor |
|---|---|
| Modo | Manual |
| Tipo | Verba Reflexa (marcar checkbox) |
| Vinculação | Estabilidade (verba principal) |
| Divisor | 12 |
| Multiplicador | **1,33** (1 + 1/3) |
| Quantidade | 12 (inicial — ajustar via Ocorrências) |
| **Integralizar** | **SIM (obrigatório)** |
| Ocorrência efetiva | Apenas **mês final** do período de estabilidade |

### 3.2 13º Salário
| Campo | Valor |
|---|---|
| Modo | Manual |
| Tipo | Verba Reflexa |
| Vinculação | Estabilidade |
| Divisor | 12 |
| Multiplicador | 1 |
| Quantidade | 12 (inicial) |
| **Integralizar** | **SIM (obrigatório)** |
| Ocorrência efetiva | Apenas **mês final** do período |

### 3.3 FGTS
| Campo | Valor |
|---|---|
| Modo | Manual |
| Divisor | 100 |
| Multiplicador | 8 (FGTS 8%) **ou 11,2 (FGTS 8% + multa 40%)** conforme deferido |
| Ocorrência | **Mensal** todo o período |
| Integralizar | SIM |

> Citação: *"O PJe-Calc ele não apura fundo de garantia após a demissão de forma automática tá, então a gente calcula ela de forma manual"* (02:10)

## 4. Incidências

- **Verba Principal**: indenizatória — não há foco em INSS/IR no vídeo
- **FGTS**: tratado como reflexo manual obrigatório (não é a aba FGTS sistêmica)

## 5. Período de Cálculo

- **Início**: 1 dia após a data da demissão real
- **Término** (gestante): data do parto + 5 meses (CF art. 10, II, 'b', ADCT)
- **Término** (acidentária): data da alta INSS + 12 meses (Lei 8.213/91 art. 118)

Fórmula: **valor mensal = Maior Remuneração**, aplicando **proporcionalização nas "pontas"** (primeiro e último mês quebrados).

> Citação: *"a demissão ocorreu dia 31/12 então começa a partir do dia seguinte dia 1 de janeiro de 2024 até o dia 25/11 2024"*
>
> *"ele apou a estabilidade do dia 1 de Janeiro Um Dia Após a demissão até o término da estabilidade dia 25 de novembro de 2024, ele fez as pontas certinho"*

### 5.1 ⚠️ AJUSTE CRÍTICO — Data Término do Cálculo (Dados do Cálculo)

**A "Data Final" no menu Dados do Cálculo DEVE ser ≥ fim da estabilidade**.

Caso contrário, o PJE-Calc **limitaria a apuração à data da demissão** e a verba principal de Indenização não seria calculada após a rescisão. Sem este ajuste no nível geral, todo o resto não funciona.

| Campo | Antes do ajuste | Depois do ajuste |
|---|---|---|
| `dataInicioCalculo` | data ajuizamento ou início do contrato | (manter) |
| **`dataTerminoCalculo`** | data da rescisão | **= último dia da estabilidade** (parto+5m / alta+12m) |

> Citação: *"O PJe-Calc não apura fundo de garantia após a demissão de forma automática, então a gente calcula ela de forma manual"* (vídeo confirma que pós-demissão é zona "fora do alcance" automático do sistema)

### 5.2 Por que Indenização modo "Calculado" funciona

O PJE-Calc não gera verbas salariais automáticas após a demissão. Mas a rubrica **Indenização** em modo **Calculado** permite **inserção manual de período posterior ao contrato** sem bloqueio de validação. É o "truque" do vídeo.

## 6. Armadilhas (CRÍTICAS)

1. **FGTS pós-demissão NÃO é automático** — sempre manual
2. **"Integralizar" obrigatório** nos reflexos. Sem isso, o sistema puxa valor PROPORCIONAL em vez do salário integral.
   > *"A importância de integralizar lá no reflexo que ele puxa de forma automática o valor total. Se não tivesse marcado integralizar ele ia puxar o 4.000"* (04:15)
3. **Ocorrências de 13º e Férias**: após salvar os reflexos, voltar na aba **Ocorrências** e **desmarcar todos os meses intermediários**, deixando apenas o **mês final** — caso contrário paga duplicado.

## 7. Implicações para o automatizador

### A) Catálogo (`modules/classification.py`)
Adicionar entradas:
```python
"INDENIZACAO_ESTABILIDADE_GESTANTE": {
    "nome_pjecalc": "INDENIZAÇÃO POR DANO MATERIAL",
    "modo": "Expresso_Adaptado",  # usa verba existente
    "tipo": "Indenização",
    "caracteristica": "Comum",
    "ocorrencia": "Mensal",
    "base_calculo": "MAIOR_REMUNERACAO",
    "multiplicador": 1, "divisor": 1, "quantidade": 1,
    "proporcionalizar": True,
    "reflexos_manuais": ["FERIAS_TERCO", "DECIMO_TERCEIRO", "FGTS"],
},
"INDENIZACAO_ESTABILIDADE_ACIDENTARIA": {... idem, com período Lei 8.213/91 ...}
```

### B) `_configurar_parametros_verba` (Playwright)
Quando processar verba `tipo=Reflexa` que vincula a uma Estabilidade:
- Setar **`integralizarBase=SIM`** (já existe no código)
- Configurar **divisor=12**, multiplicador=1 (ou 1.33 férias), quantidade=12
- Após salvar Parâmetros, abrir aba **Ocorrências** da reflexa e desmarcar todos os meses exceto o último

### C) `extraction.py` — prompt
Quando detectar "estabilidade gestante" ou "estabilidade acidentária" na sentença:
- Calcular período automaticamente: gestante = demissão+1d até parto+5m; acidentária = alta INSS até alta+12m
- Sempre adicionar reflexos manuais 13º + Férias+1/3 + FGTS na prévia
- Marcar `proporcionalizar=true` na verba principal
