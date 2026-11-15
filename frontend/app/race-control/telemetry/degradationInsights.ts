/**
 * The finding each tyre-wear card states as its title, and the rows behind
 * the wear and stint-length cards. Every title is computed from the
 * degradation payload; when the data cannot support a claim it falls back to
 * a neutral name.
 */

import { compoundLabel } from "../grand-prix/tyreCompounds";

import { lapValue, type FitLine } from "./degradationModel";

import type { DegradationLap, DegradationResponse, DegradationStint } from "./telemetryModel";

/** A slope smaller than this (s per lap of tyre age) is noise, not a trend. */
const MIN_SLOPE_S = 0.005;
/** A final stint needs this many clean laps before its pace is compared. */
const MIN_FINAL_STINT_LAPS = 3;

export interface WearRow {
  id: string;
  code: string;
  name: string;
  compound: string;
  laps: number;
  rate: number;
  raw: number;
}

export interface LengthRow {
  code: string;
  name: string;
  stints: Array<{ stint: number; compound: string; from: number; to: number; laps: number }>;
}

export function scatterTitle(fits: FitLine[]): string {
  if (fits.length === 0) return "Lap time against tyre age";
  const slopes = fits.map((fit) => fit.slope).sort((left, right) => left - right);
  const middle = slopes.length >> 1;
  const median = slopes.length % 2 === 1 ? slopes[middle] : (slopes[middle - 1] + slopes[middle]) / 2;
  if (Math.abs(median) < MIN_SLOPE_S) return "Lap times barely changed with tyre age";
  return `Lap times ${median > 0 ? "rose" : "fell"} about ${Math.abs(median).toFixed(2)} s per lap of tyre age`;
}

/** The driver whose final stint had the lowest average clean lap, among those with enough laps. */
export function paceTitle(laps: DegradationLap[], drivers: string[], corrected: boolean): string {
  const averages = drivers.flatMap((driver) => {
    const own = laps.filter(
      (lap): lap is DegradationLap & { stint: number } => lap.driver === driver && lap.stint !== null,
    );
    const last = Math.max(...own.map((lap) => lap.stint));
    const times = own
      .filter((lap) => lap.stint === last && lap.status === "clean")
      .map((lap) => lapValue(lap, corrected))
      .filter((time): time is number => time !== null);
    return times.length < MIN_FINAL_STINT_LAPS
      ? []
      : [{ driver, mean: times.reduce((sum, time) => sum + time, 0) / times.length }];
  });
  const [best, next] = averages.sort((left, right) => left.mean - right.mean);
  if (next === undefined || best.mean === next.mean) return "Race pace";
  return `${best.driver} had the quickest final stint`;
}

/** Fitted stints of the chosen drivers, steepest wear first. */
export function wearRows(data: DegradationResponse, chosen: Set<string>, corrected: boolean): WearRow[] {
  const names = new Map((data.drivers ?? []).map((driver) => [driver.code, driver.name]));
  const rows: WearRow[] = [];
  for (const stint of data.stints ?? []) {
    const fit = stint.fit;
    const line = corrected ? fit?.corrected : fit?.raw;
    if (!fit || !line || !chosen.has(stint.driver)) continue;
    rows.push({
      id: `${stint.driver}-${stint.stint}`,
      code: stint.driver,
      name: names.get(stint.driver) ?? stint.driver,
      compound: stint.compound,
      laps: stint.end_lap - stint.start_lap + 1,
      rate: line.slope,
      raw: fit.raw.slope,
    });
  }
  return rows.sort((left, right) => right.rate - left.rate);
}

export function wearTitle(rows: WearRow[]): string {
  const top = rows.at(0);
  if (top === undefined || top.rate < MIN_SLOPE_S) return "Wear rate by stint";
  return `${top.code}'s ${compoundLabel(top.compound).toLowerCase()} stint wore fastest`;
}

export function lengthRows(data: DegradationResponse, chosen: Set<string>): LengthRow[] {
  return (data.drivers ?? [])
    .filter((driver) => chosen.has(driver.code))
    .map((driver) => ({
      code: driver.code,
      name: driver.name,
      stints: (data.stints ?? [])
        .filter((stint: DegradationStint) => stint.driver === driver.code)
        .sort((left, right) => left.stint - right.stint)
        .map((stint) => ({
          stint: stint.stint,
          compound: stint.compound,
          from: stint.start_lap,
          to: stint.end_lap,
          laps: stint.end_lap - stint.start_lap + 1,
        })),
    }))
    .filter((row) => row.stints.length > 0);
}

function stops(count: number): string {
  if (count === 0) return "did not stop";
  if (count === 1) return "stopped once";
  return count === 2 ? "stopped twice" : `stopped ${count} times`;
}

function list(codes: string[]): string {
  return codes.length < 2 ? codes.join("") : `${codes.slice(0, -1).join(", ")} and ${codes[codes.length - 1]}`;
}

/** "ANT and NOR stopped once; LEC and VER stopped twice". */
export function lengthsTitle(rows: LengthRow[]): string {
  if (rows.length === 0) return "Stint lengths";
  const groups = new Map<number, string[]>();
  for (const row of rows) {
    const count = row.stints.length - 1;
    groups.set(count, [...(groups.get(count) ?? []), row.code]);
  }
  return [...groups.entries()]
    .sort(([left], [right]) => left - right)
    .map(([count, codes]) => `${list(codes)} ${stops(count)}`)
    .join("; ");
}
