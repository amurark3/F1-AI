"""Tests for app.services.race_control_championship — the title projection.

The forecast extrapolates the rest of the season from two rates: points per
event across the whole year, and points per event across the last five loadable
races. Three things must hold or the projection lies confidently.

* **Recent form must only count races that actually loaded.** The recent window
  is the divisor; counting a race whose classification failed would deflate
  every recent rate toward zero and paint the field as "Sliding".
* **Empty or early seasons must not divide by zero.** Round zero of a new
  season still has to render.
* **Keys must match how each feed spells them.** Driver rows are matched on an
  upper-cased code against FastF1 abbreviations; constructor rows are matched
  on the team name verbatim. A mismatch silently scores a rate of zero.
"""

from __future__ import annotations

import pytest

from app.services import race_control_championship as module
from app.services.race_control_championship import EntrantAccessors, SeasonProgress

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_DRIVER_ACCESSORS = EntrantAccessors(
    key=lambda row: row["code"],
    name=lambda row: row["driver"],
    team=lambda row: row["team"],
    type_label="driver",
)

_CONSTRUCTOR_ACCESSORS = EntrantAccessors(
    key=lambda row: row["team"],
    name=lambda row: row["team"],
    team=lambda row: row["team"],
    type_label="constructor",
)


def _driver_row(code: str, *, position: int, points: float, team: str = "Red Bull", wins: int = 0) -> dict:
    return {
        "position": position,
        "code": code,
        "driver": f"{code} Driver",
        "team": team,
        "points": points,
        "wins": wins,
    }


def _constructor_row(team: str, *, position: int, points: float, wins: int = 0) -> dict:
    return {"position": position, "team": team, "points": points, "wins": wins}


def _result(driver: str, team: str, points: float) -> dict:
    return {"driver": driver, "team": team, "points": points}


def _stub_season(
    monkeypatch: pytest.MonkeyPatch,
    *,
    drivers: list[dict] | None = None,
    constructors: list[dict] | None = None,
    completed_rounds: list[int] | None = None,
    total_events: int = 24,
    classifications: dict[int, object] | None = None,
) -> None:
    """Serve fixed standings, a fixed calendar position, and per-round results.

    ``classifications`` maps a round number to either the detail dict
    ``load_race_classification`` would return or an exception to raise.
    """
    monkeypatch.setattr(
        module,
        "get_standings_snapshot",
        lambda year: (list(drivers or []), list(constructors or [])),
    )
    monkeypatch.setattr(
        module,
        "completed_race_rounds",
        lambda year: (list(completed_rounds or []), total_events),
    )

    def _load(year: int, round_num: int) -> dict:
        detail = (classifications or {}).get(round_num, {})
        if isinstance(detail, BaseException):
            raise detail
        return detail

    monkeypatch.setattr(module, "load_race_classification", _load)


def _by_key(rows: list[dict]) -> dict[str, dict]:
    return {row["key"]: row for row in rows}


# ---------------------------------------------------------------------------
# trend labelling
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (5.0, "Gaining"),
        (1.51, "Gaining"),
        (1.5, "Holding"),
        (0.0, "Holding"),
        (-1.5, "Holding"),
        (-1.51, "Sliding"),
        (-9.0, "Sliding"),
    ],
)
def test_trend_label_only_moves_outside_the_dead_band(delta: float, expected: str):
    assert module._trend_label(delta) == expected


# ---------------------------------------------------------------------------
# forecast_rows
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_projection_blends_recent_form_over_the_remaining_events():
    progress = SeasonProgress(completed=10, loaded_recent=5, remaining=10)
    entries = [_driver_row("VER", position=1, points=200.0)]

    rows = module.forecast_rows(
        entries=entries,
        recent_points={"VER": 125.0},
        progress=progress,
        accessors=_DRIVER_ACCESSORS,
    )

    row = rows[0]
    # Season rate 20.0/event, recent rate 25.0/event, blended 0.62/0.38 => 23.1.
    assert row["season_points_per_event"] == 20.0
    assert row["recent_points_per_event"] == 25.0
    assert row["projected_points"] == pytest.approx(431.0)
    assert row["trend"] == "Gaining"
    assert row["confidence"] == "Medium"


