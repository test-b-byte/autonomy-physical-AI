package c2.view;

import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.Shape;

/** Predicted / planned: translucent fill, dashed outline, slow shimmer. */
public class HoloStyle implements KnowledgeStyle {
    private static final float[] DASH = {4f, 3f};

    @Override
    public void paint(Graphics2D pen, Shape shape, Color color, double clockSeconds) {
        double shimmer = 0.5 + 0.5 * Math.sin(clockSeconds * 3.0);
        int fillAlpha = (int) (40 + 40 * shimmer), lineAlpha = (int) (140 + 100 * shimmer);
        pen.setColor(new Color(color.getRed(), color.getGreen(), color.getBlue(), fillAlpha));
        pen.fill(shape);
        pen.setStroke(new BasicStroke(1.5f, BasicStroke.CAP_BUTT, BasicStroke.JOIN_MITER, 10f, DASH,
                (float) (clockSeconds * 6 % 7)));
        pen.setColor(new Color(color.getRed(), color.getGreen(), color.getBlue(), lineAlpha));
        pen.draw(shape);
    }
}
