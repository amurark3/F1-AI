/** The FIA decisions feed (`GET /api/weekend/{year}/{round}/feed`): its types and the pure rules the panel reads. */

/** The feed starts where the FIA's document collection does. */
export const FIRST_FEED_SEASON = 2019;
/** Rows shown before "Show all". */
export const PREVIEW_ROWS = 8;

export interface Outcome {
  kind: string;
  value: number | null;
}

export interface StewardsDecision {
  document: number;
  status: "summoned" | "decided";
  car: number;
  driver: string | null;
  competitor: string | null;
  session: string | null;
  incident_time: string | null;
  offence: string;
  articles: string[];
  decision: string | null;
  outcomes: Outcome[];
  hearing: string | null;
}

export interface DeletedLap {
  car: number;
  turn: number | null;
  entrant: string;
  time_of_day: string;
  lap_time: string | null;
}

export interface DeletedLaps {
  document: number;
  session: string;
  date: string;
  reason: "track_limits" | "yellow_flags" | "other";
  fact: string;
  laps: DeletedLap[];
}

export interface RuledNote {
  car: number;
  ruling: string;
  reason: string | null;
  document: number | null;
}

export interface StartingGrid {
  document: number;
  final: boolean;
  slots: Array<{ position: number; car: number; entrant: string; time: string | null; penalised: boolean }>;
  pit_lane: Array<{ car: number; entrant: string }>;
  notes: string[];
  penalties: RuledNote[];
}

interface FeedEventBase {
  number: number | null;
  title: string;
  /** As fia.com prints it (Paris wall clock); the panel shows `published_at`. */
  published: string;
  /** The same instant in UTC, `null` when fia.com's text did not parse. */
  published_at: string | null;
  url: string;
  withdrawn: string | null;
  unread: string | null;
}

export type FeedEvent =
  | (FeedEventBase & { kind: "penalty"; data: StewardsDecision | null })
  | (FeedEventBase & { kind: "deleted_laps"; data: DeletedLaps | null })
  | (FeedEventBase & { kind: "grid"; data: StartingGrid | null })
  | (FeedEventBase & {
      kind: "classification" | "entry_list" | "power_unit" | "pirelli" | "timetable" | "other";
      data: unknown;
    });

export interface WeekendFeed {
  year: number;
  round: number;
  event: string | null;
  latest: number | null;
  events: FeedEvent[];
}

/**
 * What the panel lists: stewards' decisions and summonses, deleted-lap sheets,
 * and starting grids (not permissions to start or parc fermé reports, which
 * the backend leaves unparsed; an unreadable grid sheet stays). Order kept.
 */
export function feedRows(events: readonly FeedEvent[]): FeedEvent[] {
  return events.filter(
    (event) =>
      event.kind === "penalty" ||
      event.kind === "deleted_laps" ||
      (event.kind === "grid" && (event.data !== null || event.unread !== null)),
  );
}

const OUTCOME_TEXT: Record<string, (value: number | null) => string> = {
  time_penalty: (value) => (value === null ? "Time penalty" : `${value} s time penalty`),
  grid_drop: (value) => (value === null ? "Grid drop" : `${value}-place grid drop`),
  back_of_grid: () => "Back of the grid",
  pit_lane_start: () => "Pit-lane start",
  disqualified: () => "Disqualified",
  stop_and_go: () => "Stop-and-go",
  drive_through: () => "Drive-through",
  reprimand: () => "Reprimand",
  warning: () => "Warning",
  fine: (value) => (value === null ? "Fine" : `€${value.toLocaleString("en-US")} fine`),
  penalty_points: (value) =>
    value === null ? "Penalty points" : `${value} penalty ${value === 1 ? "point" : "points"}`,
  no_further_action: () => "No further action",
};

/** One outcome as a short phrase ("10 s time penalty"). */
export function outcomeText({ kind, value }: Outcome): string {
  const text = OUTCOME_TEXT[kind];
  if (text) return text(value);
  const spaced = kind.replaceAll("_", " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** All a decision's outcomes, or the decision line as printed when the parser read none. */
export function outcomesText(decision: StewardsDecision): string {
  if (decision.outcomes.length === 0) return decision.decision ?? "";
  return decision.outcomes.map(outcomeText).join(" + ");
}

const RESULT_OUTCOMES: ReadonlySet<string> = new Set([
  "time_penalty",
  "grid_drop",
  "back_of_grid",
  "pit_lane_start",
  "disqualified",
  "stop_and_go",
  "drive_through",
]);

/** A decided, standing penalty that moves a result or a grid slot (the row's red rule). */
export function changesResult(event: FeedEvent): boolean {
  return (
    event.kind === "penalty" &&
    event.withdrawn === null &&
    event.data?.status === "decided" &&
    event.data.outcomes.some((outcome) => RESULT_OUTCOMES.has(outcome.kind))
  );
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** The panel's title, counted from the rows that still stand: "24 decisions, 98 laps deleted". */
export function feedTitle(rows: readonly FeedEvent[]): string {
  let decisions = 0;
  let laps = 0;
  for (const row of rows) {
    if (row.withdrawn !== null) continue;
    if (row.kind === "penalty" && row.data?.status === "decided") decisions += 1;
    if (row.kind === "deleted_laps") laps += row.data?.laps.length ?? 0;
  }
  const parts = [
    decisions > 0 ? plural(decisions, "decision") : null,
    laps > 0 ? `${plural(laps, "lap")} deleted` : null,
  ].filter((part) => part !== null);
  return parts.length > 0 ? parts.join(", ") : "No decisions yet";
}

/** Deleted laps per car: most first, then by car number. */
export function carCounts(laps: readonly DeletedLap[]): Array<{ car: number; count: number; entrant: string }> {
  const counts = new Map<number, { car: number; count: number; entrant: string }>();
  for (const lap of laps) {
    const known = counts.get(lap.car);
    counts.set(lap.car, { car: lap.car, count: (known?.count ?? 0) + 1, entrant: known?.entrant ?? lap.entrant });
  }
  return [...counts.values()].sort((a, b) => b.count - a.count || a.car - b.car);
}

/** "Doc 79", or "FIA document" when the title carried no number. */
export function docLabel(event: Pick<FeedEvent, "number">): string {
  return event.number === null ? "FIA document" : `Doc ${event.number}`;
}

/** The title without its "Doc N - " prefix. */
export function printedSubject(title: string): string {
  return title.replace(/^Doc\s+\d+\s*-\s*/i, "");
}

export function isCorrected(title: string): boolean {
  return /\bcorrected\b/i.test(title);
}

export const REASON_LABEL: Record<DeletedLaps["reason"], string> = {
  track_limits: "Track limits",
  yellow_flags: "Double yellow flags",
  other: "Other",
};
