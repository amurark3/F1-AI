"use client";

import { useCallback, useState } from "react";

import { API_BASE } from "@/app/constants/api";

import { awaitStoredSnapshot, isStillComputing } from "./computeRun";
import { qualifyingHasRun } from "./predictionHelpers";
import {
  buildPhaseStates,
  derivePredictionView,
  hasSnapshot,
  predictionCount,
  reasonFor,
  type ComputeJob,
} from "./predictionState";
import { usePhaseSnapshot } from "./useHubData";

import type { GrandPrixSeed } from "./hubSeed";
import type { PredictionPhase, PredictionsResponse, RaceEvent } from "./predictionModel";
import type { KeyedMutator } from "swr";

async function postPredictionCompute(url: string) {
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Prediction request failed with ${response.status}`);
  }
  return response.json() as Promise<PredictionsResponse>;
}

/**
 * The Predictions tab's state: both phases' stored snapshots, which one is on
 * screen, and the compute run that can replace one of them.
 */
export function usePredictionWorkspace(seed: GrandPrixSeed, round: number | null, race: RaceEvent | null) {
  const { year } = seed;
  const [selectedPhase, setSelectedPhase] = useState<PredictionPhase | null>(null);
  const [computeError, setComputeError] = useState<string | null>(null);
  const [job, setJob] = useState<ComputeJob | null>(null);

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

  const computePrediction = useCallback(
    async (phase: PredictionPhase, mutate: KeyedMutator<PredictionsResponse>, shownSnapshotId: string | null) => {
      if (!round || job) return;
      const reason = reasonFor(phase);
      setComputeError(null);
      setJob({ phase, reason });
      try {
        const posted = await postPredictionCompute(
          `${API_BASE}/api/predictions/${year}/${round}/compute?reason=${reason}&phase=${phase}`,
        );
        // A run that outlasted the request keeps going on the server; wait for
        // the snapshot it stores rather than blanking the one on screen.
        const result = isStillComputing(posted)
          ? await awaitStoredSnapshot(
              `${API_BASE}/api/predictions/${year}/${round}/snapshot?phase=${phase}`,
              shownSnapshotId,
            )
          : posted;
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
    [round, job, year],
  );

  const shownSnapshotId = active.data?.cache?.snapshot_id ?? null;
  const runActivePhase = useCallback(() => {
    void computePrediction(activePhase, active.mutate, shownSnapshotId);
  }, [activePhase, active.mutate, shownSnapshotId, computePrediction]);

  return {
    data: active.data,
    predictions: view.predictions,
    riskPredictions: view.riskPredictions,
    podium: view.podium,
    raceName: view.raceName,
    predictionLoading: active.awaiting,
    predictionError: Boolean(active.error || view.backendError),
    activePhase,
    phaseStates: buildPhaseStates(preQualifying, postQualifying, qualifyingRun, job),
    phaseAvailable: activePhase === "pre_qualifying" || qualifyingRun,
    isComputing: job !== null,
    computeReason: job?.reason ?? null,
    computeError,
    onSelectPhase: (phase: PredictionPhase) => {
      setSelectedPhase(phase);
      setComputeError(null);
    },
    onRun: runActivePhase,
    onRetry: () => void active.mutate(),
    clearComputeError: () => setComputeError(null),
  };
}
