# Installing GHOST on the robot

After installing, follow the staged bench test in [bench/BENCH.md](bench/BENCH.md).

What runs where:

```
 JETSON (Orin, Isaac ROS environment)              RASPBERRY PI 5 (+ Hailo AI HAT)
 ┌───────────────────────────────────────┐        ┌─────────────────────────────────────┐
 │ ghost-core            :9001 ◀─────────┼── LAN ─┤ sensors/fusion.py --hardware        │
 │ robot.launch.py: Gemini 330 camera,   │        │   thermal · IR · mic · IMU · vision │
 │   cuVSLAM odometry, Nav2              │        │   vision = YOLOv8 on Hailo          │
 │ base_driver.py ── USB ── motor board  │  :5555 │     ◀── camera frames ──────────────┤
 │ frame_server.py ─────────────────────▶┼────────┼▶                                    │
 │ ghost_bridge.py: core ⇄ Nav2          │        │ pi/operator_link.py ── Meshtastic   │
 └───────────────────────────────────────┘        └─────────────────────────────────────┘
```

GHOST decides **where to search** (core). Nav2 decides **how to get there**
without hitting anything. The base driver turns velocity into wheel speeds.

---

## 0. Before you start

- [ ] Jetson with the Isaac ROS environment (container or native) that already
      has `orbbec_camera`, `isaac_ros_cuvslam` and Nav2 built and working.
- [ ] Orbbec Gemini 330-series camera on the Jetson (USB 3).
- [ ] Motor board on the Jetson over USB (`/dev/ttyACM0`), battery charged,
      motor switch reachable.
- [ ] Pi 5 with the Hailo AI HAT, sensors wired, same network as the Jetson.
- [ ] A Meshtastic node on the Pi (USB) and one with the operator.
- [ ] **A way to kill the motors** (switch or battery disconnect) within
      reach the whole time. Software stops are not enough.

Get the code on both machines:

```bash
git clone -b ghost-upgrade https://github.com/CodeMetalForge-Hackathon/Team-20.git ~/ghost
```

---

## 1. Jetson

### 1.1 Install

Inside the Isaac ROS environment. If you use the container, start it with the
motor board and camera passed through (`--device /dev/ttyACM0`, plus USB access
for the camera).

```bash
cd ~/ghost
bash jetson/setup.sh          # builds ghost-core, pip deps, checks every ROS package
```

Fix anything it lists as `MISSING`, then re-run it until it's clean. If
`/dev/ttyACM0` isn't writable: `sudo usermod -aG dialout $USER` and log in
again.

### 1.2 Wheels, with the robot ON BLOCKS (wheels off the ground)

1. **Measure the chassis** and put the numbers in `jetson/base_driver.py`:
   `WHEEL_RADIUS_M`, `HALF_WHEELBASE_M` (half the front-to-rear axle
   distance) and `HALF_TRACK_M` (half the left-to-right wheel distance).
   You can pass them as flags instead.
2. **Find the motor wiring.** Each motor spins in turn and you say which wheel
   moved and which way:
   ```bash
   python3 jetson/base_driver.py --identify
   ```
   It prints a line like `--ids 1,2,3,4 --signs=1,1,-1,-1`. Keep it, including
   the `=`.
3. **Check it.** Every wheel should turn "forward":
   ```bash
   python3 jetson/base_driver.py --spin-test --ids 1,2,3,4 --signs=1,1,-1,-1
   ```
4. **Drive by keyboard** (two terminals):
   ```bash
   python3 jetson/base_driver.py --hardware --ids 1,2,3,4 --signs=1,1,-1,-1   # add --unstamped on Humble
   python3 jetson/teleop.py                                                    # w/s a/d q/e, space stop
   ```
   Pass: `w` drives forward, `a` strafes **left**, `q` turns **counter-clockwise**.
   Letting go of the key stops the robot within half a second.

### 1.3 Camera and odometry (robot on the floor)

```bash
NO_NAV2=1 DRY_RUN=1 bash jetson/start.sh
# second terminal:
ros2 topic hz /visual_slam/tracking/odometry          # ~30 Hz
ros2 topic echo --once /visual_slam/tracking/odometry
```

Push the robot 1 m forward by hand. Pass: `pose.position.x` grows by about
1.0 m (within ±0.1), and `y` stays near 0.

Measure where the camera sits relative to the robot centre and pass it with
`CAM_X` (forward) and `CAM_Z` (up), in metres.

### 1.4 First driven mission

```bash
DRIVE_ARGS="--ids 1,2,3,4 --signs=1,1,-1,-1" \
CELL_M=0.5 ORIGIN=0.5,0.5 CAM_X=0.10 CAM_Z=0.12 \
bash jetson/start.sh
```

