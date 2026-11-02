"""Real Mexico 2026 data for the standings tests: f1db through round 18, every feed for round 19.

The standings rule was written the morning after Mexico 2026, when no single
feed had the table right, so its tests run on what the feeds published then:

* ``f1db_2026_r18/standings_r18.json``: f1db v2026.18.0's 2026 entrants, every
  Grand Prix and sprint result through round 18 and the standings after it.
* ``mexico_2026_r19/``: OpenF1's sessions, ``drivers`` lists, ``session_result``
  and ``championship_*`` tables, and Jolpica's standings, all captured on
  2 Nov 2026. By midday OpenF1 and Jolpica had both caught up on every total but
  one: OpenF1's driver table gave Hirakawa no point for his 10th place.
* ``mexico_2026_r19/f1db_standings_after_r19.json``: the table f1db v2026.19.0
  published after round 19, which matches the FIA.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
import sqlite3
from types import SimpleNamespace
from typing import TYPE_CHECKING

import httpx
import pandas as pd

from app.data import (
    current_standings,
    f1db_source,
    identity,
    session_entries,
    standings_cross_check,
    standings_rounds,
)
from app.utils.ttl_cache import TtlCache
from tests.openf1_support import serve
from tests.profiles_support import SCHEMA
from tests.roster_support import AFTER_MEXICO, F1DB_2026, MEXICO, drivers_route, load, mexico_drivers, weekend

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    import pytest

    from app.data.openf1.sessions import OpenF1Session

MEXICO_ROUND = 19


def install_f1db_through_r18(path: Path) -> Path:
    """An f1db holding f1db v2026.18.0's 2026 season, built at ``path``."""
    data = load(F1DB_2026 / "standings_r18.json")
    rounds = sorted({result[0] for result in data["results"]})
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO driver (id, name, abbreviation, permanent_number) VALUES (?, ?, ?, ?)", data["drivers"]
        )
        conn.executemany("INSERT INTO constructor (id, name, full_name) VALUES (?, ?, ?)", data["constructors"])
        conn.executemany("INSERT INTO race (id, year, round) VALUES (?, 2026, ?)", [(rnd, rnd) for rnd in rounds])
        conn.executemany(
            """INSERT INTO race_data (race_id, type, driver_id, constructor_id, driver_number, position_number, race_points)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            data["results"],
        )
        conn.executemany(
            "INSERT INTO season_entrant_driver (year, driver_id, constructor_id, rounds, test_driver) VALUES (2026, ?, ?, '', ?)",
            data["entrants"],
        )
        last = rounds[-1]
        conn.executemany(
            "INSERT INTO race_driver_standing (race_id, driver_id, position_number, points) VALUES (?, ?, ?, ?)",
            [(last, *row) for row in data["driver_standings"]],
        )
        conn.executemany(
            "INSERT INTO race_constructor_standing (race_id, constructor_id, position_number, points) VALUES (?, ?, ?, ?)",
            [(last, *row) for row in data["constructor_standings"]],
        )
        conn.commit()
    return path


def jolpica_driver_records() -> list[dict]:
    """Jolpica's driver standings after round 19, as FastF1's Ergast client flattens them."""
    return [
        {
            "position": int(row["position"]),
            "points": float(row["points"]),
            "wins": int(row["wins"]),
            "driverCode": row["Driver"]["code"],
        }
        for row in load(MEXICO / "jolpica_driver_standings.json")["DriverStandings"]
    ]


def jolpica_team_records() -> list[dict]:
    """Jolpica's constructor standings after round 19, flattened the same way."""
    return [
        {
            "position": int(row["position"]),
            "points": float(row["points"]),
            "wins": int(row["wins"]),
            "constructorId": row["Constructor"]["constructorId"],
            "constructorName": row["Constructor"]["name"],
        }
        for row in load(MEXICO / "jolpica_constructor_standings.json")["ConstructorStandings"]
    ]


@dataclass
class Feeds:
    """What every feed answers, editable by a test before it reads the standings."""

    routes: dict
    weekends: dict[int, tuple[OpenF1Session, ...]]
    jolpica_drivers: list[dict] = field(default_factory=jolpica_driver_records)
    jolpica_teams: list[dict] = field(default_factory=jolpica_team_records)
    jolpica_error: Exception | None = None
    jolpica_calls: int = 0
    weekend_calls: list[int] = field(default_factory=list)
    clock: list[float] = field(default_factory=lambda: [1000.0])
    fakes: list = field(default_factory=list)

    def openf1_paths(self) -> list[str]:
        return [path for fake in self.fakes for path in fake.paths()]


class FakeErgast:
    """FastF1's Ergast client, answering from :class:`Feeds`."""

    def __init__(self, feeds: Feeds) -> None:
        self.feeds = feeds

    def _answer(self, records: list[dict]) -> SimpleNamespace:
        self.feeds.jolpica_calls += 1
        if self.feeds.jolpica_error is not None:
            raise self.feeds.jolpica_error
        return SimpleNamespace(content=[pd.DataFrame(records)] if records else [])

    def get_driver_standings(self, season: int, round: int) -> SimpleNamespace:  # noqa: A002 - FastF1's keyword
        return self._answer(self.feeds.jolpica_drivers)

    def get_constructor_standings(self, season: int, round: int) -> SimpleNamespace:  # noqa: A002 - FastF1's keyword
        return self._answer(self.feeds.jolpica_teams)


def _weekends(feeds: Feeds) -> Callable:
    def weekend_sessions(_client: httpx.Client, _year: int, round_num: int) -> tuple[OpenF1Session, ...]:
        feeds.weekend_calls.append(round_num)
        return feeds.weekends.get(round_num, ())

    return weekend_sessions


def mexico_feeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Feeds]:
    """f1db at round 18, OpenF1 and Jolpica as they stood after round 19, and empty caches.

    A generator for a test module's own fixture to ``yield from``: importing a
    fixture into the conftest would import ``app`` before the environment is
    scrubbed.
    """
    monkeypatch.setattr(f1db_source, "DB_PATH", install_f1db_through_r18(tmp_path / "f1db_r18.db"))
    identity.clear_cache()
    feeds = Feeds(
        routes={
            "drivers": drivers_route(mexico_drivers()),
            "session_result": load(MEXICO / "openf1_session_result.json"),
            "championship_drivers": load(MEXICO / "openf1_championship_drivers.json"),
            "championship_teams": load(MEXICO / "openf1_championship_teams.json"),
        },
        weekends={MEXICO_ROUND: weekend(MEXICO)},
    )
    for module in (standings_rounds, standings_cross_check, session_entries):
        feeds.fakes.append(serve(monkeypatch, module, feeds.routes))
    for module in (standings_rounds, session_entries):
        monkeypatch.setattr(module, "weekend_sessions", _weekends(feeds))
    monkeypatch.setattr(session_entries, "_cache", TtlCache())
    monkeypatch.setattr(session_entries, "_utc_now", lambda: AFTER_MEXICO)
    monkeypatch.setattr(standings_cross_check, "Ergast", lambda: FakeErgast(feeds))
    monkeypatch.setattr(standings_cross_check, "_alerted", TtlCache(clock=lambda: feeds.clock[0]))
    monkeypatch.setattr(current_standings, "_cache", TtlCache(clock=lambda: feeds.clock[0]))
    monkeypatch.setattr(current_standings, "_utc_now", lambda: AFTER_MEXICO)
    monkeypatch.setattr(current_standings, "installed_version", lambda: "v2026.18.0")
    yield feeds
    identity.clear_cache()


def route_error(status: int) -> httpx.Response:
    return httpx.Response(status, json={"detail": "error"})
