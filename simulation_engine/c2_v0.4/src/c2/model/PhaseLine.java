package c2.model;

/**
 * A straight control line between two squares. One side is friendly / controlled (comms available),
 * the other is denied. Which side is friendly is decided by a reference square on that side (the TOC).
 */
public record PhaseLine(String label, GridPos from, GridPos to, GridPos friendlyReference) {

    /** Positive on one side of the line, negative on the other (2D cross product). */
    private double sideOf(GridPos pos) {
        return (to.col() - from.col()) * (pos.row() - from.row()) - (to.row() - from.row()) * (pos.col() - from.col());
    }

    public boolean isFriendly(GridPos pos) {
        return Math.signum(sideOf(pos)) == Math.signum(sideOf(friendlyReference));
    }
}
