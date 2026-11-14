import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { E2E_API_ORIGIN, mockBackend } from "./support/mockBackend";

// Playwright loads specs as CommonJS (the package has no "type": "module"), so no import.meta.
const PRERENDER_MANIFEST = join(__dirname, "../.next/prerender-manifest.json");
const READINESS_PATH = "/api/ready";

const PHONE = { width: 390, height: 844 };

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

test("the build prerenders the homepage once and never revalidates it", () => {
  const manifest = JSON.parse(readFileSync(PRERENDER_MANIFEST, "utf8")) as {
    routes: Record<string, { initialRevalidateSeconds: number | false } | undefined>;
  };

  expect(manifest.routes["/"]?.initialRevalidateSeconds).toBe(false);
});

test("the readiness probe is the homepage's only call to the backend", async ({ page }) => {
  const calls: string[] = [];
  page.on("request", (request) => {
    if (request.url().startsWith(E2E_API_ORIGIN)) calls.push(new URL(request.url()).pathname);
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: /Your AI\s*Race Engineer/ })).toBeVisible();
  await page.waitForLoadState("networkidle");

  expect(calls.filter((path) => path !== READINESS_PATH)).toEqual([]);
});

test("every link on the homepage opens a real screen", async ({ page }) => {
  await page.goto("/");
  const hrefs = await page
    .locator("#main")
    .getByRole("link")
    .evaluateAll((links) => links.map((link) => link.getAttribute("href") ?? ""));
  const screens = [...new Set(hrefs)];
  expect(screens.length).toBeGreaterThan(0);

  const statuses = await Promise.all(
    screens.map(async (href) => [href, (await page.request.get(href)).status()] as const),
  );
  expect(statuses.filter(([, status]) => status !== 200)).toEqual([]);
});

test("the hero's calls to action open Race Control and the AI Engineer", async ({ page }) => {
  const mainNav = page.getByRole("banner").getByRole("navigation", { name: "Main" });

  await page.goto("/");
  await page.getByRole("link", { name: /^Enter Race Control/ }).click();
  await expect(page).toHaveURL(/\/race-control$/);
  await expect(mainNav.getByRole("link", { name: "Race Control", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );

  await page.goto("/");
  await page.getByRole("link", { name: /^Ask the AI Engineer/ }).click();
  await expect(page).toHaveURL(/\/race-control\/engineer$/);
  await expect(mainNav.getByRole("link", { name: "AI Engineer" })).toHaveAttribute("aria-current", "page");
});

test.describe("on a phone", () => {
  test.use({ viewport: PHONE });

  test("the homepage fits the screen with no sideways scroll", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: /^Enter Race Control/ })).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