@pytest.mark.unit
def test_recent_rate_falls_back_to_the_season_rate_when_no_race_loaded():
    """With no loaded window there is no independent signal — never a zero rate."""
    progress = SeasonProgress(completed=8, loaded_recent=0, remaining=12)
    entries = [_driver_row("VER", position=1, points=160.0)]

    rows = module.forecast_rows(
        entries=entries,
        recent_points={},
        progress=progress,
        accessors=_DRIVER_ACCESSORS,
    )

    row = rows[0]
    assert row["recent_points_per_event"] == row["season_points_per_event"] == 20.0
    assert row["projected_points"] == 400.0
    assert row["trend"] == "Holding"
    assert row["confidence"] == "Low"


@pytest.mark.unit
def test_a_season_with_no_completed_event_does_not_divide_by_zero():
    progress = SeasonProgress(completed=0, loaded_recent=0, remaining=24)
    entries = [_driver_row("VER", position=1, points=0.0)]

    rows = module.forecast_rows(
        entries=entries,
        recent_points={},
        progress=progress,
        accessors=_DRIVER_ACCESSORS,
    )

    assert rows[0]["season_points_per_event"] == 0.0
    assert rows[0]["projected_points"] == 0.0


@pytest.mark.unit
def test_confidence_reaches_medium_only_from_three_loaded_races():
    entries = [_driver_row("VER", position=1, points=100.0)]

    def _confidence(loaded: int) -> str:
        progress = SeasonProgress(completed=10, loaded_recent=loaded, remaining=5)
        rows = module.forecast_rows(
            entries=entries,
            recent_points={"VER": 60.0},
            progress=progress,
            accessors=_DRIVER_ACCESSORS,
        )
        return rows[0]["confidence"]

    assert [_confidence(loaded) for loaded in (1, 2, 3, 4)] == ["Low", "Low", "Medium", "Medium"]


@pytest.mark.unit
def test_driver_keys_are_upper_cased_to_match_the_classification_feed():
    progress = SeasonProgress(completed=4, loaded_recent=4, remaining=4)

    rows = module.forecast_rows(
        entries=[_driver_row("ver", position=1, points=40.0)],
        recent_points={"VER": 40.0},
        progress=progress,
        accessors=_DRIVER_ACCESSORS,
    )

    assert rows[0]["key"] == "VER"
    assert rows[0]["code"] == "ver"
    assert rows[0]["recent_points_per_event"] == 10.0


@pytest.mark.unit
def test_constructor_keys_keep_their_original_casing():
    progress = SeasonProgress(completed=4, loaded_recent=4, remaining=4)

    rows = module.forecast_rows(
        entries=[_constructor_row("McLaren", position=1, points=80.0)],
        recent_points={"McLaren": 80.0},
        progress=progress,
        accessors=_CONSTRUCTOR_ACCESSORS,
    )

    assert rows[0]["key"] == "McLaren"
    assert rows[0]["code"] is None
    assert rows[0]["name"] == rows[0]["team"] == "McLaren"
    assert rows[0]["recent_points_per_event"] == 20.0


@pytest.mark.unit
def test_rows_are_ranked_by_projection_and_carry_the_move_against_today():
    progress = SeasonProgress(completed=10, loaded_recent=5, remaining=10)
    entries = [
        _driver_row("VER", position=1, points=200.0),
        _driver_row("NOR", position=2, points=180.0, team="McLaren"),
    ]

    rows = module.forecast_rows(
        entries=entries,
        recent_points={"VER": 50.0, "NOR": 125.0},
        progress=progress,
        accessors=_DRIVER_ACCESSORS,
    )

    assert [row["key"] for row in rows] == ["NOR", "VER"]
    assert [row["projected_position"] for row in rows] == [1, 2]
    # NOR climbs one place; VER drops one.
    assert _by_key(rows)["NOR"]["position_delta"] == 1
    assert _by_key(rows)["VER"]["position_delta"] == -1
    assert _by_key(rows)["VER"]["trend"] == "Sliding"