| Variable | Meaning |
|---|---|
| `CELL_M` | grid cell size. **Must equal** the Pi's `--cell-m` |
| `ORIGIN` | where the launch point sits on the grid (m). Launch with the corner of the search area behind-right of the robot, facing +x along the grid |
| `DRY_RUN=1` | wheels print instead of move |
| `NO_NAV2=1` | camera and odometry only |
| `NO_BRIDGE=1` | Nav2 up, but GHOST doesn't drive (for manual goals) |
| `COLOR=1` | stream colour for the detector (more USB bandwidth) |

Logs are in `jetson/logs/`: `core`, `robot`, `base`, `frames`, `bridge`.
Nav2 takes about 15 s to come up; the bridge logs `Nav2 ready` once it has.

---

## 2. Raspberry Pi

### 2.1 Hailo AI HAT (one-off, three reboots)

```bash
cd ~/ghost
bash pi/hailo_setup.sh firmware     # reboots
bash pi/hailo_setup.sh install      # reboots
bash pi/hailo_setup.sh verify       # want: device found, hailo_platform OK, throttled=0x0
```

### 2.2 Install

```bash
GHOST_HOST=<jetson-ip> bash pi/setup.sh
```

This installs the sensor drivers, `onnxruntime`, `pyzmq` and Meshtastic, then
runs `pi/get_models.sh`. That links the Hailo YOLOv8 model and exports
`models/yolov8n.onnx` as the CPU fallback. Enable I2C in `raspi-config` if
setup warns about it.

### 2.3 Run

```bash
cd ~/ghost/sensors
GHOST_FRAMES=tcp://<jetson-ip>:5555 python3 fusion.py --hardware --host <jetson-ip> \
    --grid 10x10 --cell-m 0.5 --lkp 2.5,2.5 --sigma 1.5 --specs indoor_specs.json
```

The first lines say which sensors are live. A sensor without hardware is
**excluded**, never simulated, and the log tells you so. Vision should log
`[Vision] hailo on tcp://…`.

This sets up the search but **doesn't start it**. The robot waits for the
operator to press GO.

- **Grid:** 10×10 at 0.5 m covers a 5 m room. `--lkp` is the centre of where
  to look, `--sigma` how spread out.
- **Sensor ranges:** `indoor_specs.json` has short ranges suited to a room.
  Outdoors, drop `--specs` to use the defaults.

Operator radio, in a second terminal:

```bash
python3 ~/ghost/pi/operator_link.py --host <jetson-ip> --allow '!a1b2c3d4'
```

`--allow` takes the operator's Meshtastic node ID (shown in the Meshtastic
app). Only that node can command the drone. Contact alerts and a status line
every 45 s come back the same way.

### 2.4 Operator controls

Two ways to run the robot. Both do exactly the same thing:

| | Dashboard (laptop on the same Wi-Fi) | Meshtastic text |
|---|---|---|
| Start the search | **GO** | `go` |
| Stop | **HALT** (or Space) | `halt` / `stop` |
| Continue | **RESUME** | `go` |
| Back to the launch point | **RTB** | `home` |
| New search, same grid | **NEW SEARCH** (click twice) | `reset`, then `go` |
| State | badge, top right | `status` |

Open the dashboard at:
`dashboard/index.html?ws=ws://<jetson-ip>:9001/ws&cell=0.5`
(use the same `cell` value as `--cell-m`).

---

## 3. Checks before a demo

- [ ] `jetson/logs/base.log` says `HARDWARE`, and the wiring flags are right.
- [ ] `bridge.log` has `Nav2 ready` and `core connected`.
- [ ] `fusion.py` shows the sensors you expect as live.
- [ ] Stand 1 m in front of the camera: vision fires (`[Vision]` / core sweeps).
- [ ] Texting `halt` stops the robot. Then test the physical kill.
- [ ] Battery: `ros2 topic echo /base/battery_mv` (3S pack: charge below ~10 800 mV).

## 4. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `base_driver` dry-runs only | `--hardware` missing, or `DRY_RUN` is set |
| Wheels fight each other, robot spins on `w` | wrong `--ids`/`--signs`: run `--identify` again |
| Robot strafes the wrong way | the rollers are an O-layout, not X: negate `vy` in `mecanum_ik` |
| Nothing moves, `/cmd_vel` has data | message type mismatch: on Humble use `--unstamped` |
| Wheels stop every 0.4 s | commands are arriving too slowly; check the `controller_frequency` that Nav2 is actually using |
| `bridge.log`: `Nav2 not ready` | `robot.log`: Nav2 nodes failed to configure (missing package or param) |
| Robot goes to the wrong cell | `CELL_M` ≠ the Pi's `--cell-m`, or `ORIGIN` is wrong |
| Odometry jumps or drifts | IR projector must be off (it is in `robot.launch.py`); textured surroundings help |
| Vision always stub | no model: `bash pi/get_models.sh`; no frames: `GHOST_FRAMES` / `frame_server` log |
| Hailo `throttled=0x5` | under-voltage: use the official 27 W supply |
