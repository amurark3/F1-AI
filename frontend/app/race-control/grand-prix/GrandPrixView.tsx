"use client";

import { useCallback, useMemo, useState } from "react";
import useSWR, { type KeyedMutator } from "swr";

import { API_BASE } from "@/app/constants/api";
import { awaitingFirstData, seededWith } from "@/app/lib/swrFallback";
import { fetcher } from "@/app/utils/fetcher";

import { PageLoader } from "../components/RaceControlPrimitives";

import { GrandPrixBoard, type GrandPrixBoardProps } from "./GrandPrixBoard";
import { qualifyingHasRun, resolveDefaultRace } from "./predictionHelpers";

import type { StartingGridResponse } from "./gridModel";
import type { DriverStanding, PredictionPhase, PredictionsResponse, RaceEvent } from "./predictionModel";
import type { PhaseTabState } from "./PredictionPhaseTabs";
import type { WeekendSessionsResponse } from "./sessionsModel";
import type { RaceStrategyResponse } from "./strategyModel";

export interface DriversResponse {
  drivers: DriverStanding[];
  error?: string | null;
}

/** One server-rendered snapshot per phase, to seed the client's SWR caches. */
export type PhaseSnapshots = Record<PredictionPhase, PredictionsResponse | null>;

/** Server-rendered payloads used to seed the workspace's SWR caches. */
export interface GrandPrixSeed {
  year: number;
  schedule: RaceEvent[] | { error: string } | null;
  drivers: DriversResponse | null;
  /** Both phases for the default round, each null if there was none to prefetch. */
  snapshots: PhaseSnapshots;
  /** The round `snapshots` belong to, so a different selection is not seeded. */
  snapshotRound: number | null;
  /** The starting grid for `snapshotRound`, or null when there was none. */
  grid: StartingGridResponse | null;
  /** Practice and sprint classifications for `snapshotRound`. */
  sessions: WeekendSessionsResponse | null;
  /** Tyre stints and pit stops for `snapshotRound`. */
  strategy: RaceStrategyResponse | null;
}

