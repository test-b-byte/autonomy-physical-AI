package c2.time;

import c2.input.Command;
import c2.input.CommandSink;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Mission clock. Ticks on its own thread at a fixed real-time rate and advances
 * mission time by (real interval x speed). Speed 1 = live, higher = simulation.
 * Observer subject: every TickListener gets every tick.
 */
public class SimClock implements CommandSink {
    private static final double[] SPEEDS = {1, 10, 30, 60, 120, 300};

    private final List<TickListener> listeners = new CopyOnWriteArrayList<>();
    private final long tickMillis;
    private ScheduledExecutorService ticker;
    private volatile Instant missionTime;
    private volatile int speedIndex = 3;
    private volatile boolean paused = false;

    public SimClock(Instant start, long tickMillis) {
        this.missionTime = start;
        this.tickMillis = tickMillis;
    }

    public void addListener(TickListener listener) { listeners.add(listener); }

    public void start() {
        ticker = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "sim-clock");
            thread.setDaemon(true);
            return thread;
        });
        ticker.scheduleAtFixedRate(this::tick, tickMillis, tickMillis, TimeUnit.MILLISECONDS);
    }

    public void stop() { if (ticker != null) ticker.shutdownNow(); }

    /** One step. Public so headless runs can step the clock by hand. */
    public void tick() {
        if (paused) return;
        Duration elapsed = Duration.ofMillis((long) (tickMillis * SPEEDS[speedIndex]));
        missionTime = missionTime.plus(elapsed);
        for (TickListener listener : listeners) {
            try {
                listener.onTick(missionTime, elapsed);
            } catch (RuntimeException problem) {
                problem.printStackTrace();     // one bad listener must not stop the clock
            }
        }
    }

    public Instant now() { return missionTime; }
    public double speed() { return SPEEDS[speedIndex]; }
    public boolean isPaused() { return paused; }

    @Override
    public void submit(Command command) {
        switch (command.type()) {
            case PAUSE_TOGGLE -> paused = !paused;
            case SPEED_UP -> speedIndex = Math.min(SPEEDS.length - 1, speedIndex + 1);
            case SLOW_DOWN -> speedIndex = Math.max(0, speedIndex - 1);
            default -> { }
        }
    }
}
