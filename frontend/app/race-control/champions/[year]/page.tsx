"use client";

import { ArrowLeft, Trophy, Users, Flag } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import useSWR from "swr";

import { getTeamColor } from "@/app/components/PredictionDriverCard";
import { API_BASE } from "@/app/constants/api";
import {
  InlineNotice,
  MetricCard,
  MetricRow,
  Panel,
  PageLoader,
  SectionHeader,
  StatusPill,
  rcFont,
} from "@/app/race-control/components/RaceControlPrimitives";
import { fetcher } from "@/app/utils/fetcher";

interface DriverChampion {
  name: string;
  code: string | null;
  team: string | null;
  points: number;
  wins: number;
  nationality: string | null;
  title_decided: boolean;
}

interface ConstructorChampion {
  name: string;
  points: number;
  title_decided: boolean;
}

interface RaceWinner {
  round: number;
  race_name: string;
  date: string | null;
  winner: string;
  team: string | null;
}

interface SeasonDetail {
  season: number;
  is_in_progress: boolean;
  driver_champion: DriverChampion | null;
  constructor_champion: ConstructorChampion | null;
  runner_up: { name: string; points: number } | null;
  race_winners?: RaceWinner[];
  error?: string;
}

export default function SeasonDetailPage({ params }: { params: Promise<{ year: string }> }) {
  const { year } = use(params);
  const { data, error, isLoading } = useSWR<SeasonDetail, Error>(
    `${API_BASE}/api/champions/${year}`,
    fetcher,
  );

  if (isLoading) {
    return (
      <div className="w-full">
        <PageLoader title={`Loading ${year} season`} detail="Fetching champions and race winners." />
      </div>
    );
  }

  if (error || data?.error || !data) {
    return (
      <div className="w-full">
        <BackLink />
        <InlineNotice title={`Season ${year} unavailable`} tone="error">
          {data?.error ?? "Could not load this season."}
        </InlineNotice>
      </div>
    );
  }

  const driver = data.driver_champion;
  const teamColor = getTeamColor(driver?.team ?? "");
  const winners = data.race_winners ?? [];

  return (
    <div className="w-full">
      <BackLink />
      <SectionHeader
        eyebrow={data.is_in_progress ? "Season in progress" : "Champions"}
        title={`${data.season} Season`}
        description={
          data.is_in_progress
            ? "The title is not yet decided — current championship leaders are shown."
            : undefined
        }
      />

      <MetricRow>
        <MetricCard
          label={data.is_in_progress ? "Championship Leader" : "World Champion"}
          value={driver?.code ?? "—"}
          sub={driver?.name}
          icon={Trophy}
          color={teamColor}
        />
        <MetricCard label="Points" value={driver ? String(driver.points) : "—"} sub={driver?.team ?? undefined} icon={Flag} color="#00FF78" />
        <MetricCard label="Wins" value={driver ? String(driver.wins) : "—"} sub={`of ${winners.length} races`} icon={Trophy} color="#FFD700" />
        <MetricCard
          label="Constructors' Champion"
          value={data.constructor_champion ? "" : "—"}
          sub={data.constructor_champion?.name ?? "Title introduced in 1958"}
          icon={Users}
          color="#00D2FF"
        />
      </MetricRow>

      {data.runner_up && (
        <p className="mb-6 text-sm text-[#8E96A8]">
          Runner-up: <span className="font-semibold text-white">{data.runner_up.name}</span> ({data.runner_up.points} pts)
        </p>
      )}

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-bold uppercase tracking-[0.22em] text-[#7F8797]" style={rcFont}>
          Race winners
        </h2>
        {data.is_in_progress && <StatusPill color="#FFF200">In Progress</StatusPill>}
      </div>

      {winners.length === 0 ? (
        <InlineNotice title="No races yet" tone="info">
          No completed races recorded for this season.
        </InlineNotice>
      ) : (
        <Panel className="divide-y divide-[#1E2633]">
          {winners.map((race) => {
            const color = getTeamColor(race.team ?? "");
            return (
              <div key={race.round} className="flex items-center gap-3 px-4 py-2.5">
                <span className="w-8 shrink-0 font-mono text-sm font-bold text-[#6F7789]">R{race.round}</span>
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-white">{race.winner}</p>
                  <p className="truncate text-xs text-[#8E96A8]">{race.race_name}</p>
                </div>
                <span className="hidden shrink-0 text-xs text-[#6F7789] sm:block">{race.team}</span>
              </div>
            );
          })}
        </Panel>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/race-control/champions"
      className="mb-5 inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.16em] text-[#8E96A8] transition-colors hover:text-white"
    >
      <ArrowLeft className="h-3.5 w-3.5" /> All champions
    </Link>
  );
}
