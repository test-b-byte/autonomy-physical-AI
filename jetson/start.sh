#!/usr/bin/env bash
# GHOST Jetson startup
# Launches ghost-core (Rust), the ROS2 navigation stack, and the bridge.
#
# Usage:
#   ./jetson/start.sh                     # defaults
#   ./jetson/start.sh --cell-m 0.5        # 0.5 m cells for the hot-cup demo
#   GHOST_ADDR=0.0.0.0:9001 ./jetson/start.sh
#   NO_NAV2=1 ./jetson/start.sh           # skip ros2 launch (simulator mode)

set -euo pipefail

GHOST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
GHOST_ADDR="${GHOST_ADDR:-127.0.0.1:9001}"
ROS_DISTRO="${ROS_DISTRO:-humble}"

# ── ROS2 environment ──────────────────────────────────────────────────────────
# shellcheck disable=SC1090
source "/opt/ros/${ROS_DISTRO}/setup.bash"
# If using a colcon workspace, uncomment:
# source "$HOME/ros2_ws/install/setup.bash"

# ── ghost-core ────────────────────────────────────────────────────────────────
echo "[ghost] starting ghost-core on $GHOST_ADDR"
(
  cd "$GHOST_DIR/core"
  GHOST_ADDR="$GHOST_ADDR" cargo run --release
) &
CORE_PID=$!

# Give the WebSocket server a moment to bind before the bridge connects.
sleep 2

# ── GHOST bridge ──────────────────────────────────────────────────────────────
echo "[ghost] starting ghost_bridge"
(
  cd "$GHOST_DIR"
  python3 jetson/ghost_bridge.py \
    --ghost-ws "ws://${GHOST_ADDR}/ws" \
    "$@"
) &
BRIDGE_PID=$!

# ── ROS2 nav stack (optional) ─────────────────────────────────────────────────
NAV2_PID=""
if [ -z "${NO_NAV2:-}" ]; then
  echo "[ghost] launching ROS2 navigation stack"
  # Swap in your own launch file; examples:
  #   ros2 launch nav2_bringup navigation_launch.py use_sim_time:=false
  #   ros2 launch ghost_nav slam_nav.launch.py
  ros2 launch nav2_bringup navigation_launch.py use_sim_time:=false &
  NAV2_PID=$!
fi

# ── cleanup ───────────────────────────────────────────────────────────────────
cleanup() {
  echo "[ghost] shutting down"
  [ -n "$NAV2_PID"   ] && kill "$NAV2_PID"   2>/dev/null || true
  [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null || true
  [ -n "$CORE_PID"   ] && kill "$CORE_PID"   2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[ghost] all processes running — Ctrl-C to stop"
wait
