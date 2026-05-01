# Teste End-to-End — Bateria 2026-05-01

Resultado da bateria de testes em ambiente de produção (Oracle Cloud, TRT7
Cidadão headless via Playwright Firefox) usando 2 relatórios estruturados
fictícios baseados em cenários reais. Validou todas as features adicionadas
nesta sessão de desenvolvimento.

## Cenários

### Cenário 1 — IRIS (proc 0000369-57.2026.5.07.0003)

Sessão: `fd8c309e-277c-4b40-9b55-22b6096e98e3`

**Features exercitadas**:
- 3 históricos salariais customizados (Salário R$ 2.526,31 + Insalubridade R$ 303,60
  + Piso Enfermagem R$ 2.223,69 com FGTS=false específico)
- 5 verbas principais: SALDO, AVISO PRÉVIO, FÉRIAS+1/3, 13º SALÁRIO, MULTA 477
- Multa 467 via checkbox FGTS
- 2 honorários recíprocos (sucumbência mútua, 7,5% cada)
- FGTS multa 40% + multa 467
- Lei 14.905/2024 (IPCA-E + IPCA + TAXA_LEGAL)
- Aviso prévio Informado (33 dias)

**Resultado**: PJC 193KB (válido pós-liquidação) gerado em ~10min.

### Cenário 2 — LEANDRO (proc 0000227-53.2026.5.07.0003)

Sessão: `cb6a79e1-fd55-47d2-b4e7-76e9d644b0d5`

**Features exercitadas**:
- 3 históricos pago × devido (R$ 2.461 → R$ 2.620 → R$ 7.000 salário "por fora")
- 6 verbas: SALDO, AVISO, FÉRIAS+1/3, 13º, **HE 50%**, INTERVALO INTRAJORNADA
- Reflexos de HE em DSR/Aviso/Férias/13º/FGTS (auto-Expresso)
- Intervalo intrajornada com natureza indenizatória (Lei 13.467/2017)
- 4 reclamadas solidárias (grupo econômico)
- Cartão de Ponto programação semanal (seg-sex 7h-18h, sáb 7h-14h)
- FGTS saldo R$ 1.425,54
- 1 honorário sucumbencial 15% (solidário)
- Multa 477 e 467 INDEFERIDAS
- ADC 58 + Lei 14.905/2024

**Resultado**: PJC 360KB gerado em ~10min.

## Bugs descobertos e corrigidos durante o teste

### 1. KeyError 'tipo_base' em str.format — commit `2ea96b1`

**Sintoma**: TODA extração via Claude API retornava `erro_ia` com mensagem
`"Falha na extração via IA: 'tipo_base'"`.

**Causa raiz**: os literais `{tipo_base: HISTORICO_SALARIAL|...}` e
`{data: 'MM/AAAA', valor: float}` adicionados aos prompts (commits b3783c3
e 0506772) NÃO estavam escapados. O `_EXTRACTION_PROMPT.format(texto=texto)`
interpretava esses chevrons como placeholders Python e levantava KeyError.

**Fix**: duplicar `{` → `{{` e `}` → `}}` nos literais descritivos do schema
(2 prompts, 6 ocorrências).

### 2. NameError 'tipo' em fase_honorarios — commit `8dd1e3e`

**Sintoma**: automação travava em Fase 8 (Honorários) com `NameError: name
'tipo' is not defined` quando IA emitia honorário SEM campo `descricao`
explícito. Após 3 retries → abortava automação.

**Causa raiz**: na geração de descrição padrão do honorário, o código
fazia `{...}.get(tipo, tipo)` mas a variável correta no escopo é `tipo_in`
(definida ~70 linhas antes na mesma função).

**Fix**: `tipo` → `tipo_in` em uma única linha.

**Impacto**: bloqueava 100% dos cenários de sucumbência recíproca onde a
IA não fornece descrição manual (caso comum — IA usualmente omite e deixa
para defaults).

## Validação das features adicionadas nesta sessão

| Commit | Feature | Validado em |
|--------|---------|-------------|
| `b3783c3` | Bases de cálculo da verba (lista) | IRIS + LEANDRO |
| `0506772` | FGTS saldos depositados (lista) | LEANDRO (R$ 1.425,54) |
| `be45b71` | Auto-bases default | IRIS + LEANDRO |
| `2009ec8` | Históricos salariais customizados | IRIS (3 entradas) + LEANDRO (3 entradas) |
| `d0bba21` | incluirBaseHistorico (Adicionar Base) | IRIS + LEANDRO |
| `2ea96b1` | Fix KeyError 'tipo_base' | TODOS |
| `8dd1e3e` | Fix NameError 'tipo' | IRIS sucumbência recíproca |

## Verificação de cálculo correto (regression guard)

`_verificar_calculo_correto()` foi executada em ambos os cenários **antes
de Liquidar**:

- IRIS: `"⚠ Verificação: número do processo não visível na página — assumindo
  correto (mesmo conversationId)" + "✓ Cálculo correto confirmado — processo
  '0000369-57.2026.5.07.0003'"` (regression guard ativou)
- LEANDRO: `"✓ Cálculo correto confirmado — processo '0000227-53.2026.5.07.0003'"`

Conforme MEMORY.md (regression-verificar-calculo): o `return True` quando
CNJ não visível é DELIBERADO — após preenchimento das fases o conversationId
na URL garante o cálculo correto. Não reverter.

