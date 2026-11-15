"""Who finished a race, who retired, and how far each car got.

The classification is the only thing allowed to say how a driver's race ended.
Inferring it from laps or stints is how Lindblad's Mexico 2026 retirement on
lap 58 was labelled a finish: the stint data simply stopped, and a stint with
no stop after it looked like the last one of a finished race.

**Where it comes from, in order** (``docs/DATA_SOURCES.md``, "Source of truth"):

1. OpenF1 ``session_result``. Published minutes after the flag, with ``dnf``,
   ``dns`` and ``dsq`` flags and laps completed per car. On the morning after
   Mexico 2026 it matched FIA document 86, the final classification, including
   the post-race penalties.
2. Jolpica's results, through :mod:`app.data.jolpica`. It applies post-race
   penalties late (it still had Piastri 7th that morning), so it only answers
   when OpenF1 cannot: while a live session locks OpenF1, or for a race OpenF1
   does not cover.

The FIA final classification takes over as the authority in task D2.3.

A result can change after it is first published, as penalties land, so an
answer is kept for :data:`CLASSIFICATION_TTL_SECONDS` and then read again. No
answer is retried after :data:`EMPTY_RETRY_SECONDS`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Literal

import structlog

from app.data.canonical_names import F1DB_READ_ERRORS
from app.data.f1db_race_results import result_rows
from app.data.jolpica import JolpicaUnavailableError, race_results as jolpica_results
from app.data.openf1.client import OpenF1UnavailableError, get_json, new_client
from app.data.openf1.sessions import EntryDriver, entry_list, find_session, session_ended
from app.utils.ttl_cache import TtlCache

logger = structlog.get_logger()

ClassificationStatus = Literal["finished", "dnf", "dns", "dsq", "not_classified"]

OPENF1_SOURCE = "openf1-session-result"
JOLPICA_SOURCE = "jolpica-results"

# How long an answer stands before it is read again: long enough to spare the
# feeds, short enough to pick up a stewards' decision the same evening.
CLASSIFICATION_TTL_SECONDS = 30 * 60
EMPTY_RETRY_SECONDS = 5 * 60

# Jolpica's ``positionText`` for a car with no classified position.
JOLPICA_STATUS_BY_POSITION_TEXT: dict[str, ClassificationStatus] = {
    "R": "dnf",
    "D": "dsq",
    # Excluded from the results, which reads the same as disqualified.
    "E": "dsq",
    # Withdrawn, or failed to qualify: either way the car never started.
    "W": "dns",
    "F": "dns",
    "N": "not_classified",
}
# Jolpica statuses for a car that took the flag. Anything else on a classified
# row ("Engine", "Accident") is a retirement after 90% distance.
JOLPICA_FINISHED_STATUSES = frozenset({"Finished", "Lapped"})


@dataclass(frozen=True)
class ClassifiedDriver:
    """One car's line in the classification."""

    driver_code: str
    #: The classified finishing position. ``None`` when the car was not
    #: classified, which is a different fact from finishing last.
    position: int | None
    status: ClassificationStatus
    #: Laps completed, or ``None`` when the source does not say.
    laps_completed: int | None
    #: Why the car stopped (f1db's ``race_reason_retired``), or ``None``: OpenF1
    #: and Jolpica carry no reason, and f1db only has it once it holds the race.
    reason: str | None = None


@dataclass(frozen=True)
class RaceClassification:
    """A race's classification, in published order, and the source it came from."""

    source: str | None
    drivers: tuple[ClassifiedDriver, ...]


NO_CLASSIFICATION = RaceClassification(source=None, drivers=())

_cache: TtlCache[tuple[int, int], RaceClassification] = TtlCache()


def _whole(value: object) -> int | None:
    """An integer field, or ``None`` when it is missing or NaN."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return int(value)


def openf1_status(row: dict) -> ClassificationStatus:
    if row.get("dsq"):
        return "dsq"
    if row.get("dns"):
        return "dns"
    if row.get("dnf"):
        return "dnf"
    return "finished" if row.get("position") is not None else "not_classified"


def _published_order(driver: ClassifiedDriver) -> tuple[bool, int, bool, int]:
    """The FIA's order: classified cars by position, then the rest by laps, disqualified last."""
    return (
        driver.position is None,
        driver.position or 0,
        driver.status == "dsq",
        -(driver.laps_completed or 0),
    )


def classification_from_openf1(rows: list[dict], codes: dict[int, str]) -> tuple[ClassifiedDriver, ...]:
    """OpenF1 ``session_result`` rows as a classification, in the FIA's order.

    ``codes`` maps car numbers onto three-letter codes. A car missing from it
    keeps its number, as the stints do.
    """
    drivers = [
        ClassifiedDriver(
            driver_code=codes.get(int(row["driver_number"]), str(row["driver_number"])),
            position=_whole(row.get("position")),
            status=openf1_status(row),
            laps_completed=_whole(row.get("number_of_laps")),
        )
        for row in rows
        if row.get("driver_number") is not None
    ]
    # sorted() is stable, so cars level on every key keep OpenF1's order.
    return tuple(sorted(drivers, key=_published_order))


