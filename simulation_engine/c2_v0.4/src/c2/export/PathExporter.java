package c2.export;

import c2.model.GeoFrame;
import c2.model.TravelPath;
import c2.model.Waypoint;

import java.nio.file.Path;
import java.util.StringJoiner;

/** Adapter: TravelPath -> waypoint list JSON for the drone layer (rows/cols and meters east/north). */
public class PathExporter {
    private final Path outFolder;
    private final GeoFrame frame;

    public PathExporter(Path outFolder, GeoFrame frame) {
        this.outFolder = outFolder;
        this.frame = frame;
    }

    public void export(TravelPath path) {
        JsonOut.write(outFolder.resolve("travel_path.json"), toJson(path, frame));
    }

    static String toJson(TravelPath path, GeoFrame frame) {
        StringJoiner points = new StringJoiner(",\n    ", "[\n    ", "\n  ]");
        for (Waypoint waypoint : path.waypoints()) {
            points.add(String.format("{\"row\": %d, \"col\": %d, \"east_m\": %.0f, \"north_m\": %.0f, \"eta\": \"%s\"}",
                    waypoint.pos().row(), waypoint.pos().col(),
                    frame.eastMeters(waypoint.pos()), frame.northMeters(waypoint.pos()), waypoint.eta()));
        }
        return "{\n  \"path_id\": \"" + path.id() + "\",\n  \"knowledge\": \"" + path.knowledge()
                + "\",\n  \"waypoints\": " + points + "\n}\n";
    }
}
