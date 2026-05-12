# Calc Machine — Execução completa observada (12/05/2026)

Captura de uma execução real do Calc Machine via Chrome MCP. Sentença
`sentenca_processada_20260501_014304.json` (processo 0001673-28.2025.07.0003,
PAULO CESAR DA SILVA DE MESQUITA, valor R$ 4.329.579,00).

Arquivo final gerado: `PROCESSO_00016732820255070003_CALCULO_976_DATA_12052026_HORA_083116.PJC`

## Padrões críticos que precisamos replicar

### 1. Validação após cada Save
```
Clicando no botão salvar...
Aguardando processamento...
✓ Operação realizada com sucesso.    ← aguardam essa mensagem no .rf-msgs-sum
=== NÚMERO DO CÁLCULO: 976 ===       ← extraem do DOM como prova de persistência
```

### 2. Liquidação com fallback não-bloqueante
```
Clicando no botão de liquidar...
Liquidação iniciada, aguardando término (pode demorar para cálculos grandes)...
Aguardando confirmação de sucesso...
⚠️ Aviso: Mensagem de sucesso não detectada, mas prosseguindo... (Selenium TimeoutException)
=== INICIANDO EXPORTAÇÃO DO ARQUIVO .PJC ===    ← prossegue mesmo sem confirmação
```

Eles usam timeout do Selenium (~30s?) mas NÃO travam — emitem aviso e seguem para Exportar.

### 3. Captura de download via diretório do navegador
```
Clicando em Exportar...
✓ Menu Exportar clicado     ← sidebar
✓ Botão Exportar clicado    ← página exportacao.jsf
✅ Arquivo salvo: PROCESSO_00016732820255070003_CALCULO_976_DATA_12052026_HORA_083116.PJC
Arquivo identificado para salvar: /root/Downloads/PROCESSO_..._.PJC
```

Configuram o Firefox/Chrome para download em `/root/Downloads/` e fazem `ls` para encontrar
o arquivo após o clique. **Não usam `page.on("download")` do Playwright** — usam scan do diretório.

### 4. Verbas Expresso — uma por vez (não em batch)

Para CADA verba expresso:
```
Procurando e selecionando <Nome da Verba>...
Checkbox <Nome> clicado com sucesso
Salvando seleção de insalubridade...    ← salva IMEDIATAMENTE após cada checkbox
Buscando verba <Nome> na listagem para inserção de dados...
✓ Verba <Nome> encontrada na linha N
Clicando para inserir dados de <Nome>...
[parametriza individualmente]
Salvando dados da <Nome>...
Clicando em exibir reflexos de <Nome>...
[seleciona reflexos individualmente]
```

**Não marcam todas as checkboxes do Expresso de uma vez** — uma por uma, salvando entre cada.

### 5. Histórico Salarial — Gerar Ocorrências + valores mensais
```
Clicando em Histórico Salarial → Novo
Preenchendo nome BASE DE CÁLCULO
Preenchendo valor da remuneração
Clicando em Gerar Ocorrências...
Preenchendo valores mensais...
Aguardando tabela de ocorrências e processamento...
Salvando histórico salarial...
Histórico salarial salvo com sucesso
```

Não usam o nome "ÚLTIMA REMUNERAÇÃO" padrão do PJE-Calc — criam "BASE DE CÁLCULO" e
preenchem TODOS os valores mensais via "Gerar Ocorrências".

### 6. Cartão de Ponto — completo (não pulam)
```
Menu de cartão de ponto → Novo
Datas competencia inicial/final
Radio button programação
Tabela horários semanais
Regerar → Confirmar regerar
```

### 7. Honorários — um por vez com confirmação
```
Processando honorários: <TIPO> / <DEVEDOR> / <CREDOR>
Selecionando tipo: <TIPO>
Preenchendo alíquota OR Preenchendo valor fixo
Honorário <TIPO>/<DEVEDOR> salvo com sucesso
```

### 8. Correção/Juros/Multa — detalhado por configuração de juros
```
Excluindo itens da tabela (1 por 1)
Data de ajuizamento igual ou posterior a 30/08/2024, usando nova configuração
Selecionando IPCA-e
Marcando checkbox de combinar índice
Selecionando 'IPCA' no segundo índice
Data de admissão é posterior à lei, usando admissão + 1 dia
Preenchendo data: 31/10/2024
Procurando botão adicionar → clicado
Marcando checkbox de combinar com outro juros
Selecionando Taxa Legal e adicionando com data de corte
Preenchendo data de ajuizamento para Taxa Legal
Adicionando configuração Taxa Legal
Salvando configurações dos juros
```

### 9. Sequência Liquidar (simples)
```
Clicando na aba Operações
Clicando em Liquidar (Menu)
Aguardando carregamento da tela de liquidação
Clicando em acumular indices
Verificando se a data de liquidação é maior que a data de ajuizamento
Data de liquidação (DD/MM/AAAA) está correta e posterior ao ajuizamento.
Clicando no botão de liquidar
Liquidação iniciada, aguardando término
[timeout fallback: prossegue mesmo sem confirmação]
```

### 10. Sequência Exportar
```
=== INICIANDO EXPORTAÇÃO DO ARQUIVO .PJC ===
Clicando em Exportar... (menu Operações)
✓ Menu Exportar clicado
✓ Botão Exportar clicado
✅ Arquivo salvo: PROCESSO_..._CALCULO_N_..._.PJC
```

E **opcional** após .PJC:
```
=== INICIANDO IMPRESSÃO DO PDF ===
Clicando em Imprimir (menu Operações)
✓ Item Imprimir clicado
✓ Botão Imprimir clicado — aguardando geração do PDF
```

## Sequência de Fases observada

| # | Fase | Tempo (s) | Status |
|---|------|-----------|--------|
| 1 | Dados do Processo + Parâmetros | ~22s | OK, NÚMERO DO CÁLCULO: 976 |
| 2 | Histórico Salarial (BASE DE CÁLCULO) | ~14s | OK |
| 3 | Verbas Expresso (Valor Pago + Insalubridade) | ~30s | OK |
| 4 | Manual: MULTA CONVENCIONAL CCT 2025/2026 | ~15s | OK |
| 5 | Cartão de Ponto + tabela horários | ~20s | OK |
| 6 | FGTS + multa | ~5s | OK |
| 7 | Honorários (3: 2 SUCUMBENCIAIS + 1 PERICIAL) | ~10s | OK |
| 8 | Contribuição Social + alíquotas | ~10s | OK |
| 9 | Correção/Juros (IPCAE→IPCA + Taxa Legal) | ~15s | OK |
| 10 | Liquidar | ~longo + timeout | "Mensagem não detectada, prosseguindo" |
| 11 | Exportar | ~5s | .PJC baixado em /root/Downloads/ |

Total: ~3-5 minutos.

## Conclusão para nosso bot

Os 5 itens mais importantes a replicar:
1. **`_aguardar_operacao_sucesso()`**: aguardar mensagem JSF de confirmação após cada save crítico (timeout 30s não-bloqueante)
2. **`_extrair_numero_calculo()`**: após Fase 2 save, extrair número do cálculo do DOM. Se ausente → save falhou silenciosamente
3. **Captura de download via diretório**: configurar Firefox download dir + scan do dir após Exportar (mais robusto que `page.on("download")`)
4. **Verbas Expresso uma-por-vez**: marcar checkbox → salvar → parametrizar → repetir (evita NPE em batch)
5. **Liquidar com timeout não-bloqueante**: se mensagem não vier em 30s, prosseguir mesmo assim
