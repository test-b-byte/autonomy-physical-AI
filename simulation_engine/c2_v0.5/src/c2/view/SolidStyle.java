package c2.view;

import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.Shape;

/** Confirmed: filled, full color, solid outline. */
public class SolidStyle implements KnowledgeStyle {
    @Override
    public void paint(Graphics2D pen, Shape shape, Color color, double clockSeconds) {
        pen.setColor(color);
        pen.fill(shape);
        pen.setStroke(new BasicStroke(1.5f));
        pen.setColor(color.darker().darker());
        pen.draw(shape);
    }
}
