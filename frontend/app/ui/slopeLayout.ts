/**
 * Geometry and wording for `SlopeChart`, kept apart from the markup so it is
 * tested directly. The numbers follow the grid → finish chart in
 * `docs/design/redesign/debrief.html`.
 */

/**
 * How the two ends are read.
 *
 * - `position`: a finishing order. Lower is better, so P1 sits at the top and
 *   every slot gets a row of its own. A change is places gained or lost.
 * - `value`: a quantity such as points. Higher is better and sits at the top.
 */
export type SlopeScale = "position" | "value";

/** Which way a change went, with "up the chart" always the better way. */
export type SlopeTrend = "gain" | "loss" | "even";

/** The chart's frame, in viewBox units (debrief.html's 600-wide figure). */
export const SLOPE = {
  width: 600,
  /** The start column's points; its labels end `labelGap` to the left. */
  xStart: 74,
  /** The end column's points; its labels start `labelGap` to the right. */
  xEnd: 486,
  labelGap: 10,
  /** Baseline of the column heads. */
  headY: 12,
  /** The first row, under the heads. */
  top: 34,
  /** One position slot; also the plot height per entity on the value scale. */
  rowGap: 29.5,
  bottom: 14,
  /** Closest two labels may sit: the 11-unit label type plus air. */
  labelMinGap: 14,
  /** From a point down to its label's baseline, so the text centres on the point. */
  baseline: 4,
  /** The value scale's shortest plot, in rows, so two entities still show a slope. */
  minValueRows: 6,
} as const;

export interface SlopeEnds {
  start: number;
  end: number;
}

/** One entity's points and the label baselines beside them (before `baseline`). */
export interface SlopeRow {
  y1: number;
  y2: number;
  labelY1: number;
  labelY2: number;
}

export interface SlopeGeometry {
  width: number;
  height: number;
  rows: SlopeRow[];
}

interface Placed {
  index: number;
  y: number;
}

/**
 * Moves labels apart until each pair is at least `minGap` apart, keeping the
 * order of their points. Crowded labels are pushed down first; any that would
 * run past `bounds[1]` are then pulled back up.
 */
export function spreadLabels(ys: readonly number[], minGap: number, bounds: readonly [number, number]): number[] {
  const order = ys.map((y, index) => ({ index, y })).sort((a, b) => a.y - b.y);
  const pushedDown = order.reduce<Placed[]>((placed, { index, y }) => {
    const above = placed.at(-1)?.y ?? Number.NEGATIVE_INFINITY;
    return [...placed, { index, y: Math.max(y, above + minGap) }];
  }, []);
  const pulledUp = pushedDown.reduceRight<Placed[]>((placed, { index, y }) => {
    const below = placed[0]?.y ?? bounds[1] + minGap;
    return [{ index, y: Math.min(y, below - minGap) }, ...placed];
  }, []);
  return [...pulledUp].sort((a, b) => a.index - b.index).map(({ y }) => y);
}

/** Maps a value to its height on the plot. */
function scaleY(values: readonly number[], scale: SlopeScale, plot: number): (value: number) => number {
  const low = Math.min(...values);
  const high = Math.max(...values);
  if (scale === "position") return (value) => SLOPE.top + (value - low) * SLOPE.rowGap;
  if (high === low) return () => SLOPE.top + plot / 2;
  return (value) => SLOPE.top + ((high - value) / (high - low)) * plot;
}

/**
 * Points and label baselines for each entity, and the height the chart needs.
 * On the position scale the plot has one row per slot from the best drawn to
 * the worst; on the value scale, one row per entity (at least
 * `minValueRows`).
 */
export function slopeLayout(pairs: readonly SlopeEnds[], scale: SlopeScale): SlopeGeometry {
  const values = pairs.flatMap(({ start, end }) => [start, end]);
  if (values.length === 0) return { width: SLOPE.width, height: SLOPE.top + SLOPE.bottom, rows: [] };

  const rowCount =
    scale === "position" ? Math.max(...values) - Math.min(...values) : Math.max(pairs.length - 1, SLOPE.minValueRows);
  const plot = rowCount * SLOPE.rowGap;
  const toY = scaleY(values, scale, plot);
  const y1s = pairs.map(({ start }) => toY(start));
  const y2s = pairs.map(({ end }) => toY(end));
  const bounds = [SLOPE.top, SLOPE.top + plot] as const;
  const labelY1s = spreadLabels(y1s, SLOPE.labelMinGap, bounds);
  const labelY2s = spreadLabels(y2s, SLOPE.labelMinGap, bounds);

  return {
    width: SLOPE.width,
    height: SLOPE.top + plot + SLOPE.bottom,
    rows: pairs.map((_, index) => ({
      y1: y1s[index],
      y2: y2s[index],
      labelY1: labelY1s[index],
      labelY2: labelY2s[index],
    })),
  };
}

/** The change from start to end, positive when the entity moved up the chart. */
export function slopeDelta(start: number, end: number, scale: SlopeScale): number {
  return scale === "position" ? start - end : end - start;
}

export function trendOf(delta: number): SlopeTrend {
  if (delta > 0) return "gain";
  if (delta < 0) return "loss";
  return "even";
}

const NUMBER = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });

/** An end's default text: "P7" on the position scale, "1,234.6" on the value scale. */
export function slopeValueText(value: number, scale: SlopeScale): string {
  return scale === "position" ? `P${value}` : NUMBER.format(value);
}

const SIGN: Record<SlopeTrend, string> = { gain: "+", loss: "−", even: "" };

/** A signed change, "+4", "−4" (a true minus sign) or "0", so its direction never rests on colour. */
export function deltaText(delta: number): string {
  return `${SIGN[trendOf(delta)]}${NUMBER.format(Math.abs(delta))}`;
}

/** The change in words for the chart's table: "gained 4 places", "down 2.5", "no change". */
export function spokenChange(delta: number, scale: SlopeScale): string {
  const trend = trendOf(delta);
  if (trend === "even") return "no change";
  const amount = NUMBER.format(Math.abs(delta));
  if (scale === "value") return `${trend === "gain" ? "up" : "down"} ${amount}`;
  const places = Math.abs(delta) === 1 ? "place" : "places";
  return `${trend === "gain" ? "gained" : "lost"} ${amount} ${places}`;
}
