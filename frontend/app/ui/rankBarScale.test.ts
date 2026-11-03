import { describe, expect, it } from "vitest";

import { BAR_STAGGER_MS, barPercents, barStaggerMs, MAX_STAGGERED_ROWS } from "./rankBarScale";

describe("barPercents", () => {
  it("scales each value against the largest, so the leader fills the track", () => {
    // Drivers' championship after R19 (standings.html): ANT, VER, HAM.
    expect(barPercents([380, 261, 259])).toEqual([100, 68.68, 68.16]);
  });

  it("scales against a caller's maximum, such as 100 for a share", () => {
    expect(barPercents([36, 27], 40)).toEqual([90, 67.5]);
  });

  it("caps a value over the maximum at a full track", () => {
    expect(barPercents([123, 109], 120)).toEqual([100, 90.83]);
  });

  it("draws no bar for zero, a negative value or a missing figure", () => {
    expect(barPercents([10, 0, -4, Number.NaN, Number.POSITIVE_INFINITY])).toEqual([100, 0, 0, 0, 0]);
  });

  it("draws no bars when there is no positive maximum to scale against", () => {
    expect(barPercents([0, 0])).toEqual([0, 0]);
    expect(barPercents([5, 3], 0)).toEqual([0, 0]);
    expect(barPercents([5, 3], Number.NaN)).toEqual([0, 0]);
    expect(barPercents([])).toEqual([]);
  });
});

describe("barStaggerMs", () => {
  it("starts each row a beat after the one above", () => {
    expect([0, 1, 2].map(barStaggerMs)).toEqual([0, BAR_STAGGER_MS, 2 * BAR_STAGGER_MS]);
  });

  it("stops staggering past the first rows, so a long list is not left waiting", () => {
    const last = MAX_STAGGERED_ROWS * BAR_STAGGER_MS;
    expect(barStaggerMs(MAX_STAGGERED_ROWS)).toBe(last);
    expect(barStaggerMs(21)).toBe(last);
  });
});
