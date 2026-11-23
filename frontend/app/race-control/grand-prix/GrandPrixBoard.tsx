"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { RacePicker } from "@/app/ui/race-picker/RacePicker";

import { SectionLoader, SkeletonPanel } from "../components/RaceControlPrimitives";
import { TabPanel, Tabs } from "../components/Tabs";

import { GridTab } from "./GridTab";
import { HubAlerts, RaceHeader } from "./HubHeader";
import { HUB_TABS, type HubTab, type PredictionView } from "./hubNavigation";
import { buildDriverLookup } from "./predictionHelpers";
import { PredictionSection } from "./PredictionSection";
import { ResultsTab } from "./ResultsTab";
import { SessionsTab } from "./SessionsTab";
import { StintChart } from "./StintChart";
import { WeekendPanel, WeekendTop } from "./WeekendPanels";

import type { StartingGridResponse } from "./gridModel";
import type {
  DriverLookup,
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

/** A way into the Telemetry Lab for the round on screen. */
function TelemetryLink({
  year,
  round,
  tab,
  label,
}: {
  year: number;
  round: number | null;
  tab: string;
  label: string;
}) {
  if (round === null) return null;
  return (
    <Link
      href={`/race-control/telemetry?tab=${tab}&round=${round}&year=${year}`}
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

/** The section the tab strip points at; `activeTab` picks which one renders. */
function HubSection(props: GrandPrixBoardProps & { driverLookup: DriverLookup }) {
  const { activeTab } = props;
  return (
    <>
      {activeTab === "weekend" && <WeekendPanel year={props.year} selectedRace={props.selectedRace} />}

      {activeTab === "sessions" && (
        <>
          <SessionsTab data={props.sessions} loading={props.sessionsLoading} />
          <TelemetryLink
            year={props.year}
            round={props.selectedRound}
            tab="map"
            label="Speed maps and lap-by-lap comparisons"
          />
        </>
      )}

      {activeTab === "grid" && (
        <GridTab
          grid={props.grid}
          loading={props.gridLoading}
          sessions={props.sessions}
          year={props.year}
          round={props.selectedRound}
          raceName={props.raceName}
        />
      )}

      {activeTab === "results" && props.selectedRound !== null && (
        <ResultsTab year={props.year} round={props.selectedRound} />
      )}

      {activeTab === "stints" && (
        <>
          <StintsSection strategy={props.strategy} strategyLoading={props.strategyLoading} />
          <TelemetryLink
            year={props.year}
            round={props.selectedRound}
            tab="tyres"
            label="Tyre degradation for this race"
          />
        </>
      )}

      {activeTab === "predictions" && <PredictionSection {...props} />}
    </>
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
  /** The calendar has not answered yet, so there is no round to show a section for. */
  schedulePending: boolean;
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
  onSelectRound: (round: number) => void;
  onSelectPhase: (phase: PredictionPhase) => void;
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
      <RacePicker
        year={props.year}
        races={props.schedule}
        selectedRound={props.selectedRound}
        onSelectRound={props.onSelectRound}
        view="grand-prix"
      />

      {props.selectedRace ? (
        <WeekendTop year={props.year} race={props.selectedRace} totalRounds={props.schedule.length} />
      ) : (
        <RaceHeader selectedRound={props.selectedRound} selectedRace={props.selectedRace} raceName={props.raceName} />
      )}

      <Tabs
        items={HUB_TABS}
        active={activeTab}
        onChange={props.onSelectTab}
        idPrefix={HUB_TABS_ID}
        label="Grand Prix sections"
      />

      <HubAlerts
        scheduleError={props.scheduleError}
        driversError={props.driversError}
        onReloadSchedule={props.onReloadSchedule}
        onReloadDrivers={props.onReloadDrivers}
      />

      <TabPanel idPrefix={HUB_TABS_ID} active={activeTab} className="space-y-4">
        {props.schedulePending ? (
          <SkeletonPanel className="h-64" />
        ) : (
          <HubSection {...props} driverLookup={driverLookup} />
        )}
      </TabPanel>
    </div>
  );
}
