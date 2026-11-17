import { expect, test } from "@playwright/test";

import { ALLOCATION_RESPONSE } from "../test/fixtures/powerUnitsAllocation";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";

const PHONE = { width: 390, height: 844 };

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

test.describe("the Teams index", () => {
  test("lists every team in championship order with its drivers' points", async ({ page }) => {
    await page.goto("/race-control/constructors");

    await expect(page.getByRole("heading", { level: 1, name: "Eleven teams" })).toBeVisible();
    const redBull = page.getByRole("link", { name: /Red Bull/ });
    await expect(redBull).toContainText("R12–14");
    await expect(redBull).toContainText("14");
    await expect(
      redBull.getByRole("img", { name: "Points split: Verstappen 279, Hadjar 122, Lawson 14" }),
    ).toBeVisible();
  });

  test("opens a team from its card", async ({ page }) => {
    await page.goto("/race-control/constructors");
    await page.getByRole("link", { name: /Mercedes/ }).click();

    await expect(page).toHaveURL(/\/race-control\/constructors\/mercedes$/);
  });

  test("does not scroll sideways on a phone", async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto("/race-control/constructors");
    await expect(page.getByRole("heading", { level: 1, name: "Eleven teams" })).toBeVisible();

    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(PHONE.width);
  });
});

test.describe("the Team page", () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`${E2E_API_ORIGIN}/api/race-control/power-units/*`, (route) =>
      fulfillJson(route, ALLOCATION_RESPONSE),
    );
  });

  test("reads a retirement as DNF in the heat grid, never the place it was classified in", async ({ page }) => {
    await page.goto("/race-control/constructors/red-bull");

    await expect(page.getByRole("heading", { level: 1, name: "Red Bull" })).toBeVisible();
    const grid = page.getByRole("table", { name: /race results by round/ });
    const verstappen = grid.getByRole("row", { name: /Verstappen/ });
    await expect(verstappen.getByRole("cell").nth(8)).toContainText("DNF");
    await expect(verstappen.getByRole("cell").nth(8)).toContainText("Spun off");
  });

  test("switches to another team from the strip at the top", async ({ page }) => {
    await page.goto("/race-control/constructors/red-bull");
    const ferrari = page.getByRole("navigation", { name: "Teams" }).getByRole("link", { name: "Ferrari" });

    await expect(ferrari).toHaveAttribute("href", "/race-control/constructors/ferrari");
  });

  test("states the points finding computed from the rounds", async ({ page }) => {
    await page.goto("/race-control/constructors/mercedes");

    await expect(
      page.getByRole("heading", { level: 3, name: "Scored in every round; the Chinese GP was the biggest haul" }),
    ).toBeVisible();
  });

  test("shows the power units on their own endpoint, in car terms", async ({ page }) => {
    await page.goto("/race-control/constructors/mercedes");

    await expect(page.getByRole("heading", { level: 2, name: "Power units" })).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 3, name: "Both cars are past the allocation: 90 grid places lost" }),
    ).toBeVisible();
  });

  test("keeps the rest of the page when the power units fail", async ({ page }) => {
    await page.route(`${E2E_API_ORIGIN}/api/race-control/power-units/*`, (route) =>
      fulfillJson(route, { detail: "boom" }, 500),
    );
    await page.goto("/race-control/constructors/mercedes");

    await expect(page.getByText("Power units unavailable", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "Mercedes" })).toBeVisible();
    await expect(page.getByRole("table", { name: /race results by round/ })).toBeVisible();
  });

  test("says unavailable with a Retry when the team cannot be read, while the switch still renders", async ({
    page,
  }) => {
    await page.route(`${E2E_API_ORIGIN}/api/profiles/*/teams/red-bull`, (route) =>
      fulfillJson(route, { detail: "boom" }, 500),
    );
    await page.goto("/race-control/constructors/red-bull");

    await expect(page.getByText("Team season unavailable", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Teams" })).toBeVisible();
  });

  test("does not scroll sideways on a phone", async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto("/race-control/constructors/mercedes");
    await expect(page.getByRole("heading", { level: 1, name: "Mercedes" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Power units" })).toBeVisible();

    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(PHONE.width);
  });
});

test.describe("the Driver page", () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`${E2E_API_ORIGIN}/api/race-control/power-units/*`, (route) =>
      fulfillJson(route, ALLOCATION_RESPONSE),
    );
  });

  test("reads Verstappen's retirement as DNF and gains and loses no places for it", async ({ page }) => {
    await page.goto("/race-control/drivers/max-verstappen");

    await expect(page.getByRole("heading", { level: 1, name: "Max Verstappen" })).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 3, name: "Verstappen gained 53 places over the season" }),
    ).toBeVisible();
    const columns = page.getByRole("list", { name: "Places gained or lost by round" }).getByRole("listitem");
    await expect(columns.nth(8)).toContainText("DNF");
    await expect(page.locator("main")).not.toContainText("−13");
  });

  test("states the teammate battle and the rule that counts it", async ({ page }) => {
    await page.goto("/race-control/drivers/max-verstappen");

    await expect(
      page.getByRole("heading", { level: 3, name: "Verstappen finished ahead 14 times in 17" }),
    ).toBeVisible();
    await expect(page.getByText(/A retirement or disqualification counts as finishing behind/)).toBeVisible();
  });

  test("loads a driver who raced once, as a stand-in", async ({ page }) => {
    await page.goto("/race-control/drivers/ryo-hirakawa");

    await expect(page.getByRole("heading", { level: 1, name: "Ryō Hirakawa" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 3, name: "Scored in 1 of 1 race" })).toBeVisible();
  });

  test("shows the power unit in car terms, and keeps the page when it fails", async ({ page }) => {
    await page.goto("/race-control/drivers/lewis-hamilton");
    await expect(page.getByRole("heading", { level: 2, name: "Power unit" })).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 3, name: "Car #44 has used its full allocation of every element" }),
    ).toBeVisible();

    await page.route(`${E2E_API_ORIGIN}/api/race-control/power-units/*`, (route) =>
      fulfillJson(route, { detail: "boom" }, 500),
    );
    await page.reload();
    await expect(page.getByText("Power units unavailable", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "Lewis Hamilton" })).toBeVisible();
  });

  test("does not scroll sideways on a phone", async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto("/race-control/drivers/liam-lawson");
    await expect(page.getByRole("heading", { level: 1, name: "Liam Lawson" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Power unit" })).toBeVisible();

    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width).toBeLessThanOrEqual(PHONE.width);
  });
});
