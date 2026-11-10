#!/usr/bin/env bash
# Fetch the person-detector models into models/ (gitignored).
#
#   Hailo:  links the YOLOv8 .hef that the hailo-models package installs
#           (pi/hailo_setup.sh install) — nothing to download.
#   CPU:    exports yolov8n.onnx with ultralytics in a throwaway venv.  Works
#           on the Pi or on a laptop (then scp models/yolov8n.onnx to the Pi).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODELS="$ROOT/models"
mkdir -p "$MODELS"

# Hailo model, if the system package is installed
for hef in /usr/share/hailo-models/yolov8s_h8l.hef /usr/share/hailo-models/yolov8s_h8.hef \
           /usr/share/hailo-models/yolov8s.hef; do
  if [ -f "$hef" ]; then
    ln -sf "$hef" "$MODELS/$(basename "$hef")"
    echo "[models] Hailo: $(basename "$hef")"
    break
  fi
done

# CPU fallback
if [ ! -f "$MODELS/yolov8n.onnx" ]; then
  echo "[models] exporting yolov8n.onnx (one-off, ~1 min)"
  VENV="$(mktemp -d)"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q ultralytics onnx onnxslim
  (cd "$MODELS" && "$VENV/bin/python" - <<'EOF'
from ultralytics import YOLO
YOLO("yolov8n.pt").export(format="onnx", imgsz=640, opset=12, simplify=True)
EOF
  )
  rm -rf "$VENV" "$MODELS/yolov8n.pt"
fi
ls -la "$MODELS"
python3 - <<EOF
try:
    import onnxruntime as ort
    s = ort.InferenceSession("$MODELS/yolov8n.onnx", providers=["CPUExecutionProvider"])
    print("[models] yolov8n.onnx loads; input", s.get_inputs()[0].shape)
except Exception as e:
    print("[models] could not test-load the ONNX model:", e)
EOF
