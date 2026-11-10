"""
GHOST Jetson bridge: ghost-core ⇄ ROS 2.

  cuVSLAM odometry  → core teleport   (pose in GHOST grid metres)
  core next_waypoint → Nav2 goal       (centre of the target cell, odom frame)
  core contact       → /ghost/contact  (+ goal cancelled)
  core status        → /ghost/status

Frames: GHOST's grid starts at its (0,0) corner; the robot's launch point is
the odom origin.  --origin X,Y says where the launch point sits on the grid
(metres), e.g. 0.5,0.5 to start half a metre in from the corner.

Safety: the robot doesn't move until sensor data is flowing (the search has
started); if the core stops answering, the Nav2 goal is cancelled before
reconnecting.  If the core reports a mission state (halted / idle /
complete), the goal is cancelled; "returning" drives back to the launch point.

  python3 jetson/ghost_bridge.py
  python3 jetson/ghost_bridge.py --origin 0.5,0.5 --cell-m 0.5
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String
from websockets.sync.client import connect as ws_connect

from nav2_driver import Nav2Driver

log = logging.getLogger("ghost.bridge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")

GHOST_WS    = "ws://localhost:9001/ws"
ODOM_TOPIC  = "/visual_slam/tracking/odometry"
TELEPORT_HZ = 5.0
POLL_HZ     = 4.0
CORE_TIMEOUT_S = 3.0


class GhostBridge:
    def __init__(self, args) -> None:
        self.args = args
        self.origin = tuple(float(v) for v in args.origin.split(","))
        rclpy.init()
        self.node = rclpy.create_node("ghost_bridge")
        self.rlog = self.node.get_logger()
        self.pose = None                      # (x, y, frame) in odom
        self.pose_fresh = False
        self.node.create_subscription(Odometry, args.odom, self._on_odom, qos_profile_sensor_data)
        self.contact_pub = self.node.create_publisher(String, "/ghost/contact", 10)
        self.status_pub = self.node.create_publisher(String, "/ghost/status", 10)
        self.nav = Nav2Driver(frame="odom")
        self.active_goal = None               # cell tuple, or "home"
        self.contact_declared = False
        self.waiting_logged = False

    # ── frames ────────────────────────────────────────────────────────────────

    def to_grid(self, x: float, y: float) -> tuple[float, float]:
        return x + self.origin[0], y + self.origin[1]

    def to_odom(self, gx: float, gy: float) -> tuple[float, float]:
        return gx - self.origin[0], gy - self.origin[1]

    def _on_odom(self, msg: Odometry) -> None:
        p = msg.pose.pose.position
        self.pose = (p.x, p.y)
        self.nav.frame = msg.header.frame_id or "odom"
        self.pose_fresh = True

    # ── core I/O ──────────────────────────────────────────────────────────────

    def _call(self, ws, msg: dict) -> dict:
        ws.send(json.dumps(msg))
        return json.loads(ws.recv(timeout=CORE_TIMEOUT_S))

    def run(self) -> None:
        self.rlog.info("waiting for Nav2 (NavigateToPose)…")
        if not self.nav.wait_until_ready(timeout_sec=120.0):
            self.rlog.error("Nav2 not ready after 120 s — is robot.launch.py running with nav2:=true?")
            return
        self.rlog.info("Nav2 ready")
        while rclpy.ok():
            try:
                with ws_connect(self.args.ghost_ws, max_size=None, open_timeout=5) as ws:
                    ws.recv(timeout=CORE_TIMEOUT_S)          # initial snapshot
                    self.rlog.info(f"core connected at {self.args.ghost_ws}")
                    self._loop(ws)
            except Exception as exc:                          # timeout, refused, closed…
                self.nav.cancel()
                self.active_goal = None
                self.rlog.warning(f"core link lost ({exc!r}) — Nav2 goal cancelled, retrying in 2 s")
                time.sleep(2.0)

    def _loop(self, ws) -> None:
        t_tele = t_poll = 0.0
        while rclpy.ok():
            rclpy.spin_once(self.node, timeout_sec=0.0)
            self.nav.tick()
            now = time.monotonic()
            if self.pose_fresh and now - t_tele >= 1.0 / TELEPORT_HZ:
                gx, gy = self.to_grid(*self.pose)
                self._call(ws, {"type": "teleport", "x": round(gx, 3), "y": round(gy, 3)})
                self.pose_fresh = False
                t_tele = now
            if now - t_poll >= 1.0 / POLL_HZ:
                self._handle(self._call(ws, {"type": "query"}))
                t_poll = now
            time.sleep(0.02)

    # ── decisions ─────────────────────────────────────────────────────────────

    def _handle(self, s: dict) -> None:
        contact = s.get("contact")
        self.status_pub.publish(String(data=json.dumps({
            "mission": s.get("mission", "active"),
            "entropy": round(s.get("entropy", 0.0), 3),
            "peak_p": round(s.get("max_probability", 0.0), 4),
            "sweeps": s.get("sweep_count", 0),
            "contact": contact is not None,
        })))

        if contact and not self.contact_declared:
            self.contact_declared = True
            self.contact_pub.publish(String(data=json.dumps(contact)))
            self.rlog.warning(f"★ CONTACT ({contact['world_x']:.1f}, {contact['world_y']:.1f}) m "
                              f"P={contact['probability']:.3f}")
        if not contact:
            self.contact_declared = False
        if self.contact_declared:
            self._stop("contact")
            return

        mission = s.get("mission")
        if mission is None:
            # Cores without mission state plan waypoints from the moment they
            # start.  Don't drive until the search has really begun — i.e.
            # sensor data is flowing from the Pi.
            if s.get("sweep_count", 0) == 0:
                self._stop("waiting for the search to start (no sensor data yet)")
                if not self.waiting_logged:
                    self.rlog.info("holding still until the Pi's sensors start reporting")
                    self.waiting_logged = True
                return
            self.waiting_logged = False
            mission = "active"
        if mission == "returning":
            if self.active_goal != "home":
                self.nav.navigate_to(0.0, 0.0)     # launch point = odom origin
                self.active_goal = "home"
                self.rlog.info("→ returning to launch point")
            return
        if mission != "active":
            self._stop(mission)
            return

        wp = s.get("next_waypoint")
        if wp is None or self.pose is None:
            return
        cell = s.get("cell_size_m") or self.args.cell_m
        gx, gy = (wp[0] + 0.5) * cell, (wp[1] + 0.5) * cell     # cell centre, grid metres
        ox, oy = self.to_odom(gx, gy)
        dist = math.hypot(ox - self.pose[0], oy - self.pose[1])
        tol = self.args.tol_m if self.args.tol_m is not None else cell / 3.0
        if dist < tol:
            return
        cell_key = (wp[0], wp[1])
        if cell_key != self.active_goal or self.nav.done():
            yaw = math.atan2(oy - self.pose[1], ox - self.pose[0])
            self.nav.navigate_to(ox, oy, yaw)
            self.active_goal = cell_key
            self.rlog.info(f"→ cell {list(cell_key)} = odom ({ox:.2f}, {oy:.2f}), {dist:.2f} m away")

    def _stop(self, why: str) -> None:
        if self.active_goal is not None:
            self.nav.cancel()
            self.active_goal = None
            self.rlog.info(f"{why} — Nav2 goal cancelled")

    def destroy(self) -> None:
        self.nav.destroy()
        try:
            self.node.destroy_node()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--ghost-ws", default=GHOST_WS)
    ap.add_argument("--odom", default=ODOM_TOPIC)
    ap.add_argument("--cell-m", type=float, default=2.0,
                    help="grid cell size if the core doesn't report it (must match the mission)")
    ap.add_argument("--origin", default="0,0",
                    help="X,Y metres: where the launch point sits on the GHOST grid")
    ap.add_argument("--tol-m", type=float, default=None,
                    help="don't re-send a goal closer than this (default: cell/3)")
    args = ap.parse_args()
    bridge = GhostBridge(args)
    try:
        bridge.run()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.destroy()


if __name__ == "__main__":
    main()
