# Lancador Analysis — FASE 1

**Data:** 2026-03-23
**JAR analisado:** `pjecalc-dist/bin/pjecalc.jar`
**Ferramenta:** CFR 0.152

---

## Fluxo completo do `Lancador.main()`

```
[TRT8] Caminho da instalacao : /opt/pjecalc
[TRT8] Configurando variaveis basicas.
  → configurarVariaveisBase()
    [TRT8] Buscando porta HTTP.
    [TRT8] Buscando url correta.
    [TRT8] Porta HTTP: 9257
    [TRT8] URL HTTP: http://localhost:9257/pjecalc
[TRT8] Validando a existencia do banco H2.
  → validarPastaInstalador()      ← BLOQUEIO POSSÍVEL #1
[TRT8] Iniciando a aplicacao.
  → iniciarAplicacao()            ← BLOQUEIO POSSÍVEL #2
[TRT8] Fim.
```

---

## Ponto de Bloqueio #1 — `validarPastaInstalador()`

**Código exato (decompilado):**
```java
private static void validarPastaInstalador() throws Exception {
    File file = new File(Lancador.getURLBanco());
    if (!file.exists()) {
        StringBuilder msg = new StringBuilder();
        msg.append("O banco de dados não foi encontrado para o atual usuário (");
        msg.append(System.getProperty("user.name"));
        // ... mensagem de erro ...
        JOptionPane.showMessageDialog(null, msg.toString(), "Erro", 0);  // ← BLOQUEIA
        System.exit(1);  // ← MATA o processo após dialog ser fechado
    } else {
        // Se persistence.xml.tmp existe, processa e converte para persistence.xml
        // (não é o caso em pjecalc-dist/ — persistence.xml já existe)
    }
}
```

**`getURLBanco()` retorna:**
```java
Desinstalador.getPastaInstalacao() + ".dados" + File.separator + "pjecalc.h2.db"
// = System.getProperty("caminho.instalacao") + "/" + ".dados/pjecalc.h2.db"
// = /opt/pjecalc/.dados/pjecalc.h2.db
```

**Status em Docker:**
- `/opt/pjecalc/.dados/pjecalc.h2.db` existe (commitado com exceção no .gitignore) ✓
- Se o arquivo não existir → JOptionPane bloqueia → xdotool dismisses → `System.exit(1)` mata o processo

---

## Ponto de Bloqueio #2 — `iniciarAplicacao()`

**Código exato:**
```java
private static void iniciarAplicacao() throws Exception {
    block8: {
        try {
            new Socket("localhost", (int)PORTA_HTTP_EM_USO);  // testa se 9257 já está aberto
            int escolhaDoUsuario = JOptionPane.showConfirmDialog(  // ← BLOQUEIA se porta em uso
                null,
                "O PJe-Calc Cidadão aberto da última vez não foi encerrado completamente...",
                "Confirmação", 0, 2);
            if (escolhaDoUsuario == 0) {    // Sim = continuar com instância existente
                Lancador.abrirSite();
                break block8;
            }
            System.exit(1);                 // Não = MATA o processo
        }
        catch (Exception e) {              // Porta livre = fluxo normal
            TomCat tomCat = new TomCat("tomcat");
            tomCat.startTomcat();           // Inicia Tomcat (async via Bootstrap)
            if (SystemTray.isSupported() && Desktop.isDesktopSupported()) {
                // Modo desktop (Windows): Bandeja do sistema + abre browser
                new Bandeja().adicionar(tomCat);
                Lancador.abrirSite();
            } else {
                // Modo headless/servidor (Docker): cria JFrame simples
                new Janela(tomCat);         // ← BLOQUEIO POSSÍVEL #3
            }
        }
    }
}
```

**Riscos em Docker:**
1. Se porta 9257 já estiver em uso (restart sem cleanup) → dialog → possivelmente `System.exit(1)`
2. `new Janela(tomCat)` com `setDefaultCloseOperation(EXIT_ON_CLOSE=3)` — se xdotool fechar a janela via Alt+F4 ou WM close → `System.exit(0)` → mata Tomcat

---

## Ponto de Bloqueio #3 — `Janela` com EXIT_ON_CLOSE

```java
public Janela(TomCat cat) {
    super("PjeCalc");
    this.cat = cat;
    this.init();
    this.setDefaultCloseOperation(3);  // EXIT_ON_CLOSE — mata JVM ao fechar janela
    this.pack();
    this.setLocationRelativeTo(null);
    this.setVisible(true);             // Aparece no Xvfb
}
```

Se o xdotool enviar um evento de fechar janela (WM_DELETE_WINDOW) ao invés de apenas Enter/Space, o JVM morre levando o Tomcat junto.

---

## Como Tomcat é iniciado

```java
// TomCat.startTomcat()
Bootstrap daemon = new Bootstrap();
daemon.setCatalinaHome("/opt/pjecalc/tomcat");  // catalina.home via System.setProperty
daemon.init();    // configura classloaders, lê catalina.properties, conf/
daemon.start();   // inicia os conectores Tomcat em threads separadas (retorna imediatamente)
```

**Estrutura de diretórios de `/opt/pjecalc/tomcat`:**
```
tomcat/
├── conf/       ← server.xml, context.xml, catalina.properties
├── lib/        ← bibliotecas compartilhadas
├── logs/       ← catalina.out
├── temp/
├── webapps/    ← pjecalc/ (o WAR explodido)
└── work/
```
**Nota:** `tomcat/bin/` NÃO EXISTE em `pjecalc-dist/`. O Bootstrap é carregado via `-jar pjecalc.jar` (classpath do manifest inclui `bin/lib/*.jar`).

**JDBC H2:**
```xml
<!-- tomcat/webapps/pjecalc/META-INF/context.xml -->
url="jdbc:h2:.dados/pjecalc"
<!-- Relativo ao cwd = /opt/pjecalc → /opt/pjecalc/.dados/pjecalc.h2.db -->
```

---

## System.setProperty necessários

| Propriedade | Valor | Onde é usado |
|---|---|---|
| `caminho.instalacao` | `/opt/pjecalc` | `Desinstalador.getPastaInstalacao()` → path do H2 |
| `catalina.home` | `/opt/pjecalc/tomcat` | Bootstrap.init() → estrutura Tomcat |
| `file.encoding` | `ISO-8859-1` | Encoding padrão do PJE-Calc |
| `user.timezone` | `GMT-3` | Timestamps BR |
| `seguranca.pjecalc.tokenServicos` | `pW4jZ4g9VM5MCy6FnB5pEfQe` | Autenticação interna |

---

## Conclusão

**Tipo de bloqueio:** Múltiplo — JOptionPane + System.exit + EXIT_ON_CLOSE

**Estratégia recomendada:** Java Agent (Opção A) usando Javassist para interceptar:
1. `JOptionPane.showMessageDialog` → retornar void imediatamente
2. `JOptionPane.showConfirmDialog` → retornar `0` (YES_OPTION = continuar)
3. `JOptionPane.showOptionDialog` → retornar `0`
4. `Janela.setDefaultCloseOperation(3)` → alterar para `DISPOSE_ON_CLOSE (2)`

**Alternativa se Java Agent falhar:** Opção B — Iniciar Tomcat direto via Bootstrap, bypassando Lancador completamente.
