import { describe, expect, it } from "vitest";

import {
  brakeTitle,
  deltaTitle,
  gearTitle,
  lapTitle,
  mapTitle,
  speedTitle,
  throttleTitle,
  timeShare,
} from "./headToHeadInsights";
import { traceRows } from "./headToHeadModel";
import { COMPARISON } from "./telemetryTestData";

const CODES = { a: "ANT", b: "RUS" };
const ROWS = traceRows(COMPARISON.trace, COMPARISON.gap);

describe("head-to-head titles", () => {
  it("names who won the lap, or says it was level", () => {
    expect(lapTitle(0.27, CODES)).toBe("ANT by 0.270 s");
    expect(lapTitle(-0.1, CODES)).toBe("RUS by 0.100 s");
    expect(lapTitle(0.0001, CODES)).toBe("Level on the line");
    expect(lapTitle(undefined, CODES)).toBe("Lap and sector times");
  });

  it("counts mini-sectors, and stays neutral without any", () => {
    const stretch = (faster: "a" | "b" | "even") => ({ label: "m", start: 0, end: 1, gain: 0, faster });
    expect(mapTitle([stretch("a"), stretch("a"), stretch("b")], CODES)).toBe(
      "ANT faster in 2 of 3 mini-sectors, RUS in 1",
    );
    expect(mapTitle([stretch("b"), stretch("b"), stretch("a")], CODES)).toContain("RUS faster in 2 of 3");
    expect(mapTitle([stretch("a"), stretch("b")], CODES)).toBe("The mini-sectors split 1–1");
    expect(mapTitle([], CODES)).toBe("Mini-sector map");
  });

  it("finds the biggest swing in the gap within a kilometre", () => {
    expect(deltaTitle(ROWS, CODES)).toBe("ANT gains 0.14 s between 0.0 and 1.0 km");
    const flipped = ROWS.map((row) => ({ ...row, delta: -row.delta }));
    expect(deltaTitle(flipped, CODES)).toContain("RUS gains");
    expect(deltaTitle([], CODES)).toBe("Gap along the lap");
    expect(
      deltaTitle(
        ROWS.map((row) => ({ ...row, delta: 0 })),
        CODES,
      ),
    ).toBe("Gap along the lap");
  });

  it("states top speed for the faster driver first, or a tie", () => {
    expect(speedTitle(ROWS, CODES)).toBe("Top speed 320 km/h for ANT, 310 for RUS");
    const swapped = ROWS.map((row) => ({ ...row, speed_a: row.speed_b, speed_b: row.speed_a }));
    expect(speedTitle(swapped, CODES)).toBe("Top speed 320 km/h for RUS, 310 for ANT");
    expect(
      speedTitle(
        ROWS.map((row) => ({ ...row, speed_b: row.speed_a })),
        CODES,
      ),
    ).toBe("Both top out at 320 km/h");
    expect(speedTitle([], CODES)).toBe("Speed trace");
  });

  it("weights shares by time, not by sample count", () => {
    // Same two samples, but the slow one lasts far longer.
    const rows = [
      { ...ROWS[0], distance: 0, speed_a: 360, brake_a: 0 },
      { ...ROWS[0], distance: 1000, speed_a: 36, brake_a: 100 },
      { ...ROWS[0], distance: 2000, speed_a: 36, brake_a: 100 },
    ];
    expect(timeShare(rows, "a", (row) => row.brake_a > 0)).toBeCloseTo(90.9, 1);
    expect(timeShare([], "a", () => true)).toBeNull();
  });

  it("compares full throttle, braking and top-gear time, and goes neutral without a trace", () => {
    expect(throttleTitle(ROWS, CODES)).toBe("Both flat out for 77% of the lap");
    expect(brakeTitle(ROWS, CODES)).toMatch(/^RUS on the brakes for \d+% of the lap, the other \d+%$/);
    expect(gearTitle(ROWS, CODES)).toMatch(/^ANT in gear 8 for \d+% of the lap, the other \d+%$/);
    const slower = ROWS.map((row) => ({ ...row, throttle_b: 50 }));
    expect(throttleTitle(slower, CODES)).toMatch(/^ANT flat out for \d+% of the lap, the other \d+%$/);
    const swapped = ROWS.map((row) => ({ ...row, brake_a: row.brake_b, brake_b: row.brake_a }));
    expect(brakeTitle(swapped, CODES)).toMatch(/^ANT on the brakes/);
    const same = ROWS.map((row) => ({ ...row, brake_b: row.brake_a, speed_b: row.speed_a }));
    expect(brakeTitle(same, CODES)).toMatch(/^Both on the brakes for \d+% of the lap$/);
    const alike = ROWS.map((row) => ({ ...row, gear_b: row.gear_a, speed_b: row.speed_a }));
    expect(gearTitle(alike, CODES)).toMatch(/^Both in gear 8 for \d+% of the lap$/);
    expect(brakeTitle([], CODES)).toBe("Brake trace");
    expect(throttleTitle([], CODES)).toBe("Throttle trace");
    expect(gearTitle([], CODES)).toBe("Gear trace");
  });
});
