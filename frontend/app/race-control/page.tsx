import { currentSeason, getOverviewSegment } from "@/app/lib/server/raceControl";

import { CommandCenterView, type OverviewSeed } from "./CommandCenterView";

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

export default async function RaceControlHome() {
  const year = currentSeason();

  // Five parallel requests, each its own cache entry, so one slow segment
  // neither blocks the others nor invalidates their cached copies. Any that
  // does not arrive in time is simply left unseeded — the browser fetches it.
  const [shell, strategy, predictions, weather, circuit] = await Promise.all([
    getOverviewSegment<OverviewShell>(year, "/shell"),
    getOverviewSegment<OverviewStrategy>(year, "/strategy"),
    getOverviewSegment<OverviewPredictions>(year, "/predictions"),
    getOverviewSegment<OverviewWeather>(year, "/weather"),
    getOverviewSegment<OverviewCircuit>(year, "/circuit"),
  ]);

  const seed: OverviewSeed = { year, shell, strategy, predictions, weather, circuit };

  return <CommandCenterView seed={seed} />;
}
