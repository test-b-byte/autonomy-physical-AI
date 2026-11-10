# GHOST — Bayesian SAR Path Planner

GPS-free, infrastructure-free search and rescue for ground drones. GHOST maintains a live probability map of where a subject most likely is, fuses evidence from four sensor modalities, flags terrain hazards in real time, and always routes the robot toward the highest-value unsearched cell.

**No GPS. No cell signal. No infrastructure.**

---

## Quick start

```bash
# 1 — build and run the Rust core (WebSocket on :9001)
cd core && cargo run

# 2 — start the sensor fusion layer (stub demo, no hardware needed)
cd sensors && python3 fusion.py

# 3 — open the live dashboard
open dashboard/index.html
```

The stub demo auto-navigates toward the subject at (20 m, 20 m), fires all four sensors with realistic probability falloff, and declares **CONTACT** when the belief converges.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  dashboard/index.html   (browser, no build step)        │
│  Canvas heatmap · hazard overlay · sensor status        │
└────────────────────────┬────────────────────────────────┘
                         │  WebSocket  ws://localhost:9001/ws
┌────────────────────────▼────────────────────────────────┐
│  sensors/fusion.py      (Python, runs on Pi / laptop)   │
│  IMU · Thermal · Vision · Acoustic · IR                 │
│  Hardware-or-stub on every sensor module                │
└────────────────────────┬────────────────────────────────┘
                         │  WebSocket (same connection)
┌────────────────────────▼────────────────────────────────┐
│  core/  (Rust, single binary — ghost-core)              │
│                                                         │
│  BeliefMap      Bayesian grid, Gaussian prior           │
│  SensorModel    SensorSpec physics, LR fusion           │
│  PathPlanner    info-gain waypoint scoring              │
│  DeadReckoning  IMU integration, altitude tracking      │
│  HazardDetector cliff / ravine / slope / obstacle       │
│  GhostEngine    stateless handler — msg in, snap out    │
│  axum WS server :9001                                   │
└─────────────────────────────────────────────────────────┘
```

See [ADR-001](docs/adr/0001-layered-architecture.md) for why the layers are split this way.

---

## How it works

Every grid cell starts with a Gaussian probability prior centred on the last-known position. As the robot sweeps, each sensor vote multiplies that cell's probability using a Bayesian likelihood ratio:

```
LR+ = Pd(dist) / Pfa          # detection
LR− = (1 − Pd(dist)) / (1 − Pfa)   # no detection
```

Renormalize after every update. When the global peak crosses **P > 0.20** with multi-sensor agreement, GHOST declares **CONTACT** — grid cell, world coordinates, combined confidence.

The path planner scores unswept cells by `P(c) × hazard_weight(c) × sar_boost(c) / (1 + 0.08 × dist)` and routes the robot to the highest-value cell.

---

## Default sensor specs

| Sensor | Range | Peak Pd | Pfa |
|--------|-------|---------|-----|
| Thermal (MLX90640) | 10 m | 0.90 | 0.05 |
| IR / PIR | 3 m | 0.95 | 0.02 |
| Acoustic (VAD 85–255 Hz) | 20 m | 0.75 | 0.08 |
| Vision (YOLOv8-nano) | 15 m | 0.85 | 0.03 |

Specs are runtime-overridable via the `Config` message — no recompile needed:

```json
{
  "type": "config",
  "width": 20, "height": 20, "cell_size_m": 0.5,
  "last_known_x": 5.0, "last_known_y": 5.0,
  "sensor_specs": {
    "thermal": { "max_range_m": 5.0, "peak_pd": 0.93, "pfa": 0.02 }
  }
}
```

---

## Hazard detection

The IMU's vertical accelerometer tracks elevation continuously. The `HazardDetector` classifies:

| Hazard | Trigger | Path-planner weight | SAR note |
|--------|---------|---------------------|----------|
| Cliff/drop | altitude rate < −0.5 m/s | 0.05 (avoid) | |
| Obstacle/wall | altitude rate > +0.5 m/s | 0.10 (avoid) | |
| Steep slope | lateral g > 0.30 g | 0.25 (penalise) | |
| Ravine bottom | descending fast → levelling | 0.80 (passable) | +50% SAR priority |

Hazard cells are rendered with coloured borders on the dashboard and routed around by the path planner.

---

## Running on hardware (Jetson + Pi)

**Full setup and bring-up steps: [INSTALL.md](INSTALL.md).** Short version:

```
Jetson:  bash jetson/setup.sh
         DRIVE_ARGS="--ids … --signs=…" CELL_M=0.5 ORIGIN=0.5,0.5 bash jetson/start.sh
Pi:      bash pi/hailo_setup.sh firmware|install|verify ; GHOST_HOST=<jetson> bash pi/setup.sh
         GHOST_FRAMES=tcp://<jetson>:5555 python3 sensors/fusion.py --hardware --host <jetson> \
             --grid 10x10 --cell-m 0.5 --specs sensors/indoor_specs.json
         python3 pi/operator_link.py --host <jetson> --allow '<operator node id>'
