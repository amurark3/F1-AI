import { notFound } from "next/navigation";

import { currentSeason, getTeamDetail, getTeams } from "@/app/lib/server/raceControl";

import { TeamDetailView, type TeamDetail } from "./TeamDetailView";

import type { Metadata } from "next";

interface TeamPageProps {
  params: Promise<{ team: string }>;
}

interface TeamDetailResponse {
  team: TeamDetail | null;
  error?: string;
}

/** Team profiles track the standings, which move once per race weekend. */
export const revalidate = 900;

/**
 * Prerender the constructors currently in the championship.
 *
 * `dynamicParams` stays on, so a slug that is not on this list — a team added
 * mid-season, or a stale bookmark — still renders on demand.
 */
export async function generateStaticParams(): Promise<Array<{ team: string }>> {
  const teams = await getTeams(currentSeason());
  return (teams?.teams ?? []).map((team) => ({ team: team.slug }));
}

export async function generateMetadata({ params }: TeamPageProps): Promise<Metadata> {
  const { team: slug } = await params;
  const year = currentSeason();
  const data = await getTeamDetail<TeamDetailResponse>(slug, year);
  const team = data?.team;

  if (!team) {
    return { title: "Team Profile | F1 AI" };
  }

  return {
    title: `${team.name} — ${year} F1 Season | F1 AI`,
    description: `${team.name} championship position, points, and driver line-up for the ${year} Formula 1 season, with pace and standings profiles.`,
  };
}

export default async function TeamDetailPage({ params }: TeamPageProps) {
  const { team: slug } = await params;
  const year = currentSeason();
  const data = await getTeamDetail<TeamDetailResponse>(slug, year);

  // A reachable backend that knows no such constructor is a genuine 404. An
  // unreachable one returns null, and the view fetches for itself instead.
  if (data !== null && !data.team) {
    notFound();
  }

  return <TeamDetailView slug={slug} year={year} initial={data} />;
}
