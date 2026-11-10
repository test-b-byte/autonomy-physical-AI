#!/usr/bin/env python3
"""
main.py — the rescue medical check app.

    python3 main.py             run on the Pi with the PiTFT
    python3 main.py --preview   no hardware: save every page as a PNG in ./preview

Answers are saved in ./reports/ (one file per session, plus latest.json).
After the last question: REPORT COLLECTED (5 s) -> point-of-contact mode, decided from the answers:
    ESCORT (follow the drone)  |  RESPONDER (stay here, help coming)  |  BEACON (emergency sky beacon)
"""

import math
import sys
import time
from pathlib import Path

from content import QUESTIONS
from events import TAP, ButtonEvent
from layout import Layout
from map_data import DefaultHeading, DemoMapSource, JsonMapSource, MapFileHeading
from mode_pages import build_mode_pages
from modes import RESPONDER, SWITCH_TO_RESPONDER, decide_mode
from pages import BACK, NEXT, CompletePage, QuestionPage
from situation import CLOSE, SituationPage
from report import MedicalReport
from version import VERSION

APP_FOLDER = Path(__file__).resolve().parent      # works no matter where it's started from
REPORTS_FOLDER = APP_FOLDER / "reports"
SECONDS_BETWEEN_CHECKS = 0.02


def build_pages(map_source, heading_source):
    """
    The fixed start: 7 question pages -> REPORT COLLECTED.
    What follows depends on the answers, so RescueApp adds the mode pages after REPORT COLLECTED.
    """
    page_count = len(QUESTIONS) + 2
    question_pages = [QuestionPage(index, page_count) for index in range(len(QUESTIONS))]
    return question_pages + [CompletePage(page_count)]


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
        self.map_source = map_source
        self.heading_source = heading_source
        self.base_pages = build_pages(map_source, heading_source)
        self.pages = list(self.base_pages)
        self.page_index = 0
        self.entered_page_at = time.monotonic()
        self.last_frame_at = 0.0
        self.keep_running = True

    def current_page(self):
        return self.pages[self.page_index]

    def enter_mode(self, mode, reason):
        """Record the decided mode and replace everything after REPORT COLLECTED with that mode's pages."""
        self.report.set_mode(mode, reason)
        self.pages = list(self.base_pages) + build_mode_pages(mode, self.map_source, self.heading_source,
                                                              len(self.base_pages))

    def apply(self, action):
        previous_index = self.page_index
        leaving_report_page = action == NEXT and self.page_index == len(self.base_pages) - 1
        if leaving_report_page:                                   # point of contact: decide the mode here
            self.enter_mode(*decide_mode(self.report.values))
        if action == SWITCH_TO_RESPONDER:                         # escort aborted: "I'm hurt"
            self.enter_mode(RESPONDER, "hurt during escort")
            self.page_index = len(self.base_pages)
        last_page = len(self.pages) - 1
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
    """Render every point-of-contact mode to PNG, without any hardware."""
    preview_folder = APP_FOLDER / "preview"
    preview_folder.mkdir(exist_ok=True)
    layout = Layout(320, 240)
    map_source, heading_source = build_map_sources()
    scenarios = {                                           # answers: bleeding, breathing, head, cold, walk, arms, safe
        "escort": [3, 3, 3, 2, 3, 3, 3],
        "responder": [2, 3, 2, 2, 1, 3, 2],
        "beacon": [0, 1, 2, 1, 2, 3, 2],
    }
    for name, answers in scenarios.items():
        report = MedicalReport(APP_FOLDER / "preview_reports")
        for question_index, value in enumerate(answers):
            report.record(question_index, value)
        mode, reason = decide_mode(report.values)
        report.set_mode(mode, reason)
        print(f"{name}: {answers} -> {mode} ({reason})")
        for page_number, page in enumerate(build_mode_pages(mode, map_source, heading_source, 9)):
            for frame_number, clock in enumerate((0.0, 0.6, 1.4)):
                page.clock = clock
                page.seconds_left = page.auto_seconds
                page.render(layout, report).save(preview_folder / f"{name}_{page_number + 1}_f{frame_number}.png")
        if mode == "BEACON":
            friendly = build_mode_pages(mode, map_source, heading_source, 9)[2]
            friendly.clock = 0.0
            friendly.render(layout, report)
            friendly.clock = 75.0
            friendly.handle(ButtonEvent(1, TAP), report)
            friendly.render(layout, report).save(preview_folder / "beacon_signal_heard.png")
    print(f"{VERSION}: pages written to {preview_folder}")


if __name__ == "__main__":
    if "--preview" in sys.argv:
        run_preview()
    else:
        run_on_pi()
