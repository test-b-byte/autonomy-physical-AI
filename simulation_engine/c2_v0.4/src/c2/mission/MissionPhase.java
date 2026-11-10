package c2.mission;

import c2.input.Command;

import java.time.Duration;
import java.time.Instant;

/**
 * State pattern: one phase of the mission loop (INFO -> INIT -> EXECUTE -> REGROUP).
 * Each method returns the phase to be in next (itself to stay).
 */
public interface MissionPhase {
    String name();
    void enter(MissionController controller);
    MissionPhase onTick(MissionController controller, Instant now, Duration elapsed);
    MissionPhase onCommand(MissionController controller, Command command);
}
