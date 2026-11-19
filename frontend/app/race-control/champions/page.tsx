import { getChampions, getChampionStats, getLatestChampion } from "@/app/lib/server/champions";

import { ChampionsView } from "./ChampionsView";

import type { Metadata } from "next";

/**
 * Hourly background regeneration. The dataset only moves when a title is
 * decided, so this is not about freshness — it caps how long a render made
 * against a slow backend keeps serving an unseeded page.
 */
export const revalidate = 3_600;

export const metadata: Metadata = {
  title: "F1 World Champions (1950–Present) | F1 AI",
  description:
    "Every Formula 1 World Drivers' and Constructors' Champion since 1950, with points, wins, and the races that decided each title.",
};

/** Awaits nothing: the promises go to the sections, which take them up behind their own boundaries. */
export default function ChampionsPage() {
  return (
    <ChampionsView seeds={{ latest: getLatestChampion(), stats: getChampionStats(), champions: getChampions() }} />
  );
}
