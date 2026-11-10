package c2.input;

import java.awt.event.KeyAdapter;
import java.awt.event.KeyEvent;
import java.util.List;

/**
 * Adapter: Swing keyboard events -> Commands. Keeps Swing out of the model
 * (same role as AirCom's PlayerInput).
 *   SPACE pause   +/- sim speed   H halt   R resume   P replan
 *   E escort   U urgent   S severe (beacon): pick the mode at contact, or arm it for the next contact
 *   arrows pan    Z zoom in       X zoom out
 */
public class SwingInputAdapter extends KeyAdapter {
    private final List<CommandSink> sinks;

    public SwingInputAdapter(List<CommandSink> sinks) { this.sinks = sinks; }

    @Override
    public void keyPressed(KeyEvent event) {
        Command command = switch (event.getKeyCode()) {
            case KeyEvent.VK_SPACE -> Command.of(CommandType.PAUSE_TOGGLE);
            case KeyEvent.VK_EQUALS, KeyEvent.VK_PLUS, KeyEvent.VK_ADD -> Command.of(CommandType.SPEED_UP);
            case KeyEvent.VK_MINUS, KeyEvent.VK_SUBTRACT -> Command.of(CommandType.SLOW_DOWN);
            case KeyEvent.VK_H -> Command.of(CommandType.HALT);
            case KeyEvent.VK_R -> Command.of(CommandType.RESUME);
            case KeyEvent.VK_P -> Command.of(CommandType.REPLAN);
            case KeyEvent.VK_E -> Command.of(CommandType.ARM_ESCORT);
            case KeyEvent.VK_U -> Command.of(CommandType.ARM_URGENT);
            case KeyEvent.VK_S -> Command.of(CommandType.ARM_SEVERE);
            case KeyEvent.VK_Z -> Command.of(CommandType.ZOOM_IN);
            case KeyEvent.VK_X -> Command.of(CommandType.ZOOM_OUT);
            case KeyEvent.VK_UP -> new Command(CommandType.PAN, -1, -1);
            case KeyEvent.VK_DOWN -> new Command(CommandType.PAN, 1, 1);
            case KeyEvent.VK_LEFT -> new Command(CommandType.PAN, 1, -1);
            case KeyEvent.VK_RIGHT -> new Command(CommandType.PAN, -1, 1);
            default -> null;
        };
        if (command != null) {
            for (CommandSink sink : sinks) sink.submit(command);
        }
    }
}
