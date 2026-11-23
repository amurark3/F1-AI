"""The debrief's team radio: each OpenF1 clip set with the race moment it came within a lap of.

A moment is the driver's own stop, penalty, incident or retirement, or a race-wide
one (start, Safety Car, VSC, red flag, chequered flag). A clip within a lap of
several takes the nearest in time; one inside a red-flag suspension takes the red
flag. Clips that match nothing are listed apart, so nothing OpenF1 published is hidden.
The audio is OpenF1's ``recording_url`` on F1's archive; there is no transcript.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import TYPE_CHECKING

from app.data.openf1.client import get_json, new_client
from app.data.openf1.race_control import RED_FLAG, neutralised_windows
from app.data.openf1.session_laps import SessionLaps, load_session_laps
from app.data.openf1.sessions import canonical_entry
from app.services.debrief_penalties import _MESSAGE
from app.services.live_timing import parse_iso
from app.services.pit_stop_rule import is_stop, lane_seconds, stop_lane_limit
from app.services.race_results import build_session_result

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.data.openf1.sessions import EntryDriver

RECORDING_ORIGIN = "https://livetiming.formula1.com/"
RADIO_WINDOW_LAPS = 1
NO_LAPS = "OpenF1 hasn't published this race's laps yet."
NO_RADIO = "OpenF1 has no team radio for this race."

_RACE_WIDE = (
    ("SAFETY CAR DEPLOYED", "safety_car"),
    ("SAFETY CAR IN THIS LAP", "safety_car_in"),
    ("VSC DEPLOYED", "vsc"),
    ("VIRTUAL SAFETY CAR DEPLOYED", "vsc"),
    ("VSC ENDING", "vsc_ending"),
    ("VIRTUAL SAFETY CAR ENDING", "vsc_ending"),
)
_INCIDENT = re.compile(
    r"^(?:TURN (?P<turn>\d+) )?INCIDENT INVOLVING CARS? (?P<cars>.+?) NOTED(?: - (?P<reason>.+?))?"
    r"(?: \((?P<at>\d{1,2}:\d{2}:\d{2})\))?$"
)
_NAMED_CAR = re.compile(r"(\d+) \(([A-Z]{3})\)")
_OFFSET = re.compile(r"([+-]?)(\d{1,2}):(\d{2})(?::\d{2})?")

Starts = dict[int, list[tuple[datetime, int]]]


@dataclass(frozen=True)
class RadioInputs:
    laps: SessionLaps
    radio: list[dict]
    pit: list[dict]
    messages: list[dict]
    gmt_offset: str | None
    # Car number -> laps completed, from the classification, for the cars it lists as DNF.
    dnf_cars: Mapping[int, int]


@dataclass(frozen=True)
class Moment:
    kind: str
    lap: int
    at: datetime
    car: int | None = None
    detail: str | None = None
    until: datetime | None = None


@dataclass(frozen=True)
class Clip:
    car: int
    lap: int
    at: datetime
    url: str


def _unavailable(reason: str) -> dict:
    return {
        "available": False,
        "reason": reason,
        "total": 0,
        "utc_offset_minutes": None,
        "moments": [],
        "unattached": [],
    }


def offset_minutes(gmt_offset: str | None) -> int | None:
    found = _OFFSET.fullmatch(gmt_offset or "")
    if not found:
        return None
    minutes = int(found[2]) * 60 + int(found[3])
    return -minutes if found[1] == "-" else minutes


def _starts(laps: SessionLaps) -> Starts:
    starts: Starts = {}
    for lap in laps.laps:
        if lap.start is not None:
            starts.setdefault(lap.driver, []).append((lap.start, lap.number))
    return starts


def _lap_at(starts: Starts, car: int, at: datetime) -> int:
    return max((number for start, number in starts.get(car, ()) if start <= at), default=0)


def _clips(inputs: RadioInputs, starts: Starts) -> list[Clip]:
    kept = []
    for row in inputs.radio:
        url, at, car = row.get("recording_url"), parse_iso(row.get("date")), row.get("driver_number")
        if isinstance(url, str) and url.startswith(RECORDING_ORIGIN) and at and car in inputs.laps.drivers:
            kept.append(Clip(car, _lap_at(starts, car, at), at, url))
    return kept


def _red_flag_moments(messages: list[dict]) -> list[Moment]:
    """One moment per red-flag window, from the first message dated at its start that carries a lap."""
    moments = []
    for window in (w for w in neutralised_windows(messages) if w.kind == RED_FLAG):
        lap = next(
            (
                r["lap_number"]
                for r in messages
                if parse_iso(r.get("date")) == window.start and r.get("lap_number") is not None
            ),
            None,
        )
        if lap is not None:
            moments.append(Moment("red_flag", lap, window.start, until=window.end))
    return moments


def _flag_moments(messages: list[dict]) -> list[Moment]:
    moments = []
    for row in messages:
        at, lap, text = parse_iso(row.get("date")), row.get("lap_number"), str(row.get("message") or "").upper()
        kind = next((kind for prefix, kind in _RACE_WIDE if text.startswith(prefix)), None)
        if str(row.get("flag") or "").upper() == "CHEQUERED":
            kind = "chequered"
        if kind and at and lap is not None:
            moments.append(Moment(kind, lap, at))
    return [*moments, *_red_flag_moments(messages)]


def _penalty_moments(messages: list[dict]) -> list[Moment]:
    moments = []
    for row in messages:
        found = _MESSAGE.match(str(row.get("message") or ""))
        at = parse_iso(row.get("date"))
        if found and not found["served"] and at and row.get("lap_number") is not None:
            moments.append(Moment("penalty", row["lap_number"], at, int(found["car"]), found["penalty"].capitalize()))
    return moments


def _incident_at(row_at: datetime, clock: str | None, offset: int | None) -> datetime:
    """The incident's own time: the message's circuit-local ``(HH:MM:SS)``, on the message's local date."""
    if clock is None or offset is None:
        return row_at
    hour, minute, second = (int(part) for part in clock.split(":"))
    shift = timedelta(minutes=offset)
    return (row_at + shift).replace(hour=hour, minute=minute, second=second, microsecond=0) - shift


