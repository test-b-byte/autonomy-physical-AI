"""
Computer-vision sensor — YOLOv8-nano person detection.
Hardware: Pi 5 camera + AI HAT (runs at ~20 fps).
Stub: confirms with ~85 % probability once inside range.
"""
import math, random
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class VisionReading:
    detection:  bool
    confidence: float
    bbox:       Optional[Tuple[int,int,int,int]] = None   # xyxy

_MAX_RANGE = 15.0
_PEAK_PD   =  0.85

try:
    from ultralytics import YOLO as _YOLO
    import cv2 as _cv2
    _HW = True
except ImportError:
    _HW = False


class VisionSensor:
    def __init__(self, camera_index: int = 0):
        self._robot_x   = 0.0
        self._robot_y   = 0.0
        self._subject_x = 20.0
        self._subject_y = 20.0
        self._hw        = False

        if _HW:
            try:
                self._model = _YOLO("yolov8n.pt")
                self._cap   = _cv2.VideoCapture(camera_index)
                if not self._cap.isOpened():
                    raise RuntimeError("camera not found")
                self._hw = True
            except Exception as e:
                print(f"[Vision] hw init failed ({e}) — stub mode")

    def update_robot_pos(self, x: float, y: float) -> None:
        self._robot_x = x
        self._robot_y = y

    def read(self) -> VisionReading:
        return self._read_hw() if self._hw else self._read_stub()

    # ── hardware ─────────────────────────────────────────────────────────────

    def _read_hw(self) -> VisionReading:
        ok, frame = self._cap.read()
        if not ok:
            return VisionReading(detection=False, confidence=0.0)
        results = self._model(frame, classes=[0], verbose=False)   # class 0 = person
        boxes   = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return VisionReading(detection=False, confidence=0.0)
        best  = max(boxes, key=lambda b: float(b.conf))
        conf  = float(best.conf)
        xyxy  = tuple(int(v) for v in best.xyxy[0].tolist())
        return VisionReading(detection=True, confidence=conf, bbox=xyxy)

    # ── stub ─────────────────────────────────────────────────────────────────

    def _read_stub(self) -> VisionReading:
        dist = math.hypot(self._robot_x - self._subject_x,
                          self._robot_y - self._subject_y)
        if dist > _MAX_RANGE:
            return VisionReading(detection=False, confidence=0.0)
        pd  = _PEAK_PD * (1.0 - (dist / _MAX_RANGE) ** 2)
        det = random.random() < pd
        conf = random.uniform(0.75, 0.92) if det else 0.0
        return VisionReading(detection=det, confidence=conf)

    def release(self) -> None:
        if self._hw:
            self._cap.release()
