import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RaceEvent } from "@/app/race-control/grand-prix/predictionModel";

import { fetchFromBackend } from "./backend";
import {
  currentSeason,
  getDebrief,
  getDrivers,
  getOverviewSegment,
  getPowerUnits,
  getPredictionSnapshot,
  getSchedule,
  getStandingsProgression,
  getStartingGrid,
  getTeams,
  getWeekendSessions,
  scheduleRaces,
} from "./raceControl";
import { REVALIDATE } from "./revalidate";

vi.mock("./backend", () => ({ fetchFromBackend: vi.fn() }));

const fetchMock = vi.mocked(fetchFromBackend);

describe("race control reads", () => {
  beforeEach(() => {
    fetchMock.mockResolvedValue(null);
  });

  it("asks for every document with its own path, clock and tags", async () => {
    await getSchedule(2026);
    await getTeams(2026);
    await getDrivers(2026);
    await getOverviewSegment(2026, "/weather");
    await getDebrief(2026, 5);
    await getStartingGrid(2026, 5);
    await getWeekendSessions(2026, 5);
    await getPowerUnits(2026);
    await getStandingsProgression(2026);

    expect(fetchMock.mock.calls).toEqual([
      ["/api/schedule/2026", { revalidate: REVALIDATE.SCHEDULE, tags: ["schedule", "schedule:2026"] }],
      ["/api/race-control/teams/2026", { revalidate: REVALIDATE.STANDINGS, tags: ["teams", "teams:2026"] }],
      ["/api/race-control/drivers/2026", { revalidate: REVALIDATE.ENTRY_LIST, tags: ["drivers", "drivers:2026"] }],
      [
        "/api/race-control/overview/2026/weather",
        { revalidate: REVALIDATE.OVERVIEW, tags: ["overview", "overview:2026"] },
      ],
      ["/api/race-control/debrief/2026/5", { revalidate: REVALIDATE.STANDINGS, tags: ["debrief", "debrief:2026:5"] }],
      ["/api/race-control/grid/2026/5", { revalidate: REVALIDATE.GRID, tags: ["grid", "grid:2026:5"] }],
      [
        "/api/race-control/sessions/2026/5",
        { revalidate: REVALIDATE.SESSION_RESULTS, tags: ["sessions", "sessions:2026:5"] },
      ],
      [
        "/api/race-control/power-units/2026",
        { revalidate: REVALIDATE.POWER_UNITS, tags: ["power-units", "power-units:2026"] },
      ],
      [
        "/api/race-control/standings/2026/progression",
        { revalidate: REVALIDATE.STANDINGS, tags: ["standings", "standings:2026"] },
      ],
    ]);
  });

  it("reads a prediction snapshot per phase, or the latest one", async () => {
    await getPredictionSnapshot(2026, 5, "qualifying");
    await getPredictionSnapshot(2026, 5);

    expect(fetchMock.mock.calls).toEqual([
      [
        "/api/predictions/2026/5/snapshot?phase=qualifying",
        {
          revalidate: REVALIDATE.PREDICTIONS,
          tags: ["predictions", "predictions:2026:5", "predictions:2026:5:qualifying"],
        },
      ],
      [
        "/api/predictions/2026/5/snapshot",
        {
          revalidate: REVALIDATE.PREDICTIONS,
          tags: ["predictions", "predictions:2026:5", "predictions:2026:5:latest"],
        },
      ],
    ]);
  });
});

describe("currentSeason", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("is the calendar year", () => {
    vi.useFakeTimers({ now: new Date("2027-01-02T00:00:00Z") });

    expect(currentSeason()).toBe(2027);
  });
});

describe("scheduleRaces", () => {
  it("keeps a schedule and drops an error payload or a failed fetch", () => {
    const races = [{ round: 1 }] as RaceEvent[];

    expect(scheduleRaces(races)).toBe(races);
    expect(scheduleRaces({ error: "nope" })).toEqual([]);
    expect(scheduleRaces(null)).toEqual([]);
  });
});
