/** Every title and note on the page, computed from the payload. */

import { ordinal } from "@/app/race-control/champions/championsModel";
import { driverLabel, type NameDirectory } from "@/app/ui/names/names";

import { leaderRuns, type LeaderRun } from "../debriefs/lapsModel";

import { leaders, orderBefore, stepKind } from "./rewindModel";

import type { RaceRewind, RewindChange, RewindFinal, RewindPenalty, TrackKind } from "./rewindTypes";

export const FIA_SOURCE = "fia-final-classification";
export const OPENF1_SOURCE = "openf1-session-result";

const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

/** Two to ten in words, digits beyond. */
function word(n: number): string {
  return WORDS[n] ?? String(n);
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** A surname by the names rule; "" for no one. */
export function surnameFn(data: RaceRewind, directory?: NameDirectory): (code: string | null) => string {
  return (code) => {
    if (code === null) return "";
    const driver = data.drivers.find((entry) => entry.driver_code === code);
    return driverLabel({ name: driver?.driver_name ?? code, code }, "last", directory);
  };
}

function hasStopAround(data: RaceRewind, code: string | null, lap: number): boolean {
  return data.stops.some((stop) => stop.driver_code === code && (stop.lap === lap || stop.lap === lap - 1));
}

/** Lead changes: every run after the first, with whether the old or new leader stopped around its start. */
function leadChanges(data: RaceRewind): { runs: LeaderRun[]; atStop: number; total: number } {
  const runs = leaderRuns(leaders(data));
  const changes = runs.slice(1);
  const atStop = changes.filter(
    (run, index) => hasStopAround(data, run.code, run.startLap) || hasStopAround(data, runs[index].code, run.startLap),
  ).length;
  return { runs, atStop, total: changes.length };
}

const TIMES = ["", "once", "twice"];

export function rewindHeadline(data: RaceRewind, directory?: NameDirectory): string {
  const { runs, atStop, total } = leadChanges(data);
  if (total === 0) return `${surnameFn(data, directory)(runs[0].code)} led every lap`;
  const times = TIMES[total] ?? `${total} times`;
  if (atStop === 0) return `The lead changed ${times}`;
  if (atStop < total) return `The lead changed ${total} times, ${atStop} of them at a stop`;
  if (total === 1) return "The lead changed once, at a stop";
  return total === 2
    ? "The lead changed twice, both times at a stop"
    : `The lead changed ${total} times, each time at a stop`;
}

function finalPhrase(final: RewindFinal): string {
  if (final.source === FIA_SOURCE) return "the FIA final classification";
  if (final.source === OPENF1_SOURCE) return "OpenF1's provisional classification";
  return "Jolpica's provisional classification";
}

function runPhrase(run: LeaderRun, index: number, count: number, name: string): string {
  if (index === count - 1) return `${name} from lap ${run.startLap} to the flag`;
  return `${index === 0 ? `${name} led` : name} to lap ${run.endLap}`;
}

export function rewindMeta(data: RaceRewind, directory?: NameDirectory): string {
  const { runs } = leadChanges(data);
  const name = surnameFn(data, directory);
  const led =
    runs.length === 1
      ? `${name(runs[0].code)} led every lap.`
      : `${runs.map((run, index) => runPhrase(run, index, runs.length, name(run.code))).join(", ")}.`;
  const drag = `${led} Drag the scrubber to replay the order at the line, lap by lap`;
  return data.final ? `${drag}; the last step is ${finalPhrase(data.final)}.` : `${drag}.`;
}

export function lapChartTitle(data: RaceRewind, directory?: NameDirectory): string {
  const last = leaderRuns(leaders(data)).at(-1);
  const who = surnameFn(data, directory)(last?.code ?? null);
  return !last || last.startLap === 1 ? `${who} led every lap` : `${who} led every lap from ${last.startLap}`;
}

export interface TowerHeading {
  eyebrow: string;
  title: string;
  sub: string;
}

function gridSub(data: RaceRewind): string {
  const { source, document } = data.grid;
  if (source === "fia_starting_grid") {
    return document === null ? "FIA final starting grid" : `FIA final starting grid (doc ${document})`;
  }
  return source === "f1db" ? "Official grid (f1db)" : "Order at the start, from OpenF1 positions";
}

/** "Verstappen leads; Antonelli stopped", or the leader and the cars in the pits. */
function lapTitle(data: RaceRewind, lap: number, name: (code: string | null) => string): string {
  const order = data.laps[lap - 1].order;
  const [leader] = order;
  const [was] = orderBefore(data, lap);
  if (leader !== was) {
    const old = data.laps[lap - 1].changes.find((change) => change.driver_code === was);
    if (old?.kind === "own_stop") return `${name(leader)} leads; ${name(was)} stopped`;
    if (!order.includes(was)) return `${name(leader)} leads; ${name(was)} retired`;
    return `${name(leader)} leads; ${name(was)} lost the lead`;
  }
  const pits = order.filter((code) => hasStopAround(data, code, lap)).length;
  if (pits === 0) return `${name(leader)} leads`;
  return `${name(leader)} leads; ${pits} ${pits === 1 ? "car" : "cars"} in the pits`;
}

export function towerHeading(data: RaceRewind, step: number, directory?: NameDirectory): TowerHeading {
  const name = surnameFn(data, directory);
  const at = stepKind(step, data);
  if (at.kind === "grid") {
    return { eyebrow: "Starting grid", title: `${name(data.grid.order[0])} on pole`, sub: gridSub(data) };
  }
  if (at.kind === "final") {
    const winner = data.final?.rows.find((row) => row.position === 1);
    return {
      eyebrow: "Classification",
      title: `${name(winner?.driver_code ?? null)} wins`,
      sub: "+/− = places vs the road order at the flag",
    };
  }
  return {
    eyebrow: `Order after lap ${at.lap}`,
    title: lapTitle(data, at.lap, name),
    sub: `+/− = places vs ${at.lap === 1 ? "the grid" : `lap ${at.lap - 1}`}`,
  };
}

const TRACK_NAMES: Record<TrackKind, string> = { sc: "Safety Car", vsc: "VSC", red: "red flag" };

function tally(changes: readonly RewindChange[], track: TrackKind | null): string {
  const count = (...kinds: Array<RewindChange["kind"]>) =>
    changes.filter((change) => kinds.includes(change.kind)).length;
  const known = count("own_stop", "rival_stop", "retirement", "neutralised", "pass");
  const parts: Array<[number, string]> = [
    [count("own_stop", "rival_stop"), "at a stop"],
    [count("retirement"), "from a retirement"],
    [count("neutralised"), `under the ${track ? TRACK_NAMES[track] : "neutralisation"}`],
    [count("pass"), count("pass") === 1 ? "pass" : "passes"],
    [changes.length - known, "other"],
  ];
  return parts
    .filter(([n]) => n > 0)
    .map(([n, text]) => `${n} ${text}`)
    .join(", ");
}

/** "Antonelli's stop moved the top four", "Leclerc took the lead from Hamilton", or the tally. */
export function changesTitle(data: RaceRewind, lap: number, directory?: NameDirectory): string {
  const name = surnameFn(data, directory);
  const { order, changes, track } = data.laps[lap - 1];
  if (changes.length === 0) return `No position changes on lap ${lap}`;
  const [was] = orderBefore(data, lap);
  if (order[0] !== was) {
    const old = changes.find((change) => change.driver_code === was);
    if (old?.kind === "own_stop") return `${name(was)}'s stop moved the top ${word(old.to)}`;
    return `${name(order[0])} took the lead from ${name(was)}`;
  }
  return `${changes.length} position ${changes.length === 1 ? "change" : "changes"}: ${tally(changes, track)}`;
}

/** The final card's finding: the post-race penalties and the places they moved. */
export function finalTitle(final: RewindFinal): string {
  const moved = final.rows.flatMap((row) =>
    row.position !== null && row.road_position !== null && row.road_position !== row.position
      ? [{ place: row.position, penalised: row.penalties.length > 0 }]
      : [],
  );
  if (moved.length === 0) return "The road order stood";
  const places = moved.map((row) => row.place);
  const range = `${ordinal(Math.min(...places))} to ${ordinal(Math.max(...places))}`;
  const penalised = moved.filter((row) => row.penalised).length;
  if (penalised === 0) return `The classification moved ${range}`;
  if (penalised === 1) return `One post-race penalty moved ${range}`;
  return `${capital(word(penalised))} post-race penalties reshuffled ${range}`;
}

/** "10 s · FIA doc 79"; the ruling as printed when it names no seconds. */
export function penaltyText(penalty: RewindPenalty): string {
  const ruling = penalty.seconds === null ? penalty.ruling : `${penalty.seconds} s`;
  return penalty.document === null ? ruling : `${ruling} · FIA doc ${penalty.document}`;
}

export interface FinalSource {
  name: string;
  /** "doc 86", linked to `url` when there is one. */
  doc: string | null;
  url: string | null;
}

export function finalSource(final: RewindFinal): FinalSource {
  if (final.source === FIA_SOURCE) {
    return {
      name: "FIA final classification",
      doc: final.document === null ? null : `doc ${final.document}`,
      url: final.url,
    };
  }
  const name = final.source === OPENF1_SOURCE ? "OpenF1 session result, provisional" : "Jolpica, provisional";
  return { name, doc: null, url: null };
}

export const SOURCE_NOTE_LEAD =
  'Order at the line: OpenF1 position, sampled at each car\'s line crossing · stops: OpenF1 pit (red-flag pit-lane entries are not stops) · passes: OpenF1 overtakes, labelled "pass" only when no stop, retirement or neutralisation explains the change';

export function sourceNote(data: RaceRewind): string {
  if (!data.final) return SOURCE_NOTE_LEAD;
  const { name, doc } = finalSource(data.final);
  return `${SOURCE_NOTE_LEAD} · final order: ${name}${doc ? ` (${doc})` : ""}`;
}
