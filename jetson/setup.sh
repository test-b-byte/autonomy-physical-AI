#!/usr/bin/env bash
# GHOST Jetson setup — run once on a fresh Jetson Orin with ROS2 already installed.
# Installs Rust, builds ghost-core, installs Python deps, clones the repo if needed.
#
# Usage:
#   bash jetson/setup.sh
#   GHOST_REPO=git@github.com:CodeMetalForge-Hackathon/Team-20.git bash jetson/setup.sh

set -euo pipefail

GHOST_DIR="${GHOST_DIR:-$HOME/ghost}"
GHOST_REPO="${GHOST_REPO:-https://github.com/CodeMetalForge-Hackathon/Team-20.git}"
GHOST_BRANCH="${GHOST_BRANCH:-ghost}"
ROS_DISTRO="${ROS_DISTRO:-humble}"

log() { echo "[setup] $*"; }

# ── clone repo if not present ─────────────────────────────────────────────────
if [ ! -d "$GHOST_DIR/.git" ]; then
  log "cloning $GHOST_REPO → $GHOST_DIR"
  git clone --branch "$GHOST_BRANCH" "$GHOST_REPO" "$GHOST_DIR"
else
  log "repo already present at $GHOST_DIR — pulling"
  git -C "$GHOST_DIR" pull --ff-only
fi

# ── Rust ──────────────────────────────────────────────────────────────────────
if ! command -v cargo &>/dev/null; then
  log "installing Rust"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
  # shellcheck disable=SC1090
  source "$HOME/.cargo/env"
else
  log "Rust $(rustc --version) already installed"
fi

# ── build ghost-core ──────────────────────────────────────────────────────────
log "building ghost-core (release)…"
(
  source "$HOME/.cargo/env" 2>/dev/null || true
  cd "$GHOST_DIR/core"
  cargo build --release
)
log "ghost-core binary: $GHOST_DIR/core/target/release/ghost-core"

# ── Python deps (Jetson — no ROS2 packages here, they come with the distro) ──
log "installing Python deps"
pip3 install --break-system-packages "websockets>=11.0" 2>/dev/null \
  || pip3 install "websockets>=11.0"

# ── ROS2 environment check ────────────────────────────────────────────────────
ROS_SETUP="/opt/ros/${ROS_DISTRO}/setup.bash"
if [ ! -f "$ROS_SETUP" ]; then
  log "WARNING: ROS2 $ROS_DISTRO not found at $ROS_SETUP"
  log "         set ROS_DISTRO= to match your installed distro"
else
  # shellcheck disable=SC1090
  source "$ROS_SETUP"
  if python3 -c "import rclpy" 2>/dev/null; then
    log "rclpy OK"
  else
    log "WARNING: rclpy not importable — check ROS2 Python path"
  fi
  if python3 -c "from nav2_simple_commander.robot_navigator import BasicNavigator" 2>/dev/null; then
    log "nav2_simple_commander OK"
  else
    log "WARNING: nav2_simple_commander missing — install nav2 or build from source"
  fi
fi

log "Jetson setup complete"
log ""
log "To start GHOST:"
log "  cd $GHOST_DIR && bash jetson/start.sh"
