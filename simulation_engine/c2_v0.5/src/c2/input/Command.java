package c2.input;

/** One commander action. dRow/dCol only used by PAN. */
public record Command(CommandType type, int dRow, int dCol) {
    public static Command of(CommandType type) { return new Command(type, 0, 0); }
}
