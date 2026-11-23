/**
 * Pure helpers behind the race-weekend showcase: colours, copy and the small
 * bits of arithmetic the panels share. No React, so they read the same on the
 * server and in the browser.
 */
import { contenderName, nextEventSentence, type ChampionshipTable } from "@/app/lib/clinch";
import { rc } from "@/app/ui/tokens";

import type { MeasuredWeather, SessionForecast, SessionPhase, SessionWeatherRow, TableStakes } from "./weekendTypes";

/** Rain probability bands: dry, mixed and likely wet, rising from the caption tone to info blue. */
const RAIN_MIXED_PCT = 20;
const RAIN_WET_PCT = 50;

export function rainColor(pct: number | null): string {
  if (pct === null) return rc.dim;
  if (pct >= RAIN_WET_PCT) return rc.blue;
  if (pct >= RAIN_MIXED_PCT) return rc.ink2;
  return rc.ink3;
}

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
const COMPASS_STEP = 360 / COMPASS.length;

/** "SW" for 225°: the direction the wind blows *from*, as forecasts report it. */
export function compassPoint(degrees: number | null): string | null {
  if (degrees === null) return null;
  const index = Math.round((((degrees % 360) + 360) % 360) / COMPASS_STEP) % COMPASS.length;
  return COMPASS[index] ?? null;
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
  return { tone: "possible", text: nextEventSentence(table, stakes.leader, venue, clinch.needs) };
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

/** How many of a session's trackside readings reported rain. */
export function rainReadings(rainfall: boolean[]): { wet: number; total: number } {
  return { wet: rainfall.filter(Boolean).length, total: rainfall.length };
}

/** Measured track temperature minus the forecast's estimate, 1 dp; null when either is missing. */
export function trackDelta(forecast: SessionForecast | null, measured: MeasuredWeather): number | null {
  const estimate = forecast?.track_temp_c ?? null;
  if (estimate === null || measured.track_temp_c === null) return null;
  return Math.round((measured.track_temp_c - estimate) * 10) / 10;
}

/** "+3.4°", "−1.2°" (U+2212) and "0.0°". */
export function formatSignedDegrees(value: number): string {
  const text = `${Math.abs(value).toFixed(1)}°`;
  if (value === 0) return text;
  return `${value > 0 ? "+" : "−"}${text}`;
}