def _incident_detail(found: re.Match[str], car: int, cars: list[tuple[int, str]]) -> str:
    others = [code for number, code in cars if number != car]
    parts = [
        f"Turn {found['turn']}" if found["turn"] else None,
        f"with {', '.join(others)}" if others else None,
        found["reason"].capitalize() if found["reason"] else None,
    ]
    return " · ".join(part for part in parts if part)


def _incident_moments(messages: list[dict], starts: Starts, offset: int | None) -> list[Moment]:
    moments = []
    for row in messages:
        found = _INCIDENT.match(str(row.get("message") or "").upper())
        row_at = parse_iso(row.get("date"))
        if not found or row_at is None or row.get("lap_number") is None:
            continue
        at = _incident_at(row_at, found["at"], offset)
        cars = [(int(number), code) for number, code in _NAMED_CAR.findall(found["cars"])]
        moments.extend(
            Moment("incident", _lap_at(starts, car, at), at, car, _incident_detail(found, car, cars)) for car, _ in cars
        )
    return moments


def _stop_moments(pit: list[dict]) -> list[Moment]:
    limit = stop_lane_limit(pit)
    moments = []
    for row in pit:
        at = parse_iso(row.get("date"))
        if at is None or not is_stop(row, limit):
            continue
        detail = f"{row['stop_duration']:.1f} s" if row.get("stop_duration") else f"pit lane {lane_seconds(row):.1f} s"
        moments.append(Moment("stop", row["lap_number"], at, row["driver_number"], detail))
    return moments


def _retirement_moments(inputs: RadioInputs) -> list[Moment]:
    """A DNF reads the lap the classification says it completed; the moment sits at that lap's start."""
    moments = []
    for car, completed in sorted(inputs.dnf_cars.items()):
        lap = next((lap for lap in inputs.laps.laps_of(car) if lap.number == completed), None)
        if lap is not None and lap.start is not None:
            moments.append(Moment("retirement", completed, lap.start, car))
    return moments


