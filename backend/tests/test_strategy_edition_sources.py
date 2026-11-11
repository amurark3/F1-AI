"""Tests for app.data.strategy.edition_sources: reading one edition for the baseline plan.

The sources are served from the 2025 São Paulo Grand Prix responses captured on
10 Nov 2026 (``sao_paulo_2025_support``). An empty answer from any source is
"not readable right now" for a race that has been run, so the edition is
reported unread rather than summarised from part of its data.
"""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from app.data.f1db_pitstops import PitStop
from app.data.pit_sheet import JOLPICA_SOURCE, NO_SHEET, PitSheet
from app.data.race_classification import NO_CLASSIFICATION, OPENF1_SOURCE, RaceClassification
from app.data.stint_model import Stint
from app.data.strategy import edition_sources as module
from app.data.strategy.edition_plan import Edition
from tests import sao_paulo_2025_support as r21
from tests.openf1_support import make_session, serve

pytestmark = pytest.mark.unit

EDITION = Edition(year=r21.YEAR, round=r21.ROUND, name=r21.EVENT_NAME)


@pytest.fixture
def openf1(monkeypatch):
    """OpenF1's race session, pit rows and entry list for São Paulo 2025."""
    state = {"session": make_session("R")}
    monkeypatch.setattr(module, "find_session", lambda client, year, rnd, code: state["session"])
    state["fake"] = serve(
        monkeypatch,
        module,
        {"pit": r21.fixture("openf1_pit.json"), "drivers": r21.fixture("openf1_drivers.json")},
    )
    return state


@pytest.fixture
def sources(monkeypatch, openf1):
    """Every source answering with the captured race."""
    state = {
        "stints": r21.stints(),
        "classification": RaceClassification(source=OPENF1_SOURCE, drivers=r21.classification()),
        "sheet": PitSheet(source=JOLPICA_SOURCE, entries=r21.sheet_entries()),
        "calls": [],
    }

    def answer(name):
        def read(year, rnd):
            state["calls"].append((name, year, rnd))
            return state[name]

        return read

    monkeypatch.setattr(module, "openf1_race_stints", answer("stints"))
    monkeypatch.setattr(module, "race_classification", answer("classification"))
    monkeypatch.setattr(module, "race_pit_sheet", answer("sheet"))
    return state


# --- OpenF1 pit-lane times ------------------------------------------------------------------


def test_pit_lane_times_are_openf1s_pit_duration_by_driver_and_lap(openf1):
    times = module.pit_lane_times(2025, 21)

    assert times is not None
    assert len(times) == 37
    assert times[("NOR", 30)] == 23_490
    assert times[("HUL", 36)] == 23_000
    assert openf1["fake"].paths() == ["pit", "drivers"]


def test_the_newer_lane_duration_name_is_read_when_pit_duration_is_absent(monkeypatch, openf1):
    serve(
        monkeypatch,
        module,
        {
            "pit": [{"driver_number": 4, "lap_number": 30, "pit_duration": None, "lane_duration": 23.49}],
            "drivers": r21.fixture("openf1_drivers.json"),
        },
    )

    assert module.pit_lane_times(2025, 21) == {("NOR", 30): 23_490}


@pytest.mark.parametrize(
    "row",
    [
        {"driver_number": 4, "lap_number": 30, "pit_duration": None, "lane_duration": None},
        {"driver_number": 99, "lap_number": 30, "pit_duration": 23.4},
        {"driver_number": 4, "lap_number": None, "pit_duration": 23.4},
    ],
    ids=["no-time", "unknown-car", "no-lap"],
)
def test_a_pass_without_a_time_a_known_car_or_a_lap_is_skipped(monkeypatch, openf1, row):
    serve(monkeypatch, module, {"pit": [row], "drivers": r21.fixture("openf1_drivers.json")})

    assert module.pit_lane_times(2025, 21) == {}


def test_a_race_with_no_pit_rows_has_no_times_and_asks_for_no_entry_list(monkeypatch, openf1):
    fake = serve(monkeypatch, module, {})

    assert module.pit_lane_times(2025, 21) == {}
    assert fake.paths() == ["pit"]


def test_an_unreachable_openf1_is_none_not_an_empty_answer(monkeypatch, openf1):
    serve(monkeypatch, module, {"pit": httpx.Response(401)})

    assert module.pit_lane_times(2025, 21) is None


def test_an_unmatched_race_is_none(openf1):
    openf1["session"] = None

    assert module.pit_lane_times(2025, 21) is None


# --- the edition ------------------------------------------------------------------------


def test_the_2025_sao_paulo_grand_prix_is_read_with_every_source_named(sources):
    reference = module.edition_reference(EDITION)

    assert reference is not None
    assert reference["source_year"] == 2025
    assert reference["sequences"][0]["compounds"] == ["MEDIUM", "SOFT", "MEDIUM"]
    assert reference["pit_lane"] == {"median_seconds": 23.5, "stops": 34}
    assert reference["suspension_entries"] == 0
    assert reference["sources"] == {
        "stints": "openf1-stints",
        "stops": "jolpica-pitstops",
        "classification": "openf1-session-result",
        "pit_lane": "openf1-pit",
    }
    assert sorted(call[0] for call in sources["calls"]) == ["classification", "sheet", "stints"]
    assert {call[1:] for call in sources["calls"]} == {(2025, 21)}


@pytest.mark.parametrize(
    ("name", "empty"),
    [("stints", ()), ("classification", NO_CLASSIFICATION), ("sheet", NO_SHEET)],
)
def test_an_edition_missing_any_source_is_unread(sources, openf1, name, empty):
    sources[name] = empty

    assert module.edition_reference(EDITION) is None
    # The pit-lane times are not asked for an edition already known to be unread.
    assert openf1["fake"].paths() == []


def test_an_edition_whose_pit_lane_times_cannot_be_read_is_unread(sources, openf1):
    openf1["session"] = None

    assert module.edition_reference(EDITION) is None


def test_no_published_pit_lane_time_leaves_the_figure_and_its_source_out(monkeypatch, sources):
    serve(monkeypatch, module, {})

    reference = module.edition_reference(EDITION)

    assert reference is not None
    assert reference["pit_lane"] is None
    assert reference["sources"]["pit_lane"] is None


def test_an_edition_with_no_finisher_on_the_stints_is_unread(sources):
    sources["stints"] = (
        Stint(
            driver_code="ZZZ",
            team="",
            stint=1,
            compound="SOFT",
            start_lap=1,
            end_lap=5,
            laps=5,
            tyre_life_start=0,
            fresh=True,
            ended_under_red_flag=False,
        ),
    )

    assert module.edition_reference(EDITION) is None


def test_tyre_changes_under_a_red_flag_are_not_stops(sources):
    """Monza 2026's shape: the field changed tyres on lap 3 under the suspension."""
    norris = [stint for stint in r21.stints() if stint.driver_code == "NOR"]
    first, *rest = norris
    flagged = replace(first, end_lap=3, laps=3, ended_under_red_flag=True)
    sources["stints"] = (*(stint for stint in r21.stints() if stint.driver_code != "NOR"), flagged, *rest)
    suspension = tuple(PitStop(driver_code=code, stop=1, lap=3, time=None, millis=None) for code in ("NOR", "VER"))
    sources["sheet"] = PitSheet(source=JOLPICA_SOURCE, entries=r21.sheet_entries() + suspension)

    reference = module.edition_reference(EDITION)

    assert reference is not None
    assert reference["suspension_entries"] == 2
    assert reference["stop_counts"][0] == {"stops": 2, "drivers": 13}
