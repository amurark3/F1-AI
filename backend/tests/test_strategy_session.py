"""Tests for app.data.strategy.session — loading a race and reading its stints.

Every other strategy module builds on the stint list this file produces, so the
risks are the ones that would quietly poison everything downstream:

* **Pit in/out laps polluting stint pace.** Those laps run seconds slow; an
  unfiltered mean describes the pit stop rather than the stint.
* **Degradation read from too few laps.** A trend taken from two laps is noise
  presented as tyre wear, so short stints must report 0.0.
* **A failed read masquerading as an empty race.** It has to return
  None so callers degrade rather than reporting a race with no strategy.
* **A location the history cannot find.** The history matches past seasons on
  f1db's calendar, so the race's location is f1db's ("Montreal"), not FastF1's
  ("Montréal").
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from app.data.f1db_calendar import CalendarUnavailableError
from app.data.openf1.client import OpenF1UnavailableError
from app.data.strategy import session as module
from tests.strategy_fixture import laps_frame, stint_rows
from tests.strategy_openf1_support import (
    race_classification_2025,
    race_session_laps,
    race_stints_2025,
)


@pytest.fixture(autouse=True)
def _calendar(calendar_f1db):
    """f1db's real 2026 calendar: R5 is Canada, R6 Monaco, R7 Barcelona."""


@pytest.fixture(autouse=True)
def _clear_cache():
    """The race loader memoises per (year, round) for the process lifetime."""
    module._race_data_cache.clear()
    yield
    module._race_data_cache.clear()


@pytest.fixture(autouse=True)
def _openf1(monkeypatch, no_fastf1):
    """The race, as OpenF1 publishes it, with every FastF1 request refused."""
    monkeypatch.setattr(module, "load_session_laps", lambda year, rnd, code: race_session_laps())
    monkeypatch.setattr(module, "race_stints", lambda year, rnd: race_stints_2025())
    monkeypatch.setattr(module, "race_classification", lambda year, rnd: race_classification_2025())


# ---------------------------------------------------------------------------
# _fmt_laptime
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (75.432, "1:15.432"),
        (60.0, "1:00.000"),
        (59.999, "59.999"),
        (9.5, "9.500"),
        (3661.0, "61:01.000"),
    ],
)
def test_lap_times_are_formatted_as_minutes_and_seconds(seconds: float, expected: str):
    assert module._fmt_laptime(pd.to_timedelta(seconds, unit="s")) == expected


@pytest.mark.unit
def test_a_missing_lap_time_renders_as_a_dash():
    assert module._fmt_laptime(pd.NaT) == "-"


# ---------------------------------------------------------------------------
# _load_race_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_loaded_race_exposes_its_laps_results_and_event_identity():
    data = module._load_race_data(2026, 5)

    assert data is not None
    assert data["event_name"] == "Canadian Grand Prix"
    assert data["location"] == "Montreal"
    assert set(data) == {"laps", "results", "event_name", "location"}
    assert len(data["laps"]) == 71
    assert data["results"].iloc[0].to_dict() == {"Abbreviation": "NOR", "Position": 1.0}
    # Three cars have no classified position (retirements) and are not in the order.
    assert len(data["results"]) == 17


@pytest.mark.unit
def test_the_laps_frame_tags_each_lap_with_its_stint_from_race_stints():
    laps = module._load_race_data(2026, 5)["laps"]

    stints = module._extract_stint_data(laps, "ANT")

    assert [(s["stint"], s["compound"], s["laps"], s["stint_length"]) for s in stints] == [
        (1, "SOFT", "1-21", 21),
        (2, "MEDIUM", "22-47", 26),
        (3, "MEDIUM", "48-71", 24),
    ]
    # OpenF1 says SOFT's first set was used, the second new; stint 3 was not.
    assert [s["fresh_tyres"] for s in stints] == [False, True, False]
    assert [p["lap"] for p in module._extract_pit_stops(laps, None, "ANT")] == [22, 48]


@pytest.mark.unit
def test_a_lap_outside_every_stint_has_no_stint_and_a_car_off_the_entry_list_is_dropped(monkeypatch):
    race = race_session_laps()
    stranger = replace(race.laps[0], driver=99)
    monkeypatch.setattr(module, "load_session_laps", lambda *a: replace(race, laps=(stranger, *race.laps)))
    monkeypatch.setattr(module, "race_stints", lambda *a: tuple(s for s in race_stints_2025() if s.stint != 2))

    laps = module._load_race_data(2026, 5)["laps"]

    assert len(laps) == 71
    ant = laps[laps["Driver"] == "ANT"]
    assert ant[ant["LapNumber"] == 30.0]["Stint"].isna().all()


@pytest.mark.unit
def test_a_classified_car_without_a_position_is_left_out_of_the_results(monkeypatch):
    classification = race_classification_2025()
    unplaced = replace(classification.drivers[0], position=None)
    monkeypatch.setattr(
        module,
        "race_classification",
        lambda *a: replace(classification, drivers=(unplaced, *classification.drivers[1:])),
    )

    assert len(module._load_race_data(2026, 5)["results"]) == 16


