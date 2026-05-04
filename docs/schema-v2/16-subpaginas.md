# Schema — Sub-páginas (Ocorrências, parametrizar-fgts, parametrizar-inss)

Estas sub-páginas do PJE-Calc são acessadas a partir das páginas principais
e contêm tabelas mensais detalhadas. O schema da prévia trata cada uma
diferentemente conforme o nível de controle que o usuário precisa.

## 1. Ocorrências da Verba (parametrizar-ocorrencia.jsf)

### Quando o agente automatiza (default)
Para a maioria das verbas, a tabela de Ocorrências é gerada automaticamente
pelo PJE-Calc com base nos parâmetros da verba (período, base, fórmula).
A automação clica "Gerar Ocorrências" e depois aplica Alteração em Lote
quando há valor informado.

**Não há campos na prévia para isso** — é fluxo automático.

### Quando a prévia controla (`ocorrencias_override`)
Quando a sentença determina valores específicos mês a mês (raro):

```json
{
  "verbas_principais": [
    {
      "id": "v01",
      "ocorrencias_override": {
        "modo": "valores_mensais",
        "valores": [
          {"mes": "04/2025", "valor_devido": 5000.00, "valor_pago": 0.00},
          {"mes": "05/2025", "valor_devido": 4500.00, "valor_pago": 0.00},
          {"mes": "06/2025", "valor_devido": 4500.00, "valor_pago": 1000.00}
        ]
      }
    }
  ]
}
```

Para casos com **valor uniforme** durante todo o período da verba (caso típico
de indenizações por dano moral, dispensa discriminatória), a prévia usa
`parametros.valor_devido.valor_informado_brl` (informa o valor mensal único)
e a automação aplica em LOTE no header da página de Ocorrências
(`formulario:devido` + clicar Alterar). Isso evita preencher cada linha.

### Modo de aplicação ("alteracao_em_lote" vs "valores_mensais")

```json
{
  "ocorrencias_modo": "alteracao_em_lote",  // default
  // ou
  "ocorrencias_modo": "valores_mensais"     // só quando há tabela na sentença
}
```

| Modo | Quando usar | Como o agente preenche |
|---|---|---|
| `alteracao_em_lote` | Valor mensal uniforme (ex: indenização R$5.000/mês) | Preenche Header (Devido R$ 5000) + clica Alterar |
| `valores_mensais` | Cada mês tem valor diferente | Preenche `formulario:listagem:N:valorDevido` linha a linha |

A automação infere automaticamente qual modo usar baseado em `parametros.valor` (CALCULADO vs INFORMADO) e em `ocorrencias_override`.

## 2. parametrizar-fgts.jsf (sub-página do FGTS)

### Estrutura

Página com tabela de **recolhimentos mensais existentes** + Alteração em Lote.

```
formulario:dataInicialInputDate / dataFinalInputDate    (lote: período)
formulario:valorBase / valorRecolhido                   (lote: valores)
formulario:recuperar (button "Recuperar")               (recupera valores do histórico)
formulario:listagem:N:baseHistorico                     (linha N: histórico salarial)
formulario:listagem:N:baseVerba                         (linha N: verba referência)
formulario:listagem:N:depositado                        (linha N: valor depositado)
formulario:listagem:N:selecionar                        (linha N: checkbox)
formulario:regerar (button "Regerar")
formulario:salvar (button "Salvar")
```

### Schema da prévia

A maioria dos casos NÃO precisa editar essa tabela — o PJE-Calc puxa os valores
do histórico salarial automaticamente. A prévia apenas precisa informar:

```json
{
  "fgts": {
    "...": "...",
    "recolhimentos_existentes": [
      {
        "tipo": "DEPOSITO_REGULAR",
        "competencia_inicio": "01/2024",
        "competencia_fim": "12/2024",
        "valor_total_depositado_brl": 2400.00,
        "fonte": "INFORMADO_PELA_PARTE"
      }
    ]
  }
}
```

⚠️ **Nota**: o sistema só pré-carrega valores nesta sub-página quando o
usuário já tem histórico salarial cadastrado. A automação usa o botão
"Recuperar" automaticamente.

**Quando a prévia precisa editar**: apenas se o reclamante já recebeu saques
do FGTS durante o contrato (multa rescisória prévia, doença grave, etc.) e
esses valores devem ser deduzidos. Ainda assim, a edição é raríssima.

## 3. parametrizar-inss.jsf (sub-página do INSS)

### Estrutura

```
formulario:dataInicialInputDate / dataFinalInputDate / salariosPago  (lote)
formulario:recuperarDevidos (button)                                  (puxa histórico→CS)
formulario:copiarDevidos (button)                                     (Devidos→Pagos)
formulario:listagemOcorrenciasDevidos:N:baseHistoricoDevido (text)   (vínculo por linha)
formulario:listagemOcorrenciasDevidos:N:selecionarDevido (checkbox)
formulario:regerar (button)
formulario:salvar (button)
```

### Vínculo Histórico → CS

⚠️ **Importante**: cada ocorrência da CS sobre Salários Devidos precisa estar
**vinculada a um histórico salarial específico**. Sem isso, o cálculo da CS
falha com pendência:
> "Histórico Salarial X não possui valor cadastrado para todas as ocorrências
> da Contribuição Social sobre Salários Devidos"

### Schema da prévia

```json
{
  "contribuicao_social": {
    "...": "...",
    "vinculacao_historicos_devidos": {
      "modo": "automatica",
      "...": "..."
    }
  }
}
```

**Modos de vinculação**:

