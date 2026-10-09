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

/**
 * Short chip text for a sanction, or null when the driver starts where they
 * qualified.
 *
 * The offence is deliberately absent: the published grid sheet records the
 * places dropped, not the reason, and no reason is inferred here.
 */
export function penaltyChipLabel(slot: GridSlot): string | null {
  if (slot.pit_lane) return "PIT LANE";
  if (slot.start_from_back) return "BACK OF GRID";
  if (slot.penalty_positions) return `-${slot.penalty_positions} PLACES`;
  return null;
}

/** Where a driver lines up, written the way a timing screen would. */
export function startLabel(slot: GridSlot): string {
  if (slot.pit_lane) return "Pit lane";
  return slot.position === null ? "-" : `P${slot.position}`;
}

/** Where a driver qualified, or a dash when the classification is unknown. */
export function qualifiedLabel(slot: GridSlot): string {
  return slot.qualifying_position === null ? "-" : `P${slot.qualifying_position}`;
}

/** The penalty as published: a place count, or the sanction's own name. */
export function penaltyLabel(slot: GridSlot): string {
  if (slot.start_from_back) return "Back of grid";
  if (slot.penalty_positions) return `${slot.penalty_positions} places`;
  return slot.pit_lane ? "Pit lane start" : "-";
}

/**
 * Slots actually dropped, signed.
 *
 * A penalty of five places moves a driver fewer than five slots when someone
 * ahead of them is also penalised, so this reports the real movement rather
 * than restating the sanction.
 */
export function netMoveLabel(slot: GridSlot): string {
  if (slot.places_lost === null) return "-";
  if (slot.places_lost === 0) return "held";
  return slot.places_lost > 0 ? `-${slot.places_lost}` : `+${Math.abs(slot.places_lost)}`;
}

/** Colour for the net-move cell: a drop, a gain, or no movement. */
export function netMoveColor(slot: GridSlot): string {
  if (slot.places_lost === null) return "text-[#3F4756]";
  if (slot.places_lost > 0) return "text-[#FF4655]";
  if (slot.places_lost < 0) return "text-[#00FF78]";
  return "text-[#D7DBE7]";
}

/** Provenance line for the panel header, so the source is never implicit. */
export function gridSourceLabel(source: GridSource): string {
  if (source === "official_grid") return "official grid sheet";
  if (source === "qualifying_classification") return "qualifying order - provisional";
  return "not published";
}

/** Whether a payload holds a grid worth drawing. */
export function hasGrid(data: StartingGridResponse | undefined): boolean {
  return Boolean(data?.available) && (data?.grid.length ?? 0) > 0;
}
