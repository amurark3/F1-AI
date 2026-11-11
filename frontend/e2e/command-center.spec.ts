import { expect, test, type Page, type Route } from "@playwright/test";

import { OVERVIEW_SEGMENTS_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, mockBackend } from "./support/mockBackend";

type Segment = keyof typeof OVERVIEW_SEGMENTS_2026;

const SEGMENTS = Object.keys(OVERVIEW_SEGMENTS_2026) as Segment[];
const CORS_HEADERS = { "access-control-allow-origin": "*" };
const SERVER_ERROR = 500;
/** Past the Command Center's 120 s SWR deduping window, so a reconnect fetches again. */
const PAST_DEDUPING = "02:01";

/** The URL pattern of one overview segment, any season. */
const segmentUrl = (segment: Segment): string => `${E2E_API_ORIGIN}/api/race-control/overview/*/${segment}`;

async function serveSegments(page: Page): Promise<void> {
  for (const segment of SEGMENTS) {
    await page.route(segmentUrl(segment), (route) =>
      route.fulfill({ json: OVERVIEW_SEGMENTS_2026[segment], headers: CORS_HEADERS }),
    );
  }
}

/** Every request for these segments answers 500 until `unroute`d (newest routes win). */
async function failSegments(page: Page, segments: Segment[]): Promise<() => Promise<void>> {
  const handler = (route: Route) => route.fulfill({ status: SERVER_ERROR, body: "", headers: CORS_HEADERS });
  for (const segment of segments) await page.route(segmentUrl(segment), handler);
  return async () => {
    for (const segment of segments) await page.unroute(segmentUrl(segment), handler);
  };
}

const tile = (page: Page, label: string) => page.getByRole("group", { name: label });
/** The visible stale mark; the screen-reader announcement words it differently. */
const STALE = { exact: true } as const;

/** The four key numbers São Paulo's segments give. */
async function expectSaoPauloNumbers(page: Page): Promise<void> {
  await expect(tile(page, "Race-day rain")).toContainText("21%");
  await expect(tile(page, "Pit lane time")).toContainText("23.5s");
  await expect(tile(page, "Title gap")).toContainText("Decided");
  await expect(tile(page, "Pole → win here")).toContainText("6/10");
}

test.beforeEach(async ({ page }) => {
  // Figures print their final value at once rather than counting up.
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockBackend(page);
  await serveSegments(page);
});

test("a failed refresh keeps the key numbers, marked stale, and a retry brings them up to date", async ({ page }) => {
  await page.clock.install();
  await page.goto("/race-control");
  await expectSaoPauloNumbers(page);
  await expect(page.getByText("Couldn't refresh", STALE)).toHaveCount(0);

  // The backend starts failing; the device reconnects, so every segment refreshes.
  const recover = await failSegments(page, SEGMENTS);
  await page.clock.fastForward(PAST_DEDUPING);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));

  // 2026-11-06: all four tiles read "Unavailable" over real data here.
  for (const label of ["Race-day rain", "Pit lane time", "Title gap", "Pole → win here"]) {
    await expect(tile(page, label).getByText("Couldn't refresh", STALE)).toBeVisible();
  }
  await expectSaoPauloNumbers(page);
  await expect(page.getByText("Unavailable", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/ unavailable$/)).toHaveCount(0);
  // The six panels keep their data too, each with its own mark.
  await expect(page.getByRole("heading", { name: "Weekend risks" })).toBeVisible();
  await expect(page.getByText("Couldn't refresh", STALE)).toHaveCount(10);

  await recover();
  await tile(page, "Title gap").getByRole("button", { name: "Retry" }).click();
  await expect(tile(page, "Title gap").getByText("Couldn't refresh", STALE)).toHaveCount(0);
  await expect(tile(page, "Title gap")).toContainText("Decided");
  // Only the shell refreshed; the other segments are still behind.
  await expect(tile(page, "Race-day rain").getByText("Couldn't refresh", STALE)).toBeVisible();
});

test("a segment that fails before it has data says so, and only there", async ({ page }) => {
  const recover = await failSegments(page, ["weather"]);
  await page.goto("/race-control");

  const rain = tile(page, "Race-day rain");
  await expect(rain).toContainText("Unavailable");
  await expect(rain).toContainText("Request failed: 500 Internal Server Error");
  await expect(page.getByText("Weather feed unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText("Risk register unavailable", { exact: true })).toBeVisible();
  // Every other segment is intact.
  await expect(tile(page, "Title gap")).toContainText("Decided");
  await expect(tile(page, "Pit lane time")).toContainText("23.5s");
  await expect(tile(page, "Pole → win here")).toContainText("6/10");
  await expect(page.getByText("Unavailable", { exact: true })).toHaveCount(1);

  await recover();
  await rain.getByRole("button", { name: "Retry" }).click();
  await expect(rain).toContainText("21%");
  await expect(page.getByText("Weather feed unavailable", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Risk register unavailable", { exact: true })).toHaveCount(0);
});
