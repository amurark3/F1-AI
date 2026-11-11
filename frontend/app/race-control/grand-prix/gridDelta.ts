/**
 * The predictions table's "vs grid" column: the predicted finish against where
 * the car actually starts.
 *
 * The start comes from the starting grid (`/api/race-control/grid/{year}/{round}`),
 * matched by driver code. It used to be parsed out of the prediction's own
 * explanation text, which often held only the model's projection, so the column
 * compared the prediction with itself. It means the same on both phase tabs.
 *
 * Every state is labelled rather than guessed (docs/DATA_SOURCES.md, accuracy
 * rules 3 and 7): a pit-lane start is not a slot number, a driver missing from
 * the grid gets no number, and before qualifying there is no grid at all.
 */

import { gridSourceLabel, hasGrid } from "./gridHelpers";
import { deltaColor, deltaLabel } from "./predictionHelpers";

import type { GridSlot, StartingGridResponse } from "./gridModel";
import type { DriverPrediction } from "./predictionModel";

/** Why a row has no number. */
export type GridDeltaUnknownReason =
  /** The grid has not loaded, or the request failed. */
  | "grid_not_loaded"
  /** The round has no grid yet: qualifying has not run or has no results. */
  | "no_grid"
  /** Every slot is coded and none is this driver's. */
  | "not_on_grid"
  /** This driver's code is not on the grid, but a slot has no code, so it may be theirs. */
  | "slot_unidentified"
  /** The driver's slot was published with no position and is not a pit-lane start. */
  | "no_slot";

/** What the grid says about one predicted driver. */
export type GridDelta =
  /** `places` = `start − finish`: positive is places gained on the grid slot. */
  | { kind: "places"; start: number; finish: number; places: number }
  | { kind: "pit_lane" }
  | { kind: "unknown"; reason: GridDeltaUnknownReason };

/** The cell as drawn: its text, its token colour and a sentence saying what it means. */
export interface GridDeltaCell {
  text: string;
  className: string;
  note: string;
}

const UNKNOWN_TEXT = "—";
const UNKNOWN_CLASS = "text-rc-ink-3";
const PIT_LANE_CLASS = "text-rc-ink-2";

const UNKNOWN_NOTES: Record<GridDeltaUnknownReason, string> = {
  grid_not_loaded: "The starting grid has not loaded",
  no_grid: "No grid yet",
  not_on_grid: "Not on the starting grid",
  slot_unidentified: "Not matched: a grid slot has no driver code",
  no_slot: "No grid slot published",
};

/** A slot a driver can be matched to: one carrying a code its source stands behind. */
function isIdentified(slot: GridSlot): boolean {
  return slot.code_unresolved !== true && slot.driver_code.trim() !== "";
}

function unknown(reason: GridDeltaUnknownReason): GridDelta {
  return { kind: "unknown", reason };
}

/** The predicted driver's place on the starting grid, by code, or why there is none. */
export function gridDelta(
  prediction: Pick<DriverPrediction, "driver_code" | "position">,
  grid: StartingGridResponse | undefined,
): GridDelta {
  if (!grid || grid.error) return unknown("grid_not_loaded");
  if (!hasGrid(grid)) return unknown("no_grid");

  const code = prediction.driver_code.toUpperCase();
  const slot = grid.grid.find((candidate) => isIdentified(candidate) && candidate.driver_code.toUpperCase() === code);
  if (!slot) {
    return unknown(grid.grid.every(isIdentified) ? "not_on_grid" : "slot_unidentified");
  }
  if (slot.pit_lane) return { kind: "pit_lane" };
  if (slot.position === null) return unknown("no_slot");

  return {
    kind: "places",
    start: slot.position,
    finish: prediction.position,
    places: slot.position - prediction.position,
  };
}

/** How a `GridDelta` is written in the table. */
export function gridDeltaCell(delta: GridDelta): GridDeltaCell {
  if (delta.kind === "pit_lane") {
    return { text: "Pit lane", className: PIT_LANE_CLASS, note: "Starts from the pit lane" };
  }
  if (delta.kind === "unknown") {
    return { text: UNKNOWN_TEXT, className: UNKNOWN_CLASS, note: UNKNOWN_NOTES[delta.reason] };
  }
  return {
    text: deltaLabel(delta.places),
    className: deltaColor(delta.places),
    note: `Starts P${delta.start}, predicted P${delta.finish}`,
  };
}

/** The table header's word on which grid the column reads, so its source is never implicit. */
export function gridColumnNote(grid: StartingGridResponse | undefined, loading: boolean): string {
  return `vs grid: ${gridState(grid, loading)}`;
}

function gridState(grid: StartingGridResponse | undefined, loading: boolean): string {
  if (!grid) return loading ? "grid loading" : "grid unavailable";
  if (grid.error) return "grid unavailable";
  return hasGrid(grid) ? gridSourceLabel(grid.source) : "no grid yet";
}
