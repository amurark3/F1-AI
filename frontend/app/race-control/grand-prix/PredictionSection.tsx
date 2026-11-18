"use client";

import { AlertTriangle, LockKeyhole } from "lucide-react";

import { InlineNotice, Panel, rcFont, SectionLoader } from "../components/RaceControlPrimitives";
import { TabPanel, Tabs } from "../components/Tabs";

import { PREDICTION_VIEWS, type PredictionView } from "./hubNavigation";
import { PodiumPanel } from "./OrderPanels";
import { OrderTable } from "./OrderTable";
import { phaseDescription, phaseTabLabel } from "./predictionHelpers";
import { PredictionBar } from "./PredictionPhaseTabs";
import { ResultsReview } from "./PredictionResultsReview";
import { ModelIO, RiskTable, StandbyPanel } from "./RiskModelPanels";

import type { GrandPrixBoardProps } from "./GrandPrixBoard";
import type { StartingGridResponse } from "./gridModel";
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
    <Panel as="section">
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
    </Panel>
  );
}

interface PredictionLoadStateProps {
  predictionLoading: boolean;
  predictionError: boolean;
  hasPredictions: boolean;
  activePhase: PredictionPhase;
  /** False while the active phase cannot be computed yet. */
  phaseAvailable: boolean;
  errorMessage?: string;
  raceName: string;
  onRetry: () => void;
}

/** What stands in for a prediction that is not on screen yet. Visitors cannot run the model. */
function PredictionLoadState({
  predictionLoading,
  predictionError,
  hasPredictions,
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
        <Panel as="section">
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
        </Panel>
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
  /** The round's starting grid, which the order's "vs grid" column reads. */
  grid?: StartingGridResponse;
  gridLoading: boolean;
  phase: PredictionPhase;
  year: number;
  round: number | null;
}

function PredictionViewContent({
  view,
  predictions,
  riskPredictions,
  podium,
  driverLookup,
  data,
  grid,
  gridLoading,
  phase,
  year,
  round,
}: PredictionViewContentProps) {
  return (
    <>
      {view === "order" && (
        <OrderTable
          predictions={predictions}
          driverLookup={driverLookup}
          phase={phase}
          grid={grid}
          gridLoading={gridLoading}
          data={data}
        />
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
          year={year}
          round={round}
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
      />

      <PredictionLoadState
        predictionLoading={props.predictionLoading}
        predictionError={props.predictionError}
        hasPredictions={hasPredictions}
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
              grid={props.grid}
              gridLoading={props.gridLoading}
              phase={props.activePhase}
              year={props.year}
              round={props.selectedRound}
            />
          </TabPanel>
        </>
      )}

      <PredictionWarnings warnings={props.data?.warnings} />
    </div>
  );
}
