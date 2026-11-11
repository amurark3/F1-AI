import { describe, expect, it } from "vitest";

import { STRATEGY_2026 } from "@/test/fixtures";

import { pitLaneFigure } from "./pitLaneFigure";

import type { StrategyContext } from "../components/CommandCenterPanels";

const SAO_PAULO = STRATEGY_2026.saoPaulo;

describe("pitLaneFigure", () => {
  it("reads São Paulo's median pit-lane time from the 2025 edition", () => {
    // 6 Nov: "21.9s" with "Undercut 1.4s · overcut 0.9s · modeled", from 2022 FastF1 laps.
    expect(pitLaneFigure(SAO_PAULO)).toEqual({
      seconds: 23.5,
      detail: "Median of 34 stops · 2025 São Paulo Grand Prix",
    });
  });

  it("says why there is no figure", () => {
    expect(pitLaneFigure(undefined)).toEqual({ seconds: null, detail: "Baseline plan unavailable" });
    expect(pitLaneFigure(STRATEGY_2026.madringNoEdition)).toEqual({
      seconds: null,
      detail: "No edition of this circuit measured",
    });
  });

  it("names the edition when it published no pit-lane time", () => {
    const unpublished: StrategyContext = { ...SAO_PAULO, pit_model: { pit_lane_seconds: null, pit_lane_stops: null } };

    expect(pitLaneFigure(unpublished)).toEqual({
      seconds: null,
      detail: "Not published for the 2025 São Paulo Grand Prix",
    });
  });

  it("falls back to plain words for an unnamed edition and a missing stop count", () => {
    const source = {
      ...SAO_PAULO.data_source,
      mode: "edition" as const,
      edition_year: 2025,
      sample_size: 17,
      event_name: null,
    };
    const sparse: StrategyContext = {
      ...SAO_PAULO,
      data_source: source,
      pit_model: { pit_lane_seconds: 23.5, pit_lane_stops: null },
    };

    expect(pitLaneFigure(sparse)).toEqual({ seconds: 23.5, detail: "Median of 0 stops · 2025 edition" });
    expect(pitLaneFigure({ ...sparse, pit_model: undefined })).toEqual({
      seconds: null,
      detail: "Not published for the 2025 edition",
    });
  });
});
