import { fetchFromBackend } from "./backend";
import { REVALIDATE } from "./revalidate";

export interface DriverChampion {
  name: string;
  code: string | null;
  team: string | null;
  points: number;
  wins: number;
  nationality: string | null;
  title_decided: boolean;
}

export interface ConstructorChampion {
  name: string;
  points: number;
  title_decided: boolean;
}

export interface SeasonChampion {
  season: number;
  is_in_progress: boolean;
  driver_champion: DriverChampion | null;
  constructor_champion: ConstructorChampion | null;
  round_count: number;
}

export interface ChampionsResponse {
  seasons?: SeasonChampion[];
  error?: string;
}

export interface TitleEntry {
  name: string;
  titles: number;
}

export interface StatsResponse {
  most_driver_titles?: TitleEntry[];
  most_constructor_titles?: TitleEntry[];
  error?: string;
}

export interface RaceWinner {
  round: number;
  race_name: string;
  date: string | null;
  winner: string;
  team: string | null;
}

export interface SeasonDetail {
  season: number;
  is_in_progress: boolean;
  driver_champion: DriverChampion | null;
  constructor_champion: ConstructorChampion | null;
  runner_up: { name: string; points: number } | null;
  race_winners?: RaceWinner[];
  error?: string;
}

/** The first season of the World Championship — the archive's lower bound. */
export const FIRST_SEASON = 1950;

/**
 * Every season with its champions.
 *
 * Served from the backend's local f1db dataset, which only changes when a title
 * is decided, so a day-long cache costs nothing and removes the backend from
 * the critical path of the most-visited reference page.
 */
export function getChampions(): Promise<ChampionsResponse | null> {
  return fetchFromBackend<ChampionsResponse>("/api/champions", {
    revalidate: REVALIDATE.ARCHIVE,
    tags: ["champions"],
  });
}

/** Aggregate title leaderboards. Same volatility as the season list. */
export function getChampionStats(): Promise<StatsResponse | null> {
  return fetchFromBackend<StatsResponse>("/api/champions/stats", {
    revalidate: REVALIDATE.ARCHIVE,
    tags: ["champions"],
  });
}

/**
 * Champions plus race winners for one season.
 *
 * An unknown year comes back as `{ error }` with no season payload; callers
 * distinguish that (a 404) from a null return (backend unreachable).
 */
export function getSeasonDetail(year: string): Promise<SeasonDetail | null> {
  return fetchFromBackend<SeasonDetail>(`/api/champions/${year}`, {
    revalidate: REVALIDATE.ARCHIVE,
    tags: ["champions", `champions:${year}`],
  });
}

/**
 * Every season year, newest first — the set of season detail routes to
 * prerender.
 *
 * Derived from the champions list rather than a hardcoded range so a new season
 * appears without touching this file. Returns an empty list when the backend is
 * unreachable at build time, which leaves the routes to render on demand.
 */
export async function listSeasonYears(): Promise<string[]> {
  const champions = await getChampions();
  return (champions?.seasons ?? []).map((season) => String(season.season));
}
