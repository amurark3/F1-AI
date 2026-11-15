import { nextUp } from "@/app/ui/nextUp";

import type { RaceResultsResponse, ResultRow } from "./resultsModel";
import type { CircuitRecord, OverviewCircuit } from "../weekend/weekendTypes";

/** `GET /api/race-control/circuit/{year}/{round}`: the Command Center's circuit segment, plus which round it is. */
export interface RoundCircuit extends OverviewCircuit {
  round: number;
}

export type ScheduleState = "done" | "live" | "next" | "later";

export interface ScheduleNode {
  name: string;
  startsAt: string;
  state: ScheduleState;
}

/**
 * Each session in start order, marked done, live, next or later against the
 * clock. With no clock yet (the server render) every session is "later": a
 * prerendered page has no honest "now".
 */
export function scheduleNodes(sessions: Record<string, string>, nowMs: number | null): ScheduleNode[] {
  const upcoming = nowMs === null ? null : nextUp(sessions, nowMs);
  return Object.entries(sessions)
    .map(([name, startsAt]) => ({ name, startsAt, start: new Date(startsAt).getTime() }))
    .filter((session) => !Number.isNaN(session.start))
    .sort((a, b) => a.start - b.start)
    .map(({ name, startsAt, start }) => {
      if (nowMs === null) return { name, startsAt, state: "later" as const };
      if (upcoming?.name === name)
        return { name, startsAt, state: upcoming.live ? ("live" as const) : ("next" as const) };
      return { name, startsAt, state: start < nowMs ? ("done" as const) : ("later" as const) };
    });
}

/** The race winner: the classification's row at position 1. Null until one is published. */
export function raceWinner(results: RaceResultsResponse | undefined): ResultRow | null {
  return results?.race?.classification.find((row) => row.position === 1) ?? null;
}

const DIRECTION_WORDS: Record<NonNullable<CircuitRecord["direction"]>, string> = {
  clockwise: "Clockwise",
  "anti-clockwise": "Anticlockwise",
};

/** The facts strip's four figures from f1db's record; a missing fact reads "-", never zero. */
export function circuitFacts(record: CircuitRecord | null | undefined): {
  lap: string;
  laps: string;
  distance: string;
  corners: string;
  direction: string | null;
} {
  const number = (value: number | null | undefined, digits = 0): string =>
    value === null || value === undefined ? "-" : value.toFixed(digits);
  return {
    lap: number(record?.length_km, 3),
    laps: number(record?.laps),
    distance: number(record?.distance_km, 1),
    corners: number(record?.turns),
    direction: record?.direction ? DIRECTION_WORDS[record.direction] : null,
  };
}
