/**
 * The Standings page's pure model: what the hero says, the tiles beside it,
 * and the small helpers the lists share. No title arithmetic happens here:
 * "decided" is the backend's (`stakes.<table>.decided`, or the progression's
 * `clinched`).
 */

import type { StandingsFreshness } from "@/app/lib/standingsFreshness";
import { getTeamColor } from "@/app/lib/teamColors";
import type { ChampionshipTable } from "@/app/race-control/weekend/weekendModel";
import type { ChampionshipStakes } from "@/app/race-control/weekend/weekendTypes";
import { driverLabel, teamLabel, type NameDirectory } from "@/app/ui/names/names";

import { formatPoints, type DriverStanding, type TeamsResponse } from "./teamsModel";

/** One round of the season, as `/standings/{year}/progression` lists it. */
export interface ProgressionRound {
  round: number;
  name: string | null;
  location: string | null;
  sprint: boolean | null;
  provisional: boolean;
}

/** One driver's or team's points and place after each round; null before the first round they had a row. */
export interface ProgressionEntrant {
  key: string;
  name: string;
  team: string;
  points: Array<number | null>;
  positions: Array<number | null>;
}

export interface Clinched {
  round: number;
  races_left: number | null;
  sprints_left: number | null;
}

export interface ProgressionTable {
  entrants: ProgressionEntrant[];
  clinched: Clinched | null;
}

export interface StandingsProgression extends StandingsFreshness {
  year: number;
  rounds: ProgressionRound[];
  drivers: ProgressionTable;
  constructors: ProgressionTable;
  error?: string | null;
}

/** Both come from the same title rule on the backend. */
export function isDecided(
  table: ChampionshipTable,
  stakes?: ChampionshipStakes | null,
  progression?: StandingsProgression | null,
): boolean {
  return stakes?.[table]?.decided === true || progression?.[table].clinched != null;
}

/** The city of a round's location, or "round N" when the calendar is missing. */
export function venueOf(rounds: readonly ProgressionRound[], round: number): string {
  const location = rounds.find((r) => r.round === round)?.location;
  return location ? location.split(",")[0] : `round ${round}`;
}

/** Splits rows into two columns to read down: the first takes the odd one. */
export function columnsOf<T>(rows: readonly T[]): [T[], T[]] {
  const half = Math.ceil(rows.length / 2);
  return [rows.slice(0, half), rows.slice(half)];
}

/** The gap column: a dash for the leader, otherwise the gap with a true minus. */
export function gapAside(points: number, leaderPoints: number, index: number): string {
  return index === 0 ? "—" : `−${formatPoints(leaderPoints - points)}`;
}

/** A row of either championship, in one shape. */
interface StandingRow {
  name: string;
  code?: string;
  team: string;
  points: number;
  wins: number;
}

function rowsOf(table: ChampionshipTable, teams: TeamsResponse): StandingRow[] {
  if (table === "constructors")
    return teams.teams.map((t) => ({ name: t.name, team: t.name, points: t.points, wins: t.wins }));
  return (teams.drivers ?? []).map((d: DriverStanding) => ({
    name: d.driver,
    code: d.code,
    team: d.team,
    points: d.points,
    wins: d.wins,
  }));
}

export interface HeroTile {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
}

export interface HeroModel {
  decided: boolean;
  eyebrow: string;
  figure: string;
  leader: { name: string; code?: string };
  /** The team's colour beside the meta line; drivers only. */
  swatch: string | null;
  meta: string;
  line: string;
  tiles: HeroTile[];
}

export interface HeroContext {
  year: number;
  stakes?: ChampionshipStakes | null;
  progression?: StandingsProgression | null;
  directory?: NameDirectory;
}

