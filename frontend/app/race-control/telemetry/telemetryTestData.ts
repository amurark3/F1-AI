import type {
  ComparisonResponse,
  DegradationLap,
  DegradationResponse,
  LapListResponse,
  TrackMapResponse,
  WeekendSession,
} from "./telemetryModel";

/** Small hand-made analysis answers for the Telemetry Lab tests. */

export const SESSIONS: WeekendSession[] = [
  { code: "FP1", name: "Practice 1", date_start: null, started: true },
  { code: "Q", name: "Qualifying", date_start: null, started: true },
  { code: "R", name: "Race", date_start: null, started: false },
];

const DRIVER = { number: 12, code: "ANT", name: "Kimi Antonelli", team: "Mercedes", colour: "27F4D2" };

export const LAPS: LapListResponse = {
  available: true,
  pending: false,
  drivers: [
    { ...DRIVER, number: 63, code: "RUS", name: "George Russell", best: null, laps: [] },
    {
      ...DRIVER,
      best: 94.035,
      laps: [
        { number: 13, time: null, deleted: false, is_fastest: false },
        { number: 14, time: 94.035, deleted: false, is_fastest: true },
        { number: 15, time: 95.2, deleted: true, is_fastest: false },
      ],
    },
  ],
};

export const TRACK_MAP: TrackMapResponse = {
  available: true,
  pending: false,
  modeled: ["distance"],
  warnings: ["One sample was missing."],
  driver: DRIVER,
  lap: {
    number: 14,
    time: 94.035,
    sectors: [30, 32, 32.035],
    speed_traps: { i1: 300, i2: 310, speed_trap: 341 },
    deleted: false,
    pit_out: false,
    is_fastest: true,
  },
  points: {
    distance: [0, 100, 200, 300],
    x: [0, 1000, 1500, 1000],
    y: [0, 0, 800, 1500],
    speed: [200, 320, 90, 150],
    throttle: [100, 100, 0, 60],
    brake: [0, 0, 1, 0],
    gear: [6, 8, 2, 4],
  },
  braking_zones: [{ start: 150.4, end: 190, entry_speed: 320, min_speed: 90, x: 1400, y: 600 }],
  stats: {
    top_speed: { speed: 341, distance: 100, x: 1000, y: 0 },
    full_throttle_pct: 56,
    braking_pct: 11,
    distance_m: 300,
  },
  corners: [{ number: 1, label: "1", x: 1500, y: 800, angle: 90 }],
};

const RIVAL = { number: 63, code: "RUS", name: "George Russell", team: "Mercedes", colour: "#9fb4c8" };

const LAP_A = { ...TRACK_MAP.lap!, time: 94.0 };
const LAP_B = { ...TRACK_MAP.lap!, number: 11, time: 94.27, is_fastest: false };

/** ANT is 0.27 s up at the line, having gained it all in the middle of the lap. */
export const COMPARISON: ComparisonResponse = {
  available: true,
  pending: false,
  modeled: ["distance", "delta"],
  warnings: ["One sample was missing."],
  a: { driver: DRIVER, lap: LAP_A },
  b: { driver: RIVAL, lap: LAP_B },
  gap: 0.27,
  trace: {
    distance: [0, 500, 1000, 1500, 2000],
    delta: [0, 0.02, 0.1, 0.3, 0.27],
    speed_a: [100, 300, 320, 200, 250],
    speed_b: [100, 290, 310, 200, 250],
    throttle_a: [100, 100, 100, 20, 100],
    throttle_b: [100, 100, 100, 20, 100],
    brake_a: [0, 0, 0, 100, 0],
    brake_b: [0, 0, 100, 100, 0],
    gear_a: [3, 8, 8, 4, 6],
    gear_b: [3, 8, 7, 4, 6],
  },
  mini_sectors: [
    { label: "Mini-sector 1", start: 0, end: 1000, gain: 0.1, faster: "a" },
    { label: "Mini-sector 2", start: 1000, end: 2000, gain: 0.17, faster: "a" },
  ],
  sectors: [
    { sector: 1, a: 25.3, b: 25.2, gain: -0.1 },
    { sector: 2, a: 37.3, b: 37.4, gain: 0.1 },
    { sector: 3, a: 31.4, b: 31.4, gain: 0 },
    { sector: 4, a: null, b: null, gain: null },
  ],
  map: { distance: [0, 500, 1000, 1500, 2000], x: [0, 1000, 1500, 1000, 0], y: [0, 0, 800, 1500, 800] },
  corner_markers: [{ number: 1, label: "1", x: 1500, y: 800, angle: 90 }],
};

