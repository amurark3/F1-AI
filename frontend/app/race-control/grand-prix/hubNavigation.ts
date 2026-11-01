/**
 * Where the Grand Prix Hub is pointed: which round, which section, and which
 * view of the prediction — all held in the URL so any of them can be linked to.
 *
 * Pure functions only; the hook that binds them to the router lives in
 * `useHubUrlState`.
 */

import type { GrandPrixTab } from "@/app/lib/entityLinks";

import { isLiveRace, qualifyingHasRun } from "./predictionHelpers";

import type { RaceEvent } from "./predictionModel";

export type HubTab = GrandPrixTab;

/** The views of one stored prediction, shown inside the Predictions tab. */
export type PredictionView = "order" | "podium" | "risk" | "model" | "review";

export const HUB_TABS: ReadonlyArray<{ key: HubTab; label: string }> = [
  { key: "weekend", label: "Weekend" },
  { key: "sessions", label: "Sessions" },
  { key: "grid", label: "Grid" },
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
export function readHubParams(search: URLSearchParams): HubSelection {
  return {
    round: positiveInt(search.get("round")),
    tab: HUB_TABS.find((item) => item.key === search.get("tab"))?.key ?? null,
    view: PREDICTION_VIEWS.find((item) => item.key === search.get("view"))?.key ?? null,
  };
}

export function hubQuery(selection: HubSelection): string {
  const query = new URLSearchParams();
  if (selection.round !== null) query.set("round", String(selection.round));
  if (selection.tab !== null) query.set("tab", selection.tab);
  if (selection.view !== null) query.set("view", selection.view);
  return query.toString();
}

function anySessionStarted(race: RaceEvent, now: number): boolean {
  return Object.values(race.sessions ?? {}).some((value) => {
    const start = new Date(value).getTime();
    return !Number.isNaN(start) && start <= now;
  });
}

/**
 * The section a round opens on when the URL names none: wherever the weekend
 * has got to. Read from the calendar, not from what has loaded, so the tab
 * does not jump as each section's data arrives.
 */
export function defaultHubTab(race: RaceEvent | null, now: number = Date.now()): HubTab {
  if (!race) return "weekend";
  if (race.status === "completed") return "predictions";
  if (qualifyingHasRun(race, now)) return "grid";
  if (isLiveRace(race.status) || anySessionStarted(race, now)) return "sessions";
  return "weekend";
}

/** After the race, the prediction opens on how it scored; before, on the call itself. */
export function defaultPredictionView(race: RaceEvent | null): PredictionView {
  return race?.status === "completed" ? "review" : "order";
}
