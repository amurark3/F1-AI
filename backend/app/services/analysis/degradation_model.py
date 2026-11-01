"""The modelled half of tyre degradation: fuel correction and the fitted wear rates.

**Fuel correction.** A car gets lighter, and so quicker, as fuel burns, which
hides tyre wear. Each lap is put on an empty-tank footing:
``corrected = time − k × fuel on board``, with fuel burnt evenly over the race
distance. ``k`` and the start fuel are assumptions from :mod:`app.config`,
returned with every result. They are not measured, and the correction is about
as large as the wear itself (``k × burn`` ≈ 0.04–0.06 s/lap), so the raw slope
is always reported beside the corrected one. A sprint, or a season with no
start fuel configured, gets no correction rather than a guessed one.

**Wear rate.** A straight line through each stint's clean laps, lap time
against tyre age. The slope is seconds lost per lap of tyre age. A stint needs
:data:`MIN_FIT_LAPS` clean laps to be fitted. Per compound, the median slope
across stints and its spread (interquartile range).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from app.config import FUEL_EFFECT_SECONDS_PER_KG, RACE_START_FUEL_KG

if TYPE_CHECKING:
    from collections.abc import Iterable

MIN_FIT_LAPS = 5
RACE_CODE = "R"


@dataclass(frozen=True)
class FuelModel:
    start_kg: float
    seconds_per_kg: float
    race_laps: int

    def on_board(self, lap: int) -> float:
        """Fuel at the middle of ``lap``, burnt evenly over the race distance."""
        burnt = max(lap - 0.5, 0.0) / self.race_laps
        return self.start_kg * max(1.0 - burnt, 0.0)

    def corrected(self, lap: int, time: float) -> float:
        return round(time - self.seconds_per_kg * self.on_board(lap), 3)

    @property
    def slope_effect(self) -> float:
        """How much the correction adds to a stint's slope, seconds per lap."""
        return self.seconds_per_kg * self.start_kg / self.race_laps

    def to_json(self) -> dict:
        return {
            "start_fuel_kg": self.start_kg,
            "seconds_per_kg": self.seconds_per_kg,
            "race_laps": self.race_laps,
            "slope_effect": round(self.slope_effect, 4),
        }


def fuel_model(year: int, code: str, race_laps: int) -> FuelModel | None:
    start = RACE_START_FUEL_KG.get(year)
    if code != RACE_CODE or start is None or race_laps <= 0:
        return None
    return FuelModel(start_kg=start, seconds_per_kg=FUEL_EFFECT_SECONDS_PER_KG, race_laps=race_laps)


@dataclass(frozen=True)
class Fit:
    slope: float
    intercept: float
    r2: float


def line_fit(ages: list[float], times: list[float]) -> Fit:
    x, y = np.asarray(ages, dtype=float), np.asarray(times, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    residual = float(np.sum((y - (slope * x + intercept)) ** 2))
    spread = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - residual / spread if spread > 0 else 1.0
    return Fit(slope=round(float(slope), 4), intercept=round(float(intercept), 3), r2=round(r2, 3))


def stint_fit(rows: list[dict]) -> dict | None:
    """The stint's raw and fuel-corrected wear rates from its clean laps; None with too few."""
    clean = [row for row in rows if row["status"] == "clean"]
    ages = [row["tyre_age"] for row in clean]
    if len(clean) < MIN_FIT_LAPS or len(set(ages)) < 2:
        return None
    raw = line_fit(ages, [row["time"] for row in clean])
    corrected = None
    if all(row["corrected"] is not None for row in clean):
        corrected = line_fit(ages, [row["corrected"] for row in clean])
    return {
        "laps_fitted": len(clean),
        "raw": raw.__dict__,
        "corrected": None if corrected is None else corrected.__dict__,
    }


def _rate(fit: dict) -> float:
    """The wear rate a summary reads: corrected when there is one, raw otherwise."""
    return (fit["corrected"] or fit["raw"])["slope"]


def compound_summary(stints: Iterable[dict]) -> list[dict]:
    """Median wear rate and spread per compound, over the stints that were fitted."""
    by_compound: dict[str, list[dict]] = {}
    for stint in stints:
        if stint["fit"] is not None:
            by_compound.setdefault(stint["compound"], []).append(stint["fit"])
    summary = []
    for compound, fits in sorted(by_compound.items()):
        rates = np.asarray([_rate(fit) for fit in fits])
        raw = np.asarray([fit["raw"]["slope"] for fit in fits])
        low, high = np.percentile(rates, [25, 75])
        summary.append(
            {
                "compound": compound,
                "stints": len(fits),
                "median_slope": round(float(np.median(rates)), 4),
                "median_raw_slope": round(float(np.median(raw)), 4),
                "iqr": [round(float(low), 4), round(float(high), 4)],
                "corrected": all(fit["corrected"] is not None for fit in fits),
            }
        )
    return summary
