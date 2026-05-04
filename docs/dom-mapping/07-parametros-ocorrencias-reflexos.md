# DOM Mapping — Parâmetros e Ocorrências de REFLEXOS

⚠️ **CRÍTICO** — esta página foi inicialmente OMITIDA dos docs 03 e 04.
Documentação verificada empiricamente em 2026-05-04 via Chrome MCP.

## 1. Acesso à página Parâmetros do REFLEXO

### Pré-condição
O ícone "Parametrizar" do reflexo só aparece **APÓS o checkbox do reflexo
estar marcado e SALVO** no servidor. Sequência obrigatória:

1. Expandir painel da verba principal:
   ```
   formulario:listagem:N:divDestinacoes .linkDestinacoes  (click — texto "Exibir")
   ```
2. Marcar checkbox do reflexo:
   ```
   formulario:listagem:N:listaReflexo:M:ativo  (click — dispara A4J.AJAX.Submit)
   ```
3. Aguardar AJAX completar (~2-3s — o servidor cria a entidade do reflexo)
4. **Aparece** o ícone Parametrizar:
   ```
   formulario:listagem:N:listaReflexo:M:j_id573  (anchor com title="Parametrizar")
   ```

### Para abrir a página de Parâmetros do reflexo
Click no anchor `formulario:listagem:N:listaReflexo:M:j_id573`.

⚠️ O sufixo `j_id573` é dinâmico no PJE-Calc. Selector mais robusto:
```css
#formulario\:listagem\:N\:listaReflexo\:M\:ativo + ... a[title="Parametrizar"]
```
Ou via TR ancestral:
```javascript
const cb = document.getElementById('formulario:listagem:N:listaReflexo:M:ativo');
const tr = cb.closest('tr');
const link = [...tr.querySelectorAll('a')].find(a => a.title === 'Parametrizar');
link.click();
```

## 2. Formulário "Dados de Verba" do REFLEXO

URL: `verba-calculo.jsf?conversationId=N` (mesma URL da Principal — distingue pelo conteúdo).  
Breadcrumb: `Cálculo > Verbas > Alterar`

### Diferenças vs Verba Principal

**Campos exclusivos do REFLEXO**:
| Campo | DOM ID | Tipo | Obs |
|---|---|---|---|
| Nome completo do Reflexo (readonly) | `formulario:nome` | text | Ex: "AVISO PRÉVIO SOBRE ADICIONAL DE INSALUBRIDADE 20%" |
| **Comportamento** | `formulario:comportamentoDoReflexo:0..3` | radio | VALOR_MENSAL / MEDIA_PELO_VALOR / MEDIA_PELO_VALOR_CORRIGIDO / MEDIA_PELA_QUANTIDADE |
| Tipo (sempre REFLEXO disabled) | `formulario:tipoDeVerba:1` | radio (disabled) | apenas REFLEXO selecionado |
| Quantidade (única opção) | `formulario:tipoDaQuantidade` | radio (única opção: APURADA) | sem `valorInformadoDaQuantidade` |
| Divisor (única opção) | `formulario:tipoDeDivisor` | radio (única opção: OUTRO_VALOR) | só `outroValorDoDivisor` (default 30) |

**Campos AUSENTES no REFLEXO** (existem na Principal):
- `tipoDaBaseTabelada` — não há (a base é a verba principal vinculada)
- `baseHistoricos` — não há
- `proporcionalizaHistorico` — não há
- `incluirBaseHistorico` — não há (mas há "+" verde para adicionar mais bases via `baseVerbaDeCalculo`)
- `aplicarProporcionalidadeABase` — não há
- `gerarPrincipal` — não há (Principal já existe; a reflexa não gera Principal)
- `valorInformadoDaQuantidade`, `aplicarProporcionalidadeAQuantidade` — não há (Quantidade é APURADA)
- `excluirFaltaJustificada`, `excluirFaltaNaoJustificada`, `excluirFeriasGozadas` — não há
- `integralizarBase` — não há (substituído por "Tratamento da Fração de Mês")

