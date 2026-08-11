"""Tests for app.data.strategy.analysis — undercuts, pit windows, compounds.

These numbers are read as claims about what a team *did*, so the tests pin the
boundaries where a claim becomes wrong:

* **Undercut vs overcut is a sign.** Pitting before a rival is an undercut,
  after is an overcut; a flipped comparison inverts every attempt reported.
* **One stop is one attempt.** The same stop must not be counted against a
  rival twice, or the attempt list inflates.
* **Percentiles on tiny samples.** A single-driver sample must return that
  value, not crash or interpolate against nothing.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.strategy import analysis as module
from app.data.strategy.analysis import AdjacentDriver
from tests.strategy_fixture import laps_frame, results_frame, stint_rows

# ---------------------------------------------------------------------------
# _attempt_kind
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (-3, "undercut"),
        (-1, "undercut"),
        (0, None),
        (1, "overcut"),
        (3, "overcut"),
        (4, None),
        (-4, None),
    ],
)
def test_only_stops_inside_the_three_lap_window_count_as_an_attempt(delta: int, expected):
    assert module._attempt_kind(delta) == expected


# ---------------------------------------------------------------------------
# _attempts_against
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_attempt_records_the_lap_the_target_and_the_outcome():
    adjacent = AdjacentDriver(code="NOR", pit_laps=[20], outcome="gained position over NOR")

    attempts = module._attempts_against([18], adjacent)

    assert attempts == [{"type": "undercut", "target_driver": "NOR", "lap": 18, "result": "gained position over NOR"}]


@pytest.mark.unit
def test_a_single_stop_is_never_counted_as_both_an_undercut_and_an_overcut():
    """Two rival stops bracket our one stop; only the first match may score."""
    adjacent = AdjacentDriver(code="NOR", pit_laps=[22, 18], outcome="did not gain on NOR")

    attempts = module._attempts_against([20], adjacent)

    assert len(attempts) == 1
    assert attempts[0]["type"] == "undercut"


@pytest.mark.unit
def test_each_of_our_stops_can_score_its_own_attempt():
    adjacent = AdjacentDriver(code="NOR", pit_laps=[20, 40], outcome="gained position over NOR")

    attempts = module._attempts_against([18, 42], adjacent)

    assert [attempt["type"] for attempt in attempts] == ["undercut", "overcut"]
    assert [attempt["lap"] for attempt in attempts] == [18, 42]


@pytest.mark.unit
def test_stops_nowhere_near_the_rivals_produce_no_attempts():
    adjacent = AdjacentDriver(code="NOR", pit_laps=[20], outcome="did not gain on NOR")

    assert module._attempts_against([1, 45], adjacent) == []


# ---------------------------------------------------------------------------
# _get_pit_stop_laps
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pit_laps_are_the_laps_the_stint_number_changes_on():
    laps = laps_frame(stint_rows("VER", [("MEDIUM", 1, 15), ("HARD", 16, 35), ("SOFT", 36, 50)]))

    assert module._get_pit_stop_laps(laps, "VER") == [16, 36]


@pytest.mark.unit
def test_a_one_stint_race_has_no_pit_laps():
    laps = laps_frame(stint_rows("VER", [("HARD", 1, 50)]))

    assert module._get_pit_stop_laps(laps, "VER") == []


@pytest.mark.unit
def test_an_absent_driver_has_no_pit_laps():
    laps = laps_frame(stint_rows("VER", [("HARD", 1, 50)]))

    assert module._get_pit_stop_laps(laps, "NOR") == []


@pytest.mark.unit
def test_laps_missing_a_stint_number_are_skipped_when_finding_stops():
    rows = stint_rows("VER", [("MEDIUM", 1, 10), ("HARD", 11, 20)])
    for row in rows:
        if row["LapNumber"] == 11.0:
            row["Stint"] = None

    assert module._get_pit_stop_laps(laps_frame(rows), "VER") == [12]


# ---------------------------------------------------------------------------
# _analyze_undercut_overcut
# ---------------------------------------------------------------------------


def _two_car_race() -> pd.DataFrame:
    return laps_frame(
        stint_rows("VER", [("MEDIUM", 1, 18), ("HARD", 19, 50)]),
        stint_rows("NOR", [("MEDIUM", 1, 21), ("HARD", 22, 50)]),
    )


@pytest.mark.unit
def test_pitting_before_the_car_ahead_and_beating_it_reads_as_a_gain():
    attempts = module._analyze_undercut_overcut(_two_car_race(), results_frame([("VER", 1), ("NOR", 2)]), "VER")

    assert attempts == [{"type": "undercut", "target_driver": "NOR", "lap": 19, "result": "gained position over NOR"}]


@pytest.mark.unit
def test_the_rival_who_pitted_later_and_lost_reads_as_no_gain():
    attempts = module._analyze_undercut_overcut(_two_car_race(), results_frame([("VER", 1), ("NOR", 2)]), "NOR")

    assert attempts == [{"type": "overcut", "target_driver": "VER", "lap": 22, "result": "did not gain on VER"}]


@pytest.mark.unit
def test_only_rivals_within_two_places_are_compared():
    laps = laps_frame(
        stint_rows("VER", [("MEDIUM", 1, 18), ("HARD", 19, 50)]),
        stint_rows("HUL", [("MEDIUM", 1, 20), ("HARD", 21, 50)]),
    )

    attempts = module._analyze_undercut_overcut(laps, results_frame([("VER", 1), ("HUL", 4)]), "VER")

    assert attempts == []


@pytest.mark.unit
def test_a_race_with_no_results_cannot_be_analysed():
    assert module._analyze_undercut_overcut(_two_car_race(), pd.DataFrame(), "VER") == []
    assert module._analyze_undercut_overcut(_two_car_race(), None, "VER") == []


@pytest.mark.unit
def test_a_driver_missing_from_the_results_is_not_analysed():
    assert module._analyze_undercut_overcut(_two_car_race(), results_frame([("NOR", 1)]), "VER") == []


@pytest.mark.unit
def test_a_driver_who_never_pitted_has_nothing_to_attribute():
    laps = laps_frame(
        stint_rows("VER", [("HARD", 1, 50)]),
        stint_rows("NOR", [("MEDIUM", 1, 20), ("HARD", 21, 50)]),
    )

    assert module._analyze_undercut_overcut(laps, results_frame([("VER", 1), ("NOR", 2)]), "VER") == []


@pytest.mark.unit
def test_a_rival_who_never_pitted_is_skipped_rather_than_compared():
    laps = laps_frame(
        stint_rows("VER", [("MEDIUM", 1, 18), ("HARD", 19, 50)]),
        stint_rows("NOR", [("HARD", 1, 50)]),
    )

    assert module._analyze_undercut_overcut(laps, results_frame([("VER", 1), ("NOR", 2)]), "VER") == []


@pytest.mark.unit
def test_results_rows_without_a_finishing_position_are_ignored():
    results = pd.DataFrame(
        [
            {"Abbreviation": "VER", "Position": 1.0},
            {"Abbreviation": "NOR", "Position": 2.0},
            {"Abbreviation": "LAW", "Position": None},
        ]
    )

    attempts = module._analyze_undercut_overcut(_two_car_race(), results, "VER")

    assert [attempt["target_driver"] for attempt in attempts] == ["NOR"]


# ---------------------------------------------------------------------------
# _percentile
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_percentiles_interpolate_between_the_surrounding_values():
    values = [10, 20, 30, 40]

    assert module._percentile(values, 0.25) == pytest.approx(17.5)
    assert module._percentile(values, 0.5) == pytest.approx(25.0)
    assert module._percentile(values, 0.75) == pytest.approx(32.5)


@pytest.mark.unit
def test_the_extremes_land_exactly_on_the_end_values():
    assert module._percentile([5, 9, 14], 0.0) == 5.0
    assert module._percentile([5, 9, 14], 1.0) == 14.0


@pytest.mark.unit
def test_a_single_sample_is_its_own_percentile():
    assert module._percentile([21], 0.75) == 21.0


@pytest.mark.unit
def test_no_samples_yield_no_percentile():
    assert module._percentile([], 0.5) is None


@pytest.mark.unit
def test_percentiles_do_not_depend_on_input_order():
    assert module._percentile([40, 10, 30, 20], 0.25) == pytest.approx(17.5)


# ---------------------------------------------------------------------------
# _summarize_compound_stints
# ---------------------------------------------------------------------------


def _driver_stints(driver: str, stints: list[dict]) -> dict:
    return {"driver": driver, "stints": stints}


def _stint(compound: str, length: int, degradation: float | None = 0.0) -> dict:
    return {"compound": compound, "stint_length": length, "degradation_sec": degradation}


@pytest.mark.unit
def test_compounds_are_summarised_alphabetically_with_their_own_samples():
    summary = module._summarize_compound_stints(
        [
            _driver_stints("VER", [_stint("MEDIUM", 20, 1.0), _stint("HARD", 30, 0.5)]),
            _driver_stints("NOR", [_stint("MEDIUM", 24, 2.0), _stint("HARD", 26, 1.5)]),
        ]
    )

    assert [row["compound"] for row in summary] == ["HARD", "MEDIUM"]
    hard, medium = summary
    assert hard == {
        "compound": "HARD",
        "sample_size": 2,
        "median_stint": 28.0,
        "p75_stint": 29.0,
        "max_observed_stint": 30,
        "avg_degradation_sec": 1.0,
    }
    assert medium["median_stint"] == 22.0
    assert medium["avg_degradation_sec"] == 1.5


@pytest.mark.unit
def test_compound_names_are_normalised_before_grouping():
    summary = module._summarize_compound_stints([_driver_stints("VER", [_stint("soft", 10), _stint("SOFT", 12)])])

    assert len(summary) == 1
    assert summary[0]["compound"] == "SOFT"
    assert summary[0]["sample_size"] == 2


@pytest.mark.unit
def test_a_stint_with_no_compound_is_grouped_as_unknown():
    summary = module._summarize_compound_stints(
        [_driver_stints("VER", [{"compound": None, "stint_length": 10, "degradation_sec": 0.0}])]
    )

    assert summary[0]["compound"] == "UNKNOWN"


@pytest.mark.unit
def test_stints_without_a_usable_length_are_not_counted():
    summary = module._summarize_compound_stints(
        [
            _driver_stints(
                "VER",
                [_stint("SOFT", 0), _stint("SOFT", -1), {"compound": "SOFT", "stint_length": "20"}],
            )
        ]
    )

    assert summary == []


@pytest.mark.unit
def test_a_compound_with_no_degradation_readings_reports_none():
    summary = module._summarize_compound_stints(
        [_driver_stints("VER", [{"compound": "SOFT", "stint_length": 15, "degradation_sec": None}])]
    )

    assert summary[0]["avg_degradation_sec"] is None


@pytest.mark.unit
def test_a_driver_row_without_stints_contributes_nothing():
    assert module._summarize_compound_stints([{"driver": "VER"}]) == []
    assert module._summarize_compound_stints([]) == []
