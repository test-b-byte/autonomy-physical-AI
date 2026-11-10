package c2.mission;

import c2.export.MapStateWriter;
import c2.export.MissionOrderWriter;
import c2.export.PathExporter;
import c2.ingest.InboundQueue;
import c2.ingest.ReportIngest;
import c2.ingest.SimulatedDroneFeed;
import c2.input.Command;
import c2.input.CommandSink;
import c2.input.CommandType;
import c2.model.Alert;
import c2.model.AlertLevel;
import c2.model.AooStatus;
import c2.model.BeliefGrid;
import c2.model.DroneReport;
import c2.model.GridPos;
import c2.model.Knowledge;
import c2.model.MapObject;
import c2.model.ObjectKind;
import c2.model.OperationsPicture;
import c2.model.PatrolRoute;
import c2.model.SortieView;
import c2.model.Source;
import c2.model.TravelPath;
import c2.model.Waypoint;
import c2.observe.PictureEventType;
import c2.search.LocalSearchEngine;
import c2.search.PathFinder;
import c2.search.SearchEngine;
import c2.time.TickListener;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * State pattern context and clock listener. Each tick: apply what arrived, let time act on the picture
 * (belief spreads, patrols move, sorties fly, confirmations age), then let the current phase run.
 *
 * Mission loop per run: INIT -> EXECUTE -> (REGROUP -> INIT)* -> contact -> LOITER -> ESCORT / URGENT / SEVERE
 * -> COMPLETE -> reset -> next run.
 */
public class MissionController implements TickListener, CommandSink {
    public static final String ESCORT = "ESCORT", URGENT = "URGENT", SEVERE = "SEVERE";

