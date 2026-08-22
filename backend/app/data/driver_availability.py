"""Curated per-weekend driver availability adjustments.

There is a window — from the moment a withdrawal is announced until the
weekend's first session produces timing data — in which no automated source in
this stack knows who is actually racing. FastF1 has no entry list before the
cars run, and f1db is a pinned snapshot of completed rounds. During that window
a driver withdrawn on the Tuesday is still predicted on the Thursday.

This module is the manual bridge across that window: a small, explicit,
attributed record of "this driver is out for this round, here is why, here is
the source, here is who replaces them". Every adjustment carries its provenance
and is surfaced in the prediction warnings, so an adjusted grid is visibly
adjusted rather than passing itself off as observed data.

Adjustments are stored in the shared document store (Postgres when configured,
JSON file locally), so a lineup change needs no redeploy. Once the weekend's
real entry list exists, :mod:`app.data.session_entries` supersedes this for
everything it covers — an adjustment left behind is redundant, not harmful.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import structlog

from app.data.store import DOCUMENT_DRIVER_AVAILABILITY, document_store
from app.data.store_types import WriteResult

logger = structlog.get_logger()

PAYLOAD_VERSION = 1

STATUS_OUT = "out"
VALID_STATUSES = frozenset({STATUS_OUT})

_DRIVER_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")

# Angle brackets are how documentation marks a value the operator must fill in.
# A command copied verbatim from an example otherwise validates cleanly and
# writes "source: https://<announcement-url>" to the live grid, which is worse
# than no adjustment at all: it looks attributed and is not.
_UNFILLED_PLACEHOLDER = re.compile(r"[<>]")


class InvalidAdjustment(ValueError):
    """Raised when an adjustment fails validation at the write boundary."""


@dataclass(frozen=True)
class DriverAdjustment:
    """One curated change to a weekend's entry list.

    ``reason`` and ``source`` are mandatory on write: an unattributed override
    of observed data is indistinguishable from invented data, which is the
    failure mode this module exists to avoid.
    """

    driver_code: str
    status: str
    reason: str
    source: str
    noted_at: str
    replacement_code: str = ""
    replacement_name: str = ""
    replacement_team: str = ""

    @property
    def has_replacement(self) -> bool:
        return bool(self.replacement_code)

    def describe(self) -> str:
        """Human-readable note for the prediction warnings."""
        base = f"{self.driver_code} withdrawn ({self.reason})"
        if self.has_replacement:
            base += f", replaced by {self.replacement_name or self.replacement_code}"
        return f"{base} — manual entry adjustment, source: {self.source}"

    def as_payload(self) -> dict:
        return {
            "driver_code": self.driver_code,
            "status": self.status,
            "reason": self.reason,
            "source": self.source,
            "noted_at": self.noted_at,
            "replacement_code": self.replacement_code,
            "replacement_name": self.replacement_name,
            "replacement_team": self.replacement_team,
        }


@dataclass(frozen=True)
class WeekendAvailability:
    """Every curated adjustment for one round.

    ``ok`` is false when the store could not be read. That is *not* the same as
    "no adjustments": treating an outage as an empty override set would quietly
    restore the withdrawn driver to the grid, so callers surface it instead.
    """

    adjustments: tuple[DriverAdjustment, ...] = ()
    ok: bool = True
    error: str | None = None

    @property
    def withdrawn(self) -> frozenset[str]:
        return frozenset(a.driver_code for a in self.adjustments if a.status == STATUS_OUT)

    @property
    def replacements(self) -> tuple[DriverAdjustment, ...]:
        return tuple(a for a in self.adjustments if a.has_replacement)

    @property
    def notes(self) -> tuple[str, ...]:
        return tuple(a.describe() for a in self.adjustments)


def round_key(year: int, round_num: int) -> str:
    """Document key for one round's adjustments."""
    return f"{int(year)}:{int(round_num)}"


def _normalise_code(value: str, field: str) -> str:
    code = str(value or "").strip().upper()
    if not _DRIVER_CODE_PATTERN.match(code):
        raise InvalidAdjustment(f"{field} must be a three-letter driver code, got {value!r}")
    return code


