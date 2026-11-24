import {
  DIRECTORY_2026,
  GRIDS_2026,
  MEXICO_CITY_2026,
  PREDICTION_REVIEW_R19,
  PROFILE_PAGES_2026,
  RACE_RESULTS_2026,
  READY,
  TEAMS_2026,
  WEEKEND_FEED_2026_R19,
  WEEKEND_SESSIONS_2026,
} from "../../test/fixtures";

import type { Page, Route } from "@playwright/test";

/**
 * The backend origin the e2e build is pointed at.
 *
 * Nothing listens here. Server renders fail fast and the pages render unseeded,
 * and every browser request is answered by `mockBackend` from the captured
 * fixtures, so a run sees the same data whether or not a backend is running
 * on this machine, and CI needs no Python.
 */
export const E2E_API_ORIGIN = "http://127.0.0.1:8799";

/** The responses cross origins (app port to API port), so CORS still applies. */
const CORS_HEADERS = { "access-control-allow-origin": "*" };

const NOT_FOUND = 404;

export function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, json: body, headers: CORS_HEADERS });
}

/**
 * Answers the app's backend calls from the fixtures.
 *
 * `/api/ready` answers ready at once, so the restart lights never show, unless
 * the test holds it elsewhere with `readiness` (a body, as `READY` is). A
 * path no test declared gets FastAPI's 404 instead of hanging; Playwright
 * tries routes newest first, so the catch-all is registered first.
 */
export async function mockBackend(page: Page, { readiness = READY }: { readiness?: unknown } = {}): Promise<void> {
  await page.route(`${E2E_API_ORIGIN}/**`, (route) => fulfillJson(route, { detail: "Not Found" }, NOT_FOUND));
  await page.route(`${E2E_API_ORIGIN}/api/ready`, (route) => fulfillJson(route, readiness));
  // Pages ask for the calendar year's season; the fixture is 2026's table.
  await page.route(`${E2E_API_ORIGIN}/api/weekend/*/*/feed`, (route) => fulfillJson(route, WEEKEND_FEED_2026_R19));
  await page.route(`${E2E_API_ORIGIN}/api/race-control/teams/*`, (route) => fulfillJson(route, TEAMS_2026));
  await page.route(`${E2E_API_ORIGIN}/api/profiles/*/directory`, (route) => fulfillJson(route, DIRECTORY_2026));
  // The Teams index (its own path, so it does not shadow a team's `/teams/{id}`).
  await page.route(`${E2E_API_ORIGIN}/api/profiles/*/teams`, (route) =>
    fulfillJson(route, PROFILE_PAGES_2026.teams_index),
  );
  // A team's season by f1db id; any other id is a team the season does not have.
  await page.route(`${E2E_API_ORIGIN}/api/profiles/*/teams/*`, (route) => {
    const id = route.request().url().split("/").pop() ?? "";
    const known: Record<string, unknown> = {
      mercedes: PROFILE_PAGES_2026.mercedes,
      "red-bull": PROFILE_PAGES_2026.red_bull,
    };
    return fulfillJson(route, known[id] ?? { year: 2026, status: "not_found", team: null });
  });
  // A driver's season by f1db id; any other id is a driver the season does not have.
  await page.route(`${E2E_API_ORIGIN}/api/profiles/*/drivers/*`, (route) => {
    const id = route.request().url().split("/").pop() ?? "";
    const known: Record<string, unknown> = {
      "max-verstappen": PROFILE_PAGES_2026.verstappen,
      "lewis-hamilton": PROFILE_PAGES_2026.hamilton,
      "liam-lawson": PROFILE_PAGES_2026.lawson,
      "ryo-hirakawa": PROFILE_PAGES_2026.hirakawa,
    };
    return fulfillJson(route, known[id] ?? { year: 2026, status: "not_found", driver: null });
  });
  // The Results tab: Mexico City (no sprint) and the Chinese Grand Prix (a sprint weekend).
  await page.route(`${E2E_API_ORIGIN}/api/race-control/results/2026/*`, (route) => {
    const round = route.request().url().split("/").pop();
    const body = round === "2" ? RACE_RESULTS_2026.sprintWeekend : RACE_RESULTS_2026.mexicoCity;
    return fulfillJson(route, body);
  });
  // The Weekend tab's circuit and the Stints tab's chart: Mexico City.
  await page.route(`${E2E_API_ORIGIN}/api/race-control/circuit/2026/*`, (route) =>
    fulfillJson(route, MEXICO_CITY_2026.circuit),
  );
  await page.route(`${E2E_API_ORIGIN}/api/race-control/stints/2026/*`, (route) =>
    fulfillJson(route, MEXICO_CITY_2026.strategy),
  );
  await page.route(`${E2E_API_ORIGIN}/api/race-control/glance/2026/*`, (route) =>
    fulfillJson(route, MEXICO_CITY_2026.glance),
  );
  // The Sessions and Grid tabs: Mexico City's qualifying (with its disqualification) and official grid.
  await page.route(`${E2E_API_ORIGIN}/api/race-control/sessions/2026/*`, (route) =>
    fulfillJson(route, WEEKEND_SESSIONS_2026.mexicoCity),
  );
  await page.route(`${E2E_API_ORIGIN}/api/race-control/grid/2026/*`, (route) =>
    fulfillJson(route, GRIDS_2026.mexicoCityOfficial),
  );
  // The Predictions tab: Mexico City's stored after-qualifying call, with its review.
  await page.route(`${E2E_API_ORIGIN}/api/predictions/2026/*/snapshot*`, (route) =>
    fulfillJson(route, PREDICTION_REVIEW_R19),
  );
}
