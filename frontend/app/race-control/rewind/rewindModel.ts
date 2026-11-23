/** The state of the replay at each step, computed from the payload and nothing else. */

import { leaderRuns } from "../debriefs/lapsModel";

import type { RaceRewind, RewindChange, RewindDriver, RewindFinalRow, RewindLap, TrackKind } from "./rewindTypes";

/** A step is 0 (the grid), a lap 1…total, or total + 1 (the final classification, when one is published). */
export type StepKind = { kind: "grid" } | { kind: "lap"; lap: number } | { kind: "final" };

export interface TowerRow {
  /** The place to show; null for a pit-lane starter and a car that is out. */
  place: number | null;
  code: string;
  name: string;
  team: string;
  /** Places gained (positive) or lost against the reference order; null where there is none. */
  delta: number | null;
  tag: string | null;
  out: boolean;
}

/** The last step: one past the last lap when a classification is published. */
export function maxStep(data: RaceRewind): number {
  return data.total_laps + (data.final ? 1 : 0);
}

export function stepKind(step: number, data: RaceRewind): StepKind {
  if (step <= 0) return { kind: "grid" };
  if (step > data.total_laps) return { kind: "final" };
  return { kind: "lap", lap: step };
}

/** The range's `aria-valuetext`. */
export function stepLabel(step: number, data: RaceRewind): string {
  const at = stepKind(step, data);
  if (at.kind === "grid") return "Grid";
  if (at.kind === "final") return "Final classification";
  return `After lap ${at.lap} of ${data.total_laps}`;
}

/** Each lap's leader. */
export function leaders(data: RaceRewind): Array<string | null> {
  return data.laps.map((lap) => lap.order[0] ?? null);
}

/** Where the page opens: the first lap of the last lead run (lap 1 when one driver led every lap). */
export function defaultStep(data: RaceRewind): number {
  return leaderRuns(leaders(data)).at(-1)?.startLap ?? 1;
}

/** The step a URL asks for when this race has it, else the default. */
export function initialStep(requested: number | "final" | null, data: RaceRewind): number {
  if (requested === "final") return data.final ? data.total_laps + 1 : defaultStep(data);
  return requested !== null && requested <= data.total_laps ? requested : defaultStep(data);
}

/** The lap's order and the order before it (the grid on lap 1). */
export function orderBefore(data: RaceRewind, lap: number): string[] {
  return lap > 1 ? data.laps[lap - 2].order : data.grid.order;
}

export function driverOf(data: RaceRewind, code: string): RewindDriver {
  return (
    data.drivers.find((driver) => driver.driver_code === code) ?? {
      car: 0,
      driver_code: code,
      driver_name: code,
      team: "",
      status: null,
      laps: null,
    }
  );
}

function rowFor(data: RaceRewind, code: string, rest: Partial<TowerRow>): TowerRow {
  const driver = driverOf(data, code);
  return {
    place: null,
    code,
    name: driver.driver_name,
    team: driver.team,
    delta: null,
    tag: null,
    out: false,
    ...rest,
  };
}

function gridRows(data: RaceRewind): TowerRow[] {
  const pitLane = new Set(data.grid.pit_lane);
  const slotted = data.grid.order.filter((code) => !pitLane.has(code));
  return data.grid.order.map((code) =>
    pitLane.has(code)
      ? rowFor(data, code, { tag: "Pit lane" })
      : rowFor(data, code, { place: slotted.indexOf(code) + 1 }),
  );
}

/** A stop on this lap or the one before reads PIT: the in-lap and the out-lap. */
function inThePits(data: RaceRewind, code: string, lap: number): boolean {
  return data.stops.some((stop) => stop.driver_code === code && (stop.lap === lap || stop.lap === lap - 1));
}

const lapsOf = (driver: RewindDriver): number => driver.laps ?? 0;

function outRows(data: RaceRewind, lap: number): TowerRow[] {
  return data.drivers
    .filter((driver) => driver.status === "dns" || (driver.status === "dnf" && lapsOf(driver) < lap))
    .sort((a, b) => lapsOf(b) - lapsOf(a) || a.driver_code.localeCompare(b.driver_code))
    .map((driver) =>
      rowFor(data, driver.driver_code, { tag: driver.status === "dns" ? "DNS" : `DNF L${lapsOf(driver)}`, out: true }),
    );
}

function lapRows(data: RaceRewind, lap: number): TowerRow[] {
  const before = orderBefore(data, lap);
  const running = data.laps[lap - 1].order.map((code, index) => {
    const was = before.indexOf(code);
    return rowFor(data, code, {
      place: index + 1,
      delta: was === -1 ? null : was - index,
      tag: inThePits(data, code, lap) ? "PIT" : null,
    });
  });
  return [...running, ...outRows(data, lap)];
}

const FINAL_TAGS: Record<RewindFinalRow["status"], (row: RewindFinalRow) => string | null> = {
  finished: () => null,
  dnf: (row) => `DNF L${row.laps}`,
  dsq: () => "DSQ",
  dns: () => "DNS",
  not_classified: () => "NC",
};

function finalRows(data: RaceRewind): TowerRow[] {
  return (data.final?.rows ?? []).map((row) =>
    rowFor(data, row.driver_code, {
      place: row.position,
      delta: row.road_position !== null && row.position !== null ? row.road_position - row.position : null,
      tag: FINAL_TAGS[row.status](row),
      out: row.status === "dnf" || row.status === "dsq",
    }),
  );
}

/** One row per car for the step. */
export function towerRows(data: RaceRewind, step: number): TowerRow[] {
  const at = stepKind(step, data);
  if (at.kind === "grid") return gridRows(data);
  if (at.kind === "final") return finalRows(data);
  return lapRows(data, at.lap);
}

/** The lap's place changes; none at the grid or the final step. */
export function changesAt(data: RaceRewind, step: number): RewindChange[] {
  const at = stepKind(step, data);
  return at.kind === "lap" ? data.laps[at.lap - 1].changes : [];
}

/** The lap a step shows, or null at the grid and the final step. */
export function lapAt(data: RaceRewind, step: number): RewindLap | null {
  const at = stepKind(step, data);
  return at.kind === "lap" ? data.laps[at.lap - 1] : null;
}

const TRACK_LABELS: Record<TrackKind, string> = {
  sc: "Under Safety Car",
  vsc: "Under VSC",
  red: "Under red flag",
};

const CHANGE_LABELS: Record<Exclude<RewindChange["kind"], "neutralised">, string> = {
  own_stop: "Own stop",
  rival_stop: "A rival's stop",
  retirement: "Retirement ahead",
  pass: "Pass",
  change: "Position change",
};

/** Why the place changed, as a tag. */
export function changeLabel(change: RewindChange, track: TrackKind | null): string {
  if (change.kind !== "neutralised") return CHANGE_LABELS[change.kind];
  return track ? TRACK_LABELS[track] : "Neutralised";
}

/** The detail under the label; `nameOf` gives a surname. */
export function changeDetail(change: RewindChange, nameOf: (code: string | null) => string): string {
  const rival = nameOf(change.rival);
  switch (change.kind) {
    case "own_stop":
      return `stopped lap ${change.stop_lap}`;
    case "rival_stop":
      return `${rival} stopped lap ${change.stop_lap}`;
    case "retirement":
      return `${rival} retired`;
    case "neutralised":
      return "not counted as a pass";
    case "pass":
      return change.to < change.from ? `passed ${rival}` : `passed by ${rival}`;
    case "change":
      return "";
  }
}
