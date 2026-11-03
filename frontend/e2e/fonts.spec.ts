import { expect, test } from "@playwright/test";

import { mockBackend } from "./support/mockBackend";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

test("the Barlow Condensed display face resolves and loads", async ({ page }) => {
  await page.goto("/race-control/teams");
  await expect(page.getByRole("heading", { name: "Championship Standings" })).toBeVisible();

  // The token and the components' older `var(--font-barlow, …)` form both
  // resolve to Barlow, not to their fallbacks.
  const families = await page.evaluate(() =>
    ["var(--font-display)", "var(--font-barlow, var(--font-geist-sans))"].map((stack) => {
      const probe = document.createElement("span");
      probe.style.fontFamily = stack;
      document.body.append(probe);
      const family = getComputedStyle(probe).fontFamily;
      probe.remove();
      return family;
    }),
  );
  for (const family of families) expect(family).toMatch(/^"?Barlow Condensed"?,/);

  // Every weight the layout asks next/font for is served.
  const statuses = await page.evaluate(() =>
    Promise.all(
      ["600", "700", "800"].map(async (weight) => {
        const faces = await document.fonts.load(`${weight} 16px "Barlow Condensed"`);
        return faces.map((face) => `${face.weight}:${face.status}`);
      }),
    ),
  );
  expect(statuses).toEqual([["600:loaded"], ["700:loaded"], ["800:loaded"]]);
});
