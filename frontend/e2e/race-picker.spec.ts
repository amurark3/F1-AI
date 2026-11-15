import { expect, test } from "@playwright/test";

import { SEASON_2026 } from "../test/fixtures";

import { E2E_API_ORIGIN, fulfillJson, mockBackend } from "./support/mockBackend";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.route(`${E2E_API_ORIGIN}/api/schedule/*`, (route) => fulfillJson(route, SEASON_2026.schedule));
  await page.route(`${E2E_API_ORIGIN}/api/champions/*`, (route) => fulfillJson(route, SEASON_2026.winners));
});

/** The URL's `round`, exactly: `round=2` must not match `round=20`. */
function roundIs(round: number): RegExp {
  return new RegExp(`[?&]round=${round}(&|$)`);
}

// The Telemetry Lab: the picker with its season select, on a page that never
// waits on the backend, so the unmocked analysis requests cannot hide it.
test("the race picker changes ?round= from the keyboard alone", async ({ page }) => {
  await page.goto("/race-control/telemetry?tab=map&year=2026&round=20");

  const rail = page.getByRole("listbox", { name: "2026 season rounds" });
  await expect(rail.getByRole("option", { selected: true })).toHaveAccessibleName(
    "R20 · São Paulo GP, Lando Norris won · McLaren",
  );

  // The arrows preview a round; Enter selects it.
  await rail.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page).toHaveURL(roundIs(20));
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(roundIs(19));
  await expect(rail.getByRole("option", { selected: true })).toHaveAccessibleName(
    "R19 · Mexico City GP, Max Verstappen won · Red Bull",
  );

  // › steps to the next round.
  await page.getByRole("button", { name: "Next round" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(roundIs(20));

  // "All races" opens a list that takes focus; End and Enter choose the finale and close it.
  const allRaces = page.getByRole("button", { name: "All races" });
  const list = page.getByRole("listbox", { name: "All 2026 races" });
  await allRaces.focus();
  await page.keyboard.press("Enter");
  await expect(list).toBeFocused();
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(roundIs(23));
  await expect(list).toBeHidden();
  await expect(allRaces).toBeFocused();

  // Escape closes it without choosing.
  await page.keyboard.press("Enter");
  await expect(list).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(list).toBeHidden();
  await expect(allRaces).toBeFocused();
  await expect(page).toHaveURL(roundIs(23));
});
