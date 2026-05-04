# Schema da Prévia v2 — Visão Geral

**Princípio fundamental**: a prévia é a **única fonte de verdade** para a
automação. Todos os campos necessários para o preenchimento do PJE-Calc devem
estar na prévia, com nomes semânticos e validação prévia (antes de iniciar
a automação).

## Objetivos do schema

1. **Cobertura completa**: cada campo do PJE-Calc tem 1:1 correspondência na prévia
2. **Validação no upload**: prévia incompleta → erro de extração (não inicia automação)
3. **Editabilidade**: usuário pode revisar/corrigir TODOS os campos antes de confirmar
4. **Estrutura paralela ao DOM**: hierarquia da prévia espelha hierarquia das páginas
5. **Defaults explícitos**: campos opcionais têm `null` claro (não strings vazias)
6. **Rastreabilidade**: cada field do schema mapeia para 1 DOM ID + lista no doc 02

## Estrutura top-level

```json
{
  "meta": {
    "schema_version": "2.0",
    "criado_em": "2026-05-04T08:30:00-03:00",
    "extraido_por": "Claude Sonnet 4.6",
    "validacao": {
      "completude": "OK | INCOMPLETO | ERRO",
      "campos_faltantes": [],
      "avisos": []
    }
  },
  "processo": { /* doc 01 */ },
  "parametros_calculo": { /* doc 02 */ },
  "historico_salarial": [ /* doc 03 */ ],
  "verbas_principais": [ /* doc 04 */ ],
  "cartao_de_ponto": { /* doc 05 */ } | null,
  "faltas": [ /* doc 06 */ ],
  "ferias": [ /* doc 07 */ ],
  "fgts": { /* doc 08 */ },
  "contribuicao_social": { /* doc 09 */ },
  "imposto_de_renda": { /* doc 10 */ },
  "honorarios": [ /* doc 11 */ ],
  "custas_judiciais": { /* doc 12 */ },
  "correcao_juros_multa": { /* doc 13 */ },
  "liquidacao": { /* doc 14 */ },
  "salario_familia": null /* doc 15 */,
  "seguro_desemprego": null /* doc 16 */,
  "previdencia_privada": null /* doc 17 */,
  "pensao_alimenticia": null /* doc 18 */,
  "multas_indenizacoes": [] /* doc 19 */
}
```

## Convenções

### Tipos básicos
- **`string`**: texto sem restrição
- **`date_br`**: string no formato `DD/MM/YYYY`
- **`competencia_br`**: string no formato `MM/YYYY`
- **`money_br`**: número com até 2 casas decimais (interno: float, exibido: `1.234,56`)
- **`percent`**: número entre 0 e 100 com 2 casas decimais
- **`hora_br`**: string no formato `HH:MM`
- **`enum`**: valor restrito a uma lista (sempre em UPPER_CASE)
- **`bool`**: true/false

### Nullability
- Campo OBRIGATÓRIO ausente → erro de validação
- Campo OPCIONAL ausente → `null`
- Lista vazia → `[]` (não `null`)
- Default explícito documentado em cada campo

### Naming
- Sempre `snake_case`
- Sufixos semânticos: `_inicio`, `_fim`, `_brl`, `_pct`, `_qtd`
- Prefixos: `apurar_`, `incidencia_`, `excluir_`, `valor_`
- Listas: nome no plural

## Documentos individuais

| Doc | Seção | Tabela DOM-ID |
|---|---|---|
| 01 | [processo.md](01-processo.md) | Dados do Processo |
| 02 | [parametros-calculo.md](02-parametros-calculo.md) | Parâmetros do Cálculo |
| 03 | [historico-salarial.md](03-historico-salarial.md) | Histórico Salarial (multi-entrada) |
| 04 | [verbas-principais.md](04-verbas-principais.md) | Verbas Principais + Reflexos (CORE) |
| 05 | [cartao-ponto.md](05-cartao-ponto.md) | Cartão de Ponto |
| 06 | [faltas.md](06-faltas.md) | Faltas |
| 07 | [ferias.md](07-ferias.md) | Férias |
| 08 | [fgts.md](08-fgts.md) | FGTS |
| 09 | [contribuicao-social.md](09-contribuicao-social.md) | Contribuição Social (INSS) |
| 10 | [imposto-renda.md](10-imposto-renda.md) | Imposto de Renda |
| 11 | [honorarios.md](11-honorarios.md) | Honorários |
| 12 | [custas-judiciais.md](12-custas-judiciais.md) | Custas Judiciais |
| 13 | [correcao-juros-multa.md](13-correcao-juros-multa.md) | Correção, Juros e Multa |
| 14 | [liquidacao.md](14-liquidacao.md) | Liquidação |
| 15-19 | [secundarias.md](15-secundarias.md) | Salário-família, Seguro-desemprego, Previdência Privada, Pensão Alimentícia, Multas |
| 99 | [pydantic-models.py](99-pydantic-models.py) | Implementação Pydantic v2 |
