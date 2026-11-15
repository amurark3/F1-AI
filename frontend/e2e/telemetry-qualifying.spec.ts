import { expect, test } from "@playwright/test";

import { SEASON_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";
import { mockTelemetry } from "./support/mockTelemetry";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await mockTelemetry(page);
  await page.route(`${E2E_API_ORIGIN}/api/schedule/*`, (route) => fulfillJson(route, SEASON_2026.schedule));
});

test("switching Q1 to Q3 redraws the speed map with that part's fastest lap", async ({ page }) => {
  await page.goto("/race-control/telemetry?tab=map&year=2026&round=19&session=Q&segment=1");

  const title = page.getByRole("heading", { level: 2 }).first();
  await expect(page.getByRole("radio", { name: "Q1", checked: true })).toBeVisible();
  await expect(title).toContainText("Q1 · fastest valid lap");
  await expect(title).toContainText("1:17.341");
  await expect(page.getByText("Lap 6 · fastest valid")).toBeVisible();

  await page.getByRole("radio", { name: "Q3" }).click();

  await expect(page).toHaveURL(/segment=3/);
  await expect(title).toContainText("Q3 · fastest valid lap");
  await expect(title).toContainText("1:16.514");
  await expect(page.getByText("Lap 19 · fastest valid")).toBeVisible();
});

test("opens on the last part the driver reached", async ({ page }) => {
  await page.goto("/race-control/telemetry?tab=map&year=2026&round=19&session=Q&a=HUL");

  await expect(page.getByRole("radio", { name: "Q2", checked: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Driver" })).toHaveValue("HUL");
});
