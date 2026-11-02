/**
 * Payload shapes for the race-weekend showcase on the Command Center.
 *
 * They mirror the backend segments one for one: the per-session forecast rides
 * on `/overview/{year}/weather`, the circuit map and record on `/circuit`, and
 * the championship stakes on `/shell`.
 */

import type { StandingsFreshness } from "@/app/lib/standingsFreshness";

export type WeatherCondition =
  "clear" | "partly_cloudy" | "cloudy" | "fog" | "drizzle" | "rain" | "storm" | "snow" | "unknown";

export type SessionPhase = "done" | "live" | "upcoming";

/** One session's weather, read off every hour it is on track. Blank readings stay null. */
export interface SessionForecast {
  condition: WeatherCondition;
  label: string;
  is_day: boolean | null;
  air_temp_c: number | null;
  /** Modelled from air temperature and cloud — never a trackside reading. */
  track_temp_c: number | null;
  rain_probability_pct: number | null;
  precipitation_mm: number | null;
  wind_kph: number | null;
  wind_direction_deg: number | null;
  humidity_pct: number | null;
  cloud_cover_pct: number | null;
}

export interface SessionWeatherRow {
  name: string;
  starts_at: string;
  ends_at: string;
  phase: SessionPhase;
  forecast: SessionForecast | null;
  /** ISO date the forecast becomes available, for a session past the horizon. */
  forecast_opens: string | null;
}

export interface SessionWeather {
  status: "ready" | "pending" | "unavailable";
  note: string | null;
  source: string;
  attribution: string;
  sessions: SessionWeatherRow[];
}

export interface CircuitCorner {
  label: string;
  x: number;
  y: number;
  label_x: number;
  label_y: number;
}

/** The outline in SVG coordinates, already turned and scaled by the backend. */
export interface CircuitMapData {
  source: string;
  season: number;
  width: number;
  height: number;
  points: Array<[number, number]>;
  corners: CircuitCorner[];
}

export interface Headliner {
  driver_id: string;
  driver_name: string;
  team_id: string;
  team_name: string;
}

export interface CircuitEdition {
  year: number;
  winner: (Headliner & { grid: number | null }) | null;
  pole: Headliner | null;
  won_from_pole: boolean;
}

export interface CircuitRecord {
  circuit_id: string;
  name: string | null;
  place: string | null;
  length_km: number | null;
  turns: number | null;
  direction: "clockwise" | "anti-clockwise" | null;
  laps: number | null;
  distance_km: number | null;
  first_year: number | null;
  races_held: number;
  pole_conversion: { wins_from_pole: number; editions: number };
  editions: CircuitEdition[];
  active_winners: Array<{ driver_id: string; driver_name: string; wins: number; last_win: number }>;
}

export interface LapRecord {
  time: string;
  driver: string;
  year: number;
}

/** `GET /api/race-control/overview/{year}/circuit` */
export interface OverviewCircuit {
  year?: number;
  record: CircuitRecord | null;
  lap_record: LapRecord | null;
  map: CircuitMapData | null;
  error?: string | null;
}

export interface Contender {
  position: number;
  name: string;
  code: string | null;
  team: string | null;
  points: number;
  gap: number;
  alive: boolean;
}

export interface Clinch {
  rival: string;
  /** The points the leader must outscore the rival by here; zero or less means "unless outscored". */
  margin_needed: number;
  possible: boolean;
  rivals_in_play: number;
}

export interface TableStakes {
  max_available: number;
  max_this_weekend: number;
  leader: Contender;
  contenders: Contender[];
  rivals_alive: number;
  decided: boolean;
  clinch: Clinch | null;
}

/** Counted from the table's `as_of_round`: the newest round with published points. */
export interface ChampionshipStakes extends StandingsFreshness {
  races_left: number;
  sprints_left: number;
  drivers: TableStakes | null;
  constructors: TableStakes | null;
}

export interface RiskCard {
  level: string;
  title: string;
  detail: string;
}
