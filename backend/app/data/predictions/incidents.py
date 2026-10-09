"""Retirement and incident history used to score reliability risk.

Classifies a race status string into DNF/crash/mechanical flags and rolls those
up into a per-driver incident profile over recent rounds.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()

# year -> {round: {driver_code: retirement reason or None}} — loaded once
_season_retirements_cache: dict[int, dict[int, dict[str, str | None]]] = {}

# (driver_code, year, round_num) -> recent incident profile
_incident_cache: dict[tuple[str, int, int], dict[str, Any]] = {}


def _classify_status(status: str) -> dict[str, bool]:
    text = status.lower()
    classified = bool(text) and "finished" not in text and "lap" not in text
    crash_terms = ("accident", "collision", "crash", "spun", "damage")
    mechanical_terms = (
        "engine",
        "gearbox",
        "hydraul",
        "electrical",
        "brake",
        "power unit",
        "transmission",
        "suspension",
        "overheating",
        "oil",
        "water",
        "fuel",
    )
    return {
        "dnf": classified,
        "crash": any(term in text for term in crash_terms),
        "mechanical": any(term in text for term in mechanical_terms),
    }


def _season_retirements(year: int) -> dict[int, dict[str, str | None]]:
    """Return ``{round: {driver_code: retirement reason or None}}`` for a season.

    Loaded once per season from f1db and cached.
    """
    cached = _season_retirements_cache.get(year)
    if cached is not None:
        return cached

    from app.data.f1db_results import race_retirements, race_schedule

    cached = {}
    try:
        for event in race_schedule(year):
            round_num = int(event["round"])
            statuses = race_retirements(year, round_num)
            if statuses:
                cached[round_num] = statuses
    except Exception as exc:
        logger.warning("predictions.season_retirements_error", year=year, error=str(exc))

    _season_retirements_cache[year] = cached
    return cached


def _load_recent_incidents(driver_code: str, year: int, current_round: int) -> dict[str, Any]:
    """Return recent DNF/crash profile for a driver across current and prior season."""
    cache_key = (driver_code, year, current_round)
    if cache_key in _incident_cache:
        return _incident_cache[cache_key]

    starts = 0
    dnfs = 0
    crashes = 0
    mechanical = 0
    statuses: list[str] = []

    def _accumulate(season: int, before_round: int | None) -> None:
        nonlocal starts, dnfs, crashes, mechanical
        results = _season_retirements(season)
        for round_num in sorted(results):
            if before_round is not None and round_num >= before_round:
                continue
            if driver_code not in results[round_num]:
                continue
            starts += 1
            reason = results[round_num][driver_code]
            if not reason:  # classified finisher — no retirement
                continue
            flags = _classify_status(reason)
            if flags["dnf"]:
                dnfs += 1
                statuses.append(reason)
            if flags["crash"]:
                crashes += 1
            if flags["mechanical"]:
                mechanical += 1

    try:
        _accumulate(year, current_round)  # this season, before the current round
        _accumulate(year - 1, None)  # plus the whole prior season
    except Exception as exc:
        logger.warning("predictions.incident_history_error", driver=driver_code, error=str(exc))

    profile = {
        "starts": starts,
        "dnfs": dnfs,
        "crashes": crashes,
        "mechanical": mechanical,
        "dnf_rate": dnfs / starts if starts else 0.08,
        "crash_rate": crashes / starts if starts else 0.03,
        "mechanical_rate": mechanical / starts if starts else 0.04,
        "recent_statuses": statuses[-3:],
    }
    _incident_cache[cache_key] = profile
    return profile
