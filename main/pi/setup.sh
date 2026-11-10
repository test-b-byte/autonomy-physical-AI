#!/usr/bin/env bash
# GHOST Pi setup — run once on a fresh Raspberry Pi.
# Installs Python sensor deps and clones the repo.
#
# Usage:
#   bash pi/setup.sh
#   GHOST_HOST=10.1.200.x bash pi/setup.sh   # set Jetson IP for fusion.py

set -euo pipefail

GHOST_DIR="${GHOST_DIR:-$HOME/ghost}"
GHOST_REPO="${GHOST_REPO:-https://github.com/CodeMetalForge-Hackathon/Team-20.git}"
GHOST_BRANCH="${GHOST_BRANCH:-ghost}"
GHOST_HOST="${GHOST_HOST:-}"   # Jetson IP — set this

log() { echo "[setup] $*"; }

# ── clone repo ────────────────────────────────────────────────────────────────
if [ ! -d "$GHOST_DIR/.git" ]; then
  log "cloning $GHOST_REPO → $GHOST_DIR"
  git clone --branch "$GHOST_BRANCH" "$GHOST_REPO" "$GHOST_DIR"
else
  log "repo already at $GHOST_DIR — pulling"
  git -C "$GHOST_DIR" pull --ff-only
fi

# ── system packages ───────────────────────────────────────────────────────────
log "installing system packages"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  python3-pip python3-numpy python3-smbus \
  portaudio19-dev libportaudio2 \
  python3-rpi.gpio i2c-tools

# ── Python packages ───────────────────────────────────────────────────────────
log "installing Python packages"
PIP="pip3 install --break-system-packages"
$PIP "websockets>=11.0"
$PIP numpy opencv-python-headless

# Sensor hardware drivers
$PIP pyaudio                                         # microphone
$PIP smbus2                                          # I2C (IMU)
$PIP adafruit-circuitpython-mlx90640                 # thermal camera

# Vision: YOLOv8 runs on the Hailo AI HAT (pi/hailo_setup.sh) or ONNX on the
# CPU — no ultralytics needed at runtime.  Frames arrive from the Jetson over ZMQ.
$PIP onnxruntime pyzmq

# Operator link (LoRa)
$PIP meshtastic pypubsub

log "Python packages installed"

# ── models ────────────────────────────────────────────────────────────────────
bash "$GHOST_DIR/pi/get_models.sh" || log "WARNING: model download failed — vision runs as a stub until models/ has yolov8n.onnx or a .hef"

# ── I2C enable check ──────────────────────────────────────────────────────────
if i2cdetect -l 2>/dev/null | grep -q i2c; then
  log "I2C buses: $(i2cdetect -l | awk '{print $1}' | tr '\n' ' ')"
else
  log "WARNING: no I2C buses found — enable via raspi-config → Interfaces → I2C"
fi

# ── summary ───────────────────────────────────────────────────────────────────
log ""
log "Pi setup complete"
log ""
if [ -n "$GHOST_HOST" ]; then
  log "To start sensors (pointing at Jetson at $GHOST_HOST):"
  log "  cd $GHOST_DIR/sensors && GHOST_FRAMES=tcp://$GHOST_HOST:5555 python3 fusion.py --hardware --host $GHOST_HOST"
  log ""
  log "To start operator link (LoRa):"
  log "  python3 $GHOST_DIR/pi/operator_link.py --host $GHOST_HOST --allow '!abcd1234'"
else
  log "Set GHOST_HOST to your Jetson's IP, then:"
  log "  cd $GHOST_DIR/sensors && python3 fusion.py --hardware --host \$GHOST_HOST"
fi
