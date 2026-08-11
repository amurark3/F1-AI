"""Tests for app.services.race_control.strategy_context — the command-center
shell and the strategy numbers printed inside it.

The risk this module carries is the one the hardcoded-data audit is about: pit
loss, first-stop laps, undercut/overcut deltas and rejoin traffic are shown as
pit-wall numbers, but only *some* of them are measured. When
``circuit_strategy_reference`` returns telemetry from a completed edition the
values are real; otherwise circuit-shape formulas fill the same fields with the
same shape. So each fallback is tested for the flag that distinguishes it
(``data_source.mode``, ``*_modeled``) as well as for its value — a number that
loses its "modeled" marker is indistinguishable from a measurement.

The dashboard half carries a different risk: session status ("in_progress")
drives the live banner, the workstream board and the risk register, and it is
derived purely from clock arithmetic over the FastF1 schedule.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.services.race_control import strategy_context as module

_NOW = datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _row(**fields) -> dict:
    """One schedule row: practice on Friday, the Grand Prix on Sunday.

    Only ``Session1`` and ``Session5`` columns exist, which is also how the real
    frame looks for a testing-free calendar entry with gaps — the loop has to
    tolerate session slots that are absent from the frame entirely.
    """
    base = {
        "RoundNumber": 1,
        "EventName": "Bahrain Grand Prix",
        "Location": "Sakhir",
        "Country": "Bahrain",
        "EventDate": pd.Timestamp("2026-03-08"),
        "Session1": "Practice 1",
        "Session1DateUtc": pd.Timestamp(_NOW - timedelta(days=30)),
        "Session5": "Race",
        "Session5DateUtc": pd.Timestamp(_NOW - timedelta(days=28)),
    }
    return {**base, **fields}


def _upcoming_row(**fields) -> dict:
    base = {
        "RoundNumber": 2,
        "EventName": "Monaco Grand Prix",
        "Location": "Monaco",
        "Country": "Monaco",
        "EventDate": pd.Timestamp("2026-05-24"),
        "Session1DateUtc": pd.Timestamp(_NOW + timedelta(days=9, hours=6)),
        "Session5DateUtc": pd.Timestamp(_NOW + timedelta(days=11)),
    }
    return _row(**{**base, **fields})


def _stub_schedule(monkeypatch: pytest.MonkeyPatch, rows: list[dict]) -> None:
    frame = pd.DataFrame(rows)
    monkeypatch.setattr(module.fastf1, "get_event_schedule", lambda **_kwargs: frame)


def _stub_standings(monkeypatch: pytest.MonkeyPatch, **feeds) -> None:
    """Serve fixed ``(drivers, constructors)`` for the championship block."""
    drivers = feeds.get("drivers", [])
    constructors = feeds.get("constructors", [])
    monkeypatch.setattr(module, "get_standings_snapshot", lambda _year: (drivers, constructors))


def _team(rank: int, points: float) -> dict:
    return {"position": rank, "team": f"Team {rank}", "points": points, "wins": 0}


# ---------------------------------------------------------------------------
# build_strategy_dashboard — session status
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dashboard_grades_each_weekend_from_the_session_clock(monkeypatch):
    """A race an hour old is still running: "completed" needs the last session
    plus three hours, which is roughly a Grand Prix distance."""
    _stub_schedule(
        monkeypatch,
        [
            _row(),
            _row(
                RoundNumber=2,
                Session1DateUtc=pd.Timestamp(_NOW - timedelta(hours=2)),
                Session5DateUtc=pd.Timestamp(_NOW - timedelta(hours=1)),
            ),
            _upcoming_row(RoundNumber=3),
        ],
    )
    _stub_standings(monkeypatch)

    dashboard = module.build_strategy_dashboard(2026)

    assert dashboard["season"] == {"total_events": 3, "completed_events": 1, "upcoming_events": 1}
    assert dashboard["race"]["round"] == 2, "the one that is neither finished nor future is the live one"


@pytest.mark.unit
def test_dashboard_selects_the_live_session_over_the_next_race(monkeypatch):
    _stub_schedule(
        monkeypatch,
        [
            _row(
                RoundNumber=2,
                Session1DateUtc=pd.Timestamp(_NOW - timedelta(hours=2)),
                Session5DateUtc=pd.Timestamp(_NOW + timedelta(hours=1)),
            ),
            _upcoming_row(RoundNumber=3),
        ],
    )
    _stub_standings(monkeypatch)

    dashboard = module.build_strategy_dashboard(2026)

    assert dashboard["race"]["round"] == 2
    assert dashboard["race"]["status"] == "in_progress"
    assert dashboard["focus"] == "Live session control"
    # A live event has no countdown — the clock is already past lights out.
    assert dashboard["race"]["days_until"] is None


@pytest.mark.unit
def test_dashboard_counts_whole_days_to_the_first_session_of_the_next_race(monkeypatch):
    _stub_schedule(monkeypatch, [_row(), _upcoming_row()])
    _stub_standings(monkeypatch)

    dashboard = module.build_strategy_dashboard(2026)

    assert dashboard["race"]["round"] == 2
    assert dashboard["race"]["days_until"] == 9
    assert dashboard["focus"] == "Race-week strategy lock"


@pytest.mark.unit
def test_dashboard_never_reports_a_negative_countdown(monkeypatch):
    """Between "now" and the first session there can be seconds, not days."""
    _stub_schedule(
        monkeypatch,
        [
            _row(
                Session1DateUtc=pd.Timestamp(_NOW + timedelta(seconds=30)),
                Session5DateUtc=pd.Timestamp(_NOW + timedelta(days=2)),
            )
        ],
    )
    _stub_standings(monkeypatch)

    assert module.build_strategy_dashboard(2026)["race"]["days_until"] == 0


@pytest.mark.unit
def test_dashboard_falls_back_to_the_last_event_once_every_race_is_run(monkeypatch):
    _stub_schedule(monkeypatch, [_row(), _row(RoundNumber=2, EventName="Monaco Grand Prix")])
    _stub_standings(monkeypatch)

    dashboard = module.build_strategy_dashboard(2026)

    assert dashboard["race"]["round"] == 2
    assert dashboard["season"]["upcoming_events"] == 0


@pytest.mark.unit
def test_dashboard_has_no_race_and_a_season_review_focus_for_an_empty_calendar(monkeypatch):
    _stub_schedule(monkeypatch, [])
    _stub_standings(monkeypatch)

    dashboard = module.build_strategy_dashboard(2026)

    assert dashboard["race"] is None
    assert dashboard["focus"] == "Season review"
    assert dashboard["season"] == {"total_events": 0, "completed_events": 0, "upcoming_events": 0}


# ---------------------------------------------------------------------------
# build_strategy_dashboard — event payload
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dashboard_lists_only_dated_sessions_and_stamps_them_in_utc(monkeypatch):
    """An undated session must be dropped, not rendered with a null timestamp."""
    _stub_schedule(monkeypatch, [_row(Session5DateUtc=pd.NaT)])
    _stub_standings(monkeypatch)

    event = module.build_strategy_dashboard(2026)["race"]

    assert list(event["sessions"]) == ["Practice 1"]
    assert event["sessions"]["Practice 1"].endswith("Z")
    assert event["race_session"] is None, "no dated race session means no countdown target"


@pytest.mark.unit
def test_dashboard_ignores_a_session_slot_with_no_name(monkeypatch):
    """A calendar entry can carry a session date with the name still blank."""
    _stub_schedule(monkeypatch, [_upcoming_row(Session1=None)])
    _stub_standings(monkeypatch)

    event = module.build_strategy_dashboard(2026)["race"]

    assert list(event["sessions"]) == ["Race"]
    # The countdown now runs to the race itself, the only session left dated.
    assert event["days_until"] == 10


@pytest.mark.unit
def test_dashboard_marks_a_sprint_weekend_from_the_session_list(monkeypatch):
    _stub_schedule(
        monkeypatch,
        [_row(Session1="Sprint", Session1DateUtc=pd.Timestamp(_NOW + timedelta(days=2)))],
    )
    _stub_standings(monkeypatch)

    event = module.build_strategy_dashboard(2026)["race"]

    assert event["is_sprint"] is True
    assert event["sessions"]["Sprint"].endswith("Z")


@pytest.mark.unit
def test_dashboard_attaches_circuit_metadata_and_a_race_session_stamp(monkeypatch):
    _stub_schedule(monkeypatch, [_upcoming_row()])
    _stub_standings(monkeypatch)

    event = module.build_strategy_dashboard(2026)["race"]

    assert event["location"] == "Monaco, Monaco"
    assert event["circuit"]["circuit_type"] == "Street circuit"
    assert event["race_session"].startswith(str((_NOW + timedelta(days=11)).year))
    assert event["date"] == "2026-05-24T00:00:00"


@pytest.mark.unit
def test_dashboard_leaves_circuit_null_for_a_venue_with_no_reference_entry(monkeypatch):
    """An unmapped venue must return no metadata rather than a neighbour's."""
    _stub_schedule(monkeypatch, [_upcoming_row(Location="Kyalami", Country="South Africa")])
    _stub_standings(monkeypatch)

    assert module.build_strategy_dashboard(2026)["race"]["circuit"] is None


