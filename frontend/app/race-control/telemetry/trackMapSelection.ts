import { quickest } from "./qualifyingSegments";

import type { LapListDriver } from "./telemetryModel";

/** The quickest driver with a time (in the qualifying part, if one is on show): the natural first map to show. */
export function defaultDriver(drivers: LapListDriver[], segment: number | null = null): string | null {
  return quickest(drivers, segment)[0]?.code ?? null;
}
