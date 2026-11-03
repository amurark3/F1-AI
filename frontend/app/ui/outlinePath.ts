/**
 * A circuit outline, ready to draw: the shape `CircuitMap` takes and the SVG
 * path through it. No React, so it reads the same on the server and in the
 * browser.
 */

export interface CircuitCorner {
  label: string;
  x: number;
  y: number;
  label_x: number;
  label_y: number;
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

/** An SVG path through the outline's points, closed back to the start. */
export function outlinePath(map: CircuitMapData): string {
  const [first, ...rest] = map.points;
  if (!first) return "";
  return `M${first[0]} ${first[1]}${rest.map(([x, y]) => `L${x} ${y}`).join("")}Z`;
}
