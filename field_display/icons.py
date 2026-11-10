"""
icons.py — one picture per medical question, drawn from simple shapes.

Icon is the parent: every icon has draw(picture, pen, box), where box is the
(left, top, right, bottom) area it must fit inside. Each icon scales itself to
the box, so the same icon works at any screen size.
"""

import math
from abc import ABC, abstractmethod

from PIL import Image, ImageChops, ImageDraw

INK = (20, 20, 20)
BLOOD_RED = (210, 25, 35)
WATER_BLUE = (30, 140, 220)


def draw_arrow(pen, tail, tip, color, line_width=4):
    """Line from tail to tip with a filled arrowhead at the tip."""
    pen.line([tail, tip], fill=color, width=line_width)
    angle = math.atan2(tip[1] - tail[1], tip[0] - tail[0])
    head_length = line_width * 3
    pen.polygon([tip,
                 (tip[0] - head_length * math.cos(angle - 0.5), tip[1] - head_length * math.sin(angle - 0.5)),
                 (tip[0] - head_length * math.cos(angle + 0.5), tip[1] - head_length * math.sin(angle + 0.5))],
                fill=color)


def draw_drop(pen, center_x, center_y, radius, color):
    """Round bottom (circle) + pointed top (triangle)."""
    pen.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), fill=color)
    pen.polygon([(center_x - radius * 0.95, center_y - radius * 0.3),
                 (center_x + radius * 0.95, center_y - radius * 0.3),
                 (center_x, center_y - radius * 2.1)], fill=color)


class Icon(ABC):
    """Parent for all question pictures. Subclasses only implement _draw_centered."""

    def draw(self, picture, pen, box):
        left, top, right, bottom = box
        center_x, center_y = (left + right) / 2, (top + bottom) / 2
        half_size = min(right - left, bottom - top) * 0.45      # leave a margin inside the box
        self._draw_centered(picture, pen, center_x, center_y, half_size)

    @abstractmethod
    def _draw_centered(self, picture, pen, center_x, center_y, s):
        """s = half the icon's size. All coordinates are fractions of s from the center."""


class WalkIcon(Icon):
    """Stick figure mid-stride, red arrow at the knee: 'can you walk?'"""

    def _draw_centered(self, picture, pen, cx, cy, s):
        stroke = max(4, int(s * 0.09))
        head_r = s * 0.16
        shoulder, hip = (cx, cy - s * 0.40), (cx - s * 0.05, cy + s * 0.10)
        knee = (cx + s * 0.28, cy + s * 0.35)
        pen.ellipse((cx - head_r, cy - s * 0.62 - head_r, cx + head_r, cy - s * 0.62 + head_r), outline=INK, width=stroke)
        pen.line([shoulder, hip], fill=INK, width=stroke)
        pen.line([shoulder, (cx - s * 0.38, cy - s * 0.12)], fill=INK, width=stroke)
        pen.line([shoulder, (cx + s * 0.32, cy - s * 0.05)], fill=INK, width=stroke)
        pen.line([hip, knee, (cx + s * 0.22, cy + s * 0.72)], fill=INK, width=stroke, joint="curve")
        pen.line([hip, (cx - s * 0.42, cy + s * 0.68)], fill=INK, width=stroke)
        draw_arrow(pen, (knee[0] + s * 0.42, knee[1] - s * 0.30), (knee[0] + s * 0.10, knee[1] - s * 0.04), BLOOD_RED)


class BloodIcon(Icon):
    """Heart with its lower part filled red, one drop falling: 'are you losing blood?'"""

    def _draw_centered(self, picture, pen, cx, cy, s):
        heart_cy = cy - s * 0.15
        scale = (s * 1.3) / 34.0
        outline = []
        for step in range(120):
            t = 2 * math.pi * step / 120
            curve_x = 16 * math.sin(t) ** 3
            curve_y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            outline.append((cx + curve_x * scale, heart_cy - curve_y * scale))
        heart_top = min(point[1] for point in outline)
        heart_bottom = max(point[1] for point in outline)
        fill_line_y = heart_top + (heart_bottom - heart_top) * 0.45
        fill_mask = Image.new("L", picture.size, 0)
        mask_pen = ImageDraw.Draw(fill_mask)
        mask_pen.polygon(outline, fill=255)
        mask_pen.rectangle((0, 0, picture.size[0], fill_line_y), fill=0)   # erase the top part
        picture.paste(BLOOD_RED, (0, 0, picture.size[0], picture.size[1]), fill_mask)
        pen.polygon(outline, outline=BLOOD_RED, width=4)
        draw_drop(pen, cx, heart_bottom + s * 0.38, s * 0.11, BLOOD_RED)


