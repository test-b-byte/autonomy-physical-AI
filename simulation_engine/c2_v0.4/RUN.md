# Running the C2 operations picture (v0.4)

Requires a Java JDK 17 or newer. No external libraries.

```
cd c2-picture
./run.sh            # demo: simulated drones; reads ./map.txt (the robot's test-floor map) if present
./run.sh --no-sim   # real reports only: drop drone report JSON files into ./inbox
./run.sh --room=/path/to/map.txt
```

## Demo flow (one run, about 1 to 1.5 minutes at x60)

1. Two UAVs launch from STAGING, cross PL ALPHA into the denied area, and search.
2. A UAV finds the casualty (the robot's red cup) and **loiters**. The heat map collapses onto the find.
3. Press **E** (escort), **U** (urgent) or **S** (severe beacon). Or press one earlier to arm it. No key: random pick after ~8 s.
4. The mode plays out with the rescue team; when the team reaches the casualty: MISSION COMPLETE, then a new run.

## Keys

E escort · U urgent · S severe · SPACE pause · +/- sim speed · H halt · R resume · P replan · arrows pan · Z/X zoom

## Files

| File | What |
|---|---|
| `map.txt` | Ground robot's test-floor map (JSON): obstacles, cups, path. Built into the terrain at startup |
| `inbox/*.json` | Drone reports; moved to `inbox/processed/` once read |
| `out/mission_order_*.json`, `out/travel_path.json`, `out/map_state.json` | Mission orders, planned route, victim-device map |
