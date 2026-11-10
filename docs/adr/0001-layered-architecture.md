# ADR-0001 — Three-layer architecture: Rust core / WebSocket / Python sensors

**Status:** Accepted
**Date:** 2026-11-07
**Authors:** Team 20 — Code Metal Forge Hackathon

---

## Context

GHOST must operate without GPS, cellular networks, or external infrastructure. The system combines compute-intensive probabilistic inference with hardware-specific sensor I/O, targeting a heterogeneous embedded platform (Jetson Orin Nano + Raspberry Pi 5) in a time-constrained hackathon build.

Key constraints driving the decision:

- **Real-time sensor I/O** — IMU at 10 Hz, thermal at 2–3 Hz, GPIO-level IR polling, microphone FFT; latency matters, failure must be isolated
- **Deterministic math** — Bayesian updates, floating-point normalization, and path scoring must be numerically stable and testable in isolation from hardware
- **Hardware variability** — demo day uses stubs; competition day uses real sensors; the same code must run both without conditionals scattered everywhere
- **Platform split** — the Pi handles GPIO / I2C sensors; the Jetson runs inference and the planning core; they communicate over a local link
- **Team velocity** — mixed Rust / Python skills; both need to contribute in parallel without blocking on each other

---

## Decision

Split the system into three layers with a WebSocket JSON boundary between each:

```
[ Dashboard ]  ←── ws://host:9001/ws (query-response, 250 ms poll)
      ↕
[ Sensor fusion layer ]  Python — sensors/fusion.py
      ↕  (same WS connection, request-response)
[ Core engine ]  Rust — ghost-core binary
```

### Layer responsibilities

**Core (Rust)**
Owns all stateful probabilistic reasoning: the Bayesian belief grid, sensor likelihood math, dead reckoning, hazard detection, and information-gain path planning. Exposes a single WebSocket endpoint. Receives typed JSON messages (`Config`, `Imu`, `Sensor`, `Teleport`, `Query`, `Reset`); returns a `StateSnapshot` for every message. No I/O, no threads beyond the async runtime, no hardware coupling.

**Sensor layer (Python)**
Owns all hardware coupling. Each sensor module (`imu.py`, `thermal.py`, etc.) tries to import its hardware library at startup; falls back to a physics-based stub if unavailable. The stub uses the same detection-probability model as the core so stub runs produce statistically realistic results. `fusion.py` drives the main loop and speaks WebSocket to the core.

**Dashboard (HTML/JS)**
Single static file, no build step. Polls the core via WebSocket at 250 ms and renders the belief heatmap, robot position, waypoint, hazard overlays, and contact alert. Zero dependencies — opens directly from `file://` or any static server.

---

## Alternatives considered

### A: Monolithic Rust binary (sensors + core in one process)
Rust has embedded / RPi support via `rppal`, `linux-embedded-hal`, etc.

**Rejected because:**
- Hardware bring-up and physics debugging are much faster in Python
- Sensor stub/hardware switching requires conditional compilation or runtime flags that pollute the core logic
- The Pi and Jetson are separate machines; a single binary can't span both
- YOLOv8 inference has no production Rust binding that runs on the Jetson GPU

### B: ROS2 nodes from the start
Wire everything as ROS2 topics and nodes.

**Rejected because:**
- ROS2 setup on a Pi in a hackathon timeframe introduces significant build / dependency risk
- The core algorithm is not tied to ROS concepts; starting there couples algorithm correctness to framework correctness
- ROS2 can be added later via a thin bridge node (see ADR consequence below)

### C: Python throughout (NumPy + asyncio)
Single language, faster iteration.

**Rejected because:**
- The Bayesian update loop runs on every sensor message; Python GIL and NumPy overhead add non-determinism under async load
- The core needs to be embeddable on the Jetson with minimal dependencies and predictable memory use
- Rust ownership model eliminates an entire class of state-mutation bugs in the update loop

### D: gRPC / HTTP instead of WebSocket
More structured RPC with generated schemas.

**Rejected because:**
- WebSocket gives full-duplex request-response with minimal framing overhead
- JSON is human-readable during development and debuggable with standard browser tools
- No codegen tooling needed; schema is the Rust enum `IncomingMsg`

---

## Consequences

### Positive
- Core is fully testable headless (`cargo run -- --sim`) with no hardware present
- Sensor layer is replaceable: swap Python for a ROS2 bridge node, a C++ driver, or a web client without touching the core
- The WebSocket boundary is the natural integration point for ROS2 — a ~150-line bridge node subscribes to `/imu/data`, `/scan`, etc. and forwards to `:9001/ws`
- Dashboard works from any browser on the same network — no special tooling for judges to view the demo
- Sensor specs are runtime-configurable via the `Config` message; retuning for a new platform (e.g. hot-cup thermal demo) requires no recompile

### Negative / risks
- Two runtimes to manage; both must be running for the system to work
- WebSocket adds ~1–5 ms per message on a local link — acceptable for 10 Hz IMU but would not suit 100 Hz control loops
- JSON serialization adds ~50–100 µs per message; negligible at current rates, revisit if cell count scales to 1000×1000+
- The sensor layer holds no state between messages; any per-sensor calibration state must live in Python and be resent on reconnect

### Future decisions this enables (not decided here)
- ADR-002: Bayesian grid vs. particle filter for the belief representation
- ADR-003: Nav2 integration — GHOST as belief/detection engine, Nav2 as motion planner
- ADR-004: Grid resolution and cell-size tradeoffs for larger search areas
