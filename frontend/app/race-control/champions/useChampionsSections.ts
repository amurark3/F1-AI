"use client";

import { API_BASE } from "@/app/constants/api";
import type { ChampionsResponse, LatestChampion, SeasonDetail, StatsResponse } from "@/app/lib/server/champions";
import { useSection, type SectionResult } from "@/app/ui/section/useSection";

/** The archive moves when a title is decided: no refetch on focus. */
const CONFIG = { revalidateOnFocus: false };

/** The newest champion and the records the title sets. */
export function useLatestChampion(seed: LatestChampion | null): SectionResult<LatestChampion> {
  return useSection<LatestChampion>(`${API_BASE}/api/champions/latest`, { seed, config: CONFIG });
}

/** Most titles, drivers and constructors. */
export function useChampionStats(seed: StatsResponse | null): SectionResult<StatsResponse> {
  return useSection<StatsResponse>(`${API_BASE}/api/champions/stats`, { seed, config: CONFIG });
}

/** Every season with its champions. */
export function useChampionList(seed: ChampionsResponse | null): SectionResult<ChampionsResponse> {
  return useSection<ChampionsResponse>(`${API_BASE}/api/champions`, { seed, config: CONFIG });
}

/** One season's champions and race winners: one SWR key, so the page's sections share a request. */
export function useSeasonDetail(year: number, seed: SeasonDetail | null): SectionResult<SeasonDetail> {
  return useSection<SeasonDetail>(`${API_BASE}/api/champions/${year}`, { seed, config: CONFIG });
}

/** The server render's three payloads, as promises the sections `use()`; each may resolve to null. */
export interface ChampionsSeeds {
  latest: Promise<LatestChampion | null>;
  stats: Promise<StatsResponse | null>;
  champions: Promise<ChampionsResponse | null>;
}
