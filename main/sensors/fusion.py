"""
GHOST sensor fusion layer.
Connects all sensors to the Rust core over WebSocket.

Usage:
  python3 fusion.py              # stub mode — automated demo scenario
  python3 fusion.py --hardware   # real hardware mode
  python3 fusion.py --host HOST --port PORT
"""
import asyncio, argparse, json, logging, math, sys, time
from dataclasses import asdict

import websockets

from imu      import IMUSensor
from thermal  import ThermalSensor
from vision   import VisionSensor
from acoustic import AcousticSensor
from ir       import IRSensor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ghost.fusion")

# ── Config ────────────────────────────────────────────────────────────────────

GRID_W        = 20
GRID_H        = 20
CELL_SIZE_M   = 2.0
LKP_X         = 20.0   # last-known-position world metres
LKP_Y         = 20.0
PRIOR_SIGMA   = 12.0

SUBJECT_X     = 20.0   # true subject position (stub only)
SUBJECT_Y     = 20.0

IMU_HZ        = 10.0   # IMU sample rate
SENSOR_HZ     =  3.0   # sensor poll rate


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sensor_msg(sensor_type: str, detection: bool, confidence: float) -> str:
    return json.dumps({
        "type": "sensor",
        "sensor_type": sensor_type,
        "detection": detection,
        "confidence": round(confidence, 4),
    })


def _imu_msg(ax: float, ay: float, az: float, gz: float, dt: float) -> str:
    return json.dumps({
        "type": "imu",
        "ax": ax, "ay": ay, "az": az, "gz": gz, "dt": dt,
    })


def _teleport_msg(x: float, y: float) -> str:
    return json.dumps({"type": "teleport", "x": round(x, 3), "y": round(y, 3)})


SENSOR_SPECS = None   # optional per-sensor overrides (--specs file.json)


def _config_msg() -> str:
    msg = {
        "type": "config",
        "width": GRID_W, "height": GRID_H, "cell_size_m": CELL_SIZE_M,
        "last_known_x": LKP_X, "last_known_y": LKP_Y,
        "prior_sigma_m": PRIOR_SIGMA,
    }
    if SENSOR_SPECS:
        msg["sensor_specs"] = SENSOR_SPECS
    return json.dumps(msg)


def _log_state(state: dict) -> None:
    c = state.get("contact")
    contact_str = (
        f"CONTACT cell({c['cell_x']},{c['cell_y']}) "
        f"P={c['probability']:.3f} conf={c['combined_confidence']:.3f} "
        f"sensors={c['sensors']}"
    ) if c else "none"
    hazards = state.get("hazard_alerts", [])
    hazard_str = f"{len(hazards)} alerts" if hazards else "clear"
    log.info(
        "robot=(%.1f,%.1f) elev=%.2fm cell=%s wp=%s entropy=%.2f peak=%.4f "
        "sweeps=%d terrain=%s | %s",
        state["robot_x"], state["robot_y"],
        state.get("elevation", 0.0),
        state["robot_cell"], state["next_waypoint"],
        state["entropy"], state["max_probability"],
        state["sweep_count"], hazard_str, contact_str,
    )


# ── Main loops ────────────────────────────────────────────────────────────────

async def run_hardware(ws_url: str) -> None:
    """Real hardware loop — reads all sensors, sends events, never stops."""
    imu      = IMUSensor()
    thermal  = ThermalSensor()
    vision   = VisionSensor()
    acoustic = AcousticSensor()
    ir_sens  = IRSensor()
    sensors  = [
        ("thermal",  thermal),
        ("vision",   vision),
        ("acoustic", acoustic),
        ("ir",       ir_sens),
    ]
    # A sensor whose hardware failed to start falls back to its simulator —
    # never feed simulated readings into a real search.
    live = [(n, s) for n, s in sensors if getattr(s, "_hw", False)]
    for n, s in sensors:
        if (n, s) not in live:
            log.warning("%s: no hardware — excluded from the search", n)
    sensors = live
    use_imu = getattr(imu, "_hw", False)
    if not use_imu:
        log.warning("imu: no hardware — dead reckoning/terrain alerts off (odometry comes from the Jetson)")

    async with websockets.connect(ws_url) as ws:
        log.info("connected to %s", ws_url)
        await ws.send(_config_msg())
        state = json.loads(await ws.recv())
        log.info("search grid configured — waiting for the operator's GO "
                 "(dashboard button or 'go' over the radio)")
        last_mission = state.get("mission")

        imu_interval    = 1.0 / IMU_HZ
        sensor_interval = 1.0 / SENSOR_HZ
        t_imu = t_sensor = time.monotonic()

        while True:
            now = time.monotonic()

            if use_imu and now - t_imu >= imu_interval:
                r = imu.read()
                await ws.send(_imu_msg(r.ax, r.ay, r.az, r.gz, r.dt))
                state = json.loads(await ws.recv())
                for _, s in sensors:
                    s.update_robot_pos(state["robot_x"], state["robot_y"])
                t_imu = now

            if now - t_sensor >= sensor_interval:
                for name, sensor in sensors:
                    reading = sensor.read()
                    if not getattr(reading, "valid", True):
                        continue                   # e.g. no fresh camera frame
                    await ws.send(_sensor_msg(name, reading.detection, reading.confidence))
                    state = json.loads(await ws.recv())
                    for _, s in sensors:
                        s.update_robot_pos(state["robot_x"], state["robot_y"])
                if state.get("mission") != last_mission:
                    last_mission = state.get("mission")
                    log.warning("mission: %s", last_mission)
                if sensors and last_mission == "active":
                    _log_state(state)
                if state.get("contact"):
                    log.warning("CONTACT DECLARED — holding position")
                t_sensor = now

            await asyncio.sleep(0.01)


