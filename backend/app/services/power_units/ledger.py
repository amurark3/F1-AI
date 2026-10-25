"""Each car's elements, unit by unit: where each one first ran, and what it cost.

For every seat and element type the ledger numbers units the way the FIA does
— the 5th ICE is the fifth new engine of the season — and places each at the
round it was introduced:

* from a *New PU Elements* report or a stewards' decision, which name the
  round outright (``report``);
* otherwise from two consecutive usage reports: a unit counted going into
  round N but not into round M < N arrived between them — at round M exactly
  when no other round lies between (``derived``). With rounds in between, the
  ledger gives the window instead of picking one.

The count is the FIA's own: its latest usage report, plus units named since.
When a later report counts fewer units than earlier numbering implied — Kimi
Antonelli's 4th exhaust was announced at Belgium 2026, counted for two rounds,
then dropped from every report from Monza on — the unit stays on the ledger,
marked ``not_counted_from`` that round, and out of the total.

A unit past the season's allowance should be named by a decision of its
round. One that is not is ``pending`` while its round is the latest the
documents reach — stewards decide hours after the Technical Delegate reports —
and ``not_found`` after that: a decision this corpus does not hold, which the
screen says rather than inventing a penalty.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.services.power_units.evidence import DecisionEvidence, DocumentRef, Evidence, IntroductionEvidence
    from app.services.power_units.seats import Seat, SeatMap

SOURCE_REPORT = "report"
SOURCE_DERIVED = "derived"

STATUS_NONE = "none"
STATUS_DECIDED = "decided"
STATUS_PENDING = "pending"
STATUS_NOT_FOUND = "not_found"


@dataclass(frozen=True)
class Season:
    """The season facts every ledger is built against."""

    codes: tuple[str, ...]
    allowance: Mapping[str, int]
    #: Calendar rounds, ascending.
    rounds: tuple[int, ...]
    #: The latest round any document reaches.
    latest_round: int | None

    def round_before(self, round_num: int) -> int | None:
        earlier = [item for item in self.rounds if item < round_num]
        return earlier[-1] if earlier else None


@dataclass(frozen=True)
class Part:
    """One unit of one element type."""

    code: str
    number: int
    #: The round it was introduced at, when the documents pin it down.
    round: int | None
    #: The first and last round it could have arrived at, when they do not.
    window: tuple[int, int] | None
    source: str
    beyond_allowance: bool
    #: The first round whose usage report no longer counts this unit.
    not_counted_from: int | None = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "number": self.number,
            "round": self.round,
            "window": list(self.window) if self.window else None,
            "source": self.source,
            "beyond_allowance": self.beyond_allowance,
            "not_counted_from": self.not_counted_from,
        }


@dataclass(frozen=True)
class ElementLedger:
    code: str
    allowance: int | None
    used: int
    parts: tuple[Part, ...]

    @property
    def over_by(self) -> int:
        return max(0, self.used - self.allowance) if self.allowance is not None else 0


@dataclass(frozen=True)
class RoundActivity:
    """What happened to one car at one round."""

    round: int
    new_parts: tuple[Part, ...]
    decisions: tuple[DecisionEvidence, ...]
    penalty_status: str
    sources: tuple[DocumentRef, ...]


@dataclass(frozen=True)
class SeatLedger:
    seat: Seat
    elements: tuple[ElementLedger, ...]
    rounds: tuple[RoundActivity, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _SeatEvidence:
    snapshots: tuple[tuple[int, Mapping[str, int]], ...]
    introductions: tuple[IntroductionEvidence, ...]
    decisions: tuple[DecisionEvidence, ...]


def _for_seat(seat: Seat, evidence: Evidence, seat_map: SeatMap) -> _SeatEvidence:
    def mine(round_num: int, team_id: str | None, car_number: int) -> bool:
        found = seat_map.seat_for(round_num, team_id, car_number)
        return found is not None and found.seat_id == seat.seat_id

    return _SeatEvidence(
        snapshots=tuple(
            (row.round, row.counts) for row in evidence.usage if mine(row.round, row.team_id, row.car_number)
        ),
        introductions=tuple(item for item in evidence.introductions if mine(item.round, item.team_id, item.car_number)),
        decisions=tuple(
            item for item in evidence.decisions if mine(item.round, item.team_id, item.decision.car_number)
        ),
    )


def _explicit_rounds(code: str, mine: _SeatEvidence) -> dict[int, int]:
    """``{unit number: round}`` wherever a report or decision names the round."""
    named = [(item.number, item.round) for item in mine.introductions if item.code == code]
    named += [
        (number, decision.round)
        for decision in mine.decisions
        for element_code, number in decision.elements
        if element_code == code
    ]
    rounds: dict[int, int] = {}
    for number, round_num in named:
        rounds.setdefault(number, round_num)
    return rounds


def _derived_part(code: str, number: int, between: tuple[int | None, int], season: Season) -> Part:
    after, before = between
    first = after if after is not None else (season.rounds[0] if season.rounds else None)
    last = season.round_before(before)
    beyond = number > season.allowance[code] if code in season.allowance else False
    if first is None or last is None or last < first:
        return Part(code, number, None, None, SOURCE_DERIVED, beyond)
    if first == last:
        return Part(code, number, first, None, SOURCE_DERIVED, beyond)
    return Part(code, number, None, (first, last), SOURCE_DERIVED, beyond)


def _used(code: str, mine: _SeatEvidence, explicit: Mapping[int, int]) -> int:
    """The FIA's own count: its latest usage report, plus units named since it."""
    if not mine.snapshots:
        return max(explicit, default=0)
    latest_round, counts = mine.snapshots[-1]
    since = [number for number, round_num in explicit.items() if round_num >= latest_round]
    return max([counts.get(code, 0), *since])