**Campos comuns** (mesmos da Principal):
- `descricao` (Nome curto da verba reflexa)
- `codigoAssuntosCnj`, `assuntosCnj`
- `tipoVariacaoDaParcela` (FIXA/VARIAVEL)
- `valor` (CALCULADO/INFORMADO)
- `irpf`, `inss`, `fgts`, `previdenciaPrivada`, `pensaoAlimenticia`
- `caracteristicaVerba` (COMUM/13o/AVISO/FERIAS) — **derivado automaticamente** do tipo do reflexo
- `ocorrenciaPagto` (DESLIGAMENTO/DEZEMBRO/MENSAL/PERIODO_AQUISITIVO)
- `ocorrenciaAjuizamento` (Súmula 439)
- `geraReflexo` (DEVIDO/DIFERENCA)
- `comporPrincipal` (SIM/NAO)
- `zeraValorNegativo`
- `periodoInicialInputDate`, `periodoFinalInputDate`
- `dobraValorDevido`
- `baseVerbaDeCalculo` (select com a verba principal já vinculada)
- `outroValorDoDivisor` (default 30 — fração mensal)
- `outroValorDoMultiplicador`
- `tipoDoValorPago`, `valorInformadoPago`, `aplicarProporcionalidadeValorPago`
- `comentarios`

**Fórmula gerada** (exemplo do reflexo Aviso Prévio sobre Insalubridade 20%):
```
((((ADICIONAL DE INSALUBRIDADE 20%) / 30,0000) X 1,00000000) X APURADA)
```

### Botões
| Função | DOM ID |
|---|---|
| Salvar | `formulario:salvar` |
| Cancelar | `formulario:cancelar` |

## 3. Seção "Reflexos" dentro da página Ocorrências da Verba Principal

Quando se acessa Ocorrências da verba principal (`parametrizar-ocorrencia.jsf`) e
há reflexos marcados, a página exibe uma **subseção "Reflexos"** abaixo da
tabela principal, com seu próprio header de Alteração em Lote e tabela.

### Estrutura DOM

```
formulario
├── (Cabeçalho da Verba Principal)
│   ├── dataInicialInputDate, dataFinalInputDate, divisor, multiplicador,
│   │   quantidade, propQuantidade, dobra, devido, propDevido, pago, propPago,
│   │   recuperar (botão Alterar)
│   └── listagem:N:* (linhas mensais: ativo, termoDiv, termoMult, termoQuant,
│       dobra, valorDevido, valorPago, selecionar)
└── reflexos:N:*  ← seção repetida para CADA reflexo marcado
    ├── (Cabeçalho do Reflexo)
    │   ├── reflexos:N:dataInicialInputDate, dataFinalInputDate
    │   ├── reflexos:N:divisor, multiplicador, quantidade
    │   ├── reflexos:N:propQuantidade (select), dobra (select)
    │   ├── reflexos:N:devido, propDevido (select)
    │   ├── reflexos:N:pago, propPago (select)
    │   └── reflexos:N:recuperar (botão Alterar)
    └── reflexos:N:listagem:M:* (linhas mensais por reflexo)
        ├── reflexos:N:listagem:M:ativo (checkbox)
        ├── reflexos:N:listagem:M:termoDivReflexo (text)
        ├── reflexos:N:listagem:M:termoMultReflexo (text)
        ├── reflexos:N:listagem:M:termoQuantReflexo (text)
        ├── reflexos:N:listagem:M:dobra (checkbox)
        ├── reflexos:N:listagem:M:valorDevidoReflexo (text)
        ├── reflexos:N:listagem:M:valorPagoReflexo (text)
        └── reflexos:N:listagem:M:selecionar (checkbox)
```

### Diferenças importantes vs tabela Principal

