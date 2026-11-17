/**
 * The clinch calculator's payload (`GET /api/race-control/standings/{year}/clinch`) and the one
 * sentence model every page prints from. The backend decides; nothing here works out who is alive.
 *
 * Drivers take singular verbs ("clinches", "outscores"), teams plural ones ("clinch", "outscore");
 * the leader is always "them". Points are whole from 2025, so they print with `String`.
 */

import { driverLabel, teamLabel } from "@/app/ui/names/names";

import type { StandingsFreshness } from "./standingsFreshness";

/** Which championship a table counts. */
export type ChampionshipTable = "drivers" | "constructors";

/** A rival the leader must outscore at the next event. */
export interface ClinchNeed {
  name: string;
  code: string | null;
  team: string;
  /** Outscore them by at least this; zero or less means "unless they outscore the leader by more than -margin". */
  margin: number;
  /** A finish exactly one point short of `margin` turns on the count-back, i.e. on the event's places. */
  countback: boolean;
}

export interface ClinchEvent {
  round: number;
  name: string;
  venue: string;
}

export interface NextEvent extends ClinchEvent {
  races: number;
  sprints: number;
  max_points: number;
  /** The leader can settle the title at this event. */
  possible: boolean;
  needs: ClinchNeed[];
}

export interface DecidedAt extends ClinchEvent {
  lead: number;
  left: number;
  races_to_spare: number;
  sprints_to_spare: number;
  provisional: boolean;
}

export interface ClinchLeader {
  name: string;
  code: string | null;
  team: string;
  points: number;
}

export interface TitleClinch {
  decided: boolean;
  leader: ClinchLeader;
  max_available: number;
  next: NextEvent | null;
  earliest: ClinchEvent | null;
  decided_at: DecidedAt | null;
}

export interface ClinchResponse extends StandingsFreshness {
  year: number;
  drivers: TitleClinch | null;
  constructors: TitleClinch | null;
}

export interface SentenceParts {
  strong: string;
  rest: string;
}

/** Who a clinch clause is about: a driver by `code`, a team by `name`. */
export interface ClinchEntrant {
  name: string;
  code?: string | null;
}

const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

const word = (n: number): string => WORDS[n] ?? String(n);

const plural = (n: number, noun: string): string => `${word(n)} ${noun}${n === 1 ? "" : "s"}`;

/** A contender in a sentence: the driver's full name, or the team's f1db name. */
export function contenderName(table: ChampionshipTable, name: string, code: string | null = null): string {
  return table === "constructors" ? teamLabel({ name }, "name") : driverLabel({ name, code }, "full");
}

interface Verbs {
  clinch: string;
  outscore: string;
  stay: string;
  has: string;
}

const verbs = (table: ChampionshipTable): Verbs =>
  table === "drivers"
    ? { clinch: "clinches", outscore: "outscores", stay: "stays", has: "has" }
    : { clinch: "clinch", outscore: "outscore", stay: "stay", has: "have" };

