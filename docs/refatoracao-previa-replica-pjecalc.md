# Refatoração: Prévia como Réplica Perfeita do PJE-Calc

> **Princípio:** a prévia HTML deve ser um espelho 1:1 do PJE-Calc Cidadão. Cada campo editável no PJE-Calc tem um campo editável correspondente na prévia. A automação não infere nada — apenas APLICA o que está no JSON resultante da prévia.

## Problema atual

A prévia hoje mostra um subconjunto de campos (caracteristica, ocorrencia, periodo, base, percentual). A automação faz **inferência** para preencher campos ausentes (divisor=carga horária, multiplicador=outro, integralizar=true para reflexos pós-contratuais, ocorrencia=MENSAL como default, qtd=22h/mês como fallback HE etc.). Isso causa:

1. **Liquidação infiel** — automação preenche valores inferidos que podem divergir da sentença
2. **Bugs não-reproduzíveis** — usuário não vê o que foi inferido até a Liquidação falhar
3. **Cada bug requer fix manual no código** — em vez de corrigir no JSON

## Arquitetura alvo

### 3 camadas

```
┌──────────────────────────────────────────────────────────┐
│  IA (extraction.py / classification.py)                  │
│  Lê PDF/DOCX → produz JSON v2 COMPLETO (todos campos)    │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Prévia HTML (espelho do PJE-Calc)                       │
│  Mostra TODOS os campos do JSON, editáveis pelo usuário  │
└──────────────────────┬───────────────────────────────────┘
                       │ Confirmar
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Automação (aplicador puro)                              │
│  Lê JSON → preenche campo por campo, sem inferir         │
└──────────────────────────────────────────────────────────┘
```

### Catálogo de campos como fonte da verdade

`docs/pjecalc-fields-catalog.json` (gerado via `scripts/cataloga_pjecalc.py`) é a fonte ÚNICA da verdade sobre quais campos existem em cada página. Dele derivam:

1. **Pydantic models** (validação)
2. **Prévia HTML** (renderização)
3. **Automação** (aplicação)

Quando o PJE-Calc evoluir, basta re-rodar o script de catalogação e os 3 artefatos são atualizados.

## Arquivos novos a criar

### `infrastructure/pjecalc_pages.py`
Pydantic v2 models gerados a partir do catálogo JSON. Um modelo por página/sub-página:

```python
class PaginaDadosProcesso(BaseModel):
    numero: str
    digito: str
    ano: str
    regiao: str
    vara: str
    autuado_em: str  # DD/MM/YYYY
    valor_da_causa: Decimal
    documento_fiscal_reclamante: Literal["CPF", "CNPJ", "CEI"]
    reclamante_numero_documento_fiscal: str
    reclamante_nome: str
    # ... 70+ campos
    model_config = ConfigDict(extra="forbid")  # erro se campo desconhecido

class ParametrosVerba(BaseModel):
    nome: str
    caracteristica: Literal["COMUM", "DECIMO_TERCEIRO_SALARIO", "AVISO_PREVIO", "FERIAS"]
    ocorrencia_pagto: Literal["MENSAL", "DEZEMBRO", "DESLIGAMENTO", "PERIODO_AQUISITIVO"]
    periodo_inicial: date | None = None
    periodo_final: date | None = None
    tipo_da_base_tabelada: Literal["HISTORICO_SALARIAL", "MAIOR_REMUNERACAO", "ULTIMA_REMUNERACAO", "SALARIO_MINIMO", "VALOR_INFORMADO"]
    base_historicos: Literal["ULTIMA_REMUNERACAO", "SALARIO_REGISTRADO", ...] | None = None
    bases_calculo: list[BaseCalculoExtra] = []
    tipo_de_divisor: Literal["CARGA_HORARIA", "OUTRO_VALOR"] = "CARGA_HORARIA"
    outro_valor_divisor: Decimal | None = None
    tipo_da_quantidade: Literal["INFORMADA", "CALCULADA"] = "CALCULADA"
    valor_informado_da_quantidade: Decimal | None = None
    outro_valor_do_multiplicador: Decimal | None = None
    integralizar: bool = False
    sumula_439: bool = False
    compor_principal: bool = True
    valor_informado: Decimal | None = None  # para indenizações com valor fixo

class OcorrenciaVerba(BaseModel):
    """Cada linha da tabela de Ocorrências da Verba."""
    indice: int  # 0-based
    competencia: date  # mês/ano da ocorrência
    ativo: bool = True
    termo_div: Decimal | None = None
    termo_mult: Decimal | None = None
    termo_quant: Decimal | None = None
    valor_devido: Decimal | None = None
    dobra: bool = False
```

### `templates/previa_v2/_macros.html`
Macros Jinja genéricas que renderizam qualquer campo a partir de metadados:

