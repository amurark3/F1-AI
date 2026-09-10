"use client";

import { Activity, Shield, Trophy, Users } from "lucide-react";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";

import {
  InlineNotice,
  MetricCard,
  MetricRow,
  PageLoader,
  Panel,
  SectionHeader,
  rcFont,
} from "../components/RaceControlPrimitives";
import { RefreshButton } from "../components/RefreshButton";

import { StandingsSplit } from "./ChampionshipPanels";
import { formatPoints, type DriverStanding, type Team, type TeamsResponse } from "./teamsModel";

export default function TeamsPage() {
  const year = new Date().getFullYear();
  const {
    data,
    error,
    isLoading,
    mutate: reloadTeams,
  } = useSWR<TeamsResponse, Error>(`${API_BASE}/api/race-control/teams/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 180000,
  });
  const teams = data?.teams ?? [];
  const drivers = data?.drivers ?? flattenDrivers(teams);
  const constructorLeader = teams[0];
  const driverLeader = drivers[0];
  const pageLoading = isLoading && teams.length === 0;
  const generatedAt = data?.generated_at
    ? new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      }).format(new Date(data.generated_at))
    : null;

  if (pageLoading) {
    return (
      <div>
        <SectionHeader
          eyebrow="Championship Hub"
          title="Standings & Team Ops"
          description="Load the official championship order first, then inspect standings-backed team operating profiles for strategy review."
        />
        <PageLoader
          title="Preparing championship hub"
          detail="Loading the current driver and constructor standings before team profiles open."
        />
      </div>
    );
  }

  return (
    <div>
      <SectionHeader
        eyebrow="Championship Hub"
        title="Championship Standings"
        description="Current WDC and WCC order from the standings feed, with charts for gaps and compact tables for exact points."
      />

      <TeamsMetrics
        driverLeader={driverLeader}
        constructorLeader={constructorLeader}
        driverCount={drivers.length}
        teamCount={teams.length}
      />

      <TeamsErrorNotice
        show={!isLoading && Boolean(error || data?.error || teams.length === 0)}
        hasError={Boolean(error)}
        message={data?.error}
        onRetry={() => void reloadTeams()}
      />

      <Panel className="mb-6 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-black uppercase tracking-[0.16em] text-neutral-400" style={rcFont}>
              Data Source
            </p>
            <p className="mt-1 text-sm text-neutral-400">
              Championship standings feed{generatedAt ? ` · refreshed ${generatedAt}` : ""}
            </p>
          </div>
          <RefreshButton onRefresh={reloadTeams} />
        </div>
      </Panel>

      <StandingsSplit year={year} drivers={drivers} teams={teams} />
    </div>
  );
}

function TeamsMetrics({
  driverLeader,
  constructorLeader,
  driverCount,
  teamCount,
}: {
  driverLeader?: DriverStanding;
  constructorLeader?: Team;
  driverCount: number;
  teamCount: number;
}) {
  return (
    <MetricRow>
      <MetricCard
        label="Driver Leader"
        value={driverLeader?.driver ?? "No standings"}
        sub={
          driverLeader ? `${driverLeader.team} · ${formatPoints(driverLeader.points)} pts` : "Driver table unavailable"
        }
        icon={Trophy}
        color="#00FF78"
      />
      <MetricCard
        label="Constructor Leader"
        value={constructorLeader?.name ?? "No standings"}
        sub={constructorLeader ? `${formatPoints(constructorLeader.points)} pts` : "Constructor table unavailable"}
        icon={Shield}
        color="#E10600"
      />
      <MetricCard
        label="Drivers"
        value={String(driverCount || "No data")}
        sub="Current WDC entries"
        icon={Users}
        color="#3671C6"
      />
      <MetricCard
        label="Teams"
        value={String(teamCount || "No data")}
        sub="Current constructor entries"
        icon={Activity}
        color="#FF8000"
      />
    </MetricRow>
  );
}

function TeamsErrorNotice({
  show,
  hasError,
  message,
  onRetry,
}: {
  show: boolean;
  hasError: boolean;
  message?: string | null;
  onRetry: () => void;
}) {
  if (!show) {
    return null;
  }
  return (
    <div className="mb-5">
      <InlineNotice title="Championship Standings" tone={hasError ? "error" : "warning"}>
        {hasError
          ? "The standings API did not respond."
          : (message ?? "No constructor standings are available for this season yet.")}
        <button onClick={onRetry} className="ml-2 font-bold text-white underline decoration-white/30">
          Retry
        </button>
      </InlineNotice>
    </div>
  );
}

function flattenDrivers(teams: Team[]) {
  return teams
    .flatMap((team) => team.drivers.map((driver) => ({ ...driver, team: driver.team || team.name })))
    .sort((a, b) => a.position - b.position);
}
