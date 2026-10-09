"""Tests for app.services.race_control_battles — the driver priority call.

This screen answers a strategy question ("which of our two drivers gets first
call?") purely from championship standings, so the risks are about *claiming
more than the data supports*:

* **Inventing a priority when the standings are too close.** The close-call
  guard must produce a null priority code, not a coin-flip winner.
* **Pairing a value against the wrong driver.** Every comparison row is keyed
  by driver code; a swapped pair is a silent, plausible-looking lie.
* **Dividing by an incomplete season.** Points-per-race is only meaningful once
  races have run — the fact must disappear rather than divide by zero.
"""

from __future__ import annotations

import pytest

from app.services import race_control_battles as module

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _driver(
    code: str,
    *,
    name: str | None = None,
    team: str = "Red Bull",
    position: int = 1,
    points: float = 100.0,
    wins: int = 5,
) -> dict:
    return {
        "code": code,
        "name": name or f"{code} Driver",
        "team": team,
        "position": position,
        "points": points,
        "wins": wins,
        "driver_id": code.lower(),
    }


def _stub_feed(
    monkeypatch: pytest.MonkeyPatch,
    drivers: list[dict],
    *,
    completed_races: int | None = 10,
    source: str = "f1db-driver-standings",
    error: str | None = None,
) -> None:
    """Serve a fixed standings feed and season progress to the battle builder.

    Both helpers are imported into the module namespace, so they are patched
    there rather than on ``race_control_common``.
    """
    monkeypatch.setattr(
        module,
        "get_driver_options",
        lambda year: {
            "year": year,
            "source": source,
            "drivers": drivers,
            "error": error,
        },
    )
    monkeypatch.setattr(module, "completed_race_count", lambda year: completed_races)


def _fact(result: dict, key: str) -> dict:
    return next(fact for fact in result["facts"] if fact["key"] == key)


# ---------------------------------------------------------------------------
# battle_fact
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_battle_fact_keys_each_value_by_its_own_driver_code():
    first, second = _driver("VER"), _driver("NOR")

    fact = module.battle_fact("points", "Championship points", (first, second), ("100", "80"))

    assert fact == {
        "key": "points",
        "label": "Championship points",
        "values": {"VER": "100", "NOR": "80"},
    }


@pytest.mark.unit
def test_battle_fact_with_identical_codes_collapses_to_one_entry():
    """Guards the assumption the caller enforces: two distinct drivers."""
    same = _driver("VER")

    fact = module.battle_fact("points", "Points", (same, same), ("100", "80"))

    assert fact["values"] == {"VER": "80"}


# ---------------------------------------------------------------------------
# failure branches — no synthetic data may be emitted
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_standings_report_data_unavailable_without_metrics(monkeypatch: pytest.MonkeyPatch):
    _stub_feed(monkeypatch, [], error="No driver standings found for this season yet.")

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert result["status"] == "data_unavailable"
    assert result["drivers"] == []
    assert result["metrics"] == []
    assert result["error"] == "No driver standings found for this season yet."
    assert "facts" not in result


@pytest.mark.unit
def test_unknown_first_driver_names_the_missing_query_and_keeps_the_found_one(
    monkeypatch: pytest.MonkeyPatch,
):
    standings = [_driver("NOR", name="Lando Norris")]
    _stub_feed(monkeypatch, standings)

    result = module.build_driver_battle(2024, "ZZZ", "NOR")

    assert result["status"] == "driver_not_found"
    assert result["error"] == "Driver 'ZZZ' not found."
    assert [driver["code"] for driver in result["drivers"]] == ["NOR"]
    assert result["available_drivers"] == standings


@pytest.mark.unit
def test_unknown_second_driver_names_the_second_query(monkeypatch: pytest.MonkeyPatch):
    _stub_feed(monkeypatch, [_driver("VER", name="Max Verstappen")])

    result = module.build_driver_battle(2024, "VER", "ZZZ")

    assert result["status"] == "driver_not_found"
    assert result["error"] == "Driver 'ZZZ' not found."
    assert [driver["code"] for driver in result["drivers"]] == ["VER"]


