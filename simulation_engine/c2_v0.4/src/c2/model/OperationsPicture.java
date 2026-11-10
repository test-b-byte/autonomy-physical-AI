package c2.model;

import c2.observe.PictureEvent;
import c2.observe.PictureEventType;
import c2.observe.PictureObserver;

import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * The digital twin (AirCom's GameBoard role). Holds terrain, belief, objects, zones, patrols, paths, alerts.
 * Observer subject: changes are collected during an update and sent to observers after it.
 *
 * Threading: writers call update(...); readers (views) wrap reads in synchronized (picture).
 */
public class OperationsPicture {
    private static final int ALERTS_KEPT = 10;

    private final GeoFrame frame;
    private final TerrainGrid terrain;
    private final BeliefGrid belief;
    private final Map<String, MapObject> objects = new LinkedHashMap<>();
    private final List<Zone> zones = new ArrayList<>();
    private final List<PatrolRoute> patrols = new ArrayList<>();
    private final Map<String, TravelPath> plannedPaths = new LinkedHashMap<>();
    private final List<TravelPath> flownTracks = new ArrayList<>();
    private final Deque<Alert> alerts = new ArrayDeque<>();
    private final List<PictureObserver> observers = new CopyOnWriteArrayList<>();
    private final List<PictureEvent> pendingEvents = new ArrayList<>();
    private final Instant start;

    private List<SortieView> sorties = List.of();
    private final java.util.Set<GridPos> blocked = new java.util.HashSet<>();   // squares drones and walkers route around
    private PhaseLine phaseLine;
    private AooStatus aoo = AooStatus.searching(null);
    private GridPos beaconPos;
    private int runNumber = 1;
    private Instant now;
    private String phaseName = "-";
    private int contacts = 0;
    private int sortiesFlown = 0;

    public OperationsPicture(GeoFrame frame, TerrainGrid terrain, Instant start) {
        this.frame = frame;
        this.terrain = terrain;
        this.belief = new BeliefGrid(frame.rows(), frame.cols());
        this.start = start;
        this.now = start;
    }

    public void addObserver(PictureObserver observer) { observers.add(observer); }

    /** Run a block of changes under the lock, then notify observers of everything that changed. */
    public void update(Runnable changes) {
        List<PictureEvent> toSend;
        synchronized (this) {
            changes.run();
            toSend = new ArrayList<>(pendingEvents);
            pendingEvents.clear();
        }
        for (PictureEvent event : toSend) {
            for (PictureObserver observer : observers) observer.onPictureChanged(event);
        }
    }

    /** Record a change; sent when the current update finishes. */
    public void changed(PictureEventType type, String detail) { pendingEvents.add(new PictureEvent(type, detail)); }

    public void add(MapObject object) { objects.put(object.id(), object); }
    public MapObject object(String id) { return objects.get(id); }
    public Collection<MapObject> objects() { return objects.values(); }

    public void addZone(Zone zone) { zones.add(zone); }
    public List<Zone> zones() { return zones; }
    public boolean insideZone(GridPos pos, ZoneType type) {
        for (Zone zone : zones) if (zone.type() == type && zone.contains(pos)) return true;
        return false;
    }

    public void addPatrol(PatrolRoute patrol) { patrols.add(patrol); }
    public List<PatrolRoute> patrols() { return patrols; }

    public void putPlannedPath(TravelPath path) {
        plannedPaths.put(path.id(), path);
        changed(PictureEventType.PATH_PLANNED, path.id());
    }
    public void removePlannedPath(String pathId) {
        plannedPaths.remove(pathId);
        changed(PictureEventType.PATH_PLANNED, "cleared " + pathId);
    }
    public Collection<TravelPath> plannedPaths() { return plannedPaths.values(); }
    public void addFlownTrack(TravelPath track) { flownTracks.add(track); sortiesFlown++; }
    public List<TravelPath> flownTracks() { return flownTracks; }

    public void raise(Alert alert) {
        alerts.addFirst(alert);
        while (alerts.size() > ALERTS_KEPT) alerts.removeLast();
        changed(PictureEventType.ALERT_RAISED, alert.text());
    }

    public void countContact() { contacts++; }

    public java.util.Set<GridPos> blocked() { return blocked; }
    public void setPhaseLine(PhaseLine line) { phaseLine = line; }
    public PhaseLine phaseLine() { return phaseLine; }
    public void setAoo(AooStatus status) { aoo = status; }
    public AooStatus aoo() { return aoo; }
    public void setBeaconPos(GridPos pos) { beaconPos = pos; }
    public GridPos beaconPos() { return beaconPos; }
    public int runNumber() { return runNumber; }

    /** Start the next run of the loop: clear paths, tracks, sorties; keep terrain, zones and counters. */
    public void beginNextRun() {
        runNumber++;
        plannedPaths.clear();
        flownTracks.clear();
        sorties = List.of();
        beaconPos = null;
    }
    public void setSorties(List<SortieView> views) { sorties = List.copyOf(views); }
    public void setNow(Instant time) { now = time; }
    public void setPhaseName(String name) {
        phaseName = name;
        changed(PictureEventType.PHASE_CHANGED, name);
    }

    public GeoFrame frame() { return frame; }
    public TerrainGrid terrain() { return terrain; }
    public BeliefGrid belief() { return belief; }
    public Collection<Alert> alerts() { return alerts; }
    public List<SortieView> sorties() { return sorties; }
    public Instant start() { return start; }
    public Instant now() { return now; }
    public String phaseName() { return phaseName; }
    public int contacts() { return contacts; }
    public int sortiesFlown() { return sortiesFlown; }
}
