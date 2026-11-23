/** The debrief endpoints' payloads (`/api/race-control/debrief/{year}/{round}` and its three sections). */

import type { Neutralisation } from "../grand-prix/strategyModel";

export interface DebriefRow {
  position: number | null;
  driver_code: string;
  driver_name: string;
  team: string;
  status: "Finished" | "DNF" | "DNS" | "DSQ" | "NC";
  reason: string | null;
  laps: number | null;
  time: string | null;
  gap: string | null;
  laps_down: number | null;
  time_penalty: number | null;
  road_position: number | null;
  points: number | null;
  fastest_lap: boolean;
  /** The official grid slot; null for a pit-lane start or when no official grid is published. */
  grid: number | null;
  pit_lane: boolean;
}

export interface FiaDocumentRef {
  number: number | null;
  url?: string;
  final?: boolean;
}

export interface DebriefSource {
  source: string;
  role: string;
  version?: string;
  document?: number | null;
  url?: string;
}

export interface DebriefTitle {
  table: "drivers" | "constructors";
  name: string;
  team: string;
  points: number;
  lead: number | null;
  runner_up: string | null;
  races_left: number | null;
  provisional: boolean;
}

export interface DebriefSummary {
  year: number;
  round: number;
  race: string;
  location: string;
  available: boolean;
  reason: string | null;
  final: boolean;
  sources: DebriefSource[];
  classification: DebriefRow[];
  grid: { available: boolean; fia_document: FiaDocumentRef | null };
  titles: DebriefTitle[];
}

export interface DebriefDriver {
  driver_code: string;
  driver_name: string;
  team: string;
}

export interface TraceCar {
  driver_code: string;
  position: number;
  /** Seconds behind the leader at each line crossing; null where either car has no crossing. */
  gaps: Array<number | null>;
}

export interface DebriefLaps {
  available: boolean;
  reason?: string | null;
  total_laps: number;
  drivers: DebriefDriver[];
  /** The leader's code at each line, lap 1 first; null when no car has a crossing. */
  leaders: Array<string | null>;
  trace: TraceCar[];
  neutralisations: Neutralisation[];
}

export interface InRacePenalty {
  lap: number | null;
  car: number;
  driver_code: string;
  driver_name: string;
  penalty: string;
  seconds: number | null;
  offence: string | null;
  served: boolean;
}

export interface PostRacePenalty {
  driver_code: string;
  driver_name: string;
  car: number | null;
  ruling: string;
  seconds: number | null;
  reason: string | null;
  document: number | null;
  road_position: number | null;
  position: number | null;
}

export interface DebriefPenalties {
  available: boolean;
  in_race: InRacePenalty[];
  post_race: PostRacePenalty[];
  fia_document: { number: number | null; url: string } | null;
}

export interface OvertakeDriver extends DebriefDriver {
  made: number;
}

export interface DebriefOvertakes {
  available: boolean;
  total: number;
  drivers: OvertakeDriver[];
}

export type RadioMomentKind =
  | "start"
  | "safety_car"
  | "safety_car_in"
  | "vsc"
  | "vsc_ending"
  | "red_flag"
  | "chequered"
  | "stop"
  | "penalty"
  | "incident"
  | "retirement";

export interface RadioClip extends DebriefDriver {
  colour: string;
  /** 0 = before the driver's lap 1 began. */
  lap: number;
  at: string;
  url: string;
}

export interface RadioMoment {
  kind: RadioMomentKind;
  lap: number;
  at: string;
  driver: DebriefDriver | null;
  detail: string | null;
  clips: RadioClip[];
}

export interface DebriefRadio {
  available: boolean;
  reason: string | null;
  total: number;
  utc_offset_minutes: number | null;
  moments: RadioMoment[];
  unattached: RadioClip[];
}
