"""Tests for the pure scoring layer (app.data.predictions.scoring).

This module turns raw weekend signals into the three things a user actually
sees: the reasoning factors under each prediction, the confidence band, and the
DNF/crash risk table. It performs no I/O, so every behaviour here is a
weighting decision that can be pinned exactly.

What the assertions guard:

* the reasoning shown is the *strongest* three signals, so a sprint win can
  never be crowded out by "no prior results at this circuit";
* the confidence band narrows when signals agree and widens when they conflict,
  and a pre-qualifying prediction is never presented as confidently as a
  post-qualifying one;
* risk percentages stay inside their published bounds and stay monotone in the
  inputs that drive them — a driver with a worse retirement record must never
  come out with a lower DNF risk than an identical driver with a clean one.
"""

from __future__ import annotations

import pytest

from app.data.predictions import scoring
from app.data.predictions.scoring import (
    CRASH_RISK_THRESHOLD,
    DNF_RISK_THRESHOLD,
    FactorInputs,
    RiskContext,
    _compute_confidence,
    _compute_risk_predictions,
    _generate_factors,
    _get_team_position,
    _risk_factors,
    _risk_level,
    _safe_mean,
    safe_number,
)

CLEAN_PROFILE = {
    "starts": 10,
    "dnfs": 0,
    "crashes": 0,
    "mechanical": 0,
    "dnf_rate": 0.0,
    "crash_rate": 0.0,
    "mechanical_rate": 0.0,
    "recent_statuses": [],
}

FRAGILE_PROFILE = {
    "starts": 10,
    "dnfs": 5,
    "crashes": 3,
    "mechanical": 4,
    "dnf_rate": 0.5,
    "crash_rate": 0.3,
    "mechanical_rate": 0.4,
    "recent_statuses": ["Engine", "Accident", "Gearbox"],
}


def _prediction(code: str, position: int) -> dict:
    return {"driver_code": code, "driver_name": f"{code} Driver", "team": "Team", "position": position}


@pytest.fixture
def incidents(monkeypatch):
    """Serve a per-driver incident profile without touching f1db or FastF1."""

    profiles: dict[str, dict] = {}

    def _lookup(code, year, round_num):
        return profiles.get(code, CLEAN_PROFILE)

    monkeypatch.setattr(scoring, "_load_recent_incidents", _lookup)
    return profiles


# ---------------------------------------------------------------------------
# Numeric coercion
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_safe_mean_averages_the_values_it_is_given():
    assert _safe_mean([2, 4, 6]) == 4


@pytest.mark.unit
def test_safe_mean_falls_back_to_a_midfield_default_when_there_is_no_history():
    # A driver with no results must score as mid-pack, not as P0 (a win).
    assert _safe_mean([]) == 10.0
    assert _safe_mean([], default=15.0) == 15.0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (12, 12.0),
        ("7.5", 7.5),
        (None, 0.0),
        ("", 0.0),
        ("not a number", 0.0),
        ([], 0.0),
        (object(), 0.0),
    ],
)
def test_safe_number_coerces_untrusted_history_fields_without_raising(value, expected):
    # History rows come from JSON/Postgres, so a stored risk can legitimately be
    # a string, a null, or junk — accuracy math must not blow up on any of them.
    assert safe_number(value) == expected


# ---------------------------------------------------------------------------
# Confidence band
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_confidence_is_a_wide_default_when_there_is_only_one_signal():
    assert _compute_confidence([4.0]) == (40, 60)


@pytest.mark.unit
def test_agreeing_signals_produce_a_tighter_and_higher_confidence_band_than_conflicting_ones():
    agreeing = _compute_confidence([1.0, 1.0, 1.2])
    conflicting = _compute_confidence([1.0, 20.0, 3.0])

    assert agreeing[1] > conflicting[1]
    assert agreeing[0] > conflicting[0]


@pytest.mark.unit
def test_confidence_band_stays_inside_its_published_bounds():
    for signals in ([1.0, 1.0], [1.0, 20.0], [5.0, 5.5, 6.0, 18.0]):
        low, high = _compute_confidence(signals)
        assert 35 <= low <= high <= 95


@pytest.mark.unit
@pytest.mark.parametrize("signals", [[4.0], [1.0, 1.0], [1.0, 20.0]])
def test_pre_qualifying_predictions_are_reported_less_confidently(signals):
    # Practice pace is a weaker read than a grid slot, so the band must widen
    # downward rather than claim the same certainty.
    post = _compute_confidence(signals, is_pre_qualifying=False)
    pre = _compute_confidence(signals, is_pre_qualifying=True)

    assert pre[0] < post[0]
    assert pre[1] < post[1]
    assert pre[0] >= 20
    assert pre[1] >= pre[0] + 5


