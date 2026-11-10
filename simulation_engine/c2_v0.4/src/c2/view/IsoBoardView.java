package c2.view;

import c2.model.BeliefGrid;
import c2.model.GridPos;
import c2.model.Knowledge;
import c2.model.MapObject;
import c2.model.ObjectKind;
import c2.model.OperationsPicture;
import c2.model.PatrolRoute;
import c2.model.TerrainGrid;
import c2.model.TravelPath;
import c2.model.Waypoint;
import c2.model.Zone;
import c2.observe.PictureEvent;
import c2.observe.PictureObserver;

import javax.swing.JPanel;
import java.awt.AlphaComposite;
import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Composite;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.Polygon;
import java.awt.RenderingHints;
import java.awt.geom.Ellipse2D;
import java.awt.geom.Path2D;
import java.awt.image.BufferedImage;
import java.util.List;

/** The isometric board. Observer of the picture; draws terrain (cached), zones, heat, paths, objects. */
public class IsoBoardView extends JPanel implements PictureObserver {
    private static final KnowledgeStyle HOLO = new HoloStyle();
    private static final KnowledgeStyle SOLID = new SolidStyle();
    private static final Color BACKGROUND = new Color(8, 11, 16);
    private static final Color DRONE_CYAN = new Color(60, 230, 230);
    private static final Color ENEMY_RED = new Color(235, 50, 50);

    private final OperationsPicture picture;
    private final TerrainImageCache terrainCache;
    private final Camera camera;
    private final SpriteLibrary sprites;
    private final long startNanos = System.nanoTime();
    private volatile double lastFrameMillis;

    public IsoBoardView(OperationsPicture picture, TerrainImageCache terrainCache, Camera camera, SpriteLibrary sprites) {
        this.picture = picture;
        this.terrainCache = terrainCache;
        this.camera = camera;
        this.sprites = sprites;
        setPreferredSize(new Dimension(1100, 780));
        setBackground(BACKGROUND);
        setFocusable(true);
    }

    @Override
    public void onPictureChanged(PictureEvent event) { repaint(); }

