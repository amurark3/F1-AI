import { expect, test, type Page } from "@playwright/test";

import { OVERVIEW_SEGMENTS_2026, SEASON_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";
import { mockTelemetry } from "./support/mockTelemetry";

/** How long a held call waits before it is answered by the fixture anyway. */
const HOLD_MS = 20_000;
/** What "at once" means: the shell and skeletons must show well before any API answer. */
const AT_ONCE = { timeout: 1_000 };
const SERVER_ERROR = 500;

const segment = (name: string): string => `/overview/2026/${name}`;

interface Backend {
  /** Answers every held and later call whose URL contains `part` from the fixtures. */
  release: (part: string) => void;
  /** Answers every held and later call whose URL contains `part` with a 500. */
  fail: (part: string) => void;
  /** Answers everything still held from the fixtures. */
  releaseAll: () => void;
}

/**
 * Holds every API call (but the readiness probe) until the test lets it go, or 20 s pass.
 * Registered after the fixture routes: Playwright tries the newest route first, and
 * `fallback()` passes the call on to the fixture handler beneath.
 */
async function holdBackend(page: Page): Promise<Backend> {
  const verdicts = new Map<string, "release" | "fail">();
  let all = false;
  const waiting = new Set<() => void>();
  const verdictFor = (url: string) =>
    [...verdicts].find(([part]) => url.includes(part))?.[1] ?? (all ? "release" : undefined);
  const wake = () => [...waiting].forEach((resolve) => resolve());

  await page.route(`${E2E_API_ORIGIN}/api/**`, async (route) => {
    const url = route.request().url();
    if (url.endsWith("/api/ready") || route.request().method() === "OPTIONS") return route.fallback();
    const deadline = Date.now() + HOLD_MS;
    while (!verdictFor(url) && Date.now() < deadline) {
      await new Promise<void>((resolve) => {
        waiting.add(resolve);
        setTimeout(resolve, 250);
      });
    }
    // The page may have closed while the call was held.
    try {
      if (verdictFor(url) === "fail") {
        await route.fulfill({ status: SERVER_ERROR, body: "", headers: { "access-control-allow-origin": "*" } });
      } else {
        await route.fallback();
      }
    } catch {
      return;
    }
  });

  return {
    release: (part) => {
      verdicts.set(part, "release");
      wake();
    },
    fail: (part) => {
      verdicts.set(part, "fail");
      wake();
    },
    releaseAll: () => {
      all = true;
      wake();
    },
  };
}

test.beforeEach(async ({ page }) => {
  test.setTimeout(60_000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockBackend(page);
  await page.route(`${E2E_API_ORIGIN}/api/schedule/*`, (route) => fulfillJson(route, SEASON_2026.schedule));
  await mockTelemetry(page);
  for (const name of Object.keys(OVERVIEW_SEGMENTS_2026) as Array<keyof typeof OVERVIEW_SEGMENTS_2026>) {
    await page.route(`${E2E_API_ORIGIN}/api/race-control/overview/*/${name}`, (route) =>
      fulfillJson(route, OVERVIEW_SEGMENTS_2026[name]),
    );
  }
});

const banner = (page: Page) => page.getByRole("banner");

test("Command Center: the frame and skeletons paint, then each section fills on its own", async ({ page }) => {
  const backend = await holdBackend(page);
  await page.goto("/race-control", { waitUntil: "commit" });

  await expect(banner(page)).toBeVisible(AT_ONCE);
  await expect(page.locator('[aria-busy="true"]').first()).toBeVisible(AT_ONCE);
  await expect(page.getByRole("heading", { level: 2, name: "Projected podium" })).toHaveCount(0);

  backend.release(segment("circuit"));
  await expect(page.getByRole("heading", { level: 2, name: "History" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Projected podium" })).toHaveCount(0);

  backend.fail(segment("predictions"));
  backend.releaseAll();
  await expect(page.getByText("Prediction snapshot unavailable", { exact: true })).toBeVisible();
  await expect(page.getByRole("group", { name: "Race-day rain" })).toContainText("21%");
  await expect(page.getByRole("heading", { level: 2, name: "History" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Weekend risks" })).toBeVisible();
});

test("Grand Prix: the hub paints at once and its sections fill independently", async ({ page }) => {
  const backend = await holdBackend(page);
  await page.goto("/race-control/grand-prix?round=19", { waitUntil: "commit" });

  await expect(banner(page)).toBeVisible(AT_ONCE);
  await expect(page.locator('[aria-busy="true"], [class*="animate-pulse"]').first()).toBeVisible(AT_ONCE);

  backend.release("/api/schedule/");
  backend.release("/api/race-control/drivers/");
  await expect(page.getByRole("group", { name: "2026 race picker" })).toBeVisible();
  await expect(page.getByRole("img", { name: /layout/ })).toHaveCount(0);

  backend.fail("/api/race-control/glance/");
  backend.releaseAll();
  await expect(page.getByText("This round's history could not be loaded.")).toBeVisible();
  await expect(page.getByRole("img", { name: /layout/ })).toBeVisible();
  await expect(page.getByRole("group", { name: "2026 race picker" })).toBeVisible();
});

test("Telemetry Lab: the frame paints, the picker fills, a failed weekend leaves it intact", async ({ page }) => {
  const backend = await holdBackend(page);
  await page.goto("/race-control/telemetry?tab=map&year=2026&round=19", { waitUntil: "commit" });

  await expect(banner(page)).toBeVisible(AT_ONCE);
  await expect(page.getByRole("heading", { level: 1, name: "Telemetry Lab" })).toBeVisible(AT_ONCE);

  backend.release("/api/schedule/");
  await expect(page.getByRole("group", { name: "2026 race picker" })).toBeVisible();
  await expect(page.getByText("Loading the weekend's sessions")).toBeVisible();

  backend.fail("/api/analysis/2026/19/sessions");
  await expect(page.getByText("Could not load")).toBeVisible();
  await expect(page.getByRole("group", { name: "2026 race picker" })).toBeVisible();
});

const ROUTES = [
  "/race-control",
  "/race-control/grand-prix",
  "/race-control/telemetry",
  "/race-control/standings",
  "/race-control/constructors",
  "/race-control/drivers/max-verstappen",
  "/race-control/power-units",
  "/race-control/power-units/1",
  "/race-control/champions",
  "/race-control/champions/2025",
  "/race-control/debriefs",
  "/race-control/rewind",
];

for (const route of ROUTES) {
  test(`the header shows at once on ${route} while the API is held`, async ({ page }) => {
    await holdBackend(page);
    await page.goto(route, { waitUntil: "commit" });

    await expect(banner(page)).toBeVisible(AT_ONCE);
  });
}
