package br.jus.trt8.pjecalc.web.util;

import javax.faces.event.PhaseEvent;
import javax.faces.event.PhaseId;
import javax.faces.event.PhaseListener;
import javax.persistence.EntityManager;
import javax.persistence.FlushModeType;

import org.jboss.seam.Component;

/**
 * PhaseListener JSF que força flush do EntityManager Seam após cada fase
 * INVOKE_APPLICATION ou RESTORE_VIEW. Isso garante que mudanças feitas
 * pelos beans cheguem ao banco antes do redirect/render seguinte.
 *
 * Independente de Seam @Observer (que não está disparando neste setup).
 */
public class FlushPhaseListener implements PhaseListener {

    private static final long serialVersionUID = 1L;
    private static int flushCount = 0;
    private static int phaseCount = 0;

    @Override
    public PhaseId getPhaseId() {
        return PhaseId.ANY_PHASE;
    }

    @Override
    public void beforePhase(PhaseEvent event) {
        // não faz nada antes
    }

    @Override
    public void afterPhase(PhaseEvent event) {
        phaseCount++;
        // Flushar após INVOKE_APPLICATION (onde os listeners de save rodam)
        // e RENDER_RESPONSE (antes do redirect)
        PhaseId id = event.getPhaseId();
        if (id != PhaseId.INVOKE_APPLICATION && id != PhaseId.RENDER_RESPONSE) {
            return;
        }
        try {
            EntityManager em = (EntityManager) Component.getInstance("entityManager", false);
            if (em == null || !em.isOpen()) return;
            if (em.getFlushMode() != FlushModeType.AUTO) {
                em.setFlushMode(FlushModeType.AUTO);
            }
            em.flush();
            flushCount++;
            if (flushCount <= 30 || flushCount % 25 == 0) {
                System.out.println("[FlushPhaseListener] flush #" + flushCount +
                    " after " + id + " (phase #" + phaseCount + ")");
            }
        } catch (Throwable t) {
            if (phaseCount <= 5) {
                System.out.println("[FlushPhaseListener] falhou após " + id +
                    ": " + t.getClass().getSimpleName() + ": " + t.getMessage());
            }
        }
    }

    public static int getFlushCount() { return flushCount; }
}
