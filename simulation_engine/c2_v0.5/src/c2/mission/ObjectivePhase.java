package c2.mission;

import c2.input.Command;
import c2.model.AooState;
import c2.model.AooStatus;
import c2.model.GridPos;
import c2.model.TravelPath;

import java.time.Duration;
import java.time.Instant;

/**
 * Escort, urgent, or beacon, carried out on the board. One class, three behaviors, chosen by mode:
 *   ESCORT  casualty walks toward staging with the drone leading; the rescue team walks out to meet them
 *   URGENT  drone flies home fast; on crossing the phase line it uploads, and the team is dispatched to the casualty
 *   SEVERE  drone moves to an offset beacon point and signals; once seen, the team homes on the beacon, then the casualty
 * Finishes when the rescue team reaches the casualty.
 */
public class ObjectivePhase implements MissionPhase {
    private static final Duration BEACON_SEEN_AFTER = Duration.ofMinutes(3);

    private final Sortie sortie;
    private final String mode, chosenBy;
    private Instant startedAt;
    private TravelPath casualtyWalk, droneRoute, teamRoute;
    private boolean teamDispatched, uploaded;
    private String morse;

    public ObjectivePhase(Sortie sortie, String mode, String chosenBy) {
        this.sortie = sortie;
        this.mode = mode;
        this.chosenBy = chosenBy;
    }

    @Override public String name() { return "ON OBJECTIVE"; }

    @Override
    public void enter(MissionController controller) {
        startedAt = controller.picture().now();
        controller.announceMode(mode, chosenBy);
        switch (mode) {
            case MissionController.ESCORT -> {
                casualtyWalk = controller.walkFromCasualtyToStaging(startedAt);
                teamRoute = controller.teamRouteTo(controller.casualtyPos(), startedAt);
                teamDispatched = true;
            }
            case MissionController.URGENT -> droneRoute = controller.droneRouteHome(sortie, startedAt);
            default -> {
                GridPos beacon = controller.beaconPoint();
                droneRoute = controller.droneRouteTo(sortie, beacon, startedAt);
                morse = controller.beaconMessage(beacon);
                controller.picture().setBeaconPos(beacon);
            }
        }
    }

    @Override
    public MissionPhase onTick(MissionController controller, Instant now, Duration elapsed) {
        String teamEta = null;
        switch (mode) {
            case MissionController.ESCORT -> {
                GridPos walker = casualtyWalk.positionAt(now);
                controller.moveCasualty(walker);
                controller.moveDrone(sortie, casualtyWalk.positionAt(now.plusSeconds(120)));   // a little ahead, leading
                controller.moveTeam(teamRoute.positionAt(now));
                teamEta = controller.meetingEtaText();
            }
            case MissionController.URGENT -> {
                GridPos dronePos = droneRoute.positionAt(now);
                controller.moveDrone(sortie, dronePos);
                if (!uploaded && controller.isFriendlySide(dronePos)) {
                    uploaded = true;
                    controller.urgentUploaded(sortie);
                    teamRoute = controller.teamRouteTo(controller.casualtyPos(), now);
                    teamDispatched = true;
                }
                if (!now.isBefore(droneRoute.end())) controller.landDrone(sortie, now);
                if (teamDispatched) {
                    controller.moveTeam(teamRoute.positionAt(now));
                    teamEta = controller.etaText(teamRoute, now);
                }
            }
            default -> {
                controller.moveDrone(sortie, droneRoute.positionAt(now));
                if (!teamDispatched && Duration.between(startedAt, now).compareTo(BEACON_SEEN_AFTER) >= 0) {
                    teamDispatched = true;
                    controller.beaconSeen();
                    teamRoute = controller.teamRouteVia(controller.picture().beaconPos(), controller.casualtyPos(), now);
                }
                if (teamDispatched) {
                    controller.moveTeam(teamRoute.positionAt(now));
                    teamEta = controller.etaText(teamRoute, now);
                }
            }
        }
        AooState state = switch (mode) {
            case MissionController.ESCORT -> AooState.ESCORT;
            case MissionController.URGENT -> AooState.URGENT;
            default -> AooState.BEACON;
        };
        controller.picture().setAoo(new AooStatus(state, mode, chosenBy, controller.droneLabel(sortie), 1,
                teamDispatched ? teamEta : "not yet dispatched", morse, -1, controller.armedMode(), null));
        if (teamDispatched && controller.teamReachedCasualty()) return new CompletePhase(mode);
        return this;
    }

    @Override
    public MissionPhase onCommand(MissionController controller, Command command) { return this; }
}
