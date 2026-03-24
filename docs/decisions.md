# Decisões Técnicas — Agente PJE-Calc

## 2026-03-23 — FASE 1: Estratégia de Desbloqueio do Lancador

**Contexto:** O Tomcat embarcado do PJE-Calc não sobe no Railway. O log Java para em
`[TRT8] Configurando variaveis basicas.`. Decompilação do `pjecalc.jar` com CFR revelou
três pontos de bloqueio distintos.

**Decisão:** Implementar Java Agent (Opção A do plano) usando Javassist para interceptar
chamadas de JOptionPane em runtime, sem modificar o JAR original.

**Motivo:** O JAR original não deve ser modificado (commitado como distribuição oficial do TRT8).
O Java Agent intercept é transparente, pode ser ativado/desativado via flag JVM, e não
requer recompilação ou acesso ao código-fonte original.

**Bloqueios identificados:**
1. `JOptionPane.showMessageDialog` em `validarPastaInstalador()` → se H2 não encontrado, seguido de `System.exit(1)`
2. `JOptionPane.showConfirmDialog` em `iniciarAplicacao()` → se porta 9257 já em uso, seguido de `System.exit(1)`
3. `Janela.setDefaultCloseOperation(EXIT_ON_CLOSE)` → xdotool pode fechar a janela matando o JVM

**Alternativa documentada:** Se o Agent falhar, iniciar Tomcat diretamente via
`org.apache.catalina.startup.Bootstrap` com os system properties mapeados na FASE 1.

---

## 2026-03-23 — FASE 2: Implementação do Java Agent

**Decisão:** DialogSuppressorAgent transforma 4 métodos de JOptionPane via Javassist:
- `showMessageDialog` → `return` void (suprime completamente)
- `showConfirmDialog` → `return 0` (YES_OPTION, para continuar execução)
- `showOptionDialog` → `return 0` (primeira opção)
- `showInputDialog` → `return null` (sem input)

E transforma `JFrame.setDefaultCloseOperation` para converter `EXIT_ON_CLOSE (3)` → `DISPOSE_ON_CLOSE (2)`.

**Estratégia de System.exit:** Ao suprimir `showMessageDialog` e retornar imediatamente,
o `System.exit(1)` subsequente ainda executa. Para evitar isso, transformamos
`Lancador.validarPastaInstalador()` para remover o `System.exit(1)` — ou instalamos
um SecurityManager que bloqueia `System.exit(1)`.

**Decisão final:** Usar SecurityManager custom (`NoExitSecurityManager`) que lança uma
exceção runtime ao invés de matar o JVM. Isso permite que o fluxo continue mesmo
quando o dialog é suprimido. O SecurityManager é instalado ANTES do Lancador.main() rodar
(no premain do Agent).

**Risco aceitável:** SecurityManager pode bloquear operações legítimas. Monitorar via
`GET /api/logs/java` após deploy.