```

On the Jetson, `jetson/launch/robot.launch.py` brings up the Gemini 330 depth camera, cuVSLAM odometry and a minimal Nav2: MPPI in omni mode for the mecanum base, with rolling-window costmaps fed by the depth point cloud. `jetson/base_driver.py` converts `/cmd_vel` into wheel speeds for the motor board (`jetson/motor_board.py`). It has a 0.4 s no-command stop, and `--identify` / `--spin-test` for checking the wiring. `jetson/frame_server.py` forwards camera frames to the Pi, where `sensors/detector.py` runs YOLOv8 on the Hailo AI HAT.

**Operator control:** the Pi sets up the search grid, but nothing moves until the operator presses **GO**, either on the dashboard (`dashboard/index.html?ws=ws://<jetson>:9001/ws`) or by texting `go` over Meshtastic. **HALT** (button, Space bar, or text `halt`) stops the robot: the core stops planning and ignores sensor readings until RESUME, and the bridge cancels the Nav2 goal. Mission states: `idle → active ⇄ halted`, `returning`, `complete` on contact.

The bridge (`jetson/ghost_bridge.py`) feeds odometry into GHOST and sends Nav2 to the centre of each next cell. It cancels the goal if the core stops answering. CONTACT is published on `/ghost/contact` and sent over LoRa to the operator.

---

## Directory structure

```
ghost/
├── core/                   Rust — the engine
│   └── src/
│       ├── belief_map.rs   Bayesian probability grid
│       ├── sensor_model.rs SensorSpec physics + SensorType identity
│       ├── path_planner.rs info-gain waypoint + LR factor computation
│       ├── dead_reckoning.rs IMU integration, elevation tracking
│       ├── hazard.rs       terrain hazard detection + path weights
│       ├── engine.rs       GhostEngine — message handler + snapshot
│       ├── server.rs       axum WebSocket server
│       └── sim.rs          scripted headless demo (cargo run -- --sim)
├── sensors/                Python — Pi sensor abstraction
│   ├── fusion.py           main loop — hardware or stub mode
│   ├── imu.py              MPU-6050 / random-walk stub
│   ├── thermal.py          MLX90640 / Pd(dist) stub
│   ├── vision.py           YOLOv8 person detection (Jetson frames or local camera) / stub
│   ├── detector.py         YOLOv8 on Hailo or ONNX CPU
│   ├── indoor_specs.json   short-range sensor models for indoor runs
│   ├── acoustic.py         PyAudio FFT VAD / Pd(dist) stub
│   └── ir.py               RPi.GPIO / 3 m-range stub
├── jetson/                 Jetson — robot + navigation
│   ├── launch/robot.launch.py  camera + cuVSLAM + Nav2 bringup
│   ├── config/nav2_params.yaml Nav2 tuned for the mecanum base
│   ├── base_driver.py      /cmd_vel → mecanum wheel speeds (dry-run by default)
│   ├── motor_board.py      motor-controller serial protocol
│   ├── teleop.py           keyboard driving for bench tests
│   ├── frame_server.py     camera frames → Pi detector (ZMQ)
│   ├── ghost_bridge.py     odometry → GHOST, GHOST waypoint → Nav2
│   ├── nav2_driver.py      Nav2 BasicNavigator wrapper
│   ├── setup.sh / start.sh install check / start everything
│   └── test_hardware_layer.py
├── pi/                     Pi — operator comms + setup
│   ├── operator_link.py    LoRa (Meshtastic) ↔ GHOST, sender allowlist
│   ├── setup.sh            Pi packages + models
│   ├── hailo_setup.sh      Hailo AI HAT bring-up
│   ├── get_models.sh       YOLOv8 models (Hailo .hef / ONNX)
│   └── requirements.txt
├── dashboard/
│   └── index.html          single-file live dashboard (no build step)
└── docs/
    └── adr/
        └── 0001-layered-architecture.md
```

---

## Hardware target

| Component | Role |
|-----------|------|
| Jetson Orin Nano | Runs `ghost-core`, YOLOv8 inference |
| Raspberry Pi 5 | GPIO sensors — IMU, thermal, IR, mic |
| MLX90640 | 32×24 thermal array, I2C |
| MPU-6050 | 6-DOF IMU, I2C |
| USB microphone | Acoustic VAD |
| Pi Camera + AI HAT | YOLOv8-nano person detection |

The Pi runs `fusion.py --hardware`; it connects to the Jetson's WebSocket over Ethernet or USB-C gadget mode.

---

## ROS2 integration

`ghost-core` is I/O-free and stateless by design — it plugs into any navigation stack via a thin bridge node.

`ghost_bridge.py` publishes two topics:

| Topic | Type | Content |
|-------|------|---------|
| `/ghost/contact` | `std_msgs/String` | JSON ContactDeclaration when GHOST declares a find |
| `/ghost/status` | `std_msgs/String` | JSON snapshot every ~250 ms (entropy, peak_p, sweeps, elevation, hazards) |

Swap `--odom /visual_slam/tracking/odometry` → `--odom /odom` to use wheel odometry instead of cuVSLAM.

---

## Branch status

This is the `ghost` working branch off `Team-20/main`.
Open a PR to merge when ready for team review.
