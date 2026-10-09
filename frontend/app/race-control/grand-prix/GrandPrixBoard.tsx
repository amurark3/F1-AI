"use client";

import { useMemo, useState } from "react";

import { LocalCountdown, LocalTime } from "@/app/components/LocalTime";
import type { DriverPrediction } from "@/app/components/PredictionDriverCard";

import { InlineNotice, SectionLoader, rcFont } from "../components/RaceControlPrimitives";


import { WeekendPanel } from "./GrandPrixPanels";
import { GridPenalties } from "./GridPenalties";
import { buildDriverLookup, raceSessionTime } from "./predictionHelpers";
import { PredictionSection } from "./PredictionSection";
import { SeasonRoundStrip } from "./SeasonRoundStrip";
import { StartingGrid } from "./StartingGrid";
import { StintChart } from "./StintChart";
import { WeekendSessions } from "./WeekendSessions";

import type { StartingGridResponse } from "./gridModel";
import type {
  DriverStanding,
  PredictionPhase,
  PredictionsResponse,
  RaceEvent,
  RiskPrediction,
  TabKey,
} from "./predictionModel";
import type { PhaseTabState } from "./PredictionPhaseTabs";
import type { WeekendSessionsResponse } from "./sessionsModel";
import type { RaceStrategyResponse } from "./strategyModel";

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "weekend", label: "Weekend" },
  { key: "sessions", label: "Sessions" },
  { key: "grid", label: "Grid" },
  { key: "stints", label: "Stints" },
  { key: "predictions", label: "Predictions" },
  { key: "podium", label: "Podium" },
  { key: "risk", label: "DNF / Crash" },
  { key: "model", label: "Model I/O" },
  { key: "results", label: "Results" },
];

/**
 * The tabs whose content comes from a stored prediction snapshot.
 *
 * Everything outside this set describes the event itself and must render on a
 * weekend the model has never been run for — which is why the phase tabs, the
 * run button and the snapshot load states live inside the prediction section
 * rather than above every tab, as they used to.
 */
const PREDICTION_TABS: ReadonlySet<TabKey> = new Set<TabKey>([
  "predictions",
  "podium",
  "risk",
  "model",
  "results",
]);

function isPredictionTab(tab: TabKey): boolean {
  return PREDICTION_TABS.has(tab);
}

interface RaceHeaderProps {
  schedule: RaceEvent[];
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  raceName: string;
  data?: PredictionsResponse;
  scheduleLoading: boolean;
  onSelectRound: (round: number) => void;
}

/** The event this screen is reporting on, and the control that changes it. */
function RaceHeader({
  schedule,
  selectedRound,
  selectedRace,
  raceName,
  data,
  scheduleLoading,
  onSelectRound,
}: RaceHeaderProps) {
  const raceTime = raceSessionTime(selectedRace);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <select
          value={selectedRound ?? ""}
          onChange={(event) => onSelectRound(Number(event.target.value))}
          disabled={scheduleLoading || schedule.length === 0}
          className="h-10 rounded-md border border-[#1E2633] bg-[#0D111B] px-3 font-mono text-xs font-bold text-[#D7DBE7] outline-none focus:border-[#E10600]/70 disabled:text-[#596173]"
          aria-label="Select race"
        >
          <option value="">{scheduleLoading ? "Loading calendar..." : "Select race"}</option>
          {schedule.map((race) => (
            <option key={race.round} value={race.round}>
              {race.name} - Round {race.round}
            </option>
          ))}
        </select>
        <span className="hidden font-mono text-xs text-[#596173] sm:inline">/</span>
        <span className="font-mono text-xs text-[#8E96A8]">
          {selectedRace?.is_sprint ? "Sprint weekend" : "Grand Prix weekend"}
        </span>
      </div>

      <div className="flex flex-col gap-3 border-b border-[#1E2633] pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-black leading-tight text-white sm:text-4xl" style={rcFont}>
            {raceName}
          </h1>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-[#8E96A8]">
            <span>{selectedRace?.location ?? "location TBC"}</span>
            <span>
              Round {selectedRound ?? data?.round ?? "-"}/{data?.year ?? new Date().getFullYear()}
            </span>
            <span>
              Race <LocalTime value={raceTime} style="day" fallback="date TBC" /> -{" "}
              <LocalTime value={raceTime} style="time" fallback="time TBC" />
            </span>
            <span>
              status <b className="text-white">{selectedRace?.status ?? "unknown"}</b>
            </span>
          </div>
        </div>
        <LocalCountdown value={raceTime} />
      </div>
    </div>
  );
}

function TabBar({ activeTab, setActiveTab }: { activeTab: TabKey; setActiveTab: (tab: TabKey) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-[#1E2633]" role="tablist">
      {TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.key}
          onClick={() => setActiveTab(tab.key)}
          className={`relative shrink-0 px-4 py-3 text-sm transition-colors ${
            activeTab === tab.key ? "text-white" : "text-[#6F7789] hover:text-[#D7DBE7]"
          }`}
        >
          {tab.label}
          {activeTab === tab.key && <span className="absolute inset-x-0 bottom-0 h-[2px] bg-[#E10600]" />}
        </button>
      ))}
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

/** What each driver ran, and every stop that punctuated it. */
function StintsSection({
  strategy,
  strategyLoading,
}: {
  strategy?: RaceStrategyResponse;
  strategyLoading: boolean;
}) {
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
  schedule: RaceEvent[];
  scheduleError: boolean;
  scheduleLoading: boolean;
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
  const [activeTab, setActiveTab] = useState<TabKey>("weekend");
  const driverLookup = useMemo(() => buildDriverLookup(props.drivers), [props.drivers]);

  return (
    <div className="space-y-4">
      <SeasonRoundStrip
        schedule={props.schedule}
        selectedRound={props.selectedRound}
        onSelectRound={props.onSelectRound}
      />

      <RaceHeader
        schedule={props.schedule}
        selectedRound={props.selectedRound}
        selectedRace={props.selectedRace}
        raceName={props.raceName}
        data={props.data}
        scheduleLoading={props.scheduleLoading}
        onSelectRound={props.onSelectRound}
      />

      <TabBar activeTab={activeTab} setActiveTab={setActiveTab} />

      <PredictionAlerts
        scheduleError={props.scheduleError}
        driversError={props.driversError}
        onReloadSchedule={props.onReloadSchedule}
        onReloadDrivers={props.onReloadDrivers}
      />

      {activeTab === "weekend" && <WeekendPanel selectedRace={props.selectedRace} />}

      {activeTab === "sessions" && (
        <WeekendSessions data={props.sessions} loading={props.sessionsLoading} raceName={props.raceName} />
      )}

      {activeTab === "grid" && (
        <GridSection grid={props.grid} gridLoading={props.gridLoading} raceName={props.raceName} />
      )}

      {activeTab === "stints" && (
        <StintsSection strategy={props.strategy} strategyLoading={props.strategyLoading} />
      )}

      {isPredictionTab(activeTab) && (
        <PredictionSection {...props} activeTab={activeTab} driverLookup={driverLookup} />
      )}
    </div>
  );
}
