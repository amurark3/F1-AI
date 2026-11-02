"""Tests for the official pit sheet (app.data.pit_sheet).

A red flag sends every running car into the pit lane, and the published sheet
lists each of those as a "stop". At Mexico 2026 (R19) that added a ~38 minute
entry for every car, plus a second one-minute pass for each lapped car on the
leader's red-flag lap, against 34 real stops. The sheet here leaves those out,
keeps the real stops on the lap before (Hamilton, Gasly, Piastri, Russell all
stopped on lap 44), and renumbers what is left.

The R19 fixtures are the real Jolpica and OpenF1 responses captured on 2 Nov 2026.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from app.data import pit_sheet as module
from app.data.f1db_pitstops import PitStop
from app.data.pit_sheet import (
    NO_SHEET,
    PitSheet,
    format_duration,
    stops_from_jolpica,
    suspension_laps,
    without_suspension,
)
from app.utils.ttl_cache import TtlCache
from tests.openf1_support import make_session, serve

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures" / "mexico_2026_r19"


def fixture(name: str) -> list | dict:
    return json.loads((FIXTURES / name).read_text())


def ergast_seconds(text: str) -> timedelta:
    minutes, _, seconds = text.rpartition(":")
    return timedelta(minutes=int(minutes or 0), seconds=float(seconds))


def jolpica_pit_rows() -> list[dict]:
    """The R19 sheet as FastF1's Ergast client flattens it."""
    return [
        {
            "driverId": row["driverId"],
            "stop": int(row["stop"]),
            "lap": int(row["lap"]),
            "duration": ergast_seconds(row["duration"]),
        }
        for row in fixture("jolpica_pitstops.json")["PitStops"]
    ]


def jolpica_codes() -> dict[str, str]:
    return {row["Driver"]["driverId"]: row["Driver"]["code"] for row in fixture("jolpica_results.json")["Results"]}


def r19_entries() -> tuple[PitStop, ...]:
    return stops_from_jolpica(jolpica_pit_rows(), jolpica_codes())


def entry(code: str, lap: int, seconds: float | None, stop: int = 1) -> PitStop:
    millis = None if seconds is None else round(seconds * 1000)
    return PitStop(
        driver_code=code,
        stop=stop,
        lap=lap,
        time=None if seconds is None else format_duration(timedelta(seconds=seconds)),
        millis=millis,
    )


# --- reading the sheet ----------------------------------------------------------------


def test_the_sheet_reads_every_entry_with_codes_and_times():
    entries = r19_entries()

    assert len(entries) == 58
    first = next(item for item in entries if item.driver_code == "VER")
    assert (first.stop, first.lap, first.time, first.millis) == (1, 27, "22.466", 22466)


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(22.466, "22.466"), (9.05, "9.050"), (60.513, "1:00.513"), (2284.66, "38:04.660")],
)
def test_durations_read_as_the_sheet_prints_them(seconds, text):
    assert format_duration(timedelta(seconds=seconds)) == text


def test_an_entry_without_a_duration_has_no_time():
    rows = [{"driverId": "alonso", "stop": 1, "lap": 3, "duration": pd.NaT}]

    stop = stops_from_jolpica(rows, {"alonso": "ALO"})[0]

    assert (stop.time, stop.millis) == (None, None)


def test_an_entry_for_an_unknown_driver_is_skipped():
    rows = [{"driverId": "nobody", "stop": 1, "lap": 3, "duration": timedelta(seconds=22)}]

    assert stops_from_jolpica(rows, {}) == ()


def test_entries_without_a_lap_are_skipped():
    rows = [{"driverId": "alonso", "stop": 1, "lap": float("nan"), "duration": timedelta(seconds=22)}]

    assert stops_from_jolpica(rows, {"alonso": "ALO"}) == ()


# --- leaving the suspension out --------------------------------------------------------


def test_mexico_2026_counts_only_the_real_stops():
    kept = without_suspension(r19_entries(), frozenset())
    counts = Counter(stop.driver_code for stop in kept.stops)

    assert {code: counts[code] for code in ("VER", "HAM", "LAW", "HIR", "STR")} == {
        "VER": 1,
        "HAM": 2,
        "LAW": 2,
        "HIR": 3,
        "STR": 1,
    }
    assert len(kept.stops) == 34
    assert kept.suspension_entries == 24


