"use client";

import { ArrowLeft } from "lucide-react";
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
import { DriverLink, TeamLink } from "@/app/race-control/profiles/EntityLinks";
import { DriverName } from "@/app/ui/names/DriverName";
import { driverLabel, teamLabel } from "@/app/ui/names/names";
import { TeamName } from "@/app/ui/names/TeamName";
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

      <SeasonChampionMetrics data={data} driver={driver} raceCount={winners.length} />

      {data.runner_up && (
        <p className="mb-6 text-sm text-[#8E96A8]">
          Runner-up:{" "}
          <DriverName
            className="font-semibold text-white"
            name={data.runner_up.name}
            lastName={data.runner_up.last_name}
            year={data.season}
          />{" "}
          ({data.runner_up.points} pts)
        </p>
      )}

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-bold uppercase tracking-[0.22em] text-[#7F8797]" style={rcFont}>
          Race winners
        </h2>
        {data.is_in_progress && <StatusPill color="#FFF200">In Progress</StatusPill>}
      </div>

      {/* Team and driver pages cover the current season only. */}
      <RaceWinnersList winners={winners} season={data.season} linkable={data.season === new Date().getFullYear()} />
    </div>
  );
}

function SeasonChampionMetrics({
  data,
  driver,
  raceCount,
}: {
  data: SeasonDetail;
  driver: DriverChampion | null;
  raceCount: number;
}) {
  const champion = driver && { name: driver.name, lastName: driver.last_name, code: driver.code, year: data.season };
  return (
    <MetricRow>
      <MetricCard
        label={data.is_in_progress ? "Championship Leader" : "World Champion"}
        value={champion ? driverLabel(champion, "code") : "—"}
        sub={champion ? driverLabel(champion, "full") : undefined}
      />
      <MetricCard
        label="Points"
        value={driver ? String(driver.points) : "—"}
        sub={driver?.team ? teamLabel({ name: driver.team, year: data.season }, "name") : undefined}
      />
      <MetricCard label="Wins" value={driver ? String(driver.wins) : "—"} sub={`of ${raceCount} races`} />
      <MetricCard
        label="Constructors' Champion"
        value={
          data.constructor_champion
            ? teamLabel({ name: data.constructor_champion.name, year: data.season }, "name")
            : "—"
        }
        sub={data.constructor_champion ? undefined : "Title introduced in 1958"}
      />
    </MetricRow>
  );
}

function RaceWinnersList({ winners, season, linkable }: { winners: RaceWinner[]; season: number; linkable: boolean }) {
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
        const winner = <DriverName name={race.winner} id={race.driver_id} year={season} />;
        const team = race.team ? <TeamName name={race.team} id={race.team_id} year={season} /> : null;
        return (
          <div key={race.round} className="flex items-center gap-3 px-4 py-2.5">
            <span className="w-8 shrink-0 font-mono text-sm font-bold text-[#6F7789]">R{race.round}</span>
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-white">
                {linkable ? <DriverLink id={race.driver_id}>{winner}</DriverLink> : winner}
              </p>
              <p className="truncate text-xs text-[#8E96A8]">{race.race_name}</p>
            </div>
            <span className="hidden shrink-0 text-xs text-[#6F7789] sm:block">
              {linkable ? <TeamLink id={race.team_id}>{team}</TeamLink> : team}
            </span>
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
