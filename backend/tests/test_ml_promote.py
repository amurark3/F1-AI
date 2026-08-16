"""Tests for app.ml.promote — the challenger/champion gate.

This module is the only thing standing between a scheduled retrain and the
committed model artifact. Two failure directions matter, and they are not
symmetric:

* **Promoting a worse model** silently degrades every prediction the app serves
  until someone notices. The gate is a single ``>=`` comparison against the
  grid-order baseline, so the tests pin the comparison itself — including the
  tie — rather than trusting it by inspection.
* **Rejecting is not a failure.** The workflow must exit 0 and leave the
  incumbent in place, because a noisy season that fails the gate is the system
  working. Only a genuinely empty dataset is an error exit.

The ``promoted`` / ``f1db_version`` lines written to ``$GITHUB_OUTPUT`` are the
workflow's sole signal about whether to commit a new model, so they are asserted
through the real ``_set_github_output`` against a temporary file rather than
stubbed.

f1db refresh, data collection, the backtest and training are all mocked at the
boundary; nothing here touches the network, the dataset or the model artifact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from app.ml import promote as promote_module
from app.ml.features import FEATURES, TARGET

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dataset(seasons: list[int], rows_per_season: int = 2) -> pd.DataFrame:
    """A collected dataset with every feature present, so `dropna` keeps it all."""
    records = []
    for year in seasons:
        for offset in range(rows_per_season):
            row = {name: float(offset + 1) for name in FEATURES}
            row[TARGET] = float(offset + 1)
            row["year"] = year
            records.append(row)
    return pd.DataFrame(records)


def _metrics(spearman: float) -> dict[str, float]:
    return {
        "spearman": spearman,
        "podium_hit_rate": 0.5,
        "winner_accuracy": 0.25,
        "points_accuracy": 0.6,
        "mae": 3.1,
    }


class _Harness:
    """Records what the gate did to each mocked boundary."""

    def __init__(self) -> None:
        self.refreshed_urls: list[str] = []
        self.trained_on: list[pd.DataFrame] = []
        self.backtest_calls: list[dict] = []


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    dataset: pd.DataFrame,
    model_spearman: float = 0.9,
    grid_spearman: float = 0.5,
    module=promote_module,
) -> tuple[_Harness, Path]:
    """Stub every boundary the gate reaches and point GITHUB_OUTPUT at a file."""
    harness = _Harness()

    monkeypatch.setattr(module, "latest_release_version", lambda: "2026.11.0")
    monkeypatch.setattr(module, "sqlite_url_for", lambda version: f"https://f1db.test/{version}.db")

    def _refresh(url: str) -> None:
        harness.refreshed_urls.append(url)

    monkeypatch.setattr(module, "refresh_f1db", _refresh)
    monkeypatch.setattr(module, "collect_data", lambda: dataset)

    def _backtest(df, build_model, holdout_seasons):
        harness.backtest_calls.append({"df": df, "build_model": build_model, "holdout_seasons": holdout_seasons})
        return {
            "model": _metrics(model_spearman),
            "grid_order": _metrics(grid_spearman),
            "_meta": {"n_races": 42},
        }

    def _train(df: pd.DataFrame) -> None:
        harness.trained_on.append(df)

    monkeypatch.setattr(module, "backtest", _backtest)
    monkeypatch.setattr(module, "train", _train)

    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    return harness, output


def _outputs(path: Path) -> dict[str, str]:
    """Parse the `key=value` lines the gate wrote for the workflow."""
    if not path.exists():
        return {}
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if line)


# ---------------------------------------------------------------------------
# _set_github_output
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_output_is_written_as_a_key_equals_value_line(tmp_path, monkeypatch):
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    promote_module._set_github_output("promoted", "true")

    assert output.read_text() == "promoted=true\n"


@pytest.mark.unit
def test_outputs_accumulate_rather_than_overwrite(tmp_path, monkeypatch):
    # The gate writes `promoted` and `f1db_version` in separate calls; opening
    # in truncate mode would leave the workflow with only the last one.
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    promote_module._set_github_output("promoted", "true")
    promote_module._set_github_output("f1db_version", "2026.11.0")

    assert _outputs(output) == {"promoted": "true", "f1db_version": "2026.11.0"}


@pytest.mark.unit
def test_writing_an_output_outside_github_actions_is_a_silent_no_op(monkeypatch):
    # `python -m app.ml.promote` run by hand has no GITHUB_OUTPUT, and that must
    # not be an error.
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    promote_module._set_github_output("promoted", "true")


# ---------------------------------------------------------------------------
# Dataset preparation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_gate_refreshes_f1db_to_the_latest_release_first(tmp_path, monkeypatch, capsys):
    # Gating a challenger against a stale dataset would score it on races it was
    # already trained on.
    harness, _ = _install(monkeypatch, tmp_path, dataset=_dataset([2023, 2024, 2025, 2026]))

    promote_module.main()

    assert harness.refreshed_urls == ["https://f1db.test/2026.11.0.db"]


@pytest.mark.unit
def test_an_empty_dataset_aborts_without_touching_the_model(tmp_path, monkeypatch, capsys):
    harness, output = _install(monkeypatch, tmp_path, dataset=pd.DataFrame(columns=[*FEATURES, TARGET, "year"]))

    with pytest.raises(SystemExit) as exit_info:
        promote_module.main()

    assert exit_info.value.code == 1
    assert harness.trained_on == [], "a model was trained on nothing"
    assert harness.backtest_calls == [], "an empty dataset was sent to the gate"
    assert _outputs(output) == {"promoted": "false"}


@pytest.mark.unit
def test_rows_with_an_incomplete_feature_vector_never_reach_the_gate(tmp_path, monkeypatch, capsys):
    # A driver whose standings were unavailable produces a NaN row; scoring it
    # would measure the gaps in the dataset rather than the challenger.
    dataset = _dataset([2024, 2025])
    dataset.loc[0, FEATURES[0]] = None

    harness, _ = _install(monkeypatch, tmp_path, dataset=dataset)
    promote_module.main()

    gated = harness.backtest_calls[0]["df"]
    assert len(gated) == len(dataset) - 1
    assert not gated[[*FEATURES, TARGET]].isna().to_numpy().any()


@pytest.mark.unit
def test_the_holdout_is_the_most_recent_seasons(tmp_path, monkeypatch, capsys):
    harness, _ = _install(monkeypatch, tmp_path, dataset=_dataset([2019, 2020, 2021, 2022, 2023, 2024]))

    promote_module.main()

    assert harness.backtest_calls[0]["holdout_seasons"] == [2021, 2022, 2023, 2024]


@pytest.mark.unit
def test_a_dataset_shorter_than_the_holdout_span_gates_on_every_season(tmp_path, monkeypatch, capsys):
    harness, _ = _install(monkeypatch, tmp_path, dataset=_dataset([2025, 2026]))

    promote_module.main()

    assert harness.backtest_calls[0]["holdout_seasons"] == [2025, 2026]


@pytest.mark.unit
def test_the_holdout_span_is_configurable(tmp_path, monkeypatch, reload_module, capsys):
    # Read at import time, so the reload is what makes the override visible.
    monkeypatch.setenv("PROMOTE_HOLDOUT_SEASONS", "2")
    reloaded = reload_module("app.ml.promote")

    harness, _ = _install(monkeypatch, tmp_path, dataset=_dataset([2021, 2022, 2023, 2024]), module=reloaded)
    reloaded.main()

    assert reloaded.GATE_HOLDOUT_COUNT == 2
    assert harness.backtest_calls[0]["holdout_seasons"] == [2023, 2024]


@pytest.mark.unit
def test_the_gate_backtests_the_same_estimator_the_trainer_builds(tmp_path, monkeypatch, capsys):
    # Gating one estimator and shipping another would make the decision
    # meaningless, so the builder handed to `backtest` must be train's own.
    harness, _ = _install(monkeypatch, tmp_path, dataset=_dataset([2024, 2025]))

    promote_module.main()

    assert harness.backtest_calls[0]["build_model"] is promote_module._build_model


# ---------------------------------------------------------------------------
# The promotion decision
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_challenger_that_beats_the_baseline_is_promoted(tmp_path, monkeypatch, capsys):
    harness, output = _install(
        monkeypatch, tmp_path, dataset=_dataset([2024, 2025]), model_spearman=0.81, grid_spearman=0.62
    )

    promote_module.main()

    assert len(harness.trained_on) == 1, "a promoted challenger was never refit"
    assert _outputs(output) == {"promoted": "true", "f1db_version": "2026.11.0"}


@pytest.mark.unit
def test_a_promoted_challenger_is_refit_on_every_season_not_just_the_holdout(tmp_path, monkeypatch, capsys):
    # The gate scores on recent seasons, but the shipped model is fit on all of
    # them — refitting on the holdout alone would throw away most of the data.
    dataset = _dataset([2019, 2020, 2021, 2022, 2023, 2024])
    harness, _ = _install(monkeypatch, tmp_path, dataset=dataset, model_spearman=0.9, grid_spearman=0.1)

    promote_module.main()

    assert sorted(harness.trained_on[0]["year"].unique()) == [2019, 2020, 2021, 2022, 2023, 2024]


@pytest.mark.unit
def test_a_challenger_that_loses_to_the_baseline_is_rejected(tmp_path, monkeypatch, capsys):
    harness, output = _install(
        monkeypatch, tmp_path, dataset=_dataset([2024, 2025]), model_spearman=0.40, grid_spearman=0.62
    )

    promote_module.main()

    assert harness.trained_on == [], "a rejected challenger overwrote the incumbent"
    assert _outputs(output) == {"promoted": "false"}
    assert "f1db_version" not in _outputs(output)


@pytest.mark.unit
def test_a_rejection_exits_zero_because_it_is_not_a_failure(tmp_path, monkeypatch, capsys):
    # A season that fails the gate is the gate working. Exiting non-zero would
    # turn every honest rejection into a red scheduled workflow.
    _install(monkeypatch, tmp_path, dataset=_dataset([2024, 2025]), model_spearman=0.1, grid_spearman=0.9)

    promote_module.main()  # must simply return


@pytest.mark.unit
def test_a_tie_promotes_the_challenger(tmp_path, monkeypatch, capsys):
    # The comparison is `>=`: an equal challenger is the fresher model, trained
    # on the newer races, so it wins the tie.
    harness, output = _install(
        monkeypatch, tmp_path, dataset=_dataset([2024, 2025]), model_spearman=0.62, grid_spearman=0.62
    )

    promote_module.main()

    assert len(harness.trained_on) == 1
    assert _outputs(output)["promoted"] == "true"


@pytest.mark.unit
def test_the_decision_is_made_on_spearman(tmp_path, monkeypatch, capsys):
    # Ranking quality is the product — the drivers' finishing *order*. A
    # challenger with better absolute error but worse ordering is not an
    # improvement, so the losing metrics must not rescue it.
    assert promote_module.PRIMARY_METRIC == "spearman"

    harness, output = _install(
        monkeypatch, tmp_path, dataset=_dataset([2024, 2025]), model_spearman=0.30, grid_spearman=0.55
    )
    monkeypatch.setattr(
        promote_module,
        "backtest",
        lambda df, build_model, holdout_seasons: {
            "model": {**_metrics(0.30), "mae": 0.1},  # far better absolute error
            "grid_order": {**_metrics(0.55), "mae": 9.9},
            "_meta": {"n_races": 42},
        },
    )

    promote_module.main()

    assert harness.trained_on == []
    assert _outputs(output)["promoted"] == "false"


@pytest.mark.unit
def test_a_backtest_missing_the_primary_metric_scores_zero_for_both_sides(tmp_path, monkeypatch, capsys):
    # Both sides default to 0.0, so the tie rule promotes. Pinned because it is
    # the one path where a promotion happens without evidence behind it.
    harness, output = _install(monkeypatch, tmp_path, dataset=_dataset([2024, 2025]))
    monkeypatch.setattr(
        promote_module,
        "backtest",
        lambda df, build_model, holdout_seasons: {
            "model": {"mae": 3.0},
            "grid_order": {"mae": 4.0},
            "_meta": {"n_races": 7},
        },
    )

    promote_module.main()

    assert _outputs(output)["promoted"] == "true"
    assert len(harness.trained_on) == 1


# ---------------------------------------------------------------------------
# The printed report
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_report_shows_every_gate_metric_for_both_sides(tmp_path, monkeypatch, capsys):
    # The workflow log is the only record of why a challenger was kept or
    # dropped; a decision line with no numbers behind it cannot be reviewed.
    _install(monkeypatch, tmp_path, dataset=_dataset([2024, 2025]), model_spearman=0.81, grid_spearman=0.62)

    promote_module.main()
    report = capsys.readouterr().out

    for metric in ("spearman", "podium_hit_rate", "winner_accuracy", "points_accuracy", "mae"):
        assert metric in report
    assert "42 races" in report
    assert "PROMOTE" in report


@pytest.mark.unit
def test_the_report_names_the_rejection_explicitly(tmp_path, monkeypatch, capsys):
    _install(monkeypatch, tmp_path, dataset=_dataset([2024, 2025]), model_spearman=0.10, grid_spearman=0.62)

    promote_module.main()
    report = capsys.readouterr().out

    assert "REJECT" in report
    assert "incumbent model kept" in report


@pytest.mark.unit
def test_an_empty_dataset_says_the_model_was_left_alone(tmp_path, monkeypatch, capsys):
    _install(monkeypatch, tmp_path, dataset=pd.DataFrame(columns=[*FEATURES, TARGET, "year"]))

    with pytest.raises(SystemExit):
        promote_module.main()

    assert "aborting without touching the model" in capsys.readouterr().out
