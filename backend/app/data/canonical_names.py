"""The driver and team names an emit point prints, from whatever cell a feed handed it.

Every payload that names a driver or team routes the feed's words through here:

* **Resolved:** f1db's ``driver.name`` / ``last_name`` ("Kimi Antonelli", where
  FastF1 says "Andrea Kimi Antonelli") and its constructor name ("Racing Bulls",
  where FastF1 says "RB F1 Team"), through :mod:`app.data.identity`.
* **Unresolved:** the feed's own words, display-cased ("Ryo HIRAKAWA" ->
  "Ryo Hirakawa"), never a guess.
* **f1db unreadable:** the feed's own words, which is what every emit point
  printed before the resolver, and a warning that says why.

Cells come straight from pandas or JSON, so NaN, numpy numbers and floats are
accepted and turned into the ``str`` / ``int`` / ``None`` the resolver takes.
Nothing is stored: names resolve on the fly against the cached f1db index.
"""

from __future__ import annotations

from numbers import Integral, Real
import sqlite3
from typing import TYPE_CHECKING
import zipfile

import structlog

from app.data.identity import CanonicalDriver, as_int, canonical_driver, feed_driver, resolve_team_name

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = structlog.get_logger()

# What reading f1db raises: a missing file is downloaded first (``requests``
# errors are ``OSError``s; a bad archive is ``BadZipFile``, or ``ValueError``
# when it holds no database), and a corrupt or half-written file raises
# ``sqlite3.Error``. A caller's own bug (a ``TypeError``) is not in this list.
F1DB_READ_ERRORS: tuple[type[Exception], ...] = (sqlite3.Error, OSError, zipfile.BadZipFile, ValueError)

#: The label on a classified row whose driver no source can give a code: FastF1
#: sent none and f1db does not know the driver yet (a debutant before f1db
#: publishes a round they drove). The row keeps its place with an empty
#: ``driver_code``, this flag set and its ``driver_number``.
CODE_UNRESOLVED = "code_unresolved"


def feed_text(value: object) -> str | None:
    """A text cell, or ``None`` for a blank or a non-text cell (pandas' NaN is a float)."""
    return value if isinstance(value, str) and value.strip() else None


def feed_code(value: object) -> str | None:
    """A driver-code cell in capitals, or ``None`` for a blank or non-text cell.

    FastF1 hands a missing abbreviation over as NaN, which ``str()`` would print
    as a code nobody has.
    """
    text = feed_text(value)
    return text.strip().upper() if text else None


def feed_number(value: object) -> int | None:
    """A car-number cell as an int: FastF1 writes "50", pandas 50.0 or NaN, OpenF1 50."""
    if isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        return int(number) if number.is_integer() else None
    return as_int(value.strip()) if isinstance(value, str) else None


def driver_identity(year: int, *, code: object = None, number: object = None, name: object = None) -> CanonicalDriver:
    """How to print the driver a feed row names in ``year``: f1db's identity, or the feed's words."""
    keys = {"code": feed_text(code), "number": feed_number(number), "name": feed_text(name)}
    try:
        return canonical_driver(year, **keys)
    except F1DB_READ_ERRORS as exc:
        logger.warning("canonical_names.f1db_unreadable", year=year, code=keys["code"], error=str(exc))
        return feed_driver(**keys)


def fastf1_driver(year: int, row: Mapping[str, object]) -> CanonicalDriver:
    """The driver a FastF1 results row names, by its abbreviation, car number and FirstName + LastName."""
    name = " ".join(part for part in (feed_text(row.get("FirstName")), feed_text(row.get("LastName"))) if part)
    return driver_identity(year, code=row.get("Abbreviation"), number=row.get("DriverNumber"), name=name)


def fastf1_code(year: int, row: Mapping[str, object]) -> str | None:
    """The code a FastF1 results row prints: FastF1's own, else f1db's, else ``None``.

    FastF1 sends some debutants and stand-ins with no abbreviation (Hirakawa at
    Mexico City, Câmara at São Paulo in 2026). f1db names them by car number or
    name once it has published a round they drove; until then nobody can.
    f1db is only read for a row without an abbreviation.
    """
    return feed_code(row.get("Abbreviation")) or fastf1_driver(year, row).code


def team_display_name(year: int, name: object) -> str:
    """f1db's name for the team a feed names in ``year``, else the feed's spelling ("" for a blank)."""
    text = feed_text(name)
    if text is None:
        return ""
    try:
        return resolve_team_name(year, text) or text
    except F1DB_READ_ERRORS as exc:
        logger.warning("canonical_names.f1db_unreadable", year=year, team=text, error=str(exc))
        return text
