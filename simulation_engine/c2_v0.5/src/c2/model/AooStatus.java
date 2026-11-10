package c2.model;

/** Read-only summary of the actions-on-objective loop, for the dashboard and board banner. */
public record AooStatus(AooState state, String mode, String chosenBy, String contactDrone,
                        double loiterFraction, String teamEta, String morse, int morseLetter,
                        String armedMode, String banner) {
    public static AooStatus searching(String armedMode) {
        return new AooStatus(AooState.SEARCHING, null, null, null, 0, null, null, -1, armedMode, null);
    }
}
