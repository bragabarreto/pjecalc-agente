# Catálogo Oficial de Verbas PJE-Calc

Fonte: `modules/classification.py` → `VERBAS_PREDEFINIDAS` + Manual Oficial PJE-Calc v1.0

## Verbas Lançamento Expresso (Predefinidas)

| Nome PJE-Calc | Chave de busca | Tipo | Característica | Ocorrência | FGTS | INSS | IR | Reflexas típicas |
|---|---|---|---|---|---|---|---|---|
| Saldo de Salário | saldo de salario | Principal | Comum | Desligamento | ✓ | ✓ | ✓ | — |
| Aviso Prévio Indenizado | aviso previo indenizado | Principal | Aviso Previo | Desligamento | ✓ | ✓ | ✓ | — |
| 13º Salário Proporcional | 13 salario proporcional / decimo terceiro salario proporcional | Principal | 13o Salario | Desligamento | ✓ | ✓ | ✓ | — |
| Férias Proporcionais + 1/3 | ferias proporcionais | Principal | Ferias | Periodo Aquisitivo | ✗ | ✓ | ✓ | — |
| Férias Vencidas + 1/3 | ferias vencidas | Principal | Ferias | Periodo Aquisitivo | ✗ | ✓ | ✓ | — |
| Horas Extras | horas extras | Principal | Comum | Mensal | ✓ | ✓ | ✓ | RSR, 13º, Férias |
| Adicional Noturno | adicional noturno | Principal | Comum | Mensal | ✓ | ✓ | ✓ | RSR, 13º, Férias |
| Adicional de Insalubridade | adicional de insalubridade | Principal | Comum | Mensal | ✓ | ✓ | ✓ | 13º, Férias |
| Adicional de Periculosidade | adicional de periculosidade | Principal | Comum | Mensal | ✓ | ✓ | ✓ | — |
| Multa Art. 477 CLT | multa art 477 | Principal | Comum | Desligamento | ✗ | ✗ | ✗ | — |
| Multa Art. 467 CLT | multa art 467 | **NÃO é verba Expresso** | — | — | ✗ | ✗ | ✗ | Checkbox FGTS (`multaDoArtigo467`) + reflexa automática sob cada verba principal na aba Verbas |
| Vale Transporte | vale transporte | Principal | Comum | Mensal | ✗ | ✗ | ✗ | — |
| Salário-Família | salario familia | Principal | Comum | Mensal | ✗ | ✗ | ✗ | — |
| Indenização por Dano Moral | dano moral / indenizacao por dano moral | Principal | Comum | Desligamento | ✗ | ✗ | ✗ | — |
| Indenização por Dano Material | dano material | Principal | Comum | Desligamento | ✗ | ✗ | ✗ | — |

## Verbas de Uso Frequente (Lançamento Manual)

Estas verbas não estão no catálogo Expresso mas são frequentemente deferidas:

| Nome PJE-Calc | Tipo | Característica | Ocorrência | FGTS | INSS | IR | Obs. |
|---|---|---|---|---|---|---|---|
| Diferenças Salariais | Principal | Comum | Mensal | ✓ | ✓ | ✓ | Quando há aumento negado |
| Adicional de Transferência | Principal | Comum | Mensal | ✓ | ✓ | ✓ | 25% do salário |
| Gratificação de Função | Principal | Comum | Mensal | ✓ | ✓ | ✓ | Verificar integração |
| Comissões | Principal | Comum | Mensal | ✓ | ✓ | ✓ | Base: média |
| Horas in Itinere | Principal | Comum | Mensal | ✓ | ✓ | ✓ | Pré-Reforma |
| Intervalo Intrajornada | Principal | Comum | Mensal | ✓ | ✓ | ✓ | Art. 71 §4º CLT |
| Intervalo do Art. 384 | Principal | Comum | Mensal | ✓ | ✓ | ✓ | Mulher, pré-Reforma |
| Adicional de Sobreaviso | Principal | Comum | Mensal | ✓ | ✓ | ✓ | 1/3 do horário normal |
| Multa Normativa / Cláusula Penal | Principal | Comum | Desligamento | ✗ | ✗ | ✗ | Prevista em ACT/CCT |
| Indenização por Estabilidade | Principal | Comum | Desligamento | ✗ | ✗ | ✗ | CIPA, gestante, etc. |
| Reintegração / Salários do período | Principal | Comum | Mensal | ✓ | ✓ | ✓ | |
| FGTS não depositado | — | — | — | — | — | — | Via campo FGTS, não verba |

## Verbas Reflexas (geradas automaticamente)

| Nome PJE-Calc | Verba principal | Característica | Ocorrência | FGTS | INSS | IR |
|---|---|---|---|---|---|---|
| RSR sobre Horas Extras | Horas Extras | Comum | Mensal | ✓ | ✓ | ✓ |
| 13º s/ Horas Extras | Horas Extras | 13o Salario | Desligamento | ✓ | ✓ | ✓ |
| Férias + 1/3 s/ Horas Extras | Horas Extras | Ferias | Periodo Aquisitivo | ✗ | ✓ | ✓ |
| RSR sobre Adicional Noturno | Adicional Noturno | Comum | Mensal | ✓ | ✓ | ✓ |
| 13º s/ Adicional Noturno | Adicional Noturno | 13o Salario | Desligamento | ✓ | ✓ | ✓ |
| Férias + 1/3 s/ Adicional Noturno | Adicional Noturno | Ferias | Periodo Aquisitivo | ✗ | ✓ | ✓ |
| 13º s/ Insalubridade | Adicional de Insalubridade | 13o Salario | Desligamento | ✓ | ✓ | ✓ |
| Férias + 1/3 s/ Insalubridade | Adicional de Insalubridade | Ferias | Periodo Aquisitivo | ✗ | ✓ | ✓ |

## Verbas sem incidência (checklist rápido)

**Não incidem FGTS, INSS ou IR:**
- Dano moral / material
- Multa art. 477 (verba Expresso), art. 467 (checkbox FGTS + reflexa, NÃO é verba Expresso), normativa/cláusula penal
- Vale transporte
- Reembolso de despesas
- Honorários periciais (campo próprio)

**Incidem INSS e IR mas NÃO FGTS:**
- Férias (indenizadas ou proporcionais)
- Aviso prévio indenizado (posição majoritária: incide FGTS; verificar sentença)

## Comportamento de base de cálculo das reflexas

- `Média pelo Valor Absoluto`: soma total da verba no período ÷ meses
- `Valor Mensal`: usa o último valor mensal fixo da verba
- `Percentual sobre Salário`: aplica percentual sobre salário base
