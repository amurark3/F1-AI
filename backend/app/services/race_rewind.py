"""Race Rewind: the order at the line after every lap, why each place changed, and the road order against the FIA's.

The OpenF1 ``position`` and ``overtakes`` streams are measured inputs the
read-through never stores, so a race that has ended and settled keeps them in
the analysis cache. The payload is derived on every call and never stored: the
classification can change when a late stewards' decision lands.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from app.data.analysis_cache import analysis_cache
from app.data.fia_documents.results import FIA_FINAL_SOURCE, final_classification
from app.data.openf1.client import get_json, new_client
from app.data.openf1.session_laps import load_session_laps
from app.data.openf1.sessions import canonical_entry, find_session, session_ended
from app.data.race_classification import NO_CLASSIFICATION, RaceClassification, race_classification
from app.data.race_neutralisations import lap_ranges
from app.services.debrief_overtakes import OVERTAKES_KIND, OVERTAKES_VERSION
from app.services.race_grid import SOURCE_OFFICIAL_GRID, build_starting_grid
from app.services.rewind_order import LapView, lap_changes, lap_orders, overtake_laps, real_stops, track_status

if TYPE_CHECKING:
    import httpx

    from app.data.openf1.laps import Lap
    from app.data.openf1.sessions import OpenF1Session

POSITIONS_KIND = "race_positions"
POSITIONS_VERSION = 1
NO_LAPS_REASON = "OpenF1 hasn't published this race's laps yet."
NO_POSITIONS_REASON = "OpenF1 hasn't published this race's positions yet."
FIA_GRID_SOURCE = "fia_starting_grid"
F1DB_GRID_SOURCE = "f1db"
OPENF1_GRID_SOURCE = "openf1-position"
_SECONDS = re.compile(r"(\d+)\s+second\s+time\s+penalty", re.IGNORECASE)


def _unavailable(year: int, round_num: int, reason: str) -> dict:
    return {
        "year": year,
        "round": round_num,
        "available": False,
        "reason": reason,
        "total_laps": 0,
        "drivers": [],
        "grid": None,
        "neutralisations": [],
        "stops": [],
        "laps": [],
        "final": None,
    }


class Stream(NamedTuple):
    """An OpenF1 endpoint and the analysis-cache kind and version its rows are kept under."""

    endpoint: str
    kind: str
    version: int


POSITIONS = Stream("position", POSITIONS_KIND, POSITIONS_VERSION)
OVERTAKES = Stream("overtakes", OVERTAKES_KIND, OVERTAKES_VERSION)


def _kept_rows(client: httpx.Client, session: OpenF1Session, stream: Stream, key: str) -> list[dict]:
    """One OpenF1 stream, kept in the analysis cache once the race has ended and settled."""
    kept = analysis_cache.get(stream.kind, key, stream.version)
    if kept is not None:
        return kept["rows"]
    rows = get_json(client, stream.endpoint, {"session_key": session.session_key})
    if rows and session_ended(session):
        analysis_cache.put(stream.kind, key, stream.version, {"rows": rows})
    return rows


def _penalties(year: int, round_num: int) -> tuple[dict[str, list[dict]], dict | None]:
    """The FIA classification's penalty notes by driver code, and its document number and URL."""
    final = final_classification(year, round_num, "race")
    if final is None:
        return {}, None
    printed = {entry.car: entry.driver for entry in final.classification.entries}
    notes: dict[str, list[dict]] = {}
    for note in final.classification.penalties:
        code = final.driver(year, note.car, printed.get(note.car, "")).code
        found = _SECONDS.search(note.ruling)
        seconds = int(found[1]) if found else None
        notes.setdefault(code, []).append({"ruling": note.ruling, "seconds": seconds, "document": note.document})
    return notes, {"document": final.classification.document, "url": final.url}


def _grid(year: int, round_num: int, positions: list[dict], codes: dict[int, str]) -> dict:
    """The official grid when it is final; otherwise each car's first OpenF1 place."""
    official = build_starting_grid(year, round_num)
    if official["available"] and not official["provisional"]:
        slotted = sorted((r for r in official["grid"] if not r["pit_lane"]), key=lambda r: r["position"])
        pit_lane = [r["driver_code"] for r in official["grid"] if r["pit_lane"]]
        document = official["fia_document"]
        return {
            "order": [r["driver_code"] for r in slotted] + pit_lane,
            "pit_lane": pit_lane,
            "source": F1DB_GRID_SOURCE if official["source"] == SOURCE_OFFICIAL_GRID else FIA_GRID_SOURCE,
            "document": document["number"] if document else None,
        }
    first: dict[int, int] = {}
    for row in sorted(positions, key=lambda r: r["date"]):
        first.setdefault(int(row["driver_number"]), int(row["position"]))
    order = [codes[n] for n in sorted((n for n in first if n in codes), key=lambda n: first[n])]
    return {"order": order, "pit_lane": [], "source": OPENF1_GRID_SOURCE, "document": None}


