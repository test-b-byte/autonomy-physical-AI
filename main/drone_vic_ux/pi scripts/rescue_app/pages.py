"""
pages.py — what each screen looks like and what the buttons do on it.

Page is the parent. Every page can:
    render(layout, report)       -> a finished PIL picture
    handle(event, report)        -> what the app should do next (NEXT, BACK, STAY)
Pages never touch hardware; they only draw pictures and make decisions.
"""

from abc import ABC, abstractmethod

from PIL import Image, ImageDraw

from content import QUESTIONS, SEVERITY_SCALE
from version import VERSION
from events import HOLD, TAP

NEXT, BACK, STAY = "next", "back", "stay"

WHITE = (255, 255, 255)
INK = (20, 20, 20)
NAV_GRAY = (232, 232, 232)
BACK_ARROW = "<back>"           # a nav label drawn as a ◀ triangle instead of text


def draw_nav_row(pen, layout, labels):
    """Bottom strip, one cell per button."""
    left, top, right, bottom = layout.nav_area
    pen.rectangle(layout.nav_area, fill=NAV_GRAY)
    middle_y = (top + bottom) // 2
    for button_index in range(1, layout.BUTTON_COUNT):
        divider_x = layout.column(button_index)[0]
        pen.line([(divider_x, top), (divider_x, bottom)], fill=INK, width=1)
    for button_index, label in enumerate(labels):
        center_x = layout.column_center_x(button_index)
        if label == BACK_ARROW:
            half = (bottom - top) // 4
            pen.polygon([(center_x - half, middle_y), (center_x + half, middle_y - half),
                         (center_x + half, middle_y + half)], fill=INK)
        elif label:
            pen.text((center_x, middle_y), label, font=layout.nav_font, fill=INK, anchor="mm")


class Page(ABC):
    """
    Optional timing, read by RescueApp:
        auto_seconds / auto_action   after this many seconds on the page, do this action
        animated / frame_interval    redraw on a timer even without button presses (blinking)
        seconds_left / clock         set by RescueApp just before each render
    """
    auto_seconds = None
    auto_action = None
    animated = False
    frame_interval_seconds = 0.25
    seconds_left = None
    clock = 0.0

    @abstractmethod
    def render(self, layout, report):
        """Return a PIL picture exactly layout.width x layout.height."""

    @abstractmethod
    def handle(self, event, report):
        """Return NEXT, BACK, or STAY."""

    def blank_picture(self, layout):
        picture = Image.new("RGB", (layout.width, layout.height), WHITE)
        return picture, ImageDraw.Draw(picture)


class QuestionPage(Page):
    """
    Picture + question + four answer boxes, one above each button.
        tap any button      -> record that answer, go to the next page
        hold button 1 (◀)   -> back one page
        hold button 2 or 3  -> skip forward without answering
    """

    def __init__(self, question_index, page_count):
        self.question_index = question_index
        self.question = QUESTIONS[question_index]
        self.page_count = page_count

    def render(self, layout, report):
        picture, pen = self.blank_picture(layout)
        self.question.icon.draw(picture, pen, layout.picture_area)

        prompt_font = layout.fitted_prompt_font(pen, self.question.prompt)
        pen.text(layout.center_of(layout.prompt_area), self.question.prompt, font=prompt_font, fill=INK, anchor="mm")

        arrow_top, arrow_bottom = layout.arrow_area[1], layout.arrow_area[3]
        arrow_half_width = (arrow_bottom - arrow_top) * 0.7
        chosen_value = report.values[self.question_index]
        for button_index, level in enumerate(SEVERITY_SCALE):
            center_x = layout.column_center_x(button_index)
            pen.polygon([(center_x - arrow_half_width, arrow_top + 1), (center_x + arrow_half_width, arrow_top + 1),
                         (center_x, arrow_bottom - 1)], fill=INK)
            column_left, column_right = layout.column(button_index)
            box = (column_left + 2, layout.answer_area[1], column_right - 2, layout.answer_area[3] - 2)
            pen.rectangle(box, fill=level.color, outline=INK, width=4 if button_index == chosen_value else 1)
            pen.text(layout.center_of(box), level.label, font=layout.answer_font, fill=WHITE, anchor="mm")

        page_number = self.question_index + 1
        draw_nav_row(pen, layout, [BACK_ARROW, "HOLD", "NEXT", f"{page_number}/{self.page_count}"])
        return picture

    def handle(self, event, report):
        if event.kind == TAP:
            report.record(self.question_index, event.button_index)
            report.save()
            return NEXT
        if event.button_index == 0:
            return BACK
        if event.button_index in (1, 2):
            return NEXT
        return STAY


class CompletePage(Page):
    """
    "REPORT COLLECTED", what rescuers will be told, and a short countdown,
    then it moves on to the situation map by itself.
        hold button 1 (◀)  -> go back to change an answer (cancels the countdown)
    """

    auto_seconds = 5
    auto_action = NEXT          # then show the situation map

    def __init__(self, page_count):
        self.page_count = page_count
        self.seconds_left = self.auto_seconds

    def render(self, layout, report):
        picture, pen = self.blank_picture(layout)
        text_x = 12
        line_y = layout.height * 0.10
        pen.text((layout.width // 2, line_y), "REPORT COLLECTED", font=layout.title_font, fill=(40, 155, 60), anchor="mm")
        line_y += layout.height * 0.13

        attention_items = report.needs_attention()
        skipped_count = sum(1 for value in report.values if value is None)
        header = "Rescuers will be told:" if attention_items else "No serious problems reported"
        pen.text((text_x, line_y), header, font=layout.body_font, fill=INK, anchor="lm")
        if skipped_count:
            pen.text((layout.width - text_x, line_y), f"skipped {skipped_count}", font=layout.body_font,
                     fill=(110, 110, 110), anchor="rm")

        # Spread the items over the space above the nav row, so up to all 7 always fit.
        space_left = layout.nav_area[1] - line_y - 8
        line_gap = min(layout.height * 0.085, space_left / max(len(attention_items), 1))
        for item in attention_items:
            line_y += line_gap
            pen.text((text_x + 10, line_y), item, font=layout.body_font, fill=(200, 30, 30), anchor="lm")

        draw_nav_row(pen, layout, [BACK_ARROW, "", "", ""])
        # Middle of the nav row: countdown and version (drawn after the row, so it isn't painted over).
        nav_middle_y = (layout.nav_area[1] + layout.nav_area[3]) // 2
        pen.rectangle((layout.column(1)[0] + 1, layout.nav_area[1], layout.column(3)[1] - 1, layout.nav_area[3]),
                      fill=NAV_GRAY)
        pen.text((layout.column(2)[0], nav_middle_y), f"map in {self.seconds_left}s   {VERSION}",
                 font=layout.nav_font, fill=(110, 110, 110), anchor="mm")
        return picture

    def handle(self, event, report):
        if event.kind == HOLD and event.button_index == 0:
            return BACK
        return STAY
