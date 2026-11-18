/**
 * The starting grid as the backend publishes it.
 *
 * The grid is a different fact from the qualifying classification: a driver who
 * qualifies third and takes a five-place penalty starts eighth, and a driver
 * released from the pit lane holds no grid slot at all. Every field here keeps
 * that distinction visible rather than flattening the two into one order.
 */

/** Which source answered, and therefore what the panel may claim. */
export type GridSource = "official_grid" | "fia_starting_grid" | "qualifying_classification" | "unavailable";

/** One FIA ruling on a car's grid slot: what was decided, why, and the stewards' document behind it. */
export interface GridReason {
  ruling: string;
  reason: string | null;
  document: number | null;
}

/** The FIA starting grid the order or the reasons were read from. */
export interface FiaGridDocument {
  number: number | null;
  final: boolean;
  url: string;
}

export interface GridSlot {
  driver_code: string;
  driver_name: string;
  team: string;
  /** Grid slot, or null for a pit-lane start. */
  position: number | null;
  /** Where the driver qualified, before any penalty. */
  qualifying_position: number | null;
  /** Places dropped, or null for an unquantified sanction. */
  penalty_positions: number | null;
  /** A start-from-the-back sanction, which carries no fixed place count. */
  start_from_back: boolean;
  /** A pit-lane release: the driver starts behind the grid, not on it. */
  pit_lane: boolean;
  /** True when any sanction moved this driver off their qualifying slot. */
  penalised: boolean;
  /**
   * Slots actually dropped between qualifying and the grid.
   *
   * Null when either position is unknown — never 0, which would read as
   * "held position".
   */
  places_lost: number | null;
  /** The FIA's rulings on this car, notes first; empty or absent when the FIA grid is not held. */
  reasons?: GridReason[];
  /**
   * True when no source could give this qualifier a driver code: the slot
   * keeps its place with `driver_code` empty. Nothing may be matched to it.
   */
  code_unresolved?: boolean;
}

export interface StartingGridResponse {
  year: number;
  round: number;
  /** False before qualifying has run: there is no grid and no stand-in for one. */
  available: boolean;
  /**
   * True when the order can still change: the qualifying classification standing in
   * for the grid (no penalty applied to it), or the FIA's provisional starting grid.
   */
  provisional: boolean;
  source: GridSource;
  /** Which feed a provisional order came from ("jolpica-qualifying"); absent on an official grid. */
  source_detail?: string;
  /** The FIA starting grid read for this round, or null when the store holds none. */
  fia_document?: FiaGridDocument | null;
  grid: GridSlot[];
  /** The subset of `grid` carrying a sanction. */
  penalties: GridSlot[];
  warnings?: string[];
  error?: string;
}
