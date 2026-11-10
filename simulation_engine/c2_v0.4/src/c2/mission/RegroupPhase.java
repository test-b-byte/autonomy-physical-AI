package c2.mission;

import c2.input.Command;
import c2.input.CommandType;

import java.time.Duration;
import java.time.Instant;

/** Report is in. Short turnaround (battery swap, review), then replan. */
public class RegroupPhase implements MissionPhase {
    private static final Duration TURNAROUND = Duration.ofMinutes(3);
    private Instant enteredAt;

    @Override public String name() { return "REGROUP"; }

    @Override
    public void enter(MissionController controller) { enteredAt = controller.picture().now(); }

    @Override
    public MissionPhase onTick(MissionController controller, Instant now, Duration elapsed) {
        return now.isAfter(enteredAt.plus(TURNAROUND)) ? new InitPhase() : this;
    }

    @Override
    public MissionPhase onCommand(MissionController controller, Command command) {
        if (command.type() == CommandType.REPLAN) return new InitPhase();
        if (command.type() == CommandType.HALT) return new HaltedPhase(this);
        return this;
    }
}
