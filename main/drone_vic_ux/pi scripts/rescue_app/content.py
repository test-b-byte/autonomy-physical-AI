"""
content.py — WHAT the app asks. Edit this file to change questions, their order,
or the answer scale; no other file needs to change.
"""

from dataclasses import dataclass

from icons import (ArmsIcon, BloodIcon, BreathingIcon, HeadIcon, Icon, SafeToMoveIcon,
                   TemperatureIcon, WalkIcon)


@dataclass(frozen=True)
class SeverityLevel:
    label: str
    color: tuple
    needs_attention: bool     # True = rescuers should be told about this answer


# Left to right, one per button. The button index (0-3) is the value saved.
SEVERITY_SCALE = (
    SeverityLevel("SEVERE", (200, 30, 30), True),     # button 0  (GPIO 17)
    SeverityLevel("BAD", (235, 120, 20), True),       # button 1  (GPIO 22)
    SeverityLevel("OK", (215, 185, 25), False),       # button 2  (GPIO 23)
    SeverityLevel("FINE", (40, 155, 60), False),      # button 3  (GPIO 27)
)


@dataclass(frozen=True)
class Question:
    key: str              # short name saved in the report
    prompt: str           # text shown on screen
    rescuer_text: str     # how the answer reads to rescuers, e.g. "Bleeding: SEVERE"
    icon: Icon


# Asked in this order. Most life-threatening first.
QUESTIONS = (
    Question("bleeding", "BLOOD LOSS?", "Bleeding", BloodIcon()),
    Question("breathing", "BREATHING?", "Breathing injury", BreathingIcon()),
    Question("head", "HEAD WOUND?", "Head wound", HeadIcon()),
    Question("cold", "COLD?", "Cold / freezing", TemperatureIcon()),
    Question("walk", "CAN YOU WALK?", "Walking", WalkIcon()),
    Question("arms", "ARMS HURT?", "Arm injury", ArmsIcon()),
    Question("safe_to_move", "SAFE TO MOVE?", "Safe to move", SafeToMoveIcon()),
)
