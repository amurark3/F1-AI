"""Tests for app.services.race_control.baseline_plan: the "Base race plan" panel's words.

R20 2026 (São Paulo) is planned from the 2025 São Paulo Grand Prix, read from
the OpenF1 and Jolpica responses captured on 10 Nov 2026
(``sao_paulo_2025_support.reference``). On 6 Nov the panel read "Field ran a
Soft-to-Soft two-stop here in 2022 (median first stop L22, 20-car sample)",
with an undercut of 1.4 s and an overcut of 0.9 s (both formulas) and HIGH
confidence because a prediction snapshot existed.
"""

from __future__ import annotations

import json

import pytest

from app.services.race_control import baseline_plan as module
from app.services.race_control.risk import RAIN_RISK_HIGH
from tests import sao_paulo_2025_support as r21

pytestmark = pytest.mark.unit

PLANNING_YEAR = 2026
RACE_DAY_SOURCE = "Race-day forecast (Open-Meteo)"


def r20(race_day: dict | None = None, **changes) -> dict:
    return module.build_baseline(PLANNING_YEAR, {**r21.reference(), **changes}, race_day)


# --- R20 2026 from the 2025 edition ----------------------------------------------------------


def test_r20_names_the_full_sequence_its_share_the_year_and_the_previous_regulations():
    summary = r20()["primary_call"]["summary"]

    assert summary == (
        "Medium–Soft–Medium two-stop: 5 of 17 finishers ran it at the 2025 São Paulo Grand Prix "
        "(previous regulations), the winner among them. Soft–Medium–Medium two-stop was as common. "
        "13 of 17 finishers stopped twice. First stops: median L21, middle half L17–L30."
    )


def test_r20_says_where_the_plan_comes_from():
    assert r20()["data_source"] == {
        "mode": "edition",
        "edition_year": 2025,
        "event_name": "São Paulo Grand Prix",
        "round": 21,
        "previous_regulations": True,
        "sample_size": 17,
        "sources": ["OpenF1 stints", "Jolpica pit stops", "OpenF1 classification", "OpenF1 pit-lane times"],
        "unread_years": [],
    }


def test_r20_draws_the_headline_sequence_on_its_own_stop_laps():
    assert r20()["plan"] == {
        "compounds": ["Medium", "Soft", "Medium"],
        "stops": 2,
        "drivers": ["NOR", "RUS", "PIA", "ALB", "COL"],
        "finishers": 17,
        "total_laps": 71,
        "stints": [
            {"compound": "Medium", "start_lap": 1, "end_lap": 34},
            {"compound": "Soft", "start_lap": 35, "end_lap": 50},
            {"compound": "Medium", "start_lap": 51, "end_lap": 71},
        ],
    }


def test_r20_lists_the_next_sequences_stop_counts_and_first_stop_window():
    baseline = r20()

    assert baseline["alternatives"] == [
        {"compounds": ["Soft", "Medium", "Medium"], "stops": 2, "drivers": 5},
        {"compounds": ["Hard", "Medium", "Medium"], "stops": 2, "drivers": 3},
    ]
    assert baseline["stop_counts"][0] == {"stops": 2, "drivers": 13}
    assert baseline["first_stop"] == {"median_lap": 21, "p25_lap": 17, "p75_lap": 30, "drivers": 17}


def test_r20_confidence_comes_from_the_sample_and_the_editions_age_not_a_prediction():
    call = r20()["primary_call"]

    assert (call["confidence"], call["confidence_basis"]) == (
        "medium",
        "17 finishers · 2025 edition · previous regulations",
    )


def test_the_pit_model_is_the_measured_pit_lane_time_and_nothing_modelled():
    pit_model = r20()["pit_model"]

    assert pit_model == {"pit_lane_seconds": 23.5, "pit_lane_stops": 34}


