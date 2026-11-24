"""Fitted DNF/crash risk: dataset, fit, season-forward backtest and serving maths."""

from __future__ import annotations

import numpy as np
import pytest

from app.ml import risk_model
from app.ml.risk_predict import FITS, LogisticFit, risk_features, risk_probabilities, shrunk_rates


def _raw(year, round_num, code, team, grid=1, reason=None, points=0.0):
    return {
        "year": year,
        "round": round_num,
        "code": code,
        "team": team,
        "grid": grid,
        "reason": reason,
        "points": points,
    }


def _synthetic_rows():
    """Seasons 2018-2023 where a deeper grid slot really does retire more often."""
    rng = np.random.default_rng(7)
    rows = []
    for year in range(2018, 2024):
        for round_num in range(1, 11):
            for grid in range(1, 21):
                crashed = rng.random() < 0.02 + grid * 0.006
                broke = rng.random() < 0.03 + grid * 0.004
                rows.append(
                    {
                        "year": year,
                        "round": round_num,
                        "code": f"D{grid}",
                        "starts": 20,
                        "dnfs": 3,
                        "crashes": 1,
                        "mechanical": 1,
                        "team_pos": (grid + 1) // 2,
                        "grid": grid,
                        "dnf": crashed or broke,
                        "crash": crashed,
                        "other": broke and not crashed,
                    }
                )
    return rows


@pytest.mark.unit
def test_rows_use_only_what_was_known_before_the_race():
    raw = [
        _raw(2018, 1, "AAA", "red", reason="Engine", points=25),
        _raw(2018, 1, "BBB", "ferrari", reason="Collision", points=18),
        _raw(2018, 2, "AAA", "red", grid=0),
        _raw(2018, 2, "BBB", "ferrari", grid=3),
        _raw(2019, 1, "AAA", "red", grid=2),
    ]
    rows = risk_model.build_rows(raw)
    first, second, last = rows[0], rows[2], rows[4]

    assert (first["starts"], first["dnfs"], first["team_pos"]) == (0, 0, risk_model.DEFAULT_TEAM_POS)
    assert first["dnf"]
    assert not first["crash"]
    assert first["other"]
    assert rows[1]["crash"]
    assert rows[1]["dnf"]
    assert not rows[1]["other"]
    # Round 2: the round-1 retirement is now history, red outscored ferrari, and a
    # missing grid slot (pit-lane start) reads as the back of the field.
    assert (second["starts"], second["dnfs"], second["mechanical"], second["team_pos"]) == (1, 1, 1, 1)
    assert second["grid"] == risk_model.DEFAULT_GRID
    assert rows[3]["team_pos"] == 2
    assert rows[3]["crashes"] == 1
    # New season: history carries over and round 1 ranks teams by last year's points.
    assert (last["starts"], last["dnfs"], last["team_pos"]) == (2, 1, 1)
    assert not last["dnf"]


@pytest.mark.unit
def test_legacy_formula_matches_the_retired_hand_tuned_weights():
    base = {"starts": 0, "dnfs": 0, "crashes": 0, "mechanical": 0, "team_pos": 5, "grid": 1}
    fresh = risk_model.legacy_risks(base)
    assert fresh["dnf"] == pytest.approx(0.11)  # 6 + 2.48 + 0.72 + 0 + 2 -> 11
    assert fresh["crash"] == pytest.approx(0.06)

    mid = risk_model.legacy_risks({**base, "starts": 10, "dnfs": 5, "crashes": 3, "mechanical": 4, "grid": 12})
    assert mid["dnf"] == pytest.approx(0.33)
    assert mid["crash"] == pytest.approx(0.18)


@pytest.mark.unit
def test_shrunk_rates_pull_thin_histories_toward_the_field_rate():
    assert shrunk_rates(0, 0, 0) == pytest.approx({"dnf": 0.18, "crash": 0.07, "other": 0.11})
    thin = shrunk_rates(2, 2, 0)["dnf"]
    deep = shrunk_rates(200, 200, 0)["dnf"]
    assert 0.18 < thin < 0.5 < deep < 1.0


@pytest.mark.unit
def test_risk_features_follow_the_published_order():
    features = risk_features({"starts": 0, "dnfs": 0, "crashes": 0}, 7, 3)
    assert features == pytest.approx([0.07, 0.11, 3.0, 7.0])


@pytest.mark.unit
def test_logistic_fit_predicts_a_probability_from_standardised_inputs():
    fit = LogisticFit(means=(0.0,), scales=(2.0,), weights=(1.0,), bias=0.0)
    assert fit.predict([0.0]) == pytest.approx(0.5)
    assert fit.predict([4.0]) > 0.85
    assert fit.predict([-4.0]) < 0.15


@pytest.mark.unit
def test_shipped_probabilities_rise_toward_the_back_of_the_grid():
    clean = {"starts": 20, "dnfs": 2, "crashes": 1}
    front = risk_probabilities(clean, 2, 3)
    back = risk_probabilities(clean, 19, 3)
    assert set(front) == {"dnf", "crash", "other"} == set(FITS)
    assert back["dnf"] > front["dnf"]
    assert back["crash"] > front["crash"]
    assert all(0 < p < 1 for p in front.values())


@pytest.mark.unit
def test_fit_learns_the_grid_signal_and_best_threshold_maximises_f1():
    rows = _synthetic_rows()
    fit = risk_model.fit_logistic(rows, "dnf")
    grid_weight = fit.weights[risk_model.row_features(rows[0]).index(1.0)]
    assert grid_weight > 0

    probs = [0.1, 0.2, 0.8, 0.9]
    assert risk_model.best_threshold(probs, [False, False, True, True]) == 0.8

    flat = risk_model.fit_logistic([{**r, "grid": 5, "team_pos": 5} for r in rows], "dnf")
    assert flat.scales[-1] == 1.0  # a constant column does not divide by zero


@pytest.mark.unit
def test_backtest_scores_the_fit_against_the_legacy_formula_on_held_out_seasons():
    rows = _synthetic_rows()
    result = risk_model.backtest(rows, "dnf")

    assert set(result) == {"fitted", "legacy"}
    for stats in result.values():
        assert 0 <= stats["auc"] <= 1
        assert 0 <= stats["precision"] <= 1
        assert 0 <= stats["recall"] <= 1
    # Only 2021-2023 are held out, each predicted from earlier seasons.
    assert result["fitted"]["auc"] > 0.5
    assert result["fitted"]["flagged"] > 0


@pytest.mark.unit
def test_metrics_report_zero_precision_when_nothing_is_flagged():
    stats = risk_model._metrics([0.1, 0.2, 0.3], [False, True, False], cut=0.9)
    assert stats["precision"] == 0.0
    assert stats["flagged"] == 0
    assert stats["recall"] == 0.0


@pytest.mark.unit
def test_load_rows_reads_the_race_history_from_f1db(fake_f1db):
    rows = risk_model.load_rows()

    assert rows
    assert {"year", "starts", "dnfs", "grid", "team_pos", "dnf", "crash", "other"} <= set(rows[0])
    assert all(row["year"] >= risk_model.FIRST_TRAIN_YEAR for row in rows)


@pytest.mark.unit
def test_main_prints_one_backtest_and_one_ship_line_per_label(monkeypatch, capsys):
    monkeypatch.setattr(risk_model, "load_rows", _synthetic_rows)

    risk_model.main()

    out = capsys.readouterr().out
    assert out.count("ship") == 3
    for label in ("dnf", "crash", "other"):
        assert label in out
