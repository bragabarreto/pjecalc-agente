import java.lang.instrument.Instrumentation;
import java.security.Permission;

/**
 * DialogSuppressorAgent — Java Agent para headless PJE-Calc no Railway/Docker.
 *
 * Estratégias (sem dependências externas):
 *
 * 1. NoExitSecurityManager
 *    Intercepta System.exit(código≠0) e lança ExitAttemptException em vez
 *    de matar o JVM. Garante que mesmo se o xdotool dismssar um JOptionPane
 *    e o código subsequente chamar System.exit(1), o processo sobrevive e
 *    o Tomcat continua rodando em suas threads.
 *
 * 2. java.awt.headless=false (garantia explícita)
 *    Força AWT a não rodar em modo headless quando DISPLAY=:99 estiver
 *    configurado.
 *
 * Os dialogs Swing (JOptionPane) são tratados pelo xdotool no
 * iniciarPjeCalc.sh (camada GUI). O SecurityManager é a rede de segurança
 * para o System.exit(1) que segue o dialog.
 *
 * Compilação (dentro do Dockerfile):
 *   javac DialogSuppressorAgent.java
 *   jar cfm dialog-suppressor.jar MANIFEST.MF DialogSuppressorAgent*.class
 *
 * Uso:
 *   java -javaagent:/opt/dialog-suppressor.jar -jar pjecalc.jar
 */
public class DialogSuppressorAgent {

    public static void premain(String agentArgs, Instrumentation inst) {
        log("Agent carregado v3.0 (SecurityManager only).");

        // Garantir que AWT não rode headless (Xvfb está disponível)
        if (System.getProperty("java.awt.headless") == null) {
            System.setProperty("java.awt.headless", "false");
            log("java.awt.headless=false configurado.");
        }

        // Instalar SecurityManager que intercepta System.exit(≠0)
        installNoExitSecurityManager();
    }

    public static void agentmain(String agentArgs, Instrumentation inst) {
        premain(agentArgs, inst);
    }

    static void log(String msg) {
        System.out.println("[DialogSuppressor] " + msg);
        System.out.flush();
    }

    // ── SecurityManager ───────────────────────────────────────────────────────

    static void installNoExitSecurityManager() {
        try {
            System.setSecurityManager(new NoExitSecurityManager());
            log("NoExitSecurityManager ativo — System.exit(≠0) será convertido em exceção.");
        } catch (SecurityException se) {
            log("AVISO: SecurityManager já instalado — " + se.getMessage());
        } catch (Exception e) {
            log("AVISO: Falha ao instalar SecurityManager — " + e.getMessage());
        }
    }

    /**
     * SecurityManager que:
     *  - Converte System.exit(código≠0) em ExitAttemptException (processo sobrevive)
     *  - Permite System.exit(0) para desligamento limpo
     *  - Permite todas as outras permissões (não restritivo)
     */
    public static final class NoExitSecurityManager extends SecurityManager {

        @Override
        public void checkExit(int status) {
            if (status != 0) {
                log("System.exit(" + status + ") interceptado — thread continuará.");
                throw new ExitAttemptException(status);
            }
            // status == 0: saída limpa permitida
        }

        @Override
        public void checkPermission(Permission perm) {
            // Permitir tudo exceto exit não-zero (tratado em checkExit)
        }

        @Override
        public void checkPermission(Permission perm, Object context) {
            // Permitir tudo
        }
    }

    public static final class ExitAttemptException extends RuntimeException {
        public final int exitStatus;

        public ExitAttemptException(int exitStatus) {
            super("System.exit(" + exitStatus + ") bloqueado pelo DialogSuppressorAgent");
            this.exitStatus = exitStatus;
        }
    }
}
