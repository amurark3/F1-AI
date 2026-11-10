/**
 * Where each corner number sits on a circuit map: off the racing line, clear
 * of every stretch of track and of the other numbers.
 *
 * MultiViewer gives each corner an apex and a direction to push its number.
 * Where the track doubles back that spot can land on another stretch (at
 * Interlagos, T10 on the run to T14 and T15 on the T7–T8 section), so each
 * number tries MultiViewer's direction first, then turns 30° at a time either
 * side, then steps outwards, and takes the first spot whose box clears the
 * drawn track by its half-width plus a gap, stays inside the bounds and
 * touches no number already placed. When no spot does, it takes the clearest
 * free one (the clearest of all when none is free). A number far from its
 * apex, or one that could not clear, gets a leader line back to it.
 *
 * Pure geometry in the map's own units with y down (SVG). Deterministic: the
 * same outline and corners give the same spots, on the server and in the
 * browser.
 */

export type MapPoint = readonly [number, number];

export interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** A corner as the backend sends it: the apex and MultiViewer's direction. */
export interface CornerApex {
  label: string;
  x: number;
  y: number;
  /** Degrees from +x toward +y, in the map's own axes. */
  angle: number;
}

/** Sizes in the map's units. */
export interface LabelSizing {
  fontSize: number;
  /** Half the width of the drawn track, its widest stroke included. */
  trackHalfWidth: number;
  /** Space kept between a number and the track, and between two numbers. */
  gap: number;
  /** The area the numbers must stay inside (the viewBox), when the map has a fixed one. */
  bounds?: Box;
}

export interface Leader {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface PlacedCornerLabel {
  label: string;
  /** The number's centre. */
  x: number;
  y: number;
  box: Box;
  /** Whether the box clears the track and every other number. */
  clear: boolean;
  /** From the edge of the track at the apex to just short of the number. */
  leader: Leader | null;
}

export const LABEL_SEARCH = {
  /** Turns from MultiViewer's direction, in the order they are tried. */
  turns: [0, 30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180],
  /** Distances tried, each a step further out than the last. */
  rings: 8,
  /** One step, in em. */
  ringStep: 0.5,
} as const;

/** Geist Mono's advance per character, in em. */
const CHARACTER_EM = 0.6;
/** The number's halo stroke, in em; its box leaves room for it on both sides. */
export const LABEL_HALO_EM = 0.2;
/** A number further than this (em) beyond its closest possible spot gets a leader. */
const LEADER_AFTER_EM = 0.75;

/** The box a number covers, centred on `centre`. */
export function labelBox(label: string, fontSize: number, centre: MapPoint): Box {
  const halfWidth = ((label.length * CHARACTER_EM + LABEL_HALO_EM) * fontSize) / 2;
  const halfHeight = fontSize / 2;
  return {
    left: centre[0] - halfWidth,
    top: centre[1] - halfHeight,
    right: centre[0] + halfWidth,
    bottom: centre[1] + halfHeight,
  };
}

export function pointSegmentDistance(point: MapPoint, a: MapPoint, b: MapPoint): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSquared = dx * dx + dy * dy;
  const along = lengthSquared === 0 ? 0 : ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / lengthSquared;
  const t = Math.min(Math.max(along, 0), 1);
  return Math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dy));
}

export function pointBoxDistance(point: MapPoint, box: Box): number {
  const dx = Math.max(box.left - point[0], 0, point[0] - box.right);
  const dy = Math.max(box.top - point[1], 0, point[1] - box.bottom);
  return Math.hypot(dx, dy);
}

/** Whether the segment a→b passes through the box (Liang–Barsky clipping). */
export function segmentCrossesBox(a: MapPoint, b: MapPoint, box: Box): boolean {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const edges: Array<[number, number]> = [
    [-dx, a[0] - box.left],
    [dx, box.right - a[0]],
    [-dy, a[1] - box.top],
    [dy, box.bottom - a[1]],
  ];
  let enter = 0;
  let leave = 1;
  for (const [direction, room] of edges) {
    if (direction === 0) {
      // Parallel to this edge: outside it means outside the box.
      if (room < 0) return false;
    } else if (direction < 0) {
      enter = Math.max(enter, room / direction);
    } else {
      leave = Math.min(leave, room / direction);
    }
  }
  return enter <= leave;
}

/** Nearest distance between a segment and a box; zero when the segment passes through it. */
export function segmentBoxDistance(a: MapPoint, b: MapPoint, box: Box): number {
  if (segmentCrossesBox(a, b, box)) return 0;
  // Apart, two convex shapes are nearest at a vertex of one against the other.
  return Math.min(
    pointBoxDistance(a, box),
    pointBoxDistance(b, box),
    pointSegmentDistance([box.left, box.top], a, b),
    pointSegmentDistance([box.right, box.top], a, b),
    pointSegmentDistance([box.right, box.bottom], a, b),
    pointSegmentDistance([box.left, box.bottom], a, b),
  );
}

