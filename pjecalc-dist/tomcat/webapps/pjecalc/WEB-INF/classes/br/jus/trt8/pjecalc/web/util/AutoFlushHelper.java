package br.jus.trt8.pjecalc.web.util;

import javax.persistence.EntityManager;
import javax.persistence.FlushModeType;

import org.jboss.seam.Component;
import org.jboss.seam.ScopeType;
import org.jboss.seam.annotations.Name;
import org.jboss.seam.annotations.Observer;
import org.jboss.seam.annotations.Scope;
import org.jboss.seam.annotations.Startup;
import org.jboss.seam.annotations.intercept.BypassInterceptors;
import org.jboss.seam.log.Log;
import org.jboss.seam.log.Logging;

/**
 * Workaround para o bug de persistência no PJE-Calc Cidadão com H2.
 *
 * Causa raiz: Cálculos criados via "Novo" não persistem no H2 porque o Seam EPC
 * (Extended Persistence Context) usa FlushMode.MANUAL e o @End que dispararia o
 * flush só acontece em paths específicos (exportacao, etc) que requerem que o
 * cálculo já esteja no banco — chicken-and-egg.
 *
 * Solução: escutar eventos do ciclo de vida Seam e forçar:
 *   1) FlushMode.AUTO no EPC após cada beginConversation (incluindo @Begin nested)
 *   2) Flush explícito antes do render da view
 *
 * Risco aceitável: estados intermediários podem persistir se usuário cancelar.
 * Para nosso caso (automação que vai até o fim), isso não é problema.
 */
@Name("autoFlushHelper")
@Scope(ScopeType.APPLICATION)
@Startup
@BypassInterceptors
public class AutoFlushHelper {

    private static final Log log = Logging.getLog(AutoFlushHelper.class);

    /**
     * Toda vez que uma conversa Seam começa (inclusive nested), força AUTO mode.
     * Cobre tanto Begin global quanto @Begin(nested=true, flushMode=MANUAL).
     */
    @Observer({"org.jboss.seam.beginConversation",
               "org.jboss.seam.beginNestedConversation",
               "org.jboss.seam.postCreate.entityManager"})
    public void forceAutoFlushMode() {
        try {
            EntityManager em = (EntityManager) Component.getInstance("entityManager", false);
            if (em != null && em.isOpen()) {
                FlushModeType cur = em.getFlushMode();
                if (cur != FlushModeType.AUTO) {
                    em.setFlushMode(FlushModeType.AUTO);
                    log.info("[AutoFlushHelper] FlushMode " + cur + " → AUTO");
                }
            }
        } catch (Throwable t) {
            log.warn("[AutoFlushHelper] forceAutoFlushMode falhou: " + t.getMessage());
        }
    }

    /**
     * Antes de renderizar qualquer view JSF, flusha o EPC.
     * Garante que mudanças feitas durante o INVOKE_APPLICATION phase
     * sejam commitadas antes que o usuário navegue para fora.
     */
    @Observer("org.jboss.seam.preRenderView")
    public void flushBeforeRender() {
        try {
            EntityManager em = (EntityManager) Component.getInstance("entityManager", false);
            if (em != null && em.isOpen()) {
                em.setFlushMode(FlushModeType.AUTO);
                em.flush();
            }
        } catch (Throwable t) {
            // Silencioso: render não deve falhar por causa do flush
        }
    }
}
