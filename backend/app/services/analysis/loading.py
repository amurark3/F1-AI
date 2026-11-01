"""Load a session and one driver's lap trace, or say exactly what is missing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.data.openf1.session_laps import load_session_laps
from app.data.openf1.telemetry import load_lap_trace
from app.services.analysis.common import (
    REASON_NO_DRIVER,
    REASON_NO_LAP,
    REASON_NO_SESSION,
    REASON_NO_TELEMETRY,
    AnalysisUnavailableError,
    DriverLap,
    SessionRef,
)
from app.services.analysis.lap_selection import LapChoice, choose_lap

if TYPE_CHECKING:
    from app.data.openf1.session_laps import SessionLaps
    from app.data.openf1.sessions import EntryDriver
    from app.data.openf1.telemetry import LapTrace


@dataclass(frozen=True)
class LoadedLap:
    driver: EntryDriver
    choice: LapChoice
    trace: LapTrace


def require_session(ref: SessionRef) -> SessionLaps:
    session = load_session_laps(ref.year, ref.round, ref.code)
    if session is None or not session.laps:
        raise AnalysisUnavailableError(REASON_NO_SESSION)
    return session


def require_lap(session: SessionLaps, pick: DriverLap) -> LoadedLap:
    driver = session.driver_by_code(pick.code)
    if driver is None:
        raise AnalysisUnavailableError(REASON_NO_DRIVER)
    choice = choose_lap(session, driver.number, pick.lap)
    if choice is None:
        raise AnalysisUnavailableError(REASON_NO_LAP)
    trace = load_lap_trace(session, choice.lap)
    if trace is None:
        raise AnalysisUnavailableError(REASON_NO_TELEMETRY)
    return LoadedLap(driver=driver, choice=choice, trace=trace)
