# Diagnóstico: Falhas no Preenchimento Automático do PJE-Calc

Após uma análise aprofundada do repositório `pjecalc-agente`, identifiquei diversas razões estruturais e arquiteturais que explicam por que o preenchimento automático dos dados da condenação no PJE-Calc não está funcionando de forma consistente. O projeto apresenta uma complexidade elevada devido à natureza do sistema alvo (PJE-Calc Cidadão, baseado em Java/Tomcat e JSF/RichFaces) e à existência de múltiplas abordagens de automação concorrentes no mesmo código.

Abaixo, detalho as principais causas identificadas, divididas em problemas de infraestrutura, inconsistências de automação e desafios de interface.

## 1. Instabilidade na Inicialização do PJE-Calc (Problema de Infraestrutura)

O principal gargalo técnico reside na forma como o PJE-Calc é inicializado, especialmente em ambientes headless (como Docker ou Railway). O aplicativo alvo não foi desenhado para ser um serviço de backend puro, o que gera bloqueios severos antes mesmo de a automação começar.

**Bloqueios do Lancador Java:**
O arquivo `pjecalc.jar` possui uma classe `Lancador` que executa validações de ambiente ao iniciar. Conforme documentado em `docs/lancador-analysis.md`, existem três pontos críticos de falha:
1. **Validação do Banco de Dados:** Se o banco H2 não for encontrado, o sistema exibe um `JOptionPane` (interface gráfica Swing) e, ao ser fechado, executa `System.exit(1)`, matando o processo.
2. **Verificação de Porta:** Se a porta 9257 já estiver em uso (por exemplo, após um reinício mal-sucedido), outro dialog é exibido. Se não for tratado corretamente, o processo também é encerrado.
3. **Dependência de Interface Gráfica:** A janela principal (`Janela`) utiliza `setDefaultCloseOperation(EXIT_ON_CLOSE)`. Qualquer fechamento acidental dessa janela (mesmo por scripts de automação como o `xdotool`) derruba o servidor Tomcat embarcado.

**Workarounds Frágeis:**
O script `iniciarPjeCalc.sh` tenta contornar esses problemas subindo um display virtual (`Xvfb`), um gerenciador de janelas (`fluxbox` ou `openbox`) e um script de auto-dismiss usando `xdotool` para clicar em botões "OK" ou "Sim" nas janelas de erro. Essa abordagem é extremamente frágil e sujeita a falhas de temporização (race conditions). Se o `xdotool` falhar ou demorar, o Tomcat nunca sobe, e o Playwright não tem onde preencher os dados.

## 2. Concorrência de Múltiplas Estratégias de Automação

O repositório sofre de uma crise de identidade arquitetural. Existem pelo menos três implementações distintas de automação competindo entre si, com regras e seletores divergentes. Isso explica por que "tentar de tudo" não resolve: dependendo de como o usuário executa, ele aciona um código diferente.

**A. Automação Principal (Playwright SSE)**
Localizada em `modules/playwright_pjecalc.py`, esta é a implementação mais robusta. Ela segue a convenção documentada no `CLAUDE.md` de usar o menu **"Novo"** para criar a primeira liquidação. Possui tratamento avançado para AJAX do JSF, recuperação de crash do Chromium e seletores hierárquicos.

**B. Script Standalone Gerado**
O arquivo `modules/playwright_script_builder.py` gera um script Python que o usuário baixa e roda localmente. O problema crítico aqui é que este script ignora a convenção do `CLAUDE.md` e navega explicitamente para **"Cálculo Externo"** (`/pages/calculo/calculo-externo.xhtml`). Além disso, utiliza seletores CSS rígidos e pausas manuais (`_pausar()`), sendo muito menos resiliente a mudanças na interface do PJE-Calc.

