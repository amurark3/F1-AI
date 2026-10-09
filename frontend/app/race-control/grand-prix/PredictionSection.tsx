"use client";

import { AlertTriangle, LockKeyhole, Sparkles } from "lucide-react";

import type { DriverPrediction } from "@/app/components/PredictionDriverCard";

import { InlineNotice, SectionLoader, rcFont } from "../components/RaceControlPrimitives";

import { ModelIO, ModelStatsPanel, PodiumPanel, RiskTable, StandbyPanel , FullGridTable } from "./GrandPrixPanels";
import { ConsolePanel } from "./predictionConsole";
import { phaseDescription, phaseTabLabel } from "./predictionHelpers";
import { PredictionPhaseTabs } from "./PredictionPhaseTabs";
import { ResultsReview } from "./PredictionResultsReview";

import type { GrandPrixBoardProps } from "./GrandPrixBoard";
import type { DriverLookup, PredictionPhase, PredictionsResponse, RiskPrediction, TabKey } from "./predictionModel";

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

/**
 * The bar that runs the model, with the accuracy record of the one that ran
 * last.
 *
 * Both used to sit at the top of the screen, which made every tab below read as
 * prediction output. They belong to the prediction section alone.
 */
function PredictionRunBar({
  activePhase,
  phaseAvailable,
  isComputing,
  hasRound,
  accuracy,
  onRun,
}: {
  activePhase: PredictionPhase;
  phaseAvailable: boolean;
  isComputing: boolean;
  hasRound: boolean;
  accuracy?: PredictionsResponse["accuracy"];
  onRun: () => void;
}) {
  const scored = accuracy?.races_evaluated ?? 0;
  const window = accuracy?.rolling_window ?? 8;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-[#1E2633] bg-[#0D111B] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="font-mono text-xs text-[#8E96A8]">{phaseDescription(activePhase)}</p>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-[#596173]">
          {scored} of the latest {window} predictions scored against results
        </p>
      </div>
      <button
        onClick={onRun}
        disabled={!hasRound || isComputing || !phaseAvailable}
        title={phaseAvailable ? undefined : "Qualifying has not run yet."}
        className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-[#00FF78]/35 bg-[#00FF78]/10 px-3 font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-[#00FF78] transition-colors hover:bg-[#00FF78] hover:text-black disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/[0.03] disabled:text-[#596173]"
      >
        <Sparkles className="h-3.5 w-3.5" />
        {isComputing ? "running" : `run ${phaseTabLabel(activePhase).toLowerCase()}`}
      </button>
    </div>
  );
}

interface PredictionTabContentProps {
  show: boolean;
  activeTab: TabKey;
  predictions: DriverPrediction[];
  riskPredictions: RiskPrediction[];
  podium: DriverPrediction[];
  driverLookup: DriverLookup;
  data?: PredictionsResponse;
}

function PredictionTabContent({
  show,
  activeTab,
  predictions,
  riskPredictions,
  podium,
  driverLookup,
  data,
}: PredictionTabContentProps) {
  if (!show) return null;
  return (
    <>
      {activeTab === "predictions" && (
        <FullGridTable predictions={predictions} riskPredictions={riskPredictions} driverLookup={driverLookup} />
      )}
      {activeTab === "podium" && <PodiumPanel podium={podium} driverLookup={driverLookup} data={data} />}
      {activeTab === "risk" && <RiskTable rows={riskPredictions} />}
      {activeTab === "model" && (
        <div className="space-y-4">
          <ModelIO data={data} />
          <ModelStatsPanel data={data} />
        </div>
      )}
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

function ComputeErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-[#E10600]/35 bg-[#E10600]/10 px-4 py-3 text-sm text-red-100">
      <AlertTriangle className="h-4 w-4 shrink-0 text-[#E10600]" />
      <span>{message}</span>
    </div>
  );
}

/** Everything that reads a stored prediction snapshot, in one section. */
export function PredictionSection(props: GrandPrixBoardProps & { activeTab: TabKey; driverLookup: DriverLookup }) {
  return (
    <div className="space-y-4">
      <PredictionPhaseTabs
        states={props.phaseStates}
        activePhase={props.activePhase}
        onSelectPhase={props.onSelectPhase}
      />

      <PredictionRunBar
        activePhase={props.activePhase}
        phaseAvailable={props.phaseAvailable}
        isComputing={props.isComputing}
        hasRound={props.selectedRound !== null}
        accuracy={props.data?.accuracy}
        onRun={props.onRun}
      />

      {props.computeError && <ComputeErrorBanner message={props.computeError} />}

      <PredictionLoadState
        predictionLoading={props.predictionLoading}
        predictionError={props.predictionError}
        hasPredictions={props.predictions.length > 0}
        isComputing={props.isComputing}
        activePhase={props.activePhase}
        phaseAvailable={props.phaseAvailable}
        errorMessage={props.data?.error}
        raceName={props.raceName}
        onRetry={props.onRetry}
        onRun={props.onRun}
      />

      <PredictionTabContent
        show={!props.predictionLoading && props.predictions.length > 0}
        activeTab={props.activeTab}
        predictions={props.predictions}
        riskPredictions={props.riskPredictions}
        podium={props.podium}
        driverLookup={props.driverLookup}
        data={props.data}
      />

      <PredictionWarnings warnings={props.data?.warnings} />
    </div>
  );
}
