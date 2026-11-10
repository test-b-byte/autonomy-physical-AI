package c2.mission;

import c2.input.Command;
import c2.model.AooState;
import c2.model.AooStatus;

import java.time.Duration;
import java.time.Instant;
import java.util.Random;

/**
 * Contact. The finding drone circles the casualty while the mode is decided:
 * by the operator (E / U / S, pressed now or armed earlier) or at random when the loiter window runs out.
 */
public class LoiterPhase implements MissionPhase {
    public static final Duration LOITER_WINDOW = Duration.ofMinutes(8);
    private static final Random RANDOM = new Random();

    private final Sortie sortie;
    private Instant startedAt;

    public LoiterPhase(Sortie sortie) { this.sortie = sortie; }

    @Override public String name() { return "ON OBJECTIVE"; }

    @Override
    public void enter(MissionController controller) {
        startedAt = controller.picture().now();
        controller.beginContact(sortie);
    }

    @Override
    public MissionPhase onTick(MissionController controller, Instant now, Duration elapsed) {
        controller.loiterDrone(sortie, now);
        double fraction = Math.min(1, Duration.between(startedAt, now).toMillis() / (double) LOITER_WINDOW.toMillis());
        controller.picture().setAoo(new AooStatus(AooState.LOITER, null, null,
                controller.droneLabel(sortie), fraction, null, null, -1, controller.armedMode(), null));
        String mode = controller.takeArmedMode();
        String chosenBy = "operator";
        if (mode == null && fraction >= 1) {
            mode = new String[]{MissionController.ESCORT, MissionController.URGENT, MissionController.SEVERE}[RANDOM.nextInt(3)];
            chosenBy = "random (no input)";
        }
        return mode == null ? this : controller.modePhase(sortie, mode, chosenBy);
    }

    @Override
    public MissionPhase onCommand(MissionController controller, Command command) { return this; }
}
