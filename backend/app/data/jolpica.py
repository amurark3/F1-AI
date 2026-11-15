"""Jolpica (the Ergast successor), called directly with our own pacer.

Jolpica is a fallback source only (``docs/DATA_SOURCES.md``). It used to be read
through FastF1's Ergast client, which counted every call against FastF1's 500
requests an hour per process, shared with everything else FastF1 loads. Here
the calls have their own budget and their own limits, Jolpica's published ones:
4 requests a second in a burst and 500 an hour.

Every failure (unreachable, rate limited, a bad answer, our own hourly budget
spent) is a :class:`JolpicaUnavailableError`. It is never an empty answer, so a
caller cannot cache a failed fetch as "nothing published".

Rows come back flat, with the keys FastF1's client used (``driverCode``,
``constructorName``, ``duration`` as a ``timedelta``), numbers already numbers.
"""

from __future__ import annotations

from collections import deque
from datetime import timedelta
import threading
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable

JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"
HTTP_TIMEOUT_SECONDS = 15.0

BURST_REQUESTS = 4
BURST_WINDOW_SECONDS = 1.0
HOURLY_REQUESTS = 500
HOUR_SECONDS = 3600.0

# Jolpica answers 30 rows unless asked for more. A red-flagged race doubles the
# pit sheet: Mexico 2026 had 58 entries.
PAGE_LIMIT = 100

QUALIFYING_SOURCE = "jolpica-qualifying"


class JolpicaUnavailableError(RuntimeError):
    """Jolpica gave no usable answer: unreachable, rate limited, malformed, or our hourly budget is spent."""


class Pacer:
    """Keeps the process inside Jolpica's limits.

    A request is booked a start time: never more than 4 starts in one
    window, so a caller sleeps until its slot. Past 500 starts in the
    last hour it raises instead of sleeping, because the next free slot is
    minutes away and a page is waiting. The lock guards the schedule, not the
    request.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._starts: deque[float] = deque()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            start = now
            if len(self._starts) >= BURST_REQUESTS:
                start = max(now, self._starts[-BURST_REQUESTS] + BURST_WINDOW_SECONDS)
            while self._starts and self._starts[0] <= start - HOUR_SECONDS:
                self._starts.popleft()
            if len(self._starts) >= HOURLY_REQUESTS:
                raise JolpicaUnavailableError(f"our {HOURLY_REQUESTS} requests an hour are spent")
            self._starts.append(start)
        if start > now:
            self._sleep(start - now)


PACER = Pacer()


def _get(path: str, params: dict | None = None) -> dict:
    """One paced request; the answer's ``MRData`` object."""
    PACER.wait()
    try:
        response = httpx.get(f"{JOLPICA_BASE}/{path}.json", params=params, timeout=HTTP_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise JolpicaUnavailableError(f"{path}: {exc}") from exc
    if response.status_code != httpx.codes.OK:
        raise JolpicaUnavailableError(f"{path}: HTTP {response.status_code}")
    try:
        return response.json()["MRData"]
    except (ValueError, KeyError) as exc:
        raise JolpicaUnavailableError(f"{path}: not a Jolpica answer") from exc


def _race_rows(year: int, round_num: int, kind: str, key: str) -> list[dict]:
    """The ``key`` rows of one race's ``kind`` table (empty before it is published); every page, or an error."""
    rows: list[dict] = []
    while True:
        data = _get(f"{year}/{round_num}/{kind}", {"limit": PAGE_LIMIT, "offset": len(rows)})
        races = data["RaceTable"]["Races"] if "RaceTable" in data else None
        if races is None:
            raise JolpicaUnavailableError(f"{kind}: not a race table")
        page = races[0][key] if races else []
        rows.extend(page)
        if not page or len(rows) >= int(data["total"]):
            return rows


def _seconds(text: str) -> timedelta:
    """A pit duration as Jolpica prints it: ``22.466`` or ``1:00.513``."""
    minutes, _, seconds = text.rpartition(":")
    return timedelta(minutes=int(minutes or 0), seconds=float(seconds))


def pit_stops(year: int, round_num: int) -> list[dict]:
    """The race's pit sheet: ``driverId``, ``lap``, ``stop`` and ``duration`` (``None`` when untimed)."""
    try:
        return [
            {
                "driverId": row["driverId"],
                "lap": int(row["lap"]),
                "stop": int(row["stop"]),
                "duration": _seconds(row["duration"]) if row.get("duration") else None,
            }
            for row in _race_rows(year, round_num, "pitstops", "PitStops")
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise JolpicaUnavailableError(f"pitstops: unreadable row ({exc})") from exc


def race_results(year: int, round_num: int) -> list[dict]:
    """The race's result rows, in Jolpica's order (which lags post-race penalties)."""
    try:
        return [
            {
                "driverId": row["Driver"]["driverId"],
                "driverCode": row["Driver"].get("code"),
                "position": int(row["position"]),
                "positionText": row["positionText"],
                "grid": int(row["grid"]),
                "laps": int(row["laps"]),
                "status": row["status"],
            }
            for row in _race_rows(year, round_num, "results", "Results")
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise JolpicaUnavailableError(f"results: unreadable row ({exc})") from exc


def provisional_grid(year: int, round_num: int) -> list[dict]:
    """The starting order taken from the qualifying classification, before any official grid exists.

    Jolpica has no grid before the race, and qualifying's order ignores grid
    penalties, so this is provisional and every row says where it came from.
    """
    try:
        return [
            {
                "position": int(row["position"]),
                "driverCode": row["Driver"]["code"],
                "provisional": True,
                "source": QUALIFYING_SOURCE,
            }
            for row in _race_rows(year, round_num, "qualifying", "QualifyingResults")
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise JolpicaUnavailableError(f"qualifying: unreadable row ({exc})") from exc


def _standings(year: int, round_num: int, kind: str, key: str) -> list[dict]:
    data = _get(f"{year}/{round_num}/{kind}", {"limit": PAGE_LIMIT})
    try:
        lists = data["StandingsTable"]["StandingsLists"]
        return lists[0][key] if lists else []
    except (KeyError, TypeError) as exc:
        raise JolpicaUnavailableError(f"{kind}: not a standings table") from exc


def driver_standings(year: int, round_num: int) -> list[dict]:
    """The driver table after the round: ``driverCode`` and ``points``; empty before Jolpica publishes it."""
    try:
        return [
            {"driverCode": row["Driver"]["code"], "points": float(row["points"])}
            for row in _standings(year, round_num, "driverstandings", "DriverStandings")
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise JolpicaUnavailableError(f"driverstandings: unreadable row ({exc})") from exc


def constructor_standings(year: int, round_num: int) -> list[dict]:
    """The constructor table after the round: ``constructorName`` and ``points``; empty before it is published."""
    try:
        return [
            {"constructorName": row["Constructor"]["name"], "points": float(row["points"])}
            for row in _standings(year, round_num, "constructorstandings", "ConstructorStandings")
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise JolpicaUnavailableError(f"constructorstandings: unreadable row ({exc})") from exc
