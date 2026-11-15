import { describe, expect, it } from "vitest";

import { lengthRows, lengthsTitle, paceTitle, scatterTitle, wearRows, wearTitle } from "./degradationInsights";
import {
  defaultDrivers,
  fitLines,
  formatRate,
  lapValue,
  paceDomain,
  paceRows,
  scatterGroups,
  yDomain,
} from "./degradationModel";
import { DEGRADATION } from "./telemetryTestData";

import type { FitLine } from "./degradationModel";
import type { DegradationLap, DegradationResponse } from "./telemetryModel";

const fit = (slope: number): FitLine => ({
  key: String(slope),
  compound: "SOFT",
  driver: "X",
  stint: 1,
  slope,
  points: [
    { x: 0, y: 0 },
    { x: 1, y: 1 },
  ],
});
const lapAt = (driver: string, stint: number, time: number | null, status = "clean"): DegradationLap => ({
  driver,
  lap: 1,
  time,
  corrected: time,
  tyre_age: 1,
  compound: "SOFT",
  stint,
  status,
  gap_ahead: null,
});
const BARE = { available: true, pending: false };
const ALL = new Set(["ANT", "RUS", "VER"]);

describe("scatterTitle", () => {
  it("states the median slope, or stays neutral without a trend", () => {
    expect(scatterTitle([])).toBe("Lap time against tyre age");
    expect(scatterTitle([fit(0.001)])).toBe("Lap times barely changed with tyre age");
    expect(scatterTitle([fit(0.06), fit(0.2), fit(0.05)])).toBe("Lap times rose about 0.06 s per lap of tyre age");
    expect(scatterTitle([fit(-0.1), fit(-0.3)])).toBe("Lap times fell about 0.20 s per lap of tyre age");
  });
});

describe("paceTitle", () => {
  const four = (driver: string, time: number) => [1, 2, 3, 4].map(() => lapAt(driver, 2, time));
  it("names the quickest final stint, comparing only those with enough clean laps", () => {
    const laps = [
      ...four("A", 90),
      ...four("B", 91),
      ...four("C", 80).slice(0, 2),
      lapAt("A", 1, 10),
      lapAt("D", 1, null),
    ];
    expect(paceTitle(laps, ["A", "B", "C"], false)).toBe("A had the quickest final stint");
  });

  it("stays neutral for one comparable driver, a tie or a lap with no time", () => {
    expect(paceTitle(four("A", 90), ["A", "B"], false)).toBe("Race pace");
    expect(paceTitle([...four("A", 90), ...four("B", 90)], ["A", "B"], false)).toBe("Race pace");
    expect(paceTitle([...four("A", 90), ...[1, 2, 3, 4].map(() => lapAt("B", 1, null))], ["A", "B"], true)).toBe(
      "Race pace",
    );
    expect(paceTitle([{ ...lapAt("A", 1, 90), stint: null }], ["A"], false)).toBe("Race pace");
  });
});

