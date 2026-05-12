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
 * específicos (exportacao) que requerem o cálculo já estar no banco — chicken-and-egg.
 *
 * Este componente escuta múltiplos eventos Seam e força:
 *   1) FlushMode.AUTO no EPC sempre que possível
 *   2) Flush explícito em pontos-chave do ciclo de vida da requisição
 */
@Name("autoFlushHelper")
@Scope(ScopeType.APPLICATION)
@Startup
public class AutoFlushHelper {

    private static final Log log = Logging.getLog(AutoFlushHelper.class);
    private static int flushCount = 0;
    private static int eventCount = 0;

    /**
     * Cobre todos os eventos comuns do ciclo da requisição/conversa em Seam 2.x.
     * Em qualquer ponto, tenta promover FlushMode para AUTO e flushar.
     */
    @Observer({
        "org.jboss.seam.beginConversation",
        "org.jboss.seam.beginNestedConversation",
        "org.jboss.seam.endConversation",
        "org.jboss.seam.preRenderView",
        "org.jboss.seam.afterPhase",
        "org.jboss.seam.postSetVariable.entityManager"
    })
    public void forceFlush(String eventName) {
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
            if (flushCount <= 20 || flushCount % 10 == 0) {
                log.info("[AutoFlushHelper] flush #" + flushCount + " (event evt#" + eventCount + ") FlushMode was " + cur);
            }
        } catch (Throwable t) {
            if (eventCount <= 5) {
                log.warn("[AutoFlushHelper] flush falhou (evt#" + eventCount + "): " + t.getClass().getSimpleName() + ": " + t.getMessage());
            }
        }
    }

    public static int getFlushCount() { return flushCount; }
    public static int getEventCount() { return eventCount; }
}
