"""
Person detector — YOLOv8 on the Pi.

Backend is chosen at start-up:
  hailo  Hailo-8/8L AI HAT, if `hailo_platform` imports and a YOLOv8 .hef is
         found (models/*.hef, or the system hailo-models package)
  onnx   onnxruntime on the CPU with models/yolov8n.onnx (or yolov8s.onnx)
  none   neither available — `available` is False and the caller falls back

detect(image) takes JPEG bytes or a BGR numpy array and returns
[(confidence, (x1, y1, x2, y2))] for people, box normalised 0–1, best first.
Get the models with pi/get_models.sh.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models"
SYSTEM_HEFS = [Path("/usr/share/hailo-models")]
PERSON = 0                                   # COCO class id


def _nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    """Plain NMS on xyxy boxes; returns kept indices, best first."""
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area = lambda b: (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])
        ious = inter / (area(boxes[i]) + area(boxes[order[1:]]) - inter + 1e-9)
        order = order[1:][ious < iou]
    return keep


def decode_yolov8(out: np.ndarray, conf: float, iou: float, cls: int = PERSON):
    """Raw YOLOv8 head (1, 4+C, N) → [(score, xyxy)] in model-input pixels."""
    pred = out[0].T                                   # (N, 4+C)
    scores = pred[:, 4 + cls]
    m = scores >= conf
    if not m.any():
        return []
    cx, cy, w, h = pred[m, 0], pred[m, 1], pred[m, 2], pred[m, 3]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    s = scores[m]
    return [(float(s[i]), tuple(float(v) for v in boxes[i])) for i in _nms(boxes, s, iou)]


def parse_hailo_nms(raw, num_classes: int, cls: int = PERSON):
    """Hailo on-chip NMS output → [(score, (ymin, xmin, ymax, xmax))] normalised.
    Accepts a per-class list of (n, 5) arrays or the flat by-class buffer
    [n0, n0×5 values, n1, n1×5 values, …]."""
    if isinstance(raw, (list, tuple)) and raw and np.ndim(raw[0]) > 0:
        per_class = [np.asarray(a).reshape(-1, 5) for a in raw]
    else:
        flat, i, per_class = np.asarray(raw, dtype=np.float32).ravel(), 0, []
        for _ in range(num_classes):
            n = int(flat[i]); i += 1
            per_class.append(flat[i:i + 5 * n].reshape(n, 5)); i += 5 * n
    if cls >= len(per_class):
        return []
    return [(float(r[4]), (float(r[0]), float(r[1]), float(r[2]), float(r[3]))) for r in per_class[cls]]


class PersonDetector:
    def __init__(self, conf: float = 0.4, iou: float = 0.5, threads: int = 4) -> None:
        self.conf, self.iou = conf, iou
        self.size = 640
        self.backend = "none"
        hef = self._find(["*.hef"], [MODEL_DIR] + SYSTEM_HEFS, prefer="yolov8")
        if hef and self._try_hailo(hef):
            self.backend = "hailo"
        else:
            onnx = self._find(["yolov8n.onnx", "yolov8s.onnx", "*.onnx"], [MODEL_DIR])
            if onnx and self._try_onnx(onnx, threads):
                self.backend = "onnx"
        self.model = (hef if self.backend == "hailo" else onnx if self.backend == "onnx" else None)

    @property
    def available(self) -> bool:
        return self.backend != "none"

    @staticmethod
    def _find(patterns, dirs, prefer: str | None = None):
        for d in dirs:
            for pat in patterns:
                hits = sorted(d.glob(pat)) if d.exists() else []
                if prefer:
                    hits = sorted(hits, key=lambda p: prefer not in p.name)
                if hits:
                    return hits[0]
        return None

    def _try_hailo(self, hef: Path) -> bool:
        try:
            from hailo_platform import FormatType, HailoSchedulingAlgorithm, VDevice
            params = VDevice.create_params()
            params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
            self._stack = contextlib.ExitStack()
            dev = self._stack.enter_context(VDevice(params))
            model = dev.create_infer_model(str(hef))
            model.input().set_format_type(FormatType.UINT8)
            model.output().set_format_type(FormatType.FLOAT32)
            self._cfg = self._stack.enter_context(model.configure())
            self.size = model.input().shape[0]
            self._out = np.empty(model.output().shape, dtype=np.float32)
            return True
        except Exception as exc:
            print(f"[detector] Hailo unavailable ({exc}) — trying CPU")
            return False

    def _try_onnx(self, path: Path, threads: int) -> bool:
        try:
            import onnxruntime as ort
            so = ort.SessionOptions()
            so.intra_op_num_threads = threads
            self._sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
            self._inp = self._sess.get_inputs()[0].name
            self.size = int(self._sess.get_inputs()[0].shape[2] or 640)
            return True
        except Exception as exc:
            print(f"[detector] ONNX unavailable ({exc})")
            return False

    def _letterbox(self, img: np.ndarray):
        import cv2
        h, w = img.shape[:2]
        r = min(self.size / w, self.size / h)
        nw, nh = round(w * r), round(h * r)
        left, top = (self.size - nw) // 2, (self.size - nh) // 2
        canvas = np.full((self.size, self.size, 3), 114, np.uint8)
        canvas[top:top + nh, left:left + nw] = cv2.resize(img, (nw, nh))
        return np.ascontiguousarray(canvas[:, :, ::-1]), r, left, top   # → RGB

    def detect(self, image) -> list[tuple[float, tuple[float, float, float, float]]]:
        if not self.available:
            return []
        import cv2
        img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR) \
            if isinstance(image, (bytes, bytearray)) else image
        if img is None:
            return []
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)        # IR frames are mono
        oh, ow = img.shape[:2]
        rgb, r, left, top = self._letterbox(img)
        S = float(self.size)
        if self.backend == "hailo":
            b = self._cfg.create_bindings()
            b.input().set_buffer(rgb)
            b.output().set_buffer(self._out)
            self._cfg.run([b], 5000)
            dets = [(s, (x1 * S, y1 * S, x2 * S, y2 * S))
                    for s, (y1, x1, y2, x2) in parse_hailo_nms(b.output().get_buffer(), 80)
                    if s >= self.conf]
        else:
            x = rgb.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
            dets = decode_yolov8(self._sess.run(None, {self._inp: x})[0], self.conf, self.iou)
        out = []
        for s, (x1, y1, x2, y2) in sorted(dets, reverse=True):     # undo letterbox
            box = ((x1 - left) / r / ow, (y1 - top) / r / oh, (x2 - left) / r / ow, (y2 - top) / r / oh)
            out.append((s, tuple(float(np.clip(v, 0, 1)) for v in box)))
        return out

    def close(self) -> None:
        if self.backend == "hailo":
            self._stack.close()
