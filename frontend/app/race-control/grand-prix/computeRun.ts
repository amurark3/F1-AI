import { fetcher } from "@/app/utils/fetcher";

import type { PredictionsResponse } from "./predictionModel";

/**
 * Waiting out a model run the server is still finishing.
 *
 * On a slow host a compute outlasts the request that started it, and the
 * server answers `cache.status: "computing"` while the run carries on and
 * stores its snapshot. Posting again would only join that run, so the page
 * watches the stored snapshot instead: a new `snapshot_id` is the finished
 * run; `model_running: false` with no new snapshot is a run that ended without
 * storing one.
 */

const POLL_INTERVAL_MS = 5_000;
const POLL_LIMIT_MS = 10 * 60_000;

const ENDED_WITHOUT_SNAPSHOT = "The model run ended without storing a prediction. Try again.";
const STILL_RUNNING = "The model is still running on the server. Check back in a few minutes.";

/** True when the server handed back a run still in flight rather than its result. */
export function isStillComputing(result: PredictionsResponse): boolean {
  return result.cache?.status === "computing";
}

const pause = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

async function poll(snapshotUrl: string, previousId: string | null, deadline: number): Promise<PredictionsResponse> {
  if (Date.now() > deadline) throw new Error(STILL_RUNNING);
  await pause(POLL_INTERVAL_MS);

  const snapshot = await fetcher<PredictionsResponse>(snapshotUrl);
  const snapshotId = snapshot.cache?.snapshot_id ?? null;
  if (snapshotId !== null && snapshotId !== previousId) return snapshot;
  if (snapshot.model_running !== true) throw new Error(ENDED_WITHOUT_SNAPSHOT);
  return poll(snapshotUrl, previousId, deadline);
}

/**
 * Resolve with the snapshot a still-running compute stores.
 *
 * `previousId` is the snapshot on screen when the run was requested, so the
 * one already stored is never mistaken for the new result.
 */
export function awaitStoredSnapshot(snapshotUrl: string, previousId: string | null): Promise<PredictionsResponse> {
  return poll(snapshotUrl, previousId, Date.now() + POLL_LIMIT_MS);
}
