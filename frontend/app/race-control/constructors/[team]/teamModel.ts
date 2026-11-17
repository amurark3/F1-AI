/**
 * What the Team page says about a team's season, as pure functions of the
 * profile payload: the standing sentence, the KPI tiles, each heat-grid cell
 * and the points-by-weekend title.
 *
 * Counts read the team's **race** finishes of completed rounds, through the
 * status the backend sets, so a classified retirement is a retirement.
 */
import { driverLabel, teamLabel } from "@/app/ui/names/names";

import {
  formatPoints,
  type Finish,
  type TeamProfile,
  type TeamRound,
  type TeamRoundResult,
} from "../../profiles/profilesModel";

export type HeatKind = "future" | "absent" | "out" | "p1" | "p2" | "p3" | "points" | "plain";

export interface HeatCell {
  kind: HeatKind;
  finish: Finish | null;
}

export interface Kpi {
  value: number;
  unit?: string;
  sub: string;
}

export interface TeamKpiSet {
  wins: Kpi;
  podiums: Kpi;
  poles: Kpi;
  retirements: Kpi;
}

const NONE = "None";

function completed(profile: TeamProfile): TeamRound[] {
  return profile.rounds.filter((round) => round.status === "complete");
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** The sentence under the hero's place: the points and the gap to the team that matters. */
export function standingLine(profile: TeamProfile): string {
  const { team, rivals, year } = profile;
  const points = formatPoints(team.points);
  const name = (rival: { id: string; name: string }) => teamLabel({ id: rival.id, name: rival.name, year }, "name");
  if (team.position === 1 && rivals.behind) {
    const gap = team.points - rivals.behind.points;
    if (gap === 0) return `${points} points, level with ${name(rivals.behind)}.`;
    const left = profile.rounds.filter((round) => round.status === "pending").length;
    const clause = left === 0 ? "" : ` with ${plural(left, "round")} to run`;
    return `${points} points, ${formatPoints(gap)} clear of ${name(rivals.behind)}${clause}.`;
  }
  if (team.position !== null && team.position > 1 && rivals.ahead) {
    const gap = rivals.ahead.points - team.points;
    if (gap === 0) return `${points} points, level with ${name(rivals.ahead)}.`;
    return `${points} points, ${formatPoints(gap)} behind ${name(rivals.ahead)}.`;
  }
  return `${points} points.`;
}

interface Tally {
  id: string;
  label: string;
  count: number;
  rounds: number[];
}

/** Each listed driver's count of the races `matches` picks, in the profile's driver order. */
function tally(profile: TeamProfile, matches: (finish: Finish) => boolean): Tally[] {
  const known = new Map(profile.drivers.map((driver) => [driver.id, driver]));
  const byId = new Map<string, Tally>();
  for (const round of completed(profile)) {
    for (const result of round.results) {
      if (!result.race || !matches(result.race)) continue;
      const driver = known.get(result.driver_id);
      const label = driver
        ? driverLabel(
            { name: driver.name, lastName: driver.last_name, code: driver.code, id: driver.id, year: profile.year },
            "last",
          )
        : result.driver_id;
      const row = byId.get(result.driver_id) ?? { id: result.driver_id, label, count: 0, rounds: [] };
      byId.set(result.driver_id, { ...row, count: row.count + 1, rounds: [...row.rounds, round.round] });
    }
  }
  const order = (id: string) => profile.drivers.findIndex((driver) => driver.id === id);
  return [...byId.values()].sort((a, b) => order(a.id) - order(b.id));
}

function total(rows: Tally[]): number {
  return rows.reduce((sum, row) => sum + row.count, 0);
}

function byCount(rows: Tally[]): string {
  if (rows.length === 0) return NONE;
  return [...rows]
    .sort((a, b) => b.count - a.count)
    .map((row) => `${row.label} ${row.count}`)
    .join(" · ");
}

function byRound(rows: Tally[]): string {
  if (rows.length === 0) return NONE;
  return rows.map((row) => `${row.label} ${row.rounds.map((round) => `R${round}`).join(", ")}`).join(" · ");
}

export function teamKpis(profile: TeamProfile): TeamKpiSet {
  const won = tally(profile, (race) => race.status === "finished" && race.position === 1);
  const podiums = tally(profile, (race) => race.status === "finished" && (race.position ?? 99) <= 3);
  const poles = tally(profile, (race) => race.pole);
  const out = tally(profile, (race) => race.status === "dnf");
  const starts = total(tally(profile, (race) => race.status !== "dns"));
  return {
    wins: { value: total(won), unit: `of ${completed(profile).length}`, sub: byCount(won) },
    podiums: { value: total(podiums), sub: `of ${starts} starts` },
    poles: { value: total(poles), sub: byCount(poles) },
    retirements: { value: total(out), sub: byRound(out) },
  };
}

/** A driver's race wins and pole positions for the team over completed rounds. */
export function driverRecord(profile: TeamProfile, driverId: string): { wins: number; poles: number } {
  const races = completed(profile).flatMap((round) =>
    round.results.filter((result) => result.driver_id === driverId && result.race).map((result) => result.race!),
  );
  return {
    wins: races.filter((race) => race.status === "finished" && race.position === 1).length,
    poles: races.filter((race) => race.pole).length,
  };
}

const PODIUM: Record<number, HeatKind> = { 1: "p1", 2: "p2", 3: "p3" };

/** How one driver's race of one round paints on the heat grid. */
export function heatCell(round: TeamRound, result: TeamRoundResult | undefined): HeatCell {
  if (round.status === "pending") return { kind: "future", finish: null };
  const finish = result?.race ?? null;
  if (!finish) return { kind: "absent", finish: null };
  if (finish.status !== "finished") return { kind: "out", finish };
  const podium = finish.position === null ? undefined : PODIUM[finish.position];
  if (podium) return { kind: podium, finish };
  return { kind: finish.points > 0 ? "points" : "plain", finish };
}

/** The finding over the points-by-weekend chart. */
export function weekendTitle(profile: TeamProfile): string {
  const done = completed(profile);
  const scored = done.filter((round) => round.points > 0).length;
  if (scored === 0) return "No points yet";
  const first = scored === done.length ? "Scored in every round" : `Scored in ${scored} of ${done.length} rounds`;
  const best = Math.max(...done.map((round) => round.points));
  const winners = done.filter((round) => round.points === best);
  const tied = winners.length > 1 ? " (tied)" : "";
  return `${first}; the ${winners[0]?.short_name} was the biggest haul${tied}`;
}
