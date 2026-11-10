# GHOST basic bench test

Goal: prove each link in the chain on the real robot, one at a time, in a small
indoor space. Then run one short autonomous search. Install first: [INSTALL.md](../INSTALL.md).

**Roles:**
- **Driver**: hand on the physical motor kill for the whole session.
- **Operator**: runs the laptop and terminals.
- **Subject**: a person who'll be "found" in stage G.

**Space:** a clear area of about 4×4 m with furniture at the edges (cuVSLAM
needs texture), floor not too shiny, no stairs or drops.

Record each stage's result in the sheet at the bottom. Don't move on from a FAIL.

---

## Stop methods, rehearsed before anything moves

| How | Effect |
|---|---|
| **Physical kill** (switch or battery) | always works: use it first if in doubt |
| **HALT** on the dashboard (or Space) | core stops planning, bridge cancels the Nav2 goal, wheels stop within ~0.5 s |
| text `halt` over Meshtastic | same as HALT, after radio latency (a few seconds) |
| Release the teleop key | wheels stop in ≤ 0.5 s (teleop deadman + driver 0.4 s watchdog) |
| `bash bench/stop.sh` (Jetson) | bridge cancels its Nav2 goal, zero velocity sent, stack shuts down |
| Ctrl-C on `jetson/start.sh` | everything stops; the driver sends zero on exit |

After a HALT: **RESUME** continues the search, **RTB** drives back to the
launch point, **NEW SEARCH** resets the belief and waits for GO again.

---

## A. Power and core (5 min, robot on blocks)

Jetson:
```bash
DRY_RUN=1 NO_NAV2=1 bash jetson/start.sh
curl localhost:9001/health                 # → GHOST online
```
**Pass:** health answers, and `jetson/logs/core.log` shows the core listening on `0.0.0.0:9001`.

## B. Wheels (15 min, robot ON BLOCKS)

```bash
python3 jetson/base_driver.py --identify          # once; note the --ids / --signs it prints
python3 jetson/base_driver.py --spin-test --ids … --signs=…
python3 jetson/base_driver.py --hardware --ids … --signs=…     # terminal 1
python3 jetson/teleop.py                                        # terminal 2
```
**Pass:**
- Spin-test: every wheel turns "forward".
- Teleop: `w` gives all wheels forward; `a` strafes left; `q` turns counter-clockwise.
- Releasing the key stops the wheels within 0.5 s.
- Ctrl-C on the driver stops the wheels.

Then on the floor, at `--speed 0.15`: drive a 1 m square with `w` / `a`.
**Pass:** it tracks straight and doesn't pull hard to one side.

## C. Camera and odometry (10 min, robot on the floor)

```bash
NO_NAV2=1 DRY_RUN=1 CAM_X=<m> CAM_Z=<m> bash jetson/start.sh
bash bench/preflight.sh              # camera / odometry / TF lines should PASS
ros2 topic echo /visual_slam/tracking/odometry --field pose.pose.position
```
Push the robot by hand 1 m forward, then 1 m left, then back to the start.
**Pass:**
- Forward: x ≈ +1.0 (±0.1).
- Left: y ≈ +1.0 (±0.1).
- Back at the start: within 0.15 m of 0,0.
- Odometry ≥ 15 Hz throughout.

## D. Pi sensors (20 min)

Pi, with the Jetson stack from C still running:
```bash
GHOST_FRAMES=tcp://<jetson-ip>:5555 python3 bench/sensor_check.py
```
**Pass:** the sensors you expect show **LIVE**, and vision logs `hailo` (or `onnx`).

Distance test: the subject stands in front of the robot at each distance for
20 s:
```bash
GHOST_FRAMES=tcp://<jetson-ip>:5555 python3 bench/sensor_check.py --label 0.5m --csv dist.csv
# …repeat with --label 1m, 2m, 3m, and "empty" with nobody there
```
**Pass:** with nobody there, every sensor's hit rate is under 10%. At 1 m,
vision and thermal hit rates are over 60%.

Write down the distance where each sensor's hit rate falls under about 30%.
That's its real range: put it in `sensors/indoor_specs.json` as `max_range_m`.

