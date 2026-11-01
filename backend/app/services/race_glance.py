"""The Grand Prix Hub's "at a glance" card for one round.

Two facts, each from its own source of record:

* the previous race at this circuit — winner and pole — from f1db;
* this round's power-unit penalty decisions from the FIA documents the power
  unit tracker reads. Only decisions are listed; a new part with no decision
  yet is not a penalty, and saying so would be inventing one.
"""

from __future__ import annotations

from app.data.profiles.circuit_history import previous_edition
from app.services.profiles import load_power_units


def _decisions(cars: list[dict], round_num: int) -> list[dict]:
    decisions = [
        {
            **decision,
            "car_number": car["car_number"],
            "seat_id": car["seat_id"],
            "team_id": car["team_id"],
            "team": car["team"],
            # The round's own occupant, so a stand-in is named.
            "driver": event["driver"] or car["driver"],
        }
        for car in cars
        for event in car["events"]
        if event["round"] == round_num
        for decision in event["decisions"]
    ]
    return sorted(decisions, key=lambda item: item["car_number"])


def build_race_glance(year: int, round_num: int) -> dict:
    payload, reason = load_power_units(year)
    return {
        "year": year,
        "round": round_num,
        "previous": previous_edition(year, round_num),
        "power_units": {
            "available": payload is not None,
            "reason": reason,
            "decisions": _decisions(payload["cars"], round_num) if payload else [],
        },
    }
