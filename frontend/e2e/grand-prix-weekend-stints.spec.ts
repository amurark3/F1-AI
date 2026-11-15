import { expect, test } from "@playwright/test";

import { SEASON_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.route(`${E2E_API_ORIGIN}/api/schedule/*`, (route) => fulfillJson(route, SEASON_2026.schedule));
  await page.route(`${E2E_API_ORIGIN}/api/champions/*`, (route) => fulfillJson(route, SEASON_2026.winners));
});

test("?tab=weekend on a finished round shows the winner and a link to Results, not a countdown", async ({ page }) => {
  await page.goto("/race-control/grand-prix?round=19&tab=weekend");

  await expect(page.getByRole("tab", { name: "Weekend", selected: true })).toBeVisible();
  await expect(page.getByText("Winner", { exact: true })).toBeVisible();
  await expect(page.getByText("Max Verstappen").first()).toBeVisible();
  await expect(page.getByRole("timer")).toHaveCount(0);
  await expect(page.getByRole("img", { name: /layout/ })).toBeVisible();

  await page.getByRole("link", { name: /Final classification/ }).click();
  await expect(page).toHaveURL(/tab=results/);
});

test("?tab=stints reads a retirement as DNF with its reason, and labels the red flag", async ({ page }) => {
  await page.goto("/race-control/grand-prix?round=19&tab=stints");

  const lindblad = page.getByTitle(/^LIN: Retired: Collision/);
  await expect(lindblad).toContainText("DNF");
  await expect(lindblad).not.toContainText("NC");
  await expect(page.getByText("RED FLAG · L45")).toBeVisible();
});

test("at 390 px the red flag label and the SC band label do not overlap", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/race-control/grand-prix?round=19&tab=stints");

  const red = await page.getByText("RED FLAG · L45").boundingBox();
  const band = await page.getByText("SC", { exact: true }).first().boundingBox();
  expect(red).not.toBeNull();
  expect(band).not.toBeNull();
  const apart = red!.y + red!.height <= band!.y || band!.y + band!.height <= red!.y;
  const clear = red!.x + red!.width <= band!.x || band!.x + band!.width <= red!.x;
  expect(apart || clear).toBe(true);
});
