"""When the collection last ran, and how it went — the screen's "last updated".

One small document, ``power_unit_ingest_status``, written by every run of the
ingest job — including runs that find nothing new and runs that fail — so
the screen can tell three states apart that would otherwise look the same:

* checked recently, nothing new (the numbers are current);
* not checked for a while (the job has stopped, the numbers may be stale);
* checked, but the FIA site could not be read (the numbers are as of the last
  run that worked).

``changed_at`` is the last run that changed the stored corpus, carried over
by runs that change nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import structlog

from app.data.store import DOCUMENT_POWER_UNIT_STATUS, document_store

if TYPE_CHECKING:
    from app.data.store_types import WriteResult

logger = structlog.get_logger()

OUTCOME_OK = "ok"
OUTCOME_DOCUMENT_FAILURES = "document_failures"
OUTCOME_WRITE_FAILED = "write_failed"
OUTCOME_ABORTED = "aborted"


@dataclass(frozen=True)
class IngestStatus:
    """One run's outcome, as the screen reports it."""

    year: int
    checked_at: str
    outcome: str
    added: int = 0
    failed: int = 0
    withdrawn: int = 0
    #: A client-safe line on what went wrong, for a run that did not finish.
    error: str | None = None
    #: The last run that changed the stored corpus.
    changed_at: str | None = None

    def as_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "outcome": self.outcome,
            "added": self.added,
            "failed": self.failed,
            "withdrawn": self.withdrawn,
            "error": self.error,
            "changed_at": self.changed_at,
        }


def _seasons() -> dict:
    result = document_store.read(DOCUMENT_POWER_UNIT_STATUS)
    seasons = (result.payload or {}).get("seasons") if result.ok else None
    return seasons if isinstance(seasons, dict) else {}


def load_status(year: int) -> IngestStatus | None:
    """The season's last recorded run, or ``None`` when there is none to show.

    Never raises: a missing "last updated" line must not take the screen down
    with it, so an unreadable status reads as no status.
    """
    raw = _seasons().get(str(year))
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("checked_at"), str)
        or not isinstance(raw.get("outcome"), str)
    ):
        return None
    counts = {key: value if isinstance(value := raw.get(key), int) else 0 for key in ("added", "failed", "withdrawn")}
    text = {key: value if isinstance(value := raw.get(key), str) else None for key in ("error", "changed_at")}
    return IngestStatus(year=year, checked_at=raw["checked_at"], outcome=raw["outcome"], **counts, **text)


def record_status(status: IngestStatus, *, changed: bool) -> WriteResult:
    """Store this run's outcome; ``changed`` says whether it changed the corpus."""
    previous = load_status(status.year)
    carried = status.checked_at if changed else (previous.changed_at if previous else None)
    seasons = {**_seasons(), str(status.year): replace(status, changed_at=carried).as_dict()}
    result = document_store.write(DOCUMENT_POWER_UNIT_STATUS, {"seasons": seasons})
    logger.info("power_units.status_recorded", year=status.year, outcome=status.outcome, ok=result.ok)
    return result
