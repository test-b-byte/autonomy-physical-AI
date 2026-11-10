"""
Computer-vision sensor — YOLOv8 person detection on the Pi.

Frames come from, in order of preference:
  1. the Jetson's depth camera, forwarded by jetson/frame_server.py
     (set GHOST_FRAMES=tcp://<jetson-ip>:5555)
  2. a local camera (GHOST_CAMERA=<index>, default 0)
Inference runs on the Hailo AI HAT if present, else ONNX on the CPU
(sensors/detector.py).  With no frames or no model the sensor is a stub.

A reading with valid=False (no fresh frame) carries no evidence and should
not be sent to the core — an old frame says nothing about here and now.
"""
import math
import os
import random
import struct
import time
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class VisionReading:
    detection:  bool
    confidence: float
    bbox:       Optional[Tuple[float, float, float, float]] = None   # xyxy, normalised
    valid:      bool = True

_MAX_RANGE  = 15.0
_PEAK_PD    =  0.85
FRAME_MAX_AGE_S = 1.0


class _ZmqFrames:
    def __init__(self, url: str) -> None:
        import zmq
        self._sock = zmq.Context.instance().socket(zmq.SUB)
        self._sock.setsockopt(zmq.CONFLATE, 1)            # newest frame only
        self._sock.setsockopt(zmq.SUBSCRIBE, b"")
        self._sock.connect(url)
        self._zmq = zmq
        self._t_rx = 0.0

    def latest(self):
        """Newest JPEG bytes, or None if nothing fresh."""
        try:
            msg = self._sock.recv(self._zmq.NOBLOCK)
        except self._zmq.Again:
            return None
        if len(msg) <= 8:
            return None
        self._t_rx = time.monotonic()
        _stamp = struct.unpack("<d", msg[:8])[0]
        return msg[8:]

    def stale(self) -> bool:
        return time.monotonic() - self._t_rx > FRAME_MAX_AGE_S

    def close(self) -> None:
        self._sock.close()


class _LocalCamera:
    def __init__(self, index: int) -> None:
        import cv2
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError(f"camera {index} not found")

    def latest(self):
        ok, frame = self._cap.read()
        return frame if ok else None

    def stale(self) -> bool:
        return False

    def close(self) -> None:
        self._cap.release()


class VisionSensor:
    def __init__(self, frames: Optional[str] = None, camera_index: Optional[int] = None):
        self._robot_x = self._robot_y = 0.0
        self._subject_x = self._subject_y = 20.0
        self._hw = False
        self._src = None
        self._det = None
        frames = frames or os.environ.get("GHOST_FRAMES")
        cam = camera_index if camera_index is not None else os.environ.get("GHOST_CAMERA")
        try:
            from detector import PersonDetector
            det = PersonDetector()
            if not det.available:
                raise RuntimeError("no YOLO model (run pi/get_models.sh)")
            if frames:
                self._src = _ZmqFrames(frames)
            else:
                self._src = _LocalCamera(int(cam or 0))
            self._det, self._hw = det, True
            print(f"[Vision] {det.backend} on {frames or f'camera {cam or 0}'}")
        except Exception as e:
            print(f"[Vision] hw init failed ({e}) — stub mode")

    @property
    def hardware(self) -> bool:
        return self._hw

    def update_robot_pos(self, x: float, y: float) -> None:
        self._robot_x, self._robot_y = x, y

    def read(self) -> VisionReading:
        return self._read_hw() if self._hw else self._read_stub()

    # ── hardware ─────────────────────────────────────────────────────────────

    def _read_hw(self) -> VisionReading:
        img = self._src.latest()
        if img is None:
            return VisionReading(False, 0.0, valid=False)     # no fresh frame: no evidence
        dets = self._det.detect(img)
        if not dets:
            return VisionReading(False, 0.0)
        conf, box = dets[0]
        return VisionReading(True, conf, box)

    # ── stub ─────────────────────────────────────────────────────────────────

    def _read_stub(self) -> VisionReading:
        dist = math.hypot(self._robot_x - self._subject_x, self._robot_y - self._subject_y)
        if dist > _MAX_RANGE:
            return VisionReading(detection=False, confidence=0.0)
        pd  = _PEAK_PD * (1.0 - (dist / _MAX_RANGE) ** 2)
        det = random.random() < pd
        return VisionReading(detection=det, confidence=random.uniform(0.75, 0.92) if det else 0.0)

    def release(self) -> None:
        if self._src:
            self._src.close()
        if self._det:
            self._det.close()
