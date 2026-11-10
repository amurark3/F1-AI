"""The Command Center's "Base race plan": the latest edition's measured strategy, in words.

The numbers come from :func:`app.data.strategy.circuit_strategy_reference`: the
latest same-circuit edition's finishers, their compound sequences, stops,
first-stop laps and pit-lane time. This module only says them, and says where
they came from (``docs/DATA_SOURCES.md``: every number shows its source and
its state).

What the panel said until Nov 2026, and why each went:

* "Field ran a Soft-to-Soft two-stop here in 2022": the opening and finishing
  compounds only, from a 2022 edition (FastF1 could no longer load 2023-2025).
  The plan now names every compound, the share of finishers that ran it, and
  the edition's year; an edition before 2026 is "previous regulations".
* Undercut 1.4 s and overcut 0.9 s were fixed formulas of circuit type and
  weekend format, and rejoin traffic a guess from the first-stop spread.
  Nothing measures them, so none is shown.
* Confidence was "high" whenever a prediction snapshot existed. It now comes
  from the sample (finishers) and how recent and relevant the edition is.
* With no edition the panel made up a Medium-Hard one-stop at 42% distance and
  a 21 s pit loss. It now says why there is no plan.

When the race-day forecast (P0b.1) is at or above the risk register's "High"
rain cut-off, the plan is flagged as the secondary branch: it is a dry race's.
"""

from __future__ import annotations

from app.data.pit_sheet import F1DB_SOURCE as SHEET_F1DB, JOLPICA_SOURCE as SHEET_JOLPICA
from app.data.race_classification import JOLPICA_SOURCE as RESULTS_JOLPICA, OPENF1_SOURCE as RESULTS_OPENF1
from app.data.strategy.edition_sources import PIT_LANE_SOURCE, STINTS_SOURCE
from app.data.strategy.reference import OPENF1_FIRST_SEASON
from app.services.race_control.risk import RAIN_RISK_HIGH

PLAN_TITLE = "Base race plan"

# The first season of the current technical regulations. An edition before it
# planned a car, tyres and power unit that no longer race.
REGULATIONS_ERA_START = 2026
# A full grid's finishers, less the usual retirements: below this the sample is thin.
FULL_SAMPLE_FINISHERS = 15
CONFIDENCE_LEVELS = ("low", "medium", "high")
# Sequences named after the headline one.
ALTERNATIVES_SHOWN = 2

STOP_WORDS = {0: "no-stop", 1: "one-stop", 2: "two-stop", 3: "three-stop", 4: "four-stop"}
STOPPED = {0: "made no stop", 1: "stopped once", 2: "stopped twice"}

SOURCE_NAMES = {
    STINTS_SOURCE: "OpenF1 stints",
    SHEET_JOLPICA: "Jolpica pit stops",
    SHEET_F1DB: "f1db pit stops",
    RESULTS_OPENF1: "OpenF1 classification",
    RESULTS_JOLPICA: "Jolpica classification",
    PIT_LANE_SOURCE: "OpenF1 pit-lane times",
}

COMPOUNDS_NOTE = "Compounds read Soft / Medium / Hard: the weekend's Pirelli allocation (C1–C5) is not read yet."
UNMEASURED_NOTE = "No undercut, overcut or rejoin-traffic figure is shown: nothing measures them yet."
RETRY_NOTE = "It is tried again in a few minutes."
NO_EDITION = (
    f"No baseline plan: this circuit has no completed race since {OPENF1_FIRST_SEASON}, "
    "OpenF1's first season, to read tyre stints and pit stops from."
)
NO_PIT_LANE = "pit-lane time not published"


def compound_name(code: str) -> str:
    """A compound as the panel prints it: "MEDIUM" → "Medium"."""
    return code.title()


def sequence_name(compounds: list[str]) -> str:
    return "–".join(compound_name(code) for code in compounds)


def stop_word(stops: int) -> str:
    return STOP_WORDS.get(stops, f"{stops}-stop")


