"use client";

import { API_BASE } from "@/app/constants/api";
import type { RaceEvent } from "@/app/race-control/grand-prix/predictionModel";
import type { RaceResultsResponse } from "@/app/race-control/grand-prix/resultsModel";

import { useSection } from "../section/useSection";

const RESULT_CONFIG = { revalidateOnFocus: false, dedupingInterval: 120_000 };

/** Why a post-race view is locked: a published classification (provisional or final) unlocks it. */
export const RACE_LOCK = "Unlocks once the race classification is published.";

/** The round's published classifications; an upcoming round (or none) asks for nothing. */
export function useRaceResults(year: number, race: RaceEvent | null) {
  return useSection<RaceResultsResponse>(
    race && race.status !== "upcoming" ? `${API_BASE}/api/race-control/results/${year}/${race.round}` : null,
    { config: RESULT_CONFIG },
  );
}
