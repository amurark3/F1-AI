"""Parse the stored corpus into round-tagged evidence.

Each document is tied to an f1db round by its cover's race day — the FIA's
event names drift ("Bahrain Grand Prix" was held in Malaysia in 2026), dates
do not — and by its listed event name when the cover date cannot be read.

A document that cannot be read, or tied to a round, is not dropped: it becomes
an :class:`UnreadDocument` with the reason, and the screen lists it. A season
total built on a silently skipped report would undercount without a trace.

Documents the FIA took back are set aside on purpose, each with the reason, so
the screen can list them: one the collection found withdrawn from its event
page; one a later notice of the same event withdraws, rescinds or replaces
("This decision replaces Document 37"); and a decision the stewards reissued
— "Corrected Infringement - Car 6", or a second decision naming the same
elements — which gives way to the later one, so a corrected penalty is
counted once.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from app.data.power_units.decision import PuDecision
from app.data.power_units.documents import ParsedDocument, parse_document
from app.data.power_units.elements import canonical_code
from app.data.power_units.new_elements import NewElementsReport
from app.data.power_units.text import DocumentParseError, compact
from app.data.power_units.usage_report import UsageReport

if TYPE_CHECKING:
    from app.data.power_units.season_context import SeasonContext
    from app.data.power_units.sources import SeasonSources, SourceDocument

# "Doc 44 - Corrected Infringement - Car 6 - …" and the original it replaces
# share everything after these two prefixes.
_TITLE_NUMBER = re.compile(r"^\s*Doc\s+\d+\s*-\s*", re.IGNORECASE)
_TITLE_CORRECTED = re.compile(r"^\s*Corrected\s+", re.IGNORECASE)


@dataclass(frozen=True)
class DocumentRef:
    """Where a fact came from, for the screen to link to."""

    title: str
    url: str
    published: str
    number: int | None

    def as_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "published": self.published, "number": self.number}


@dataclass(frozen=True)
class UsageRowEvidence:
    """One car's running totals going into a round, element codes canonical."""

    round: int
    car_number: int
    #: The team the row is printed under, ``None`` when it names no known team.
    team_id: str | None
    counts: dict[str, int]
    ref: DocumentRef


@dataclass(frozen=True)
class IntroductionEvidence:
    round: int
    code: str
    car_number: int
    team_id: str | None
    number: int
    ref: DocumentRef


@dataclass(frozen=True)
class AllowanceStatement:
    """An allowance as a Technical Delegate's report states it in words."""

    round: int
    code: str
    allowance: int
    ref: DocumentRef


@dataclass(frozen=True)
class DecisionEvidence:
    round: int
    decision: PuDecision
    #: The competitor the decision is addressed to, as a team id.
    team_id: str | None
    #: ``(code, number)`` per element named, codes canonical.
    elements: tuple[tuple[str, int], ...]
    ref: DocumentRef


@dataclass(frozen=True)
class UnreadDocument:
    title: str
    url: str
    event: str
    reason: str

    def as_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "event": self.event, "reason": self.reason}


@dataclass(frozen=True)
class WithdrawnDocument:
    """A collected document the FIA took back, with how it did."""

    title: str
    url: str
    reason: str

    def as_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "reason": self.reason}


@dataclass(frozen=True)
class Evidence:
    """Everything the season's documents establish, in round and document order."""

    usage: tuple[UsageRowEvidence, ...]
    introductions: tuple[IntroductionEvidence, ...]
    statements: tuple[AllowanceStatement, ...]
    decisions: tuple[DecisionEvidence, ...]
    unread: tuple[UnreadDocument, ...]
    #: Documents excluded because the FIA took them back, or replaced them.
    withdrawn: tuple[WithdrawnDocument, ...]
    #: The most recent document read, and its round.
    latest: tuple[int, DocumentRef] | None

    def rounds(self) -> frozenset[int]:
        """Every round any readable document speaks about."""
        return frozenset(item.round for group in (self.usage, self.introductions, self.decisions) for item in group)


@dataclass(frozen=True)
class _Located:
    round: int
    parsed: ParsedDocument
    ref: DocumentRef


