package c2.time;

import java.time.Duration;
import java.time.Instant;

/** Anything that runs on mission time. Observer listener for SimClock. */
public interface TickListener {
    void onTick(Instant missionTime, Duration elapsed);
}