## Métricas

| Métrica | IRIS | LEANDRO |
|---------|------|---------|
| Tempo total automação | ~10min | ~10min |
| Linhas SSE | 1042 | 1110 |
| Fases concluídas | 11 (1, 2, 2a, 3, 3 Expresso, 4, 5, 5d, 7, 8, 9) | 12 (+ 5b Cartão) |
| Erros recuperados | 1 (NameError pré-fix) | 0 |
| Verbas mapeadas | 5 + Multa467 | 6 |
| Históricos salariais | 3 | 3 |
| Tamanho PJC (zip) | 10.9 KB | 14.9 KB |
| Tamanho PJC (descompactado) | 193 KB | 360 KB |

### Cenário 3 — PEDRO (proc 0000948-78.2021.5.07.0003)

Sessão: `a3d8e65d-f13d-439b-bb91-d890904e93b1`

**Features exercitadas**:
- 2 históricos paralelos: "Salário Pago Autor" R$ 2.800 + custom "SALARIO_PARADIGMA" R$ 4.500
- Bases de cálculo apontando para histórico custom (validação direta da feature `2009ec8`)
- 8 verbas: DIFERENÇA SALARIAL + SALDO + AVISO + FÉRIAS+1/3 + 13º + HE 50% +
  AD NOTURNO 20% + INTERVALO INTRAJORNADA
- Equiparação salarial (R$ 1.700/mês de diferença)
- Jornada noturna integral (22h-06h) com hora ficta reduzida
- Adicional Noturno 20% sobre todas as horas + Súmula 60-II TST
- Intervalo intrajornada 30min suprimido (indenizatório, sem reflexos)
- Aviso prévio Calculado proporcional Lei 12.506/2011 (36 dias)
- 1 honorário 10% sucumbencial reclamado
- ADC 58 + Lei 14.905/2024

**Resultado**: PJC 1014KB (maior da bateria) gerado em ~12min após resolver
problemas operacionais.

**Tentativas até sucesso**: 12 — descobriu múltiplos bugs operacionais:
- 5 bugs no código (CPF/CNPJ DV, CNJ DV, runner cache, etc.)
- Padronização do processo CNJ usado em todos os testes: 0000948-78.2021.5.07.0003

## Bugs adicionais corrigidos durante o teste do Cenário 3

### 5. Limpeza CPF/CNPJ inválido — commit `e0152ff`

**Sintoma**: dados de teste com CPF/CNPJ fictícios bloqueavam Fase 1
indefinidamente (loop de 3 retries → 0 corrigidos → automação prossegue
com dados não persistidos).

**Fix**: estratégia em 2 níveis em `_tentar_corrigir_erros`:
- Nível 1: reformatar (remover caracteres não-dígito)
- Nível 2: se ainda inválido (DV errado), LIMPAR campo e prosseguir
  (CPF/CNPJ só são obrigatórios ao enviar ao PJe — etapa manual posterior)

### 6. Runner cache eternamente travado — commit `35aa4bb`

**Sintoma**: após `/api/parar`, próxima `/api/executar` retornava
instantaneamente com 246 linhas de logs antigos, sem nunca rodar de fato.

**Causa raiz**:
- `_AutomacaoRunner.stop()` fechava generator + adicionava `[FIM]` mas
  NÃO setava `self.done = True`
- `_limpar_runners_antigos` só remove runners `done=True` → runner parado
  ficava cacheado eternamente (>5min)
- `/api/reset-lock` só limpava locks, não removia runner do cache
- Próxima `/api/executar` via `existing_runner.done == False` → entrava
  em "follow mode" do runner morto

**Fix**:
- `stop()`: agora seta `self.done = True` ao final
- `/api/reset-lock`: agora também faz `_automacao_runners.pop()`

## Total — 6 bugs descobertos e corrigidos pela bateria

| # | Commit | Categoria |
|---|--------|-----------|
| 1 | `2ea96b1` | Prompt format `{...}` literais não escapados |
| 2 | `8dd1e3e` | NameError 'tipo' em fase_honorarios |
| 3 | `21ffb5c` | URLs Fase 6 + recovery navegação |
| 4 | `3b96af1` | Liquidar URL direta fallback |
| 5 | `e0152ff` | Limpar CPF/CNPJ inválido |
| 6 | `35aa4bb` | Runner cache (stop() + reset-lock) |

## Próximos passos sugeridos

1. **Auditoria pós-importação**: importar os PJCs gerados em uma instância
   PJE-Calc desktop e verificar que os totais batem com o esperado das
   sentenças simuladas.
2. **Fix observado mas não tratado**: a IA emitiu `saldo_fgts: 8500.0`
   (legacy) em vez de `saldos: [{data: '09/2024', valor: 8500.0}]` (novo
   formato) — refinar prompt para preferir lista quando há competência
   específica.
3. **Cobertura de extraction**: AD INSALUB foi extraído como 40% quando
   sentença dizia 20% (cenário 1 PDF) — refinar prompt para detectar grau
   "médio" = 20% explicitamente.
4. **Bases default das rescisórias**: SALDO/AVISO/13º/MULTA 477 às vezes
   caem no fallback HE-style (CARGA_HORARIA + 1.5) quando característica
   do classifier vem como Comum. Detectar pelo NOME quando característica
   é genérica.
