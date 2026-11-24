/**
 * The Review view's rows and sentences, computed from the stored review and the
 * Results classification. A retirement carries its call, `DNF` and a reason,
 * never a place or a delta.
 */

import { stoppedLabel, type RaceResultsResponse } from "./resultsModel";

import type { PredictionDriverResult, PredictionReview } from "./predictionModel";

/** The risk the scoring counts as a retirement call; mirrors the backend's `DNF_RISK_THRESHOLD`. */
export const DNF_FLAG_PCT = 16;

/** A car within this many places of its call counts as "within 3". */
const NEAR = 3;

export interface PlacedRow {
  kind: "placed";
  code: string;
  called: number;
  finished: number;
  /** `called - finished`: positive means the car finished ahead of the call. */
  delta: number;
}

export interface OutRow {
  kind: "out";
  code: string;
  called: number;
  /** `DNF`, `DNS`, `DSQ` or `NC`. */
  status: string;
  /** Reason and laps from the classification, or the status in words. */
  detail: string;
  risk: number | null;
  flagged: boolean;
}

export type ReviewRow = PlacedRow | OutRow;

function outRow(row: PredictionDriverResult, called: number, detail: string): OutRow {
  const risk = row.predicted_dnf_risk_pct ?? null;
  return {
    kind: "out",
    code: row.driver_code,
    called,
    status: row.status ?? "DNF",
    detail,
    risk,
    flagged: risk !== null && risk >= DNF_FLAG_PCT,
  };
}

/** One row per car the model called, in called order. */
export function buildReviewRows(review: PredictionReview, results: RaceResultsResponse | undefined): ReviewRow[] {
  const classified = new Map((results?.race?.classification ?? []).map((row) => [row.driver_code, row]));
  const rows: ReviewRow[] = [];
  for (const row of review.driver_results ?? []) {
    if (row.predicted_position === null) continue;
    if (row.actual_position !== null && row.position_delta !== null) {
      rows.push({
        kind: "placed",
        code: row.driver_code,
        called: row.predicted_position,
        finished: row.actual_position,
        delta: -row.position_delta,
      });
      continue;
    }
    const result = classified.get(row.driver_code);
    rows.push(outRow(row, row.predicted_position, result ? stoppedLabel(result) : (row.status ?? "DNF")));
  }
  return rows.toSorted((a, b) => a.called - b.called);
}

export function placedRows(rows: ReviewRow[]): PlacedRow[] {
  return rows.filter((row): row is PlacedRow => row.kind === "placed");
}

export function retiredRows(rows: ReviewRow[]): OutRow[] {
  return rows
    .filter((row): row is OutRow => row.kind === "out" && row.status === "DNF")
    .toSorted((a, b) => (b.risk ?? 0) - (a.risk ?? 0));
}

/** Classified cars within three places of the call. */
export function withinThree(rows: ReviewRow[]): number {
  return placedRows(rows).filter((row) => Math.abs(row.delta) <= NEAR).length;
}

/** `(position - 1) / (span)` as a percentage along the track, for a grid of `size` places. */
export function trackPercent(position: number, size: number): number {
  return ((position - 1) / Math.max(1, size - 1)) * 100;
}

/** The last place any call or result sits at, which sets the track's length. */
export function trackSize(rows: ReviewRow[]): number {
  return Math.max(2, ...rows.map((row) => (row.kind === "placed" ? Math.max(row.called, row.finished) : row.called)));
}

const PLACES = (count: number) => `${count} ${count === 1 ? "place" : "places"}`;

/** The chart's finding: who beat the call by most, from the rows. */
export function chartTitle(rows: ReviewRow[], surnameOf: (code: string) => string): string {
  const placed = placedRows(rows);
  const best = Math.max(0, ...placed.map((row) => row.delta));
  if (best === 0) return "No classified car beat its call";
  const names = placed.filter((row) => row.delta === best).map((row) => surnameOf(row.code));
  return `${names.join(" and ")} beat${names.length === 1 ? "s" : ""} the call by ${PLACES(best)}`;
}

/** The retirement panel's finding, from the review's own retirement counts. */
export function retirementTitle(review: PredictionReview): string {
  const caught = review.dnf_correct ?? 0;
  const actual = review.dnf_actual ?? 0;
  if (actual === 0) return "No car retired";
  return `The risk model flagged ${caught} of the ${actual} ${actual === 1 ? "retirement" : "retirements"}`;
}

/** What the winner tile says: the call against who won. */
export function winnerSub(review: PredictionReview, nameOf: (code: string) => string): string {
  const called = review.predicted_winner;
  const won = review.actual_winner;
  if (!called || !won) return "No winner recorded";
  return review.winner_correct
    ? `Called ${nameOf(called)} P1 · they won`
    : `Called ${nameOf(called)} · ${nameOf(won)} won`;
}
