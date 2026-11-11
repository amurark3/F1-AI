"""One edition of a circuit reduced to the plan its finishers ran: measured, never modelled.

An upcoming race has no laps of its own, so the Command Center's "Base race
plan" is read off the latest edition of the same circuit
(:mod:`app.data.strategy.reference` decides which). This module turns that race
into planning facts:

* **The sample is the classified finishers.** A retired car's tyres describe a
  race cut short, not a strategy, and whether a car finished comes from the
  classification, never from where its stints stop (``docs/DATA_SOURCES.md``,
  accuracy rule 1).
* **Every compound a finisher ran**, in order, from the stints (OpenF1, one row
  per tyre set). Until Nov 2026 the plan named only the first and the last
  ("Soft-to-Soft two-stop") and dropped the middle stint.
* **Stop counts and stop laps** come from the published pit sheet with the
  red-flag suspension left out (:func:`app.data.pit_sheet.without_suspension`),
  not from stint boundaries, which OpenF1 opens on every pit-lane pass.
* **Pit-lane time** is OpenF1's ``pit_duration`` (pit entry to pit exit) over
  those same stops. The median, so a stop that served a penalty or replaced a
  wing does not move it.

Sequences are grouped by compounds and stop count and ranked by how many
finishers ran them; a tie goes to the sequence of the better-placed finisher.
Compounds stay Soft / Medium / Hard until the weekend's Pirelli allocation
(C1-C5) is read (plan task D2.2).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import median
from typing import TYPE_CHECKING

from app.data.stint_model import UNKNOWN_COMPOUND

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.data.f1db_pitstops import PitStop
    from app.data.race_classification import ClassifiedDriver
    from app.data.stint_model import Stint

FINISHED = "finished"
WINNER_POSITION = 1
# The quarter points of the first-stop laps: the middle half of the field.
LOWER_QUARTER = 0.25
UPPER_QUARTER = 0.75
MILLIS_PER_TENTH = 100


@dataclass(frozen=True)
class Edition:
    """Which race a plan is read from."""

    year: int
    round: int
    #: The event's name in its season's calendar, e.g. "São Paulo Grand Prix".
    name: str


@dataclass(frozen=True)
class EditionRace:
    """What the sources published for an edition's race."""

    stints: tuple[Stint, ...]
    #: The pit sheet's real stops: the red-flag suspension already left out.
    stops: tuple[PitStop, ...]
    classification: tuple[ClassifiedDriver, ...]
    #: OpenF1's pit-lane time per stop by (driver, lap); empty when it published none.
    lane_millis: dict[tuple[str, int], int]


def _quantile(values: Sequence[int], fraction: float) -> float:
    """Linear interpolation between the closest ranks, as numpy's default does."""
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _lap(value: float) -> int:
    return round(value)


def _compounds(stints: list[Stint]) -> tuple[str, ...]:
    return tuple(stint.compound or UNKNOWN_COMPOUND for stint in sorted(stints, key=lambda item: item.stint))


def _stop_laps(stops: tuple[PitStop, ...]) -> dict[str, list[int]]:
    laps: dict[str, list[int]] = {}
    for item in stops:
        laps.setdefault(item.driver_code, []).append(item.lap)
    return {code: sorted(values) for code, values in laps.items()}


def _sequences(
    sample: list[ClassifiedDriver], compounds: dict[str, tuple[str, ...]], laps: dict[str, list[int]]
) -> list[dict]:
    """The sequences the sample ran, most common first; ties to the better-placed finisher."""
    groups: dict[tuple[tuple[str, ...], int], list[ClassifiedDriver]] = {}
    for driver in sample:
        stops = laps.get(driver.driver_code, [])
        groups.setdefault((compounds[driver.driver_code], len(stops)), []).append(driver)

    def rank(item: tuple[tuple[tuple[str, ...], int], list[ClassifiedDriver]]) -> tuple[int, int]:
        return -len(item[1]), min(driver.position or 0 for driver in item[1])

    return [
        {
            "compounds": list(sequence),
            "stops": stops,
            "drivers": [driver.driver_code for driver in drivers],
            # The median lap of each stop across the drivers who ran this sequence.
            "stop_laps": [
                _lap(median(values))
                for values in zip(*(laps.get(driver.driver_code, []) for driver in drivers), strict=True)
            ],
        }
        for (sequence, stops), drivers in sorted(groups.items(), key=rank)
    ]


def _stop_counts(sample: list[ClassifiedDriver], laps: dict[str, list[int]]) -> list[dict]:
    counts = Counter(len(laps.get(driver.driver_code, [])) for driver in sample)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"stops": stops, "drivers": drivers} for stops, drivers in ranked]


def _first_stop(sample: list[ClassifiedDriver], laps: dict[str, list[int]]) -> dict | None:
    firsts = [laps[driver.driver_code][0] for driver in sample if laps.get(driver.driver_code)]
    if not firsts:
        return None
    return {
        "median_lap": _lap(median(firsts)),
        "p25_lap": _lap(_quantile(firsts, LOWER_QUARTER)),
        "p75_lap": _lap(_quantile(firsts, UPPER_QUARTER)),
        "drivers": len(firsts),
    }


def _pit_lane(
    sample: list[ClassifiedDriver], laps: dict[str, list[int]], lane_millis: dict[tuple[str, int], int]
) -> dict | None:
    times = [
        lane_millis[(driver.driver_code, lap)]
        for driver in sample
        for lap in laps.get(driver.driver_code, [])
        if (driver.driver_code, lap) in lane_millis
    ]
    if not times:
        return None
    return {"median_seconds": round(median(times) / MILLIS_PER_TENTH) / 10, "stops": len(times)}


def summarize_edition(edition: Edition, race: EditionRace) -> dict | None:
    """The edition's plan, or None when no classified finisher has stints."""
    by_driver: dict[str, list[Stint]] = {}
    for item in race.stints:
        by_driver.setdefault(item.driver_code, []).append(item)
    sample = [driver for driver in race.classification if driver.status == FINISHED and driver.driver_code in by_driver]
    if not sample:
        return None

    compounds = {driver.driver_code: _compounds(by_driver[driver.driver_code]) for driver in sample}
    laps = _stop_laps(race.stops)
    distance = [driver.laps_completed for driver in sample if driver.laps_completed is not None]
    return {
        "source_year": edition.year,
        "round": edition.round,
        "event_name": edition.name,
        "finishers": len(sample),
        "total_laps": max(distance) if distance else max(item.end_lap for item in race.stints),
        "winner": next((driver.driver_code for driver in sample if driver.position == WINNER_POSITION), None),
        "sequences": _sequences(sample, compounds, laps),
        "stop_counts": _stop_counts(sample, laps),
        "first_stop": _first_stop(sample, laps),
        "pit_lane": _pit_lane(sample, laps, race.lane_millis),
    }