def test_mexico_2026_lap_45_entries_are_not_stops():
    kept = without_suspension(r19_entries(), frozenset())

    assert all(stop.lap != 45 for stop in kept.stops)
    assert all(stop.millis is not None and stop.millis <= 120_000 for stop in kept.stops)


def test_mexico_2026_real_stops_on_the_lap_before_the_red_flag_survive():
    kept = without_suspension(r19_entries(), frozenset())

    on_lap_44 = sorted(stop.driver_code for stop in kept.stops if stop.lap == 44)
    assert on_lap_44 == ["GAS", "HAM", "PIA", "RUS"]


def test_the_red_flag_lap_is_the_leaders_lap():
    # Lapped cars sat in the pit lane from their lap 44; the leaders from lap 45.
    assert suspension_laps(r19_entries(), frozenset()) == frozenset({45})


def test_stops_are_renumbered_once_the_suspension_is_gone():
    # Hirakawa's sheet numbers his lap-59 stop 5; it was his third.
    kept = without_suspension(r19_entries(), frozenset())

    assert [(stop.stop, stop.lap) for stop in kept.stops if stop.driver_code == "HIR"] == [(1, 35), (2, 43), (3, 59)]


def test_an_entry_longer_than_two_minutes_in_a_suspension_is_left_out():
    entries = (
        entry("VER", 29, 22.1),
        entry("VER", 30, 1800.0, stop=2),
        entry("HAM", 30, 1790.0),
        entry("LEC", 30, 1795.0),
    )

    kept = without_suspension(entries, frozenset())

    assert [(stop.driver_code, stop.lap) for stop in kept.stops] == [("VER", 29)]
    assert kept.suspension_entries == 3


def test_a_lone_long_stop_with_no_red_flag_is_a_real_stop():
    # A car in the garage for repairs is one long entry, not a suspended race.
    entries = (entry("VER", 20, 22.0), entry("STR", 20, 185.0), entry("HAM", 21, 22.4))

    kept = without_suspension(entries, frozenset())

    assert len(kept.stops) == 3
    assert kept.suspension_entries == 0


def test_a_red_flag_the_stints_saw_counts_even_without_long_entries():
    # Monza 2026: red-flagged on lap 3, and the stint data marks it.
    entries = (entry("VER", 3, 28.0), entry("HAM", 3, 27.5), entry("LEC", 19, 22.0))

    kept = without_suspension(entries, frozenset({3}))

    assert [(stop.driver_code, stop.lap) for stop in kept.stops] == [("LEC", 19)]


def test_a_sheet_without_a_red_flag_is_left_alone():
    entries = (entry("VER", 20, 22.0), entry("VER", 40, 23.0, stop=2))

    assert without_suspension(entries, frozenset()).stops == entries


def test_an_untimed_entry_is_never_read_as_a_suspension():
    entries = (entry("VER", 20, None), entry("HAM", 20, None), entry("LEC", 20, None))

    assert len(without_suspension(entries, frozenset()).stops) == 3


# --- where the sheet comes from ----------------------------------------------------------


class FakeErgast:
    def __init__(self, state: dict) -> None:
        self.state = state

    def get_pit_stops(self, season: int, round: int, limit: int) -> SimpleNamespace:  # noqa: A002 - FastF1's keyword
        self.state["calls"].append(("pit_stops", limit))
        if self.state["error"] is not None:
            raise self.state["error"]
        rows = self.state["pit_rows"]
        return SimpleNamespace(content=[pd.DataFrame(rows)] if rows else [], is_complete=self.state["complete"])

    def get_race_results(self, season: int, round: int) -> SimpleNamespace:  # noqa: A002 - FastF1's keyword
        self.state["calls"].append(("results", None))
        rows = [{"driverId": key, "driverCode": code} for key, code in self.state["codes"].items()]
        return SimpleNamespace(content=[pd.DataFrame(rows)] if rows else [])


