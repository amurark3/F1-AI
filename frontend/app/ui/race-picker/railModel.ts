/**
 * The season as a timeline (`grand-prix.html`'s race picker): each round
 * placed by its race day, coloured by the team that won it.
 *
 * Pure and server-safe. Dates are read in UTC on purpose: the schedule's
 * `date` is the race day at the circuit, and a reader's local clock would
 * also differ between the server render and the browser's first pass.
 */

import type { RaceWinner } from "@/app/lib/server/champions";
import { NEUTRAL_TEAM_COLOR, getTeamColor } from "@/app/lib/teamColors";
import type { RaceEvent } from "@/app/race-control/grand-prix/predictionModel";
import { driverLabel, teamLabel } from "@/app/ui/names/names";

/** Won: the winner is published. Awaiting: run or running, no winner yet. Upcoming: not started. */
export type TickState = "won" | "awaiting" | "upcoming";

export interface RailTick {
  race: RaceEvent;
  /** Distance along the rail, in percent. */
  left: number;
  state: TickState;
  /** The winning team's colour; null when there is no winner to show. */
  color: string | null;
  /** "R19 · Mexico City GP". */
  title: string;
  /** Who won, or where the round stands. */
  detail: string;
}

export interface RailMonth {
  /** "MAR". */
  label: string;
  left: number;
}

export interface SeasonRail {
  ticks: RailTick[];
  months: RailMonth[];
}

/**
 * How near either end a tip stops centring on its tick and aligns to that end,
 * in percent: half a tip's width on the narrowest rail, beside a long header.
 */
const TIP_EDGE = 25;

// en-US: en-GB abbreviates September to "Sept", and the mockups print three letters for every month.
const MONTH = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });

/** The race day as a timestamp; NaN when the payload has none. */
function raceTime(race: RaceEvent): number {
  return Date.parse(race.date ?? "");
}

/** "8 Nov", the race day at the circuit. */
export function raceDay(race: RaceEvent): string {
  const time = raceTime(race);
  return Number.isNaN(time) ? "date TBC" : `${new Date(time).getUTCDate()} ${MONTH.format(time)}`;
}

/** "São Paulo Grand Prix" reads "São Paulo GP", as on the timing screens. */
export function shortRaceName(name: string): string {
  return name.replace(/\bGrand Prix\b/, "GP");
}

/** A winner's colour and line. f1db joins the team loosely, so a result may come without one. */
function winnerMark(winner: RaceWinner): Pick<RailTick, "color" | "detail"> {
  const name = driverLabel({ name: winner.winner, id: winner.driver_id }, "full");
  if (winner.team === null) return { color: NEUTRAL_TEAM_COLOR, detail: `${name} won` };
  const team = teamLabel({ name: winner.team, id: winner.team_id }, "name");
  return { color: getTeamColor(team), detail: `${name} won · ${team}` };
}

function tickFor(race: RaceEvent, winner: RaceWinner | undefined, winnersKnown: boolean): Omit<RailTick, "left"> {
  const title = `R${race.round} · ${shortRaceName(race.name)}`;
  const base = { race, title, color: null };
  if (winner) return { ...base, state: "won", ...winnerMark(winner) };
  if (race.status === "upcoming") return { ...base, state: "upcoming", detail: `Race day ${raceDay(race)}` };
  if (race.status !== "completed") return { ...base, state: "awaiting", detail: "Race weekend under way" };
  // Without the winners there is no knowing whether one is published, so claim nothing.
  return { ...base, state: "awaiting", detail: winnersKnown ? "Winner not published yet" : "Completed" };
}

/** The first of the month `time` falls in. */
function monthStart(time: number): number {
  const date = new Date(time);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1);
}

function nextMonth(time: number): number {
  const date = new Date(time);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1);
}

function months(start: number, end: number, place: (time: number) => number): RailMonth[] {
  const marks: RailMonth[] = [];
  for (let month = start; month < end; month = nextMonth(month)) {
    marks.push({ label: MONTH.format(month).toUpperCase(), left: place(month) });
  }
  return marks;
}

/**
 * Every round on one rail, in whole months: from the first of the opening
 * race's month to the end of the finale's, so every month's label has room. A round with no date (none should lack one) would
 * have nowhere to go, so then the rounds are spaced evenly with no months.
 */
export function seasonRail(races: readonly RaceEvent[], winners: readonly RaceWinner[] | undefined): SeasonRail {
  if (races.length === 0) return { ticks: [], months: [] };
  const byRound = new Map((winners ?? []).map((winner) => [winner.round, winner]));
  const times = races.map(raceTime);
  const described = races.map((race) => tickFor(race, byRound.get(race.round), winners !== undefined));
  if (times.some(Number.isNaN)) {
    const even = described.map((tick, index) => ({ ...tick, left: ((index + 0.5) / races.length) * 100 }));
    return { ticks: even, months: [] };
  }
  const start = monthStart(Math.min(...times));
  const end = nextMonth(Math.max(...times));
  const place = (time: number) => ((time - start) / (end - start)) * 100;
  return {
    ticks: described.map((tick, index) => ({ ...tick, left: place(times[index]) })),
    months: months(start, end, place),
  };
}

/** A round's accessible name, the tip's two lines in one: "R19 · Mexico City GP, Max Verstappen won · Red Bull". */
export function tickLabel(tick: RailTick): string {
  return `${tick.title}, ${tick.detail}`;
}

/** Where a tip hangs from its tick: centred, or aligned to the rail's end so it never spills off it. */
export function tipAlign(left: number): "start" | "center" | "end" {
  if (left < TIP_EDGE) return "start";
  return left > 100 - TIP_EDGE ? "end" : "center";
}
