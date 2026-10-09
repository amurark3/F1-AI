/**
 * How a season's calendar is broken into the rows of the round selector.
 *
 * A single wrapping row of 24 tiles wraps wherever the panel happens to end,
 * which puts the break in a different place at every window width and means
 * nothing about the season. Splitting the calendar at its own shutdown — the
 * three-plus week gap in August — gives two rows that are the same at any
 * width and that a reader already has a name for.
 */

import { raceSessionTime } from "./predictionHelpers";

import type { RaceEvent } from "./predictionModel";

/** One row of the selector: a run of consecutive rounds under a caption. */
export interface SeasonSegment {
  key: string;
  /** Row caption, empty when the whole calendar fits one unlabelled row. */
  label: string;
  races: RaceEvent[];
}

/** Calendars this short read fine as one row, uncaptioned. */
const SINGLE_ROW_MAX = 12;

/** A gap at least this long between rounds is a shutdown, not a fortnight off. */
const BREAK_GAP_DAYS = 21;

/** Keep both rows substantial: never split within this many rounds of an end. */
const MIN_SEGMENT_RACES = 4;

const DAY_MS = 86_400_000;

/** Month index of August, the FIA's mandated shutdown month. */
const AUGUST = 7;

/** When a round runs, from its race session, or null if the date is unusable. */
function raceTime(race: RaceEvent): number | null {
  const value = raceSessionTime(race);
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

interface CalendarGap {
  /** Index of the first race after the gap. */
  index: number;
  days: number;
  from: number;
  to: number;
}

/** The longest shutdown-length gap that leaves a substantial row either side. */
function longestBreak(schedule: readonly RaceEvent[]): CalendarGap | null {
  let longest: CalendarGap | null = null;
  for (let index = MIN_SEGMENT_RACES; index <= schedule.length - MIN_SEGMENT_RACES; index += 1) {
    const from = raceTime(schedule[index - 1]);
    const to = raceTime(schedule[index]);
    if (from == null || to == null) continue;
    const days = (to - from) / DAY_MS;
    if (days < BREAK_GAP_DAYS) continue;
    if (!longest || days > longest.days) longest = { index, days, from, to };
  }
  return longest;
}

/** Whether a gap covers any of August, which is what makes it *the* summer break. */
function spansAugust(gap: CalendarGap): boolean {
  const from = new Date(gap.from).getUTCMonth();
  const to = new Date(gap.to).getUTCMonth();
  return from === AUGUST || to === AUGUST || (from < AUGUST && to > AUGUST);
}

function segmentPair(schedule: readonly RaceEvent[], index: number, labels: [string, string]): SeasonSegment[] {
  return [
    { key: "first", label: labels[0], races: schedule.slice(0, index) },
    { key: "second", label: labels[1], races: schedule.slice(index) },
  ];
}

/**
 * The calendar split into selector rows: at the summer break when the schedule
 * has one, otherwise down the middle, and left whole when it is short enough
 * to read in a single row.
 */
export function seasonSegments(schedule: readonly RaceEvent[]): SeasonSegment[] {
  if (schedule.length <= SINGLE_ROW_MAX) return [{ key: "season", label: "", races: [...schedule] }];

  const gap = longestBreak(schedule);
  if (gap && spansAugust(gap)) {
    return segmentPair(schedule, gap.index, ["before the summer break", "after the summer break"]);
  }
  if (gap) return segmentPair(schedule, gap.index, ["first half", "second half"]);
  return segmentPair(schedule, Math.ceil(schedule.length / 2), ["first half", "second half"]);
}

/** Round range covering a segment, e.g. "R1-R14". */
export function segmentRange(segment: SeasonSegment): string {
  const first = segment.races[0];
  const last = segment.races[segment.races.length - 1];
  if (!first || !last) return "";
  return `R${first.round}-R${last.round}`;
}
