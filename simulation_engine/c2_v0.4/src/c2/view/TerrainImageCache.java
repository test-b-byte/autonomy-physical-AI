package c2.view;

import c2.model.GroundCover;
import c2.model.TerrainCell;
import c2.model.TerrainGrid;

import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.Polygon;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.util.HashMap;
import java.util.Map;

/**
 * Terrain never changes, so it's drawn once per zoom level into an image and reused every frame.
 * Adds hillshading, per-square color variation, and textures: trees on forest, speckle on rock,
 * ripples on water, tufts on open ground.
 */
public class TerrainImageCache {
    private static final Color CONIFER = new Color(18, 40, 24), CONIFER_SHADE = new Color(12, 28, 17);
    private static final Color LEAF = new Color(40, 70, 36), LEAF_LIGHT = new Color(64, 96, 52);
    private static final Color SHADOW = new Color(0, 0, 0, 70);

    private final TerrainGrid terrain;
    private final int rows, cols;
    private final Map<Integer, BufferedImage> images = new HashMap<>();
    private final Map<Integer, IsoProjection> projections = new HashMap<>();

    public TerrainImageCache(TerrainGrid terrain, int rows, int cols) {
        this.terrain = terrain;
        this.rows = rows;
        this.cols = cols;
    }

    public synchronized IsoProjection projection(int tileWidth) {
        return projections.computeIfAbsent(tileWidth, width -> new IsoProjection(width, rows, cols, terrain.maxHeight()));
    }

    public synchronized BufferedImage image(int tileWidth) {
        return images.computeIfAbsent(tileWidth, this::render);
    }

    private BufferedImage render(int tileWidth) {
        IsoProjection iso = projection(tileWidth);
        BufferedImage image = new BufferedImage(iso.boardWidth(), iso.boardHeight(), BufferedImage.TYPE_INT_ARGB);
        Graphics2D pen = image.createGraphics();
        pen.setRenderingHint(RenderingHints.KEY_ANTIALIASING,
                tileWidth >= 24 ? RenderingHints.VALUE_ANTIALIAS_ON : RenderingHints.VALUE_ANTIALIAS_OFF);
        pen.setStroke(new BasicStroke(1f));

        // Back to front (painter's order): squares with a smaller row+col are farther away.
        for (int depth = 0; depth <= rows + cols - 2; depth++) {
            for (int row = Math.max(0, depth - cols + 1); row <= Math.min(rows - 1, depth); row++) {
                int col = depth - row;
                drawTile(pen, iso, row, col);
            }
        }
        pen.dispose();
        return image;
    }

    private double heightAt(int row, int col) {
        return terrain.at(Math.max(0, Math.min(rows - 1, row)), Math.max(0, Math.min(cols - 1, col))).heightMeters();
    }

