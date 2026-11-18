"use client";

import { API_BASE } from "@/app/constants/api";
import { useSection, type SectionResult } from "@/app/ui/section/useSection";

import type { StandingsProgression } from "./standingsModel";
import type { TeamsResponse } from "./teamsModel";
import type { OverviewShell } from "../components/CommandCenterPanels";

/** Standings move once a race weekend: no refetch on focus, a long dedupe. */
const CONFIG = { revalidateOnFocus: false, dedupingInterval: 180_000 };

/** The championship tables, rows and freshness. */
export function useTeams(year: number, seed: TeamsResponse | null): SectionResult<TeamsResponse> {
  return useSection<TeamsResponse>(`${API_BASE}/api/race-control/teams/${year}`, { seed, config: CONFIG });
}

/** The overview shell, for the stakes. `RaceStatusChip` already fetches this key, so SWR dedupes it. */
export function useShell(year: number, seed: OverviewShell | null): SectionResult<OverviewShell> {
  return useSection<OverviewShell>(`${API_BASE}/api/race-control/overview/${year}/shell`, { seed, config: CONFIG });
}

/** Each round's table, and the round each title was clinched. */
export function useProgression(year: number, seed: StandingsProgression | null): SectionResult<StandingsProgression> {
  return useSection<StandingsProgression>(`${API_BASE}/api/race-control/standings/${year}/progression`, {
    seed,
    config: CONFIG,
  });
}

/** The server render's three payloads, as promises the sections `use()`; each may resolve to null. */
export interface StandingsSeeds {
  teams: Promise<TeamsResponse | null>;
  shell: Promise<OverviewShell | null>;
  progression: Promise<StandingsProgression | null>;
}
