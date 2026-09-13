"use client";

import { ArrowLeft, Trophy, Users, Flag } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import type { DriverChampion, RaceWinner, SeasonDetail } from "@/app/lib/server/champions";
import { awaitingFirstData, seededWith } from "@/app/lib/swrFallback";
import { getTeamColor } from "@/app/lib/teamColors";
import {
  InlineNotice,
  MetricCard,
  MetricRow,
  PageLoader,
  Panel,
  SectionHeader,
  StatusPill,
  rcFont,
} from "@/app/race-control/components/RaceControlPrimitives";
import { fetcher } from "@/app/utils/fetcher";


export function SeasonDetailView({ year, initial }: { year: string; initial: SeasonDetail | null }) {
  // Seeded by the server when it reached the backend in time, fetched here when
  // it did not — so a slow prerender costs a moment, not a cached error page.
  const { data, error, isLoading } = useSWR<SeasonDetail, Error>(
    `${API_BASE}/api/champions/${year}`,
    fetcher,
    seededWith(initial),
  );

  if (awaitingFirstData(isLoading, data !== undefined)) {
    return (
      <div className="w-full">
        <PageLoader title={`Loading ${year} season`} detail="Fetching champions and race winners." />
      </div>
    );
  }

  if (error || !data || data.error) {
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
          data.is_in_progress ? "The title is not yet decided — current championship leaders are shown." : undefined
        }
      />

      <SeasonChampionMetrics data={data} driver={driver} teamColor={teamColor} raceCount={winners.length} />

      {data.runner_up && (
        <p className="mb-6 text-sm text-[#8E96A8]">
          Runner-up: <span className="font-semibold text-white">{data.runner_up.name}</span> ({data.runner_up.points}{" "}
          pts)
        </p>
      )}

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-bold uppercase tracking-[0.22em] text-[#7F8797]" style={rcFont}>
          Race winners
        </h2>
        {data.is_in_progress && <StatusPill color="#FFF200">In Progress</StatusPill>}
      </div>

      <RaceWinnersList winners={winners} />
    </div>
  );
}

function SeasonChampionMetrics({
  data,
  driver,
  teamColor,
  raceCount,
}: {
  data: SeasonDetail;
  driver: DriverChampion | null;
  teamColor: string;
  raceCount: number;
}) {
  return (
    <MetricRow>
      <MetricCard
        label={data.is_in_progress ? "Championship Leader" : "World Champion"}
        value={driver?.code ?? "—"}
        sub={driver?.name}
        icon={Trophy}
        color={teamColor}
      />
      <MetricCard
        label="Points"
        value={driver ? String(driver.points) : "—"}
        sub={driver?.team ?? undefined}
        icon={Flag}
        color="#00FF78"
      />
      <MetricCard
        label="Wins"
        value={driver ? String(driver.wins) : "—"}
        sub={`of ${raceCount} races`}
        icon={Trophy}
        color="#FFD700"
      />
      <MetricCard
        label="Constructors' Champion"
        value={data.constructor_champion ? "" : "—"}
        sub={data.constructor_champion?.name ?? "Title introduced in 1958"}
        icon={Users}
        color="#00D2FF"
      />
    </MetricRow>
  );
}

function RaceWinnersList({ winners }: { winners: RaceWinner[] }) {
  if (winners.length === 0) {
    return (
      <InlineNotice title="No races yet" tone="info">
        No completed races recorded for this season.
      </InlineNotice>
    );
  }

  return (
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
