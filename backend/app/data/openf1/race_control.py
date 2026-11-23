"""What race control said that changes how a lap reads.

Two things, both only ever published as free-text messages:

* **Deleted lap times.** ``CAR 10 (GAS) TIME 1:36.764 DELETED - TRACK LIMITS AT
  TURN 9 LAP 3``. The message's ``driver_number`` is empty, so the lap is found
  by its **time**. The message's "LAP n" is OpenF1's lap n in a race or sprint
  and lap n - 1 in every other session (Gasly's 1:36.764 at Austin 2026 FP2 is
  his lap 2): 652 timed messages over 2026's sprint weekends and R17-R20 agree.
  "LAP n" picks the lap when a time matches two laps of one car, and places a
  deletion without a time ("LAP DELETED", an in-lap), which can be sent many
  minutes late. A message with neither ("(NEXT LAP PIT)") falls back to the
  car's last lap finished before it; a time that matches no lap marks nothing.
  "WILL BE REINSTATED" cancels the deletion with the same time.
* **Neutralised running.** Safety car, virtual safety car and red flag periods,
  as time windows. Each message is stamped with the *leader's* lap, which a
  lapped car is not on, so callers place a window by time against each car's
  own lap starts. A safety car or VSC ends at the next track-wide "TRACK CLEAR"
  or green flag. A red flag ends when the session is started again, not at the
  "TRACK CLEAR" sent seconds after the suspension (Monza 2026).
* **Qualifying segments.** Each ``qualifying_phase`` runs from its first green
  light ("PIT EXIT OPEN") to its chequered flag; a red flag stays inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from app.services.live_timing import parse_iso

if TYPE_CHECKING:
    from datetime import datetime

    from app.data.openf1.laps import Lap

SAFETY_CAR = "sc"
VIRTUAL_SAFETY_CAR = "vsc"
RED_FLAG = "red"

# Times are published to the millisecond, as lap durations are.
TIME_MATCH_TOLERANCE_SECONDS = 0.0015

_DELETION = re.compile(
    r"^CAR (?P<car>\d+) \([A-Z]+\) (?:TIME (?P<time>[\d:.]+) )?(?:LAP )?(?P<verb>DELETED|(?:WILL BE )?REINSTATED)"
)
_NAMED_LAP = re.compile(r"\bLAP (\d+)\b")
# OpenF1's lap number minus the message's "LAP n", by app session code.
_NAMED_LAP_OFFSET = {"R": 0, "S": 0, "FP1": -1, "FP2": -1, "FP3": -1, "Q": -1, "SQ": -1}
_TRACK_GREEN = frozenset({"CLEAR", "GREEN"})
SEGMENT_NUMBERS = (1, 2, 3)


@dataclass(frozen=True)
class Deletion:
    car: int
    seconds: float | None
    at: datetime
    lap: int | None = None


@dataclass(frozen=True)
class Window:
    """A neutralised period; ``end`` is None when the feed never closed it."""

    kind: str
    start: datetime
    end: datetime | None

    def to_json(self) -> dict:
        return {
            "kind": self.kind,
            "start": self.start.isoformat(),
            "end": None if self.end is None else self.end.isoformat(),
        }

    @classmethod
    def from_json(cls, row: dict) -> Window:
        start = parse_iso(row["start"])
        if start is None:
            raise ValueError(f"window without a start: {row!r}")
        return cls(kind=str(row["kind"]), start=start, end=parse_iso(row["end"]))


@dataclass(frozen=True)
class SegmentWindow:
    """One qualifying segment (1-3) from its first green light to its chequered flag."""

    number: int
    start: datetime
    end: datetime

    def to_json(self) -> dict:
        return {"number": self.number, "start": self.start.isoformat(), "end": self.end.isoformat()}

    @classmethod
    def from_json(cls, row: dict) -> SegmentWindow:
        start, end = parse_iso(row["start"]), parse_iso(row["end"])
        if start is None or end is None:
            raise ValueError(f"segment window without both ends: {row!r}")
        return cls(number=int(row["number"]), start=start, end=end)


def _text(message: dict) -> str:
    return str(message.get("message") or "").strip().upper()


def _dated(messages: list[dict]) -> list[tuple[datetime, dict]]:
    dated = [(moment, message) for message in messages if (moment := parse_iso(message.get("date"))) is not None]
    return sorted(dated, key=lambda item: item[0])


def lap_seconds(text: str) -> float | None:
    """``1:36.764`` (or ``56.123``) in seconds."""
    minutes, _, seconds = text.rpartition(":")
    try:
        return round(int(minutes or 0) * 60 + float(seconds), 3)
    except ValueError:
        return None


def standing_deletions(messages: list[dict]) -> tuple[Deletion, ...]:
    """Deletions not later reinstated, in the order they were issued."""
    standing: list[Deletion] = []
    for moment, message in _dated(messages):
        match = _DELETION.match(_text(message))
        if match is None:
            continue
        car = int(match["car"])
        seconds = None if match["time"] is None else lap_seconds(match["time"])
        if match["verb"] == "DELETED":
            named = _NAMED_LAP.search(_text(message), match.end())
            lap = None if named is None else int(named[1])
            standing.append(Deletion(car=car, seconds=seconds, at=moment, lap=lap))
        else:
            standing = [kept for kept in standing if (kept.car, kept.seconds) != (car, seconds)]
    return tuple(standing)


def _laps_by_time(laps: list[Lap], seconds: float) -> list[Lap]:
    return [lap for lap in laps if lap.time is not None and abs(lap.time - seconds) <= TIME_MATCH_TOLERANCE_SECONDS]


def lap_by_time(laps: list[Lap], seconds: float | None) -> Lap | None:
    """The lap whose time is ``seconds`` to the millisecond; the first, should two match."""
    if seconds is None:
        return None
    return next(iter(_laps_by_time(laps, seconds)), None)


def _last_finished_before(laps: list[Lap], moment: datetime) -> Lap | None:
    finished = [lap for lap in laps if (end := lap.end) is not None and end <= moment]
    return max(finished, key=lambda lap: lap.number, default=None)


def _named_lap(laps: list[Lap], deletion: Deletion, code: str) -> Lap | None:
    offset = _NAMED_LAP_OFFSET.get(code)
    if deletion.lap is None or offset is None:
        return None
    return next((lap for lap in laps if lap.number == deletion.lap + offset), None)


def _deleted_lap(laps: list[Lap], deletion: Deletion, code: str) -> Lap | None:
    named = _named_lap(laps, deletion, code)
    if deletion.seconds is None:
        return named or _last_finished_before(laps, deletion.at)
    timed = _laps_by_time(laps, deletion.seconds)
    return named if named in timed else next(iter(timed), None)


def deleted_laps(deletions: tuple[Deletion, ...], laps: tuple[Lap, ...], code: str) -> frozenset[tuple[int, int]]:
    """The (car, lap number) of every lap whose time stands deleted, in the session with app code ``code``."""
    found: set[tuple[int, int]] = set()
    for deletion in deletions:
        lap = _deleted_lap([lap for lap in laps if lap.driver == deletion.car], deletion, code)
        if lap is not None:
            found.add((lap.driver, lap.number))
    return frozenset(found)


def _opens(message: dict) -> str | None:
    text = _text(message)
    if str(message.get("flag") or "").upper() == "RED" or text.startswith("RED FLAG"):
        return None if "INFRINGEMENT" in text else RED_FLAG
    if "DEPLOYED" not in text:
        return None
    if text.startswith(("VSC", "VIRTUAL SAFETY CAR")):
        return VIRTUAL_SAFETY_CAR
    return SAFETY_CAR if text.startswith("SAFETY CAR") else None


def _closes(kind: str, message: dict) -> bool:
    if kind == RED_FLAG:
        return str(message.get("category") or "") == "SessionStatus" and "STARTED" in _text(message)
    return str(message.get("scope") or "") == "Track" and str(message.get("flag") or "").upper() in _TRACK_GREEN


def neutralised_windows(messages: list[dict]) -> tuple[Window, ...]:
    """Every safety car, virtual safety car and red flag period, in order."""
    dated = _dated(messages)
    windows: list[Window] = []
    for index, (moment, message) in enumerate(dated):
        kind = _opens(message)
        if kind is None:
            continue
        end = next((later for later, closing in dated[index + 1 :] if _closes(kind, closing)), None)
        windows.append(Window(kind=kind, start=moment, end=end))
    return tuple(windows)


def segment_windows(messages: list[dict]) -> tuple[SegmentWindow, ...]:
    """Windows of segments 1-3, or none at all unless race control published all three."""
    opened: dict[int, datetime] = {}
    closed: dict[int, datetime] = {}
    for moment, message in _dated(messages):
        phase, flag = message.get("qualifying_phase"), str(message.get("flag") or "").upper()
        if phase not in SEGMENT_NUMBERS or message.get("scope") != "Track":
            continue
        if flag == "GREEN" and "PIT EXIT OPEN" in _text(message):
            opened.setdefault(phase, moment)
        elif flag == "CHEQUERED":
            closed.setdefault(phase, moment)
    if not all(number in opened and number in closed and opened[number] < closed[number] for number in SEGMENT_NUMBERS):
        return ()
    return tuple(SegmentWindow(number, opened[number], closed[number]) for number in SEGMENT_NUMBERS)