@pytest.fixture
def sources(monkeypatch):
    state = {
        "pit_rows": jolpica_pit_rows(),
        "codes": jolpica_codes(),
        "complete": True,
        "error": None,
        "calls": [],
        "f1db": (entry("VER", 27, 22.466),),
        "session": make_session("R"),
        "routes": {"pit": fixture("openf1_pit.json"), "drivers": fixture("openf1_drivers.json")},
        "now": 1000.0,
    }
    monkeypatch.setattr(module, "Ergast", lambda: FakeErgast(state))
    monkeypatch.setattr(module, "f1db_pit_stops", lambda year, rnd: state["f1db"])
    monkeypatch.setattr(module, "find_session", lambda client, year, rnd, code: state["session"])
    monkeypatch.setattr(module, "_cache", TtlCache(clock=lambda: state["now"]))
    serve(monkeypatch, module, state["routes"])
    return state


def test_jolpica_publishes_the_sheet_first(sources):
    sheet = module.race_pit_sheet(2026, 19)

    assert sheet.source == module.JOLPICA_SOURCE
    assert len(sheet.entries) == 58
    # Jolpica answers 30 rows unless asked for more; a red-flagged race has 58.
    assert ("pit_stops", module.JOLPICA_PAGE_LIMIT) in sources["calls"]


def test_f1db_answers_when_jolpica_has_no_sheet(sources):
    sources["pit_rows"] = []

    assert module.race_pit_sheet(2026, 19) == PitSheet(source=module.F1DB_SOURCE, entries=sources["f1db"])


def test_f1db_answers_when_jolpica_is_unreachable(sources):
    sources["error"] = OSError("jolpica down")

    assert module.race_pit_sheet(2026, 19).source == module.F1DB_SOURCE


def test_a_page_cut_short_is_not_trusted(sources):
    sources["complete"] = False

    assert module.race_pit_sheet(2026, 19).source == module.F1DB_SOURCE


def test_a_sheet_jolpica_cannot_name_drivers_for_falls_back(sources):
    sources["codes"] = {}

    assert module.race_pit_sheet(2026, 19).source == module.F1DB_SOURCE


def test_no_sheet_anywhere_is_no_sheet(sources):
    sources["pit_rows"], sources["f1db"] = [], ()

    assert module.race_pit_sheet(2026, 19) == NO_SHEET


def test_openf1_stationary_times_are_attached_when_published(sources):
    rows = [{"driver_number": 3, "lap_number": 27, "stop_duration": 2.4, "lane_duration": 22.4}]
    sources["routes"]["pit"] = rows

    sheet = module.race_pit_sheet(2026, 19)
    verstappen = next(stop for stop in sheet.entries if stop.driver_code == "VER" and stop.lap == 27)

    assert verstappen.stationary_millis == 2400
    assert all(stop.stationary_millis is None for stop in sheet.entries if stop is not verstappen)


def test_mexico_2026_published_no_stationary_times(sources):
    assert all(stop.stationary_millis is None for stop in module.race_pit_sheet(2026, 19).entries)


def test_openf1_being_locked_out_leaves_the_sheet_untimed(sources):
    sources["routes"]["pit"] = httpx.Response(401, json={"detail": "live"})

    sheet = module.race_pit_sheet(2026, 19)

    assert sheet.source == module.JOLPICA_SOURCE
    assert all(stop.stationary_millis is None for stop in sheet.entries)


@pytest.mark.parametrize("session", [None, make_session("R", ended=False)], ids=["unmatched", "still running"])
def test_openf1_is_not_read_for_a_race_it_cannot_place(sources, session):
    sources["session"] = session
    sources["routes"]["pit"] = [{"driver_number": 3, "lap_number": 27, "stop_duration": 2.4}]

    assert all(stop.stationary_millis is None for stop in module.race_pit_sheet(2026, 19).entries)


def test_the_sheet_is_kept_for_a_while_then_read_again(sources):
    module.race_pit_sheet(2026, 19)
    sources["pit_rows"] = []
    sources["now"] += module.SHEET_TTL_SECONDS - 1
    assert module.race_pit_sheet(2026, 19).source == module.JOLPICA_SOURCE

    sources["now"] += 2
    assert module.race_pit_sheet(2026, 19).source == module.F1DB_SOURCE


def test_no_sheet_is_retried_after_a_short_window(sources):
    sources["pit_rows"], sources["f1db"] = [], ()
    module.race_pit_sheet(2026, 19)
    sources["pit_rows"] = jolpica_pit_rows()

    assert module.race_pit_sheet(2026, 19) == NO_SHEET
    sources["now"] += module.EMPTY_RETRY_SECONDS + 1
    assert module.race_pit_sheet(2026, 19).source == module.JOLPICA_SOURCE
