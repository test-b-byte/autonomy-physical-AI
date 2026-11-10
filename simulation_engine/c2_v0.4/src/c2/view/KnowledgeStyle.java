package c2.view;

import java.awt.Graphics2D;
import java.awt.Shape;
import java.awt.Color;

/** Strategy: how an object is drawn, chosen by its knowledge state. */
public interface KnowledgeStyle {
    void paint(Graphics2D pen, Shape shape, Color color, double clockSeconds);
}
