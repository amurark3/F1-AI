import { currentSeason, getOverviewSegment, getStandingsProgression, getTeams } from "@/app/lib/server/raceControl";

import { StandingsView } from "./StandingsView";

import type { OverviewShell } from "../components/CommandCenterPanels";
import type { Metadata } from "next";

/**
 * Standings move once per race weekend, so a 15-minute window keeps the
 * prerendered page current without putting the backend in the request path.
 */
export const revalidate = 900;

export const metadata: Metadata = {
  title: "F1 Championship Standings | F1 AI",
  description:
    "Current Formula 1 Drivers' and Constructors' Championship standings, with points gaps, win counts, and the title race round by round.",
};

/** Awaits nothing: the promises go to the sections, which take them up behind their own boundaries. */
export default function StandingsPage() {
  const year = currentSeason();
  return (
    <StandingsView
      year={year}
      seeds={{
        teams: getTeams(year),
        shell: getOverviewSegment<OverviewShell>(year, "/shell"),
        progression: getStandingsProgression(year),
      }}
    />
  );
}