# ---------------------------------------------------------------------------
# Reasoning factors
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sprint_pos", "fragment"),
    [
        (1, "Won the sprint race"),
        (3, "Sprint race podium (P3)"),
        (8, "Points finish in sprint (P8)"),
        (15, "Sprint race P15"),
    ],
)
def test_sprint_result_is_described_by_how_good_it_was(sprint_pos, fragment):
    factors = _generate_factors(FactorInputs(sprint_pos=sprint_pos))
    assert any(fragment in factor for factor in factors)


@pytest.mark.unit
def test_a_sprint_win_outranks_every_other_signal():
    # Same-weekend race pace is the strongest read available, so it must lead
    # the reasoning even against a pole position.
    factors = _generate_factors(
        FactorInputs(sprint_pos=1, quali_pos=1, recent_positions=[1, 1, 1], circuit_positions=[1, 1], team_pos=1)
    )
    assert factors[0] == "Won the sprint race this weekend"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("quali_pos", "fragment"),
    [
        (1, "Pole position"),
        (2, "Front row start (qualifying P2)"),
        (5, "Strong qualifying (P5)"),
        (9, "Qualifying P9"),
        (18, "Qualifying P18"),
    ],
)
def test_qualifying_position_is_described_by_its_grid_slot(quali_pos, fragment):
    factors = _generate_factors(FactorInputs(quali_pos=quali_pos))
    assert any(fragment in factor for factor in factors)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("quali_pos", "fragment"),
    [
        (2, "Strong practice pace (P2 in sessions)"),
        (7, "Midfield practice pace (P7)"),
        (16, "Practice pace P16"),
    ],
)
def test_pre_qualifying_reads_the_same_number_as_practice_pace_not_a_grid_slot(quali_pos, fragment):
    factors = _generate_factors(FactorInputs(quali_pos=quali_pos, is_pre_qualifying=True))
    assert any(fragment in factor for factor in factors)


@pytest.mark.unit
def test_a_driver_with_no_session_position_gets_no_qualifying_factor():
    factors = _generate_factors(FactorInputs(quali_pos=None, team_pos=3))
    assert not any("ualifying" in factor or "ractice" in factor for factor in factors)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("recent", "fragment"),
    [
        ([1, 1, 5], "Won 2 of last 3 races"),
        ([2, 3, 9], "2 podiums in last 3 races"),
        ([4, 5, 6], "Strong recent form (avg P5)"),
        ([8, 9, 10], "Consistent points finisher (avg P9)"),
        ([14, 16, 18], "Recent average P16"),
    ],
)
def test_recent_form_is_summarised_by_the_best_thing_it_shows(recent, fragment):
    factors = _generate_factors(FactorInputs(recent_positions=recent))
    assert any(fragment in factor for factor in factors)


@pytest.mark.unit
def test_a_driver_with_no_recent_results_gets_no_form_factor():
    factors = _generate_factors(FactorInputs(recent_positions=[], team_pos=3))
    assert not any("recent" in factor.lower() or "podium" in factor for factor in factors)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("circuit", "fragment"),
    [
        ([], "No prior results at this circuit"),
        ([1, 4], "Previous winner at this circuit"),
        ([3, 8], "Podium history here (best P3"),
        ([5, 6], "Good circuit record (avg P6"),
        ([12, 14], "Circuit history avg P13"),
    ],
)
def test_circuit_record_is_reported_even_when_the_driver_has_never_raced_there(circuit, fragment):
    # The "no history" case is stated explicitly rather than omitted, so the
    # absence of a track record is visible instead of looking like an oversight.
    factors = _generate_factors(FactorInputs(circuit_positions=circuit, quali_pos=None, team_pos=20))
    assert any(fragment in factor for factor in factors)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("team_pos", "fragment"),
    [(1, "Top team (constructor P1)"), (4, "Midfield team (constructor P4)"), (9, "Constructor standing P9")],
)
def test_constructor_strength_is_banded_by_championship_position(team_pos, fragment):
    factors = _generate_factors(FactorInputs(team_pos=team_pos, quali_pos=None))
    assert any(fragment in factor for factor in factors)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("grid_delta", "fragment"),
    [(3.0, "Historically gains ~3 positions"), (-3.0, "Tends to lose ~3 positions here")],
)
def test_a_strong_overtaking_record_at_this_track_is_called_out(grid_delta, fragment):
    factors = _generate_factors(FactorInputs(grid_delta=grid_delta, quali_pos=None, team_pos=20))
    assert any(fragment in factor for factor in factors)