| Coluna | Principal (DOM ID) | Reflexo (DOM ID) |
|---|---|---|
| Multiplicador linha | `listagem:N:termoMult` | `reflexos:N:listagem:M:termoMultReflexo` |
| Quantidade linha | `listagem:N:termoQuant` | `reflexos:N:listagem:M:termoQuantReflexo` |
| Devido linha | `listagem:N:valorDevido` | `reflexos:N:listagem:M:valorDevidoReflexo` |
| Pago linha | `listagem:N:valorPago` | `reflexos:N:listagem:M:valorPagoReflexo` |
| Divisor linha | `listagem:N:termoDiv` | `reflexos:N:listagem:M:termoDivReflexo` |

⚠️ **Importante**: os IDs do reflexo têm sufixo `Reflexo` em campos texto
(termoMultReflexo, termoQuantReflexo, valorDevidoReflexo, valorPagoReflexo,
termoDivReflexo). Os campos `ativo`, `dobra`, `selecionar` permanecem sem
o sufixo. Selectors do agente devem cobrir AMBOS os padrões via `[id$=':valorDevido']`
ou `[id$=':valorDevidoReflexo']`.

### Quantidade de linhas
Cada reflexo tem sua própria tabela mensal com linhas para os meses em que ele
ocorre. Por exemplo:
- Reflexo "Aviso Prévio sobre Adic Insalub" → 1 linha (mês do desligamento)
- Reflexo "13º sobre Adic Insalub" → linhas para cada dezembro do período
- Reflexo "Férias + 1/3 sobre Adic Insalub" → linhas para cada período aquisitivo

### Botão Salvar
O botão `formulario:salvar` salva tanto a tabela principal quanto **todas as
sub-tabelas de reflexos** simultaneamente. Não há salvar separado para cada reflexo.

## 4. Implicações para a arquitetura do agente

### Fase 2 — Schema da prévia
O nó `reflexos[]` de cada verba principal precisa armazenar:
```json
{
  "nome": "Aviso Prévio sobre Adic Insalubridade 20%",
  "estrategia_reflexa": "checkbox_painel" | "manual",
  "indice_reflexo_listagem": 0,           // M no listaReflexo:M
  "parametros": {                          // ← se diferente do default
    "comportamento": "VALOR_MENSAL",        // ou MEDIA_PELO_VALOR | _CORRIGIDO | _PELA_QUANTIDADE
    "tratamento_fracao_mes": "INTEGRALIZAR",
    "outro_valor_divisor": 30,
    "outro_valor_multiplicador": 1,
    // ... + os mesmos campos comuns da Principal (caracteristica, ocorrencia, etc.)
  },
  "ocorrencias": {                         // ← se necessário sobrescrever
    "modo": "default",                      // mantém valores calculados pelo Expresso
    // ou "valores_explicitos" se sentença determina valores específicos
  }
}
```

### Fase 5 — Automação
Sequência obrigatória para ativar reflexo:
1. Navegar para listagem de Verbas
2. Expandir painel da verba principal (`linkDestinacoes`)
3. Click no checkbox do reflexo (`listaReflexo:M:ativo`) — aguardar AJAX
4. Se prévia tem ajustes específicos: click `:j_id573` (Parametrizar) → preencher → Salvar
5. Quando navegar a Ocorrências da verba principal:
   - Tabela principal usa `listagem:N:*`
   - Subtabela do reflexo usa `reflexos:M:listagem:K:*Reflexo`
   - Salvar UMA VEZ persiste tudo

### Auto-correção
Quando pendência indica problema em reflexo (ex: "valorDevido zero em
13º SOBRE X"), a automação precisa:
1. Navegar a Ocorrências da verba **principal X**
2. Localizar a sub-tabela `reflexos:M:*` desejada
3. Preencher `reflexos:M:devido` (Lote) ou `reflexos:M:listagem:K:valorDevidoReflexo`
4. Click `formulario:salvar`
