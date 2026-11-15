import { expect, test } from "@playwright/test";

import { SEASON_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.route(`${E2E_API_ORIGIN}/api/schedule/*`, (route) => fulfillJson(route, SEASON_2026.schedule));
  await page.route(`${E2E_API_ORIGIN}/api/champions/*`, (route) => fulfillJson(route, SEASON_2026.winners));
});

test("?tab=sessions shows the disqualification's promotion tags and the official in-part gap", async ({ page }) => {
  await page.goto("/race-control/grand-prix?round=19&tab=sessions");

  await expect(page.getByRole("tab", { name: "Sessions", selected: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /takes pole by 0.009 s/ })).toBeVisible();
  await expect(page.getByText("Up 1 · LAW DSQ")).toHaveCount(2);
  await expect(page.getByText("Disqualified from qualifying")).toBeVisible();
  await expect(page.getByRole("row", { name: /Norris/ })).toContainText("+0.310");
  await expect(page.getByRole("columnheader", { name: "Team" })).toHaveCount(0);
});

test("?tab=grid puts the pit-lane starter in the pit-lane box, never in a numbered slot", async ({ page }) => {
  await page.goto("/race-control/grand-prix?round=19&tab=grid");

  await expect(page.getByRole("tab", { name: "Grid", selected: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "3 penalties on the grid" })).toBeVisible();
  const pitLane = page.getByText("Pit lane", { exact: true }).first().locator("..");
  await expect(pitLane).toContainText("Lawson");
  await expect(page.getByText("P22")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Results" })).toHaveAttribute("href", /tab=results/);
});
