package c2.model;

import java.time.Instant;

/** Read-only summary of one sortie, for the SITREP panel. */
public record SortieView(String sortieId, String droneLabel, Instant launched, Instant due, String status) { }
