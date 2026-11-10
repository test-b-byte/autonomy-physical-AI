package c2.view;

import c2.input.Command;
import c2.input.CommandSink;

/** What part of the board is in view: a center square and a zoom level. */
public class Camera implements CommandSink {
    public static final int[] TILE_WIDTHS = {6, 12, 24, 40};
    private static final int PAN_STEP_CELLS = 6;

    private volatile double centerRow, centerCol;
    private volatile int zoomIndex;
    private final int rows, cols;
    private Runnable onChange = () -> { };

    public Camera(int rows, int cols, double centerRow, double centerCol, int zoomIndex) {
        this.rows = rows;
        this.cols = cols;
        this.centerRow = centerRow;
        this.centerCol = centerCol;
        this.zoomIndex = zoomIndex;
    }

    public void setOnChange(Runnable onChange) { this.onChange = onChange; }

    public int zoomIndex() { return zoomIndex; }
    public int tileWidth() { return TILE_WIDTHS[zoomIndex]; }
    public double centerRow() { return centerRow; }
    public double centerCol() { return centerCol; }

    @Override
    public void submit(Command command) {
        switch (command.type()) {
            case PAN -> {
                centerRow = Math.max(0, Math.min(rows - 1, centerRow + command.dRow() * PAN_STEP_CELLS));
                centerCol = Math.max(0, Math.min(cols - 1, centerCol + command.dCol() * PAN_STEP_CELLS));
            }
            case ZOOM_IN -> zoomIndex = Math.min(TILE_WIDTHS.length - 1, zoomIndex + 1);
            case ZOOM_OUT -> zoomIndex = Math.max(0, zoomIndex - 1);
            default -> { return; }
        }
        onChange.run();
    }
}