class ArmsIcon(Icon):
    """Stick figure, arms out, red arrows at both arms: 'are your arms OK?'"""

    def _draw_centered(self, picture, pen, cx, cy, s):
        stroke = max(4, int(s * 0.09))
        head_r = s * 0.16
        shoulder, hip = (cx, cy - s * 0.38), (cx, cy + s * 0.15)
        pen.ellipse((cx - head_r, cy - s * 0.62 - head_r, cx + head_r, cy - s * 0.62 + head_r), outline=INK, width=stroke)
        pen.line([shoulder, hip], fill=INK, width=stroke)
        pen.line([(cx - s * 0.55, cy - s * 0.15), shoulder, (cx + s * 0.55, cy - s * 0.15)], fill=INK, width=stroke, joint="curve")
        pen.line([(cx - s * 0.35, cy + s * 0.72), hip, (cx + s * 0.35, cy + s * 0.72)], fill=INK, width=stroke, joint="curve")
        draw_arrow(pen, (cx - s * 0.75, cy - s * 0.72), (cx - s * 0.42, cy - s * 0.34), BLOOD_RED)
        draw_arrow(pen, (cx + s * 0.75, cy - s * 0.72), (cx + s * 0.42, cy - s * 0.34), BLOOD_RED)


class FoodWaterIcon(Icon):
    """Red stomach, half full, and a blue water drop: 'are you hungry or thirsty?'"""

    def _draw_centered(self, picture, pen, cx, cy, s):
        stomach_box = (cx - s * 0.85, cy - s * 0.45, cx + s * 0.15, cy + s * 0.30)
        pen.chord(stomach_box, start=0, end=180, fill=BLOOD_RED)
        pen.ellipse(stomach_box, outline=BLOOD_RED, width=5)
        pen.line([(cx, cy - s * 0.38), (cx + s * 0.07, cy - s * 0.85)], fill=BLOOD_RED, width=5)
        pen.line([(cx - s * 0.77, cy + s * 0.10), (cx - s * 0.83, cy + s * 0.55)], fill=BLOOD_RED, width=5)
        draw_drop(pen, cx + s * 0.55, cy + s * 0.30, s * 0.28, WATER_BLUE)


class HeadIcon(Icon):
    """Frowning face with a red bandage that stops at the edge of the head: 'is your head hurt?'"""

    def _draw_centered(self, picture, pen, cx, cy, s):
        face_r = s * 0.70
        face_box = (cx - face_r, cy - face_r, cx + face_r, cy + face_r)
        pen.ellipse(face_box, outline=INK, width=4)
        eye_r = s * 0.06
        for eye_x in (cx - s * 0.25, cx + s * 0.25):
            pen.ellipse((eye_x - eye_r, cy - eye_r, eye_x + eye_r, cy + eye_r), fill=INK)
        pen.arc((cx - s * 0.25, cy + s * 0.25, cx + s * 0.25, cy + s * 0.58), start=200, end=340, width=4, fill=INK)
        bandage_mask = Image.new("L", picture.size, 0)
        bandage_pen = ImageDraw.Draw(bandage_mask)
        bandage_pen.line([(cx - s * 0.85, cy - s * 0.22), (cx + s * 0.75, cy - s * 0.70)], fill=255, width=7)
        bandage_pen.line([(cx - s * 0.80, cy - s * 0.02), (cx + s * 0.78, cy - s * 0.50)], fill=255, width=7)
        face_mask = Image.new("L", picture.size, 0)
        ImageDraw.Draw(face_mask).ellipse(face_box, fill=255)
        picture.paste(BLOOD_RED, (0, 0, picture.size[0], picture.size[1]), ImageChops.multiply(bandage_mask, face_mask))


