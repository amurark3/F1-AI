/**
 * What the Teams index says about each team, computed from its payload: the
 * title, the gap to the leader and how the team's points split between its
 * drivers. Pure, so every sentence on the page is tested.
 */

import { driverLabel } from "@/app/ui/names/names";

import { formatPoints, type TeamsIndexDriver, type TeamsIndexTeam } from "../profiles/profilesModel";

const COUNT_WORDS = [
  "Zero",
  "One",
  "Two",
  "Three",
  "Four",
  "Five",
  "Six",
  "Seven",
  "Eight",
  "Nine",
  "Ten",
  "Eleven",
  "Twelve",
  "Thirteen",
  "Fourteen",
  "Fifteen",
  "Sixteen",
  "Seventeen",
  "Eighteen",
  "Nineteen",
  "Twenty",
];

const FULL_SHARE = 100;
/** The runners-up in a team's bar, set back from the top scorer. */
const SECONDARY_OPACITY = 0.45;

/** "Eleven teams"; digits above twenty. */
export function teamsTitle(count: number): string {
  const amount = COUNT_WORDS[count] ?? String(count);
  return `${amount} ${count === 1 ? "team" : "teams"}`;
}

/** "Leader", "−142" (a true minus) or "Unranked". */
export function gapLabel(team: TeamsIndexTeam, leader: TeamsIndexTeam): string {
  if (team.position === null) return "Unranked";
  if (team.position === 1) return "Leader";
  return `−${formatPoints(leader.points - team.points)}`;
}

export interface ShareSegment {
  driver: TeamsIndexDriver;
  points: number;
  /** Of the drivers' points, 0 to 100. */
  percent: number;
  /** The top scorer reads at full strength; the rest are set back. */
  opacity: number;
}

function scorers(team: TeamsIndexTeam): TeamsIndexDriver[] {
  return team.drivers.filter((driver) => driver.points > 0);
}

/** One segment per driver who scored for the team, widest first. */
export function shareSegments(team: TeamsIndexTeam): ShareSegment[] {
  const total = team.drivers.reduce((sum, driver) => sum + driver.points, 0);
  return scorers(team).map((driver, index) => ({
    driver,
    points: driver.points,
    percent: (driver.points / total) * FULL_SHARE,
    opacity: index === 0 ? 1 : SECONDARY_OPACITY,
  }));
}

function surname(driver: TeamsIndexDriver, year: number): string {
  return driverLabel({ name: driver.name, lastName: driver.last_name, code: driver.code, id: driver.id, year }, "last");
}

/** The one line under a team's bar. */
export function shareNote(team: TeamsIndexTeam, year: number): string {
  const [top, second] = scorers(team);
  if (!top) return "No points yet";
  const total = team.drivers.reduce((sum, driver) => sum + driver.points, 0);
  if (second?.points === top.points) {
    return `${surname(top, year)} and ${surname(second, year)} level on ${formatPoints(top.points)}`;
  }
  if (top.points === total) return `${surname(top, year)} scored all ${formatPoints(total)} points`;
  return `${surname(top, year)} scored ${Math.round((top.points / total) * FULL_SHARE)}% of the points`;
}

/** The share bar's accessible name: "Points split: Verstappen 279, Hadjar 122, Lawson 14". */
export function shareLabel(team: TeamsIndexTeam, year: number): string {
  const parts = shareSegments(team).map(({ driver, points }) => `${surname(driver, year)} ${formatPoints(points)}`);
  return `Points split: ${parts.join(", ")}`;
}

/** A driver who missed part of the season shows which rounds they raced for the team. */
export function showRounds(driver: TeamsIndexDriver, through: number): boolean {
  return driver.rounds_label !== "" && driver.rounds.length < through;
}