| Modo | Comportamento |
|---|---|
| `automatica` (default) | Agente clica "Recuperar Devidos" + "Copiar Devidos→Pagos" automaticamente. Funciona para 90% dos casos |
| `manual_por_periodo` | Usuário define qual histórico cobre quais meses (raro) |

### Modo `manual_por_periodo`

```json
{
  "vinculacao_historicos_devidos": {
    "modo": "manual_por_periodo",
    "intervalos": [
      {
        "competencia_inicial": "09/2020",
        "competencia_final": "04/2024",
        "historico_nome": "SALÁRIO REGISTRADO",
        "valor_base_brl": 1200.00
      },
      {
        "competencia_inicial": "05/2024",
        "competencia_final": "04/2025",
        "historico_nome": "ÚLTIMA REMUNERAÇÃO",
        "valor_base_brl": 1702.14
      }
    ]
  }
}
```

A automação usa Alteração em Lote por intervalo (preenche dataInicialInputDate
+ dataFinalInputDate + salariosPago + clica "Alterar").

## 4. Sub-seção "Reflexos" dentro de Ocorrências (`reflexos:N:listagem:M:*`)

Quando se acessa Ocorrências da Verba **principal**, aparece uma sub-tabela
para cada reflexo marcado com seus próprios campos:

```
formulario:reflexos:N:dataInicialInputDate (lote do reflexo N)
formulario:reflexos:N:devido (lote: valor devido)
formulario:reflexos:N:listagem:M:valorDevidoReflexo (linha M do reflexo N)
formulario:reflexos:N:listagem:M:termoQuantReflexo
formulario:reflexos:N:listagem:M:valorPagoReflexo
```

### Schema da prévia

Já coberto em `verbas_principais[].reflexos[].ocorrencias_override`:

```json
{
  "reflexos": [
    {
      "id": "r01-01",
      "nome": "13º sobre Indenização Adicional",
      "estrategia_reflexa": "checkbox_painel",
      "parametros_override": null,
      "ocorrencias_override": {
        "modo": "valores_mensais",
        "valores": [
          {"mes": "12/2024", "valor_devido": 416.67}
        ]
      }
    }
  ]
}
```

A automação detecta quando há `ocorrencias_override` no reflexo e abre a
página Ocorrências da verba PRINCIPAL para preencher a sub-seção
`formulario:reflexos:N:listagem:M:*` correspondente.

## 5. Modal "Selecionar Assuntos CNJ" (`btnSelecionarCNJ`)

Modal pop-up para escolher Assunto CNJ na criação de Verba/Honorário.

### Schema da prévia

Já coberto via `assunto_cnj.codigo` + `assunto_cnj.label`. A automação
preenche os campos hidden + visible diretamente sem abrir o modal:

```javascript
document.getElementById('formulario:codigoAssuntosCnj').value = 1855;
document.getElementById('formulario:assuntosCnj').value = 'Indenização por Dano Moral';
```

⚠️ **Tabela de códigos CNJ**: a IA de extração precisa conhecer a tabela
oficial de assuntos CNJ trabalhistas. Para a Fase 3, recomenda-se incluir
no prompt a lista dos ~50 assuntos mais comuns (1855=Dano Moral, 1888=Dano
Material, 2581=Dispensa Discriminatória, 1666=Insalubridade, etc.).

## Resumo da cobertura

| Sub-página | Cobertura | Localização no schema |
|---|---|---|
| Ocorrências da Verba | ✅ Completo | `verbas_principais[].ocorrencias_override` + automação implícita |
| parametrizar-fgts | ✅ Completo | `fgts.recolhimentos_existentes` |
| parametrizar-inss | ✅ Completo | `contribuicao_social.vinculacao_historicos_devidos` |
| Sub-seção Reflexos em Ocorrências | ✅ Completo | `verbas_principais[].reflexos[].ocorrencias_override` |
| Modal Assuntos CNJ | ✅ Completo | `verbas_principais[].parametros.assunto_cnj` + `honorarios[].assunto_cnj` (a adicionar) |
| Parâmetros do Reflexo (form separado) | ✅ Completo | `verbas_principais[].reflexos[].parametros_override` |

## Atualizações necessárias no schema 99-pydantic-models.py

Adicionar:

```python
class VinculacaoHistoricoIntervalo(BaseModel):
    competencia_inicial: str
    competencia_final: str
    historico_nome: str
    valor_base_brl: float


class VinculacaoHistoricos(BaseModel):
    modo: Literal["automatica", "manual_por_periodo"] = "automatica"
    intervalos: list[VinculacaoHistoricoIntervalo] = Field(default_factory=list)


class ContribuicaoSocial(BaseModel):
    # ... campos existentes ...
    vinculacao_historicos_devidos: VinculacaoHistoricos = Field(default_factory=VinculacaoHistoricos)


class RecolhimentoFGTS(BaseModel):
    tipo: Literal["DEPOSITO_REGULAR", "SAQUE", "MULTA_RESCISORIA"] = "DEPOSITO_REGULAR"
    competencia_inicio: str
    competencia_fim: str
    valor_total_depositado_brl: float = Field(ge=0)
    fonte: Literal["INFORMADO_PELA_PARTE", "EXTRATO_FGTS_OFICIAL", "AUTOMATICO"] = "AUTOMATICO"


class FGTS(BaseModel):
    # ... campos existentes ...
    recolhimentos_existentes: list[RecolhimentoFGTS] = Field(default_factory=list)


class OcorrenciasOverride(BaseModel):
    modo: Literal["alteracao_em_lote", "valores_mensais"] = "alteracao_em_lote"
    valores_mensais: list[OcorrenciaMensalOverride] = Field(default_factory=list)
```