LUNG_PINK = (245, 170, 180)
ICE_BLUE = (60, 150, 230)
WARNING_ORANGE = (235, 120, 20)


class BreathingIcon(Icon):
    """Two lungs on a windpipe, one with a red injury mark, air arrows going in: 'trouble breathing?'"""

    def _draw_centered(self, picture, pen, cx, cy, s):
        lung_top, lung_bottom = cy - s * 0.35, cy + s * 0.70
        left_lung = (cx - s * 0.75, lung_top, cx - s * 0.08, lung_bottom)
        right_lung = (cx + s * 0.08, lung_top, cx + s * 0.75, lung_bottom)
        for lung_box in (left_lung, right_lung):
            pen.ellipse(lung_box, fill=LUNG_PINK, outline=BLOOD_RED, width=4)
        windpipe_split = (cx, cy - s * 0.30)
        pen.line([(cx, cy - s * 0.72), windpipe_split], fill=INK, width=5)                        # windpipe
        pen.line([windpipe_split, (cx - s * 0.30, cy - s * 0.05)], fill=INK, width=4)             # left branch
        pen.line([windpipe_split, (cx + s * 0.30, cy - s * 0.05)], fill=INK, width=4)             # right branch
        pen.line([(cx + s * 0.30, cy + s * 0.15), (cx + s * 0.45, cy + s * 0.30), (cx + s * 0.32, cy + s * 0.40),
                  (cx + s * 0.50, cy + s * 0.55)], fill=BLOOD_RED, width=5)                       # injury mark
        draw_arrow(pen, (cx - s * 0.55, cy - s * 0.72), (cx - s * 0.12, cy - s * 0.55), ICE_BLUE, line_width=3)
        draw_arrow(pen, (cx + s * 0.55, cy - s * 0.72), (cx + s * 0.12, cy - s * 0.55), ICE_BLUE, line_width=3)


class TemperatureIcon(Icon):
    """Thermometer nearly empty (blue = cold) next to a snowflake: 'are you cold / freezing?'"""

    def _draw_centered(self, picture, pen, cx, cy, s):
        tube_x = cx - s * 0.35
        tube_half_width = s * 0.11
        tube_top, tube_bottom = cy - s * 0.80, cy + s * 0.45
        bulb_r = s * 0.24
        pen.rounded_rectangle((tube_x - tube_half_width, tube_top, tube_x + tube_half_width, tube_bottom + bulb_r * 0.5),
                              radius=tube_half_width, outline=INK, width=4, fill=(255, 255, 255))
        pen.ellipse((tube_x - bulb_r, tube_bottom, tube_x + bulb_r, tube_bottom + 2 * bulb_r), fill=ICE_BLUE, outline=INK, width=4)
        pen.rectangle((tube_x - tube_half_width * 0.45, cy + s * 0.15, tube_x + tube_half_width * 0.45, tube_bottom + bulb_r),
                      fill=ICE_BLUE)                                                               # low liquid level
        for mark_step in range(5):                                                                 # scale ticks
            mark_y = tube_top + s * 0.18 + mark_step * s * 0.22
            pen.line([(tube_x + tube_half_width, mark_y), (tube_x + tube_half_width + s * 0.10, mark_y)], fill=INK, width=2)

        flake_cx, flake_cy, flake_r = cx + s * 0.42, cy - s * 0.10, s * 0.42
        for arm_step in range(6):                                                                  # 6 arms, 60° apart
            angle = math.radians(arm_step * 60)
            tip = (flake_cx + flake_r * math.cos(angle), flake_cy + flake_r * math.sin(angle))
            pen.line([(flake_cx, flake_cy), tip], fill=ICE_BLUE, width=4)
            branch_base = (flake_cx + flake_r * 0.6 * math.cos(angle), flake_cy + flake_r * 0.6 * math.sin(angle))
            for side in (-0.6, 0.6):                                                               # little V on each arm
                branch_tip = (branch_base[0] + flake_r * 0.3 * math.cos(angle + side),
                              branch_base[1] + flake_r * 0.3 * math.sin(angle + side))
                pen.line([branch_base, branch_tip], fill=ICE_BLUE, width=3)


