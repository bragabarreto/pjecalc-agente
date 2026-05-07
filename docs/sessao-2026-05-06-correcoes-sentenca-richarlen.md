# Sessão 2026-05-06 — Correções no fluxo Expresso + Auto-fix per-verba

Sessão de testes da sentença RICHARLEN COSTA (processo 0001512-18.2025.5.07.0003), envolvendo:
- Diferença Salarial + reflexos
- Horas Extras 50% + reflexos
- Indenização por Dano Moral (R$ 15.000, ocorrência **Desligamento**)
- Indenização Adicional (estabilidade acidentária, 12 meses)
- Indenização por Dano Material (Lei 9.029, dispensa discriminatória, dobro de 6 meses)
- Multa do art. 477 (1 salário, ocorrência **Desligamento**)

## Linha do tempo dos commits

| Commit | Tipo | Descrição |
|---|---|---|
| `04aadbd` | fix | Auto-fix: buscar verbas em `verbas_mapeadas` além de `_dados['verbas']` (matching falhava em uploads JSON v2) |
| `2d16669` | fix | Auto-fix: preencher `termoQuant`/`valorDevido` independente do botão Gerar (fills pulados quando ocorrências já existem) |
| `e6a244f` | fix | Auto-fix: Regerar APÓS edições + dialog handler permanente |
| `3fd258e` | fix | RichFaces 3: blur event + ajax wait após click no radio Sobrescrever |
| `bd34994` | fix | RichFaces 3 v2: locator.fill() iter em vez de JS evaluate em massa (DOM detached) |
| `c759466` | fix | RichFaces 3 v3: reativar linhas `:ativo` antes do fill termoQuant |
| `3732e53` | **refactor** | **Fase 3: Params→Regerar→Ocorrências em vez de Params+Ocorrências por verba** |
| `0b3cbb6` | fix | RichFaces 3 v4: re-marcar `:ativo` também antes do fill valorDevido |
| `16a968e` | fix | Regerar: sempre usar 'Manter alterações' em vez de Sobrescrever (decisão do usuário) |
| `502a8f0` | **fix** | **Verbas: seguir estritamente `caracteristica`+`ocorrencia` do JSON (DANO MORAL/MULTA 477 → DESLIGAMENTO)** |
| `200f734` | fix | Safety: early break + cap reduzido (200→80) + abort em context destroyed |
| `6c50af1` | fix | AJAX v7: timeout 15s→8s + reinstalar monitor após 3 timeouts consecutivos |

## O que ficou consolidado e funcional

### 1. Refactor da Fase 3 (Loop 1 → Regerar → Loop 2)
Antes: `[Params + Ocorrências] por verba` → marcava flag "multiplicador alterado" em cada verba.
Agora: `Params em todas` → 1 Regerar global → `Ocorrências em todas` → flag limpa.

### 2. Fidelidade ao JSON em Parâmetros da Verba
- `caracteristica` (COMUM, FERIAS, DECIMO_TERCEIRO_SALARIO, AVISO_PREVIO) **lida do JSON**.
- `ocorrenciaPagto` (MENSAL, DESLIGAMENTO, DEZEMBRO, PERIODO_AQUISITIVO) **lida do JSON**.
- Default da característica respeitado (não clica `ocorrenciaPagto` redundantemente para evitar NPE em `LegendaDaFormula.getBase`).
- Auto-override que forçava MENSAL para verbas pós-rescisão **REMOVIDO** (violava fidelidade).

### 3. Regerar Global = "Manter alterações"
Decisão do usuário: nunca usar Sobrescrever, que zera `termoQuant`/`valorDevido` e `:ativo`.

### 4. Locator iterativo para fills
- Substituiu `page.evaluate` em massa (que sofria detach do DOM por re-render AJAX).
- `locator.fill()` simula digitação real + dispara blur.
- Idempotente (pula linhas já preenchidas).
- Cap reduzido (80 linhas) + early break em 5 idempotentes consecutivos.
- Abort em "Execution context destroyed".

### 5. Safety no `_aguardar_ajax`
- Timeout reduzido 15s→8s.
- Reinstala monitor após 3 timeouts consecutivos (evita zumbi onde flag fica presa em `false`).

## ❌ Problema crítico ainda pendente: ocorrências geradas pelo Expresso ficam mesmo após mudança de ocorrenciaPagto

**Sintoma observado em rodada 02:00-02:33 UTC (commit 6c50af1):**
- Loop 1 setou `INDENIZAÇÃO POR DANO MORAL: ocorrenciaPagto=DESLIGAMENTO` corretamente.
- Mas a tabela de Ocorrências continuou com **56 linhas mensais** (geradas pelo Expresso original com MENSAL).
- Auto-fix per-verba preencheu R$ 15.000 nas 56 linhas → R$ 840.000 (deveria ser R$ 15.000 × 1).

**Causa-raiz:** Saving Parâmetros com `ocorrenciaPagto=DESLIGAMENTO` não regenera as ocorrências automaticamente no banco. "Manter alterações" preserva as 56 linhas. Só "Sobrescrever" recriaria com 1 linha (mas zera valores).

## Decisão pendente do usuário

- **(A)** Permitir Sobrescrever **per-verba** quando `ocorrenciaPagto` mudou — limita o impacto a essa verba; depois preenche o valor na 1 linha resultante.
- **(B)** Após Save Params, abrir Ocorrências da verba e **desmarcar checkbox `:ativo`** das 55 linhas mensais extras, deixando ativa só a do mês de desligamento.

## Estratégia de restart

1. Escolher A ou B e implementar.
2. Limpar cálculos H2 (já automático no startup do container).
3. Re-uploar JSON v2 da sentença RICHARLEN.
4. Executar a partir da prévia.
5. Validar Liquidação e .PJC.
