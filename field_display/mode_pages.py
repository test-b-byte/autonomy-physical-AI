"""
mode_pages.py — what the screen shows at the point of contact, once the mode is decided.

    ModeBriefPage     big colored briefing: what's happening and what to do
    EscortPage        map + route to the team, walking pace and ETA; PAUSE, DONE, HURT buttons
    ResponderMapPage  situation map while the drone flies home ("drone returning" countdown)
    StayHerePage      stay-put instructions, rotating survival tips, team ETA; screen off to save battery
    BeaconPage        emergency: the drone hovers at an offset and sends the person's relative location by
                      IR / optical Morse; shown live with the letter and dot/dash highlighted
    FriendlySignalPage  wait for the rescuers' recognition signal; HEARD IT logs the time and shows how to answer
"""

import math

from PIL import ImageDraw

from events import HOLD, TAP
from icons import WalkIcon
from modes import (ANSWER_TEXT, BEACON, BEACON_OFFSET_M, ESCORT, FRIENDLY_SIGNAL_COUNT, FRIENDLY_SIGNAL_TEXT,
                   MODE_STYLE, MORSE, RESPONDER, SWITCH_TO_RESPONDER, TEAM_SPEED_MPS, WALKING_SPEED_MPS,
                   beacon_message, morse_timeline)
from layout import load_font
from pages import BACK, BACK_ARROW, NAV_GRAY, NEXT, STAY, Page, draw_nav_row
from situation import CLOSE, SituationPage, compass_word, distance_text

INK = (20, 20, 20)
WHITE = (255, 255, 255)
MUTED = (110, 110, 110)
PANEL_DARK = (14, 20, 16)
TEXT_GREEN = (120, 230, 140)

BRIEF_LINES = {
    ESCORT: ["You can walk.", "Follow the drone", "to the rescue team.", "Go at your own pace.",
             "Stop if anything hurts."],
    RESPONDER: ["Stay where you are.", "The drone is flying back", "to bring the rescue team.",
                "Keep warm. Stay visible."],
    BEACON: ["Do not move.", "Drone moves close by", "and signals rescuers", "with your location.",
             "Wait for friendly signal."],
}

SURVIVAL_TIPS = [
    ("KEEP WARM", "Cover your head and body. Sit on a pack, not the ground."),
    ("STAY VISIBLE", "Open ground, bright clothing, spread items out."),
    ("SAVE ENERGY", "Rest. Sip water if you have it."),
    ("MAKE NOISE", "3 whistles or 3 shouts means: help."),
]