class SafeToMoveIcon(Icon):
    """
    Warning sign above three small threat pictures: fire, predator (paw print), hostile person.
    Asks: 'is there danger around you — is it safe to move?'
    """

    def _draw_centered(self, picture, pen, cx, cy, s):
        # Warning triangle with "!" on top
        triangle = [(cx, cy - s * 0.95), (cx - s * 0.36, cy - s * 0.32), (cx + s * 0.36, cy - s * 0.32)]
        pen.polygon(triangle, fill=(255, 225, 120), outline=WARNING_ORANGE, width=4)
        pen.line([(cx, cy - s * 0.76), (cx, cy - s * 0.52)], fill=INK, width=5)
        dot_r = s * 0.045
        pen.ellipse((cx - dot_r, cy - s * 0.43 - dot_r, cx + dot_r, cy - s * 0.43 + dot_r), fill=INK)

        threat_y = cy + s * 0.40          # the three small threats sit in a row below
        threat_size = s * 0.32
        self._draw_fire(pen, cx - s * 0.72, threat_y, threat_size)
        self._draw_paw(pen, cx, threat_y, threat_size)
        self._draw_hostile_person(pen, cx + s * 0.72, threat_y, threat_size)

    @staticmethod
    def _draw_fire(pen, center_x, center_y, size):
        """Three stacked flame shapes: red outside, orange, yellow core."""
        for scale, color in ((1.0, (215, 40, 20)), (0.68, (245, 140, 20)), (0.38, (255, 220, 60))):
            half_width = size * 0.55 * scale
            base_y = center_y + size * 0.75
            pen.ellipse((center_x - half_width, base_y - half_width * 1.6, center_x + half_width, base_y), fill=color)
            pen.polygon([(center_x - half_width * 0.95, base_y - half_width * 0.9),
                         (center_x + half_width * 0.95, base_y - half_width * 0.9),
                         (center_x + half_width * 0.15, base_y - half_width * 3.0)], fill=color)

    @staticmethod
    def _draw_paw(pen, center_x, center_y, size):
        """Animal paw print: one big pad and four toes."""
        paw_brown = (110, 70, 40)
        pad_w, pad_h = size * 0.55, size * 0.45
        pad_center_y = center_y + size * 0.35
        pen.ellipse((center_x - pad_w, pad_center_y - pad_h, center_x + pad_w, pad_center_y + pad_h), fill=paw_brown)
        toe_r = size * 0.20
        for toe_x, toe_y in ((-0.62, -0.30), (-0.22, -0.62), (0.22, -0.62), (0.62, -0.30)):
            toe_cx, toe_cy = center_x + toe_x * size, center_y + toe_y * size
            pen.ellipse((toe_cx - toe_r, toe_cy - toe_r * 1.2, toe_cx + toe_r, toe_cy + toe_r * 1.2), fill=paw_brown)

    @staticmethod
    def _draw_hostile_person(pen, center_x, center_y, size):
        """Dark silhouette with red eyes."""
        silhouette = (40, 40, 40)
        head_r = size * 0.32
        head_cy = center_y - size * 0.45
        pen.ellipse((center_x - head_r, head_cy - head_r, center_x + head_r, head_cy + head_r), fill=silhouette)
        pen.polygon([(center_x - size * 0.30, center_y - size * 0.10), (center_x + size * 0.30, center_y - size * 0.10),
                     (center_x + size * 0.65, center_y + size * 0.80), (center_x - size * 0.65, center_y + size * 0.80)],
                    fill=silhouette)
        eye_r = size * 0.07
        for eye_x in (center_x - head_r * 0.40, center_x + head_r * 0.40):
            pen.ellipse((eye_x - eye_r, head_cy - eye_r, eye_x + eye_r, head_cy + eye_r), fill=BLOOD_RED)
