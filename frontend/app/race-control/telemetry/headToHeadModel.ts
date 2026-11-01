/**
 * Shapes the comparison payload for the charts.
 *
 * Each driver keeps their team colour, the colour the reader already knows them
 * by. Driver B is also always dashed, so the pair stays apart when two
 * team-mates share a colour and for readers who can't tell the two colours
 * apart.
 */

import { EVEN_COLOUR, stretchIndex } from "./trackMapGeometry";

import type { ComparisonResponse, Faster, Stretch } from "./telemetryModel";

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

/** The columnar trace as one row per distance step, which is what recharts reads. */
export function traceRows(trace: Record<string, number[]> | undefined): TraceRow[] {
  const distance = trace?.distance ?? [];
  return distance.map((value, index) => {
    const row = { distance: value } as TraceRow;
    for (const channel of CHANNELS) row[channel] = trace?.[channel]?.[index] ?? 0;
    return row;
  });
}

export interface PairColours {
  a: string;
  b: string;
}

export function pairColours(data: ComparisonResponse): PairColours {
  return { a: data.a?.driver.colour ?? "#3987E5", b: data.b?.driver.colour ?? "#D95926" };
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
