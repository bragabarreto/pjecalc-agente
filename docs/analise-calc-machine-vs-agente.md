# Análise Comparativa: Calc Machine vs. PJECalc Agente

Este documento apresenta uma análise detalhada do funcionamento do sistema **Calc Machine** e o compara com a arquitetura atual do projeto **PJECalc Agente**, com o objetivo de identificar as melhores práticas e estratégias para replicar o sucesso da automação.

## 1. Como o Calc Machine Funciona

O Calc Machine divide o processo em duas etapas distintas e bem separadas: **Extração de Dados (IA)** e **Automação de Preenchimento (RPA)**.

### 1.1. Etapa 1: Extração e Estruturação de Dados (IA)
1. O usuário insere o texto da sentença (ou relatório estruturado) em um campo de texto.
2. O sistema envia esse texto para uma API de LLM (provavelmente OpenAI ou Claude) com um prompt rigoroso que exige a saída em um formato JSON estrito.
3. O JSON retornado mapeia **todos** os campos necessários para o PJE-Calc (dados do processo, verbas rescisórias, adicionais, jornada de trabalho, honorários, etc.).
4. **Ponto Chave:** O sistema carrega esse JSON em um formulário visual interativo, permitindo que o usuário **revise e corrija** os dados antes de iniciar a automação. Isso evita que erros da IA quebrem o robô na etapa seguinte.

### 1.2. Etapa 2: Automação de Preenchimento (RPA)
1. Após a validação do JSON (o sistema verifica se campos obrigatórios, como o tipo de gratificação, estão preenchidos), o usuário clica em "Executar Automação".
2. O sistema inicia um processo em background (PID isolado) usando uma ferramenta de automação de navegador (como Playwright ou Selenium).
3. **Estratégia de Acesso:** O robô acessa uma instância do **PJE-Calc Cidadão** que já está rodando em um servidor ou container Docker controlado pelo Calc Machine (não na máquina do usuário).
4. **Fluxo de Preenchimento:**
   - Clica em "Criar Novo Cálculo" (não usa "Cálculo Externo").
   - Preenche os Parâmetros do Cálculo (número, estado, município, datas).
   - Salva e aguarda o processamento (AJAX).
   - Navega pelas abas laterais (Férias, Histórico Salarial, Verbas, Cartão de Ponto, Honorários, etc.) de forma sequencial.
   - Para cada aba, preenche os dados baseados no JSON validado.
   - Lida com as tabelas dinâmicas do JSF/RichFaces clicando em links específicos (ex: `formulario:listagem:0:listaReflexo:0:ativo`).
5. **Liquidação e Exportação:**
   - Após preencher tudo, vai para a aba "Operações" > "Liquidar".
   - Executa a liquidação e aguarda a mensagem de sucesso.
   - Vai para "Exportar" e baixa o arquivo `.PJC`.
6. O arquivo `.PJC` baixado pelo robô é então salvo no banco de dados do sistema web e disponibilizado para o usuário na aba "Meus Arquivos".

---

## 2. Comparação com o PJECalc Agente

Abaixo estão as principais diferenças entre a abordagem do Calc Machine e a do seu repositório atual:

| Característica | Calc Machine | PJECalc Agente (Atual) |
| :--- | :--- | :--- |
| **Arquitetura** | Web App centralizado. O robô roda no servidor acessando uma instância própria do PJE-Calc. | Script local/Extensão. Tenta rodar o PJE-Calc na máquina do usuário via `iniciarPjeCalc.sh`. |
| **Validação de Dados** | O JSON gerado pela IA é exibido em um formulário para revisão humana antes da automação. | O JSON vai direto da extração para a automação, aumentando a chance de falhas por dados incompletos. |
| **Estratégia de Criação** | Clica em **"Criar Novo Cálculo"** e preenche tudo do zero pela interface web. | Tenta usar **"Cálculo Externo"** (importar um `.PJC` base) e depois editar, o que causa conflitos de IDs no JSF. |
| **Controle de Estado (AJAX)** | Aguarda explicitamente mensagens de sucesso ("Operação realizada com sucesso") após cada clique em "Salvar". | Usa `page.wait_for_timeout()` fixos ou espera por seletores que podem mudar, causando falhas de sincronia. |
| **Isolamento** | Cada execução roda em um processo isolado (PID único) com seu próprio contexto de navegador. | Múltiplas estratégias concorrentes (Playwright principal, script gerado, extensão) que podem conflitar. |

---

## 3. Como Replicar o Sucesso no Seu Projeto

Para que o **PJECalc Agente** funcione de forma tão fluida quanto o Calc Machine, recomendo as seguintes mudanças arquiteturais:

### Passo 1: Adotar a Abordagem "Novo Cálculo"
Abandone a ideia de usar "Cálculo Externo" ou gerar um arquivo `.PJC` de backup diretamente. O PJE-Calc é muito sensível a arquivos importados.
**Ação:** Atualize o script Playwright para sempre clicar em "Criar Novo Cálculo" e preencher os dados aba por aba, exatamente como um humano faria.

### Passo 2: Implementar a Etapa de Revisão (Human-in-the-loop)
A IA (Claude/OpenAI) pode errar ou omitir dados. Se o robô tentar preencher um campo vazio, ele vai falhar.
**Ação:** No seu `webapp.py`, após a extração (`extraction.py`), renderize o JSON em um formulário HTML. Só permita que o usuário clique em "Executar Automação" após revisar e validar os dados.

### Passo 3: Melhorar a Sincronia com o JSF (RichFaces)
O PJE-Calc usa JSF antigo, onde quase todo clique gera um request AJAX que bloqueia a tela.
**Ação:** Crie uma função utilitária no Playwright que clique em "Salvar" e espere especificamente pelo elemento de mensagem de sucesso (`.rf-msgs-sum` ou similar contendo "Operação realizada com sucesso") antes de ir para a próxima aba.

### Passo 4: Resolver o Problema do Lancador Java
O seu script `iniciarPjeCalc.sh` tenta iniciar o PJE-Calc em background, mas o Lancador Java bloqueia esperando input no terminal.
**Ação:** Em vez de tentar iniciar o PJE-Calc via script a cada execução, assuma que o PJE-Calc já está rodando (seja via Docker ou iniciado manualmente pelo usuário) e faça o Playwright conectar diretamente em `http://localhost:8080/pjecalc`.

### Passo 5: Unificar a Base de Código
Atualmente você tem o `playwright_pjecalc.py`, o `playwright_script_builder.py` e uma extensão do Chrome. Isso gera confusão.
**Ação:** Escolha apenas uma via. A melhor é usar o **Playwright puro via Python** (como no `playwright_pjecalc.py`), rodando em modo *headless* (oculto), recebendo o JSON validado do `webapp.py`.

## Conclusão

O segredo do Calc Machine não é uma IA mágica que preenche o PJE-Calc diretamente, mas sim um **pipeline bem orquestrado**:
`IA extrai -> Humano revisa -> Robô (Playwright) digita como humano -> Robô exporta o PJC`.

Se você ajustar o seu projeto para seguir esse mesmo pipeline linear, abandonando os atalhos (como Cálculo Externo), você conseguirá o mesmo nível de estabilidade.
