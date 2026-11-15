/**
 * Shapes the comparison payload for the charts.
 *
 * Each driver keeps their team colour, the colour the reader already knows them
 * by. Driver B is also always dashed, so the pair stays apart when two
 * team-mates share a colour and for readers who can't tell the two colours
 * apart.
 */

import { rc } from "@/app/ui/tokens";

import { EVEN_COLOUR, stretchIndex } from "./trackMapGeometry";

import type { ComparisonResponse, Faster, LapListDriver, Stretch } from "./telemetryModel";

export const DASH_B = "6 4";

export interface TraceRow {
  distance: number;
  delta: number;
  speed_a: number;
  speed_b: number;
  throttle_a: number;
  throttle_b: number;
  brake_a: number;
  brake_b: number;
  gear_a: number;
  gear_b: number;
}

const CHANNELS = [
  "delta",
  "speed_a",
  "speed_b",
  "throttle_a",
  "throttle_b",
  "brake_a",
  "brake_b",
  "gear_a",
  "gear_b",
] as const;

/** Samples either side of a point that the delta's moving average reads. */
const SMOOTH_RADIUS = 4;

/**
 * The delta, smoothed with a moving average, then tilted by a straight line so
 * it starts at 0 and ends exactly on the official gap: smoothing must never
 * move the figure the title and the lap card quote.
 */
export function smoothDelta(values: number[], gap: number): number[] {
  const last = values.length - 1;
  if (last < 1) return values.map(() => gap);
  const averaged = values.map((_, index) => {
    const window = values.slice(Math.max(0, index - SMOOTH_RADIUS), index + SMOOTH_RADIUS + 1);
    return window.reduce((sum, value) => sum + value, 0) / window.length;
  });
  return averaged.map((value, index) => {
    const share = index / last;
    return value - averaged[0] * (1 - share) - (averaged[last] - gap) * share;
  });
}

/**
 * The columnar trace as one row per distance step, which is what recharts
 * reads. The delta is smoothed and pinned to `gap` (default: its own last value).
 */
export function traceRows(trace: Record<string, number[]> | undefined, gap?: number): TraceRow[] {
  const distance = trace?.distance ?? [];
  const raw = trace?.delta ?? [];
  const delta = smoothDelta(
    distance.map((_, index) => raw[index] ?? 0),
    gap ?? raw.at(-1) ?? 0,
  );
  return distance.map((value, index) => {
    const row = { distance: value } as TraceRow;
    for (const channel of CHANNELS) row[channel] = trace?.[channel]?.[index] ?? 0;
    row.delta = delta[index];
    return row;
  });
}

/** Drivers with a valid lap, the only ones a comparison can use. */
export function rankedDrivers(drivers: LapListDriver[] | undefined): LapListDriver[] {
  return (drivers ?? []).filter((driver) => driver.best !== null);
}

/** The pair shown: the URL's picks, else the two quickest. */
export function resolvePair(
  drivers: LapListDriver[],
  a: string | null,
  b: string | null,
): { first: string | null; second: string | null } {
  const first = a ?? drivers[0]?.code ?? null;
  return { first, second: b ?? drivers.find((driver) => driver.code !== first)?.code ?? null };
}

export interface PairColours {
  a: string;
  b: string;
}

export function pairColours(data: ComparisonResponse): PairColours {
  return { a: data.a?.driver.colour ?? rc.ink, b: data.b?.driver.colour ?? rc.ink2 };
}

/** Colour of the faster driver through a stretch; neutral when it was a tie. */
export function winnerColour(faster: Faster, colours: PairColours): string {
  if (faster === "even") return EVEN_COLOUR;
  return faster === "a" ? colours.a : colours.b;
}

/** For each map point, the mini-sector it sits in. */
export function miniSectorAt(stretches: Stretch[], distances: number[]): number[] {
  const starts = stretches.map((stretch) => stretch.start);
  return distances.map((distance) => stretchIndex(starts, distance));
}

/** "NOR +0.096s" — who gained, by how much. */
export function gainLabel(stretch: Stretch, codes: { a: string; b: string }): string {
  if (stretch.faster === "even") return "even";
  const code = stretch.faster === "a" ? codes.a : codes.b;
  return `${code} +${Math.abs(stretch.gain).toFixed(3)}s`;
}
