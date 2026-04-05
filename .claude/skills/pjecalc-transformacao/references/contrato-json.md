# Contrato JSON: O Formato que Conecta IA ↔ Automação

## Índice

1. [Visão geral](#1-visão-geral)
2. [Esquema completo](#2-esquema-completo)
3. [Conversões obrigatórias](#3-conversões-obrigatórias)
4. [Tabela de estados](#4-tabela-de-estados)
5. [Exemplo real](#5-exemplo-real)

---

## 1. Visão geral

O JSON da sentença é o **contrato de dados** entre a Fase 2 (extração com IA) e a Fase 5
(automação Playwright). A IA gera o JSON; a automação o consome. Qualquer incompatibilidade
de formato causa falhas silenciosas no PJe-Calc.

O formato segue o padrão do CalcMACHINE: campos flat (não aninhados demais), datas ISO no
JSON (convertidas para BR na automação), booleanos como strings "sim"/"não", estado como
índice numérico.

## 2. Esquema completo

```json
{
  // === PROCESSO ===
  "numero": "0000081",         // 7 dígitos, com zeros à esquerda
  "digito": "12",              // 2 dígitos verificadores (CNJ mod 97)
  "ano": "2026",               // 4 dígitos
  "regiao": "07",              // 2 dígitos (07 = TRT7 Ceará)
  "vara": "0003",              // 4 dígitos

  // === PARTES ===
  "reclamante": "GIDEON DE SOUSA DAVI",
  "reclamado": "M & R MODAS LTDA",

  // === LOCALIZAÇÃO ===
  "estado": "5",               // ÍNDICE NUMÉRICO (ver tabela abaixo)
  "municipio": "Fortaleza",

  // === VALORES ===
  "valor_causa": "16246.53",   // float como string
  "remuneracao": "2163.00",    // último salário
  "saldo_fgts": "455.04",      // saldo FGTS existente

  // === DATAS (ISO YYYY-MM-DD) ===
  "data_admissao": "2024-01-10",
  "data_demissao": "2026-01-16",
  "data_ajuizamento": "2026-01-16",
  "data_final_calculo": "2026-02-21",  // com projeção do aviso prévio

  // === VERBAS DEFERIDAS (nomes) ===
  "verbas": [
    "SALDO DE SALÁRIO",
    "AVISO PRÉVIO",
    "FÉRIAS + 1/3",
    "13º SALÁRIO",
    "MULTA DO ARTIGO 477 DA CLT"
  ],

  // === CONFIGURAÇÕES BOOLEANAS (strings "sim"/"não") ===
  "aplicar prescricao": "não",
  "aviso indenizado": "sim",
  "calcular multa do art. 467": "não",
  "ajustar ocorrencias fgts": "sim",
  "calcular FGTS sobre salários pagos": "não",
  "calcular multa do FGTS": "sim",
  "calcular_seguro_desemprego": "sim",
  "cadastrar historico": "não",
  "usar_salario_minimo": "não",
  "marcar ferias": "sim",
  "lancar_deducao": "não",

  // === ADICIONAIS ===
  "insalubridade": { "calcular": false },
  "periculosidade": { "calcular": false },

  // === VERBAS MENSAIS (array, pode ser vazio) ===
  "verbas_mensais": [],

  // === JORNADA (array, pode ser vazio) ===
  "jornada": [],

  // === HONORÁRIOS (SEMPRE array, mesmo se único) ===
  "honorarios": [
    {
      "calcular": true,
      "tipo": "ADVOCATICIOS",
      "tipo_devedor": "RECLAMADO",
      "nome_credor": "Advogado do Reclamante",
      "aliquota": 15,
      "valor": 0,
      "exigibilidade_suspensa": false
    }
  ],

  // === DANOS MORAIS ===
  "danos_morais": { "calcular": false },

  // === CONTRIBUIÇÃO SOCIAL ===
  "contribuicao_social": {
    "calcular": true,
    "aliquota_empregador": 20,
    "aliquota_sat": 3,
    "optante_simples": false,
    "data_inicial": "2024-01-10",
    "data_final": "2026-02-21"
  },

  // === 13º SALÁRIO ===
  "decimos_terceiros_selecionados": [
    { "ano": 2025, "avos": 12 },
    { "ano": 2026, "avos": 2 }
  ],

  // === FÉRIAS ===
  "ferias_selecionadas": [
    { "periodo": "2024/2025", "tipo": "vencidas_dobro" },
    { "periodo": "2025/2026", "tipo": "simples" },
    { "periodo": "2026", "tipo": "proporcionais", "avos": 1 }
  ],

  // === CORREÇÃO MONETÁRIA ===
  "correcao_monetaria": {
    "pre_judicial": "IPCA-E",
    "ajuizamento_ate_29082024": "SELIC",
    "apos_30082024": "IPCA_SELIC_SUBTRAI",
    "lei_14905_2024": true
  },

  // === OBSERVAÇÕES ===
  "observacoes": {
    "tipo_rescisao": "RESCISAO_INDIRETA",
    "aviso_previo_dias": 36,
    "data_saida_ctps": "2026-02-21",
    "artigo_rescisao": "art. 483, d, CLT",
    "decisao": "PROCEDENTES EM PARTE"
  }
}
```

## 3. Conversões obrigatórias

Quando a automação Playwright consome o JSON para preencher o PJe-Calc:

| Campo no JSON | Formato JSON | Formato PJe-Calc | Conversão |
|---------------|-------------|-------------------|-----------|
| Datas | `YYYY-MM-DD` | `DD/MM/YYYY` | `iso_para_br()` |
| Valores monetários | `1234.56` (float) | `1.234,56` | `fmt_br()` |
| Estado | `"5"` (índice) | Seleção no dropdown | `selecionar_dropdown()` |
| Booleanos | `"sim"` / `"não"` | checkbox checked/unchecked | Comparar e clicar |
| Honorários | Array | Iterar e adicionar cada | Loop com `aguardar_ajax()` |

**Nunca enviar formato ISO ou ponto decimal para o PJe-Calc.** A conversão deve ser feita
pela camada de automação, não pela IA.

## 4. Tabela de estados (UF → índice)

O PJe-Calc usa índice numérico no dropdown de estado:

| Índice | UF | Índice | UF | Índice | UF |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 | AC | 9 | MA | 18 | RJ |
| 1 | AL | 10 | MG | 19 | RN |
| 2 | AM | 11 | MS | 20 | RO |
| 3 | AP | 12 | MT | 21 | RR |
| 4 | BA | 13 | PA | 22 | RS |
| 5 | CE | 14 | PB | 23 | SC |
| 6 | DF | 15 | PE | 24 | SP |
| 7 | ES | 16 | PI | 25 | SE |
| 8 | GO | 17 | PR | 26 | TO |

## 5. Exemplo real

Sentença processada (Processo 0000081-12.2026.5.07.0003):

- **Tipo**: Rescisão Indireta (art. 483, d, CLT)
- **Contrato**: 10/01/2024 a 16/01/2026 (2 anos, 6 dias)
- **Salário**: R$ 2.163,00
- **Aviso prévio**: 36 dias (3 anos × 3 dias = 6 + 30 base)
- **Data projetada**: 21/02/2026

Verbas: saldo salário, aviso prévio indenizado, férias (vencidas em dobro + simples +
proporcionais) + 1/3, 13º salário, multa 477, FGTS + multa 40%, seguro-desemprego.

Honorários: advocatícios 15% sobre valor bruto da condenação, a cargo do reclamado.

Contribuição social: alíquota patronal 20%, SAT 3%.

Correção: IPCA-E (pré-judicial), SELIC (pós-ajuizamento até 29/08/2024),
IPCA-E + SELIC subtraído (após 30/08/2024, Lei 14.905/2024).