@pytest.mark.unit
def test_dashboard_truncates_both_championship_tables_to_five_rows(monkeypatch):
    _stub_schedule(monkeypatch, [_upcoming_row()])
    _stub_standings(
        monkeypatch,
        drivers=[{"position": rank, "code": f"D{rank}"} for rank in range(1, 8)],
        constructors=[_team(rank, 100 - rank) for rank in range(1, 8)],
    )

    dashboard = module.build_strategy_dashboard(2026)

    assert [row["position"] for row in dashboard["championship"]["drivers"]] == [1, 2, 3, 4, 5]
    assert len(dashboard["championship"]["constructors"]) == 5
    assert dashboard["year"] == 2026
    assert dashboard["generated_at"].endswith("+00:00")


# ---------------------------------------------------------------------------
# derive_traffic_threshold
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("window", "expected"),
    [(0, "high"), (4, "high"), (5, "medium"), (9, "medium"), (10, "low"), (30, "low")],
    ids=["identical-laps", "at-high-cutoff", "just-over", "at-medium-cutoff", "just-over-medium", "spread-out"],
)
def test_traffic_threshold_reads_the_real_first_stop_spread(window, expected):
    """A narrow first-stop window means the field pits together, so rejoins are busy."""
    label, modeled = module.derive_traffic_threshold({"first_stop_p25": 20, "first_stop_p75": 20 + window}, False)

    assert (label, modeled) == (expected, False)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("window", "expected"),
    [(0, "high"), (5, "high"), (10, "medium")],
    ids=["already-high", "bumped-to-high", "bumped-to-medium"],
)
def test_traffic_threshold_bumps_street_circuits_one_level_and_caps_at_high(window, expected):
    label, modeled = module.derive_traffic_threshold({"first_stop_p25": 20, "first_stop_p75": 20 + window}, True)

    assert (label, modeled) == (expected, False)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("reference", "street", "expected"),
    [
        ({}, False, "medium"),
        ({}, True, "high"),
        ({"first_stop_p25": 20}, False, "medium"),
        ({"first_stop_p75": 28}, True, "high"),
        ({"first_stop_p25": None, "first_stop_p75": None}, False, "medium"),
    ],
    ids=["no-telemetry", "no-telemetry-street", "half-a-window", "half-a-window-street", "null-percentiles"],
)
def test_traffic_threshold_flags_itself_modeled_without_a_full_window(reference, street, expected):
    """Circuit shape alone is a guess, and the caller has to be able to tell."""
    label, modeled = module.derive_traffic_threshold(reference, street)

    assert (label, modeled) == (expected, True)


