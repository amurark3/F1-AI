/**
 * The finding each head-to-head card states as its title. Every one is
 * computed from the comparison payload; when the data cannot support a claim
 * the title falls back to a neutral name.
 */

import type { TraceRow } from "./headToHeadModel";
import type { Stretch } from "./telemetryModel";

export interface Codes {
  a: string;
  b: string;
}

/** How far a window may look for the biggest swing in the gap. */
const DELTA_WINDOW_M = 1000;
/** A swing smaller than this (s) is noise, not a finding. */
const MIN_SWING_S = 0.005;
/** Throttle at or above this (%) counts as flat out. */
const FULL_THROTTLE = 98;

export function lapTitle(gap: number | undefined, codes: Codes): string {
  if (gap === undefined) return "Lap and sector times";
  const size = Math.abs(gap).toFixed(3);
  if (Number(size) === 0) return "Level on the line";
  return `${gap > 0 ? codes.a : codes.b} by ${size} s`;
}

export function mapTitle(stretches: Stretch[], codes: Codes): string {
  const a = stretches.filter((stretch) => stretch.faster === "a").length;
  const b = stretches.filter((stretch) => stretch.faster === "b").length;
  if (stretches.length === 0) return "Mini-sector map";
  if (a === b) return `The mini-sectors split ${a}–${b}`;
  const [code, won, other, lost] = a > b ? [codes.a, a, codes.b, b] : [codes.b, b, codes.a, a];
  return `${code} faster in ${won} of ${stretches.length} mini-sectors, ${other} in ${lost}`;
}

/** The biggest change in the gap over any 1 km: positive means A gained. */
export function deltaTitle(rows: TraceRow[], codes: Codes): string {
  let best = { change: 0, from: 0, to: 0 };
  rows.forEach((start) => {
    const end = rows.reduce((last, row) => (row.distance <= start.distance + DELTA_WINDOW_M ? row : last), start);
    const change = end.delta - start.delta;
    if (Math.abs(change) > Math.abs(best.change)) best = { change, from: start.distance, to: end.distance };
  });
  if (Math.abs(best.change) < MIN_SWING_S) return "Gap along the lap";
  const km = (metres: number) => (metres / 1000).toFixed(1);
  return `${best.change > 0 ? codes.a : codes.b} gains ${Math.abs(best.change).toFixed(2)} s between ${km(best.from)} and ${km(best.to)} km`;
}

/** Share of lap time (0-100) a driver spends where `test` holds; each sample lasts its step over speed. */
export function timeShare(rows: TraceRow[], side: "a" | "b", test: (row: TraceRow) => boolean): number | null {
  let total = 0;
  let inside = 0;
  rows.slice(0, -1).forEach((row, index) => {
    const seconds = (rows[index + 1].distance - row.distance) / Math.max(row[`speed_${side}`], 1);
    total += seconds;
    if (test(row)) inside += seconds;
  });
  return total > 0 ? (inside / total) * 100 : null;
}

interface ShareWords {
  test: (row: TraceRow, side: "a" | "b") => boolean;
  both: (share: number) => string;
  each: (code: string, share: number, other: number) => string;
  neutral: string;
}

/** "ANT 56% of the lap, RUS 52%", or one sentence when the two are level. */
function shareTitle(rows: TraceRow[], codes: Codes, words: ShareWords): string {
  const a = timeShare(rows, "a", (row) => words.test(row, "a"));
  const b = timeShare(rows, "b", (row) => words.test(row, "b"));
  if (a === null || b === null) return words.neutral;
  if (Math.round(a) === Math.round(b)) return words.both(Math.round(a));
  return a > b ? words.each(codes.a, Math.round(a), Math.round(b)) : words.each(codes.b, Math.round(b), Math.round(a));
}

export function speedTitle(rows: TraceRow[], codes: Codes): string {
  if (rows.length === 0) return "Speed trace";
  const a = Math.round(Math.max(...rows.map((row) => row.speed_a)));
  const b = Math.round(Math.max(...rows.map((row) => row.speed_b)));
  if (a === b) return `Both top out at ${a} km/h`;
  return a > b
    ? `Top speed ${a} km/h for ${codes.a}, ${b} for ${codes.b}`
    : `Top speed ${b} km/h for ${codes.b}, ${a} for ${codes.a}`;
}

export function throttleTitle(rows: TraceRow[], codes: Codes): string {
  return shareTitle(rows, codes, {
    test: (row, side) => row[`throttle_${side}`] >= FULL_THROTTLE,
    both: (share) => `Both flat out for ${share}% of the lap`,
    each: (code, share, other) => `${code} flat out for ${share}% of the lap, the other ${other}%`,
    neutral: "Throttle trace",
  });
}

export function brakeTitle(rows: TraceRow[], codes: Codes): string {
  return shareTitle(rows, codes, {
    test: (row, side) => row[`brake_${side}`] > 0,
    both: (share) => `Both on the brakes for ${share}% of the lap`,
    each: (code, share, other) => `${code} on the brakes for ${share}% of the lap, the other ${other}%`,
    neutral: "Brake trace",
  });
}

export function gearTitle(rows: TraceRow[], codes: Codes): string {
  if (rows.length === 0) return "Gear trace";
  const top = Math.max(...rows.map((row) => Math.max(row.gear_a, row.gear_b)));
  return shareTitle(rows, codes, {
    test: (row, side) => row[`gear_${side}`] === top,
    both: (share) => `Both in gear ${top} for ${share}% of the lap`,
    each: (code, share, other) => `${code} in gear ${top} for ${share}% of the lap, the other ${other}%`,
    neutral: "Gear trace",
  });
}
