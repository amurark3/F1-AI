import { describe, expect, it } from "vitest";

import { outlinePath, type CircuitMapData } from "./outlinePath";

const MAP: CircuitMapData = {
  source: "multiviewer",
  season: 2026,
  width: 100,
  height: 50,
  points: [
    [0, 0],
    [100, 0],
    [50, 50],
  ],
  corners: [],
};

describe("outlinePath", () => {
  it("moves to the first point, lines through the rest and closes the loop", () => {
    expect(outlinePath(MAP)).toBe("M0 0L100 0L50 50Z");
  });

  it("closes a single point on itself", () => {
    expect(outlinePath({ ...MAP, points: [[12.5, 7]] })).toBe("M12.5 7Z");
  });

  it("draws nothing for an outline without points", () => {
    expect(outlinePath({ ...MAP, points: [] })).toBe("");
  });
});
