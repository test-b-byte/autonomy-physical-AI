#!/usr/bin/env bash
# Software stop: stops the bridge (it cancels its Nav2 goal on exit) and
# floods zero velocity.  Under jetson/start.sh the whole stack then shuts
# down, and the base driver commands zero wheel speed on exit.
# NOT a substitute for the physical kill.
#
#   bash bench/stop.sh
ROS_DISTRO="${ROS_DISTRO:-$(ls /opt/ros | head -1)}"
# shellcheck disable=SC1090
source "/opt/ros/$ROS_DISTRO/setup.bash"
for pid in $(pgrep -f "jetson/ghost_bridge.py"); do kill -INT "$pid"; done
TYPE=geometry_msgs/msg/TwistStamped; [ "$ROS_DISTRO" = humble ] && TYPE=geometry_msgs/msg/Twist
timeout 2 ros2 topic pub -r 20 /cmd_vel "$TYPE" "{}" >/dev/null 2>&1
echo "stopped: bridge down, zero velocity sent (start.sh shuts the rest down) — restart with jetson/start.sh"
