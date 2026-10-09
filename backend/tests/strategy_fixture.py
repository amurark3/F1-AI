"""Shared builders for the pit-strategy suites.

The strategy modules all read the same FastF1 shapes — a laps frame, a results
frame, an event schedule — so the builders live here rather than being retyped
in five files. Frames are real pandas so the ``dropna``/``mode``/``median``
paths under test are the production ones.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

__all__ = [
    "FakeSession",
    "laps_frame",
    "results_frame",
    "schedule_frame",
    "stint_rows",
]


def stint_rows(
    driver: str,
    stints: list[tuple[str, int, int]],
    *,
    lap_seconds: float | list[float] = 90.0,
    fresh: bool | None = None,
    position: int | None = None,
    track_status: str = "1",
    pit_laps: tuple[int, ...] = (),
) -> list[dict]:
    """Rows for one driver's race, one entry per lap.

    ``stints`` is ``(compound, first_lap, last_lap)`` per stint, numbered from
    one in order. ``lap_seconds`` is either a constant or one value per lap of
    the whole race, so a degradation trend can be scripted. Laps listed in
    ``pit_laps`` carry a ``PitInTime``, and the lap after carries a
    ``PitOutTime``.
    """
    rows: list[dict] = []
    lap_index = 0
    for stint_num, (compound, first_lap, last_lap) in enumerate(stints, start=1):
        for lap_number in range(first_lap, last_lap + 1):
            seconds = lap_seconds[lap_index] if isinstance(lap_seconds, list) else lap_seconds
            lap_index += 1
            rows.append(
                {
                    "Driver": driver,
                    "LapNumber": float(lap_number),
                    "Stint": float(stint_num),
                    "Compound": compound,
                    "LapTime": pd.to_timedelta(seconds, unit="s") if seconds is not None else pd.NaT,
                    "FreshTyre": fresh,
                    "Position": position,
                    "TrackStatus": track_status,
                    "PitInTime": pd.to_timedelta(1, unit="s") if lap_number in pit_laps else pd.NaT,
                    "PitOutTime": pd.to_timedelta(1, unit="s") if lap_number - 1 in pit_laps else pd.NaT,
                }
            )
    return rows


def laps_frame(*row_groups: list[dict]) -> pd.DataFrame:
    """One laps frame from any number of per-driver row groups."""
    rows = [row for group in row_groups for row in group]
    return pd.DataFrame(rows)


def results_frame(finishers: list[tuple[str, int]]) -> pd.DataFrame:
    """A results frame of ``(abbreviation, finishing position)`` pairs."""
    return pd.DataFrame([{"Abbreviation": code, "Position": float(position)} for code, position in finishers])


def schedule_frame(events: list[tuple[int, str]]) -> pd.DataFrame:
    """A schedule frame of ``(round number, location)`` pairs."""
    return pd.DataFrame([{"RoundNumber": rnd, "Location": location} for rnd, location in events])


class FakeSession:
    """Stand-in for the session ``fastf1.get_session`` returns."""

    def __init__(
        self,
        *,
        laps: pd.DataFrame | None = None,
        results: pd.DataFrame | None = None,
        event: dict[str, Any] | None = None,
        load_error: BaseException | None = None,
    ):
        self.laps = laps
        self.results = results
        self.event = event if event is not None else {}
        self.load_kwargs: dict | None = None
        self._load_error = load_error

    def load(self, **kwargs) -> None:
        if self._load_error is not None:
            raise self._load_error
        self.load_kwargs = kwargs