# ---------------------------------------------------------------------------
# build_strategy_context — telemetry vs heuristic
# ---------------------------------------------------------------------------

_TELEMETRY = {
    "pit_loss_seconds": 19.4,
    "median_first_stop": 22,
    "first_stop_p25": 18,
    "first_stop_p75": 27,
    "opening_compound": "Soft",
    "finishing_compound": "Medium",
    "most_common_stops": 2,
    "source_year": 2025,
    "sample_size": 18,
}


def _race(**fields) -> dict:
    base = {"status": "upcoming", "is_sprint": False, "circuit": {"laps": 57, "circuit_type": "Purpose-built"}}
    return {**base, **fields}


@pytest.mark.unit
def test_context_sources_the_pit_model_from_telemetry_and_says_so():
    context = module.build_strategy_context(_race(), [], None, _TELEMETRY)

    assert context["data_source"] == {"mode": "telemetry", "edition_year": 2025, "sample_size": 18}
    assert context["pit_model"]["pit_loss_seconds"] == 19.4
    assert context["stint_windows"]["modeled"] is False
    assert context["stint_windows"]["primary_lap"] == 22
    assert context["stint_windows"]["offset_lap"] == 18
    # Late window is the measured p75 plus a permanent-circuit buffer, capped
    # so the last stop cannot land inside the final eight laps.
    assert context["stint_windows"]["late_lap"] == 37


