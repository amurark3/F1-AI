/**
 * Shapes of the `/api/profiles/{year}/…` endpoints behind the Teams & Drivers
 * pages, and the pure helpers those pages share.
 *
 * Everything here is a function of the payload — no fetching, no React — so
 * server and client components can both use it.
 *
 * Power-unit usage belongs to the car (FIA B8.2.7). A driver's page therefore
 * carries whole cars, plus the rounds that were theirs and who else drove them.
 */

import { standingsLabel, type StandingsFreshness } from "@/app/lib/standingsFreshness";
import { findDirectoryDriver, findDirectoryTeam } from "@/app/ui/names/names";

import type { DocumentRef, ElementInfo, PowerUnitCar } from "../power-units/powerUnitsModel";

export interface DirectoryDriver {
  id: string;
  /** f1db's display name ("Carlos Sainz Jr."). */
  name: string;
  /**
   * f1db's surname as it stores it ("Sainz Jr.", "Hülkenberg"). The payload's
   * `first_name` is left untyped on purpose: f1db's can be a legal name
   * ("Carlton" for Jak Crawford), so no display name is ever built from parts.
   */
  last_name: string;
  code: string | null;
  number: number | null;
  team_id: string;
}

export interface DirectoryTeam {
  id: string;
  name: string;
  full_name: string;
  color: string;
  position: number | null;
  points: number;
  /** Other feeds' spellings of the team, already folded with `foldName` (`app/ui/names`). */
  aliases: string[];
}

/** Teams come in the order of the same table the team pages show. */
export interface SeasonDirectory extends Partial<StandingsFreshness> {
  year: number;
  status?: "ok" | "error";
  drivers: DirectoryDriver[];
  teams: DirectoryTeam[];
  error?: string;
}

/** One car's classification in one race or sprint. */
export interface Finish {
  number: number | null;
  position: number | null;
  position_text: string;
  grid: number | null;
  points: number;
  positions_gained: number | null;
  reason_retired: string | null;
  fastest_lap: boolean;
  pole: boolean;
}

export type RoundStatus = "complete" | "pending";

export interface RoundRef {
  round: number;
  name: string;
  short_name: string;
}

export interface ResultsThrough {
  round: number;
  name: string;
}

export interface ProfilePowerUnits<C> {
  available: boolean;
  reason: string | null;
  as_of: (DocumentRef & { round: number }) | null;
  elements: ElementInfo[];
  cars: C[];
}

/** Every non-ok answer: an unknown id, or a backend that failed. */
export interface MissingProfile {
  year: number;
  status: "not_found" | "error";
  error?: string;
  error_id?: string;
}

// --- Team ------------------------------------------------------------------

export interface TeamSummary {
  id: string;
  name: string;
  full_name: string;
  color: string;
  position: number | null;
  points: number;
  wins: number;
  podiums: number;
  poles: number;
}

export interface TeamDriver {
  id: string;
  name: string;
  code: string | null;
  number: number | null;
  /** Started the team's latest race. */
  current: boolean;
  rounds: number[];
  rounds_label: string;
  position: number | null;
  points: number;
  wins: number;
}

export interface TeamWin extends RoundRef {
  driver_id: string;
  grid: number | null;
}

export interface TeamRoundResult {
  driver_id: string;
  race: Finish | null;
  sprint: Finish | null;
}

export interface TeamRound extends RoundRef {
  date: string;
  status: RoundStatus;
  results: TeamRoundResult[];
  points: number;
  cumulative_points: number | null;
}

export interface TeamProfile extends StandingsFreshness {
  year: number;
  status: "ok";
  team: TeamSummary;
  drivers: TeamDriver[];
  wins: TeamWin[];
  rounds: TeamRound[];
  results_through: ResultsThrough | null;
  /** The key the rival-intel endpoint knows this team by. */
  intel_slug: string;
  power_units: ProfilePowerUnits<PowerUnitCar>;
}

export type TeamProfileResponse = TeamProfile | MissingProfile;

// --- Driver ----------------------------------------------------------------

export interface DriverSummary {
  id: string;
  name: string;
  code: string | null;
  number: number | null;
  nationality: string | null;
  team_id: string;
  team_name: string;
  color: string;
}

export interface DriverTeamSpell {
  id: string;
  name: string;
  color: string;
  rounds: number[];
  rounds_label: string;
}

export interface DriverStats {
  starts: number;
  wins: number;
  podiums: number;
  poles: number;
  fastest_laps: number;
  retirements: number;
  best_finish: number | null;
}

export interface DriverRound extends RoundRef {
  date: string;
  status: RoundStatus;
  team_id: string | null;
  race: Finish | null;
  sprint: Finish | null;
}

export interface CarShare {
  id: string;
  name: string;
  rounds: number[];
  rounds_label: string;
}

export interface DriverCar extends PowerUnitCar {
  /** The rounds this driver raced this car. */
  driver_rounds: number[];
  shared_with: CarShare[];
}

export interface DriverProfile extends StandingsFreshness {
  year: number;
  status: "ok";
  driver: DriverSummary;
  standing: { position: number | null; points: number };
  stats: DriverStats;
  teams: DriverTeamSpell[];
  wins: RoundRef[];
  rounds: DriverRound[];
  results_through: ResultsThrough | null;
  power_units: ProfilePowerUnits<DriverCar>;
}

export type DriverProfileResponse = DriverProfile | MissingProfile;

// --- Helpers ---------------------------------------------------------------

export function profilesUrl(apiBase: string, year: number, path: string): string {
  return `${apiBase}/api/profiles/${year}/${path}`;
}

export function isTeamProfile(response: TeamProfileResponse | null | undefined): response is TeamProfile {
  return response?.status === "ok";
}

export function isDriverProfile(response: DriverProfileResponse | null | undefined): response is DriverProfile {
  return response?.status === "ok";
}

export function formatPoints(points: number): string {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}

export function ordinalPosition(position: number | null): string {
  return position === null ? "—" : `P${position}`;
}

/** "382 pts · after round 19 · provisional": championship points and how fresh the table is. */
export function championshipPoints(points: number, freshness: Partial<StandingsFreshness>): string {
  const label = standingsLabel(freshness);
  return label ? `${formatPoints(points)} pts · ${label}` : `${formatPoints(points)} pts`;
}

/** "Results through R18 United States Grand Prix", or a plain "no results yet". */
export function freshnessLine(through: ResultsThrough | null, year: number): string {
  return through ? `Results through R${through.round} ${through.name}` : `No ${year} results published yet`;
}

// --- Resolving names from other feeds --------------------------------------

export interface DriverQuery {
  id?: string | null;
  code?: string | null;
  name?: string | null;
}

/**
 * The f1db id a feed's driver refers to this season, or `null`.
 *
 * Codes are unique within a season (not across them), and names are compared
 * folded, so "Sergio Perez" finds "Sergio Pérez". Nothing is guessed.
 */
export function resolveDriverId(directory: SeasonDirectory | undefined, query: DriverQuery): string | null {
  return findDirectoryDriver(directory, query)?.id ?? null;
}

/** The f1db id a feed's team name refers to this season — exact or alias, never a substring. */
export function resolveTeamId(
  directory: SeasonDirectory | undefined,
  query: { id?: string | null; name?: string | null },
): string | null {
  return findDirectoryTeam(directory, query)?.id ?? null;
}
