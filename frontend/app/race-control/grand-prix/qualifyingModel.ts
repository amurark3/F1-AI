/**
 * What the Sessions tab computes from the payload: the benchmark of each qualifying part,
 * the cut lines between parts, and the sentences that name a finding. Nothing is typed by
 * hand; every number and name on the tab comes through here from the rows.
 */

import type { PracticeEntry, QualifyingEntry, QualifyingPart } from "./sessionsModel";

export const PARTS: readonly QualifyingPart[] = ["q1", "q2", "q3"];

const DSQ = "DSQ";
const NUMBER_WORDS = ["No", "One", "Two", "Three", "Four"];

export function isDsq(entry: { position_text: string }): boolean {
  return entry.position_text === DSQ;
}

/** `m:ss.sss` or `+s.sss` in milliseconds. */
export function timeMs(text: string): number {
  const [minutes, seconds] = text.includes(":") ? text.split(":") : ["0", text.replace("+", "")];
  return Math.round((Number(minutes) * 60 + Number(seconds)) * 1000);
}

/** The fastest classified lap of each part, whoever set it. A disqualified car sets no benchmark. */
export function fastestByPart(entries: QualifyingEntry[]): Partial<Record<QualifyingPart, number>> {
  const best: Partial<Record<QualifyingPart, number>> = {};
  for (const entry of entries.filter((row) => !isDsq(row))) {
    for (const part of PARTS) {
      const time = entry[part];
      if (time) best[part] = Math.min(best[part] ?? Infinity, timeMs(time));
    }
  }
  return best;
}

export interface QualifyingGroup {
  key: string;
  /** The cut line above the group; null for the cars that reached the last part. */
  cut: string | null;
  disqualified: boolean;
  rows: QualifyingEntry[];
}

function cutLabel(part: QualifyingPart | null): string {
  return part === null ? "No time set" : `Knocked out in ${part.toUpperCase()}`;
}

/** Rows grouped by the part each car ran in on the road, disqualified cars last under a red cut. */
export function qualifyingGroups(entries: QualifyingEntry[]): QualifyingGroup[] {
  const groups: QualifyingGroup[] = [];
  for (const row of entries.filter((entry) => !isDsq(entry))) {
    const key = row.part ?? "none";
    const last = groups.at(-1);
    if (last?.key === key) {
      last.rows.push(row);
    } else {
      const cut = groups.length === 0 && key === "q3" ? null : cutLabel(row.part);
      groups.push({ key, cut, disqualified: false, rows: [row] });
    }
  }
  const disqualified = entries.filter(isDsq);
  if (disqualified.length > 0) {
    groups.push({ key: DSQ, cut: "Disqualified from qualifying", disqualified: true, rows: disqualified });
  }
  return groups;
}

/** The time a phone shows: the last part's lap, prefixed with the part. */
export function lastTime(entry: QualifyingEntry): { part: string; time: string } | null {
  return entry.part === null ? null : { part: entry.part.toUpperCase(), time: entry[entry.part]! };
}

/** Bar length as a fraction of the largest in-part gap on the table. */
export function gapFraction(entry: QualifyingEntry, entries: QualifyingEntry[]): number {
  if (entry.part_gap === null) return 0;
  const largest = Math.max(...entries.map((row) => (row.part_gap === null ? 0 : timeMs(row.part_gap))));
  return Math.max(timeMs(entry.part_gap) / largest, 0.004);
}

export interface PoleMargin {
  pole: QualifyingEntry;
  second: QualifyingEntry;
  /** Seconds, "0.009". */
  seconds: string;
}

export function poleMargin(entries: QualifyingEntry[]): PoleMargin | null {
  const pole = entries.find((entry) => entry.position === 1);
  const second = entries.find((entry) => entry.position === 2);
  if (!pole || !second?.part_gap) return null;
  return { pole, second, seconds: second.part_gap.replace("+", "") };
}

export interface PartLeader {
  label: string;
  entry: QualifyingEntry;
}

/** Who set the fastest lap of each part. */
export function partLeaders(entries: QualifyingEntry[]): PartLeader[] {
  const best = fastestByPart(entries);
  return PARTS.flatMap((part) => {
    const entry = entries.find((row) => {
      const time = row[part];
      return !isDsq(row) && time !== null && timeMs(time) === best[part];
    });
    return entry ? [{ label: part.toUpperCase(), entry }] : [];
  });
}

export interface StewardsCard {
  title: string;
  body: string;
}

/** The decisions that changed this classification: a disqualification moves cars; a grid drop does not. */
export function stewardsCard(entries: QualifyingEntry[]): StewardsCard {
  const out = entries.filter(isDsq);
  if (out.length === 0) {
    return {
      title: "No decision changed this order",
      body: "Grid penalties, if any, change the grid and not this order. See Grid.",
    };
  }
  const count = NUMBER_WORDS[out.length] ?? String(out.length);
  const names = out.map((entry) => entry.driver_name).join(" and ");
  return {
    title: `${count} ${out.length === 1 ? "decision" : "decisions"} changed this order`,
    body: `${names} disqualified after the session, lifting every car classified below by one place. Grid penalties change the grid, not this order. See Grid.`,
  };
}

export function qualifyingTitle(margin: PoleMargin | null, session: string): string {
  return margin ? `${margin.pole.driver_name} takes pole by ${margin.seconds} s` : `${session} classification`;
}

/** Practice: how many cars a stand-in drove, for the sub line. */
export function standInCount(entries: PracticeEntry[]): number {
  return entries.filter((entry) => entry.stand_in_for !== null).length;
}
