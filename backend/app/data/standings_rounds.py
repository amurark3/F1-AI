"""Each round's points since f1db's last release, from OpenF1 ``session_result``.

f1db publishes a round's results and standings about 10 hours after the race,
sometimes days. Until it does, a later round's points come from OpenF1
``session_result``, which matched FIA document 86, the final classification,
points included, on the morning after Mexico 2026. The FIA final
classification takes over in task D2.3.

* **A round counts as a whole, once its race has ended.** Its sprint, if it
  had one, counts with it, never alone, so the table always reads "after
  round N".
* **Points are used as published.** A race shortened by a red flag scores what
  was awarded, which no points table can know. A row without points makes the
  round unusable.
* **Cars are named from the weekend entry list** (``session_entries``), which
  fills a blank team from the weekend's other sessions: OpenF1 left
  Hirakawa's car 50 without a team in the Mexico race list. A scoring car that
  cannot be named or placed in a team makes the round unusable, so a point is
  never credited to the wrong team. A car that scored nothing is left out.
* **Rounds are read in order and stop at the first one that is not usable.** A
  table never skips a round.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.data.identity import resolve_team_name
from app.data.openf1.client import OpenF1UnavailableError, get_json, new_client
from app.data.openf1.sessions import session_ended, weekend_sessions
from app.data.session_entries import load_weekend_entry_list
from app.data.standings_table import Score

if TYPE_CHECKING:
    from collections.abc import Mapping

    import httpx

    from app.data.openf1.sessions import OpenF1Session
    from app.data.session_entries import EntryListDriver

logger = structlog.get_logger()

# Points-paying sessions, in running order: a sprint is run before its race.
POINTS_SESSIONS = ("S", "R")
# No season has had this many rounds; bounds the look-ahead past f1db.
MAX_ROUNDS = 30
RACE = "R"


@dataclass(frozen=True)
class RoundPoints:
    """Every score of one round, and the sessions they came from."""

    round: int
    race_session_key: int
    #: Session codes counted, in running order: ``("R",)`` or ``("S", "R")``.
    sessions: tuple[str, ...]
    scores: tuple[Score, ...]


class UnusableRoundError(Exception):
    """A round's result is published but cannot be credited safely."""


def _finish(row: dict, session_code: str) -> int | None:
    position = row.get("position")
    return position if session_code == RACE and isinstance(position, int) else None


def _score(row: dict, session_code: str, cars: Mapping[int, EntryListDriver], year: int) -> Score | None:
    car = cars.get(row.get("driver_number", -1))
    team = resolve_team_name(year, car.team) if car else None
    if car is None or team is None:
        return None
    return Score(
        code=car.code, name=car.name, team=team, points=float(row["points"]), finish=_finish(row, session_code)
    )


def _session_scores(
    rows: list[dict], session_code: str, cars: Mapping[int, EntryListDriver], year: int
) -> tuple[Score, ...]:
    """A session's scores; raises :class:`UnusableRoundError` when one cannot be credited."""
    scores = []
    for row in rows:
        if not isinstance(row.get("points"), int | float):
            raise UnusableRoundError(f"car {row.get('driver_number')} has no points")
        score = _score(row, session_code, cars, year)
        if score is not None:
            scores.append(score)
        elif row["points"]:
            raise UnusableRoundError(f"car {row.get('driver_number')} scored but has no driver or team")
    return tuple(scores)


def _published(client: httpx.Client, sessions: tuple[OpenF1Session, ...]) -> tuple[list[dict], ...] | None:
    """Each session's result, or ``None`` while any of them is unpublished."""
    results = tuple(get_json(client, "session_result", {"session_key": session.session_key}) for session in sessions)
    return results if all(results) else None


def round_points(client: httpx.Client, year: int, round_num: int) -> RoundPoints | None:
    """The round's points; ``None`` when its race has not ended or a result is not published."""
    by_code = {session.code: session for session in weekend_sessions(client, year, round_num)}
    race = by_code.get(RACE)
    if race is None or not session_ended(race):
        return None
    counted = tuple(by_code[code] for code in POINTS_SESSIONS if code in by_code)
    results = _published(client, counted)
    if results is None:
        return None
    entries = load_weekend_entry_list(year, round_num)
    if not entries.available:
        return None
    cars = {entry.number: entry for entry in entries.entries if entry.number is not None}
    scores = tuple(
        score
        for session, rows in zip(counted, results, strict=True)
        for score in _session_scores(rows, session.code, cars, year)
    )
    return RoundPoints(
        round=round_num,
        race_session_key=race.session_key,
        sessions=tuple(session.code for session in counted),
        scores=scores,
    )


def later_rounds(year: int, after_round: int) -> tuple[RoundPoints, ...]:
    """Every round after ``after_round`` with published points, in order, up to the first without."""
    found: list[RoundPoints] = []
    try:
        with new_client() as client:
            for round_num in range(after_round + 1, MAX_ROUNDS + 1):
                points = round_points(client, year, round_num)
                if points is None:
                    break
                found.append(points)
    except UnusableRoundError as exc:
        logger.warning("standings.round_unusable", year=year, round=after_round + len(found) + 1, error=str(exc))
    # The calendar lookup reaches FastF1's schedule backend, which raises
    # ValueError/KeyError for a bad season and OSError for a network failure.
    except (OpenF1UnavailableError, ValueError, KeyError, OSError) as exc:
        logger.warning("standings.openf1_unavailable", year=year, error=str(exc))
    return tuple(found)
