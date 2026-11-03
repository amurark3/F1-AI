import { DIRECTORY_2026, READY, TEAMS_2026 } from "../../test/fixtures";

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

function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, json: body, headers: CORS_HEADERS });
}

/**
 * Answers the app's backend calls from the fixtures.
 *
 * `/api/ready` answers ready at once, so the cold-start gate never shows. A
 * path no test declared gets FastAPI's 404 instead of hanging; Playwright
 * tries routes newest first, so the catch-all is registered first.
 */
export async function mockBackend(page: Page): Promise<void> {
  await page.route(`${E2E_API_ORIGIN}/**`, (route) => fulfillJson(route, { detail: "Not Found" }, NOT_FOUND));
  await page.route(`${E2E_API_ORIGIN}/api/ready`, (route) => fulfillJson(route, READY));
  // Pages ask for the calendar year's season; the fixture is 2026's table.
  await page.route(`${E2E_API_ORIGIN}/api/race-control/teams/*`, (route) => fulfillJson(route, TEAMS_2026));
  await page.route(`${E2E_API_ORIGIN}/api/profiles/*/directory`, (route) => fulfillJson(route, DIRECTORY_2026));
}
