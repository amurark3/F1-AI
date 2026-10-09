"""Tests for app.ml.evaluate — the ranking backtest harness.

This module is the evidence base for every claim the project makes about the
model being worth having, and `app.ml.promote` turns its output directly into a
ship/no-ship decision. That makes two properties load-bearing:

* **The metrics must mean what they say.** The product output is a finishing
  *order*, so the scores are rank-based and the sign conventions matter: lower
  predicted score = predicted to finish better, throughout. A flipped comparison
  here would read as a model that beats the grid baseline when it does not.
* **The backtest must not leak the future.** Each held-out season is scored by a
  model fit strictly on earlier seasons. Training on the season being scored
  would inflate every headline number in the report.

The estimator is a recording stub, so nothing here fits a real model or touches
the cached dataset; the numeric expectations are computed by hand from the
default weights in ``app.config``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.config import ML_PREDICTION_BLEND_WEIGHT
from app.ml import evaluate as evaluate_module
from app.ml.evaluate import (
    BASELINES,
    _aggregate,
    _heuristic_scores,
    _print_report,
    _ranking_metrics,
    backtest,
    load_or_collect_dataset,
)
from app.ml.features import FEATURES, TARGET

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _season_frame(
    year: int,
    rounds: tuple[int, ...] = (1,),
    n_drivers: int = 4,
    *,
    grid_matches_finish: bool = True,
) -> pd.DataFrame:
    """One season of collected rows.

    ``grid_position`` runs 1..N. With ``grid_matches_finish`` the finish order is
    identical, so the grid baseline scores perfectly; without it the finish order
    is exactly reversed, which is the worst case the metrics can express.
    """
    records = []
    for rnd in rounds:
        for index in range(n_drivers):
            row = dict.fromkeys(FEATURES, 0.0)
            row["grid_position"] = float(index + 1)
            row["recent_form_avg"] = float(index + 1)
            row["driver_standing"] = float(index + 1)
            row[TARGET] = float(index + 1) if grid_matches_finish else float(n_drivers - index)
            row["year"] = year
            row["round"] = rnd
            records.append(row)
    return pd.DataFrame(records)


class _Recorder:
    """Captures the shape of every training set the backtest builds."""

    def __init__(self) -> None:
        self.fit_sizes: list[int] = []
        self.fit_widths: list[int] = []


class _GridEchoModel:
    """Predicts the first feature column verbatim.

    With the default feature order that is ``grid_position``, which makes the
    model's scores identical to the ``grid_order`` baseline — a fixed point the
    harness's own arithmetic can be checked against.
    """

    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        self._recorder.fit_sizes.append(len(x))
        self._recorder.fit_widths.append(x.shape[1])

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(x)[:, 0]


def _factory(recorder: _Recorder):
    return lambda: _GridEchoModel(recorder)


# ---------------------------------------------------------------------------
# _ranking_metrics
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("size", [0, 1])
def test_a_race_with_fewer_than_two_finishers_is_unscoreable(size):
    # Rank correlation is undefined for a single entry; returning {} is what lets
    # `backtest` drop the race instead of averaging in a meaningless number.
    assert _ranking_metrics(np.arange(size, dtype=float), np.arange(1, size + 1, dtype=float)) == {}


@pytest.mark.unit
def test_a_perfect_prediction_scores_perfectly_on_every_metric():
    metrics = _ranking_metrics(np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.0, 2.0, 3.0, 4.0]))

    assert metrics == {
        "spearman": 1.0,
        "mae": 0.0,
        "podium_hit_rate": 1.0,
        "points_accuracy": 1.0,
        "winner_accuracy": 1.0,
    }


@pytest.mark.unit
def test_an_exactly_reversed_prediction_scores_minus_one():
    metrics = _ranking_metrics(np.array([4.0, 3.0, 2.0, 1.0]), np.array([1.0, 2.0, 3.0, 4.0]))

    assert metrics["spearman"] == -1.0
    assert metrics["winner_accuracy"] == 0.0
    assert metrics["mae"] == pytest.approx(2.0)
    # Two of the actual top three were still predicted inside the top three.
    assert metrics["podium_hit_rate"] == pytest.approx(2 / 3)


@pytest.mark.unit
def test_lower_predicted_scores_mean_predicted_to_finish_better():
    # The sign convention the whole module runs on: the model, the heuristic and
    # every baseline are all "lower = better", so they can be compared directly.
    metrics = _ranking_metrics(np.array([0.1, 0.9]), np.array([1.0, 2.0]))

    assert metrics["winner_accuracy"] == 1.0
    assert metrics["spearman"] == pytest.approx(1.0)


@pytest.mark.unit
# scipy warns that the correlation is undefined here — which is exactly the
# input this test exists to cover, so the warning is the expected path.
@pytest.mark.filterwarnings("ignore:An input array is constant")
def test_a_field_that_all_finished_equal_scores_zero_rather_than_nan():
    # `spearmanr` returns NaN against a zero-variance vector. A NaN would poison
    # every downstream average, so it is clamped to 0.0 — no signal, not "broken".
    metrics = _ranking_metrics(np.array([1.0, 2.0, 3.0]), np.array([5.0, 5.0, 5.0]))

    assert metrics["spearman"] == 0.0
    assert not np.isnan(metrics["spearman"])


@pytest.mark.unit
def test_podium_hit_rate_always_divides_by_three():
    # A two-car race can score at most 2/3 here. Pinned because it makes podium
    # numbers from very short fields incomparable with full-grid ones.
    metrics = _ranking_metrics(np.array([1.0, 2.0]), np.array([1.0, 2.0]))

    assert metrics["podium_hit_rate"] == pytest.approx(2 / 3)


@pytest.mark.unit
def test_points_accuracy_shrinks_its_window_to_the_field_size():
    # Unlike the podium, the points window is min(10, N) — so a short field can
    # still score 1.0 rather than being capped below it.
    metrics = _ranking_metrics(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]))

    assert metrics["points_accuracy"] == 1.0


@pytest.mark.unit
def test_the_points_window_stops_at_ten_for_a_full_grid():
    # 20 cars, and the prediction is right about exactly who scores but wrong
    # about the order inside and outside the top ten.
    actual = np.arange(1.0, 21.0)
    pred = np.concatenate([np.arange(10.0, 0.0, -1.0), np.arange(20.0, 10.0, -1.0)])

    metrics = _ranking_metrics(pred, actual)

    assert metrics["points_accuracy"] == 1.0


@pytest.mark.unit
def test_ties_in_predicted_score_are_broken_stably():
    # `argsort(kind="stable")` keeps the dataset's own order, so an all-tied
    # prediction is scored deterministically instead of by numpy's whim.
    first = _ranking_metrics(np.array([1.0, 1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0, 4.0]))
    second = _ranking_metrics(np.array([1.0, 1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0, 4.0]))

    assert first == second
    assert first["winner_accuracy"] == 1.0


# ---------------------------------------------------------------------------
# _aggregate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregating_no_races_yields_no_metrics():
    # A predictor that scored nothing must report {} rather than zeros, so the
    # report shows nan instead of claiming a real score of 0.
    assert _aggregate([]) == {}


@pytest.mark.unit
def test_metrics_are_averaged_across_races():
    aggregated = _aggregate([{"spearman": 1.0, "mae": 2.0}, {"spearman": 0.0, "mae": 4.0}])

    assert aggregated == {"spearman": 0.5, "mae": 3.0}


@pytest.mark.unit
def test_every_aggregated_metric_is_a_plain_float():
    # numpy scalars serialise inconsistently once these land in JSON reports.
    aggregated = _aggregate([{"spearman": np.float64(0.5)}])

    assert type(aggregated["spearman"]) is float


# ---------------------------------------------------------------------------
# _heuristic_scores
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_normal_weekend_scores_on_the_configured_weights():
    # 0.35*2 + 0.25*4 + 0.20*6 + 0.15*3 - 0.05*1, weights already summing to 1.0.
    race = _season_frame(2024, n_drivers=1)
    race.loc[0, ["grid_position", "recent_form_avg", "circuit_avg", "team_standing", "grid_delta_avg"]] = [
        2.0,
        4.0,
        6.0,
        3.0,
        1.0,
    ]

    assert _heuristic_scores(race)[0] == pytest.approx(3.3)


@pytest.mark.unit
def test_a_sprint_weekend_adds_the_sprint_signal_and_renormalises():
    # Sprint adds 0.30 and cuts qualifying to 0.20, taking the raw total to 1.15;
    # the result is divided back down so the scales stay comparable.
    race = _season_frame(2024, n_drivers=1)
    race.loc[
        0,
        [
            "had_sprint",
            "sprint_position",
            "grid_position",
            "recent_form_avg",
            "circuit_avg",
            "team_standing",
            "grid_delta_avg",
        ],
    ] = [1.0, 5.0, 2.0, 4.0, 6.0, 3.0, 1.0]

    expected = (0.30 * 5 + 0.20 * 2 + 0.25 * 4 + 0.20 * 6 + 0.15 * 3 - 0.05 * 1) / 1.15
    assert _heuristic_scores(race)[0] == pytest.approx(expected)


@pytest.mark.unit
def test_the_sprint_flag_is_read_once_for_the_whole_race():
    # `had_sprint` is a weekend-level fact; it is taken from row 0 and applied to
    # every driver, so a per-row disagreement must not split the weighting.
    race = _season_frame(2024, n_drivers=3)
    race["had_sprint"] = [1.0, 0.0, 0.0]
    race["sprint_position"] = [1.0, 1.0, 1.0]

    scores = _heuristic_scores(race)

    # All three were scored on the sprint weighting, so the sprint term is in
    # every score — the grid term alone cannot explain the spacing.
    assert len(scores) == 3
    assert scores[0] != pytest.approx(0.35 * 1.0)


@pytest.mark.unit
def test_positions_gained_at_a_circuit_improve_the_score():
    # `grid_delta_avg` is subtracted: a driver who historically gains places gets
    # a *lower* score, which is the better-finish direction.
    race = _season_frame(2024, n_drivers=2)
    race["grid_position"] = [5.0, 5.0]
    race["grid_delta_avg"] = [3.0, 0.0]

    scores = _heuristic_scores(race)

    assert scores[0] < scores[1]


@pytest.mark.unit
def test_a_better_grid_slot_improves_the_score():
    race = _season_frame(2024, n_drivers=2)
    race["grid_position"] = [1.0, 18.0]

    scores = _heuristic_scores(race)

    assert scores[0] < scores[1]


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_most_recent_season_is_held_out_by_default():
    recorder = _Recorder()
    df = pd.concat([_season_frame(2022), _season_frame(2023), _season_frame(2024)], ignore_index=True)

    results = backtest(df, _factory(recorder))

    assert results["_meta"]["holdout_seasons"] == [2024]


@pytest.mark.unit
def test_a_held_out_season_is_scored_by_a_model_that_never_saw_it():
    # The leak this guards against would inflate every number in the report.
    recorder = _Recorder()
    df = pd.concat(
        [
            _season_frame(2022, n_drivers=4),
            _season_frame(2023, n_drivers=6),
            _season_frame(2024, n_drivers=8),
        ],
        ignore_index=True,
    )

    backtest(df, _factory(recorder), holdout_seasons=[2023, 2024])

    # 2023 trains on 2022 alone (4 rows); 2024 on 2022+2023 (10 rows).
    assert recorder.fit_sizes == [4, 10]


@pytest.mark.unit
def test_a_fresh_estimator_is_fit_for_each_held_out_season():
    # Reusing one estimator across seasons would carry the later season's fit
    # backwards on any incremental learner.
    recorder = _Recorder()
    df = pd.concat([_season_frame(2022), _season_frame(2023), _season_frame(2024)], ignore_index=True)

    backtest(df, _factory(recorder), holdout_seasons=[2023, 2024])

    assert len(recorder.fit_sizes) == 2


@pytest.mark.unit
def test_the_earliest_season_cannot_be_held_out():
    # There is nothing earlier to train on, so the season is skipped rather than
    # scored by an unfit model.
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024)], ignore_index=True)

    results = backtest(df, _factory(recorder), holdout_seasons=[2023])

    assert recorder.fit_sizes == []
    assert results["_meta"]["n_races"] == 0


@pytest.mark.unit
def test_a_holdout_season_absent_from_the_data_is_skipped():
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024)], ignore_index=True)

    results = backtest(df, _factory(recorder), holdout_seasons=[2024, 2025])

    assert results["_meta"]["n_races"] == 1


@pytest.mark.unit
def test_rows_with_a_missing_feature_are_dropped_before_scoring():
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023, n_drivers=4), _season_frame(2024, n_drivers=4)], ignore_index=True)
    df.loc[0, "circuit_avg"] = None

    backtest(df, _factory(recorder), holdout_seasons=[2024])

    assert recorder.fit_sizes == [3]


@pytest.mark.unit
def test_the_caller_s_dataframe_is_never_modified():
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024)], ignore_index=True)
    df.loc[0, "circuit_avg"] = None
    before = df.copy()

    backtest(df, _factory(recorder), holdout_seasons=[2024])

    pd.testing.assert_frame_equal(df, before)


@pytest.mark.unit
def test_a_race_with_a_single_classified_driver_is_skipped():
    recorder = _Recorder()
    df = pd.concat(
        [
            _season_frame(2023, n_drivers=4),
            _season_frame(2024, rounds=(1,), n_drivers=1),
            _season_frame(2024, rounds=(2,), n_drivers=4),
        ],
        ignore_index=True,
    )

    results = backtest(df, _factory(recorder), holdout_seasons=[2024])

    assert results["_meta"]["n_races"] == 1


@pytest.mark.unit
def test_every_race_in_a_held_out_season_is_scored():
    recorder = _Recorder()
    df = pd.concat(
        [_season_frame(2023), _season_frame(2024, rounds=(1, 2, 3))],
        ignore_index=True,
    )

    results = backtest(df, _factory(recorder), holdout_seasons=[2024])

    assert results["_meta"]["n_races"] == 3


@pytest.mark.unit
def test_the_report_covers_the_model_the_heuristic_the_blend_and_every_baseline():
    # The whole point of the harness is the comparison; a missing predictor makes
    # the "does it beat the grid?" question unanswerable.
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024)], ignore_index=True)

    results = backtest(df, _factory(recorder), holdout_seasons=[2024])

    assert set(results) == {"ensemble", "model", "heuristic", "_meta", *BASELINES}


@pytest.mark.unit
def test_a_model_that_echoes_the_grid_scores_exactly_like_the_grid_baseline():
    # An arithmetic fixed point: the stub predicts `grid_position` verbatim, so
    # any divergence here is the harness scoring the two paths differently.
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024, grid_matches_finish=False)], ignore_index=True)

    results = backtest(df, _factory(recorder), holdout_seasons=[2024])

    assert results["model"] == results["grid_order"]


@pytest.mark.unit
def test_a_grid_that_predicts_the_finish_scores_perfectly():
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024)], ignore_index=True)

    results = backtest(df, _factory(recorder), holdout_seasons=[2024])

    assert results["grid_order"]["spearman"] == 1.0
    assert results["grid_order"]["winner_accuracy"] == 1.0


@pytest.mark.unit
def test_a_reversed_season_scores_minus_one_for_the_grid_baseline():
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024, grid_matches_finish=False)], ignore_index=True)

    results = backtest(df, _factory(recorder), holdout_seasons=[2024])

    assert results["grid_order"]["spearman"] == -1.0


@pytest.mark.unit
def test_the_meta_block_records_how_the_backtest_was_run():
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024, rounds=(1, 2))], ignore_index=True)

    meta = backtest(df, _factory(recorder), holdout_seasons=[2024])["_meta"]

    assert meta == {
        "holdout_seasons": [2024],
        "n_races": 2,
        "blend_weight": ML_PREDICTION_BLEND_WEIGHT,
    }


@pytest.mark.unit
def test_a_custom_feature_set_is_what_the_model_is_fit_on():
    # The harness doubles as a feature-selection tool, so the override has to
    # reach the estimator rather than being silently ignored.
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024)], ignore_index=True)

    backtest(df, _factory(recorder), holdout_seasons=[2024], features=["grid_position", "recent_form_avg"])

    assert recorder.fit_widths == [2]


@pytest.mark.unit
def test_the_full_feature_set_is_used_when_none_is_given():
    recorder = _Recorder()
    df = pd.concat([_season_frame(2023), _season_frame(2024)], ignore_index=True)

    backtest(df, _factory(recorder), holdout_seasons=[2024])

    assert recorder.fit_widths == [len(FEATURES)]


# ---------------------------------------------------------------------------
# load_or_collect_dataset
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_cached_dataset_is_reused_without_recollecting(tmp_path, monkeypatch, capsys):
    cached = tmp_path / "training_dataset.csv"
    _season_frame(2024).to_csv(cached, index=False)
    monkeypatch.setattr(evaluate_module, "DATASET_PATH", cached)

    def _explode() -> pd.DataFrame:
        raise AssertionError("the cache was ignored")

    monkeypatch.setattr("app.ml.train.collect_data", _explode)

    df = load_or_collect_dataset()

    assert len(df) == 4
    assert "Loading cached dataset" in capsys.readouterr().out


@pytest.mark.unit
def test_refresh_recollects_even_when_a_cache_exists(tmp_path, monkeypatch, capsys):
    cached = tmp_path / "training_dataset.csv"
    _season_frame(2024, n_drivers=4).to_csv(cached, index=False)
    monkeypatch.setattr(evaluate_module, "DATASET_PATH", cached)
    monkeypatch.setattr("app.ml.train.collect_data", lambda: _season_frame(2025, n_drivers=7))

    df = load_or_collect_dataset(refresh=True)

    assert len(df) == 7
    assert df["year"].unique().tolist() == [2025]


@pytest.mark.unit
def test_a_missing_cache_triggers_collection(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(evaluate_module, "DATASET_PATH", tmp_path / "absent.csv")
    monkeypatch.setattr("app.ml.train.collect_data", lambda: _season_frame(2025))

    assert len(load_or_collect_dataset()) == 4


@pytest.mark.unit
def test_a_freshly_collected_dataset_is_cached_for_the_next_run(tmp_path, monkeypatch, capsys):
    target = tmp_path / "nested" / "training_dataset.csv"
    monkeypatch.setattr(evaluate_module, "DATASET_PATH", target)
    monkeypatch.setattr("app.ml.train.collect_data", lambda: _season_frame(2025))

    load_or_collect_dataset(refresh=True)

    assert target.exists(), "the collected dataset was not cached"
    assert len(pd.read_csv(target)) == 4


@pytest.mark.unit
def test_an_empty_collection_is_not_cached(tmp_path, monkeypatch, capsys):
    # Caching an empty frame would make every later run load nothing instantly
    # and never retry the collection.
    target = tmp_path / "training_dataset.csv"
    monkeypatch.setattr(evaluate_module, "DATASET_PATH", target)
    monkeypatch.setattr("app.ml.train.collect_data", pd.DataFrame)

    assert load_or_collect_dataset(refresh=True).empty
    assert not target.exists()


# ---------------------------------------------------------------------------
# _print_report
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_report_lists_every_predictor_and_metric(capsys):
    _print_report(
        {
            "ensemble": {
                "spearman": 0.8,
                "podium_hit_rate": 0.6,
                "winner_accuracy": 0.3,
                "points_accuracy": 0.7,
                "mae": 3.0,
            },
            "model": {
                "spearman": 0.7,
                "podium_hit_rate": 0.5,
                "winner_accuracy": 0.2,
                "points_accuracy": 0.6,
                "mae": 3.5,
            },
            "heuristic": {
                "spearman": 0.6,
                "podium_hit_rate": 0.4,
                "winner_accuracy": 0.1,
                "points_accuracy": 0.5,
                "mae": 4.0,
            },
            "grid_order": {"spearman": 0.5},
            "championship_order": {"spearman": 0.4},
            "recent_form_order": {"spearman": 0.3},
            "_meta": {"n_races": 57, "holdout_seasons": [2023, 2024], "blend_weight": 0.65},
        }
    )
    report = capsys.readouterr().out

    for predictor in ("ensemble", "model", "heuristic", *BASELINES):
        assert predictor in report
    assert "57 races" in report
    assert "[2023, 2024]" in report


@pytest.mark.unit
def test_the_report_states_the_blend_it_is_scoring(capsys):
    # Without the split, "ensemble" is an unlabelled number.
    _print_report({"_meta": {"n_races": 1, "holdout_seasons": [2024], "blend_weight": 0.65}})

    assert "0.65*model + 0.35*heuristic" in capsys.readouterr().out


@pytest.mark.unit
def test_a_predictor_that_scored_nothing_shows_nan_rather_than_zero(capsys):
    # A predictor with no races must not read as a genuine score of 0.000.
    _print_report({"model": {}, "_meta": {"n_races": 0, "holdout_seasons": [2024], "blend_weight": 0.65}})

    assert "nan" in capsys.readouterr().out


@pytest.mark.unit
def test_the_report_explains_which_direction_is_better(capsys):
    # MAE runs the opposite way to every other column in the table.
    _print_report({"_meta": {"n_races": 1, "holdout_seasons": [2024], "blend_weight": 0.65}})
    report = capsys.readouterr().out

    assert "lower is better for MAE" in report
    assert "beats grid_order" in report


@pytest.mark.unit
def test_a_report_without_meta_still_prints(capsys):
    _print_report({})

    assert "Backtest over 0 races" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_empty_dataset_exits_with_a_pointer_to_refresh(monkeypatch, capsys):
    monkeypatch.setattr(evaluate_module.sys, "argv", ["evaluate"])
    monkeypatch.setattr(evaluate_module, "load_or_collect_dataset", lambda refresh: pd.DataFrame())

    with pytest.raises(SystemExit) as exit_info:
        evaluate_module.main()

    assert exit_info.value.code == 1
    assert "--refresh" in capsys.readouterr().out


@pytest.mark.unit
def test_the_refresh_flag_is_read_from_the_command_line(monkeypatch, capsys):
    seen: list[bool] = []
    monkeypatch.setattr(evaluate_module.sys, "argv", ["evaluate", "--refresh"])
    monkeypatch.setattr(
        evaluate_module,
        "load_or_collect_dataset",
        lambda refresh: seen.append(refresh) or _season_frame(2024),
    )
    monkeypatch.setattr(evaluate_module, "backtest", lambda df, factory, holdout_seasons: {"_meta": {}})
    monkeypatch.setattr(evaluate_module, "_print_report", lambda results: None)

    evaluate_module.main()

    assert seen == [True]


@pytest.mark.unit
def test_without_the_flag_the_cached_dataset_is_used(monkeypatch, capsys):
    seen: list[bool] = []
    monkeypatch.setattr(evaluate_module.sys, "argv", ["evaluate"])
    monkeypatch.setattr(
        evaluate_module,
        "load_or_collect_dataset",
        lambda refresh: seen.append(refresh) or _season_frame(2024),
    )
    monkeypatch.setattr(evaluate_module, "backtest", lambda df, factory, holdout_seasons: {"_meta": {}})
    monkeypatch.setattr(evaluate_module, "_print_report", lambda results: None)

    evaluate_module.main()

    assert seen == [False]


@pytest.mark.unit
def test_every_season_with_three_prior_ones_is_held_out(monkeypatch, capsys):
    # The headline numbers come from a multi-season sample so one noisy ~10-race
    # season cannot define the project's whole claim about the model.
    seen: list[list[int]] = []
    seasons = [2019, 2020, 2021, 2022, 2023, 2024]
    df = pd.concat([_season_frame(year) for year in seasons], ignore_index=True)

    monkeypatch.setattr(evaluate_module.sys, "argv", ["evaluate"])
    monkeypatch.setattr(evaluate_module, "load_or_collect_dataset", lambda refresh: df)
    monkeypatch.setattr(
        evaluate_module,
        "backtest",
        lambda frame, factory, holdout_seasons: seen.append(holdout_seasons) or {"_meta": {}},
    )
    monkeypatch.setattr(evaluate_module, "_print_report", lambda results: None)

    evaluate_module.main()

    assert seen == [[2022, 2023, 2024]]


@pytest.mark.unit
def test_a_thin_dataset_falls_back_to_the_most_recent_season(monkeypatch, capsys):
    seen: list[list[int]] = []
    df = pd.concat([_season_frame(2023), _season_frame(2024)], ignore_index=True)

    monkeypatch.setattr(evaluate_module.sys, "argv", ["evaluate"])
    monkeypatch.setattr(evaluate_module, "load_or_collect_dataset", lambda refresh: df)
    monkeypatch.setattr(
        evaluate_module,
        "backtest",
        lambda frame, factory, holdout_seasons: seen.append(holdout_seasons) or {"_meta": {}},
    )
    monkeypatch.setattr(evaluate_module, "_print_report", lambda results: None)

    evaluate_module.main()

    assert seen == [[2024]]
