package c2.view;

/**
 * Square -> screen math only (AirCom's IsoRig, plus height). 2:1 isometric diamonds.
 * Positions are relative to the board image's top-left corner.
 */
public class IsoProjection {
    public final int tileWidth, tileHeight;
    public final double pixelsPerMeter;
    private final int rows, cols, margin, heightHeadroom;

    public IsoProjection(int tileWidth, int rows, int cols, double maxHeightMeters) {
        this.tileWidth = tileWidth;
        this.tileHeight = tileWidth / 2;
        this.pixelsPerMeter = tileHeight / 30.0;            // 30 m of height = half a tile
        this.rows = rows;
        this.cols = cols;
        this.margin = tileWidth * 2;
        this.heightHeadroom = (int) Math.ceil(maxHeightMeters * pixelsPerMeter);
    }

    /** Screen x of a square's top corner. */
    public double x(double row, double col) { return (col - row) * tileWidth / 2.0 + rows * tileWidth / 2.0 + margin; }

    /** Screen y of a square's top corner, lifted by its height. */
    public double y(double row, double col, double heightMeters) {
        return (col + row) * tileHeight / 2.0 + heightHeadroom + margin - heightMeters * pixelsPerMeter;
    }

    /** Screen y of a square's center (half a tile below its top corner). */
    public double centerY(double row, double col, double heightMeters) { return y(row, col, heightMeters) + tileHeight / 2.0; }

    public int boardWidth() { return (rows + cols) * tileWidth / 2 + 2 * margin; }
    public int boardHeight() { return (rows + cols) * tileHeight / 2 + heightHeadroom + 2 * margin + tileHeight; }
}
