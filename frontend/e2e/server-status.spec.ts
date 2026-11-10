import { expect, test } from "@playwright/test";

import { WARMING } from "../test/fixtures";

import { E2E_API_ORIGIN, mockBackend } from "./support/mockBackend";

/**
 * The backend is always on, so the only warm-up a reader ever sees is a restart
 * (a deploy). It must never hold a page back (PLAN.md, locked decision
 * "Loading", 2026-11-08): a small notice says why, and the page stays usable.
 */
test("a restarting backend shows a notice and leaves the page usable", async ({ page }) => {
  await mockBackend(page, { readiness: WARMING });
  await page.goto("/race-control/teams");

  const notice = page.getByRole("status", { name: "Server status" });
  await expect(notice).toContainText("Updating — back in a few seconds");
  await expect(notice).toContainText("Loading the race prediction model");
  // The lights follow the backend's real stage: the model is the third of five.
  await expect(notice.getByRole("progressbar", { name: "Server restart progress" })).toHaveAttribute(
    "aria-valuenow",
    "3",
  );

  // Nothing is blocked: no inert subtree, no modal, the data shows, and a link
  // still takes the reader to another page, where the notice follows.
  await expect(page.locator("[inert]")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("Mercedes · 380 pts")).toBeVisible();
  await page.getByRole("link", { name: "Champions", exact: true }).click();
  await expect(page).toHaveURL(/\/race-control\/champions$/);
  await expect(notice).toContainText("Updating — back in a few seconds");
});

test("a backend that is up shows no notice", async ({ page }) => {
  await mockBackend(page);
  const probe = page.waitForResponse(`${E2E_API_ORIGIN}/api/ready`);
  await page.goto("/race-control/teams");
  await probe;

  await expect(page.getByText("Mercedes · 380 pts")).toBeVisible();
  await expect(page.getByRole("status", { name: "Server status" })).toBeEmpty();
});
