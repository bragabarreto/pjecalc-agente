package br.jus.trt8.pjecalc.web.util;

import javax.persistence.EntityManager;
import javax.persistence.FlushModeType;

import org.jboss.seam.Component;
import org.jboss.seam.ScopeType;
import org.jboss.seam.annotations.Name;
import org.jboss.seam.annotations.Observer;
import org.jboss.seam.annotations.Scope;
import org.jboss.seam.annotations.Startup;
import org.jboss.seam.log.Log;
import org.jboss.seam.log.Logging;

/**
 * Workaround para o bug de persistência no PJE-Calc Cidadão com H2.
 *
 * Sem este componente, cálculos criados via "Novo" nunca persistem no H2 porque o
 * Seam EPC usa FlushMode.MANUAL e o @End que dispararia flush só acontece em paths
 * específicos.
 *
 * Métodos sem argumentos para compatibilidade com event binding via XML.
 */
@Name("autoFlushHelper")
@Scope(ScopeType.APPLICATION)
@Startup
public class AutoFlushHelper {

    private static final Log log = Logging.getLog(AutoFlushHelper.class);
    private static int flushCount = 0;
    private static int eventCount = 0;

    @Observer({
        "org.jboss.seam.beginConversation",
        "org.jboss.seam.beginNestedConversation",
        "org.jboss.seam.endConversation",
        "org.jboss.seam.preRenderView",
        "org.jboss.seam.afterPhase"
    })
    public void forceFlush() {
        eventCount++;
        try {
            EntityManager em = (EntityManager) Component.getInstance("entityManager", false);
            if (em == null || !em.isOpen()) return;
            FlushModeType cur = em.getFlushMode();
            if (cur != FlushModeType.AUTO) {
                em.setFlushMode(FlushModeType.AUTO);
            }
            em.flush();
            flushCount++;
            if (flushCount <= 30 || flushCount % 25 == 0) {
                log.info("[AutoFlushHelper] flush #" + flushCount + " (evt#" + eventCount + ") cur_mode=" + cur);
            }
        } catch (Throwable t) {
            if (eventCount <= 10) {
                log.warn("[AutoFlushHelper] flush falhou: " + t.getClass().getSimpleName() + ": " + t.getMessage());
            }
        }
    }

    public static int getFlushCount() { return flushCount; }
    public static int getEventCount() { return eventCount; }
}
