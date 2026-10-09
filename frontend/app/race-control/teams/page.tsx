import { currentSeason, getTeams } from "@/app/lib/server/raceControl";

import { TeamsView } from "./TeamsView";

import type { Metadata } from "next";

/**
 * Standings move once per race weekend, so a 15-minute window keeps the
 * prerendered table current without putting the backend in the request path.
 */
export const revalidate = 900;

export const metadata: Metadata = {
  title: "F1 Championship Standings | F1 AI",
  description:
    "Current Formula 1 Drivers' and Constructors' Championship standings, with points gaps, win counts, and team operating profiles.",
};

export default async function TeamsPage() {
  const year = currentSeason();
  const initialTeams = await getTeams(year);

  return <TeamsView year={year} initialTeams={initialTeams} />;
}
