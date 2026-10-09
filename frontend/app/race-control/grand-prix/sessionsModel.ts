/**
 * The sessions a race weekend actually ran.
 *
 * The backend returns only sessions that produced a classification, so this
 * list *is* the weekend's format: three practice sessions on a conventional
 * weekend, one plus the sprint set on a sprint weekend, and nothing at all for
 * a round that has not been run. Nothing here should be inferred from a
 * calendar flag.
 */

import type { GridSlot } from "./gridModel";

/** Which columns carry meaning for a session. */
export type SessionKind = "practice" | "qualifying" | "race" | "grid";

export interface SessionEntry {
  driver_code: string;
  driver_name: string;
  team: string;
  /** Classified position, or null when the driver was not classified. */
  position: number | null;
  /** Carries "DNF"/"NC" where a number cannot. */
  position_text: string;
  /** Best lap (practice) or total/interval (race). */
  time: string | null;
  gap: string | null;
  laps: number | null;
  q1: string | null;
  q2: string | null;
  q3: string | null;
  points: number | null;
  /** The slot a sprint was started from. */
  grid: number | null;
  /** Retirement cause; null for a classified finisher. */
  retired: string | null;
}

interface SessionBase {
  id: string;
  /** Short tab label, e.g. "FP1". */
  label: string;
  /** Full name for the panel heading. */
  name: string;
}

/** A session that produced a classification: practice, qualifying, a race. */
export interface ClassificationSession extends SessionBase {
  kind: "practice" | "qualifying" | "race";
  entries: SessionEntry[];
}

/**
 * A grid, which is an order rather than a classification.
 *
 * Its rows are grid slots, not session entries, and it is the only session
 * kind that carries penalties — so it is a separate member of the union
 * rather than a classification with optional extra fields.
 */
export interface GridSession extends SessionBase {
  kind: "grid";
  entries: GridSlot[];
  penalties: GridSlot[];
}

export type WeekendSession = ClassificationSession | GridSession;

export interface WeekendSessionsResponse {
  year: number;
  round: number;
  available: boolean;
  /** True only when a sprint was actually run, not merely scheduled. */
  is_sprint: boolean;
  sessions: WeekendSession[];
  warnings?: string[];
  error?: string;
}