    private void drawTile(Graphics2D pen, IsoProjection iso, int row, int col) {
        TerrainCell cell = terrain.at(row, col);
        double h = cell.heightMeters();
        int topX = (int) Math.round(iso.x(row, col)), topY = (int) Math.round(iso.y(row, col, h));
        int halfW = iso.tileWidth / 2, halfH = iso.tileHeight / 2;

        // Hillshade: light from the upper-left of the screen.
        double slopeAcross = heightAt(row, col + 1) - heightAt(row, col - 1);
        double slopeDown = heightAt(row + 1, col) - heightAt(row - 1, col);
        double light = 1.0 + clamp(slopeAcross * 0.010 - slopeDown * 0.006, -0.35, 0.30);
        double variation = 1.0 + 0.07 * noise(row, col);                     // per-square color variation
        Color base = cell.cover().color;
        Color topColor = shade(base, light * variation);

        // Side walls down to each lower front neighbour (+1 px overlap so no seams show).
        double frontLeft = row + 1 < rows ? heightAt(row + 1, col) : h - 40;
        double frontRight = col + 1 < cols ? heightAt(row, col + 1) : h - 40;
        int leftDrop = (int) Math.ceil(Math.max(0, (h - frontLeft) * iso.pixelsPerMeter)) + 1;
        int rightDrop = (int) Math.ceil(Math.max(0, (h - frontRight) * iso.pixelsPerMeter)) + 1;
        pen.setColor(shade(topColor, 0.70));
        pen.fillPolygon(new int[]{topX - halfW, topX, topX, topX - halfW},
                new int[]{topY + halfH, topY + 2 * halfH, topY + 2 * halfH + leftDrop, topY + halfH + leftDrop}, 4);
        pen.setColor(shade(topColor, 0.84));
        pen.fillPolygon(new int[]{topX, topX + halfW, topX + halfW, topX},
                new int[]{topY + 2 * halfH, topY + halfH, topY + halfH + rightDrop, topY + 2 * halfH + rightDrop}, 4);

        Polygon top = new Polygon(new int[]{topX, topX + halfW, topX, topX - halfW},
                new int[]{topY, topY + halfH, topY + 2 * halfH, topY + halfH}, 4);
        pen.setColor(topColor);
        pen.fillPolygon(top);
        pen.drawPolygon(top);                                               // closes 1 px gaps between squares
        if (cell.cliff() && iso.tileWidth >= 12) {
            pen.setColor(new Color(40, 28, 20, 160));
            pen.drawLine(topX - halfW, topY + halfH, topX, topY + 2 * halfH);
        }

        drawTexture(pen, iso, cell.cover(), row, col, topX, topY, halfW, halfH);
    }

    private void drawTexture(Graphics2D pen, IsoProjection iso, GroundCover cover, int row, int col,
                             int topX, int topY, int halfW, int halfH) {
        int tileWidth = iso.tileWidth;
        if (tileWidth < 12) {
            if (cover == GroundCover.HEAVY_FOREST && noise(row * 7, col * 3) > 0.2) {
                pen.setColor(CONIFER);
                pen.fillRect(topX, topY + halfH, 1, 1);
            }
            return;
        }
        switch (cover) {
            case HEAVY_FOREST -> {
                int treeCount = tileWidth >= 24 ? 4 : 3;
                for (int tree = 0; tree < treeCount; tree++) {
                    double u = 0.15 + 0.7 * unit(row, col, tree * 2), v = 0.15 + 0.7 * unit(row, col, tree * 2 + 1);
                    drawConifer(pen, topX + (u - v) * halfW, topY + (u + v) * halfH, tileWidth);
                }
            }
            case LIGHT_FOREST -> {
                int treeCount = unit(row, col, 9) > 0.45 ? 2 : 1;
                for (int tree = 0; tree < treeCount; tree++) {
                    double u = 0.2 + 0.6 * unit(row, col, tree * 2 + 4), v = 0.2 + 0.6 * unit(row, col, tree * 2 + 5);
                    drawRoundTree(pen, topX + (u - v) * halfW, topY + (u + v) * halfH, tileWidth);
                }
            }
            case ROCK -> {
                for (int speck = 0; speck < 3; speck++) {
                    double u = unit(row, col, speck * 2), v = unit(row, col, speck * 2 + 1);
                    pen.setColor(speck % 2 == 0 ? new Color(140, 136, 128) : new Color(70, 68, 64));
                    int size = Math.max(1, tileWidth / 12);
                    pen.fillRect((int) (topX + (u - v) * halfW), (int) (topY + (u + v) * halfH), size, size);
                }
            }
            case MOUNTAIN -> {
                for (int speck = 0; speck < 4; speck++) {
                    double u = unit(row, col, speck * 2 + 20), v = unit(row, col, speck * 2 + 21);
                    pen.setColor(speck % 2 == 0 ? new Color(150, 122, 92) : new Color(72, 54, 38));
                    int size = Math.max(1, tileWidth / 10);
                    pen.fillRect((int) (topX + (u - v) * halfW), (int) (topY + (u + v) * halfH), size, size);
                }
                if (terrain.at(row, col).heightMeters() > terrain.maxHeight() - 60) {           // snow on the highest peaks
                    pen.setColor(new Color(228, 232, 236, 200));
                    pen.fillOval(topX - halfW / 3, topY + halfH / 2, (2 * halfW) / 3, halfH);
                }
            }
            case WATER -> {
                if (unit(row, col, 3) > 0.55) {
                    pen.setColor(new Color(70, 110, 160, 150));
                    int x = (int) (topX + (unit(row, col, 1) - 0.5) * halfW), y = topY + halfH;
                    pen.drawLine(x - tileWidth / 8, y, x + tileWidth / 8, y);
                }
            }
            case OPEN -> {
                if (tileWidth >= 24 && unit(row, col, 5) > 0.5) {
                    pen.setColor(new Color(66, 78, 42));
                    double u = unit(row, col, 6), v = unit(row, col, 7);
                    int x = (int) (topX + (u - v) * halfW), y = (int) (topY + (u + v) * halfH);
                    pen.drawLine(x, y, x - 1, y - 2);
                    pen.drawLine(x, y, x + 1, y - 2);
                }
            }
            default -> { }
        }
    }

