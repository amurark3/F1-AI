/**
 * What the Driver page says about a season, as pure functions of the profile
 * payload: the standing sentence, the KPI tiles, the last-five chips, the two
 * per-round charts and the teammate battle.
 *
 * A car that did not finish reads its status code and moves no places, even
 * when f1db classified it (docs/DATA_SOURCES.md, "Accuracy rules"). Every
 * title and caption here is computed from the data, never written by hand.
 */
import type { ColumnBarItem } from "@/app/ui/ColumnBars";
import { driverLabel } from "@/app/ui/names/names";
import { rc } from "@/app/ui/tokens";

import { finishSentence, isFinished, statusCode } from "../../profiles/finishes";
import {
  formatPoints,
  type DriverProfile,
  type DriverRound,
  type Finish,
  type Teammate,
} from "../../profiles/profilesModel";

export interface DriverKpi {
  value: number;
  unit?: string;
  sub: string;
}

export interface DriverKpiSet {
  podiums: DriverKpi;
  wins: DriverKpi;
  poles: DriverKpi;
  fastestLaps: DriverKpi;
}

export type FormTone = "win" | "podium" | "plain" | "out";

export interface FormChip {
  axis: string;
  /** "1", "9", or the status code of a car that did not finish. */
  text: string;
  tone: FormTone;
  sentence: string;
}

export interface HeadToHead {
  teammate: Teammate;
  /** Rounds one car finished ahead of the other. */
  compared: number;
  ahead: number;
  behind: number;
  /** Rounds neither car finished: counted for neither. */
  bothOut: number;
  gridAhead: number;
  gridBehind: number;
  notCounted: string[];
}

const NONE = "—";

function raced(profile: DriverProfile): DriverRound[] {
  return profile.rounds.filter((round) => round.status === "complete" && round.race !== null);
}

export function surname(profile: DriverProfile): string {
  const { driver, year } = profile;
  return driverLabel({ name: driver.name, lastName: driver.last_name, code: driver.code, id: driver.id, year }, "last");
}

