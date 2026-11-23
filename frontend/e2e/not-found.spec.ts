import { expect, test, type Locator, type Page } from "@playwright/test";

import { COMMAND_CENTER_LINK, ENGINEER_LINK, NAV_LINKS } from "../app/ui/shell/navConfig";

import { mockBackend } from "./support/mockBackend";

/** Every screen, in the order the grouped navigation list them. */
const SCREENS = NAV_LINKS;

const footerLinks = (page: Page) =>
  page.getByRole("contentinfo").getByRole("navigation", { name: "Footer" }).getByRole("link");

const hrefs = (links: Locator) => links.evaluateAll((anchors) => anchors.map((a) => a.getAttribute("href")));

test.use({ viewport: { width: 1280, height: 800 } });

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

test("an unknown address answers 404 with the styled page, in the shell, and a way back to every screen", async ({
  page,
}) => {
  const response = await page.goto("/no-such-page");

  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
  await expect(page.getByRole("banner").getByRole("navigation", { name: "Main" })).toBeVisible();

  const wayBack = page.getByRole("navigation", { name: "All screens" }).getByRole("link");
  await expect(wayBack).toHaveText(SCREENS.map(({ label }, i) => `${String(i + 1).padStart(2, "0")}${label}`));
  expect(await hrefs(wayBack)).toEqual(SCREENS.map(({ href }) => href));

  await wayBack.filter({ hasText: "Power Units" }).click();
  await expect(page).toHaveURL(/\/race-control\/power-units(\?|$)/);
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toHaveCount(0);
});

test("the footer lists the same screens as the grouped navigation, on every framed page", async ({ page }) => {
  for (const path of ["/race-control", "/no-such-page"]) {
    await page.goto(path);

    await expect(footerLinks(page)).toHaveText(SCREENS.map(({ label }) => label));
    expect(await hrefs(footerLinks(page))).toEqual(SCREENS.map(({ href }) => href));
    await expect(page.getByRole("banner").getByRole("navigation", { name: "Main" }).getByRole("link")).toHaveText([
      COMMAND_CENTER_LINK.label,
      ENGINEER_LINK.label,
    ]);
  }
});
