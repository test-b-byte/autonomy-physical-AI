"""
events.py — ButtonEvent, kept separate from hardware.py so pages can use it
without needing the Pi's GPIO libraries (lets --preview run on a Mac).
"""

from dataclasses import dataclass

TAP = "tap"
HOLD = "hold"


@dataclass(frozen=True)
class ButtonEvent:
    button_index: int      # 0 = leftmost button ... 3 = rightmost
    kind: str              # TAP or HOLD
