"""The power-unit elements a season counts, and the codes documents print them under.

Only the vocabulary lives in code — it is what the parsers need to read a
document at all. How many units of each a car may use does *not*: it is data,
kept in the shared store (:mod:`app.data.power_units.allowances`) and taken
from the FIA's own reports, because the regulations can change between issues
and a number frozen into a release would go on looking authoritative after it
stopped being true.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class Element:
    """One power-unit element type as the regulations count it."""

    code: str
    name: str


ELEMENTS_2026: tuple[Element, ...] = (
    Element("ICE", "Internal combustion engine"),
    Element("TC", "Turbocharger"),
    Element("EXH", "Exhaust set"),
    Element("MGU-K", "Motor generator unit – kinetic"),
    Element("ES", "Energy store"),
    Element("PU-CE", "Control electronics"),
    Element("PU-ANC", "Power unit ancillaries"),
)

_SEASON_ELEMENTS: Mapping[int, tuple[Element, ...]] = MappingProxyType({2026: ELEMENTS_2026})

# Codes as other documents print them → the 2026 code. Stewards write "MGU-K"
# without a bracketed code, and older documents abbreviate the control
# electronics, ancillaries and exhaust differently.
_ALIASES = MappingProxyType({"MGUK": "MGU-K", "CE": "PU-CE", "ANC": "PU-ANC", "EX": "EXH"})

SUPPORTED_SEASONS: frozenset[int] = frozenset(_SEASON_ELEMENTS)


def elements_for(year: int) -> tuple[Element, ...]:
    """The element types counted in ``year``, or ``()`` for a season not yet read."""
    return _SEASON_ELEMENTS.get(year, ())


def canonical_code(raw: str, year: int) -> str | None:
    """The season's code for an element as a document printed it, else ``None``."""
    known = {element.code for element in elements_for(year)}
    code = raw.strip().upper()
    if code in known:
        return code
    alias = _ALIASES.get(code)
    return alias if alias in known else None
