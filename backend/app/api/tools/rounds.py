"""Which round of a season a Grand Prix name means, from f1db's calendar.

The chat tools take the name the user typed ("Mexico", "Monaco Grand Prix", or a
round number). FastF1 matched it loosely against its own schedule; this reads the
same f1db calendar everything else does.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

from app.api.errors import SafeToShowError
from app.data.f1db_calendar import season_schedule

if TYPE_CHECKING:
    import pandas as pd

CLOSE_MATCH_CUTOFF = 0.6


def _plain(text: object) -> str:
    return str(text).lower().replace("grand prix", "").strip()


def _round_for(schedule: pd.DataFrame, year: int, grand_prix: str) -> int:
    text = _plain(grand_prix)
    if text.isdigit() and int(text) in set(schedule["RoundNumber"]):
        return int(text)
    for column in ("EventName", "Location", "Country"):
        names = {int(row["RoundNumber"]): _plain(row[column]) for _, row in schedule.iterrows()}
        found = next((number for number, name in names.items() if text and text in name), None)
        if found is not None:
            return found
    names = {_plain(row["EventName"]): int(row["RoundNumber"]) for _, row in schedule.iterrows()}
    close = difflib.get_close_matches(text, names, n=1, cutoff=CLOSE_MATCH_CUTOFF)
    if close:
        return names[close[0]]
    raise SafeToShowError(f"No {year} Grand Prix matches '{grand_prix}'")


def resolve_event(year: int, grand_prix: str) -> tuple[int, str]:
    """The round and its ``EventName`` for a round number or a (partial) event, place or country name.

    The event's own name beats its place, which beats its country (Miami and Las
    Vegas share a country with Austin). Raises ``ValueError`` when nothing fits.
    """
    schedule = season_schedule(year)
    number = _round_for(schedule, year, grand_prix)
    row = schedule[schedule["RoundNumber"] == number].iloc[0]
    return number, str(row["EventName"])


def resolve_round(year: int, grand_prix: str) -> int:
    """The round for a Grand Prix name; see :func:`resolve_event`."""
    return resolve_event(year, grand_prix)[0]
