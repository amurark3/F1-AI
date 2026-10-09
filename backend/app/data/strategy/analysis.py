"""Derived strategy numbers: undercut/overcut, pit windows and compound mix."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import pandas as pd
import structlog

logger = structlog.get_logger()


# A pit stop this many laps either side of a rival's counts as an attempt on them.
_PIT_WINDOW_LAPS = 3

# Finishing places either side of a driver that make a rival worth comparing.
_ADJACENT_PLACES = (1, 2)


@dataclass(frozen=True)
class AdjacentDriver:
    """A rival finishing within two places, and how our driver fared against them."""

    code: str
    pit_laps: list[int]
    outcome: str


def _attempt_kind(delta: int) -> str | None:
    """Classify a pit-lap gap: negative means our driver pitted first."""
    if -_PIT_WINDOW_LAPS <= delta < 0:
        return "undercut"
    if 0 < delta <= _PIT_WINDOW_LAPS:
        return "overcut"
    return None


def _attempts_against(driver_pit_laps: list[int], adjacent: AdjacentDriver) -> list[dict]:
    """One attempt per driver pit stop that lands inside the window on ``adjacent``.

    The inner loop stops at the first rival stop that matches, so a single stop
    is never counted as both an undercut and an overcut.
    """
    attempts = []
    for driver_lap in driver_pit_laps:
        for adjacent_lap in adjacent.pit_laps:
            kind = _attempt_kind(driver_lap - adjacent_lap)
            if kind:
                attempts.append(
                    {
                        "type": kind,
                        "target_driver": adjacent.code,
                        "lap": driver_lap,
                        "result": adjacent.outcome,
                    }
                )
                break
    return attempts


def _analyze_undercut_overcut(laps: pd.DataFrame, results: pd.DataFrame, driver_code: str) -> list[dict]:
    """Analyze undercut/overcut attempts for a specific driver.

    Compares pit stop timing with cars immediately ahead and behind.
    Undercut = pitting 1-3 laps before the car ahead.
    Overcut = pitting 1-3 laps after the car ahead.
    """
    if results is None or results.empty:
        return []

    # Get finishing order to find cars ahead/behind
    sorted_results = results.sort_values("Position")
    driver_positions = {
        str(row.get("Abbreviation", "")): int(row["Position"])
        for _, row in sorted_results.iterrows()
        if pd.notna(row.get("Position"))
    }

    if driver_code not in driver_positions:
        return []

    driver_pos = driver_positions[driver_code]

    driver_pit_laps = _get_pit_stop_laps(laps, driver_code)
    if not driver_pit_laps:
        return []

    undercut_overcut: list[dict] = []
    for code, position in driver_positions.items():
        if code == driver_code or abs(position - driver_pos) not in _ADJACENT_PLACES:
            continue
        pit_laps = _get_pit_stop_laps(laps, code)
        if not pit_laps:
            continue
        adjacent = AdjacentDriver(
            code=code,
            pit_laps=pit_laps,
            outcome=f"gained position over {code}" if driver_pos < position else f"did not gain on {code}",
        )
        undercut_overcut.extend(_attempts_against(driver_pit_laps, adjacent))

    return undercut_overcut


def _get_pit_stop_laps(laps: pd.DataFrame, driver_code: str) -> list[int]:
    """Get the lap numbers where a driver made pit stops."""
    driver_laps = laps[laps["Driver"] == driver_code].sort_values("LapNumber")
    if driver_laps.empty:
        return []

    pit_laps = []
    prev_stint = None

    for _, lap in driver_laps.iterrows():
        current_stint = lap.get("Stint")
        if pd.isna(current_stint):
            continue
        if prev_stint is not None and current_stint != prev_stint:
            pit_laps.append(int(lap["LapNumber"]))
        prev_stint = current_stint

    return pit_laps


def _percentile(values: list[int | float], percentile: float) -> float | None:
    """Small percentile helper to avoid adding another numeric dependency."""
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _summarize_compound_stints(stints_by_driver: list[dict]) -> list[dict]:
    """Summarize observed stint lengths and degradation by compound."""
    lengths_by_compound: dict[str, list[int]] = {}
    degradation_by_compound: dict[str, list[float]] = {}

    for driver_row in stints_by_driver:
        for stint in driver_row.get("stints", []):
            compound = str(stint.get("compound") or "UNKNOWN").upper()
            length = stint.get("stint_length")
            if isinstance(length, int) and length > 0:
                lengths_by_compound.setdefault(compound, []).append(length)
            degradation = stint.get("degradation_sec")
            if isinstance(degradation, (int, float)):
                degradation_by_compound.setdefault(compound, []).append(float(degradation))

    summary = []
    for compound, lengths in sorted(lengths_by_compound.items()):
        degradations = degradation_by_compound.get(compound, [])
        summary.append(
            {
                "compound": compound,
                "sample_size": len(lengths),
                "median_stint": round(median(lengths), 1),
                "p75_stint": round(_percentile(lengths, 0.75) or median(lengths), 1),
                "max_observed_stint": max(lengths),
                "avg_degradation_sec": round(sum(degradations) / len(degradations), 2) if degradations else None,
            }
        )
    return summary