def _ref(source: SourceDocument, parsed: ParsedDocument) -> DocumentRef:
    return DocumentRef(
        title=source.title,
        url=source.url,
        published=source.published,
        number=parsed.cover.document_number,
    )


def _round_for(source: SourceDocument, parsed: ParsedDocument, context: SeasonContext) -> int | None:
    if parsed.cover.race_day is not None:
        by_day = context.round_on(parsed.cover.race_day)
        if by_day is not None:
            return by_day.round
    wanted = compact(source.event.replace("Grand Prix", "GP"))
    return next((item.round for item in context.rounds if compact(item.name) == wanted), None)


def _canonical(codes: list[str], year: int) -> list[str]:
    canonical = [canonical_code(code, year) for code in codes]
    unknown = [raw for raw, code in zip(codes, canonical, strict=True) if code is None]
    if unknown:
        raise DocumentParseError(f"unknown element code(s) {', '.join(unknown)}")
    return [code for code in canonical if code is not None]


def _locate(source: SourceDocument, context: SeasonContext) -> _Located | UnreadDocument:
    """Parse one document and tie it to a round, or say why it cannot be."""

    def unread(reason: str) -> UnreadDocument:
        return UnreadDocument(title=source.title, url=source.url, event=source.event, reason=reason)

    if source.text is None:
        return unread(source.error or "no text was extracted")
    try:
        parsed = parse_document(source.text)
    except DocumentParseError as exc:
        return unread(str(exc))
    if parsed.cover.season not in (None, context.year):
        return unread(f"document is for the {parsed.cover.season} season")
    round_num = _round_for(source, parsed, context)
    if round_num is None:
        return unread("its event could not be matched to the season calendar")
    return _Located(round=round_num, parsed=parsed, ref=_ref(source, parsed))


def _usage_rows(located: _Located, report: UsageReport, context: SeasonContext) -> list[UsageRowEvidence]:
    codes = _canonical(list(report.codes), context.year)
    return [
        UsageRowEvidence(
            round=located.round,
            car_number=row.car_number,
            team_id=context.team_named(row.entrant),
            counts=dict(zip(codes, (row.counts[raw] for raw in report.codes), strict=True)),
            ref=located.ref,
        )
        for row in report.rows
    ]


def _introductions(
    located: _Located,
    report: NewElementsReport,
    context: SeasonContext,
) -> tuple[list[IntroductionEvidence], list[AllowanceStatement]]:
    raw_codes = sorted({item.code for item in report.introductions} | set(report.stated_allowance))
    canonical = dict(zip(raw_codes, _canonical(raw_codes, context.year), strict=True))
    introductions = [
        IntroductionEvidence(
            round=located.round,
            code=canonical[item.code],
            car_number=item.car_number,
            team_id=context.team_named(item.entrant),
            number=item.number,
            ref=located.ref,
        )
        for item in report.introductions
    ]
    statements = [
        AllowanceStatement(round=located.round, code=canonical[code], allowance=count, ref=located.ref)
        for code, count in report.stated_allowance.items()
    ]
    return introductions, statements


def _decision(located: _Located, decision: PuDecision, context: SeasonContext) -> DecisionEvidence:
    codes = _canonical([element.code for element in decision.elements], context.year)
    return DecisionEvidence(
        round=located.round,
        decision=decision,
        team_id=context.team_named(decision.competitor),
        elements=tuple(zip(codes, (element.number for element in decision.elements), strict=True)),
        ref=located.ref,
    )


@dataclass(frozen=True)
class _Facts:
    """What one readable document contributes."""

    located: _Located
    usage: tuple[UsageRowEvidence, ...] = ()
    introductions: tuple[IntroductionEvidence, ...] = ()
    statements: tuple[AllowanceStatement, ...] = ()
    decisions: tuple[DecisionEvidence, ...] = ()


def _facts(located: _Located, context: SeasonContext) -> _Facts | None:
    """The document's facts; ``None`` when it is about something else."""
    body = located.parsed.body
    if isinstance(body, UsageReport):
        return _Facts(located, usage=tuple(_usage_rows(located, body, context)))
    if isinstance(body, NewElementsReport):
        introductions, statements = _introductions(located, body, context)
        return _Facts(located, introductions=tuple(introductions), statements=tuple(statements))
    if isinstance(body, PuDecision):
        return _Facts(located, decisions=(_decision(located, body, context),))
    return None


