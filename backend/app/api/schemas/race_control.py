"""Request schemas for the Race Control v2 API."""

from typing import Optional

from pydantic import BaseModel, Field


class StrategySimulationRequest(BaseModel):
    """Inputs for the Race Control strategy simulator."""

    year: int
    race: str = "Next Grand Prix"
    team: str
    driver: str = "Selected driver"
    current_lap: int = Field(default=14, ge=1, le=70)
    starting_position: int = Field(default=6, ge=1, le=22)
    tyre_compound: str = "MEDIUM"
    tyre_age: int = Field(default=12, ge=0, le=70)
    pit_lap: int = Field(default=22, ge=1, le=70)
    traffic_risk: int = Field(default=45, ge=0, le=100)
    safety_car_probability: int = Field(default=35, ge=0, le=100)
    weather_risk: int = Field(default=20, ge=0, le=100)


class RulebookSearchRequest(BaseModel):
    """Inputs for a visual rulebook search."""

    query: str
    category: Optional[str] = None
    year: Optional[int] = None
