package c2.model;

import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The real test floor, converted to board squares (see RoomMapLoader):
 *   mountains   brown obstacle squares -> extra elevation in meters
 *   shifts      grey obstacle squares  -> a change of ground cover
 *   cups        red = casualty, blue = fire / enemy
 *   staging     where the robot started = the launch point
 */
public record RoomFeatures(Map<GridPos, Double> mountains, Set<GridPos> shifts, List<RoomCup> cups, GridPos staging) {
    public GridPos casualty() {
        return cups.stream().filter(cup -> cup.colour().equals("red")).map(RoomCup::pos).findFirst().orElse(null);
    }
}
