package c2.model;

import java.time.Instant;

public record Alert(Instant time, AlertLevel level, String text) { }
