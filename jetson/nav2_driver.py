"""
Nav2 waypoint driver for GHOST.

Thin wrapper around Nav2's BasicNavigator.  Accepts world-frame coordinates
from the GHOST engine and drives the robot there.  Call navigate_to() to
start a goal; poll done() each loop tick to detect completion.
"""
import math
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult


def _stamped_pose(nav: BasicNavigator, x: float, y: float, yaw: float) -> PoseStamped:
    p = PoseStamped()
    p.header.frame_id = "map"
    p.header.stamp = nav.get_clock().now().to_msg()
    p.pose.position.x = float(x)
    p.pose.position.y = float(y)
    p.pose.orientation.z = math.sin(yaw / 2.0)
    p.pose.orientation.w = math.cos(yaw / 2.0)
    return p


class Nav2Driver:
    """
    Drives the robot to world-frame waypoints via Nav2.

    Lifecycle:
        driver = Nav2Driver()
        driver.wait_until_ready()          # block until action servers are up
        driver.navigate_to(x, y)           # send a goal
        while not driver.done():           # poll
            driver.tick()
    """

    def __init__(self) -> None:
        rclpy.init()
        self._nav = BasicNavigator()
        self._active = False

    # ── readiness ─────────────────────────────────────────────────────────────

    def wait_until_ready(self, timeout_sec: float = 90.0) -> bool:
        """Block until Nav2 action servers respond or timeout expires."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_sec:
            try:
                if (self._nav.nav_to_pose_client.server_is_ready()
                        and self._nav.follow_waypoints_client.server_is_ready()):
                    return True
            except Exception:
                pass
            rclpy.spin_once(self._nav, timeout_sec=1.0)
        return False

    # ── goal control ──────────────────────────────────────────────────────────

    def navigate_to(self, x: float, y: float, yaw: float = 0.0) -> None:
        """Send a new goal.  Any current goal is cancelled first."""
        if self._active:
            self._nav.cancelTask()
        self._nav.goToPose(_stamped_pose(self._nav, x, y, yaw))
        self._active = True

    def follow_path(self, waypoints: list[tuple[float, float]]) -> None:
        """Drive through an ordered list of (x, y) world-frame waypoints."""
        if not waypoints:
            return
        if self._active:
            self._nav.cancelTask()
        poses, prev = [], waypoints[0]
        for x, y in waypoints:
            yaw = math.atan2(y - prev[1], x - prev[0])
            poses.append(_stamped_pose(self._nav, x, y, yaw))
            prev = (x, y)
        self._nav.followWaypoints(poses)
        self._active = True

    def cancel(self) -> None:
        if self._active:
            self._nav.cancelTask()
            self._active = False

    # ── status ────────────────────────────────────────────────────────────────

    def done(self) -> bool:
        """True when no goal is active or the last goal has finished."""
        if not self._active:
            return True
        if self._nav.isTaskComplete():
            self._active = False
            return True
        return False

    def result(self) -> TaskResult:
        return self._nav.getResult()

    def tick(self, timeout_sec: float = 0.0) -> None:
        """Advance ROS2 callbacks.  Call once per main-loop iteration."""
        rclpy.spin_once(self._nav, timeout_sec=timeout_sec)

    # ── cleanup ───────────────────────────────────────────────────────────────

    def destroy(self) -> None:
        try:
            self.cancel()
        except Exception:
            pass
        try:
            self._nav.destroy_node()
        except Exception:
            pass
        try:
            rclpy.try_shutdown()
        except Exception:
            pass
