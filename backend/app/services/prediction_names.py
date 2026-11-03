"""Canonical names over a stored prediction snapshot, applied as it is read.

A snapshot froze the names its compute saw: FastF1's "Andrea Kimi Antonelli",
"Carlos Sainz" and "RB F1 Team". A read prints f1db's instead ("Kimi
Antonelli", "Carlos Sainz Jr.", "Racing Bulls"), found by each row's code and
car number (when stored) through :mod:`app.data.canonical_names`.

* Only the values of ``driver_name`` and ``team`` change; no key is added or
  removed, and codes, numbers and every model figure stay as stored.
* The overlay works on the copy a read serves. The stored document is never
  rewritten, so the record of what the model saw stays as it was.
* A row nobody resolves keeps its stored name, display-cased; an unreadable
  f1db serves the stored names (and logs why).
"""

from __future__ import annotations

from app.data.canonical_names import driver_identity, team_display_name
from app.data.identity import as_int

# The per-driver row lists of a prediction result.
ROW_LISTS = ("predictions", "risk_predictions")


def with_canonical_names(result: dict) -> dict:
    """``result`` with every row's driver and team printed under f1db's names; ``result`` itself is untouched."""
    year = as_int(result.get("year"))
    if year is None:
        return result
    named = {
        key: [_named_row(year, row) for row in rows] for key in ROW_LISTS if isinstance(rows := result.get(key), list)
    }
    return {**result, **named}


def _named_row(year: int, row: object) -> object:
    if not isinstance(row, dict):
        return row
    names = {}
    if "driver_name" in row:
        driver = driver_identity(
            year, code=row.get("driver_code"), number=row.get("driver_number"), name=row.get("driver_name")
        )
        names["driver_name"] = driver.name or row["driver_name"]
    if "team" in row:
        names["team"] = team_display_name(year, row.get("team")) or row["team"]
    return {**row, **names}
