/**
 * Payload types for the Telemetry Lab (`/api/analysis/{year}/{round}/...`).
 *
 * Every answer carries `available`; when it is false, `reason` and `message`
 * say why (OpenF1 closed for a live session, not published yet, still loading),
 * and the page shows that message instead of an empty chart.
 */

export type TabKey = "map" | "head-to-head" | "tyres";

export const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "map", label: "Speed Map" },
  { key: "head-to-head", label: "Head-to-Head" },
  { key: "tyres", label: "Tyre Degradation" },
];

/** OpenF1 holds lap and car data from this season on. */
export const FIRST_SEASON = 2023;

export type UnavailableReason =
  | "no_session"
  | "no_driver"
  | "no_lap"
  | "no_telemetry"
  | "no_stints"
  | "openf1_live"
  | "openf1_unavailable"
  | "loading"
  | "error";

/** Fields every analysis answer shares. */
export interface AnalysisStatus {
  available: boolean;
  pending: boolean;
  reason?: UnavailableReason;
  message?: string;
  error_id?: string;
  warnings?: string[];
  modeled?: string[];
}

export interface WeekendSession {
  code: string;
  name: string;
  date_start: string | null;
  started: boolean;
}

export interface WeekendResponse extends AnalysisStatus {
  sessions?: WeekendSession[];
}

export interface AnalysisDriver {
  number: number;
  code: string;
  name: string;
  team: string;
  colour: string;
}

export interface TimedLap {
  number: number;
  time: number | null;
  deleted: boolean;
  is_fastest: boolean;
}

export interface LapListDriver extends AnalysisDriver {
  best: number | null;
  laps: TimedLap[];
}

export interface LapListResponse extends AnalysisStatus {
  drivers?: LapListDriver[];
}

export interface LapInfo {
  number: number;
  time: number | null;
  sectors: Array<number | null>;
  speed_traps: { i1: number | null; i2: number | null; speed_trap: number | null };
  deleted: boolean;
  pit_out: boolean;
  is_fastest: boolean;
}

export interface CornerMarker {
  number: number;
  label: string;
  x: number;
  y: number;
  label_x: number;
  label_y: number;
}

export interface BrakingZone {
  start: number;
  end: number;
  entry_speed: number;
  min_speed: number;
  x: number;
  y: number;
}

export interface HighSpeedZone {
  start: number;
  end: number;
  peak_speed: number;
  x: number;
  y: number;
}

export interface TrackMapResponse extends AnalysisStatus {
  driver?: AnalysisDriver;
  lap?: LapInfo;
  points?: {
    distance: number[];
    x: number[];
    y: number[];
    speed: number[];
    throttle: number[];
    brake: number[];
    gear: number[];
  };
  braking_zones?: BrakingZone[];
  high_speed_zones?: HighSpeedZone[];
  stats?: {
    top_speed: { speed: number; distance: number; x: number; y: number };
    full_throttle_pct: number;
    braking_pct: number;
    distance_m: number;
  };
  corners?: CornerMarker[];
}

export type Faster = "a" | "b" | "even";

export interface Stretch {
  label: string;
  start: number;
  end: number;
  gain: number;
  faster: Faster;
}

export interface ComparisonSide {
  driver: AnalysisDriver;
  lap: LapInfo;
}

export interface ComparisonResponse extends AnalysisStatus {
  a?: ComparisonSide;
  b?: ComparisonSide;
  gap?: number;
  trace?: Record<string, number[]>;
  mini_sectors?: Stretch[];
  corners?: Stretch[];
  sectors?: Array<{ sector: number; a: number | null; b: number | null; gain: number | null }>;
  biggest_gains?: { a: Stretch[]; b: Stretch[] };
  map?: { distance: number[]; x: number[]; y: number[] };
  corner_markers?: CornerMarker[];
}

export interface DegradationLap {
  driver: string;
  lap: number;
  time: number | null;
  corrected: number | null;
  tyre_age: number | null;
  compound: string | null;
  stint: number | null;
  status: string;
  gap_ahead: number | null;
}

export interface LineFit {
  slope: number;
  intercept: number;
  r2: number;
}

export interface DegradationStint {
  driver: string;
  stint: number;
  compound: string;
  start_lap: number;
  end_lap: number;
  tyre_life_start: number | null;
  boundary_checked: boolean;
  fit: { laps_fitted: number; raw: LineFit; corrected: LineFit | null } | null;
}

export interface CompoundSummary {
  compound: string;
  stints: number;
  median_slope: number;
  median_raw_slope: number;
  iqr: [number, number];
  corrected: boolean;
}

export interface DegradationResponse extends AnalysisStatus {
  drivers?: Array<AnalysisDriver & { position: number | null }>;
  laps?: DegradationLap[];
  stints?: DegradationStint[];
  compounds?: CompoundSummary[];
  neutralised?: Array<{ kind: string; from_lap: number; to_lap: number }>;
  status_labels?: Record<string, string>;
  assumptions?: {
    fuel: { start_fuel_kg: number; seconds_per_kg: number; race_laps: number; slope_effect: number } | null;
    traffic_gap_seconds: number;
    min_fit_laps: number;
    outlier_factor: number;
  };
}

/** "1:34.539" from seconds; a dash when there is no time. */
export function formatLapTime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "-";
  const minutes = Math.floor(seconds / 60);
  const rest = (seconds - minutes * 60).toFixed(3).padStart(6, "0");
  return minutes > 0 ? `${minutes}:${rest}` : rest;
}

/** "+0.325" / "-0.120": a signed gap in seconds. */
export function formatGap(seconds: number | null | undefined, digits = 3): string {
  if (seconds === null || seconds === undefined) return "-";
  const sign = seconds > 0 ? "+" : "";
  return `${sign}${seconds.toFixed(digits)}`;
}
