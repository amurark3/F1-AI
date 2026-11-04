/**
 * Payload shapes for the race-weekend showcase on the Command Center.
 *
 * They mirror the backend segments one for one: the per-session forecast rides
 * on `/overview/{year}/weather`, the circuit map and record on `/circuit`, and
 * the championship stakes on `/shell`.
 */

import type { StandingsFreshness } from "@/app/lib/standingsFreshness";
import type { CircuitMapData } from "@/app/ui/outlinePath";

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

export interface Headliner {
  driver_id: string;
  driver_name: string;
  /** f1db's `last_name`, as it stores it ("Sainz Jr.", "De Vries"). */
  last_name: string;
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
  active_winners: Array<{ driver_id: string; driver_name: string; last_name: string; wins: number; last_win: number }>;
}

export interface LapRecord {
  time: string;
  driver: string;
  year: number;
  /**
   * f1db's surname for the holder, resolved in the record's season by the
   * circuit segment; null when the holder does not resolve. The schedule's own
   * copy (the hero's fallback) has none.
   */
  last_name?: string | null;
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
  /** A driver's team in their latest round; a team row's own name. Never null (`Standing.team`). */
  team: string;
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

/** The only grades `risk.build_risk_register` gives a card. */
export type RiskLevel = "High" | "Medium" | "Low";

export interface RiskCard {
  level: RiskLevel;
  title: string;
  detail: string;
}
