import { expect, test, type Page } from "@playwright/test";

import { OVERVIEW_SEGMENTS_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, mockBackend } from "./support/mockBackend";

const SHELL_URL = `${E2E_API_ORIGIN}/api/race-control/overview/*/shell`;
const CORS_HEADERS = { "access-control-allow-origin": "*" };
/** São Paulo week, before Practice 1 (6 Nov, 15:30 UTC): the fixture's weekend is still ahead. */
const SAO_PAULO_WEEK = new Date("2026-11-03T13:15:30Z");

const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 844 };

/** Serves the shell segment and counts the requests for it. */
async function serveShell(page: Page): Promise<{ count: () => number }> {
  let requests = 0;
  await page.route(SHELL_URL, (route) => {
    requests += 1;
    return route.fulfill({ json: OVERVIEW_SEGMENTS_2026.shell, headers: CORS_HEADERS });
  });
  return { count: () => requests };
}

const topBar = (page: Page) => page.getByRole("banner");
const mainNav = (page: Page) => topBar(page).getByRole("navigation", { name: "Main" });

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

test.describe("on a wide screen", () => {
  test.use({ viewport: DESKTOP });

  test("one top bar on every screen, with the current section marked, and no sidebar", async ({ page }) => {
    for (const [path, section] of [
      ["/race-control", "Race Control"],
      ["/race-control/teams", "Standings"],
      ["/race-control/drivers/lewis-hamilton", "Teams"],
    ] as const) {
      await page.goto(path);
      await expect(topBar(page)).toHaveCount(1);
      await expect(mainNav(page).getByRole("link")).toHaveText([
        "Race Control",
        "Grand Prix",
        "Telemetry",
        "Standings",
        "Teams",
        "Power Units",
        "AI Engineer",
      ]);
      await expect(mainNav(page).getByRole("link", { name: section, exact: true })).toHaveAttribute(
        "aria-current",
        /^(page|true)$/,
      );
      await expect(page.getByRole("complementary", { name: "Race Control navigation" })).toHaveCount(0);
      await expect(page.getByText("Decision Tools")).toHaveCount(0);
    }
  });

  test("a click moves the current section to the screen it opens", async ({ page }) => {
    await page.goto("/race-control/teams");
    await mainNav(page).getByRole("link", { name: "Power Units" }).click();

    await expect(page).toHaveURL(/\/race-control\/power-units(\?|$)/);
    await expect(mainNav(page).getByRole("link", { name: "Power Units" })).toHaveAttribute("aria-current", "page");
    await expect(mainNav(page).getByRole("link", { name: "Standings" })).not.toHaveAttribute("aria-current");
  });

  test("More holds Champions, Debriefs and Rulebook, by mouse or keyboard", async ({ page }) => {
    await page.goto("/race-control/teams");
    const more = mainNav(page).getByRole("button", { name: "More" });
    const champions = mainNav(page).getByRole("link", { name: /^Champions/ });

    await expect(champions).toBeHidden();
    await more.click();
    await expect(more).toHaveAttribute("aria-expanded", "true");
    await expect(champions).toBeVisible();
    await expect(mainNav(page).getByRole("link", { name: /^Debriefs/ })).toBeVisible();
    await expect(mainNav(page).getByRole("link", { name: /^Rulebook/ })).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(champions).toBeHidden();
    await expect(more).toBeFocused();

    await page.keyboard.press("ArrowDown");
    await expect(champions).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/race-control\/champions(\?|$)/);
    await expect(more).toHaveAttribute("aria-expanded", "false");

    await more.click();
    await expect(champions).toHaveAttribute("aria-current", "page");
  });

  test("the status chip reads the weekend, with its countdown on hover", async ({ page }) => {
    await page.clock.install({ time: SAO_PAULO_WEEK });
    await serveShell(page);
    await page.goto("/race-control/teams");

    const chip = topBar(page).getByRole("button", { name: "R20 · Pre-race" });
    await expect(chip).toBeVisible();
    await chip.hover();
    const tip = page.getByRole("tooltip");
    await expect(tip).toContainText("São Paulo Grand Prix");
    await expect(tip).toContainText(/Practice 1 in 3d 02h 1\dm/);
  });

  test("the static homepage shows no status and never asks for it", async ({ page }) => {
    const shell = await serveShell(page);
    await page.goto("/");

    await expect(mainNav(page)).toBeVisible();
    await expect(topBar(page).getByRole("button", { name: /^R\d+ · / })).toHaveCount(0);
    await page.waitForLoadState("networkidle");
    expect(shell.count()).toBe(0);
  });

  test("the AI Engineer fills the screen under the bar, with no footer to scroll to", async ({ page }) => {
    await page.goto("/race-control/engineer");

    await expect(mainNav(page).getByRole("link", { name: "AI Engineer" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("contentinfo")).toHaveCount(0);
    const overflow = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test.describe("on a phone", () => {
  test.use({ viewport: PHONE });

  test("MENU opens every section in a modal menu that keeps focus and holds the page still", async ({ page }) => {
    await page.clock.install({ time: SAO_PAULO_WEEK });
    await serveShell(page);
    await page.goto("/race-control/teams");

    await expect(mainNav(page)).toBeHidden();
    const menuButton = topBar(page).getByRole("button", { name: "Menu" });
    await menuButton.click();

    const menu = page.getByRole("dialog", { name: "Site menu" });
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("button", { name: "Close" })).toBeFocused();
    await expect(menu.getByRole("navigation", { name: "Main" }).getByRole("link")).toHaveCount(10);
    await expect(menu.getByRole("link", { name: /Standings/ })).toHaveAttribute("aria-current", "page");
    await expect(menu.getByRole("button", { name: "R20 · Pre-race" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.style.overflow)).toBe("hidden");

    // Shift+Tab from the first control goes round to the last: focus never leaves the menu.
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(menu.getByRole("link", { name: /Rulebook/ })).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(menuButton).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.style.overflow)).toBe("");

    await menuButton.click();
    await menu.getByRole("link", { name: /Grand Prix/ }).click();
    await expect(page).toHaveURL(/\/race-control\/grand-prix(\?|$)/);
    await expect(menu).toBeHidden();
  });
});
