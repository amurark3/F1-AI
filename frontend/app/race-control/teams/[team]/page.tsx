"use client";

import { ArrowLeft, BarChart3, Gauge, ShieldAlert, Trophy, Users } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";

import {
  MetricCard,
  MetricRow,
  PageLoader,
  Panel,
  SectionHeader,
  StatusPill,
  WorkspaceSplit,
  rcFont,
} from "../../components/RaceControlPrimitives";

interface TeamDetail {
  slug: string;
  name: string;
  color: string;
  position?: number;
  points: number;
  wins: number;
  drivers: Array<{ driver: string; points: number; position: number }>;
  recent_form: Array<{ round: number; points: number }>;
  strengths: string[];
  weaknesses: string[];
  strategy_tendency: string;
  standing_profile?: Record<string, number>;
  pace_profile?: Record<string, number>;
}

export default function TeamDetailPage() {
  const year = new Date().getFullYear();
  const params = useParams<{ team: string }>();
  const slug = params.team;
  const { data, isLoading } = useSWR<{ team: TeamDetail | null; error?: string }>(
    `${API_BASE}/api/race-control/teams/${slug}/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 180000 },
  );

  const team = data?.team;

  if (isLoading) {
    return <TeamDetailLoading />;
  }

  if (!team) {
    return <TeamNotFound />;
  }

  return (
    <div>
      <Link
        href="/race-control/teams"
        className="mb-5 inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 text-sm font-bold text-neutral-300 transition-colors hover:border-white/20 hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00FF78]/50"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to team hub
      </Link>

      <SectionHeader
        eyebrow={`Constructor P${team.position ?? "-"} · ${team.points} pts`}
        title={team.name}
        description={team.strategy_tendency}
      />

      <MetricRow>
        <MetricCard
          label="Position"
          value={team.position ? `P${team.position}` : "No rank"}
          sub="Constructor table"
          icon={Trophy}
          color={team.color}
        />
        <MetricCard label="Points" value={String(team.points)} sub="Season score" icon={BarChart3} color="#3671C6" />
        <MetricCard label="Wins" value={String(team.wins)} sub="Race wins" icon={Gauge} color="#FF8000" />
        <MetricCard
          label="Drivers"
          value={String(team.drivers.length)}
          sub="Active roster"
          icon={Users}
          color="#00FF78"
        />
      </MetricRow>

      <TeamProfileWorkspace team={team} />
    </div>
  );
}

const DATA_BOUNDARIES = [
  "Official standings provide position, points, wins, and listed drivers.",
  "This view does not claim live race pace, tyre degradation, or reliability telemetry.",
  "Use forecasts and debriefs for model projections and completed-race classification detail.",
];

function TeamProfileWorkspace({ team }: { team: TeamDetail }) {
  return (
    <WorkspaceSplit className="xl:[&>*:first-child]:basis-[58%] xl:[&>*:last-child]:flex-1">
      <Panel accent={team.color} className="p-5">
        <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>
          Standing Profile
        </h2>
        <div className="grid gap-2 sm:grid-cols-2">
          {Object.entries(team.standing_profile ?? team.pace_profile ?? {}).map(([label, value]) => (
            <div key={label} className="rounded-lg border border-white/6 bg-white/[0.025] p-3">
              <p className="text-[10px] font-black uppercase tracking-wider text-neutral-600">{label}</p>
              <p className="mt-1 text-2xl font-black text-white" style={rcFont}>
                {formatPoints(value)}
              </p>
              <p className="mt-1 text-[10px] text-neutral-600">official standings field</p>
            </div>
          ))}
        </div>

        <div className="mt-6 flex flex-col gap-4 sm:flex-row [&>*]:flex-1">
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-neutral-600 mb-3">Standing Evidence</p>
            <div className="space-y-2">
              {team.strengths.map((item) => (
                <StatusPill key={item} color={team.color}>
                  {item}
                </StatusPill>
              ))}
            </div>
          </div>
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-neutral-600 mb-3">Pressure Points</p>
            <div className="space-y-2">
              {team.weaknesses.map((item) => (
                <StatusPill key={item} color="#FFF200">
                  {item}
                </StatusPill>
              ))}
            </div>
          </div>
        </div>
      </Panel>

      <div className="space-y-5">
        <Panel className="p-5">
          <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>
            Teammate View
          </h2>
          <div className="space-y-2">
            {team.drivers.length > 0 ? (
              team.drivers.map((driver) => (
                <div key={driver.driver} className="rounded-lg border border-white/6 bg-white/[0.025] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-white truncate">{driver.driver}</p>
                      <p className="text-[10px] text-neutral-600">WDC P{driver.position}</p>
                    </div>
                    <span className="text-lg font-black text-neutral-300" style={rcFont}>
                      {driver.points}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-sm text-neutral-500">Driver data pending.</p>
            )}
          </div>
        </Panel>

        <Panel className="p-5">
          <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>
            Data Boundaries
          </h2>
          <div className="space-y-2">
            {DATA_BOUNDARIES.map((item) => (
              <div
                key={item}
                className="flex items-center gap-3 rounded-lg border border-white/6 bg-white/[0.025] px-3 py-2"
              >
                <ShieldAlert className="h-4 w-4 text-neutral-600" />
                <span className="text-sm text-neutral-400">{item}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </WorkspaceSplit>
  );
}

function TeamDetailLoading() {
  return (
    <div>
      <SectionHeader
        eyebrow="Team Performance Hub"
        title="Constructor Detail"
        description="Loading the constructor standings profile, driver table, and operating notes."
      />
      <PageLoader
        title="Preparing team profile"
        detail="Loading constructor standings and strategy profile for this team."
      />
    </div>
  );
}

function TeamNotFound() {
  return (
    <Panel className="p-8">
      <p className="text-neutral-400">Team not found.</p>
      <Link
        href="/race-control/teams"
        className="mt-5 inline-flex items-center justify-center gap-2 rounded-lg border border-[#00FF78]/35 bg-[#00FF78]/10 px-4 py-2.5 text-sm font-black uppercase tracking-wider text-[#00FF78] transition-colors hover:bg-[#00FF78] hover:text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00FF78]/60"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to teams
      </Link>
    </Panel>
  );
}

function formatPoints(points: number) {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}
