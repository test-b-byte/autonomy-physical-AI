package c2.mission;

import c2.model.TravelPath;

import java.time.Duration;
import java.time.Instant;

/** One drone trip: which drone, its route, and where it is in its life (out, over the line, on objective...). */
public class Sortie {
    public static final Duration OVERDUE_GRACE = Duration.ofMinutes(5);
    public static final Duration LOST_AFTER = Duration.ofMinutes(15);

    private final String id;
    private final String droneId;
    private final TravelPath route;
    private boolean landed, uploaded, reportReceived, overdueRaised, lost, beenDenied, onObjective;

    public Sortie(String id, String droneId, TravelPath route) {
        this.id = id;
        this.droneId = droneId;
        this.route = route;
    }

    public String id() { return id; }
    public String droneId() { return droneId; }
    public TravelPath route() { return route; }
    public Instant expectedReturn() { return route.end(); }
    public boolean isLanded() { return landed; }
    public boolean isUploaded() { return uploaded; }
    public boolean isReportReceived() { return reportReceived; }
    public boolean isLost() { return lost; }
    public boolean isOnObjective() { return onObjective; }
    public boolean hasBeenDenied() { return beenDenied; }

    /** Done with this sortie: its report is in (or it's written off) and it's back (or handed over to the objective). */
    public boolean isFinished() { return (reportReceived || lost) && (landed || onObjective) || onObjective; }

    public void markLanded() { landed = true; }
    public void markUploaded() { uploaded = true; }
    public void markReportReceived() { reportReceived = true; }
    public void markDenied() { beenDenied = true; }
    public void markOnObjective() { onObjective = true; }

    public boolean becameOverdue(Instant now) {
        if (reportReceived || overdueRaised || onObjective) return false;
        if (now.isAfter(expectedReturn().plus(OVERDUE_GRACE))) { overdueRaised = true; return true; }
        return false;
    }

    public boolean becameLost(Instant now) {
        if (reportReceived || lost || onObjective) return false;
        if (now.isAfter(expectedReturn().plus(LOST_AFTER))) { lost = true; return true; }
        return false;
    }
}
