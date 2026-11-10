package c2.model;

import java.awt.Color;

/** Ground type per square, and the numbers the rest of the system uses. Colors: deep, satellite-like. */
public enum GroundCover {
    //            walkCost sensorFactor pull   color
    OPEN(        1.0,     1.0,         1.0,   new Color(92, 104, 60)),
    LIGHT_FOREST(1.5,     0.7,         0.9,   new Color(50, 76, 42)),
    HEAVY_FOREST(2.5,     0.35,        0.8,   new Color(28, 52, 32)),
    WATER(       99,      1.0,         0.0,   new Color(22, 50, 88)),
    TRAIL(       0.7,     1.0,         1.6,   new Color(138, 116, 82)),
    ROCK(        2.0,     0.9,         0.6,   new Color(104, 100, 94)),
    MOUNTAIN(    3.0,     0.8,         0.4,   new Color(120, 92, 64));      // from the room's brown obstacles

    public final double walkCost, sensorFactor, pull;
    public final Color color;

    GroundCover(double walkCost, double sensorFactor, double pull, Color color) {
        this.walkCost = walkCost;
        this.sensorFactor = sensorFactor;
        this.pull = pull;
        this.color = color;
    }

    public boolean blocksWalking() { return walkCost >= 99; }
}
