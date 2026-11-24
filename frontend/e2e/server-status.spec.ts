import { expect, test, type Page } from "@playwright/test";

import { READY } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";

const HELD_AT_MODEL = { ready: false, stage: "model", detail: "Loading the race prediction model" };
const READINESS_URL = `${E2E_API_ORIGIN}/api/ready`;
const PHONE = { width: 390, height: 844 };

const region = (page: Page) => page.getByRole("status", { name: "Server status" });
const litLamps = (page: Page) => page.locator("header i.bg-f1-red");

/** Nothing is blocked: no inert subtree, no scroll lock, no dialog, and the page takes a click. */
async function expectInteractive(page: Page): Promise<void> {
  await expect(page.locator("[inert]")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).not.toBe("hidden");
  await page.getByRole("link", { name: "F1 AI home" }).focus();
  await expect(page.getByRole("link", { name: "F1 AI home" })).toBeFocused();
}

test.describe("backend up", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackend(page);
  });

  for (const path of ["/", "/race-control/standings"]) {
    test(`${path} shows nothing, with the status region mounted and empty`, async ({ page }) => {
      await page.goto(path);

      await expect(region(page)).toBeEmpty();
      await expect(page.getByText("Server starting")).toHaveCount(0);
      await expect(litLamps(page)).toHaveCount(0);
      await expectInteractive(page);
    });
  }
});

test.describe("backend restarting", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackend(page, { readiness: HELD_AT_MODEL });
  });

  for (const path of ["/", "/race-control/standings"]) {
    test(`${path} stays interactive and shows the lights at the stage's count`, async ({ page }) => {
      await page.goto(path);

      await expect(region(page)).toHaveText("Server starting: Loading the race prediction model");
      await expect(page.getByRole("button", { name: /Server starting/ })).toBeVisible();
      await expect(litLamps(page)).toHaveCount(3);
      await expectInteractive(page);

      await page.getByRole("button", { name: /Server starting/ }).hover();
      await expect(page.getByRole("tooltip")).toContainText("Loading the race prediction model");
      await expect(page.getByRole("tooltip")).toContainText("Stage 3 of 5");
    });
  }

  test("a link still navigates while the lights are up", async ({ page }) => {
    await page.goto("/");
    await expect(litLamps(page)).toHaveCount(3);

    await page.getByRole("link", { name: "F1 AI home" }).click();
    await expect(page).toHaveURL(/\/$/);
    await page.goto("/race-control/standings");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(litLamps(page)).toHaveCount(3);
  });

  test("on a phone the lights take the bar's slot without a sideways scroll", async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto("/race-control/standings");

    await expect(page.getByRole("button", { name: /Starting/ })).toBeVisible();
    await expect(litLamps(page)).toHaveCount(3);
    const [scrollWidth, clientWidth] = await page.evaluate(() => [
      document.documentElement.scrollWidth,
      document.documentElement.clientWidth,
    ]);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });
});

test("ready plays back online and lights out, then the lights go and the region empties", async ({ page }) => {
  let body: unknown = { ready: false, stage: "season", detail: "Priming this season's schedule" };
  await mockBackend(page);
  await page.route(READINESS_URL, (route) => fulfillJson(route, body));
  await page.goto("/");
  await expect(litLamps(page)).toHaveCount(4);

  body = READY;
  await expect(region(page)).toHaveText("Back online", { timeout: 10_000 });
  await expect(litLamps(page)).toHaveCount(5);
  await expect(litLamps(page)).toHaveCount(0);
  await expect(page.getByText("Back online")).toHaveCount(0, { timeout: 5000 });
  await expect(region(page)).toBeEmpty();
});

test("a failed probe keeps the lights on the count reached instead of putting them out", async ({ page }) => {
  let fail = false;
  await mockBackend(page);
  await page.route(READINESS_URL, (route) =>
    fail ? route.abort("connectionrefused") : fulfillJson(route, HELD_AT_MODEL),
  );
  await page.goto("/");
  await expect(litLamps(page)).toHaveCount(3);

  fail = true;
  await page.waitForTimeout(7000);
  await expect(litLamps(page)).toHaveCount(3);
  await expect(page.getByRole("button", { name: /Server starting/ })).toBeVisible();
});
