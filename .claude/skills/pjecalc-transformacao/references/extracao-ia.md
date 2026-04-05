# Fase 1-2: Ingestão e Extração com IA

## Índice

1. [Ingestão de PDF/texto](#1-ingestão-de-pdftexto)
2. [Extração com Claude API](#2-extração-com-claude-api)
3. [Modelo Pydantic de saída](#3-modelo-pydantic-de-saída)
4. [Prompt de extração](#4-prompt-de-extração)
5. [Rastreabilidade](#5-rastreabilidade)
6. [Confidence scores e HITL](#6-confidence-scores-e-hitl)

---

## 1. Ingestão de PDF/texto

O CalcMACHINE aceita duas formas de entrada:

- **PDF upload**: extração via pdfplumber (nativo) com OCR fallback via pytesseract (escaneados)
- **Texto colado**: recebido diretamente no formulário web

O pjecalc-agente deve suportar ambas. Para PDFs:

```python
import pdfplumber

def extrair_texto_pdf(caminho_pdf: str) -> str:
    """Extrai texto de PDF nativo. Retorna texto concatenado de todas as páginas."""
    texto_paginas = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                texto_paginas.append(texto)

    texto_completo = "\n".join(texto_paginas)

    # Se muito pouco texto, provavelmente é escaneado → OCR
    if len(texto_completo.strip()) < 100:
        return extrair_texto_ocr(caminho_pdf)

    return texto_completo

def extrair_texto_ocr(caminho_pdf: str) -> str:
    """Fallback OCR para PDFs escaneados."""
    import pytesseract
    from pdf2image import convert_from_path

    imagens = convert_from_path(caminho_pdf, dpi=300)
    textos = []
    for img in imagens:
        texto = pytesseract.image_to_string(img, lang="por")
        textos.append(texto)
    return "\n".join(textos)
```

## 2. Extração com Claude API

O CalcMACHINE usa Gemini 2.5 Flash. O pjecalc-agente usa Claude com estas vantagens:

- **Structured Outputs** (response_format com Pydantic) para saída tipada
- **temperature=0** para determinismo na extração
- **Rastreabilidade**: cada campo traz o trecho exato da sentença

```python
import anthropic
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from enum import Enum

client = anthropic.Anthropic()

def extrair_sentenca(texto: str) -> dict:
    """Extrai dados estruturados de uma sentença trabalhista usando Claude."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        temperature=0,
        messages=[{
            "role": "user",
            "content": f"{PROMPT_EXTRACAO}\n\n<sentenca>\n{texto}\n</sentenca>"
        }]
    )
    # Parse do JSON retornado
    import json
    conteudo = response.content[0].text
    # Extrair JSON do response (pode vir envolto em ```json ... ```)
    if "```json" in conteudo:
        conteudo = conteudo.split("```json")[1].split("```")[0]
    return json.loads(conteudo)
```

## 3. Modelo Pydantic de saída

O JSON de saída deve seguir o contrato definido em `contrato-json.md`. Aqui está o modelo
Pydantic correspondente:

```python
class TipoRescisao(str, Enum):
    SEM_JUSTA_CAUSA = "SEM_JUSTA_CAUSA"
    JUSTA_CAUSA = "JUSTA_CAUSA"
    PEDIDO_DEMISSAO = "PEDIDO_DEMISSAO"
    CULPA_RECIPROCA = "CULPA_RECIPROCA"
    RESCISAO_INDIRETA = "RESCISAO_INDIRETA"
    APOSENTADORIA = "APOSENTADORIA"
    FALECIMENTO = "FALECIMENTO"
    CONTRATO_PRAZO = "CONTRATO_PRAZO"

class CampoExtraido(BaseModel):
    """Cada campo extraído carrega rastreabilidade."""
    valor: str
    texto_referencia: Optional[str] = Field(None, description="Trecho exato da sentença")
    confidence: float = Field(1.0, ge=0, le=1)

class VerbaExtraida(BaseModel):
    nome: str
    natureza: str  # SALARIAL | INDENIZATORIA | MISTA
    incide_fgts: bool = True
    incide_inss: bool = True
    incide_ir: bool = True
    lancamento: str = "EXPRESSO"  # EXPRESSO | MANUAL
    valor_base: Optional[float] = None
    texto_referencia: Optional[str] = None
    confidence: float = 1.0

class HonorarioExtraido(BaseModel):
    tipo: str = "ADVOCATICIOS"
    tipo_devedor: str = "RECLAMADO"
    nome_credor: str = "Advogado do Reclamante"
    aliquota: float
    exigibilidade_suspensa: bool = False

class SentencaExtraida(BaseModel):
    """Modelo completo de extração — contrato entre IA e automação."""
    numero: str
    digito: str
    ano: str
    regiao: str
    vara: str
    reclamante: str
    reclamado: str
    estado: str  # índice numérico (CE=5, SP=24)
    municipio: str
    data_admissao: str  # ISO YYYY-MM-DD
    data_demissao: Optional[str] = None
    data_ajuizamento: Optional[str] = None
    data_final_calculo: Optional[str] = None
    remuneracao: str
    tipo_rescisao: TipoRescisao
    verbas: List[str]  # nomes das verbas deferidas
    verbas_detalhadas: List[VerbaExtraida] = []
    honorarios: List[HonorarioExtraido] = []
    # Configurações booleanas (strings "sim"/"não")
    aviso_indenizado: str = "não"
    calcular_multa_fgts: str = "não"
    calcular_seguro_desemprego: str = "não"
    aplicar_prescricao: str = "não"
    # Observações
    observacoes: Optional[str] = None
    confidence_geral: float = 1.0
```

## 4. Prompt de extração

O prompt deve ser específico para sentenças trabalhistas brasileiras e orientar o modelo
sobre o formato de saída esperado:

```python
PROMPT_EXTRACAO = """
Você é um especialista em liquidação de sentenças trabalhistas brasileiras.
Extraia TODOS os dados necessários para preencher o PJe-Calc Cidadão a partir
da sentença abaixo.

REGRAS DE EXTRAÇÃO:

1. NÚMERO DO PROCESSO: Desmembre em numero (7 dígitos), digito (2), ano (4),
   regiao (2), vara (4). Exemplo: 0000081-12.2026.5.07.0003

2. DATAS: Sempre no formato ISO YYYY-MM-DD. Extraia:
   - data_admissao
   - data_demissao
   - data_ajuizamento (se disponível)
   - data_final_calculo (projeção com aviso prévio, se aplicável)

3. VERBAS: Liste TODAS as verbas deferidas. Para cada uma, determine:
   - natureza (SALARIAL/INDENIZATORIA/MISTA)
   - incidências FGTS/INSS/IR
   - se o PJe-Calc calcula automaticamente (EXPRESSO) ou valor fixo (MANUAL)

4. TIPO DE RESCISÃO: Classifique exatamente como um dos valores:
   SEM_JUSTA_CAUSA, JUSTA_CAUSA, PEDIDO_DEMISSAO, CULPA_RECIPROCA,
   RESCISAO_INDIRETA, APOSENTADORIA, FALECIMENTO, CONTRATO_PRAZO

5. ESTADO: Converta para índice numérico (AC=0, AL=1, AM=2, AP=3, BA=4,
   CE=5, DF=6, ES=7, GO=8, MA=9, MG=10, MS=11, MT=12, PA=13, PB=14,
   PE=15, PI=16, PR=17, RJ=18, RN=19, RO=20, RR=21, RS=22, SC=23,
   SP=24, SE=25, TO=26)

6. REMUNERAÇÃO: Último salário em formato numérico (ex: "2163.00")

7. CONFIGURAÇÕES BOOLEANAS: Use strings "sim" ou "não" (não true/false):
   - aviso_indenizado, calcular_multa_fgts, calcular_seguro_desemprego,
     aplicar_prescricao, ajustar_ocorrencias_fgts, marcar_ferias

8. HONORÁRIOS: SEMPRE como array, mesmo se apenas um. Inclua tipo, aliquota,
   tipo_devedor, exigibilidade_suspensa.

9. CORREÇÃO MONETÁRIA: Identifique o regime determinado pela sentença
   (IPCA-E, SELIC, TR, e aplicação da Lei 14.905/2024)

10. CONFIDENCE: Para cada campo, atribua um score de 0 a 1 indicando certeza.
    Campos inferidos ou ambíguos devem ter confidence < 0.7.

11. TEXTO_REFERENCIA: Para cada campo extraído, inclua o trecho exato da
    sentença que fundamenta o valor extraído.

Retorne APENAS JSON válido, sem explicações adicionais.
"""
```

## 5. Rastreabilidade

Cada campo extraído deve carregar o trecho da sentença que o fundamenta. Isso é essencial
para o HITL — o revisor precisa ver DE ONDE veio cada valor:

```python
# Exemplo de campo com rastreabilidade
{
    "data_admissao": "2024-01-10",
    "data_admissao_ref": "contrato de trabalho vigente de 10/01/2024 a 16/01/2026",
    "data_admissao_confidence": 0.95,

    "remuneracao": "2163.00",
    "remuneracao_ref": "salário mensal de R$ 2.163,00",
    "remuneracao_confidence": 0.98
}
```

## 6. Confidence scores e HITL

O agente PAUSA e solicita revisão humana quando:

1. Qualquer campo com `confidence < 0.7`
2. Inconsistência: tipo rescisão vs verbas (ex: justa causa + aviso prévio)
3. Mais de 3 verbas não mapeáveis para o PJe-Calc
4. Valor total diverge > 15% do mencionado na sentença
5. Data admissão posterior à data demissão
6. Tipo de rescisão ambíguo ou ausente
7. Processo com reclamados múltiplos
8. Sentença menciona "critério diverso" para FGTS/INSS

Estes gatilhos são obrigatórios — a automação NÃO deve prosseguir sem aprovação humana
quando qualquer um é ativado.
