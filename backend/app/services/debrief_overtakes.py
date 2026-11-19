"""The debrief's position changes: OpenF1's ``/overtakes``, counted per overtaking car.

OpenF1 logs any exchange of places on track as an overtake, so the page labels
these "position changes". The rows are never stored by the OpenF1 read-through,
so a race that has ended and settled keeps them in the analysis cache.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from app.data.analysis_cache import analysis_cache
from app.data.openf1.client import get_json, new_client
from app.data.openf1.sessions import canonical_entry, entry_list, find_session, session_ended

if TYPE_CHECKING:
    import httpx

    from app.data.openf1.sessions import OpenF1Session

OVERTAKES_KIND = "race_overtakes"
OVERTAKES_VERSION = 1


def _unavailable() -> dict:
    return {"available": False, "total": 0, "drivers": []}


def _rows(client: httpx.Client, session: OpenF1Session, key: str) -> list[dict]:
    """The race's overtake rows, kept once the race has ended and settled."""
    kept = analysis_cache.get(OVERTAKES_KIND, key, OVERTAKES_VERSION)
    if kept is not None:
        return kept["rows"]
    rows = get_json(client, "overtakes", {"session_key": session.session_key})
    if rows and session_ended(session):
        analysis_cache.put(OVERTAKES_KIND, key, OVERTAKES_VERSION, {"rows": rows})
    return rows


def build_debrief_overtakes(year: int, round_num: int) -> dict:
    with new_client() as client:
        session = find_session(client, year, round_num, "R")
        rows = _rows(client, session, f"{year}:{round_num}") if session else []
        if not rows:
            return _unavailable()
        entries = entry_list(client, session.session_key)
    made = Counter(
        int(row["overtaking_driver_number"]) for row in rows if row.get("overtaking_driver_number") is not None
    )
    drivers = [
        {"driver_code": entry.code, "driver_name": entry.name, "team": entry.team, "made": count}
        for entry, count in ((canonical_entry(entries[n], year), count) for n, count in made.items() if n in entries)
    ]
    return {
        "available": True,
        "total": len(rows),
        "drivers": sorted(drivers, key=lambda row: (-row["made"], row["driver_code"])),
    }
