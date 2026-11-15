"use client";

import { RacePicker } from "@/app/ui/race-picker/RacePicker";
import { useSchedule } from "@/app/ui/race-picker/useSchedule";

import { InlineNotice, PageStack, SectionHeader } from "../components/RaceControlPrimitives";
import { resolveDefaultRace } from "../grand-prix/predictionHelpers";

import { AnalysisGate } from "./AnalysisNotice";
import { ANALYSIS_PANEL_ID, AnalysisToolbar } from "./AnalysisToolbar";
import { HeadToHeadControls } from "./HeadToHeadControls";
import { HeadToHeadPanel } from "./HeadToHeadPanel";
import { FIRST_SEASON, type TabKey, type WeekendSession } from "./telemetryModel";
import { TrackMapControls } from "./TrackMapControls";
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

export function TelemetryView({ seed }: { seed: TelemetrySeed }) {
  const { params, update } = useTelemetryParams(seed.year);
  const races = useSchedule(params.year, params.year === seed.year ? seed.schedule : null).races;
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
      <RacePicker
        year={params.year}
        races={races}
        selectedRound={round}
        onSelectRound={(next) => {
          update({ round: next, session: null, a: null, b: null, lap: null });
        }}
        seasons={{
          years: seasons(seed.year),
          onSelect: (year) => {
            update({ year, round: null, session: null, a: null, b: null, lap: null });
          },
        }}
      />
      <AnalysisToolbar
        tab={params.tab}
        onTab={(tab) => {
          update({ tab });
        }}
        sessions={weekend.data?.available ? sessions : null}
        session={session}
        allowed={allowedFor(params.tab)}
        onSession={(code) => {
          update({ session: code, lap: null });
        }}
      >
        {params.tab === "map" && (
          <TrackMapControls
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
          <HeadToHeadControls
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
      </AnalysisToolbar>
      <AnalysisGate state={weekend} loadingTitle="Loading the weekend's sessions" />
      {weekend.data?.available && session === null && (
        <InlineNotice title="Not run yet" tone="info">
          No session of this kind has started on this weekend yet. Pick an earlier round to analyse.
        </InlineNotice>
      )}
      <div id={ANALYSIS_PANEL_ID} role="tabpanel" className="space-y-4">
        {params.tab === "map" && (
          <TrackMapPanel year={params.year} round={round} session={session} driver={params.a} lap={params.lap} />
        )}
        {params.tab === "head-to-head" && (
          <HeadToHeadPanel year={params.year} round={round} session={session} a={params.a} b={params.b} />
        )}
        {params.tab === "tyres" && <TyreDegPanel year={params.year} round={round} session={session} />}
      </div>
    </PageStack>
  );
}