const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? "" : "s"}`;

function shortName(table: ChampionshipTable, row: { name: string; code?: string | null }, directory?: NameDirectory) {
  return table === "constructors"
    ? teamLabel({ name: row.name }, "name", directory)
    : driverLabel({ name: row.name, code: row.code }, "last", directory);
}

function leadLine(table: ChampionshipTable, rows: StandingRow[], round: number, directory?: NameDirectory): string {
  const lead = rows[0].points - rows[1].points;
  const second = shortName(table, rows[1], directory);
  if (lead === 0) return `Level on points with ${second}, ahead on count-back.`;
  return `${formatPoints(lead)} points clear of ${second} after round ${round}.`;
}

function racesLeftTile(stakes: ChampionshipStakes): HeroTile {
  const { races_left: races, sprints_left: sprints } = stakes;
  let sub = plural(sprints, "sprint");
  if (races === 0) sub = "season complete";
  else if (sprints === 0) sub = "no sprints";
  return { label: "Races left", value: String(races), sub };
}

/** The tile beside the leader: the fight for second when decided, the rivals in reach while open. */
function contestTile(
  table: ChampionshipTable,
  rows: StandingRow[],
  decided: boolean,
  ctx: HeroContext,
): HeroTile | null {
  const { directory } = ctx;
  const stakes = ctx.stakes?.[table];
  if (decided) {
    const chase = rows.slice(1, 5);
    if (chase.length < 2) return null;
    return {
      label: "Fight for second",
      value: formatPoints(chase[0].points - chase[chase.length - 1].points),
      unit: "pts",
      sub: chase.map((r) => shortName(table, r, directory)).join(", "),
    };
  }
  if (!stakes) return null;
  const listed = stakes.contenders.filter((c) => c.alive && c.position > 1);
  const more = stakes.rivals_alive - listed.length;
  const names = listed.map((c) => shortName(table, c, directory)).join(", ");
  return {
    label: "Rivals in reach",
    value: String(stakes.rivals_alive),
    sub: more > 0 ? `${names} +${more} more` : names,
  };
}

/** The other championship's lead, as a tile. */
function otherTile(table: ChampionshipTable, teams: TeamsResponse, ctx: HeroContext): HeroTile | null {
  const other: ChampionshipTable = table === "drivers" ? "constructors" : "drivers";
  const rows = rowsOf(other, teams);
  if (rows.length < 2) return null;
  const first = shortName(other, rows[0], ctx.directory);
  const base = isDecided(other, ctx.stakes, ctx.progression)
    ? `${first} clinched`
    : `${first} over ${shortName(other, rows[1], ctx.directory)}`;
  const left = ctx.stakes?.[other]?.max_available;
  return {
    label: other === "drivers" ? "Drivers" : "Constructors",
    value: formatPoints(rows[0].points - rows[1].points),
    unit: "pts",
    sub: left === undefined ? base : `${base} · ${formatPoints(left)} left`,
  };
}

/**
 * The hero for one championship, or null when the table has no two rows or no
 * round yet. The line is the plain lead: the clinch sentence is P5.3b's.
 */
export function heroModel(table: ChampionshipTable, teams: TeamsResponse, ctx: HeroContext): HeroModel | null {
  const rows = rowsOf(table, teams);
  const round = teams.as_of_round;
  if (rows.length < 2 || !round) return null;

  const decided = isDecided(table, ctx.stakes, ctx.progression);
  const [leader] = rows;
  const drivers = table === "drivers";
  const record = `${plural(leader.wins, "win")} from ${plural(round, "race")}`;
  const tiles = [
    contestTile(table, rows, decided, ctx),
    otherTile(table, teams, ctx),
    ctx.stakes ? racesLeftTile(ctx.stakes) : null,
  ];

  let eyebrow = drivers ? "Championship leader" : "Constructors' leader";
  if (decided) eyebrow = drivers ? `${ctx.year} World Champion` : `${ctx.year} Constructors' Champion`;

  return {
    decided,
    eyebrow,
    figure: formatPoints(leader.points),
    leader: { name: leader.name, code: leader.code },
    swatch: drivers ? getTeamColor(leader.team) : null,
    meta: drivers ? `${teamLabel({ name: leader.team }, "name", ctx.directory)} · ${record}` : record,
    line: leadLine(table, rows, round, ctx.directory),
    tiles: tiles.filter((t): t is HeroTile => t !== null),
  };
}