def _final(year: int, round_num: int, classification: RaceClassification, orders: list[list[str]]) -> dict | None:
    if classification is NO_CLASSIFICATION:
        return None
    fia = classification.source == FIA_FINAL_SOURCE
    notes, document = _penalties(year, round_num) if fia else ({}, None)
    rows = []
    for driver in classification.drivers:
        code = driver.driver_code
        lap = next((i for i in range(len(orders) - 1, -1, -1) if code in orders[i]), None)
        rows.append(
            {
                "driver_code": code,
                "position": driver.position,
                "status": driver.status,
                "laps": driver.laps_completed,
                "road_position": None if lap is None else orders[lap].index(code) + 1,
                "penalties": notes.get(code, []),
            }
        )
    return {
        "source": classification.source,
        "provisional": not fia,
        "document": document["document"] if document else None,
        "url": document["url"] if document else None,
        "rows": rows,
    }


def _lap_rows(orders: list[list[str]], grid: list[str], ranges: list[dict], why: tuple[dict, dict]) -> list[dict]:
    stops, passes = why
    rows = []
    for lap, order in enumerate(orders, start=1):
        status = track_status(ranges, lap)
        previous = orders[lap - 2] if lap > 1 else grid
        changes = lap_changes(LapView(lap, previous, order, stops, passes.get(lap, set()), status))
        rows.append({"lap": lap, "order": order, "track": status, "changes": changes})
    return rows


def _drivers(entries: dict, classification: RaceClassification) -> list[dict]:
    by_code = {d.driver_code: d for d in classification.drivers}
    rows = []
    for number, entry in sorted(entries.items()):
        found = by_code.get(entry.code)
        rows.append(
            {
                "car": number,
                "driver_code": entry.code,
                "driver_name": entry.name,
                "team": entry.team,
                "status": found.status if found else None,
                "laps": found.laps_completed if found else None,
            }
        )
    return rows


def _streams(client: httpx.Client, found: OpenF1Session, year: int, round_num: int) -> tuple[list, list, list]:
    key = f"{year}:{round_num}"
    positions = _kept_rows(client, found, POSITIONS, key)
    if not positions:
        return [], [], []
    overtakes = _kept_rows(client, found, OVERTAKES, key)
    return positions, overtakes, get_json(client, "pit", {"session_key": found.session_key})


def _orders(laps: tuple[Lap, ...], positions: list[dict], codes: dict[int, str], finishers: set[str]) -> list:
    numbers = {n for n, code in codes.items() if code in finishers}
    return [[codes[n] for n in order] for order in lap_orders(laps, positions, numbers)]


def build_race_rewind(year: int, round_num: int) -> dict:
    session = load_session_laps(year, round_num, "R")
    if session is None or not session.laps:
        return _unavailable(year, round_num, NO_LAPS_REASON)
    with new_client() as client:
        found = find_session(client, year, round_num, "R")
        positions, overtakes, pit = _streams(client, found, year, round_num) if found else ([], [], [])
    if not positions:
        return _unavailable(year, round_num, NO_POSITIONS_REASON)
    entries = {number: canonical_entry(entry, year) for number, entry in session.drivers.items()}
    codes = {number: entry.code for number, entry in entries.items()}
    classification = race_classification(year, round_num)
    finishers = {d.driver_code for d in classification.drivers if d.status == "finished"}
    laps = tuple(lap for lap in session.laps if lap.driver in codes)
    orders = _orders(laps, positions, codes, finishers)
    stops = real_stops(pit, codes)
    by_driver: dict[str, list[int]] = {}
    for code, lap in stops:
        by_driver.setdefault(code, []).append(lap)
    grid = _grid(year, round_num, positions, codes)
    ranges = lap_ranges(session.laps, session.windows)
    return {
        "year": year,
        "round": round_num,
        "available": True,
        "reason": None,
        "total_laps": len(orders),
        "drivers": _drivers(entries, classification),
        "grid": grid,
        "neutralisations": ranges,
        "stops": [{"driver_code": code, "lap": lap} for code, lap in stops],
        "laps": _lap_rows(orders, grid["order"], ranges, (by_driver, overtake_laps(overtakes, laps, codes))),
        "final": _final(year, round_num, classification, orders),
    }
