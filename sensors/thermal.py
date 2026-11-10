"""
Thermal camera — MLX90640 32×24 IR array via I2C.
Stub: probabilistic detection based on distance to known subject position.
"""
import math, random
from dataclasses import dataclass, field
from typing import Optional, Tuple

@dataclass
class ThermalReading:
    detection:  bool
    confidence: float
    bbox:       Optional[Tuple[int,int,int,int]] = None   # x,y,w,h pixels

_HUMAN_MIN  = 34.0   # °C — attenuated body temp at sensor
_HUMAN_MAX  = 38.5
_BLOB_AREA  = 4      # min pixels
_MAX_RANGE  = 10.0   # metres — matches Rust sensor_model
_PEAK_PD    =  0.90

try:
    import board, busio
    import adafruit_mlx90640 as _mlx_mod
    _HW_THERMAL = True
except ImportError:
    _HW_THERMAL = False

try:
    import numpy as np
    import cv2
    _CV = True
except ImportError:
    _CV = False


class ThermalSensor:
    def __init__(self):
        self._robot_x = 0.0
        self._robot_y = 0.0
        self._subject_x = 20.0   # world metres — updated by fusion if known
        self._subject_y = 20.0
        self._hw = False

        if _HW_THERMAL:
            try:
                i2c = busio.I2C(board.SCL, board.SDA, frequency=400_000)
                self._cam = _mlx_mod.MLX90640(i2c)
                self._cam.refresh_rate = _mlx_mod.RefreshRate.REFRESH_4_HZ
                self._hw = True
            except Exception as e:
                print(f"[Thermal] hw init failed ({e}) — stub mode")

    def update_robot_pos(self, x: float, y: float) -> None:
        self._robot_x = x
        self._robot_y = y

    def read(self) -> ThermalReading:
        return self._read_hw() if self._hw else self._read_stub()

    # ── hardware ─────────────────────────────────────────────────────────────

    def _read_hw(self) -> ThermalReading:
        frame = [0.0] * 768
        self._cam.getFrame(frame)

        if not _CV:
            hot = [t for t in frame if _HUMAN_MIN <= t <= _HUMAN_MAX]
            det = len(hot) >= _BLOB_AREA
            return ThermalReading(detection=det, confidence=min(len(hot)/30.0, 0.95) if det else 0.0)

        arr  = np.array(frame, dtype=np.float32).reshape(24, 32)
        mask = ((arr >= _HUMAN_MIN) & (arr <= _HUMAN_MAX)).astype(np.uint8) * 255
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        blobs = [s for s in stats[1:] if s[cv2.CC_STAT_AREA] >= _BLOB_AREA]
        if not blobs:
            return ThermalReading(detection=False, confidence=0.0)

        best      = max(blobs, key=lambda s: s[cv2.CC_STAT_AREA])
        area_conf = min(best[cv2.CC_STAT_AREA] / 30.0, 1.0)
        mean_temp = arr[mask > 0].mean()
        temp_conf = max(1.0 - abs(mean_temp - 36.5) / 5.0, 0.0)
        conf      = min(0.6 * area_conf + 0.4 * temp_conf, 0.95)
        bbox      = (best[cv2.CC_STAT_LEFT], best[cv2.CC_STAT_TOP],
                     best[cv2.CC_STAT_WIDTH], best[cv2.CC_STAT_HEIGHT])
        return ThermalReading(detection=True, confidence=conf, bbox=bbox)

    # ── stub ─────────────────────────────────────────────────────────────────

    def _read_stub(self) -> ThermalReading:
        dist = math.hypot(self._robot_x - self._subject_x,
                          self._robot_y - self._subject_y)
        if dist > _MAX_RANGE:
            return ThermalReading(detection=False, confidence=0.0)
        pd  = _PEAK_PD * (1.0 - (dist / _MAX_RANGE) ** 2)
        det = random.random() < pd
        conf = random.uniform(0.70, 0.90) if det else 0.0
        return ThermalReading(detection=det, confidence=conf)
