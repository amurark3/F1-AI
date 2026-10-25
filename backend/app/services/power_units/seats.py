"""Which car a document row is about, when the documents print cars by driver.

The FIA counts power-unit usage per *car*: Article B8.2.7 deems a replacement
driver to be the original driver, so a stand-in uses — and adds to — the
allocation of the car they take over. The documents print each row under the
number of a driver, though: at Monza 2026 Liam Lawson raced Red Bull's second
car as number 30 while Yuki Tsunoda raced Lawson's Racing Bulls car as number
22, and both rows carried the counts of the car, not of the man.

A seat is one team's car, keyed by the number it opened the season with (Red
Bull #6). Two questions are kept apart, because the 2026 documents showed they
can have different answers for the same weekend:

*Which car a document row is about* is settled by the team and number the row
is printed under. A usage report lists every car, so its rows settle each
other: within a team, a row under a seat's opening number is that seat, and a
lone row under any other number is the team's remaining seat. That label then
stands for later documents printing the same team and number — a decision
about "car 30, Oracle Red Bull Racing" is about whichever Red Bull car the
reports print as 30.

*Who raced the car* comes from f1db's race-weekend entries, which record the
race. The two disagree exactly when a Friday report is printed before a line-up
change reaches it: Azerbaijan's still listed "30 Red Bull … Lawson" with the
counts of Red Bull's #6 car, while Isack Hadjar was back in it for the race.
Counts follow the printed label; the name beside the car follows the race.

Anything these rules cannot settle is a warning and goes unattributed — never
a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from app.data.power_units.season_context import Entry, SeasonContext
    from app.services.power_units.evidence import Evidence, UsageRowEvidence


@dataclass(frozen=True)
class Seat:
    """One team's car for the season."""

    seat_id: str
    constructor_id: str
    team: str
    opening_number: int


@dataclass(frozen=True)
class Occupant:
    """Who raced a seat at one round, and under which number (from f1db)."""

    round: int
    car_number: int
    driver_id: str
    driver_name: str
    driver_code: str

    def as_dict(self) -> dict:
        return {"id": self.driver_id, "name": self.driver_name, "code": self.driver_code, "car_number": self.car_number}


@dataclass(frozen=True)
class SeatMap:
    """Every seat, who raced it when, and how the reports labelled it."""

    seats: tuple[Seat, ...]
    #: ``{seat_id: occupants in round order}`` from the race-weekend entries.
    occupants: Mapping[str, tuple[Occupant, ...]]
    #: ``{(round, team_id, number): seat_id}`` as each usage report printed it.
    labels: Mapping[tuple[int, str, int], str]
    warnings: tuple[str, ...] = ()

    def seat_for(self, round_num: int, team_id: str | None, car_number: int) -> Seat | None:
        """The car a row printed under ``team_id`` and ``car_number`` is about.

        ``team_id`` is ``None`` when the printed team matched no constructor;
        the number is then looked up across every team.
        """
        team_seats = [seat for seat in self.seats if team_id is None or seat.constructor_id == team_id]
        opening = [seat for seat in team_seats if seat.opening_number == car_number]
        if len(opening) == 1:
            return opening[0]
        labelled = self._labelled(round_num, team_id, car_number)
        if labelled is not None:
            return labelled
        raced = [
            seat
            for seat in team_seats
            if any(item.round == round_num and item.car_number == car_number for item in self.occupants[seat.seat_id])
        ]
        return raced[0] if len(raced) == 1 else None

    def _labelled(self, round_num: int, team_id: str | None, car_number: int) -> Seat | None:
        matches = [
            (label_round, seat_id)
            for (label_round, label_team, number), seat_id in self.labels.items()
            if number == car_number and label_round <= round_num and team_id in (None, label_team)
        ]
        if not matches:
            return None
        seat_id = max(matches)[1]
        return next(seat for seat in self.seats if seat.seat_id == seat_id)


def _seed(context: SeasonContext) -> tuple[Seat, ...]:
    """The opening line-up: every car of f1db's first round of the season.

    Before f1db publishes a round of the season there is no line-up, and no
    printed team can be told from another either — so no seats, which the
    service reports as such rather than guessing teams from report text.
    """
    if not context.entries:
        return ()
    first = min(entry.round for entry in context.entries)
    return tuple(
        Seat(
            seat_id=f"{entry.constructor_id}-{entry.car_number}",
            constructor_id=entry.constructor_id,
            team=entry.constructor_name,
            opening_number=entry.car_number,
        )
        for entry in context.entries_at(first)
    )


