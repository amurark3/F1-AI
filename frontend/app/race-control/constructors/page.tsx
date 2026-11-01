import { redirect } from "next/navigation";

import { teamHref } from "@/app/lib/entityLinks";
import { getDirectory } from "@/app/lib/server/profiles";
import { currentSeason } from "@/app/lib/server/raceControl";

import { ConstructorsIndex } from "./ConstructorsIndex";

import type { Metadata } from "next";

/** Follows the constructor table, which moves once per race weekend. */
export const revalidate = 900;

export const metadata: Metadata = {
  title: "F1 Teams & Drivers | F1 AI",
  description:
    "Every Formula 1 team and driver of the season: line-ups, race wins, each driver's finish in every round, and power-unit usage from FIA documents.",
};

/** Opens on the constructor championship leader; the team dropdown moves from there. */
export default async function ConstructorsPage() {
  const year = currentSeason();
  const directory = await getDirectory(year);
  const leader = directory?.teams[0]?.id;
  if (leader) {
    redirect(teamHref(leader));
  }
  return <ConstructorsIndex year={year} />;
}
