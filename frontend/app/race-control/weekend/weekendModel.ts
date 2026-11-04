/**
 * Pure helpers behind the race-weekend showcase: colours, copy and the small
 * bits of arithmetic the panels share. No React, so they read the same on the
 * server and in the browser.
 */
import { driverLabel, teamLabel } from "@/app/ui/names/names";

import type { SessionPhase, SessionWeatherRow, TableStakes, WeatherCondition } from "./weekendTypes";

/** Rain probability bands: dry, mixed, and likely wet. */
const RAIN_MIXED_PCT = 20;
const RAIN_WET_PCT = 50;
const DRY_COLOR = "#00FF78";
const MIXED_COLOR = "#FFF200";
const WET_COLOR = "#4C8DFF";

export function rainColor(pct: number | null): string {
  if (pct === null) return "#3A4254";
  if (pct >= RAIN_WET_PCT) return WET_COLOR;
  if (pct >= RAIN_MIXED_PCT) return MIXED_COLOR;
  return DRY_COLOR;
}

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
const COMPASS_STEP = 360 / COMPASS.length;

/** "SW" for 225°: the direction the wind blows *from*, as forecasts report it. */
export function compassPoint(degrees: number | null): string | null {
  if (degrees === null) return null;
  const index = Math.round((((degrees % 360) + 360) % 360) / COMPASS_STEP) % COMPASS.length;
  return COMPASS[index] ?? null;
}

/** The ambient backdrop a session card gets for its weather. */
export type Ambience = "sun" | "night" | "cloud" | "rain" | "storm" | "snow" | "none";

const AMBIENCE: Record<WeatherCondition, Ambience> = {
  clear: "sun",
  partly_cloudy: "sun",
  cloudy: "cloud",
  fog: "cloud",
  drizzle: "rain",
  rain: "rain",
  storm: "storm",
  snow: "snow",
  unknown: "none",
};

export function ambienceFor(condition: WeatherCondition, isDay: boolean | null): Ambience {
  const ambience = AMBIENCE[condition];
  return ambience === "sun" && isDay === false ? "night" : ambience;
}

/**
 * How far along the rail joining the session nodes the weekend has run, 0–1.
 *
 * The rail runs from the first node to the last. A live session puts the fill
 * on its own node; between sessions it stops halfway to the next one.
 */
export function railFill(phases: SessionPhase[]): number {
  const last = phases.length - 1;
  if (last < 1) return phases[0] === "done" ? 1 : 0;
  const live = phases.indexOf("live");
  if (live >= 0) return live / last;
  const done = phases.filter((phase) => phase === "done").length;
  if (done === 0) return 0;
  return done > last ? 1 : (done - 0.5) / last;
}

export interface WeekendSummary {
  wettest: SessionWeatherRow | null;
  coolest: number | null;
  warmest: number | null;
}

/** The wettest session and the temperature range across the weekend's forecasts. */
export function summariseWeekend(rows: SessionWeatherRow[]): WeekendSummary {
  const forecast = rows.filter((row) => row.forecast !== null);
  const temps = forecast
    .map((row) => row.forecast?.air_temp_c ?? null)
    .filter((value): value is number => value !== null);
  const wettest = forecast.reduce<SessionWeatherRow | null>((best, row) => {
    const rain = row.forecast?.rain_probability_pct ?? -1;
    return rain > (best?.forecast?.rain_probability_pct ?? -1) ? row : best;
  }, null);
  return {
    wettest,
    coolest: temps.length ? Math.min(...temps) : null,
    warmest: temps.length ? Math.max(...temps) : null,
  };
}

export type ClinchTone = "decided" | "possible" | "open";

/** Which championship a stakes table counts. */
export type ChampionshipTable = "drivers" | "constructors";

/** A contender in a sentence: the driver's full name, or the team's f1db name. */
function contenderName(table: ChampionshipTable, name: string, code: string | null = null): string {
  return table === "constructors" ? teamLabel({ name }, "name") : driverLabel({ name, code }, "full");
}

/** Championship points, which are whole except in the odd half-points race. */
export const formatPoints = (points: number): string => (Number.isInteger(points) ? String(points) : points.toFixed(1));

/**
 * The one-line headline for a championship this weekend. A thin reader: whether
 * the title is decided is the backend's `decided` (its shared title rule, which
 * settles a lead equal to the points left on count-back), never worked out here.
 */
export function clinchLine(
  stakes: TableStakes,
  venue: string,
  table: ChampionshipTable,
): { tone: ClinchTone; text: string } {
  const leader = contenderName(table, stakes.leader.name, stakes.leader.code);
  if (stakes.decided) return { tone: "decided", text: `${leader} has already clinched the title.` };
  const { clinch } = stakes;
  if (!clinch?.possible) {
    return {
      tone: "open",
      text: `The title can't be settled in ${venue} — ${formatPoints(stakes.max_available)} pts still on offer.`,
    };
  }
  const rival = contenderName(table, clinch.rival);
  if (clinch.margin_needed > 0) {
    return {
      tone: "possible",
      text: `${leader} clinches in ${venue} by outscoring ${rival} by ${formatPoints(clinch.margin_needed)}+ pts.`,
    };
  }
  return {
    tone: "possible",
    text: `${leader} clinches in ${venue} unless ${rival} outscores them by ${formatPoints(1 - clinch.margin_needed)}+ pts.`,
  };
}

/**
 * Where on a leader-scaled bar a rival must reach to stay in contention on
 * points. A bar ending exactly on it is the count-back's call; its row's `alive`
 * says which way that went. Null when every bar clears it (nobody can be out yet).
 */
export function reachLine(stakes: TableStakes): number | null {
  const leaderPoints = stakes.leader.points;
  const threshold = leaderPoints - stakes.max_available;
  return threshold > 0 ? (threshold / leaderPoints) * 100 : null;
}