@pytest.mark.unit
def test_an_identical_projection_is_broken_by_the_current_standings_order():
    progress = SeasonProgress(completed=5, loaded_recent=0, remaining=5)
    # Listed chaser-first, so input order cannot be what produces the ranking.
    entries = [
        _driver_row("NOR", position=2, points=100.0, team="McLaren"),
        _driver_row("VER", position=1, points=100.0),
    ]

    rows = module.forecast_rows(
        entries=entries,
        recent_points={},
        progress=progress,
        accessors=_DRIVER_ACCESSORS,
    )

    assert [row["key"] for row in rows] == ["VER", "NOR"]
    assert [row["position_delta"] for row in rows] == [0, 0]


@pytest.mark.unit
def test_missing_points_and_position_coerce_instead_of_raising():
    progress = SeasonProgress(completed=2, loaded_recent=0, remaining=2)

    rows = module.forecast_rows(
        entries=[{"code": "TBD", "driver": "Reserve", "team": "Haas", "position": None}],
        recent_points={},
        progress=progress,
        accessors=_DRIVER_ACCESSORS,
    )

    assert rows[0]["current_points"] == 0.0
    assert rows[0]["current_position"] == 0
    assert rows[0]["wins"] == 0
    assert rows[0]["projected_position"] == 1


@pytest.mark.unit
def test_no_entries_produce_no_rows():
    progress = SeasonProgress(completed=5, loaded_recent=5, remaining=5)

    assert module.forecast_rows([], {}, progress, _DRIVER_ACCESSORS) == []