def previous_regulations(edition_year: int, planning_year: int) -> bool:
    return edition_year < REGULATIONS_ERA_START <= planning_year


def plan_confidence(edition_year: int, planning_year: int, finishers: int) -> tuple[str, str]:
    """The grade and its basis: one step down each for older rules, an older edition, a thin sample."""
    level = len(CONFIDENCE_LEVELS) - 1
    basis = [f"{finishers} finishers", f"{edition_year} edition"]
    if previous_regulations(edition_year, planning_year):
        level -= 1
        basis.append("previous regulations")
    age = planning_year - edition_year
    if age > 1:
        level -= 1
        basis.append(f"{age} seasons old")
    if finishers < FULL_SAMPLE_FINISHERS:
        level -= 1
        basis.append(f"fewer than {FULL_SAMPLE_FINISHERS} finishers")
    return CONFIDENCE_LEVELS[max(level, 0)], " · ".join(basis)


def _editions(years: list[int]) -> str:
    """ "2025 edition", or "2025 and 2024 editions"."""
    return f"{' and '.join(str(year) for year in years)} edition{'s' if len(years) > 1 else ''}"


def _where(reference: dict) -> str:
    name = reference.get("event_name") or "edition here"
    return f"the {reference['source_year']} {name}"


def _summary(reference: dict, previous: bool) -> str:
    sequences, finishers = reference["sequences"], reference["finishers"]
    head = sequences[0]
    text = (
        f"{sequence_name(head['compounds'])} {stop_word(head['stops'])}: {len(head['drivers'])} of "
        f"{finishers} finishers ran it at {_where(reference)}"
    )
    if previous:
        text += " (previous regulations)"
    if reference.get("winner") in head["drivers"]:
        text += ", the winner among them"
    text += "."
    for tied in sequences[1:]:
        if len(tied["drivers"]) == len(head["drivers"]):
            text += f" {sequence_name(tied['compounds'])} {stop_word(tied['stops'])} was as common."
    top = reference["stop_counts"][0]
    stopped = STOPPED.get(top["stops"], f"stopped {top['stops']} times")
    text += f" {top['drivers']} of {finishers} finishers {stopped}."
    first = reference.get("first_stop")
    if first:
        text += f" First stops: median L{first['median_lap']}, middle half L{first['p25_lap']}–L{first['p75_lap']}."
    return text


def _plan(reference: dict) -> dict:
    """The headline sequence on the edition's own laps, for the stint timeline.

    Each stint ends on the median lap its stop was made on. A sequence with more
    sets than stops (a tyre change under a red flag) has no lap to split on, so
    it is named but not drawn.
    """
    head, total = reference["sequences"][0], reference["total_laps"]
    compounds, stop_laps = head["compounds"], head["stop_laps"]
    stints = []
    if len(compounds) == len(stop_laps) + 1:
        starts = [1, *(lap + 1 for lap in stop_laps)]
        ends = [*stop_laps, total]
        stints = [
            {"compound": compound_name(code), "start_lap": start, "end_lap": end}
            for code, start, end in zip(compounds, starts, ends, strict=True)
        ]
    return {
        "compounds": [compound_name(code) for code in compounds],
        "stops": head["stops"],
        "drivers": head["drivers"],
        "finishers": reference["finishers"],
        "total_laps": total,
        "stints": stints,
    }


def _rain_branch(race_day: dict | None) -> dict | None:
    """The wet-race flag, graded as the risk register grades the same forecast."""
    rain = (race_day or {}).get("rain_risk")
    if rain is None or round(rain) < RAIN_RISK_HIGH:
        return None
    rain_pct = round(rain)
    return {
        "rain_pct": rain_pct,
        "threshold_pct": RAIN_RISK_HIGH,
        "note": (
            f"{race_day['confidence']}: {rain_pct}% peak rain probability in the race window, "
            "so this dry plan is the secondary branch."
        ),
    }


