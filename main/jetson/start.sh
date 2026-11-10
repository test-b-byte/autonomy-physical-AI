#!/usr/bin/env bash
# GHOST Jetson start-up: ghost-core + robot bringup (camera, cuVSLAM, Nav2) +
# base driver + frame server for the Pi + the GHOST↔Nav2 bridge.
#
#   bash jetson/start.sh                        everything, wheels LIVE
#   DRY_RUN=1 bash jetson/start.sh              wheels print instead of move
#   NO_NAV2=1 bash jetson/start.sh              camera + odometry only (no driving)
#   NO_BRIDGE=1 bash jetson/start.sh            Nav2 up but GHOST not driving (manual goals)
#   CELL_M=0.5 ORIGIN=0.5,0.5 bash jetson/start.sh   indoor grid, launch 0.5 m in from the corner
#   CAM_X=0.12 CAM_Z=0.10 bash jetson/start.sh  camera mount offset from robot centre (m)
#   DRIVE_ARGS="--ids 2,1,4,3 --signs=1,-1,1,-1" bash jetson/start.sh   wheel wiring
#
# Logs: jetson/logs/*.log      Stop: Ctrl-C (wheels are stopped on exit)
set -uo pipefail

GHOST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
J="$GHOST_DIR/jetson"
LOGS="$J/logs"; mkdir -p "$LOGS"
GHOST_ADDR="${GHOST_ADDR:-0.0.0.0:9001}"          # 0.0.0.0 so the Pi can reach the core
CELL_M="${CELL_M:-2.0}"
ORIGIN="${ORIGIN:-0,0}"

# ── ROS environment ───────────────────────────────────────────────────────────
if [ -z "${ROS_DISTRO:-}" ]; then
  ROS_DISTRO="$(ls /opt/ros 2>/dev/null | head -1)"
fi
# shellcheck disable=SC1090
source "/opt/ros/${ROS_DISTRO}/setup.bash" || { echo "no ROS 2 at /opt/ros/$ROS_DISTRO"; exit 1; }
WS="${ISAAC_ROS_WS:-/workspaces/isaac_ros-dev}"
[ -f "$WS/install/setup.bash" ] && source "$WS/install/setup.bash"
STAMP_ARGS=(); [ "$ROS_DISTRO" = "humble" ] && STAMP_ARGS=(--unstamped)
echo "[ghost] ROS 2 $ROS_DISTRO  workspace ${WS}"

PIDS=()
cleanup() {
  echo "[ghost] stopping…"
  kill "${PIDS[@]}" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM
start() {   # start NAME CMD…  → background, logged
  local name="$1"; shift
  echo "[ghost] $name → $LOGS/$name.log"
  "$@" > "$LOGS/$name.log" 2>&1 &
  PIDS+=($!)
}

# ── ghost-core ────────────────────────────────────────────────────────────────
CORE_BIN="$GHOST_DIR/core/target/release/ghost"
[ -x "$CORE_BIN" ] || (cd "$GHOST_DIR/core" && cargo build --release) || exit 1
GHOST_ADDR="$GHOST_ADDR" start core "$CORE_BIN"

# ── robot: camera + cuVSLAM (+ Nav2) ──────────────────────────────────────────
NAV2=true; [ -n "${NO_NAV2:-}" ] && NAV2=false
start robot ros2 launch "$J/launch/robot.launch.py" nav2:="$NAV2" \
  color:="${COLOR:-false}" cam_x:="${CAM_X:-0.0}" cam_z:="${CAM_Z:-0.0}"

# ── wheels ────────────────────────────────────────────────────────────────────
HW=(--hardware); [ -n "${DRY_RUN:-}" ] && HW=()
# shellcheck disable=SC2086
start base python3 "$J/base_driver.py" "${HW[@]}" --nav "${STAMP_ARGS[@]}" ${DRIVE_ARGS:-}

# ── camera frames → Pi detector ──────────────────────────────────────────────
FRAME_TOPIC=/camera/left_ir/image_raw/compressed
[ "${COLOR:-false}" = "true" ] && FRAME_TOPIC=/camera/color/image_raw/compressed
start frames python3 "$J/frame_server.py" --topic "$FRAME_TOPIC"

# ── bridge (waits for Nav2, and drives only once the Pi's sensors report) ────
if [ "$NAV2" = "true" ] && [ -z "${NO_BRIDGE:-}" ]; then
  sleep 2
  start bridge python3 "$J/ghost_bridge.py" --ghost-ws "ws://127.0.0.1:${GHOST_ADDR##*:}/ws" \
    --cell-m "$CELL_M" --origin "$ORIGIN"
fi

echo "[ghost] running — core ws://$(hostname -I 2>/dev/null | awk '{print $1}'):${GHOST_ADDR##*:}/ws   Ctrl-C to stop"
echo "[ghost] watch: tail -f $LOGS/*.log"
wait -n "${PIDS[@]}"
echo "[ghost] a process exited — see $LOGS/" >&2
