import { expect, test, type Locator, type Page } from "@playwright/test";

import { OVERVIEW_SEGMENTS_2026, RACE_RESULTS_2026, SEASON_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";

const SHELL_URL = `${E2E_API_ORIGIN}/api/race-control/overview/*/shell`;
const CORS_HEADERS = { "access-control-allow-origin": "*" };
/** São Paulo week, before Practice 1 (6 Nov, 15:30 UTC): the fixture's weekend is still ahead. */
const SAO_PAULO_WEEK = new Date("2026-11-03T13:15:30Z");

const DESKTOP = { width: 1024, height: 800 };
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
const thisRace = (page: Page) => page.getByRole("navigation", { name: "This race" });
const mainNav = (page: Page) => topBar(page).getByRole("navigation", { name: "Main" });

function documentTop(locator: Locator): Promise<number> {
  return locator.evaluate((element) => element.getBoundingClientRect().top + window.scrollY);
}

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.route(`${E2E_API_ORIGIN}/api/schedule/*`, (route) => fulfillJson(route, SEASON_2026.schedule));
});

test.describe("on a wide screen", () => {
  test.use({ viewport: DESKTOP });

  test("the grouped bar fits on one line at 1024 px with the race status", async ({ page }) => {
    await page.clock.install({ time: SAO_PAULO_WEEK });
    await serveShell(page);
    await page.goto("/race-control/standings");

    const nav = mainNav(page);
    await expect(topBar(page)).toHaveCount(1);
    await expect(nav.getByRole("link")).toHaveText(["Race Control", "AI Engineer"]);
    await expect(nav.getByRole("button")).toHaveText(["Races", "Season", "Reference"]);
    const chip = topBar(page).getByRole("button", { name: "R20 · Pre-race" });
    await expect(chip).toBeVisible();
    await expect(topBar(page).getByRole("button", { name: "Menu" })).toBeHidden();
    const control = await nav.getByRole("link", { name: "Race Control" }).boundingBox();
    const status = await chip.boundingBox();
    expect(status?.x).toBeGreaterThan(control?.x ?? 0);
    expect(status!.x + status!.width).toBeLessThanOrEqual(DESKTOP.width);
    expect(Math.abs(status!.y + status!.height / 2 - (control!.y + control!.height / 2))).toBeLessThan(2);
  });

  test("all three menus open on click, close independently and support keyboard travel", async ({ page }) => {
    await page.goto("/race-control/standings");
    const nav = mainNav(page);
    const races = nav.getByRole("button", { name: "Races" });
    const season = nav.getByRole("button", { name: "Season" });
    const reference = nav.getByRole("button", { name: "Reference" });
    await expect(season.locator("span.bg-f1-red")).toBeAttached();

    await races.hover();
    await expect(races).toHaveAttribute("aria-expanded", "false");
    await races.click();
    await expect(nav.getByRole("link")).toHaveText([
      "Race Control",
      /^Grand Prix/,
      /^Telemetry/,
      /^Debrief/,
      /^Race Rewind/,
      "AI Engineer",
    ]);

    await season.click();
    await expect(races).toHaveAttribute("aria-expanded", "false");
    await expect(nav.getByRole("link", { name: /^Standings/ })).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("link", { name: /^Teams & drivers/ })).toBeVisible();
    await expect(nav.getByRole("link", { name: /^Power Units/ })).toBeVisible();

    await reference.click();
    await expect(season).toHaveAttribute("aria-expanded", "false");
    await expect(nav.getByRole("link", { name: /^Rulebook/ })).toBeVisible();
    const champions = nav.getByRole("link", { name: /^Champions/ });
    await page.keyboard.press("Escape");
    await expect(reference).toBeFocused();
    await expect(champions).toBeHidden();
    await page.keyboard.press("ArrowDown");
    await expect(champions).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/race-control\/champions(\?|$)/);
    await expect(reference).toHaveAttribute("aria-expanded", "false");
    await expect(reference.locator("span.bg-f1-red")).toBeAttached();
  });

  test("a driver profile highlights the Season menu and its Teams & drivers link", async ({ page }) => {
    await page.goto("/race-control/drivers/lewis-hamilton");
    await expect(mainNav(page).getByRole("link", { name: "Race Control" })).not.toHaveAttribute("aria-current");
    await mainNav(page).getByRole("button", { name: "Season" }).click();
    await expect(mainNav(page).getByRole("link", { name: /^Teams & drivers/ })).toHaveAttribute("aria-current", "true");
  });

  test("the status chip reads the weekend, with its countdown on hover", async ({ page }) => {
    await page.clock.install({ time: SAO_PAULO_WEEK });
    await serveShell(page);
    await page.goto("/race-control/standings");

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
    await page.goto("/race-control/standings");

    await expect(mainNav(page)).toBeHidden();
    const menuButton = topBar(page).getByRole("button", { name: "Menu" });
    await menuButton.click();

    const menu = page.getByRole("dialog", { name: "Site menu" });
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("button", { name: "Close" })).toBeFocused();
    const drawer = menu.getByRole("navigation", { name: "Main" });
    await expect(drawer.getByRole("link")).toHaveCount(11);
    await expect(drawer.getByRole("heading")).toHaveText(["Races", "Season", "Reference"]);
    expect(await menu.evaluate((element) => element.scrollWidth)).toBeLessThanOrEqual(PHONE.width);
    await expect(menu.getByRole("link", { name: /Standings/ })).toHaveAttribute("aria-current", "page");
    await expect(menu.getByRole("button", { name: "R20 · Pre-race" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.style.overflow)).toBe("hidden");

    // Shift+Tab from the first control goes round to the last: focus never leaves the menu.
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(menu.getByRole("link", { name: "AI Engineer" })).toBeFocused();

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

test("This race carries a historical season and a newly picked round between all four pages", async ({ page }) => {
  const season = SEASON_2026.schedule.map((race) =>
    race.round === 19 ? { ...race, name: "Historical Grand Prix" } : race,
  );
  await page.route(`${E2E_API_ORIGIN}/api/schedule/2025`, (route) => fulfillJson(route, season));
  await page.route(`${E2E_API_ORIGIN}/api/race-control/results/2025/19`, (route) =>
    fulfillJson(route, { ...RACE_RESULTS_2026.mexicoCity, year: 2025 }),
  );
  await page.goto("/race-control/telemetry?round=20&year=2025");
  const picker = page.getByRole("group", { name: "2025 race picker" });
  await picker.getByRole("button", { name: "Previous round" }).click();
  await expect(picker.getByText("Historical GP", { exact: true })).toBeVisible();
  await expect(thisRace(page).getByRole("link")).toHaveText(["Grand Prix", "Telemetry", "Debrief", "Rewind"]);
  const pickerTop = await documentTop(picker);
  const switcherTop = await documentTop(thisRace(page));

  for (const [view, path] of [
    ["Grand Prix", "grand-prix"],
    ["Debrief", "debriefs"],
    ["Rewind", "rewind"],
    ["Telemetry", "telemetry"],
  ]) {
    await thisRace(page).getByRole("link", { name: view }).click();
    await expect(page).toHaveURL(`/race-control/${path}?round=19&year=2025`);
    await expect(thisRace(page).getByRole("link", { name: view })).toHaveAttribute("aria-current", "page");
    await expect(picker.getByText("Historical GP", { exact: true })).toBeVisible();
    expect(await documentTop(picker)).toBeCloseTo(pickerTop, 0);
    expect(await documentTop(thisRace(page))).toBeCloseTo(switcherTop, 0);
  }
});

test("This race leaves post-race views disabled on a 390 px screen while the race has no result", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto("/race-control/grand-prix?round=21");
  const nav = thisRace(page);
  await expect(nav.locator("a, button")).toHaveText(["Grand Prix", "Telemetry", "Debrief", "Rewind"]);
  await expect(nav.getByRole("button", { name: "Debrief" })).toBeDisabled();
  await expect(nav.getByRole("button", { name: "Rewind" })).toBeDisabled();
  const switcherTop = await documentTop(nav);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(PHONE.width);
  await nav.getByRole("link", { name: "Telemetry" }).click();
  await expect(page).toHaveURL(/round=21&year=2026$/);
  await expect(nav.getByRole("link", { name: "Telemetry" })).toHaveAttribute("aria-current", "page");
  expect(await documentTop(nav)).toBeCloseTo(switcherTop, 0);
  const title = page.getByRole("heading", { level: 1, name: "Telemetry Lab" });
  expect(await documentTop(title)).toBeGreaterThan(switcherTop);
  expect(await documentTop(page.getByRole("tablist", { name: "Analysis" }))).toBeGreaterThan(await documentTop(title));
  await expect(page.getByRole("combobox", { name: "Season" })).toHaveValue("2026");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(PHONE.width);
});
