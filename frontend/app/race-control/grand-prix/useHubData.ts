"use client";

import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { awaitingFirstData, seededWith } from "@/app/lib/swrFallback";
import { fetcher } from "@/app/utils/fetcher";

import type { StartingGridResponse } from "./gridModel";
import type { PredictionPhase, PredictionsResponse } from "./predictionModel";
import type { PhaseSnapshot } from "./predictionState";
import type { WeekendSessionsResponse } from "./sessionsModel";
import type { RaceStrategyResponse } from "./strategyModel";

/**
 * One phase's stored snapshot.
 *
 * The two phases are separate SWR keys on purpose: recomputing one must not
 * invalidate, blank or reorder the other, which is exactly what sharing a key
 * and swapping a query parameter would do.
 */
export function usePhaseSnapshot(
  year: number,
  round: number | null,
  phase: PredictionPhase,
  seed: PredictionsResponse | null,
): PhaseSnapshot {
  const { data, error, isLoading, mutate } = useSWR<PredictionsResponse, Error>(
    round ? `${API_BASE}/api/predictions/${year}/${round}/snapshot?phase=${phase}` : null,
    fetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
      ...seededWith(seed),
    },
  );

  return { data, error, awaiting: awaitingFirstData(isLoading, data !== undefined), mutate };
}

/**
 * The published starting grid for the round in focus.
 *
 * A separate key from the prediction snapshots on purpose: the grid is a fact
 * about the weekend, not model output, and recomputing a prediction must not
 * invalidate or blank it.
 */
export function useStartingGrid(year: number, round: number | null, seed: StartingGridResponse | null) {
  const { data, isLoading } = useSWR<StartingGridResponse, Error>(
    round ? `${API_BASE}/api/race-control/grid/${year}/${round}` : null,
    fetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 120000,
      ...seededWith(seed),
    },
  );

  return { grid: data, gridLoading: awaitingFirstData(isLoading, data !== undefined) };
}

/**
 * The weekend's sessions and its race strategy.
 *
 * Both describe what the weekend did, not what the model thinks, so they hold
 * their own SWR keys: recomputing a prediction must not blank either, and a
 * round with no snapshot still fills these tabs.
 *
 * Stints come from a FastF1 load that costs ~28 s warm and minutes cold, so
 * they are fetched only once the Stints tab has been opened.
 */
export function useWeekendData(
  year: number,
  round: number | null,
  seed: { sessions: WeekendSessionsResponse | null; strategy: RaceStrategyResponse | null },
  wantStints: boolean,
) {
  const sessions = useSWR<WeekendSessionsResponse, Error>(
    round ? `${API_BASE}/api/race-control/sessions/${year}/${round}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 120000, ...seededWith(seed.sessions) },
  );
  const strategy = useSWR<RaceStrategyResponse, Error>(
    round && wantStints ? `${API_BASE}/api/race-control/stints/${year}/${round}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 120000, ...seededWith(seed.strategy) },
  );

  return {
    sessions: sessions.data,
    sessionsLoading: awaitingFirstData(sessions.isLoading, sessions.data !== undefined),
    strategy: strategy.data,
    strategyLoading: awaitingFirstData(strategy.isLoading, strategy.data !== undefined),
  };
}
