"""Tyre stints for a race, from OpenF1.

FastF1 reads stints from F1's live-timing archive, which has answered 401 to
anyone without an F1 TV token since mid-October 2026. On a cold FastF1 cache,
and Render's is always cold, that left the Stints tab with pit stops and no
stints for every race, past seasons included. OpenF1 publishes the same stints
without a login and agrees with FastF1's lap frame: driver, stint number,
compound and lap range matched on all 52 stints of Monza 2026.

Four details differ, and each is normalised here so callers see one meaning:

* **A stint is a tyre set.** OpenF1 opens a new stint on every pit-lane pass,
  so a drive-through or "all cars through the pit lane" under a safety car
  (15 drivers at R15 2026) reads as a tyre change that never happened. A row
  that carries on the same compound at the age the last one reached is merged
  back into it.

* **Tyre age.** ``tyre_age_at_start`` is the laps already on the set, 0 for a
  new one, which is what :class:`Stint` means. (FastF1's ``TyreLife`` counts the
  lap being driven; :mod:`app.data.race_stints` subtracts it.)
* **Freshness.** OpenF1 has no ``FreshTyre``. A set with no laps on it is new,
  which matched FastF1 on every Monza stint.
* **Red flags.** There is no per-lap track status. A suspension is a race
  control message, ``flag: "RED"`` up to 2025 and "RED FLAG - RACE SUSPENDED"
  with no flag since 2026, stamped with the *leader's* lap. A lapped car was
  on an earlier lap when the flag came out, so each car's lap in progress at
  that moment is read from its own lap start times. Steward notes such as
  "... RED FLAG INFRINGEMENT" are not suspensions.

The meeting is matched by circuit location and the session by name, never by
round index or ``session_type``, which reads "Race" for a sprint too (see
:mod:`app.services.live_timing`).

OpenF1 refuses unauthenticated clients while any F1 session is live, and rate
limits bursts with 429. Every failure ends in "no stints", which the caller
retries rather than caches.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.data.openf1.client import OpenF1UnavailableError, get_json, new_client
from app.data.openf1.sessions import find_session
from app.data.stint_model import Stint, clean_compound
from app.services.live_timing import parse_iso

if TYPE_CHECKING:
    from datetime import datetime

    import httpx

logger = structlog.get_logger()

RED_FLAG = "RED"
FIRST_LAP = 1

# Red-flag laps per driver number.
RedFlagLaps = dict[int, frozenset[int]]


def red_flag_moments(messages: list[dict]) -> tuple[datetime, ...]:
    """When the race was suspended, read from race-control messages."""
    moments: set[datetime] = set()
    for message in messages:
        text = str(message.get("message") or "").strip().upper()
        if str(message.get("flag") or "").upper() != RED_FLAG and not text.startswith("RED FLAG"):
            continue
        moment = parse_iso(message.get("date"))
        if moment is not None:
            moments.add(moment)
    return tuple(sorted(moments))


def laps_in_progress(laps: list[dict], moments: tuple[datetime, ...]) -> RedFlagLaps:
    """Each car's lap in progress at each moment: the latest lap it had started.

    OpenF1 leaves lap 1's start undated, so a moment before any dated start
    falls on lap 1.
    """
    starts: dict[int, list[tuple[datetime, int]]] = {}
    for lap in laps:
        start = parse_iso(lap.get("date_start"))
        number, lap_number = lap.get("driver_number"), lap.get("lap_number")
        if start is None or number is None or lap_number is None:
            continue
        starts.setdefault(int(number), []).append((start, int(lap_number)))
    return {
        number: frozenset(max((lap for start, lap in rows if start <= moment), default=FIRST_LAP) for moment in moments)
        for number, rows in starts.items()
    }


def _stint(row: dict, driver: dict, red_flag_laps: frozenset[int]) -> Stint:
    start, end = int(row["lap_start"]), int(row["lap_end"])
    age = row.get("tyre_age_at_start")
    return Stint(
        driver_code=str(driver.get("name_acronym") or row["driver_number"]).strip().upper(),
        team=str(driver.get("team_name") or "").strip(),
        stint=int(row["stint_number"]),
        compound=clean_compound(row.get("compound")),
        start_lap=start,
        end_lap=end,
        laps=end - start + 1,
        tyre_life_start=None if age is None else int(age),
        fresh=None if age is None else int(age) == 0,
        ended_under_red_flag=end in red_flag_laps,
    )


def _same_set(previous: dict, row: dict) -> bool:
    """Whether ``row`` carries on the set ``previous`` ran: a pit-lane pass, not a tyre change.

    The set carried on when the compound is unchanged and the new row starts at
    the age the last one reached. An unrecorded age proves nothing either way,
    so it is left as a change.
    """
    if previous["driver_number"] != row["driver_number"] or previous.get("compound") != row.get("compound"):
        return False
    before, after = previous.get("tyre_age_at_start"), row.get("tyre_age_at_start")
    if before is None or after is None:
        return False
    return int(after) == int(before) + int(previous["lap_end"]) - int(previous["lap_start"]) + 1


def _merge_same_set(rows: list[dict]) -> list[dict]:
    """One row per tyre set, numbered from 1 for each driver."""
    merged: list[dict] = []
    for row in sorted(rows, key=lambda item: (item["driver_number"], item["stint_number"])):
        if merged and _same_set(merged[-1], row):
            merged[-1] = {**merged[-1], "lap_end": row["lap_end"]}
        else:
            merged.append(row)
    counts: dict[int, int] = {}
    numbered: list[dict] = []
    for row in merged:
        counts[row["driver_number"]] = counts.get(row["driver_number"], 0) + 1
        numbered.append({**row, "stint_number": counts[row["driver_number"]]})
    return numbered


def stints_from_openf1(rows: list[dict], drivers: dict[int, dict], red_flag_laps: RedFlagLaps) -> tuple[Stint, ...]:
    """OpenF1 stint rows as stints, one per tyre set, by driver then stint order."""
    required = ("driver_number", "stint_number", "lap_start", "lap_end")
    complete = [row for row in rows if all(row.get(field) is not None for field in required)]
    stints = [
        _stint(row, drivers.get(row["driver_number"], {}), red_flag_laps.get(row["driver_number"], frozenset()))
        for row in _merge_same_set(complete)
    ]
    return tuple(sorted(stints, key=lambda stint: (stint.driver_code, stint.stint)))


def _race_session_key(client: httpx.Client, year: int, round_num: int) -> int | None:
    race = find_session(client, year, round_num, "R")
    if race is None:
        logger.warning("openf1_stints.race_unmatched", year=year, round=round_num)
        return None
    return race.session_key


def _session_stints(client: httpx.Client, session_key: int) -> tuple[Stint, ...]:
    query = {"session_key": session_key}
    rows = get_json(client, "stints", query)
    if not rows:
        return ()
    drivers = {row["driver_number"]: row for row in get_json(client, "drivers", query) if "driver_number" in row}
    if not drivers:
        # Stored, a numbers-only answer would outlive the gap that caused it.
        raise OpenF1UnavailableError("drivers: no entry list for a session with stints")
    moments = red_flag_moments(get_json(client, "race_control", query))
    # Lap timings place a red flag and are the largest feed, so only then.
    red_flag_laps = laps_in_progress(get_json(client, "laps", query), moments) if moments else {}
    return stints_from_openf1(rows, drivers, red_flag_laps)


def openf1_race_stints(year: int, round_num: int) -> tuple[Stint, ...]:
    """Every tyre stint of a race, by driver then stint; empty when OpenF1 cannot say."""
    try:
        with new_client() as client:
            session_key = _race_session_key(client, year, round_num)
            stints = () if session_key is None else _session_stints(client, session_key)
    # The calendar lookup reaches FastF1's schedule backend, which raises
    # ValueError/KeyError for a bad season and OSError for a network failure.
    except (OpenF1UnavailableError, ValueError, KeyError, OSError) as exc:
        logger.warning("openf1_stints.unavailable", year=year, round=round_num, error=str(exc))
        return ()
    logger.info("openf1_stints.loaded", year=year, round=round_num, stints=len(stints))
    return stints
