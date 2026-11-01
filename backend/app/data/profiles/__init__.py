"""Team and driver season profiles, read from the local f1db dataset."""

from app.data.profiles.drivers import driver_season
from app.data.profiles.teams import team_season

__all__ = ["driver_season", "team_season"]