def _sources(reference: dict) -> list[str]:
    return [SOURCE_NAMES.get(source, source) for source in (reference.get("sources") or {}).values() if source]


def _source_note(reference: dict, previous: bool) -> str:
    sources = reference.get("sources") or {}

    def name(key: str, missing: str) -> str:
        return SOURCE_NAMES.get(sources.get(key) or "", missing)

    suspension = reference.get("suspension_entries") or 0
    left_out = f" ({suspension} red-flag suspension entries left out)" if suspension else ""
    lane = f"pit-lane time from {name('pit_lane', '')}" if sources.get("pit_lane") else NO_PIT_LANE
    return (
        f"Base plan: {_where(reference)}, {reference['finishers']} classified finishers"
        f"{', previous regulations' if previous else ''}. Compound sequences from {name('stints', 'the stints')}; "
        f"stop counts and stop laps from {name('stops', 'the pit sheet')}{left_out}; {lane}; "
        f"finishers from {name('classification', 'the classification')}."
    )


def _no_plan(reference: dict | None) -> dict:
    unread = list((reference or {}).get("unread_years") or [])
    if reference is None:
        summary = NO_EDITION
    elif unread:
        summary = (
            f"No baseline plan right now: the tyre stints, classification or pit sheet of the "
            f"{_editions(unread)} could not be read. {RETRY_NOTE}"
        )
    else:
        summary = f"No baseline plan right now: the circuit's last edition could not be read. {RETRY_NOTE}"
    return {
        "primary_call": {"title": PLAN_TITLE, "summary": summary, "confidence": None, "confidence_basis": None},
        "data_source": {
            "mode": "none",
            "edition_year": None,
            "event_name": None,
            "round": None,
            "previous_regulations": False,
            "sample_size": None,
            "sources": [],
            "unread_years": unread,
        },
        "plan": None,
        "alternatives": [],
        "stop_counts": [],
        "first_stop": None,
        "pit_model": {"pit_lane_seconds": None, "pit_lane_stops": None},
        "rain_branch": None,
        "assumptions": [UNMEASURED_NOTE],
    }


def build_baseline(planning_year: int, reference: dict | None, race_day: dict | None) -> dict:
    """The panel's plan, sources, confidence and rain flag for the season being planned."""
    if not (reference or {}).get("source_year"):
        return _no_plan(reference)

    year, finishers = reference["source_year"], reference["finishers"]
    previous = previous_regulations(year, planning_year)
    confidence, basis = plan_confidence(year, planning_year, finishers)
    unread = list(reference.get("unread_years") or [])
    pit_lane = reference.get("pit_lane") or {}
    assumptions = [_source_note(reference, previous), COMPOUNDS_NOTE, UNMEASURED_NOTE]
    if unread:
        assumptions.append(
            f"The {_editions(unread)} could not be read right now, so this plan uses {year}. {RETRY_NOTE}"
        )
    return {
        "primary_call": {
            "title": PLAN_TITLE,
            "summary": _summary(reference, previous),
            "confidence": confidence,
            "confidence_basis": basis,
        },
        "data_source": {
            "mode": "edition",
            "edition_year": year,
            "event_name": reference.get("event_name") or None,
            "round": reference.get("round"),
            "previous_regulations": previous,
            "sample_size": finishers,
            "sources": _sources(reference),
            "unread_years": unread,
        },
        "plan": _plan(reference),
        "alternatives": [
            {
                "compounds": [compound_name(code) for code in item["compounds"]],
                "stops": item["stops"],
                "drivers": len(item["drivers"]),
            }
            for item in reference["sequences"][1 : 1 + ALTERNATIVES_SHOWN]
        ],
        "stop_counts": reference["stop_counts"],
        "first_stop": reference.get("first_stop"),
        "pit_model": {
            "pit_lane_seconds": pit_lane.get("median_seconds"),
            "pit_lane_stops": pit_lane.get("stops"),
        },
        "rain_branch": _rain_branch(race_day),
        "assumptions": assumptions,
    }
