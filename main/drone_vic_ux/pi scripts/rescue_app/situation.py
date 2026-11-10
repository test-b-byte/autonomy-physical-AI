"""
situation.py — SituationPage: the map the lost person sees after the report is collected.

Shows, relative to YOU (center of the map):
    the drone, the rescue team / deployment point, known hazards, hostile positions,
    estimated distances (range rings + list), a compass, and which way the drone will fly.

Map style: drawn at half resolution, then scaled up 2x with no smoothing, which gives the
chunky pixel look. Icons blink at different rates, like a tactical display.
Symbols follow the common military convention: friendly = blue rectangle,
hostile = red diamond, hazard = orange triangle.

Heading: if a real heading is available (MapFileHeading), the map turns so the direction
the device faces is up ("MAG"). Otherwise north is up and the compass says "EST".
"""

import math
import time

from PIL import Image, ImageDraw

from map_data import DRONE, HAZARD, HOSTILE, TEAM
from pages import BACK, BACK_ARROW, NAV_GRAY, STAY, Page, draw_nav_row
from events import HOLD
from version import VERSION

CLOSE = "close"

MAP_GREEN = (8, 28, 14)
GRID_GREEN = (18, 55, 28)
RING_GREEN = (40, 120, 60)
TEXT_GREEN = (120, 230, 140)
FRIENDLY_BLUE = (80, 160, 255)
FRIENDLY_FILL = (20, 50, 110)
HOSTILE_RED = (235, 50, 50)
HAZARD_ORANGE = (245, 150, 20)
DRONE_CYAN = (60, 230, 230)
YOU_WHITE = (255, 255, 255)
NEEDLE_RED = (230, 40, 40)

KIND_COLORS = {TEAM: FRIENDLY_BLUE, DRONE: DRONE_CYAN, HAZARD: HAZARD_ORANGE, HOSTILE: HOSTILE_RED}
PANEL_ORDER = {TEAM: 0, DRONE: 1, HOSTILE: 2, HAZARD: 3}
NICE_RANGES_M = (25, 50, 100, 150, 250, 500, 1000, 2000, 5000, 10000)
PIXEL_SCALE = 2                     # map drawn at 1/2 resolution then enlarged = pixel look


