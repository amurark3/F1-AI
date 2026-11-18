import { expect, test, type Page } from "@playwright/test";

import { CLINCH_2026, OVERVIEW_SEGMENTS_2026, STANDINGS_PROGRESSION_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.route(`${E2E_API_ORIGIN}/api/race-control/overview/*/shell`, (route) =>
    fulfillJson(route, OVERVIEW_SEGMENTS_2026.shell),
  );
  await page.route(`${E2E_API_ORIGIN}/api/race-control/standings/*/progression`, (route) =>
    fulfillJson(route, STANDINGS_PROGRESSION_2026),
  );
});

async function answerClinch(page: Page, body: unknown, status = 200): Promise<void> {
  await page.route(`${E2E_API_ORIGIN}/api/race-control/standings/*/clinch`, (route) =>
    fulfillJson(route, body, status),
  );
}

test("the Standings page says where one title was clinched and where the other can be", async ({ page }) => {
  await answerClinch(page, CLINCH_2026.afterRound19);
  await page.goto("/race-control/standings");

  await expect(page.getByText("Provisionally clinched in Mexico City", { exact: true })).toBeVisible();
  await expect(page.getByText("Mercedes can clinch in São Paulo", { exact: true })).toBeVisible();
});

test("a team page adds the team's own clause after its standing", async ({ page }) => {
  await answerClinch(page, CLINCH_2026.afterRound20);
  await page.goto("/race-control/constructors/mercedes");

  await expect(page.getByText("Clinched in São Paulo with three races to spare.", { exact: true })).toBeVisible();
});

test("the Standings page keeps its plain lead line when the calculator cannot be read", async ({ page }) => {
  await answerClinch(page, { detail: "boom" }, 500);
  await page.goto("/race-control/standings");

  await expect(page.getByText(/^119 points clear of .*Verstappen after round 19\.$/)).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Constructors" })).toBeVisible();
});
