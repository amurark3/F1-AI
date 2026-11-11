"""Tests for app.services.race_control.strategy_context — the command-center
shell and the strategy numbers printed inside it.

The baseline plan itself is built and tested in ``baseline_plan``
(``test_race_control_baseline_plan.py``); the context only places it beside the
session phase and the rival rows.

The dashboard half carries a different risk: session status ("in_progress")
drives the workstream board and the risk register, and it is derived purely
from clock arithmetic over the FastF1 schedule. "Live" is narrower — a weekend
is in progress from Friday to Sunday, but only a session on track makes the
desk live.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.services.race_control import live, stakes, strategy_context as module
from tests.standings_support import standings_from_rows

_NOW_UTC = datetime.now(UTC)
_NOW = _NOW_UTC.replace(tzinfo=None)


class _Clock(datetime):
    """``datetime`` whose ``now`` is ``_NOW``, the instant every row here is built around."""

    @classmethod
    def now(cls, tz=None):
        return _NOW_UTC.astimezone(tz) if tz else _NOW_UTC


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    """Freeze every clock the code under test reads at ``_NOW``.

    The rows are built from ``_NOW`` when this file is imported, at collection;
    the modules read the clock when each test runs. A full suite can put more
    than a minute between the two, which turned a session 30 s ahead into one
    that had already started.
    """
    for clock_reader in (module, live, stakes):
        monkeypatch.setattr(clock_reader, "datetime", _Clock)


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
    """Serve a fixed computed table for the championship block and the stakes."""
    standings = standings_from_rows(feeds.get("drivers", []), feeds.get("constructors", []))
    monkeypatch.setattr(module, "current_standings", lambda _year: standings)


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
                Session1DateUtc=pd.Timestamp(_NOW - timedelta(days=2)),
                Session5DateUtc=pd.Timestamp(_NOW - timedelta(minutes=30)),
            ),
            _upcoming_row(RoundNumber=3),
        ],
    )
    _stub_standings(monkeypatch)

    dashboard = module.build_strategy_dashboard(2026)

    assert dashboard["race"]["round"] == 2
    assert dashboard["race"]["status"] == "in_progress"
    assert dashboard["focus"] == "Live session control", "the race is on track"
    # A live event has no countdown — the clock is already past lights out.
    assert dashboard["race"]["days_until"] is None


@pytest.mark.unit
def test_an_in_progress_weekend_between_sessions_is_not_live_control(monkeypatch):
    """Saturday night: the weekend is under way, but nothing is on track."""
    _stub_schedule(
        monkeypatch,
        [
            _row(
                RoundNumber=2,
                Session1DateUtc=pd.Timestamp(_NOW - timedelta(hours=6)),
                Session5DateUtc=pd.Timestamp(_NOW + timedelta(hours=12)),
            ),
        ],
    )
    _stub_standings(monkeypatch)

    dashboard = module.build_strategy_dashboard(2026)

    assert dashboard["race"]["status"] == "in_progress"
    assert dashboard["focus"] != "Live session control"


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
    # The countdown now runs to the race itself (11 days), the only session left
    # dated, not to the nameless practice slot 9 days out.
    assert event["days_until"] == 11


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
        drivers=[
            {"position": rank, "code": f"D{rank}", "driver": f"Driver {rank}", "team": "Team 1", "points": 50 - rank}
            for rank in range(1, 8)
        ],
        constructors=[_team(rank, 100 - rank) for rank in range(1, 8)],
    )

    dashboard = module.build_strategy_dashboard(2026)

    assert [row["position"] for row in dashboard["championship"]["drivers"]] == [1, 2, 3, 4, 5]
    assert len(dashboard["championship"]["constructors"]) == 5
    assert dashboard["year"] == 2026
    assert dashboard["generated_at"].endswith("+00:00")
    # Stakes read the whole table, not the five rows the panel shows.
    assert len(dashboard["stakes"]["drivers"]["contenders"]) == 6
    assert len(dashboard["stakes"]["constructors"]["contenders"]) == 6


# ---------------------------------------------------------------------------
# build_strategy_context — the baseline plan beside the rivals
# ---------------------------------------------------------------------------

_BASELINE = {"primary_call": {"title": "Base race plan"}, "data_source": {"mode": "edition"}, "plan": None}


def _race(**fields) -> dict:
    base = {"status": "upcoming", "is_sprint": False, "circuit": {"laps": 57, "circuit_type": "Purpose-built"}}
    return {**base, **fields}


@pytest.mark.unit
def test_context_carries_the_baseline_plan_as_given():
    context = module.build_strategy_context(_race(), [], _BASELINE)

    assert context["primary_call"] == {"title": "Base race plan"}
    assert context["data_source"] == {"mode": "edition"}
    assert context["plan"] is None
    assert set(context) == {"phase", "primary_call", "data_source", "plan", "competitors"}


def _sessions_starting(offset: timedelta) -> dict[str, str]:
    """A race session that started ``offset`` ago (negative: still to come)."""
    start = _NOW_UTC - offset
    return {"Race": start.isoformat()}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "sessions", "phase"),
    [
        ("in_progress", _sessions_starting(timedelta(minutes=30)), "Live race desk"),
        ("in_progress", _sessions_starting(timedelta(hours=-12)), "Pre-race build"),
        ("upcoming", _sessions_starting(timedelta(days=-3)), "Pre-race build"),
        ("completed", _sessions_starting(timedelta(days=3)), "Pre-race build"),
    ],
    ids=["live", "between-sessions", "upcoming", "completed"],
)
def test_context_phase_switches_to_the_race_desk_only_during_a_session(status, sessions, phase):
    race = _race(status=status, sessions=sessions)

    assert module.build_strategy_context(race, [], _BASELINE)["phase"] == phase


@pytest.mark.unit
def test_context_phase_is_pre_race_without_any_event():
    assert module.build_strategy_context(None, [], _BASELINE)["phase"] == "Pre-race build"


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

    rows = module.build_strategy_context(_race(), constructors, _BASELINE)["competitors"]

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

    rows = module.build_strategy_context(_race(), constructors, _BASELINE)["competitors"]

    assert [row["gap_to_leader"] for row in rows] == [0, 0]


@pytest.mark.unit
def test_context_lists_at_most_five_competitors():
    constructors = [{"team": f"Team {rank}", "points": 100.0 - rank} for rank in range(8)]

    assert len(module.build_strategy_context(_race(), constructors, _BASELINE)["competitors"]) == 5


@pytest.mark.unit
def test_context_returns_no_competitor_rows_without_a_standings_feed():
    assert module.build_strategy_context(_race(), [], _BASELINE)["competitors"] == []


@pytest.mark.unit
def test_context_reads_an_unmapped_venue_without_failing():
    """Was a pinned bug: ``build_strategy_dashboard`` sets ``circuit`` to None
    for any venue missing from ``CIRCUIT_DATA``, and the context dereferenced
    it. The context now reads nothing from the circuit at all."""
    context = module.build_strategy_context({"circuit": None, "status": "upcoming"}, [], _BASELINE)

    assert context["phase"] == "Pre-race build"
