/**
 * Where the Grand Prix Hub is pointed: which round, which section, and which
 * view of the prediction — all held in the URL so any of them can be linked to.
 *
 * Pure functions only; the hook that binds them to the router lives in
 * `useHubUrlState`.
 */

import type { GrandPrixTab } from "@/app/lib/entityLinks";
import { raceQuery, readRaceYear } from "@/app/ui/race-picker/raceUrl";
import { RACE_LOCK } from "@/app/ui/race-picker/useRaceResults";

import type { StartingGridResponse } from "./gridModel";
import type { RaceEvent } from "./predictionModel";
import type { RaceResultsResponse } from "./resultsModel";
import type { WeekendSessionsResponse } from "./sessionsModel";

export type HubTab = GrandPrixTab;

/** The views of one stored prediction, shown inside the Predictions tab. */
export type PredictionView = "order" | "podium" | "risk" | "model" | "review";

export const HUB_TABS: ReadonlyArray<{ key: HubTab; label: string }> = [
  { key: "weekend", label: "Weekend" },
  { key: "sessions", label: "Sessions" },
  { key: "grid", label: "Grid" },
  { key: "results", label: "Results" },
  { key: "stints", label: "Stints" },
  { key: "predictions", label: "Predictions" },
];

/**
 * Whether qualifying has set a grid yet: the Grand Prix's, or on a sprint weekend
 * the sprint's. `undefined` until both calls have answered.
 */
export function gridSet(grid?: StartingGridResponse, sessions?: WeekendSessionsResponse): boolean | undefined {
  if (grid?.available || sessions?.sessions.some((session) => session.kind === "grid")) return true;
  return grid && sessions ? false : undefined;
}

/**
 * The tab strip, each section locked until it has something to show: Grid needs
 * qualifying, Results a sprint or race classification, Stints the race's.
 * Unknown (`undefined`: loading, failed, or no round yet) locks nothing; `null`
 * results mean the round has not started.
 */
export function hubTabs(
  results: RaceResultsResponse | null | undefined,
  hasGrid?: boolean,
): ReadonlyArray<{ key: HubTab; label: string; locked?: string }> {
  const race = Boolean(results?.race?.classification.length);
  const any = race || Boolean(results?.sprint?.classification.length);
  const known = results !== undefined;
  const reasons: Partial<Record<HubTab, string | false>> = {
    grid: hasGrid === false && "Unlocks once qualifying sets the starting grid.",
    results: known && !any && "Unlocks once the sprint or race classification is published.",
    stints: known && !race && RACE_LOCK,
  };
  return HUB_TABS.map((tab) => {
    const locked = reasons[tab.key];
    return locked ? { ...tab, locked } : tab;
  });
}

export const PREDICTION_VIEWS: ReadonlyArray<{ key: PredictionView; label: string; title: string }> = [
  { key: "order", label: "Order", title: "The predicted finishing order" },
  { key: "podium", label: "Podium", title: "The top three, and why the winner leads" },
  { key: "risk", label: "DNF / Crash", title: "Retirement and incident risk per driver" },
  { key: "model", label: "Model", title: "What the model was fed and what it produced" },
  { key: "review", label: "Review", title: "How the prediction scored against the result" },
];

export interface HubSelection {
  year: number | null;
  round: number | null;
  tab: HubTab | null;
  view: PredictionView | null;
}

function positiveInt(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

/** Reads untrusted URL params into a selection, dropping anything malformed. */
export function readHubParams(search: URLSearchParams, currentYear: number): HubSelection {
  return {
    year: readRaceYear(search, currentYear),
    round: positiveInt(search.get("round")),
    tab: HUB_TABS.find((item) => item.key === search.get("tab"))?.key ?? null,
    view: PREDICTION_VIEWS.find((item) => item.key === search.get("view"))?.key ?? null,
  };
}

export function hubQuery(selection: HubSelection): string {
  const query = raceQuery(selection.round, selection.year);
  if (selection.tab !== null) query.set("tab", selection.tab);
  if (selection.view !== null) query.set("view", selection.view);
  return query.toString();
}

/** After the race, the prediction opens on how it scored; before, on the call itself. */
export function defaultPredictionView(race: RaceEvent | null): PredictionView {
  return race?.status === "completed" ? "review" : "order";
}
