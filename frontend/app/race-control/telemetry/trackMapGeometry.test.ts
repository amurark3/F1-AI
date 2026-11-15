import { describe, expect, it } from "vitest";

import {
  fitView,
  nearestIndex,
  rampColour,
  speedScale,
  SPEED_RAMP,
  stretchIndex,
  trackLayout,
  viewBoxString,
} from "./trackMapGeometry";

describe("fitView", () => {
  it("frames the points with a margin, y flipped for SVG", () => {
    const view = fitView([0, 100], [0, 50], 0.1);
    expect(view).toEqual({ minX: -10, minY: -60, width: 120, height: 70 });
    expect(viewBoxString(view)).toBe("-10 -60 120 70");
  });

  it("falls back to a unit box with no points, and never a zero-size one", () => {
    expect(fitView([], [])).toEqual({ minX: 0, minY: 0, width: 1, height: 1 });
    expect(fitView([5], [5])).toMatchObject({ width: 1, height: 1 });
  });
});

describe("trackLayout", () => {
  it("sizes the line from the lap and grows the frame to hold the corner numbers", () => {
    const xs = [0, 1000, 1000, 0];
    const ys = [0, 0, 800, 800];
    const bare = trackLayout(xs, ys, []);
    const numbered = trackLayout(xs, ys, [{ number: 1, label: "1", x: 1000, y: 0, angle: 45 }]);
    expect(bare.labels).toEqual([]);
    expect(numbered.labels).toHaveLength(1);
    expect(numbered.stroke).toBe(bare.stroke);
    expect(numbered.view.width * numbered.view.height).toBeGreaterThanOrEqual(bare.view.width * bare.view.height);
  });
});

describe("rampColour", () => {
  it("hits the ends and blends between steps", () => {
    expect(rampColour(0).toLowerCase()).toBe(SPEED_RAMP[0].toLowerCase());
    expect(rampColour(1).toLowerCase()).toBe(SPEED_RAMP[4].toLowerCase());
    expect(rampColour(0.125)).toBe("#236ac1");
  });

  it("clamps a share outside 0 to 1", () => {
    expect(rampColour(-3)).toBe(rampColour(0));
    expect(rampColour(7)).toBe(rampColour(1));
  });
});

describe("speedScale", () => {
  it("maps the slowest to the deep end and the fastest to the pale end", () => {
    const scale = speedScale([90, 200, 320]);
    expect([scale.min, scale.max]).toEqual([90, 320]);
    expect(scale.colour(90)).toBe(rampColour(0));
    expect(scale.colour(320)).toBe(rampColour(1));
  });

  it("copes with no speeds and with a single one", () => {
    expect(speedScale([])).toMatchObject({ min: 0, max: 1 });
    expect(speedScale([100]).colour(100)).toBe(rampColour(0));
  });
});

describe("nearestIndex", () => {
  it("finds the point closest to an SVG-space position (y flipped)", () => {
    expect(nearestIndex([0, 10, 20], [0, -5, -10], { x: 19, y: 9 })).toBe(2);
    expect(nearestIndex([0, 10, 20], [0, -5, -10], { x: 1, y: 0 })).toBe(0);
  });
});

describe("stretchIndex", () => {
  it("picks the stretch a distance falls in", () => {
    const starts = [0, 100, 250];
    expect(stretchIndex(starts, 0)).toBe(0);
    expect(stretchIndex(starts, 100)).toBe(1);
    expect(stretchIndex(starts, 999)).toBe(2);
  });
});
