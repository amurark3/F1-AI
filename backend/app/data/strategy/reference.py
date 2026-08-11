"""Pre-race strategy reference for upcoming races with no live laps.

The command-center homepage plans an *upcoming* race, so there is no live
telemetry to analyse yet. Instead we derive planning numbers from the most
recent completed edition of the same circuit: real pit loss, tyre windows,
and stint compounds. Undercut/overcut deltas are left to the caller's model
because the available stint-pace signal is not cleanly fuel-corrected.
"""

from __future__ import annotations

from collections import Counter
from statistics import median

import fastf1
import pandas as pd
import structlog

from app.data.strategy.analysis import (
    _get_pit_stop_laps,
    _percentile,
)
from app.data.strategy.session import _extract_stint_data, _load_race_data

logger = structlog.get_logger()

# (city, current_year) -> derived reference dict (or None when unavailable)
_circuit_reference_cache: dict[str, dict | None] = {}


def _estimate_pit_loss(laps: pd.DataFrame) -> float | None:
    """Estimate pit-lane time loss in seconds from in-lap/out-lap deltas.

    For each stop, compares the combined in-lap + out-lap time against twice
    the driver's median green-flag lap. The median across every stop in the
    race approximates the circuit's pit-lane delta. Returns None when no
    usable stop pairs are found.
    """
    losses: list[float] = []
    # Driver codes come from this frame, so every one of them selects rows.
    for drv in laps["Driver"].dropna().unique():
        drv_laps = laps[laps["Driver"] == drv].sort_values("LapNumber")

        # Green-flag reference pace: laps with no pit activity, excluding lap 1.
        green = drv_laps[drv_laps["PitInTime"].isna() & drv_laps["PitOutTime"].isna() & (drv_laps["LapNumber"] > 1)][
            "LapTime"
        ].dropna()
        if green.empty:
            continue
        reference = green.median().total_seconds()

        by_number = {int(row["LapNumber"]): row for _, row in drv_laps.iterrows() if pd.notna(row.get("LapNumber"))}
        for _, lap in drv_laps.iterrows():
            if pd.isna(lap.get("PitInTime")) or pd.isna(lap.get("LapNumber")):
                continue
            out_lap = by_number.get(int(lap["LapNumber"]) + 1)
            if out_lap is None:
                continue
            in_time = lap.get("LapTime")
            out_time = out_lap.get("LapTime")
            if pd.isna(in_time) or pd.isna(out_time):
                continue
            loss = in_time.total_seconds() + out_time.total_seconds() - 2 * reference
            # Filter safety-car and data anomalies; real pit loss sits well inside this.
            if 5.0 < loss < 60.0:
                losses.append(loss)

    return round(median(losses), 1) if losses else None


def _summarize_circuit_edition(race_data: dict, edition_year: int) -> dict | None:
    """Reduce one completed race into pre-race planning reference numbers."""
    laps = race_data["laps"]
    if laps is None or laps.empty:
        return None
    total_laps = int(laps["LapNumber"].max())
    if total_laps <= 0:
        return None

    first_stop_laps: list[int] = []
    stop_counts: list[int] = []
    compound_sequences: list[list[str]] = []
    for drv in laps["Driver"].dropna().unique():
        stints = _extract_stint_data(laps, str(drv))
        if not stints:
            continue
        stop_counts.append(len(stints) - 1)
        pit_laps = _get_pit_stop_laps(laps, str(drv))
        if pit_laps:
            first_stop_laps.append(pit_laps[0])
        compound_sequences.append([s["compound"].upper() for s in stints])

    if not first_stop_laps or not stop_counts:
        return None

    median_first_stop = round(median(first_stop_laps))
    most_common_stops = Counter(stop_counts).most_common(1)[0][0]

    # Most common opening / finishing compounds across the field.
    opening_counter = Counter(seq[0] for seq in compound_sequences if seq)
    finishing_counter = Counter(seq[-1] for seq in compound_sequences if len(seq) > 1)
    opening_compound = opening_counter.most_common(1)[0][0] if opening_counter else "MEDIUM"
    finishing_compound = finishing_counter.most_common(1)[0][0] if finishing_counter else "HARD"

    return {
        "source_year": edition_year,
        "sample_size": len(stop_counts),
        "total_laps": total_laps,
        "median_first_stop": median_first_stop,
        "first_stop_p25": round(_percentile(first_stop_laps, 0.25) or median_first_stop),
        "first_stop_p75": round(_percentile(first_stop_laps, 0.75) or median_first_stop),
        "most_common_stops": most_common_stops,
        "opening_compound": opening_compound.title(),
        "finishing_compound": finishing_compound.title(),
        "pit_loss_seconds": _estimate_pit_loss(laps),
    }


def circuit_strategy_reference(location: str, current_year: int) -> dict | None:
    """Derive real pre-race strategy numbers for a circuit from its most recent
    completed edition.

    Args:
        location: Circuit location, e.g. ``"Budapest, Hungary"`` or ``"Budapest"``.
        current_year: The season being planned; editions are searched backwards
            from here (the current-year edition is included in case it has
            already been run).

    Returns:
        A reference dict with pit loss, tyre windows, stint compounds, and
        degradation-based undercut/overcut deltas, or None when no historical
        race data can be loaded for the circuit.
    """
    city = location.split(",", maxsplit=1)[0].strip() if location else ""
    if not city:
        return None

    cache_key = f"{city}_{current_year}"
    if cache_key in _circuit_reference_cache:
        return _circuit_reference_cache[cache_key]

    reference: dict | None = None
    for past_year in range(current_year, 2017, -1):
        try:
            schedule = fastf1.get_event_schedule(past_year, include_testing=False)
        except Exception as exc:
            logger.debug("strategy.reference_schedule_error", year=past_year, error=str(exc))
            continue

        matching = schedule[schedule["Location"] == city]
        if matching.empty:
            for _, evt in schedule.iterrows():
                if city.lower() in str(evt.get("Location", "")).lower():
                    matching = schedule[schedule.index == evt.name]
                    break
        if matching.empty:
            continue

        round_num = int(matching.iloc[0]["RoundNumber"])
        race_data = _load_race_data(past_year, round_num)
        if race_data is None:
            continue

        try:
            reference = _summarize_circuit_edition(race_data, past_year)
        except Exception as exc:
            logger.warning("strategy.reference_summary_error", year=past_year, error=str(exc))
            reference = None
        if reference:
            break

    _circuit_reference_cache[cache_key] = reference
    logger.info(
        "strategy.reference_ready",
        location=city,
        year=current_year,
        source_year=(reference or {}).get("source_year"),
    )
    return reference
