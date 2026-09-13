import { getChampions, getChampionStats } from "@/app/lib/server/champions";

import { ChampionsView, type ChampionsSeed } from "./ChampionsView";

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

export default async function ChampionsPage() {
  // Cached independently, so the slower one never delays the other.
  const [champions, stats] = await Promise.all([getChampions(), getChampionStats()]);

  const seed: ChampionsSeed = { champions, stats };

  return <ChampionsView seed={seed} />;
}
