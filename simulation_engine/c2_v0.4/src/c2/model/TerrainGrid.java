package c2.model;

/** Terrain for every square. synthetic() builds a demo landscape until terrain.json prep exists. */
public class TerrainGrid {
    private final TerrainCell[][] cells;
    private final double maxHeight;

    public TerrainGrid(TerrainCell[][] cells) {
        this.cells = cells;
        double highest = 0;
        for (TerrainCell[] row : cells) for (TerrainCell cell : row) highest = Math.max(highest, cell.heightMeters());
        this.maxHeight = highest;
    }

    public TerrainCell at(GridPos pos) { return cells[pos.row()][pos.col()]; }
    public TerrainCell at(int row, int col) { return cells[row][col]; }
    public double maxHeight() { return maxHeight; }

    /**
     * A copy of this terrain with the test floor's features built in:
     * brown obstacles raise the ground into mountains (with a gentle shoulder around them),
     * grey obstacles change the ground cover to rock. Cliff flags are recomputed afterwards.
     */
    public TerrainGrid withRoomFeatures(RoomFeatures features) {
        int rows = cells.length, cols = cells[0].length;
        double[][] height = new double[rows][cols];
        GroundCover[][] cover = new GroundCover[rows][cols];
        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                height[row][col] = cells[row][col].heightMeters();
                cover[row][col] = cells[row][col].cover();
            }
        }
        double[][] lift = new double[rows][cols];
        for (var entry : features.mountains().entrySet()) {
            GridPos peak = entry.getKey();
            double peakLift = entry.getValue();
            for (int dRow = -2; dRow <= 2; dRow++) {
                for (int dCol = -2; dCol <= 2; dCol++) {
                    int row = peak.row() + dRow, col = peak.col() + dCol;
                    if (row < 0 || row >= rows || col < 0 || col >= cols) continue;
                    double distance = Math.hypot(dRow, dCol);
                    double share = distance == 0 ? 1.0 : Math.max(0, 1.0 - distance / 3.0) * 0.8;
                    lift[row][col] = Math.max(lift[row][col], peakLift * share);
                }
            }
            if (peak.row() >= 0 && peak.row() < rows && peak.col() >= 0 && peak.col() < cols) {
                cover[peak.row()][peak.col()] = GroundCover.MOUNTAIN;
            }
        }
        for (GridPos shifted : features.shifts()) {
            if (shifted.row() < 0 || shifted.row() >= rows || shifted.col() < 0 || shifted.col() >= cols) continue;
            if (cover[shifted.row()][shifted.col()] != GroundCover.WATER) cover[shifted.row()][shifted.col()] = GroundCover.ROCK;
            lift[shifted.row()][shifted.col()] = Math.max(lift[shifted.row()][shifted.col()], 18);
        }
        TerrainCell[][] updated = new TerrainCell[rows][cols];
        for (int row = 0; row < rows; row++) for (int col = 0; col < cols; col++) height[row][col] += lift[row][col];
        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                double h = height[row][col], drop = 0;
                if (row + 1 < rows) drop = Math.max(drop, Math.abs(h - height[row + 1][col]));
                if (col + 1 < cols) drop = Math.max(drop, Math.abs(h - height[row][col + 1]));
                updated[row][col] = new TerrainCell(h, cover[row][col], drop > 16.0 && cover[row][col] != GroundCover.WATER);
            }
        }
        return new TerrainGrid(updated);
    }

    /** Demo terrain: rolling hills, a ridge with a cliff band, a river, a trail, forest by elevation. */
    public static TerrainGrid synthetic(GeoFrame frame) {
        int rows = frame.rows(), cols = frame.cols();
        double[][] height = new double[rows][cols];
        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                double y = row / (double) rows, x = col / (double) cols;
                height[row][col] = 120
                        + 60 * Math.sin(x * 6.0) * Math.cos(y * 4.0)
                        + 40 * Math.sin((x + y) * 9.0)
                        + 90 * Math.exp(-Math.pow((x - 0.62) * 6, 2))     // north-south ridge
                        + 20 * Math.sin(x * 23.0) * Math.sin(y * 19.0);
            }
        }
        TerrainCell[][] cells = new TerrainCell[rows][cols];
        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                double h = height[row][col];
                double neighborDrop = 0;
                if (row + 1 < rows) neighborDrop = Math.max(neighborDrop, Math.abs(h - height[row + 1][col]));
                if (col + 1 < cols) neighborDrop = Math.max(neighborDrop, Math.abs(h - height[row][col + 1]));
                boolean cliff = neighborDrop > 16.0;

                int riverCol = (int) (cols * 0.28 + 10 * Math.sin(row / 11.0));
                int trailRow = (int) (rows * 0.55 + 14 * Math.sin(col / 17.0));
                GroundCover cover;
                if (Math.abs(col - riverCol) <= 1) cover = GroundCover.WATER;
                else if (Math.abs(row - trailRow) == 0) cover = GroundCover.TRAIL;
                else if (h > 245) cover = GroundCover.ROCK;
                else if (h > 175) cover = GroundCover.HEAVY_FOREST;
                else if (h > 125) cover = GroundCover.LIGHT_FOREST;
                else cover = GroundCover.OPEN;
                cells[row][col] = new TerrainCell(h, cover, cliff && cover != GroundCover.WATER);
            }
        }
        return new TerrainGrid(cells);
    }
}
