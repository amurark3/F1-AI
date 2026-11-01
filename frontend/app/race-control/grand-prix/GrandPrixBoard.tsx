"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { LocalCountdown, LocalTime } from "@/app/components/LocalTime";

import { InlineNotice, SectionLoader, rcFont } from "../components/RaceControlPrimitives";
import { TabPanel, Tabs } from "../components/Tabs";

import { WeekendPanel } from "./GrandPrixPanels";
import { GridPenalties } from "./GridPenalties";
import { HUB_TABS, type HubTab, type PredictionView } from "./hubNavigation";
import { buildDriverLookup, raceSessionTime } from "./predictionHelpers";
import { PredictionSection } from "./PredictionSection";
import { SeasonRoundStrip } from "./SeasonRoundStrip";
import { StartingGrid } from "./StartingGrid";
import { StintChart } from "./StintChart";
import { WeekendSessions } from "./WeekendSessions";

import type { StartingGridResponse } from "./gridModel";
import type {
  DriverPrediction,
  DriverStanding,
  PredictionPhase,
  PredictionsResponse,
  RaceEvent,
  RiskPrediction,
} from "./predictionModel";
import type { PhaseTabState } from "./PredictionPhaseTabs";
import type { WeekendSessionsResponse } from "./sessionsModel";
import type { RaceStrategyResponse } from "./strategyModel";

const HUB_TABS_ID = "grand-prix";

const STATUS_LABELS: Record<string, string> = {
  completed: "Completed",
  upcoming: "Upcoming",
  in_progress: "Race weekend",
  live: "Live",
};

/**
 * The event this screen is reporting on, in one line. The round strip above
 * is the one control that changes it; the countdown shows only while there is
 * still a race to count down to.
 */
function RaceHeader({
  selectedRound,
  selectedRace,
  raceName,
}: {
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  raceName: string;
}) {
  const raceTime = raceSessionTime(selectedRace);
  const status = selectedRace?.status ?? "";

  return (
    <div className="flex flex-col gap-3 border-b border-[#1E2633] pb-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h1 className="text-3xl font-black leading-tight text-white sm:text-4xl" style={rcFont}>
          {raceName}
        </h1>
        <p className="mt-2 flex flex-wrap gap-x-2 gap-y-1 font-mono text-xs text-[#8E96A8]">
          <span>{selectedRace?.circuit?.circuit_name ?? selectedRace?.location ?? "Circuit TBC"}</span>
          <span aria-hidden="true">·</span>
          <span>Round {selectedRound ?? "-"}</span>
          <span aria-hidden="true">·</span>
          <span>
            Race <LocalTime value={raceTime} style="day" fallback="date TBC" />{" "}
            <LocalTime value={raceTime} style="time" fallback="time TBC" />
          </span>
          <span aria-hidden="true">·</span>
          <b className="text-white">{STATUS_LABELS[status] ?? (status || "Status unknown")}</b>
        </p>
      </div>
      {status !== "completed" && <LocalCountdown value={raceTime} />}
    </div>
  );
}

function PredictionAlerts({
  scheduleError,
  driversError,
  onReloadSchedule,
  onReloadDrivers,
}: {
  scheduleError: boolean;
  driversError: boolean;
  onReloadSchedule: () => void;
  onReloadDrivers: () => void;
}) {
  return (
    <>
      {scheduleError && (
        <InlineNotice title="Race calendar unavailable" tone="error">
          The race list could not be loaded.
          <button onClick={onReloadSchedule} className="ml-2 font-bold text-white underline decoration-white/30">
            Retry
          </button>
        </InlineNotice>
      )}
      {driversError && (
        <InlineNotice title="Driver standings unavailable" tone="warning">
          Driver-name lookups may be limited.
          <button onClick={onReloadDrivers} className="ml-2 font-bold text-white underline decoration-white/30">
            Retry
          </button>
        </InlineNotice>
      )}
    </>
  );
}

/** A way into the Telemetry Lab for the round on screen. */
function TelemetryLink({ round, tab, label }: { round: number | null; tab: string; label: string }) {
  if (round === null) return null;
  return (
    <Link
      href={`/race-control/telemetry?tab=${tab}&round=${round}`}
      className="inline-flex items-center gap-1.5 font-mono text-xs text-[#86B6EF] hover:text-white"
    >
      {label}
      <ArrowRight className="h-3.5 w-3.5" aria-hidden />
    </Link>
  );
}

/** What each driver ran, and every stop that punctuated it. */
function StintsSection({ strategy, strategyLoading }: { strategy?: RaceStrategyResponse; strategyLoading: boolean }) {
  if (strategyLoading) {
    return (
      <SectionLoader
        title="Loading race strategy"
        detail="Reading tyre stints from timing data and pit stops from the published stop sheet."
      />
    );
  }

  return <StintChart data={strategy} />;
}

