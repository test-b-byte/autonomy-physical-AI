package c2.model;

import java.util.List;

/**
 * The victim device's answers (rescue_app). Values in question order:
 * bleeding, breathing, head, cold, walk, arms, safe_to_move. 0 SEVERE, 1 BAD, 2 OK, 3 FINE, null skipped.
 */
public record MedicalReport(List<Integer> values, List<String> needsAttention, String appVersion) {
    private static final int SEVERE = 0, BAD = 1, OK = 2;

    /** Urgent = SEVERE on bleeding, breathing, head, or cold. */
    public boolean isUrgent() {
        for (int question = 0; question < 4 && question < values.size(); question++) {
            Integer value = values.get(question);
            if (value != null && value == SEVERE) return true;
        }
        return false;
    }

    /** Escort = can walk (OK/FINE) and safe to move isn't SEVERE/BAD. */
    public boolean canEscort() {
        if (values.size() < 7 || values.get(4) == null || values.get(6) == null) return false;
        return values.get(4) >= OK && values.get(6) > BAD;
    }
}
