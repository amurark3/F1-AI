/**
 * Qualifying segments (Q1-Q3, SQ1-SQ3) in the Telemetry Lab: which part is
 * shown, how drivers and laps group under it, and why a driver has no time.
 * Everything here reads the lap list's `segments` block and each driver's
 * `segment_*` fields; a session without them stays ungrouped.
 */

import type { LapListDriver, LapListResponse, SegmentGroup, TimedLap } from "./telemetryModel";

export interface SegmentChoice {
  labels: string[];
  /** 1-based: 1 is Q1. */
  segment: number;
}

export interface DriverGroup {
  key: SegmentGroup | "ungrouped";
  heading: string | null;
  drivers: LapListDriver[];
}

const GROUP_ORDER: SegmentGroup[] = ["q3", "out_q2", "out_q1", "disqualified"];

/** The best time in the part, or the whole session's best when no part is chosen. */
export function segmentBest(driver: LapListDriver, segment: number | null): number | null {
  return segment === null ? driver.best : (driver.segment_bests?.[segment - 1] ?? null);
}

/** The drivers with a time in the part (the session when null), quickest first. */
export function quickest(drivers: LapListDriver[], segment: number | null): LapListDriver[] {
  return drivers
    .flatMap((driver) => {
      const best = segmentBest(driver, segment);
      return best === null ? [] : [{ driver, best }];
    })
    .sort((x, y) => x.best - y.best)
    .map((entry) => entry.driver);
}

/**
 * The part on show: the URL's, else the last one every named driver reached
 * (the last part when none is named). Null outside qualifying or when the
 * parts are not published.
 */
export function resolveSegment(
  response: LapListResponse | undefined,
  codes: Array<string | null>,
  asked: number | null,
): SegmentChoice | null {
  const info = response?.segments;
  if (!info?.available) return null;
  const last = info.labels.length;
  if (asked !== null) return { labels: info.labels, segment: Math.min(asked, last) };
  const reached = (response?.drivers ?? [])
    .filter((driver) => codes.includes(driver.code))
    .map((driver) => driver.segment_reached ?? last);
  return { labels: info.labels, segment: Math.min(last, ...reached) };
}

/** Why a driver has no time in the part. */
export function noTimeReason(driver: LapListDriver, choice: SegmentChoice): string {
  const label = choice.labels[choice.segment - 1];
  return choice.segment > (driver.segment_reached ?? choice.labels.length)
    ? `didn't reach ${label}`
    : `no time set in ${label}`;
}

function groupHeading(group: SegmentGroup, labels: string[]): string {
  if (group === "q3") return labels[2];
  if (group === "out_q2") return `Out in ${labels[1]}`;
  if (group === "out_q1") return `Out in ${labels[0]}`;
  return "Disqualified";
}

/** Drivers under Q3 / Out in Q2 / Out in Q1 / Disqualified, quickest in the part first; one flat group without parts. */
export function groupDrivers(drivers: LapListDriver[], choice: SegmentChoice | null): DriverGroup[] {
  if (choice === null) return [{ key: "ungrouped", heading: null, drivers }];
  const quickest = (list: LapListDriver[]) =>
    [...list].sort(
      (x, y) =>
        (segmentBest(x, choice.segment) ?? Infinity) - (segmentBest(y, choice.segment) ?? Infinity) ||
        x.code.localeCompare(y.code),
    );
  const grouped = GROUP_ORDER.map((key) => ({
    key,
    heading: groupHeading(key, choice.labels),
    drivers: quickest(drivers.filter((driver) => driver.group === key)),
  })).filter((group) => group.drivers.length > 0);
  const rest = drivers.filter((driver) => driver.group === undefined);
  return rest.length > 0 ? [...grouped, { key: "ungrouped", heading: null, drivers: rest }] : grouped;
}

/** Laps under Q1 / Q2 / Q3 headings, then any outside the windows; one flat group without parts. */
export function groupLaps(
  laps: TimedLap[],
  labels: string[] | null,
): Array<{ heading: string | null; laps: TimedLap[] }> {
  if (labels === null) return [{ heading: null, laps }];
  const parts = labels.map((heading, index) => ({ heading, laps: laps.filter((lap) => lap.segment === index + 1) }));
  const outside = laps.filter((lap) => !lap.segment || lap.segment > labels.length);
  return [...parts, { heading: "Outside the parts", laps: outside }].filter((group) => group.laps.length > 0);
}

/** The part a title names: the chosen lap's own part, else the one on show. */
export function titleSegment(
  drivers: LapListDriver[],
  code: string | null,
  lap: number | null,
  choice: SegmentChoice | null,
): string | null {
  if (choice === null) return null;
  const own = drivers.find((driver) => driver.code === code)?.laps.find((entry) => entry.number === lap)?.segment;
  return choice.labels[(own ?? choice.segment) - 1];
}
