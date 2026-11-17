import { Suspense } from "react";

import { getDirectory } from "@/app/lib/server/profiles";
import { currentSeason } from "@/app/lib/server/raceControl";
import { teamLabel } from "@/app/ui/names/names";

import { SeededTeamSwitch, SeededTeamView } from "./TeamSeeds";
import { TeamSwitch } from "./TeamSwitch";
import { TeamView } from "./TeamView";

import type { Metadata } from "next";

interface TeamPageProps {
  params: Promise<{ team: string }>;
}

/** Follows the constructor table, which moves once per race weekend. */
export const revalidate = 900;

/**
 * Prerender every team of the season, by f1db constructor id.
 *
 * `dynamicParams` stays on, so a team added mid-season still renders on demand.
 */
export async function generateStaticParams(): Promise<Array<{ team: string }>> {
  const directory = await getDirectory(currentSeason());
  return (directory?.teams ?? []).map((team) => ({ team: team.id }));
}

/** Reads only the directory, which the page and its static params share, so metadata never waits on the profile. */
export async function generateMetadata({ params }: TeamPageProps): Promise<Metadata> {
  const { team: teamId } = await params;
  const year = currentSeason();
  const directory = await getDirectory(year);
  const team = directory?.teams.find((entry) => entry.id === teamId);
  if (!team) {
    return { title: "F1 Teams | F1 AI" };
  }
  const fullName = teamLabel({ id: team.id, name: team.name, fullName: team.full_name, year }, "full");
  return {
    title: `${fullName} — ${year} F1 Season | F1 AI`,
    description: `${fullName}'s ${year} Formula 1 season: line-up, race wins, every driver's finish by round, points by weekend and power-unit usage from FIA documents.`,
  };
}

/** Nothing here waits on the backend: each section paints its skeleton at once and its seed streams in. */
export default async function TeamPage({ params }: TeamPageProps) {
  const { team: teamId } = await params;
  const year = currentSeason();
  return (
    <div>
      <Suspense fallback={<TeamSwitch year={year} teamId={teamId} seed={null} />}>
        <SeededTeamSwitch year={year} teamId={teamId} />
      </Suspense>
      <div className="mt-6">
        <Suspense fallback={<TeamView year={year} teamId={teamId} seed={null} />}>
          <SeededTeamView year={year} teamId={teamId} />
        </Suspense>
      </div>
    </div>
  );
}