/** "A", "A and B", "A, B and C". */
function andList(items: string[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** What a rival needs to outscore the leader by to stay in it, given the leader's `margin` (zero or less). */
const outscoredBy = (need: ClinchNeed): number => (need.countback ? 2 - need.margin : 1 - need.margin);

function ifTheyOutscore(table: ChampionshipTable, needs: ClinchNeed[]): string {
  const positives = needs.filter((need) => need.margin > 0);
  if (positives.length === 0) return "";
  const clauses = positives.map((need) => {
    const back = need.countback ? ` (${need.margin - 1} on count-back)` : "";
    return `${contenderName(table, need.name, need.code)} by ${need.margin}${back}`;
  });
  return ` if they outscore ${andList(clauses)}`;
}

function unlessOutscored(table: ChampionshipTable, needs: ClinchNeed[], hasPositives: boolean): string {
  const rest = needs.filter((need) => need.margin <= 0);
  if (rest.length === 0) return "";
  const clauses = rest.map((need) => {
    const back = need.countback ? ` (${1 - need.margin} goes to count-back)` : "";
    return `${contenderName(table, need.name, need.code)} ${verbs(table).outscore} them by ${outscoredBy(need)} or more${back}`;
  });
  return `${hasPositives ? ", unless " : " unless "}${clauses.join(", or ")}`;
}

/** What the leader must do at the next event, against every rival still alive. */
export function nextEventSentence(
  table: ChampionshipTable,
  leader: { name: string; code: string | null },
  venue: string,
  needs: ClinchNeed[],
): string {
  const base = `${contenderName(table, leader.name, leader.code)} ${verbs(table).clinch} in ${venue}`;
  const hasPositives = needs.some((need) => need.margin > 0);
  return `${base}${ifTheyOutscore(table, needs)}${unlessOutscored(table, needs, hasPositives)}.`;
}

function spareText(decided: DecidedAt): string {
  const races = plural(decided.races_to_spare, "race");
  return decided.sprints_to_spare > 0 ? `${races} and ${plural(decided.sprints_to_spare, "sprint")}` : races;
}

const clinchedIn = (decided: DecidedAt): string =>
  `${decided.provisional ? "Provisionally clinched" : "Clinched"} in ${decided.venue}`;

const finalRound = (decided: DecidedAt): boolean => decided.races_to_spare === 0 && decided.sprints_to_spare === 0;

/** "Clinched in Mexico City" + " with four races to spare: 119 points clear, and only 100 left to win." */
export function decidedSentence(decided: DecidedAt): SentenceParts {
  const strong = clinchedIn(decided);
  if (finalRound(decided)) return { strong, rest: ` at the final round, ${decided.lead} points clear.` };
  return {
    strong,
    rest: ` with ${spareText(decided)} to spare: ${decided.lead} points clear, and only ${decided.left} left to win.`,
  };
}

/** The hero line under a championship: decided, can clinch next, or when it can at the earliest. */
export function heroSentence(table: ChampionshipTable, title: TitleClinch): SentenceParts | null {
  const leader = contenderName(table, title.leader.name, title.leader.code);
  if (title.decided) {
    return title.decided_at
      ? decidedSentence(title.decided_at)
      : { strong: `${leader} ${verbs(table).has} clinched the title`, rest: "." };
  }
  const { next, earliest } = title;
  if (next?.possible) return { strong: "", rest: nextEventSentence(table, title.leader, next.venue, next.needs) };
  if (next && earliest) {
    return {
      strong: "",
      rest: `The title can't be settled in ${next.venue}. ${leader} can clinch in ${earliest.venue} at the earliest.`,
    };
  }
  return null;
}

/** The short aside beside a championship's heading. */
export function clinchAside(table: ChampionshipTable, title: TitleClinch): string | null {
  const leader = contenderName(table, title.leader.name, title.leader.code);
  if (title.decided) {
    const { decided_at: at } = title;
    if (!at) return `${leader} ${verbs(table).has} clinched the title`;
    return `${leader} ${at.provisional ? "provisionally clinched" : "clinched"} in ${at.venue}`;
  }
  if (title.next?.possible) return `${leader} can clinch in ${title.next.venue}`;
  if (title.earliest) return `${leader} can clinch in ${title.earliest.venue} at the earliest`;
  return null;
}

/** A rival's side of a need: what keeps them in it. */
export function stayInItSentence(
  table: ChampionshipTable,
  leader: { name: string; code: string | null },
  need: ClinchNeed,
): string {
  const rival = contenderName(table, need.name, need.code);
  const lead = contenderName(table, leader.name, leader.code);
  if (need.margin > 0) {
    const back = need.countback ? ` (${need.margin - 1} goes to count-back)` : "";
    return `${rival} ${verbs(table).stay} in it unless ${lead} ${verbs(table).outscore} them by ${need.margin} or more${back}.`;
  }
  const back = need.countback ? ` (${1 - need.margin} goes to count-back)` : "";
  return `${rival} must outscore ${lead} by ${outscoredBy(need)} or more to stay in it${back}.`;
}

const isEntrant = (table: ChampionshipTable, entrant: ClinchEntrant, other: { name: string; code: string | null }) =>
  table === "drivers" ? entrant.code === other.code : entrant.name === other.name;

function leaderClause(title: TitleClinch): string | null {
  if (title.decided) {
    const at = title.decided_at;
    if (!at) return null;
    return `${clinchedIn(at)} ${finalRound(at) ? "at the final round" : `with ${spareText(at)} to spare`}.`;
  }
  if (title.next?.possible) return `Can clinch in ${title.next.venue}.`;
  return title.earliest ? `Can clinch in ${title.earliest.venue} at the earliest.` : null;
}

/** One entrant's own line on their team or driver page, or null when there is nothing to say. */
export function entrantClause(table: ChampionshipTable, title: TitleClinch, entrant: ClinchEntrant): string | null {
  if (isEntrant(table, entrant, title.leader)) return leaderClause(title);
  const next = title.next;
  const need = next?.needs.find((candidate) => isEntrant(table, entrant, candidate));
  if (!next || !need) return null;
  return need.margin <= next.max_points ? stayInItSentence(table, title.leader, need) : "Still in the title fight.";
}
