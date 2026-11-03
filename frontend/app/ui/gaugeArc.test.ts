import { describe, expect, it } from "vitest";

import { GAUGE_PATH_LENGTH, gaugeDashOffset, gaugeReading, shareText } from "./gaugeArc";

describe("gaugeReading", () => {
  it("places the value on the range as a share, and fills the ring by that share", () => {
    // Model scorecard (gp-predictions.html): podium places right 62%.
    expect(gaugeReading(62, 0, 100)).toEqual({ share: 0.62, fill: 0.62, now: 62 });
  });

  it("reads a count against its own range", () => {
    expect(gaugeReading(7, 0, 19)?.fill).toBeCloseTo(7 / 19);
    expect(gaugeReading(15, 10, 20)).toEqual({ share: 0.5, fill: 0.5, now: 15 });
  });

  it("keeps the true share but fills no further than the ends of the ring", () => {
    expect(gaugeReading(105, 0, 100)).toEqual({ share: 1.05, fill: 1, now: 100 });
    expect(gaugeReading(-5, 0, 100)).toEqual({ share: -0.05, fill: 0, now: 0 });
  });

  it("has no reading for a missing value or a range with no width", () => {
    expect(gaugeReading(null, 0, 100)).toBeNull();
    expect(gaugeReading(Number.NaN, 0, 100)).toBeNull();
    expect(gaugeReading(50, 100, 100)).toBeNull();
    expect(gaugeReading(50, 100, 0)).toBeNull();
    expect(gaugeReading(50, 0, Number.POSITIVE_INFINITY)).toBeNull();
    expect(gaugeReading(50, Number.NaN, 100)).toBeNull();
  });
});

describe("gaugeDashOffset", () => {
  it("leaves the filled share of the ring's path length showing", () => {
    expect(gaugeDashOffset(0.5)).toBe(GAUGE_PATH_LENGTH / 2);
    expect(gaugeDashOffset(1)).toBe(0);
    expect(gaugeDashOffset(0)).toBe(GAUGE_PATH_LENGTH);
  });
});

describe("shareText", () => {
  it("reads a share as a whole percentage", () => {
    expect(shareText(0.5)).toBe("50%");
    expect(shareText(0.786)).toBe("79%");
    expect(shareText(1.05)).toBe("105%");
  });
});
