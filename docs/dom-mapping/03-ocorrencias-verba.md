# DOM Mapping — Ocorrências da Verba

**URL**: `/pjecalc/pages/calculo/parametrizar-ocorrencia.jsf`  
**Caminho**: Cálculo > Verbas > [ícone Ocorrências] da linha da verba

## Header — Alteração em Lote
| Campo | DOM ID | Tipo | Descrição |
|---|---|---|---|
| Data Inicial | `formulario:dataInicialInputDate` | text | DD/MM/YYYY — limita o lote |
| Data Final | `formulario:dataFinalInputDate` | text | DD/MM/YYYY |
| Divisor | `formulario:divisor` | text | número |
| Multiplicador | `formulario:multiplicador` | text | número |
| Quantidade | `formulario:quantidade` | text | número |
| Proporcionalizar Quantidade | `formulario:propQuantidade` | select | (?) |
| Dobra | `formulario:dobra` | select | (SIM/NAO) |
| Devido | `formulario:devido` | text | valor monetário |
| Proporcionalizar Devido | `formulario:propDevido` | select | (?) |
| Pago | `formulario:pago` | text | valor monetário |
| Proporcionalizar Pago | `formulario:propPago` | select | (?) |
| **Botão Alterar** | `formulario:recuperar` | input button | aplica em todas linhas selecionadas |

## Tabela de Ocorrências (linhas mensais)
| Coluna | DOM ID | Tipo |
|---|---|---|
| Ativo? (cabeçalho marcar todos) | `formulario:listagem:ativarTodos` | checkbox |
| Selecionar (cabeçalho selecionar todos para Lote) | `formulario:listagem:selecionarTodos` | checkbox |
| Ativo (linha N) | `formulario:listagem:N:ativo` | checkbox |
| Selecionar (linha N) | `formulario:listagem:N:selecionar` | checkbox |
| Data Inicial (linha N) | (auto) | exibido como label |
| Data Final (linha N) | (auto) | exibido como label |
| Divisor por linha | `formulario:listagem:N:termoDiv` | text |
| Multiplicador por linha | `formulario:listagem:N:termoMult` | text |
| Quantidade por linha | `formulario:listagem:N:termoQuant` | text |
| Dobra por linha | `formulario:listagem:N:dobra` | checkbox |
| **Devido por linha** | `formulario:listagem:N:valorDevido` | text |
| **Pago por linha** | `formulario:listagem:N:valorPago` | text |

## Botões Globais
| Função | DOM ID |
|---|---|
| Salvar | `formulario:salvar` |
| Cancelar | `formulario:cancelar` |

## Como a automação deve operar (NOVA arquitetura)

### Caso 1: verba com Valor=CALCULADO (default Expresso)
- Ocorrências são geradas automaticamente a partir dos parâmetros
  (Base, Divisor, Multiplicador, Quantidade) já configurados em "Parâmetros da Verba".
- Na maioria dos casos, **não há nada a alterar** nesta página — basta clicar
  Salvar para confirmar a estrutura.
- Se a sentença determina **quantidade específica de horas** para HE/intervalo,
  a prévia deve trazer `quantidade_mensal_horas` e a automação preenche o campo
  "Quantidade" do Lote + clica Alterar (aplica em todas linhas marcadas).

### Caso 2: verba com Valor=INFORMADO (indenização, dano moral)
- A prévia DEVE trazer `valor_devido_mensal`.
- A automação preenche o campo "**Devido**" do Lote + clica Alterar.
- Resultado: todas as linhas ativas ficam com `valorDevido = valor_devido_mensal`.
- **Sem isso, todas as linhas ficam 0,00 e Liquidar rejeita.**

### Caso 3: verba com valores variáveis mês a mês (raro — sentença com tabela)
- A prévia traz `ocorrencias_explicitas: [{mes, valor}, ...]`.
- A automação itera sobre as linhas e preenche `formulario:listagem:N:valorDevido`
  diretamente (sem usar Lote).

## Filtro de Período
Quando a verba tem período menor que o cálculo total (ex: indenização que cobre
só os 12 meses pós-rescisão), a automação deve **desmarcar** as linhas fora do
período via `formulario:listagem:N:ativo` (checkbox) — ou usar o botão "Ativar Todos"
do cabeçalho e depois desmarcar os fora.
