"""The official classification of a round's Grand Prix, and its sprint, for the Results tab.

**Authority** (``docs/DATA_SOURCES.md``): the FIA final classification, which f1db
mirrors, so a session f1db holds is ``final``. Until f1db has it, OpenF1's
``session_result`` answers, marked provisional. Jolpica is never used here: it
still showed the pre-penalty order the morning after Mexico 2026.

**Special states** read the same words as every other tab: ``Finished``, ``DNF``,
``NC``, ``DNS``, ``DSQ``. A car that is not ``Finished`` has no ``position``,
whatever place the source lists it at.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

import structlog

from app.data.canonical_names import F1DB_READ_ERRORS, driver_identity, team_display_name
from app.data.f1db_grid import starting_grid
from app.data.f1db_race_results import TYPE_RACE, TYPE_SPRINT, ResultRow, fastest_lap, result_rows
from app.data.f1db_source import installed_version
from app.data.race_classification import openf1_session_result, openf1_status

logger = structlog.get_logger()

F1DB_SOURCE = "f1db"
OPENF1_SOURCE = "openf1-session-result"

# f1db's position_text for a car with no classified place. Any other word
# (a car that never qualified) did not start; a word f1db adds later reads NC.
STATUS_BY_TEXT = {"DNF": "DNF", "NC": "NC", "DNS": "DNS", "DSQ": "DSQ", "EX": "DSQ", "DNQ": "DNS", "DNPQ": "DNS"}
OPENF1_STATUS = {"finished": "Finished", "dnf": "DNF", "dns": "DNS", "dsq": "DSQ", "not_classified": "NC"}
# Row order: classified cars, then NC, then DNF by laps, then DNS, then DSQ.
STATUS_ORDER = {"Finished": 0, "NC": 1, "DNF": 2, "DNS": 3, "DSQ": 4}
# kind -> (f1db result type, OpenF1 session code)
SESSION_KINDS = {"race": (TYPE_RACE, "R"), "sprint": (TYPE_SPRINT, "S")}
OPENF1_LAPS_DOWN = re.compile(r"\+(\d+)\s*LAPS?", re.IGNORECASE)


@dataclass(frozen=True)
class _Car:
    """One car's result in a source-neutral shape."""

    code: str
    name: str
    team: str
    status: str
    position: int | None
    laps: int | None
    time_millis: int | None
    gap: str | None
    laps_down: int | None
    penalty_millis: int | None
    reason: str | None
    points: float | None
    fastest_lap: bool


def clock(millis: int) -> str:
    """Milliseconds as ``h:mm:ss.mmm``, or ``m:ss.mmm`` / ``s.mmm`` under an hour / minute."""
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    if hours:
        return f"{hours}:{minutes:02d}:{rest / 1000:06.3f}"
    return f"{minutes}:{rest / 1000:06.3f}" if minutes else f"{rest / 1000:.3f}"


def _status(row: ResultRow) -> str:
    return "Finished" if row.position is not None else STATUS_BY_TEXT.get(row.position_text, "NC")


def _f1db_car(row: ResultRow) -> _Car:
    return _Car(
        code=row.code,
        name=row.name,
        team=row.team,
        status=_status(row),
        position=row.position,
        laps=row.laps,
        time_millis=row.time_millis,
        gap=row.gap,
        laps_down=row.gap_laps,
        penalty_millis=row.penalty_millis,
        reason=row.reason,
        # f1db leaves a car that scored nothing blank: a final result's zero is a fact.
        points=row.points or 0,
        fastest_lap=row.fastest_lap,
    )


def _openf1_gap(value: object) -> tuple[str | None, int | None]:
    """OpenF1's ``gap_to_leader`` (seconds, or ``"+1 LAP"``) as f1db's gap text and laps down."""
    if isinstance(value, str):
        lapped = OPENF1_LAPS_DOWN.fullmatch(value.strip())
        return (f"+{lapped[1]} lap" if lapped else None), (int(lapped[1]) if lapped else None)
    if isinstance(value, int | float) and value > 0:
        return f"+{clock(round(value * 1000))}", None
    return None, None


def _openf1_car(year: int, row: dict, entries: dict) -> _Car:
    entry = entries.get(int(row["driver_number"]))
    who = driver_identity(year, code=entry and entry.code, number=row["driver_number"], name=entry and entry.name)
    gap, laps_down = _openf1_gap(row.get("gap_to_leader"))
    duration = row.get("duration")
    status = OPENF1_STATUS[openf1_status(row)]
    return _Car(
        code=who.code or str(row["driver_number"]),
        name=who.name,
        team=team_display_name(year, entry.team if entry else None),
        status=status,
        position=int(row["position"]) if status == "Finished" else None,
        laps=row.get("number_of_laps"),
        time_millis=round(duration * 1000) if isinstance(duration, int | float) else None,
        gap=gap,
        laps_down=laps_down,
        # OpenF1 does not say which time penalties its durations include.
        penalty_millis=None,
        reason=None,
        points=row.get("points"),
        fastest_lap=False,
    )


def _road_positions(cars: list[_Car]) -> dict[str, int]:
    """Each timed, classified car's place before time penalties: the order of race time minus penalty."""
    timed = [car for car in cars if car.status == "Finished" and car.time_millis is not None]
    ordered = sorted(timed, key=lambda car: car.time_millis - (car.penalty_millis or 0))
    return {car.code: index for index, car in enumerate(ordered, start=1)}