**C. Extensão de Navegador**
A pasta `extension/` contém uma extensão Chrome/Firefox (`content.js`) que implementa uma terceira via de automação injetada diretamente no DOM. Assim como o script gerado, ela também força o uso de **"Cálculo Externo"** e depende de eventos JavaScript manuais (`input`, `change`, `blur`) que frequentemente falham em acionar os listeners AJAX do RichFaces, resultando em campos que parecem preenchidos na tela, mas não são salvos no backend.

## 3. Desafios com a Interface JSF / RichFaces

O PJE-Calc utiliza tecnologias legadas (JavaServer Faces e RichFaces) que são notoriamente difíceis de automatizar devido ao comportamento dinâmico do DOM e ao gerenciamento de estado no servidor.

**Eventos AJAX e ViewState:**
Muitos campos no PJE-Calc disparam requisições AJAX ao perderem o foco (`blur`). Se a automação preencher os campos muito rápido ou não aguardar a conclusão do AJAX, o servidor pode retornar erros HTTP 500 ou invalidar o `ViewState` da página (`ViewExpiredException`). O módulo `playwright_pjecalc.py` tenta mitigar isso injetando um monitor AJAX (`jsf.ajax.addOnEvent`), mas as outras abordagens (script gerado e extensão) não possuem essa proteção.

**Campos de Data e Máscaras:**
Campos de data utilizam o componente RichFaces Calendar. Clicar nesses campos abre um popup que intercepta eventos. A automação principal tenta usar `focus()` e `press_sequentially()` seguido de `Escape` para evitar o popup, mas qualquer variação no tempo de resposta do navegador pode quebrar esse fluxo.

**Identificadores Dinâmicos:**
Os IDs dos elementos no JSF frequentemente mudam ou contêm prefixos dinâmicos (ex: `formulario:j_id_jsp_123:dataAdmissao`). A automação precisa usar seletores baseados em sufixos (`[id$='dataAdmissao']`), o que aumenta o risco de selecionar elementos ocultos ou incorretos.

## 4. Geração de Arquivo .PJC como Backup Incompleto

Devido às falhas na automação da interface, o sistema tenta gerar um arquivo `.PJC` nativo (`modules/pjc_generator.py`) como alternativa. No entanto, a análise desse gerador revela que ele aplica simplificações severas:
- Zera o valor da causa (`valorDaCausa = 0.00`).
- Ignora a data de autuação (`dataAutuacao = null`).
- Oculta documentos fiscais de reclamante e reclamado.
- Infere fórmulas de verbas de maneira genérica, o que pode não refletir as particularidades da sentença extraída.

Isso significa que, mesmo quando a automação falha e o usuário recorre ao arquivo `.PJC`, os dados importados no PJE-Calc estarão incompletos ou incorretos.

## Conclusão e Recomendações

O fracasso no preenchimento não se deve a um único erro de código, mas a uma combinação de um ambiente alvo hostil (PJE-Calc legado) e uma arquitetura fragmentada no projeto.

Para estabilizar o preenchimento, recomendo as seguintes ações:

1. **Unificar a Estratégia de Automação:** Eliminar o script standalone e a extensão de navegador. Concentrar todos os esforços no `playwright_pjecalc.py`, garantindo que exista apenas uma "fonte da verdade" para os seletores e fluxos de navegação.
2. **Respeitar a Convenção "Novo" vs "Cálculo Externo":** Garantir que todo o código siga a diretriz do `CLAUDE.md` de usar o menu "Novo" para a primeira liquidação, pois o formulário de "Cálculo Externo" possui comportamentos diferentes e menos previsíveis.
3. **Bypass do Lancador Java:** Em vez de usar `xdotool` para fechar janelas de erro, alterar o `iniciarPjeCalc.sh` para iniciar o Tomcat diretamente via classe `Bootstrap`, ignorando completamente a interface gráfica do `Lancador`. Isso eliminará 90% das falhas de inicialização em ambientes de nuvem.
4. **Aprimorar o Gerador .PJC:** Atualizar o `pjc_generator.py` para mapear corretamente todos os campos extraídos da sentença, tornando-o uma alternativa viável e completa quando a automação da interface não for possível.
