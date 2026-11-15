import type { DriverLookup, DriverPrediction, DriverStanding, PredictionPhase, RaceEvent } from "./predictionModel";

export function confidenceMidpoint(prediction: DriverPrediction): number {
  return Math.round((prediction.confidence_low + prediction.confidence_high) / 2);
}

export function buildDriverLookup(drivers: DriverStanding[]): DriverLookup {
  return Object.fromEntries(drivers.map((driver) => [driver.code.toUpperCase(), driver]));
}

export function driverDisplayName(prediction: DriverPrediction, lookup: DriverLookup): string {
  const code = prediction.driver_code.toUpperCase();
  const name = lookup[code]?.name;
  if (name) return name;
  return prediction.driver_name && prediction.driver_name !== prediction.driver_code
    ? prediction.driver_name
    : prediction.driver_code;
}

export function countdownTo(value?: string): string | null {
  if (!value) return null;
  const target = new Date(value).getTime();
  if (Number.isNaN(target)) return null;
  const diff = target - Date.now();
  if (diff <= 0) return null;
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  return `${String(days).padStart(2, "0")}D ${String(hours).padStart(2, "0")}H ${String(minutes).padStart(2, "0")}M`;
}

export function raceSessionTime(race?: RaceEvent | null): string | undefined {
  if (!race?.sessions) return race?.date;
  return race.sessions.Race ?? race.sessions["Grand Prix"] ?? race.date;
}

/** Tab heading for a phase. */
export function phaseTabLabel(phase: PredictionPhase): string {
  return phase === "post_qualifying" ? "After Qualifying" : "Overall";
}

/** One line explaining what the phase's model did and did not look at. */
export function phaseDescription(phase: PredictionPhase): string {
  return phase === "post_qualifying"
    ? "Form, history and the qualifying result — the grid is known."
    : "Form, history and practice pace only — the grid is ignored.";
}

/**
 * Whether this weekend's qualifying session has already run.
 *
 * The post-qualifying prediction cannot exist before it has: the backend
 * refuses to store one, so the tab stays empty rather than quietly showing a
 * pre-qualifying call under the wrong heading. Falls back to the race start
 * when the schedule carries no qualifying entry, matching the backend's own
 * "roughly a day before the race" assumption.
 */
export function qualifyingHasRun(race: RaceEvent | null | undefined, now: number = Date.now()): boolean {
  if (!race) return false;

  const qualifying = race.sessions?.Qualifying;
  if (qualifying) {
    const start = new Date(qualifying).getTime();
    if (!Number.isNaN(start)) return start <= now;
  }

  const raceTime = raceSessionTime(race);
  if (!raceTime) return false;
  const start = new Date(raceTime).getTime();
  if (Number.isNaN(start)) return false;
  return start - 86400000 <= now;
}

export function estimatePodiumPct(prediction: DriverPrediction): number {
  const confidence = confidenceMidpoint(prediction);
  const pos = Math.max(1, prediction.position);
  const value = pos <= 3 ? confidence * 0.72 + (4 - pos) * 4 : confidence * 0.4 * Math.pow(0.72, pos - 3);
  return Math.max(0.2, Math.min(99, value));
}

export function formatPct(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function modelStatusColor(status: string): string {
  if (status === "available") return "#00FF78";
  if (status === "missing") return "#E10600";
  if (status === "limited" || status === "fallback") return "#F5C542";
  return "#3671C6";
}

/** Whether a race is currently running. */
export function isLiveRace(status: string): boolean {
  return status === "in_progress" || status === "live";
}

/** Places-moved colour, from tokens: gained, lost, held, or unknown. */
export function deltaColor(delta: number | null): string {
  if (delta == null) return "text-rc-ink-3";
  if (delta > 0) return "text-rc-gain";
  if (delta < 0) return "text-rc-red-text";
  return "text-rc-ink-2";
}

/** Places moved, signed. */
export function deltaLabel(delta: number | null): string {
  if (delta == null) return "-";
  return delta > 0 ? `+${delta}` : String(delta);
}

/**
 * The race a visitor should land on: whatever is running now, else the next one
 * up, else the most recent completed round.
 *
 * Shared by the server (to decide which prediction snapshot to prefetch) and
 * the client (to pick the initially selected round). Both must agree, or the
 * server would seed a snapshot the client never asks for.
 */
export function resolveDefaultRace(schedule: RaceEvent[]): RaceEvent | null {
  if (schedule.length === 0) return null;
  return (
    schedule.find((race) => isLiveRace(race.status)) ??
    schedule.find((race) => race.status === "upcoming") ??
    [...schedule].reverse().find((race) => race.status === "completed") ??
    schedule[0]
  );
}
