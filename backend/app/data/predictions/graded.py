"""The graded call: which of a race's stored calls its accuracy is scored on.

A race can hold several stored calls of both phases. The one that grades the
model is the latest post-qualifying call when the race has one, else its
latest pre-qualifying call: the most informed call the site published, however
the calls were ordered. A pre-qualifying recompute after the post-qualifying
call (R20 São Paulo, 2026-11-08) must not take its place.

Every reader that scores a race (rolling accuracy, the adaptive corrections,
the post-mortem, a review that names no phase) reads it through
:func:`graded_call`. A history entry's top-level fields hold a copy of it
(:func:`with_graded_fields`), written by ``save_prediction`` and by the one-off
``scripts.repair_graded_predictions``.

Calls stored before phases existed carry none: the latest of them is graded,
and an entry with no stored calls at all is read from its top-level fields.

Dependency-free apart from the phase names, like ``phases``.
"""

from __future__ import annotations

from app.data.predictions.phases import PHASE_POST_QUALIFYING, PHASE_PRE_QUALIFYING

# Most informed first: the first phase a race has a call for is graded.
GRADED_PHASE_ORDER = (PHASE_POST_QUALIFYING, PHASE_PRE_QUALIFYING)

# The fields one call carries, both in a history snapshot and, for the graded
# call, at the top level of its entry.
CALL_FIELDS = ("generated_at", "prediction_phase", "data_sources", "predicted_positions", "risk_predictions")


def legacy_call(entry: dict) -> dict:
    """The call held in an entry's top-level fields, absent collections read as empty."""
    return {
        "generated_at": entry.get("generated_at"),
        "prediction_phase": entry.get("prediction_phase"),
        "data_sources": entry.get("data_sources") or [],
        "predicted_positions": entry.get("predicted_positions") or {},
        "risk_predictions": entry.get("risk_predictions") or {},
    }


def _graded_snapshot(entry: dict) -> dict | None:
    """The stored call that grades the race, or None when it stores none."""
    snapshots = [item for item in entry.get("snapshots") or [] if isinstance(item, dict)]
    for phase in GRADED_PHASE_ORDER:
        matching = [item for item in snapshots if item.get("prediction_phase") == phase]
        if matching:
            return matching[-1]
    return snapshots[-1] if snapshots else None


def graded_call(entry: dict) -> dict:
    """The call a race is graded on: its latest post-qualifying, else pre-qualifying, call."""
    snapshot = _graded_snapshot(entry)
    return snapshot if snapshot is not None else legacy_call(entry)


def with_graded_fields(entry: dict) -> dict:
    """A copy of ``entry`` whose top-level call fields are its graded call's.

    An entry with no stored calls keeps its top-level fields as they are: they
    are its only call.
    """
    snapshot = _graded_snapshot(entry)
    if snapshot is None:
        return dict(entry)
    return {**entry, **{field: snapshot.get(field) for field in CALL_FIELDS}}
