"""Tests for app.services.anomaly — proactive race storyline detection.

The assistant volunteers these findings unprompted ("Norris lost 12 places"),
so a false positive is a confidently wrong statement about a real race. The
risks covered here are therefore: the thresholds that decide what counts as
notable, the unclassified-entry rows (``position_number`` is NULL for a DNF)
that must never be arithmetic'd into a fake result, and the degradation path —
a database failure must read as "no anomalies available", never as "a clean,
orderly race".
"""

from __future__ import annotations

import pytest

from app.services import anomaly


def _row(driver="Norris", team="mclaren", **fields):
    """A single ``RACE_RESULT`` row shaped like the f1db query output.

    Overrides arrive as keywords (``finish``, ``grid``, ``retired``,
    ``driver_id``) so the helper stays within the argument budget and reads as
    "a default row, except ..." at each call site.
    """
    finish = fields.get("finish")
    grid = fields.get("grid")
    return {
        "driver_id": fields.get("driver_id") or driver.lower(),
        "driver": driver,
        "team": team,
        "finish": finish,
        "finish_text": str(finish) if finish is not None else "DNF",
        "grid": grid,
        "gained": None if grid is None or finish is None else grid - finish,
        "retired": fields.get("retired"),
    }


# ---------------------------------------------------------------------------
# _big_movers
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("grid", "finish", "kind", "magnitude"),
    [
        (15, 3, "big_gain", 12),
        (20, 15, "big_gain", 5),  # exactly at the threshold
        (1, 6, "big_loss", 5),
        (2, 18, "big_loss", 16),
    ],
)
def test_big_movers_classifies_direction_and_magnitude(grid, finish, kind, magnitude):
    (found,) = anomaly._big_movers([_row(grid=grid, finish=finish)])

    assert found["kind"] == kind
    assert found["magnitude"] == magnitude
    assert f"P{grid} → P{finish}" in found["detail"]


@pytest.mark.unit
@pytest.mark.parametrize("delta", [4, -4, 0], ids=["gained-4", "lost-4", "held-position"])
def test_big_movers_ignores_moves_below_the_threshold(delta):
    assert anomaly._big_movers([_row(grid=10, finish=10 - delta)]) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("grid", "finish"),
    [(None, 4), (18, None), (None, None)],
    ids=["pit-lane-start", "retired", "neither-recorded"],
)
def test_big_movers_skips_rows_with_a_missing_position(grid, finish):
    """A DNF has no finishing position — subtracting from it would invent one."""
    assert anomaly._big_movers([_row(grid=grid, finish=finish)]) == []


@pytest.mark.unit
def test_big_movers_reports_the_gained_wording_for_a_climb():
    (found,) = anomaly._big_movers([_row(driver="Hulkenberg", grid=19, finish=7)])

    assert found["detail"] == "Hulkenberg gained 12 places (P19 → P7)"
    assert found["driver"] == "Hulkenberg"


@pytest.mark.unit
def test_big_movers_reports_the_lost_wording_for_a_drop():
    (found,) = anomaly._big_movers([_row(driver="Piastri", grid=1, finish=13)])

    assert found["detail"] == "Piastri lost 12 places (P1 → P13)"


# ---------------------------------------------------------------------------
# _teammate_battles
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_teammate_battles_flags_a_lopsided_pairing():
    rows = [
        _row(driver="Leclerc", team="ferrari", finish=2, grid=3),
        _row(driver="Hamilton", team="ferrari", finish=12, grid=6),
    ]

    (found,) = anomaly._teammate_battles(rows)

    assert found["kind"] == "teammate_gap"
    assert found["driver"] == "Leclerc"
    assert found["magnitude"] == 10
    assert found["detail"] == "Leclerc beat teammate Hamilton by 10 places (P2 vs P12)"


@pytest.mark.unit
def test_teammate_battles_names_the_better_driver_regardless_of_row_order():
    """Row order is result order; the pairing must be decided by position."""
    rows = [
        _row(driver="Slower", team="alpine", finish=17, grid=17),
        _row(driver="Faster", team="alpine", finish=4, grid=9),
    ]

    (found,) = anomaly._teammate_battles(rows)

    assert found["driver"] == "Faster"
    assert found["magnitude"] == 13


@pytest.mark.unit
def test_teammate_battles_ignores_a_gap_below_the_threshold():
    rows = [
        _row(driver="A", team="williams", finish=8),
        _row(driver="B", team="williams", finish=13),
    ]

    assert anomaly._teammate_battles(rows) == []


@pytest.mark.unit
def test_teammate_battles_needs_two_classified_finishers():
    """One car retiring leaves nothing to compare — not a 20-place thrashing."""
    rows = [
        _row(driver="Finisher", team="haas", finish=5),
        _row(driver="Retiree", team="haas", finish=None, retired="Gearbox"),
    ]

    assert anomaly._teammate_battles(rows) == []


@pytest.mark.unit
def test_teammate_battles_compares_the_extremes_of_a_three_car_team():
    rows = [
        _row(driver="First", team="ferrari", finish=1),
        _row(driver="Middle", team="ferrari", finish=5),
        _row(driver="Last", team="ferrari", finish=14),
    ]

    (found,) = anomaly._teammate_battles(rows)

    assert (found["driver"], found["magnitude"]) == ("First", 13)


