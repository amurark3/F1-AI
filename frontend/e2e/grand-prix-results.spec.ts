import { expect, test } from "@playwright/test";

import { SEASON_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.route(`${E2E_API_ORIGIN}/api/schedule/*`, (route) => fulfillJson(route, SEASON_2026.schedule));
  await page.route(`${E2E_API_ORIGIN}/api/champions/*`, (route) => fulfillJson(route, SEASON_2026.winners));
});

test("?tab=results shows the classification, and a retirement reads DNF, never a place", async ({ page }) => {
  await page.goto("/race-control/grand-prix?round=19&tab=results");

  await expect(page.getByRole("tab", { name: "Results", selected: true })).toBeVisible();
  const table = page.getByRole("table");
  await expect(table.getByRole("row", { name: /Verstappen/ })).toContainText("2:20:28.772");
  await expect(table.getByText("Did not finish")).toBeVisible();

  const lindblad = table.getByRole("row", { name: /LIN/ });
  await expect(lindblad.getByRole("cell").first()).toHaveText("DNF");
  await expect(lindblad).toContainText("Collision · 58 laps");
  await expect(page.getByRole("tab", { name: /^(Weekend|Sessions|Grid|Results|Stints|Predictions)$/ })).toHaveText([
    "Weekend",
    "Sessions",
    "Grid",
    "Results",
    "Stints",
    "Predictions",
  ]);
});

test("every round opens on Weekend, a finished one too, and changing round starts over there", async ({ page }) => {
  await page.goto("/race-control/grand-prix?round=19");

  await expect(page.getByRole("tab", { name: "Weekend", selected: true })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: /Mexico City Grand/ })).toBeVisible();

  await page.getByRole("tab", { name: "Results" }).click();
  await expect(page.getByRole("heading", { name: /Verstappen wins/ })).toBeVisible();
  await page.getByRole("button", { name: "Previous round" }).click();
  await expect(page).toHaveURL(/round=18$/);
  await expect(page.getByRole("tab", { name: "Weekend", selected: true })).toBeVisible();
});
