/**
 * Bar lengths and entrance timing for `RankBars`, kept apart from the markup
 * so the arithmetic is tested directly.
 */

/** The delay between one row's entrance and the next, as the mockups stagger them. */
export const BAR_STAGGER_MS = 40;
/** Rows after this many enter together, so a 22-row list never waits a second to finish. */
export const MAX_STAGGERED_ROWS = 10;

/** Two decimals keep the inline widths short without a visible step. */
const roundPercent = (share: number) => Math.round(share * 10_000) / 100;

/**
 * Each value's bar as a percentage of the track, from zero.
 *
 * The scale runs from 0 to `max`, or to the largest value when no maximum is
 * given, so the leader fills the track. A value over the maximum fills it and
 * no more. Zero, a negative value and a missing figure draw no bar; the row's
 * text still says what the value is.
 */
export function barPercents(values: readonly number[], max?: number): number[] {
  const finite = values.filter((value) => Number.isFinite(value));
  const scaleMax = max ?? Math.max(0, ...finite);
  if (!Number.isFinite(scaleMax) || scaleMax <= 0) return values.map(() => 0);
  return values.map((value) => (Number.isFinite(value) && value > 0 ? roundPercent(Math.min(value / scaleMax, 1)) : 0));
}

/** When row `index` starts its entrance, in milliseconds. */
export function barStaggerMs(index: number): number {
  return Math.min(index, MAX_STAGGERED_ROWS) * BAR_STAGGER_MS;
}
