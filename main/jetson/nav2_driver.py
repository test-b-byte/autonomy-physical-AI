"""
Nav2 waypoint driver for GHOST.

Thin wrapper around Nav2's BasicNavigator: navigate_to() starts a goal,
done() polls it, cancel() stops.  Goals are stamped in the same frame as the
odometry that GHOST is fed (default "odom"), so pose and goal always agree.
"""
import math
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult


class Nav2Driver:
    def __init__(self, frame: str = "odom") -> None:
        if not rclpy.ok():                    # the bridge may already have initialised ROS
            rclpy.init()
        self.frame = frame
        self._nav = BasicNavigator(node_name="ghost_navigator")
        self._active = False

    @property
    def node(self):
        return self._nav

    def wait_until_ready(self, timeout_sec: float = 90.0) -> bool:
        """Block until the NavigateToPose action server answers (no localizer needed)."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_sec:
            try:
                if self._nav.nav_to_pose_client.server_is_ready():
                    return True
            except Exception:
                pass
            rclpy.spin_once(self._nav, timeout_sec=1.0)
        return False

    def _pose(self, x: float, y: float, yaw: float) -> PoseStamped:
        p = PoseStamped()
        p.header.frame_id = self.frame
        p.header.stamp = self._nav.get_clock().now().to_msg()
        p.pose.position.x, p.pose.position.y = float(x), float(y)
        p.pose.orientation.z = math.sin(yaw / 2.0)
        p.pose.orientation.w = math.cos(yaw / 2.0)
        return p

    def navigate_to(self, x: float, y: float, yaw: float = 0.0) -> None:
        if self._active:
            self._nav.cancelTask()
        self._nav.goToPose(self._pose(x, y, yaw))
        self._active = True

    def cancel(self) -> None:
        if self._active:
            try:
                self._nav.cancelTask()
            finally:
                self._active = False

    def done(self) -> bool:
        if not self._active:
            return True
        if self._nav.isTaskComplete():
            self._active = False
            return True
        return False

    def result(self) -> TaskResult:
        return self._nav.getResult()

    def tick(self, timeout_sec: float = 0.0) -> None:
        rclpy.spin_once(self._nav, timeout_sec=timeout_sec)

    def destroy(self) -> None:
        for fn in (self.cancel, self._nav.destroy_node, rclpy.try_shutdown):
            try:
                fn()
            except Exception:
                pass
