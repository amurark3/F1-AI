"""The 2025 São Paulo Grand Prix (2025 round 21) as the baseline-plan sources read it.

R20 2026 (São Paulo) plans its race from this edition: the planning season's
own race has not been run, and 2025 is the season before. The fixtures in
``fixtures/sao_paulo_2025_r21/`` are the real OpenF1 and Jolpica responses,
captured on 10 Nov 2026 (``provenance.json`` names every request). Each builder
here turns one of them into what the production readers return, through the
production parsers, so a test reads the same values the live feeds give.
"""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from typing import TYPE_CHECKING

from app.data.openf1_stints import stints_from_openf1
from app.data.pit_sheet import JOLPICA_SOURCE, stops_from_jolpica, without_suspension
from app.data.race_classification import OPENF1_SOURCE, classification_from_openf1
from app.data.strategy.edition_plan import Edition, EditionRace, summarize_edition
from app.data.strategy.edition_sources import PIT_LANE_SOURCE, STINTS_SOURCE

if TYPE_CHECKING:
    from app.data.f1db_pitstops import PitStop
    from app.data.race_classification import ClassifiedDriver
    from app.data.stint_model import Stint

FIXTURES = Path(__file__).parent / "fixtures" / "sao_paulo_2025_r21"
YEAR = 2025
ROUND = 21
EVENT_NAME = "São Paulo Grand Prix"
RACE_SESSION_KEY = 9869


def fixture(name: str) -> list | dict:
    return json.loads((FIXTURES / name).read_text())


def driver_rows() -> dict[int, dict]:
    """OpenF1's entry list for the race, by car number."""
    return {row["driver_number"]: row for row in fixture("openf1_drivers.json")}


def codes_by_number() -> dict[int, str]:
    return {number: row["name_acronym"] for number, row in driver_rows().items()}


def stints() -> tuple[Stint, ...]:
    """The race's tyre stints as OpenF1 publishes them (no red flag at this race)."""
    return stints_from_openf1(fixture("openf1_stints.json"), driver_rows(), {})


def classification() -> tuple[ClassifiedDriver, ...]:
    """OpenF1's ``session_result``: 17 finishers; HAM, LEC and BOR retired."""
    return classification_from_openf1(fixture("openf1_session_result.json"), codes_by_number())


def _ergast_seconds(text: str) -> timedelta:
    minutes, _, seconds = text.rpartition(":")
    return timedelta(minutes=int(minutes or 0), seconds=float(seconds))


def jolpica_pit_rows() -> list[dict]:
    """Jolpica's pit sheet as FastF1's Ergast client flattens it."""
    return [
        {
            "driverId": row["driverId"],
            "stop": int(row["stop"]),
            "lap": int(row["lap"]),
            "duration": _ergast_seconds(row["duration"]),
        }
        for row in fixture("jolpica_pitstops.json")["PitStops"]
    ]


def jolpica_codes() -> dict[str, str]:
    return {row["Driver"]["driverId"]: row["Driver"]["code"] for row in fixture("jolpica_results.json")["Results"]}


def sheet_entries() -> tuple[PitStop, ...]:
    """Every entry of Jolpica's pit sheet: 37, no red flag."""
    return stops_from_jolpica(jolpica_pit_rows(), jolpica_codes())


def pit_lane_millis() -> dict[tuple[str, int], int]:
    """OpenF1's ``pit_duration`` per stop in milliseconds, by (driver, lap)."""
    codes = codes_by_number()
    return {
        (codes[row["driver_number"]], row["lap_number"]): round(row["pit_duration"] * 1000)
        for row in fixture("openf1_pit.json")
    }


def reference() -> dict:
    """What ``circuit_strategy_reference("São Paulo, Brazil", 2026)`` returns for R20 2026.

    The 2025 edition read in full: the shape ``edition_sources.edition_reference``
    gives (``test_strategy_edition_sources.py`` checks it on the same responses),
    with the search's ``unread_years``.
    """
    stops = without_suspension(sheet_entries(), frozenset()).stops
    plan = summarize_edition(
        Edition(year=YEAR, round=ROUND, name=EVENT_NAME),
        EditionRace(stints(), stops, classification(), pit_lane_millis()),
    )
    assert plan is not None
    return {
        **plan,
        "suspension_entries": 0,
        "sources": {
            "stints": STINTS_SOURCE,
            "stops": JOLPICA_SOURCE,
            "classification": OPENF1_SOURCE,
            "pit_lane": PIT_LANE_SOURCE,
        },
        "unread_years": [],
    }
