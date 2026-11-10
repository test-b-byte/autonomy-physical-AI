package c2.model;

import java.time.Instant;

public record Waypoint(GridPos pos, Instant eta) { }
