package c2.model;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

/** A predicted patrol loop for a hostile: the object is moved around this loop as mission time passes. */
public record PatrolRoute(String objectId, List<GridPos> loop, Duration lapTime) {
    public GridPos positionAt(Instant start, Instant now) {
        double laps = Duration.between(start, now).toMillis() / (double) lapTime.toMillis();
        double along = (laps - Math.floor(laps)) * loop.size();
        int index = (int) along;
        GridPos from = loop.get(index % loop.size()), to = loop.get((index + 1) % loop.size());
        double fraction = along - index;
        return new GridPos((int) Math.round(from.row() + (to.row() - from.row()) * fraction),
                (int) Math.round(from.col() + (to.col() - from.col()) * fraction));
    }
}
