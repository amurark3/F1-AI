"use client";

import { AlertTriangle, BarChart3, Database, Radar, ShieldCheck } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";

import { InlineNotice, MetricCard, MetricRow, PageLoader, Panel, SectionHeader, SectionLoader, StatusPill, rcFont } from "../components/RaceControlPrimitives";

interface Intel {
  team: { name: string; color: string; strategy_tendency: string; strengths: string[]; weaknesses: string[] };
  year?: number;
  source?: string;
  status?: string;
  upgrade_watch: string[];
  threats: string[];
  opportunities: string[];
  error?: string | null;
}

interface TeamsResponse {
  teams: Array<{ slug: string; name: string; position: number; points: number; color: string }>;
  error?: string | null;
}

export default function IntelPage() {
  const year = new Date().getFullYear();
  const [team, setTeam] = useState("");
  const { data: teamsData, error: teamsError, isLoading: teamsLoading, mutate: reloadTeams } = useSWR<TeamsResponse, Error>(
    `${API_BASE}/api/race-control/teams/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 180000 }
  );
  const teams = teamsData?.teams ?? [];
  const selectedTeam = team || teams[0]?.slug || "";

  const { data, error, isLoading, mutate } = useSWR<Intel, Error>(
    selectedTeam ? `${API_BASE}/api/race-control/intel/${selectedTeam}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 180000 }
  );
  const color = data?.team.color ?? "#00FF78";
  const pageLoading = teamsLoading && teams.length === 0;

  if (pageLoading) {
    return (
      <div>
        <SectionHeader
          eyebrow="Competitor Intelligence Board"
          title="Rival Standing Read"
          description="Load the constructor field first, then inspect rival pressure using official standings."
        />
        <PageLoader
          title="Loading constructor field"
          detail="Fetching official constructor standings before opening rival analysis."
        />
      </div>
    );
  }

  return (
    <div>
      <SectionHeader
        eyebrow="Competitor Intelligence Board"
        title="Rival Standing Read"
        description="A standings-backed competitor desk: constructor order, gaps, driver contribution, threats, and opportunities. No upgrade rumors or invented pace claims."
      />

      <Panel className="p-5 mb-5">
        <div className="flex flex-col sm:flex-row sm:items-end gap-3">
          <label className="w-full sm:w-72">
            <span className="block text-[10px] font-black uppercase tracking-[0.18em] text-neutral-600 mb-2">Target team</span>
            <select value={selectedTeam} onChange={(e) => setTeam(e.target.value)} disabled={!teams.length} className="w-full rounded-lg bg-white/[0.04] border border-white/10 px-3 py-2 text-sm text-white outline-none disabled:text-neutral-500">
              {!teams.length && <option value="">Constructor standings unavailable</option>}
              {teams.map((teamOption) => <option key={teamOption.slug} value={teamOption.slug}>{teamOption.name}</option>)}
            </select>
          </label>
          <StatusPill color={color}>{data?.team.name ?? "Profile updating"}</StatusPill>
          {data?.source && <StatusPill color="#3671C6">Official standings</StatusPill>}
        </div>
      </Panel>

      {!teamsLoading && (teamsError || teamsData?.error || teams.length === 0) && (
        <div className="mb-5">
          <InlineNotice title="Constructor Feed Unavailable" tone="error">
            {teamsData?.error ?? "The constructor standings API did not respond."}
            <button onClick={() => void reloadTeams()} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
          </InlineNotice>
        </div>
      )}

      {isLoading && (
        <SectionLoader
          title="Refreshing rival standing read"
          detail="Updating constructor gap, driver contribution, threats, and opportunities from the standings feed."
        />
      )}

      {!isLoading && error && (
        <Panel className="p-8">
          <InlineNotice title="Intel Profile Unavailable" tone="error">
            The rival profile could not be loaded.
            <button onClick={() => void mutate()} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
          </InlineNotice>
        </Panel>
      )}

      {!isLoading && !error && data && (
        <>
          <MetricRow>
            <MetricCard label="Intel Target" value={data.team.name} sub="Competitor profile" icon={Radar} color={color} />
            <MetricCard label="Evidence Items" value={String(data.upgrade_watch.length)} sub="Standings-derived facts" icon={Database} color="#3671C6" />
            <MetricCard label="Threats" value={String(data.threats.length)} sub="Championship pressure" icon={AlertTriangle} color="#E10600" />
            <MetricCard label="Opportunities" value={String(data.opportunities.length)} sub="Points scenarios" icon={ShieldCheck} />
          </MetricRow>

          <div className="flex flex-col gap-5 xl:flex-row xl:flex-wrap sm:[&>*]:min-w-[320px] [&>*]:flex-1">
            <Panel className="p-5" accent={color}>
              <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>Performance Read</h2>
              <p className="text-sm text-neutral-400 leading-relaxed mb-5">{data.team.strategy_tendency}</p>
              <div className="flex flex-col gap-4 sm:flex-row [&>*]:flex-1">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.18em] text-neutral-600 mb-3">Standing Evidence</p>
                  <div className="space-y-2">
                    {data.team.strengths.map((item) => <StatusPill key={item} color={color}>{item}</StatusPill>)}
                  </div>
                </div>
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.18em] text-neutral-600 mb-3">Pressure Points</p>
                  <div className="space-y-2">
                    {data.team.weaknesses.map((item) => <StatusPill key={item} color="#FFF200">{item}</StatusPill>)}
                  </div>
                </div>
              </div>
            </Panel>

            <Panel className="p-5">
              <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>Evidence Board</h2>
              <div className="space-y-2">
                {data.upgrade_watch.map((item) => (
                  <div key={item} className="flex items-start gap-3 rounded-lg border border-white/6 bg-white/[0.025] p-3">
                    <BarChart3 className="h-4 w-4 shrink-0 text-neutral-600 mt-0.5" />
                    <p className="text-sm text-neutral-400 leading-relaxed">{item}</p>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel className="p-5">
              <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>Threats</h2>
              <div className="space-y-2">
                {data.threats.map((item) => (
                  <div key={item} className="rounded-lg border border-red-500/20 bg-red-500/[0.035] p-3 text-sm text-neutral-400">{item}</div>
                ))}
              </div>
            </Panel>

            <Panel className="p-5">
              <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>Opportunities</h2>
              <div className="space-y-2">
                {data.opportunities.map((item) => (
                  <div key={item} className="rounded-lg border border-[#00FF78]/20 bg-[#00FF78]/[0.035] p-3 text-sm text-neutral-400">{item}</div>
                ))}
              </div>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
