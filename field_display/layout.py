"""
layout.py — every pixel region on the screen, computed from the screen size.

No other file uses raw pixel numbers for placement. If the screen changes,
only DisplayProfile changes and this recomputes everything.

Landscape 320 x 240, top to bottom:
    picture area   the icon
    prompt         the question text
    arrow row      small triangles pointing down at each button
    answer row     SEVERE | BAD | OK | FINE   (one column per button)
    nav row        ◀ | HOLD | NEXT | n/x
"""

from PIL import ImageFont

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def load_font(size_in_pixels):
    try:
        return ImageFont.truetype(FONT_PATH, size_in_pixels)
    except OSError:
        return ImageFont.load_default()


class Layout:
    BUTTON_COUNT = 4

    # Each band's share of the screen height. They add up to 1.0.
    PICTURE_SHARE = 0.54
    PROMPT_SHARE = 0.13
    ARROW_SHARE = 0.05
    ANSWER_SHARE = 0.15
    NAV_SHARE = 0.13

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.column_width = width // self.BUTTON_COUNT

        band_top = 0
        self.picture_area = (0, band_top, width, band_top + round(height * self.PICTURE_SHARE))
        band_top = self.picture_area[3]
        self.prompt_area = (0, band_top, width, band_top + round(height * self.PROMPT_SHARE))
        band_top = self.prompt_area[3]
        self.arrow_area = (0, band_top, width, band_top + round(height * self.ARROW_SHARE))
        band_top = self.arrow_area[3]
        self.answer_area = (0, band_top, width, band_top + round(height * self.ANSWER_SHARE))
        band_top = self.answer_area[3]
        self.nav_area = (0, band_top, width, height)

        # Situation (map) page: square-ish map on the left, text panel on the right, nav row below.
        nav_top = self.nav_area[1]
        map_width = round(width * 0.62)
        self.map_area = (0, 0, map_width, nav_top)
        self.panel_area = (map_width, 0, width, nav_top)
        self.small_font = load_font(round(height * 0.048))
        self.panel_font = load_font(round(height * 0.052))

        self.prompt_font_size = round(height * 0.10)
        self.answer_font = load_font(round(height * 0.058))
        self.nav_font = load_font(round(height * 0.058))
        self.title_font = load_font(round(height * 0.11))
        self.body_font = load_font(round(height * 0.065))

    def column(self, button_index):
        """Left and right x of the column above one button."""
        left = button_index * self.column_width
        return left, left + self.column_width

    def column_center_x(self, button_index):
        left, right = self.column(button_index)
        return (left + right) // 2

    @staticmethod
    def center_of(area):
        left, top, right, bottom = area
        return (left + right) // 2, (top + bottom) // 2

    def fitted_prompt_font(self, pen, text):
        """Largest font (up to prompt_font_size) that fits the text across the screen."""
        size = self.prompt_font_size
        font = load_font(size)
        while pen.textlength(text, font=font) > self.width - 12 and size > 10:
            size -= 1
            font = load_font(size)
        return font
