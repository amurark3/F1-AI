/**
 * How a driver or team name is printed, from data and never from guesswork.
 *
 * Payloads carry f1db's canonical `driver.name` and team names (P2.2). The
 * plan's name rule is: full name in heroes, code + surname in tables, code on
 * chart axes. The surname and the code are read from data only:
 *
 * 1. the payload's own `last_name` / code;
 * 2. else this season's profiles directory (`/api/profiles/{year}/directory`),
 *    matched by f1db id, then code, then folded name, only for rows of that
 *    same season (codes are unique within a season, not across them: "VER" is
 *    Vergne in 2014 and Verstappen in 2026);
 * 3. else the full name. A name is never split into words, so "Carlos Sainz
 *    Jr.", "Nyck de Vries" and "Juan Manuel Fangio" can never come out as
 *    "Jr.", "Vries" or "Juan Fangio".
 *
 * Pure and server-safe; `DriverName` / `TeamName` wrap it for components.
 */

export type DriverNameVariant = "full" | "last" | "code" | "codeLast";

export type TeamNameVariant = "name" | "full";

/** What a payload knows about a driver. */
export interface DriverIdentity {
  /** f1db's display name, as the payload sends it. */
  name: string;
  /** f1db's `last_name`, when the payload carries it. */
  lastName?: string | null;
  code?: string | null;
  /** f1db's driver id. */
  id?: string | null;
  /** The season the row belongs to; the directory answers only for its own season. */
  year?: number | null;
}

/** What a payload knows about a team. */
export interface TeamIdentity {
  /** The team as the payload names it: f1db's name, or a feed's spelling. */
  name: string;
  fullName?: string | null;
  /** f1db's constructor id. */
  id?: string | null;
  year?: number | null;
}

/** What the directory is searched by; every key may be missing or blank. */
export interface DirectoryQuery {
  id?: string | null;
  code?: string | null;
  name?: string | null;
  year?: number | null;
}

/** The parts of a profiles-directory driver row the names read. */
export interface NameDirectoryDriver {
  id: string;
  name: string;
  code: string | null;
  last_name?: string | null;
}

/** The parts of a profiles-directory team row the names read. */
export interface NameDirectoryTeam {
  id: string;
  name: string;
  full_name: string;
  /** Other feeds' spellings, already folded with {@link foldName}. */
  aliases: readonly string[];
}

/** One season's drivers and teams, as `/api/profiles/{year}/directory` serves them. */
export interface NameDirectory {
  year: number;
  drivers: readonly NameDirectoryDriver[];
  teams: readonly NameDirectoryTeam[];
}

/** Case-, accent- and punctuation-insensitive form of a name; mirrors the backend's `fold`. */
export function foldName(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

/** `text` when it has any letters, else null: a blank cell is no data. */
function present(text: string | null | undefined): string | null {
  return text?.trim() ? text : null;
}

/** The directory, when it describes the season the row belongs to. */
function sameSeason<D extends NameDirectory>(directory: D | undefined, year: number | null | undefined): D | null {
  if (!directory) return null;
  return year === undefined || year === null || year === directory.year ? directory : null;
}

/** The directory's row for a driver: f1db id, then code, then folded name; never a near match. */
export function findDirectoryDriver<D extends NameDirectory>(
  directory: D | undefined,
  identity: DirectoryQuery,
): D["drivers"][number] | null {
  const season = sameSeason(directory, identity.year);
  if (!season) return null;
  const { drivers } = season;
  const byId = identity.id ? drivers.find((driver) => driver.id === identity.id) : undefined;
  if (byId) return byId;
  const code = identity.code?.toUpperCase();
  const byCode = code ? drivers.find((driver) => driver.code === code) : undefined;
  if (byCode) return byCode;
  const name = foldName(identity.name ?? "");
  return (name && drivers.find((driver) => foldName(driver.name) === name)) || null;
}

/** The directory's row for a team: id, f1db name, full name or a feed's alias, never a substring. */
export function findDirectoryTeam<D extends NameDirectory>(
  directory: D | undefined,
  team: Omit<DirectoryQuery, "code">,
): D["teams"][number] | null {
  const season = sameSeason(directory, team.year);
  if (!season) return null;
  const { teams } = season;
  const byId = team.id ? teams.find((entry) => entry.id === team.id) : undefined;
  if (byId) return byId;
  const name = foldName(team.name ?? "");
  if (!name) return null;
  const match = teams.find(
    (entry) =>
      foldName(entry.id) === name ||
      foldName(entry.name) === name ||
      foldName(entry.full_name) === name ||
      entry.aliases.includes(name),
  );
  return match ?? null;
}

/** f1db's surname for the driver: the payload's, else the directory's; null when neither has one. */
export function driverSurname(identity: DriverIdentity, directory?: NameDirectory): string | null {
  return present(identity.lastName) ?? present(findDirectoryDriver(directory, identity)?.last_name);
}

/** The driver's three-letter code: the payload's, else the directory's; null when neither has one. */
export function driverCode(identity: DriverIdentity, directory?: NameDirectory): string | null {
  return present(identity.code) ?? present(findDirectoryDriver(directory, identity)?.code);
}

/**
 * The text for a variant. `codeLast` reads surname then code ("Sainz Jr. SAI"),
 * the order of the mockups' table rows. Any part the data lacks falls back to
 * the full name.
 */
export function driverLabel(identity: DriverIdentity, variant: DriverNameVariant, directory?: NameDirectory): string {
  if (variant === "full") return identity.name;
  const last = driverSurname(identity, directory) ?? identity.name;
  if (variant === "last") return last;
  const code = driverCode(identity, directory);
  if (variant === "code") return code ?? identity.name;
  return code ? `${last} ${code}` : last;
}

/** f1db's name for the team (a feed's spelling resolved by alias), else the payload's own. */
export function teamLabel(team: TeamIdentity, variant: TeamNameVariant, directory?: NameDirectory): string {
  const match = findDirectoryTeam(directory, team);
  if (variant === "name") return match?.name ?? team.name;
  return present(team.fullName) ?? match?.full_name ?? team.name;
}
