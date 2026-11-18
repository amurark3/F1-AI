/**
 * The official classification the Results tab prints, as
 * `GET /api/race-control/results/{year}/{round}` serves it
 * (`backend/app/services/race_results.py`), and the words it is read in.
 */

export type ResultStatus = "Finished" | "DNF" | "NC" | "DNS" | "DSQ";

export interface ResultDriver {
  driver_code: string;
  driver_name: string;
  team: string;
}

export interface ResultRow extends ResultDriver {
  /** Null for every car that is not `Finished`, whatever place a source lists it at. */
  position: number | null;
  status: ResultStatus;
  reason: string | null;
  laps: number | null;
  /** The winner's race time; null for everyone else. */
  time: string | null;
  gap: string | null;
  laps_down: number | null;
  /** Seconds added to the race time after the flag. */
  time_penalty: number | null;
  road_position: number | null;
  points: number | null;
  fastest_lap: boolean;
}

export interface ChangedAfterFlag extends ResultDriver {
  road_position: number;
  position: number | null;
  time_penalty: number | null;
  moved_up: Array<ResultDriver & { road_position: number; position: number | null }>;
}

export interface FastestLap extends ResultDriver {
  lap: number;
  time: string;
}

export interface ResultSource {
  source: string;
  role: string;
  version?: string | null;
  /** The FIA document number, for a classification read from the FIA's own document. */
  document?: number | null;
}

export interface SessionResult {
  final: boolean;
  sources: ResultSource[];
  classification: ResultRow[];
  changed_after_flag: ChangedAfterFlag[];
  fastest_lap: FastestLap | null;
}

export interface RaceResultsResponse {
  year: number;
  round: number;
  race: SessionResult | null;
  sprint: SessionResult | null;
  error?: string | null;
}

export type ResultsKind = "race" | "sprint";

/** The Pos cell: the place for a finisher, the status word for everyone else. */
export function positionLabel(row: ResultRow): string {
  return row.position === null ? row.status : String(row.position);
}

const STATUS_WORDS: Record<ResultStatus, string> = {
  Finished: "Finished",
  DNF: "Retired",
  NC: "Not classified",
  DNS: "Did not start",
  DSQ: "Disqualified",
};

/** A non-finisher's reason and laps completed; the status in words when the source gave neither. */
export function stoppedLabel(row: ResultRow): string {
  const parts = [row.reason, row.laps ? `${row.laps} ${row.laps === 1 ? "lap" : "laps"}` : null].filter(
    (part): part is string => Boolean(part),
  );
  return parts.length > 0 ? parts.join(" · ") : STATUS_WORDS[row.status];
}

/** A finisher's time cell: the winner's time, else the lapped car's laps down, else the gap. */
export function timeLabel(row: ResultRow): string {
  if (row.time) return row.time;
  if (row.laps_down) return `+${row.laps_down} ${row.laps_down === 1 ? "lap" : "laps"}`;
  return row.gap ?? "—";
}

/** `incl. +10 s · P7 on the road`, or null for a car with no time penalty. */
export function penaltyLabel(row: ResultRow): string | null {
  if (!row.time_penalty) return null;
  const road = row.road_position ? ` · P${row.road_position} on the road` : "";
  return `incl. +${row.time_penalty} s${road}`;
}

const SOURCE_NAMES: Record<string, (source: ResultSource) => string> = {
  f1db: ({ version }) => `f1db${version ? ` ${version}` : ""}, mirroring the FIA final classification`,
  "openf1-session-result": () => "OpenF1 session result",
  "fia-final-classification": ({ document }) => `FIA final classification${document ? `, document ${document}` : ""}`,
};

/** The provenance line: what the table was read from and whether the FIA's final has landed. */
export function provenanceNote(result: SessionResult): string {
  const names = result.sources.map((source) => SOURCE_NAMES[source.source]?.(source) ?? source.source);
  const state = result.final ? "final" : "provisional until the FIA final classification is published";
  return `Classification: ${names.join(", ")} · ${state}`;
}

/** The winner and the cars that retired, for the table's title; computed from the rows. */
export function resultsTitle(result: SessionResult): string {
  const winner = result.classification.find((row) => row.position === 1);
  const out = result.classification.filter((row) => row.status === "DNF").length;
  const head = winner ? `${winner.driver_name} wins` : "Classification";
  if (out === 0) return head;
  return `${head}; ${out} ${out === 1 ? "car retires" : "cars retire"}`;
}
