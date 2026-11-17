"""A 2026 season as f1db holds it for the progression and clinch tests: rounds 1-17 of its published tables.

Layered on ``standings_support.mexico_feeds`` (f1db at round 18, Mexico computed). The test
database's shared ``SCHEMA`` lacks f1db's ``*_championship_decider`` columns, so they are added here.
"""

from __future__ import annotations

from contextlib import closing
import sqlite3
from typing import TYPE_CHECKING

from app.data import f1db_source
from tests.roster_support import F1DB_2026, load
from tests.standings_support import SEASON, Feeds, event, mexico_feeds

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    import types

    import pytest

SPRINT_ROUNDS = (2, 4, 5, 9, 12, 17)
EARLIER = load(F1DB_2026 / "standings_by_round.json")
ROUND_18 = load(F1DB_2026 / "standings_r18.json")


def _earlier_event(round_num: int) -> dict:
    return {
        **event(18),
        "round": round_num,
        "name": f"Round {round_num} Grand Prix",
        "location": f"Venue {round_num}, Country",
        "is_sprint": round_num in SPRINT_ROUNDS,
    }


SEASON_ALL = [_earlier_event(n) for n in range(1, 18)] + SEASON


def install_earlier_rounds(path: Path) -> None:
    """Rounds 1-17 of f1db's published tables, and the decider columns the real schema has."""
    with closing(sqlite3.connect(path)) as conn:
        conn.executemany(
            "INSERT INTO race_driver_standing (race_id, driver_id, position_number, points) VALUES (?, ?, ?, ?)",
            EARLIER["driver_standings"],
        )
        conn.executemany(
            "INSERT INTO race_constructor_standing (race_id, constructor_id, position_number, points) "
            "VALUES (?, ?, ?, ?)",
            EARLIER["constructor_standings"],
        )
        conn.execute("ALTER TABLE race ADD COLUMN drivers_championship_decider INTEGER")
        conn.execute("ALTER TABLE race ADD COLUMN constructors_championship_decider INTEGER")
        conn.commit()


def earlier_rounds_feeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calendar_readers: tuple[types.ModuleType, ...]
) -> Iterator[Feeds]:
    """``mexico_feeds`` plus rounds 1-17, with ``season_events`` of each reader module serving the whole season."""
    for module in calendar_readers:
        monkeypatch.setattr(module, "season_events", lambda _year: SEASON_ALL)
    for opened in mexico_feeds(tmp_path, monkeypatch):
        install_earlier_rounds(f1db_source.DB_PATH)
        yield opened
