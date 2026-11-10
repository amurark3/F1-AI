"""One edition's race, read from the sources the baseline plan trusts.

Four reads, each from the source ``docs/DATA_SOURCES.md`` names for its fact:

* **Tyre stints:** OpenF1 ``stints`` (:func:`app.data.openf1_stints.openf1_race_stints`),
  merged to one row per tyre set. FastF1's laps are not used: F1's live-timing
  archive has needed a login since 15 Oct 2026, so 2023-2025 no longer load on
  a cold cache, which is how R20 2026 came to be planned from 2022.
* **Who finished:** the classification (:func:`app.data.race_classification.race_classification`):
  OpenF1 ``session_result``, else Jolpica.
* **Stops:** the published pit sheet (:func:`app.data.pit_sheet.race_pit_sheet`):
  Jolpica, else f1db. The red-flag suspension is left out exactly as the Stints
  tab leaves it out (P0.2), with the stints' red-flag laps.
* **Pit-lane time:** OpenF1 ``pit.pit_duration``, pit entry to pit exit.

A finished edition always has all four, so an empty answer from any of them
means "not readable right now" (OpenF1 refuses every request while a session
is live; Jolpica publishes stops hours after the flag), never "this race had
none". The edition is then reported unread, and the caller tries again later.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.data.openf1.client import OpenF1UnavailableError, get_json, new_client
from app.data.openf1.sessions import entry_list, find_session
from app.data.openf1_stints import openf1_race_stints
from app.data.pit_sheet import race_pit_sheet, without_suspension
from app.data.race_classification import race_classification
from app.data.strategy.edition_plan import EditionRace, summarize_edition

if TYPE_CHECKING:
    from app.data.strategy.edition_plan import Edition

logger = structlog.get_logger()

STINTS_SOURCE = "openf1-stints"
PIT_LANE_SOURCE = "openf1-pit"

MILLIS_PER_SECOND = 1000


def _lane_seconds(row: dict) -> float | None:
    """OpenF1's pit-lane time for one pass; ``lane_duration`` is the same figure under its newer name."""
    value = row.get("pit_duration")
    if value is None:
        value = row.get("lane_duration")
    return None if value is None else float(value)


def pit_lane_times(year: int, round_num: int) -> dict[tuple[str, int], int] | None:
    """OpenF1's pit-lane time per pass in milliseconds, by (driver, lap).

    Empty when OpenF1 publishes none for the race; None when it could not be
    asked (unreachable, rate limited, closed for a live session, or the race
    not matched), which the caller must not read as "none published".
    """
    try:
        with new_client() as client:
            race = find_session(client, year, round_num, "R")
            if race is None:
                logger.warning("strategy.pit_lane_race_unmatched", year=year, round=round_num)
                return None
            rows = get_json(client, "pit", {"session_key": race.session_key})
            entries = entry_list(client, race.session_key) if rows else {}
    # The calendar lookup reaches FastF1's schedule backend, which raises
    # ValueError/KeyError for a bad season and OSError for a network failure.
    except (OpenF1UnavailableError, ValueError, KeyError, OSError) as exc:
        logger.warning("strategy.pit_lane_unavailable", year=year, round=round_num, error=str(exc))
        return None

    times: dict[tuple[str, int], int] = {}
    for row in rows:
        seconds, driver, lap = _lane_seconds(row), entries.get(row.get("driver_number")), row.get("lap_number")
        if seconds is None or driver is None or lap is None:
            continue
        times[(driver.code, int(lap))] = round(seconds * MILLIS_PER_SECOND)
    return times


def edition_reference(edition: Edition) -> dict | None:
    """The edition's measured plan with its sources, or None when it cannot be read right now."""
    year, round_num = edition.year, edition.round
    stints = openf1_race_stints(year, round_num)
    classification = race_classification(year, round_num)
    sheet = race_pit_sheet(year, round_num)
    missing = [
        name
        for name, present in (
            ("stints", stints),
            ("classification", classification.drivers),
            ("pit sheet", sheet.entries),
        )
        if not present
    ]
    if missing:
        logger.warning("strategy.edition_unread", year=year, round=round_num, missing=missing)
        return None
    lane = pit_lane_times(year, round_num)
    if lane is None:
        logger.warning("strategy.edition_unread", year=year, round=round_num, missing=["pit lane"])
        return None

    flagged = frozenset(stint.end_lap for stint in stints if stint.ended_under_red_flag)
    real = without_suspension(sheet.entries, flagged)
    plan = summarize_edition(edition, EditionRace(stints, real.stops, classification.drivers, lane))
    if plan is None:
        logger.warning("strategy.edition_without_finishers", year=year, round=round_num)
        return None
    return {
        **plan,
        # Sheet entries left out because the race was suspended, not because anyone stopped.
        "suspension_entries": real.suspension_entries,
        "sources": {
            "stints": STINTS_SOURCE,
            "stops": sheet.source,
            "classification": classification.source,
            "pit_lane": PIT_LANE_SOURCE if plan["pit_lane"] else None,
        },
    }
