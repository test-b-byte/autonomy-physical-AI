package c2.mission;

import c2.input.Command;
import c2.model.AooState;
import c2.model.AooStatus;

import java.time.Duration;
import java.time.Instant;

/** End state: banner on the board for a short hold, then the whole loop resets and runs again. */
public class CompletePhase implements MissionPhase {
    private static final Duration HOLD = Duration.ofMinutes(6);
    private final String mode;
    private Instant startedAt;

    public CompletePhase(String mode) { this.mode = mode; }

    @Override public String name() { return "COMPLETE"; }

    @Override
    public void enter(MissionController controller) {
        startedAt = controller.picture().now();
        controller.missionComplete(mode);
    }

    @Override
    public MissionPhase onTick(MissionController controller, Instant now, Duration elapsed) {
        long secondsLeft = Math.max(0, HOLD.minus(Duration.between(startedAt, now)).toMinutes());
        controller.picture().setAoo(new AooStatus(AooState.COMPLETE, mode, null, null, 1, "with casualty", null, -1,
                controller.armedMode(), "MISSION COMPLETE: " + mode + "   ·   next run in " + secondsLeft));
        if (Duration.between(startedAt, now).compareTo(HOLD) >= 0) {
            controller.resetRun();
            return new InitPhase();
        }
        return this;
    }

    @Override
    public MissionPhase onCommand(MissionController controller, Command command) { return this; }
}
