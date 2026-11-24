import { describe, expect, it } from "vitest";

import { GRIDS_2026, RACE_RESULTS_2026, SEASON_2026, WEEKEND_SESSIONS_2026 } from "@/test/fixtures";

import { HUB_TABS, defaultPredictionView, gridSet, hubTabs, hubQuery, readHubParams } from "./hubNavigation";

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

describe("hubTabs", () => {
  const locked = (results: Parameters<typeof hubTabs>[0]) =>
    hubTabs(results)
      .filter((tab) => tab.locked)
      .map((tab) => tab.key);

  it("locks nothing while the results and grid are unknown", () => {
    expect(locked(undefined)).toEqual([]);
  });

  it("locks Grid until qualifying sets one", () => {
    expect(
      hubTabs(undefined, false)
        .filter((tab) => tab.locked)
        .map((tab) => tab.key),
    ).toEqual(["grid"]);
    expect(hubTabs(undefined, true).every((tab) => !tab.locked)).toBe(true);
  });

  it("locks Results and Stints before the round starts, and Stints alone after only a sprint", () => {
    expect(locked(null)).toEqual(["results", "stints"]);
    expect(locked({ ...RACE_RESULTS_2026.sprintWeekend, race: null })).toEqual(["stints"]);
    expect(hubTabs(null).find((tab) => tab.key === "stints")?.locked).toBe(
      "Unlocks once the race classification is published.",
    );
  });

  it("unlocks both once the race is classified", () => {
    expect(locked(RACE_RESULTS_2026.mexicoCity)).toEqual([]);
  });
});

describe("gridSet", () => {
  const grid = (available: boolean) => ({ ...GRIDS_2026.mexicoCityOfficial, available });
  const sessions = WEEKEND_SESSIONS_2026.mexicoCity;
  const sprint = WEEKEND_SESSIONS_2026.sprintWeekend;

  it("is unknown until both the grid and the sessions answer", () => {
    expect(gridSet(undefined, sessions)).toBeUndefined();
    expect(gridSet(grid(false), undefined)).toBeUndefined();
  });

  it("is set by the Grand Prix's grid or the sprint's, and unset before qualifying", () => {
    expect(gridSet(grid(true), undefined)).toBe(true);
    expect(gridSet(grid(false), sprint)).toBe(true);
    expect(gridSet(grid(false), sessions)).toBe(false);
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
    expect(readHubParams(new URLSearchParams("round=19&year=2025&tab=results&view=review"), 2026)).toEqual({
      year: 2025,
      round: 19,
      tab: "results",
      view: "review",
    });
    expect(readHubParams(new URLSearchParams("round=-3&tab=nope&view=x"), 2026)).toEqual({
      year: null,
      round: null,
      tab: null,
      view: null,
    });
    expect(readHubParams(new URLSearchParams(""), 2026)).toEqual({ year: null, round: null, tab: null, view: null });
  });

  it("writes only what is selected", () => {
    expect(hubQuery({ year: 2025, round: 19, tab: "results", view: null })).toBe("round=19&year=2025&tab=results");
    expect(hubQuery({ year: null, round: null, tab: "predictions", view: "risk" })).toBe("tab=predictions&view=risk");
    expect(hubQuery({ year: null, round: null, tab: null, view: null })).toBe("");
  });
});
