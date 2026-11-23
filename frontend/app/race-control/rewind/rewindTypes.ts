/** The Race Rewind endpoint's payload (`/api/race-control/rewind/{year}/{round}`). */

import type { Neutralisation } from "../grand-prix/strategyModel";

export type ChangeKind = "own_stop" | "rival_stop" | "retirement" | "neutralised" | "pass" | "change";

/** The lap's neutralisation: a red flag outranks a Safety Car, which outranks a VSC. */
export type TrackKind = Neutralisation["kind"];

export type ClassificationStatus = "finished" | "dnf" | "dns" | "dsq" | "not_classified";

export interface RewindDriver {
  car: number;
  driver_code: string;
  driver_name: string;
  team: string;
  /** The classification's status; null when none is published. */
  status: ClassificationStatus | null;
  /** Laps completed, per the classification; null when it doesn't say. */
  laps: number | null;
}

export interface RewindGrid {
  /** Grid order, pit-lane starters last. */
  order: string[];
  pit_lane: string[];
  /** `fia_starting_grid`, `f1db`, or `openf1-position` (the fallback). */
  source: string;
  document: number | null;
}

export interface RewindStop {
  driver_code: string;
  lap: number;
}

export interface RewindChange {
  driver_code: string;
  from: number;
  to: number;
  kind: ChangeKind;
  rival: string | null;
  stop_lap: number | null;
}

export interface RewindLap {
  lap: number;
  /** Codes in place order at the line after this lap, P1 first. */
  order: string[];
  track: TrackKind | null;
  changes: RewindChange[];
}

export interface RewindPenalty {
  ruling: string;
  seconds: number | null;
  document: number | null;
}

export interface RewindFinalRow {
  driver_code: string;
  position: number | null;
  status: ClassificationStatus;
  laps: number | null;
  /** The car's place at the line on its last lap; null when it has none. */
  road_position: number | null;
  penalties: RewindPenalty[];
}

export interface RewindFinal {
  source: string;
  provisional: boolean;
  document: number | null;
  url: string | null;
  rows: RewindFinalRow[];
}

/** A race the rewind can replay. */
export interface RaceRewind {
  year: number;
  round: number;
  available: true;
  reason: null;
  total_laps: number;
  drivers: RewindDriver[];
  grid: RewindGrid;
  neutralisations: Neutralisation[];
  stops: RewindStop[];
  laps: RewindLap[];
  /** Null until a classification is published: there is then no Final step. */
  final: RewindFinal | null;
}

/** A race with nothing to replay yet; `reason` says why. */
export interface RewindUnavailable {
  year: number;
  round: number;
  available: false;
  reason: string | null;
}

export type RewindResponse = RaceRewind | RewindUnavailable;
