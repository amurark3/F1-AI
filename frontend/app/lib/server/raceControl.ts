import type { RaceEvent } from "@/app/race-control/predictions/predictionModel";
import type { TeamsResponse } from "@/app/race-control/teams/teamsModel";

import { fetchFromBackend } from "./backend";
import { REVALIDATE } from "./revalidate";


/** The season every Race Control surface reports on. */
export const currentSeason = (): number => new Date().getFullYear();

/**
 * The race calendar.
 *
 * Shared by predictions, debriefs, and live timing. All three hit the same
 * cache entry, so the schedule is fetched once per hour for the whole app
 * rather than once per visitor per page.
 */
export function getSchedule(year: number): Promise<RaceEvent[] | { error: string } | null> {
  return fetchFromBackend<RaceEvent[] | { error: string }>(`/api/schedule/${year}`, {
    revalidate: REVALIDATE.SCHEDULE,
    tags: ["schedule", `schedule:${year}`],
  });
}

/** Championship standings plus team operating profiles. */
export function getTeams(year: number): Promise<TeamsResponse | null> {
  return fetchFromBackend<TeamsResponse>(`/api/race-control/teams/${year}`, {
    revalidate: REVALIDATE.STANDINGS,
    tags: ["teams", `teams:${year}`],
  });
}

/** One constructor's detail page payload. */
export function getTeamDetail<T>(slug: string, year: number): Promise<T | null> {
  return fetchFromBackend<T>(`/api/race-control/teams/${slug}/${year}`, {
    revalidate: REVALIDATE.STANDINGS,
    tags: ["teams", `teams:${year}`],
  });
}

/** The season entry list, used to seed the prediction grid. */
export function getDrivers<T>(year: number): Promise<T | null> {
  return fetchFromBackend<T>(`/api/race-control/drivers/${year}`, {
    revalidate: REVALIDATE.ENTRY_LIST,
    tags: ["drivers", `drivers:${year}`],
  });
}

/**
 * One segment of the command-centre overview.
 *
 * The backend splits the overview into independently-loading segments so a slow
 * telemetry read delays only the panels that need it. Fetching them as separate
 * cache entries preserves that: each segment revalidates on its own clock.
 */
export function getOverviewSegment<T>(year: number, path: string): Promise<T | null> {
  return fetchFromBackend<T>(`/api/race-control/overview/${year}${path}`, {
    revalidate: REVALIDATE.OVERVIEW,
    tags: ["overview", `overview:${year}`],
  });
}

/** Post-race debrief for a single round. */
export function getDebrief<T>(year: number, round: number): Promise<T | null> {
  return fetchFromBackend<T>(`/api/race-control/debrief/${year}/${round}`, {
    revalidate: REVALIDATE.STANDINGS,
    tags: ["debrief", `debrief:${year}:${round}`],
  });
}

/** Rival intel for one constructor. */
export function getIntel<T>(slug: string): Promise<T | null> {
  return fetchFromBackend<T>(`/api/race-control/intel/${slug}`, {
    revalidate: REVALIDATE.OVERVIEW,
    tags: ["intel", `intel:${slug}`],
  });
}

/** Cached model output for a round. Never triggers a recompute. */
/**
 * A stored prediction snapshot, optionally for one phase of the race weekend.
 *
 * Each phase is cached and tagged separately so recomputing one does not
 * invalidate the other's server-rendered payload.
 */
export function getPredictionSnapshot<T>(year: number, round: number, phase?: string): Promise<T | null> {
  const query = phase ? `?phase=${phase}` : "";
  return fetchFromBackend<T>(`/api/predictions/${year}/${round}/snapshot${query}`, {
    revalidate: REVALIDATE.PREDICTIONS,
    tags: ["predictions", `predictions:${year}:${round}`, `predictions:${year}:${round}:${phase ?? "latest"}`],
  });
}

/** Narrows the schedule response to an array, discarding an `{ error }` payload. */
export function scheduleRaces(response: RaceEvent[] | { error: string } | null): RaceEvent[] {
  return Array.isArray(response) ? response : [];
}
