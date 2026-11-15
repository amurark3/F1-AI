import type { LapListResponse, TrackMapResponse, WeekendSession } from "./telemetryModel";

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
