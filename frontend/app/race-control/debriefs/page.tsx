"use client";

import { AlertTriangle, ClipboardList, Flag, Trophy, Users } from "lucide-react";
import { useMemo, useState } from "react";
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
  SectionLoader,
  SkeletonPanel,
  StatusPill,
  WorkspaceSplit,
  rcFont,
} from "../components/RaceControlPrimitives";

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  status: string;
}

interface Debrief {
  race?: string;
  location?: string;
  headline?: string;
  podium?: Array<{ position: number; driver: string; full_name: string; team: string; points: number }>;
  podium_cause?: Array<{
    position: number;
    driver: string;
    full_name: string;
    team: string;
    grid?: number | null;
    points: number;
    delta?: number | null;
    call: string;
  }>;
  strategy_winners?: Array<{ position: number; driver: string; full_name: string; team: string; grid: number }>;
  constructor_impact?: Array<{ team: string; points: number; classified_cars: number }>;
  reliability_watch?: Array<{ position: number; driver: string; full_name: string; team: string; status: string }>;
  classification?: Array<{
    position: number;
    driver: string;
    full_name: string;
    team: string;
    grid?: number | null;
    points: number;
    status: string;
  }>;
  race_control_notes?: Array<{ label: string; detail: string }>;
  takeaways?: string[];
  insight_source?: string;
  error?: string;
}

const year = new Date().getFullYear();

export default function DebriefsPage() {
  const [selectedRound, setSelectedRound] = useState<number | null>(null);
  const {
    data: scheduleResponse,
    error: scheduleError,
    isLoading: scheduleLoading,
    mutate: reloadSchedule,
  } = useSWR<RaceEvent[] | { error: string }, Error>(`${API_BASE}/api/schedule/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 300000,
  });

  const races = useMemo(() => (Array.isArray(scheduleResponse) ? scheduleResponse : []), [scheduleResponse]);
  const completedRaces = useMemo(() => races.filter((race) => race.status === "completed"), [races]);
  const defaultRace = useMemo(() => completedRaces.at(-1) ?? races[0] ?? null, [completedRaces, races]);
  const effectiveRound = selectedRound ?? defaultRace?.round ?? null;
  const selectedRace = races.find((race) => race.round === effectiveRound) ?? defaultRace;
  const {
    data,
    error: debriefError,
    isLoading: debriefLoading,
    mutate,
  } = useSWR<Debrief, Error>(
    effectiveRound ? `${API_BASE}/api/race-control/debrief/${year}/${effectiveRound}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 120000 },
  );

  const pageLoading = scheduleLoading && races.length === 0;

  if (pageLoading) {
    return (
      <div>
        <SectionHeader
          eyebrow="Race Debrief Generator"
          title="Post-Race Review"
          description="Select a Grand Prix and generate a debrief from the final classification: podium, grid gain, points swing, non-finish statuses, and constructor impact."
        />
        <PageLoader
          title="Preparing debrief desk"
          detail="Loading the race calendar so completed Grands Prix can be selected by name."
        />
      </div>
    );
  }

  return (
    <div>
      <SectionHeader
        eyebrow="Race Debrief Generator"
        title="Post-Race Review"
        description="Select a Grand Prix and generate a debrief from the final classification: podium, grid gain, points swing, non-finish statuses, and constructor impact."
      />

      <DebriefSelector
        races={races}
        effectiveRound={effectiveRound}
        selectedRace={selectedRace}
        scheduleLoading={scheduleLoading}
        debriefLoading={debriefLoading}
        showScheduleError={Boolean(scheduleError) || (!scheduleLoading && races.length === 0)}
        onSelectRound={setSelectedRound}
        onRefresh={() => void mutate()}
        onReloadSchedule={() => void reloadSchedule()}
      />

      <DebriefBody
        debriefLoading={debriefLoading}
        hasError={Boolean(debriefError) || Boolean(data?.error)}
        errorMessage={data?.error}
        data={data}
        selectedRace={selectedRace}
        onRetry={() => void mutate()}
      />
    </div>
  );
}

