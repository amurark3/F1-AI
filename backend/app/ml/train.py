"""
ML Training Pipeline
====================
Trains a GradientBoostingRegressor on 2018–2025 historical F1 race data
and saves the model to ``models/race_predictor.joblib``.

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
import time
import warnings
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd
from fastf1.ergast import Ergast
from fastf1.exceptions import RateLimitExceededError as F1RateLimitError
from app.utils.fastf1_cache import enable_fastf1_cache

# Suppress fastf1 and pandas noise during bulk data loading
warnings.filterwarnings("ignore")
fastf1.set_log_level("ERROR")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRAIN_YEARS = list(range(2018, 2025))   # 2018–2024 (2025 still in progress)
MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "race_predictor.joblib"
CACHE_DIR = Path(__file__).parent.parent.parent / "f1_cache"
ERGAST_RATE_LIMIT = 0.4   # minimum seconds between Ergast calls
ERGAST_MAX_RETRIES = 4    # max attempts before giving up on a single call
ERGAST_BACKOFF_BASE = 2.0 # first retry waits this many seconds; doubles each time

ergast = Ergast()

# ---------------------------------------------------------------------------
# In-process caches for Ergast calls
# These survive for the lifetime of one training run.  FastF1 already
# provides persistent disk-cache for session loads (qualifying/race/sprint).
# ---------------------------------------------------------------------------
_driver_standings_cache: dict[tuple[int, int], dict[str, int]] = {}
_constructor_standings_cache: dict[tuple[int, int], dict[str, int]] = {}

# Track the wall-clock time of the last Ergast HTTP call so we can enforce
# a minimum gap even across different helper functions.
_last_ergast_call: float = 0.0


# ---------------------------------------------------------------------------
# Data collection helpers
# ---------------------------------------------------------------------------

def _sleep() -> None:
    """Enforce the minimum inter-call gap since the last Ergast request."""
    global _last_ergast_call
    elapsed = time.monotonic() - _last_ergast_call
    wait = ERGAST_RATE_LIMIT - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_ergast_call = time.monotonic()


def _ergast_call_with_retry(fn, *args, **kwargs):
    """Call an Ergast method with exponential backoff on failure.

    Catches FastF1's RateLimitExceededError (500 calls/h bucket) and generic
    HTTP 429 responses, backing off significantly before retrying.
    Returns None if all retries are exhausted.
    """
    for attempt in range(ERGAST_MAX_RETRIES):
        _sleep()
        try:
            result = fn(*args, **kwargs)
            return result
        except F1RateLimitError as exc:
            # FastF1 client-side rate bucket exceeded — must wait for window to drain
            wait = 120.0 * (attempt + 1)  # 120s, 240s, 360s, 480s
            print(f"\n  [rate-limit] FastF1 bucket exhausted — waiting {wait:.0f}s (attempt {attempt + 1}/{ERGAST_MAX_RETRIES})")
            time.sleep(wait)
        except Exception as exc:
            msg = str(exc).lower()
            is_rate_limit = "429" in msg or "too many" in msg or "500 calls" in msg
            wait = ERGAST_BACKOFF_BASE * (2 ** attempt)
            if is_rate_limit:
                wait = max(wait, 120.0)
                print(f"\n  [rate-limit] HTTP 429 — waiting {wait:.0f}s (attempt {attempt + 1}/{ERGAST_MAX_RETRIES})")
            else:
                print(f"\n  [retry {attempt + 1}/{ERGAST_MAX_RETRIES}] {exc!r} — waiting {wait:.1f}s")
            time.sleep(wait)

    print(f"\n  [error] all {ERGAST_MAX_RETRIES} retries exhausted")
    return None


def _get_race_schedule(year: int) -> pd.DataFrame:
    """Return the race schedule for a season as a DataFrame."""
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        return schedule[["RoundNumber", "EventName", "Location"]].copy()
    except Exception as exc:
        print(f"  [warn] schedule {year}: {exc}")
        return pd.DataFrame()


def _get_qualifying_positions(year: int, round_num: int) -> dict[str, int]:
    """Return {driver_code: grid_position} for a race weekend."""
    try:
        session = fastf1.get_session(year, round_num, "Q")
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results
        if results is None or results.empty:
            return {}
        return {
            str(row["Abbreviation"]): int(row["Position"])
            for _, row in results.iterrows()
            if pd.notna(row.get("Position"))
        }
    except Exception:
        return {}


def _get_race_results(year: int, round_num: int) -> dict[str, int]:
    """Return {driver_code: finish_position} for a completed race."""
    try:
        session = fastf1.get_session(year, round_num, "R")
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results
        if results is None or results.empty:
            return {}
        return {
            str(row["Abbreviation"]): int(row["Position"])
            for _, row in results.iterrows()
            if pd.notna(row.get("Position"))
        }
    except Exception:
        return {}


def _get_sprint_positions(year: int, round_num: int) -> dict[str, int]:
    """Return {driver_code: sprint_finish_position} or {} if no sprint that weekend.

    Sprint races were introduced in 2021 at selected rounds only.
    FastF1 raises an exception when trying to load a non-existent sprint
    session, which we catch and treat as «no sprint».
    """
    try:
        session = fastf1.get_session(year, round_num, "S")
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results
        if results is None or results.empty:
            return {}
        return {
            str(row["Abbreviation"]): int(row["Position"])
            for _, row in results.iterrows()
            if pd.notna(row.get("Position"))
        }
    except Exception:
        return {}


def _get_driver_standings(year: int, round_num: int) -> dict[str, int]:
    """Return {driver_code: championship_position} after round_num-1.

    Results are cached in-process so repeated calls for the same (year, round)
    within a single training run never hit the network twice.
    """
    lookup_round = max(1, round_num - 1)
    cache_key = (year, lookup_round)
    if cache_key in _driver_standings_cache:
        return _driver_standings_cache[cache_key]

    data = _ergast_call_with_retry(
        ergast.get_driver_standings, season=year, round=lookup_round
    )
    if data is None or not data.content:
        return {}

    result = {
        str(row["driverCode"]): int(row["position"])
        for _, row in data.content[0].iterrows()
        if pd.notna(row.get("driverCode")) and pd.notna(row.get("position"))
    }
    _driver_standings_cache[cache_key] = result
    return result


def _get_constructor_standings(year: int, round_num: int) -> dict[str, int]:
    """Return {constructor_name: championship_position} after round_num-1.

    Results are cached in-process so repeated calls for the same (year, round)
    within a single training run never hit the network twice.
    """
    lookup_round = max(1, round_num - 1)
    cache_key = (year, lookup_round)
    if cache_key in _constructor_standings_cache:
        return _constructor_standings_cache[cache_key]

    data = _ergast_call_with_retry(
        ergast.get_constructor_standings, season=year, round=lookup_round
    )
    if data is None or not data.content:
        return {}

    result = {
        str(row["constructorName"]): int(row["position"])
        for _, row in data.content[0].iterrows()
        if pd.notna(row.get("constructorName")) and pd.notna(row.get("position"))
    }
    _constructor_standings_cache[cache_key] = result
    return result


def _get_team_for_driver(year: int, round_num: int) -> dict[str, str]:
    """Return {driver_code: team_name} for a race weekend."""
    try:
        session = fastf1.get_session(year, round_num, "R")
        session.load(telemetry=False, laps=False, weather=False)
        results = session.results
        if results is None or results.empty:
            return {}
        return {
            str(row["Abbreviation"]): str(row["TeamName"])
            for _, row in results.iterrows()
            if pd.notna(row.get("Abbreviation"))
        }
    except Exception:
        return {}


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

    had_sprint = 1 if sprint else 0

    rows = []
    for driver_code, finish_pos in race.items():
        grid_pos = grid.get(driver_code, 15)  # fallback: midfield

        # Sprint result this weekend (0 = no sprint)
        sprint_pos = sprint.get(driver_code, 0)

        # Recent race form: last 5 full-race finishes this season
        recent = season_results_so_far.get(driver_code, [])[-5:]
        recent_avg = float(np.mean(recent)) if recent else 10.0

        # Recent sprint form: last 3 sprint finishes this season (0 = none yet)
        recent_sprints = season_sprints_so_far.get(driver_code, [])[-3:]
        recent_sprint_avg = float(np.mean(recent_sprints)) if recent_sprints else 0.0

        # Circuit history: avg finish at this location (across past seasons)
        circ_hist = circuit_results.get(driver_code, [])
        circuit_avg = float(np.mean(circ_hist)) if circ_hist else 10.0

        # Grid-to-finish delta history at this circuit
        deltas = circuit_grid_deltas.get(driver_code, [])
        grid_delta_avg = float(np.mean(deltas)) if deltas else 0.0

        # Standings
        driver_pos = driver_standings.get(driver_code, 10)
        team_name = driver_teams.get(driver_code, "")
        team_pos = _team_position(team_name, constructor_standings)

        rows.append({
            "year": year,
            "round": round_num,
            "location": location,
            "driver_code": driver_code,
            "grid_position": grid_pos,
            "sprint_position": sprint_pos,
            "had_sprint": had_sprint,
            "recent_form_avg": recent_avg,
            "recent_sprint_avg": recent_sprint_avg,
            "circuit_avg": circuit_avg,
            "team_standing": team_pos,
            "driver_standing": driver_pos,
            "grid_delta_avg": grid_delta_avg,
            "finish_position": finish_pos,
        })

    return rows, sprint


# ---------------------------------------------------------------------------
# Main training routine
# ---------------------------------------------------------------------------

FEATURES = [
    "grid_position",
    "sprint_position",
    "had_sprint",
    "recent_form_avg",
    "recent_sprint_avg",
    "circuit_avg",
    "team_standing",
    "driver_standing",
    "grid_delta_avg",
]
TARGET = "finish_position"


def collect_data() -> pd.DataFrame:
    """Fetch historical race data for all training years and return a DataFrame."""
    enable_fastf1_cache(CACHE_DIR)
    all_rows: list[dict] = []

    # Circuit history accumulated across all years (keyed by location string)
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


def train(df: pd.DataFrame) -> None:
    """Train a GradientBoostingRegressor and save to MODEL_PATH."""
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import cross_val_score
    import joblib

    df = df.dropna(subset=FEATURES + [TARGET])
    X = df[FEATURES].values
    y = df[TARGET].values

    sprint_rounds = int((df["had_sprint"] == 1).sum())
    print(f"\nTraining on {len(df)} driver-race samples across {df['year'].nunique()} seasons")
    print(f"  of which {sprint_rounds} driver-rows are from sprint weekends")

    model = GradientBoostingRegressor(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        min_samples_leaf=5,
        random_state=42,
    )

    # Cross-validation for a quick sanity check
    scores = cross_val_score(model, X, y, cv=5, scoring="neg_mean_absolute_error")
    mae = -scores.mean()
    print(f"CV mean absolute error: {mae:.2f} positions")

    # Fit on full dataset
    model.fit(X, y)

    # Feature importances
    print("\nFeature importances:")
    for feat, imp in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1]):
        print(f"  {feat:<22} {imp:.3f}")

    # Save model + feature list so inference code always uses matching features
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES}, MODEL_PATH)
    print(f"\nModel saved to {MODEL_PATH}")


if __name__ == "__main__":
    print("Collecting historical race data (2018–2024)...")
    print("This may take several minutes due to API rate limiting.\n")

    df = collect_data()

    if df.empty:
        print("No data collected — check your network connection and FastF1 cache.")
        sys.exit(1)

    print(f"\nTotal rows collected: {len(df)}")
    train(df)
