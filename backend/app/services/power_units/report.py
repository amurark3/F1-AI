"""Assemble the power-unit screen's payload for one season.

Pipeline: stored corpus → evidence (:mod:`.evidence`) → seats (:mod:`.seats`)
→ one ledger per car (:mod:`.ledger`) → this payload, with each round's grid
outcome joined from f1db's published grid sheet, the allowances read from the
shared store, and the freshness and provenance lines of :mod:`.provenance`.

The payload is cached for a few minutes. The corpus only changes when the
ingest job runs, and every rebuild re-reads the whole season from the store —
cheap, but not something to repeat on every page view.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import threading
import time
from typing import TYPE_CHECKING

import structlog

from app.data.f1db_grid import starting_grid
from app.data.power_units.allowances import load_allowances
from app.data.power_units.elements import SUPPORTED_SEASONS, elements_for
from app.data.power_units.season_context import load_season_context
from app.data.power_units.sources import load_season
from app.services.power_units.evidence import gather_evidence
from app.services.power_units.ledger import (
    STATUS_NOT_FOUND,
    STATUS_PENDING,
    Season,
    SeatLedger,
    build_seat_ledger,
)
from app.services.power_units.provenance import allowance_warnings, element_payload, freshness
from app.services.power_units.seats import assign_seats

if TYPE_CHECKING:
    from app.data.f1db_grid import GridSlot
    from app.data.power_units.allowances import AllowanceEntry
    from app.data.power_units.season_context import SeasonContext, SeasonRound
    from app.services.power_units.evidence import DecisionEvidence, Evidence
    from app.services.power_units.ledger import RoundActivity
    from app.services.power_units.seats import Occupant, SeatMap

logger = structlog.get_logger()

CACHE_TTL_SECONDS = 300

GRID_OFFICIAL = "official"
GRID_PENDING = "pending"
GRID_NOT_LISTED = "not_listed"

NOTES = (
    "Each allowance is the latest figure the FIA's own reports state (\"the fifth (5th) of the four (4) new … "
    'allowed"), kept in the shared store; one pinned by hand is marked as such.',
    "Usage is counted per car: a stand-in uses, and adds to, the allocation of the car they drive (Article B8.2.7).",
    "Every count and penalty is read from the FIA Technical Delegate's reports and the stewards' decisions. "
    "Grid outcomes come from the published starting grid.",
    "A document the FIA withdraws, rescinds or replaces stops counting, and is listed below with the reason.",
)

_cache: dict[int, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(UTC)


def _unavailable(year: int, reason: str, fresh: dict | None = None) -> dict:
    return {
        "year": year,
        "available": False,
        "reason": reason,
        "freshness": fresh,
        "cars": [],
        "unread": [],
        "withdrawn": [],
        "warnings": [],
    }


@dataclass(frozen=True)
class _Build:
    """Everything one payload is assembled from."""

    context: SeasonContext
    evidence: Evidence
    seat_map: SeatMap
    season: Season
    allowances: dict[str, AllowanceEntry]
    freshness: dict


def _occupant_at(seat_map: SeatMap, seat_id: str, round_num: int) -> Occupant | None:
    """Who raced the seat at ``round_num`` — or, for a round f1db has not
    published yet, the last driver it records in the seat."""
    occupants = seat_map.occupants[seat_id]
    exact = next((item for item in occupants if item.round == round_num), None)
    if exact is not None:
        return exact
    earlier = [item for item in occupants if item.round <= round_num]
    return earlier[-1] if earlier else None


def _grid(slots: tuple[GridSlot, ...], driver_code: str | None) -> dict:
    if not slots:
        return {"status": GRID_PENDING}
    slot = next((item for item in slots if item.driver_code == driver_code), None)
    if slot is None:
        return {"status": GRID_NOT_LISTED}
    return {
        "status": GRID_OFFICIAL,
        "qualified": slot.qualifying_position,
        "started": slot.position,
        "pit_lane": slot.pit_lane,
        "back_of_grid": slot.start_from_back,
        "penalty_positions": slot.penalty_positions,
    }


def _decision(item: DecisionEvidence) -> dict:
    decision = item.decision
    return {
        **item.ref.as_dict(),
        "session": decision.session,
        "outcome": decision.outcome,
        "places": decision.places,
        "nominal_places": decision.nominal_places,
        "summary": decision.summary,
        "elements": [{"code": code, "number": number} for code, number in item.elements],
    }


def _round_payload(activity: RoundActivity, occupant: Occupant | None, current: Occupant, grid: dict) -> dict:
    """One round of one car; ``occupant`` is ``None`` for a round before f1db's first."""
    return {
        "round": activity.round,
        "driver": occupant.as_dict() if occupant else None,
        "stand_in": occupant is not None and occupant.driver_id != current.driver_id,
        "new_parts": [part.as_dict() for part in activity.new_parts],
        "decisions": [_decision(item) for item in activity.decisions],
        "penalty_status": activity.penalty_status,
        "grid": grid,
        "sources": [ref.as_dict() for ref in activity.sources],
    }


