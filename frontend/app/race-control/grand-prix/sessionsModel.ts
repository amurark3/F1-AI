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

/** The qualifying parts, last first: a car's part is the last one it set a time in. */
export type QualifyingPart = "q1" | "q2" | "q3";

/** A practice row: who the car belonged to when a stand-in drove it. */
export interface PracticeEntry extends SessionEntry {
  stand_in_for: { driver_code: string; driver_name: string } | null;
}

/** A qualifying row, with the gap measured inside the part the car ran in. */
export interface QualifyingEntry extends SessionEntry {
  part: QualifyingPart | null;
  /** Gap to the fastest lap of `part` ("+0.310"); null for that lap's owner and for a disqualified car. */
  part_gap: string | null;
  /** Disqualified cars that lifted this one into a part it did not run in. */
  promoted_by: string[];
}

export interface PracticeSession extends SessionBase {
  kind: "practice";
  entries: PracticeEntry[];
}

export interface QualifyingSession extends SessionBase {
  kind: "qualifying";
  entries: QualifyingEntry[];
}

/** A race classification: the Results tab's story, not this payload's. */
export interface RaceSession extends SessionBase {
  kind: "race";
  entries: SessionEntry[];
}

export type ClassificationSession = PracticeSession | QualifyingSession | RaceSession;

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
