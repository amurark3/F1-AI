"use client";

import { AlertTriangle, Check, CircleDot, LockKeyhole, RefreshCw, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import type { DriverPrediction } from "@/app/components/PredictionDriverCard";

import { InlineNotice, SectionLoader, rcFont } from "../components/RaceControlPrimitives";

import { ConsoleHeader, ConsolePanel } from "./predictionConsole";
import {
  buildDriverLookup,
  countdownTo,
  formatDate,
  formatTime,
  isLiveRace,
  phaseLabel,
  raceSessionTime,
  roundColor,
  roundStateLabel,
} from "./predictionHelpers";
import { ResultsReview } from "./PredictionResultsReview";
import { CircuitPanel, FullGridTable, ModelIO, PodiumPanel, RiskTable, StandbyPanel } from "./RacePredictionTabs";

import type {
  DriverLookup,
  DriverStanding,
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

/** Round-selector glyph: check when scored, dot when live/selected, else the round number. */
function RoundGlyph({ completed, activeOrLive, round }: { completed: boolean; activeOrLive: boolean; round: number }) {
  if (completed) return <Check className="h-3.5 w-3.5" />;
  if (activeOrLive) return <CircleDot className="h-3.5 w-3.5 fill-current" />;
  return <>{round}</>;
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function SeasonAccuracyStrip({
  schedule,
  selectedRound,
  data,
  onSelectRound,
}: {
  schedule: RaceEvent[];
  selectedRound: number | null;
  data?: PredictionsResponse;
  onSelectRound: (round: number) => void;
}) {
  // Show the whole calendar, not a fixed slice — the "N races" count in the
  // header must match the number of dots. The row scrolls horizontally when the
  // season is longer than the panel (e.g. a full 22-race calendar).
  const completed = schedule.filter((race) => race.status === "completed").length;
  const total = schedule.length || 0;
  const scored = data?.accuracy?.races_evaluated ?? 0;
  const window = data?.accuracy?.rolling_window ?? 8;

  return (
    <ConsolePanel>
      <ConsoleHeader
        label={`${new Date().getFullYear()} season - prediction accuracy`}
        right={
          <span className="font-mono text-[11px] text-[#7F8797]">
            {total} races / {completed} complete / {scored} of latest {window} scored
          </span>
        }
      />
      <div className="overflow-x-auto px-4 py-4">
        <div className="flex w-max items-start gap-5">
          {schedule.map((race) => {
            const active = race.round === selectedRound;
            const completedRace = race.status === "completed";
            const liveRace = isLiveRace(race.status);
            const color = roundColor(completedRace, liveRace, active);
            const stateLabel = roundStateLabel(liveRace, completedRace, active);
            return (
              <button
                key={race.round}
                type="button"
                onClick={() => onSelectRound(race.round)}
                className="group flex w-16 shrink-0 flex-col items-center gap-2 text-center"
              >
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-full border text-[11px] transition-transform group-hover:scale-105 ${
                    active ? "ring-4 ring-[#E10600]/20" : ""
                  }`}
                  style={{ borderColor: `${color}88`, color, background: active ? `${color}22` : "transparent" }}
                >
                  <RoundGlyph completed={completedRace} activeOrLive={liveRace || active} round={race.round} />
                </span>
                <span className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-[#A8AFBF]">
                  {race.location.split(",")[0].slice(0, 3)}
                </span>
                <span className="font-mono text-[10px] text-[#596173]">{stateLabel}</span>
              </button>
            );
          })}
        </div>
        <div className="mt-4 flex flex-wrap gap-4 font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
          <LegendDot color="#00FF78" label="scored or complete" />
          <LegendDot color="#E10600" label="live or selected" />
          <LegendDot color="#333B49" label="future" />
        </div>
      </div>
    </ConsolePanel>
  );
}

function RaceHeader({
  schedule,
  selectedRound,
  selectedRace,
  raceName,
  data,
  scheduleLoading,
  isComputing,
  computeReason,
  onSelectRound,
  onRun,
  onQualifyingRecompute,
}: {
  schedule: RaceEvent[];
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  raceName: string;
  data?: PredictionsResponse;
  scheduleLoading: boolean;
  isComputing: boolean;
  computeReason: "manual_compute" | "qualifying_recompute" | null;
  onSelectRound: (round: number) => void;
  onRun: () => void;
  onQualifyingRecompute: () => void;
}) {
  const raceTime = raceSessionTime(selectedRace);
  const countdown = countdownTo(raceTime);

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
          <span className="font-mono text-xs text-[#8E96A8]">{phaseLabel(data?.prediction_phase)}</span>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={onRun}
            disabled={!selectedRound || isComputing}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-[#00FF78]/35 bg-[#00FF78]/10 px-3 font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-[#00FF78] transition-colors hover:bg-[#00FF78] hover:text-black disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/[0.03] disabled:text-[#596173]"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {computeReason === "manual_compute" ? "running" : "run model"}
          </button>
          <button
            onClick={onQualifyingRecompute}
            disabled={!selectedRound || isComputing}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-[#E10600]/35 bg-[#E10600]/10 px-3 font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-[#FF6B67] transition-colors hover:bg-[#E10600] hover:text-white disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/[0.03] disabled:text-[#596173]"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {computeReason === "qualifying_recompute" ? "recomputing" : "after quali"}
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
              Race {formatDate(raceTime)} - {formatTime(raceTime)}
            </span>
            <span>
              status <b className="text-white">{selectedRace?.status ?? "unknown"}</b>
            </span>
          </div>
        </div>
        {countdown && (
          <div className="w-fit rounded-full border border-[#E10600]/40 bg-[#E10600]/10 px-4 py-2 font-mono text-xs font-bold uppercase tracking-[0.18em] text-white shadow-[0_0_24px_rgba(225,6,0,0.12)]">
            lights out in <span className="text-[#FF4655]">{countdown}</span>
          </div>
        )}
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

interface PredictionLoadStateProps {
  predictionLoading: boolean;
  predictionError: boolean;
  hasPredictions: boolean;
  isComputing: boolean;
  computeReason: "manual_compute" | "qualifying_recompute" | null;
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
  computeReason,
  errorMessage,
  raceName,
  onRetry,
  onRun,
}: PredictionLoadStateProps) {
  return (
    <>
      {predictionLoading && (
        <SectionLoader
          title="Loading stored snapshot"
          detail="Checking whether this Grand Prix already has a saved prediction."
        />
      )}

      {!predictionLoading && predictionError && !hasPredictions && (
        <ConsolePanel>
          <div className="flex items-start gap-4 p-6">
            <AlertTriangle className="mt-1 h-5 w-5 text-[#E10600]" />
            <div>
              <h2 className="text-xl font-black text-white" style={rcFont}>
                No Prediction Snapshot
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
                  run model
                </button>
              </div>
            </div>
          </div>
        </ConsolePanel>
      )}

      {isComputing && (
        <SectionLoader
          title={computeReason === "qualifying_recompute" ? "Recomputing after qualifying" : "Running prediction model"}
          detail="Building a fresh stored snapshot with finish order, model I/O, accuracy, and incident risk."
        />
      )}

      {!predictionLoading && !hasPredictions && !predictionError && (
        <StandbyPanel raceName={raceName} onRun={onRun} isComputing={isComputing} />
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
  isComputing: boolean;
  computeReason: "manual_compute" | "qualifying_recompute" | null;
  onSelectRound: (round: number) => void;
  onRun: () => void;
  onQualifyingRecompute: () => void;
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
  isComputing,
  computeReason,
  onSelectRound,
  onRun,
  onQualifyingRecompute,
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
        isComputing={isComputing}
        computeReason={computeReason}
        onSelectRound={onSelectRound}
        onRun={onRun}
        onQualifyingRecompute={onQualifyingRecompute}
      />

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
        computeReason={computeReason}
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
