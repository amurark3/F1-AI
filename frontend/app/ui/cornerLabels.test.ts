import { describe, expect, it } from "vitest";

import {
  LABEL_SEARCH,
  boxesOverlap,
  labelBox,
  placeCornerLabels,
  pointBoxDistance,
  pointSegmentDistance,
  segmentBoxDistance,
  segmentCrossesBox,
  trackClearance,
  type Box,
  type LabelSizing,
  type MapPoint,
} from "./cornerLabels";

/** Numbers 10 units tall, a track 6 wide, a 2-unit gap: a number must sit 5 clear of the centreline. */
const SIZING: LabelSizing = { fontSize: 10, trackHalfWidth: 3, gap: 2 };
const REQUIRED = SIZING.trackHalfWidth + SIZING.gap;

const SQUARE: MapPoint[] = [
  [0, 0],
  [200, 0],
  [200, 200],
  [0, 200],
];

/**
 * Three runs 16 apart, joined into one closed loop: (0,0)→(400,0), back along
 * y = 16, out along y = 32, back along y = 48 and up the left side. A number
 * 10 tall needs 20 between runs, so none fits between them.
 */
const SERPENTINE: MapPoint[] = [
  [0, 0],
  [400, 0],
  [400, 16],
  [40, 16],
  [40, 32],
  [400, 32],
  [400, 48],
  [0, 48],
];

const BOX: Box = { left: 0, top: 0, right: 10, bottom: 4 };

describe("distances", () => {
  it("measures a point to a segment: to its foot, either end, or a segment with no length", () => {
    expect(pointSegmentDistance([5, 3], [0, 0], [10, 0])).toBe(3);
    expect(pointSegmentDistance([-3, 4], [0, 0], [10, 0])).toBe(5);
    expect(pointSegmentDistance([13, 4], [0, 0], [10, 0])).toBe(5);
    expect(pointSegmentDistance([3, 4], [0, 0], [0, 0])).toBe(5);
  });

  it("measures a point to a box: nothing inside, straight to a side, or to a corner", () => {
    expect(pointBoxDistance([5, 2], BOX)).toBe(0);
    expect(pointBoxDistance([-3, 2], BOX)).toBe(3);
    expect(pointBoxDistance([5, 7], BOX)).toBe(3);
    expect(pointBoxDistance([13, 8], BOX)).toBe(5);
  });

  it("knows when a segment passes through a box", () => {
    expect(segmentCrossesBox([-5, 2], [15, 2], BOX)).toBe(true);
    expect(segmentCrossesBox([5, 2], [20, 20], BOX)).toBe(true);
    expect(segmentCrossesBox([5, -5], [5, 10], BOX)).toBe(true);
    // Parallel to the top edge, above it.
    expect(segmentCrossesBox([-5, -1], [15, -1], BOX)).toBe(false);
    // Its line crosses the box, the segment stops short.
    expect(segmentCrossesBox([-10, 2], [-5, 2], BOX)).toBe(false);
    // Passes the corner diagonally.
    expect(segmentCrossesBox([-5, 3], [3, 11], BOX)).toBe(false);
  });

  it("measures a segment to a box: zero through it, else the nearest end or box corner", () => {
    expect(segmentBoxDistance([-5, 2], [15, 2], BOX)).toBe(0);
    expect(segmentBoxDistance([-5, 7], [15, 7], BOX)).toBe(3);
    expect(segmentBoxDistance([13, 8], [20, 8], BOX)).toBe(5);
    expect(segmentBoxDistance([12, -10], [12, 20], BOX)).toBe(2);
  });

  it("measures the whole closed outline, the stretch back to the start included", () => {
    const nearTheClosingSide: Box = { left: 5, top: 40, right: 15, bottom: 60 };
    expect(trackClearance(nearTheClosingSide, SQUARE)).toBe(5);
  });

  it("calls two boxes overlapping when they come within the gap", () => {
    const left: Box = { left: 0, top: 0, right: 10, bottom: 10 };
    expect(boxesOverlap(left, { left: 12, top: 0, right: 20, bottom: 10 }, 1)).toBe(false);
    expect(boxesOverlap(left, { left: 12, top: 0, right: 20, bottom: 10 }, 3)).toBe(true);
    expect(boxesOverlap(left, { left: 0, top: 11, right: 10, bottom: 20 }, 0.5)).toBe(false);
    expect(boxesOverlap(left, { left: 0, top: 11, right: 10, bottom: 20 }, 2)).toBe(true);
  });

  it("sizes a number's box from its characters, centred on its spot", () => {
    // Two monospaced characters at 0.6 em, plus 0.2 em for the halo; one em tall.
    expect(labelBox("10", 20, [100, 50])).toEqual({ left: 86, top: 40, right: 114, bottom: 60 });
  });
});

