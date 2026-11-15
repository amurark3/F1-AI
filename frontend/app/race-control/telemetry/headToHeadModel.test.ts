import { describe, expect, it } from "vitest";

import {
  gainLabel,
  pairColours,
  rankedDrivers,
  resolvePair,
  smoothDelta,
  traceRows,
  winnerColour,
} from "./headToHeadModel";
import { COMPARISON, LAPS } from "./telemetryTestData";
import { EVEN_COLOUR } from "./trackMapGeometry";

describe("smoothDelta", () => {
  it("smooths a spike but starts at 0 and ends exactly on the gap", () => {
    const raw = [0, 0.01, 0.4, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.27];
    const smooth = smoothDelta(raw, 0.27);
    expect(smooth[0]).toBe(0);
    expect(smooth.at(-1)).toBeCloseTo(0.27, 12);
    expect(Math.max(...smooth)).toBeLessThan(0.4);
  });

  it("copes with traces too short to smooth", () => {
    expect(smoothDelta([], 0.3)).toEqual([]);
    expect(smoothDelta([0.1], 0.3)).toEqual([0.3]);
  });
});

describe("traceRows", () => {
  it("makes a row per step with the delta pinned to the gap", () => {
    const rows = traceRows(COMPARISON.trace, 0.27);
    expect(rows).toHaveLength(5);
    expect(rows[4].delta).toBeCloseTo(0.27, 12);
    expect(rows[2].speed_a).toBe(320);
  });

  it("pins to its own last value without a gap, and takes no trace as none", () => {
    expect(traceRows(COMPARISON.trace)[4].delta).toBeCloseTo(0.27, 12);
    expect(traceRows(undefined)).toEqual([]);
    expect(traceRows({ distance: [0, 1] })[1]).toMatchObject({ delta: 0, speed_a: 0 });
  });
});

describe("gainLabel", () => {
  it("names who gained and by how much, or calls it even", () => {
    const stretch = { label: "m", start: 0, end: 1, gain: -0.0961, faster: "b" as const };
    expect(gainLabel(stretch, { a: "ANT", b: "RUS" })).toBe("RUS +0.096s");
    expect(gainLabel({ ...stretch, faster: "even" }, { a: "ANT", b: "RUS" })).toBe("even");
  });
});

describe("pair", () => {
  it("keeps drivers with a valid lap and picks the two quickest by default", () => {
    const drivers = rankedDrivers(LAPS.drivers);
    expect(drivers.map((driver) => driver.code)).toEqual(["ANT"]);
    expect(rankedDrivers(undefined)).toEqual([]);
    const two = [...drivers, { ...drivers[0], code: "RUS" }];
    expect(resolvePair(two, null, null)).toEqual({ first: "ANT", second: "RUS" });
    expect(resolvePair(two, "RUS", "ANT")).toEqual({ first: "RUS", second: "ANT" });
    expect(resolvePair([], null, null)).toEqual({ first: null, second: null });
  });

  it("colours each driver by team, falls back to neutral inks, and greys a tie", () => {
    expect(pairColours(COMPARISON)).toEqual({ a: "27F4D2", b: "#9fb4c8" });
    const bare = pairColours({ available: true, pending: false });
    expect(bare.a).not.toBe(bare.b);
    expect(winnerColour("even", bare)).toBe(EVEN_COLOUR);
    expect(winnerColour("a", bare)).toBe(bare.a);
    expect(winnerColour("b", bare)).toBe(bare.b);
  });
});
