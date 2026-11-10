import { expect, test } from "@playwright/test";

import { mockBackend } from "./support/mockBackend";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

test("the championship hub shows the standings once the backend is ready", async ({ page }) => {
  await page.goto("/race-control/teams");

  await expect(page.getByRole("heading", { name: "Championship Standings" })).toBeVisible();
  await expect(page.getByText("Mercedes · 380 pts")).toBeVisible();
  const badge = page.getByRole("button", { name: /after round 19 · confirmed · as of/i });
  await expect(badge).toBeVisible();
  await expect(badge).toHaveAccessibleDescription("Sources Base: f1db v2026.19.0, through round 19");
  // The source list stays out of sight until the badge is hovered or focused.
  const sources = page.getByRole("tooltip");
  await expect(sources).toBeHidden();
  await badge.hover();
  await expect(sources).toBeVisible();
  await expect(sources).toContainText("Base: f1db v2026.19.0, through round 19");
  // A backend that answers ready at once never shows the restart notice.
  await expect(page.getByRole("status", { name: "Server status" })).toBeEmpty();
});
