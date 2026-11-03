import { describe, expect, it } from "vitest";

import { countdownParts } from "./countdownParts";

const NOW = Date.UTC(2026, 10, 2, 12, 0, 0);
const SECOND = 1000;

describe("countdownParts", () => {
  it("splits the time left into padded days, hours, minutes and seconds", () => {
    const target = NOW + ((2 * 24 + 3) * 3600 + 4 * 60 + 5) * SECOND;
    expect(countdownParts(target, NOW)).toEqual({ days: "02", hours: "03", minutes: "04", seconds: "05" });
  });

  it("keeps three-digit day counts whole", () => {
    expect(countdownParts(NOW + 120 * 86_400 * SECOND, NOW).days).toBe("120");
  });

  it("drops a partial second rather than rounding up", () => {
    expect(countdownParts(NOW + 59_999, NOW)).toEqual({ days: "00", hours: "00", minutes: "00", seconds: "59" });
  });

  it.each([
    ["the moment itself", NOW],
    ["a moment already past", NOW - 90 * SECOND],
  ])("reads all zeros at %s", (_case, target) => {
    expect(countdownParts(target, NOW)).toEqual({ days: "00", hours: "00", minutes: "00", seconds: "00" });
  });
});
