/**
 * A circuit outline, ready to draw: the shape `CircuitMap` takes, the SVG path
 * through it and where its corner numbers go. No React, so it reads the same
 * on the server and in the browser.
 */

import { placeCornerLabels, type LabelSizing, type PlacedCornerLabel } from "./cornerLabels";

/** A corner's apex and MultiViewer's direction for its number (degrees, in SVG axes). */
export interface CircuitCorner {
  label: string;
  x: number;
  y: number;
  angle: number;
}

/** The outline in SVG coordinates, already turned and scaled by the backend. */
export interface CircuitMapData {
  source: string;
  season: number;
  width: number;
  height: number;
  points: Array<[number, number]>;
  corners: CircuitCorner[];
}

/** The track's strokes in viewBox units, widest first: the red halo, the dark band, the line. */
export const CIRCUIT_TRACK = { halo: 28, band: 22, line: 5 } as const;

/** Corner numbers are this share of the map's longer side. */
const LABEL_SHARE = 1 / 42;
/** Space between a number and the track, or another number, in em. */
const LABEL_GAP_EM = 0.25;

/** An SVG path through the outline's points, closed back to the start. */
export function outlinePath(map: CircuitMapData): string {
  const [first, ...rest] = map.points;
  if (!first) return "";
  return `M${first[0]} ${first[1]}${rest.map(([x, y]) => `L${x} ${y}`).join("")}Z`;
}

/** The corner numbers' size and spacing on this map; they stay inside its viewBox. */
export function circuitLabelSizing(map: CircuitMapData): LabelSizing {
  const fontSize = Math.max(map.width, map.height) * LABEL_SHARE;
  return {
    fontSize,
    trackHalfWidth: CIRCUIT_TRACK.halo / 2,
    gap: fontSize * LABEL_GAP_EM,
    bounds: { left: 0, top: 0, right: map.width, bottom: map.height },
  };
}

/** Each corner's number, placed clear of the track and of the others. */
export function circuitCornerLabels(map: CircuitMapData): PlacedCornerLabel[] {
  return placeCornerLabels(map.points, map.corners, circuitLabelSizing(map));
}
