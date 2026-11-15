import { describe, expect, it } from "vitest";

import { MEXICO_CITY_2026 } from "@/test/fixtures";

import {
  finalStintLabel,
  redFlagLap,
  resultCode,
  retirementTag,
  stintEndingLabel,
  stopTimeLabel,
  type DriverStrategy,
} from "./strategyModel";

const rows = MEXICO_CITY_2026.strategy.drivers;
const lindblad = rows.find((row) => row.driver_code === "LIN")!;
const verstappen = rows.find((row) => row.driver_code === "VER")!;

describe("resultCode", () => {
  it("reads DNF for a retirement whatever place a source lists, a plain number for a finisher", () => {
    expect(resultCode(lindblad)).toBe("DNF");
    expect(resultCode({ finish_position: 18, status: "dnf" })).toBe("DNF");
    expect(resultCode(verstappen)).toBe("1");
    expect(resultCode({ finish_position: null, status: "dns" })).toBe("DNS");
    expect(resultCode({ finish_position: null, status: "dsq" })).toBe("DSQ");
    expect(resultCode({ finish_position: null, status: "not_classified" })).toBe("NC");
  });

  it("falls back to f1db's order before a classification, and a dash with nothing", () => {
    expect(resultCode({ finish_position: 4, status: null })).toBe("4");
    expect(resultCode({ finish_position: null, status: null })).toBe("-");
    expect(resultCode({ finish_position: null, status: "finished" })).toBe("-");
  });
});

describe("retirementTag", () => {
  it("tags a retirement with the lap it ended on, and only a retirement", () => {
    expect(retirementTag(lindblad)).toBe("DNF · L58");
    expect(retirementTag({ status: "dnf", laps_completed: null })).toBe("DNF");
    expect(retirementTag(verstappen)).toBeNull();
  });
});

describe("finalStintLabel", () => {
  const base: Pick<DriverStrategy, "laps_completed" | "retired_in_pits" | "reason"> = {
    laps_completed: 10,
    retired_in_pits: false,
    reason: null,
  };

  it("names the reason of a retirement, and the lap", () => {
    expect(finalStintLabel(lindblad)).toBe("Retired: Collision · lap 58");
    expect(finalStintLabel({ ...base, status: "dnf" })).toBe("Retired · lap 10");
    expect(finalStintLabel({ ...base, status: "dnf", retired_in_pits: true, laps_completed: null })).toBe(
      "Retired in the pits",
    );
  });

  it("words every other ending from the classification alone", () => {
    expect(finalStintLabel({ ...base, status: "finished" })).toBe("Took the flag");
    expect(finalStintLabel({ ...base, status: "dns" })).toBe("Did not start");
    expect(finalStintLabel({ ...base, status: "dsq" })).toBe("Disqualified");
    expect(finalStintLabel({ ...base, status: "not_classified" })).toBe("Not classified · 10 laps");
    expect(finalStintLabel({ ...base, status: "not_classified", laps_completed: null })).toBe("Not classified");
    expect(finalStintLabel({ ...base, status: null })).toBe("Result not published yet");
  });
});

describe("stintEndingLabel and stopTimeLabel", () => {
  const [first, second] = verstappen.stints;

  it("says how each stint ended: a stop, a red flag, an untimed stop or the flag", () => {
    expect(stintEndingLabel(first, verstappen, false)).toMatch(/^Stop 1 on lap \d+: /);
    expect(stintEndingLabel({ ...second, ended_under_red_flag: true }, verstappen, false)).toBe(
      "Tyres changed under the red flag",
    );
    expect(stintEndingLabel({ ...first, ended_by_stop: null }, verstappen, false)).toBe("Stop time not published yet");
    expect(stintEndingLabel(second, verstappen, true)).toBe("Took the flag");
  });

  it("gives the pit-lane time with its unit, and the stationary time when it is published", () => {
    expect(stopTimeLabel({ time: null, stationary_millis: null })).toBe("pit-lane time not published yet");
    expect(stopTimeLabel({ time: "22.5", stationary_millis: null })).toBe("22.5 s in the pit lane");
    expect(stopTimeLabel({ time: "1:14.7", stationary_millis: 2400 })).toBe("1:14.7 in the pit lane, 2.4 s stationary");
  });
});

describe("redFlagLap", () => {
  it("is the lap the red flag came out on, or null without one", () => {
    expect(redFlagLap(MEXICO_CITY_2026.strategy.neutralisations)).toBe(45);
    expect(redFlagLap([])).toBeNull();
    expect(redFlagLap(null)).toBeNull();
  });
});