describe("wear and length rows", () => {
  it("ranks fitted stints of the chosen drivers, steepest first", () => {
    const rows = wearRows(DEGRADATION, ALL, true);
    expect(rows.map((row) => row.id)).toEqual(["ANT-1", "ANT-2", "RUS-2"]);
    expect(rows[0]).toMatchObject({ name: "Kimi Antonelli", laps: 6, rate: 0.13, raw: 0.1 });
    expect(wearRows(DEGRADATION, new Set(["RUS"]), false).map((row) => row.id)).toEqual(["RUS-1", "RUS-2"]);
    expect(wearRows({ ...DEGRADATION, drivers: undefined }, ALL, true)[0].name).toBe("ANT");
    expect(wearRows(BARE, ALL, true)).toEqual([]);
  });

  it("titles the steepest stint, or stays neutral without a real wear", () => {
    expect(wearTitle(wearRows(DEGRADATION, ALL, true))).toBe("ANT's medium stint wore fastest");
    expect(wearTitle([])).toBe("Wear rate by stint");
    expect(wearTitle(wearRows(DEGRADATION, new Set(["VER"]), true))).toBe("Wear rate by stint");
    const flat = {
      ...DEGRADATION,
      stints: [
        { ...DEGRADATION.stints![0], fit: { laps_fitted: 3, raw: { slope: 0, intercept: 0, r2: 1 }, corrected: null } },
      ],
    };
    expect(wearTitle(wearRows(flat, ALL, false))).toBe("Wear rate by stint");
  });

  it("lists each driver's stints in order and counts the stops", () => {
    const rows = lengthRows(DEGRADATION, ALL);
    expect(rows.map((row) => row.stints.length)).toEqual([2, 2, 1]);
    expect(lengthRows(DEGRADATION, new Set(["RUS"]))).toHaveLength(1);
    expect(lengthRows({ ...BARE, drivers: DEGRADATION.drivers }, ALL)).toEqual([]);
    expect(lengthRows(BARE, ALL)).toEqual([]);
    expect(lengthsTitle(rows)).toBe("VER did not stop; ANT and RUS stopped once");
  });

  it("words zero to many stops and lists of one, two and three", () => {
    const row = (code: string, stints: number) => ({
      code,
      name: code,
      stints: Array.from({ length: stints }, (_, index) => ({
        stint: index,
        compound: "SOFT",
        from: 1,
        to: 2,
        laps: 2,
      })),
    });
    expect(lengthsTitle([])).toBe("Stint lengths");
    expect(lengthsTitle([row("A", 3), row("B", 3), row("C", 3), row("D", 4)])).toBe(
      "A, B and C stopped twice; D stopped 3 times",
    );
  });
});

describe("degradationModel", () => {
  it("reads the plotted time for the chosen mode", () => {
    const lap = DEGRADATION.laps![1];
    expect([lapValue(lap, false), lapValue(lap, true)]).toEqual([90, 89.5]);
    expect(defaultDrivers(DEGRADATION)).toEqual(["ANT", "RUS", "VER"]);
    expect(defaultDrivers(BARE)).toEqual([]);
  });

  it("groups clean laps by compound and keeps the rest apart", () => {
    const groups = scatterGroups(DEGRADATION.laps!, ALL, false);
    expect([...groups.clean.keys()]).toEqual(["MEDIUM", "HARD", "UNKNOWN"]);
    expect(groups.excluded.map((entry) => entry.status)).toEqual(["pit_in", "sc", "sc"]);
    expect(yDomain(groups.clean)).toEqual([89.1, 92.5]);
    expect(yDomain(new Map())).toBeNull();
  });

  it("draws one line per fitted stint of the chosen drivers", () => {
    expect(fitLines(DEGRADATION.stints!, DEGRADATION.laps!, ALL, true).map((line) => line.key)).toEqual([
      "ANT-1",
      "ANT-2",
      "RUS-2",
    ]);
    expect(fitLines(DEGRADATION.stints!, DEGRADATION.laps!, new Set(["ANT"]), false)).toHaveLength(2);
    const noAge = { ...DEGRADATION.laps![1], tyre_age: null };
    expect(fitLines([DEGRADATION.stints![0]], [noAge], ALL, false)[0].points[0].x).toBe(0);
  });

  it("leaves gaps for laps that are not racing and sets a pace range", () => {
    const rows = paceRows(DEGRADATION.laps!, ["ANT", "RUS"], false);
    expect(rows.find((row) => row.lap === 6)?.ANT).toBeNull();
    expect(rows.find((row) => row.lap === 2)?.ANT).toBe(90);
    expect(paceDomain(rows, ["ANT", "RUS"])).toEqual([89.1, 91.7]);
    expect(paceDomain([], ["ANT"])).toBeNull();
    expect(formatRate(0.1234)).toBe("+0.123 s/lap");
    expect(formatRate(-0.01)).toBe("-0.010 s/lap");
    expect(formatRate(null)).toBe("-");
    expect(formatRate(undefined)).toBe("-");
  });
});

export type { DegradationResponse };
