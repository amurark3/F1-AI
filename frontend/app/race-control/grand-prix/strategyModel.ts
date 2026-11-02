/**
 * Tyre stints and pit stops for a race.
 *
 * Two sources joined by the backend: the compound and lap range come from
 * timing data, the pit-lane time from the published stop sheet. Either can
 * be absent without the other being useless, so both are flagged separately
 * rather than collapsed into one "available".
 */

export interface PitStop {
  driver_code: string;
  /** Which stop of the race this was for the driver, counting from 1. */
  stop: number;
  lap: number;
  /**
   * Pit-lane time as the sheet publishes it, entry to exit: e.g. "24.681" or
   * "1:14.773". Not the time stationary, which is a couple of seconds of it.
   */
  time: string | null;
  millis: number | null;
  /** Time stationary in the box, in milliseconds, when OpenF1 publishes it. */
  stationary_millis: number | null;
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
  /**
   * The stop that ended this stint. Null for a driver's last stint, which ends
   * at the flag or the retirement, and for a stop whose time is not published.
   */
  ended_by_stop: PitStop | null;
}

/**
 * How a driver's race ended, as the classification publishes it.
 *
 * Never inferred from laps or stints: a last stint with no stop after it looks
 * the same whether the car took the flag or stopped on track.
 */
export type FinishStatus = "finished" | "dnf" | "dns" | "dsq" | "not_classified";

export interface DriverStrategy {
  driver_code: string;
  team: string;
  /**
   * Where the driver finished. Null when the result does not place them,
   * which is a different state from finishing last.
   */
  finish_position: number | null;
  /** Null until a classification is published: the ending is then unknown. */
  status: FinishStatus | null;
  /** Laps completed, from the classification; null when it does not say. */
  laps_completed: number | null;
  /** Went into the pits on its last lap and retired there, which is not a stop. */
  retired_in_pits: boolean;
  /** Empty for a classified car with no stint data, such as one that never started. */
  stints: DriverStint[];
  /**
   * Pit stops actually made, from stint boundaries — excluding the final stint
   * (which ends at the flag) and any change forced by a red flag.
   */
  stops: number;
  /** Free tyre changes handed to the driver by a suspended race. */
  red_flag_changes: number;
  /** How many of those stops have a published pit-lane time. */
  timed_stops: number;
  total_laps: number;
}

export interface RaceStrategyResponse {
  year: number;
  round: number;
  available: boolean;
  has_stints: boolean;
  has_stops: boolean;
  /** Where each driver's status and the row order came from; null before a result is published. */
  classification_source: string | null;
  drivers: DriverStrategy[];
  stops: PitStop[];
  /** Stops whose lap matched no stint boundary: reported, never forced. */
  unmatched_stops: PitStop[];
  /** Stops the field actually made, from stint boundaries. */
  stops_made: number;
  /** Free tyre changes under a suspended race — not pit stops. */
  red_flag_changes: number;
  fastest_stop: PitStop | null;
  /** Where the stop sheet came from; null when none is published. */
  stops_source: string | null;
  /** Sheet entries left out because the race was suspended, not stops. */
  suspension_entries: number;
  warnings?: string[];
  error?: string;
}

const STATUS_CODE: Record<FinishStatus, string> = {
  finished: "",
  dnf: "DNF",
  dns: "DNS",
  dsq: "DSQ",
  not_classified: "NC",
};

/**
 * The short result for a driver's row: the classified position, or the
 * status for a car the classification does not place. "-" before any result.
 */
export function resultCode(driver: Pick<DriverStrategy, "finish_position" | "status">): string {
  if (driver.finish_position !== null) return `P${driver.finish_position}`;
  return driver.status === null ? "-" : STATUS_CODE[driver.status] || "-";
}

/** How the driver's last stint ended, in words, from the classification only. */
export function finalStintLabel(driver: Pick<DriverStrategy, "status" | "laps_completed" | "retired_in_pits">): string {
  const laps = driver.laps_completed;
  switch (driver.status) {
    case "finished":
      return "Took the flag";
    case "dnf": {
      const where = driver.retired_in_pits ? "Retired in the pits" : "Retired";
      return laps === null ? where : `${where} · lap ${laps}`;
    }
    case "dns":
      return "Did not start";
    case "dsq":
      return "Disqualified";
    case "not_classified":
      return laps === null ? "Not classified" : `Not classified · ${laps} laps`;
    case null:
      return "Result not published yet";
  }
}

/**
 * How one stint ended, for its tooltip.
 *
 * Only the last stint can end at the flag or a retirement. Any earlier one
 * ended in a stop or a red flag; a stop with no published time is still a
 * stop, so it says the time is missing rather than that no stop happened.
 */
export function stintEndingLabel(stint: DriverStint, driver: DriverStrategy, isLast: boolean): string {
  if (isLast) return finalStintLabel(driver);
  if (stint.ended_under_red_flag) return "Tyres changed under the red flag";
  const stop = stint.ended_by_stop;
  if (!stop) return "Stop time not published yet";
  return `Stop ${stop.stop} on lap ${stop.lap}: ${stopTimeLabel(stop)}`;
}

/**
 * A stop's times in words: the pit-lane time the sheet publishes, and the
 * stationary time when OpenF1 publishes that too.
 */
export function stopTimeLabel(stop: Pick<PitStop, "time" | "stationary_millis">): string {
  if (stop.time === null) return "pit-lane time not published yet";
  // "1:00.513" already reads as a time; "22.466" needs its unit.
  const lane = `${stop.time.includes(":") ? stop.time : `${stop.time} s`} in the pit lane`;
  if (stop.stationary_millis === null) return lane;
  return `${lane}, ${(stop.stationary_millis / 1000).toFixed(1)} s stationary`;
}
