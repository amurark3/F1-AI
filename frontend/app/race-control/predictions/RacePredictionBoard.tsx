"use client";

import { AlertTriangle, LockKeyhole, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { LocalCountdown, LocalTime } from "@/app/components/LocalTime";
import type { DriverPrediction } from "@/app/components/PredictionDriverCard";

import { InlineNotice, SectionLoader, rcFont } from "../components/RaceControlPrimitives";

import { ConsolePanel } from "./predictionConsole";
import { buildDriverLookup, phaseDescription, phaseTabLabel, raceSessionTime } from "./predictionHelpers";
import { PredictionPhaseTabs, type PhaseTabState } from "./PredictionPhaseTabs";
import { ResultsReview } from "./PredictionResultsReview";
import { CircuitPanel, FullGridTable, ModelIO, PodiumPanel, RiskTable, StandbyPanel } from "./RacePredictionTabs";
import { SeasonAccuracyStrip } from "./SeasonAccuracyStrip";

import type {
  DriverLookup,
  DriverStanding,
  PredictionPhase,
  PredictionsResponse,
  RaceEvent,
  RiskPrediction,
  TabKey,
} from "./predictionModel";

const tabs: Array<{ key: TabKey; label: string; locked?: boolean }> = [
  { key: "predictions", label: "Predictions" },
  { key: "podium", label: "Podium" },
  { key: "circuit", label: "Circuit" },
  { key: "risk", label: "DNF / Crash" },
  { key: "model", label: "Model I/O" },
  { key: "results", label: "Results" },
];

interface RaceHeaderProps {
  schedule: RaceEvent[];
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  raceName: string;
  data?: PredictionsResponse;
  scheduleLoading: boolean;
  activePhase: PredictionPhase;
  /** False while the active phase cannot be computed yet. */
  phaseAvailable: boolean;
  isComputing: boolean;
  onSelectRound: (round: number) => void;
  onRun: () => void;
}

function RaceHeader({
  schedule,
  selectedRound,
  selectedRace,
  raceName,
  data,
  scheduleLoading,
  activePhase,
  phaseAvailable,
  isComputing,
  onSelectRound,
  onRun,
}: RaceHeaderProps) {
  const raceTime = raceSessionTime(selectedRace);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
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
          <span className="font-mono text-xs text-[#8E96A8]">{phaseDescription(activePhase)}</span>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={onRun}
            disabled={!selectedRound || isComputing || !phaseAvailable}
            title={phaseAvailable ? undefined : "Qualifying has not run yet."}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-[#00FF78]/35 bg-[#00FF78]/10 px-3 font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-[#00FF78] transition-colors hover:bg-[#00FF78] hover:text-black disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/[0.03] disabled:text-[#596173]"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {isComputing ? "running" : `run ${phaseTabLabel(activePhase).toLowerCase()}`}
          </button>
        </div>
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
    <div className="flex gap-1 overflow-x-auto border-b border-[#1E2633]">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => setActiveTab(tab.key)}
          className={`relative shrink-0 px-4 py-3 text-sm transition-colors ${
            activeTab === tab.key ? "text-white" : "text-[#6F7789] hover:text-[#D7DBE7]"
          }`}
        >
          <span className="inline-flex items-center gap-1.5">
            {tab.label}
            {tab.locked && <LockKeyhole className="h-3 w-3 text-[#C6A24B]" />}
          </span>
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

/** Shown on the after-qualifying tab before the session that feeds it has run. */
function AwaitingQualifyingPanel({ raceName }: { raceName: string }) {
  return (
    <ConsolePanel>
      <div className="flex items-start gap-4 p-6">
        <LockKeyhole className="mt-1 h-5 w-5 text-[#C6A24B]" />
        <div>
          <h2 className="text-xl font-black text-white" style={rcFont}>
            Qualifying Has Not Run
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#8E96A8]">
            This prediction is the one the model makes once the grid is set, so it cannot exist until
            qualifying for {raceName} has been run. The Overall tab holds the call the model can make
            today.
          </p>
        </div>
      </div>
    </ConsolePanel>
  );
}

interface PredictionLoadStateProps {
  predictionLoading: boolean;
  predictionError: boolean;
  hasPredictions: boolean;
  isComputing: boolean;
  activePhase: PredictionPhase;
  /** False while the active phase cannot be computed yet. */
  phaseAvailable: boolean;
  errorMessage?: string;
  raceName: string;
  onRetry: () => void;
  onRun: () => void;
}

function PredictionLoadState({
  predictionLoading,
  predictionError,
  hasPredictions,
  isComputing,
  activePhase,
  phaseAvailable,
  errorMessage,
  raceName,
  onRetry,
  onRun,
}: PredictionLoadStateProps) {
  const phaseName = phaseTabLabel(activePhase);

  if (!phaseAvailable) {
    return <AwaitingQualifyingPanel raceName={raceName} />;
  }

  return (
    <>
      {predictionLoading && (
        <SectionLoader
          title={`Loading the ${phaseName.toLowerCase()} snapshot`}
          detail="Checking whether this Grand Prix already has a saved prediction for this phase."
        />
      )}

      {!predictionLoading && predictionError && !hasPredictions && (
        <ConsolePanel>
          <div className="flex items-start gap-4 p-6">
            <AlertTriangle className="mt-1 h-5 w-5 text-[#E10600]" />
            <div>
              <h2 className="text-xl font-black text-white" style={rcFont}>
                No {phaseName} Snapshot
              </h2>
              <p className="mt-2 text-sm text-[#8E96A8]">
                {errorMessage ?? "The stored prediction could not be loaded."}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  onClick={onRetry}
                  className="rounded-md border border-[#1E2633] bg-white/[0.03] px-3 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-[#AEB5C5] hover:text-white"
                >
                  check again
                </button>
                <button
                  onClick={onRun}
                  disabled={isComputing}
                  className="rounded-md border border-[#00FF78]/35 bg-[#00FF78]/10 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-[#00FF78] hover:bg-[#00FF78] hover:text-black disabled:opacity-50"
                >
                  run {phaseName.toLowerCase()}
                </button>
              </div>
            </div>
          </div>
        </ConsolePanel>
      )}

      {isComputing && (
        <SectionLoader
          title={`Running the ${phaseName.toLowerCase()} model`}
          detail="Building a fresh stored snapshot with finish order, model I/O, accuracy, and incident risk. The other tab keeps its own prediction."
        />
      )}

      {!predictionLoading && !hasPredictions && !predictionError && (
        <StandbyPanel
          raceName={raceName}
          phaseName={phaseName}
          phaseDetail={phaseDescription(activePhase)}
          onRun={onRun}
          isComputing={isComputing}
        />
      )}
    </>
  );
}

interface PredictionTabContentProps {
  show: boolean;
  activeTab: TabKey;
  predictions: DriverPrediction[];
  riskPredictions: RiskPrediction[];
  podium: DriverPrediction[];
  driverLookup: DriverLookup;
  selectedRace: RaceEvent | null;
  data?: PredictionsResponse;
}

function PredictionTabContent({
  show,
  activeTab,
  predictions,
  riskPredictions,
  podium,
  driverLookup,
  selectedRace,
  data,
}: PredictionTabContentProps) {
  if (!show) return null;
  return (
    <>
      {activeTab === "predictions" && (
        <FullGridTable predictions={predictions} riskPredictions={riskPredictions} driverLookup={driverLookup} />
      )}
      {activeTab === "podium" && <PodiumPanel podium={podium} driverLookup={driverLookup} data={data} />}
      {activeTab === "circuit" && <CircuitPanel selectedRace={selectedRace} data={data} />}
      {activeTab === "risk" && <RiskTable rows={riskPredictions} />}
      {activeTab === "model" && <ModelIO data={data} />}
      {activeTab === "results" && (
        <ResultsReview
          review={data?.prediction_review}
          accuracy={data?.accuracy}
          predictions={predictions}
          driverLookup={driverLookup}
        />
      )}
    </>
  );
}

function PredictionWarnings({ warnings }: { warnings?: string[] }) {
  if (!warnings?.length) return null;
  return (
    <InlineNotice title="Prediction notes" tone="warning">
      {warnings.slice(0, 2).join(" ")}
    </InlineNotice>
  );
}

export interface RacePredictionBoardProps {
  schedule: RaceEvent[];
  scheduleError: boolean;
  scheduleLoading: boolean;
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  data?: PredictionsResponse;
  predictions: DriverPrediction[];
  riskPredictions: RiskPrediction[];
  podium: DriverPrediction[];
  drivers: DriverStanding[];
  driversError: boolean;
  raceName: string;
  predictionLoading: boolean;
  predictionError: boolean;
  /** Which of the race's two predictions every panel below is describing. */
  activePhase: PredictionPhase;
  phaseStates: PhaseTabState[];
  /** False while the active phase cannot be computed yet. */
  phaseAvailable: boolean;
  isComputing: boolean;
  computeReason: "manual_compute" | "qualifying_recompute" | null;
  onSelectRound: (round: number) => void;
  onSelectPhase: (phase: PredictionPhase) => void;
  onRun: () => void;
  onRetry: () => void;
  onReloadSchedule: () => void;
  onReloadDrivers: () => void;
}

export function RacePredictionBoard({
  schedule,
  scheduleError,
  scheduleLoading,
  selectedRound,
  selectedRace,
  data,
  predictions,
  riskPredictions,
  podium,
  drivers,
  driversError,
  raceName,
  predictionLoading,
  predictionError,
  activePhase,
  phaseStates,
  phaseAvailable,
  isComputing,
  onSelectRound,
  onSelectPhase,
  onRun,
  onRetry,
  onReloadSchedule,
  onReloadDrivers,
}: RacePredictionBoardProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("predictions");
  const driverLookup = useMemo(() => buildDriverLookup(drivers), [drivers]);

  return (
    <div className="space-y-4">
      <SeasonAccuracyStrip
        schedule={schedule}
        selectedRound={selectedRound}
        data={data}
        onSelectRound={onSelectRound}
      />

      <RaceHeader
        schedule={schedule}
        selectedRound={selectedRound}
        selectedRace={selectedRace}
        raceName={raceName}
        data={data}
        scheduleLoading={scheduleLoading}
        activePhase={activePhase}
        phaseAvailable={phaseAvailable}
        isComputing={isComputing}
        onSelectRound={onSelectRound}
        onRun={onRun}
      />

      <PredictionPhaseTabs states={phaseStates} activePhase={activePhase} onSelectPhase={onSelectPhase} />

      <TabBar activeTab={activeTab} setActiveTab={setActiveTab} />

      <PredictionAlerts
        scheduleError={scheduleError}
        driversError={driversError}
        onReloadSchedule={onReloadSchedule}
        onReloadDrivers={onReloadDrivers}
      />

      <PredictionLoadState
        predictionLoading={predictionLoading}
        predictionError={predictionError}
        hasPredictions={predictions.length > 0}
        isComputing={isComputing}
        activePhase={activePhase}
        phaseAvailable={phaseAvailable}
        errorMessage={data?.error}
        raceName={raceName}
        onRetry={onRetry}
        onRun={onRun}
      />

      <PredictionTabContent
        show={!predictionLoading && predictions.length > 0}
        activeTab={activeTab}
        predictions={predictions}
        riskPredictions={riskPredictions}
        podium={podium}
        driverLookup={driverLookup}
        selectedRace={selectedRace}
        data={data}
      />

      <PredictionWarnings warnings={data?.warnings} />
    </div>
  );
}
