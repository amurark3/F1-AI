"""
ML Training Pipeline
====================
Trains the race-finish model (a Ridge regression over standardized features,
chosen via the app.ml.evaluate backtest) on 2018–2024 historical F1 race data
and saves it to ``models/race_predictor.joblib``.

Features per driver-race row:
  - grid_position       : qualifying grid position (1–20)
  - sprint_position     : sprint race finish (1–20); 0 = no sprint that weekend
  - had_sprint          : 1 if a sprint race was held, 0 otherwise
  - recent_form_avg     : average finish over driver's last 5 races that season
  - recent_sprint_avg   : average sprint finish over driver's last 3 sprints (0 if none)
  - circuit_avg         : driver's average finish at this circuit (last 3 editions)
  - team_standing       : constructor championship position at race time
  - driver_standing     : driver championship position at race time
  - grid_delta_avg      : historical avg positions gained/lost at this circuit

Target:
  - finish_position     : actual race finishing position (1–20)

Usage:
    cd backend
    python -m app.ml.train
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd
from app.data.f1db_results import (
    driver_teams,
    qualifying_positions,
    race_results,
    race_schedule,
    sprint_positions,
)
from app.data.f1db_standings import (
    constructor_standings_after_round,
    driver_standings_after_round,
)
from app.ml.features import FEATURES, TARGET, build_feature_row

# Suppress pandas noise during bulk data assembly
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRAIN_YEARS = list(range(2018, 2027))   # 2018–2026 (2026 in progress; partial season handled)
MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "race_predictor.joblib"


# ---------------------------------------------------------------------------
# Data collection helpers
# ---------------------------------------------------------------------------

def _get_race_schedule(year: int) -> pd.DataFrame:
    """Return the race schedule for a season as a DataFrame (from f1db)."""
    rows = race_schedule(year)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {"RoundNumber": r["round"], "EventName": r["name"], "Location": r["location"]}
            for r in rows
        ]
    )


def _get_qualifying_positions(year: int, round_num: int) -> dict[str, int]:
    """Return {driver_code: qualifying_position} for a race weekend (from f1db)."""
    return qualifying_positions(year, round_num)


def _get_race_results(year: int, round_num: int) -> dict[str, int]:
    """Return {driver_code: finish_position} for a completed race (from f1db)."""
    return race_results(year, round_num)


def _get_sprint_positions(year: int, round_num: int) -> dict[str, int]:
    """Return {driver_code: sprint_finish_position}, or {} if no sprint (from f1db)."""
    return sprint_positions(year, round_num)


def _get_driver_standings(year: int, round_num: int) -> dict[str, int]:
    """Return {driver_code: championship_position} going into ``round_num``.

    Standings *before* a race are those recorded after the previous round.
    Sourced from the local f1db dataset — no live API, no rate limits.
    """
    lookup_round = max(1, round_num - 1)
    return driver_standings_after_round(year, lookup_round)


def _get_constructor_standings(year: int, round_num: int) -> dict[str, int]:
    """Return {constructor_name: championship_position} going into ``round_num``.

    Standings *before* a race are those recorded after the previous round.
    Sourced from the local f1db dataset — no live API, no rate limits.
    """
    lookup_round = max(1, round_num - 1)
    return {
        row["constructor_name"]: row["position"]
        for row in constructor_standings_after_round(year, lookup_round)
    }


def _get_team_for_driver(year: int, round_num: int) -> dict[str, str]:
    """Return {driver_code: team_name} for a race weekend (from f1db)."""
    return driver_teams(year, round_num)


def _team_position(team_name: str, constructor_standings: dict[str, int]) -> int:
    """Fuzzy-match team name against constructor standings."""
    tl = team_name.lower()
    for name, pos in constructor_standings.items():
        if name.lower() in tl or tl in name.lower():
            return pos
    return 10  # midfield fallback


# ---------------------------------------------------------------------------
# Feature engineering per race
# ---------------------------------------------------------------------------

def _build_race_rows(
    year: int,
    round_num: int,
    location: str,
    # Accumulated history passed in from the outer loop
    circuit_results: dict[str, list[int]],        # driver -> [finish positions at this circuit]
    season_results_so_far: dict[str, list[int]],  # driver -> [race finishes this season so far]
    circuit_grid_deltas: dict[str, list[float]],  # driver -> [grid-finish deltas at this circuit]
    season_sprints_so_far: dict[str, list[int]],  # driver -> [sprint finishes this season so far]
) -> tuple[list[dict], dict[str, int]]:
    """Build one feature row per driver for a single race.

    Returns (rows, sprint_results) so the caller can update sprint accumulators.
    """
    grid = _get_qualifying_positions(year, round_num)
    race = _get_race_results(year, round_num)
    sprint = _get_sprint_positions(year, round_num)
    driver_standings = _get_driver_standings(year, round_num)
    constructor_standings = _get_constructor_standings(year, round_num)
    driver_teams = _get_team_for_driver(year, round_num)

    if not race:
        return [], {}

    rows = []
    for driver_code, finish_pos in race.items():
        team_name = driver_teams.get(driver_code, "")
        features = build_feature_row(
            grid_position=grid.get(driver_code),
            sprint_position=sprint.get(driver_code),
            had_sprint=bool(sprint),
            recent_finishes=season_results_so_far.get(driver_code, []),
            recent_sprint_finishes=season_sprints_so_far.get(driver_code, []),
            circuit_finishes=circuit_results.get(driver_code, []),
            circuit_grid_deltas=circuit_grid_deltas.get(driver_code, []),
            team_standing=_team_position(team_name, constructor_standings),
            driver_standing=driver_standings.get(driver_code, 10),
        )
        rows.append({
            "year": year,
            "round": round_num,
            "location": location,
            "driver_code": driver_code,
            **features,
            "finish_position": finish_pos,
        })

    return rows, sprint


# ---------------------------------------------------------------------------
# Main training routine
# ---------------------------------------------------------------------------

def collect_data() -> pd.DataFrame:
    """Assemble historical race data for all training years from f1db (offline)."""
    all_rows: list[dict] = []

    # Circuit history accumulated across all years (keyed by circuit id)
    all_circuit_results: dict[str, dict[str, list[int]]] = {}
    all_circuit_deltas: dict[str, dict[str, list[float]]] = {}

    for year in TRAIN_YEARS:
        print(f"\n=== {year} ===")
        schedule = _get_race_schedule(year)
        if schedule.empty:
            print(f"  [skip] no schedule for {year}")
            continue

        # Reset per-season accumulators
        season_results_so_far: dict[str, list[int]] = {}
        season_sprints_so_far: dict[str, list[int]] = {}

        for _, event in schedule.iterrows():
            round_num = int(event["RoundNumber"])
            location = str(event.get("Location", f"round_{round_num}"))
            print(f"  Round {round_num:2d} — {event['EventName'][:40]}", end=" ", flush=True)

            circ_hist = all_circuit_results.get(location, {})
            circ_deltas = all_circuit_deltas.get(location, {})

            rows, sprint = _build_race_rows(
                year, round_num, location,
                circ_hist, season_results_so_far, circ_deltas,
                season_sprints_so_far,
            )

            if rows:
                sprint_tag = f", sprint" if sprint else ""
                all_rows.extend(rows)
                print(f"({len(rows)} drivers{sprint_tag})")

                # Update accumulators
                for row in rows:
                    code = row["driver_code"]
                    finish = row["finish_position"]
                    grid_pos = row["grid_position"]

                    # Circuit history (persists across seasons)
                    all_circuit_results.setdefault(location, {}).setdefault(code, []).append(finish)
                    all_circuit_deltas.setdefault(location, {}).setdefault(code, []).append(grid_pos - finish)

                    # Season race form (resets each year)
                    season_results_so_far.setdefault(code, []).append(finish)

                # Update sprint accumulators separately (season sprint form)
                for code, pos in sprint.items():
                    season_sprints_so_far.setdefault(code, []).append(pos)
            else:
                print("(no data)")

    return pd.DataFrame(all_rows)


# Model hyperparameters — kept in one place so validation and the final
# production fit always use an identical estimator.
#
# A regularized linear model (Ridge over standardized features) was chosen over
# gradient boosting after backtesting: the boosted trees overfit the noisy
# historical signals and lost to a plain "predict the grid order" baseline on
# 2021-2024, whereas this model beats that baseline on Spearman rank
# correlation, podium hit rate and MAE across every held-out season. See
# app.ml.evaluate for the harness that established this.
MODEL_PARAMS = {
    "alpha": 10.0,
}


def _build_model():
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(StandardScaler(), Ridge(**MODEL_PARAMS))


def _print_feature_influence(model) -> None:
    """Print each feature's influence, whichever estimator kind is in use.

    Linear models expose standardized ``coef_`` (sign matters: positive means the
    feature pushes the predicted finish worse); tree ensembles expose
    ``feature_importances_`` (magnitude only).
    """
    final = model.steps[-1][1] if hasattr(model, "steps") else model
    if hasattr(final, "coef_"):
        print("\nStandardized coefficients (sign = direction, |value| = strength):")
        for feat, coef in sorted(zip(FEATURES, final.coef_), key=lambda x: -abs(x[1])):
            print(f"  {feat:<22} {coef:+.3f}")
    elif hasattr(final, "feature_importances_"):
        print("\nFeature importances:")
        for feat, imp in sorted(zip(FEATURES, final.feature_importances_), key=lambda x: -x[1]):
            print(f"  {feat:<22} {imp:.3f}")


def walk_forward_validation(df: pd.DataFrame) -> list[dict]:
    """Season-forward backtest: train on all seasons < N, validate on season N.

    This respects chronology — a plain k-fold CV would leak future races into the
    training folds and report an over-optimistic error. Returns one result dict
    per validated season.
    """
    from sklearn.metrics import mean_absolute_error

    seasons = sorted(df["year"].unique())
    results: list[dict] = []

    # Start from the second season so there is always at least one prior season
    # to train on.
    for season in seasons[1:]:
        train_df = df[df["year"] < season]
        val_df = df[df["year"] == season]
        if train_df.empty or val_df.empty:
            continue

        model = _build_model()
        model.fit(train_df[FEATURES].values, train_df[TARGET].values)
        preds = model.predict(val_df[FEATURES].values)
        mae = float(mean_absolute_error(val_df[TARGET].values, preds))
        results.append({"season": int(season), "n": len(val_df), "mae": mae})

    return results


def train(df: pd.DataFrame) -> None:
    """Validate with a season-forward backtest, then fit the production model."""
    import joblib

    df = df.dropna(subset=FEATURES + [TARGET])

    sprint_rounds = int((df["had_sprint"] == 1).sum())
    print(f"\nCollected {len(df)} driver-race samples across {df['year'].nunique()} seasons")
    print(f"  of which {sprint_rounds} driver-rows are from sprint weekends")

    seasons = sorted(df["year"].unique())

    # ------------------------------------------------------------------
    # Walk-forward validation across all seasons (honest, leakage-free MAE)
    # ------------------------------------------------------------------
    print("\nWalk-forward validation (train on prior seasons, test on next):")
    wf_results = walk_forward_validation(df)
    for r in wf_results:
        print(f"  {r['season']}: MAE {r['mae']:.2f} positions  (n={r['n']})")
    wf_mae = (
        sum(r["mae"] for r in wf_results) / len(wf_results) if wf_results else float("nan")
    )
    print(f"  mean walk-forward MAE: {wf_mae:.2f} positions")

    # ------------------------------------------------------------------
    # Held-out most-recent season — the headline generalization number.
    # Trained only on strictly earlier seasons, never on the test season.
    # ------------------------------------------------------------------
    holdout_mae = float("nan")
    ranking_results: dict = {}
    if len(seasons) >= 2:
        from sklearn.metrics import mean_absolute_error

        from app.ml.evaluate import backtest

        holdout_season = seasons[-1]
        train_df = df[df["year"] < holdout_season]
        test_df = df[df["year"] == holdout_season]
        holdout_model = _build_model()
        holdout_model.fit(train_df[FEATURES].values, train_df[TARGET].values)
        holdout_mae = float(
            mean_absolute_error(test_df[TARGET].values, holdout_model.predict(test_df[FEATURES].values))
        )
        print(
            f"\nHeld-out {holdout_season} season MAE: {holdout_mae:.2f} positions "
            f"(trained on {int(train_df['year'].min())}–{int(holdout_season) - 1}, "
            f"tested on {holdout_season})"
        )

        # Ranking metrics vs. trivial baselines — the numbers that actually
        # measure whether the predicted finishing order is any good.
        ranking_results = backtest(df, _build_model, holdout_seasons=[int(holdout_season)])
        model_rank = ranking_results.get("model", {})
        grid_rank = ranking_results.get("grid_order", {})
        print(
            f"  ranking vs grid-order baseline (held-out {holdout_season}):\n"
            f"    Spearman     model {model_rank.get('spearman', float('nan')):.3f} "
            f"vs grid {grid_rank.get('spearman', float('nan')):.3f}\n"
            f"    podium hit   model {model_rank.get('podium_hit_rate', float('nan')):.3f} "
            f"vs grid {grid_rank.get('podium_hit_rate', float('nan')):.3f}\n"
            f"    winner acc   model {model_rank.get('winner_accuracy', float('nan')):.3f} "
            f"vs grid {grid_rank.get('winner_accuracy', float('nan')):.3f}"
        )

    # ------------------------------------------------------------------
    # Fit the production model on ALL available seasons for maximum data.
    # ------------------------------------------------------------------
    model = _build_model()
    model.fit(df[FEATURES].values, df[TARGET].values)

    _print_feature_influence(model)

    # Save model + feature list so inference code always uses matching features.
    # Metrics travel with the artifact so a model can be compared/rolled back.
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
            "metrics": {
                "walk_forward_mae": wf_mae,
                "walk_forward_by_season": wf_results,
                "holdout_mae": holdout_mae,
                "holdout_ranking": ranking_results,
                "trained_seasons": [int(s) for s in seasons],
                "n_samples": int(len(df)),
            },
        },
        MODEL_PATH,
    )
    print(f"\nModel saved to {MODEL_PATH}")


if __name__ == "__main__":
    # By default reuse the cached dataset (fast, seconds). Pass --refresh to
    # re-collect session data from FastF1 and standings from the local f1db
    # dataset (slower, but no live API rate limits).
    from app.ml.evaluate import load_or_collect_dataset

    refresh = "--refresh" in sys.argv
    df = load_or_collect_dataset(refresh=refresh)

    if df.empty:
        print("No data available — run once with --refresh to collect it.")
        sys.exit(1)

    print(f"\nTotal rows: {len(df)}")
    train(df)