async function postPredictionCompute(url: string) {
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Prediction request failed with ${response.status}`);
  }
  return response.json() as Promise<PredictionsResponse>;
}

/** True when the schedule endpoint returned an `{ error }` payload rather than an array. */
function hasScheduleErrorPayload(response: RaceEvent[] | { error: string } | undefined): boolean {
  return !Array.isArray(response) && Boolean(response?.error);
}

type ComputeReason = "manual_compute" | "qualifying_recompute";

/** What is in flight, so only the tab being recomputed shows a running state. */
interface ComputeJob {
  phase: PredictionPhase;
  reason: ComputeReason;
}

/**
 * The reason recorded against a stored snapshot.
 *
 * The backend has always labelled a post-qualifying refresh as a qualifying
 * recompute, and that label shows up in the snapshot history, so the phase
 * being computed picks it rather than the button that was pressed.
 */
function reasonFor(phase: PredictionPhase): ComputeReason {
  return phase === "post_qualifying" ? "qualifying_recompute" : "manual_compute";
}

interface PhaseSnapshot {
  data?: PredictionsResponse;
  error?: Error;
  /** True only before this phase has anything to show, not on a background refresh. */
  awaiting: boolean;
  mutate: KeyedMutator<PredictionsResponse>;
}

/**
 * One phase's stored snapshot.
 *
 * The two phases are separate SWR keys on purpose: recomputing one must not
 * invalidate, blank or reorder the other, which is exactly what sharing a key
 * and swapping a query parameter would do.
 */
function usePhaseSnapshot(
  year: number,
  round: number | null,
  phase: PredictionPhase,
  seed: PredictionsResponse | null,
): PhaseSnapshot {
  const { data, error, isLoading, mutate } = useSWR<PredictionsResponse, Error>(
    round ? `${API_BASE}/api/predictions/${year}/${round}/snapshot?phase=${phase}` : null,
    fetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
      ...seededWith(seed),
    },
  );

  return { data, error, awaiting: awaitingFirstData(isLoading, data !== undefined), mutate };
}

/**
 * The published starting grid for the round in focus.
 *
 * A separate key from the prediction snapshots on purpose: the grid is a fact
 * about the weekend, not model output, and recomputing a prediction must not
 * invalidate or blank it.
 */
function useStartingGrid(year: number, round: number | null, seed: StartingGridResponse | null) {
  const { data, isLoading } = useSWR<StartingGridResponse, Error>(
    round ? `${API_BASE}/api/race-control/grid/${year}/${round}` : null,
    fetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 120000,
      ...seededWith(seed),
    },
  );

  return { grid: data, gridLoading: awaitingFirstData(isLoading, data !== undefined) };
}

/**
 * The weekend's sessions and its race strategy.
 *
 * Both describe what the weekend did, not what the model thinks, so they hold
 * their own SWR keys: recomputing a prediction must not blank either, and a
 * round with no snapshot still fills these tabs.
 */
function useWeekendData(
  year: number,
  round: number | null,
  seed: { sessions: WeekendSessionsResponse | null; strategy: RaceStrategyResponse | null },
) {
  const sessions = useSWR<WeekendSessionsResponse, Error>(
    round ? `${API_BASE}/api/race-control/sessions/${year}/${round}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 120000, ...seededWith(seed.sessions) },
  );
  const strategy = useSWR<RaceStrategyResponse, Error>(
    round ? `${API_BASE}/api/race-control/stints/${year}/${round}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 120000, ...seededWith(seed.strategy) },
  );

  return {
    sessions: sessions.data,
    sessionsLoading: awaitingFirstData(sessions.isLoading, sessions.data !== undefined),
    strategy: strategy.data,
    strategyLoading: awaitingFirstData(strategy.isLoading, strategy.data !== undefined),
  };
}

/** Resolve which round/race is in focus from the selection and schedule defaults. */
function resolveRound(schedule: RaceEvent[], selectedRound: number | null, defaultRace: RaceEvent | null) {
  const effectiveRound = selectedRound ?? defaultRace?.round ?? null;
  const selectedRace = schedule.find((r) => r.round === effectiveRound) ?? defaultRace;
  return { effectiveRound, selectedRace };
}

/** Derive the display-ready prediction slices from the snapshot payload. */
function derivePredictionView(data: PredictionsResponse | undefined, selectedRace: RaceEvent | null) {
  const predictions = data?.predictions ?? [];
  const backendError = data?.error && predictions.length === 0 ? data.error : null;
  return {
    predictions,
    riskPredictions: data?.risk_predictions ?? [],
    podium: predictions.slice(0, 3),
    raceName: data?.grand_prix ?? selectedRace?.name ?? "Select A Race",
    backendError,
  };
}

/** Whether a phase holds a usable stored prediction. */
function hasSnapshot(snapshot: PhaseSnapshot): boolean {
  return predictionCount(snapshot.data) > 0;
}

/** Finishing-order rows in a payload, tolerating a backend error shape without them. */
function predictionCount(data: PredictionsResponse | undefined): number {
  return data?.predictions?.length ?? 0;
}

function buildPhaseStates(
  preQualifying: PhaseSnapshot,
  postQualifying: PhaseSnapshot,
  qualifyingRun: boolean,
  job: ComputeJob | null,
): PhaseTabState[] {
  return [
    {
      phase: "pre_qualifying",
      available: true,
      hasSnapshot: hasSnapshot(preQualifying),
      // `stored_at` is this snapshot's own timestamp; `updated_at` covers the
      // whole race, so recomputing the other tab would move this one's clock.
      storedAt: preQualifying.data?.cache?.stored_at,
      computing: job?.phase === "pre_qualifying",
    },
    {
      phase: "post_qualifying",
      // The model has no grid to predict from until qualifying has run, and the
      // backend refuses to store a call under this heading before then.
      available: qualifyingRun,
      hasSnapshot: hasSnapshot(postQualifying),
      storedAt: postQualifying.data?.cache?.stored_at,
      computing: job?.phase === "post_qualifying",
    },
  ];
}

/**
 * The season-wide inputs every tab needs: the calendar and the entry list.
 *
 * Both are per-season rather than per-round, so they sit apart from the
 * round-scoped fetches — selecting a different race must not refetch either.
 */
function useSeasonContext(seed: GrandPrixSeed) {
  const { year } = seed;

  const {
    data: scheduleResponse,
    error: scheduleError,
    isLoading: scheduleLoading,
    mutate: reloadSchedule,
  } = useSWR<RaceEvent[] | { error: string }, Error>(`${API_BASE}/api/schedule/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 300000,
    ...seededWith(seed.schedule),
  });

  const {
    data: driversData,
    error: driversError,
    isLoading: driversLoading,
    mutate: reloadDrivers,
  } = useSWR<DriversResponse, Error>(`${API_BASE}/api/race-control/drivers/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 180000,
    ...seededWith(seed.drivers),
  });

  const schedule = useMemo(() => (Array.isArray(scheduleResponse) ? scheduleResponse : []), [scheduleResponse]);
  const drivers = driversData?.drivers ?? [];

  return {
    schedule,
    scheduleResponse,
    // Background revalidation must not re-open the loading chrome over content
    // the server already rendered.
    awaitingSchedule: awaitingFirstData(scheduleLoading, schedule.length > 0),
    scheduleFailed: Boolean(scheduleError) || hasScheduleErrorPayload(scheduleResponse),
    reloadSchedule,
    drivers,
    driversFailed: Boolean(driversError || driversData?.error),
    awaitingDrivers: awaitingFirstData(driversLoading, drivers.length > 0),
    reloadDrivers,
  };
}

function useGrandPrixWorkspace(seed: GrandPrixSeed) {
  const { year } = seed;
  const [selectedRound, setSelectedRound] = useState<number | null>(null);
  const [selectedPhase, setSelectedPhase] = useState<PredictionPhase | null>(null);
  const [computeError, setComputeError] = useState<string | null>(null);
  const [job, setJob] = useState<ComputeJob | null>(null);

  const season = useSeasonContext(seed);
  const { schedule } = season;
  const defaultRace = useMemo(() => resolveDefaultRace(schedule), [schedule]);

  const { effectiveRound, selectedRace } = resolveRound(schedule, selectedRound, defaultRace);

  // Only seed the round the server actually prefetched — selecting another
  // round must fall through to a real fetch, not reuse this payload.
  const seeded = effectiveRound === seed.snapshotRound;
  const preQualifying = usePhaseSnapshot(year, effectiveRound, "pre_qualifying", seeded ? seed.snapshots.pre_qualifying : null);
  const postQualifying = usePhaseSnapshot(year, effectiveRound, "post_qualifying", seeded ? seed.snapshots.post_qualifying : null);
  const { grid, gridLoading } = useStartingGrid(year, effectiveRound, seeded ? seed.grid : null);
  const weekend = useWeekendData(year, effectiveRound, {
    sessions: seeded ? seed.sessions : null,
    strategy: seeded ? seed.strategy : null,
  });

  const qualifyingRun = qualifyingHasRun(selectedRace);
  // Land on the most informed prediction the race actually has, until the
  // reader picks a tab for themselves.
  const defaultPhase: PredictionPhase = hasSnapshot(postQualifying) ? "post_qualifying" : "pre_qualifying";
  const activePhase = selectedPhase ?? defaultPhase;
  const active = activePhase === "post_qualifying" ? postQualifying : preQualifying;

  const view = derivePredictionView(active.data, selectedRace ?? null);
  const pageLoading = season.awaitingSchedule || season.awaitingDrivers;

  const computePrediction = useCallback(
    async (phase: PredictionPhase, mutate: KeyedMutator<PredictionsResponse>) => {
      if (!effectiveRound || job) return;
      const reason = reasonFor(phase);
      setComputeError(null);
      setJob({ phase, reason });
      try {
        const result = await postPredictionCompute(
          `${API_BASE}/api/predictions/${year}/${effectiveRound}/compute?reason=${reason}&phase=${phase}`,
        );
        // Only this phase's cache is written, so the other tab keeps the
        // prediction it was already showing.
        await mutate(result, { revalidate: false });
        if (result.error && predictionCount(result) === 0) setComputeError(result.error);
      } catch (error) {
        setComputeError(error instanceof Error ? error.message : "Prediction compute failed.");
      } finally {
        setJob(null);
      }
    },
    [effectiveRound, job, year],
  );

  const runActivePhase = useCallback(() => {
    void computePrediction(activePhase, active.mutate);
  }, [activePhase, active.mutate, computePrediction]);

  const boardProps: GrandPrixBoardProps = {
    schedule,
    scheduleError: season.scheduleFailed,
    scheduleLoading: season.awaitingSchedule,
    selectedRound: effectiveRound,
    selectedRace: selectedRace ?? null,
    data: active.data,
    grid,
    gridLoading,
    sessions: weekend.sessions,
    sessionsLoading: weekend.sessionsLoading,
    strategy: weekend.strategy,
    strategyLoading: weekend.strategyLoading,
    predictions: view.predictions,
    riskPredictions: view.riskPredictions,
    podium: view.podium,
    drivers: season.drivers,
    driversError: season.driversFailed,
    raceName: view.raceName,
    predictionLoading: active.awaiting,
    predictionError: Boolean(active.error || view.backendError),
    activePhase,
    phaseStates: buildPhaseStates(preQualifying, postQualifying, qualifyingRun, job),
    phaseAvailable: activePhase === "pre_qualifying" || qualifyingRun,
    isComputing: job !== null,
    computeReason: job?.reason ?? null,
    computeError,
    onSelectRound: (round) => {
      setSelectedRound(round);
      setComputeError(null);
    },
    onSelectPhase: (phase) => {
      setSelectedPhase(phase);
      setComputeError(null);
    },
    onRun: runActivePhase,
    onRetry: () => void active.mutate(),
    onReloadSchedule: () => void season.reloadSchedule(),
    onReloadDrivers: () => void season.reloadDrivers(),
  };

  return { pageLoading, boardProps };
}

export function GrandPrixView({ seed }: { seed: GrandPrixSeed }) {
  const { pageLoading, boardProps } = useGrandPrixWorkspace(seed);

  if (pageLoading) {
    return (
      <div>
        <PageLoader
          title="Preparing the Grand Prix hub"
          detail="Loading the race calendar and championship table."
        />
      </div>
    );
  }

  return <GrandPrixBoard {...boardProps} />;
}