@pytest.mark.unit
@pytest.mark.parametrize("grid_delta", [1.5, 0.0, -1.5])
def test_a_negligible_grid_delta_is_not_worth_saying(grid_delta):
    factors = _generate_factors(FactorInputs(grid_delta=grid_delta, quali_pos=None, team_pos=20))
    assert not any("position" in factor for factor in factors)


@pytest.mark.unit
def test_only_the_three_strongest_factors_are_shown_and_they_are_ordered_by_weight():
    factors = _generate_factors(
        FactorInputs(
            sprint_pos=1,  # 6.0
            quali_pos=1,  # 5.0
            circuit_positions=[1, 2],  # 4.5
            recent_positions=[1, 1],  # 4.0
            team_pos=1,  # 3.0
            grid_delta=4.0,  # 2.0
        )
    )

    assert factors == [
        "Won the sprint race this weekend",
        "Pole position (qualifying P1)",
        "Previous winner at this circuit (best P1 in last 2 editions)",
    ]


# ---------------------------------------------------------------------------
# Team name matching
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("team_name", "expected"),
    [
        # FastF1 and Ergast disagree on team naming, so matching is substring
        # based in both directions.
        ("Red Bull Racing", 1),
        ("Red Bull", 1),
        ("scuderia ferrari", 2),
        ("Ferrari", 2),
    ],
)
def test_team_position_matches_across_the_naming_differences_between_sources(team_name, expected):
    standings = [
        {"constructor_name": "Red Bull", "position": 1},
        {"constructor_name": "Scuderia Ferrari", "position": 2},
    ]
    assert _get_team_position(team_name, standings) == expected


@pytest.mark.unit
def test_an_unrecognised_team_is_scored_as_midfield_rather_than_dropped():
    assert _get_team_position("Brabham", [{"constructor_name": "Red Bull", "position": 1}]) == 10
    assert _get_team_position("Anything", []) == 10


# ---------------------------------------------------------------------------
# Risk profile
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "low"), (12, "low"), (13, "medium"), (21, "medium"), (22, "high"), (40, "high")],
)
def test_risk_level_bands_are_monotone_in_the_percentage(value, expected):
    assert _risk_level(value) == expected


@pytest.mark.unit
def test_risk_factors_name_the_recent_retirement_record_first():
    factors = _risk_factors(
        RiskContext(profile=FRAGILE_PROFILE, quali_pos=12, team_pos=3, sprint_pos=2),
        dnf_risk=30,
        crash_risk=20,
    )
    assert factors[0] == "5 DNF events in recent history"
    assert factors[1] == "3 accident/collision flags in recent history"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("quali_pos", "fragment"),
    [(8, "highest traffic band"), (16, "highest traffic band"), (3, "Front group restart exposure")],
)
def test_grid_slot_risk_distinguishes_midfield_traffic_from_front_group_exposure(quali_pos, fragment):
    factors = _risk_factors(
        RiskContext(profile=CLEAN_PROFILE, quali_pos=quali_pos, team_pos=2, sprint_pos=1),
        dnf_risk=10,
        crash_risk=5,
    )
    assert fragment in factors[0]


@pytest.mark.unit
def test_a_weak_constructor_is_flagged_as_a_reliability_proxy():
    factors = _risk_factors(
        RiskContext(profile=CLEAN_PROFILE, quali_pos=6, team_pos=8, sprint_pos=1),
        dnf_risk=10,
        crash_risk=5,
    )
    assert "Lower constructor reliability proxy (P8)" in factors


@pytest.mark.unit
def test_a_non_sprint_weekend_is_reported_as_a_missing_signal_not_a_risk():
    factors = _risk_factors(
        RiskContext(profile=CLEAN_PROFILE, quali_pos=6, team_pos=2, sprint_pos=None),
        dnf_risk=10,
        crash_risk=5,
    )
    assert "No same-weekend sprint reliability signal" in factors


@pytest.mark.unit
def test_a_spotless_driver_still_gets_an_explanation_rather_than_an_empty_list():
    factors = _risk_factors(
        RiskContext(profile=CLEAN_PROFILE, quali_pos=6, team_pos=2, sprint_pos=1),
        dnf_risk=5,
        crash_risk=3,
    )
    assert factors == ["Low recent incident profile"]


