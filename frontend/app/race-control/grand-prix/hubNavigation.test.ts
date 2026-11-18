import { describe, expect, it } from "vitest";

import { SEASON_2026 } from "@/test/fixtures";

import { HUB_TABS, defaultPredictionView, hubQuery, readHubParams } from "./hubNavigation";

import type { RaceEvent } from "./predictionModel";

const MEXICO = SEASON_2026.schedule.find((race) => race.round === 19)!;
/** The weekend before the race has finished. */
const during = (status: string): RaceEvent => ({ ...MEXICO, status });

describe("the hub's tabs", () => {
  it("run Weekend, Sessions, Grid, Results, Stints, Predictions", () => {
    expect(HUB_TABS.map((tab) => tab.label)).toEqual([
      "Weekend",
      "Sessions",
      "Grid",
      "Results",
      "Stints",
      "Predictions",
    ]);
  });
});

describe("defaultPredictionView", () => {
  it("opens on the review after the race and the order before it", () => {
    expect(defaultPredictionView(MEXICO)).toBe("review");
    expect(defaultPredictionView(during("upcoming"))).toBe("order");
    expect(defaultPredictionView(null)).toBe("order");
  });
});

describe("the URL", () => {
  it("reads a round, a tab and a view, and drops anything malformed", () => {
    expect(readHubParams(new URLSearchParams("round=19&tab=results&view=review"))).toEqual({
      round: 19,
      tab: "results",
      view: "review",
    });
    expect(readHubParams(new URLSearchParams("round=-3&tab=nope&view=x"))).toEqual({
      round: null,
      tab: null,
      view: null,
    });
    expect(readHubParams(new URLSearchParams(""))).toEqual({ round: null, tab: null, view: null });
  });

  it("writes only what is selected", () => {
    expect(hubQuery({ round: 19, tab: "results", view: null })).toBe("round=19&tab=results");
    expect(hubQuery({ round: null, tab: "predictions", view: "risk" })).toBe("tab=predictions&view=risk");
    expect(hubQuery({ round: null, tab: null, view: null })).toBe("");
  });
});
