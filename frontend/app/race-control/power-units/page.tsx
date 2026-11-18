import { currentSeason, getPowerUnits, getTeams } from "@/app/lib/server/raceControl";

import { PowerUnitsView } from "./PowerUnitsView";

import type { PowerUnitsResponse } from "./powerUnitsModel";
import type { Metadata } from "next";

/** Documents arrive through a race weekend; the collection job runs hourly. */
export const revalidate = 300;

export const metadata: Metadata = {
  title: "Power Unit Tracker | F1 AI",
  description:
    "Every Formula 1 car's power-unit allocation — engines, turbochargers, MGU-K, energy stores and more — the Grand Prix each new unit arrived at, and the grid penalties it cost, read from the FIA's own documents.",
};

/** Awaits nothing: the promises go to the sections, which take them up behind their own boundaries. */
export default function PowerUnitsPage() {
  const year = currentSeason();
  return (
    <PowerUnitsView
      year={year}
      seeds={{ powerUnits: getPowerUnits<PowerUnitsResponse>(year), teams: getTeams(year) }}
    />
  );
}