@pytest.mark.unit
def test_same_driver_selected_twice_is_rejected_before_any_maths(
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_feed(monkeypatch, [_driver("VER", name="Max Verstappen")])

    result = module.build_driver_battle(2024, "VER", "Max Verstappen")

    assert result["status"] == "invalid_selection"
    assert result["error"] == "Both selected drivers are the same."
    assert [driver["code"] for driver in result["drivers"]] == ["VER"]
    assert result["metrics"] == []


# ---------------------------------------------------------------------------
# comparison facts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_facts_cover_every_metric_and_pair_values_to_the_right_driver(
    monkeypatch: pytest.MonkeyPatch,
):
    ver = _driver("VER", team="Red Bull", position=1, points=310.0, wins=9)
    per = _driver("PER", team="Red Bull", position=4, points=190.0, wins=1)
    _stub_feed(monkeypatch, [ver, per], completed_races=10)

    result = module.build_driver_battle(2024, "VER", "PER")

    assert [fact["key"] for fact in result["facts"]] == [
        "wdc_position",
        "points",
        "wins",
        "team_share",
        "points_per_race",
    ]
    assert _fact(result, "wdc_position")["values"] == {"VER": "P1", "PER": "P4"}
    assert _fact(result, "points")["values"] == {"VER": "310", "PER": "190"}
    assert _fact(result, "wins")["values"] == {"VER": "9 wins", "PER": "1 win"}
    # 310 and 190 of a 500-point team total.
    assert _fact(result, "team_share")["values"] == {"VER": "62.0%", "PER": "38.0%"}
    assert _fact(result, "points_per_race")["values"] == {"VER": "31.0", "PER": "19.0"}


@pytest.mark.unit
@pytest.mark.parametrize("completed_races", [None, 0])
def test_points_per_race_is_omitted_when_no_race_has_completed(
    monkeypatch: pytest.MonkeyPatch, completed_races: int | None
):
    _stub_feed(
        monkeypatch,
        [_driver("VER", points=0.0, wins=0), _driver("NOR", position=2, team="McLaren", points=0.0, wins=0)],
        completed_races=completed_races,
    )

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert "points_per_race" not in [fact["key"] for fact in result["facts"]]
    assert not any("Scoring rate uses" in factor for factor in result["decision_factors"])


@pytest.mark.unit
def test_team_share_is_zero_when_the_team_has_scored_nothing(monkeypatch: pytest.MonkeyPatch):
    """A pointless team must read 0.0%, never raise on the division."""
    _stub_feed(
        monkeypatch,
        [
            _driver("BOT", team="Sauber", position=19, points=0.0, wins=0),
            _driver("ZHO", team="Sauber", position=20, points=0.0, wins=0),
        ],
    )

    result = module.build_driver_battle(2024, "BOT", "ZHO")

    assert _fact(result, "team_share")["values"] == {"BOT": "0.0%", "ZHO": "0.0%"}


# ---------------------------------------------------------------------------
# priority call
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_close_standings_refuse_to_name_a_priority_driver(monkeypatch: pytest.MonkeyPatch):
    ver = _driver("VER", name="Max Verstappen", position=1, points=205.0, wins=6)
    nor = _driver("NOR", name="Lando Norris", team="McLaren", position=2, points=200.0, wins=5)
    _stub_feed(monkeypatch, [ver, nor])

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert result["status"] == "ok"
    assert result["priority"] == {
        "code": None,
        "driver": "No automatic priority",
        "team": None,
        "confidence": "Low",
        "basis": "current championship standings",
    }
    assert "should not decide priority" in result["summary"]
    assert result["recommendation"].startswith("Do not assign priority from standings alone.")


@pytest.mark.unit
def test_a_wide_points_gap_gives_a_high_confidence_priority(monkeypatch: pytest.MonkeyPatch):
    ver = _driver("VER", name="Max Verstappen", position=1, points=310.0, wins=9)
    nor = _driver("NOR", name="Lando Norris", team="McLaren", position=2, points=240.0, wins=4)
    _stub_feed(monkeypatch, [ver, nor])

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert result["priority"]["code"] == "VER"
    assert result["priority"]["driver"] == "Max Verstappen"
    assert result["priority"]["team"] == "Red Bull"
    assert result["priority"]["confidence"] == "High"
    assert result["summary"].startswith("Max Verstappen has the stronger standings case: P1 with 310 points")


@pytest.mark.unit
def test_a_wide_position_gap_alone_is_enough_for_high_confidence(monkeypatch: pytest.MonkeyPatch):
    leader = _driver("VER", position=1, points=40.0, wins=2)
    chaser = _driver("HUL", team="Haas", position=12, points=8.0, wins=0)
    _stub_feed(monkeypatch, [leader, chaser])

    result = module.build_driver_battle(2024, "VER", "HUL")

    assert result["priority"]["confidence"] == "High"


@pytest.mark.unit
def test_a_moderate_gap_is_medium_confidence(monkeypatch: pytest.MonkeyPatch):
    leader = _driver("VER", position=1, points=100.0, wins=4)
    chaser = _driver("NOR", team="McLaren", position=3, points=80.0, wins=2)
    _stub_feed(monkeypatch, [leader, chaser])

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert result["priority"]["confidence"] == "Medium"


