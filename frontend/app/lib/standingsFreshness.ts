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
