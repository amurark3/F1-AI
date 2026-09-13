import { currentSeason, getIntel, getTeams } from "@/app/lib/server/raceControl";

import { IntelView, type Intel, type IntelSeed } from "./IntelView";

import type { Metadata } from "next";

/** Rival pace reads shift during a session weekend. */
export const revalidate = 300;

export const metadata: Metadata = {
  title: "F1 Rival Intel | F1 AI",
  description:
    "Head-to-head Formula 1 constructor comparisons — championship pressure, pace profiles, and competitor threat analysis from official standings.",
};

export default async function IntelPage() {
  const year = currentSeason();
  const teams = await getTeams(year);

  // The board opens on the leading constructor, so that is the intel to prefetch.
  const defaultSlug = teams?.teams?.[0]?.slug ?? null;
  const intel = defaultSlug ? await getIntel<Intel>(defaultSlug) : null;

  const seed: IntelSeed = { year, teams, intel, intelSlug: defaultSlug };

  return <IntelView seed={seed} />;
}
