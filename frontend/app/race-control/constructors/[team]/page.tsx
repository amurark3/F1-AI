import { notFound } from "next/navigation";

import { getDirectory, getTeamProfile } from "@/app/lib/server/profiles";
import { currentSeason } from "@/app/lib/server/raceControl";

import { isTeamProfile } from "../../profiles/profilesModel";

import { TeamView } from "./TeamView";

import type { Metadata } from "next";

interface TeamPageProps {
  params: Promise<{ team: string }>;
}

/** Carries power-unit usage, which the FIA updates through a race weekend. */
export const revalidate = 300;

/**
 * Prerender every team of the season, by f1db constructor id.
 *
 * `dynamicParams` stays on, so a team added mid-season still renders on demand.
 */
export async function generateStaticParams(): Promise<Array<{ team: string }>> {
  const directory = await getDirectory(currentSeason());
  return (directory?.teams ?? []).map((team) => ({ team: team.id }));
}

export async function generateMetadata({ params }: TeamPageProps): Promise<Metadata> {
  const { team: teamId } = await params;
  const year = currentSeason();
  const profile = await getTeamProfile(year, teamId);
  if (!isTeamProfile(profile)) {
    return { title: "Teams & Drivers | F1 AI" };
  }
  const { team } = profile;
  return {
    title: `${team.full_name} — ${year} F1 Season | F1 AI`,
    description: `${team.full_name}'s ${year} Formula 1 season: line-up, race wins, every driver's finish by round, points, and power-unit usage from FIA documents.`,
  };
}

export default async function TeamPage({ params }: TeamPageProps) {
  const { team: teamId } = await params;
  const year = currentSeason();
  const [profile, directory] = await Promise.all([getTeamProfile(year, teamId), getDirectory(year)]);

  // Only a backend that answered "not found" proves the URL wrong. With no
  // answer at all the browser fetches for itself and decides.
  if (profile?.status === "not_found") {
    notFound();
  }

  return <TeamView teamId={teamId} seed={{ year, profile, directory }} />;
}
