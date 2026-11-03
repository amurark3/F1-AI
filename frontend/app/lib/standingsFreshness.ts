/**
 * How fresh a championship table is.
 *
 * The backend computes the current table from f1db's last published round plus
 * each later round's points from OpenF1 results. Those later rounds stay
 * provisional until f1db publishes them. Every standings payload (the standings
 * page, the stakes panel, the team and driver pages) carries these fields.
 */

export interface StandingsSource {
  source: string;
  role: "base" | "points" | "cross_check";
  through_round?: number;
  round?: number;
  version?: string | null;
  sessions?: string[];
  status?: "agrees" | "disagrees" | "unavailable";
}

export interface StandingsFreshness {
  /** The last round the table includes; null before any round has points. */
  as_of_round: number | null;
  /** True while a round in the table is not yet in f1db. */
  provisional: boolean;
  sources: StandingsSource[];
}

/** "after round 19 · provisional", or null when the table holds no round yet. */
export function standingsLabel(freshness: Partial<StandingsFreshness> | null | undefined): string | null {
  const round = freshness?.as_of_round;
  if (!round) return null;
  const status = freshness.provisional ? "provisional" : "confirmed";
  return `after round ${round} · ${status}`;
}

/** The backend's feed ids in words; an id not listed here shows as sent. */
const SOURCE_NAMES: Record<string, string> = {
  f1db: "f1db",
  "openf1-session-result": "OpenF1 session results",
  "openf1-championship": "OpenF1 championship table",
  "jolpica-standings": "Jolpica standings",
};

const ROLE_NAMES: Record<StandingsSource["role"], string> = {
  base: "Base",
  points: "Points",
  cross_check: "Cross-check",
};

/** OpenF1 session codes that score points; any other code shows as sent. */
const SESSION_NAMES: Record<string, string> = { R: "race", S: "sprint" };

function roundPart(source: StandingsSource): string | null {
  if (source.through_round) return `through round ${source.through_round}`;
  if (!source.round) return null;
  const sessions = source.sessions?.length
    ? ` (${source.sessions.map((code) => SESSION_NAMES[code] ?? code).join(", ")})`
    : "";
  return `round ${source.round}${sessions}`;
}

/**
 * One source in words, for the list behind a freshness label:
 * "Base: f1db v2026.19.0, through round 19",
 * "Points: OpenF1 session results, round 20 (sprint, race)",
 * "Cross-check: Jolpica standings, round 20 — disagrees".
 */
export function sourceLine(source: StandingsSource): string {
  const name = SOURCE_NAMES[source.source] ?? source.source;
  const feed = source.version ? `${name} ${source.version}` : name;
  const parts = [feed, roundPart(source)].filter((part): part is string => part !== null).join(", ");
  const status = source.status ? ` — ${source.status}` : "";
  return `${ROLE_NAMES[source.role]}: ${parts}${status}`;
}

/** True when a feed the table was checked against reports different points. */
export function hasDisagreement(freshness: Partial<StandingsFreshness> | null | undefined): boolean {
  return freshness?.sources?.some((source) => source.status === "disagrees") ?? false;
}
