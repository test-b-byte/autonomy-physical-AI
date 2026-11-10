"""
IR / PIR close-range sensor — digital GPIO pin on Raspberry Pi.
Stub: triggers inside 3 m with high probability.
"""
import math, random, time
from dataclasses import dataclass

@dataclass
class IRReading:
    detection:  bool
    confidence: float

_MAX_RANGE = 3.0
_PEAK_PD   = 0.95
_GPIO_PIN  = 17   # BCM pin — change to match your wiring

try:
    import RPi.GPIO as _gpio
    _HW = True
except (ImportError, RuntimeError):
    _HW = False


class IRSensor:
    def __init__(self, pin: int = _GPIO_PIN):
        self._pin       = pin
        self._robot_x   = 0.0
        self._robot_y   = 0.0
        self._subject_x = 20.0
        self._subject_y = 20.0
        self._hw        = False

        if _HW:
            try:
                _gpio.setmode(_gpio.BCM)
                _gpio.setup(pin, _gpio.IN, pull_up_down=_gpio.PUD_DOWN)
                self._hw = True
            except Exception as e:
                print(f"[IR] hw init failed ({e}) — stub mode")

    def update_robot_pos(self, x: float, y: float) -> None:
        self._robot_x = x
        self._robot_y = y

    def read(self) -> IRReading:
        return self._read_hw() if self._hw else self._read_stub()

    # ── hardware ─────────────────────────────────────────────────────────────

    def _read_hw(self) -> IRReading:
        level = _gpio.input(self._pin)
        return IRReading(detection=bool(level), confidence=0.95 if level else 0.0)

    # ── stub ─────────────────────────────────────────────────────────────────

    def _read_stub(self) -> IRReading:
        dist = math.hypot(self._robot_x - self._subject_x,
                          self._robot_y - self._subject_y)
        if dist > _MAX_RANGE:
            return IRReading(detection=False, confidence=0.0)
        pd  = _PEAK_PD * (1.0 - (dist / _MAX_RANGE) ** 2)
        det = random.random() < pd
        return IRReading(detection=det, confidence=0.95 if det else 0.0)

    def cleanup(self) -> None:
        if self._hw:
            _gpio.cleanup(self._pin)