@pytest.mark.unit
def test_context_quotes_the_measured_edition_in_the_base_plan():
    context = module.build_strategy_context(_race(), [], None, _TELEMETRY)

    summary = context["primary_call"]["summary"]
    assert "Soft-to-Medium two-stop here in 2025" in summary
    assert "median first stop L22, 18-car sample" in summary
    # With a real two-stop baseline the branch to keep alive is the one-stop.
    assert "keep a one-stop branch open" in summary
    assert context["primary_call"]["confidence"] == "medium"


@pytest.mark.unit
def test_context_marks_the_heuristic_plan_as_heuristic_everywhere_it_shows():
    context = module.build_strategy_context(_race(), [], None, None)

    assert context["data_source"] == {"mode": "heuristic", "edition_year": None, "sample_size": None}
    assert context["stint_windows"]["modeled"] is True
    assert "no completed edition of this circuit was available for telemetry" in context["assumptions"][2]
    assert context["primary_call"]["confidence"] == "low"
    assert "Model a medium-to-hard one-stop" in context["primary_call"]["summary"]


@pytest.mark.unit
def test_context_still_calls_undercut_and_overcut_modeled_under_full_telemetry():
    """Audit item 2.1: the telemetry reference never carries these two deltas."""
    context = module.build_strategy_context(_race(), [], None, _TELEMETRY)

    assert context["pit_model"]["undercut_modeled"] is True
    assert context["pit_model"]["overcut_modeled"] is True
    assert context["pit_model"]["traffic_modeled"] is False
    assert "Undercut and overcut deltas remain modeled estimates" in context["assumptions"][1]


@pytest.mark.unit
def test_context_uses_measured_deltas_when_the_reference_ever_provides_them():
    context = module.build_strategy_context(
        _race(), [], None, {**_TELEMETRY, "undercut_delta": 0.9, "overcut_delta": 0.3}
    )

    assert context["pit_model"]["undercut_delta"] == 0.9
    assert context["pit_model"]["overcut_delta"] == 0.3
    assert context["pit_model"]["undercut_modeled"] is False
    assert context["pit_model"]["overcut_modeled"] is False


# ---------------------------------------------------------------------------
# build_strategy_context — circuit-shape fallbacks
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("circuit_type", "pit_loss", "undercut"),
    [("Street", 24, 1.6), ("street", 24, 1.6), ("Purpose-built", 21, 1.4)],
    ids=["street", "lowercase-street", "permanent"],
)
def test_context_derives_the_fallback_pit_model_from_circuit_shape(circuit_type, pit_loss, undercut):
    context = module.build_strategy_context(_race(circuit={"laps": 57, "circuit_type": circuit_type}), [], None)

    assert context["pit_model"]["pit_loss_seconds"] == pit_loss
    assert context["pit_model"]["undercut_delta"] == undercut