def _require_text(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise InvalidAdjustment(f"{field} is required")
    if _UNFILLED_PLACEHOLDER.search(text):
        raise InvalidAdjustment(
            f"{field} still contains an unfilled placeholder ({text!r}); "
            "replace it with the real value"
        )
    return text


def _adjustment_from_payload(row: object) -> DriverAdjustment | None:
    """Parse one stored row, discarding anything malformed.

    Stored documents are external data: a hand-edited row must not be able to
    crash a prediction compute.
    """
    if not isinstance(row, dict):
        return None
    code = str(row.get("driver_code", "") or "").strip().upper()
    status = str(row.get("status", "") or "").strip().lower()
    if not _DRIVER_CODE_PATTERN.match(code) or status not in VALID_STATUSES:
        logger.warning("driver_availability.malformed_row", row=row)
        return None
    return DriverAdjustment(
        driver_code=code,
        status=status,
        reason=str(row.get("reason", "") or "").strip() or "reason not recorded",
        source=str(row.get("source", "") or "").strip() or "source not recorded",
        noted_at=str(row.get("noted_at", "") or "").strip(),
        replacement_code=str(row.get("replacement_code", "") or "").strip().upper(),
        replacement_name=str(row.get("replacement_name", "") or "").strip(),
        replacement_team=str(row.get("replacement_team", "") or "").strip(),
    )


def _read_document() -> tuple[dict, bool, str | None]:
    """Return ``(payload, ok, error)`` for the availability document."""
    result = document_store.read(DOCUMENT_DRIVER_AVAILABILITY)
    if not result.ok:
        logger.warning("driver_availability.read_failed", error=result.error)
        return {}, False, result.error
    return result.payload or {}, True, None


def load_weekend_availability(year: int, round_num: int) -> WeekendAvailability:
    """Return the curated adjustments recorded for one round."""
    payload, ok, error = _read_document()
    if not ok:
        return WeekendAvailability(ok=False, error=error)

    rounds = payload.get("rounds")
    rows = rounds.get(round_key(year, round_num), []) if isinstance(rounds, dict) else []
    adjustments = tuple(
        adjustment
        for adjustment in (_adjustment_from_payload(row) for row in rows)
        if adjustment is not None
    )
    return WeekendAvailability(adjustments=adjustments)


def record_driver_out(
    year: int,
    round_num: int,
    driver_code: str,
    reason: str,
    source: str,
    replacement_code: str = "",
    replacement_name: str = "",
    replacement_team: str = "",
) -> WriteResult:
    """Record that a driver is out for one round, optionally naming a replacement.

    Replaces any existing adjustment for the same driver and round rather than
    appending a second one, so a corrected entry supersedes the stale one.
    """
    code = _normalise_code(driver_code, "driver_code")
    adjustment = DriverAdjustment(
        driver_code=code,
        status=STATUS_OUT,
        reason=_require_text(reason, "reason"),
        source=_require_text(source, "source"),
        noted_at=datetime.now(timezone.utc).isoformat(),
    )
    if replacement_code:
        adjustment = replace(
            adjustment,
            replacement_code=_normalise_code(replacement_code, "replacement_code"),
            replacement_name=str(replacement_name or "").strip(),
            replacement_team=str(replacement_team or "").strip(),
        )

    payload, ok, error = _read_document()
    if not ok:
        # Writing on top of a failed read would drop every other adjustment in
        # the document, so refuse rather than silently truncate it.
        return WriteResult(ok=False, durable=False, error=error)

    key = round_key(year, round_num)
    rounds = payload.get("rounds")
    existing = list(rounds.get(key, [])) if isinstance(rounds, dict) else []
    kept = [
        row for row in existing
        if not (isinstance(row, dict) and str(row.get("driver_code", "")).strip().upper() == code)
    ]
    next_payload = {
        **payload,
        "version": PAYLOAD_VERSION,
        "rounds": {
            **(rounds if isinstance(rounds, dict) else {}),
            key: [*kept, adjustment.as_payload()],
        },
    }

    result = document_store.write(DOCUMENT_DRIVER_AVAILABILITY, next_payload)
    logger.info(
        "driver_availability.recorded",
        year=year, round=round_num, driver=code,
        replacement=adjustment.replacement_code or None,
        durable=result.durable,
    )
    return result


def clear_driver_adjustment(year: int, round_num: int, driver_code: str) -> WriteResult:
    """Remove a driver's adjustment for one round (a withdrawal that was reversed)."""
    code = _normalise_code(driver_code, "driver_code")
    payload, ok, error = _read_document()
    if not ok:
        return WriteResult(ok=False, durable=False, error=error)

    key = round_key(year, round_num)
    rounds = payload.get("rounds")
    existing = list(rounds.get(key, [])) if isinstance(rounds, dict) else []
    kept = [
        row for row in existing
        if not (isinstance(row, dict) and str(row.get("driver_code", "")).strip().upper() == code)
    ]
    next_payload = {
        **payload,
        "version": PAYLOAD_VERSION,
        "rounds": {**(rounds if isinstance(rounds, dict) else {}), key: kept},
    }
    result = document_store.write(DOCUMENT_DRIVER_AVAILABILITY, next_payload)
    logger.info("driver_availability.cleared", year=year, round=round_num, driver=code)
    return result