async def run_stub(ws_url: str) -> None:
    """
    Stub / demo mode.
    Navigates the robot automatically toward next_waypoint, fires all
    four stub sensors, and converges to a CONTACT declaration.
    Also sends synthetic IMU readings (with terrain events) so the
    hazard detector fires even without real hardware.
    Subject is fixed at (SUBJECT_X, SUBJECT_Y).
    """
    imu      = IMUSensor()
    thermal  = ThermalSensor()
    vision   = VisionSensor()
    acoustic = AcousticSensor()
    ir_sens  = IRSensor()

    for s in [thermal, vision, acoustic, ir_sens]:
        s._subject_x = SUBJECT_X
        s._subject_y = SUBJECT_Y

    robot_x, robot_y = 2.0, 2.0   # start near origin

    async with websockets.connect(ws_url) as ws:
        log.info("connected to %s (stub mode)", ws_url)
        await ws.send(_config_msg())
        state = json.loads(await ws.recv())
        await ws.send(json.dumps({"type": "command", "action": "start"}))   # demo: GO immediately
        state = json.loads(await ws.recv())
        log.info("engine configured — starting autonomous demo")

        sensor_interval = 1.0 / SENSOR_HZ
        t_last = time.monotonic()

        while True:
            now = time.monotonic()
            if now - t_last < sensor_interval:
                await asyncio.sleep(0.05)
                continue
            t_last = now

            # Navigate: inch robot toward next_waypoint
            wp = state.get("next_waypoint")
            if wp:
                target_x = wp[0] * CELL_SIZE_M
                target_y = wp[1] * CELL_SIZE_M
                dx = target_x - robot_x
                dy = target_y - robot_y
                dist = math.hypot(dx, dy)
                step = min(1.5, dist)   # metres per tick
                if dist > 0.1:
                    robot_x += (dx / dist) * step
                    robot_y += (dy / dist) * step

            # Update stub sensor positions
            for s in [thermal, vision, acoustic, ir_sens]:
                s.update_robot_pos(robot_x, robot_y)

            # Send IMU reading (triggers hazard detection + terrain events)
            r = imu.read()
            await ws.send(_imu_msg(r.ax, r.ay, r.az, r.gz, r.dt))
            state = json.loads(await ws.recv())

            # Teleport robot to new position
            await ws.send(_teleport_msg(robot_x, robot_y))
            state = json.loads(await ws.recv())

            # Poll all sensors
            readings = [
                ("thermal",  thermal.read()),
                ("vision",   vision.read()),
                ("acoustic", acoustic.read()),
                ("ir",       ir_sens.read()),
            ]
            for name, reading in readings:
                await ws.send(_sensor_msg(name, reading.detection, reading.confidence))
                state = json.loads(await ws.recv())

            _log_state(state)

            if state.get("contact"):
                c = state["contact"]
                log.warning(
                    "★ CONTACT at (%.1fm, %.1fm) P=%.3f sensors=%s",
                    c["world_x"], c["world_y"], c["probability"], c["sensors"],
                )
                log.info("Demo complete. Press Ctrl-C to exit.")
                await asyncio.sleep(60)   # hold so dashboard can display result


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="GHOST sensor fusion layer")
    p.add_argument("--hardware", action="store_true", help="use real sensors")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=9001)
    p.add_argument("--grid", default=None, help="hardware: search grid WxH cells, e.g. 10x10")
    p.add_argument("--cell-m", type=float, default=None, help="hardware: cell size (m), e.g. 0.5")
    p.add_argument("--lkp", default=None, help="hardware: last-known position X,Y (m) on the grid")
    p.add_argument("--sigma", type=float, default=None, help="hardware: prior spread (m)")
    p.add_argument("--specs", default=None,
                   help="hardware: sensor model overrides JSON, e.g. sensors/indoor_specs.json")
    args = p.parse_args()

    global GRID_W, GRID_H, CELL_SIZE_M, LKP_X, LKP_Y, PRIOR_SIGMA, SENSOR_SPECS
    if args.specs:
        SENSOR_SPECS = {k: v for k, v in json.load(open(args.specs)).items() if not k.startswith("_")}
    if args.grid:
        GRID_W, GRID_H = (int(v) for v in args.grid.lower().split("x"))
    if args.cell_m:
        CELL_SIZE_M = args.cell_m
    if args.lkp:
        LKP_X, LKP_Y = (float(v) for v in args.lkp.split(","))
    if args.sigma:
        PRIOR_SIGMA = args.sigma
    ws_url = f"ws://{args.host}:{args.port}/ws"
    runner = run_hardware if args.hardware else run_stub

    try:
        asyncio.run(runner(ws_url))
    except KeyboardInterrupt:
        log.info("shutdown")


if __name__ == "__main__":
    main()
