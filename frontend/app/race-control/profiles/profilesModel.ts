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

import type { DocumentRef, ElementInfo, PowerUnitCar } from "../power-units/powerUnitsModel";

export interface DirectoryDriver {
  id: string;
  name: string;
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
  /** Other feeds' spellings of the team, already folded with {@link foldName}. */
  aliases: string[];
}

export interface SeasonDirectory {
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

export interface TeamProfile {
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

export interface DriverProfile {
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

export const PODIUM_POSITIONS = 3;
export const WIN_COLOR = "#FFD15C";
export const PODIUM_COLOR = "#E8E8E8";
export const POINTS_COLOR = "#00FF78";
export const RETIRED_COLOR = "#FF6B6B";
export const MUTED_COLOR = "#5A6273";

export function profilesUrl(apiBase: string, year: number, path: string): string {
  return `${apiBase}/api/profiles/${year}/${path}`;
}

export function isTeamProfile(response: TeamProfileResponse | null | undefined): response is TeamProfile {
  return response?.status === "ok";
}

export function isDriverProfile(response: DriverProfileResponse | null | undefined): response is DriverProfile {
  return response?.status === "ok";
}

/** "P3", "DNF", "DNS" — or an em dash for a round the car did not take part in. */
export function finishLabel(finish: Finish | null): string {
  if (!finish) return "—";
  return finish.position === null ? finish.position_text || "NC" : `P${finish.position}`;
}

/** The colour a finish reads in: gold for a win, through to muted for no points. */
export function finishColor(finish: Finish | null): string {
  if (!finish) return MUTED_COLOR;
  if (finish.position === null) return RETIRED_COLOR;
  if (finish.position === 1) return WIN_COLOR;
  if (finish.position <= PODIUM_POSITIONS) return PODIUM_COLOR;
  return finish.points > 0 ? POINTS_COLOR : "#B7BDCA";
}

/** Tooltip text for a finish: the grid slot, places gained, and why it ended. */
export function finishDetail(finish: Finish | null): string {
  if (!finish) return "Did not take part";
  const parts = [finish.grid ? `Started P${finish.grid}` : "No grid slot"];
  if (finish.positions_gained) {
    parts.push(`${finish.positions_gained > 0 ? "+" : ""}${finish.positions_gained} places`);
  }
  parts.push(`${formatPoints(finish.points)} pts`);
  if (finish.reason_retired) parts.push(finish.reason_retired);
  if (finish.pole) parts.push("Pole");
  if (finish.fastest_lap) parts.push("Fastest lap");
  return parts.join(" · ");
}

export function formatPoints(points: number): string {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}

export function ordinalPosition(position: number | null): string {
  return position === null ? "—" : `P${position}`;
}

/** "Results through R18 United States Grand Prix", or a plain "no results yet". */
export function freshnessLine(through: ResultsThrough | null, year: number): string {
  return through ? `Results through R${through.round} ${through.name}` : `No ${year} results published yet`;
}

// --- Resolving names from other feeds --------------------------------------

/** Case-, accent- and punctuation-insensitive form of a name; mirrors the backend's `fold`. */
export function foldName(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

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
  if (!directory) return null;
  const { drivers } = directory;
  if (query.id && drivers.some((driver) => driver.id === query.id)) return query.id;
  const code = query.code?.toUpperCase();
  const byCode = code ? drivers.find((driver) => driver.code === code) : undefined;
  if (byCode) return byCode.id;
  const name = query.name ? foldName(query.name) : "";
  return (name && drivers.find((driver) => foldName(driver.name) === name)?.id) || null;
}

/** The f1db id a feed's team name refers to this season — exact or alias, never a substring. */
export function resolveTeamId(
  directory: SeasonDirectory | undefined,
  query: { id?: string | null; name?: string | null },
): string | null {
  if (!directory) return null;
  const { teams } = directory;
  if (query.id && teams.some((team) => team.id === query.id)) return query.id;
  const name = query.name ? foldName(query.name) : "";
  if (!name) return null;
  const match = teams.find(
    (team) =>
      foldName(team.id) === name ||
      foldName(team.name) === name ||
      foldName(team.full_name) === name ||
      team.aliases.includes(name),
  );
  return match?.id ?? null;
}
