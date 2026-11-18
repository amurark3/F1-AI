"""A stewards' summons or decision about one car: the penalty log's rows.

A decision ("Infringement - Car 81 - Causing a collision", "Decision - Car 10 - …")
is a form::

    No / Driver 81 - Oscar Piastri
    Competitor McLaren Mastercard F1 Team
    Time 15:12
    Session Race
    Fact Collision with Car 41 at Turn 2.
    Infringement Breach of Appendix L, Chapter IV, Article 2 d) of the FIA International Sporting Code.
    Decision 10 second time penalty imposed after the Race.
    Reason ...

A summons ("Summons - Car 63 - …") has the car, a hearing time and the
alleged breach in its Reason line, and no decision yet. Only the decision line
says what was imposed, so outcomes are read from it alone: a "warning" in the
reasoning is not a warning given.

A stop-and-go imposed after the race reads as published; the classification
converts it to time (Mexico 2026: "converted to 30 second time penalty").
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.data.fia_documents.parsers.fields import NUMBER, document_number, number
from app.data.fia_documents.text import DocumentParseError, clean, squash

STATUS_SUMMONED = "summoned"
STATUS_DECIDED = "decided"

_TITLE = re.compile(
    r"^\s*(?:Doc\s+\d+\s*-\s*)?(?:Corrected\s+)?(?P<type>Infring\w*|Decision|Summons|Offence)\s*-\s*(?P<rest>.+?)\s*$",
    re.IGNORECASE,
)
_TITLE_CAR = re.compile(r"\bCar\s+(?P<car>\d{1,2})\b", re.IGNORECASE)
_DRIVER = re.compile(r"^\s*No\s*/\s*Driver\s+(?P<car>\d{1,2})\s*-\s*(?P<name>.+?)\s*$", re.MULTILINE)
_COMPETITOR = re.compile(r"^\s*Competitor\s+(?P<name>.+?)\s*$", re.MULTILINE)
_TEAM_MANAGER = re.compile(r"^\s*To\s+The\s+Team\s+Manager,\s*\n\s*(?P<name>.+?)\s*$", re.MULTILINE)
_SESSION = re.compile(r"^\s*Session\s+(?P<name>.+?)\s*$", re.MULTILINE)
_TIME = re.compile(r"^\s*Time\s+(?P<time>\d{1,2}:\d{2})\s*$", re.MULTILINE)
_HEARING = re.compile(r"report\s+to\s+the\s+Stewards\s+at\s+(?P<time>\d{1,2}:\d{2})", re.IGNORECASE)
_INFRINGEMENT = re.compile(r"^\s*Infringement\s+(?P<text>.+?)^\s*Decision\b", re.MULTILINE | re.DOTALL)
_DECISION = re.compile(
    r"^\s*Decision\s+(?P<text>.+?)(?:^\s*(?:Reason|Note)\b|Competitors\s+are\s+reminded|\Z)",
    re.MULTILINE | re.DOTALL,
)
_REASON = re.compile(r"^\s*Reason\s+(?P<text>.+?)(?:Competitors\s+are\s+reminded|\Z)", re.MULTILINE | re.DOTALL)
# F1 Regulations sections (B1.8.4a, C5.12.6, B1.6.2b.i), International Sporting Code
# articles (12.2.1.l), and the ISC's appendices (L: driving, H: flags).
_APPENDIX = re.compile(
    r"Appendix\s+(?P<appendix>[A-Z]),\s*(?:Chapter\s+(?P<chapter>[IVX]+),\s*)?"
    r"Article\s+(?P<article>\d+(?:\.\d+)*(?:\s*[a-z]\))?)"
)
_ARTICLE = re.compile(r"\b(?P<code>[A-C]\d+(?:\.\d+)+[a-z]?(?:\.[ivx]+)?|\d+(?:\.\d+){2,}(?:\.[a-z])?)(?!\w)(?!\.\w)")


@dataclass(frozen=True)
class Outcome:
    """One thing imposed: ``kind`` and, where it has one, a value."""

    kind: str
    #: Seconds, grid places, penalty points or euros; ``None`` for the rest.
    value: int | None = None


#: What a decision line can impose, in the order a reader weighs them.
_OUTCOMES: tuple[tuple[str, re.Pattern[str], bool], ...] = (
    ("disqualified", re.compile(r"\bdisqualified\b", re.IGNORECASE), False),
    ("pit_lane_start", re.compile(r"from\s+the\s+pit\s*lane", re.IGNORECASE), False),
    ("back_of_grid", re.compile(r"back\s+of\s+the\s+(?:starting\s+)?grid", re.IGNORECASE), False),
    (
        "grid_drop",
        re.compile(
            rf"drop\s+of\s+(?P<value>{NUMBER})\s+grid\s+positions?|(?P<places>\d+)\s+place\s+grid\s+penalty",
            re.IGNORECASE,
        ),
        True,
    ),
    ("time_penalty", re.compile(r"(?P<value>\d+)\s+second\s+time\s+penalty", re.IGNORECASE), True),
    ("stop_and_go", re.compile(r"stop\s+and\s+go", re.IGNORECASE), False),
    ("drive_through", re.compile(r"drive[\s-]+through", re.IGNORECASE), False),
    ("reprimand", re.compile(r"\breprimand\b", re.IGNORECASE), False),
    ("warning", re.compile(r"\bwarning\b", re.IGNORECASE), False),
    ("fine", re.compile(r"€\s*(?P<value>\d{1,3}(?:,\d{3})+|\d+)"), True),
    ("penalty_points", re.compile(rf"(?P<value>{NUMBER})\s+penalty\s+points?", re.IGNORECASE), True),
    ("no_further_action", re.compile(r"no\s+further\s+action", re.IGNORECASE), False),
)


@dataclass(frozen=True)
class StewardsDecision:
    """A summons or a decision about one car."""

    document: int | None
    status: str
    car: int
    driver: str | None
    competitor: str | None
    session: str | None
    #: When it happened, local time, as the form gives it.
    incident_time: str | None
    #: The title's words: "Causing a collision", "Alleged misconduct".
    offence: str
    #: "B1.8.4a", "ISC 12.2.1.l", "ISC Appendix L Chapter IV Article 2 d)", "ISC Appendix H Article 2.5.5 b)".
    articles: tuple[str, ...]
    #: The decision line as printed; ``None`` for a summons.
    decision: str | None
    outcomes: tuple[Outcome, ...]
    #: A summons's hearing time, local.
    hearing: str | None = None


def _articles(text: str) -> tuple[str, ...]:
    found = [
        " ".join(
            part
            for part in (
                f"ISC Appendix {match['appendix']}",
                f"Chapter {match['chapter']}" if match["chapter"] else "",
                f"Article {squash(match['article'])}",
            )
            if part
        )
        for match in _APPENDIX.finditer(text)
    ]
    for match in _ARTICLE.finditer(_APPENDIX.sub(" ", text)):
        code = match["code"]
        found.append(code if code[0].isalpha() else f"ISC {code}")
    return tuple(dict.fromkeys(found))


def _value(match: re.Match[str]) -> int:
    token = next(group for group in match.groups() if group)
    return int(token.replace(",", "")) if token[0].isdigit() else number(token)


def outcomes(decision: str) -> tuple[Outcome, ...]:
    """Everything a decision line imposes, e.g. a time penalty and the penalty points with it."""
    found = []
    for kind, pattern, valued in _OUTCOMES:
        match = pattern.search(decision)
        if match:
            found.append(Outcome(kind, _value(match) if valued else None))
    return tuple(found)


def _field(pattern: re.Pattern[str], text: str, start: int = 0) -> str | None:
    match = pattern.search(text, start)
    return squash(match.group(1)) if match else None


def _block(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return squash(match["text"]) if match else None


def parse_stewards_decision(title: str, text: str) -> StewardsDecision:
    """Read a summons or a decision. Raises :class:`DocumentParseError` when a field the log needs is missing."""
    heading = _TITLE.match(title)
    if heading is None:
        raise DocumentParseError(f"not a stewards' summons or decision title: {title!r}")
    text = clean(text)
    driver = _DRIVER.search(text)
    named = driver or _TITLE_CAR.search(heading["rest"])
    if named is None:
        raise DocumentParseError("no car named")
    subject, _, offence = heading["rest"].partition(" - ")
    summoned = heading["type"].lower() == "summons"
    decision = None if summoned else _block(_DECISION, text)
    imposed = outcomes(decision) if decision else ()
    if not summoned and not imposed:
        raise DocumentParseError(f"no outcome read from the decision: {decision!r}")
    return StewardsDecision(
        document=document_number(text),
        status=STATUS_SUMMONED if summoned else STATUS_DECIDED,
        car=int(named["car"]),
        driver=squash(driver["name"]) if driver else None,
        competitor=_field(_COMPETITOR, text) or _field(_TEAM_MANAGER, text),
        session=_field(_SESSION, text),
        incident_time=_field(_TIME, text, driver.end()) if driver else None,
        offence=squash(offence or subject),
        articles=_articles(_block(_REASON if summoned else _INFRINGEMENT, text) or ""),
        decision=decision,
        outcomes=imposed,
        hearing=_field(_HEARING, text) if summoned else None,
    )
