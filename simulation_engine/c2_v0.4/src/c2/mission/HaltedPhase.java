package c2.mission;

import c2.input.Command;
import c2.input.CommandType;

import java.time.Duration;
import java.time.Instant;

/** Commander halted planning. Time still passes (predictions keep spreading). RESUME returns to the paused phase. */
public class HaltedPhase implements MissionPhase {
    private final MissionPhase resumeTo;

    public HaltedPhase(MissionPhase resumeTo) { this.resumeTo = resumeTo; }

    @Override public String name() { return "HALTED"; }
    @Override public void enter(MissionController controller) { }

    @Override
    public MissionPhase onTick(MissionController controller, Instant now, Duration elapsed) { return this; }

    @Override
    public MissionPhase onCommand(MissionController controller, Command command) {
        return command.type() == CommandType.RESUME ? resumeTo : this;
    }
}
