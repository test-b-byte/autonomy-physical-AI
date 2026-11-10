#!/usr/bin/env python3
"""
Keyboard teleop for the mecanum base (bench testing).  Run alongside
`base_driver.py --hardware` (WITHOUT --nav):

    w / s  forward / back      a / d  strafe left / right
    q / e  rotate left / right space  stop      x / Ctrl-C  quit

Deadman: the robot moves only while a key keeps repeating; release it and
the robot stops after --hold s.  Publishes on /cmd_vel_teleop at 20 Hz, so
Nav2 (/cmd_vel) can never fight it.  Needs a real terminal.
"""
from __future__ import annotations

import argparse
import select
import sys
import termios
import time
import tty

KEYS = {"w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, 1, 0), "d": (0, -1, 0),
        "q": (0, 0, 1), "e": (0, 0, -1)}
MAX_LIN, MAX_ANG = 0.5, 3.0          # refuse typos above these


def command(key: str | None, since_key: float, hold: float, lin: float, ang: float):
    if key not in KEYS or since_key > hold:
        return 0.0, 0.0, 0.0
    x, y, z = KEYS[key]
    return x * lin, y * lin, z * ang


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--speed", type=float, default=0.25, help="m/s")
    ap.add_argument("--turn", type=float, default=1.2, help="rad/s")
    ap.add_argument("--hold", type=float, default=0.25, help="deadman window, s")
    ap.add_argument("--unstamped", action="store_true", help="publish Twist instead of TwistStamped")
    args = ap.parse_args()
    if args.speed > MAX_LIN or args.turn > MAX_ANG:
        sys.exit(f"refusing --speed > {MAX_LIN} or --turn > {MAX_ANG}")
    if not sys.stdin.isatty():
        sys.exit("teleop needs an interactive terminal (docker exec -it …)")

    import rclpy
    from geometry_msgs.msg import Twist, TwistStamped
    rclpy.init()
    node = rclpy.create_node("ghost_teleop")
    pub = node.create_publisher(Twist if args.unstamped else TwistStamped, "/cmd_vel_teleop", 10)

    def publish(vx, vy, wz):
        if args.unstamped:
            m = Twist()
            t = m
        else:
            m = TwistStamped()
            m.header.stamp = node.get_clock().now().to_msg()
            m.header.frame_id = "base_link"
            t = m.twist
        t.linear.x, t.linear.y, t.angular.z = float(vx), float(vy), float(wz)
        pub.publish(m)

    print(__doc__.split("\n\n")[1])
    old = termios.tcgetattr(sys.stdin)
    key, t_key = None, 0.0
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            if select.select([sys.stdin], [], [], 0.05)[0]:
                c = sys.stdin.read(1).lower()
                if c in ("x", "\x03"):
                    break
                key, t_key = c, time.monotonic()
            publish(*command(key, time.monotonic() - t_key, args.hold, args.speed, args.turn))
    except KeyboardInterrupt:
        pass
    finally:
        for _ in range(3):
            publish(0, 0, 0)
            time.sleep(0.02)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
