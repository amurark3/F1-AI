/**
 * Which session a countdown points at. No React, so it reads the same on the
 * server and in the browser.
 */

/** How long each session runs, in minutes — the backend's windows, for the live check. */
const SESSION_MINUTES: Record<string, number> = { Race: 120, "Sprint Qualifying": 45, "Sprint Shootout": 45 };
const DEFAULT_SESSION_MINUTES = 60;
const MINUTE_MS = 60_000;

export interface NextUp {
  name: string;
  startsAt: string;
  live: boolean;
}

/** The session on track now, else the next to start; null once the weekend is over. */
export function nextUp(sessions: Record<string, string>, nowMs: number): NextUp | null {
  const timed = Object.entries(sessions)
    .map(([name, startsAt]) => ({ name, startsAt, start: new Date(startsAt).getTime() }))
    .filter((session) => !Number.isNaN(session.start))
    .sort((a, b) => a.start - b.start);
  for (const session of timed) {
    const end = session.start + (SESSION_MINUTES[session.name] ?? DEFAULT_SESSION_MINUTES) * MINUTE_MS;
    if (nowMs < session.start) return { name: session.name, startsAt: session.startsAt, live: false };
    if (nowMs < end) return { name: session.name, startsAt: session.startsAt, live: true };
  }
  return null;
}
