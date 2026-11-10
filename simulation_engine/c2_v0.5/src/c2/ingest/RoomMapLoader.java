package c2.ingest;

import c2.model.GridPos;
import c2.model.RoomCup;
import c2.model.RoomFeatures;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Adapter: the ground robot's map file (map.txt, JSON) -> RoomFeatures on the board. Read once at startup.
 *
 * Robot frame: odometry, x forward, y left, meters, origin at its start.
 * Board placement:
 *   - the robot's start becomes the STAGING square
 *   - rotated so the robot's direction of travel points from staging toward the search area
 *     (board east = robot +y, board north = robot -x)
 *   - scale 1:200: one 50 m board square = 25 cm of floor (the 7.5 x 5.5 m area = 30 x 22 squares)
 *   - only the test area (7.5 m x 5.5 m around the course) is used; the robot also saw walls beyond it
 * Obstacles: the robot's real obstacle clusters -> gentle hills, height from the measured height.
 * Skipped: clusters longer than 2 m (the room's walls / window line) and specks under 8 cells.
 */
public final class RoomMapLoader {
    public static final double FLOOR_METERS_PER_SQUARE = 0.25;          // 1:200
    private static final double AREA_X_MIN = -6.5, AREA_X_MAX = 1.0;      // 7.5 m
    private static final double AREA_Y_MIN = -0.8, AREA_Y_MAX = 4.7;      // 5.5 m
    private static final double METERS_OF_RELIEF_PER_METER = 120;          // 0.6 m box -> ~75 m hill
    private static final double SKIP_IF_LONGER_THAN_M = 2.0;               // room walls / window line: not terrain
    private static final int SKIP_IF_FEWER_CELLS = 8;                      // sensor specks

    private RoomMapLoader() { }

    /** Null if the file is missing or unreadable: the board then runs on generated terrain alone. */
    @SuppressWarnings("unchecked")
    public static RoomFeatures load(Path file, GridPos staging) {
        if (!Files.exists(file)) return null;
        try {
            Map<String, Object> root = (Map<String, Object>) MiniJson.parse(Files.readString(file));
            Map<GridPos, Double> mountains = new HashMap<>();
            Set<GridPos> shifts = new HashSet<>();
            for (Object boxJson : (List<Object>) root.get("boxes")) {
                Map<String, Object> box = (Map<String, Object>) boxJson;
                List<Object> size = (List<Object>) box.get("size");
                double longest = Math.max((Double) size.get(0), (Double) size.get(1));
                List<Object> cellList = (List<Object>) box.get("cells");
                if (longest > SKIP_IF_LONGER_THAN_M || cellList.size() < SKIP_IF_FEWER_CELLS) continue;
                double relief = (Double) box.get("height") * METERS_OF_RELIEF_PER_METER;
                for (Object cellJson : cellList) {
                    List<Object> cell = (List<Object>) cellJson;
                    double x = (Double) cell.get(0), y = (Double) cell.get(1);
                    if (!insideArea(x, y)) continue;
                    mountains.merge(toBoard(x, y, staging), relief, Math::max);
                }
            }
            List<RoomCup> cups = new ArrayList<>();
            for (Object cupJson : (List<Object>) root.get("cups")) {
                Map<String, Object> cup = (Map<String, Object>) cupJson;
                List<Object> pos = (List<Object>) cup.get("pos");
                cups.add(new RoomCup(((Double) cup.get("id")).intValue(), String.valueOf(cup.get("colour")),
                        toBoard((Double) pos.get(0), (Double) pos.get(1), staging)));
            }
            shifts.removeAll(mountains.keySet());
            return new RoomFeatures(mountains, shifts, cups, staging);
        } catch (IOException | RuntimeException problem) {
            System.err.println("Room map not loaded (" + file + "): " + problem.getMessage());
            return null;
        }
    }

    private static boolean insideArea(double x, double y) {
        return x >= AREA_X_MIN && x <= AREA_X_MAX && y >= AREA_Y_MIN && y <= AREA_Y_MAX;
    }

    /** Robot meters -> board square. east = +y, north = -x; north is "up", so it lowers the row number. */
    static GridPos toBoard(double x, double y, GridPos staging) {
        int eastSquares = (int) Math.round(y / FLOOR_METERS_PER_SQUARE);
        int northSquares = (int) Math.round(-x / FLOOR_METERS_PER_SQUARE);
        return new GridPos(staging.row() - northSquares, staging.col() + eastSquares);
    }
}
