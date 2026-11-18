import type { PredictionsResponse, RaceEvent } from "./predictionModel";
import type { PhaseTabState } from "./PredictionPhaseTabs";
import type { KeyedMutator } from "swr";

export interface PhaseSnapshot {
  data?: PredictionsResponse;
  error?: Error;
  /** True only before this phase has anything to show, not on a background refresh. */
  awaiting: boolean;
  mutate: KeyedMutator<PredictionsResponse>;
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
): PhaseTabState[] {
  return [
    {
      phase: "pre_qualifying",
      available: true,
      hasSnapshot: hasSnapshot(preQualifying),
      // `stored_at` is this snapshot's own timestamp; `updated_at` covers the
      // whole race, so recomputing the other tab would move this one's clock.
      storedAt: preQualifying.data?.cache?.stored_at,
    },
    {
      phase: "post_qualifying",
      // The model has no grid to predict from until qualifying has run, and the
      // backend refuses to store a call under this heading before then.
      available: qualifyingRun,
      hasSnapshot: hasSnapshot(postQualifying),
      storedAt: postQualifying.data?.cache?.stored_at,
    },
  ];
}
