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

---

## 2026-03-24 — FASE 3: Correções Playwright por Playwright JSF Automator Skill

**Contexto:** Automação chegava na fase de verbas mas não detectava os campos do formulário.
Log mostrava `_form_abriu = False` mesmo após clicar em "Novo".

**Causa raiz identificada:** `no_viewport=True` em modo headless → elementos JSF reportam
`offsetParent === null` e `getBoundingClientRect() = {width:0, height:0}` → filtro de
visibilidade `e.offsetParent !== null` excluía TODOS os elementos → form nunca detectado.

**Decisões:**

1. Viewport explícito `{"width": 1920, "height": 1080}` substitui `no_viewport=True`
   — garante layout correto e `getBoundingClientRect()` funcional em headless.
2. Substituir `offsetParent !== null` por `getBoundingClientRect().width > 0 && height > 0`
   em todos os lugares JS (mapear_campos, fase_verbas) — confiável em headless e headed.
3. Adicionar `--no-sandbox --disable-dev-shm-usage` aos args do Chromium — obrigatórios
   em Docker (Railway usa container sem privilégios SUID sandbox).
4. Adicionar interceptores de rede (response ≥400 e console errors) para diagnóstico
   automático em produção via SSE log.

**Referência:** Playwright JSF Automator Skill §1 (setup), §2 (seleção robusta),
§3 (mapeamento automático), troubleshooting "Timeout: waiting for selector".
