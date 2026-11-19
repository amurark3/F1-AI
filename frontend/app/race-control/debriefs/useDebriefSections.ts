"use client";

import { API_BASE } from "@/app/constants/api";
import type { ScheduleSeed } from "@/app/ui/race-picker/useSchedule";
import { useSection, type SectionResult } from "@/app/ui/section/useSection";

import type { DebriefLaps, DebriefOvertakes, DebriefPenalties, DebriefSummary } from "./debriefTypes";

/** A classified race stops changing: no refetch on focus, a long dedupe. */
const CONFIG = { revalidateOnFocus: false, dedupingInterval: 120_000 };

function url(year: number, round: number, part: string): string {
  return `${API_BASE}/api/race-control/debrief/${year}/${round}${part}`;
}

/** The result, grid and titles; the server render seeds the default round. */
export function useDebriefSummary(
  year: number,
  round: number,
  seed: DebriefSummary | null,
): SectionResult<DebriefSummary> {
  return useSection<DebriefSummary>(url(year, round, ""), { seed, config: CONFIG });
}

export function useDebriefLaps(year: number, round: number): SectionResult<DebriefLaps> {
  return useSection<DebriefLaps>(url(year, round, "/laps"), { config: CONFIG });
}

export function useDebriefPenalties(year: number, round: number): SectionResult<DebriefPenalties> {
  return useSection<DebriefPenalties>(url(year, round, "/penalties"), { config: CONFIG });
}

export function useDebriefOvertakes(year: number, round: number): SectionResult<DebriefOvertakes> {
  return useSection<DebriefOvertakes>(url(year, round, "/overtakes"), { config: CONFIG });
}

/** The server render's two payloads: the calendar, and the default round's summary with its round. */
export interface DebriefSeeds {
  schedule: Promise<ScheduleSeed>;
  summary: Promise<{ round: number; data: DebriefSummary | null } | null>;
}
