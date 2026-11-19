"""The debrief's penalty timeline: the stewards' in-race penalties from race control, and the post-race ones.

In-race penalties are race control's "FIA STEWARDS" messages with their lap.
Race control's "PENALTY SERVED" message carries the leader's lap when it went
out, not the lap the car served on, so a penalty reads "served" with no lap.
Post-race penalties come from the FIA's final classification (the authority),
or from f1db's time penalties until the document lands.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.data.canonical_names import driver_identity
from app.data.fia_documents.results import final_classification
from app.data.openf1.client import get_json, new_client
from app.data.openf1.sessions import find_session
from app.services.race_results import build_session_result

if TYPE_CHECKING:
    from app.data.fia_documents.results import FinalClassification

_MESSAGE = re.compile(
    r"^FIA STEWARDS: (?P<served>PENALTY SERVED - )?(?P<penalty>.+? PENALTY) FOR CAR (?P<car>\d+) "
    r"\((?P<code>[A-Z]{3})\)(?: - (?P<offence>.+?))?(?: \((?P<at>\d{1,2}:\d{2}:\d{2})\))?$"
)
_IN_RACE_SECONDS = re.compile(r"(\d+) SECOND TIME PENALTY")
_RULING_SECONDS = re.compile(r"(\d+)\s+second\s+time\s+penalty", re.IGNORECASE)


def _empty() -> dict:
    return {"available": False, "in_race": [], "post_race": [], "fia_document": None}


def _served_keys(matches: list[re.Match[str]]) -> set[tuple[str, str]]:
    """What a "penalty served" message names: the car and the time of the ruling, or its text when it prints none."""
    return {(m["car"], m["at"] or m["penalty"]) for m in matches if m["served"]}


def _in_race(year: int, messages: list[dict]) -> list[dict]:
    parsed = [(message, _MESSAGE.match(message.get("message") or "")) for message in messages]
    matches = [(message, m) for message, m in parsed if m]
    served = _served_keys([m for _, m in matches])
    rows = []
    for message, m in matches:
        if m["served"]:
            continue
        seconds = _IN_RACE_SECONDS.search(m["penalty"])
        rows.append(
            {
                "lap": message.get("lap_number"),
                "car": int(m["car"]),
                "driver_code": m["code"],
                "driver_name": driver_identity(year, code=m["code"], number=m["car"]).name or m["code"],
                "penalty": m["penalty"].capitalize(),
                "seconds": int(seconds[1]) if seconds else None,
                "offence": m["offence"].capitalize() if m["offence"] else None,
                "served": (m["car"], m["at"] or m["penalty"]) in served,
            }
        )
    return sorted(rows, key=lambda row: row["lap"] or 0)


def _seconds(ruling: str) -> int | None:
    found = _RULING_SECONDS.search(ruling)
    return int(found[1]) if found else None


def _changes(race: dict | None) -> dict[str, dict]:
    return {row["driver_code"]: row for row in (race["changed_after_flag"] if race else [])}


def _post_race_fia(year: int, final: FinalClassification, changes: dict[str, dict]) -> list[dict]:
    names = {entry.car: entry.driver for entry in final.classification.entries}
    rows = []
    for note in final.classification.penalties:
        who = final.driver(year, note.car, names.get(note.car, ""))
        moved = changes.get(who.code)
        rows.append(
            {
                "driver_code": who.code,
                "driver_name": who.name,
                "car": note.car,
                "ruling": note.ruling,
                "seconds": _seconds(note.ruling),
                "reason": note.reason,
                "document": note.document,
                "road_position": moved["road_position"] if moved else None,
                "position": moved["position"] if moved else None,
            }
        )
    return sorted(rows, key=lambda row: (row["document"] is None, row["document"] or 0, row["car"]))


def _post_race_f1db(changes: dict[str, dict]) -> list[dict]:
    return [
        {
            "driver_code": code,
            "driver_name": row["driver_name"],
            "car": None,
            "ruling": f"{row['time_penalty']} second time penalty",
            "seconds": row["time_penalty"],
            "reason": None,
            "document": None,
            "road_position": row["road_position"],
            "position": row["position"],
        }
        for code, row in changes.items()
    ]


def build_debrief_penalties(year: int, round_num: int) -> dict:
    with new_client() as client:
        session = find_session(client, year, round_num, "R")
        if session is None:
            return _empty()
        messages = get_json(client, "race_control", {"session_key": session.session_key})
    in_race = _in_race(year, messages)
    final = final_classification(year, round_num, "race")
    changes = _changes(build_session_result(year, round_num, "race"))
    post_race = _post_race_f1db(changes) if final is None else _post_race_fia(year, final, changes)
    taken = {(row["driver_code"], row["seconds"]) for row in in_race if row["seconds"] is not None}
    return {
        "available": True,
        "in_race": in_race,
        "post_race": [row for row in post_race if (row["driver_code"], row["seconds"]) not in taken],
        "fia_document": None if final is None else {"number": final.classification.document, "url": final.url},
    }