def _order(item: UsageRowEvidence | IntroductionEvidence | AllowanceStatement | DecisionEvidence) -> tuple[int, int]:
    return item.round, item.ref.number or 0


def _subject(title: str) -> str:
    return compact(_TITLE_CORRECTED.sub("", _TITLE_NUMBER.sub("", title)))


def _supersedes(later: DecisionEvidence, earlier: DecisionEvidence) -> bool:
    """Whether ``later`` replaces ``earlier`` rather than adding to it."""
    same_car = (later.round, later.decision.car_number) == (earlier.round, earlier.decision.car_number)
    if not same_car or (later.ref.number or 0) <= (earlier.ref.number or 0):
        return False
    return _subject(later.ref.title) == _subject(earlier.ref.title) or set(later.elements) == set(earlier.elements)


def _current(decisions: list[DecisionEvidence]) -> tuple[list[DecisionEvidence], list[WithdrawnDocument]]:
    """The decisions still standing, and each one a later decision replaced."""
    standing: list[DecisionEvidence] = []
    replaced: list[WithdrawnDocument] = []
    for item in decisions:
        later = next((other for other in decisions if _supersedes(other, item)), None)
        if later is None:
            standing.append(item)
        else:
            replaced.append(WithdrawnDocument(item.ref.title, item.ref.url, f"replaced by {later.ref.title}"))
    return standing, replaced


@dataclass(frozen=True)
class _Read:
    """The corpus split into what can count, what cannot be read, and what was taken back."""

    located: tuple[tuple[SourceDocument, _Located], ...]
    unread: tuple[UnreadDocument, ...]
    withdrawn: tuple[WithdrawnDocument, ...]


def _read(sources: SeasonSources, context: SeasonContext) -> _Read:
    located: list[tuple[SourceDocument, _Located]] = []
    unread: list[UnreadDocument] = []
    withdrawn = [
        WithdrawnDocument(source.title, source.url, source.withdrawn)
        for source in sources.documents
        if source.withdrawn is not None
    ]
    for source in (document for document in sources.documents if document.withdrawn is None):
        item = _locate(source, context)
        if isinstance(item, UnreadDocument):
            unread.append(item)
        else:
            located.append((source, item))

    # A notice taking back an earlier document of the same event removes it.
    taken_back = {(item.round, number): item.ref for _, item in located for number in item.parsed.withdraws}
    standing = [(source, item) for source, item in located if (item.round, item.ref.number) not in taken_back]
    withdrawn.extend(
        WithdrawnDocument(source.title, source.url, f"withdrawn by {taken_back[(item.round, item.ref.number)].title}")
        for source, item in located
        if (item.round, item.ref.number) in taken_back
    )
    return _Read(located=tuple(standing), unread=tuple(unread), withdrawn=tuple(withdrawn))


def gather_evidence(sources: SeasonSources, context: SeasonContext) -> Evidence:
    """Read every stored document of the season into evidence."""
    corpus = _read(sources, context)
    unread = list(corpus.unread)
    facts: list[_Facts] = []
    for source, located in corpus.located:
        try:
            found = _facts(located, context)
        except DocumentParseError as exc:
            unread.append(UnreadDocument(title=source.title, url=source.url, event=source.event, reason=str(exc)))
            continue
        if found is not None:
            facts.append(found)

    decisions, replaced = _current([row for item in facts for row in item.decisions])
    latest = max(facts, key=lambda item: (item.located.round, item.located.ref.number or 0), default=None)
    return Evidence(
        usage=tuple(sorted((row for item in facts for row in item.usage), key=_order)),
        introductions=tuple(sorted((row for item in facts for row in item.introductions), key=_order)),
        statements=tuple(sorted((row for item in facts for row in item.statements), key=_order)),
        decisions=tuple(sorted(decisions, key=_order)),
        unread=tuple(unread),
        withdrawn=(*corpus.withdrawn, *replaced),
        latest=(latest.located.round, latest.located.ref) if latest else None,
    )