def nav_middle(pen, layout, text, color=MUTED):
    """Write text across the middle two nav cells (drawn after the nav row so it isn't covered)."""
    top, bottom = layout.nav_area[1], layout.nav_area[3]
    pen.rectangle((layout.column(1)[0] + 1, top, layout.column(2)[1] - 1, bottom), fill=NAV_GRAY)
    pen.text((layout.column(2)[0], (top + bottom) // 2), text, font=layout.nav_font, fill=color, anchor="mm")


def fitted_font(pen, lines, max_width, start_size):
    """Largest bold font (from start_size down) that fits every line within max_width."""
    size = start_size
    font = load_font(size)
    while size > 9 and max(pen.textlength(line, font=font) for line in lines) > max_width:
        size -= 1
        font = load_font(size)
    return font


def draw_drone(pen, center_x, center_y, size, color=(40, 40, 40)):
    """Simple quadcopter from above: X frame and four rotors."""
    arm = size * 0.5
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        pen.line([(center_x, center_y), (center_x + dx * arm, center_y + dy * arm)], fill=color, width=3)
        rotor = size * 0.22
        pen.ellipse((center_x + dx * arm - rotor, center_y + dy * arm - rotor,
                     center_x + dx * arm + rotor, center_y + dy * arm + rotor), outline=color, width=2)
    pen.rectangle((center_x - size * 0.12, center_y - size * 0.12, center_x + size * 0.12, center_y + size * 0.12), fill=color)


def draw_person(pen, base_x, base_y, height, color=INK):
    head = height * 0.16
    pen.ellipse((base_x - head, base_y - height, base_x + head, base_y - height + 2 * head), outline=color, width=3)
    neck, hip = (base_x, base_y - height + 2 * head), (base_x, base_y - height * 0.35)
    pen.line([neck, hip], fill=color, width=3)
    pen.line([(base_x - height * 0.25, base_y - height * 0.55), (base_x + height * 0.25, base_y - height * 0.55)], fill=color, width=3)
    pen.line([(base_x - height * 0.2, base_y), hip, (base_x + height * 0.2, base_y)], fill=color, width=3)


class ModeBriefPage(Page):
    """
    Colored briefing for the decided mode. Moves on by itself.
        tap any button   -> next
        hold button 1    -> back (to REPORT COLLECTED, to change an answer)
    """
    auto_seconds = 12
    auto_action = NEXT

    def __init__(self, mode):
        self.mode = mode
        self.seconds_left = self.auto_seconds

    def render(self, layout, report):
        picture, pen = self.blank_picture(layout)
        title, header_color, accent = MODE_STYLE[self.mode]
        header_bottom = round(layout.height * 0.19)
        pen.rectangle((0, 0, layout.width, header_bottom), fill=header_color)
        pen.text((layout.width // 2, header_bottom // 2), title, font=layout.title_font, fill=WHITE, anchor="mm")

        icon_box = (4, header_bottom + 6, 118, layout.nav_area[1] - 24)
        self.draw_icon(picture, pen, icon_box, accent)

        text_x, line_y = 124, header_bottom + 18
        lines = BRIEF_LINES[self.mode]
        line_font = fitted_font(pen, lines, layout.width - text_x - 6, round(layout.height * 0.068))
        line_gap = (layout.nav_area[1] - 30 - line_y) / len(lines)
        for index, line in enumerate(lines):
            pen.text((text_x, line_y + index * line_gap), line, font=line_font,
                     fill=INK if index else header_color, anchor="lm")

        if report.mode_reason:
            pen.text((8, layout.nav_area[1] - 10), "why: " + report.mode_reason, font=layout.small_font,
                     fill=MUTED, anchor="lm")
        draw_nav_row(pen, layout, [BACK_ARROW, "", "", "OK"])
        nav_middle(pen, layout, f"next in {self.seconds_left}s")
        return picture

    def draw_icon(self, picture, pen, box, accent):
        left, top, right, bottom = box
        center_x, center_y = (left + right) / 2, (top + bottom) / 2
        if self.mode == ESCORT:
            WalkIcon().draw(picture, pen, (left, top + 20, right, bottom))
            draw_drone(pen, center_x + 30, top + 18, 26, color=accent)
            pen.line([(center_x + 10, top + 34), (center_x + 46, top + 34)], fill=accent, width=3)
        elif self.mode == RESPONDER:
            draw_person(pen, center_x - 20, bottom - 6, 60)
            draw_drone(pen, center_x + 22, top + 26, 26, color=accent)
            pen.line([(center_x + 2, top + 56), (right - 6, top + 8)], fill=accent, width=3)
            pen.polygon([(right - 6, top + 8), (right - 20, top + 10), (right - 10, top + 22)], fill=accent)
        else:
            draw_person(pen, center_x, bottom - 6, 56)
            draw_drone(pen, center_x, top + 18, 26, color=accent)
            for angle in range(0, 360, 45):
                radians = math.radians(angle)
                pen.line([(center_x + 22 * math.cos(radians), top + 18 + 22 * math.sin(radians)),
                          (center_x + 34 * math.cos(radians), top + 18 + 34 * math.sin(radians))],
                         fill=(240, 190, 30), width=3)

    def handle(self, event, report):
        if event.kind == HOLD and event.button_index == 0:
            return BACK
        if event.kind == TAP:
            return NEXT
        return STAY


class EscortPage(SituationPage):
    """
    Map with the route to the team, plus walking pace and ETA.
        tap button 1   -> PAUSE / GO (the drone holds and waits for you)
        hold button 3  -> DONE (reached the team): app closes
        hold button 4  -> HURT: escort stops, switch to stay-put / help-coming mode
    """
    auto_seconds = None
    auto_action = None

    def __init__(self, map_source, heading_source, page_count):
        super().__init__(map_source, heading_source, page_count)
        self.paused = False

    def draw_panel(self, pen, layout, map_state):
        panel_left, panel_top, panel_right, panel_bottom = layout.panel_area
        pen.rectangle(layout.panel_area, fill=PANEL_DARK)
        text_x, line_y = panel_left + 6, panel_top + 12
        team = map_state.team()
        title_color = (255, 200, 60) if self.paused else (90, 230, 130)
        pen.text((text_x, line_y), "PAUSED" if self.paused else "ESCORT", font=layout.panel_font, fill=title_color, anchor="lm")
        line_y += 16
        pen.text((text_x, line_y), "drone holding" if self.paused else "follow the drone", font=layout.small_font,
                 fill=(200, 200, 200), anchor="lm")
        if team:
            distance = map_state.distance_m(team)
            line_y += 26
            pen.text((text_x, line_y), "TO TEAM", font=layout.small_font, fill=TEXT_GREEN, anchor="lm")
            line_y += 16
            pen.text((text_x, line_y), f"{distance_text(distance)} {compass_word(map_state.bearing_deg(team))}",
                     font=layout.panel_font, fill=(80, 160, 255), anchor="lm")
            line_y += 24
            pen.text((text_x, line_y), "ETA WALKING", font=layout.small_font, fill=TEXT_GREEN, anchor="lm")
            line_y += 16
            pen.text((text_x, line_y), f"~{max(1, round(distance / WALKING_SPEED_MPS / 60))} min",
                     font=layout.panel_font, fill=WHITE, anchor="lm")
        line_y += 26
        pen.text((text_x, line_y), "PACE: SLOW", font=layout.small_font, fill=(200, 200, 200), anchor="lm")
        if int(self.clock * 1.5) % 2 == 0:
            pen.text((text_x, panel_bottom - 8), "hurt? hold HURT", font=layout.small_font, fill=(255, 110, 110), anchor="lm")

    def draw_nav(self, pen, layout):
        draw_nav_row(pen, layout, ["GO" if self.paused else "PAUSE", "", "DONE", "HURT"])
        top, bottom = layout.nav_area[1], layout.nav_area[3]
        hurt_left = layout.column(3)[0] + 1
        pen.rectangle((hurt_left, top, layout.width, bottom), fill=(200, 40, 40))
        pen.text((layout.column_center_x(3), (top + bottom) // 2), "HURT", font=layout.nav_font, fill=WHITE, anchor="mm")
        pen.text((layout.column_center_x(1), (top + bottom) // 2), "", font=layout.nav_font, fill=INK, anchor="mm")

    def handle(self, event, report):
        if event.kind == TAP and event.button_index == 0:
            self.paused = not self.paused
            return STAY
        if event.kind == HOLD and event.button_index == 2:
            return CLOSE
        if event.kind == HOLD and event.button_index == 3:
            return SWITCH_TO_RESPONDER
        if event.kind == HOLD and event.button_index == 0:
            return BACK
        return STAY


class ResponderMapPage(SituationPage):
    """Situation map while the drone heads home; then moves on to the stay-put screen instead of closing."""
    auto_action = NEXT


class StayHerePage(Page):
    """
    Stay put: help is coming. Team distance and ETA, survival tips that rotate every few seconds.
    The screen switches off after a while to save battery.
        hold button 3  -> DONE (close now)
        hold button 1  -> back
    """
    auto_seconds = 45
    auto_action = CLOSE
    animated = True
    frame_interval_seconds = 0.5

    def __init__(self, map_source):
        self.map_source = map_source
        self.seconds_left = self.auto_seconds

    def render(self, layout, report):
        picture, pen = self.blank_picture(layout)
        _, header_color, accent = MODE_STYLE[RESPONDER]
        header_bottom = round(layout.height * 0.19)
        pen.rectangle((0, 0, layout.width, header_bottom), fill=header_color)
        pen.text((layout.width // 2, header_bottom // 2), "STAY HERE", font=layout.title_font, fill=WHITE, anchor="mm")

        map_state = self.map_source.latest()
        team = map_state.team()
        line_y = header_bottom + 22
        pen.text((12, line_y), "Help is coming.", font=layout.body_font, fill=INK, anchor="lm")
        if team:
            distance = map_state.distance_m(team)
            eta_minutes = max(1, round(distance / TEAM_SPEED_MPS / 60))
            pen.text((layout.width - 12, line_y), f"team ~{eta_minutes} min", font=layout.body_font,
                     fill=header_color, anchor="rm")
            line_y += 22
            pen.text((12, line_y), f"Team is {distance_text(distance)} {compass_word(map_state.bearing_deg(team))} of you.",
                     font=layout.small_font, fill=MUTED, anchor="lm")

        tip_number = int(self.clock / 4) % len(SURVIVAL_TIPS)
        tip_title, tip_text = SURVIVAL_TIPS[tip_number]
        box_top, box_bottom = line_y + 14, layout.nav_area[1] - 10
        pen.rounded_rectangle((10, box_top, layout.width - 10, box_bottom), radius=8, outline=accent, width=2,
                              fill=(255, 248, 230))
        pen.text((20, box_top + 18), tip_title, font=layout.body_font, fill=header_color, anchor="lm")
        self.draw_wrapped(pen, tip_text, 20, box_top + 40, layout.width - 40, layout.small_font, INK)
        for dot in range(len(SURVIVAL_TIPS)):                     # which tip of how many
            dot_x = layout.width - 20 - (len(SURVIVAL_TIPS) - 1 - dot) * 10
            pen.ellipse((dot_x - 3, box_top + 15, dot_x + 3, box_top + 21),
                        fill=header_color if dot == tip_number else (220, 210, 190))

        draw_nav_row(pen, layout, [BACK_ARROW, "", "", "DONE"])
        nav_middle(pen, layout, f"screen off in {self.seconds_left}s")
        return picture

    @staticmethod
    def draw_wrapped(pen, text, x, y, max_width, font, color):
        words, line, line_y = text.split(), "", y
        for word in words:
            trial = (line + " " + word).strip()
            if pen.textlength(trial, font=font) > max_width and line:
                pen.text((x, line_y), line, font=font, fill=color, anchor="lm")
                line, line_y = word, line_y + 16
            else:
                line = trial
        if line:
            pen.text((x, line_y), line, font=font, fill=color, anchor="lm")

    def handle(self, event, report):
        if event.kind == HOLD and event.button_index == 3:
            return CLOSE
        if event.kind == HOLD and event.button_index == 0:
            return BACK
        return STAY


class BeaconPage(Page):
    """
    Emergency beacon. The drone moves to an offset position (toward the rescue team) and sends the
    person's relative location by IR / optical Morse. This page shows that transmission live, with the
    current letter and dot/dash highlighted, and explains that IR can't be seen.
        tap any button  -> next (wait for friendly signal)
        hold button 1   -> back
    Moves on by itself after auto_seconds.
    """
    animated = True
    frame_interval_seconds = 0.08
    auto_seconds = 30
    auto_action = NEXT
    UNIT_SECONDS = 0.25                       # one Morse time unit

    def __init__(self, map_source):
        self.map_source = map_source
        self.started_clock = None
        self.seconds_left = self.auto_seconds

    def signal_state(self, timeline):
        """Where we are in the repeating Morse sequence: (light on?, letter index, step index)."""
        if self.started_clock is None:
            self.started_clock = self.clock
        total_units = sum(units for _, units, _ in timeline)
        position = ((self.clock - self.started_clock) / self.UNIT_SECONDS) % total_units
        for step_index, (is_on, units, letter_index) in enumerate(timeline):
            if position < units:
                return is_on, letter_index, step_index
            position -= units
        return False, 0, 0

    def render(self, layout, report):
        picture, pen = self.blank_picture(layout)
        message, toward_team = beacon_message(self.map_source.latest(), compass_word)
        timeline = morse_timeline(message)
        light_on, letter_index, step_index = self.signal_state(timeline)
        letters = message.replace(" ", "")

        _, header_color, accent = MODE_STYLE[BEACON]
        header_bottom = round(layout.height * 0.19)
        pulse = 0.75 + 0.25 * math.sin(self.clock * 6)
        pen.rectangle((0, 0, layout.width, header_bottom), fill=tuple(int(channel * pulse) for channel in header_color))
        pen.text((layout.width // 2, header_bottom // 2), "BEACON SENDING", font=layout.title_font, fill=WHITE, anchor="mm")

        # Left: person on the ground, drone hovering offset, dotted link, IR rays when the signal is on
        person_x, ground_y = 30, layout.nav_area[1] - 14
        drone_x, drone_y = 92, header_bottom + 30
        draw_person(pen, person_x, ground_y, 46)
        for dot in range(0, 10):
            fraction = dot / 10
            dot_x = person_x + (drone_x - person_x) * fraction
            dot_y = (ground_y - 50) + (drone_y + 14 - (ground_y - 50)) * fraction
            pen.ellipse((dot_x - 1.5, dot_y - 1.5, dot_x + 1.5, dot_y + 1.5), fill=(150, 150, 150))
        if light_on:
            for angle in range(0, 360, 30):
                radians = math.radians(angle)
                pen.line([(drone_x + 17 * math.cos(radians), drone_y + 17 * math.sin(radians)),
                          (drone_x + 30 * math.cos(radians), drone_y + 30 * math.sin(radians))],
                         fill=(150, 40, 120), width=3)                       # IR drawn as deep magenta
        draw_drone(pen, drone_x, drone_y, 22, color=(40, 40, 40))
        offset_text = f"{BEACON_OFFSET_M} m {compass_word(toward_team)}" if toward_team is not None else "nearby"
        pen.text((drone_x, drone_y + 30), offset_text, font=layout.small_font, fill=MUTED, anchor="mt")

        # Right: what is being sent
        text_x = 134
        pen.text((text_x, header_bottom + 14), "IR + LIGHT MORSE", font=layout.small_font, fill=MUTED, anchor="lm")
        letter_x = text_x
        letter_font = fitted_font(pen, [" ".join(letters)], layout.width - text_x - 8, round(layout.height * 0.10))
        for index, letter in enumerate(letters):
            pen.text((letter_x, header_bottom + 36), letter, font=letter_font,
                     fill=accent if index == letter_index else (190, 190, 190), anchor="lm")
            letter_x += pen.textlength(letter, font=letter_font) + 5

        current_letter = letters[letter_index] if letter_index < len(letters) else ""
        code = MORSE.get(current_letter, "")
        lit_steps = [index for index, (is_on, _, letter) in enumerate(timeline) if letter == letter_index and is_on]
        symbol_x, symbol_y = text_x, header_bottom + 66
        for symbol_number, symbol in enumerate(code):
            lit = light_on and symbol_number < len(lit_steps) and lit_steps[symbol_number] == step_index
            color = (250, 190, 20) if lit else INK
            if symbol == ".":
                pen.ellipse((symbol_x, symbol_y - 6, symbol_x + 12, symbol_y + 6), fill=color)
                symbol_x += 20
            else:
                pen.rounded_rectangle((symbol_x, symbol_y - 6, symbol_x + 34, symbol_y + 6), radius=6, fill=color)
                symbol_x += 42

        meaning = message.split(" ", 1)[1] if " " in message else ""
        if meaning:
            direction, meters = meaning.split()
            pen.text((text_x, header_bottom + 92), f"= you are {meters} m {direction} of it",
                     font=layout.small_font, fill=INK, anchor="lm")
        pen.text((text_x, header_bottom + 112), "IR is invisible to the eye.", font=layout.small_font, fill=MUTED, anchor="lm")
        pen.text((text_x, header_bottom + 128), "That is normal.", font=layout.small_font, fill=MUTED, anchor="lm")
        pen.text((text_x, header_bottom + 150), "Do not move.", font=layout.body_font, fill=header_color, anchor="lm")

        draw_nav_row(pen, layout, [BACK_ARROW, "", "", "NEXT"])
        nav_middle(pen, layout, f"next in {self.seconds_left}s")
        return picture

    def handle(self, event, report):
        if event.kind == HOLD and event.button_index == 0:
            return BACK
        if event.kind == TAP:
            return NEXT
        return STAY


class FriendlySignalPage(Page):
    """
    Wait for the rescuers' recognition signal, so the person knows who is friendly.
    Shows the signal pattern (animated), how to answer, and how long they've waited.
        tap button 2   -> HEARD IT: logs the time in the report, shows how to answer
        hold button 3  -> DONE (close)
        hold button 1  -> back
    """
    animated = True
    frame_interval_seconds = 0.2

    def __init__(self):
        self.started_clock = None
        self.heard_at_clock = None

    def render(self, layout, report):
        picture, pen = self.blank_picture(layout)
        if self.started_clock is None:
            self.started_clock = self.clock
        header_color = (25, 60, 130)
        header_bottom = round(layout.height * 0.19)
        pen.rectangle((0, 0, layout.width, header_bottom), fill=header_color)
        title = "SIGNAL HEARD" if self.heard_at_clock else "WAIT FOR FRIENDLY SIGNAL"
        title_font = fitted_font(pen, [title], layout.width - 16, round(layout.height * 0.10))
        pen.text((layout.width // 2, header_bottom // 2), title, font=title_font, fill=WHITE, anchor="mm")

        line_y = header_bottom + 18
        if self.heard_at_clock:
            pen.text((12, line_y), "Rescuers are close.", font=layout.body_font, fill=(30, 130, 70), anchor="lm")
            line_y += 26
            pen.text((12, line_y), ANSWER_TEXT + ".", font=layout.body_font, fill=INK, anchor="lm")
            line_y += 24
            pen.text((12, line_y), "Stay where you are.", font=layout.body_font, fill=INK, anchor="lm")
        else:
            pen.text((12, line_y), "Stay still and quiet.", font=layout.body_font, fill=INK, anchor="lm")
            line_y += 22
            pen.text((12, line_y), "Friendly rescuers will signal:", font=layout.small_font, fill=MUTED, anchor="lm")

        # The recognition pattern: dots that light up in turn (3 short, pause, repeat)
        pattern_y = layout.nav_area[1] - 62
        cycle = (self.clock - self.started_clock) % (FRIENDLY_SIGNAL_COUNT * 0.5 + 1.5)
        lit_dot = int(cycle / 0.5) if cycle < FRIENDLY_SIGNAL_COUNT * 0.5 else -1
        for dot in range(FRIENDLY_SIGNAL_COUNT):
            dot_x = 24 + dot * 34
            pen.ellipse((dot_x, pattern_y - 12, dot_x + 24, pattern_y + 12),
                        fill=(250, 190, 20) if dot == lit_dot else (210, 210, 210), outline=INK, width=1)
        pen.text((24, pattern_y + 24), FRIENDLY_SIGNAL_TEXT, font=layout.small_font, fill=INK, anchor="lm")

        waited = int(self.clock - self.started_clock)
        pen.text((layout.width - 10, layout.nav_area[1] - 12), f"waiting {waited // 60:02d}:{waited % 60:02d}",
                 font=layout.small_font, fill=MUTED, anchor="rm")
        draw_nav_row(pen, layout, [BACK_ARROW, "HEARD IT", "DONE", ""])
        return picture

    def handle(self, event, report):
        if event.kind == TAP and event.button_index == 1:
            if self.heard_at_clock is None:
                self.heard_at_clock = self.clock
                report.log_event("friendly signal heard")
            return STAY
        if event.kind == HOLD and event.button_index == 2:
            return CLOSE
        if event.kind == HOLD and event.button_index == 0:
            return BACK
        return STAY


def build_mode_pages(mode, map_source, heading_source, page_count):
    """The pages that follow REPORT COLLECTED, for each mode."""
    if mode == ESCORT:
        return [ModeBriefPage(ESCORT), EscortPage(map_source, heading_source, page_count)]
    if mode == RESPONDER:
        return [ModeBriefPage(RESPONDER), ResponderMapPage(map_source, heading_source, page_count),
                StayHerePage(map_source)]
    return [ModeBriefPage(BEACON), BeaconPage(map_source), FriendlySignalPage()]
