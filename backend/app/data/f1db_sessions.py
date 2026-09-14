"""Practice, sprint qualifying and sprint race classifications from f1db.

A Grand Prix weekend is not one session, and which sessions it has is a
property of the weekend rather than a constant. A conventional weekend runs
three practice sessions; a sprint weekend runs one, then sprint qualifying, the
sprint itself, and only then Grand Prix qualifying. f1db records each under its
own ``race_data.type``, so the set of rows that exist for a round *is* the
weekend's format — no calendar flag has to be trusted, and a format change in a
future season needs no code change here.

Three column families carry the classifications, and they do not overlap:

``practice_*``
    ``practice_time`` is the session's best lap, with ``practice_gap`` to the
    fastest driver and ``practice_laps`` as the tour count. A practice session
    has no points and no retirements.
``qualifying_*``
    ``qualifying_q1/q2/q3`` hold each segment's time. Sprint qualifying is a
    three-segment session like Grand Prix qualifying.
``race_*``
    ``race_time`` is the winner's total and an interval for everyone else,
    alongside points, laps, the grid slot started from, and a retirement
    reason for anyone who did not finish.

Availability follows the f1db release cadence: a round's sessions land together
once the round is complete, so a weekend still being run returns nothing here.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.data.f1db_source import connect

logger = structlog.get_logger()

TYPE_PRACTICE_1 = "FREE_PRACTICE_1_RESULT"
TYPE_PRACTICE_2 = "FREE_PRACTICE_2_RESULT"
TYPE_PRACTICE_3 = "FREE_PRACTICE_3_RESULT"
TYPE_SPRINT_QUALIFYING = "SPRINT_QUALIFYING_RESULT"
TYPE_SPRINT_RACE = "SPRINT_RACE_RESULT"

#: How a session is classified, which decides the columns that carry meaning.
KIND_PRACTICE = "practice"
KIND_QUALIFYING = "qualifying"
KIND_RACE = "race"

_SESSION_QUERY = """
    SELECT rd.position_number AS position,
           rd.position_text AS position_text,
           d.abbreviation AS code,
           d.name AS name,
           con.name AS team,
           rd.practice_time AS practice_time,
           rd.practice_gap AS practice_gap,
           rd.practice_laps AS practice_laps,
           rd.qualifying_q1 AS q1,
           rd.qualifying_q2 AS q2,
           rd.qualifying_q3 AS q3,
           rd.qualifying_gap AS qualifying_gap,
           rd.race_time AS race_time,
           rd.race_gap AS race_gap,
           rd.race_laps AS race_laps,
           rd.race_points AS race_points,
           rd.race_grid_position_number AS race_grid,
           rd.race_reason_retired AS retired
    FROM race_data rd
    JOIN race r ON r.id = rd.race_id
    JOIN driver d ON d.id = rd.driver_id
    JOIN constructor con ON con.id = rd.constructor_id
    WHERE r.year = ? AND r.round = ? AND rd.type = ?
    ORDER BY rd.position_display_order
"""


@dataclass(frozen=True)
class SessionEntry:
    """One driver's line in a session classification.

    Fields outside the session's own column family stay ``None``: a practice
    session has no points, and a sprint has no Q3 time. Leaving them empty
    keeps a renderer from printing a zero that was never recorded.
    """

    driver_code: str
    driver_name: str
    team: str
    #: Classified position, or ``None`` when the driver was not classified.
    position: int | None
    #: f1db's position text, which carries "DNF"/"NC" where a number cannot.
    position_text: str
    #: Best lap (practice) or total/interval (race). ``None`` if never set.
    time: str | None
    #: Gap to the session leader.
    gap: str | None
    #: Laps completed.
    laps: int | None
    q1: str | None = None
    q2: str | None = None
    q3: str | None = None
    points: float | None = None
    #: The slot this driver started the sprint from.
    grid: int | None = None
    #: Retirement cause, ``None`` for a classified finisher.
    retired: str | None = None


def _int_or_none(value) -> int | None:
    return None if value is None else int(value)


def _text_or_none(value) -> str | None:
    """Normalise f1db's empty strings to ``None``.

    An unset time arrives as ``''`` rather than NULL for some rows, and an
    empty string rendered into a table looks like a value that exists.
    """
    text = (value or "").strip() if isinstance(value, str) else value
    return text or None


def _practice_entry(row) -> SessionEntry:
    return SessionEntry(
        driver_code=row["code"],
        driver_name=row["name"],
        team=row["team"],
        position=_int_or_none(row["position"]),
        position_text=row["position_text"],
        time=_text_or_none(row["practice_time"]),
        gap=_text_or_none(row["practice_gap"]),
        laps=_int_or_none(row["practice_laps"]),
    )


def _qualifying_entry(row) -> SessionEntry:
    # The headline time is the best segment the driver reached, which is the
    # last one they set — a driver knocked out in Q1 has no Q2 or Q3 time.
    q1, q2, q3 = (_text_or_none(row["q1"]), _text_or_none(row["q2"]), _text_or_none(row["q3"]))
    return SessionEntry(
        driver_code=row["code"],
        driver_name=row["name"],
        team=row["team"],
        position=_int_or_none(row["position"]),
        position_text=row["position_text"],
        time=q3 or q2 or q1,
        gap=_text_or_none(row["qualifying_gap"]),
        laps=None,
        q1=q1,
        q2=q2,
        q3=q3,
    )


def _race_entry(row) -> SessionEntry:
    return SessionEntry(
        driver_code=row["code"],
        driver_name=row["name"],
        team=row["team"],
        position=_int_or_none(row["position"]),
        position_text=row["position_text"],
        time=_text_or_none(row["race_time"]),
        gap=_text_or_none(row["race_gap"]),
        laps=_int_or_none(row["race_laps"]),
        points=None if row["race_points"] is None else float(row["race_points"]),
        grid=_int_or_none(row["race_grid"]),
        retired=_text_or_none(row["retired"]),
    )


_BUILDERS = {
    KIND_PRACTICE: _practice_entry,
    KIND_QUALIFYING: _qualifying_entry,
    KIND_RACE: _race_entry,
}


def session_classification(year: int, round_num: int, result_type: str, kind: str) -> tuple[SessionEntry, ...]:
    """One session's classification, in finishing order.

    Returns an empty tuple when the round has no such session — a conventional
    weekend has no sprint, and a weekend still being run has nothing at all.
    Neither is an error.
    """
    build = _BUILDERS[kind]
    with connect() as conn:
        rows = conn.execute(_SESSION_QUERY, (year, round_num, result_type)).fetchall()

    entries = tuple(build(row) for row in rows if row["code"])
    logger.info(
        "f1db_sessions.loaded",
        year=year,
        round=round_num,
        result_type=result_type,
        entries=len(entries),
    )
    return entries
