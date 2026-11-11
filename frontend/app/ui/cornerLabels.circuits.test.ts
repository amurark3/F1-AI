/**
 * Corner numbers over real layouts: MultiViewer's outlines and corners for six
 * circuits where the track doubles back or crosses itself (Suzuka), drawn as
 * the circuit segment serves them (`test/fixtures/circuit-maps.json`).
 */
import { describe, expect, it } from "vitest";

import { CIRCUIT_MAPS_2026 } from "@/test/fixtures";

import {
  boxesOverlap,
  labelBox,
  placeCornerLabels,
  trackClearance,
  type Box,
  type LabelSizing,
  type PlacedCornerLabel,
} from "./cornerLabels";
import { CIRCUIT_TRACK, circuitCornerLabels, circuitLabelSizing, type CircuitMapData } from "./outlinePath";

const CIRCUITS = Object.entries(CIRCUIT_MAPS_2026);

/** The speed map's proportions: a line 1/140 of the map, numbers 1/45. */
function speedMapSizing(map: CircuitMapData): LabelSizing {
  const span = Math.max(map.width, map.height);
  return { fontSize: span / 45, trackHalfWidth: span / 280, gap: span / 180 };
}

function inside(box: Box, bounds: Box): boolean {
  return box.left >= bounds.left && box.top >= bounds.top && box.right <= bounds.right && box.bottom <= bounds.bottom;
}

function expectClearOfTrackAndEachOther(labels: PlacedCornerLabel[], map: CircuitMapData, sizing: LabelSizing) {
  const required = sizing.trackHalfWidth + sizing.gap;
  expect(labels.map((label) => label.label)).toEqual(map.corners.map((corner) => corner.label));
  for (const label of labels) {
    expect(label.clear, `T${label.label}`).toBe(true);
    expect(trackClearance(label.box, map.points), `T${label.label}`).toBeGreaterThanOrEqual(required);
  }
  labels.forEach((label, index) => {
    for (const other of labels.slice(index + 1)) {
      expect(boxesOverlap(label.box, other.box, sizing.gap), `T${label.label} and T${other.label}`).toBe(false);
    }
  });
}

describe.each(CIRCUITS)("corner numbers at %s", (_name, map) => {
  it("clear the Command Center map's track and every other number, inside its viewBox", () => {
    const sizing = circuitLabelSizing(map);
    const labels = circuitCornerLabels(map);

    expect(sizing.trackHalfWidth).toBe(CIRCUIT_TRACK.halo / 2);
    expectClearOfTrackAndEachOther(labels, map, sizing);
    for (const label of labels)
      expect(inside(label.box, { left: 0, top: 0, right: map.width, bottom: map.height })).toBe(true);
  });

  it("clear the speed map's thinner line too", () => {
    const sizing = speedMapSizing(map);

    expectClearOfTrackAndEachOther(placeCornerLabels(map.points, map.corners, sizing), map, sizing);
  });

  it("land in the same spots every time", () => {
    expect(circuitCornerLabels(map)).toEqual(circuitCornerLabels(map));
  });
});

describe("Interlagos", () => {
  const map = CIRCUIT_MAPS_2026.interlagos;
  const sizing = circuitLabelSizing(map);
  const required = sizing.trackHalfWidth + sizing.gap;
  const labels = circuitCornerLabels(map);

  // Where the map drew them before: a fixed 43 units along MultiViewer's angle.
  it.each([
    ["10", "the run to T14", [876.3, 200.1]],
    ["15", "the T7–T8 section", [581.2, 109.5]],
  ] as const)("moves T%s off %s, where it used to sit", (number, _stretch, before) => {
    expect(trackClearance(labelBox(number, sizing.fontSize, before), map.points)).toBeLessThan(required);

    const placed = labels.find((label) => label.label === number);
    if (placed === undefined) throw new Error(`T${number} was not placed`);
    expect(placed.clear).toBe(true);
    expect(trackClearance(placed.box, map.points)).toBeGreaterThanOrEqual(required);
  });
});
