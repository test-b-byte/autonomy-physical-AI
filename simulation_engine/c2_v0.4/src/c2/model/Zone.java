package c2.model;

import java.util.List;

/** An area on the board, as a polygon of square corners (row, col). Ray-cast point-in-polygon test. */
public record Zone(String label, ZoneType type, List<GridPos> corners, Knowledge knowledge) {
    public boolean contains(GridPos pos) {
        boolean inside = false;
        for (int index = 0, previous = corners.size() - 1; index < corners.size(); previous = index++) {
            GridPos a = corners.get(index), b = corners.get(previous);
            boolean crosses = (a.row() > pos.row()) != (b.row() > pos.row());
            if (crosses) {
                double colAtRow = (b.col() - a.col()) * (pos.row() - a.row()) / (double) (b.row() - a.row()) + a.col();
                if (pos.col() < colAtRow) inside = !inside;
            }
        }
        return inside;
    }
}
