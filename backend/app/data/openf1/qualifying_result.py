"""A qualifying session's classification as OpenF1 ``/session_result`` publishes it.

``duration`` is each car's best time per segment ([Q1, Q2, Q3], null where none),
which is what the segment windows are checked against. OpenF1 gives a car
disqualified from qualifying no position and leaves ``dsq`` false (Lawson, Mexico
City 2026), so a disqualification is read from f1db, not from here.
"""

from __future__ import annotations

from dataclasses import dataclass

SEGMENTS = 3


@dataclass(frozen=True)
class ResultRow:
    driver: int
    position: int | None
    durations: tuple[float | None, float | None, float | None]

    def to_json(self) -> dict:
        return {"driver": self.driver, "position": self.position, "durations": list(self.durations)}

    @classmethod
    def from_json(cls, row: dict) -> ResultRow:
        times = row["durations"]
        return cls(driver=int(row["driver"]), position=row["position"], durations=(times[0], times[1], times[2]))


def _time(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def result_rows(rows: list[dict]) -> tuple[ResultRow, ...]:
    """Every car with a number, in published order."""
    found = []
    for row in rows:
        driver, position, times = row.get("driver_number"), row.get("position"), row.get("duration")
        if not isinstance(driver, int):
            continue
        padded = [_time(time) for time in (times if isinstance(times, list) else [])][:SEGMENTS]
        padded += [None] * (SEGMENTS - len(padded))
        found.append(
            ResultRow(driver, position if isinstance(position, int) else None, (padded[0], padded[1], padded[2]))
        )
    return tuple(found)
