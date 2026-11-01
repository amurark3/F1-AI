"use client";

import { AlertTriangle, LockKeyhole } from "lucide-react";

import { InlineNotice, SectionLoader, rcFont } from "../components/RaceControlPrimitives";
import { TabPanel, Tabs } from "../components/Tabs";

import { ModelIO, PodiumPanel, RiskTable, StandbyPanel, FullGridTable } from "./GrandPrixPanels";
import { PREDICTION_VIEWS, type PredictionView } from "./hubNavigation";
import { ConsolePanel } from "./predictionConsole";
import { phaseDescription, phaseTabLabel } from "./predictionHelpers";
import { PredictionBar } from "./PredictionPhaseTabs";
import { ResultsReview } from "./PredictionResultsReview";

import type { GrandPrixBoardProps } from "./GrandPrixBoard";
import type {
  DriverLookup,
  DriverPrediction,
  PredictionPhase,
  PredictionsResponse,
  RiskPrediction,
} from "./predictionModel";

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
            This prediction is the one the model makes once the grid is set, so it cannot exist until qualifying for{" "}
            {raceName} has been run. Overall holds the call the model can make today.
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
}

/**
 * What stands in for a prediction that is not on screen yet. None of these
 * states carries its own run button: the bar above holds the only one.
 */
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
              <button
                type="button"
                onClick={onRetry}
                className="mt-4 rounded-md border border-[#1E2633] bg-white/[0.03] px-3 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-[#AEB5C5] hover:text-white"
              >
                check again
              </button>
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
        <StandbyPanel raceName={raceName} phaseName={phaseName} phaseDetail={phaseDescription(activePhase)} />
      )}
    </>
  );
}

interface PredictionViewContentProps {
  view: PredictionView;
  predictions: DriverPrediction[];
  riskPredictions: RiskPrediction[];
  podium: DriverPrediction[];
  driverLookup: DriverLookup;
  data?: PredictionsResponse;
}

function PredictionViewContent({
  view,
  predictions,
  riskPredictions,
  podium,
  driverLookup,
  data,
}: PredictionViewContentProps) {
  return (
    <>
      {view === "order" && (
        <FullGridTable predictions={predictions} riskPredictions={riskPredictions} driverLookup={driverLookup} />
      )}
      {view === "podium" && <PodiumPanel podium={podium} driverLookup={driverLookup} data={data} />}
      {view === "risk" && <RiskTable rows={riskPredictions} />}
      {view === "model" && <ModelIO data={data} />}
      {view === "review" && (
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

const VIEWS_ID = "prediction-views";

/** Everything that reads a stored prediction snapshot, in one section. */
export function PredictionSection(props: GrandPrixBoardProps & { driverLookup: DriverLookup }) {
  const hasPredictions = props.predictions.length > 0;
  return (
    <div className="space-y-4">
      <PredictionBar
        states={props.phaseStates}
        activePhase={props.activePhase}
        onSelectPhase={props.onSelectPhase}
        accuracy={props.data?.accuracy}
        canRun={props.selectedRound !== null && !props.isComputing && props.phaseAvailable}
        isComputing={props.isComputing}
        onRun={props.onRun}
      />

      {props.computeError && <ComputeErrorBanner message={props.computeError} />}

      <PredictionLoadState
        predictionLoading={props.predictionLoading}
        predictionError={props.predictionError}
        hasPredictions={hasPredictions}
        isComputing={props.isComputing}
        activePhase={props.activePhase}
        phaseAvailable={props.phaseAvailable}
        errorMessage={props.data?.error}
        raceName={props.raceName}
        onRetry={props.onRetry}
      />

      {!props.predictionLoading && hasPredictions && (
        <>
          <Tabs
            items={PREDICTION_VIEWS}
            active={props.predictionView}
            onChange={props.onSelectView}
            idPrefix={VIEWS_ID}
            label="Prediction views"
            variant="segmented"
          />
          <TabPanel idPrefix={VIEWS_ID} active={props.predictionView}>
            <PredictionViewContent
              view={props.predictionView}
              predictions={props.predictions}
              riskPredictions={props.riskPredictions}
              podium={props.podium}
              driverLookup={props.driverLookup}
              data={props.data}
            />
          </TabPanel>
        </>
      )}

      <PredictionWarnings warnings={props.data?.warnings} />
    </div>
  );
}
