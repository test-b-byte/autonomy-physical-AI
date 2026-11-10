package c2.app;

import c2.ingest.RoomMapLoader;
import c2.model.GeoFrame;
import c2.model.GridPos;
import c2.model.Knowledge;
import c2.model.MapObject;
import c2.model.ObjectKind;
import c2.model.OperationsPicture;
import c2.model.PatrolRoute;
import c2.model.PhaseLine;
import c2.model.RoomCup;
import c2.model.RoomFeatures;
import c2.model.Source;
import c2.model.TerrainGrid;
import c2.model.Zone;
import c2.model.ZoneType;

import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

/**
 * The starting picture: 5 x 5 mile AO, 50 m squares, TOC, staging point, 2 UAVs, rescue team, enemy presence,
 * and (when map.txt is present) the real test floor built into the terrain at 1:400 around the search area.
 */
public final class Scenario {
    public static final String SUBJECT = "subject-1", TOC = "toc", STAGING = "staging", TEAM = "team";
    public static final List<String> DRONES = List.of("uav-1", "uav-2");
    public static final GeoFrame FRAME = new GeoFrame(162, 162, 50);
    public static final GridPos LAST_KNOWN = new GridPos(70, 82);
    public static final GridPos TOC_POS = new GridPos(134, 40);
    public static final GridPos STAGING_POS = new GridPos(126, 78);         // the robot's start lands here
    public static final GridPos DEFAULT_SUBJECT = new GridPos(90, 99);      // used when there's no room map
    public static final Instant START = Instant.parse("2026-11-08T13:00:00Z");

    private Scenario() { }

    /** Where the hidden casualty really is: the robot's red cup when the room map loaded. */
    public static GridPos trueSubject(RoomFeatures room) {
        return room != null && room.casualty() != null ? room.casualty() : DEFAULT_SUBJECT;
    }

    public static RoomFeatures loadRoom(Path roomFile) { return RoomMapLoader.load(roomFile, STAGING_POS); }

    public static OperationsPicture build(RoomFeatures room) {
        TerrainGrid terrain = TerrainGrid.synthetic(FRAME);
        if (room != null) terrain = terrain.withRoomFeatures(room);
        OperationsPicture picture = new OperationsPicture(FRAME, terrain, START);

        picture.add(new MapObject(TOC, ObjectKind.TOC, "TOC", TOC_POS, Knowledge.SOLID, Source.ANCHOR, START, 0));
        picture.add(new MapObject(STAGING, ObjectKind.ANCHOR, "STAGING", STAGING_POS, Knowledge.SOLID, Source.ANCHOR, START, 0));
        picture.add(new MapObject(TEAM, ObjectKind.TEAM, "RESCUE TEAM", STAGING_POS, Knowledge.SOLID, Source.ANCHOR, START, 0));
        for (int index = 0; index < DRONES.size(); index++) {
            picture.add(new MapObject(DRONES.get(index), ObjectKind.DRONE, "UAV-" + (index + 1), STAGING_POS,
                    Knowledge.SOLID, Source.ANCHOR, START, 0));
        }
        picture.add(new MapObject(SUBJECT, ObjectKind.SUBJECT, "SUBJECT", LAST_KNOWN, Knowledge.HOLO, Source.PREDICTED, null, 12));

        // Phase line: friendly / controlled side (TOC, staging) vs denied side (search area)
        picture.setPhaseLine(new PhaseLine("PL ALPHA", new GridPos(112, 55), new GridPos(140, 105), TOC_POS));

        // Known hazards
        picture.add(new MapObject("hazard-cliff", ObjectKind.HAZARD, "CLIFF", new GridPos(62, 101), Knowledge.SOLID, Source.ANCHOR, START, 0));
        picture.add(new MapObject("hazard-ford", ObjectKind.HAZARD, "FAST WATER", new GridPos(104, 43), Knowledge.SOLID, Source.ANCHOR, START, 0));

        // The test floor's blue cups: alternating forest fire and enemy
        if (room != null) {
            for (RoomCup cup : room.cups()) {
                if (!cup.colour().equals("blue")) continue;
                // v0.4.2: at most one hazard between the casualty and the rescue team (cup 3, midway);
                // cup 6 sits beyond the casualty, off the team's line. No enemies in the middle.
                boolean fire = cup.id() == 3 || cup.id() == 6;
                if (fire) {
                    picture.add(new MapObject("room-fire-" + cup.id(), ObjectKind.HAZARD, "FOREST FIRE", cup.pos(),
                            Knowledge.SOLID, Source.REPORT, START, 0));
                }
            }
            // Drones and walkers route around the room's obstacles (with a one-square margin)
            for (GridPos square : room.mountains().keySet()) blockAround(picture, square);
            for (GridPos square : room.shifts()) blockAround(picture, square);
            picture.blocked().remove(STAGING_POS);
            picture.blocked().remove(trueSubject(room));
        }

        // Enemy area of operations (north-east) and the forces in and around it
        picture.addZone(new Zone("ENEMY AO", ZoneType.ENEMY_AO, List.of(
                new GridPos(10, 104), new GridPos(12, 152), new GridPos(58, 156),
                new GridPos(66, 128), new GridPos(48, 108)), Knowledge.SOLID));
        picture.add(new MapObject("hostile-cp", ObjectKind.HOSTILE, "ENEMY CP", new GridPos(24, 140), Knowledge.SOLID, Source.REPORT, START, 1));
        picture.add(new MapObject("hostile-op", ObjectKind.HOSTILE, "ENEMY OP", new GridPos(46, 118), Knowledge.HOLO, Source.PREDICTED, null, 5));
        picture.add(new MapObject("hostile-sqd", ObjectKind.HOSTILE, "ENEMY SQD", new GridPos(38, 132), Knowledge.HOLO, Source.PREDICTED, null, 7));
        picture.add(new MapObject("hostile-ptl", ObjectKind.HOSTILE, "PATROL", new GridPos(52, 122), Knowledge.HOLO, Source.PREDICTED, null, 5));
        picture.addPatrol(new PatrolRoute("hostile-ptl", List.of(
                new GridPos(52, 122), new GridPos(62, 112), new GridPos(66, 128), new GridPos(56, 138)),
                Duration.ofMinutes(50)));

        picture.belief().seedGaussian(LAST_KNOWN, 14, terrain);
        return picture;
    }

    private static void blockAround(OperationsPicture picture, GridPos square) {
        for (int dRow = -1; dRow <= 1; dRow++) {
            for (int dCol = -1; dCol <= 1; dCol++) {
                GridPos near = new GridPos(square.row() + dRow, square.col() + dCol);
                if (FRAME.inBounds(near)) picture.blocked().add(near);
            }
        }
    }
}
