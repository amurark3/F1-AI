"use client";

import { RacePicker } from "@/app/ui/race-picker/RacePicker";
import { FIRST_RACE_SEASON } from "@/app/ui/race-picker/raceUrl";
import { useSchedule } from "@/app/ui/race-picker/useSchedule";
import { DISPLAY } from "@/app/ui/typography";

import { InlineNotice, PageStack } from "../components/RaceControlPrimitives";
import { resolveDefaultRace } from "../grand-prix/predictionHelpers";

import { AnalysisGate } from "./AnalysisNotice";
import { ANALYSIS_PANEL_ID, AnalysisToolbar } from "./AnalysisToolbar";
import { HeadToHeadControls } from "./HeadToHeadControls";
import { HeadToHeadPanel } from "./HeadToHeadPanel";
import { TrackMapControls } from "./TrackMapControls";
import { TrackMapPanel } from "./TrackMapPanel";
import { TyreDegPanel } from "./TyreDegPanel";
import { useWeekend } from "./useAnalysisData";
import { useTelemetryParams } from "./useTelemetryParams";

import type { TabKey, WeekendSession } from "./telemetryModel";
import type { RaceEvent } from "../grand-prix/predictionModel";

export interface TelemetrySeed {
  year: number;
  schedule: RaceEvent[] | { error: string } | null;
}

const RACE_CODES = new Set(["S", "R"]);
const CLEAR_SESSION_SELECTION = { session: null, a: null, b: null, lap: null, segment: null };
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

export function TelemetryView({ seed }: { seed: TelemetrySeed }) {
  const { params, update } = useTelemetryParams(seed.year);
  const races = useSchedule(params.year, params.year === seed.year ? seed.schedule : null).races;
  const round = params.round ?? resolveDefaultRace(races)?.round ?? null;
  const weekend = useWeekend(params.year, round);
  const sessions = weekend.data?.sessions ?? [];
  const session = pickSession(sessions, params.tab, params.session);

  return (
    <PageStack>
      <RacePicker
        year={params.year}
        races={races}
        selectedRound={round}
        view="telemetry"
        onSelectRound={(next) => update({ round: next, ...CLEAR_SESSION_SELECTION })}
        onSelectYear={(year) => update({ year, round: null, ...CLEAR_SESSION_SELECTION })}
      />
      <header className="min-w-0">
        <h1 className={`${DISPLAY} text-4xl text-rc-ink sm:text-5xl`}>Telemetry Lab</h1>
        <p className="mt-2 text-sm text-rc-ink-2">
          Lap timing and car telemetry from OpenF1 since {FIRST_RACE_SEASON}.
        </p>
      </header>
      <AnalysisToolbar
        tab={params.tab}
        onTab={(tab) => {
          update({ tab });
        }}
        sessions={weekend.data?.available ? sessions : null}
        session={session}
        allowed={allowedFor(params.tab)}
        onSession={(code) => {
          update({ session: code, lap: null, segment: null });
        }}
      >
        {params.tab === "map" && (
          <TrackMapControls
            year={params.year}
            round={round}
            session={session}
            driver={params.a}
            lap={params.lap}
            segment={params.segment}
            onPick={(driver, lap) => {
              update({ a: driver, lap });
            }}
            onSegment={(segment) => {
              update({ segment, lap: null });
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
            segment={params.segment}
            onPick={(a, b) => {
              update({ a, b, lap: null });
            }}
            onSegment={(segment) => {
              update({ segment, lap: null });
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
          <TrackMapPanel
            year={params.year}
            round={round}
            session={session}
            driver={params.a}
            lap={params.lap}
            segment={params.segment}
          />
        )}
        {params.tab === "head-to-head" && (
          <HeadToHeadPanel
            year={params.year}
            round={round}
            session={session}
            a={params.a}
            b={params.b}
            segment={params.segment}
          />
        )}
        {params.tab === "tyres" && <TyreDegPanel year={params.year} round={round} session={session} />}
      </div>
    </PageStack>
  );
}
