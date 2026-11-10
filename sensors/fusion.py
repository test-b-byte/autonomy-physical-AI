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


def _config_msg() -> str:
    return json.dumps({
        "type": "config",
        "width": GRID_W, "height": GRID_H, "cell_size_m": CELL_SIZE_M,
        "last_known_x": LKP_X, "last_known_y": LKP_Y,
        "prior_sigma_m": PRIOR_SIGMA,
    })


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

    async with websockets.connect(ws_url) as ws:
        log.info("connected to %s", ws_url)
        await ws.send(_config_msg())
        await ws.recv()
        log.info("engine configured")

        imu_interval    = 1.0 / IMU_HZ
        sensor_interval = 1.0 / SENSOR_HZ
        t_imu = t_sensor = time.monotonic()

        while True:
            now = time.monotonic()

            if now - t_imu >= imu_interval:
                r = imu.read()
                await ws.send(_imu_msg(r.ax, r.ay, r.az, r.gz, r.dt))
                state = json.loads(await ws.recv())
                for _, s in sensors:
                    s.update_robot_pos(state["robot_x"], state["robot_y"])
                t_imu = now

            if now - t_sensor >= sensor_interval:
                for name, sensor in sensors:
                    reading = sensor.read()
                    await ws.send(_sensor_msg(name, reading.detection, reading.confidence))
                    state = json.loads(await ws.recv())
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
    args = p.parse_args()

    ws_url = f"ws://{args.host}:{args.port}/ws"
    runner = run_hardware if args.hardware else run_stub

    try:
        asyncio.run(runner(ws_url))
    except KeyboardInterrupt:
        log.info("shutdown")


if __name__ == "__main__":
    main()
