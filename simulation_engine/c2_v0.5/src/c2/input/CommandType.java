package c2.input;

public enum CommandType {
    PAUSE_TOGGLE, SPEED_UP, SLOW_DOWN,            // clock
    HALT, RESUME, REPLAN,                         // mission
    ARM_ESCORT, ARM_URGENT, ARM_SEVERE,           // actions on objective: E, U, S
    PAN, ZOOM_IN, ZOOM_OUT, TOGGLE_LABELS         // view
}
