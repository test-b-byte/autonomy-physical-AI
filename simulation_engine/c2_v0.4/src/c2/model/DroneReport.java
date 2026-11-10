package c2.model;

import java.time.Instant;
import java.util.List;

/** What a drone brings home. sighting and medical are null when there was no contact. */
public record DroneReport(String sortieId, Instant returnedAt, List<GridPos> sweptCells,
                          GridPos sighting, MedicalReport medical, List<GridPos> hazardsSeen,
                          List<GridPos> hostilesSeen) { }
