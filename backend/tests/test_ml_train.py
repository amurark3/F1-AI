"""Tests for app.ml.train — offline dataset assembly and the production fit.

This module produces the artifact the live prediction path loads, so its risks
are the ones that stay silent until predictions are already wrong:

* **Chronological leakage.** Every accumulated signal — season form, circuit
  history, championship standings — must be *as of* the race being built and
  must never include it. A row that knows its own result trains a model that
  cannot reproduce its own validation numbers in production.
* **Accumulator scope.** Circuit history deliberately persists across seasons
  while season form resets each year. Getting either backwards changes the
  meaning of a feature without changing its name.
* **The artifact is a contract.** The saved bundle carries the feature list and
  the metrics alongside the estimator, so inference cannot silently pair a new
  model with an old feature order, and a regression can be traced to a fit.

f1db is stubbed at the module boundary; the estimator is real (a Ridge pipeline
over a handful of rows fits instantly) and the artifact is written to tmp_path.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml import train as train_module
from app.ml.features import (
    CIRCUIT_FALLBACK,
    FEATURES,
    GRID_DELTA_FALLBACK,
    GRID_FALLBACK,
    RECENT_FORM_FALLBACK,
    STANDING_FALLBACK,
    TARGET,
)
from app.ml.train import (
    MODEL_PARAMS,
    SeasonHistory,
    _build_model,
    _build_race_rows,
    _get_constructor_standings,
    _get_driver_standings,
    _get_race_schedule,
    _print_feature_influence,
    _team_position,
    collect_data,
    train,
    walk_forward_validation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _round_data(
    *,
    grid: dict[str, int],
    race: dict[str, int],
    sprint: dict[str, int] | None = None,
    teams: dict[str, str] | None = None,
    location: str = "Monza",
    name: str = "Italian Grand Prix",
) -> dict:
    return {
        "grid": grid,
        "race": race,
        "sprint": sprint or {},
        "teams": teams or dict.fromkeys(race, "Ferrari"),
        "location": location,
        "name": name,
    }


def _install_f1db(monkeypatch: pytest.MonkeyPatch, seasons: dict[int, dict[int, dict]]) -> None:
    """Stub every f1db accessor `train` reads, from a {year: {round: data}} map."""

    def _round(year: int, rnd: int) -> dict:
        return seasons.get(year, {}).get(rnd, {})

    monkeypatch.setattr(
        train_module,
        "race_schedule",
        lambda year: [
            {"round": rnd, "name": data["name"], "location": data["location"]}
            for rnd, data in sorted(seasons.get(year, {}).items())
        ],
    )
    monkeypatch.setattr(train_module, "qualifying_positions", lambda year, rnd: _round(year, rnd).get("grid", {}))
    monkeypatch.setattr(train_module, "race_results", lambda year, rnd: _round(year, rnd).get("race", {}))
    monkeypatch.setattr(train_module, "sprint_positions", lambda year, rnd: _round(year, rnd).get("sprint", {}))
    monkeypatch.setattr(train_module, "driver_teams", lambda year, rnd: _round(year, rnd).get("teams", {}))
    monkeypatch.setattr(train_module, "driver_standings_after_round", lambda year, rnd: {})
    monkeypatch.setattr(train_module, "constructor_standings_after_round", lambda year, rnd: [])
    monkeypatch.setattr(train_module, "TRAIN_YEARS", sorted(seasons))


def _empty_history() -> SeasonHistory:
    return SeasonHistory(
        circuit_results={},
        season_results_so_far={},
        circuit_grid_deltas={},
        season_sprints_so_far={},
    )


def _training_frame(seasons: tuple[int, ...] = (2022, 2023, 2024), n_drivers: int = 6) -> pd.DataFrame:
    """A collected-shape frame good enough to fit a real Ridge pipeline."""
    records = []
    for year in seasons:
        for rnd in (1, 2):
            for index in range(n_drivers):
                row = dict.fromkeys(FEATURES, 0.0)
                row["grid_position"] = float(index + 1)
                row["recent_form_avg"] = float(index + 1)
                row["driver_standing"] = float(index + 1)
                row["team_standing"] = float(index // 2 + 1)
                row[TARGET] = float(index + 1)
                row["year"] = year
                row["round"] = rnd
                row["location"] = "Monza"
                row["driver_code"] = f"D{index}"
                records.append(row)
    return pd.DataFrame(records)


class _Importances:
    """A tree-style estimator: magnitudes only, no signed coefficients."""

    feature_importances_ = np.linspace(0.9, 0.1, len(FEATURES))


class _Opaque:
    """An estimator exposing neither coefficients nor importances."""


# ---------------------------------------------------------------------------
# f1db accessors
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_season_with_no_schedule_yields_an_empty_frame(monkeypatch):
    monkeypatch.setattr(train_module, "race_schedule", lambda year: [])

    assert _get_race_schedule(2030).empty


@pytest.mark.unit
def test_the_schedule_is_reshaped_into_the_columns_the_collector_reads(monkeypatch):
    monkeypatch.setattr(
        train_module,
        "race_schedule",
        lambda year: [{"round": 3, "name": "Australian Grand Prix", "location": "Melbourne"}],
    )

    schedule = _get_race_schedule(2024)

    assert schedule.to_dict("records") == [
        {"RoundNumber": 3, "EventName": "Australian Grand Prix", "Location": "Melbourne"}
    ]


@pytest.mark.unit
def test_standings_going_into_a_race_are_those_after_the_previous_round(monkeypatch):
    # The leak this prevents: standings *after* the race already encode its
    # result, so the model would be told who won before predicting it.
    seen: list[int] = []
    monkeypatch.setattr(train_module, "driver_standings_after_round", lambda year, rnd: seen.append(rnd) or {"VER": 1})

    _get_driver_standings(2024, 7)

    assert seen == [6]


@pytest.mark.unit
def test_standings_for_the_opening_round_fall_back_to_round_one(monkeypatch):
    # There is no round 0; clamping avoids asking f1db for one.
    seen: list[int] = []
    monkeypatch.setattr(train_module, "driver_standings_after_round", lambda year, rnd: seen.append(rnd) or {})

    _get_driver_standings(2024, 1)

    assert seen == [1]


@pytest.mark.unit
def test_constructor_standings_are_keyed_by_team_name(monkeypatch):
    monkeypatch.setattr(
        train_module,
        "constructor_standings_after_round",
        lambda year, rnd: [
            {"constructor_name": "Red Bull", "position": 1},
            {"constructor_name": "Ferrari", "position": 2},
        ],
    )

    assert _get_constructor_standings(2024, 5) == {"Red Bull": 1, "Ferrari": 2}


@pytest.mark.unit
def test_constructor_standings_also_read_the_previous_round(monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr(train_module, "constructor_standings_after_round", lambda year, rnd: seen.append(rnd) or [])

    _get_constructor_standings(2024, 9)

    assert seen == [8]


# ---------------------------------------------------------------------------
# _team_position
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_team_name_matches_its_standings_entry_exactly():
    assert _team_position("Ferrari", {"Ferrari": 2, "Red Bull": 1}) == 2


@pytest.mark.unit
def test_a_team_name_matches_case_insensitively():
    assert _team_position("FERRARI", {"ferrari": 3}) == 3


@pytest.mark.unit
def test_a_longer_entrant_name_matches_its_shorter_standings_name():
    # f1db's entrant strings are verbose; the standings key is the short form.
    assert _team_position("Scuderia Ferrari HP", {"Ferrari": 2}) == 2


@pytest.mark.unit
def test_a_shorter_entrant_name_matches_its_longer_standings_name():
    assert _team_position("Ferrari", {"Scuderia Ferrari HP": 2}) == 2


@pytest.mark.unit
def test_an_unmatched_team_is_treated_as_midfield():
    # A rename or a new entrant must not crash the collection run.
    assert _team_position("Andretti Cadillac", {"Ferrari": 2}) == 10


@pytest.mark.unit
def test_a_driver_with_no_team_is_treated_as_midfield():
    """A driver with no known team must not inherit the championship leader.

    ``_get_team_for_driver`` returns ``{}`` for a weekend f1db has no entrant
    rows for, and ``_build_race_rows`` then passes ``""`` here. Without a guard
    the match ``tl in name.lower()`` succeeds on the *first* constructor —
    the empty string is a substring of every name — so those rows would train
    the model to associate a title-winning car with whatever the driver
    actually finished.
    """
    assert _team_position("", {"Red Bull": 1, "Ferrari": 2}) == 10


@pytest.mark.unit
def test_a_whitespace_only_team_is_treated_as_midfield():
    assert _team_position("   ", {"Red Bull": 1, "Ferrari": 2}) == 10


# ---------------------------------------------------------------------------
# _build_race_rows
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_race_with_no_results_produces_nothing(monkeypatch):
    # A future or abandoned round: there is no target to learn from.
    _install_f1db(monkeypatch, {2024: {1: _round_data(grid={"VER": 1}, race={})}})

    assert _build_race_rows(2024, 1, "Monza", _empty_history()) == ([], {})


@pytest.mark.unit
def test_one_row_is_built_per_classified_driver(monkeypatch):
    _install_f1db(
        monkeypatch,
        {2024: {1: _round_data(grid={"VER": 1, "LEC": 2}, race={"VER": 1, "LEC": 2, "NOR": 3})}},
    )

    rows, _ = _build_race_rows(2024, 1, "Monza", _empty_history())

    assert [row["driver_code"] for row in rows] == ["VER", "LEC", "NOR"]


@pytest.mark.unit
def test_each_row_carries_the_full_feature_vector_and_its_target(monkeypatch):
    _install_f1db(monkeypatch, {2024: {3: _round_data(grid={"VER": 1}, race={"VER": 2})}})

    rows, _ = _build_race_rows(2024, 3, "Spa", _empty_history())

    assert set(rows[0]) == {"year", "round", "location", "driver_code", *FEATURES, TARGET}
    assert rows[0]["year"] == 2024
    assert rows[0]["round"] == 3
    assert rows[0]["location"] == "Spa"
    assert rows[0][TARGET] == 2


@pytest.mark.unit
def test_a_driver_who_did_not_qualify_gets_the_grid_fallback(monkeypatch):
    # Pit-lane starts and no-shows have no grid slot; the row still has to exist.
    _install_f1db(monkeypatch, {2024: {1: _round_data(grid={}, race={"VER": 5})}})

    rows, _ = _build_race_rows(2024, 1, "Monza", _empty_history())

    assert rows[0]["grid_position"] == GRID_FALLBACK


@pytest.mark.unit
def test_a_weekend_with_a_sprint_is_flagged_and_its_results_returned(monkeypatch):
    _install_f1db(
        monkeypatch,
        {2024: {1: _round_data(grid={"VER": 1}, race={"VER": 1}, sprint={"VER": 2})}},
    )

    rows, sprint = _build_race_rows(2024, 1, "Monza", _empty_history())

    assert rows[0]["had_sprint"] == 1
    assert rows[0]["sprint_position"] == 2
    assert sprint == {"VER": 2}


@pytest.mark.unit
def test_a_weekend_without_a_sprint_is_not_flagged(monkeypatch):
    _install_f1db(monkeypatch, {2024: {1: _round_data(grid={"VER": 1}, race={"VER": 1})}})

    rows, sprint = _build_race_rows(2024, 1, "Monza", _empty_history())

    assert rows[0]["had_sprint"] == 0
    assert sprint == {}


@pytest.mark.unit
def test_accumulated_history_reaches_the_feature_row(monkeypatch):
    _install_f1db(monkeypatch, {2024: {1: _round_data(grid={"VER": 1}, race={"VER": 1})}})
    history = SeasonHistory(
        circuit_results={"VER": [2, 4]},
        season_results_so_far={"VER": [1, 3]},
        circuit_grid_deltas={"VER": [1.0, 3.0]},
        season_sprints_so_far={"VER": [2]},
    )

    rows, _ = _build_race_rows(2024, 1, "Monza", history)

    assert rows[0]["circuit_avg"] == 3.0
    assert rows[0]["recent_form_avg"] == 2.0
    assert rows[0]["grid_delta_avg"] == 2.0


@pytest.mark.unit
def test_a_driver_with_no_history_gets_every_fallback(monkeypatch):
    _install_f1db(monkeypatch, {2024: {1: _round_data(grid={"VER": 1}, race={"VER": 1})}})

    rows, _ = _build_race_rows(2024, 1, "Monza", _empty_history())

    assert rows[0]["recent_form_avg"] == RECENT_FORM_FALLBACK
    assert rows[0]["circuit_avg"] == CIRCUIT_FALLBACK
    assert rows[0]["grid_delta_avg"] == GRID_DELTA_FALLBACK
    assert rows[0]["driver_standing"] == STANDING_FALLBACK


@pytest.mark.unit
def test_a_drivers_team_standing_comes_from_the_constructor_table(monkeypatch):
    _install_f1db(
        monkeypatch,
        {2024: {1: _round_data(grid={"VER": 1}, race={"VER": 1}, teams={"VER": "Red Bull Racing"})}},
    )
    monkeypatch.setattr(
        train_module,
        "constructor_standings_after_round",
        lambda year, rnd: [{"constructor_name": "Red Bull", "position": 1}],
    )

    rows, _ = _build_race_rows(2024, 1, "Monza", _empty_history())

    assert rows[0]["team_standing"] == 1


# ---------------------------------------------------------------------------
# collect_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_season_without_a_schedule_is_skipped(monkeypatch, capsys):
    _install_f1db(monkeypatch, {2024: {1: _round_data(grid={"VER": 1}, race={"VER": 1})}})
    monkeypatch.setattr(train_module, "TRAIN_YEARS", [2023, 2024])

    df = collect_data()

    assert df["year"].unique().tolist() == [2024]
    assert "[skip] no schedule for 2023" in capsys.readouterr().out


@pytest.mark.unit
def test_a_round_with_no_results_is_reported_and_skipped(monkeypatch, capsys):
    _install_f1db(
        monkeypatch,
        {
            2024: {
                1: _round_data(grid={"VER": 1}, race={"VER": 1}),
                2: _round_data(grid={"VER": 1}, race={}),
            }
        },
    )

    df = collect_data()

    assert df["round"].tolist() == [1]
    assert "(no data)" in capsys.readouterr().out


@pytest.mark.unit
def test_every_driver_race_pair_becomes_one_row(monkeypatch, capsys):
    _install_f1db(
        monkeypatch,
        {
            2024: {
                1: _round_data(grid={"VER": 1, "LEC": 2}, race={"VER": 1, "LEC": 2}),
                2: _round_data(grid={"VER": 1, "LEC": 2}, race={"VER": 2, "LEC": 1}),
            }
        },
    )

    df = collect_data()

    assert len(df) == 4
    assert sorted(df["driver_code"].unique()) == ["LEC", "VER"]


@pytest.mark.unit
def test_season_form_builds_up_across_the_season(monkeypatch, capsys):
    # Round 2 must see round 1's result, and round 1 must see nothing.
    _install_f1db(
        monkeypatch,
        {
            2024: {
                1: _round_data(grid={"VER": 1}, race={"VER": 4}),
                2: _round_data(grid={"VER": 1}, race={"VER": 6}, location="Spa"),
            }
        },
    )

    df = collect_data().sort_values("round")

    assert df.iloc[0]["recent_form_avg"] == RECENT_FORM_FALLBACK
    assert df.iloc[1]["recent_form_avg"] == 4.0


@pytest.mark.unit
def test_a_race_never_contributes_to_its_own_features(monkeypatch, capsys):
    # The single most important property in this module: if the round-1 row's
    # form already averaged in its own finish, the model would be trained on the
    # answer it is asked to predict.
    _install_f1db(monkeypatch, {2024: {1: _round_data(grid={"VER": 1}, race={"VER": 4})}})

    df = collect_data()

    assert df.iloc[0]["recent_form_avg"] == RECENT_FORM_FALLBACK
    assert df.iloc[0]["circuit_avg"] == CIRCUIT_FALLBACK


@pytest.mark.unit
def test_season_form_resets_between_seasons(monkeypatch, capsys):
    _install_f1db(
        monkeypatch,
        {
            2023: {1: _round_data(grid={"VER": 1}, race={"VER": 4})},
            2024: {1: _round_data(grid={"VER": 1}, race={"VER": 6})},
        },
    )

    df = collect_data().sort_values("year")

    assert df.iloc[1]["year"] == 2024
    assert df.iloc[1]["recent_form_avg"] == RECENT_FORM_FALLBACK


@pytest.mark.unit
def test_circuit_history_persists_across_seasons(monkeypatch, capsys):
    # Deliberately the opposite of season form: how a driver goes at Monza is a
    # multi-year signal, and resetting it annually would discard most of it.
    _install_f1db(
        monkeypatch,
        {
            2023: {1: _round_data(grid={"VER": 1}, race={"VER": 4}, location="Monza")},
            2024: {1: _round_data(grid={"VER": 1}, race={"VER": 6}, location="Monza")},
        },
    )

    df = collect_data().sort_values("year")

    assert df.iloc[0]["circuit_avg"] == CIRCUIT_FALLBACK
    assert df.iloc[1]["circuit_avg"] == 4.0


@pytest.mark.unit
def test_circuit_history_is_kept_per_circuit(monkeypatch, capsys):
    # A strong record at Monza must not colour the row for Spa.
    _install_f1db(
        monkeypatch,
        {
            2024: {
                1: _round_data(grid={"VER": 1}, race={"VER": 2}, location="Monza"),
                2: _round_data(grid={"VER": 1}, race={"VER": 3}, location="Spa"),
            }
        },
    )

    df = collect_data().sort_values("round")

    assert df.iloc[1]["location"] == "Spa"
    assert df.iloc[1]["circuit_avg"] == CIRCUIT_FALLBACK


@pytest.mark.unit
def test_grid_deltas_accumulate_per_circuit(monkeypatch, capsys):
    # Started 1st, finished 4th → a delta of -3 recorded against Monza.
    _install_f1db(
        monkeypatch,
        {
            2023: {1: _round_data(grid={"VER": 1}, race={"VER": 4}, location="Monza")},
            2024: {1: _round_data(grid={"VER": 1}, race={"VER": 2}, location="Monza")},
        },
    )

    df = collect_data().sort_values("year")

    assert df.iloc[1]["grid_delta_avg"] == pytest.approx(1.0 - 4.0)


@pytest.mark.unit
def test_sprint_form_accumulates_across_the_season(monkeypatch, capsys):
    _install_f1db(
        monkeypatch,
        {
            2024: {
                1: _round_data(grid={"VER": 1}, race={"VER": 1}, sprint={"VER": 3}),
                2: _round_data(grid={"VER": 1}, race={"VER": 1}, sprint={"VER": 5}, location="Spa"),
            }
        },
    )

    df = collect_data().sort_values("round")

    assert df.iloc[1]["recent_sprint_avg"] == 3.0


@pytest.mark.unit
def test_a_run_that_collects_nothing_returns_an_empty_frame(monkeypatch, capsys):
    monkeypatch.setattr(train_module, "TRAIN_YEARS", [2030])
    monkeypatch.setattr(train_module, "race_schedule", lambda year: [])

    assert collect_data().empty


# ---------------------------------------------------------------------------
# _build_model
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_estimator_standardises_before_regularising():
    # Ridge penalises coefficients by magnitude, so unscaled features would be
    # regularised in proportion to their units rather than their information.
    model = _build_model()

    assert [name for name, _ in model.steps] == ["standardscaler", "ridge"]


@pytest.mark.unit
def test_the_regularisation_strength_comes_from_one_place():
    # Validation and the production fit must use an identical estimator, which
    # only holds while both go through `_build_model`.
    assert MODEL_PARAMS == {"alpha": 10.0}
    assert _build_model().steps[-1][1].alpha == 10.0


@pytest.mark.unit
def test_each_call_returns_an_independent_estimator():
    first, second = _build_model(), _build_model()

    assert first is not second
    assert first.steps[-1][1] is not second.steps[-1][1]


# ---------------------------------------------------------------------------
# _print_feature_influence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_linear_model_reports_signed_coefficients(capsys):
    df = _training_frame()
    model = _build_model()
    model.fit(df[FEATURES].values, df[TARGET].values)

    _print_feature_influence(model)
    report = capsys.readouterr().out

    assert "Standardized coefficients" in report
    for feature in FEATURES:
        assert feature in report


@pytest.mark.unit
def test_coefficients_are_ordered_by_strength_not_by_sign(capsys):
    # The reader wants the strongest signals first; sorting by raw value would
    # bury a large negative coefficient at the bottom.
    df = _training_frame()
    model = _build_model()
    model.fit(df[FEATURES].values, df[TARGET].values)

    _print_feature_influence(model)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("  ")]

    magnitudes = [abs(float(line.split()[-1])) for line in lines]
    assert magnitudes == sorted(magnitudes, reverse=True)


@pytest.mark.unit
def test_a_tree_ensemble_reports_importances_instead(capsys):
    # The module documents supporting either estimator kind; this is the branch
    # that keeps that true if the model is ever swapped back.
    _print_feature_influence(_Importances())
    report = capsys.readouterr().out

    assert "Feature importances" in report
    assert "Standardized coefficients" not in report


@pytest.mark.unit
def test_an_estimator_exposing_neither_prints_nothing(capsys):
    _print_feature_influence(_Opaque())

    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# walk_forward_validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_validation_starts_at_the_second_season():
    # The first season has nothing earlier to train on.
    results = walk_forward_validation(_training_frame(seasons=(2022, 2023, 2024)))

    assert [r["season"] for r in results] == [2023, 2024]


@pytest.mark.unit
def test_each_validated_season_reports_its_sample_count_and_error():
    results = walk_forward_validation(_training_frame(seasons=(2022, 2023), n_drivers=6))

    assert set(results[0]) == {"season", "n", "mae"}
    assert results[0]["n"] == 12  # 2 rounds x 6 drivers
    assert results[0]["mae"] >= 0.0


@pytest.mark.unit
def test_a_single_season_cannot_be_validated():
    assert walk_forward_validation(_training_frame(seasons=(2024,))) == []


@pytest.mark.unit
def test_a_season_that_cannot_be_split_is_skipped_rather_than_fit():
    # A row with an unusable year survives the feature-level dropna (only the
    # feature columns and the target are checked), so it reaches the split as a
    # season with neither a training nor a validation side. Fitting an empty
    # matrix would raise and take the whole training run down.
    df = _training_frame(seasons=(2022, 2023))
    orphan = df.iloc[[0]].copy()
    orphan["year"] = float("nan")
    df = pd.concat([df, orphan], ignore_index=True)

    results = walk_forward_validation(df)

    assert [r["season"] for r in results] == [2023]


# ---------------------------------------------------------------------------
# train
# ---------------------------------------------------------------------------


@pytest.fixture
def model_path(tmp_path, monkeypatch):
    """Point the artifact at tmp_path so a test can never overwrite the real model."""
    path = tmp_path / "models" / "race_predictor.joblib"
    monkeypatch.setattr(train_module, "MODEL_PATH", path)
    return path


def _bundle(path):
    import joblib

    return joblib.load(path)


@pytest.mark.integration
def test_training_writes_the_model_artifact(model_path, capsys):
    train(_training_frame())

    assert model_path.exists()
    assert "Model saved to" in capsys.readouterr().out


@pytest.mark.integration
def test_the_artifact_carries_the_feature_order_it_was_fit_on(model_path, capsys):
    # Inference reads this list rather than importing FEATURES, so an artifact
    # trained on an older order still serves its own columns.
    train(_training_frame())

    assert _bundle(model_path)["features"] == FEATURES


@pytest.mark.integration
def test_the_artifact_carries_the_metrics_that_justify_it(model_path, capsys):
    # Metrics travel with the model so a promotion or rollback can be argued
    # from the artifact alone.
    train(_training_frame())

    metrics = _bundle(model_path)["metrics"]

    assert set(metrics) == {
        "walk_forward_mae",
        "walk_forward_by_season",
        "holdout_mae",
        "holdout_ranking",
        "trained_seasons",
        "n_samples",
    }
    assert metrics["trained_seasons"] == [2022, 2023, 2024]
    assert metrics["n_samples"] == 36


@pytest.mark.integration
def test_the_saved_model_can_predict_the_features_it_was_given(model_path, capsys):
    df = _training_frame()
    train(df)

    bundle = _bundle(model_path)
    predictions = bundle["model"].predict(df[bundle["features"]].values)

    assert len(predictions) == len(df)


@pytest.mark.integration
def test_rows_with_a_missing_feature_are_dropped_before_fitting(model_path, capsys):
    df = _training_frame()
    df.loc[0, "circuit_avg"] = None

    train(df)

    assert _bundle(model_path)["metrics"]["n_samples"] == len(df) - 1


@pytest.mark.integration
def test_the_production_model_is_fit_on_every_season(model_path, capsys):
    # The holdout fit exists to measure; the shipped fit exists to serve, and
    # restricting it to the training split would throw away the latest season.
    train(_training_frame(seasons=(2022, 2023, 2024)))

    assert _bundle(model_path)["metrics"]["trained_seasons"] == [2022, 2023, 2024]


@pytest.mark.integration
def test_the_headline_holdout_number_comes_from_the_most_recent_season(model_path, capsys):
    train(_training_frame(seasons=(2022, 2023, 2024)))
    report = capsys.readouterr().out

    assert "Held-out 2024 season MAE" in report
    assert "tested on 2024" in report


@pytest.mark.integration
def test_the_holdout_is_compared_against_the_grid_baseline(model_path, capsys):
    # An MAE on its own does not say whether the model beats predicting the grid.
    train(_training_frame())
    report = capsys.readouterr().out

    assert "ranking vs grid-order baseline" in report
    assert "Spearman" in report
    assert _bundle(model_path)["metrics"]["holdout_ranking"]["_meta"]["holdout_seasons"] == [2024]


@pytest.mark.integration
def test_a_single_season_still_trains_but_reports_no_holdout(model_path, capsys):
    # Nothing to hold out, and the run must not crash on the attempt.
    train(_training_frame(seasons=(2024,)))

    metrics = _bundle(model_path)["metrics"]
    assert np.isnan(metrics["holdout_mae"])
    assert metrics["holdout_ranking"] == {}
    assert "Held-out" not in capsys.readouterr().out


@pytest.mark.integration
def test_a_single_season_reports_no_walk_forward_mean(model_path, capsys):
    train(_training_frame(seasons=(2024,)))

    assert np.isnan(_bundle(model_path)["metrics"]["walk_forward_mae"])
    assert "mean walk-forward MAE: nan" in capsys.readouterr().out


@pytest.mark.integration
def test_the_walk_forward_mean_averages_the_validated_seasons(model_path, capsys):
    train(_training_frame(seasons=(2022, 2023, 2024)))

    metrics = _bundle(model_path)["metrics"]
    by_season = metrics["walk_forward_by_season"]

    assert [r["season"] for r in by_season] == [2023, 2024]
    assert metrics["walk_forward_mae"] == pytest.approx(sum(r["mae"] for r in by_season) / 2)


@pytest.mark.integration
def test_sprint_rows_are_counted_in_the_run_summary(model_path, capsys):
    df = _training_frame()
    df.loc[:5, "had_sprint"] = 1.0

    train(df)

    assert "6 driver-rows are from sprint weekends" in capsys.readouterr().out


@pytest.mark.integration
def test_the_artifact_directory_is_created_when_absent(model_path, capsys):
    assert not model_path.parent.exists()

    train(_training_frame())

    assert model_path.exists()
