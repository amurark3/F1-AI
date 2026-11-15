import { describe, expect, it } from "vitest";

import { SEASON_2026 } from "@/test/fixtures";

import { HUB_TABS, defaultHubTab, defaultPredictionView, hubQuery, readHubParams } from "./hubNavigation";

import type { RaceEvent } from "./predictionModel";

const MEXICO = SEASON_2026.schedule.find((race) => race.round === 19)!;
const SESSIONS = MEXICO.sessions!;
const at = (iso: string) => new Date(iso).getTime();
/** The weekend as the calendar would show it at a moment, before the race has finished. */
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

describe("defaultHubTab", () => {
  it("opens on Weekend before anything has run, and with no round at all", () => {
    expect(defaultHubTab(during("upcoming"), at("2026-10-20T00:00:00Z"))).toBe("weekend");
    expect(defaultHubTab(null)).toBe("weekend");
  });

  it("opens on Sessions once practice has started, and while the weekend is live", () => {
    expect(defaultHubTab(during("upcoming"), at(SESSIONS["Practice 1"]) + 60_000)).toBe("sessions");
    expect(defaultHubTab(during("in_progress"), at("2026-10-20T00:00:00Z"))).toBe("sessions");
    expect(defaultHubTab(during("live"), at("2026-10-20T00:00:00Z"))).toBe("sessions");
  });

  it("opens on Grid once qualifying has run and the race is not finished", () => {
    expect(defaultHubTab(during("in_progress"), at(SESSIONS.Qualifying) + 60_000)).toBe("grid");
  });

  it("opens on Results once the race is finished", () => {
    expect(defaultHubTab(MEXICO)).toBe("results");
  });

  it("treats a round with no session times as not started", () => {
    expect(defaultHubTab({ ...during("upcoming"), sessions: undefined }, at("2026-10-20T00:00:00Z"))).toBe("weekend");
  });

  it("ignores a session time it cannot read", () => {
    const garbled = { ...during("upcoming"), sessions: { "Practice 1": "soon" } };
    expect(defaultHubTab(garbled, at("2026-10-20T00:00:00Z"))).toBe("weekend");
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
