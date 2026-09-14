/**
 * Tyre stints and pit stops for a race.
 *
 * Two sources joined by the backend: the compound and lap range come from
 * timing data, the stationary time from the published stop sheet. Either can
 * be absent without the other being useless, so both are flagged separately
 * rather than collapsed into one "available".
 */

export interface PitStop {
  driver_code: string;
  /** Which stop of the race this was for the driver, counting from 1. */
  stop: number;
  lap: number;
  /** Stationary time as published, e.g. "24.681" or "1:14.773". */
  time: string | null;
  millis: number | null;
}

export interface DriverStint {
  driver_code: string;
  stint: number;
  /** Null when timing data has lap rows but no compound. */
  compound: string | null;
  start_lap: number;
  end_lap: number;
  laps: number;
  /** Laps already on the set when the stint began; 0 means new. */
  tyre_life_start: number | null;
  /** Null when the tyre history was not recorded — never assume fresh. */
  fresh: boolean | null;
  /**
   * True when this stint ended on a red-flagged lap.
   *
   * A suspended race sends the whole field into the pit lane to change tyres
   * for free, which looks exactly like a stop in the lap data but is not one.
   * This is why a driver can show two compounds beside a count of zero stops.
   */
  ended_under_red_flag: boolean;
  /** The stop that ended this stint; null for the stint that ran to the flag. */
  ended_by_stop: PitStop | null;
}

export interface DriverStrategy {
  driver_code: string;
  team: string;
  /**
   * Where the driver finished. Null when the result does not place them,
   * which is a different state from finishing last.
   */
  finish_position: number | null;
  stints: DriverStint[];
  /**
   * Pit stops actually made, from stint boundaries — excluding the final stint
   * (which ends at the flag) and any change forced by a red flag.
   */
  stops: number;
  /** Free tyre changes handed to the driver by a suspended race. */
  red_flag_changes: number;
  /** How many of those stops have a published stationary time. */
  timed_stops: number;
  total_laps: number;
}

export interface RaceStrategyResponse {
  year: number;
  round: number;
  available: boolean;
  has_stints: boolean;
  has_stops: boolean;
  drivers: DriverStrategy[];
  stops: PitStop[];
  /** Stops whose lap matched no stint boundary: reported, never forced. */
  unmatched_stops: PitStop[];
  /** Stops the field actually made, from stint boundaries. */
  stops_made: number;
  /** Free tyre changes under a suspended race — not pit stops. */
  red_flag_changes: number;
  fastest_stop: PitStop | null;
  warnings?: string[];
  error?: string;
}
