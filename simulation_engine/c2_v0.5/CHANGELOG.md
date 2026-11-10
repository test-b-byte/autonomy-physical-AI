# C2 operations picture: iteration log

## v0.5
- **Cleaner, less cartoony board** (feedback on v0.4):
  - Test floor now at **1:200** (one 50 m square = 25 cm of floor): the 7.5 x 5.5 m area is ~30 x 22 squares inside the
    search area instead of taking it over.
  - Only the robot's real obstacles are used: clusters longer than 2 m (the room's walls / window line) and specks under
    8 cells are dropped.
  - Obstacles become **gentle hills** (smooth bell-shaped rise, ~75 m, ground cover unchanged) instead of brown towers.
    No grey terrain shift.
  - Blue-cup **fire / enemy symbols removed**. One central hazard (CLIFF) plus FAST WATER at the river.
  - **TOC moved further back**; staging and PL ALPHA moved so the line crosses open ground near staging.
  - **Labels decluttered:** FRIENDLY / DENIED text removed; units parked at staging share one tag
    ("STAGING · 2 UAV · TEAM"); hazard / hostile text only at the two closest zoom levels; **L** toggles all labels.
- Search tuned so it's visible: contact range 3 squares, guaranteed contact by wave 2 (about 20 s of search at x60).

## v0.4
- **Real test floor built into the terrain.** At startup the board reads the ground robot's `map.txt` and places the
  7.5 m x 5.5 m test area at **1:400** inside the drone operating region (one 50 m square = 12.5 cm of floor).
  The robot's start becomes the **STAGING** point, offset forward of the TOC.
  - Compact obstacles (brown in the robot's map) -> **mountains**, elevation from their measured height, snow on the highest.
  - Sprawling obstacles (grey) -> **terrain shift** to rock.
  - **Red cup** -> where the casualty really is. **Blue cups** -> alternating **FOREST FIRE** and **ENEMY**.
  - Drones and walkers **route around** the obstacles (A* path finding).
  - No `map.txt` -> generated terrain only, as before.
- **Phase line PL ALPHA:** friendly / controlled side vs denied side. Drones upload their report wirelessly as soon as
  they cross back to the friendly side.
- **Actions on objective, live:** a searching drone that comes within range of the casualty **loiters** over it
  (heat map collapses onto the find). Pick the mode with **E** (escort), **U** (urgent), **S** (severe), or arm a key
  ahead of time; with no input the mode is picked at random when the loiter window ends.
  - **ESCORT:** casualty walks toward staging with the drone leading; the rescue team walks out to meet them.
  - **URGENT:** drone flies home fast; on crossing the phase line it uploads, and the rescue team is dispatched.
  - **SEVERE:** drone moves to an offset IR beacon point (200 m toward staging) signalling "SOS <dir> 200"; once the
    signal is received, the team homes on the beacon, then the casualty.
- **Rescue team** unit (friendly symbol with a cross) staged at the launch point.
- **End state:** when the team reaches the casualty, MISSION COMPLETE banner, then the whole loop resets and runs again.
- **Control stops:** one contact at a time, no new waves during an objective, guaranteed contact by wave 4.
- **Dashboard:** Actions-on-Objective card (state, loiter timer, mode and who chose it, team ETA, beacon Morse) replaces
  the tracked-object list.

## v0.3
- 2 UAVs per wave instead of 3, so routes and drones are easier to follow.

## v0.2
- **3 UAVs** fly each wave in parallel. The planner spreads them out: each drone skips targets the earlier drones already took. Launches are staggered one minute apart.
- **Larger enemy presence:** an ENEMY AO zone (pulsing red area), six hostiles (command post, observation post, squad, vehicle, possible sniper, a patrol moving along a predicted loop). The planner routes around enemy areas and keeps stand-off from known hostiles.
- **Hostiles confirmed by reports:** a drone that passes within stand-off range reports hostiles it saw; the nearest predicted hostile snaps HOLO -> SOLID.
- **Terrain:** deeper, satellite-like colors, hillshading, per-square color variation, trees on forest (conifers on heavy forest, broadleaf on light), speckle on rock, ripples on water, grass tufts. Seam fix removes the dark striping.
- **Heat map:** stronger color ramp (amber -> red -> magenta -> white at the peak), a clean contour at 50% of the peak, and a pulsing ring on the most likely square.
- **4th zoom level** (40 px tiles).
- **Dashboard redesign:** gradient glass cards, large clock, phase card, stat tiles (belief peak, entropy, sorties flown, contacts), per-UAV sortie cards with progress bars and status chips, two-column tracked-object list, alert cards with color bars, modern fonts (Helvetica Neue / SF Mono when available).
- Sorties that stay overdue 15 minutes are written off as LOST so the mission can continue.

## v0.1
- First end-to-end build: clock, digital twin, observer bridge to Swing, State-pattern mission loop, drone report inbox adapter, simulated drone, mission order / travel path / map state writers, local search engine, isometric board with HOLO/SOLID styles.
