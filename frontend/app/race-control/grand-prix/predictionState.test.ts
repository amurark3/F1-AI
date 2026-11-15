import { describe, expect, it, vi } from "vitest";

import { PREDICTION_REVIEW_R19, SEASON_2026 } from "@/test/fixtures";

import {
  buildPhaseStates,
  derivePredictionView,
  hasSnapshot,
  predictionCount,
  reasonFor,
  type PhaseSnapshot,
} from "./predictionState";

const MEXICO = SEASON_2026.schedule.find((race) => race.round === 19)!;
const snap = (data: PhaseSnapshot["data"]): PhaseSnapshot => ({ data, awaiting: false, mutate: vi.fn() });

describe("predictionState", () => {
  it("labels a post-qualifying refresh as a qualifying recompute and any other as manual", () => {
    expect(reasonFor("post_qualifying")).toBe("qualifying_recompute");
    expect(reasonFor("pre_qualifying")).toBe("manual_compute");
  });

  it("counts the finishing-order rows, tolerating an error body without them", () => {
    expect(predictionCount(PREDICTION_REVIEW_R19)).toBe(22);
    expect(predictionCount(undefined)).toBe(0);
    expect(predictionCount({ error: "x" } as never)).toBe(0);
    expect(hasSnapshot(snap(PREDICTION_REVIEW_R19))).toBe(true);
    expect(hasSnapshot(snap(undefined))).toBe(false);
  });

  it("derives the order, risk rows, podium and race name from the payload", () => {
    const view = derivePredictionView(PREDICTION_REVIEW_R19, MEXICO);
    expect(view.predictions).toHaveLength(22);
    expect(view.riskPredictions.length).toBeGreaterThan(0);
    expect(view.podium).toHaveLength(3);
    expect(view.raceName).toBe(PREDICTION_REVIEW_R19.grand_prix);
    expect(view.backendError).toBeNull();
  });

  it("falls back to the race's name, then a prompt, and surfaces a backend error only when there is no order", () => {
    expect(derivePredictionView(undefined, MEXICO).raceName).toBe(MEXICO.name);
    expect(derivePredictionView(undefined, null).raceName).toBe("Select A Race");
    expect(derivePredictionView({ predictions: [], error: "No snapshot" } as never, null).backendError).toBe(
      "No snapshot",
    );
    expect(derivePredictionView({ ...PREDICTION_REVIEW_R19, error: "late" }, null).backendError).toBeNull();
    expect(derivePredictionView({ error: "x" } as never, null).predictions).toEqual([]);
  });

  it("builds both phase tabs, the post-qualifying one unavailable until qualifying has run", () => {
    const job = { phase: "post_qualifying" as const, reason: "qualifying_recompute" as const };
    const states = buildPhaseStates(snap(PREDICTION_REVIEW_R19), snap(undefined), false, job);
    expect(states).toEqual([
      expect.objectContaining({ phase: "pre_qualifying", available: true, hasSnapshot: true, computing: false }),
      expect.objectContaining({ phase: "post_qualifying", available: false, hasSnapshot: false, computing: true }),
    ]);
    expect(buildPhaseStates(snap(undefined), snap(undefined), true, null)[1].available).toBe(true);
  });
});
