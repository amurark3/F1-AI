import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { mockBackend } from "./support/mockBackend";

import type { APIResponse, Page } from "@playwright/test";

// Playwright loads specs as CommonJS (the package has no "type": "module"), so no import.meta.
const APP_DIR = join(__dirname, "../app");
const ICON_SVG = readFileSync(join(APP_DIR, "icon.svg"), "utf8");
const OG_ALT = readFileSync(join(APP_DIR, "opengraph-image.alt.txt"), "utf8");

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

/** Fetches a head-tag URL from the app under test; absolute og:image URLs keep only their path. */
async function fetchAsset(page: Page, url: string | null): Promise<APIResponse> {
  expect(url).toBeTruthy();
  const { pathname, search } = new URL(url ?? "", "http://app.invalid");
  const response = await page.request.get(`${pathname}${search}`);
  expect(response.status()).toBe(200);
  return response;
}

test("the browser tab shows the B1 mark", async ({ page }) => {
  await page.goto("/");

  const icon = page.locator('head link[rel="icon"]');
  await expect(icon).toHaveCount(1);
  await expect(icon).toHaveAttribute("type", "image/svg+xml");
  await expect(icon).toHaveAttribute("href", /^\/icon\.svg(\?|$)/);

  const response = await fetchAsset(page, await icon.getAttribute("href"));
  expect(response.headers()["content-type"]).toContain("image/svg+xml");
  expect(await response.text()).toBe(ICON_SVG);
});

test("the build serves the apple touch icon and the link preview", async ({ page }) => {
  await page.goto("/");

  const appleIcon = page.locator('head link[rel="apple-touch-icon"]');
  await expect(appleIcon).toHaveAttribute("href", /^\/apple-icon\.png(\?|$)/);
  await expect(appleIcon).toHaveAttribute("sizes", "180x180");
  const icon = await fetchAsset(page, await appleIcon.getAttribute("href"));
  expect(icon.headers()["content-type"]).toBe("image/png");

  const ogImage = page.locator('head meta[property="og:image"]');
  await expect(ogImage).toHaveAttribute("content", /\/opengraph-image\.png(\?|$)/);
  await expect(page.locator('head meta[property="og:image:width"]')).toHaveAttribute("content", "1200");
  await expect(page.locator('head meta[property="og:image:height"]')).toHaveAttribute("content", "630");
  await expect(page.locator('head meta[property="og:image:alt"]')).toHaveAttribute("content", OG_ALT);
  const preview = await fetchAsset(page, await ogImage.getAttribute("content"));
  expect(preview.headers()["content-type"]).toBe("image/png");
});

test("the header shows the F1·AI lockup in the display face", async ({ page }) => {
  await page.goto("/");

  const home = page.locator("header").getByRole("link", { name: "F1 AI home" });
  const lockup = home.getByRole("img", { name: "F1 AI" });
  await expect(lockup).toBeVisible();
  await expect(lockup.locator("svg")).toBeVisible();
  await expect(lockup).toHaveText("F1AI");

  const wordmark = lockup.locator("> span");
  await expect(wordmark).toHaveCSS("font-family", /^"?Barlow Condensed"?,/);
  await expect(wordmark).toHaveCSS("font-weight", "800");
});
