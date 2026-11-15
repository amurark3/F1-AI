import qualifyingLaps from "../../test/fixtures/qualifying-laps-mexico-2026.json";

import { E2E_API_ORIGIN, fulfillJson } from "./mockBackend";

import type { Page } from "@playwright/test";

const SESSIONS = {
  available: true,
  pending: false,
  sessions: [{ code: "Q", name: "Qualifying", date_start: qualifyingLaps.session.date_start, started: true }],
};

/** One lap's worth of speed map: 200 points round an oval, enough for the map to draw. */
function pointsFor(): Record<string, number[]> {
  const index = Array.from({ length: 200 }, (_, step) => step);
  const angle = (step: number) => (step / 200) * 2 * Math.PI;
  return {
    distance: index.map((step) => step * 20),
    x: index.map((step) => Math.cos(angle(step)) * 1000),
    y: index.map((step) => Math.sin(angle(step)) * 600),
    speed: index.map((step) => 120 + (step % 100) * 2),
    throttle: index.map(() => 100),
    brake: index.map(() => 0),
    gear: index.map(() => 6),
  };
}

/** The Telemetry Lab's qualifying answers: Mexico City 2026's real lap list, and the segment's fastest valid lap as the map. */
export async function mockTelemetry(page: Page): Promise<void> {
  const base = `${E2E_API_ORIGIN}/api/analysis/2026/19`;
  await page.route(`${base}/sessions`, (route) => fulfillJson(route, SESSIONS));
  await page.route(`${base}/laps?*`, (route) => fulfillJson(route, qualifyingLaps));
  await page.route(`${base}/track-map?*`, (route) => {
    const query = new URL(route.request().url()).searchParams;
    const driver =
      qualifyingLaps.drivers.find((entry) => entry.code === query.get("driver")) ?? qualifyingLaps.drivers[0];
    const segment = Number(query.get("segment") ?? 3);
    const time = driver.segment_bests[segment - 1];
    const lap = driver.laps.find((entry) => entry.time === time);
    return fulfillJson(route, {
      available: true,
      pending: false,
      driver: { number: driver.number, code: driver.code, name: driver.name, team: driver.team, colour: driver.colour },
      lap: {
        number: lap?.number ?? 0,
        time,
        sectors: [null, null, null],
        speed_traps: { i1: null, i2: null, speed_trap: null },
        deleted: false,
        pit_out: false,
        is_fastest: true,
      },
      points: pointsFor(),
    });
  });
}
