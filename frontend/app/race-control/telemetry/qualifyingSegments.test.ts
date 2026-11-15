import { describe, expect, it } from "vitest";

import fixture from "@/test/fixtures/qualifying-laps-mexico-2026.json";

import { groupDrivers, groupLaps, noTimeReason, resolveSegment, segmentBest, titleSegment } from "./qualifyingSegments";
import { SEGMENT_NOTICE_LAPS } from "./telemetryTestData";
import { defaultDriver } from "./trackMapSelection";

import type { LapListResponse } from "./telemetryModel";

/**
 * Mexico City 2026 qualifying (session 11400): `build_lap_list` run on the captured
 * OpenF1 laps, race control and session result, with f1db's DSQ for Lawson.
 */
const MEXICO = fixture as unknown as LapListResponse;
const DRIVERS = MEXICO.drivers!;
const Q3 = { labels: ["Q1", "Q2", "Q3"], segment: 3 };
const codes = (group: string) =>
  groupDrivers(DRIVERS, Q3)
    .find((entry) => entry.key === group)
    ?.drivers.map((driver) => driver.code);

describe("qualifying segments on Mexico City 2026", () => {
  it("groups the drivers 9 / 1 disqualified / 6 / 6 under their headings", () => {
    const groups = groupDrivers(DRIVERS, Q3);
    expect(groups.map((group) => [group.heading, group.drivers.length])).toEqual([
      ["Q3", 9],
      ["Out in Q2", 6],
      ["Out in Q1", 6],
      ["Disqualified", 1],
    ]);
    expect(codes("disqualified")).toEqual(["LAW"]);
    expect(codes("out_q2")).toContain("HUL");
    expect(codes("out_q1")).toContain("ALB");
  });

  it("carries the on-road notes", () => {
    const note = (code: string) => DRIVERS.find((driver) => driver.code === code)?.note;
    expect(note("HUL")).toBe("P10 after Lawson's DSQ");
    expect(note("ALB")).toBe("P16 after Lawson's DSQ");
  });

  it("defaults to the last part the driver reached", () => {
    expect(resolveSegment(MEXICO, ["HAM"], null)?.segment).toBe(3);
    expect(resolveSegment(MEXICO, ["HUL"], null)?.segment).toBe(2);
    expect(resolveSegment(MEXICO, ["ALB"], null)?.segment).toBe(1);
    expect(resolveSegment(MEXICO, ["HAM", "HUL"], null)?.segment).toBe(2);
    expect(resolveSegment(MEXICO, [null], null)?.segment).toBe(3);
  });

  it("takes the URL's part, kept to the parts that exist", () => {
    expect(resolveSegment(MEXICO, ["HAM"], 1)).toEqual({ labels: ["Q1", "Q2", "Q3"], segment: 1 });
    expect(resolveSegment(MEXICO, ["HAM"], 3)?.segment).toBe(3);
  });

  it("explains a missing time", () => {
    const albon = DRIVERS.find((driver) => driver.code === "ALB")!;
    expect(noTimeReason(albon, Q3)).toBe("didn't reach Q3");
    expect(noTimeReason(albon, { ...Q3, segment: 1 })).toBe("no time set in Q1");
    expect(segmentBest(albon, 3)).toBeNull();
    expect(segmentBest(albon, 1)).not.toBeNull();
  });

  it("keeps Lawson's laps, and ranks within the part", () => {
    const lawson = DRIVERS.find((driver) => driver.code === "LAW")!;
    expect(lawson.laps.length).toBeGreaterThan(0);
    expect(segmentBest(lawson, 1)).toBe(78.097);
    expect(defaultDriver(DRIVERS, 3)).toBe("HAM");
    const quickestQ1 = Math.min(...DRIVERS.map((driver) => segmentBest(driver, 1) ?? Infinity));
    expect(
      segmentBest(
        DRIVERS.find((driver) => driver.code === defaultDriver(DRIVERS, 1))!,
        1,
      ),
    ).toBe(quickestQ1);
  });

  it("groups a driver's laps under Q1 / Q2 / Q3, outside laps last", () => {
    const ham = DRIVERS.find((driver) => driver.code === "HAM")!;
    const groups = groupLaps(ham.laps, Q3.labels);
    expect(groups.map((group) => group.heading)).toEqual(["Q1", "Q2", "Q3"]);
    expect(groupLaps(ham.laps, null)).toEqual([{ heading: null, laps: ham.laps }]);
    const stray = { number: 99, time: 80, deleted: false, is_fastest: false, segment: null };
    expect(groupLaps([stray], Q3.labels)).toEqual([{ heading: "Outside the parts", laps: [stray] }]);
  });

  it("names the part from the chosen lap, else the one on show", () => {
    const ham = DRIVERS.find((driver) => driver.code === "HAM")!;
    const q1Lap = ham.laps.find((lap) => lap.segment === 1)!;
    expect(titleSegment(DRIVERS, "HAM", null, Q3)).toBe("Q3");
    expect(titleSegment(DRIVERS, "HAM", q1Lap.number, Q3)).toBe("Q1");
    expect(titleSegment(DRIVERS, "HAM", null, null)).toBeNull();
  });
});

describe("a session whose parts are not published", () => {
  it("stays ungrouped and carries the notice", () => {
    expect(resolveSegment(SEGMENT_NOTICE_LAPS, [null], null)).toBeNull();
    expect(groupDrivers(SEGMENT_NOTICE_LAPS.drivers!, null)).toHaveLength(1);
    expect(SEGMENT_NOTICE_LAPS.segments?.notice).toBe("Q1/Q2/Q3 not published for this session");
  });

  it("puts a row without a group after the groups", () => {
    const loose = { ...DRIVERS[0], code: "XXX", group: undefined, segment_reached: undefined };
    const groups = groupDrivers([...DRIVERS, loose], Q3);
    expect(groups.at(-1)).toMatchObject({ key: "ungrouped", heading: null });
    expect(noTimeReason(loose, Q3)).toBe("no time set in Q3");
    expect(resolveSegment(MEXICO, ["XXX"], null)?.segment).toBe(3);
    expect(resolveSegment({ ...MEXICO, drivers: undefined }, ["HAM"], null)?.segment).toBe(3);
    expect(resolveSegment({ ...MEXICO, drivers: [loose] }, ["XXX"], null)?.segment).toBe(3);
  });
});
