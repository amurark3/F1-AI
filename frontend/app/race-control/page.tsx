import { currentSeason, getOverviewSegment } from "@/app/lib/server/raceControl";

import { CommandCenterView } from "./CommandCenterView";

import type {
  OverviewPredictions,
  OverviewShell,
  OverviewStrategy,
  OverviewWeather,
} from "./components/CommandCenterPanels";
import type { OverviewCircuit } from "./weekend/weekendTypes";
import type { Metadata } from "next";

/**
 * Regenerated every five minutes, the cadence the telemetry and strategy inputs
 * actually move at. Readers are served the previous render while the refresh
 * happens behind them, so a slow backend never becomes a slow page.
 */
export const revalidate = 300;

export const metadata: Metadata = {
  title: "Race Weekend Command Center | F1 AI",
  description:
    "The Formula 1 race weekend at a glance — circuit map, session-by-session weather, championship stakes, projected podium, circuit history, and baseline strategy.",
};

export default function RaceControlHome() {
  const year = currentSeason();

  // Five parallel requests, each its own cache entry, and nothing is awaited here:
  // each slot of the view waits only for the segments it shows, so one slow segment
  // neither blocks the page nor the others. Any that does not arrive in time is
  // simply left unseeded — the browser fetches it.
  const seeds = {
    shell: getOverviewSegment<OverviewShell>(year, "/shell"),
    strategy: getOverviewSegment<OverviewStrategy>(year, "/strategy"),
    predictions: getOverviewSegment<OverviewPredictions>(year, "/predictions"),
    weather: getOverviewSegment<OverviewWeather>(year, "/weather"),
    circuit: getOverviewSegment<OverviewCircuit>(year, "/circuit"),
  };

  return <CommandCenterView year={year} seeds={seeds} />;
}
