package c2.export;

import c2.model.GeoFrame;
import c2.model.MapObject;
import c2.model.ObjectKind;
import c2.model.OperationsPicture;

import java.nio.file.Path;
import java.util.StringJoiner;

/**
 * Adapter: picture -> map_state.json in the victim device's format (rescue_app v0.5):
 * meters east/north, centered on the subject's current estimate.
 */
public class MapStateWriter {
    private final Path outFolder;

    public MapStateWriter(Path outFolder) { this.outFolder = outFolder; }

    public void write(OperationsPicture picture, String subjectId) {
        GeoFrame frame = picture.frame();
        MapObject subject = picture.object(subjectId);
        if (subject == null) return;
        double originEast = frame.eastMeters(subject.pos()), originNorth = frame.northMeters(subject.pos());

        StringJoiner hazards = new StringJoiner(", ", "[", "]");
        StringJoiner hostiles = new StringJoiner(", ", "[", "]");
        String team = null, drone = null;
        for (MapObject object : picture.objects()) {
            String point = String.format("{\"x\": %.0f, \"y\": %.0f, \"label\": \"%s\"}",
                    frame.eastMeters(object.pos()) - originEast, frame.northMeters(object.pos()) - originNorth, object.label());
            if (object.kind() == ObjectKind.HAZARD) hazards.add(point);
            else if (object.kind() == ObjectKind.HOSTILE) hostiles.add(point);
            else if (object.kind() == ObjectKind.TOC) team = point;
            else if (object.kind() == ObjectKind.DRONE && drone == null) drone = point;
        }
        String json = "{\n"
                + "  \"you\": {\"x\": 0, \"y\": 0, \"uncertainty_m\": "
                + Math.round(subject.uncertaintyCells() * frame.metersPerCell()) + "},\n"
                + (drone != null ? "  \"drone\": " + drone + ",\n" : "")
                + (team != null ? "  \"team\": " + team + ",\n" : "")
                + "  \"hazards\": " + hazards + ",\n"
                + "  \"hostiles\": " + hostiles + ",\n"
                + "  \"updated\": " + picture.now().getEpochSecond() + "\n"
                + "}\n";
        JsonOut.write(outFolder.resolve("map_state.json"), json);
    }
}
