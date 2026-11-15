import { expect, test } from "@playwright/test";

import { SEASON_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.route(`${E2E_API_ORIGIN}/api/schedule/*`, (route) => fulfillJson(route, SEASON_2026.schedule));
  await page.route(`${E2E_API_ORIGIN}/api/champions/*`, (route) => fulfillJson(route, SEASON_2026.winners));
});

test("?tab=predictions&view=review scores the call: DNF rows read DNF and a reason, with no place delta and no results table", async ({
  page,
}) => {
  await page.goto("/race-control/grand-prix?round=19&tab=predictions&view=review");

  await expect(page.getByRole("tab", { name: "Predictions", selected: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Review", selected: true })).toBeVisible();
  await expect(page.getByText("Scored against the provisional result")).toBeVisible();

  const lindblad = page.getByRole("listitem").filter({ hasText: "Collision · 58 laps" }).first();
  await expect(lindblad).toContainText("DNF");
  await expect(lindblad).toContainText("no place delta");
  await expect(lindblad).not.toContainText(/[+\u2212]\d/);

  const hamilton = page.getByRole("listitem").filter({ hasText: "Hamilton" }).first();
  await expect(hamilton).toContainText("+2");

  await expect(page.getByRole("table")).toHaveCount(0);
  await expect(page.getByText("Predicted vs actual")).toHaveCount(0);
  await expect(page.getByRole("columnheader", { name: "Outcome" })).toHaveCount(0);
});

test("?tab=predictions&view=order lists 22 cars with an agreement band and vs grid, and none of the removed columns", async ({
  page,
}) => {
  await page.goto("/race-control/grand-prix?round=19&tab=predictions&view=order");

  await expect(page.getByText("Predicted order \u00b7 22 cars")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Agreement", exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "vs grid" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Pts" })).toHaveCount(0);
  await expect(page.getByRole("columnheader", { name: "Win est." })).toHaveCount(0);
  await expect(page.getByRole("row", { name: /LAW/ })).toContainText("from pit lane");
});
