"use client";

import { Activity, Gauge, Timer } from "lucide-react";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { seededWith } from "@/app/lib/swrFallback";
import { fetcher } from "@/app/utils/fetcher";

import { InlineNotice, PageStack, SectionHeader } from "../components/RaceControlPrimitives";
import { resolveDefaultRace } from "../grand-prix/predictionHelpers";
import { SeasonRoundStrip } from "../grand-prix/SeasonRoundStrip";

import { AnalysisGate } from "./AnalysisNotice";
import { SessionPicker, YearPicker } from "./AnalysisPickers";
import { HeadToHeadPanel } from "./HeadToHeadPanel";
import { FIRST_SEASON, TABS, type TabKey, type WeekendSession } from "./telemetryModel";
import { TrackMapPanel } from "./TrackMapPanel";
import { TyreDegPanel } from "./TyreDegPanel";
import { useWeekend } from "./useAnalysisData";
import { useTelemetryParams } from "./useTelemetryParams";

import type { RaceEvent } from "../grand-prix/predictionModel";

export interface TelemetrySeed {
  year: number;
  schedule: RaceEvent[] | { error: string } | null;
}

const RACE_CODES = new Set(["S", "R"]);
/** Which session each tab opens on, most useful first. */
const PREFERRED: Record<TabKey, string[]> = {
  map: ["Q", "SQ", "FP3", "FP2", "FP1", "R", "S"],
  "head-to-head": ["Q", "SQ", "FP3", "FP2", "FP1", "R", "S"],
  tyres: ["R", "S"],
};
const TAB_ICONS = { map: Gauge, "head-to-head": Activity, tyres: Timer };

function allowedFor(tab: TabKey): (code: string) => boolean {
  return tab === "tyres" ? (code) => RACE_CODES.has(code) : () => true;
}

/** The session a tab shows: the one asked for if it fits the tab and has run, else the most useful that has. */
export function pickSession(sessions: WeekendSession[], tab: TabKey, asked: string | null): string | null {
  const started = new Set(sessions.filter((session) => session.started).map((session) => session.code));
  if (asked && allowedFor(tab)(asked) && started.has(asked)) return asked;
  return PREFERRED[tab].find((code) => started.has(code)) ?? null;
}

function seasons(current: number): number[] {
  return Array.from({ length: current - FIRST_SEASON + 1 }, (_, index) => current - index);
}

function useSchedule(year: number, seed: TelemetrySeed): RaceEvent[] {
  const response = useSWR<RaceEvent[] | { error: string }, Error>(`${API_BASE}/api/schedule/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 600000,
    ...seededWith(year === seed.year ? seed.schedule : null),
  });
  return Array.isArray(response.data) ? response.data : [];
}

function TabBar({ tab, onChange }: { tab: TabKey; onChange: (tab: TabKey) => void }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-[#1E2633]" role="group" aria-label="Analysis">
      {TABS.map((item) => {
        const Icon = TAB_ICONS[item.key];
        const selected = item.key === tab;
        return (
          <button
            key={item.key}
            type="button"
            aria-pressed={selected}
            onClick={() => {
              onChange(item.key);
            }}
            className={`-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-semibold transition-colors ${
              selected ? "border-[#3987E5] text-white" : "border-transparent text-[#7F8797] hover:text-white"
            }`}
          >
            <Icon className="h-4 w-4" aria-hidden />
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

export function TelemetryView({ seed }: { seed: TelemetrySeed }) {
  const { params, update } = useTelemetryParams(seed.year);
  const races = useSchedule(params.year, seed);
  const round = params.round ?? resolveDefaultRace(races)?.round ?? null;
  const weekend = useWeekend(params.year, round);
  const sessions = weekend.data?.sessions ?? [];
  const session = pickSession(sessions, params.tab, params.session);

  return (
    <PageStack>
      <SectionHeader
        eyebrow="Telemetry Lab"
        title="Speed, lines and tyre wear, lap by lap"
        description="Car telemetry and lap timing from OpenF1 for every session since 2023: a lap drawn round the circuit by speed, two drivers' laps side by side, and how fast each compound wore through a race."
      />
      <YearPicker
        years={seasons(seed.year)}
        value={params.year}
        onChange={(year) => {
          update({ year, round: null, session: null, a: null, b: null, lap: null });
        }}
      />
      <SeasonRoundStrip
        schedule={races}
        year={params.year}
        selectedRound={round}
        onSelectRound={(next) => {
          update({ round: next, session: null, a: null, b: null, lap: null });
        }}
      />
      <TabBar
        tab={params.tab}
        onChange={(tab) => {
          update({ tab });
        }}
      />
      <AnalysisGate state={weekend} loadingTitle="Loading the weekend's sessions" />
      {weekend.data?.available && (
        <SessionPicker
          sessions={sessions}
          value={session}
          allowed={allowedFor(params.tab)}
          onChange={(code) => {
            update({ session: code, lap: null });
          }}
        />
      )}
      {weekend.data?.available && session === null && (
        <InlineNotice title="Not run yet" tone="info">
          No session of this kind has started on this weekend yet. Pick an earlier round to analyse.
        </InlineNotice>
      )}
      {params.tab === "map" && (
        <TrackMapPanel
          year={params.year}
          round={round}
          session={session}
          driver={params.a}
          lap={params.lap}
          onPick={(driver, lap) => {
            update({ a: driver, lap });
          }}
        />
      )}
      {params.tab === "head-to-head" && (
        <HeadToHeadPanel
          year={params.year}
          round={round}
          session={session}
          a={params.a}
          b={params.b}
          onPick={(a, b) => {
            update({ a, b, lap: null });
          }}
        />
      )}
      {params.tab === "tyres" && <TyreDegPanel year={params.year} round={round} session={session} />}
    </PageStack>
  );
}
