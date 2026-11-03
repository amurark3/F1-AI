/**
 * The arithmetic behind `Gauge`: where a value sits on its range, and how
 * much of the ring that fills.
 */

/** The ring's `pathLength`, so the dash offset reads as a percentage of the ring. */
export const GAUGE_PATH_LENGTH = 100;

export interface GaugeReading {
  /** Where the value sits on the range: 0 at `min`, 1 at `max`, beyond either end when the value is. */
  share: number;
  /** The part of the ring to fill: the share held to 0–1. */
  fill: number;
  /** The value held to the range, for `aria-valuenow`, which must not leave it. */
  now: number;
}

const clamp = (value: number, low: number, high: number) => Math.min(Math.max(value, low), high);

/**
 * The value against its range, or `null` when there is nothing honest to
 * draw: no value, or a range without width. A missing value never reads as
 * an empty ring, which would look like a real zero.
 */
export function gaugeReading(value: number | null, min: number, max: number): GaugeReading | null {
  if (value === null || !Number.isFinite(value) || !Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
    return null;
  }
  const share = (value - min) / (max - min);
  return { share, fill: clamp(share, 0, 1), now: clamp(value, min, max) };
}

/**
 * The ring's `stroke-dashoffset` for a fill share. The ring's dash array is
 * one full dash and one full gap, so an offset of the whole path length shows
 * nothing, which is where the shared `gauge-fill` entrance starts.
 */
export function gaugeDashOffset(fill: number): number {
  return GAUGE_PATH_LENGTH * (1 - fill);
}

/** A share as the whole percentage written in the ring: 0.786 → "79%". */
export function shareText(share: number): string {
  return `${Math.round(share * 100)}%`;
}
