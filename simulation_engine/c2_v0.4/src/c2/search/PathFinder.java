package c2.search;

import c2.model.GeoFrame;
import c2.model.GridPos;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.function.Predicate;
import java.util.function.ToDoubleFunction;

/**
 * A* route around blocked squares on the board (8 directions). Used for drone legs around the room's
 * obstacles, and for walking routes (escort, rescue team). The result is thinned to its turning points.
 */
public final class PathFinder {
    private static final int[][] STEPS = {{-1, 0}, {1, 0}, {0, -1}, {0, 1}, {-1, -1}, {-1, 1}, {1, -1}, {1, 1}};

    private PathFinder() { }

    /**
     * @param blocked    squares that may not be entered
     * @param stepCost   cost of entering a square (1 for flying; terrain walk cost for walking)
     * @return squares from start to goal (both included), or a straight two-point line if no route exists
     */
    public static List<GridPos> route(GeoFrame frame, GridPos start, GridPos goal,
                                      Predicate<GridPos> blocked, ToDoubleFunction<GridPos> stepCost) {
        Map<GridPos, Double> costSoFar = new HashMap<>();
        Map<GridPos, GridPos> cameFrom = new HashMap<>();
        PriorityQueue<double[]> frontier = new PriorityQueue<>((a, b) -> Double.compare(a[0], b[0]));
        costSoFar.put(start, 0.0);
        frontier.add(new double[]{start.distanceTo(goal), start.row(), start.col()});
        boolean reached = false;
        int expanded = 0;
        while (!frontier.isEmpty() && !reached && expanded < 60_000) {
            double[] item = frontier.poll();
            GridPos current = new GridPos((int) item[1], (int) item[2]);
            expanded++;
            if (current.equals(goal)) { reached = true; continue; }
            for (int[] step : STEPS) {
                GridPos next = new GridPos(current.row() + step[0], current.col() + step[1]);
                if (!frame.inBounds(next) || (blocked.test(next) && !next.equals(goal))) continue;
                double stepLength = (step[0] != 0 && step[1] != 0) ? 1.414 : 1.0;
                double newCost = costSoFar.get(current) + stepLength * stepCost.applyAsDouble(next);
                Double known = costSoFar.get(next);
                if (known == null || newCost < known) {
                    costSoFar.put(next, newCost);
                    cameFrom.put(next, current);
                    frontier.add(new double[]{newCost + next.distanceTo(goal), next.row(), next.col()});
                }
            }
        }
        if (!reached) return List.of(start, goal);
        List<GridPos> path = new ArrayList<>();
        GridPos step = goal;
        while (step != null) { path.add(step); step = cameFrom.get(step); }
        Collections.reverse(path);
        return thin(path);
    }

    /** Keep only the squares where the direction changes (plus start and end). */
    private static List<GridPos> thin(List<GridPos> path) {
        if (path.size() <= 2) return path;
        List<GridPos> turns = new ArrayList<>();
        turns.add(path.get(0));
        for (int index = 1; index < path.size() - 1; index++) {
            GridPos before = path.get(index - 1), here = path.get(index), after = path.get(index + 1);
            boolean sameDirection = (here.row() - before.row()) == (after.row() - here.row())
                    && (here.col() - before.col()) == (after.col() - here.col());
            if (!sameDirection) turns.add(here);
        }
        turns.add(path.get(path.size() - 1));
        return turns;
    }
}
