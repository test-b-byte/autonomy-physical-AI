package c2.view;

import c2.model.ObjectKind;

import java.awt.Color;
import java.awt.Shape;
import java.awt.geom.Ellipse2D;
import java.awt.geom.Path2D;
import java.awt.geom.Rectangle2D;

/** Map symbols drawn in code: friendly = blue rectangle, hostile = red diamond, hazard = orange triangle. */
public final class SymbolPainter {
    private SymbolPainter() { }

    public static Color colorFor(ObjectKind kind) {
        return switch (kind) {
            case SUBJECT -> new Color(255, 255, 255);
            case DRONE -> new Color(60, 230, 230);
            case TOC, ANCHOR -> new Color(70, 140, 255);
            case TEAM -> new Color(110, 200, 255);
            case HAZARD -> new Color(245, 150, 20);
            case HOSTILE -> new Color(235, 50, 50);
        };
    }

    public static Shape shapeFor(ObjectKind kind, double x, double y, double size) {
        double half = size / 2;
        return switch (kind) {
            case TOC, ANCHOR -> new Rectangle2D.Double(x - half * 1.3, y - half, size * 1.3, size);
            case TEAM -> teamSymbol(x, y, half);
            case HOSTILE -> diamond(x, y, half * 1.2);
            case HAZARD -> triangle(x, y, half * 1.2);
            case SUBJECT -> new Ellipse2D.Double(x - half * 0.7, y - half * 0.7, size * 0.7, size * 0.7);
            case DRONE -> diamond(x, y, half);
        };
    }

    /** Friendly unit rectangle with a cross inside (the conventional "medical / rescue" mark). */
    private static Shape teamSymbol(double x, double y, double half) {
        Path2D.Double path = new Path2D.Double(Path2D.WIND_EVEN_ODD);
        path.append(new Rectangle2D.Double(x - half * 1.4, y - half, half * 2.8, half * 2), false);
        path.append(new Rectangle2D.Double(x - half * 0.2, y - half * 0.75, half * 0.4, half * 1.5), false);
        path.append(new Rectangle2D.Double(x - half * 0.75, y - half * 0.2, half * 1.5, half * 0.4), false);
        return path;
    }

    private static Shape diamond(double x, double y, double half) {
        Path2D.Double path = new Path2D.Double();
        path.moveTo(x, y - half);
        path.lineTo(x + half, y);
        path.lineTo(x, y + half);
        path.lineTo(x - half, y);
        path.closePath();
        return path;
    }

    private static Shape triangle(double x, double y, double half) {
        Path2D.Double path = new Path2D.Double();
        path.moveTo(x, y - half);
        path.lineTo(x + half, y + half * 0.8);
        path.lineTo(x - half, y + half * 0.8);
        path.closePath();
        return path;
    }
}
