/** Selection and wording for the race debrief, computed from the summary payload and nothing else. */

import { getTeamColor } from "@/app/lib/teamColors";
import { driverLabel, type NameDirectory } from "@/app/ui/names/names";
import type { SlopeItem } from "@/app/ui/SlopeChart";

import type { DebriefRow, DebriefSummary, DebriefTitle } from "./debriefTypes";
import type { RaceEvent } from "../grand-prix/predictionModel";

/** The races of the season that have been run, in calendar order. */
export function completedRaces(races: readonly RaceEvent[]): RaceEvent[] {
  return races.filter((race) => race.status === "completed");
}

/** The round the page opens on: the latest completed race, or null before any has run. */
export function resolveDefaultDebriefRace(races: readonly RaceEvent[]): RaceEvent | null {
  return completedRaces(races).at(-1) ?? null;
}

/** An explicit round can have a result while the calendar still calls it in progress. */
export function resolveDebriefRound(races: readonly RaceEvent[], requested: number | null): number | null {
  const selected = races.find((race) => race.round === requested && race.status !== "upcoming");
  return selected?.round ?? resolveDefaultDebriefRace(races)?.round ?? null;
}

/** Keep the archive's completed rounds and the explicit selection, in calendar order. */
export function debriefPickerRaces(races: readonly RaceEvent[], round: number): RaceEvent[] {
  return races.filter((race) => race.status === "completed" || race.round === round);
}

/** A driver's surname for a sentence, by the names rule (`ui/names`). */
export function lastOf(row: Pick<DebriefRow, "driver_code" | "driver_name">, directory?: NameDirectory): string {
  return driverLabel({ name: row.driver_name, code: row.driver_code }, "last", directory);
}

function placed(summary: DebriefSummary, position: number): DebriefRow | undefined {
  return summary.classification.find((row) => row.position === position);
}

export function podiumOf(
  summary: DebriefSummary,
): [DebriefRow | undefined, DebriefRow | undefined, DebriefRow | undefined] {
  return [placed(summary, 1), placed(summary, 2), placed(summary, 3)];
}

/**
 * Where a car started, as a place. A pit-lane start counts as the slot behind
 * every car that took one: the number of cars with a grid slot or a pit-lane start.
 */
export function startSlot(row: DebriefRow, rows: readonly DebriefRow[]): number | null {
  if (row.pit_lane) return rows.filter((other) => other.grid !== null || other.pit_lane).length;
  return row.grid;
}

/** "pole", "P5" or "pit lane"; null when no official grid says. */
export function startPhrase(row: DebriefRow): string | null {
  if (row.pit_lane) return "pit lane";
  if (row.grid === null) return null;
  return row.grid === 1 ? "pole" : `P${row.grid}`;
}

/** The winner's lead over second: seconds, or laps when second was lapped; null when there is none to state. */
export function winningMargin(summary: DebriefSummary): { value: string; unit: "s" | "lap" | "laps" } | null {
  const second = placed(summary, 2);
  if (!second) return null;
  if (second.laps_down) return { value: String(second.laps_down), unit: second.laps_down === 1 ? "lap" : "laps" };
  return second.gap ? { value: second.gap.replace(/^\+/, ""), unit: "s" } : null;
}

function marginPhrase(margin: NonNullable<ReturnType<typeof winningMargin>>): string {
  return margin.unit === "s" ? `${margin.value} seconds` : `${margin.value} ${margin.unit}`;
}

function championOf(summary: DebriefSummary): DebriefTitle | undefined {
  return summary.titles.find((title) => title.table === "drivers");
}

/** "Verstappen wins the Mexican Grand Prix; Antonelli is champion"; the race's name before it has a winner. */
export function debriefHeadline(summary: DebriefSummary, directory?: NameDirectory): string {
  const winner = placed(summary, 1);
  if (!winner) return summary.race;
  const base = `${lastOf(winner, directory)} wins the ${summary.race}`;
  const champion = championOf(summary);
  if (!champion) return base;
  if (champion.name === winner.driver_name) return `${base} and the title`;
  return `${base}; ${driverLabel({ name: champion.name }, "last", directory)} is champion`;
}

