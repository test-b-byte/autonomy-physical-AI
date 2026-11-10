#!/usr/bin/env bash
# GHOST Jetson setup — run once, inside the Isaac ROS environment
# (the container/workspace that has orbbec_camera, isaac_ros_cuvslam and Nav2).
#
#   bash jetson/setup.sh
#   GHOST_DIR=~/ghost GHOST_BRANCH=ghost-upgrade bash jetson/setup.sh
set -euo pipefail

GHOST_DIR="${GHOST_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
log() { echo "[setup] $*"; }
fail=0
check() { if eval "$2" >/dev/null 2>&1; then log "ok    $1"; else log "MISSING $1  — $3"; fail=1; fi; }

# ── ROS 2 ─────────────────────────────────────────────────────────────────────
ROS_DISTRO="${ROS_DISTRO:-$(ls /opt/ros 2>/dev/null | head -1)}"
[ -n "$ROS_DISTRO" ] || { log "no ROS 2 under /opt/ros — run this inside the Isaac ROS container"; exit 1; }
# shellcheck disable=SC1090
source "/opt/ros/$ROS_DISTRO/setup.bash"
WS="${ISAAC_ROS_WS:-/workspaces/isaac_ros-dev}"
[ -f "$WS/install/setup.bash" ] && source "$WS/install/setup.bash"
log "ROS 2 $ROS_DISTRO, workspace $WS"

# ── Rust + ghost-core ─────────────────────────────────────────────────────────
if ! command -v cargo >/dev/null 2>&1; then
  log "installing Rust"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
fi
# shellcheck disable=SC1091
source "$HOME/.cargo/env" 2>/dev/null || true
log "building ghost-core (release)"
(cd "$GHOST_DIR/core" && cargo build --release)

# ── Python ────────────────────────────────────────────────────────────────────
log "installing Python packages"
pip3 install --break-system-packages -r "$GHOST_DIR/jetson/requirements.txt" 2>/dev/null \
  || pip3 install -r "$GHOST_DIR/jetson/requirements.txt"

# ── motor board access ────────────────────────────────────────────────────────
if [ -e /dev/ttyACM0 ]; then
  [ -w /dev/ttyACM0 ] && log "ok    /dev/ttyACM0 writable" \
    || log "MISSING write access to /dev/ttyACM0 — sudo usermod -aG dialout \$USER (then re-login), or run the container with --device /dev/ttyACM0"
else
  log "note  motor board not plugged in (/dev/ttyACM0) — base_driver will only dry-run"
fi

# ── ROS packages GHOST needs ──────────────────────────────────────────────────
check "rclpy"                  "python3 -c 'import rclpy'"                       "source ROS 2"
check "nav2_simple_commander"  "python3 -c 'import nav2_simple_commander'"       "apt install ros-$ROS_DISTRO-nav2-simple-commander"
check "orbbec_camera"          "ros2 pkg prefix orbbec_camera"                    "build OrbbecSDK_ROS2 in $WS"
check "isaac_ros_cuvslam"      "ros2 pkg prefix isaac_ros_cuvslam"                "apt install ros-$ROS_DISTRO-isaac-ros-visual-slam"
for p in nav2_planner nav2_controller nav2_behaviors nav2_bt_navigator nav2_lifecycle_manager nav2_mppi_controller nav2_navfn_planner; do
  check "$p" "ros2 pkg prefix $p" "apt install ros-$ROS_DISTRO-navigation2"
done
check "pyserial"               "python3 -c 'import serial'"                       "pip3 install pyserial"
check "pyzmq"                  "python3 -c 'import zmq'"                          "pip3 install pyzmq"

chmod +x "$GHOST_DIR"/jetson/*.sh "$GHOST_DIR"/jetson/*.py
[ "$fail" = 0 ] && log "Jetson ready — next: bash jetson/start.sh (see INSTALL.md)" \
               || log "fix the MISSING items above, then re-run"
