"""Tyre degradation for a race: every lap with why it counts or not, and the fitted wear rates.

Every lap is returned, excluded ones included, each with its status, so the page
can grey them out with the reason instead of quietly dropping them. Measured:
lap times, stints and compounds, tyre age at the start of each set, the gap to
the car ahead, rain and neutralisations. Modelled, and listed under
``modeled``: fuel-corrected times, the fitted rates, the traffic flag, and the
stint boundaries snapped onto OpenF1's pit-out laps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import TRAFFIC_GAP_SECONDS
from app.data.openf1.race_context import load_race_context
from app.services.analysis.common import (
    REASON_NO_STINTS,
    SOURCE,
    AnalysisUnavailableError,
    driver_json,
    session_json,
)
from app.services.analysis.degradation_model import MIN_FIT_LAPS, compound_summary, fuel_model, stint_fit
from app.services.analysis.lap_status import (
    OUTLIER_FACTOR,
    STATUS_LABELS,
    LapFacts,
    all_spans,
    driver_statuses,
    neutralised,
    restart_laps,
    span_of,
)
from app.services.analysis.loading import require_session

if TYPE_CHECKING:
    from app.data.openf1.race_context import RaceContext
    from app.data.openf1.session_laps import SessionLaps
    from app.services.analysis.common import SessionRef
    from app.services.analysis.degradation_model import FuelModel
    from app.services.analysis.lap_status import StintSpan

NO_FUEL_MODEL_WARNING = (
    "Lap times are not fuel-corrected here: the start fuel of a sprint, or of this season, is not modelled."
)


def _driver_order(session: SessionLaps, context: RaceContext) -> list[int]:
    classified = [number for number in context.classification if number in session.drivers]
    return classified + sorted(number for number in session.drivers if number not in classified)


def _lap_rows(session: SessionLaps, context: RaceContext, number: int, fuel: FuelModel | None) -> list[dict]:
    laps = session.laps_of(number)
    spans = all_spans(session, context).get(number, [])
    facts = LapFacts(spans, restart_laps(laps, session.windows), session.windows, context.rain)
    statuses = driver_statuses(laps, facts, context.gaps)
    code = session.drivers[number].code
    rows = []
    for lap in laps:
        span = span_of(spans, lap.number)
        rows.append(
            {
                "driver": code,
                "lap": lap.number,
                "time": lap.time,
                "corrected": None if fuel is None or lap.time is None else fuel.corrected(lap.number, lap.time),
                "tyre_age": None if span is None else span.tyre_age(lap.number),
                "compound": None if span is None else span.compound,
                "stint": None if span is None else span.stint,
                "status": statuses[lap.number],
                "gap_ahead": context.gaps.get((number, lap.number)),
            }
        )
    return rows


def _stint_rows(code: str, spans: list[StintSpan], rows: list[dict]) -> list[dict]:
    return [
        {
            "driver": code,
            "stint": span.stint,
            "compound": span.compound,
            "start_lap": span.start,
            "end_lap": span.end,
            "tyre_life_start": span.tyre_life_start,
            "boundary_checked": span.checked,
            "fit": stint_fit([row for row in rows if row["stint"] == span.stint]),
        }
        for span in spans
    ]


def neutralised_bands(session: SessionLaps, leader: int | None) -> list[dict]:
    """Each neutralisation as the leader's laps it covered, for shading a lap axis."""
    if leader is None:
        return []
    laps = session.laps_of(leader)
    bands = []
    for window in session.windows:
        covered = [lap.number for lap in laps if neutralised(lap, (window,)) is not None]
        if covered:
            bands.append({"kind": window.kind, "from_lap": min(covered), "to_lap": max(covered)})
    return bands


def _assumptions(fuel: FuelModel | None) -> dict:
    return {
        "fuel": None if fuel is None else fuel.to_json(),
        "traffic_gap_seconds": TRAFFIC_GAP_SECONDS,
        "min_fit_laps": MIN_FIT_LAPS,
        "outlier_factor": OUTLIER_FACTOR,
    }


def build_degradation(ref: SessionRef) -> dict:
    session = require_session(ref)
    context = load_race_context(session)
    if not context.stints:
        raise AnalysisUnavailableError(REASON_NO_STINTS)
    fuel = fuel_model(ref.year, ref.code, max(lap.number for lap in session.laps))
    spans = all_spans(session, context)
    order = _driver_order(session, context)
    laps, stints, drivers = [], [], []
    for position, number in enumerate(order, start=1):
        driver = session.drivers[number]
        rows = _lap_rows(session, context, number, fuel)
        laps.extend(rows)
        stints.extend(_stint_rows(driver.code, spans.get(number, []), rows))
        drivers.append({**driver_json(driver), "position": position if number in context.classification else None})
    unchecked = sum(1 for stint in stints if not stint["boundary_checked"])
    warnings = [] if fuel is not None else [NO_FUEL_MODEL_WARNING]
    if unchecked:
        warnings.append(f"{unchecked} stint change(s) had no pit-out lap nearby; OpenF1's stint lap was kept.")
    return {
        "available": True,
        "pending": False,
        "source": SOURCE,
        "session": session_json(session),
        "drivers": drivers,
        "laps": laps,
        "stints": stints,
        "compounds": compound_summary(stints),
        "neutralised": neutralised_bands(session, order[0] if order else None),
        "status_labels": STATUS_LABELS,
        "assumptions": _assumptions(fuel),
        "modeled": ["corrected", "fit", "traffic", "stint_boundaries"],
        "warnings": warnings,
    }