```jinja
{% macro field_text(name, value, label, readonly=False) %}
  <div class="campo-form">
    <label for="{{ name }}">{{ label }}</label>
    <input type="text" id="{{ name }}" value="{{ value or '' }}"
           {% if readonly %}readonly{% endif %}
           onchange="salvarCampo('{{ name }}', this.value, this)">
  </div>
{% endmacro %}

{% macro field_select(name, value, label, opcoes) %}
  <div class="campo-form">
    <label for="{{ name }}">{{ label }}</label>
    <select id="{{ name }}" onchange="salvarCampo('{{ name }}', this.value, this)">
      {% for o in opcoes %}
        <option value="{{ o.v }}" {% if o.v == value %}selected{% endif %}>{{ o.l }}</option>
      {% endfor %}
    </select>
  </div>
{% endmacro %}

{% macro field_radio(name, value, label, opcoes) %}
  <div class="campo-form">
    <label>{{ label }}</label>
    {% for o in opcoes %}
      <label><input type="radio" name="{{ name }}" value="{{ o.v }}"
                    {% if o.v == value %}checked{% endif %}
                    onchange="salvarCampo('{{ name }}', this.value, this)"> {{ o.l }}</label>
    {% endfor %}
  </div>
{% endmacro %}
```

### `templates/previa_v2/dados_processo.html`
Página: Dados do Processo (espelho fiel)

```jinja
{% from "_macros.html" import field_text, field_select, field_radio %}
<section class="pjecalc-pagina" data-pagina="dados_processo">
  <h2>1. Dados do Processo</h2>

  {{ field_text("processo.numero", dados.processo.numero, "Número") }}
  {{ field_text("processo.digito", dados.processo.digito, "Dígito") }}
  {{ field_text("processo.ano", dados.processo.ano, "Ano") }}
  ...
  {{ field_radio("processo.documento_fiscal_reclamante",
                  dados.processo.documento_fiscal_reclamante,
                  "Documento Fiscal Reclamante",
                  [{v:"CPF",l:"CPF"},{v:"CNPJ",l:"CNPJ"},{v:"CEI",l:"CEI"}]) }}
  ...
</section>
```

### `templates/previa_v2/verba_principal.html`
Para cada verba na lista, mostra TODOS os campos da página Parâmetros + lista de ocorrências geradas (editáveis individualmente).

### `core/aplicador.py`
Refatoração de `playwright_pjecalc.py` em fases que apenas APLICAM:

```python
class AplicadorPJECalc:
    def aplicar_dados_processo(self, page: PaginaDadosProcesso):
        for nome_campo in ["numero", "digito", "ano", ...]:
            self._preencher(nome_campo, getattr(page, nome_campo))

    def aplicar_parametros_verba(self, params: ParametrosVerba):
        self._selecionar("caracteristicaVerba", params.caracteristica)
        # Default automático respeitado: só clica ocorrenciaPagto se diferir do default
        self._aplicar_ocorrencia_se_diferente_do_default(params.caracteristica, params.ocorrencia_pagto)
        ...

    def aplicar_ocorrencias_verba(self, ocorrencias: list[OcorrenciaVerba]):
        for oc in ocorrencias:
            cbx = page.locator(f"#formulario:listagem:{oc.indice}:ativo")
            if cbx.is_checked() != oc.ativo:
                cbx.click()
            if oc.termo_quant is not None:
                page.fill(f"#formulario:listagem:{oc.indice}:termoQuant", _fmt_br(oc.termo_quant))
            ...
        # SEM auto-fix, SEM inferência. O JSON manda.
```

## Plano de implementação (ordem)

### Fase 2A — Schema (este passo)
1. **`infrastructure/pjecalc_pages.py`** com models para:
   - DadosProcesso (74 campos do catálogo)
   - HistoricoSalarialEntry (form Novo, 12 campos)
   - HistoricoSalarialOcorrencia (linhas mensais)
   - ParametrosVerba (do form Manual + Expresso, ~30 campos relevantes)
   - OcorrenciaVerba (linhas mensais)
   - HonorarioRegistro (16 campos)
   - FGTS, INSS, IRPF, etc. (campos básicos do catálogo + selectors.py)
2. Conversor JSON v2 atual → models (`migrar_v2_para_v3()`)

### Fase 2B — Prévia HTML v3
1. `templates/previa_v3/_base.html` — layout
2. `templates/previa_v3/_macros.html` — campos genéricos
3. Uma `<section>` por página do PJE-Calc, populada via macros
4. Cada verba expandível: Parâmetros + Tabela de Ocorrências (linha-por-linha editável)

### Fase 2C — Aplicador puro
1. `core/aplicador.py` com método `aplicar_pagina(page, dados)` por página
2. Remoção de TODA lógica de inferência (auto-fix, default por característica, fallback HE)
3. Validação prévia: se JSON tem inconsistência, FALHA com mensagem clara (não tenta corrigir)

### Fase 2D — Endpoint de migração
1. POST `/api/migrar/{sessao_id}` para converter sessões antigas
2. UI de aviso "Esta prévia usa schema antigo. Clique para atualizar."

## Estimativa