@pytest.mark.unit
def test_context_treats_a_real_street_circuit_as_permanent():
    """Pins a live bug: the only circuit-type strings the app ever produces are
    ``CIRCUIT_DATA``'s ``"Street circuit"`` / ``"Purpose-built"``, but the test
    here is ``lower() == "street"``. Monaco therefore gets Monza's pit loss,
    tyre windows and rejoin-traffic floor. Not fixed here — pinned so the fix
    has a failing assertion to flip."""
    monaco = module.build_strategy_context(_race(circuit={"laps": 78, "circuit_type": "Street circuit"}), [], None)
    monza = module.build_strategy_context(_race(circuit={"laps": 78, "circuit_type": "Purpose-built"}), [], None)

    assert monaco["pit_model"] == monza["pit_model"]
    assert monaco["stint_windows"] == monza["stint_windows"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("is_sprint", "overcut"), [(True, 1.0), (False, 0.9)], ids=["sprint-weekend", "normal-weekend"]
)
def test_context_widens_the_fallback_overcut_on_a_sprint_weekend(is_sprint, overcut):
    context = module.build_strategy_context(_race(is_sprint=is_sprint), [], None)

    assert context["pit_model"]["overcut_delta"] == overcut


@pytest.mark.unit
@pytest.mark.parametrize(
    ("laps", "primary", "offset", "late"),
    [(57, 24, 20, 34), (66, 28, 24, 38), (44, 18, 14, 28), (30, 16, 12, 22)],
    ids=["bahrain-length", "long-race", "short-race", "very-short-race"],
)
def test_context_places_the_fallback_stop_windows_inside_the_race_distance(laps, primary, offset, late):
    """The stop must sit clear of both the start and the last eight laps."""
    context = module.build_strategy_context(_race(circuit={"laps": laps}), [], None)

    windows = context["stint_windows"]
    assert (windows["primary_lap"], windows["offset_lap"], windows["late_lap"]) == (primary, offset, late)
    assert windows["total_laps"] == laps


@pytest.mark.unit
def test_context_assumes_a_58_lap_race_when_the_circuit_carries_no_lap_count():
    context = module.build_strategy_context({"circuit": {"circuit_type": "Street"}}, [], None)

    assert context["stint_windows"]["total_laps"] == 58


@pytest.mark.unit
def test_context_defaults_to_medium_hard_compounds_without_telemetry():
    context = module.build_strategy_context(_race(), [], None)

    assert [stint["compound"] for stint in context["stint_plan"]] == ["Medium", "Hard"]
    assert context["stint_windows"]["opening_compound"] == "Medium"
    assert context["stint_windows"]["finishing_compound"] == "Hard"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stops", "stop_word", "alt_word"),
    [
        (1, "one-stop", "two-stop"),
        (2, "two-stop", "one-stop"),
        (3, "three-stop", "one-stop"),
        (None, "one-stop", "two-stop"),
    ],
    ids=["one-stopper", "two-stopper", "three-stopper", "unknown"],
)
def test_context_pairs_each_measured_stop_count_with_the_opposite_branch(stops, stop_word, alt_word):
    """The desk always keeps the other strategy alive, whichever one is base."""
    context = module.build_strategy_context(_race(), [], None, {**_TELEMETRY, "most_common_stops": stops})

    assert stop_word in context["primary_call"]["summary"]
    assert f"keep a {alt_word} branch open" in context["primary_call"]["summary"]
    assert f"switch to a {alt_word}" in context["stint_plan"][1]["target"]


# ---------------------------------------------------------------------------
# build_strategy_context — prose driven by the numbers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_context_raises_confidence_when_a_predicted_winner_exists():
    podium = {"predictions": [{"driver": "VER"}, {"driver": "NOR"}, {"driver": "LEC"}, {"driver": "RUS"}]}

    with_prediction = module.build_strategy_context(_race(), [], podium)
    without = module.build_strategy_context(_race(), [], {"predictions": []})

    assert (with_prediction["primary_call"]["confidence"], without["primary_call"]["confidence"]) == ("medium", "low")
    assert module.build_strategy_context(_race(), [], podium, _TELEMETRY)["primary_call"]["confidence"] == "high"


