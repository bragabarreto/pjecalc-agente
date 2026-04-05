# Fase 3: Validação + HITL (Human-in-the-Loop)

## Índice

1. [Visão geral](#1-visão-geral)
2. [Regras de validação](#2-regras-de-validação)
3. [Interface HITL](#3-interface-hitl)
4. [Implementação da validação](#4-implementação-da-validação)

---

## 1. Visão geral

Após a extração com IA (Fase 2), o JSON gerado DEVE ser validado e revisado por humano
antes de iniciar a automação. Nunca automatizar com dados não validados — erros silenciosos
no PJe-Calc são muito piores do que atrasar o processo para revisão.

O CalcMACHINE implementa isso em duas camadas: validação programática (validar_json.js no
frontend + espelhada no backend) e revisão humana (formulário editável com cards colapsáveis).

## 2. Regras de validação

### 2.1 Campos obrigatórios (sempre)

- `data_admissao` — sem ela o PJe-Calc não calcula nenhuma verba
- `remuneracao` — deve ser > 0
- `estado` — índice numérico (0-26)
- `municipio` — texto não vazio

### 2.2 Campos obrigatórios (condicionais)

- `data_demissao` — obrigatória quando há: aviso prévio, férias, saldo de salário, multa 477
- Histórico salarial — obrigatório quando há verbas de jornada (HE, adicional noturno)
- Cartão de ponto — obrigatório quando verba tem `origem: "importar"`

### 2.3 Consistência de datas

- `data_demissao > data_admissao` (contrato com duração positiva)
- `data_final_calculo >= data_demissao` (projeção do aviso prévio)
- `data_ajuizamento >= data_demissao` (em geral)
- `data_final >= data_inicial` em todas as verbas individuais

### 2.4 Prescrição quinquenal

Se prescrição está habilitada:
```
data_inicial_verba >= data_ajuizamento - 5 anos
```
Verbas com data inicial anterior são prescritas e devem gerar aviso.

### 2.5 Cruzamento tipo rescisão × verbas

| Tipo rescisão | Aviso prévio | Multa 40% FGTS | Seguro desemp. | Multa 477 |
|---------------|:---:|:---:|:---:|:---:|
| Sem justa causa | ✓ | ✓ | ✓ | ✓ |
| Rescisão indireta | ✓ | ✓ | ✓ | ✓ |
| Pedido demissão | ✗ | ✗ | ✗ | ✓ |
| Justa causa | ✗ | ✗ | ✗ | ✗ |
| Culpa recíproca | ✗ | 20% | ✗ | ✗ |

Verbas incompatíveis com o tipo de rescisão geram **erro bloqueante**, não aviso.

### 2.6 Validação CNJ

O número do processo segue o padrão NNNNNNN-DD.AAAA.J.TT.OOOO. O dígito verificador
usa módulo 97 com segmento fixo "5" (Justiça do Trabalho):

```python
def validar_cnj(numero: str, digito: str, ano: str, regiao: str, vara: str) -> bool:
    """Valida dígito verificador do número CNJ."""
    num = numero + ano + "5" + regiao + vara + "00"
    resto = int(num) % 97
    digito_calc = 97 - resto
    return int(digito) == digito_calc
```

Se o dígito não confere, gera **aviso** (não bloqueante) — alguns processos fictícios ou
de teste podem ter dígito inválido.

### 2.7 Validação numérica

- Remuneração > 0 e < 1.000.000 (valor plausível)
- Saldo FGTS >= 0
- Alíquota honorários entre 5% e 20%
- Valores de verbas >= 0

## 3. Interface HITL

O CalcMACHINE organiza a revisão em cards colapsáveis (Bootstrap). O pjecalc-agente deve
oferecer interface equivalente com:

### 3.1 Seções obrigatórias

1. **Dados do Processo** — número CNJ, partes, localização
2. **Datas e Remuneração** — admissão, demissão, ajuizamento, projeção AP, salário
3. **Verbas Rescisórias** — checkboxes das verbas deferidas
4. **Configurações** — checkboxes booleanos (prescrição, aviso, FGTS, etc.)
5. **Insalubridade / Periculosidade** — se aplicável
6. **Verbas Mensais** — gratificações, adicionais fixos
7. **Jornada** — horas extras, adicional noturno, intrajornada
8. **Honorários** — array editável (tipo, alíquota, devedor)
9. **Danos Morais** — se aplicável
10. **Contribuição Social** — alíquotas, SAT, datas

### 3.2 Indicadores visuais

- Campos com `confidence < 0.7`: destacar com borda amarela/vermelha
- Campos alterados manualmente: indicar com ícone de edição
- Erros de validação: exibir inline com texto vermelho
- Avisos (não bloqueantes): exibir inline com texto amarelo

### 3.3 Ações disponíveis

- **Salvar** — persiste JSON no banco
- **Validar** — executa todas as regras e exibe resultado
- **Executar Automação** — só habilitado se validação passou (0 erros bloqueantes)
- **Revisar com IA** — reenviar para Claude com instruções específicas de correção

## 4. Implementação da validação

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class ResultadoValidacao:
    erros: List[str] = field(default_factory=list)      # bloqueantes
    avisos: List[str] = field(default_factory=list)      # não bloqueantes

    @property
    def valido(self) -> bool:
        return len(self.erros) == 0

def validar_json_sentenca(dados: dict) -> ResultadoValidacao:
    """Valida o JSON da sentença antes da automação."""
    r = ResultadoValidacao()

    # Obrigatórios
    for campo in ["data_admissao", "remuneracao", "estado", "municipio"]:
        if not dados.get(campo):
            r.erros.append(f"Campo obrigatório ausente: {campo}")

    # Remuneração
    rem = float(dados.get("remuneracao", 0))
    if rem <= 0:
        r.erros.append("Remuneração deve ser > 0")
    if rem > 1_000_000:
        r.avisos.append(f"Remuneração muito alta: {rem}")

    # Datas
    if dados.get("data_demissao") and dados.get("data_admissao"):
        if dados["data_demissao"] < dados["data_admissao"]:
            r.erros.append("Data demissão anterior à data admissão")

    # Verbas que exigem data_demissao
    verbas_exigem = ["AVISO PRÉVIO", "FÉRIAS + 1/3", "SALDO DE SALÁRIO",
                     "MULTA DO ARTIGO 477 DA CLT"]
    if any(v in dados.get("verbas", []) for v in verbas_exigem):
        if not dados.get("data_demissao"):
            r.erros.append("Data demissão obrigatória para as verbas selecionadas")

    # Cruzamento rescisão × verbas
    tipo = dados.get("observacoes", {}).get("tipo_rescisao", "")
    verbas = dados.get("verbas", [])
    if tipo == "JUSTA_CAUSA" and "AVISO PRÉVIO" in verbas:
        r.erros.append("Justa causa não é compatível com aviso prévio")
    if tipo == "PEDIDO_DEMISSAO" and "AVISO PRÉVIO" in verbas:
        r.avisos.append("Pedido de demissão normalmente não tem aviso prévio indenizado")

    # CNJ
    if all(dados.get(c) for c in ["numero", "digito", "ano", "regiao", "vara"]):
        if not validar_cnj(dados["numero"], dados["digito"], dados["ano"],
                          dados["regiao"], dados["vara"]):
            dig_calc = 97 - (int(dados["numero"] + dados["ano"] + "5" +
                               dados["regiao"] + dados["vara"] + "00") % 97)
            r.avisos.append(f"Dígito CNJ: esperado {dig_calc:02d}, informado {dados['digito']}")

    return r
```
