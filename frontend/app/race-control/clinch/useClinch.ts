"use client";

import { API_BASE } from "@/app/constants/api";
import type { ClinchResponse } from "@/app/lib/clinch";
import { useSection, type SectionResult } from "@/app/ui/section/useSection";

const REFRESH = { revalidateOnFocus: false, dedupingInterval: 120_000 };

/**
 * The clinch calculator's answer for a season. Every line on a page reads this
 * one key, so SWR sends one request. No server seed: the lines are
 * supplementary, and a page never waits for them.
 */
export function useClinch(year: number): SectionResult<ClinchResponse> {
  return useSection<ClinchResponse>(`${API_BASE}/api/race-control/standings/${year}/clinch`, { config: REFRESH });
}