def _jolpica_driver(row: dict) -> ClassifiedDriver:
    text = str(row.get("positionText") or "").strip().upper()
    if text.isdigit():
        position = int(text)
        status: ClassificationStatus = (
            "finished"
            if str(row.get("status") or "") in JOLPICA_FINISHED_STATUSES or str(row.get("status") or "").startswith("+")
            else "dnf"
        )
    else:
        position = None
        status = JOLPICA_STATUS_BY_POSITION_TEXT.get(text, "not_classified")
    return ClassifiedDriver(
        driver_code=str(row["driverCode"]).strip().upper(),
        position=position,
        status=status,
        laps_completed=_whole(row.get("laps")),
    )


def classification_from_jolpica(rows: list[dict]) -> tuple[ClassifiedDriver, ...]:
    """Jolpica result rows (as :mod:`app.data.jolpica` flattens them), in Jolpica's order."""
    ranked = sorted(rows, key=lambda row: _whole(row.get("position")) or 0)
    return tuple(_jolpica_driver(row) for row in ranked if isinstance(row.get("driverCode"), str))


def openf1_session_result(year: int, round_num: int, session: str = "R") -> tuple[list[dict], dict[int, EntryDriver]]:
    """OpenF1's ``session_result`` rows for a finished race (``"R"``) or sprint (``"S"``), with the entry list.

    Both are empty when the session has not ended, OpenF1 does not cover it or
    cannot be reached; callers must then say nothing is published.
    """
    try:
        with new_client() as client:
            race = find_session(client, year, round_num, session)
            # A result read while the race runs would be a running order.
            if race is None or not session_ended(race):
                return [], {}
            rows = get_json(client, "session_result", {"session_key": race.session_key})
            if not rows:
                return [], {}
            entries = entry_list(client, race.session_key)
    # The calendar lookup reads f1db, which raises CalendarUnavailableError (a
    # ValueError) for a season it does not hold.
    except (OpenF1UnavailableError, ValueError, KeyError, OSError) as exc:
        logger.warning("race_classification.openf1_unavailable", year=year, round=round_num, error=str(exc))
        return [], {}
    if not entries:
        # Numbers alone would never match the stints' driver codes.
        logger.warning("race_classification.openf1_no_entry_list", year=year, round=round_num)
        return [], {}
    return rows, entries


def _openf1_classification(year: int, round_num: int) -> tuple[ClassifiedDriver, ...]:
    rows, entries = openf1_session_result(year, round_num)
    return classification_from_openf1(rows, {number: entry.code for number, entry in entries.items()})


def _jolpica_classification(year: int, round_num: int) -> tuple[ClassifiedDriver, ...]:
    try:
        rows = jolpica_results(year, round_num)
    except JolpicaUnavailableError as exc:
        logger.warning("race_classification.jolpica_unavailable", year=year, round=round_num, error=str(exc))
        return ()
    return classification_from_jolpica(rows)


def _with_reasons(year: int, round_num: int, drivers: tuple[ClassifiedDriver, ...]) -> tuple[ClassifiedDriver, ...]:
    """``drivers`` with f1db's retirement reasons, where f1db already holds the race."""
    try:
        reasons = {row.code: row.reason for row in result_rows(year, round_num)}
    except F1DB_READ_ERRORS as exc:
        logger.warning("race_classification.f1db_unreadable", year=year, round=round_num, error=str(exc))
        return drivers
    return tuple(replace(driver, reason=reasons.get(driver.driver_code)) for driver in drivers)


def race_classification(year: int, round_num: int) -> RaceClassification:
    """The race's classification, from the first source that publishes one.

    :data:`NO_CLASSIFICATION` when none does: a race that has not run, or every
    source unreachable. Callers must then say the result is not published,
    never assume who finished.
    """
    key = (year, round_num)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    drivers = _openf1_classification(year, round_num)
    source = OPENF1_SOURCE
    if not drivers:
        drivers = _jolpica_classification(year, round_num)
        source = JOLPICA_SOURCE
    result = (
        RaceClassification(source=source, drivers=_with_reasons(year, round_num, drivers))
        if drivers
        else NO_CLASSIFICATION
    )
    _cache.put(key, result, CLASSIFICATION_TTL_SECONDS if drivers else EMPTY_RETRY_SECONDS)
    logger.info("race_classification.loaded", year=year, round=round_num, source=result.source, drivers=len(drivers))
    return result