@pytest.mark.unit
def test_an_event_off_f1dbs_calendar_is_named_by_its_round_and_has_no_location():
    data = module._load_race_data(2026, 30)

    assert (data["event_name"], data["location"]) == ("Round 30", "")


@pytest.mark.unit
def test_a_second_request_for_the_same_race_is_served_from_cache(monkeypatch):
    asked = []
    monkeypatch.setattr(module, "load_session_laps", lambda *a: asked.append(a) or race_session_laps())

    first = module._load_race_data(2026, 5)
    second = module._load_race_data(2026, 5)

    assert first is second
    assert len(asked) == 1


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["session", "laps", "stints"])
def test_a_race_with_nothing_to_read_returns_nothing_and_is_not_cached(monkeypatch, missing):
    race = race_session_laps()
    if missing == "session":
        monkeypatch.setattr(module, "load_session_laps", lambda *a: None)
    elif missing == "laps":
        monkeypatch.setattr(module, "load_session_laps", lambda *a: replace(race, laps=()))
    else:
        monkeypatch.setattr(module, "race_stints", lambda *a: ())

    assert module._load_race_data(2026, 5) is None
    assert module._race_data_cache == {}


@pytest.mark.unit
@pytest.mark.parametrize("error", [OpenF1UnavailableError("429"), CalendarUnavailableError("no season")])
def test_a_source_that_cannot_answer_degrades_to_nothing_and_is_not_cached(monkeypatch, error):
    def refuse(*args):
        raise error

    monkeypatch.setattr(module, "load_session_laps", refuse)

    assert module._load_race_data(2026, 5) is None
    assert module._race_data_cache == {}


# ---------------------------------------------------------------------------
# _stint_compound
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_stint_compound_is_the_one_most_of_its_laps_report():
    stint = pd.DataFrame({"Compound": ["MEDIUM", "MEDIUM", "SOFT"]})

    assert module._stint_compound(stint) == "MEDIUM"


@pytest.mark.unit
def test_a_stint_with_no_compound_data_is_unknown():
    stint = pd.DataFrame({"Compound": [None, None]})

    assert module._stint_compound(stint) == "UNKNOWN"


# ---------------------------------------------------------------------------
# _representative_lap_time
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_stint_pace_ignores_the_pit_lap_that_would_otherwise_dominate_it():
    # 200s is past 1.5x the 90.5s median, so only the green-flag laps average.
    times = pd.Series(pd.to_timedelta([90.0, 90.0, 91.0, 200.0], unit="s"))

    assert module._representative_lap_time(times) == "1:30.333"


@pytest.mark.unit
def test_a_stint_with_no_timed_laps_reports_a_dash():
    assert module._representative_lap_time(pd.Series([], dtype="timedelta64[ns]")) == "-"


@pytest.mark.unit
def test_when_every_lap_is_an_outlier_the_unfiltered_mean_is_used():
    """Two laps that straddle 1.5x the median leave the filter empty."""
    times = pd.Series(pd.to_timedelta([60.0, 120.0], unit="s"))

    assert module._representative_lap_time(times) == "1:30.000"


# ---------------------------------------------------------------------------
# _stint_degradation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_degradation_is_the_gap_between_the_opening_and_closing_laps():
    laps = pd.DataFrame(
        {
            "LapNumber": [6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
            "LapTime": pd.to_timedelta([92.0, 91.5, 91.0, 90.5, 90.0, 89.5], unit="s"),
        }
    )
    valid = laps["LapTime"]

    # Sorted by lap: laps 1-3 average 90.0s, laps 4-6 average 91.5s.
    assert module._stint_degradation(laps, valid) == pytest.approx(1.5)


@pytest.mark.unit
def test_a_stint_too_short_to_read_a_trend_reports_no_degradation():
    laps = pd.DataFrame({"LapNumber": [1.0, 2.0, 3.0], "LapTime": pd.to_timedelta([90.0, 91.0, 92.0], unit="s")})

    assert module._stint_degradation(laps, laps["LapTime"]) == 0.0


@pytest.mark.unit
def test_untimed_laps_are_not_counted_toward_the_degradation_sample():
    laps = pd.DataFrame(
        {
            "LapNumber": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
            "LapTime": pd.to_timedelta([90.0, None, None, None, None, None, 95.0], unit="s"),
        }
    )
    valid = pd.Series(pd.to_timedelta([90.0] * 6, unit="s"))

    assert module._stint_degradation(laps, valid) == 0.0


# ---------------------------------------------------------------------------
# _fresh_tyres
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("flag", [True, False])
def test_the_feeds_fresh_tyre_flag_is_used_when_present(flag: bool):
    stint = pd.DataFrame({"FreshTyre": [flag, flag]})

    assert module._fresh_tyres(stint, 1.0) is flag


@pytest.mark.unit
@pytest.mark.parametrize(("stint_num", "expected"), [(1.0, False), (2.0, True)])
def test_without_the_flag_only_later_stints_are_assumed_fresh(stint_num: float, expected: bool):
    """The opening stint is usually a carried-over qualifying set."""
    stint = pd.DataFrame({"FreshTyre": [None, None]})

    assert module._fresh_tyres(stint, stint_num) is expected


@pytest.mark.unit
def test_a_frame_without_the_column_at_all_falls_back_to_the_stint_number():
    assert module._fresh_tyres(pd.DataFrame({"LapNumber": [1.0]}), 3.0) is True


# ---------------------------------------------------------------------------
# _extract_stint_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_each_stint_reports_its_compound_lap_range_and_length():
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 20), ("HARD", 21, 50)]))

    stints = module._extract_stint_data(laps, "VER")

    assert [stint["stint"] for stint in stints] == [1, 2]
    assert [stint["compound"] for stint in stints] == ["MEDIUM", "HARD"]
    assert stints[0]["laps"] == "1-20"
    assert stints[0]["stint_length"] == 20
    assert stints[1]["laps"] == "21-50"
    assert stints[1]["stint_length"] == 30
    # The opening set is carried over from qualifying; the second stint is new.
    assert not stints[0]["fresh_tyres"]
    assert stints[1]["fresh_tyres"]


