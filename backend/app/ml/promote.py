"""Challenger/champion promotion gate for the race-finish model.

Run by the scheduled retraining workflow after each race weekend. It:

  1. refreshes the local f1db dataset to the latest release (new race results),
  2. rebuilds the training dataset (offline, from f1db),
  3. trains a challenger model and backtests it against the grid-order baseline
     over the most recent seasons,
  4. promotes the challenger (overwrites the committed model) ONLY if it beats
     the grid baseline on the primary ranking metric.

Rejecting a challenger is not a failure — the script exits 0 and simply leaves
the incumbent model in place. It writes ``promoted=true|false`` to
``$GITHUB_OUTPUT`` so the workflow knows whether to commit a new model.

Usage:
    cd backend
    python -m app.ml.promote
"""

from __future__ import annotations

import os
import sys

from app.data.f1db_source import sync_to_latest
from app.ml.evaluate import backtest
from app.ml.features import FEATURES, TARGET
from app.ml.train import _build_model, collect_data, train

# Gate over several recent seasons rather than one, so a single noisy 10-race
# season can't flip the decision.
GATE_HOLDOUT_COUNT = int(os.getenv("PROMOTE_HOLDOUT_SEASONS", "4"))
PRIMARY_METRIC = "spearman"


def _set_github_output(key: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as handle:
            handle.write(f"{key}={value}\n")


def main() -> None:
    # Training reads whatever the shared source says is current. This job used to
    # own the refresh, which quietly made live data freshness a side effect of
    # model retraining — the runner got the new release, production never did.
    outcome = sync_to_latest(force=True)
    version = outcome.version
    print(f"f1db dataset at {version} — {outcome.reason}")

    df = collect_data().dropna(subset=FEATURES + [TARGET])
    if df.empty:
        print("No data collected — aborting without touching the model.")
        _set_github_output("promoted", "false")
        sys.exit(1)

    seasons = sorted(int(s) for s in df["year"].unique())
    holdout = seasons[-GATE_HOLDOUT_COUNT:]
    results = backtest(df, _build_model, holdout_seasons=holdout)
    model_m, grid_m = results["model"], results["grid_order"]

    model_score = model_m.get(PRIMARY_METRIC, 0.0)
    grid_score = grid_m.get(PRIMARY_METRIC, 0.0)
    promote = model_score >= grid_score

    print(f"\nGate backtest over seasons {holdout} ({results['_meta']['n_races']} races):")
    for metric in ("spearman", "podium_hit_rate", "winner_accuracy", "points_accuracy", "mae"):
        print(f"  {metric:<18} model {model_m.get(metric, float('nan')):.3f}  vs grid {grid_m.get(metric, float('nan')):.3f}")
    print(
        f"\nDecision: challenger {PRIMARY_METRIC} {model_score:.3f} "
        f"{'>=' if promote else '<'} grid {grid_score:.3f} → "
        f"{'PROMOTE' if promote else 'REJECT'}"
    )

    if promote:
        train(df)  # fits on all seasons and saves the model with fresh metrics
        _set_github_output("promoted", "true")
        _set_github_output("f1db_version", version)
        print("\nChallenger promoted — model updated.")
    else:
        _set_github_output("promoted", "false")
        print("\nChallenger rejected — incumbent model kept.")


if __name__ == "__main__":
    main()
