import type { LapListDriver } from "./telemetryModel";

/** The quickest driver with a valid lap: the natural first map to show. */
export function defaultDriver(drivers: LapListDriver[]): string | null {
  return drivers.find((driver) => driver.best !== null)?.code ?? null;
}
