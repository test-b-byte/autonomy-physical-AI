package c2.export;

import c2.model.GeoFrame;
import c2.model.TravelPath;

import java.nio.file.Path;
import java.time.Instant;

/** Adapter: mission order -> JSON loaded onto the drone at launch. */
public class MissionOrderWriter {
    private final Path outFolder;
    private final GeoFrame frame;

    public MissionOrderWriter(Path outFolder, GeoFrame frame) {
        this.outFolder = outFolder;
        this.frame = frame;
    }

    public void write(String sortieId, TravelPath route, Instant returnDeadline, String intent) {
        String json = "{\n"
                + "  \"sortie_id\": \"" + sortieId + "\",\n"
                + "  \"commanders_intent\": \"" + intent.replace("\"", "'") + "\",\n"
                + "  \"return_deadline\": \"" + returnDeadline + "\",\n"
                + "  \"rules\": {\"urgent_if_severe\": [\"bleeding\", \"breathing\", \"head\", \"cold\"],"
                + " \"escort_if\": \"walk>=OK and safe_to_move>BAD\"},\n"
                + "  \"route\": " + PathExporter.toJson(route, frame).trim() + "\n"
                + "}\n";
        JsonOut.write(outFolder.resolve("mission_order_" + sortieId + ".json"), json);
    }
}
