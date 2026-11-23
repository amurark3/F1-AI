/** Hand-built payloads for the rewind's tests: three cars, a few laps, every special state a test needs. */

import type {
  RaceRewind,
  RewindChange,
  RewindDriver,
  RewindFinal,
  RewindLap,
} from "@/app/race-control/rewind/rewindTypes";

const TEAMS: Record<string, string> = { AAA: "Red Bull Racing", BBB: "Ferrari", CCC: "McLaren", DDD: "Mercedes" };
const NAMES: Record<string, string> = {
  AAA: "Alfa Alpha",
  BBB: "Bravo Bell",
  CCC: "Cole Carter",
  DDD: "Dale Dunn",
};

export function driver(code: string, over: Partial<RewindDriver> = {}): RewindDriver {
  return {
    car: 1,
    driver_code: code,
    driver_name: NAMES[code] ?? code,
    team: TEAMS[code] ?? "",
    status: "finished",
    laps: 3,
    ...over,
  };
}

export function change(code: string, from: number, to: number, over: Partial<RewindChange> = {}): RewindChange {
  return { driver_code: code, from, to, kind: "change", rival: null, stop_lap: null, ...over };
}

export function lap(n: number, order: string[], over: Partial<RewindLap> = {}): RewindLap {
  return { lap: n, order, track: null, changes: [], ...over };
}

export function finalOf(over: Partial<RewindFinal> = {}): RewindFinal {
  return {
    source: "fia-final-classification",
    provisional: false,
    document: 86,
    url: "https://www.fia.com/final.pdf",
    rows: [
      { driver_code: "AAA", position: 1, status: "finished", laps: 3, road_position: 1, penalties: [] },
      { driver_code: "BBB", position: 2, status: "finished", laps: 3, road_position: 2, penalties: [] },
      { driver_code: "CCC", position: 3, status: "finished", laps: 3, road_position: 3, penalties: [] },
    ],
    ...over,
  };
}

/** Three cars over three laps; AAA leads every lap and nothing changes unless a test says so. */
export function race(over: Partial<RaceRewind> = {}): RaceRewind {
  return {
    year: 2026,
    round: 1,
    available: true,
    reason: null,
    total_laps: 3,
    drivers: [driver("AAA"), driver("BBB"), driver("CCC")],
    grid: { order: ["AAA", "BBB", "CCC"], pit_lane: [], source: "fia_starting_grid", document: 67 },
    neutralisations: [],
    stops: [],
    laps: [lap(1, ["AAA", "BBB", "CCC"]), lap(2, ["AAA", "BBB", "CCC"]), lap(3, ["AAA", "BBB", "CCC"])],
    final: finalOf(),
    ...over,
  };
}
