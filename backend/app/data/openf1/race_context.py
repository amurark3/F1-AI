"""What a race's laps need besides their times, for reading tyre wear from them.

* **Stints**: OpenF1's ``/stints`` for the session, merged so a stint is a tyre
  set (a drive-through is not a tyre change; see :mod:`app.data.openf1_stints`).
* **Gap to the car ahead** for each lap: the median ``interval`` OpenF1
  published while the lap ran. ``interval`` is the gap to the car ahead *in the
  running order*, so a lapped car being passed does not show up in it, and a
  "+1 LAP" (or empty) value is no reading at all. The leader's is 0.0, which
  read as "in traffic" every lap it led (Austin 2026's winner), so it is
  dropped too.
* **Rain**: when ``/weather`` reported rainfall, as time windows.
* **Finishing order**: classified cars by position, then the rest by laps done.

All measured. Kept with the race once it has ended, as the laps are.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass
from datetime import timedelta
from statistics import median
from typing import TYPE_CHECKING

from app.data.analysis_cache import analysis_cache
from app.data.openf1.client import get_json, new_client
from app.data.openf1.sessions import session_ended
from app.data.openf1_stints import stints_from_openf1
from app.data.stint_model import Stint
from app.services.live_timing import parse_iso

if TYPE_CHECKING:
    from datetime import datetime

    from app.data.openf1.laps import Lap
    from app.data.openf1.session_laps import SessionLaps

RACE_CONTEXT_KIND = "race_context"
RACE_CONTEXT_VERSION = 1
# /weather is sampled about once a minute; a wet reading covers the minute after it.
WEATHER_SAMPLE_SECONDS = 60

LapKey = tuple[int, int]
TimeWindow = tuple["datetime", "datetime"]


@dataclass(frozen=True)
class RaceContext:
    stints: tuple[Stint, ...]
    gaps: dict[LapKey, float]
    rain: tuple[TimeWindow, ...]
    classification: tuple[int, ...]

    def to_json(self) -> dict:
        return {
            "stints": [asdict(stint) for stint in self.stints],
            "gaps": [[driver, lap, gap] for (driver, lap), gap in self.gaps.items()],
            "rain": [[start.isoformat(), end.isoformat()] for start, end in self.rain],
            "classification": list(self.classification),
        }

    @classmethod
    def from_json(cls, payload: dict) -> RaceContext:
        rain = []
        for start_text, end_text in payload["rain"]:
            start, end = parse_iso(start_text), parse_iso(end_text)
            if start is not None and end is not None:
                rain.append((start, end))
        return cls(
            stints=tuple(Stint(**row) for row in payload["stints"]),
            gaps={(int(driver), int(lap)): float(gap) for driver, lap, gap in payload["gaps"]},
            rain=tuple(rain),
            classification=tuple(int(number) for number in payload["classification"]),
        )


def _numeric(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def lap_gaps(interval_rows: list[dict], laps: tuple[Lap, ...]) -> dict[LapKey, float]:
    """The median gap to the car ahead during each lap that has any reading."""
    readings: dict[int, list[tuple[datetime, float]]] = {}
    for row in interval_rows:
        moment, driver, interval = parse_iso(row.get("date")), row.get("driver_number"), row.get("interval")
        # The leader's interval is 0: there is no car ahead, which is clean air, not traffic.
        if moment is not None and driver is not None and _numeric(interval) and interval > 0:
            readings.setdefault(int(driver), []).append((moment, float(interval)))
    for rows in readings.values():
        rows.sort()
    gaps: dict[LapKey, float] = {}
    for lap in laps:
        rows = readings.get(lap.driver)
        if not rows or lap.start is None or lap.end is None:
            continue
        moments = [moment for moment, _ in rows]
        during = rows[bisect_left(moments, lap.start) : bisect_right(moments, lap.end)]
        if during:
            gaps[(lap.driver, lap.number)] = round(median(value for _, value in during), 3)
    return gaps


def rain_windows(weather_rows: list[dict]) -> tuple[TimeWindow, ...]:
    """Spans with rain reported, overlapping readings merged."""
    wet = sorted(
        moment
        for row in weather_rows
        if (moment := parse_iso(row.get("date"))) is not None and _numeric(row.get("rainfall")) and row["rainfall"] > 0
    )
    windows: list[TimeWindow] = []
    for moment in wet:
        end = moment + timedelta(seconds=WEATHER_SAMPLE_SECONDS)
        if windows and moment <= windows[-1][1]:
            windows[-1] = (windows[-1][0], end)
        else:
            windows.append((moment, end))
    return tuple(windows)


def finishing_order(result_rows: list[dict]) -> tuple[int, ...]:
    """Classified cars by position, then unclassified ones by laps completed."""

    def rank(row: dict) -> tuple[bool, float, float]:
        position, laps = row.get("position"), row.get("number_of_laps")
        return (
            not _numeric(position),
            float(position) if _numeric(position) else 0.0,
            -float(laps) if _numeric(laps) else 0.0,
        )

    rows = [row for row in result_rows if row.get("driver_number") is not None]
    return tuple(int(row["driver_number"]) for row in sorted(rows, key=rank))


def _fetch(session: SessionLaps) -> RaceContext:
    query = {"session_key": session.session.session_key}
    with new_client() as client:
        stint_rows = get_json(client, "stints", query)
        interval_rows = get_json(client, "intervals", query)
        weather_rows = get_json(client, "weather", query)
        result_rows = get_json(client, "session_result", query)
    entries = {
        driver.number: {"name_acronym": driver.code, "team_name": driver.team} for driver in session.drivers.values()
    }
    return RaceContext(
        stints=stints_from_openf1(stint_rows, entries, {}),
        gaps=lap_gaps(interval_rows, session.laps),
        rain=rain_windows(weather_rows),
        classification=finishing_order(result_rows),
    )


def load_race_context(session: SessionLaps) -> RaceContext:
    """The race's stints, per-lap gaps, rain and finishing order."""
    key = f"{session.year}:{session.round}:{session.session.code}"
    kept = analysis_cache.get(RACE_CONTEXT_KIND, key, RACE_CONTEXT_VERSION)
    if kept is not None:
        return RaceContext.from_json(kept)
    context = _fetch(session)
    if context.stints and session_ended(session.session):
        analysis_cache.put(RACE_CONTEXT_KIND, key, RACE_CONTEXT_VERSION, context.to_json())
    return context
