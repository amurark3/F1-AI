"use client";

import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { awaitingFirstData, seededWith } from "@/app/lib/swrFallback";
import { fetcher } from "@/app/utils/fetcher";

import { ConsoleHeader, ConsolePanel } from "../../grand-prix/predictionConsole";
import { PowerUnitsSection } from "../../profiles/PowerUnitCards";
import { CumulativePointsChart } from "../../profiles/ProfileCharts";
import {
  isTeamProfile,
  profilesUrl,
  type SeasonDirectory,
  type TeamProfile,
  type TeamProfileResponse,
} from "../../profiles/profilesModel";
import { ProfileLoading, ProfileNotFound, ProfileUnavailable } from "../../profiles/ProfileStates";

import { ChampionshipPicture } from "./ChampionshipPicture";
import { TeamHeader } from "./TeamHeader";
import { TeamLineUp, TeamWins } from "./TeamLineUp";
import { TeamResultsGrid } from "./TeamResultsGrid";

export interface TeamSeed {
  year: number;
  profile: TeamProfileResponse | null;
  directory: SeasonDirectory | null;
}

const SWR_OPTIONS = { revalidateOnFocus: false, dedupingInterval: 180000 } as const;

function PointsPanel({ profile }: { profile: TeamProfile }) {
  const data = profile.rounds
    .filter((round) => round.cumulative_points !== null)
    .map((round) => ({ label: `R${round.round}`, name: round.short_name, points: round.cumulative_points ?? 0 }));
  if (data.length < 2) return null;
  return (
    <ConsolePanel className="mb-5">
      <ConsoleHeader label="Points through the season" />
      <div className="p-3">
        <CumulativePointsChart data={data} color={profile.team.color} />
      </div>
    </ConsolePanel>
  );
}

function TeamPage({ profile, directory }: { profile: TeamProfile; directory: SeasonDirectory | undefined }) {
  return (
    <div>
      <TeamHeader profile={profile} teams={directory?.teams ?? []} />
      <div className="grid gap-x-5 xl:grid-cols-2">
        <TeamLineUp profile={profile} />
        <TeamWins profile={profile} />
      </div>
      <PointsPanel profile={profile} />
      <TeamResultsGrid profile={profile} />
      <PowerUnitsSection section={profile.power_units} color={profile.team.color} />
      <ChampionshipPicture slug={profile.intel_slug} color={profile.team.color} />
    </div>
  );
}

export function TeamView({ teamId, seed }: { teamId: string; seed: TeamSeed }) {
  const { year } = seed;
  const { data, error, isLoading, mutate } = useSWR<TeamProfileResponse, Error>(
    profilesUrl(API_BASE, year, `teams/${encodeURIComponent(teamId)}`),
    fetcher,
    { ...SWR_OPTIONS, ...seededWith(seed.profile) },
  );
  const { data: directory } = useSWR<SeasonDirectory, Error>(profilesUrl(API_BASE, year, "directory"), fetcher, {
    ...SWR_OPTIONS,
    ...seededWith(seed.directory),
  });

  if (awaitingFirstData(isLoading, data !== undefined)) {
    return <ProfileLoading what="team" />;
  }
  if (isTeamProfile(data)) {
    return <TeamPage profile={data} directory={directory} />;
  }
  if (data?.status === "not_found") {
    return <ProfileNotFound what="team" backHref="/race-control/constructors" backLabel="All teams" />;
  }
  return <ProfileUnavailable onRetry={() => void mutate()} errorId={error ? undefined : data?.error_id} />;
}
