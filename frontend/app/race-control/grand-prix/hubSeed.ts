import type { StartingGridResponse } from "./gridModel";
import type { DriverStanding, PredictionPhase, PredictionsResponse, RaceEvent } from "./predictionModel";
import type { WeekendSessionsResponse } from "./sessionsModel";
import type { RaceStrategyResponse } from "./strategyModel";

export interface DriversResponse {
  drivers: DriverStanding[];
  error?: string | null;
}

/** One server-rendered snapshot per phase, to seed the client's SWR caches. */
export type PhaseSnapshots = Record<PredictionPhase, PredictionsResponse | null>;

/** Server-rendered payloads used to seed the workspace's SWR caches. */
export interface GrandPrixSeed {
  year: number;
  schedule: RaceEvent[] | { error: string } | null;
  drivers: DriversResponse | null;
  /** Both phases for the default round, each null if there was none to prefetch. */
  snapshots: PhaseSnapshots;
  /** The round `snapshots` belong to, so a different selection is not seeded. */
  snapshotRound: number | null;
  /** The starting grid for `snapshotRound`, or null when there was none. */
  grid: StartingGridResponse | null;
  /** Practice and sprint classifications for `snapshotRound`. */
  sessions: WeekendSessionsResponse | null;
  /** Tyre stints and pit stops for `snapshotRound`. */
  strategy: RaceStrategyResponse | null;
}
