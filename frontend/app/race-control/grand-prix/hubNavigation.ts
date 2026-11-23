/**
 * Where the Grand Prix Hub is pointed: which round, which section, and which
 * view of the prediction — all held in the URL so any of them can be linked to.
 *
 * Pure functions only; the hook that binds them to the router lives in
 * `useHubUrlState`.
 */

import type { GrandPrixTab } from "@/app/lib/entityLinks";
import { raceQuery, readRaceYear } from "@/app/ui/race-picker/raceUrl";

import type { RaceEvent } from "./predictionModel";

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