# ---------------------------------------------------------------------------
# build_championship_forecast
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_forecast_sums_recent_points_for_both_drivers_and_constructors(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_season(
        monkeypatch,
        drivers=[
            _driver_row("VER", position=1, points=50.0, wins=2),
            _driver_row("NOR", position=2, points=40.0, team="McLaren", wins=1),
        ],
        constructors=[
            _constructor_row("Red Bull", position=1, points=50.0, wins=2),
            _constructor_row("McLaren", position=2, points=40.0, wins=1),
        ],
        completed_rounds=[1, 2],
        total_events=4,
        classifications={
            1: {"race_results": [_result("VER", "Red Bull", 25), _result("NOR", "McLaren", 18)]},
            2: {"race_results": [_result("VER", "Red Bull", 25), _result("NOR", "McLaren", 22)]},
        },
    )

    result = module.build_championship_forecast(2024)

    assert result["completed_events"] == 2
    assert result["remaining_events"] == 2
    assert result["recent_window"] == 2
    assert result["error"] is None
    drivers = _by_key(result["drivers"])
    assert drivers["VER"]["recent_points_per_event"] == 25.0
    assert drivers["NOR"]["recent_points_per_event"] == 20.0
    constructors = _by_key(result["constructors"])
    assert constructors["Red Bull"]["recent_points_per_event"] == 25.0
    assert constructors["McLaren"]["recent_points_per_event"] == 20.0


@pytest.mark.unit
def test_recent_form_reads_only_the_last_five_completed_rounds(monkeypatch: pytest.MonkeyPatch):
    requested: list[int] = []

    _stub_season(
        monkeypatch,
        drivers=[_driver_row("VER", position=1, points=100.0)],
        completed_rounds=list(range(1, 9)),
        total_events=10,
        classifications={round_num: {"race_results": [_result("VER", "Red Bull", 10)]} for round_num in range(1, 9)},
    )
    original = module.load_race_classification

    def _tracked(year: int, round_num: int) -> dict:
        requested.append(round_num)
        return original(year, round_num)

    monkeypatch.setattr(module, "load_race_classification", _tracked)

    result = module.build_championship_forecast(2024)

    assert requested == [4, 5, 6, 7, 8]
    assert result["recent_window"] == 5


@pytest.mark.unit
def test_a_round_that_fails_to_load_is_skipped_without_shrinking_the_window(
    monkeypatch: pytest.MonkeyPatch,
):
    """A raised load must not count as a zero-points race for anyone."""
    _stub_season(
        monkeypatch,
        drivers=[_driver_row("VER", position=1, points=50.0)],
        completed_rounds=[1, 2],
        total_events=3,
        classifications={
            1: {"race_results": [_result("VER", "Red Bull", 25)]},
            2: RuntimeError("FastF1 cache miss"),
        },
    )

    result = module.build_championship_forecast(2024)

    assert result["recent_window"] == 1
    assert _by_key(result["drivers"])["VER"]["recent_points_per_event"] == 25.0


@pytest.mark.unit
@pytest.mark.parametrize("detail", [{}, {"race_results": []}, {"race_results": None}])
def test_a_round_with_no_classification_rows_is_not_counted(monkeypatch: pytest.MonkeyPatch, detail: dict):
    _stub_season(
        monkeypatch,
        drivers=[_driver_row("VER", position=1, points=25.0)],
        completed_rounds=[1, 2],
        total_events=3,
        classifications={
            1: {"race_results": [_result("VER", "Red Bull", 25)]},
            2: detail,
        },
    )

    result = module.build_championship_forecast(2024)

    assert result["recent_window"] == 1
    assert _by_key(result["drivers"])["VER"]["recent_points_per_event"] == 25.0


@pytest.mark.unit
def test_classification_rows_without_a_team_bucket_into_unknown(monkeypatch: pytest.MonkeyPatch):
    _stub_season(
        monkeypatch,
        constructors=[_constructor_row("Unknown", position=1, points=12.0)],
        completed_rounds=[1],
        total_events=2,
        classifications={1: {"race_results": [{"driver": "VER", "points": 12}]}},
    )

    result = module.build_championship_forecast(2024)

    assert _by_key(result["constructors"])["Unknown"]["recent_points_per_event"] == 12.0


@pytest.mark.unit
def test_remaining_events_never_go_negative(monkeypatch: pytest.MonkeyPatch):
    """A calendar shorter than the completed count must clamp, not project backwards."""
    _stub_season(
        monkeypatch,
        drivers=[_driver_row("VER", position=1, points=100.0)],
        completed_rounds=[1, 2, 3],
        total_events=2,
        classifications={},
    )

    result = module.build_championship_forecast(2024)

    assert result["remaining_events"] == 0
    assert _by_key(result["drivers"])["VER"]["projected_points"] == 100.0


@pytest.mark.unit
def test_an_empty_standings_snapshot_reports_the_error_and_no_rows(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_season(monkeypatch, completed_rounds=[], total_events=24)

    result = module.build_championship_forecast(2024)

    assert result["drivers"] == []
    assert result["constructors"] == []
    assert result["error"] == "Championship standings are unavailable for this season."


@pytest.mark.unit
def test_forecast_envelope_names_its_sources_and_states_its_limits(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_season(
        monkeypatch,
        drivers=[_driver_row("VER", position=1, points=100.0)],
        completed_rounds=[1],
        total_events=2,
        classifications={1: {"race_results": [_result("VER", "Red Bull", 25)]}},
    )

    result = module.build_championship_forecast(2024)

    assert result["year"] == 2024
    assert result["generated_at"].endswith("+00:00")
    assert result["source"] == "jolpica-ergast-standings + FastF1 recent race classifications"
    assert len(result["notes"]) == 3
    assert any("sprint" in note for note in result["notes"])
