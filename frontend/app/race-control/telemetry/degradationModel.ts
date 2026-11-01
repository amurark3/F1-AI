/**
 * Shapes the tyre-degradation payload for its charts.
 *
 * Only `clean` laps were fitted. Every other lap is still drawn, hollow and
 * grey, with its reason in the tooltip, so the filtering is visible rather than
 * silent. The y range is set from the clean laps: a pit lap or a safety-car lap
 * is half a minute slower and would flatten every real difference.
 */

import type { DegradationLap, DegradationResponse, DegradationStint } from "./telemetryModel";

/** Laps that are not representative running and leave a gap in the pace line. */
const NOT_RACING = new Set(["lap1", "no_time", "pit_in", "pit_out", "red", "sc", "vsc", "restart"]);
const DEFAULT_DRIVER_COUNT = 5;
const Y_PADDING_BELOW = 0.4;
const Y_PADDING_ABOVE = 1.2;

export interface ScatterPoint {
  x: number;
  y: number;
  driver: string;
  lap: number;
  compound: string | null;
  status: string;
}

export function lapValue(lap: DegradationLap, corrected: boolean): number | null {
  return corrected ? lap.corrected : lap.time;
}

export function defaultDrivers(data: DegradationResponse): string[] {
  return (data.drivers ?? []).slice(0, DEFAULT_DRIVER_COUNT).map((driver) => driver.code);
}

function point(lap: DegradationLap, corrected: boolean): ScatterPoint | null {
  const y = lapValue(lap, corrected);
  if (lap.tyre_age === null || y === null) return null;
  return { x: lap.tyre_age, y, driver: lap.driver, lap: lap.lap, compound: lap.compound, status: lap.status };
}

/** Clean laps grouped by compound, and every other lap in one excluded group. */
export function scatterGroups(laps: DegradationLap[], drivers: Set<string>, corrected: boolean) {
  const clean = new Map<string, ScatterPoint[]>();
  const excluded: ScatterPoint[] = [];
  for (const lap of laps) {
    if (!drivers.has(lap.driver)) continue;
    const entry = point(lap, corrected);
    if (entry === null) continue;
    if (lap.status !== "clean") {
      excluded.push(entry);
      continue;
    }
    const key = lap.compound ?? "UNKNOWN";
    clean.set(key, [...(clean.get(key) ?? []), entry]);
  }
  return { clean, excluded };
}

/** A y range that fits the clean laps, with room above for the slower ones. */
export function yDomain(groups: Map<string, ScatterPoint[]>): [number, number] | null {
  const values = [...groups.values()].flat().map((entry) => entry.y);
  if (values.length === 0) return null;
  return [
    Math.floor((Math.min(...values) - Y_PADDING_BELOW) * 10) / 10,
    Math.ceil((Math.max(...values) + Y_PADDING_ABOVE) * 10) / 10,
  ];
}

export interface FitLine {
  key: string;
  compound: string;
  driver: string;
  stint: number;
  slope: number;
  points: [{ x: number; y: number }, { x: number; y: number }];
}

/** Each fitted stint's line, across the tyre ages its clean laps covered. */
export function fitLines(
  stints: DegradationStint[],
  laps: DegradationLap[],
  drivers: Set<string>,
  corrected: boolean,
): FitLine[] {
  const lines: FitLine[] = [];
  for (const stint of stints) {
    const fit = corrected ? stint.fit?.corrected : stint.fit?.raw;
    if (!fit || !drivers.has(stint.driver)) continue;
    const ages = laps
      .filter((lap) => lap.driver === stint.driver && lap.stint === stint.stint && lap.status === "clean")
      .map((lap) => lap.tyre_age ?? 0);
    const from = Math.min(...ages);
    const to = Math.max(...ages);
    lines.push({
      key: `${stint.driver}-${stint.stint}`,
      compound: stint.compound,
      driver: stint.driver,
      stint: stint.stint,
      slope: fit.slope,
      points: [
        { x: from, y: fit.slope * from + fit.intercept },
        { x: to, y: fit.slope * to + fit.intercept },
      ],
    });
  }
  return lines;
}

export type PaceRow = Record<string, number | null> & { lap: number };

/** Lap-by-lap times per driver, with gaps where the lap was not representative running. */
export function paceRows(laps: DegradationLap[], drivers: string[], corrected: boolean): PaceRow[] {
  const byLap = new Map<number, PaceRow>();
  for (const lap of laps) {
    if (!drivers.includes(lap.driver)) continue;
    const row = byLap.get(lap.lap) ?? { lap: lap.lap };
    row[lap.driver] = NOT_RACING.has(lap.status) ? null : lapValue(lap, corrected);
    byLap.set(lap.lap, row);
  }
  return [...byLap.values()].sort((left, right) => left.lap - right.lap);
}

/** The pace range across the plotted laps, without the slowest few that would squash it. */
export function paceDomain(rows: PaceRow[], drivers: string[]): [number, number] | null {
  const values = rows
    .flatMap((row) => drivers.map((driver) => row[driver]))
    .filter((value): value is number => typeof value === "number")
    .sort((left, right) => left - right);
  if (values.length === 0) return null;
  const high = values[Math.floor(values.length * 0.97)] ?? values[values.length - 1];
  return [Math.floor((values[0] - Y_PADDING_BELOW) * 10) / 10, Math.ceil((high + Y_PADDING_ABOVE) * 10) / 10];
}

/** "+0.045 s/lap". */
export function formatRate(slope: number | null | undefined): string {
  if (slope === null || slope === undefined) return "-";
  return `${slope >= 0 ? "+" : ""}${slope.toFixed(3)} s/lap`;
}
