"""Backtest harness for the race-finish model.

The product output is a *finishing order*, so positional MAE alone doesn't tell
us whether the order is any good. This module scores predicted orders with
ranking-appropriate metrics and — critically — reports the same metrics for
trivial baselines (grid order, championship order, recent form). If the model
can't beat "just predict the grid order", the extra machinery isn't earning its
place.

Usage:
    cd backend
    python -m app.ml.evaluate            # uses cached dataset if present
    python -m app.ml.evaluate --refresh  # re-collect data from FastF1/Ergast
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from app.config import (
    CIRCUIT_HISTORY_WEIGHT,
    GRID_TO_FINISH_WEIGHT,
    ML_PREDICTION_BLEND_WEIGHT,
    QUALIFYING_WEIGHT,
    RECENT_FORM_WEIGHT,
    TEAM_STRENGTH_WEIGHT,
)
from app.ml.features import FEATURES, TARGET

# Cached copy of the collected training dataset so the benchmark can re-run
# instantly without hitting the network. Written by collect + evaluate runs.
DATASET_PATH = Path(__file__).parent.parent.parent / "data" / "training_dataset.csv"

PODIUM_SIZE = 3
POINTS_SIZE = 10

# The columns used as "lower value = predicted to finish better" for each
# baseline. All are already present in the collected dataset.
BASELINES = {
    "grid_order": "grid_position",
    "championship_order": "driver_standing",
    "recent_form_order": "recent_form_avg",
}


def _ranking_metrics(pred_scores: np.ndarray, actual_positions: np.ndarray) -> dict[str, float]:
    """Score one race. ``pred_scores`` lower = predicted better; actuals are 1..N."""
    n = len(actual_positions)
    if n < 2:
        return {}

    # Convert predicted scores into predicted ranks (1 = predicted winner).
    order = np.argsort(pred_scores, kind="stable")
    pred_rank = np.empty(n, dtype=float)
    pred_rank[order] = np.arange(1, n + 1)

    actual_order = np.argsort(actual_positions, kind="stable")

    spearman = spearmanr(pred_rank, actual_positions).correlation
    mae = float(np.mean(np.abs(pred_rank - actual_positions)))

    pred_top3, actual_top3 = set(order[:PODIUM_SIZE]), set(actual_order[:PODIUM_SIZE])
    podium_hit = len(pred_top3 & actual_top3) / PODIUM_SIZE

    points_k = min(POINTS_SIZE, n)
    pred_topk, actual_topk = set(order[:points_k]), set(actual_order[:points_k])
    points_acc = len(pred_topk & actual_topk) / points_k

    winner = 1.0 if order[0] == actual_order[0] else 0.0

    return {
        "spearman": float(spearman) if spearman == spearman else 0.0,  # NaN guard
        "mae": mae,
        "podium_hit_rate": podium_hit,
        "points_accuracy": points_acc,
        "winner_accuracy": winner,
    }


def _aggregate(per_race: list[dict[str, float]]) -> dict[str, float]:
    """Average each metric across races."""
    if not per_race:
        return {}
    keys = per_race[0].keys()
    return {k: float(np.mean([r[k] for r in per_race])) for k in keys}


def _heuristic_scores(race: pd.DataFrame) -> np.ndarray:
    """Reconstruct the production heuristic weighted score for one race.

    Mirrors the active-weight logic in ``app.data.predictions``: sprint weekends
    add the 0.30 sprint weight and drop qualifying to 0.20; weights are then
    normalized to sum to 1.0. Every signal is present in the collected dataset
    (fallbacks already applied at collection time), so the full weight set always
    applies. Lower score = predicted to finish better — same sign convention as
    the model, so the two can be blended directly.
    """
    weights: dict[str, float] = {}
    if bool(race["had_sprint"].iloc[0]):
        weights["sprint"] = 0.30
        weights["qualifying"] = 0.20
    else:
        weights["qualifying"] = QUALIFYING_WEIGHT
    weights["recent_form"] = RECENT_FORM_WEIGHT
    weights["circuit_history"] = CIRCUIT_HISTORY_WEIGHT
    weights["team_strength"] = TEAM_STRENGTH_WEIGHT
    weights["grid_delta"] = GRID_TO_FINISH_WEIGHT

    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    score = np.zeros(len(race), dtype=float)
    if "sprint" in weights:
        score += weights["sprint"] * race["sprint_position"].to_numpy()
    score += weights["qualifying"] * race["grid_position"].to_numpy()
    score += weights["recent_form"] * race["recent_form_avg"].to_numpy()
    score += weights["circuit_history"] * race["circuit_avg"].to_numpy()
    score += weights["team_strength"] * race["team_standing"].to_numpy()
    score -= weights["grid_delta"] * race["grid_delta_avg"].to_numpy()
    return score


def backtest(
    df: pd.DataFrame,
    model_factory: Callable[[], object],
    holdout_seasons: list[int] | None = None,
    features: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Season-forward backtest of the model against the baselines.

    For each held-out season, the model is trained only on strictly earlier
    seasons, then every race in that season is scored. Metrics are averaged
    across all held-out races. Returns ``{predictor_name: metrics}``.
    """
    feature_cols = features or FEATURES
    df = df.dropna(subset=feature_cols + [TARGET]).copy()
    seasons = sorted(df["year"].unique())
    if holdout_seasons is None:
        # Default: hold out the most recent season only.
        holdout_seasons = seasons[-1:]

    model_races: list[dict] = []
    heuristic_races: list[dict] = []
    ensemble_races: list[dict] = []
    baseline_races: dict[str, list[dict]] = {name: [] for name in BASELINES}

    for season in holdout_seasons:
        train_df = df[df["year"] < season]
        test_df = df[df["year"] == season]
        if train_df.empty or test_df.empty:
            continue

        model = model_factory()
        model.fit(train_df[feature_cols].values, train_df[TARGET].values)

        for (_, _), race in test_df.groupby(["year", "round"]):
            actual = race[TARGET].to_numpy()
            if len(actual) < 2:
                continue

            preds = model.predict(race[feature_cols].values)
            heuristic = _heuristic_scores(race)
            ensemble = (
                ML_PREDICTION_BLEND_WEIGHT * preds
                + (1 - ML_PREDICTION_BLEND_WEIGHT) * heuristic
            )

            # Score the production blend, plus each layer alone, so the harness
            # shows whether the ensemble actually beats pure ML on the same races.
            for bucket, scores in (
                (model_races, preds),
                (heuristic_races, heuristic),
                (ensemble_races, ensemble),
            ):
                m = _ranking_metrics(scores, actual)
                if m:
                    bucket.append(m)

            for name, column in BASELINES.items():
                bm = _ranking_metrics(race[column].to_numpy(), actual)
                if bm:
                    baseline_races[name].append(bm)

    results = {
        "ensemble": _aggregate(ensemble_races),
        "model": _aggregate(model_races),
        "heuristic": _aggregate(heuristic_races),
    }
    for name, races in baseline_races.items():
        results[name] = _aggregate(races)
    results["_meta"] = {
        "holdout_seasons": holdout_seasons,
        "n_races": len(model_races),
        "blend_weight": ML_PREDICTION_BLEND_WEIGHT,
    }
    return results


