"""
GHOST Jetson bridge.

Connects the GHOST Bayesian SAR engine running on this Jetson to:
  - Visual-SLAM odometry  → GHOST Teleport  (accurate pose, overrides IMU DR)
  - GHOST next_waypoint   → Nav2 goal       (drives the robot to the next cell)
  - GHOST contact         → ROS2 topic      (broadcasts the find to the stack)
  - GHOST status          → ROS2 topic      (live entropy / peak-P / hazards)

Run alongside ghost-core:
  cargo run --release &
  python3 jetson/ghost_bridge.py

Flags:
  --ghost-ws  WS endpoint for GHOST core    (default: ws://localhost:9001/ws)
  --odom      ROS2 odometry topic           (default: /visual_slam/tracking/odometry)
  --cell-m    Grid cell side in metres      (default: 2.0 — must match GHOST Config)
  --tol-m     Arrival tolerance in metres   (default: 0.4)
"""

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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

# ── defaults ──────────────────────────────────────────────────────────────────
GHOST_WS    = "ws://localhost:9001/ws"
ODOM_TOPIC  = "/visual_slam/tracking/odometry"
CONTACT_PUB = "/ghost/contact"
STATUS_PUB  = "/ghost/status"
CELL_M      = 2.0
TOL_M       = 0.4
TELEPORT_HZ = 5.0
POLL_HZ     = 4.0


# ── shared pose (written by ROS2 subscriber, read by main loop) ───────────────

class _Pose:
    __slots__ = ("x", "y", "yaw", "fresh")

    def __init__(self) -> None:
        self.x = self.y = self.yaw = 0.0
        self.fresh = False


def _yaw_from_quat(q) -> float:
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def _tx(ws, msg: dict) -> dict:
    ws.send(json.dumps(msg))
    return json.loads(ws.recv())


# ── bridge ────────────────────────────────────────────────────────────────────

