"""One lap of one car, as OpenF1's ``/laps`` publishes it.

Every timing figure here is measured: the lap and sector times, the start time,
and the three speed traps (two intermediates and the speed trap proper). OpenF1
leaves the start of a race's first lap undated and the time of an in- or
out-lap blank, so both are optional.

OpenF1 has no flag for a deleted lap. ``deleted`` is set from race control's
messages by :mod:`app.data.openf1.race_control`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from app.services.live_timing import parse_iso


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _whole(value: object) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


@dataclass(frozen=True)
class Lap:
    driver: int
    number: int
    start: datetime | None
    time: float | None
    sectors: tuple[float | None, float | None, float | None]
    # Intermediate 1, intermediate 2 and the speed trap, km/h.
    traps: tuple[int | None, int | None, int | None]
    pit_out: bool
    deleted: bool = False

    @property
    def end(self) -> datetime | None:
        if self.start is None or self.time is None:
            return None
        return self.start + timedelta(seconds=self.time)

    def marked_deleted(self) -> Lap:
        return replace(self, deleted=True)

    def to_json(self) -> dict:
        return {
            "driver": self.driver,
            "lap": self.number,
            "start": None if self.start is None else self.start.isoformat(),
            "time": self.time,
            "sectors": list(self.sectors),
            "traps": list(self.traps),
            "pit_out": self.pit_out,
            "deleted": self.deleted,
        }

    @classmethod
    def from_json(cls, row: dict) -> Lap:
        sectors = row["sectors"]
        traps = row["traps"]
        return cls(
            driver=int(row["driver"]),
            number=int(row["lap"]),
            start=parse_iso(row["start"]),
            time=row["time"],
            sectors=(sectors[0], sectors[1], sectors[2]),
            traps=(traps[0], traps[1], traps[2]),
            pit_out=bool(row["pit_out"]),
            deleted=bool(row["deleted"]),
        )


def lap_from_openf1(row: dict) -> Lap | None:
    """A ``/laps`` row as a lap; None for a row without a car or a lap number."""
    driver, number = _whole(row.get("driver_number")), _whole(row.get("lap_number"))
    if driver is None or number is None:
        return None
    return Lap(
        driver=driver,
        number=number,
        start=parse_iso(row.get("date_start")),
        time=_number(row.get("lap_duration")),
        sectors=(
            _number(row.get("duration_sector_1")),
            _number(row.get("duration_sector_2")),
            _number(row.get("duration_sector_3")),
        ),
        traps=(_whole(row.get("i1_speed")), _whole(row.get("i2_speed")), _whole(row.get("st_speed"))),
        pit_out=bool(row.get("is_pit_out_lap")),
    )


def laps_from_openf1(rows: list[dict]) -> tuple[Lap, ...]:
    """Every usable lap, by car then lap number."""
    laps = [lap for row in rows if (lap := lap_from_openf1(row)) is not None]
    return tuple(sorted(laps, key=lambda lap: (lap.driver, lap.number)))