def _drivers(seat_map: SeatMap, seat_id: str) -> list[dict]:
    """Everyone who raced the car, with the rounds they raced it."""
    drivers: dict[str, dict] = {}
    for occupant in seat_map.occupants[seat_id]:
        entry = drivers.setdefault(occupant.driver_id, {**occupant.as_dict(), "rounds": []})
        entry["rounds"].append(occupant.round)
    return list(drivers.values())


def _totals(rounds: list[dict]) -> dict:
    decisions = [decision for item in rounds for decision in item["decisions"]]
    return {
        "grid_places": sum(item["places"] or 0 for item in decisions if item["outcome"] == "grid_drop"),
        "pit_lane_starts": sum(1 for item in decisions if item["outcome"] == "pit_lane"),
        "back_of_grid": sum(1 for item in decisions if item["outcome"] == "back_of_grid"),
        "decisions": len(decisions),
        "pending": sum(1 for item in rounds if item["penalty_status"] == STATUS_PENDING),
        "not_found": sum(1 for item in rounds if item["penalty_status"] == STATUS_NOT_FOUND),
    }


def _car(ledger: SeatLedger, build: _Build, grids: dict[int, tuple[GridSlot, ...]]) -> dict:
    seat = ledger.seat
    # Every seat is seeded from an f1db round, so it has at least that occupant.
    current = build.seat_map.occupants[seat.seat_id][-1]
    rounds = []
    for activity in ledger.rounds:
        occupant = _occupant_at(build.seat_map, seat.seat_id, activity.round)
        if activity.round not in grids:
            grids[activity.round] = starting_grid(build.context.year, activity.round)
        grid = _grid(grids[activity.round], occupant.driver_code if occupant else None)
        rounds.append(_round_payload(activity, occupant, current, grid))
    return {
        "seat_id": seat.seat_id,
        "car_number": current.car_number,
        "team": seat.team,
        "team_id": seat.constructor_id,
        "driver": current.as_dict(),
        "drivers": _drivers(build.seat_map, seat.seat_id),
        "elements": [
            {
                "code": element.code,
                "allowance": element.allowance,
                "used": element.used,
                "over_by": element.over_by,
                "parts": [part.as_dict() for part in element.parts],
            }
            for element in ledger.elements
        ],
        "events": rounds,
        "penalties": _totals(rounds),
        "warnings": list(ledger.warnings),
    }


def _round_info(item: SeasonRound, evidence: Evidence) -> dict:
    return {
        "round": item.round,
        "name": item.name,
        "code": item.code,
        "date": item.race_day.isoformat(),
        "has_documents": item.round in evidence.rounds(),
    }


def _payload(year: int, build: _Build) -> dict:
    grids: dict[int, tuple[GridSlot, ...]] = {}
    ledgers = [build_seat_ledger(seat, build.evidence, build.seat_map, build.season) for seat in build.seat_map.seats]
    cars = sorted(
        (_car(ledger, build, grids) for ledger in ledgers),
        key=lambda car: (-sum(element["over_by"] for element in car["elements"]), car["car_number"]),
    )
    latest = build.evidence.latest
    return {
        "year": year,
        "available": True,
        "reason": None,
        "as_of": {"round": latest[0], **latest[1].as_dict()} if latest else None,
        "freshness": build.freshness,
        "elements": element_payload(year, build.allowances),
        "rounds": [_round_info(item, build.evidence) for item in build.context.rounds],
        "cars": cars,
        "unread": [item.as_dict() for item in build.evidence.unread],
        "withdrawn": [item.as_dict() for item in build.evidence.withdrawn],
        "warnings": [*build.seat_map.warnings, *allowance_warnings(build.evidence, build.allowances)],
        "notes": list(NOTES),
    }


def _build(year: int) -> dict:
    if year not in SUPPORTED_SEASONS:
        return _unavailable(year, f"Power-unit elements for {year} have not been read from its regulations yet.")
    sources = load_season(year)
    fresh = freshness(year, sources.updated_at, _now())
    if not sources.documents:
        return _unavailable(year, f"No FIA power-unit documents have been collected for {year} yet.", fresh)

    context = load_season_context(year)
    evidence = gather_evidence(sources, context)
    seat_map = assign_seats(context, evidence)
    if not seat_map.seats:
        return _unavailable(year, f"No {year} line-up is known yet, so no car can be identified.", fresh)
    allowances = load_allowances(year)
    season = Season(
        codes=tuple(element.code for element in elements_for(year)),
        allowance={code: entry.allowance for code, entry in allowances.items()},
        rounds=tuple(item.round for item in context.rounds),
        latest_round=evidence.latest[0] if evidence.latest else None,
    )
    build = _Build(context, evidence, seat_map, season, allowances, fresh)
    return _payload(year, build)


def build_power_units(year: int) -> dict:
    """The season's power-unit payload, rebuilt at most every few minutes."""
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(year)
        if cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
    payload = _build(year)
    with _cache_lock:
        _cache[year] = (now, payload)
    logger.info("power_units.built", year=year, available=payload["available"], cars=len(payload["cars"]))
    return payload


def clear_cache() -> None:
    """Drop every cached payload — for tests, and after a manual ingest."""
    with _cache_lock:
        _cache.clear()
