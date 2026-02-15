"""
Feature engineering for the F1 race-position predictor.

Uses the Ergast API (via FastF1) to build per-driver-per-race feature vectors
from historical data. Each observation is one (driver, race) pair.
"""

import math
import time
import pandas as pd
from fastf1.ergast import Ergast

# Delay between API calls to avoid 429 rate-limiting from the Ergast mirror.
# Training makes hundreds of calls so needs a longer delay; inference is lighter.
_API_DELAY = 0.5  # seconds (default for inference)
_TRAINING_DELAY = 1.0  # seconds (used during bulk training)


def _throttled_call(fn, *args, **kwargs):
    """Call an Ergast API function with a delay to respect rate limits."""
    time.sleep(_API_DELAY)
    return fn(*args, **kwargs)


def _safe_int(val, default: int = 20) -> int:
    """Convert a value to int, returning *default* if NaN / None / non-numeric."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else int(f)
    except (ValueError, TypeError):
        return default

# Points awarded per finishing position (2010-present scoring system).
POINTS_MAP = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}

# Features the model expects (column order matters for inference).
FEATURE_COLUMNS = [
    "grid_position",
    "constructor_strength",
    "driver_championship_pos",
    "recent_form",
    "track_history",
    "dnf_rate",
]


def build_dataset(seasons: list[int]) -> pd.DataFrame:
    """
    Builds the full training dataset across the given seasons.

    Returns a DataFrame with one row per (driver, race). Columns include
    FEATURE_COLUMNS plus metadata (year, round, driver_id, circuit_id)
    and the target: finish_position.
    """
    global _API_DELAY
    old_delay = _API_DELAY
    _API_DELAY = _TRAINING_DELAY  # Use longer delay for bulk fetching.

    ergast = Ergast()
    all_rows: list[dict] = []

    # Cache schedules and results across seasons for track history lookups.
    _schedule_cache: dict[int, pd.DataFrame] = {}
    _results_cache: dict[tuple[int, int], pd.DataFrame] = {}

    for year in seasons:
        print(f"  Fetching {year}...")

        # Get the schedule to know how many rounds and circuit IDs.
        schedule = _throttled_call(ergast.get_race_schedule, season=year)
        if schedule.empty:
            continue
        _schedule_cache[year] = schedule
        total_rounds = len(schedule)

        # Pre-fetch all race results for this season.
        season_results: dict[int, pd.DataFrame] = {}
        for rnd in range(1, total_rounds + 1):
            try:
                res = _throttled_call(ergast.get_race_results, season=year, round=rnd)
                if res.content:
                    season_results[rnd] = res.content[0]
                    _results_cache[(year, rnd)] = res.content[0]
            except Exception:
                continue
            print(f"    {year} R{rnd}/{total_rounds}", end="\r")

        # Pre-fetch standings — only need the final standings before each round,
        # but fetching every round is expensive. Fetch only for rounds 5, 10, 15, etc.
        # and the last round, then interpolate for nearby rounds.
        driver_standings: dict[int, pd.DataFrame] = {}
        constructor_standings: dict[int, pd.DataFrame] = {}
        for rnd in range(1, total_rounds + 1):
            if rnd - 1 >= 1:
                try:
                    ds = _throttled_call(ergast.get_driver_standings, season=year, round=rnd - 1)
                    if ds.content:
                        driver_standings[rnd] = ds.content[0]
                except Exception:
                    pass
                try:
                    cs = _throttled_call(ergast.get_constructor_standings, season=year, round=rnd - 1)
                    if cs.content:
                        constructor_standings[rnd] = cs.content[0]
                except Exception:
                    pass

        # Build rows.
        for rnd, results_df in season_results.items():
            circuit_id = schedule.iloc[rnd - 1].get("circuitId", "")

            for _, row in results_df.iterrows():
                driver_id = row.get("driverId", "")
                grid = _safe_int(row.get("grid"), 20)
                if grid == 0:
                    grid = 20  # Pit lane start.
                finish = _safe_int(row.get("position"), 20)
                status = str(row.get("status", ""))
                is_dnf = finish > 20 or ("+" not in status and status not in ("Finished", ""))

                # Constructor championship position entering this race.
                constructor_pos = 10  # Default mid-field.
                cid = row.get("constructorId", "")
                if rnd in constructor_standings and cid:
                    cs_df = constructor_standings[rnd]
                    match = cs_df[cs_df["constructorId"] == cid]
                    if not match.empty:
                        constructor_pos = _safe_int(match.iloc[0]["position"], 10)

                # Driver championship position entering this race.
                driver_champ_pos = 15
                if rnd in driver_standings and driver_id:
                    ds_df = driver_standings[rnd]
                    match = ds_df[ds_df["driverId"] == driver_id]
                    if not match.empty:
                        driver_champ_pos = _safe_int(match.iloc[0]["position"], 15)

                # Recent form: average finish over previous 3 races this season.
                recent_finishes = []
                for prev_rnd in range(max(1, rnd - 3), rnd):
                    if prev_rnd in season_results:
                        prev_df = season_results[prev_rnd]
                        prev_row = prev_df[prev_df["driverId"] == driver_id]
                        if not prev_row.empty:
                            recent_finishes.append(_safe_int(prev_row.iloc[0].get("position"), 20))
                recent_form = sum(recent_finishes) / len(recent_finishes) if recent_finishes else 10.0

                # Track history: average finish at this circuit in previous seasons.
                track_finishes = _get_track_history_cached(
                    driver_id, circuit_id, year, seasons, _schedule_cache, _results_cache
                )
                track_history = sum(track_finishes) / len(track_finishes) if track_finishes else 10.0

                # DNF rate over previous 5 races.
                dnf_count = 0
                dnf_window = 0
                for prev_rnd in range(max(1, rnd - 5), rnd):
                    if prev_rnd in season_results:
                        prev_df = season_results[prev_rnd]
                        prev_row = prev_df[prev_df["driverId"] == driver_id]
                        if not prev_row.empty:
                            dnf_window += 1
                            s = str(prev_row.iloc[0].get("status", ""))
                            if "+" not in s and s not in ("Finished", ""):
                                dnf_count += 1
                dnf_rate = dnf_count / dnf_window if dnf_window > 0 else 0.0

                all_rows.append({
                    "year": year,
                    "round": rnd,
                    "driver_id": driver_id,
                    "driver_name": f"{row.get('givenName', '')} {row.get('familyName', '')}",
                    "circuit_id": circuit_id,
                    "grid_position": grid,
                    "constructor_strength": constructor_pos,
                    "driver_championship_pos": driver_champ_pos,
                    "recent_form": round(recent_form, 2),
                    "track_history": round(track_history, 2),
                    "dnf_rate": round(dnf_rate, 3),
                    "finish_position": min(finish, 20),
                    "is_dnf": is_dnf,
                })

    _API_DELAY = old_delay  # Restore default delay.
    return pd.DataFrame(all_rows)


# Cache to avoid re-fetching the same (driver, circuit) history.
_track_history_cache: dict[tuple, list[int]] = {}


def _get_track_history_cached(
    driver_id: str,
    circuit_id: str,
    current_year: int,
    available_seasons: list[int],
    schedule_cache: dict[int, pd.DataFrame],
    results_cache: dict[tuple[int, int], pd.DataFrame],
) -> list[int]:
    """Track history using already-fetched data (no extra API calls)."""
    cache_key = (driver_id, circuit_id, current_year)
    if cache_key in _track_history_cache:
        return _track_history_cache[cache_key]

    finishes: list[int] = []
    for prev_year in range(current_year - 3, current_year):
        if prev_year not in available_seasons or prev_year not in schedule_cache:
            continue
        sched = schedule_cache[prev_year]
        for rnd_idx, srow in sched.iterrows():
            if srow.get("circuitId") == circuit_id:
                rnd = int(srow.get("roundNumber", rnd_idx + 1))
                if (prev_year, rnd) in results_cache:
                    res_df = results_cache[(prev_year, rnd)]
                    match = res_df[res_df["driverId"] == driver_id]
                    if not match.empty:
                        finishes.append(_safe_int(match.iloc[0].get("position"), 20))
                break

    _track_history_cache[cache_key] = finishes
    return finishes


def _get_track_history(
    ergast: Ergast,
    driver_id: str,
    circuit_id: str,
    current_year: int,
    available_seasons: list[int],
) -> list[int]:
    """Returns list of finishing positions for this driver at this circuit in prior years (with API calls)."""
    cache_key = (driver_id, circuit_id, current_year)
    if cache_key in _track_history_cache:
        return _track_history_cache[cache_key]

    finishes: list[int] = []
    for prev_year in range(current_year - 3, current_year):
        if prev_year not in available_seasons:
            continue
        try:
            sched = _throttled_call(ergast.get_race_schedule, season=prev_year)
            for rnd_idx, srow in sched.iterrows():
                if srow.get("circuitId") == circuit_id:
                    res = _throttled_call(ergast.get_race_results, season=prev_year, round=int(srow.get("roundNumber", rnd_idx + 1)))
                    if res.content:
                        match = res.content[0][res.content[0]["driverId"] == driver_id]
                        if not match.empty:
                            finishes.append(_safe_int(match.iloc[0].get("position"), 20))
                    break
        except Exception:
            continue

    _track_history_cache[cache_key] = finishes
    return finishes


def compute_features_for_prediction(year: int, grand_prix: str) -> pd.DataFrame:
    """
    Builds features for all drivers on the current grid for a specific race.
    Used at inference time by predict.py.

    No throttle delays here — inference makes few calls and needs to be fast.
    When current-season data isn't available (e.g. season hasn't started),
    falls back to previous season's final standings.
    """
    ergast = Ergast()

    # Get the schedule to find the circuit and round number.
    schedule = ergast.get_race_schedule(season=year)
    target_round = None
    circuit_id = ""
    for _, srow in schedule.iterrows():
        if grand_prix.lower() in str(srow.get("raceName", "")).lower():
            target_round = int(srow.get("roundNumber", 0))
            circuit_id = srow.get("circuitId", "")
            break

    if target_round is None:
        raise ValueError(f"Could not find '{grand_prix}' in {year} schedule.")

    # Get qualifying or grid order if available.
    grid_map: dict[str, int] = {}
    try:
        quali = ergast.get_qualifying_results(season=year, round=target_round)
        if quali.content:
            for _, qr in quali.content[0].iterrows():
                grid_map[qr["driverId"]] = _safe_int(qr.get("position"), 20)
    except Exception:
        pass

    # Get standings entering this round.
    # If round 1 or no current-season data, fall back to previous season's final standings.
    driver_standings_df = None
    constructor_standings_df = None

    if target_round > 1:
        try:
            ds = ergast.get_driver_standings(season=year, round=target_round - 1)
            if ds.content:
                driver_standings_df = ds.content[0]
        except Exception:
            pass
        try:
            cs = ergast.get_constructor_standings(season=year, round=target_round - 1)
            if cs.content:
                constructor_standings_df = cs.content[0]
        except Exception:
            pass

    # Fallback: use previous season's final standings when current season has no data.
    if driver_standings_df is None:
        try:
            ds = ergast.get_driver_standings(season=year - 1)
            if ds.content:
                driver_standings_df = ds.content[0]
        except Exception:
            pass
    if constructor_standings_df is None:
        try:
            cs = ergast.get_constructor_standings(season=year - 1)
            if cs.content:
                constructor_standings_df = cs.content[0]
        except Exception:
            pass

    # Get recent race results for form calculation.
    # If no races this season yet, use last 3 races of previous season.
    recent_results: dict[tuple[int, int], pd.DataFrame] = {}
    for rnd in range(max(1, target_round - 3), target_round):
        try:
            res = ergast.get_race_results(season=year, round=rnd)
            if res.content:
                recent_results[(year, rnd)] = res.content[0]
        except Exception:
            continue

    if not recent_results:
        # Fall back to last 3 races of previous season.
        try:
            prev_sched = ergast.get_race_schedule(season=year - 1)
            if not prev_sched.empty:
                total_prev = len(prev_sched)
                for rnd in range(max(1, total_prev - 2), total_prev + 1):
                    try:
                        res = ergast.get_race_results(season=year - 1, round=rnd)
                        if res.content:
                            recent_results[(year - 1, rnd)] = res.content[0]
                    except Exception:
                        continue
        except Exception:
            pass

    # Build features for each driver in the entry list.
    drivers = ergast.get_driver_info(season=year)

    # Pre-build driver→constructor mapping ONCE.
    driver_constructor_map: dict[str, str] = {}
    try:
        constructors = ergast.get_constructor_info(season=year)
        for _, crow in constructors.iterrows():
            cid = crow["constructorId"]
            team_drivers = ergast.get_driver_info(season=year, constructor=cid)
            for _, td in team_drivers.iterrows():
                driver_constructor_map[td["driverId"]] = cid
    except Exception:
        pass

    # If no qualifying data, use constructor standings as grid proxy.
    # Better teams start higher — approximate grid from constructor position.
    if not grid_map and constructor_standings_df is not None:
        pos = 1
        for _, csrow in constructor_standings_df.iterrows():
            cid = csrow.get("constructorId", "")
            # Find drivers for this constructor.
            for did, dcid in driver_constructor_map.items():
                if dcid == cid and did not in grid_map:
                    grid_map[did] = pos
                    pos += 1

    rows: list[dict] = []

    for _, drow in drivers.iterrows():
        did = drow["driverId"]
        dname = f"{drow['givenName']} {drow['familyName']}"

        grid = grid_map.get(did, 15)

        constructor_pos = 10
        cid = driver_constructor_map.get(did)
        if cid and constructor_standings_df is not None:
            match = constructor_standings_df[constructor_standings_df["constructorId"] == cid]
            if not match.empty:
                constructor_pos = _safe_int(match.iloc[0]["position"], 10)

        driver_champ_pos = 15
        if driver_standings_df is not None:
            match = driver_standings_df[driver_standings_df["driverId"] == did]
            if not match.empty:
                driver_champ_pos = _safe_int(match.iloc[0]["position"], 15)

        recent_finishes = []
        for _, rdf in recent_results.items():
            match = rdf[rdf["driverId"] == did]
            if not match.empty:
                recent_finishes.append(_safe_int(match.iloc[0].get("position"), 20))
        recent_form = sum(recent_finishes) / len(recent_finishes) if recent_finishes else 10.0

        # Track history — use direct calls (no throttle, few calls).
        track_finishes = _get_track_history(ergast, did, circuit_id, year, list(range(year - 3, year)))
        track_history = sum(track_finishes) / len(track_finishes) if track_finishes else 10.0

        dnf_count = sum(
            1 for _, rdf in recent_results.items()
            for _, r in rdf[rdf["driverId"] == did].iterrows()
            if "+" not in str(r.get("status", "")) and str(r.get("status", "")) not in ("Finished", "")
        )
        dnf_rate = dnf_count / len(recent_results) if recent_results else 0.0

        rows.append({
            "driver_id": did,
            "driver_name": dname,
            "grid_position": grid,
            "constructor_strength": constructor_pos,
            "driver_championship_pos": driver_champ_pos,
            "recent_form": round(recent_form, 2),
            "track_history": round(track_history, 2),
            "dnf_rate": round(dnf_rate, 3),
        })

    return pd.DataFrame(rows)
