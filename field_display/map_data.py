"""
map_data.py — where things are, and which way is north.

Positions are in METERS on a flat grid: x = meters EAST, y = meters NORTH.
Any origin works (the map is drawn relative to YOU).

    MapEntity        one thing on the map (you, the drone, the team, a hazard, a hostile)
    MapState         everything on the map at one moment
    MapSource        parent: anything that can supply a MapState
      DemoMapSource    default: built-in estimated positions (no outside data needed)
      JsonMapSource    real data: reads map_state.json (written by the drone / GHOST / radio)
    HeadingSource    parent: anything that can say which way the device is facing
      DefaultHeading   default: assumes the top of the screen is north ("EST")
      MapFileHeading   real data: heading_deg from map_state.json (e.g. from a magnetometer)

map_state.json format (every field except "you" is optional):
{
  "you":      {"x": 0, "y": 0, "uncertainty_m": 30},
  "drone":    {"x": 4, "y": 2},
  "team":     {"x": 260, "y": 210, "label": "TEAM"},
  "hazards":  [{"x": 120, "y": -40, "label": "FIRE"}],
  "hostiles": [{"x": -330, "y": -300, "label": "ENEMY"}],
  "heading_deg": 37.5,
  "background": {"image": "map_background.png", "meters_per_pixel": 2.0,
                 "center_x": 0, "center_y": 0},
  "updated": 1762550000
}
"""

import json
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

YOU, DRONE, TEAM, HAZARD, HOSTILE = "you", "drone", "team", "hazard", "hostile"


@dataclass(frozen=True)
class MapEntity:
    kind: str          # YOU, DRONE, TEAM, HAZARD or HOSTILE
    x: float           # meters east
    y: float           # meters north
    label: str


@dataclass
class MapState:
    you: MapEntity
    uncertainty_m: float
    others: list = field(default_factory=list)     # every MapEntity except YOU
    background: dict = None                        # optional real map image (see format above)
    is_estimate: bool = True                       # True = demo / estimated positions
    updated: float = None

    def offset_from_you(self, entity):
        """(meters east, meters north) from YOU to the entity."""
        return entity.x - self.you.x, entity.y - self.you.y

    def distance_m(self, entity):
        east, north = self.offset_from_you(entity)
        return math.hypot(east, north)

    def bearing_deg(self, entity):
        """Compass bearing from YOU to the entity: 0 = north, 90 = east."""
        east, north = self.offset_from_you(entity)
        return (math.degrees(math.atan2(east, north)) + 360) % 360

    def team(self):
        return next((entity for entity in self.others if entity.kind == TEAM), None)


# ---------------------------------------------------------------------------
# Map sources
# ---------------------------------------------------------------------------

class MapSource(ABC):
    @abstractmethod
    def latest(self):
        """Return the newest MapState."""


class DemoMapSource(MapSource):
    """Built-in estimated positions, so the map always has something sensible to show."""

    def latest(self):
        you = MapEntity(YOU, 0, 0, "YOU")
        return MapState(
            you=you,
            uncertainty_m=30,
            others=[
                MapEntity(DRONE, 6, 4, "DRONE"),
                MapEntity(TEAM, 260, 210, "TEAM"),
                MapEntity(HAZARD, 120, -40, "FIRE"),
                MapEntity(HAZARD, -90, 150, "CLIFF"),
                MapEntity(HOSTILE, -330, -300, "ENEMY"),
            ],
            is_estimate=True,
        )


class JsonMapSource(MapSource):
    """Reads map_state.json. If the file is missing or broken, falls back to another source."""

    def __init__(self, json_path, fallback_source):
        self.json_path = Path(json_path)
        self.fallback_source = fallback_source
        self.last_raw = None

    def read_raw(self):
        try:
            self.last_raw = json.loads(self.json_path.read_text())
        except (OSError, ValueError):
            self.last_raw = None
        return self.last_raw

    def latest(self):
        raw = self.read_raw()
        if not raw or "you" not in raw:
            return self.fallback_source.latest()
        you = MapEntity(YOU, raw["you"]["x"], raw["you"]["y"], "YOU")
        others = []
        if "drone" in raw:
            others.append(MapEntity(DRONE, raw["drone"]["x"], raw["drone"]["y"], "DRONE"))
        if "team" in raw:
            others.append(MapEntity(TEAM, raw["team"]["x"], raw["team"]["y"], raw["team"].get("label", "TEAM")))
        for hazard in raw.get("hazards", []):
            others.append(MapEntity(HAZARD, hazard["x"], hazard["y"], hazard.get("label", "HAZARD")))
        for hostile in raw.get("hostiles", []):
            others.append(MapEntity(HOSTILE, hostile["x"], hostile["y"], hostile.get("label", "ENEMY")))
        background = raw.get("background")
        if background and "image" in background:
            background = dict(background, image=str(self.json_path.parent / background["image"]))
        return MapState(you=you, uncertainty_m=raw["you"].get("uncertainty_m", 30), others=others,
                        background=background, is_estimate=False, updated=raw.get("updated"))


# ---------------------------------------------------------------------------
# Heading sources
# ---------------------------------------------------------------------------

class HeadingSource(ABC):
    @abstractmethod
    def heading(self):
        """Return (degrees clockwise from north that the top of the screen faces, is_measured)."""


class DefaultHeading(HeadingSource):
    """No compass hardware: assume the screen's top points north."""

    def heading(self):
        return 0.0, False


class MapFileHeading(HeadingSource):
    """Uses heading_deg from map_state.json when present (e.g. written by a magnetometer reader)."""

    def __init__(self, json_map_source, fallback_heading):
        self.json_map_source = json_map_source
        self.fallback_heading = fallback_heading

    def heading(self):
        raw = self.json_map_source.last_raw or self.json_map_source.read_raw()
        if raw and raw.get("heading_deg") is not None:
            return float(raw["heading_deg"]) % 360, True
        return self.fallback_heading.heading()