# ---------------------------------------------------------------------------
# _retirements
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_retirements_returns_nothing_for_a_full_classification():
    assert anomaly._retirements([_row(finish=1), _row(finish=2)]) == []


@pytest.mark.unit
def test_retirements_summarises_cause_per_driver():
    rows = [
        _row(driver="Norris", retired="Engine"),
        _row(driver="Alonso", retired="Collision"),
        _row(driver="Russell", finish=3),
    ]

    (found,) = anomaly._retirements(rows)

    assert found["kind"] == "retirements"
    assert found["driver"] is None
    assert found["magnitude"] == 2
    assert found["detail"] == "2 retirement(s): Norris (Engine), Alonso (Collision)"


@pytest.mark.unit
def test_retirements_counts_all_but_names_at_most_six():
    rows = [_row(driver=f"D{i}", retired="Accident") for i in range(9)]

    (found,) = anomaly._retirements(rows)

    assert found["magnitude"] == 9, "the count must cover every retirement"
    assert found["detail"].count("Accident") == 6, "only the first six are named"
    assert "D6" not in found["detail"]


# ---------------------------------------------------------------------------
# detect_race_anomalies — against a real f1db file
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_detect_returns_the_biggest_story_as_the_headline(fake_f1db):
    """The seeded race: NOR retires from P2 on the grid, VER and LEC finish."""
    result = anomaly.detect_race_anomalies(2026, 1)

    assert result["available"] is True
    assert result["year"] == 2026
    assert result["round"] == 1
    kinds = [a["kind"] for a in result["anomalies"]]
    assert kinds == ["retirements"], "no grid swing in the fixture reaches the threshold"
    assert result["headline"] == "1 retirement(s): Norris (Engine)"


@pytest.mark.integration
def test_detect_orders_anomalies_by_magnitude(fake_f1db, monkeypatch):
    monkeypatch.setattr(
        anomaly,
        "_race_result_rows",
        lambda _conn, _race_id: [
            _row(driver="Small", team="a", finish=10, grid=15),
            _row(driver="Huge", team="b", finish=2, grid=18),
        ],
    )

    result = anomaly.detect_race_anomalies(2026, 1)

    assert [a["magnitude"] for a in result["anomalies"]] == [16, 5]
    assert result["headline"].startswith("Huge gained 16 places")


@pytest.mark.integration
def test_detect_reports_a_clean_race_when_nothing_is_notable(fake_f1db, monkeypatch):
    monkeypatch.setattr(anomaly, "_race_result_rows", lambda _conn, _race_id: [_row(finish=1, grid=1)])

    result = anomaly.detect_race_anomalies(2026, 1)

    assert result["anomalies"] == []
    assert result["headline"] == "A clean, orderly race — no major anomalies."


@pytest.mark.integration
def test_detect_reports_unavailable_for_a_round_that_does_not_exist(fake_f1db):
    result = anomaly.detect_race_anomalies(2026, 99)

    assert result == {"year": 2026, "round": 99, "available": False, "anomalies": []}


@pytest.mark.integration
def test_detect_reports_unavailable_when_the_race_has_no_results(fake_f1db):
    """Round 3 of 2026 is scheduled but not yet run."""
    result = anomaly.detect_race_anomalies(2026, 3)

    assert result == {"year": 2026, "round": 3, "available": False, "anomalies": []}


@pytest.mark.unit
def test_detect_degrades_to_unavailable_when_the_database_is_unreachable(monkeypatch, capsys):
    def broken_connect():
        raise OSError("unable to open database file")

    monkeypatch.setattr(anomaly, "connect", broken_connect)

    result = anomaly.detect_race_anomalies(2025, 1)

    # "available: False" and not "no anomalies" — an outage must never read as
    # a verdict on the race.
    assert result == {"year": 2025, "round": 1, "available": False, "anomalies": []}
    assert "headline" not in result
    assert "anomaly.detect_failed" in capsys.readouterr().out


@pytest.mark.integration
def test_race_result_rows_returns_every_entrant_including_the_retirement(fake_f1db):
    from app.data.f1db_source import connect

    with connect() as conn:
        race_id = anomaly._race_id(conn, 2026, 1)
        rows = anomaly._race_result_rows(conn, race_id)

    assert [r["driver"] for r in rows] == ["Verstappen", "Leclerc", "Norris"]
    assert rows[-1]["finish"] is None
    assert rows[-1]["retired"] == "Engine"


@pytest.mark.integration
def test_race_id_is_none_for_an_unknown_round(fake_f1db):
    from app.data.f1db_source import connect

    with connect() as conn:
        assert anomaly._race_id(conn, 1998, 1) is None


@pytest.mark.unit
def test_thresholds_are_the_documented_values():
    # Widening either silently changes what the assistant volunteers.
    assert anomaly.BIG_MOVE_POSITIONS == 5
    assert anomaly.LOPSIDED_TEAMMATE_GAP == 6