export function otherLabel(
  profile: DriverProfile,
  other: { id: string; name: string; last_name: string; code: string | null },
) {
  return driverLabel(
    { name: other.name, lastName: other.last_name, code: other.code, id: other.id, year: profile.year },
    "last",
  );
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function roundList(rounds: readonly number[]): string {
  return rounds.map((round) => `R${round}`).join(", ");
}

function label(round: DriverRound): string {
  return `R${round.round} ${round.short_name}`;
}

/** The sentence under the hero's name: place, points and the gap that matters. */
export function standingLine(profile: DriverProfile): string {
  const { standing, rivals } = profile;
  const points = formatPoints(standing.points);
  if (standing.position === null) return `${points} points`;
  if (standing.position === 1) return leaderLine(profile, points);
  const head = `P${standing.position} in the championship · ${points} points`;
  if (!rivals.ahead) return head;
  const gap = rivals.ahead.points - standing.points;
  const name = otherLabel(profile, rivals.ahead);
  return gap === 0 ? `${head} · level with ${name} on points` : `${head} · ${formatPoints(gap)} behind ${name}`;
}

function leaderLine(profile: DriverProfile, points: string): string {
  const head = `Leads the championship · ${points} points`;
  const { behind } = profile.rivals;
  if (!behind) return head;
  const gap = profile.standing.points - behind.points;
  const name = otherLabel(profile, behind);
  if (gap === 0) return `${head} · level with ${name} on points`;
  const left = profile.rounds.filter((round) => round.status === "pending").length;
  const clause = left === 0 ? "" : ` with ${plural(left, "race")} left`;
  return `${head} · ${formatPoints(gap)} clear of ${name}${clause}`;
}

function racesWhere(profile: DriverProfile, matches: (race: Finish) => boolean): DriverRound[] {
  return raced(profile).filter((round) => matches(round.race!));
}

function winSub(profile: DriverProfile): string {
  const { wins } = profile;
  if (wins.length === 0) return NONE;
  return wins.length === 1 ? `Round ${wins[0].round}` : roundList(wins.map((win) => win.round));
}

function poleSub(profile: DriverProfile): string {
  const poles = racesWhere(profile, (race) => race.pole);
  if (poles.length === 0) return NONE;
  return poles.length === 1 ? `${poles[0].short_name} (R${poles[0].round})` : roundList(poles.map((p) => p.round));
}

function retirementSub(profile: DriverProfile): string {
  const out = racesWhere(profile, (race) => race.status === "dnf");
  if (out.length === 0) return "No retirements";
  if (out.length === 1) return `1 retirement (${out[0].short_name})`;
  return `${out.length} retirements (${roundList(out.map((round) => round.round))})`;
}

function podiumSub(profile: DriverProfile): string {
  const { wins } = profile;
  if (wins.length === 0) return "No wins";
  return wins.length === 1 ? `Win: ${wins[0].short_name} (R${wins[0].round})` : `${wins.length} wins`;
}

export function driverKpis(profile: DriverProfile): DriverKpiSet {
  const { stats } = profile;
  return {
    podiums: { value: stats.podiums, unit: `of ${stats.starts}`, sub: podiumSub(profile) },
    wins: { value: stats.wins, sub: winSub(profile) },
    poles: { value: stats.poles, sub: poleSub(profile) },
    fastestLaps: { value: stats.fastest_laps, sub: retirementSub(profile) },
  };
}

function formTone(race: Finish): FormTone {
  if (!isFinished(race)) return "out";
  if (race.position === 1) return "win";
  return race.position === 2 || race.position === 3 ? "podium" : "plain";
}

/** The last five completed races, oldest first. */
export function formGuide(profile: DriverProfile): FormChip[] {
  return raced(profile)
    .slice(-5)
    .map((round) => {
      const race = round.race!;
      return {
        axis: `R${round.round}`,
        text: isFinished(race) ? String(race.position) : statusCode(race),
        tone: formTone(race),
        sentence: finishSentence(label(round), race),
      };
    });
}

function signed(places: number): string {
  if (places === 0) return "0";
  return places < 0 ? `−${Math.abs(places)}` : `+${places}`;
}

function noRace(round: DriverRound): ColumnBarItem {
  return {
    id: String(round.round),
    axis: `R${round.round}`,
    value: null,
    marker: NONE,
    markerTone: "muted",
    description: `${label(round)}: did not race`,
  };
}

function outColumn(round: DriverRound, race: Finish): ColumnBarItem {
  return {
    id: String(round.round),
    axis: `R${round.round}`,
    value: null,
    marker: statusCode(race),
    markerTone: "alert",
    description: finishSentence(label(round), race),
  };
}

function gainColor(places: number): string | undefined {
  if (places > 0) return rc.gain;
  return places < 0 ? rc.redText : undefined;
}

function gridColumn(round: DriverRound): ColumnBarItem {
  const race = round.race;
  if (race === null) return noRace(round);
  if (!isFinished(race)) return outColumn(round, race);
  const places = race.positions_gained;
  if (places === null) return { ...noRace(round), description: finishSentence(label(round), race) };
  return {
    id: String(round.round),
    axis: `R${round.round}`,
    value: places,
    valueText: signed(places),
    color: gainColor(places),
    description: finishSentence(label(round), race),
  };
}

/** Places gained or lost in each completed round; a retirement shows its code and moves nothing. */
export function gridColumns(profile: DriverProfile): ColumnBarItem[] {
  return profile.rounds.filter((round) => round.status === "complete").map(gridColumn);
}

export function gridTitle(profile: DriverProfile): string {
  const total = raced(profile)
    .filter((round) => isFinished(round.race!))
    .reduce((sum, round) => sum + (round.race!.positions_gained ?? 0), 0);
  const name = surname(profile);
  if (total === 0) return `${name}: places gained and lost cancel out`;
  return `${name} ${total > 0 ? "gained" : "lost"} ${plural(Math.abs(total), "place")} over the season`;
}

function spellColor(profile: DriverProfile, round: DriverRound): string {
  return profile.teams.find((spell) => spell.id === round.team_id)?.color ?? profile.driver.color;
}

function pointsColumn(profile: DriverProfile, round: DriverRound): ColumnBarItem {
  const race = round.race;
  if (race === null) return noRace(round);
  if (!isFinished(race) && race.points === 0) return outColumn(round, race);
  const won = isFinished(race) && race.position === 1;
  return {
    id: String(round.round),
    axis: `R${round.round}`,
    value: race.points,
    valueText: formatPoints(race.points),
    color: won ? rc.gold : spellColor(profile, round),
    description: finishSentence(label(round), race),
  };
}

/** Grand Prix points of each completed round: gold for a win, else the colour of that round's team. */
export function pointsColumns(profile: DriverProfile): ColumnBarItem[] {
  return profile.rounds.filter((round) => round.status === "complete").map((round) => pointsColumn(profile, round));
}

/** The top of the points scale: a win, or more for a double-points haul. */
export function pointsScale(profile: DriverProfile): number {
  return Math.max(25, ...raced(profile).map((round) => round.race!.points));
}

export function pointsTitle(profile: DriverProfile): string {
  const races = raced(profile);
  const scored = races.filter((round) => round.race!.points > 0).length;
  const count = plural(races.length, "race");
  return scored === 0 ? `No points yet in ${count}` : `Scored in ${scored} of ${count}`;
}

/** Finishing order key: a car that did not finish is behind every one that did. */
function finishRank(race: Finish): number {
  return isFinished(race) && race.position !== null ? race.position : Number.POSITIVE_INFINITY;
}

/** Starting order key: a pit-lane start, or no grid slot, is behind the whole grid. */
function gridRank(race: Finish): number {
  return race.pit_lane || race.grid === null ? Number.POSITIVE_INFINITY : race.grid;
}

function compare(own: number, other: number): "ahead" | "behind" | "level" {
  if (own === other) return "level";
  return own < other ? "ahead" : "behind";
}

interface Tally {
  ahead: number;
  behind: number;
  bothOut: number;
  gridAhead: number;
  gridBehind: number;
}

function didNotStart(profile: DriverProfile, mine: Finish, round: DriverRound, mate: Teammate): string | null {
  if (mine.status === "dns") return `Not counted: R${round.round} (${surname(profile)} did not start).`;
  if (round.teammate!.race.status === "dns")
    return `Not counted: R${round.round} (${otherLabel(profile, mate)} did not start).`;
  return null;
}

function tallyRound(tally: Tally, mine: Finish, theirs: Finish): Tally {
  const finish = compare(finishRank(mine), finishRank(theirs));
  const grid = compare(gridRank(mine), gridRank(theirs));
  const bothOut = !isFinished(mine) && !isFinished(theirs);
  return {
    ahead: tally.ahead + (finish === "ahead" ? 1 : 0),
    behind: tally.behind + (finish === "behind" ? 1 : 0),
    bothOut: tally.bothOut + (bothOut ? 1 : 0),
    gridAhead: tally.gridAhead + (grid === "ahead" ? 1 : 0),
    gridBehind: tally.gridBehind + (grid === "behind" ? 1 : 0),
  };
}

/** The main teammate's season-long battle: finishing order and starting order, round by round. */
export function headToHead(profile: DriverProfile): HeadToHead | null {
  const mate = profile.teammates[0];
  if (!mate) return null;
  const notCounted = profile.teammates
    .slice(1)
    .map((other) => `Not counted: ${other.rounds_label} alongside ${otherLabel(profile, other)}.`);
  let tally: Tally = { ahead: 0, behind: 0, bothOut: 0, gridAhead: 0, gridBehind: 0 };
  let together = 0;
  for (const round of raced(profile).filter((item) => item.teammate?.driver_id === mate.id)) {
    const note = didNotStart(profile, round.race!, round, mate);
    if (note !== null) {
      notCounted.push(note);
      continue;
    }
    together += 1;
    tally = tallyRound(tally, round.race!, round.teammate!.race);
  }
  if (together === 0) return null;
  return { teammate: mate, compared: tally.ahead + tally.behind, notCounted, ...tally };
}

export function h2hTitle(profile: DriverProfile, h2h: HeadToHead): string {
  return `${surname(profile)} finished ahead ${plural(h2h.ahead, "time")} in ${h2h.compared}`;
}

/** The counting rule, in words, for the card's footnote. */
export function h2hRule(h2h: HeadToHead): string {
  const rule =
    "A retirement or disqualification counts as finishing behind; a pit-lane start counts as starting behind.";
  return h2h.bothOut === 0 ? rule : `${rule} Both out in ${plural(h2h.bothOut, "race")}: counted for neither.`;
}
