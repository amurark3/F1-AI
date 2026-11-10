/**
 * Pure geometry and colour for the track map.
 *
 * Positions arrive in OpenF1's frame (decimetres, y up), already turned to the
 * familiar map orientation by the backend. SVG's y runs down, so y is negated
 * here and nowhere else.
 *
 * Speed is a magnitude, so it takes one hue stepped light to dark (blue), never
 * a rainbow. On this dark surface the ramp's anchor flips: slow is the deep
 * end, which recedes toward the background, and fast is the pale end, which
 * stands out — the eye goes to the straights first.
 */

import { placeCornerLabels, type MapPoint, type PlacedCornerLabel } from "@/app/ui/cornerLabels";

import type { CornerMarker } from "./telemetryModel";

/** Blue ramp, deep to pale (steps 550 → 100 of the reference sequential scale). */
export const SPEED_RAMP = ["#1C5CAB", "#2A78D6", "#5598E7", "#86B6EF", "#CDE2FB"];

/** Neutral for a mini-sector neither driver won. */
export const EVEN_COLOUR = "#596173";

export interface ViewBox {
  minX: number;
  minY: number;
  width: number;
  height: number;
}

/** A bounding box around every point (in SVG space, y flipped) with a margin. */
export function fitView(xs: number[], ys: number[], marginShare = 0.06): ViewBox {
  if (xs.length === 0) return { minX: 0, minY: 0, width: 1, height: 1 };
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys.map((y) => -y));
  const maxY = Math.max(...ys.map((y) => -y));
  const margin = Math.max(maxX - minX, maxY - minY) * marginShare;
  return {
    minX: minX - margin,
    minY: minY - margin,
    width: maxX - minX + 2 * margin || 1,
    height: maxY - minY + 2 * margin || 1,
  };
}

export function viewBoxString(view: ViewBox): string {
  return `${view.minX} ${view.minY} ${view.width} ${view.height}`;
}

/** The line's width and the corner numbers' size, as shares of the lap's longer side. */
const STROKE_SHARE = 1 / 140;
const LABEL_SHARE = 1 / 45;

export interface TrackLayout {
  view: ViewBox;
  stroke: number;
  fontSize: number;
  /** In SVG space, y already flipped. */
  labels: PlacedCornerLabel[];
}

/**
 * The lap's frame, line width and corner numbers. Sizes come from the lap
 * alone; the frame then grows to take in the numbers, each placed clear of the
 * line. A corner's apex and direction arrive y-up like the lap, so both are
 * mirrored into SVG space here.
 */
export function trackLayout(xs: number[], ys: number[], corners: CornerMarker[]): TrackLayout {
  const lap = fitView(xs, ys);
  const scale = Math.max(lap.width, lap.height);
  const stroke = scale * STROKE_SHARE;
  const fontSize = scale * LABEL_SHARE;
  const outline = xs.map((x, index): MapPoint => [x, -ys[index]]);
  const apexes = corners.map((corner) => ({ label: corner.label, x: corner.x, y: -corner.y, angle: -corner.angle }));
  const labels = placeCornerLabels(outline, apexes, { fontSize, trackHalfWidth: stroke / 2, gap: fontSize / 4 });
  const view = fitView(
    [...xs, ...labels.flatMap((label) => [label.box.left, label.box.right])],
    [...ys, ...labels.flatMap((label) => [-label.box.top, -label.box.bottom])],
  );
  return { view, stroke, fontSize, labels };
}

function hexToRgb(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function rgbToHex(rgb: [number, number, number]): string {
  return `#${rgb.map((channel) => Math.round(channel).toString(16).padStart(2, "0")).join("")}`;
}

/** The ramp colour at `share` (0 = slowest, 1 = fastest), blended between steps. */
export function rampColour(share: number, ramp: string[] = SPEED_RAMP): string {
  const clamped = Math.min(Math.max(share, 0), 1);
  const position = clamped * (ramp.length - 1);
  const low = Math.floor(position);
  const high = Math.min(low + 1, ramp.length - 1);
  const mix = position - low;
  const from = hexToRgb(ramp[low]);
  const to = hexToRgb(ramp[high]);
  return rgbToHex([0, 1, 2].map((i) => from[i] + (to[i] - from[i]) * mix) as [number, number, number]);
}

export interface SpeedScale {
  min: number;
  max: number;
  colour: (speed: number) => string;
}

export function speedScale(speeds: number[]): SpeedScale {
  const min = speeds.length ? Math.min(...speeds) : 0;
  const max = speeds.length ? Math.max(...speeds) : 1;
  const span = max - min || 1;
  return { min, max, colour: (speed) => rampColour((speed - min) / span) };
}

/** Index of the point nearest an SVG-space position (y already flipped). */
export function nearestIndex(xs: number[], ys: number[], target: { x: number; y: number }): number {
  let best = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < xs.length; index += 1) {
    const distance = (xs[index] - target.x) ** 2 + (-ys[index] - target.y) ** 2;
    if (distance < bestDistance) {
      best = index;
      bestDistance = distance;
    }
  }
  return best;
}

/** Which of `edges` (ascending stretch starts) a distance falls in. */
export function stretchIndex(starts: number[], distance: number): number {
  let index = 0;
  while (index + 1 < starts.length && distance >= starts[index + 1]) index += 1;
  return index;
}
