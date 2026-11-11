/**
 * What the top bar's race status chip says: the selected weekend's round and
 * where it stands now, plus the line its tooltip adds. No React, so it reads
 * the same in tests as on the page's one shared clock.
 */
import { countdownParts } from "../countdownParts";
import { nextUp } from "../nextUp";

/** The fields of the shell segment's `race` the chip reads. */
export interface ShellRace {
  round: number;
  name: string;
  /** The weekend's status: `upcoming`, `in_progress` (Friday to Sunday evening) or `completed`. */
  status: string;
  sessions: Record<string, string>;
}

/**
 * `live` while a session is on track; `pre-race` until the race starts, the
 * gaps between sessions included; `post-race` once every session has run.
 */
export type RacePhase = "live" | "pre-race" | "post-race";

export interface RaceStatus {
  phase: RacePhase;
  /** The chip's text: "R20 · Pre-race". */
  label: string;
  /** The Grand Prix, the tooltip's first line. */
  event: string;
  /** The tooltip's second line: the next session's countdown, or what is on track. */
  detail: string | null;
}

const FINISHED = "Every session has run";

/** The time left, coarsest first: "3d 02h 14m", "9h 08m 07s", "4m 09s". */
export function countdownText(targetMs: number, nowMs: number): string {
  const { days, hours, minutes, seconds } = countdownParts(targetMs, nowMs);
  if (days !== "00") return `${Number(days)}d ${hours}h ${minutes}m`;
  if (hours !== "00") return `${Number(hours)}h ${minutes}m ${seconds}s`;
  return `${Number(minutes)}m ${seconds}s`;
}

/** Where the weekend stands at `nowMs`, read from its session times. */
export function raceStatus(race: ShellRace, nowMs: number): RaceStatus {
  const round = `R${race.round}`;
  const base = { event: race.name };
  const session = nextUp(race.sessions, nowMs);

  if (session?.live) {
    return { ...base, phase: "live", label: `${round} · ${session.name} live`, detail: `${session.name} is on track` };
  }
  if (session) {
    const countdown = countdownText(new Date(session.startsAt).getTime(), nowMs);
    return { ...base, phase: "pre-race", label: `${round} · Pre-race`, detail: `${session.name} in ${countdown}` };
  }
  // No session left to run; with no timed session at all, the weekend's status decides.
  const untimed = Object.keys(race.sessions).length === 0;
  if (untimed && race.status === "upcoming") {
    return { ...base, phase: "pre-race", label: `${round} · Pre-race`, detail: null };
  }
  return { ...base, phase: "post-race", label: `${round} · Post-race`, detail: FINISHED };
}