/** Two Mercedes cars and a lone Red Bull with an unnamed compound: one stop each for the first two, none for the third. */
function lap(
  driver: string,
  number: number,
  [stint, compound, age]: [number, string | null, number | null],
  time: number | null,
): DegradationLap {
  return {
    driver,
    lap: number,
    time,
    corrected: time === null ? null : time - 0.5,
    tyre_age: age,
    compound,
    stint,
    status: "clean",
    gap_ahead: null,
  };
}

const withStatus = (entry: DegradationLap, status: string): DegradationLap => ({ ...entry, status });

const FIT = { r2: 0.9, intercept: 90 };

export const DEGRADATION: DegradationResponse = {
  available: true,
  pending: false,
  modeled: ["corrected", "fit"],
  warnings: ["Two laps had no tyre age."],
  drivers: [
    { number: 12, code: "ANT", name: "Kimi Antonelli", team: "Mercedes", colour: "#27F4D2", position: 1 },
    { number: 63, code: "RUS", name: "George Russell", team: "Mercedes", colour: "#27F4D2", position: 2 },
    { number: 1, code: "VER", name: "Max Verstappen", team: "Red Bull Racing", colour: "#3671C6", position: null },
  ],
  laps: [
    withStatus(lap("ANT", 1, [1, "MEDIUM", null], null), "lap1"),
    ...[90, 90.1, 90.2, 90.3].map((time, index) => lap("ANT", index + 2, [1, "MEDIUM", index + 1], time)),
    withStatus(lap("ANT", 6, [1, "MEDIUM", 5], 100), "pit_in"),
    ...[89.5, 89.6, 89.7, 89.8].map((time, index) => lap("ANT", index + 7, [2, "HARD", index + 1], time)),
    ...[90.2, 90.3, 90.4, 90.5].map((time, index) => lap("RUS", index + 2, [1, "MEDIUM", index + 1], time)),
    lap("RUS", 7, [2, "HARD", 1], 89.7),
    withStatus(lap("RUS", 8, [2, "HARD", 2], 95), "sc"),
    withStatus(lap("RUS", 9, [2, "HARD", 3], 95), "sc"),
    ...[91, 91.1, 91.2, 91.3].map((time, index) => lap("VER", index + 2, [1, null, index + 1], time)),
  ],
  stints: [
    {
      driver: "ANT",
      stint: 1,
      compound: "MEDIUM",
      start_lap: 1,
      end_lap: 6,
      tyre_life_start: null,
      boundary_checked: true,
      fit: { laps_fitted: 4, raw: { ...FIT, slope: 0.1 }, corrected: { ...FIT, slope: 0.13 } },
    },
    {
      driver: "ANT",
      stint: 2,
      compound: "HARD",
      start_lap: 7,
      end_lap: 10,
      tyre_life_start: 0,
      boundary_checked: true,
      fit: { laps_fitted: 4, raw: { ...FIT, slope: 0.05 }, corrected: { ...FIT, slope: 0.08 } },
    },
    {
      driver: "RUS",
      stint: 1,
      compound: "MEDIUM",
      start_lap: 1,
      end_lap: 5,
      tyre_life_start: null,
      boundary_checked: false,
      fit: { laps_fitted: 4, raw: { ...FIT, slope: 0.1 }, corrected: null },
    },
    {
      driver: "RUS",
      stint: 2,
      compound: "HARD",
      start_lap: 6,
      end_lap: 9,
      tyre_life_start: null,
      boundary_checked: true,
      fit: { laps_fitted: 3, raw: { ...FIT, slope: 0.02 }, corrected: { ...FIT, slope: 0.04 } },
    },
    {
      driver: "VER",
      stint: 1,
      compound: "UNKNOWN",
      start_lap: 1,
      end_lap: 5,
      tyre_life_start: null,
      boundary_checked: true,
      fit: null,
    },
  ],
  neutralised: [
    { kind: "sc", from_lap: 8, to_lap: 9 },
    { kind: "red", from_lap: 9, to_lap: 9 },
  ],
  status_labels: { pit_in: "In-lap" },
  assumptions: {
    fuel: { start_fuel_kg: 70, seconds_per_kg: 0.03, race_laps: 10, slope_effect: 0.03 },
    traffic_gap_seconds: 2,
    min_fit_laps: 3,
    outlier_factor: 1.07,
  },
};
