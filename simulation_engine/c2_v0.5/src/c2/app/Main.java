package c2.app;

import java.nio.file.Path;

/**
 * Start the C2 operations picture.
 *   java -cp out c2.app.Main                      demo with simulated drone
 *   java -cp out c2.app.Main --no-sim             real drone reports only (drop JSON in ./inbox)
 *   options: --inbox=PATH  --out=PATH  --assets=PATH  --room=PATH (robot map, default ./map.txt)
 */
public class Main {
    public static void main(String[] args) {
        Path inbox = Path.of("inbox"), out = Path.of("out"), assets = Path.of("assets"), room = Path.of("map.txt");
        boolean simulate = true;
        for (String arg : args) {
            if (arg.equals("--no-sim")) simulate = false;
            else if (arg.startsWith("--inbox=")) inbox = Path.of(arg.substring(8));
            else if (arg.startsWith("--out=")) out = Path.of(arg.substring(6));
            else if (arg.startsWith("--assets=")) assets = Path.of(arg.substring(9));
            else if (arg.startsWith("--room=")) room = Path.of(arg.substring(7));
        }
        new C2App(inbox, out, assets, room, simulate).startWithWindow();
    }
}
