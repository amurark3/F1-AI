import { expect, test } from "@playwright/test";

import { mockBackend } from "./support/mockBackend";

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