@pytest.mark.unit
def test_priority_follows_the_standings_regardless_of_argument_order(
    monkeypatch: pytest.MonkeyPatch,
):
    """Asking "NOR vs VER" must not promote NOR just for being named first."""
    ver = _driver("VER", name="Max Verstappen", position=1, points=310.0, wins=9)
    nor = _driver("NOR", name="Lando Norris", team="McLaren", position=2, points=240.0, wins=4)
    _stub_feed(monkeypatch, [ver, nor])

    result = module.build_driver_battle(2024, "NOR", "VER")

    assert [driver["code"] for driver in result["drivers"]] == ["NOR", "VER"]
    assert result["priority"]["code"] == "VER"


@pytest.mark.unit
def test_tied_drivers_break_toward_the_first_named(monkeypatch: pytest.MonkeyPatch):
    """A dead heat on points, wins and position is resolved by the `>=` tie-break.

    The pair is not "close" (the gaps are zero but the wins gap rule needs the
    points gap under 10 — which it is), so this also pins the close-call path.
    """
    first = _driver("VER", name="Max Verstappen", position=1, points=100.0, wins=4)
    second = _driver("NOR", name="Lando Norris", team="McLaren", position=1, points=100.0, wins=4)
    _stub_feed(monkeypatch, [first, second])

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert result["priority"]["code"] is None
    assert result["priority"]["confidence"] == "Low"


# ---------------------------------------------------------------------------
# decision factors and recommendations
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_same_team_comparison_recommends_a_pit_window_split(monkeypatch: pytest.MonkeyPatch):
    ver = _driver("VER", name="Max Verstappen", position=1, points=310.0, wins=9)
    per = _driver("PER", name="Sergio Perez", position=6, points=150.0, wins=0)
    _stub_feed(monkeypatch, [ver, per], completed_races=12)

    result = module.build_driver_battle(2024, "VER", "PER")

    assert result["comparison"]["context"] == "same-team"
    assert "Same team comparison" in result["decision_factors"][3]
    assert "Give Max Verstappen first call" in result["recommendation"]
    assert "Sergio Perez" in result["recommendation"]


@pytest.mark.unit
def test_rival_comparison_recommends_covering_undercut_windows(monkeypatch: pytest.MonkeyPatch):
    ver = _driver("VER", name="Max Verstappen", position=1, points=310.0, wins=9)
    nor = _driver("NOR", name="Lando Norris", team="McLaren", position=2, points=240.0, wins=4)
    _stub_feed(monkeypatch, [ver, nor])

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert result["comparison"]["context"] == "rival-comparison"
    assert "Rival comparison" in result["decision_factors"][3]
    assert "Treat Max Verstappen as the higher-priority rival" in result["recommendation"]
    assert "Red Bull is inside pit-loss range" in result["recommendation"]


@pytest.mark.unit
def test_decision_factors_use_singular_wording_for_gaps_of_one(
    monkeypatch: pytest.MonkeyPatch,
):
    leader = _driver("VER", position=1, points=101.0, wins=5)
    chaser = _driver("NOR", team="McLaren", position=2, points=100.0, wins=4)
    _stub_feed(monkeypatch, [leader, chaser], completed_races=1)

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert result["decision_factors"][:3] == [
        "Points gap: 1 point.",
        "Championship order gap: 1 position.",
        "Wins gap: 1 race win.",
    ]
    assert result["decision_factors"][-1] == "Scoring rate uses 1 completed Grand Prix event."


@pytest.mark.unit
def test_decision_factors_use_plural_wording_for_wider_gaps(monkeypatch: pytest.MonkeyPatch):
    leader = _driver("VER", position=1, points=310.0, wins=9)
    chaser = _driver("NOR", team="McLaren", position=4, points=240.0, wins=4)
    _stub_feed(monkeypatch, [leader, chaser], completed_races=12)

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert result["decision_factors"][:3] == [
        "Points gap: 70 points.",
        "Championship order gap: 3 positions.",
        "Wins gap: 5 race wins.",
    ]
    assert result["decision_factors"][-1] == "Scoring rate uses 12 completed Grand Prix events."


# ---------------------------------------------------------------------------
# envelope
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_successful_battle_carries_the_source_and_disclaims_telemetry(
    monkeypatch: pytest.MonkeyPatch,
):
    ver = _driver("VER", position=1, points=310.0, wins=9)
    nor = _driver("NOR", team="McLaren", position=2, points=240.5, wins=4)
    _stub_feed(monkeypatch, [ver, nor], source="ergast-driver-standings")

    result = module.build_driver_battle(2024, "VER", "NOR")

    assert result["year"] == 2024
    assert result["source"] == "ergast-driver-standings"
    assert result["error"] is None
    assert result["metrics"] == []
    assert result["comparison"] == {
        "points_gap": 69.5,
        "position_gap": 1,
        "wins_gap": 5,
        "context": "rival-comparison",
    }
    assert result["data_limitations"] == [
        "Uses real championship standings only.",
        "Does not claim live race pace, sector strength, tyre degradation, or telemetry until session data is connected.",
    ]
