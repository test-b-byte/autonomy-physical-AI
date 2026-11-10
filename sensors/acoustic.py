"""
Acoustic sensor — microphone VAD in human voice band (85–255 Hz).
Hardware: PyAudio, 16-kHz mono, 512-sample chunks.
Stub: probabilistic detection based on distance.
"""
import math, random
from dataclasses import dataclass

@dataclass
class AcousticReading:
    detection:  bool
    confidence: float
    dominant_hz: float = 0.0   # peak frequency if detected

_RATE      = 16_000
_CHUNK     = 512
_FREQ_LO   = 85.0    # Hz — lower bound human fundamental
_FREQ_HI   = 255.0   # Hz — upper bound
_THRESHOLD = 0.015   # normalised energy threshold
_MAX_RANGE = 20.0
_PEAK_PD   =  0.75

try:
    import pyaudio as _pa
    import numpy as _np
    _HW = True
except ImportError:
    _HW = False

try:
    import numpy as _np
    _NP = True
except ImportError:
    _NP = False


class AcousticSensor:
    def __init__(self):
        self._robot_x   = 0.0
        self._robot_y   = 0.0
        self._subject_x = 20.0
        self._subject_y = 20.0
        self._hw        = False
        self._stream    = None

        if _HW:
            try:
                self._audio  = _pa.PyAudio()
                self._stream = self._audio.open(
                    format=_pa.paInt16, channels=1, rate=_RATE,
                    input=True, frames_per_buffer=_CHUNK,
                )
                self._hw = True
            except Exception as e:
                print(f"[Acoustic] hw init failed ({e}) — stub mode")

    def update_robot_pos(self, x: float, y: float) -> None:
        self._robot_x = x
        self._robot_y = y

    def read(self) -> AcousticReading:
        return self._read_hw() if self._hw else self._read_stub()

    # ── hardware ─────────────────────────────────────────────────────────────

    def _read_hw(self) -> AcousticReading:
        raw     = self._stream.read(_CHUNK, exception_on_overflow=False)
        samples = _np.frombuffer(raw, dtype=_np.int16).astype(_np.float32) / 32768.0
        fft     = _np.abs(_np.fft.rfft(samples))
        freqs   = _np.fft.rfftfreq(_CHUNK, d=1.0 / _RATE)

        band_mask  = (freqs >= _FREQ_LO) & (freqs <= _FREQ_HI)
        band_power = fft[band_mask].mean() if band_mask.any() else 0.0
        total      = fft.mean() + 1e-9
        ratio      = band_power / total

        if ratio < _THRESHOLD:
            return AcousticReading(detection=False, confidence=0.0)

        dominant = float(freqs[band_mask][fft[band_mask].argmax()])
        conf     = min(ratio / (_THRESHOLD * 5), 0.95)
        return AcousticReading(detection=True, confidence=conf, dominant_hz=dominant)

    # ── stub ─────────────────────────────────────────────────────────────────

    def _read_stub(self) -> AcousticReading:
        dist = math.hypot(self._robot_x - self._subject_x,
                          self._robot_y - self._subject_y)
        if dist > _MAX_RANGE:
            return AcousticReading(detection=False, confidence=0.0)
        pd  = _PEAK_PD * (1.0 - (dist / _MAX_RANGE) ** 2)
        det = random.random() < pd
        conf = random.uniform(0.60, 0.85) if det else 0.0
        hz   = random.uniform(_FREQ_LO, _FREQ_HI) if det else 0.0
        return AcousticReading(detection=det, confidence=conf, dominant_hz=hz)

    def close(self) -> None:
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._hw:
            self._audio.terminate()
