import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PREDICTION_REVIEW_R19 } from "@/test/fixtures";
import { apiUrl, server } from "@/test/msw/server";

import { awaitStoredSnapshot, isStillComputing } from "./computeRun";

const PATH = "/api/predictions/2026/19/snapshot";
const URL_ = apiUrl(PATH);
const snapshot = (id: string | null, running: boolean) => ({
  ...PREDICTION_REVIEW_R19,
  cache: { status: "hit", snapshot_id: id },
  model_running: running,
});

describe("computeRun", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("knows a run still in flight from a stored result", () => {
    expect(isStillComputing({ ...PREDICTION_REVIEW_R19, cache: { status: "computing" } })).toBe(true);
    expect(isStillComputing(PREDICTION_REVIEW_R19)).toBe(false);
    expect(isStillComputing({ ...PREDICTION_REVIEW_R19, cache: undefined })).toBe(false);
  });

  it("waits until a new snapshot id lands, polling while the model runs", async () => {
    const answers = [snapshot("old", true), snapshot("new", false)];
    server.use(http.get(URL_, () => HttpResponse.json(answers.shift())));

    const done = awaitStoredSnapshot(URL_, "old");
    await vi.advanceTimersByTimeAsync(5_000);
    await vi.advanceTimersByTimeAsync(5_000);

    expect((await done).cache?.snapshot_id).toBe("new");
  });

  it("gives up when the run ends without storing a snapshot", async () => {
    server.use(http.get(URL_, () => HttpResponse.json(snapshot(null, false))));

    const done = awaitStoredSnapshot(URL_, null);
    const failed = expect(done).rejects.toThrow("ended without storing");
    await vi.advanceTimersByTimeAsync(5_000);
    await failed;
  });

  it("stops waiting after ten minutes", async () => {
    server.use(http.get(URL_, () => HttpResponse.json(snapshot("old", true))));

    const done = awaitStoredSnapshot(URL_, "old");
    const failed = expect(done).rejects.toThrow("still running on the server");
    await vi.advanceTimersByTimeAsync(11 * 60_000);
    await failed;
  });
});