- Fase 2A (schema): 4-6 horas focadas
- Fase 2B (prévia HTML): 6-10 horas focadas
- Fase 2C (aplicador): 8-12 horas focadas (refatoração massiva do v1)
- Fase 2D (migração): 2-3 horas
- Testes: ~4 horas

**Total: 25-35 horas** de trabalho focado para chegar à réplica perfeita funcional.

## Decisões pendentes

1. **Manter v1 (`playwright_pjecalc.py`) em paralelo durante migração?** Recomendo: sim, na pasta `legacy/`. Sessões antigas continuam funcionando, novas usam aplicador puro.
2. **Sessões existentes com schema antigo:** migração automática (lossy — campos inferidos viram defaults) ou exigir nova prévia?
3. **Catálogo evolutivo:** rodar `cataloga_pjecalc.py` em CI para detectar mudanças do PJE-Calc?

## Status da execução

### ✅ Etapa 2B COMPLETA (todas as 7 sub-etapas)

A prévia v3 já é uma **réplica funcional** das 12 páginas do PJE-Calc, com:
- Schema Pydantic completo (`infrastructure/pjecalc_pages.py`, 13 models)
- Templates Jinja com macros + repeaters recursivos
- ~250+ campos editáveis com PATCH inline
- Migração v2→v3 com relatório de warnings
- Roteamento dual: `/previa/{sess}` (v2 atual) ↔ `/previa_v3/{sess}` (v3 nova)
- Banner na v2 direcionando para v3
- Link "← v2" no header da v3 para voltar
- `?v=3` na URL v2 redireciona para v3

**Coexistem em paralelo durante a transição.** A automação ainda usa v2;
a próxima etapa (2C) refatora para aplicador puro consumindo v3.

### ✅ Etapa 2A — Concluída (commit `1ee133e`)

`infrastructure/pjecalc_pages.py` — 9 Pydantic models com 441 linhas:
- `DadosProcesso` (~70 campos), `HistoricoSalarialEntry`/`Ocorrencia`, `ParametrosVerba` (30+),
  `OcorrenciaVerba`, `Verba` (recursivo), `Honorario`, auxiliares
- `extra="forbid"` força fidelidade
- `Literal` types para todos os enums
- Validators DD/MM/YYYY e BR
- 9 testes passaram

### ⏳ Etapa 2B — Dividida em 7 sub-etapas (aprovada pelo usuário)

| # | Sub-etapa | Entrega | Estimativa |
|---|---|---|---|
| **2B.1** | Infraestrutura base | `templates/previa_v3/_base.html` + `_macros.html` (8 macros: text, select, radio, checkbox, date, decimal, textarea, repeater) + endpoint `/previa_v3/{sessao_id}` mínimo | 1-2h |
| **2B.2** | Página Dados do Processo | `dados_processo.html` com 70 campos via macros + salvarCampo inline; testar persistência | 2h |
| **2B.3** | Página Histórico Salarial | `historico_salarial.html` com repeater de N entries; cada entry com sub-tabela de ocorrências mensais editáveis | 1.5h |
| **2B.4** | **Página Verbas** (mais crítica) | `verbas.html`: lista expansível, `ParametrosVerba` 30 campos + tabela `OcorrenciaVerba` mensal + sub-lista recursiva de reflexos. Filtros visuais (DESLIGAMENTO = 1 linha) | 3h |
| **2B.5** | Páginas auxiliares | Honorários + Cartão de Ponto + FGTS + INSS + IRPF + Custas + Correção/Juros | 2h |
| **2B.6** | Migração v2 → v3 | `/api/migrar/{sessao_id}` converte JSON antigo, valida Pydantic, persiste | 1h |
| **2B.7** | Integração + roteamento | `/previa/{sessao_id}` detecta versão e roteia v3 ou v2; botão "Migrar p/ v3" | 1h |

**Total: ~12h** em pedaços de 1-3h cada.

**Ordem recomendada de execução:** 2B.1 → 2B.2 → 2B.4 → 2B.3 → 2B.5 → 2B.6 → 2B.7

---

## Próxima sessão: iniciar 2B.1

Recomendo começar a próxima sessão com prompt:

> "Iniciar Etapa 2B.1 da refatoração documentada em `docs/refatoracao-previa-replica-pjecalc.md`. Criar `templates/previa_v3/_base.html` (layout) e `_macros.html` (8 macros: text, select, radio, checkbox, date, decimal, textarea, repeater). Adicionar endpoint mínimo `/previa_v3/{sessao_id}` que renderiza apenas Dados do Processo vazio. Testar standalone."

Tudo o que a próxima sessão precisa saber está em:
- `docs/refatoracao-previa-replica-pjecalc.md` — este documento
- `infrastructure/pjecalc_pages.py` — schema v3 pronto
- `docs/pjecalc-fields-catalog.json` — fonte da verdade dos campos
- `docs/pjecalc-fields-catalog.md` — versão legível
- `docs/sessao-2026-05-06-correcoes-sentenca-richarlen.md` — histórico de correções (contexto)
