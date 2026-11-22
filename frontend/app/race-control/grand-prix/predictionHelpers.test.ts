import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { rc } from "@/app/ui/tokens";
import { PREDICTION_REVIEW_R19, SEASON_2026 } from "@/test/fixtures";

import {
  buildDriverLookup,
  confidenceMidpoint,
  countdownTo,
  deltaColor,
  deltaLabel,
  driverDisplayName,
  estimatePodiumPct,
  formatPct,
  isLiveRace,
  modelStatusColor,
  phaseDescription,
  phaseTabLabel,
  qualifyingHasRun,
  raceSessionTime,
  resolveDefaultRace,
} from "./predictionHelpers";
import { PREDICTION_PHASES, type DriverPrediction, type RaceEvent } from "./predictionModel";

const [FIRST] = PREDICTION_REVIEW_R19.predictions;
const MEXICO = SEASON_2026.schedule.find((race) => race.round === 19)!;
const race = (changes: Partial<RaceEvent>): RaceEvent => ({ ...MEXICO, ...changes });

describe("names and bands", () => {
  it("takes a driver's name from the standings, then the snapshot, then the code", () => {
    const lookup = buildDriverLookup([
      { code: "ver", name: "Max Verstappen", team: "Red Bull", position: 1, points: 1, wins: 1 },
    ]);
    expect(driverDisplayName({ ...FIRST, driver_code: "VER" }, lookup)).toBe("Max Verstappen");
    expect(driverDisplayName(FIRST, {})).toBe(FIRST.driver_name);
    expect(driverDisplayName({ ...FIRST, driver_name: FIRST.driver_code }, {})).toBe(FIRST.driver_code);
    expect(driverDisplayName({ ...FIRST, driver_name: "" }, {})).toBe(FIRST.driver_code);
  });

  it("takes the midpoint of an agreement band and estimates a podium chance from it", () => {
    const band: DriverPrediction = { ...FIRST, position: 1, confidence_low: 60, confidence_high: 75 };
    expect(confidenceMidpoint(band)).toBe(68);
    expect(estimatePodiumPct(band)).toBeCloseTo(68 * 0.72 + 12);
    expect(estimatePodiumPct({ ...band, position: 8 })).toBeCloseTo(68 * 0.4 * Math.pow(0.72, 5));
    expect(estimatePodiumPct({ ...band, position: 0, confidence_low: 200, confidence_high: 200 })).toBe(99);
    expect(estimatePodiumPct({ ...band, position: 22, confidence_low: 0, confidence_high: 0 })).toBe(0.2);
    expect(formatPct(12.345)).toBe("12.3%");
  });
});

describe("phases", () => {
  it("names both phases and what each looks at", () => {
    expect(PREDICTION_PHASES).toEqual(["pre_qualifying", "post_qualifying"]);
    expect(phaseTabLabel("post_qualifying")).toBe("After Qualifying");
    expect(phaseTabLabel("pre_qualifying")).toBe("Overall");
    expect(phaseDescription("post_qualifying")).toMatch(/grid is known/);
    expect(phaseDescription("pre_qualifying")).toMatch(/grid is ignored/);
  });

  it("knows qualifying has run once its session start has passed", () => {
    const sessions = { Qualifying: "2026-10-31T21:00:00Z", Race: "2026-11-01T20:00:00Z" };
    const weekend = race({ sessions });
    expect(qualifyingHasRun(weekend, Date.parse("2026-10-31T22:00:00Z"))).toBe(true);
    expect(qualifyingHasRun(weekend, Date.parse("2026-10-31T20:00:00Z"))).toBe(false);
    expect(qualifyingHasRun(null)).toBe(false);
    expect(qualifyingHasRun(undefined, 0)).toBe(false);
  });

  it("falls back to a day before the race when the calendar has no usable qualifying time", () => {
    const base = { sessions: { Qualifying: "soon", Race: "2026-11-01T20:00:00Z" } };
    expect(qualifyingHasRun(race(base), Date.parse("2026-11-01T00:00:00Z"))).toBe(true);
    expect(qualifyingHasRun(race(base), Date.parse("2026-10-30T00:00:00Z"))).toBe(false);
    expect(qualifyingHasRun(race({ sessions: undefined, date: "later" }), 0)).toBe(false);
    expect(qualifyingHasRun(race({ sessions: undefined, date: undefined }), 0)).toBe(false);
  });

  it("reads the race start from the sessions, the Grand Prix key or the date", () => {
    expect(raceSessionTime(race({ sessions: { Race: "R" }, date: "D" }))).toBe("R");
    expect(raceSessionTime(race({ sessions: { "Grand Prix": "G" }, date: "D" }))).toBe("G");
    expect(raceSessionTime(race({ sessions: {}, date: "D" }))).toBe("D");
    expect(raceSessionTime(race({ sessions: undefined, date: "D" }))).toBe("D");
    expect(raceSessionTime(null)).toBeUndefined();
  });
});

describe("countdownTo", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-01T00:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("counts days, hours and minutes to a future time", () => {
    expect(countdownTo("2026-11-03T05:07:00Z")).toBe("02D 05H 07M");
  });

  it("has nothing to count for a missing, unreadable or past time", () => {
    expect(countdownTo()).toBeNull();
    expect(countdownTo("never")).toBeNull();
    expect(countdownTo("2026-10-01T00:00:00Z")).toBeNull();
  });
});

describe("colours and labels", () => {
  it("colours a model input by its status", () => {
    expect(modelStatusColor("available")).toBe(rc.ink2);
    expect(modelStatusColor("missing")).toBe(rc.redText);
    expect(modelStatusColor("limited")).toBe(rc.blue);
    expect(modelStatusColor("fallback")).toBe(rc.blue);
    expect(modelStatusColor("anything else")).toBe(rc.ink3);
  });

  it("colours and signs a places delta", () => {
    expect(deltaColor(null)).toBe("text-rc-ink-3");
    expect(deltaColor(2)).toBe("text-rc-gain");
    expect(deltaColor(-2)).toBe("text-rc-red-text");
    expect(deltaColor(0)).toBe("text-rc-ink-2");
    expect(deltaLabel(null)).toBe("-");
    expect(deltaLabel(2)).toBe("+2");
    expect(deltaLabel(-2)).toBe("-2");
    expect(deltaLabel(0)).toBe("0");
  });
});

describe("resolveDefaultRace", () => {
  const rows = (...statuses: string[]) => statuses.map((status, index) => race({ round: index + 1, status }));

  it("prefers a live race, then the next upcoming, then the last completed, then the first", () => {
    expect(isLiveRace("live")).toBe(true);
    expect(isLiveRace("in_progress")).toBe(true);
    expect(isLiveRace("completed")).toBe(false);
    expect(resolveDefaultRace(rows("completed", "in_progress", "upcoming"))?.round).toBe(2);
    expect(resolveDefaultRace(rows("completed", "upcoming", "upcoming"))?.round).toBe(2);
    expect(resolveDefaultRace(rows("completed", "completed", "cancelled"))?.round).toBe(2);
    expect(resolveDefaultRace(rows("cancelled", "cancelled"))?.round).toBe(1);
    expect(resolveDefaultRace([])).toBeNull();
  });
});