def _penalty_seconds(car: _Car) -> int | float | None:
    if not car.penalty_millis:
        return None
    seconds = car.penalty_millis / 1000
    return int(seconds) if seconds.is_integer() else seconds


def _who(year: int, code: str, name: str, team: str) -> dict:
    who = driver_identity(year, code=code, name=name)
    return {"driver_code": who.code or code, "driver_name": who.name, "team": team_display_name(year, team)}


def _row(year: int, car: _Car, road: dict[str, int]) -> dict:
    # The winner carries the race time and every other car its gap; a lapped
    # car has only its gap and the laps it is down.
    return {
        **_who(year, car.code, car.name, car.team),
        "position": car.position,
        "status": car.status,
        "reason": car.reason,
        "laps": car.laps,
        "time": clock(car.time_millis) if car.position == 1 and car.time_millis is not None else None,
        "gap": None if car.position == 1 else car.gap,
        "laps_down": car.laps_down,
        "time_penalty": _penalty_seconds(car),
        "road_position": road.get(car.code) if car.penalty_millis else None,
        "points": car.points,
        "fastest_lap": car.fastest_lap,
    }


def _passed(year: int, car: _Car, cars: list[_Car], road: dict[str, int]) -> list[dict]:
    """The cars that were behind ``car`` on the road and are classified ahead of it."""
    return [
        {
            **_who(year, other.code, other.name, other.team),
            "road_position": road[other.code],
            "position": other.position,
        }
        for other in cars
        if other.code in road and road[other.code] > road[car.code] and (other.position or 0) < (car.position or 0)
    ]


def _changed_after_flag(year: int, cars: list[_Car], road: dict[str, int]) -> list[dict]:
    """Each time penalty that moved a car: its road place, its classified place, and who it let past."""
    return [
        {
            **_who(year, car.code, car.name, car.team),
            "road_position": road[car.code],
            "position": car.position,
            "time_penalty": _penalty_seconds(car),
            "moved_up": _passed(year, car, cars, road),
        }
        for car in cars
        if car.penalty_millis and car.code in road and road[car.code] != car.position
    ]


def _session(year: int, cars: list[_Car], provenance: dict, fastest: dict | None) -> dict:
    ordered = sorted(cars, key=lambda car: (STATUS_ORDER[car.status], car.position or 0, -(car.laps or 0)))
    road = _road_positions(ordered)
    return {
        **provenance,
        "classification": [_row(year, car, road) for car in ordered],
        "changed_after_flag": _changed_after_flag(year, ordered, road),
        "fastest_lap": fastest,
    }


def _fastest(year: int, round_num: int) -> dict | None:
    lap = fastest_lap(year, round_num)
    if lap is None:
        return None
    return {**_who(year, lap.code, lap.name, lap.team), "lap": lap.lap, "time": lap.time}


def _from_f1db(year: int, round_num: int, result_type: str) -> dict | None:
    rows = result_rows(year, round_num, result_type)
    if not rows:
        return None
    provenance = {
        "final": True,
        "sources": [{"source": F1DB_SOURCE, "role": "classification", "version": installed_version()}],
    }
    fastest = _fastest(year, round_num) if result_type == TYPE_RACE else None
    return _session(year, [_f1db_car(row) for row in rows], provenance, fastest)


def _from_openf1(year: int, round_num: int, code: str) -> dict | None:
    rows, entries = openf1_session_result(year, round_num, code)
    if not rows:
        return None
    cars = [_openf1_car(year, row, entries) for row in rows if row.get("driver_number") is not None]
    provenance = {"final": False, "sources": [{"source": OPENF1_SOURCE, "role": "classification"}]}
    return _session(year, cars, provenance, None)


def _best(year: int, round_num: int, result_type: str, openf1_code: str) -> dict | None:
    return _from_f1db(year, round_num, result_type) or _from_openf1(year, round_num, openf1_code)


def build_session_result(year: int, round_num: int, kind: str) -> dict | None:
    """One session's classification (``kind`` "race" or "sprint"), or ``None`` when no source holds it."""
    result_type, openf1_code = SESSION_KINDS[kind]
    return _best(year, round_num, result_type, openf1_code)


def official_grid(year: int, round_num: int) -> dict[str, int | None]:
    """Each car's slot on f1db's published race grid (``None`` for a pit-lane start); empty until f1db holds it.

    A grid built from the qualifying order is not read: it knows no penalties,
    so a place "gained" against it would be invented.
    """
    try:
        return {slot.driver_code: slot.position for slot in starting_grid(year, round_num)}
    except F1DB_READ_ERRORS as exc:
        logger.warning("race_results.grid_unreadable", year=year, round=round_num, error=str(exc))
        return {}


def build_race_results(year: int, round_num: int) -> dict:
    """The round's race and sprint classifications; a session the round lacks is ``None``."""
    race = build_session_result(year, round_num, "race")
    sprint = build_session_result(year, round_num, "sprint")
    logger.info("race_results.built", year=year, round=round_num, race=race is not None, sprint=sprint is not None)
    return {"year": year, "round": round_num, "race": race, "sprint": sprint}
