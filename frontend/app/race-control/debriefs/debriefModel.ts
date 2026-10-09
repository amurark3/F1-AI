/** Shared shapes and selection rules for the race debrief desk. */

import type { RaceEvent } from "../grand-prix/predictionModel";

export interface Debrief {
  race?: string;
  location?: string;
  headline?: string;
  podium?: Array<{ position: number; driver: string; full_name: string; team: string; points: number }>;
  podium_cause?: Array<{
    position: number;
    driver: string;
    full_name: string;
    team: string;
    grid?: number | null;
    points: number;
    delta?: number | null;
    call: string;
  }>;
  strategy_winners?: Array<{ position: number; driver: string; full_name: string; team: string; grid: number }>;
  constructor_impact?: Array<{ team: string; points: number; classified_cars: number }>;
  reliability_watch?: Array<{ position: number; driver: string; full_name: string; team: string; status: string }>;
  classification?: Array<{
    position: number;
    driver: string;
    full_name: string;
    team: string;
    grid?: number | null;
    points: number;
    status: string;
  }>;
  race_control_notes?: Array<{ label: string; detail: string }>;
  takeaways?: string[];
  insight_source?: string;
  error?: string;
}

/**
 * The round the debrief desk opens on: the most recently completed Grand Prix,
 * falling back to the first on the calendar before any race has run.
 *
 * Shared with the server so it prefetches the debrief the client will ask for.
 */
export function resolveDefaultDebriefRace(races: RaceEvent[]): RaceEvent | null {
  return races.filter((race) => race.status === "completed").at(-1) ?? races[0] ?? null;
}
