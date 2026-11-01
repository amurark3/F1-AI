"""HTTP router for the Telemetry Lab: speed map, head-to-head and tyre degradation.

Every answer is a plain dict with ``available`` and, when there is nothing to
show, a ``reason`` and ``message`` the page shows as is:

* ``pending``: the OpenF1 load outlived this request's wait and carries on; the
  page polls and the next request joins the same load.
* ``openf1_live``: OpenF1 refuses the public while an F1 session is live.
  Sessions already kept still answer.
* ``no_session`` / ``no_driver`` / ``no_lap`` / ``no_telemetry`` / ``no_stints``:
  the data does not exist (yet).
"""

from collections.abc import Callable, Hashable
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Path, Query
import structlog

from app.api.errors import client_error
from app.api.schemas.analysis import CompareQuery, DegradationQuery, SessionQuery, TrackMapQuery
from app.api.single_flight import SingleFlight
from app.config import ANALYSIS_WAIT_SECONDS
from app.data.openf1.client import OpenF1LiveLockoutError, OpenF1UnavailableError
from app.services.analysis.common import (
    REASON_ERROR,
    REASON_LOADING,
    REASON_OPENF1_LIVE,
    REASON_OPENF1_UNAVAILABLE,
    AnalysisUnavailableError,
    DriverLap,
    SessionRef,
    unavailable,
)
from app.services.analysis.comparison import build_comparison
from app.services.analysis.degradation import build_degradation
from app.services.analysis.track_map import build_track_map
from app.services.analysis.weekend import build_lap_list, build_weekend

logger = structlog.get_logger()

router = APIRouter(prefix="/analysis", tags=["analysis"])

flights: SingleFlight[dict] = SingleFlight("analysis")

# OpenF1 holds lap and car data from 2023.
FIRST_SEASON = 2023

Year = Annotated[int, Path(ge=FIRST_SEASON, le=2100)]
Round = Annotated[int, Path(ge=1, le=30)]


async def _answer(key: Hashable, work: Callable[[], dict]) -> dict:
    try:
        result = await flights.run(key, work, ANALYSIS_WAIT_SECONDS)
    except AnalysisUnavailableError as exc:
        return unavailable(exc.reason)
    except OpenF1LiveLockoutError:
        return unavailable(REASON_OPENF1_LIVE)
    except OpenF1UnavailableError as exc:
        logger.warning("api.analysis.openf1_unavailable", key=str(key), error=str(exc))
        return unavailable(REASON_OPENF1_UNAVAILABLE)
    except Exception as exc:
        return {**unavailable(REASON_ERROR), **client_error("api.analysis.error", exc, key=str(key))}
    return unavailable(REASON_LOADING) if result is None else result


@router.get("/{year}/{round_num}/sessions")
async def get_sessions(year: Year, round_num: Round) -> dict:
    """The round's sessions, from the calendar."""
    return await _answer(("sessions", year, round_num), partial(build_weekend, year, round_num))


@router.get("/{year}/{round_num}/laps")
async def get_laps(year: Year, round_num: Round, query: Annotated[SessionQuery, Query()]) -> dict:
    """Every driver's timed laps in a session, quickest driver first."""
    ref = SessionRef(year, round_num, query.session)
    return await _answer(("laps", ref), partial(build_lap_list, ref))


@router.get("/{year}/{round_num}/track-map")
async def get_track_map(year: Year, round_num: Round, query: Annotated[TrackMapQuery, Query()]) -> dict:
    """One lap round the circuit, coloured by speed, with braking and high-speed zones."""
    ref, pick = SessionRef(year, round_num, query.session), DriverLap(query.driver.upper(), query.lap)
    return await _answer(("track-map", ref, pick), partial(build_track_map, ref, pick))


@router.get("/{year}/{round_num}/compare")
async def get_comparison(year: Year, round_num: Round, query: Annotated[CompareQuery, Query()]) -> dict:
    """Two laps side by side: traces, delta, and where each driver gains."""
    ref = SessionRef(year, round_num, query.session)
    pick_a, pick_b = DriverLap(query.a.upper(), query.lap_a), DriverLap(query.b.upper(), query.lap_b)
    return await _answer(("compare", ref, pick_a, pick_b), partial(build_comparison, ref, pick_a, pick_b))


@router.get("/{year}/{round_num}/tyre-degradation")
async def get_tyre_degradation(year: Year, round_num: Round, query: Annotated[DegradationQuery, Query()]) -> dict:
    """Lap time against tyre age, per stint and per compound, with the laps left out and why."""
    ref = SessionRef(year, round_num, query.session)
    return await _answer(("tyre-degradation", ref), partial(build_degradation, ref))
