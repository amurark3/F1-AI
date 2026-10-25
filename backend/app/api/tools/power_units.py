"""Power-unit element usage per car, read from the FIA's own documents."""

from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.tools import tool
import structlog

from app.data.power_units.text import compact
from app.services.power_units import build_power_units

logger = structlog.get_logger()

_OUTCOME_WORDS = {
    "grid_drop": "drop of {places} grid places",
    "pit_lane": "pit-lane start",
    "back_of_grid": "start from the back of the grid",
}


def _matches(car: dict, wanted: str) -> bool:
    key = compact(wanted)
    numbers = {str(car["car_number"])} | {str(item["car_number"]) for item in car["drivers"]}
    if key in numbers:
        return True
    return any(
        key in compact(item["name"] or "") or key == compact(item["code"] or "") or key == compact(item["id"] or "")
        for item in car["drivers"]
    )


def _driver_label(driver: dict) -> str:
    code = f" ({driver['code']})" if driver.get("code") else ""
    return f"{driver['name']}{code}"


def _penalty_label(penalties: dict) -> str:
    parts = [f"{penalties['grid_places']} grid places"] if penalties["grid_places"] else []
    if penalties["pit_lane_starts"]:
        parts.append(f"{penalties['pit_lane_starts']} pit-lane start(s)")
    if penalties["pending"]:
        parts.append(f"{penalties['pending']} decision(s) pending")
    return ", ".join(parts) or "none"


def _allowed(value: int | None) -> str:
    return "?" if value is None else str(value)


def _freshness_line(payload: dict) -> str:
    """When the data was last checked — the model must not present stale counts as current."""
    fresh = payload.get("freshness") or {}
    checked = fresh.get("checked_at")
    if not checked:
        return "When the FIA documents were last checked is not recorded."
    note = " — this is more than a day old, so newer documents may be missing" if fresh.get("stale") else ""
    return f"FIA documents last checked {checked}{note}."


def _season_table(payload: dict) -> str:
    codes = [element["code"] for element in payload["elements"]]
    allowance = " · ".join(f"{element['code']} {_allowed(element['allowance'])}" for element in payload["elements"])
    lines = [
        f"### Power-unit usage — {payload['year']}",
        f"Allowance per car: {allowance}. Usage is counted per car (a stand-in uses the car's allocation).",
        _freshness_line(payload),
        "",
        "| Car | Driver | Team | " + " | ".join(codes) + " | PU grid penalties |",
        "| :-- | :-- | :-- | " + " | ".join("--:" for _ in codes) + " | :-- |",
    ]
    for car in payload["cars"]:
        used = {element["code"]: element for element in car["elements"]}
        cells = " | ".join(f"{used[code]['used']}/{_allowed(used[code]['allowance'])}" for code in codes)
        lines.append(
            f"| #{car['car_number']} | {_driver_label(car['driver'])} | {car['team']} | {cells} | "
            f"{_penalty_label(car['penalties'])} |",
        )
    return "\n".join(lines)


def _part_label(part: dict) -> str:
    over = " (beyond allowance)" if part["beyond_allowance"] else ""
    return f"{part['code']} #{part['number']}{over}"


def _event_line(event: dict, names: dict[int, str]) -> str:
    label = f"- R{event['round']} {names.get(event['round'], '')}"
    if event["stand_in"]:
        label += f" (driven by {_driver_label(event['driver'])})"
    details = []
    if event["new_parts"]:
        details.append("new " + ", ".join(_part_label(part) for part in event["new_parts"]))
    for decision in event["decisions"]:
        outcome = _OUTCOME_WORDS.get(decision["outcome"], decision["summary"]).format(places=decision["places"])
        details.append(f"stewards: {outcome} ({decision['title']})")
    if event["penalty_status"] == "pending":
        details.append("stewards' decision not published yet")
    grid = event["grid"]
    if grid["status"] == "official":
        start = "from the pit lane" if grid["pit_lane"] else f"P{grid['started']}"
        # A pit-lane starter can have no qualifying position on the grid sheet.
        qualified = f"qualified P{grid['qualified']}, " if grid["qualified"] else ""
        details.append(f"{qualified}started {start}")
    return f"{label}: " + "; ".join(details)


def _car_detail(car: dict, payload: dict) -> str:
    names = {item["round"]: item["name"] for item in payload["rounds"]}
    lines = [
        f"### #{car['car_number']} {_driver_label(car['driver'])} — {car['team']}, {payload['year']}",
        _freshness_line(payload),
    ]
    others = [item for item in car["drivers"] if item["id"] != car["driver"]["id"]]
    lines.extend(
        f"Also raced by {_driver_label(item)} at round(s) {', '.join(map(str, item['rounds']))} "
        "— their units count against this car."
        for item in others
    )
    lines += ["", "| Element | Used | Allowed | Over |", "| :-- | --: | --: | --: |"]
    lines.extend(
        f"| {element['code']} | {element['used']} | {_allowed(element['allowance'])} | {element['over_by']} |"
        for element in car["elements"]
    )
    lines += ["", f"PU grid penalties: {_penalty_label(car['penalties'])}.", "", "By Grand Prix:"]
    lines.extend(_event_line(event, names) for event in car["events"])
    return "\n".join(lines)


@tool
def get_power_unit_usage(driver: str | None = None, year: int | None = None) -> str:
    """Power-unit (engine) usage from FIA documents: units of ICE, TC, EXH, MGU-K,
    ES, PU-CE and PU-ANC each car has used against its season allowance, the
    Grand Prix each new unit arrived at, and the grid penalty it cost there.

    Args:
        driver: Driver name, code or car number, e.g. "Hadjar", "HAD" or "6". Omit for every car.
        year: Season, e.g. 2026. Defaults to the current season.
    """
    season = year or datetime.now(UTC).year
    logger.info("tool.power_unit_usage", driver=driver, year=season)
    try:
        payload = build_power_units(season)
    except Exception as exc:
        # The store's error text can name the database host; the model gets none of it.
        logger.exception("tool.power_unit_usage.error", error=str(exc))
        return "Power-unit usage is unavailable right now — the FIA document store could not be read."
    if not payload["available"]:
        return payload["reason"]
    if not driver:
        return _season_table(payload)
    cars = [car for car in payload["cars"] if _matches(car, driver)]
    if not cars:
        return f"No {season} car matches '{driver}'. Try a driver's surname, three-letter code or car number."
    # The driver's own car first, then any car they stood in for.
    own = [car for car in cars if _matches({**car, "drivers": [car["driver"]]}, driver)]
    return "\n\n".join(_car_detail(car, payload) for car in [*own, *(car for car in cars if car not in own)])
