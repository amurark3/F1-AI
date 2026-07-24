"use client";

import { Activity, RefreshCw, Shield, Trophy, Users } from "lucide-react";
import useSWR from "swr";

import { getTeamColor } from "@/app/components/PredictionDriverCard";
import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";

import { ChampionshipBarChart, DriverChampionshipChart } from "../components/Charts";
import { InlineNotice, MetricCard, MetricRow, PageLoader, Panel, SectionHeader, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";

interface DriverStanding {
  code?: string;
  driver: string;
  team: string;
  points: number;
  position: number;
  wins: number;
}

interface Team {
  slug: string;
  name: string;
  color: string;
  position: number;
  points: number;
  wins: number;
  drivers: DriverStanding[];
  strengths: string[];
  weaknesses: string[];
  standing_profile?: Record<string, number>;
  pace_profile?: Record<string, number>;
}

interface TeamsResponse {
  teams: Team[];
  drivers?: DriverStanding[];
  error?: string | null;
  source?: string;
  generated_at?: string;
}

export default function TeamsPage() {
  const year = new Date().getFullYear();
  const { data, error, isLoading, mutate: reloadTeams } = useSWR<TeamsResponse, Error>(
    `${API_BASE}/api/race-control/teams/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 180000 }
  );
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

      <MetricRow>
        <MetricCard label="Driver Leader" value={driverLeader?.driver ?? "No standings"} sub={driverLeader ? `${driverLeader.team} · ${formatPoints(driverLeader.points)} pts` : "Driver table unavailable"} icon={Trophy} color="#00FF78" />
        <MetricCard label="Constructor Leader" value={constructorLeader?.name ?? "No standings"} sub={constructorLeader ? `${formatPoints(constructorLeader.points)} pts` : "Constructor table unavailable"} icon={Shield} color="#E10600" />
        <MetricCard label="Drivers" value={String(drivers.length || "No data")} sub="Current WDC entries" icon={Users} color="#3671C6" />
        <MetricCard label="Teams" value={String(teams.length || "No data")} sub="Current constructor entries" icon={Activity} color="#FF8000" />
      </MetricRow>

      {!isLoading && (error || data?.error || teams.length === 0) && (
        <div className="mb-5">
          <InlineNotice title="Championship Standings" tone={error ? "error" : "warning"}>
            {error
              ? "The standings API did not respond."
              : data?.error ?? "No constructor standings are available for this season yet."}
            <button onClick={() => void reloadTeams()} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
          </InlineNotice>
        </div>
      )}

      <Panel className="mb-6 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-black uppercase tracking-[0.16em] text-neutral-400" style={rcFont}>Data Source</p>
            <p className="mt-1 text-sm text-neutral-400">
              Championship standings feed{generatedAt ? ` · refreshed ${generatedAt}` : ""}
            </p>
          </div>
          <button
            onClick={() => void reloadTeams()}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-4 text-sm font-bold text-neutral-200 transition-colors hover:bg-white/[0.08] hover:text-white"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </Panel>

      <WorkspaceSplit className="mb-6 xl:[&>*]:flex-1">
        <Panel className="p-5" accent="#00FF78">
          <ChampionshipPanelHeader
            eyebrow="World Drivers' Championship"
            title="Driver Order"
            pill={`${year} WDC`}
            color="#00FF78"
          />
          <DriverChampionshipChart
            data={drivers.slice(0, 10).map((driver) => ({
              name: driver.driver,
              code: driver.code ?? driver.driver.slice(0, 3).toUpperCase(),
              points: driver.points,
              color: getTeamColor(driver.team),
              position: driver.position,
            }))}
            height={260}
          />
          <div className="mt-5 space-y-2">
            {drivers.length > 0 ? drivers.slice(0, 12).map((driver) => (
              <DriverStandingRow key={`${driver.position}-${driver.driver}`} driver={driver} />
            )) : (
              <p className="text-sm text-neutral-500">Driver standings are not available for this season yet.</p>
            )}
          </div>
        </Panel>

        <Panel className="p-5" accent="#E10600">
          <ChampionshipPanelHeader
            eyebrow="World Constructors' Championship"
            title="Constructor Order"
            pill={`${year} WCC`}
            color="#E10600"
          />
          <ChampionshipBarChart
            data={teams.map((team) => ({ name: team.name, points: team.points, color: team.color, position: team.position }))}
            height={Math.max(230, teams.length * 34)}
          />
          <div className="mt-5 space-y-2">
            {teams.length > 0 ? teams.map((team) => (
              <ConstructorStandingRow key={team.slug} team={team} />
            )) : (
              <p className="text-sm text-neutral-500">Constructor standings are not available for this season yet.</p>
            )}
          </div>
        </Panel>
      </WorkspaceSplit>
    </div>
  );
}

function ChampionshipPanelHeader({
  eyebrow,
  title,
  pill,
  color,
}: {
  eyebrow: string;
  title: string;
  pill: string;
  color: string;
}) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>{eyebrow}</p>
        <h2 className="mt-1 text-3xl font-black italic uppercase leading-none text-white" style={rcFont}>{title}</h2>
      </div>
      <StatusPill color={color}>{pill}</StatusPill>
    </div>
  );
}

function DriverStandingRow({ driver }: { driver: DriverStanding }) {
  const color = getTeamColor(driver.team);
  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <div className="w-10 shrink-0 text-center text-lg font-black italic text-neutral-300" style={rcFont}>P{driver.position}</div>
      <span className="hidden rounded px-2 py-0.5 text-xs font-black sm:inline-flex" style={{ color, background: `${color}20` }}>
        {driver.code ?? driver.driver.slice(0, 3).toUpperCase()}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-bold text-white">{driver.driver}</p>
        <p className="truncate text-xs font-semibold" style={{ color }}>{driver.team}</p>
      </div>
      <div className="shrink-0 text-right">
        <p className="text-sm font-black text-white" style={rcFont}>{formatPoints(driver.points)}</p>
        <p className="text-[10px] text-neutral-500">{driver.wins} win{driver.wins === 1 ? "" : "s"}</p>
      </div>
    </div>
  );
}

function ConstructorStandingRow({ team }: { team: Team }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <div className="w-10 shrink-0 text-center text-lg font-black italic text-neutral-300" style={rcFont}>P{team.position}</div>
      <span className="h-7 w-1.5 shrink-0 rounded-full" style={{ background: team.color }} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-bold text-white">{team.name}</p>
        <p className="truncate text-xs text-neutral-500">{team.drivers.map((driver) => driver.driver).join(" / ") || "Roster pending"}</p>
      </div>
      <div className="shrink-0 text-right">
        <p className="text-sm font-black text-white" style={rcFont}>{formatPoints(team.points)}</p>
        <p className="text-[10px] text-neutral-500">{team.wins} win{team.wins === 1 ? "" : "s"}</p>
      </div>
    </div>
  );
}

function flattenDrivers(teams: Team[]) {
  return teams
    .flatMap((team) => team.drivers.map((driver) => ({ ...driver, team: driver.team || team.name })))
    .sort((a, b) => a.position - b.position);
}

function formatPoints(points: number) {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}
