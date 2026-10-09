/**
 * Where each round of the season sits, for the round selector.
 *
 * Kept apart from the user's selection on purpose: the previous selector
 * painted the selected round the same red as a race that is actually running,
 * so a click could not be told apart from a live session. State describes the
 * calendar; selection is a separate layer drawn on top of it.
 */

import { isLiveRace } from "./predictionHelpers";

import type { RaceEvent } from "./predictionModel";

export type RoundState = "completed" | "live" | "next" | "future";

const ROUND_STATE_COLOR: Record<RoundState, string> = {
  completed: "#00FF78",
  live: "#E10600",
  next: "#F5C542",
  future: "#4A5261",
};

const ROUND_STATE_LABEL: Record<RoundState, string> = {
  completed: "complete",
  live: "live now",
  next: "next up",
  future: "upcoming",
};

/** Accent colour for a round in the selector. */
export function roundStateColor(state: RoundState): string {
  return ROUND_STATE_COLOR[state];
}

/** Short state wording, used in tooltips, the legend and screen-reader labels. */
export function roundStateLabel(state: RoundState): string {
  return ROUND_STATE_LABEL[state];
}

/**
 * Round number of the next race to run: the live one if a weekend is running,
 * otherwise the first round that has not been completed. `null` once the
 * season is over.
 */
export function nextRoundNumber(schedule: readonly RaceEvent[]): number | null {
  const next = schedule.find((race) => race.status !== "completed");
  return next?.round ?? null;
}

/** A round's place in the season, given the round the calendar has reached. */
export function roundState(race: RaceEvent, nextRound: number | null): RoundState {
  if (isLiveRace(race.status)) return "live";
  if (race.status === "completed") return "completed";
  return race.round === nextRound ? "next" : "future";
}
