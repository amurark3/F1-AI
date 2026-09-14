import type { DriverPrediction } from "@/app/components/PredictionDriverCard";

import type {
  DriverLookup,
  DriverStanding,
  PredictionPhase,
  RaceEvent,
  RiskPrediction,
} from "./predictionModel";

const POINTS_BY_POSITION = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1];

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

/**
 * Generational suffixes, which are part of the surname rather than the surname
 * itself. Without this, "Carlos Sainz Jr." reduces to "Jr." — which is what the
 * starting grid rendered before the list existed.
 */
const NAME_SUFFIXES = new Set(["jr", "jr.", "sr", "sr.", "i", "ii", "iii", "iv"]);

/** The surname a timing screen would show, suffix kept attached to it. */
export function shortName(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length < 2) return name;

  const last = parts[parts.length - 1];
  if (!NAME_SUFFIXES.has(last.toLowerCase())) return last;
  // Keep the suffix with the name it belongs to, e.g. "Sainz Jr.".
  return parts.length > 2 ? `${parts[parts.length - 2]} ${last}` : name;
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

export function phaseLabel(phase?: string | null): string {
  if (phase === "post_qualifying") return "post-qualifying";
  if (phase === "pre_qualifying") return "pre-qualifying";
  return "no snapshot";
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

export function pointsForPosition(position: number): number {
  return POINTS_BY_POSITION[position - 1] ?? 0;
}

export function estimateWinPct(prediction: DriverPrediction): number {
  const confidence = confidenceMidpoint(prediction);
  const pos = Math.max(1, prediction.position);
  const value = pos === 1 ? confidence * 0.62 : confidence * 0.45 * Math.pow(0.58, pos - 1);
  return Math.max(0.1, Math.min(99, value));
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

export function parseGridPosition(prediction: DriverPrediction): number | null {
  const factors = (prediction.factors ?? []).join(" ");
  if (/pole position/i.test(factors)) return 1;
  const match =
    /(?:qualifying|practice|front row start).*?P(\d+)/i.exec(factors) ?? /P(\d+)\s*(?:in sessions)?/i.exec(factors);
  return match ? Number(match[1]) : null;
}

export function deltaVsGrid(prediction: DriverPrediction): number | null {
  const grid = parseGridPosition(prediction);
  if (!grid) return null;
  return grid - prediction.position;
}

export function buildRiskLookup(rows: RiskPrediction[]): Record<string, RiskPrediction> {
  return Object.fromEntries(rows.map((row) => [row.driver_code.toUpperCase(), row]));
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

/** Round-selector dot colour for a race by its state. */
export function roundColor(completed: boolean, live: boolean, active: boolean): string {
  if (completed) return "#00FF78";
  if (live || active) return "#E10600";
  return "#333B49";
}

/**
 * Short state label shown under a round selector.
 *
 * Describes the round, not the prediction: this strip used to double as an
 * accuracy readout, where "scored" meant a stored call had been compared
 * against the result. As plain navigation it reports whether the race has run.
 */
export function roundStateLabel(live: boolean, completed: boolean, active: boolean): string {
  if (live) return "live";
  if (completed) return "done";
  return active ? "selected" : "-";
}

/** Grid-delta cell colour: gained, lost, held, or unknown. */
export function deltaColor(delta: number | null): string {
  if (delta == null) return "text-[#3F4756]";
  if (delta > 0) return "text-[#00FF78]";
  if (delta < 0) return "text-[#FF4655]";
  return "text-[#D7DBE7]";
}

/** Grid-delta cell text, signed. */
export function deltaLabel(delta: number | null): string {
  if (delta == null) return "-";
  return delta > 0 ? `+${delta}` : String(delta);
}

/** Result-review badge colour: correct, evaluated-miss, or not scored. */
export function reviewColor(winnerCorrect: boolean, evaluated: boolean): string {
  if (winnerCorrect) return "#00FF78";
  return evaluated ? "#E10600" : "#3671C6";
}

/** Circuit length line: kilometres when known, else lap count, else a dash. */
export function circuitLengthLabel(circuit?: RaceEvent["circuit"]): string {
  if (circuit?.length_km) return `${circuit.length_km} km`;
  if (circuit?.laps) return `${circuit.laps} laps`;
  return "-";
}

/** Result-review badge text: outcome when scored, otherwise the scored count. */
export function reviewBadgeLabel(
  review: { evaluated?: boolean; winner_correct?: boolean } | undefined,
  racesEvaluated: number,
): string {
  if (!review?.evaluated) return `${racesEvaluated} scored predictions`;
  return review.winner_correct ? "winner hit" : "winner miss";
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