    /** Dark conifer: a tall triangle, the right half shaded, with a ground shadow. */
    private static void drawConifer(Graphics2D pen, double baseX, double baseY, int tileWidth) {
        double width = tileWidth * 0.20, height = tileWidth * 0.36;
        pen.setColor(SHADOW);
        pen.fillOval((int) (baseX - width * 0.2), (int) (baseY - width * 0.15), (int) (width * 1.2), (int) (width * 0.45));
        int[] xs = {(int) baseX, (int) (baseX + width / 2), (int) (baseX - width / 2)};
        int[] ys = {(int) (baseY - height), (int) baseY, (int) baseY};
        pen.setColor(CONIFER);
        pen.fillPolygon(xs, ys, 3);
        pen.setColor(CONIFER_SHADE);
        pen.fillPolygon(new int[]{(int) baseX, (int) (baseX + width / 2), (int) baseX},
                new int[]{(int) (baseY - height), (int) baseY, (int) baseY}, 3);
    }

    /** Round broadleaf tree: dark canopy with a lit upper-left edge, and a ground shadow. */
    private static void drawRoundTree(Graphics2D pen, double baseX, double baseY, int tileWidth) {
        double radius = tileWidth * 0.12;
        pen.setColor(SHADOW);
        pen.fillOval((int) (baseX - radius * 0.6), (int) (baseY - radius * 0.3), (int) (radius * 2.0), (int) (radius * 0.8));
        pen.setColor(LEAF);
        pen.fillOval((int) (baseX - radius), (int) (baseY - radius * 2.2), (int) (radius * 2), (int) (radius * 2));
        pen.setColor(LEAF_LIGHT);
        pen.fillOval((int) (baseX - radius * 0.7), (int) (baseY - radius * 2.0), (int) (radius * 0.9), (int) (radius * 0.9));
    }

    /** Repeatable pseudo-random value in [-1, 1] for a square (same every render, no stored state). */
    private static double noise(int row, int col) {
        long hash = row * 73856093L ^ col * 19349663L;
        hash = (hash ^ (hash >>> 13)) * 1274126177L;
        return ((hash >>> 16) & 0xFFFF) / 32767.5 - 1.0;
    }

    /** Repeatable pseudo-random value in [0, 1] for a square and a slot number. */
    private static double unit(int row, int col, int slot) { return (noise(row * 31 + slot * 7, col * 17 + slot * 13) + 1) / 2; }

    private static double clamp(double value, double low, double high) { return Math.max(low, Math.min(high, value)); }

    private static Color shade(Color color, double factor) {
        return new Color(channel(color.getRed() * factor), channel(color.getGreen() * factor),
                channel(color.getBlue() * factor), color.getAlpha());
    }

    private static int channel(double value) { return (int) Math.max(0, Math.min(255, value)); }
}