def _settle_team(
    team_seats: list[Seat],
    numbers: list[int],
    remembered: Mapping[int, str],
) -> tuple[dict[int, str], list[int]]:
    """Match the numbers one team printed in one line-up to the team's seats.

    Opening numbers first; then a number already tied to a seat (a permanent
    swap); then a lone leftover takes the lone free seat (a stand-in).
    """
    settled: dict[int, str] = {}
    free = {seat.seat_id for seat in team_seats}
    for number in numbers:
        seat = next((s for s in team_seats if s.opening_number == number and s.seat_id in free), None)
        if seat is not None:
            settled[number] = seat.seat_id
            free.discard(seat.seat_id)
    leftovers = [number for number in numbers if number not in settled]
    for number in leftovers:
        if remembered.get(number) in free:
            settled[number] = remembered[number]
            free.discard(remembered[number])
    leftovers = [number for number in numbers if number not in settled]
    if len(leftovers) == 1 and len(free) == 1:
        settled[leftovers[0]] = free.pop()
        leftovers = []
    return settled, leftovers


def _by_team(pairs: Iterable[tuple[str | None, int]]) -> dict[str, list[int]]:
    teams: dict[str, list[int]] = {}
    for team_id, number in pairs:
        if team_id is not None:
            teams.setdefault(team_id, []).append(number)
    return teams


def _label_reports(seats: tuple[Seat, ...], usage: tuple[UsageRowEvidence, ...]) -> tuple[dict, list[str]]:
    labels: dict[tuple[int, str, int], str] = {}
    remembered: dict[str, dict[int, str]] = {}
    warnings: list[str] = []
    for round_num in sorted({row.round for row in usage}):
        rows = [(row.team_id, row.car_number) for row in usage if row.round == round_num]
        for team_id, numbers in _by_team(rows).items():
            team_seats = [seat for seat in seats if seat.constructor_id == team_id]
            settled, unsettled = _settle_team(team_seats, numbers, remembered.get(team_id, {}))
            remembered[team_id] = {**remembered.get(team_id, {}), **settled}
            labels.update({(round_num, team_id, number): seat_id for number, seat_id in settled.items()})
            warnings.extend(
                f"Round {round_num}: the usage report's {team_id} car #{number} matches no single car, "
                "so its counts are not attributed."
                for number in unsettled
            )
    return labels, warnings


def _occupant(entry: Entry) -> Occupant:
    return Occupant(entry.round, entry.car_number, entry.driver_id, entry.driver_name, entry.driver_code)


def _occupants(seats: tuple[Seat, ...], context: SeasonContext) -> dict[str, tuple[Occupant, ...]]:
    occupants: dict[str, list[Occupant]] = {seat.seat_id: [] for seat in seats}
    remembered: dict[str, dict[int, str]] = {}
    for round_num in sorted({entry.round for entry in context.entries}):
        entries = context.entries_at(round_num)
        for team_id, numbers in _by_team((entry.constructor_id, entry.car_number) for entry in entries).items():
            team_seats = [seat for seat in seats if seat.constructor_id == team_id]
            settled, _ = _settle_team(team_seats, numbers, remembered.get(team_id, {}))
            remembered[team_id] = {**remembered.get(team_id, {}), **settled}
            for entry in entries:
                if entry.constructor_id == team_id and entry.car_number in settled:
                    occupants[settled[entry.car_number]].append(_occupant(entry))
    return {seat_id: tuple(items) for seat_id, items in occupants.items()}


def assign_seats(context: SeasonContext, evidence: Evidence) -> SeatMap:
    """Every seat of the season, who raced it, and how the reports labelled it."""
    seats = _seed(context)
    labels, warnings = _label_reports(seats, evidence.usage)
    return SeatMap(
        seats=seats,
        occupants=MappingProxyType(_occupants(seats, context)),
        labels=MappingProxyType(labels),
        warnings=tuple(warnings),
    )