@pytest.mark.unit
def test_context_decision_gates_quote_the_numbers_they_were_built_from():
    context = module.build_strategy_context(_race(), [], None, _TELEMETRY)

    gates = {gate["gate"]: gate for gate in context["decision_gates"]}
    assert gates["First stop call"]["trigger"] == "L18-L22"
    assert "~1.4s" in gates["First stop call"]["decision"]
    assert "rejoin traffic stays medium or lower" in gates["First stop call"]["decision"]
    assert gates["Safety-car branch"]["trigger"] == "L22-L37"
    assert "~19.4s pit loss" in gates["Safety-car branch"]["decision"]
    assert gates["Parc ferme lock"]["owner"] == "Performance"


@pytest.mark.unit
def test_context_stint_plan_spans_the_full_race_distance():
    context = module.build_strategy_context(_race(), [], None, _TELEMETRY)

    assert [stint["window"] for stint in context["stint_plan"]] == ["L1-L22", "L23-L57"]
    assert "Hold Soft surface temperatures" in context["stint_plan"][0]["target"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "phase"),
    [("in_progress", "Live race desk"), ("upcoming", "Pre-race build"), ("completed", "Pre-race build")],
    ids=["live", "upcoming", "completed"],
)
def test_context_phase_switches_to_the_race_desk_only_during_a_session(status, phase):
    assert module.build_strategy_context(_race(status=status), [], None)["phase"] == phase


@pytest.mark.unit
def test_context_phase_is_pre_race_without_any_event():
    context = module.build_strategy_context(None, [], None)

    assert context["phase"] == "Pre-race build"
    assert context["stint_windows"]["total_laps"] == 58
    assert context["pit_model"]["pit_loss_seconds"] == 21, "no event means no street-circuit uplift"


# ---------------------------------------------------------------------------
# build_strategy_context — competitors
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_context_grades_each_constructor_by_its_real_gap_to_the_leader():
    constructors = [
        {"team": "McLaren", "points": 500.0},
        {"team": "Ferrari", "points": 460.0},
        {"team": "Red Bull", "points": 440.0},
        {"team": "Mercedes", "points": 300.0},
    ]

    rows = module.build_strategy_context(_race(), constructors, None)["competitors"]

    assert [(row["rank"], row["gap_to_leader"], row["threat"]) for row in rows] == [
        (1, 0, "Primary"),
        (2, 40.0, "High"),
        (3, 60.0, "High"),
        (4, 200.0, "Monitor"),
    ]
    # The 60-point cutoff is the editorial threshold flagged in audit item 2.4.
    assert "Undercut exposure" in rows[2]["operating_read"]
    assert "Scenario dependent" in rows[3]["operating_read"]
    assert "Benchmark car" in rows[0]["operating_read"]


@pytest.mark.unit
def test_context_never_reports_a_negative_gap_for_a_mis_sorted_table():
    constructors = [{"team": "Ferrari", "points": 100.0}, {"team": "McLaren", "points": 180.0}]

    rows = module.build_strategy_context(_race(), constructors, None)["competitors"]

    assert [row["gap_to_leader"] for row in rows] == [0, 0]


@pytest.mark.unit
def test_context_lists_at_most_five_competitors():
    constructors = [{"team": f"Team {rank}", "points": 100.0 - rank} for rank in range(8)]

    assert len(module.build_strategy_context(_race(), constructors, None)["competitors"]) == 5


@pytest.mark.unit
def test_context_returns_no_competitor_rows_without_a_standings_feed():
    context = module.build_strategy_context(_race(), [], None)

    assert context["competitors"] == []
    assert context["assumptions"][0].startswith("Race context is derived from the season schedule")


# ---------------------------------------------------------------------------
# known defect
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_context_crashes_on_an_event_whose_circuit_is_unmapped():
    """Pins a live bug: ``build_strategy_dashboard`` sets ``circuit`` to None for
    any venue missing from ``CIRCUIT_DATA`` (``get_circuit_info`` returns None),
    and the lap-count read dereferences it without a guard — so the whole
    command center 500s on an unmapped calendar entry. Not fixed here; the
    following line documents the failure mode."""
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'get'"):
        module.build_strategy_context({"circuit": None, "status": "upcoming"}, [], None)
