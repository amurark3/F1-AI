import { cache } from "react";

import type {
  DriverProfileResponse,
  SeasonDirectory,
  TeamProfileResponse,
} from "@/app/race-control/profiles/profilesModel";

import { fetchFromBackend } from "./backend";
import { REVALIDATE } from "./revalidate";

/**
 * Every driver and team of the season, by f1db id.
 *
 * Wrapped in `cache` because a page, its metadata and its static params all
 * read it during one render.
 */
export const getDirectory = cache((year: number): Promise<SeasonDirectory | null> => {
  return fetchFromBackend<SeasonDirectory>(`/api/profiles/${year}/directory`, {
    revalidate: REVALIDATE.ENTRY_LIST,
    tags: ["profiles", `profiles:${year}`],
  });
});

/**
 * A constructor's season. It carries power-unit usage, which moves through a
 * race weekend, so it refreshes on that clock rather than the standings'.
 */
export const getTeamProfile = cache((year: number, teamId: string): Promise<TeamProfileResponse | null> => {
  return fetchFromBackend<TeamProfileResponse>(`/api/profiles/${year}/teams/${encodeURIComponent(teamId)}`, {
    revalidate: REVALIDATE.POWER_UNITS,
    tags: ["profiles", `profiles:${year}`, `profiles:team:${teamId}`],
  });
});

/** A driver's season, refreshed on the same clock as the team page. */
export const getDriverProfile = cache((year: number, driverId: string): Promise<DriverProfileResponse | null> => {
  return fetchFromBackend<DriverProfileResponse>(`/api/profiles/${year}/drivers/${encodeURIComponent(driverId)}`, {
    revalidate: REVALIDATE.POWER_UNITS,
    tags: ["profiles", `profiles:${year}`, `profiles:driver:${driverId}`],
  });
});
