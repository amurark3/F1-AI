"""The stewards' decisions that apply a rule: found by article number, or by words.

Only decided, standing decisions held in the D2 store count: a summons has no
decision yet, a withdrawn document is no longer the FIA's, and an unread one has
no text. A decision is matched to a regulation passage by the article numbers
both name (``matching``). When the regulations could not be searched, the words
of the question are matched against each decision's offence and decision line
instead (``keyword_matching``), and the result says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import math
import re
from typing import TYPE_CHECKING
import unicodedata

import structlog

from app.data.fia_documents import store
from app.data.fia_documents.kinds import KIND_PENALTY, document_kind
from app.data.fia_documents.listing import title_number
from app.data.fia_documents.parsers.stewards import STATUS_DECIDED, parse_stewards_decision
from app.data.fia_documents.store import FiaStoreError
from app.data.fia_documents.text import DocumentParseError
from app.utils.ttl_cache import TtlCache

if TYPE_CHECKING:
    from app.data.fia_documents.document import SourceDocument

logger = structlog.get_logger()

DECISIONS_SHOWN = 3
SEASON_TTL_SECONDS = 600.0

ARTICLE_CODE = re.compile(r"(?<![\w.])[A-F]\d{1,2}(?:\.\d{1,2}){1,3}[a-z]?(?!\w)")
_PU = re.compile(r"\bpu\b")
_PUBLISHED_FORMAT = "%d.%m.%y %H:%M"
_STOP_TEXT = (
    "a an the is are was were be been do does did how what when where which who whom why can could should would "
    "will may might must if of in on at to for from by with as and or not no it its this that these those there "
    "their they them i me we you my our your about under during after before any mean means rule rules regulation "
    "regulations f1 formula driver drivers car cars team teams race count counts work works happen happens get gets "
    "allowed"
)
STOP_WORDS = frozenset(_STOP_TEXT.split())


def article_codes(text: str) -> tuple[str, ...]:
    """Every regulation article number in ``text``, in order, each once."""
    return tuple(dict.fromkeys(ARTICLE_CODE.findall(text)))


def cites(decision_article: str, code: str) -> bool:
    """Whether a decision's article is ``code`` or a sub-article of it ("B1.6.3a" is under "B1.6.3")."""
    if decision_article == code:
        return True
    rest = decision_article.removeprefix(code)
    return rest != decision_article and (rest[0] == "." or rest[0].islower())


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def search_words(text: str) -> tuple[str, ...]:
    """The words of ``text`` worth matching on, in order, each once."""
    folded = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()
    pieces = re.split(r"[^a-z0-9]+", _PU.sub("power unit", folded))
    return tuple(dict.fromkeys(_stem(w) for w in pieces if len(w) >= 2 and w not in STOP_WORDS))


@dataclass(frozen=True)
class _Decision:
    """One decided, standing stewards' decision: the fields shown, and what it is matched on."""

    shown: dict
    articles: tuple[str, ...]
    words: tuple[str, ...]
    stamp: float


@dataclass(frozen=True)
class _Season:
    events: int
    decisions: tuple[_Decision, ...]


def _stamp(published: str) -> float:
    """Seconds since the epoch, or 0 (oldest) when the FIA's time doesn't parse."""
    try:
        return datetime.strptime(published, _PUBLISHED_FORMAT).replace(tzinfo=UTC).timestamp()
    except ValueError:
        return 0.0


def _decision(document: SourceDocument) -> _Decision | None:
    if document.withdrawn is not None or not document.text or document_kind(document.title) != KIND_PENALTY:
        return None
    try:
        parsed = parse_stewards_decision(document.title, document.text)
    except DocumentParseError:
        return None
    number = parsed.document or title_number(document.title)
    if parsed.status != STATUS_DECIDED or number is None:
        return None
    decision = parsed.decision or ""
    shown = {
        "number": number,
        "event": document.event,
        "title": document.title,
        "car": parsed.car,
        "driver": parsed.driver,
        "session": parsed.session,
        "offence": parsed.offence,
        "decision": decision,
        "articles": list(parsed.articles),
        "published": document.published,
        "url": document.url,
    }
    return _Decision(shown, parsed.articles, search_words(f"{parsed.offence} {decision}"), _stamp(document.published))


def _read_season(year: int) -> _Season:
    events = sorted(store.events(year))
    found = (_decision(document) for event in events for document in store.load_event(year, event))
    return _Season(len(events), tuple(item for item in found if item is not None))


_SEASONS: TtlCache[int, _Season] = TtlCache()


def _season(year: int) -> _Season:
    """The season's decisions; a failed read raises and is not kept."""
    kept = _SEASONS.get(year)
    if kept is not None:
        return kept
    season = _read_season(year)
    _SEASONS.put(year, season, SEASON_TTL_SECONDS)
    return season


def _result(match: str, status: str, events: int | None, **fields: object) -> dict:
    return {
        "match": match,
        "status": status,
        "events": events,
        "total": 0,
        "articles": [],
        "words": [],
        "items": [],
        **fields,
    }


def _items(ranked: list[tuple[_Decision, list[str]]], first_cite: int) -> list[dict]:
    return [
        {**decision.shown, "cite": first_cite + index, "matched": matched}
        for index, (decision, matched) in enumerate(ranked[:DECISIONS_SHOWN])
    ]


def _passage_index(decision: _Decision, codes_per_article: list[tuple[str, ...]]) -> int:
    return next(
        index
        for index, codes in enumerate(codes_per_article)
        if any(cites(article, code) for article in decision.articles for code in codes)
    )


def matching(year: int, codes_per_article: list[tuple[str, ...]], first_cite: int) -> dict:
    """The decisions that cite an article a passage names, closest passage first, then newest."""
    try:
        season = _season(year)
    except FiaStoreError as exc:
        logger.warning("rulebook.decisions.unavailable", year=year, error=str(exc))
        return _result("article", "unavailable", None)
    codes = {code for passage in codes_per_article for code in passage}
    hits = [
        (decision, [a for a in decision.articles if any(cites(a, code) for code in codes)])
        for decision in season.decisions
    ]
    ranked = sorted(
        ((decision, matched) for decision, matched in hits if matched),
        key=lambda hit: (_passage_index(hit[0], codes_per_article), -hit[0].stamp),
    )
    union = list(dict.fromkeys(article for _, matched in ranked for article in matched))
    return _result(
        "article",
        "matched" if ranked else "none",
        season.events,
        total=len(ranked),
        items=_items(ranked, first_cite),
        articles=union,
    )


def keyword_matching(year: int, query: str) -> dict:
    """The decisions sharing at least half the question's words. Raises :class:`FiaStoreError`."""
    season = _season(year)
    words = search_words(query)
    needed = max(1, math.ceil(len(words) / 2))
    scored = [(decision, [w for w in words if w in decision.words]) for decision in season.decisions]
    ranked = sorted(
        ((decision, shared) for decision, shared in scored if words and len(shared) >= needed),
        key=lambda hit: (-len(hit[1]), -hit[0].stamp),
    )
    return _result(
        "keyword",
        "matched" if ranked else "none",
        season.events,
        total=len(ranked),
        items=_items(ranked, 1),
        words=list(words),
    )
