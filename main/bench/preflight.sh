#!/usr/bin/env bash
# Jetson preflight: run while `bash jetson/start.sh` is up.  Checks every link
# in the chain and prints PASS / WARN / FAIL.  Takes ~30 s.
#
#   bash bench/preflight.sh
set -uo pipefail
GHOST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$GHOST_DIR/jetson/logs"
ROS_DISTRO="${ROS_DISTRO:-$(ls /opt/ros 2>/dev/null | head -1)}"
# shellcheck disable=SC1090
source "/opt/ros/$ROS_DISTRO/setup.bash" 2>/dev/null
WS="${ISAAC_ROS_WS:-/workspaces/isaac_ros-dev}"
[ -f "$WS/install/setup.bash" ] && source "$WS/install/setup.bash"

pass() { printf '  \e[32mPASS\e[0m  %s\n' "$*"; }
warn() { printf '  \e[33mWARN\e[0m  %s\n' "$*"; }
fail() { printf '  \e[31mFAIL\e[0m  %s\n' "$*"; FAILED=1; }
FAILED=0

rate() {   # rate TOPIC → average Hz over ~5 s (empty if none)
  timeout 7 ros2 topic hz -w 20 "$1" 2>/dev/null | awk '/average rate/ {r=$3} END {print r}'
}
check_rate() {  # check_rate NAME TOPIC MIN_HZ
  local r; r="$(rate "$2")"
  if [ -z "$r" ]; then fail "$1: no messages on $2"
  elif awk "BEGIN{exit !($r >= $3)}"; then pass "$1: $2 at ${r} Hz"
  else warn "$1: $2 only ${r} Hz (want ≥ $3)"; fi
}

echo "GHOST preflight — ROS 2 $ROS_DISTRO"

echo "core"
curl -sf localhost:9001/health >/dev/null && pass "ghost-core answering on :9001" || fail "ghost-core not answering (jetson/logs/core.log)"

echo "camera + odometry"
check_rate "odometry"     /visual_slam/tracking/odometry 15
check_rate "depth cloud"  /camera/depth/points 5
check_rate "IR frames"    /camera/left_ir/image_raw/compressed 5
if timeout 6 ros2 run tf2_ros tf2_echo odom base_link 2>/dev/null | grep -q Translation; then
  pass "TF odom → base_link"
else
  fail "no TF odom → base_link (cuVSLAM not tracking, or camera_link→base_link missing)"
fi

echo "navigation"
if ros2 action list 2>/dev/null | grep -q navigate_to_pose; then pass "Nav2 NavigateToPose available"
else warn "Nav2 not up (normal with NO_NAV2=1; otherwise see jetson/logs/robot.log)"; fi
grep -q "Nav2 ready" "$LOGS/bridge.log" 2>/dev/null && pass "bridge sees Nav2" || warn "bridge hasn't reported 'Nav2 ready'"
grep -q "core connected" "$LOGS/bridge.log" 2>/dev/null && pass "bridge connected to core" || warn "bridge not connected to core yet"

echo "base"
if grep -q "HARDWARE" "$LOGS/base.log" 2>/dev/null; then pass "base driver in HARDWARE mode"
elif grep -q "DRY RUN" "$LOGS/base.log" 2>/dev/null; then warn "base driver is DRY RUN — wheels won't move"
else fail "base driver not running (jetson/logs/base.log)"; fi
MV="$(timeout 4 ros2 topic echo --once /base/battery_mv 2>/dev/null | awk '/data:/ {print $2}')"
if [ -n "$MV" ]; then
  if [ "$MV" -ge 11000 ]; then pass "battery ${MV} mV"
  elif [ "$MV" -ge 10500 ]; then warn "battery ${MV} mV — charge soon"
  else fail "battery ${MV} mV — too low to drive"; fi
else warn "no battery reading (/base/battery_mv) — motor board not reporting"; fi

echo "pi link"
ss -ltn 2>/dev/null | grep -q ':5555 ' && pass "frame server listening on :5555" || fail "frame server not listening (jetson/logs/frames.log)"

echo
[ "$FAILED" = 0 ] && echo "preflight OK" || echo "preflight found failures — fix before driving"
exit "$FAILED"