interface DebriefSelectorProps {
  races: RaceEvent[];
  effectiveRound: number | null;
  selectedRace: RaceEvent | null;
  scheduleLoading: boolean;
  debriefLoading: boolean;
  showScheduleError: boolean;
  onSelectRound: (round: number) => void;
  onRefresh: () => void;
  onReloadSchedule: () => void;
}

function DebriefSelector({
  races,
  effectiveRound,
  selectedRace,
  scheduleLoading,
  debriefLoading,
  showScheduleError,
  onSelectRound,
  onRefresh,
  onReloadSchedule,
}: DebriefSelectorProps) {
  return (
    <Panel className="p-5 mb-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <label className="min-w-0 flex-1">
          <span className="block text-xs font-black uppercase tracking-[0.18em] text-neutral-300 mb-2" style={rcFont}>
            Grand Prix
          </span>
          <select
            value={effectiveRound ?? ""}
            onChange={(event) => onSelectRound(Number(event.target.value))}
            disabled={scheduleLoading || races.length === 0}
            className="h-12 w-full rounded-lg border border-white/12 bg-[#151817] px-3 text-base font-semibold text-white outline-none focus:border-[#00FF78]/70 disabled:text-neutral-500"
          >
            <option value="">{scheduleLoading ? "Loading race calendar..." : "Select a completed race"}</option>
            {races.map((race) => (
              <option key={race.round} value={race.round}>
                {race.name} ({race.status})
              </option>
            ))}
          </select>
          {selectedRace && (
            <p className="mt-2 text-sm text-neutral-400">
              {selectedRace.location} · {selectedRace.status}
            </p>
          )}
        </label>

        <button
          onClick={onRefresh}
          disabled={!effectiveRound || debriefLoading}
          className="inline-flex h-12 w-full items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] px-5 text-sm font-black uppercase tracking-wider text-neutral-200 hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:text-neutral-600 lg:mt-6 lg:w-[190px] lg:shrink-0"
        >
          {debriefLoading ? "Updating Review..." : "Refresh Review"}
        </button>
      </div>

      {showScheduleError && (
        <div className="mt-4">
          <InlineNotice title="Race Calendar Unavailable" tone="error">
            The race list could not be loaded. Refresh once the schedule feed is available.
            <button onClick={onReloadSchedule} className="ml-2 font-bold text-white underline decoration-white/30">
              Retry
            </button>
          </InlineNotice>
        </div>
      )}
    </Panel>
  );
}

interface DebriefBodyProps {
  debriefLoading: boolean;
  hasError: boolean;
  errorMessage?: string;
  data?: Debrief;
  selectedRace: RaceEvent | null;
  onRetry: () => void;
}

function DebriefBody({ debriefLoading, hasError, errorMessage, data, selectedRace, onRetry }: DebriefBodyProps) {
  if (debriefLoading) {
    return <DebriefSkeleton />;
  }
  if (hasError) {
    return <DebriefErrorPanel message={errorMessage} onRetry={onRetry} />;
  }
  return <DebriefReport data={data} selectedRace={selectedRace} />;
}

/** Empty-state fallback used by every list section in the report. */
function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-neutral-500">{children}</p>;
}

function DebriefErrorPanel({ message, onRetry }: { message?: string; onRetry: () => void }) {
  return (
    <Panel className="p-8">
      <div className="flex items-start gap-4">
        <AlertTriangle className="mt-1 h-6 w-6 text-[#E10600]" />
        <div>
          <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>
            Debrief Unavailable
          </h2>
          <p className="mt-2 text-base text-neutral-400">
            {message ?? "The classification could not be loaded for this Grand Prix."}
          </p>
          <button
            onClick={onRetry}
            className="mt-5 rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-bold text-neutral-200 hover:text-white"
          >
            Retry Debrief
          </button>
        </div>
      </div>
    </Panel>
  );
}