/** How far the box sits from the nearest stretch of the closed outline. */
export function trackClearance(box: Box, outline: readonly MapPoint[]): number {
  return outline.reduce(
    (nearest, point, index) => Math.min(nearest, segmentBoxDistance(point, outline[(index + 1) % outline.length], box)),
    Number.POSITIVE_INFINITY,
  );
}

/** Whether two boxes come within `gap` of each other. */
export function boxesOverlap(a: Box, b: Box, gap: number): boolean {
  return a.left < b.right + gap && b.left < a.right + gap && a.top < b.bottom + gap && b.top < a.bottom + gap;
}

function within(box: Box, bounds: Box | undefined): boolean {
  return (
    bounds === undefined ||
    (box.left >= bounds.left && box.top >= bounds.top && box.right <= bounds.right && box.bottom <= bounds.bottom)
  );
}

interface Spot {
  x: number;
  y: number;
  box: Box;
}

/**
 * Every spot to try, nearest ring first. A ring's distance is measured so the
 * box's near side sits `trackHalfWidth + gap` from the apex on ring 0.
 */
function candidateSpots(corner: CornerApex, sizing: LabelSizing): Spot[] {
  const start = Number.isFinite(corner.angle) ? corner.angle : 0;
  const half = labelBox(corner.label, sizing.fontSize, [0, 0]);
  const step = LABEL_SEARCH.ringStep * sizing.fontSize;
  return Array.from({ length: LABEL_SEARCH.rings }, (_, ring) => ring).flatMap((ring) =>
    LABEL_SEARCH.turns.map((turn) => {
      const radians = ((start + turn) * Math.PI) / 180;
      const cos = Math.cos(radians);
      const sin = Math.sin(radians);
      const reach = Math.abs(cos) * half.right + Math.abs(sin) * half.bottom;
      const distance = sizing.trackHalfWidth + sizing.gap + reach + ring * step;
      const centre: MapPoint = [corner.x + distance * cos, corner.y + distance * sin];
      return { x: centre[0], y: centre[1], box: labelBox(corner.label, sizing.fontSize, centre) };
    }),
  );
}

interface Scored {
  spot: Spot;
  free: boolean;
  clearance: number;
}

/** A free spot beats one that is not; between equals, the clearer; on a tie, the earlier. */
function better(best: Scored, next: Scored): Scored {
  if (next.free === best.free) return next.clearance > best.clearance ? next : best;
  return next.free ? next : best;
}

function leaderTo(corner: CornerApex, spot: Spot, sizing: LabelSizing): Leader {
  const reach = Math.hypot(spot.x - corner.x, spot.y - corner.y);
  const ux = (spot.x - corner.x) / reach;
  const uy = (spot.y - corner.y) / reach;
  // Where the line from the apex enters the box (a zero component never limits it).
  const halfWidth = (spot.box.right - spot.box.left) / 2;
  const halfHeight = (spot.box.bottom - spot.box.top) / 2;
  const inBox = Math.min(halfWidth / Math.abs(ux), halfHeight / Math.abs(uy));
  const end = reach - inBox - sizing.gap / 2;
  return {
    x1: corner.x + ux * sizing.trackHalfWidth,
    y1: corner.y + uy * sizing.trackHalfWidth,
    x2: corner.x + ux * end,
    y2: corner.y + uy * end,
  };
}

function placed(corner: CornerApex, spot: Spot, clear: boolean, sizing: LabelSizing): PlacedCornerLabel {
  const fromApex = pointBoxDistance([corner.x, corner.y], spot.box);
  const far = fromApex > sizing.trackHalfWidth + sizing.gap + LEADER_AFTER_EM * sizing.fontSize;
  return {
    label: corner.label,
    x: spot.x,
    y: spot.y,
    box: spot.box,
    clear,
    leader: clear && !far ? null : leaderTo(corner, spot, sizing),
  };
}

function placeOne(
  outline: readonly MapPoint[],
  corner: CornerApex,
  sizing: LabelSizing,
  taken: readonly PlacedCornerLabel[],
): PlacedCornerLabel {
  const required = sizing.trackHalfWidth + sizing.gap;
  const spots = candidateSpots(corner, sizing);
  const isFree = (spot: Spot) =>
    within(spot.box, sizing.bounds) && !taken.some((other) => boxesOverlap(spot.box, other.box, sizing.gap));
  const clear = spots.find((spot) => isFree(spot) && trackClearance(spot.box, outline) >= required);
  if (clear) return placed(corner, clear, true, sizing);
  const clearest = spots
    .map((spot): Scored => ({ spot, free: isFree(spot), clearance: trackClearance(spot.box, outline) }))
    .reduce(better);
  return placed(corner, clearest.spot, false, sizing);
}

/** Each corner's number placed in turn, so a later one keeps clear of those before it. */
export function placeCornerLabels(
  outline: readonly MapPoint[],
  corners: readonly CornerApex[],
  sizing: LabelSizing,
): PlacedCornerLabel[] {
  return corners.reduce<PlacedCornerLabel[]>(
    (taken, corner) => [...taken, placeOne(outline, corner, sizing, taken)],
    [],
  );
}