## E. Nav2 single goal (15 min)

Jetson, with Nav2 and live wheels but no GHOST bridge, so nothing replaces your goal:
```bash
NO_BRIDGE=1 DRIVE_ARGS="--ids … --signs=…" CAM_X=… CAM_Z=… bash jetson/start.sh
bash bench/preflight.sh               # all PASS
bash bench/nav_goal.sh 1.0 0          # 1 m forward
bash bench/nav_goal.sh 1.0 0.5        # strafe-ish
bash bench/nav_goal.sh 0 0            # home
```
**Pass:**
- Each goal ends `SUCCEEDED`, within about 0.15 m of the target.
- No collisions; it slows or replans around a box placed in its path.
- Speed stays ≤ 0.3 m/s.

## F. Failure drills (10 min)

While a `nav_goal.sh` goal is running:
1. Ctrl-C `nav_goal.sh`. The goal is cancelled and the robot stops.
2. Run `bash bench/stop.sh`. The robot stops within 1 s.
3. Physical kill.

**Pass:** all three stop it.

## G. First GHOST search (15 min)

Set out a search grid on the floor: a 10×10 grid of 0.5 m cells (5×5 m), with
the robot 0.5 m in from one corner, facing along the grid's x axis. Put the
subject somewhere in the grid, not right in front of the robot.

Jetson:
```bash
DRIVE_ARGS="--ids … --signs=…" CELL_M=0.5 ORIGIN=0.5,0.5 CAM_X=… CAM_Z=… bash jetson/start.sh
bash bench/preflight.sh               # all PASS
```
Laptop (same network), to watch:
open `dashboard/index.html?ws=ws://<jetson-ip>:9001/ws&cell=0.5`.

Pi. This sets up the search grid and streams sensors; the robot does **not**
move yet. The dashboard shows `READY — PRESS GO`.
```bash
GHOST_FRAMES=tcp://<jetson-ip>:5555 python3 sensors/fusion.py --hardware --host <jetson-ip> \
    --grid 10x10 --cell-m 0.5 --lkp 2.5,2.5 --sigma 1.5 --specs sensors/indoor_specs.json
```
Driver: hand on the kill. Operator: press **GO** on the dashboard, or text `go`.

Mid-search drills: press **HALT**, and the robot stops within about 0.5 s. Press
**RESUME** and it continues. Then text `halt` over the radio, then `go` again.

**Pass:**
- Nothing moves before GO.
- HALT stops it (both from the dashboard and over the radio).
- The robot visits cells, and the dashboard's robot marker matches where it really is (within one cell).
- It stays inside the grid and avoids obstacles.
- It declares CONTACT within about 1 m of the subject, in under 5 minutes.

Record time to contact and the contact error.

---

## Record sheet

| Stage | Pass/Fail | Notes (numbers!) |
|---|---|---|
| A core | | |
| B wheels: ids / signs | | `--ids    --signs=` |
| B 1 m square drift | | ___ cm |
| C odom 1 m fwd / 1 m left / loop error | | ___ / ___ / ___ m |
| D LIVE sensors | | |
| D range at 30 % hit (thermal / vision / IR / mic) | | ___ / ___ / ___ / ___ m |
| D false-hit rate, empty room | | |
| E goal error ×3 | | |
| F stops | | |
| G HALT latency: dashboard / radio | | ___ s / ___ s |
| G time to contact / contact error | | ___ s / ___ m |
| Battery start → end | | ___ → ___ mV |

## Decisions to make after the bench

The numbers above should settle these:

1. ~~Remote stop~~ and ~~who starts the search~~: decided. HALT stops the robot, and the operator's GO starts the search.
2. **Lost link.** If the operator's radio or Wi-Fi drops mid-search, should the robot halt on its own after N seconds?
3. **Operator view.** The current dashboard is read-only over Wi-Fi. Do we need planning (area / POIs / no-go), and over LoRa or Wi-Fi?
4. **Sensor set.** Keep or drop each sensor based on its D-stage range and false-hit numbers.
5. **Speed and grid.** Grid size, cell size and Nav2 speed limits, based on E and G.
