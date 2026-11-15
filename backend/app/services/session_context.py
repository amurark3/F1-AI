"""What a session table needs beyond f1db's rows: the part each car ran in, and who a stand-in drove for.

Both are derived from the same rows the payload already holds, so nothing here
reads a second source.

Qualifying
    A car's *part* is the last of Q1/Q2/Q3 it set a time in. Its gap is measured
    inside that part (the official figure), never against a lap from another
    part. A car classified inside the band of a higher part it did not run in was
    lifted there by a disqualification, and ``promoted_by`` names the cars.

Practice
    A driver who is not on the weekend's race entry list is a stand-in, and the
    regular driver of that team missing from the session is whose car it was.
"""

from __future__ import annotations

PARTS = ("q3", "q2", "q1")
DSQ_TEXT = "DSQ"


def time_ms(text: str) -> int:
    """``m:ss.sss`` in milliseconds."""
    minutes, seconds = text.split(":")
    return round((int(minutes) * 60 + float(seconds)) * 1000)


def _part(entry: dict) -> str | None:
    return next((part for part in PARTS if entry.get(part)), None)


def _fastest_by_part(entries: list[dict]) -> dict[str, int]:
    """The fastest classified lap in each part, whichever part its driver was classified in."""
    best: dict[str, int] = {}
    for entry in entries:
        if entry["position_text"] == DSQ_TEXT:
            continue
        for part in PARTS:
            if entry.get(part):
                best[part] = min(best.get(part, 10**9), time_ms(entry[part]))
    return best


def _gap(entry: dict, part: str | None, best: dict[str, int]) -> str | None:
    if part is None or entry["position_text"] == DSQ_TEXT:
        return None
    behind = time_ms(entry[part]) - best[part]
    return f"+{behind / 1000:.3f}" if behind else None


def _promoted_by(entry: dict, part: str | None, entries: list[dict], parts: list[str | None]) -> list[str]:
    """The disqualified cars that ran in a higher part and lifted this one into its band."""
    position = entry["position"]
    if position is None or part is None:
        return []
    dsq_codes = [
        other["driver_code"]
        for other, other_part in zip(entries, parts, strict=True)
        if other["position_text"] == DSQ_TEXT and other_part is not None and PARTS.index(other_part) < PARTS.index(part)
    ]
    if not dsq_codes:
        return []
    ran_higher = sum(
        1 for other_part in parts if other_part is not None and PARTS.index(other_part) < PARTS.index(part)
    )
    return dsq_codes if position <= ran_higher else []


def annotate_qualifying(entries: list[dict]) -> list[dict]:
    """Each qualifying row plus ``part`` (``q1``/``q2``/``q3``), ``part_gap`` and ``promoted_by``."""
    parts = [_part(entry) for entry in entries]
    best = _fastest_by_part(entries)
    return [
        {
            **entry,
            "part": part,
            "part_gap": _gap(entry, part, best),
            "promoted_by": _promoted_by(entry, part, entries, parts),
        }
        for entry, part in zip(entries, parts, strict=True)
    ]


def annotate_stand_ins(entries: list[dict], regulars: dict[str, list[tuple[str, str]]]) -> list[dict]:
    """Each practice row plus ``stand_in_for``: the regular driver whose car it was, or ``None``."""
    regular_codes = {code for drivers in regulars.values() for code, _ in drivers}
    if not regular_codes:
        return [{**entry, "stand_in_for": None} for entry in entries]
    ran = {entry["driver_code"] for entry in entries}
    absent = {team: [driver for driver in drivers if driver[0] not in ran] for team, drivers in regulars.items()}
    annotated = []
    for entry in entries:
        owner = None
        if entry["driver_code"] not in regular_codes and absent.get(entry["team"]):
            code, name = absent[entry["team"]].pop(0)
            owner = {"driver_code": code, "driver_name": name}
        annotated.append({**entry, "stand_in_for": owner})
    return annotated
