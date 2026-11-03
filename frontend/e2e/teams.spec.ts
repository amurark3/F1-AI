import { expect, test } from "@playwright/test";

import { mockBackend } from "./support/mockBackend";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

test("the championship hub shows the standings once the backend is ready", async ({ page }) => {
  await page.goto("/race-control/teams");

  await expect(page.getByRole("heading", { name: "Championship Standings" })).toBeVisible();
  await expect(page.getByText("Mercedes · 380 pts")).toBeVisible();
  await expect(page.getByText(/after round 19 · confirmed/)).toBeVisible();
  // A backend that answers ready at once never raises the warm-up screen.
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