class GhostBridge:
    def __init__(self, ws_url: str, cell_m: float, tol_m: float, odom_topic: str) -> None:
        self._ws_url   = ws_url
        self._cell_m   = cell_m
        self._tol_m    = tol_m

        rclpy.init()
        self._node = rclpy.create_node("ghost_bridge")
        self._rlog = self._node.get_logger()

        self._pose = _Pose()
        self._node.create_subscription(
            Odometry, odom_topic, self._on_odom, qos_profile_sensor_data
        )
        self._contact_pub = self._node.create_publisher(String, CONTACT_PUB, 10)
        self._status_pub  = self._node.create_publisher(String, STATUS_PUB, 10)

        self._nav              = Nav2Driver()
        self._active_wp: tuple | None = None   # (cell_x, cell_y) of current Nav2 goal
        self._contact_declared = False

    # ── ROS2 odom callback ─────────────────────────────────────────────────────

    def _on_odom(self, msg: Odometry) -> None:
        p = msg.pose.pose
        self._pose.x   = p.position.x
        self._pose.y   = p.position.y
        self._pose.yaw = _yaw_from_quat(p.orientation)
        self._pose.fresh = True

    # ── single iteration of the bridge loop ───────────────────────────────────

    def _tick(self, ws, now: float, t_odom: float, t_poll: float) -> tuple[float, float]:
        """Run one pass of teleport + poll.  Returns updated (t_odom, t_poll)."""

        rclpy.spin_once(self._node, timeout_sec=0.0)

        # ── teleport: forward cuVSLAM pose to GHOST ───────────────────────────
        if self._pose.fresh and now - t_odom >= 1.0 / TELEPORT_HZ:
            _tx(ws, {
                "type": "teleport",
                "x":    round(self._pose.x, 3),
                "y":    round(self._pose.y, 3),
            })
            self._pose.fresh = False
            t_odom = now

        # ── poll GHOST state → drive Nav2 ────────────────────────────────────
        if now - t_poll >= 1.0 / POLL_HZ:
            state = _tx(ws, {"type": "query"})
            self._handle_state(state)
            t_poll = now
            self._nav.tick()

        return t_odom, t_poll

    # ── state handler ─────────────────────────────────────────────────────────

    def _handle_state(self, state: dict) -> None:
        contact = state.get("contact")

        # ── contact declaration ───────────────────────────────────────────────
        if contact and not self._contact_declared:
            self._contact_declared = True
            msg = String()
            msg.data = json.dumps(contact)
            self._contact_pub.publish(msg)
            self._rlog.warning(
                f"★ CONTACT ({contact['world_x']:.1f}m, {contact['world_y']:.1f}m) "
                f"P={contact['probability']:.3f}  sensors={contact['sensors']}"
            )

        # ── publish live status ───────────────────────────────────────────────
        s = String()
        s.data = json.dumps({
            "entropy":  round(state.get("entropy", 0.0), 3),
            "peak_p":   round(state.get("max_probability", 0.0), 4),
            "sweeps":   state.get("sweep_count", 0),
            "elev_m":   round(state.get("elevation", 0.0), 2),
            "hazards":  len(state.get("hazard_alerts", [])),
            "contact":  contact is not None,
        })
        self._status_pub.publish(s)

        # ── after contact, let the robot coast to a stop ───────────────────────
        if self._contact_declared:
            self._nav.cancel()
            return

        # ── pick up the GHOST waypoint and send it to Nav2 ────────────────────
        wp = state.get("next_waypoint")
        if wp is None:
            return

        wp_cell = (wp[0], wp[1])
        wx = wp[0] * self._cell_m
        wy = wp[1] * self._cell_m

        dist = math.hypot(wx - self._pose.x, wy - self._pose.y)
        if dist < self._tol_m:
            return  # already here

        if wp_cell != self._active_wp or self._nav.done():
            yaw = math.atan2(wy - self._pose.y, wx - self._pose.x)
            self._nav.navigate_to(wx, wy, yaw)
            self._active_wp = wp_cell
            self._rlog.info(
                f"→ Nav2 cell{list(wp_cell)} "
                f"({wx:.1f}m, {wy:.1f}m)  dist={dist:.1f}m"
            )

    # ── outer reconnect loop ──────────────────────────────────────────────────

    def run(self) -> None:
        self._rlog.info("waiting for Nav2 action servers…")
        if not self._nav.wait_until_ready(timeout_sec=90.0):
            self._rlog.error("Nav2 not ready after 90 s — aborting")
            return
        self._rlog.info("Nav2 ready")

        while rclpy.ok():
            try:
                with ws_connect(self._ws_url) as ws:
                    self._rlog.info(f"GHOST connection open at {self._ws_url}")
                    t_odom = t_poll = time.monotonic() - 999.0  # fire immediately
                    while True:
                        now = time.monotonic()
                        t_odom, t_poll = self._tick(ws, now, t_odom, t_poll)
                        time.sleep(0.02)   # 50 Hz spin
            except Exception as exc:
                self._rlog.warning(f"GHOST connection lost ({exc}), retrying in 2 s…")
                time.sleep(2.0)

    # ── cleanup ───────────────────────────────────────────────────────────────

    def destroy(self) -> None:
        self._nav.destroy()
        try:
            self._node.destroy_node()
            rclpy.try_shutdown()
        except Exception:
            pass


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="GHOST Jetson bridge")
    ap.add_argument("--ghost-ws", default=GHOST_WS,
                    help="WebSocket endpoint for the GHOST core")
    ap.add_argument("--odom",    default=ODOM_TOPIC,
                    help="ROS2 odometry topic (cuVSLAM or wheel odom)")
    ap.add_argument("--cell-m",  type=float, default=CELL_M,
                    help="Grid cell side in metres (must match GHOST Config)")
    ap.add_argument("--tol-m",   type=float, default=TOL_M,
                    help="Arrival tolerance — stop sending Nav2 goals within this radius")
    args = ap.parse_args()

    bridge = GhostBridge(
        ws_url=args.ghost_ws,
        cell_m=args.cell_m,
        tol_m=args.tol_m,
        odom_topic=args.odom,
    )
    try:
        bridge.run()
    except KeyboardInterrupt:
        log.info("shutdown")
    finally:
        bridge.destroy()


if __name__ == "__main__":
    main()
