"""A stewards' decision on a car that used power-unit elements beyond its allowance.

::

    No / Driver 30 - Liam Lawson
    Competitor Oracle Red Bull Racing
    Session Free Practice 3
    Fact The following Power Unit elements have been used:
    6th Engine (ICE)
    4th MGU-K
    7th Power Unit Ancillary Component (PU-ANC)
    Infringement Breach of Article B8.2.2 (in conjunction with B8.2.3) ...
    Decision Drop of 35 grid positions for the next Race in which the driver participates.
    Reason ... the use of ICE, TC and EXH additional element(s) carries a 5 grid
    place penalty ... MGU-K and PU-ANC additional elements carries a 10 grid ...

The outcome is one of three, and only the decision line says which. A grid
drop states its places. A pit-lane start — when the same decision also covers
parc fermé changes — says the drop "is redundant in this case", so the places
it would have cost are kept separately as ``nominal_places``: they were not
applied, and adding them to a season total would overstate the penalty.

Titles vary ("Changes to PU elements", "PU element and changes made during
Parc Ferme", "Additional changes to PU elements"), so a decision is recognised
by its fact line — "The following Power Unit elements have been used" — and
anything without one is not a power-unit decision.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.data.power_units.text import DocumentParseError, clean, squash

OUTCOME_GRID_DROP = "grid_drop"
OUTCOME_PIT_LANE = "pit_lane"
OUTCOME_BACK_OF_GRID = "back_of_grid"
OUTCOME_OTHER = "other"

ELEMENTS_USED = re.compile(r"Power\s+Unit\s+elements?\s+ha(?:s|ve)\s+been\s+used\s*:", re.IGNORECASE)
_DRIVER = re.compile(r"^\s*No\s*/\s*Driver\s+(?P<car>\d{1,2})\s*-\s*(?P<name>.+?)\s*$", re.MULTILINE)
_COMPETITOR = re.compile(r"^\s*Competitor\s+(?P<name>.+?)\s*$", re.MULTILINE)
_SESSION = re.compile(r"^\s*Session\s+(?P<name>.+?)\s*$", re.MULTILINE)
_INFRINGEMENT = re.compile(r"^\s*Infringement\b", re.MULTILINE)
_ELEMENT = re.compile(r"^\s*(?P<number>\d{1,2})(?:st|nd|rd|th)\s+(?P<label>.+?)\s*$", re.MULTILINE)
_BRACKETED_CODE = re.compile(r"\(\s*(?P<code>[A-Z][A-Z-]*)\s*\)\s*$")
_DECISION_BLOCK = re.compile(r"^\s*Decision\s+(?P<text>.+?)^\s*Reason\b", re.MULTILINE | re.DOTALL)
_REASON_BLOCK = re.compile(r"^\s*Reason\s+(?P<text>.+?)(?:Competitors\s+are\s+reminded|\Z)", re.MULTILINE | re.DOTALL)
_GRID_DROP = re.compile(r"Drop\s+of\s+(?P<places>\d+)\s+grid\s+positions?", re.IGNORECASE)
_PIT_LANE = re.compile(r"from\s+the\s+pit\s*lane", re.IGNORECASE)
_BACK_OF_GRID = re.compile(r"back\s+of\s+the\s+(?:starting\s+)?grid", re.IGNORECASE)
_NOMINAL = re.compile(r"normally\s+carr(?:y|ies)\s+an?\s+(?P<places>\d+)\s+grid\s+place", re.IGNORECASE)


@dataclass(frozen=True)
class DecisionElement:
    """An element named in a decision: the 6th ICE is ``("ICE", 6)``."""

    code: str
    number: int


@dataclass(frozen=True)
class PuDecision:
    """What the stewards decided about one car's power-unit elements."""

    car_number: int
    #: The driver as printed after "No / Driver" — display only.
    driver: str
    competitor: str
    #: The session the elements were first used in, when the decision says.
    session: str | None
    elements: tuple[DecisionElement, ...]
    outcome: str
    #: Grid places dropped, for a grid-drop outcome.
    places: int | None
    #: Places the elements would have cost when another sanction superseded them.
    nominal_places: int | None
    #: The decision line, verbatim.
    summary: str


def _element(match: re.Match[str]) -> DecisionElement:
    label = match["label"]
    bracketed = _BRACKETED_CODE.search(label)
    code = bracketed["code"] if bracketed else label.strip()
    return DecisionElement(code=code.upper(), number=int(match["number"]))


def _elements(text: str, fact: re.Match[str]) -> tuple[DecisionElement, ...]:
    end = _INFRINGEMENT.search(text, fact.end())
    block = text[fact.end() : end.start() if end else len(text)]
    elements = tuple(_element(match) for match in _ELEMENT.finditer(block))
    if not elements:
        raise DocumentParseError("decision names no power-unit elements")
    return elements


def _outcome(summary: str) -> tuple[str, int | None]:
    if _PIT_LANE.search(summary):
        return OUTCOME_PIT_LANE, None
    drop = _GRID_DROP.search(summary)
    if drop:
        return OUTCOME_GRID_DROP, int(drop["places"])
    if _BACK_OF_GRID.search(summary):
        return OUTCOME_BACK_OF_GRID, None
    return OUTCOME_OTHER, None


def _field(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return squash(match["name"]) if match else None


def parse_decision(text: str) -> PuDecision | None:
    """Read a power-unit decision; ``None`` when the decision is about something else.

    Raises :class:`DocumentParseError` when it *is* a power-unit decision but a
    field the screen depends on cannot be read.
    """
    text = clean(text)
    fact = ELEMENTS_USED.search(text)
    if fact is None:
        return None

    driver = _DRIVER.search(text)
    decision = _DECISION_BLOCK.search(text)
    if driver is None or decision is None:
        raise DocumentParseError("power-unit decision has no driver or decision line")

    summary = squash(decision["text"])
    outcome, places = _outcome(summary)
    reason = _REASON_BLOCK.search(text)
    nominal = _NOMINAL.search(reason["text"]) if reason else None
    return PuDecision(
        car_number=int(driver["car"]),
        driver=squash(driver["name"]),
        competitor=_field(_COMPETITOR, text) or "",
        session=_field(_SESSION, text),
        elements=_elements(text, fact),
        outcome=outcome,
        places=places,
        nominal_places=int(nominal["places"]) if nominal else None,
        summary=summary,
    )