def _print_report(results: dict[str, dict[str, float]]) -> None:
    meta = results.get("_meta", {})
    print(
        f"\nBacktest over {meta.get('n_races', 0)} races "
        f"(held-out seasons: {meta.get('holdout_seasons')})"
        f"\nensemble = {meta.get('blend_weight')}*model + "
        f"{round(1 - meta.get('blend_weight', 0), 2)}*heuristic\n"
    )
    metric_cols = ["spearman", "podium_hit_rate", "winner_accuracy", "points_accuracy", "mae"]
    header = "predictor".ljust(20) + "".join(m.replace("_", " ")[:14].rjust(16) for m in metric_cols)
    print(header)
    print("-" * len(header))
    for name in ["ensemble", "model", "heuristic", *BASELINES]:
        row = results.get(name, {})
        line = name.ljust(20) + "".join(f"{row.get(m, float('nan')):16.3f}" for m in metric_cols)
        print(line)
    print(
        "\nHigher is better for spearman / podium / winner / points; lower is better for MAE."
        "\nThe model earns its place only if it beats grid_order on the ranking metrics;"
        "\nthe ensemble earns its blend only if it beats 'model' (pure ML)."
    )


def load_or_collect_dataset(refresh: bool = False) -> pd.DataFrame:
    """Load the cached dataset, or collect it from FastF1/Ergast and cache it."""
    if not refresh and DATASET_PATH.exists():
        print(f"Loading cached dataset from {DATASET_PATH}")
        return pd.read_csv(DATASET_PATH)

    # Deferred import keeps this module free of a hard dependency on the (heavy)
    # data-collection path and avoids a circular import with app.ml.train.
    from app.ml.train import collect_data

    print("Collecting dataset from FastF1/Ergast (this may take several minutes)...")
    df = collect_data()
    if not df.empty:
        DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(DATASET_PATH, index=False)
        print(f"Cached dataset to {DATASET_PATH}")
    return df


def main() -> None:
    refresh = "--refresh" in sys.argv
    df = load_or_collect_dataset(refresh=refresh)
    if df.empty:
        print("No data available — run with --refresh once you have network access.")
        sys.exit(1)

    from app.ml.train import _build_model

    # Hold out every season with at least three prior seasons to train on, so the
    # headline numbers come from a robust multi-season sample rather than a single
    # noisy ~10-race season. Falls back to the most recent season if data is thin.
    seasons = sorted(int(s) for s in df["year"].unique())
    holdout = seasons[3:] or seasons[-1:]
    results = backtest(df, _build_model, holdout_seasons=holdout)
    _print_report(results)


if __name__ == "__main__":
    main()