function DebriefSummaryPanel({ data }: { data?: Debrief }) {
  const hasDebrief = Boolean(
    data && !data.error && (data.podium?.length || data.strategy_winners?.length || data.headline),
  );
  const takeaways = data?.takeaways ?? [];
  const notes = data?.race_control_notes ?? [];

  return (
    <Panel className="p-5" accent="#00FF78">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400 mb-2" style={rcFont}>
            Executive Summary
          </p>
          <h2 className="text-3xl font-black italic uppercase text-white leading-none" style={rcFont}>
            {data?.race ?? "Race Debrief"}
          </h2>
        </div>
        {hasDebrief && <StatusPill>Classification</StatusPill>}
      </div>
      <p className="text-base text-neutral-300 leading-relaxed">
        {data?.headline ?? "Select a completed Grand Prix to generate the debrief."}
      </p>

      <div className="mt-6">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-black uppercase tracking-wider text-neutral-400">Key Takeaways</h3>
          {data?.insight_source && <span className="text-xs text-neutral-500">Classification-derived</span>}
        </div>
        <div className="space-y-2">
          {takeaways.length === 0 && <EmptyNote>Takeaways appear once the race classification is available.</EmptyNote>}
          {takeaways.map((item) => (
            <div
              key={item}
              className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 text-sm text-neutral-300"
            >
              {item}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6">
        <h3 className="mb-3 text-sm font-black uppercase tracking-wider text-neutral-400">Race-Control Notes</h3>
        <div className="space-y-2">
          {notes.length === 0 && (
            <EmptyNote>Race-control notes appear once classification data is available.</EmptyNote>
          )}
          {notes.map((note) => (
            <div key={note.label} className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
              <p className="text-xs font-black uppercase tracking-[0.12em] text-neutral-500">{note.label}</p>
              <p className="mt-1 text-sm leading-relaxed text-neutral-300">{note.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function PodiumCausePanel({ rows }: { rows: NonNullable<Debrief["podium_cause"]> }) {
  return (
    <Panel className="p-5">
      <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>
        Podium Cause
      </h2>
      <div className="space-y-2">
        {rows.length === 0 && <EmptyNote>Podium data is not available yet.</EmptyNote>}
        {rows.map((row) => (
          <div
            key={row.driver}
            className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2"
          >
            <span className="w-8 text-sm font-black text-neutral-400" style={rcFont}>
              P{row.position}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-white truncate">{row.full_name || row.driver}</p>
              <p className="text-xs text-neutral-500 truncate">
                {row.team} · {row.call}
              </p>
            </div>
            <span className="font-mono text-xs text-neutral-400">
              {row.grid ? `G${row.grid}` : `${row.points} pts`}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function StrategyWinnersPanel({ rows }: { rows: NonNullable<Debrief["strategy_winners"]> }) {
  return (
    <Panel className="p-5">
      <h2 className="text-xl font-black italic uppercase text-white mb-4" style={rcFont}>
        Strategy Winners
      </h2>
      <div className="space-y-2">
        {rows.length === 0 && <EmptyNote>Grid-gain data is not available yet.</EmptyNote>}
        {rows.map((row) => (
          <div
            key={`${row.driver}-${row.position}`}
            className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2"
          >
            <ClipboardList className="h-4 w-4 text-neutral-500" />
            <span className="flex-1 text-sm font-bold text-neutral-300 truncate">{row.full_name || row.driver}</span>
            <span className="text-xs font-mono text-[#00FF78]">
              G{row.grid} to P{row.position}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ClassificationTable({ rows }: { rows: NonNullable<Debrief["classification"]> }) {
  return (
    <Panel className="p-5">
      <h2 className="mb-4 text-xl font-black italic uppercase text-white" style={rcFont}>
        Top Classification
      </h2>
      <div className="overflow-x-auto rounded-lg border border-white/10">
        <table className="min-w-[720px] w-full text-left text-sm">
          <thead className="bg-white/[0.04] text-xs uppercase tracking-[0.12em] text-neutral-500">
            <tr>
              <th className="px-3 py-2">Pos</th>
              <th className="px-3 py-2">Driver</th>
              <th className="px-3 py-2">Team</th>
              <th className="px-3 py-2">Grid</th>
              <th className="px-3 py-2">Pts</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/8">
            {rows.slice(0, 10).map((row) => (
              <tr key={`${row.position}-${row.driver}`} className="bg-white/[0.02]">
                <td className="px-3 py-3 font-mono text-neutral-300">P{row.position}</td>
                <td className="px-3 py-3 font-bold text-white">{row.full_name || row.driver}</td>
                <td className="px-3 py-3 text-neutral-400">{row.team}</td>
                <td className="px-3 py-3 font-mono text-neutral-400">{row.grid ? `G${row.grid}` : "-"}</td>
                <td className="px-3 py-3 font-mono text-[#00FF78]">{row.points}</td>
                <td className="px-3 py-3 text-neutral-400">{row.status || "Finished"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function ConstructorImpactPanel({ rows }: { rows: NonNullable<Debrief["constructor_impact"]> }) {
  return (
    <Panel className="p-5">
      <h2 className="mb-4 text-xl font-black italic uppercase text-white" style={rcFont}>
        Constructor Impact
      </h2>
      <div className="space-y-2">
        {rows.length === 0 && <EmptyNote>Constructor impact appears once points are available.</EmptyNote>}
        {rows.map((team) => (
          <div
            key={team.team}
            className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2.5"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-white">{team.team}</p>
              <p className="text-xs text-neutral-500">
                {team.classified_cars} classified car{team.classified_cars === 1 ? "" : "s"}
              </p>
            </div>
            <p className="font-mono text-sm text-[#00FF78]">{team.points} pts</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

/** Count of grid movers plus non-standard finish statuses shown as review flags. */
function countReviewFlags(data?: Debrief): number {
  return (data?.strategy_winners?.length ?? 0) + (data?.reliability_watch?.length ?? 0);
}

function DebriefMetrics({ data, selectedRace }: { data?: Debrief; selectedRace: RaceEvent | null }) {
  const constructorLeader = data?.constructor_impact?.[0];
  const raceName = data?.race ?? selectedRace?.name ?? "Select Race";
  const raceLocation = data?.location ?? selectedRace?.location ?? "Classification";
  const leaderSub = constructorLeader
    ? `${constructorLeader.points} pts · ${constructorLeader.classified_cars} classified cars`
    : "Constructor impact";

  return (
    <MetricRow>
      <MetricCard label="Race" value={raceName} sub={raceLocation} icon={Flag} color="#E10600" />
      <MetricCard
        label="Top constructor"
        value={constructorLeader?.team ?? "No points"}
        sub={leaderSub}
        icon={Trophy}
      />
      <MetricCard
        label="Review flags"
        value={String(countReviewFlags(data))}
        sub="Movers plus non-standard statuses"
        icon={Users}
        color="#FF8000"
      />
    </MetricRow>
  );
}

function DebriefReport({ data, selectedRace }: { data?: Debrief; selectedRace: RaceEvent | null }) {
  return (
    <>
      <DebriefMetrics data={data} selectedRace={selectedRace} />

      <WorkspaceSplit className="xl:[&>*:first-child]:basis-[52%] xl:[&>*:last-child]:flex-1">
        <DebriefSummaryPanel data={data} />
        <div className="space-y-5">
          <PodiumCausePanel rows={data?.podium_cause ?? []} />
          <StrategyWinnersPanel rows={data?.strategy_winners ?? []} />
        </div>
      </WorkspaceSplit>

      <WorkspaceSplit className="mt-6 xl:[&>*]:flex-1">
        <ClassificationTable rows={data?.classification ?? []} />
        <ConstructorImpactPanel rows={data?.constructor_impact ?? []} />
      </WorkspaceSplit>
    </>
  );
}

function DebriefSkeleton() {
  return (
    <div className="space-y-5">
      <SectionLoader
        title="Building race debrief"
        detail="Refreshing the selected Grand Prix classification, podium, movers, and takeaways."
      />
      <MetricRow>
        {Array.from({ length: 3 }).map((_, index) => (
          <SkeletonPanel key={index} className="h-32" />
        ))}
      </MetricRow>
      <WorkspaceSplit className="xl:[&>*:first-child]:basis-[52%] xl:[&>*:last-child]:flex-1">
        <SkeletonPanel className="h-80" />
        <div className="space-y-5">
          <SkeletonPanel className="h-44" />
          <SkeletonPanel className="h-44" />
        </div>
      </WorkspaceSplit>
    </div>
  );
}