/** The starting grid and the penalties that shaped it. */
function GridSection({
  grid,
  gridLoading,
  raceName,
}: {
  grid?: StartingGridResponse;
  gridLoading: boolean;
  raceName: string;
}) {
  if (gridLoading) {
    return (
      <SectionLoader
        title="Loading the starting grid"
        detail="Reading the published grid sheet for this Grand Prix, and any penalties applied to it."
      />
    );
  }

  return (
    <div className="space-y-4">
      <StartingGrid data={grid} raceName={raceName} />
      <GridPenalties data={grid} />
    </div>
  );
}

export interface GrandPrixBoardProps {
  year: number;
  /** The section on screen, from the URL or the weekend's progress. */
  activeTab: HubTab;
  /** Which view of the prediction the Predictions tab shows. */
  predictionView: PredictionView;
  onSelectTab: (tab: HubTab) => void;
  onSelectView: (view: PredictionView) => void;
  schedule: RaceEvent[];
  scheduleError: boolean;
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  data?: PredictionsResponse;
  grid?: StartingGridResponse;
  gridLoading: boolean;
  sessions?: WeekendSessionsResponse;
  sessionsLoading: boolean;
  strategy?: RaceStrategyResponse;
  strategyLoading: boolean;
  predictions: DriverPrediction[];
  riskPredictions: RiskPrediction[];
  podium: DriverPrediction[];
  drivers: DriverStanding[];
  driversError: boolean;
  raceName: string;
  predictionLoading: boolean;
  predictionError: boolean;
  /** Which of the race's two predictions the prediction tabs are describing. */
  activePhase: PredictionPhase;
  phaseStates: PhaseTabState[];
  /** False while the active phase cannot be computed yet. */
  phaseAvailable: boolean;
  isComputing: boolean;
  computeReason: "manual_compute" | "qualifying_recompute" | null;
  /** A failed recompute, shown inside the prediction section it belongs to. */
  computeError: string | null;
  onSelectRound: (round: number) => void;
  onSelectPhase: (phase: PredictionPhase) => void;
  onRun: () => void;
  onRetry: () => void;
  onReloadSchedule: () => void;
  onReloadDrivers: () => void;
}

/**
 * The Grand Prix Hub: one round of the season, from every angle this stack has.
 *
 * Predictions are one section among several rather than the frame around the
 * whole screen, so the circuit profile, the starting grid and the results
 * review all render on a weekend no model has been run for.
 */
export function GrandPrixBoard(props: GrandPrixBoardProps) {
  const { activeTab } = props;
  const driverLookup = useMemo(() => buildDriverLookup(props.drivers), [props.drivers]);

  return (
    <div className="space-y-4">
      <SeasonRoundStrip
        schedule={props.schedule}
        selectedRound={props.selectedRound}
        onSelectRound={props.onSelectRound}
        year={props.year}
      />

      <RaceHeader selectedRound={props.selectedRound} selectedRace={props.selectedRace} raceName={props.raceName} />

      <Tabs
        items={HUB_TABS}
        active={activeTab}
        onChange={props.onSelectTab}
        idPrefix={HUB_TABS_ID}
        label="Grand Prix sections"
      />

      <PredictionAlerts
        scheduleError={props.scheduleError}
        driversError={props.driversError}
        onReloadSchedule={props.onReloadSchedule}
        onReloadDrivers={props.onReloadDrivers}
      />

      <TabPanel idPrefix={HUB_TABS_ID} active={activeTab} className="space-y-4">
        {activeTab === "weekend" && <WeekendPanel year={props.year} selectedRace={props.selectedRace} />}

        {activeTab === "sessions" && (
          <>
            <WeekendSessions data={props.sessions} loading={props.sessionsLoading} raceName={props.raceName} />
            <TelemetryLink round={props.selectedRound} tab="map" label="Speed maps and lap-by-lap comparisons" />
          </>
        )}

        {activeTab === "grid" && (
          <GridSection grid={props.grid} gridLoading={props.gridLoading} raceName={props.raceName} />
        )}

        {activeTab === "stints" && (
          <>
            <StintsSection strategy={props.strategy} strategyLoading={props.strategyLoading} />
            <TelemetryLink round={props.selectedRound} tab="tyres" label="Tyre degradation for this race" />
          </>
        )}

        {activeTab === "predictions" && <PredictionSection {...props} driverLookup={driverLookup} />}
      </TabPanel>
    </div>
  );
}
