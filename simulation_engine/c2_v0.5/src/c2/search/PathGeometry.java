package c2.search;

import c2.model.GeoFrame;
import c2.model.GridPos;
import c2.model.TravelPath;

import java.util.LinkedHashSet;
import java.util.Set;

/** Which squares a flight path passes over, including a sensor corridor either side. */
public final class PathGeometry {
    private PathGeometry() { }

    public static Set<GridPos> sweptCells(TravelPath path, GeoFrame frame, int corridorCells) {
        Set<GridPos> swept = new LinkedHashSet<>();
        for (int index = 1; index < path.waypoints().size(); index++) {
            GridPos from = path.waypoints().get(index - 1).pos();
            GridPos to = path.waypoints().get(index).pos();
            int steps = (int) Math.max(1, Math.ceil(from.distanceTo(to)));
            for (int step = 0; step <= steps; step++) {
                int row = (int) Math.round(from.row() + (to.row() - from.row()) * step / (double) steps);
                int col = (int) Math.round(from.col() + (to.col() - from.col()) * step / (double) steps);
                for (int dRow = -corridorCells; dRow <= corridorCells; dRow++) {
                    for (int dCol = -corridorCells; dCol <= corridorCells; dCol++) {
                        GridPos cell = new GridPos(row + dRow, col + dCol);
                        if (frame.inBounds(cell)) swept.add(cell);
                    }
                }
            }
        }
        return swept;
    }
}
