#!/usr/bin/env bash
# Send ONE Nav2 goal relative to the launch point (odom frame), with feedback.
# Tests Nav2 + base without GHOST.  Stop the bridge first so it doesn't
# replace the goal.
#
#   bash bench/nav_goal.sh 0.5 0      # half a metre forward
#   bash bench/nav_goal.sh 0 0        # back to the launch point
set -euo pipefail
X="${1:?x metres}"; Y="${2:-0}"
ROS_DISTRO="${ROS_DISTRO:-$(ls /opt/ros | head -1)}"
# shellcheck disable=SC1090
source "/opt/ros/$ROS_DISTRO/setup.bash"
ros2 action send_goal --feedback /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: odom}, pose: {position: {x: $X, y: $Y, z: 0.0}, orientation: {w: 1.0}}}}"