def compass_word(bearing_degrees):
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((bearing_degrees + 22.5) % 360 // 45)]


def distance_text(meters):
    return f"{meters / 1000:.1f}km" if meters >= 1000 else f"{meters:.0f}m"


class SituationPage(Page):
    """
        hold button 1 (◀)  -> back to the report page
        otherwise: counts down auto_seconds, then the app closes and the drone heads to the team
    """

    auto_seconds = 20
    auto_action = CLOSE
    animated = True
    frame_interval_seconds = 0.25        # redraw 4x per second for the blinking
    MAP_REFRESH_SECONDS = 2.0

    def __init__(self, map_source, heading_source, page_count):
        self.map_source = map_source
        self.heading_source = heading_source
        self.page_count = page_count
        self.seconds_left = self.auto_seconds     # RescueApp updates these before each render
        self.clock = 0.0
        self.cached_state = None
        self.cached_at = -999.0

    # -- data ---------------------------------------------------------------

    def current_state(self):
        now = time.monotonic()
        if self.cached_state is None or now - self.cached_at >= self.MAP_REFRESH_SECONDS:
            self.cached_state = self.map_source.latest()
            self.cached_at = now
        return self.cached_state

    def is_visible(self, kind):
        """Blink pattern per kind: hostiles fast, hazards medium, team and drone slow."""
        if kind == HOSTILE:
            return int(self.clock * 3) % 2 == 0
        if kind == HAZARD:
            return int(self.clock * 2) % 2 == 0
        return (self.clock % 1.6) < 1.2

    # -- drawing ------------------------------------------------------------

    def render(self, layout, report):
        picture, pen = self.blank_picture(layout)
        map_state = self.current_state()
        heading_deg, heading_measured = self.heading_source.heading()

        map_left, map_top, map_right, map_bottom = layout.map_area
        low_width = (map_right - map_left) // PIXEL_SCALE
        low_height = (map_bottom - map_top) // PIXEL_SCALE
        low_map, range_m, ring_radius_px = self.draw_low_res_map(map_state, heading_deg, low_width, low_height)
        picture.paste(low_map.resize((low_width * PIXEL_SCALE, low_height * PIXEL_SCALE), Image.NEAREST),
                      (map_left, map_top))

        self.draw_map_overlay(pen, layout, heading_deg, heading_measured, range_m, ring_radius_px, map_state)
        self.draw_panel(pen, layout, map_state)

        draw_nav_row(pen, layout, [BACK_ARROW, "", "", ""])
        nav_middle_y = (layout.nav_area[1] + layout.nav_area[3]) // 2
        pen.rectangle((layout.column(1)[0] + 1, layout.nav_area[1], layout.column(3)[1] - 1, layout.nav_area[3]),
                      fill=NAV_GRAY)
        pen.text((layout.column(2)[0], nav_middle_y), f"DRONE RETURNING IN {self.seconds_left}s",
                 font=layout.nav_font, fill=(150, 20, 20), anchor="mm")
        return picture

    def draw_low_res_map(self, map_state, heading_deg, low_width, low_height):
        """The map itself at half resolution. Returns (image, range in meters, outer ring radius in low-res px)."""
        low_map = Image.new("RGB", (low_width, low_height), MAP_GREEN)
        pen = ImageDraw.Draw(low_map)
        center_x, center_y = low_width // 2, low_height // 2
        ring_radius_px = min(low_width, low_height) // 2 - 3

        farthest_m = max([map_state.distance_m(entity) for entity in map_state.others] + [map_state.uncertainty_m])
        range_m = next((nice for nice in NICE_RANGES_M if nice >= farthest_m * 1.1), NICE_RANGES_M[-1])
        meters_per_px = range_m / ring_radius_px

        if map_state.background:
            self.draw_background_image(low_map, map_state, heading_deg, meters_per_px)
        else:
            for grid_x in range(center_x % 10, low_width, 10):
                pen.line([(grid_x, 0), (grid_x, low_height)], fill=GRID_GREEN)
            for grid_y in range(center_y % 10, low_height, 10):
                pen.line([(0, grid_y), (low_width, grid_y)], fill=GRID_GREEN)

        for ring_fraction in (0.5, 1.0):
            radius = ring_radius_px * ring_fraction
            for dash_start in range(0, 360, 20):
                pen.arc((center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                        start=dash_start, end=dash_start + 10, fill=RING_GREEN)

        def to_screen(entity):
            # Turn the map so the device's facing direction is up:
            # rotate the (east, north) offset by the heading, then flip y for the screen.
            east, north = map_state.offset_from_you(entity)
            heading_rad = math.radians(heading_deg)
            right = east * math.cos(heading_rad) - north * math.sin(heading_rad)
            up = east * math.sin(heading_rad) + north * math.cos(heading_rad)
            return center_x + right / meters_per_px, center_y - up / meters_per_px

        team = map_state.team()
        if team and (self.clock % 1.0) < 0.7:                  # blinking dotted line: where the drone will fly
            team_x, team_y = to_screen(team)
            segment_count = max(2, int(math.hypot(team_x - center_x, team_y - center_y) // 4))
            for segment in range(1, segment_count - 1, 2):            # every other segment = dashed line
                start_fraction, end_fraction = segment / segment_count, (segment + 1) / segment_count
                pen.line([(center_x + (team_x - center_x) * start_fraction, center_y + (team_y - center_y) * start_fraction),
                          (center_x + (team_x - center_x) * end_fraction, center_y + (team_y - center_y) * end_fraction)],
                         fill=DRONE_CYAN)

        for entity in map_state.others:
            if self.is_visible(entity.kind):
                self.draw_symbol(pen, entity.kind, *to_screen(entity))

        uncertainty_px = max(4, map_state.uncertainty_m / meters_per_px)
        pulse = 0.8 + 0.2 * math.sin(self.clock * 4)
        radius = uncertainty_px * pulse
        for dash_start in range(0, 360, 45):
            pen.arc((center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                    start=dash_start, end=dash_start + 25, fill=YOU_WHITE)
        pen.rectangle((center_x - 1, center_y - 1, center_x + 1, center_y + 1), fill=YOU_WHITE)
        return low_map, range_m, ring_radius_px

    @staticmethod
    def draw_symbol(pen, kind, x, y):
        x, y = round(x), round(y)
        if kind == TEAM:
            pen.rectangle((x - 4, y - 3, x + 4, y + 3), fill=FRIENDLY_FILL, outline=FRIENDLY_BLUE)
        elif kind == HOSTILE:
            pen.polygon([(x, y - 4), (x + 4, y), (x, y + 4), (x - 4, y)], fill=HOSTILE_RED)
        elif kind == HAZARD:
            pen.polygon([(x, y - 4), (x + 4, y + 3), (x - 4, y + 3)], fill=HAZARD_ORANGE)
            pen.point((x, y + 1), fill=(0, 0, 0))
        elif kind == DRONE:
            pen.line([(x - 3, y - 3), (x + 3, y + 3)], fill=DRONE_CYAN)
            pen.line([(x - 3, y + 3), (x + 3, y - 3)], fill=DRONE_CYAN)

    @staticmethod
    def draw_background_image(low_map, map_state, heading_deg, meters_per_px):
        """Real map: crop the image around YOU, turn it to the heading, and scale it to the map."""
        background = map_state.background
        try:
            source_image = Image.open(background["image"]).convert("RGB")
        except OSError:
            return
        image_m_per_px = float(background["meters_per_pixel"])
        you_px = (source_image.width / 2 + (map_state.you.x - background.get("center_x", 0)) / image_m_per_px,
                  source_image.height / 2 - (map_state.you.y - background.get("center_y", 0)) / image_m_per_px)
        half_span_m = math.hypot(low_map.width, low_map.height) / 2 * meters_per_px     # covers corners after turning
        half_span_px = half_span_m / image_m_per_px
        crop = source_image.crop((you_px[0] - half_span_px, you_px[1] - half_span_px,
                                  you_px[0] + half_span_px, you_px[1] + half_span_px))
        crop = crop.rotate(heading_deg, resample=Image.BILINEAR, fillcolor=MAP_GREEN)
        crop_size_low = round(2 * half_span_m / meters_per_px)
        crop = crop.resize((crop_size_low, crop_size_low), Image.NEAREST)
        offset = ((crop_size_low - low_map.width) // 2, (crop_size_low - low_map.height) // 2)
        low_map.paste(crop.crop((offset[0], offset[1], offset[0] + low_map.width, offset[1] + low_map.height)), (0, 0))

    def draw_map_overlay(self, pen, layout, heading_deg, heading_measured, range_m, ring_radius_px, map_state):
        """Full-resolution text and compass drawn on top of the pixel map."""
        map_left, map_top, map_right, map_bottom = layout.map_area
        center_x = map_left + (map_right - map_left) // 2
        center_y = map_top + (map_bottom - map_top) // 2

        pen.text((center_x + 3, center_y - ring_radius_px * PIXEL_SCALE + 2), distance_text(range_m),
                 font=layout.small_font, fill=TEXT_GREEN, anchor="la")
        pen.text((center_x + 3, center_y - ring_radius_px * PIXEL_SCALE // 2 + 2), distance_text(range_m / 2),
                 font=layout.small_font, fill=TEXT_GREEN, anchor="la")

        compass_x, compass_y, compass_r = map_left + 26, map_top + 24, 12
        pen.ellipse((compass_x - compass_r, compass_y - compass_r, compass_x + compass_r, compass_y + compass_r),
                    outline=TEXT_GREEN, width=1)
        heading_rad = math.radians(heading_deg)
        north_dx, north_dy = -math.sin(heading_rad), -math.cos(heading_rad)     # where north is, on screen
        tip = (compass_x + north_dx * (compass_r - 2), compass_y + north_dy * (compass_r - 2))
        tail = (compass_x - north_dx * (compass_r - 6), compass_y - north_dy * (compass_r - 6))
        pen.line([tail, (compass_x, compass_y)], fill=TEXT_GREEN, width=2)
        pen.line([(compass_x, compass_y), tip], fill=NEEDLE_RED, width=3)
        label_point = (compass_x + north_dx * (compass_r + 7), compass_y + north_dy * (compass_r + 7))
        pen.text(label_point, "N", font=layout.small_font, fill=TEXT_GREEN, anchor="mm")
        source_text = "MAG" if heading_measured else "EST"
        pen.text((compass_x - compass_r, compass_y + compass_r + 12), f"{source_text} {heading_deg:03.0f}\u00b0",
                 font=layout.small_font, fill=TEXT_GREEN, anchor="lm")
        if map_state.is_estimate:
            pen.text((map_right - 4, map_bottom - 4), "EST POS", font=layout.small_font, fill=TEXT_GREEN, anchor="rb")

    def draw_panel(self, pen, layout, map_state):
        """Right-hand list: every item's distance and compass direction from YOU."""
        panel_left, panel_top, panel_right, panel_bottom = layout.panel_area
        pen.rectangle(layout.panel_area, fill=(14, 20, 16))
        text_x = panel_left + 6
        line_y = panel_top + 12
        pen.text((text_x, line_y), "SITREP", font=layout.panel_font, fill=TEXT_GREEN, anchor="lm")
        line_y += 16
        pen.text((text_x, line_y), f"YOU \u00b1{map_state.uncertainty_m:.0f}m", font=layout.panel_font,
                 fill=YOU_WHITE, anchor="lm")

        line_gap = (panel_bottom - line_y - 22) / max(len(map_state.others), 1)
        line_gap = min(line_gap, 26)
        for entity in sorted(map_state.others, key=lambda item: PANEL_ORDER.get(item.kind, 9)):
            line_y += line_gap
            color = KIND_COLORS.get(entity.kind, TEXT_GREEN)
            pen.rectangle((text_x, line_y - 9, text_x + 3, line_y - 3), fill=color)
            pen.text((text_x + 7, line_y - 6), entity.label, font=layout.panel_font, fill=color, anchor="lm")
            where = f"{distance_text(map_state.distance_m(entity))} {compass_word(map_state.bearing_deg(entity))}"
            pen.text((text_x + 7, line_y + 6), where, font=layout.panel_font, fill=(200, 200, 200), anchor="lm")

        pen.text((panel_right - 4, panel_bottom - 4), VERSION, font=layout.small_font, fill=(90, 110, 95), anchor="rb")

    def handle(self, event, report):
        if event.kind == HOLD and event.button_index == 0:
            return BACK
        return STAY
