"use client";

import { useState } from "react";

import { qualifyingHasRun } from "./predictionHelpers";
import { buildPhaseStates, derivePredictionView, hasSnapshot } from "./predictionState";
import { usePhaseSnapshot } from "./useHubData";

import type { GrandPrixSeed } from "./hubSeed";
import type { PredictionPhase, RaceEvent } from "./predictionModel";

/**
 * The Predictions tab's state: both phases' stored snapshots and which one is
 * on screen. Read-only: the site owner stores predictions, visitors only read them.
 */
export function usePredictionWorkspace(seed: GrandPrixSeed, round: number | null, race: RaceEvent | null) {
  const { year } = seed;
  const [selectedPhase, setSelectedPhase] = useState<PredictionPhase | null>(null);

  // Only seed the round the server actually prefetched — selecting another
  // round must fall through to a real fetch, not reuse this payload.
  const seeded = round === seed.snapshotRound;
  const preQualifying = usePhaseSnapshot(year, round, "pre_qualifying", seeded ? seed.snapshots.pre_qualifying : null);
  const postQualifying = usePhaseSnapshot(
    year,
    round,
    "post_qualifying",
    seeded ? seed.snapshots.post_qualifying : null,
  );

  const qualifyingRun = qualifyingHasRun(race);
  // Land on the most informed prediction the race actually has, until the
  // reader picks a tab for themselves.
  const defaultPhase: PredictionPhase = hasSnapshot(postQualifying) ? "post_qualifying" : "pre_qualifying";
  const activePhase = selectedPhase ?? defaultPhase;
  const active = activePhase === "post_qualifying" ? postQualifying : preQualifying;
  const view = derivePredictionView(active.data, race);

  return {
    data: active.data,
    predictions: view.predictions,
    riskPredictions: view.riskPredictions,
    podium: view.podium,
    raceName: view.raceName,
    predictionLoading: active.awaiting,
    predictionError: Boolean(active.error || view.backendError),
    activePhase,
    phaseStates: buildPhaseStates(preQualifying, postQualifying, qualifyingRun),
    phaseAvailable: activePhase === "pre_qualifying" || qualifyingRun,
    onSelectPhase: setSelectedPhase,
    onRetry: () => void active.mutate(),
  };
}