def build_moments(inputs: RadioInputs, starts: Starts, offset: int | None) -> list[Moment]:
    start = inputs.laps.session.date_start
    found = [
        *([Moment("start", 1, start)] if start else []),
        *_flag_moments(inputs.messages),
        *_penalty_moments(inputs.messages),
        *_incident_moments(inputs.messages, starts, offset),
        *_stop_moments(inputs.pit),
        *_retirement_moments(inputs),
    ]
    return sorted((m for m in found if m.car is None or m.car in inputs.laps.drivers), key=lambda m: m.at)


def _nearest(clip: Clip, moments: list[Moment]) -> int | None:
    suspended = [
        i
        for i, m in enumerate(moments)
        if m.kind == "red_flag" and m.at <= clip.at and (m.until is None or clip.at <= m.until)
    ]
    near = suspended or [
        i for i, m in enumerate(moments) if abs(m.lap - clip.lap) <= RADIO_WINDOW_LAPS and m.car in (None, clip.car)
    ]
    return min(near, key=lambda i: abs((moments[i].at - clip.at).total_seconds()), default=None)


def _driver(entries: dict[int, EntryDriver], car: int | None) -> dict | None:
    if car is None:
        return None
    entry = entries[car]
    return {"driver_code": entry.code, "driver_name": entry.name, "team": entry.team}


def _clip_json(entries: dict[int, EntryDriver], clip: Clip) -> dict:
    entry = entries[clip.car]
    return {
        "driver_code": entry.code,
        "driver_name": entry.name,
        "team": entry.team,
        "colour": entry.colour,
        "lap": clip.lap,
        "at": clip.at.isoformat(),
        "url": clip.url,
    }


def _ordered(clips: list[Clip]) -> list[Clip]:
    return sorted(clips, key=lambda clip: (clip.at, clip.url))


def radio_payload(inputs: RadioInputs) -> dict:
    entries = {number: canonical_entry(entry, inputs.laps.year) for number, entry in inputs.laps.drivers.items()}
    starts = _starts(inputs.laps)
    offset = offset_minutes(inputs.gmt_offset)
    clips = _clips(inputs, starts)
    moments = build_moments(inputs, starts, offset)
    taken: dict[int, list[Clip]] = {}
    loose: list[Clip] = []
    for clip in clips:
        index = _nearest(clip, moments)
        if index is None:
            loose.append(clip)
        else:
            taken[index] = [*taken.get(index, []), clip]
    return {
        "available": True,
        "reason": None,
        "total": len(clips),
        "utc_offset_minutes": offset,
        "moments": [
            {
                "kind": moments[i].kind,
                "lap": moments[i].lap,
                "at": moments[i].at.isoformat(),
                "driver": _driver(entries, moments[i].car),
                "detail": moments[i].detail,
                "clips": [_clip_json(entries, c) for c in _ordered(taken[i])],
            }
            for i in sorted(taken)
        ],
        "unattached": [_clip_json(entries, c) for c in _ordered(loose)],
    }


def _dnf_cars(year: int, round_num: int, drivers: dict[int, EntryDriver]) -> dict[int, int]:
    race = build_session_result(year, round_num, "race")
    dnf = {
        row["driver_code"]: row["laps"]
        for row in (race["classification"] if race else [])
        if row["status"] == "DNF" and row.get("laps") is not None
    }
    codes = {n: canonical_entry(entry, year).code for n, entry in drivers.items()}
    return {n: dnf[code] for n, code in codes.items() if code in dnf}


def build_debrief_radio(year: int, round_num: int) -> dict:
    laps = load_session_laps(year, round_num, "R")
    if laps is None or not laps.laps:
        return _unavailable(NO_LAPS)
    params = {"session_key": laps.session.session_key}
    with new_client() as client:
        radio = get_json(client, "team_radio", params)
        if not radio:
            return _unavailable(NO_RADIO)
        pit = get_json(client, "pit", params)
        messages = get_json(client, "race_control", params)
        sessions = get_json(client, "sessions", params)
    gmt_offset = sessions[0].get("gmt_offset") if sessions else None
    inputs = RadioInputs(laps, radio, pit, messages, gmt_offset, _dnf_cars(year, round_num, laps.drivers))
    return radio_payload(inputs)