def test_no_undercut_overcut_or_traffic_figure_is_sent():
    """The 1.4 s / 0.9 s were fixed formulas and traffic a heuristic; none is measured."""
    payload = json.dumps(r20())

    for key in ("undercut_delta", "overcut_delta", "traffic_threshold", "undercut_modeled", "pit_loss_seconds"):
        assert key not in payload
    assert module.UNMEASURED_NOTE in r20()["assumptions"]


def test_the_sources_note_names_every_source_and_the_compound_caveat():
    assumptions = r20()["assumptions"]

    assert assumptions[0] == (
        "Base plan: the 2025 São Paulo Grand Prix, 17 classified finishers, previous regulations. "
        "Compound sequences from OpenF1 stints; stop counts and stop laps from Jolpica pit stops; "
        "pit-lane time from OpenF1 pit-lane times; finishers from OpenF1 classification."
    )
    assert assumptions[1] == module.COMPOUNDS_NOTE


# --- the rain branch -------------------------------------------------------------------------


def test_a_wet_race_day_forecast_makes_the_dry_plan_the_secondary_branch():
    """R20's race window read 88-92% on 6 Nov; the plan above is a dry race's."""
    branch = r20({"rain_risk": 88, "confidence": RACE_DAY_SOURCE})["rain_branch"]

    assert branch == {
        "rain_pct": 88,
        "threshold_pct": RAIN_RISK_HIGH,
        "note": (
            "Race-day forecast (Open-Meteo): 88% peak rain probability in the race window, "
            "so this dry plan is the secondary branch."
        ),
    }


@pytest.mark.parametrize(
    ("race_day", "flagged"),
    [
        ({"rain_risk": 39.6, "confidence": RACE_DAY_SOURCE}, True),
        ({"rain_risk": 39.4, "confidence": RACE_DAY_SOURCE}, False),
        ({"rain_risk": 21, "confidence": RACE_DAY_SOURCE}, False),
        ({"rain_risk": None, "confidence": "The race-day forecast opens on 7 Nov."}, False),
        (None, False),
    ],
    ids=["rounds-up-to-the-cut-off", "rounds-below-it", "dry", "no-reading", "no-forecast"],
)
def test_the_rain_branch_uses_the_risk_registers_cut_off(race_day, flagged):
    assert (r20(race_day)["rain_branch"] is not None) is flagged


# --- confidence --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("edition", "planning", "finishers", "level"),
    [
        (2026, 2026, 17, "high"),
        (2026, 2027, 18, "high"),
        (2025, 2026, 17, "medium"),
        (2024, 2025, 18, "high"),
        (2023, 2025, 18, "medium"),
        (2025, 2026, 12, "low"),
        (2023, 2026, 9, "low"),
    ],
    ids=[
        "this-season",
        "last-season-same-rules",
        "last-season-previous-rules",
        "before-2026-same-rules",
        "two-seasons-old",
        "previous-rules-thin-sample",
        "everything-against-it",
    ],
)
def test_confidence_steps_down_for_older_rules_an_older_edition_and_a_thin_sample(edition, planning, finishers, level):
    assert module.plan_confidence(edition, planning, finishers)[0] == level


def test_the_confidence_basis_names_every_step_down():
    assert module.plan_confidence(2023, 2026, 9)[1] == (
        "9 finishers · 2023 edition · previous regulations · 3 seasons old · fewer than 15 finishers"
    )


# --- wording edge cases -----------------------------------------------------------------------


def test_stop_words_beyond_four_stops_are_spelled_out():
    assert module.stop_word(5) == "5-stop"


def test_a_headline_sequence_without_the_winner_does_not_claim_him():
    assert "the winner among them" not in r20(winner="VER")["primary_call"]["summary"]


def test_a_common_stop_count_beyond_two_is_counted_out():
    summary = r20(stop_counts=[{"stops": 3, "drivers": 9}])["primary_call"]["summary"]

    assert "9 of 17 finishers stopped 3 times." in summary


def test_a_field_with_no_stop_has_no_first_stop_sentence():
    summary = r20(first_stop=None)["primary_call"]["summary"]

    assert "First stops" not in summary