describe("placeCornerLabels", () => {
  it("takes MultiViewer's direction when its spot clears the track", () => {
    const [label] = placeCornerLabels(SQUARE, [{ label: "4", x: 200, y: 100, angle: 0 }], SIZING);

    // Half the box (4) beyond the track's half-width and the gap (5).
    expect(label).toEqual({
      label: "4",
      x: 209,
      y: 100,
      box: { left: 205, top: 95, right: 213, bottom: 105 },
      clear: true,
      leader: null,
    });
  });

  it("starts from 0° when a corner comes without a direction", () => {
    const [label] = placeCornerLabels(SQUARE, [{ label: "4", x: 200, y: 100, angle: Number.NaN }], SIZING);

    expect([label.x, label.y, label.clear]).toEqual([209, 100, true]);
  });

  it("turns away from another stretch that MultiViewer's spot would sit on", () => {
    // Two runs 16 apart; MultiViewer points from the lower run (y = 16) at the upper.
    const hairpin: MapPoint[] = [
      [0, 0],
      [400, 0],
      [400, 16],
      [0, 16],
    ];
    const [label] = placeCornerLabels(hairpin, [{ label: "10", x: 200, y: 16, angle: 270 }], SIZING);

    expect(label.clear).toBe(true);
    expect(label.box.top).toBeGreaterThanOrEqual(16 + REQUIRED);
    expect(trackClearance(label.box, hairpin)).toBeGreaterThanOrEqual(REQUIRED);
    expect(label.leader).toBeNull();
  });

  it("steps outwards when nothing clears near the apex, with a leader back to it", () => {
    const [label] = placeCornerLabels(SERPENTINE, [{ label: "7", x: 200, y: 32, angle: 270 }], SIZING);

    expect(label.clear).toBe(true);
    // No room between the runs, so it goes past the outer one.
    expect(label.box.top).toBeGreaterThanOrEqual(48 + REQUIRED);
    expect(trackClearance(label.box, SERPENTINE)).toBeGreaterThanOrEqual(REQUIRED);
    const leader = label.leader;
    if (leader === null) throw new Error("expected a leader");
    // From the edge of the drawn track toward the number's centre, stopping half a gap short of its box.
    expect(Math.hypot(leader.x1 - 200, leader.y1 - 32)).toBeCloseTo(SIZING.trackHalfWidth);
    const towardCentre = (leader.x2 - 200) * (label.y - 32) - (leader.y2 - 32) * (label.x - 200);
    expect(towardCentre).toBeCloseTo(0);
    const short = pointBoxDistance([leader.x2, leader.y2], label.box);
    expect(short).toBeGreaterThan(0);
    expect(short).toBeLessThanOrEqual(SIZING.gap / 2);
  });

  it("keeps clear of the numbers already placed", () => {
    const [first, second] = placeCornerLabels(
      SQUARE,
      [
        { label: "1", x: 200, y: 100, angle: 0 },
        { label: "2", x: 200, y: 104, angle: 0 },
      ],
      SIZING,
    );

    expect(first.x).toBe(209);
    expect(boxesOverlap(first.box, second.box, SIZING.gap)).toBe(false);
    expect([first.clear, second.clear]).toEqual([true, true]);
  });

  it("stays inside the bounds it is given", () => {
    const bounds: Box = { left: 0, top: 0, right: 205, bottom: 300 };
    const [label] = placeCornerLabels(SQUARE, [{ label: "4", x: 200, y: 100, angle: 0 }], { ...SIZING, bounds });

    expect(label.clear).toBe(true);
    expect(label.box.right).toBeLessThanOrEqual(bounds.right);
    expect(trackClearance(label.box, SQUARE)).toBeGreaterThanOrEqual(REQUIRED);
  });

  it("takes the clearest spot, with a leader, when no spot is free", () => {
    const nowhere: Box = { left: 0, top: 0, right: 1, bottom: 1 };
    const [label] = placeCornerLabels(SQUARE, [{ label: "4", x: 200, y: 100, angle: 0 }], {
      ...SIZING,
      bounds: nowhere,
    });

    // Every spot is out of bounds; the farthest one out along MultiViewer's direction is clearest.
    const farthest = REQUIRED + 4 + (LABEL_SEARCH.rings - 1) * LABEL_SEARCH.ringStep * SIZING.fontSize;
    expect([label.x, label.y, label.clear]).toEqual([200 + farthest, 100, false]);
    expect(label.leader).not.toBeNull();
  });

  it("prefers a free spot that does not clear over a clearer one it may not use", () => {
    // The track's own box: everything past the outer runs is off limits. MultiViewer
    // points off the right-hand edge, so the first spot tried is not free either.
    const inside: Box = { left: 0, top: 0, right: 400, bottom: 48 };
    const [label] = placeCornerLabels(SERPENTINE, [{ label: "7", x: 395, y: 32, angle: 0 }], {
      ...SIZING,
      bounds: inside,
    });

    expect(label.clear).toBe(false);
    expect(label.box.top).toBeGreaterThanOrEqual(inside.top);
    expect(label.box.bottom).toBeLessThanOrEqual(inside.bottom);
    expect(label.box.right).toBeLessThanOrEqual(inside.right);
    // Between two runs rather than on one.
    expect(trackClearance(label.box, SERPENTINE)).toBeGreaterThan(0);
    expect(label.leader).not.toBeNull();
  });

  it("places the same numbers in the same spots every time", () => {
    const corners = [
      { label: "7", x: 200, y: 32, angle: 270 },
      { label: "8", x: 380, y: 32, angle: 0 },
    ];

    expect(placeCornerLabels(SERPENTINE, corners, SIZING)).toEqual(placeCornerLabels(SERPENTINE, corners, SIZING));
  });
});
