"""Prediction phases, and how many stored calls of each a race keeps.

A race can be predicted twice: once from form and history alone, and again
once the grid is known. Both are kept so the two calls can be compared, and so
recomputing one never discards the other.

Dependency-free on purpose: the snapshot cache imports these to key and trim
its own stored calls, and that should not drag in FastF1 or the scoring model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

PHASE_PRE_QUALIFYING = "pre_qualifying"
PHASE_POST_QUALIFYING = "post_qualifying"
PREDICTION_PHASES = (PHASE_PRE_QUALIFYING, PHASE_POST_QUALIFYING)

# How many stored calls to keep per race, across both phases.
SNAPSHOT_HISTORY_LIMIT = 8


def normalise_phase(phase: str | None) -> str | None:
    """Return a known phase, or None for "whichever the data supports"."""
    return phase if phase in PREDICTION_PHASES else None


def history_snapshot_phase(item: dict) -> str | None:
    """Phase of a prediction-history snapshot, which stores it at the top level."""
    return item.get("prediction_phase")


def trim_snapshots(
    snapshots: list[dict],
    limit: int = SNAPSHOT_HISTORY_LIMIT,
    phase_of: Callable[[dict], str | None] = history_snapshot_phase,
) -> list[dict]:
    """Keep the most recent calls, never dropping the newest one of either phase.

    Recomputing one tab repeatedly must not evict the other tab's only stored
    prediction — that call is what its review and side-by-side comparison are
    built from.
    """
    if len(snapshots) <= limit:
        return list(snapshots)

    keep = set(range(len(snapshots) - limit, len(snapshots)))
    for phase in PREDICTION_PHASES:
        newest = max(
            (index for index, item in enumerate(snapshots) if phase_of(item) == phase),
            default=None,
        )
        if newest is not None:
            keep.add(newest)
    return [snapshots[index] for index in sorted(keep)]
