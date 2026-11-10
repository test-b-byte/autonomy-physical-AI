package c2.mission;

import c2.input.Command;
import c2.input.CommandType;

import java.time.Duration;
import java.time.Instant;

/** Sorties are out in the denied area. A contact hands over to the actions-on-objective loop. */
public class ExecutePhase implements MissionPhase {
    @Override public String name() { return "EXECUTE"; }

    @Override public void enter(MissionController controller) { }

    @Override
    public MissionPhase onTick(MissionController controller, Instant now, Duration elapsed) {
        if (controller.activeSorties().isEmpty()) return new InitPhase();
        Sortie contact = controller.findContact();
        if (contact != null) return new LoiterPhase(contact);
        boolean allFinished = controller.activeSorties().stream().allMatch(Sortie::isFinished);
        return allFinished ? new RegroupPhase() : this;
    }

    @Override
    public MissionPhase onCommand(MissionController controller, Command command) {
        return command.type() == CommandType.HALT ? new HaltedPhase(this) : this;
    }
}
