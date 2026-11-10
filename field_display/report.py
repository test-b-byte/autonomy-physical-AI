"""
report.py — MedicalReport: the answers, and saving them for rescuers.

The core record is a list of values, one per question, in question order:
    the button index pressed (0 = SEVERE, 1 = BAD, 2 = OK, 3 = FINE), or None if skipped.
Example: [0, 3, 2, None, 1]
"""

import datetime
import json
import os
from pathlib import Path

from content import QUESTIONS, SEVERITY_SCALE
from version import VERSION


class MedicalReport:

    def __init__(self, reports_folder):
        self.reports_folder = Path(reports_folder)
        self.reports_folder.mkdir(parents=True, exist_ok=True)
        self.reset()

    def reset(self):
        """Start a fresh report (new person, or starting over)."""
        self.started = datetime.datetime.now()
        self.values = [None] * len(QUESTIONS)
        self.collected_at = None
        self.mode = None
        self.mode_reason = None
        self.events = []                 # timestamped mode decisions and changes, in order
        self.session_file = self.reports_folder / f"report_{self.started:%Y%m%d_%H%M%S}.json"

    def record(self, question_index, button_index):
        self.values[question_index] = button_index

    def set_mode(self, mode, reason):
        """Record the point-of-contact mode (ESCORT / RESPONDER / BEACON) and why, then save."""
        self.mode = mode
        self.mode_reason = reason
        self.events.append({"time": datetime.datetime.now().isoformat(timespec="seconds"),
                            "mode": mode, "reason": reason})
        self.save()

    def log_event(self, what):
        """Add a timestamped note to the report (e.g. friendly signal heard) and save."""
        self.events.append({"time": datetime.datetime.now().isoformat(timespec="seconds"), "event": what})
        self.save()

    def mark_collected(self):
        """Called once, when the app finishes and closes."""
        self.collected_at = datetime.datetime.now()
        self.save()

    def answer_label(self, question_index):
        value = self.values[question_index]
        return None if value is None else SEVERITY_SCALE[value].label

    def needs_attention(self):
        """Plain-language list of answers rescuers should know about, e.g. ['Bleeding: SEVERE']."""
        attention_items = []
        for question_index, question in enumerate(QUESTIONS):
            value = self.values[question_index]
            if value is not None and SEVERITY_SCALE[value].needs_attention:
                attention_items.append(f"{question.rescuer_text}: {SEVERITY_SCALE[value].label}")
        return attention_items

    def as_dict(self):
        return {
            "app_version": VERSION,
            "started": self.started.isoformat(timespec="seconds"),
            "updated": datetime.datetime.now().isoformat(timespec="seconds"),
            "values": self.values,
            "answers": [
                {"key": question.key, "value": self.values[index], "label": self.answer_label(index)}
                for index, question in enumerate(QUESTIONS)
            ],
            "needs_attention": self.needs_attention(),
            "complete": all(value is not None for value in self.values),
            "collected_at": self.collected_at.isoformat(timespec="seconds") if self.collected_at else None,
            "mode": self.mode,
            "mode_reason": self.mode_reason,
            "events": self.events,
        }

    def save(self):
        """
        Write this session's file and refresh latest.json.
        Each is written to a temp file first, then swapped in, so a power cut
        mid-write can never leave a half-written report.
        """
        report_text = json.dumps(self.as_dict(), indent=2)
        for target_path in (self.session_file, self.reports_folder / "latest.json"):
            temp_path = target_path.with_suffix(".tmp")
            temp_path.write_text(report_text)
            os.replace(temp_path, target_path)