@pytest.mark.unit
def test_stints_are_reported_in_order_even_when_the_laps_arrive_shuffled():
    rows = stint_rows("VER", [("SOFT", 1, 10), ("HARD", 11, 20)])
    laps = laps_frame(list(reversed(rows)))

    stints = module._extract_stint_data(laps, "VER")

    assert [stint["laps"] for stint in stints] == ["1-10", "11-20"]


@pytest.mark.unit
def test_a_driver_with_no_laps_has_no_stints():
    laps = laps_frame(stint_rows("VER", [("SOFT", 1, 10)]))

    assert module._extract_stint_data(laps, "NOR") == []


@pytest.mark.unit
def test_laps_without_a_stint_number_are_ignored():
    rows = stint_rows("VER", [("SOFT", 1, 5)])
    for row in rows[:2]:
        row["Stint"] = None

    stints = module._extract_stint_data(laps_frame(rows), "VER")

    assert len(stints) == 1
    assert stints[0]["laps"] == "3-5"


@pytest.mark.unit
def test_a_stint_whose_laps_are_all_unnumbered_is_skipped():
    rows = stint_rows("VER", [("SOFT", 1, 3), ("HARD", 4, 8)])
    for row in rows:
        if row["Stint"] == 1.0:
            row["LapNumber"] = None

    stints = module._extract_stint_data(laps_frame(rows), "VER")

    assert [stint["compound"] for stint in stints] == ["HARD"]


@pytest.mark.unit
def test_degradation_is_reported_per_stint_from_its_own_laps():
    rising = [90.0 + index * 0.5 for index in range(12)]
    laps = laps_frame(stint_rows("VER", [("SOFT", 1, 12)], lap_seconds=rising))

    stints = module._extract_stint_data(laps, "VER")

    assert stints[0]["degradation_sec"] == pytest.approx(4.5)
    assert stints[0]["avg_lap_time"] == "1:32.750"


# ---------------------------------------------------------------------------
# _extract_pit_stops
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_pit_stop_is_recorded_at_the_lap_the_stint_number_changes():
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 20), ("HARD", 21, 40), ("SOFT", 41, 50)], position=3))

    stops = module._extract_pit_stops(laps, pd.DataFrame(), "VER")

    assert [stop["lap"] for stop in stops] == [21, 41]
    assert stops[0]["position_before"] == stops[0]["position_after"] == 3


@pytest.mark.unit
def test_a_driver_who_never_pitted_has_no_stops():
    laps = laps_frame(stint_rows("VER", [("HARD", 1, 50)]))

    assert module._extract_pit_stops(laps, pd.DataFrame(), "VER") == []


@pytest.mark.unit
def test_a_stop_without_position_data_records_no_position():
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 10), ("HARD", 11, 20)]))

    stops = module._extract_pit_stops(laps, pd.DataFrame(), "VER")

    assert stops[0]["position_before"] is None
    assert stops[0]["position_after"] is None


@pytest.mark.unit
def test_laps_with_no_stint_number_do_not_register_as_stops():
    rows = stint_rows("VER", [("MEDIUM", 1, 10), ("HARD", 11, 20)])
    for row in rows:
        if row["LapNumber"] == 11.0:
            row["Stint"] = None

    stops = module._extract_pit_stops(laps_frame(rows), pd.DataFrame(), "VER")

    assert [stop["lap"] for stop in stops] == [12]


@pytest.mark.unit
def test_an_absent_driver_has_no_pit_stops():
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 10)]))

    assert module._extract_pit_stops(laps, pd.DataFrame(), "NOR") == []
