#!/usr/bin/env python3
"""
Mecanum base driver: velocity commands → four wheel speeds → motor board.

  python3 jetson/base_driver.py                   DRY RUN — prints wheel speeds, no hardware
  python3 jetson/base_driver.py --hardware        drive the wheels from /cmd_vel_teleop (teleop.py)
  python3 jetson/base_driver.py --hardware --nav  drive the wheels from /cmd_vel (Nav2)
  python3 jetson/base_driver.py --identify        wheels off the ground: find motor ids + directions
  python3 jetson/base_driver.py --spin-test       wheels off the ground: spin each wheel to check wiring

Safety: wheels stop if no command arrives for --timeout s (default 0.4), and
all four wheel speeds are scaled together so none exceeds --max-rps (the
direction of travel is kept).  Never run --nav and teleop at the same time.

Velocity frame (REP-103): +x forward, +y left, +wz counter-clockwise.
Wheel order everywhere: front-left, front-right, rear-left, rear-right.
Publishes battery millivolts on /base/battery_mv (std_msgs/UInt16).
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motor_board import MotorBoard                    # noqa: E402

# ── chassis geometry: MEASURE YOUR ROBOT and pass flags or edit these ────────
WHEEL_RADIUS_M = 0.0485
HALF_WHEELBASE_M = 0.08    # half the front↔rear axle distance
HALF_TRACK_M = 0.09        # half the left↔right wheel distance
WHEELS = ("front-left", "front-right", "rear-left", "rear-right")


def mecanum_ik(vx: float, vy: float, wz: float, r: float = WHEEL_RADIUS_M,
               lx: float = HALF_WHEELBASE_M, ly: float = HALF_TRACK_M) -> tuple[float, ...]:
    """Body twist → wheel speeds (rev/s), order fl, fr, rl, rr (X-roller layout)."""
    k = lx + ly
    to_rps = 1.0 / (2.0 * math.pi * r)
    return ((vx - vy - k * wz) * to_rps,
            (vx + vy + k * wz) * to_rps,
            (vx + vy - k * wz) * to_rps,
            (vx - vy + k * wz) * to_rps)


def scale_to_limit(wheels, max_rps: float) -> list[float]:
    peak = max(abs(w) for w in wheels)
    return list(wheels) if peak <= max_rps or peak == 0 else [w * max_rps / peak for w in wheels]


class PrintOut:
    """Dry-run output: prints wheel speeds when they change."""

    def __init__(self) -> None:
        self._last = None

    def send(self, wheels) -> None:
        if self._last is None or any(abs(a - b) > 0.01 for a, b in zip(wheels, self._last)):
            print("wheels rev/s  fl={:+.3f} fr={:+.3f} rl={:+.3f} rr={:+.3f}".format(*wheels), flush=True)
            self._last = list(wheels)

    def stop(self) -> None:
        self.send([0.0] * 4)

    battery_mv = None

    def close(self) -> None:
        self.stop()


class BoardOut:
    """Hardware output: maps wheel order to motor ids and directions."""

    def __init__(self, board: MotorBoard, ids, signs) -> None:
        self.board, self.ids, self.signs = board, ids, signs
        self.stop()

    def send(self, wheels) -> None:
        self.board.set_speeds({i: w * s for i, s, w in zip(self.ids, self.signs, wheels)})

    def stop(self) -> None:
        self.board.stop(self.ids)

    @property
    def battery_mv(self):
        return self.board.battery_mv

    def close(self) -> None:
        self.board.close()


def run_ros(args, out) -> None:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import UInt16
    if args.unstamped:
        from geometry_msgs.msg import Twist as Msg
    else:
        from geometry_msgs.msg import TwistStamped as Msg

    class Driver(Node):
        def __init__(self) -> None:
            super().__init__("ghost_base_driver")
            topic = "/cmd_vel" if args.nav else "/cmd_vel_teleop"
            self.create_subscription(Msg, topic, self.on_cmd, 10)
            self.batt = self.create_publisher(UInt16, "/base/battery_mv", 1)
            self.create_timer(0.05, self.watchdog)
            self.create_timer(1.0, self.pub_battery)
            self.last = None
            self.moving = False
            self.get_logger().info(
                f"{'HARDWARE' if args.hardware else 'DRY RUN'} — {Msg.__name__} on {topic}, "
                f"max {args.max_rps} rev/s/wheel, stop after {args.timeout}s silence")

        def on_cmd(self, msg) -> None:
            tw = msg if args.unstamped else msg.twist
            wheels = scale_to_limit(
                mecanum_ik(tw.linear.x, tw.linear.y, tw.angular.z,
                           args.wheel_radius, args.half_wheelbase, args.half_track),
                args.max_rps)
            out.send(wheels)
            self.last = time.monotonic()
            self.moving = any(w != 0.0 for w in wheels)

        def watchdog(self) -> None:
            if self.moving and time.monotonic() - self.last > args.timeout:
                out.stop()
                self.moving = False
                self.get_logger().warn(f"no command for {args.timeout}s — wheels stopped")

        def pub_battery(self) -> None:
            mv = out.battery_mv
            if mv is not None:
                self.batt.publish(UInt16(data=int(mv)))

    rclpy.init()
    node = Driver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        out.close()
        node.destroy_node()
        rclpy.try_shutdown()


def spin_test(board: MotorBoard, ids, signs, rps: float) -> None:
    print(f"\nWHEELS OFF THE GROUND. Each wheel spins FORWARD for 1 s at {rps} rev/s.")
    input("Enter to start, Ctrl-C to abort: ")
    try:
        for name, mid, sgn in zip(WHEELS, ids, signs):
            print(f"  {name}: motor id {mid}, sign {sgn:+.0f}")
            board.set_speeds({mid: rps * sgn})
            time.sleep(1.0)
            board.set_speeds({mid: 0.0})
            time.sleep(1.0)
        print("\nEach named wheel should have turned so the robot would drive forward.")
        print("If not, fix --ids / --signs (or run --identify).")
    finally:
        board.stop(ids)


def identify(board: MotorBoard, rps: float) -> None:
    names = {"fl": 0, "fr": 1, "rl": 2, "rr": 3}
    print("\nWHEELS OFF THE GROUND. Each motor id spins for 1 s.")
    print("Answer from behind the robot, facing where the camera looks: fl / fr / rl / rr.")
    input("Enter to start, Ctrl-C to abort: ")
    ids, signs = [None] * 4, [None] * 4
    try:
        for mid in (1, 2, 3, 4):
            while True:
                board.set_speeds({mid: rps})
                time.sleep(1.0)
                board.set_speeds({mid: 0.0})
                w = input(f"  motor {mid}: which wheel moved? (fl/fr/rl/rr, 'r' to repeat) ").strip().lower()
                if w == "r":
                    continue
                if w not in names or ids[names[w]] is not None:
                    print("   not valid or already assigned — repeating")
                    continue
                d = ""
                while d not in ("f", "b"):
                    d = input("   did it turn the robot forward or backward? (f/b) ").strip().lower()
                ids[names[w]], signs[names[w]] = mid, 1 if d == "f" else -1
                break
    finally:
        board.stop((1, 2, 3, 4))
    print(f"\nUse:  --ids {','.join(map(str, ids))} --signs={','.join(map(str, signs))}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--hardware", action="store_true", help="drive the real wheels")
    ap.add_argument("--nav", action="store_true", help="listen on /cmd_vel (Nav2), not /cmd_vel_teleop")
    ap.add_argument("--unstamped", action="store_true",
                    help="subscribe geometry_msgs/Twist (Humble Nav2) instead of TwistStamped")
    ap.add_argument("--identify", action="store_true", help="interactive motor id / direction finder")
    ap.add_argument("--spin-test", action="store_true", help="spin each wheel forward in turn")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--ids", default="1,2,3,4", help="motor ids for fl,fr,rl,rr")
    ap.add_argument("--signs", default="1,1,-1,-1", help="+1/-1 per wheel so positive = forward")
    ap.add_argument("--max-rps", type=float, default=1.4, help="per-wheel cap (85 rpm motors ≈ 1.42)")
    ap.add_argument("--timeout", type=float, default=0.4, help="stop after this long without a command")
    ap.add_argument("--test-rps", type=float, default=0.3)
    ap.add_argument("--wheel-radius", type=float, default=WHEEL_RADIUS_M)
    ap.add_argument("--half-wheelbase", type=float, default=HALF_WHEELBASE_M)
    ap.add_argument("--half-track", type=float, default=HALF_TRACK_M)
    args = ap.parse_args()

    ids = [int(v) for v in args.ids.split(",")]
    signs = [float(v) for v in args.signs.split(",")]
    if len(ids) != 4 or len(signs) != 4:
        sys.exit("--ids and --signs need 4 comma-separated values (fl,fr,rl,rr)")

    if args.identify or args.spin_test:
        board = MotorBoard(args.port)
        time.sleep(0.3)
        try:
            identify(board, args.test_rps) if args.identify else spin_test(board, ids, signs, args.test_rps)
        finally:
            board.close()
        return

    out = BoardOut(MotorBoard(args.port), ids, signs) if args.hardware else PrintOut()
    run_ros(args, out)


if __name__ == "__main__":
    main()
