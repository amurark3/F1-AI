/**
 * Pure helpers for laying out and labelling the starting grid.
 *
 * Kept out of the components so the stagger arithmetic and the penalty wording
 * can be reasoned about — and corrected — without touching JSX.
 */

import type { GridSlot, GridSource, StartingGridResponse } from "./gridModel";

/** One staggered row of the grid: an odd slot and the even slot set back from it. */
export interface GridRow {
  /** Row index from the front, starting at 1. */
  row: number;
  /** The odd-numbered slot (P1, P3, P5 …), on the leading side. */
  leading: GridSlot | null;
  /** The even-numbered slot (P2, P4, P6 …), set back from `leading`. */
  trailing: GridSlot | null;
}

/** Drivers with a grid slot, split from those starting from the pit lane. */
export interface GridLayout {
  rows: GridRow[];
  /** Pit-lane starters, who line up behind the grid rather than on it. */
  pitLane: GridSlot[];
}

/**
 * Arrange the grid into staggered rows, the way a Formula 1 grid is drawn.
 *
 * Odd positions lead each row and even positions sit back from them, so P1/P2
 * form row one, P3/P4 row two, and so on. Pit-lane starters are separated out
 * entirely: they hold no slot, and drawing them in one would misstate where
 * the race actually begins for them.
 */
export function buildGridLayout(slots: GridSlot[]): GridLayout {
  const pitLane: GridSlot[] = [];
  const byRow = new Map<number, GridRow>();

  for (const slot of slots) {
    const position = slot.position;
    if (slot.pit_lane || position === null) {
      if (slot.pit_lane) pitLane.push(slot);
      continue;
    }
    const row = Math.ceil(position / 2);
    const existing = byRow.get(row) ?? { row, leading: null, trailing: null };
    byRow.set(row, position % 2 === 1 ? { ...existing, leading: slot } : { ...existing, trailing: slot });
  }

  return {
    rows: [...byRow.values()].sort((a, b) => a.row - b.row),
    pitLane,
  };
}

const MINUS = "\u2212";

function placesWord(count: number): string {
  return `${count} ${count === 1 ? "place" : "places"}`;
}

/** The last numbered slot on the grid: a car there cannot lose a place to a penalty. */
export function lastSlot(slots: GridSlot[]): number {
  return Math.max(0, ...slots.map((slot) => slot.position ?? 0));
}

/**
 * Where the car qualified, only when that is news: a car that started where it
 * qualified says nothing, and a disqualified qualifier says `DSQ`.
 */
export function qualifiedNote(slot: GridSlot, dsq: ReadonlySet<string>): string | null {
  if (dsq.has(slot.driver_code)) return "DSQ";
  const qualified = slot.qualifying_position;
  return qualified === null || qualified === slot.position ? null : `Qualified P${qualified}`;
}

/** The sanction in the hub's vocabulary, or null. A penalty that moved nothing says so. */
export function penaltyNote(slot: GridSlot, last: number): string | null {
  if (slot.pit_lane) return "Pit lane";
  if (slot.start_from_back) return "Back of grid";
  if (!slot.penalty_positions) return null;
  const label = `${MINUS}${placesWord(slot.penalty_positions)}`;
  if (slot.places_lost !== 0) return label;
  return `${label} \u00b7 cost nothing${slot.position === last ? ", already at the back" : ""}`;
}

/** Places gained and the penalised cars that gave them: those that qualified ahead and start behind. */
export function promotedNote(slot: GridSlot, slots: GridSlot[]): { places: number; by: string[] } | null {
  if (slot.places_lost === null || slot.places_lost >= 0) return null;
  const qualified = slot.qualifying_position;
  const by = slots
    .filter(
      (other) =>
        other.penalised &&
        other.qualifying_position !== null &&
        qualified !== null &&
        other.qualifying_position < qualified &&
        (other.position ?? Infinity) > (slot.position ?? 0),
    )
    .map((other) => other.driver_code);
  return { places: -slot.places_lost, by };
}

/** The headline: how many sanctions the grid carries, counted from the payload. */
export function gridTitle(data?: StartingGridResponse): string | undefined {
  if (!data?.available || data.grid.length === 0) return undefined;
  if (data.provisional) return "Qualifying order, before any penalty";
  const count = data.penalties.length;
  if (count === 0) return "Every car starts where it qualified";
  return `${count} ${count === 1 ? "penalty" : "penalties"} on the grid`;
}

/** The note that ends the section: which source, and whether it is final. */
export function gridNote(data?: StartingGridResponse): string {
  if (!data?.available || data.grid.length === 0) return "No grid is published for this round yet.";
  if (data.provisional) {
    return `Order: the qualifying classification (${data.source_detail ?? "qualifying"}), provisional: no penalty is applied to it · the official grid replaces it once published`;
  }
  return "Grid: f1db, mirroring the FIA final starting grid · f1db records the places dropped, never the offence behind them";
}

/** Provenance line for the panel header, so the source is never implicit. */
export function gridSourceLabel(source: GridSource): string {
  if (source === "official_grid") return "official grid sheet";
  if (source === "qualifying_classification") return "qualifying order - provisional";
  return "not published";
}

/** Whether a payload holds a grid worth drawing. */
export function hasGrid(data: StartingGridResponse | undefined): boolean {
  return data?.available === true && data.grid.length > 0;
}
