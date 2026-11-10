package c2.model;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

/** Ordered waypoints. Planned = HOLO, flown = SOLID. This is the planner's list output. */
public record TravelPath(String id, List<Waypoint> waypoints, Knowledge knowledge) {

    public Instant start() { return waypoints.get(0).eta(); }
    public Instant end() { return waypoints.get(waypoints.size() - 1).eta(); }

    public TravelPath asFlown() { return new TravelPath(id, waypoints, Knowledge.SOLID); }

    /** Where the drone should be at a given time, straight-line between waypoints. */
    public GridPos positionAt(Instant time) {
        if (!time.isAfter(start())) return waypoints.get(0).pos();
        for (int index = 1; index < waypoints.size(); index++) {
            Waypoint from = waypoints.get(index - 1);
            Waypoint to = waypoints.get(index);
            if (!time.isAfter(to.eta())) {
                double legSeconds = Math.max(1, Duration.between(from.eta(), to.eta()).toSeconds());
                double fraction = Duration.between(from.eta(), time).toSeconds() / legSeconds;
                int row = (int) Math.round(from.pos().row() + (to.pos().row() - from.pos().row()) * fraction);
                int col = (int) Math.round(from.pos().col() + (to.pos().col() - from.pos().col()) * fraction);
                return new GridPos(row, col);
            }
        }
        return waypoints.get(waypoints.size() - 1).pos();
    }
}
