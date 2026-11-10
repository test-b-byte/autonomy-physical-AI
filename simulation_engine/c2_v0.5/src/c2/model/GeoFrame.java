package c2.model;

/**
 * The shared coordinate frame. Board is rows x cols squares of metersPerCell.
 * Convention: row 0 = north edge, col 0 = west edge. World meters: east = +x, north = +y,
 * origin at the board's south-west corner.
 */
public record GeoFrame(int rows, int cols, double metersPerCell) {
    public boolean inBounds(GridPos pos) {
        return pos.row() >= 0 && pos.row() < rows && pos.col() >= 0 && pos.col() < cols;
    }
    public double eastMeters(GridPos pos) { return (pos.col() + 0.5) * metersPerCell; }
    public double northMeters(GridPos pos) { return (rows - pos.row() - 0.5) * metersPerCell; }
    public GridPos clamp(GridPos pos) {
        return new GridPos(Math.max(0, Math.min(rows - 1, pos.row())), Math.max(0, Math.min(cols - 1, pos.col())));
    }
}
