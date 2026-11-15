"""Query schemas for the Telemetry Lab API: validated before any OpenF1 request is made."""

from pydantic import BaseModel, Field

SESSION_PATTERN = r"^(FP1|FP2|FP3|SQ|S|Q|R)$"
RACE_SESSION_PATTERN = r"^(S|R)$"
DRIVER_PATTERN = r"^[A-Za-z]{3}$"
MAX_LAP = 200
SEGMENTS = 3


class SessionQuery(BaseModel):
    """A session of the round, by the app's code."""

    session: str = Field("Q", pattern=SESSION_PATTERN)


class TrackMapQuery(SessionQuery):
    """One driver's lap; no lap number means their fastest valid lap."""

    driver: str = Field(pattern=DRIVER_PATTERN)
    lap: int | None = Field(None, ge=1, le=MAX_LAP)
    # Qualifying: the default lap is the fastest valid one inside this segment (1-3).
    segment: int | None = Field(None, ge=1, le=SEGMENTS)


class CompareQuery(SessionQuery):
    """Two drivers' laps; no lap number means each one's fastest valid lap."""

    a: str = Field(pattern=DRIVER_PATTERN)
    b: str = Field(pattern=DRIVER_PATTERN)
    lap_a: int | None = Field(None, ge=1, le=MAX_LAP)
    lap_b: int | None = Field(None, ge=1, le=MAX_LAP)
    # Qualifying: each default lap is that driver's fastest valid one inside this segment (1-3).
    segment: int | None = Field(None, ge=1, le=SEGMENTS)


class DegradationQuery(BaseModel):
    """A race-like session: the grand prix or the sprint."""

    session: str = Field("R", pattern=RACE_SESSION_PATTERN)
