package c2.model;

public enum ObjectKind {
    SUBJECT(true), DRONE(true), TOC(false), HAZARD(false), HOSTILE(true), ANCHOR(false), TEAM(true);

    /** Moving things fade from SOLID back to HOLO as their confirmation ages. */
    public final boolean moves;
    ObjectKind(boolean moves) { this.moves = moves; }
}
