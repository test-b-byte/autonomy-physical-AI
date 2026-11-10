#!/usr/bin/env python3
"""
main.py — the rescue medical check app.

    python3 main.py             run on the Pi with the PiTFT
    python3 main.py --preview   no hardware: save every page as a PNG in ./preview

Answers are saved in ./reports/ (one file per session, plus latest.json).
After the last question: REPORT COLLECTED (5 s) -> situation map (20 s countdown) -> closes.
"""

import math
import sys
import time
from pathlib import Path

from content import QUESTIONS
from events import TAP, ButtonEvent
from layout import Layout
from map_data import DefaultHeading, DemoMapSource, JsonMapSource, MapFileHeading
from pages import BACK, NEXT, CompletePage, QuestionPage
from situation import CLOSE, SituationPage
from report import MedicalReport
from version import VERSION

APP_FOLDER = Path(__file__).resolve().parent      # works no matter where it's started from
REPORTS_FOLDER = APP_FOLDER / "reports"
SECONDS_BETWEEN_CHECKS = 0.02


def build_pages(map_source, heading_source):
    """7 question pages -> REPORT COLLECTED -> situation map."""
    page_count = len(QUESTIONS) + 2
    question_pages = [QuestionPage(index, page_count) for index in range(len(QUESTIONS))]
    return question_pages + [CompletePage(page_count), SituationPage(map_source, heading_source, page_count)]


def build_map_sources():
    """Real data from map_state.json when it exists; built-in estimates and north-up otherwise."""
    json_source = JsonMapSource(APP_FOLDER / "map_state.json", DemoMapSource())
    return json_source, MapFileHeading(json_source, DefaultHeading())


class RescueApp:
    """
    Owns the pages and the loop: read buttons -> current page decides -> redraw.
    Also runs page timers: auto-advance, auto-close, and animation frames.
    """

    def __init__(self, screen, buttons, layout, report, map_source, heading_source):
        self.screen = screen
        self.buttons = buttons
        self.layout = layout
        self.report = report
        self.pages = build_pages(map_source, heading_source)
        self.page_index = 0
        self.entered_page_at = time.monotonic()
        self.last_frame_at = 0.0
        self.keep_running = True

    def current_page(self):
        return self.pages[self.page_index]

    def apply(self, action):
        last_page = len(self.pages) - 1
        previous_index = self.page_index
        if action == NEXT:
            self.page_index = min(self.page_index + 1, last_page)
        elif action == BACK:
            self.page_index = max(self.page_index - 1, 0)
        elif action == CLOSE:
            self.report.mark_collected()
            self.keep_running = False
        if self.page_index != previous_index:
            self.entered_page_at = time.monotonic()     # every page change restarts that page's timer

    def redraw(self):
        page = self.current_page()
        page.clock = time.monotonic()
        self.last_frame_at = page.clock
        self.screen.show(page.render(self.layout, self.report))

    def run_timers(self):
        """Countdown and animation for the current page. Returns True if the screen needs redrawing."""
        page = self.current_page()
        needs_redraw = False
        if page.auto_seconds is not None:
            elapsed = time.monotonic() - self.entered_page_at
            seconds_left = max(0, math.ceil(page.auto_seconds - elapsed))
            if seconds_left != page.seconds_left:
                page.seconds_left = seconds_left
                needs_redraw = True
            if seconds_left == 0:
                page.seconds_left = page.auto_seconds       # reset, in case we come back to this page
                self.apply(page.auto_action)
                return self.keep_running
        if page.animated and time.monotonic() - self.last_frame_at >= page.frame_interval_seconds:
            needs_redraw = True
        return needs_redraw

    def run(self):
        self.redraw()
        try:
            while self.keep_running:
                needs_redraw = False
                for event in self.buttons.poll():
                    self.apply(self.current_page().handle(event, self.report))
                    needs_redraw = True
                if self.keep_running and self.run_timers():
                    needs_redraw = True
                if self.keep_running and needs_redraw:
                    self.redraw()
                time.sleep(SECONDS_BETWEEN_CHECKS)
        except KeyboardInterrupt:
            self.keep_running = False


def run_on_pi():
    print(f"Rescue app {VERSION}")
    import lgpio
    from hardware import ButtonPanel, DisplayProfile, Screen

    profile = DisplayProfile()
    gpio_chip = lgpio.gpiochip_open(0)
    screen = Screen(profile, gpio_chip)
    buttons = ButtonPanel(profile, gpio_chip)
    map_source, heading_source = build_map_sources()
    app = RescueApp(screen, buttons, Layout(profile.width, profile.height), MedicalReport(REPORTS_FOLDER),
                    map_source, heading_source)
    try:
        app.run()
    finally:
        from PIL import Image
        screen.show(Image.new("RGB", (profile.width, profile.height), (0, 0, 0)))
        screen.close()
        buttons.close()
        lgpio.gpiochip_close(gpio_chip)


def run_preview():
    """Render every page to PNG, after simulating taps, without any hardware."""
    preview_folder = APP_FOLDER / "preview"
    preview_folder.mkdir(exist_ok=True)
    layout = Layout(320, 240)
    report = MedicalReport(APP_FOLDER / "preview_reports")
    map_source, heading_source = build_map_sources()
    pages = build_pages(map_source, heading_source)
    simulated_taps = [0, 1, 1, 0, 2, 1, 0]
    for page_index, page in enumerate(pages):
        page.render(layout, report).save(preview_folder / f"page_{page_index + 1}.png")
        if page_index < len(simulated_taps):
            page.handle(ButtonEvent(simulated_taps[page_index], TAP), report)
    situation_page = pages[-1]
    for frame_number, clock in enumerate((0.1, 0.45, 0.9, 1.3)):     # blink phases
        situation_page.clock = clock
        situation_page.render(layout, report).save(preview_folder / f"map_frame_{frame_number}.png")
    print("values saved:", report.values)
    print(f"{VERSION}: pages written to {preview_folder}")


if __name__ == "__main__":
    if "--preview" in sys.argv:
        run_preview()
    else:
        run_on_pi()