    @Override
    protected void paintComponent(Graphics graphics) {
        super.paintComponent(graphics);
        long started = System.nanoTime();
        paintBoard((Graphics2D) graphics, getWidth(), getHeight());
        lastFrameMillis = (System.nanoTime() - started) / 1e6;
        graphics.setColor(new Color(130, 145, 160));
        graphics.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 11));
        graphics.drawString(String.format("frame %.1f ms   zoom %d/%d   arrows pan  Z/X zoom", lastFrameMillis,
                camera.zoomIndex() + 1, Camera.TILE_WIDTHS.length), 12, getHeight() - 12);
    }

    /** All drawing, separate from Swing so it can also render off-screen (snapshots, tests). */
    public void paintBoard(Graphics2D pen, int viewWidth, int viewHeight) {
        pen.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        pen.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        pen.setColor(BACKGROUND);
        pen.fillRect(0, 0, viewWidth, viewHeight);

        int tileWidth = camera.tileWidth();
        IsoProjection iso = terrainCache.projection(tileWidth);
        BufferedImage terrainImage = terrainCache.image(tileWidth);
        TerrainGrid terrain = picture.terrain();
        double centerHeight = terrain.at((int) camera.centerRow(), (int) camera.centerCol()).heightMeters();
        int offsetX = (int) (viewWidth / 2.0 - iso.x(camera.centerRow(), camera.centerCol()));
        int offsetY = (int) (viewHeight / 2.0 - iso.centerY(camera.centerRow(), camera.centerCol(), centerHeight));
        double clockSeconds = (System.nanoTime() - startNanos) / 1e9;

        pen.drawImage(terrainImage, offsetX, offsetY, null);
        pen.translate(offsetX, offsetY);
        synchronized (picture) {
            for (Zone zone : picture.zones()) drawZone(pen, iso, terrain, zone, clockSeconds);
            if (picture.phaseLine() != null) drawPhaseLine(pen, iso, terrain, picture.phaseLine());
            drawBelief(pen, iso, terrain, clockSeconds);
            for (PatrolRoute patrol : picture.patrols()) drawPatrol(pen, iso, terrain, patrol, clockSeconds);
            List<TravelPath> tracks = picture.flownTracks();                     // only the latest flown tracks
            for (int index = Math.max(0, tracks.size() - 3); index < tracks.size(); index++) {
                drawPath(pen, iso, terrain, tracks.get(index), clockSeconds);
            }
            for (TravelPath path : picture.plannedPaths()) drawPath(pen, iso, terrain, path, clockSeconds);
            drawObjectiveEffects(pen, iso, terrain, clockSeconds);
            for (MapObject object : picture.objects()) drawObject(pen, iso, terrain, object, clockSeconds);
        }
        pen.translate(-offsetX, -offsetY);
        drawLegend(pen);
        drawBanner(pen, viewWidth);
    }

    private Path2D.Double groundOutline(IsoProjection iso, TerrainGrid terrain, List<GridPos> cells, double lift) {
        Path2D.Double outline = new Path2D.Double();
        boolean first = true;
        for (GridPos corner : cells) {
            GridPos clamped = picture.frame().clamp(corner);
            double h = terrain.at(clamped).heightMeters() + lift;
            double x = iso.x(corner.row(), corner.col()), y = iso.centerY(corner.row(), corner.col(), h);
            if (first) { outline.moveTo(x, y); first = false; } else outline.lineTo(x, y);
        }
        outline.closePath();
        return outline;
    }

    /** Phase line: dashed green control line, with which side is friendly and which is denied. */
    private void drawPhaseLine(Graphics2D pen, IsoProjection iso, TerrainGrid terrain, c2.model.PhaseLine line) {
        GridPos from = line.from(), to = line.to();
        double fromX = iso.x(from.row(), from.col()), fromY = iso.centerY(from.row(), from.col(), terrain.at(from).heightMeters());
        double toX = iso.x(to.row(), to.col()), toY = iso.centerY(to.row(), to.col(), terrain.at(to).heightMeters());
        pen.setStroke(new BasicStroke(3f, BasicStroke.CAP_BUTT, BasicStroke.JOIN_ROUND, 10f, new float[]{14f, 8f}, 0f));
        pen.setColor(new Color(90, 230, 120, 220));
        pen.draw(new java.awt.geom.Line2D.Double(fromX, fromY, toX, toY));
        pen.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 12));
        drawTag(pen, line.label(), fromX + 6, fromY - 6, new Color(110, 240, 140), new Color(6, 30, 12, 200));
        pen.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 10));
        double midX = (fromX + toX) / 2, midY = (fromY + toY) / 2;
        drawTag(pen, "FRIENDLY", midX - 40, midY + 26, new Color(110, 240, 140), new Color(6, 30, 12, 180));
        drawTag(pen, "DENIED", midX + 18, midY - 18, new Color(255, 120, 120), new Color(40, 6, 6, 180));
    }

    /** Loiter ring around the casualty, and the beacon's pulsing IR rings. */
    private void drawObjectiveEffects(Graphics2D pen, IsoProjection iso, TerrainGrid terrain, double clockSeconds) {
        c2.model.AooStatus aoo = picture.aoo();
        if (aoo.state() == c2.model.AooState.LOITER) {
            MapObject subject = null;
            for (MapObject object : picture.objects()) if (object.kind() == ObjectKind.SUBJECT) subject = object;
            if (subject != null) {
                double x = iso.x(subject.pos().row(), subject.pos().col());
                double y = iso.centerY(subject.pos().row(), subject.pos().col(), terrain.at(subject.pos()).heightMeters());
                double radiusX = 2.4 * iso.tileWidth, radiusY = 2.4 * iso.tileHeight;
                pen.setStroke(new BasicStroke(2f, BasicStroke.CAP_BUTT, BasicStroke.JOIN_ROUND, 10f, new float[]{6f, 5f},
                        (float) (clockSeconds * 20 % 11)));
                pen.setColor(new Color(255, 210, 80, 220));
                pen.draw(new Ellipse2D.Double(x - radiusX, y - radiusY, radiusX * 2, radiusY * 2));
            }
        }
        GridPos beacon = picture.beaconPos();
        if (beacon != null && aoo.state() == c2.model.AooState.BEACON) {
            double x = iso.x(beacon.row(), beacon.col());
            double y = iso.centerY(beacon.row(), beacon.col(), terrain.at(beacon).heightMeters()) - 22;
            for (int ring = 0; ring < 3; ring++) {
                double phase = (clockSeconds * 0.8 + ring / 3.0) % 1.0;
                double radius = 8 + phase * 46;
                pen.setStroke(new BasicStroke(2.5f));
                pen.setColor(new Color(200, 60, 200, (int) (220 * (1 - phase))));
                pen.draw(new Ellipse2D.Double(x - radius, y - radius / 2, radius * 2, radius));
            }
            pen.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 10));
            drawTag(pen, "IR BEACON", x + 14, y - 16, new Color(240, 140, 240), new Color(30, 6, 30, 200));
        }
    }

    private void drawBanner(Graphics2D pen, int viewWidth) {
        String banner = picture.aoo().banner();
        if (banner == null) return;
        pen.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 22));
        int width = pen.getFontMetrics().stringWidth(banner) + 40;
        int x = (viewWidth - width) / 2, y = 60;
        pen.setColor(new Color(8, 40, 20, 225));
        pen.fillRoundRect(x, y, width, 44, 14, 14);
        pen.setColor(new Color(90, 230, 120));
        pen.setStroke(new BasicStroke(2f));
        pen.drawRoundRect(x, y, width, 44, 14, 14);
        pen.drawString(banner, x + 20, y + 30);
    }

    /** Enemy area: translucent red, pulsing dashed border, label. */
    private void drawZone(Graphics2D pen, IsoProjection iso, TerrainGrid terrain, Zone zone, double clockSeconds) {
        Path2D.Double outline = groundOutline(iso, terrain, zone.corners(), 0);
        double pulse = 0.5 + 0.5 * Math.sin(clockSeconds * 1.6);
        pen.setColor(new Color(200, 30, 40, (int) (34 + 22 * pulse)));
        pen.fill(outline);
        pen.setStroke(new BasicStroke(2f, BasicStroke.CAP_BUTT, BasicStroke.JOIN_ROUND, 10f, new float[]{9f, 6f},
                (float) (clockSeconds * 8 % 15)));
        pen.setColor(new Color(255, 70, 70, (int) (150 + 90 * pulse)));
        pen.draw(outline);
        GridPos labelCell = zone.corners().get(0);
        double h = terrain.at(picture.frame().clamp(labelCell)).heightMeters();
        pen.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 13));
        drawTag(pen, zone.label(), iso.x(labelCell.row(), labelCell.col()) + 8, iso.centerY(labelCell.row(), labelCell.col(), h) + 18,
                new Color(255, 90, 90), new Color(60, 8, 10, 190));
    }

    /**
     * Probability heat: color ramp from amber to red to hot magenta-white, stronger opacity than v0.1,
     * a bright contour where it crosses 50% of the peak, and a pulsing ring on the peak square.
     */
    private void drawBelief(Graphics2D pen, IsoProjection iso, TerrainGrid terrain, double clockSeconds) {
        BeliefGrid belief = picture.belief();
        double max = belief.max();
        if (max <= 0) return;
        int halfW = iso.tileWidth / 2, halfH = iso.tileHeight / 2;
        int peakRow = 0, peakCol = 0;
        pen.setStroke(new BasicStroke(1.6f));
        for (int row = 0; row < belief.rows(); row++) {
            for (int col = 0; col < belief.cols(); col++) {
                double strength = belief.at(row, col) / max;
                if (strength >= 0.999) { peakRow = row; peakCol = col; }
                if (strength < 0.12) continue;
                pen.setColor(heatColor(strength));
                int x = (int) iso.x(row, col), y = (int) iso.y(row, col, terrain.at(row, col).heightMeters());
                pen.fillPolygon(new Polygon(new int[]{x, x + halfW, x, x - halfW}, new int[]{y, y + halfH, y + 2 * halfH, y + halfH}, 4));
                if (strength >= 0.5) drawContourEdges(pen, belief, row, col, max, x, y, halfW, halfH);
            }
        }
        double h = terrain.at(peakRow, peakCol).heightMeters();
        double px = iso.x(peakRow, peakCol), py = iso.centerY(peakRow, peakCol, h);
        double ring = 10 + 6 * Math.sin(clockSeconds * 4);
        pen.setStroke(new BasicStroke(2f));
        pen.setColor(new Color(255, 230, 120, 200));
        pen.draw(new Ellipse2D.Double(px - ring, py - ring / 2, ring * 2, ring));
    }

    /** Bright line only on the diamond edges that face a square below 50% of the peak: a clean contour. */
    private static void drawContourEdges(Graphics2D pen, BeliefGrid belief, int row, int col, double max,
                                         int x, int y, int halfW, int halfH) {
        pen.setColor(new Color(255, 236, 140, 230));
        if (below(belief, row - 1, col, max)) pen.drawLine(x, y, x + halfW, y + halfH);                     // north-east edge
        if (below(belief, row + 1, col, max)) pen.drawLine(x - halfW, y + halfH, x, y + 2 * halfH);         // south-west edge
        if (below(belief, row, col - 1, max)) pen.drawLine(x, y, x - halfW, y + halfH);                     // north-west edge
        if (below(belief, row, col + 1, max)) pen.drawLine(x + halfW, y + halfH, x, y + 2 * halfH);         // south-east edge
    }

    private static boolean below(BeliefGrid belief, int row, int col, double max) {
        if (row < 0 || row >= belief.rows() || col < 0 || col >= belief.cols()) return true;
        return belief.at(row, col) / max < 0.5;
    }

    private static Color heatColor(double strength) {
        // amber (low) -> red (mid) -> magenta (high) -> near-white (peak)
        double s = Math.min(1, strength);
        int red, green, blue;
        if (s < 0.4) { double t = s / 0.4; red = 255; green = (int) (170 - 110 * t); blue = 20; }
        else if (s < 0.8) { double t = (s - 0.4) / 0.4; red = 255; green = (int) (60 - 40 * t); blue = (int) (20 + 120 * t); }
        else { double t = (s - 0.8) / 0.2; red = 255; green = (int) (20 + 200 * t); blue = (int) (140 + 100 * t); }
        int alpha = (int) Math.min(230, 20 + 210 * Math.pow(s, 1.3));     // faint at the edges, strong at the core
        return new Color(red, green, blue, alpha);
    }

    private void drawPatrol(Graphics2D pen, IsoProjection iso, TerrainGrid terrain, PatrolRoute patrol, double clockSeconds) {
        Path2D.Double loop = groundOutline(iso, terrain, patrol.loop(), 10);
        pen.setStroke(new BasicStroke(1.5f, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND, 10f, new float[]{3f, 5f},
                (float) (clockSeconds * 6 % 8)));
        pen.setColor(new Color(255, 80, 80, 150));
        pen.draw(loop);
    }

    private void drawPath(Graphics2D pen, IsoProjection iso, TerrainGrid terrain, TravelPath path, double clockSeconds) {
        Path2D.Double line = new Path2D.Double();
        boolean first = true;
        for (Waypoint waypoint : path.waypoints()) {
            double h = terrain.at(waypoint.pos()).heightMeters() + 40;       // drawn a little above ground
            double x = iso.x(waypoint.pos().row(), waypoint.pos().col());
            double y = iso.centerY(waypoint.pos().row(), waypoint.pos().col(), h);
            if (first) { line.moveTo(x, y); first = false; } else line.lineTo(x, y);
        }
        if (path.knowledge() == Knowledge.HOLO) {
            float phase = (float) (clockSeconds * 12 % 10);
            pen.setStroke(new BasicStroke(4f, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
            pen.setColor(new Color(60, 230, 230, 40));                       // soft glow under the dashes
            pen.draw(line);
            pen.setStroke(new BasicStroke(2f, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND, 10f, new float[]{6f, 4f}, 10f - phase));
            pen.setColor(new Color(60, 230, 230, 220));
            pen.draw(line);
            for (Waypoint waypoint : path.waypoints()) {
                double h = terrain.at(waypoint.pos()).heightMeters() + 40;
                double x = iso.x(waypoint.pos().row(), waypoint.pos().col());
                double y = iso.centerY(waypoint.pos().row(), waypoint.pos().col(), h);
                HOLO.paint(pen, new Ellipse2D.Double(x - 3, y - 3, 6, 6), DRONE_CYAN, clockSeconds);
            }
        } else {
            pen.setStroke(new BasicStroke(1.5f));
            pen.setColor(new Color(60, 230, 230, 60));
            pen.draw(line);
        }
    }

    private void drawObject(Graphics2D pen, IsoProjection iso, TerrainGrid terrain, MapObject object, double clockSeconds) {
        double h = terrain.at(object.pos()).heightMeters();
        double x = iso.x(object.pos().row(), object.pos().col());
        double groundY = iso.centerY(object.pos().row(), object.pos().col(), h);
        boolean holo = object.knowledge() == Knowledge.HOLO;
        KnowledgeStyle style = holo ? HOLO : SOLID;
        Color color = SymbolPainter.colorFor(object.kind());

        if (holo && object.uncertaintyCells() > 1) {                        // prediction ring, flattened to the iso ground
            double ringW = object.uncertaintyCells() * iso.tileWidth, ringH = object.uncertaintyCells() * iso.tileHeight;
            pen.setStroke(new BasicStroke(1.2f, BasicStroke.CAP_BUTT, BasicStroke.JOIN_MITER, 10f, new float[]{5f, 5f}, 0f));
            pen.setColor(new Color(color.getRed(), color.getGreen(), color.getBlue(), 120));
            pen.draw(new Ellipse2D.Double(x - ringW / 2, groundY - ringH / 2, ringW, ringH));
        }

        boolean isDrone = object.kind() == ObjectKind.DRONE;
        double size = object.kind() == ObjectKind.HOSTILE ? 16 : 14;
        double symbolY = groundY - (isDrone ? 22 : 12);                     // drones fly higher
        pen.setStroke(new BasicStroke(1f));
        pen.setColor(new Color(0, 0, 0, 120));
        pen.drawLine((int) x, (int) groundY, (int) x, (int) symbolY);       // stalk to the ground point
        pen.fill(new Ellipse2D.Double(x - 3, groundY - 1.5, 6, 3));

        BufferedImage droneSprite = sprites.drone();
        if (isDrone && droneSprite != null) {
            double spriteW = 30, spriteH = spriteW * droneSprite.getHeight() / droneSprite.getWidth();
            Composite before = pen.getComposite();
            if (holo) pen.setComposite(AlphaComposite.getInstance(AlphaComposite.SRC_OVER,
                    (float) (0.45 + 0.25 * Math.sin(clockSeconds * 3))));
            pen.drawImage(droneSprite, (int) (x - spriteW / 2), (int) (symbolY - spriteH / 2), (int) spriteW, (int) spriteH, null);
            pen.setComposite(before);
        } else {
            style.paint(pen, SymbolPainter.shapeFor(object.kind(), x, symbolY, size), color, clockSeconds);
        }

        pen.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 10));
        Color textColor = holo ? new Color(color.getRed(), color.getGreen(), color.getBlue(), 190) : color;
        drawTag(pen, object.label() + (holo ? " ?" : ""), x + 11, symbolY - 4, textColor, new Color(0, 0, 0, 140));
    }

    /** Small label with a dark backing so it reads over any terrain. */
    private static void drawTag(Graphics2D pen, String text, double x, double y, Color textColor, Color backing) {
        int width = pen.getFontMetrics().stringWidth(text);
        pen.setColor(backing);
        pen.fillRoundRect((int) x - 3, (int) y - 11, width + 6, 14, 4, 4);
        pen.setColor(textColor);
        pen.drawString(text, (int) x, (int) y);
    }

    private void drawLegend(Graphics2D pen) {
        pen.setColor(new Color(10, 16, 26, 210));
        pen.fillRoundRect(10, 10, 430, 26, 10, 10);
        pen.setColor(new Color(60, 230, 230, 120));
        pen.drawRoundRect(10, 10, 430, 26, 10, 10);
        pen.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 11));
        pen.setColor(new Color(215, 225, 235));
        pen.drawString("SOLID = confirmed    translucent / dashed = HOLO (predicted)    ? = estimate", 20, 27);
    }
}