def _uncounted(part: Part, snapshots: tuple[tuple[int, Mapping[str, int]], ...]) -> Part:
    """``part`` marked with the first report after it that stopped counting it."""
    dropped = next(
        round_num
        for round_num, counts in snapshots
        if (part.round is None or round_num > part.round) and counts.get(part.code, 0) < part.number
    )
    return replace(part, not_counted_from=dropped)


def _element_ledger(code: str, mine: _SeatEvidence, season: Season) -> tuple[ElementLedger, list[str]]:
    allowance = season.allowance.get(code)
    explicit = _explicit_rounds(code, mine)
    parts = {
        number: Part(code, number, round_num, None, SOURCE_REPORT, allowance is not None and number > allowance)
        for number, round_num in explicit.items()
    }
    previous: tuple[int | None, int] = (None, 0)
    for round_num, counts in mine.snapshots:
        count = counts.get(code, 0)
        for number in range(previous[1] + 1, count + 1):
            parts.setdefault(number, _derived_part(code, number, (previous[0], round_num), season))
        previous = (round_num, max(count, previous[1]))

    used = _used(code, mine, explicit)
    parts = {number: _uncounted(part, mine.snapshots) if number > used else part for number, part in parts.items()}
    warnings = [
        f"{code} #{number}: the documents do not show where it was introduced."
        for number in range(1, used + 1)
        if number not in parts
    ]
    for number in range(1, used + 1):
        parts.setdefault(number, _derived_part(code, number, (None, 0), season))
    ordered = tuple(parts[number] for number in sorted(parts))
    return ElementLedger(code=code, allowance=allowance, used=used, parts=ordered), warnings


def _status(round_num: int, over: list[Part], decisions: tuple[DecisionEvidence, ...], season: Season) -> str:
    if over:
        return STATUS_PENDING if round_num == season.latest_round else STATUS_NOT_FOUND
    return STATUS_DECIDED if decisions else STATUS_NONE


def _activity(round_num: int, parts: list[Part], mine: _SeatEvidence, season: Season) -> RoundActivity:
    decisions = tuple(item for item in mine.decisions if item.round == round_num)
    covered = {element for decision in decisions for element in decision.elements}
    over = [
        part
        for part in parts
        if part.beyond_allowance and part.not_counted_from is None and (part.code, part.number) not in covered
    ]
    sources = {item.ref.url: item.ref for item in mine.introductions if item.round == round_num}
    return RoundActivity(
        round=round_num,
        new_parts=tuple(parts),
        decisions=decisions,
        penalty_status=_status(round_num, over, decisions, season),
        sources=tuple(sources.values()),
    )


def build_seat_ledger(seat: Seat, evidence: Evidence, seat_map: SeatMap, season: Season) -> SeatLedger:
    """Every element and every round of activity for one car."""
    mine = _for_seat(seat, evidence, seat_map)
    elements: list[ElementLedger] = []
    warnings: list[str] = []
    for code in season.codes:
        element, element_warnings = _element_ledger(code, mine, season)
        elements.append(element)
        warnings.extend(element_warnings)

    by_round: dict[int, list[Part]] = {}
    for part in (part for element in elements for part in element.parts if part.round is not None):
        by_round.setdefault(part.round, []).append(part)
    rounds = sorted(set(by_round) | {decision.round for decision in mine.decisions})
    return SeatLedger(
        seat=seat,
        elements=tuple(elements),
        rounds=tuple(_activity(round_num, by_round.get(round_num, []), mine, season) for round_num in rounds),
        warnings=tuple(warnings),
    )