@pytest.mark.unit
def test_high_dnf_risk_with_low_crash_risk_is_attributed_to_mechanical_failure():
    factors = _risk_factors(
        RiskContext(profile=CLEAN_PROFILE, quali_pos=6, team_pos=2, sprint_pos=1),
        dnf_risk=25,
        crash_risk=5,
    )
    assert "Risk leans mechanical rather than contact" in factors


@pytest.mark.unit
def test_risk_factors_are_capped_at_three():
    factors = _risk_factors(
        RiskContext(profile=FRAGILE_PROFILE, quali_pos=12, team_pos=9, sprint_pos=None),
        dnf_risk=40,
        crash_risk=5,
    )
    assert len(factors) == 3


@pytest.mark.unit
def test_a_fragile_driver_carries_more_dnf_risk_than_an_identical_reliable_one(incidents):
    incidents["VER"] = CLEAN_PROFILE
    incidents["HUL"] = FRAGILE_PROFILE

    rows = _compute_risk_predictions(
        [_prediction("VER", 1), _prediction("HUL", 2)],
        {"VER": {"quali_pos": 5, "team_pos": 2}, "HUL": {"quali_pos": 5, "team_pos": 2}},
        2026,
        4,
    )
    by_code = {row["driver_code"]: row for row in rows}

    # Identical grid slot and team: retirement history is the only difference,
    # so it must be the only thing moving the risk.
    assert by_code["HUL"]["dnf_risk_pct"] > by_code["VER"]["dnf_risk_pct"]
    assert by_code["HUL"]["crash_risk_pct"] > by_code["VER"]["crash_risk_pct"]


@pytest.mark.unit
def test_a_slower_team_carries_more_dnf_risk_than_a_front_running_one(incidents):
    rows = _compute_risk_predictions(
        [_prediction("VER", 1), _prediction("SAR", 2)],
        {"VER": {"quali_pos": 5, "team_pos": 1}, "SAR": {"quali_pos": 5, "team_pos": 10}},
        2026,
        4,
    )
    by_code = {row["driver_code"]: row for row in rows}

    assert by_code["SAR"]["dnf_risk_pct"] > by_code["VER"]["dnf_risk_pct"]


@pytest.mark.unit
def test_risk_rows_are_ordered_most_at_risk_first(incidents):
    incidents["HUL"] = FRAGILE_PROFILE

    rows = _compute_risk_predictions(
        [_prediction("VER", 1), _prediction("HUL", 2), _prediction("NOR", 3)],
        {code: {"quali_pos": 5, "team_pos": 2} for code in ("VER", "HUL", "NOR")},
        2026,
        4,
    )

    assert rows[0]["driver_code"] == "HUL"
    assert [row["dnf_risk_pct"] for row in rows] == sorted((row["dnf_risk_pct"] for row in rows), reverse=True)


@pytest.mark.unit
def test_risk_percentages_stay_inside_their_published_bounds(incidents):
    incidents["HUL"] = FRAGILE_PROFILE

    rows = _compute_risk_predictions(
        [_prediction("VER", 1), _prediction("HUL", 12)],
        {"VER": {"quali_pos": 1, "team_pos": 1}, "HUL": {"quali_pos": 12, "team_pos": 10}},
        2026,
        4,
    )

    for row in rows:
        assert 3 <= row["dnf_risk_pct"] <= 42
        assert 1 <= row["crash_risk_pct"] <= 30
        assert 2 <= row["mechanical_risk_pct"] <= 35
        assert row["risk_level"] == _risk_level(row["dnf_risk_pct"])


@pytest.mark.unit
def test_risk_rows_fall_back_to_the_predicted_finish_when_no_scored_row_exists(incidents):
    # A driver present in the ranked predictions but missing from the scored map
    # must still get a risk row, using its projected finish as the grid proxy.
    rows = _compute_risk_predictions([_prediction("ALO", 12)], {}, 2026, 4)

    assert len(rows) == 1
    assert rows[0]["projected_finish"] == 12
    assert "Starts in the highest traffic band" in rows[0]["factors"]


@pytest.mark.unit
def test_risk_rows_carry_the_identity_the_ui_renders(incidents):
    rows = _compute_risk_predictions([_prediction("VER", 1)], {"VER": {"quali_pos": 1, "team_pos": 1}}, 2026, 4)

    assert rows[0]["driver_name"] == "VER Driver"
    assert rows[0]["team"] == "Team"


@pytest.mark.unit
def test_risk_thresholds_are_shared_so_review_and_accuracy_score_identically():
    from app.data.predictions import accuracy, review

    assert accuracy.DNF_RISK_THRESHOLD is DNF_RISK_THRESHOLD
    assert review.CRASH_RISK_THRESHOLD is CRASH_RISK_THRESHOLD
