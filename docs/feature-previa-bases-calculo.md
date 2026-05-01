# Feature: Edição de Bases de Cálculo na Prévia

**Status**: Aberta — registrada em 2026-05-01
**Solicitada por**: usuário (TRT7)
**Prioridade**: alta — bloqueia liquidações precisas

## Motivação

A tela de Prévia (`templates/previa.html` + endpoints PATCH em `webapp.py`)
hoje permite editar campos básicos de cada verba (nome, período, percentual,
base_calculo simplificada). Mas a base de cálculo de uma verba no PJE-Calc
é uma estrutura RICA — tabela "Bases Cadastradas" com múltiplas linhas
combináveis:

- Tipo de base tabelada: Maior Remuneração / Histórico Salarial / Piso /
  Salário Mínimo / Vale-Transporte
- Quando Histórico Salarial: subtipo (ÚLTIMA REMUNERAÇÃO / SALÁRIO BASE /
  ADICIONAL DE INSALUBRIDADE PAGO)
- Proporcionalizar (Sim/Não)
- Composição com OUTRAS verbas (ex: HE com base sobre COMISSÃO + SALÁRIO)
- Integralizar base (Sim/Não)
- Divisor (Carga Horária / Outro Valor / Dias Úteis / Importada do Cartão)
- Multiplicador (livre — 1,5 / 0,2 / etc.)

Hoje a Prévia trata `base_calculo` como string única. Isso é insuficiente
para casos reais como:

- "HE com integração de comissão" → precisa adicionar Histórico + Verba COMISSÃO
- "AD INSALUBRIDADE 40% sobre piso da categoria" → tipo SALARIO_DA_CATEGORIA
- "Indenização sobre maior remuneração" → tipo MAIOR_REMUNERACAO

## Inspiração — fluxo do PJE-Calc

Tela Parâmetros da Verba (verba-calculo.jsf, form inline) tem painel
"Bases Cadastradas" com:

```
[Bases Cadastradas]
( ) Maior Remuneração
( ) Histórico Salarial         ← radio "tipoDaBaseTabelada"
( ) Piso Salarial
( ) Salário Mínimo
( ) Vale Transporte

Histórico Salarial *  [select baseHistoricos]
  - ADICIONAL DE INSALUBRIDADE PAGO
  - SALÁRIO BASE
  - ÚLTIMA REMUNERAÇÃO

Proporcionalizar *  [select proporcionalizaHistorico]
  - Sim / Não

[Verba *]  [select baseVerbaDeCalculo]
  - 13 verbas existentes para escolher

Integralizar *  [select integralizarBase]
  - Sim / Não

Divisor *  [radio tipoDeDivisor]
  - Informado | Carga Horária | Dias Úteis | Importada do Cartão

Multiplicador *  [text outroValorDoMultiplicador]

[Adicionar Base]  ← link incluirBaseHistorico
```

Após preencher, clicar **Adicionar Base** insere uma linha na tabela
"Bases Cadastradas" mostrando: Histórico Salarial | Proporcionalizar | Ação(Excluir).

## Proposta para a Prévia

### Modelo de dados

Estender `Calculo.dados` (já é JSON) para que cada verba tenha:

```json
{
  "nome": "HORAS EXTRAS 50%",
  "periodo_inicio": "2024-11-22",
  "periodo_fim": "2026-04-30",
  "percentual": 0.5,
  "bases_calculo": [
    {
      "tipo_base": "HISTORICO_SALARIAL",
      "historico_subtipo": "ULTIMA_REMUNERACAO",
      "proporcionalizar": false,
      "verba_compor": null,
      "integralizar": true,
      "divisor": "CARGA_HORARIA",
      "multiplicador": 1.5
    }
  ]
}
```

(Para Maior Remuneração, Piso, Salário Mínimo o subtipo é null; para
Histórico Salarial o subtipo é obrigatório.)

### UI da Prévia

Cada verba ganha uma seção expansível "Bases de Cálculo" com:

- Lista de bases já cadastradas (cards/linhas), cada uma com botão Excluir
- Botão "+ Adicionar Base" abre formulário inline com os campos acima
- Validações:
  - se `tipo_base=HISTORICO_SALARIAL` → exigir `historico_subtipo`
  - se `tipo_base` é qualquer outro → ocultar campo subtipo
  - `divisor=OUTRO_VALOR` → mostrar campo `outro_valor_divisor`
  - se `tipo_base=SALARIO_MINIMO` ou `SALARIO_DA_CATEGORIA` → desabilitar
    `integralizar` (default NAO) e ocultar histórico_subtipo

### Backend — endpoints PATCH

- `POST /api/calculo/{sessao_id}/verba/{idx}/base` — adiciona base
- `DELETE /api/calculo/{sessao_id}/verba/{idx}/base/{base_idx}` — remove
- `PATCH /api/calculo/{sessao_id}/verba/{idx}/base/{base_idx}` — atualiza

### Automação Playwright

`_configurar_parametros_verba` precisa ler `verba["bases_calculo"]` (lista)
e para cada base:
1. Selecionar `tipoDaBaseTabelada`
2. Se HISTORICO_SALARIAL: selecionar `baseHistoricos`
3. Se há `verba_compor`: selecionar `baseVerbaDeCalculo`
4. Selecionar `proporcionalizaHistorico`
5. Selecionar `integralizarBase`
6. Marcar `tipoDeDivisor`
7. Preencher `outroValorDoMultiplicador`
8. **Clicar `incluirBaseHistorico`** (já implementado para histórico)
9. Aguardar AJAX
10. Repetir para próxima base

Default seguro (quando `verba["bases_calculo"]` está vazio ou ausente):
adicionar 1 base com `tipo_base=HISTORICO_SALARIAL` + `subtipo=ULTIMA_REMUNERACAO`
+ defaults do PJE-Calc para a característica da verba.

### Extração via IA

`extraction.py` deve identificar pistas na sentença sobre base de cálculo:

- "horas extras com integração de comissão" → adicionar base com
  verba_compor=COMISSÃO
- "adicional de insalubridade sobre o salário base" → tipo HISTORICO_SALARIAL
  + subtipo SALARIO_BASE (não default ULTIMA_REMUNERACAO)
- "adicional de periculosidade sobre o salário contratual" → SALARIO_BASE
- "adicional sobre maior remuneração" → tipo MAIOR_REMUNERACAO

Adicionar instrução ao prompt para extrair `bases_calculo` por verba quando
a sentença mencionar explicitamente.

## Validação

Após implementação, rodar caso real:
1. Verba HE 50% com 2 bases (Histórico ÚLTIMA + Verba COMISSÃO)
2. Editar via Prévia
3. Salvar e disparar automação
4. Confirmar que ambas as bases aparecem em "Bases Cadastradas" no PJE-Calc
5. Liquidar — confirmar valores refletindo a soma das duas bases

## Arquivos afetados

- `templates/previa.html` — UI das bases
- `static/js/previa.js` (se existir) ou inline — lógica add/remove base
- `webapp.py` — endpoints PATCH/POST/DELETE de bases
- `database.py` — nada (é tudo no JSON `dados`)
- `modules/extraction.py` — prompt de extração inclui bases_calculo
- `modules/playwright_pjecalc.py::_configurar_parametros_verba` —
  iterar bases_calculo no lugar do código atual de base única
