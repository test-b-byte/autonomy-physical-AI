package c2.ingest;

import c2.model.GeoFrame;
import c2.model.GridPos;
import c2.model.TerrainGrid;
import c2.model.TravelPath;
import c2.search.PathGeometry;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Random;
import java.util.Set;
import java.util.StringJoiner;

/**
 * Demo stand-in for the real drone. Knows the hidden true subject position. When a sortie
 * lands, it writes a drone report JSON into the inbox, so the demo exercises the same file
 * path a real drone report would use.
 */
public class SimulatedDroneFeed {
    private static final double SIGHTING_CHANCE_IN_RANGE = 0.75;
    private static final int SENSOR_RANGE_CELLS = 2;
    private static final int HOSTILE_SPOT_CELLS = 14;      // hostiles are spotted from stand-off range (~700 m)

    private final Path inbox;
    private final GeoFrame frame;
    private final TerrainGrid terrain;
    private final Random random;
    private GridPos trueSubject;
    private final GridPos startingSubject;

    public SimulatedDroneFeed(Path inbox, GeoFrame frame, TerrainGrid terrain, GridPos trueSubject, long seed) {
        this.inbox = inbox;
        this.frame = frame;
        this.terrain = terrain;
        this.trueSubject = trueSubject;
        this.startingSubject = trueSubject;
        this.random = new Random(seed);
    }

    public GridPos trueSubject() { return trueSubject; }

    /** Next run of the loop: the casualty is back where the scenario put them. */
    public void reset() { trueSubject = startingSubject; }

    /** The hidden subject wanders slowly; called each tick with elapsed minutes. */
    public void wander(double minutes) {
        if (random.nextDouble() < minutes * 0.05) {
            GridPos step = frame.clamp(new GridPos(trueSubject.row() + random.nextInt(3) - 1,
                    trueSubject.col() + random.nextInt(3) - 1));
            if (!terrain.at(step).cover().blocksWalking()) trueSubject = step;
        }
    }

    /** Sortie landed: write its report into the inbox. */
    public void sortieLanded(String sortieId, TravelPath flown, Instant landedAt, List<GridPos> hostiles) {
        Set<GridPos> swept = PathGeometry.sweptCells(flown, frame, 1);
        GridPos sighting = null;
        for (GridPos cell : List.<GridPos>of()) {                 // contact is detected live by the board (v0.4)
            if (cell.distanceTo(trueSubject) <= SENSOR_RANGE_CELLS
                    && random.nextDouble() < SIGHTING_CHANCE_IN_RANGE * terrain.at(cell).cover().sensorFactor) {
                sighting = trueSubject;
                break;
            }
        }
        StringJoiner hostilesJson = new StringJoiner(",", "[", "]");
        for (GridPos hostile : hostiles) {
            boolean passedNear = swept.stream().anyMatch(cell -> cell.distanceTo(hostile) <= HOSTILE_SPOT_CELLS);
            if (passedNear && random.nextDouble() < 0.8) hostilesJson.add("[" + hostile.row() + "," + hostile.col() + "]");
        }
        StringJoiner sweptJson = new StringJoiner(",", "[", "]");
        for (GridPos cell : swept) sweptJson.add("[" + cell.row() + "," + cell.col() + "]");

        String json = "{\n"
                + "  \"sortie_id\": \"" + sortieId + "\",\n"
                + "  \"returned_at\": \"" + landedAt + "\",\n"
                + "  \"swept_cells\": " + sweptJson + ",\n"
                + "  \"sighting\": " + (sighting == null ? "null" : "[" + sighting.row() + "," + sighting.col() + "]") + ",\n"
                + "  \"hazards_seen\": [],\n"
                + "  \"hostiles_seen\": " + hostilesJson + ",\n"
                + "  \"medical\": " + (sighting == null ? "null" : sampleMedical()) + "\n"
                + "}\n";
        try {
            Files.createDirectories(inbox);
            Path temp = inbox.resolve(sortieId + ".json.tmp");
            Files.writeString(temp, json);
            Files.move(temp, inbox.resolve(sortieId + ".json"));   // appear all at once, never half-written
        } catch (IOException problem) {
            System.err.println("Simulated report write failed: " + problem.getMessage());
        }
    }

    private String sampleMedical() {
        return "{\"app_version\": \"v0.5\", \"values\": [0, 1, 2, 1, 2, 3, 2], "
                + "\"needs_attention\": [\"Bleeding: SEVERE\", \"Breathing injury: BAD\", \"Cold / freezing: BAD\"]}";
    }
}
