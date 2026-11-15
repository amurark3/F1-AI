"use client";

import { API_BASE } from "@/app/constants/api";
import type { RaceWinner, SeasonDetail } from "@/app/lib/server/champions";
import type { RaceEvent } from "@/app/race-control/grand-prix/predictionModel";

import { useSection } from "../section/useSection";

/** What a server render fetched for the calendar: the rounds, the backend's handled failure, or nothing. */
export type ScheduleSeed = RaceEvent[] | { error: string } | null;

export interface Schedule {
  races: RaceEvent[];
  /** Nothing to show yet: the first answer is on its way. */
  pending: boolean;
  /** The calendar could not be loaded and none is on screen. */
  failed: boolean;
  retry: () => void;
}

/** The calendar changes only as weekends start and finish, and the champions table once per race. */
const SEASON_DEDUPE_MS = 300_000;
const SEASON_CONFIG = { revalidateOnFocus: false, dedupingInterval: SEASON_DEDUPE_MS };
const NO_RACES: RaceEvent[] = [];

/**
 * A season's calendar (`GET /api/schedule/{year}`), one cache entry for every
 * page and part that reads it: the Grand Prix hub, the Debriefs and the
 * Telemetry Lab used to fetch it three ways with three cache settings.
 */
export function useSchedule(year: number, seed: ScheduleSeed = null): Schedule {
  const section = useSection<RaceEvent[]>(`${API_BASE}/api/schedule/${year}`, {
    seed: Array.isArray(seed) ? seed : null,
    config: SEASON_CONFIG,
  });
  return {
    races: section.data ?? NO_RACES,
    pending: section.status === "pending",
    failed: section.status === "failed",
    retry: section.retry,
  };
}

/** Each round's winner and team, from f1db (`GET /api/champions/{year}`); undefined until they load. */
export function useRaceWinners(year: number): readonly RaceWinner[] | undefined {
  return useSection<Pick<SeasonDetail, "race_winners">>(`${API_BASE}/api/champions/${year}`, { config: SEASON_CONFIG })
    .data?.race_winners;
}
