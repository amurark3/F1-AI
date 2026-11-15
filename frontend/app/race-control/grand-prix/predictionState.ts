import type { PredictionPhase, PredictionsResponse, RaceEvent } from "./predictionModel";
import type { PhaseTabState } from "./PredictionPhaseTabs";
import type { KeyedMutator } from "swr";

export type ComputeReason = "manual_compute" | "qualifying_recompute";

/** What is in flight, so only the tab being recomputed shows a running state. */
export interface ComputeJob {
  phase: PredictionPhase;
  reason: ComputeReason;
}

export interface PhaseSnapshot {
  data?: PredictionsResponse;
  error?: Error;
  /** True only before this phase has anything to show, not on a background refresh. */
  awaiting: boolean;
  mutate: KeyedMutator<PredictionsResponse>;
}

/**
 * The reason recorded against a stored snapshot.
 *
 * The backend has always labelled a post-qualifying refresh as a qualifying
 * recompute, and that label shows up in the snapshot history, so the phase
 * being computed picks it rather than the button that was pressed.
 */
export function reasonFor(phase: PredictionPhase): ComputeReason {
  return phase === "post_qualifying" ? "qualifying_recompute" : "manual_compute";
}

/** Finishing-order rows in a payload, tolerating a backend error shape without them. */
export function predictionCount(data: PredictionsResponse | undefined): number {
  return data?.predictions?.length ?? 0;
}

/** Whether a phase holds a usable stored prediction. */
export function hasSnapshot(snapshot: PhaseSnapshot): boolean {
  return predictionCount(snapshot.data) > 0;
}

/** Derive the display-ready prediction slices from the snapshot payload. */
export function derivePredictionView(data: PredictionsResponse | undefined, selectedRace: RaceEvent | null) {
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

export function buildPhaseStates(
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
