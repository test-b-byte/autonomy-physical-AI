package c2.model;

/** A cup the ground robot detected, already converted to a board square. */
public record RoomCup(int id, String colour, GridPos pos) { }