    private static final Duration SOLID_LIFETIME = Duration.ofMinutes(15);
    private static final DateTimeFormatter CLOCK = DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneOffset.UTC);
    private static final double CONTACT_RANGE_SQUARES = 3;
    private static final int FORCE_CONTACT_AFTER_WAVES = 3;        // control stop: guarantee a contact by wave 4
    private static final double WALK_SQUARES_PER_SECOND = 0.8 / 50;   // casualty walking, 0.8 m/s
    private static final double TEAM_SQUARES_PER_SECOND = 1.2 / 50;   // rescue team on foot, 1.2 m/s
    private static final int BEACON_OFFSET_SQUARES = 4;               // 200 m toward staging

    private final OperationsPicture picture;
    private final SearchEngine engine;
    private final InboundQueue queue;
    private final SimulatedDroneFeed simulatedDrone;     // null when using real reports only
    private final MissionOrderWriter orderWriter;
    private final PathExporter pathExporter;
    private final MapStateWriter mapStateWriter;
    private final String subjectId, tocId, stagingId, teamId;
    private final List<String> droneIds;
    private final String intent;
    private final GridPos lastKnown;
    private final Map<String, MapObject.Snapshot> startingState = new HashMap<>();

    private MissionPhase phase;
    private final List<Sortie> activeSorties = new ArrayList<>();
    private int waveCount = 0, wavesThisRun = 0;
    private String armedMode;
    private boolean contactActive;

    public MissionController(OperationsPicture picture, SearchEngine engine, InboundQueue queue,
                             SimulatedDroneFeed simulatedDrone, MissionOrderWriter orderWriter,
                             PathExporter pathExporter, MapStateWriter mapStateWriter,
                             String subjectId, List<String> droneIds, String tocId, String stagingId, String teamId,
                             GridPos lastKnown, String intent) {
        this.picture = picture;
        this.engine = engine;
        this.queue = queue;
        this.simulatedDrone = simulatedDrone;
        this.orderWriter = orderWriter;
        this.pathExporter = pathExporter;
        this.mapStateWriter = mapStateWriter;
        this.subjectId = subjectId;
        this.droneIds = droneIds;
        this.tocId = tocId;
        this.stagingId = stagingId;
        this.teamId = teamId;
        this.lastKnown = lastKnown;
        this.intent = intent;
        for (MapObject object : picture.objects()) startingState.put(object.id(), object.snapshot());
    }

    public void begin() { picture.update(() -> transitionTo(new InitPhase())); }

    @Override
    public void onTick(Instant now, Duration elapsed) {
        picture.update(() -> {
            picture.setNow(now);
            for (Object item : queue.drain()) {
                if (item instanceof DroneReport report) ingest(report);
            }
            engine.advance(picture, elapsed);
            if (simulatedDrone != null && !contactActive) simulatedDrone.wander(elapsed.toMillis() / 60000.0);
            movePatrols(now);
            advanceSorties(now);
            ageConfirmations(now, elapsed);
            MissionPhase next = phase.onTick(this, now, elapsed);
            if (next != phase) transitionTo(next);
            publishSorties();
            picture.changed(PictureEventType.TICK, null);
        });
    }

    @Override
    public void submit(Command command) {
        picture.update(() -> {
            String mode = switch (command.type()) {
                case ARM_ESCORT -> ESCORT;
                case ARM_URGENT -> URGENT;
                case ARM_SEVERE -> SEVERE;
                default -> null;
            };
            if (mode != null) {
                armedMode = mode;
                picture.raise(new Alert(picture.now(), AlertLevel.INFO,
                        contactActive ? "Operator selected " + mode : "Armed: next contact -> " + mode));
                return;
            }
            MissionPhase next = phase.onCommand(this, command);
            if (next != phase) transitionTo(next);
        });
    }

    // ---- searching ---------------------------------------------------------

    /** One wave: every drone launches from staging on its own route; later drones avoid earlier drones' targets. */
    void launchWave() {
        waveCount++;
        wavesThisRun++;
        activeSorties.clear();
        GridPos launchPoint = picture.object(stagingId).pos();
        List<GridPos> takenTargets = new ArrayList<>();
        for (int index = 0; index < droneIds.size(); index++) {
            String sortieId = "W" + waveCount + "-" + (char) ('A' + index);
            Instant depart = picture.now().plusSeconds(index * 60L);
            boolean forceContact = index == 0 && wavesThisRun > FORCE_CONTACT_AFTER_WAVES && simulatedDrone != null;
            List<GridPos> mustVisit = forceContact ? List.of(simulatedDrone.trueSubject()) : List.of();
            TravelPath route = engine.planRoute(picture, sortieId, launchPoint, depart, takenTargets, mustVisit);
            for (Waypoint waypoint : route.waypoints()) takenTargets.add(waypoint.pos());
            activeSorties.add(new Sortie(sortieId, droneIds.get(index), route));
            picture.putPlannedPath(route);
            orderWriter.write(sortieId, route, route.end().plus(Sortie.OVERDUE_GRACE), intent);
            if (index == 0) pathExporter.export(route);
        }
        mapStateWriter.write(picture, subjectId);
        picture.raise(new Alert(picture.now(), AlertLevel.INFO, "Run " + picture.runNumber() + " wave " + wavesThisRun
                + ": " + droneIds.size() + " UAVs launched"));
    }

    /** Every tick: fly each searching drone along its route; upload when back over the phase line; land at staging. */
    private void advanceSorties(Instant now) {
        for (Sortie sortie : activeSorties) {
            if (sortie.isLanded() || sortie.isOnObjective()) continue;
            MapObject drone = picture.object(sortie.droneId());
            GridPos position = sortie.route().positionAt(now);
            drone.moveTo(position);
            if (now.isAfter(sortie.route().start())) drone.revertToHolo();
            if (!isFriendlySide(position)) sortie.markDenied();
            else if (sortie.hasBeenDenied() && !sortie.isUploaded()) upload(sortie, now);
            if (!now.isBefore(sortie.expectedReturn())) {
                if (!sortie.isUploaded()) upload(sortie, now);
                landDrone(sortie, now);
            }
            if (sortie.becameOverdue(now)) {
                picture.raise(new Alert(now, AlertLevel.OVERDUE, sortie.id() + " OVERDUE, no report"));
            }
            if (sortie.becameLost(now)) {
                picture.removePlannedPath(sortie.id());
                picture.raise(new Alert(now, AlertLevel.OVERDUE, sortie.id() + " presumed LOST"));
            }
        }
    }

    /** Back on the friendly side of the phase line: the report goes up wirelessly. */
    private void upload(Sortie sortie, Instant now) {
        sortie.markUploaded();
        if (simulatedDrone != null) simulatedDrone.sortieLanded(sortie.id(), sortie.route(), now, hostilePositions());
    }

    void landDrone(Sortie sortie, Instant now) {
        if (sortie.isLanded()) return;
        sortie.markLanded();
        picture.object(sortie.droneId()).confirm(picture.object(stagingId).pos(), now, Source.ANCHOR);
        picture.changed(PictureEventType.OBJECT_CONFIRMED, sortie.droneId());
    }

    /** A searching drone in the denied area within sensor range of the casualty. Only one contact at a time. */
    Sortie findContact() {
        if (simulatedDrone == null || contactActive) return null;
        for (Sortie sortie : activeSorties) {
            if (sortie.isLanded() || sortie.isOnObjective() || !sortie.hasBeenDenied()) continue;
            if (picture.object(sortie.droneId()).pos().distanceTo(simulatedDrone.trueSubject()) <= CONTACT_RANGE_SQUARES) {
                return sortie;
            }
        }
        return null;
    }

    // ---- actions on the objective -----------------------------------------------

    void beginContact(Sortie sortie) {
        contactActive = true;
        sortie.markOnObjective();
        picture.removePlannedPath(sortie.id());
        MapObject subject = picture.object(subjectId);
        subject.confirm(simulatedDrone.trueSubject(), picture.now(), Source.REPORT);
        picture.countContact();
        picture.belief().applySighting(simulatedDrone.trueSubject(), 2.0);     // the heat map collapses onto the find
        picture.changed(PictureEventType.BELIEF_UPDATED, "contact");
        picture.changed(PictureEventType.OBJECT_CONFIRMED, subjectId);
        picture.setAoo(new AooStatus(c2.model.AooState.LOITER, null, null, droneLabel(sortie), 0, null, null, -1, armedMode, null));
        picture.raise(new Alert(picture.now(), AlertLevel.CONTACT, "CONTACT " + droneLabel(sortie) + ": loitering, select E / U / S"));
    }

    void loiterDrone(Sortie sortie, Instant now) {
        GridPos casualty = casualtyPos();
        double angle = now.getEpochSecond() / 60.0 * 1.5;
        moveDrone(sortie, new GridPos((int) Math.round(casualty.row() + 2 * Math.sin(angle)),
                (int) Math.round(casualty.col() + 2 * Math.cos(angle))));
    }

    MissionPhase modePhase(Sortie sortie, String mode, String chosenBy) { return new ObjectivePhase(sortie, mode, chosenBy); }

    void announceMode(String mode, String chosenBy) {
        String meaning = switch (mode) {
            case ESCORT -> "casualty can walk: escorting to rescue team";
            case URGENT -> "casualty can't move: UAV returning to report";
            default -> "life-threatening: offset IR beacon active";
        };
        picture.raise(new Alert(picture.now(), mode.equals(SEVERE) || mode.equals(URGENT) ? AlertLevel.URGENT : AlertLevel.CONTACT,
                mode + " (" + chosenBy + "): " + meaning));
    }

    GridPos casualtyPos() { return picture.object(subjectId).pos(); }

    void moveCasualty(GridPos pos) { picture.object(subjectId).confirm(pos, picture.now(), Source.REPORT); }

    void moveDrone(Sortie sortie, GridPos pos) { picture.object(sortie.droneId()).confirm(pos, picture.now(), Source.REPORT); }

    void moveTeam(GridPos pos) { picture.object(teamId).confirm(pos, picture.now(), Source.REPORT); }

    TravelPath walkFromCasualtyToStaging(Instant start) {
        return walkingPath("escort", casualtyPos(), picture.object(stagingId).pos(), start, WALK_SQUARES_PER_SECOND);
    }

    TravelPath teamRouteTo(GridPos target, Instant start) {
        return walkingPath("team", picture.object(teamId).pos(), target, start, TEAM_SQUARES_PER_SECOND);
    }

    TravelPath teamRouteVia(GridPos first, GridPos then, Instant start) {
        List<GridPos> squares = new ArrayList<>(walkingSquares(picture.object(teamId).pos(), first));
        List<GridPos> second = walkingSquares(first, then);
        squares.addAll(second.subList(1, second.size()));
        return LocalSearchEngine.timed("team", squares, start, TEAM_SQUARES_PER_SECOND);
    }

    TravelPath droneRouteHome(Sortie sortie, Instant start) {
        return droneRouteTo(sortie, picture.object(stagingId).pos(), start);
    }

    TravelPath droneRouteTo(Sortie sortie, GridPos target, Instant start) {
        List<GridPos> squares = PathFinder.route(picture.frame(), picture.object(sortie.droneId()).pos(), target,
                picture.blocked()::contains, square -> 1.0);
        return LocalSearchEngine.timed(sortie.id() + "-aoo", squares, start, LocalSearchEngine.DRONE_CELLS_PER_SECOND);
    }

    /** Walking route around obstacles and water, preferring easy ground. */
    private List<GridPos> walkingSquares(GridPos from, GridPos to) {
        return PathFinder.route(picture.frame(), from, to,
                square -> picture.blocked().contains(square) || picture.terrain().at(square).cover().blocksWalking(),
                square -> picture.terrain().at(square).cover().walkCost);
    }

    private TravelPath walkingPath(String id, GridPos from, GridPos to, Instant start, double speed) {
        return LocalSearchEngine.timed(id, walkingSquares(from, to), start, speed);
    }

    /** 200 m from the casualty, toward staging (where the rescue team comes from). */
    GridPos beaconPoint() {
        GridPos casualty = casualtyPos(), staging = picture.object(stagingId).pos();
        double distance = Math.max(1, casualty.distanceTo(staging));
        return picture.frame().clamp(new GridPos(
                (int) Math.round(casualty.row() + (staging.row() - casualty.row()) / distance * BEACON_OFFSET_SQUARES),
                (int) Math.round(casualty.col() + (staging.col() - casualty.col()) / distance * BEACON_OFFSET_SQUARES)));
    }

    /** "SOS <direction> 200": where the casualty is, seen from the beacon. */
    String beaconMessage(GridPos beacon) {
        GridPos casualty = casualtyPos();
        double east = casualty.col() - beacon.col(), north = beacon.row() - casualty.row();
        double bearing = (Math.toDegrees(Math.atan2(east, north)) + 360) % 360;
        String[] words = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"};
        return "SOS " + words[(int) ((bearing + 22.5) % 360 / 45)] + " " + (BEACON_OFFSET_SQUARES * 50);
    }

    void beaconSeen() {
        picture.raise(new Alert(picture.now(), AlertLevel.CONTACT, "Beacon signal received: rescue team dispatched"));
    }

    void urgentUploaded(Sortie sortie) {
        picture.raise(new Alert(picture.now(), AlertLevel.URGENT, droneLabel(sortie) + " uploaded casualty report: team dispatched"));
    }

    boolean teamReachedCasualty() { return picture.object(teamId).pos().distanceTo(casualtyPos()) <= 1.5; }

    /** Escort: casualty and team walk toward each other, so the meeting time uses both speeds. */
    String meetingEtaText() {
        double gapSquares = picture.object(teamId).pos().distanceTo(casualtyPos());
        long minutes = Math.round(gapSquares / (WALK_SQUARES_PER_SECOND + TEAM_SQUARES_PER_SECOND) / 60);
        return minutes <= 0 ? "meeting now" : "meet in ~" + minutes + " min";
    }

    String etaText(TravelPath route, Instant now) {
        long minutes = Math.max(0, Duration.between(now, route.end()).toMinutes());
        return minutes == 0 ? "arriving" : "~" + minutes + " min";
    }

    void missionComplete(String mode) {
        picture.raise(new Alert(picture.now(), AlertLevel.CONTACT, "MISSION COMPLETE: " + mode + ", team with casualty"));
    }

    /** Put everything back to the scenario's start and begin the next run of the loop. */
    void resetRun() {
        for (MapObject object : picture.objects()) {
            MapObject.Snapshot saved = startingState.get(object.id());
            if (saved != null) object.restore(saved);
        }
        picture.belief().seedGaussian(lastKnown, 14, picture.terrain());
        picture.beginNextRun();
        activeSorties.clear();
        wavesThisRun = 0;
        armedMode = null;
        contactActive = false;
        if (simulatedDrone != null) simulatedDrone.reset();
        picture.setAoo(AooStatus.searching(null));
        picture.raise(new Alert(picture.now(), AlertLevel.INFO, "Run " + picture.runNumber() + " starting"));
    }

    boolean isFriendlySide(GridPos pos) { return picture.phaseLine() == null || picture.phaseLine().isFriendly(pos); }

    String armedMode() { return armedMode; }

    String takeArmedMode() {
        String mode = armedMode;
        armedMode = null;
        return mode;
    }

    String droneLabel(Sortie sortie) { return picture.object(sortie.droneId()).label(); }

    List<Sortie> activeSorties() { return activeSorties; }
    OperationsPicture picture() { return picture; }

    // ---- shared upkeep ----------------------------------------------------------

    void publishSorties() {
        List<SortieView> views = new ArrayList<>();
        for (Sortie sortie : activeSorties) {
            String status = sortie.isOnObjective() ? "ON OBJ" : sortie.isLanded() ? "LANDED"
                    : sortie.isReportReceived() ? "REPORTED" : sortie.isLost() ? "LOST" : "OUT";
            views.add(new SortieView(sortie.id(), picture.object(sortie.droneId()).label(),
                    sortie.route().start(), sortie.expectedReturn(), status));
        }
        picture.setSorties(views);
        if (!contactActive && !(phase instanceof CompletePhase)) picture.setAoo(AooStatus.searching(armedMode));
    }

    private void ingest(DroneReport report) {
        ReportIngest.apply(picture, engine, report, subjectId);
        for (Sortie sortie : activeSorties) {
            if (sortie.id().equals(report.sortieId())) {
                sortie.markReportReceived();
                if (!sortie.isOnObjective()) {
                    picture.addFlownTrack(sortie.route().asFlown());
                    picture.removePlannedPath(sortie.id());
                }
            }
        }
        mapStateWriter.write(picture, subjectId);
    }

    private List<GridPos> hostilePositions() {
        List<GridPos> positions = new ArrayList<>();
        for (MapObject object : picture.objects()) if (object.kind() == ObjectKind.HOSTILE) positions.add(object.pos());
        return positions;
    }

    private void movePatrols(Instant now) {
        for (PatrolRoute patrol : picture.patrols()) {
            MapObject hostile = picture.object(patrol.objectId());
            if (hostile != null && hostile.knowledge() == Knowledge.HOLO) hostile.moveTo(patrol.positionAt(picture.start(), now));
        }
    }

    /** SOLID moving objects fade to HOLO after SOLID_LIFETIME; HOLO subject follows the belief peak while searching. */
    private void ageConfirmations(Instant now, Duration elapsed) {
        double minutes = elapsed.toMillis() / 60000.0;
        for (MapObject object : picture.objects()) {
            if (!object.kind().moves || object.kind() == ObjectKind.DRONE || object.kind() == ObjectKind.TEAM) continue;
            if (object.kind() == ObjectKind.SUBJECT && contactActive) continue;
            if (object.knowledge() == Knowledge.SOLID) {
                Duration age = object.ageAt(now);
                if (age != null && age.compareTo(SOLID_LIFETIME) > 0) {
                    object.revertToHolo();
                    picture.changed(PictureEventType.OBJECT_AGED, object.id());
                }
            } else {
                object.growUncertainty(minutes * 0.15, object.kind() == ObjectKind.SUBJECT ? 30 : 10);
            }
        }
        MapObject subject = picture.object(subjectId);
        if (subject != null && !contactActive && subject.knowledge() == Knowledge.HOLO) subject.moveTo(beliefPeak());
    }

    private GridPos beliefPeak() {
        BeliefGrid belief = picture.belief();
        int bestRow = 0, bestCol = 0;
        double best = -1;
        for (int row = 0; row < belief.rows(); row++) {
            for (int col = 0; col < belief.cols(); col++) {
                if (belief.at(row, col) > best) { best = belief.at(row, col); bestRow = row; bestCol = col; }
            }
        }
        return new GridPos(bestRow, bestCol);
    }

    private void transitionTo(MissionPhase next) {
        phase = next;
        picture.setPhaseName(next.name());
        next.enter(this);
    }
}