/** The hero's one line: how the winner won, and who completed the podium. */
export function debriefMeta(summary: DebriefSummary): string {
  const [winner, second, third] = podiumOf(summary);
  if (!summary.available || !winner) return summary.reason ?? "";
  const start = startPhrase(winner);
  const from = start ? ` from ${start === "pit lane" ? "the pit lane" : start}` : "";
  const margin = winningMargin(summary);
  const lead = second
    ? `${winner.driver_name} won${from} and beat ${second.driver_name}${margin ? ` by ${marginPhrase(margin)}` : ""}.`
    : `${winner.driver_name} won the race.`;
  return third ? `${lead} ${third.driver_name} completed the podium.` : lead;
}

export interface Climb {
  row: DebriefRow;
  from: number;
  gained: number;
}

/** The finisher who gained most places on the grid (ties go to the better finish); null when nobody gained. */
export function biggestClimb(summary: DebriefSummary): Climb | null {
  const { classification } = summary;
  const climbs = classification.flatMap((row) => {
    const from = startSlot(row, classification);
    return row.status === "Finished" && row.position !== null && from !== null
      ? [{ row, from, gained: from - row.position }]
      : [];
  });
  const best = climbs.reduce<Climb | null>(
    (top, climb) => (top === null || climb.gained > top.gained ? climb : top),
    null,
  );
  return best && best.gained > 0 ? best : null;
}

/** "Stroll & Alonso L5" groups: retirements on the same lap together, in classification order. */
export function retirementGroups(summary: DebriefSummary, directory?: NameDirectory): string[] {
  const groups = new Map<number | null, string[]>();
  for (const row of summary.classification.filter((entry) => entry.status === "DNF")) {
    groups.set(row.laps, [...(groups.get(row.laps) ?? []), lastOf(row, directory)]);
  }
  return [...groups].map(([laps, names]) => `${names.join(" & ")}${laps === null ? "" : ` L${laps}`}`);
}

export function retirementCount(summary: DebriefSummary): number {
  return summary.classification.filter((row) => row.status === "DNF").length;
}

/** The slope chart's end text for a car without a place; null for one that did not start. */
function endText(row: DebriefRow): string | null {
  if (row.status === "DNF") return row.laps === null ? "DNF" : `DNF L${row.laps}`;
  return row.status === "DNS" ? null : row.status;
}

/** One line per car with a start: grid to finish, a car without a place drawn dashed in its classified slot. */
export function slopeItems(summary: DebriefSummary): SlopeItem[] {
  const { classification } = summary;
  return classification.flatMap((row, index) => {
    const start = startSlot(row, classification);
    const text = endText(row);
    if (start === null || text === null) return [];
    const finished = row.position !== null;
    return [
      {
        id: row.driver_code,
        label: row.driver_code,
        name: row.driver_name,
        start,
        end: row.position ?? index + 1,
        color: getTeamColor(row.team),
        ...(row.pit_lane ? { startText: "PL" } : {}),
        ...(finished ? {} : { endText: text, incomplete: true }),
      },
    ];
  });
}

export function gridTitle(summary: DebriefSummary, directory?: NameDirectory): string {
  const climb = biggestClimb(summary);
  if (!climb) return "Nobody gained places from the grid";
  const from = climb.row.pit_lane ? "the pit lane" : `P${climb.from}`;
  return `${lastOf(climb.row, directory)} came from ${from} to P${climb.row.position}`;
}

function classificationSource(summary: DebriefSummary): string {
  const source = summary.sources[0];
  if (source?.source === "f1db") return `f1db ${source.version ?? ""}`.trim();
  if (source?.source === "fia-final-classification") return `FIA final classification (doc ${source.document})`;
  return "OpenF1, provisional";
}

function gridSource(summary: DebriefSummary): string {
  const { available, fia_document: document } = summary.grid;
  if (!available) return "not published yet";
  return document ? `FIA final starting grid (doc ${document.number})` : "f1db";
}

/** Where each part of the page comes from. */
export function sourceNote(summary: DebriefSummary): string {
  return `Classification: ${classificationSource(summary)} · laps, race control and position changes: OpenF1 · grid: ${gridSource(summary)}`;
}
