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
