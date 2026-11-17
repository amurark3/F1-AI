import { expect, test } from "@playwright/test";

import { OVERVIEW_SEGMENTS_2026, STANDINGS_PROGRESSION_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, mockBackend } from "./support/mockBackend";

const CORS_HEADERS = { "access-control-allow-origin": "*" };

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.route(`${E2E_API_ORIGIN}/api/race-control/overview/*/shell`, (route) =>
    route.fulfill({ json: OVERVIEW_SEGMENTS_2026.shell, headers: CORS_HEADERS }),
  );
  await page.route(`${E2E_API_ORIGIN}/api/race-control/standings/*/progression`, (route) =>
    route.fulfill({ json: STANDINGS_PROGRESSION_2026, headers: CORS_HEADERS }),
  );
});

test("the champion, the title race and both tables", async ({ page }) => {
  await page.goto("/race-control/teams");

  await expect(page.getByRole("heading", { level: 1, name: "Kimi Antonelli" })).toBeVisible();
  await expect(page.getByText("2026 World Champion", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Antonelli led from Suzuka and never gave it back" })).toBeVisible();
  await expect(page.getByText("Clinched · R19 Mexico City")).toBeVisible();
  await expect(page.getByRole("list", { name: "Drivers' championship points" }).getByRole("listitem")).toHaveCount(24);

  const badge = page.getByRole("button", { name: /after round 19 · confirmed · as of/i });
  await expect(badge).toBeVisible();
  await badge.hover();
  await expect(page.getByRole("tooltip")).toContainText("Base: f1db v2026.19.0, through round 19");
  // A backend that answers ready at once never raises the warm-up screen.
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("the switch moves the hero to the constructors", async ({ page }) => {
  await page.goto("/race-control/teams");
  await expect(page.getByRole("heading", { level: 1, name: "Kimi Antonelli" })).toBeVisible();

  await page.getByRole("radio", { name: "Drivers" }).focus();
  await page.keyboard.press("ArrowRight");

  await expect(page.getByRole("heading", { level: 1, name: "Mercedes" })).toBeVisible();
  await expect(page.getByText("126 points clear of Ferrari after round 19.")).toBeVisible();
});

test("fits a phone without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/race-control/teams");
  await expect(page.getByRole("heading", { level: 1, name: "Kimi Antonelli" })).toBeVisible();

  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(390);
});
