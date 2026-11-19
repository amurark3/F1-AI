"use client";

import { API_BASE } from "@/app/constants/api";
import { useSection, type SectionResult } from "@/app/ui/section/useSection";

import { powerUnitsUrl, type PowerUnitsResponse } from "./powerUnitsModel";

import type { TeamsResponse } from "../standings/teamsModel";

/** The server render's two payloads, as promises the sections `use()`; each may resolve to null. */
export interface PowerUnitsSeeds {
  powerUnits: Promise<PowerUnitsResponse | null>;
  teams: Promise<TeamsResponse | null>;
}

/** Documents arrive through a race weekend: no refetch on focus, a long dedupe. All three sections share this one key. */
export function usePowerUnits(year: number, seed: PowerUnitsResponse | null): SectionResult<PowerUnitsResponse> {
  return useSection<PowerUnitsResponse>(powerUnitsUrl(API_BASE, year), {
    seed,
    config: { revalidateOnFocus: false, dedupingInterval: 120_000 },
  });
}