def test_an_edition_without_a_name_is_still_dated():
    summary = r20(event_name="")["primary_call"]["summary"]

    assert "ran it at the 2025 edition here (previous regulations)" in summary


def test_an_edition_from_the_current_rules_carries_no_regulations_label():
    baseline = module.build_baseline(2027, {**r21.reference(), "source_year": 2026}, None)

    assert "previous regulations" not in baseline["primary_call"]["summary"]
    assert baseline["data_source"]["previous_regulations"] is False
    assert "previous regulations" not in baseline["assumptions"][0]


def test_a_sequence_with_more_sets_than_stops_is_named_but_not_drawn():
    """A tyre change under a red flag is a set without a stop to split on."""
    sequences = r21.reference()["sequences"]
    red_flag = {**sequences[0], "compounds": ["MEDIUM", "SOFT", "SOFT", "MEDIUM"]}

    plan = r20(sequences=[red_flag, *sequences[1:]])["plan"]

    assert plan["compounds"] == ["Medium", "Soft", "Soft", "Medium"]
    assert plan["stints"] == []


def test_missing_pit_lane_times_and_suspension_entries_are_said():
    sources = {**r21.reference()["sources"], "pit_lane": None}

    baseline = r20(sources=sources, suspension_entries=24, pit_lane=None)

    assert (
        "Jolpica pit stops (24 red-flag suspension entries left out); pit-lane time not published;"
        in (baseline["assumptions"][0])
    )
    assert baseline["pit_model"] == {"pit_lane_seconds": None, "pit_lane_stops": None}
    assert "OpenF1 pit-lane times" not in baseline["data_source"]["sources"]


def test_a_reference_without_sources_falls_back_to_plain_names():
    baseline = r20(sources=None)

    assert baseline["data_source"]["sources"] == []
    assert (
        "Compound sequences from the stints; stop counts and stop laps from the pit sheet;"
        in (baseline["assumptions"][0])
    )


def test_a_newer_edition_that_could_not_be_read_is_named():
    baseline = module.build_baseline(2027, {**r21.reference(), "unread_years": [2026]}, None)

    assert baseline["data_source"]["unread_years"] == [2026]
    assert baseline["assumptions"][-1] == (
        "The 2026 edition could not be read right now, so this plan uses 2025. It is tried again in a few minutes."
    )


# --- no plan -----------------------------------------------------------------------------------


def test_a_circuit_with_no_edition_gets_no_invented_plan():
    """Until Nov 2026 this was a made-up Medium-Hard one-stop at 42% distance and a 21 s pit loss."""
    baseline = module.build_baseline(PLANNING_YEAR, None, {"rain_risk": 90, "confidence": RACE_DAY_SOURCE})

    assert baseline["primary_call"] == {
        "title": "Base race plan",
        "summary": module.NO_EDITION,
        "confidence": None,
        "confidence_basis": None,
    }
    assert "since 2023, OpenF1's first season" in module.NO_EDITION
    assert baseline["data_source"]["mode"] == "none"
    assert (baseline["plan"], baseline["first_stop"], baseline["rain_branch"]) == (None, None, None)
    assert baseline["pit_model"] == {"pit_lane_seconds": None, "pit_lane_stops": None}


def test_an_edition_that_cannot_be_read_now_is_named_and_retried():
    baseline = module.build_baseline(PLANNING_YEAR, {"source_year": None, "unread_years": [2025, 2024]}, None)

    assert baseline["primary_call"]["summary"] == (
        "No baseline plan right now: the tyre stints, classification or pit sheet of the 2025 and 2024 "
        "editions could not be read. It is tried again in a few minutes."
    )
    assert baseline["data_source"]["unread_years"] == [2025, 2024]


def test_a_failed_read_with_no_years_still_says_it_will_be_retried():
    baseline = module.build_baseline(PLANNING_YEAR, {"source_year": None, "unread_years": []}, None)

    assert baseline["primary_call"]["summary"] == (
        "No baseline plan right now: the circuit's last edition could not be read. It is tried again in a few minutes."
    )
