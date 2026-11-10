package c2.model;

/** One square on the board. Value object: two GridPos with the same row/col are equal. */
public record GridPos(int row, int col) {
    public double distanceTo(GridPos other) {
        return Math.hypot(row - other.row, col - other.col);
    }
}
