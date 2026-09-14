/**
 * The starting grid as the backend publishes it.
 *
 * The grid is a different fact from the qualifying classification: a driver who
 * qualifies third and takes a five-place penalty starts eighth, and a driver
 * released from the pit lane holds no grid slot at all. Every field here keeps
 * that distinction visible rather than flattening the two into one order.
 */

/** Which source answered, and therefore what the panel may claim. */
export type GridSource = "official_grid" | "qualifying_classification" | "unavailable";

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
}

export interface StartingGridResponse {
  year: number;
  round: number;
  /** False before qualifying has run: there is no grid and no stand-in for one. */
  available: boolean;
  /**
   * True when the order is the qualifying classification rather than the
   * published grid sheet, so no penalty has been applied to it.
   */
  provisional: boolean;
  source: GridSource;
  grid: GridSlot[];
  /** The subset of `grid` carrying a sanction. */
  penalties: GridSlot[];
  warnings?: string[];
  error?: string;
}
