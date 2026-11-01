/**
 * Where a driver, team or round lives in the app.
 *
 * Ids are f1db's (`max-verstappen`, `red-bull`): stable across every source and
 * season, unlike three-letter codes or display names. Kept free of React so
 * server components and plain modules can build links too.
 */

export type GrandPrixTab = "weekend" | "sessions" | "grid" | "stints" | "predictions";

export function driverHref(driverId: string): string {
  return `/race-control/drivers/${encodeURIComponent(driverId)}`;
}

export function teamHref(teamId: string): string {
  return `/race-control/constructors/${encodeURIComponent(teamId)}`;
}

/** A round of the Grand Prix Hub, opened on a given tab. */
export function grandPrixHref(round: number, tab?: GrandPrixTab): string {
  const query = new URLSearchParams({ round: String(round) });
  if (tab) {
    query.set("tab", tab);
  }
  return `/race-control/grand-prix?${query.toString()}`;
}
