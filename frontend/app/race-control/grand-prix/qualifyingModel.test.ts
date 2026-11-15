import { describe, expect, it } from "vitest";

import { WEEKEND_SESSIONS_2026 } from "@/test/fixtures";

import {
  fastestByPart,
  gapFraction,
  isDsq,
  lastTime,
  partLeaders,
  poleMargin,
  qualifyingGroups,
  qualifyingTitle,
  standInCount,
  stewardsCard,
  timeMs,
} from "./qualifyingModel";

import type { PracticeSession, QualifyingEntry, QualifyingSession } from "./sessionsModel";

const mexico = WEEKEND_SESSIONS_2026.mexicoCity.sessions;
const qualifying = mexico.find((s): s is QualifyingSession => s.kind === "qualifying")!.entries;
const fp1 = mexico.find((s): s is PracticeSession => s.id === "fp1")!;
const byCode = (code: string): QualifyingEntry => qualifying.find((e) => e.driver_code === code)!;

describe("qualifyingModel on Mexico City 2026", () => {
  it("reads lap and gap text in milliseconds", () => {
    expect(timeMs("1:16.514")).toBe(76514);
    expect(timeMs("+0.310")).toBe(310);
  });

  it("finds the fastest classified lap of each part, ignoring the disqualified car", () => {
    expect(fastestByPart(qualifying)).toEqual({ q1: 77341, q2: 76728, q3: 76514 });
    expect(isDsq(byCode("LAW"))).toBe(true);
  });

  it("groups the cars by the part they ran in, with Lawson under his own red cut", () => {
    const groups = qualifyingGroups(qualifying);

    expect(groups.map((g) => [g.cut, g.rows.length])).toEqual([
      [null, 9],
      ["Knocked out in Q2", 6],
      ["Knocked out in Q1", 6],
      ["Disqualified from qualifying", 1],
    ]);
    expect(groups.at(-1)?.disqualified).toBe(true);
    expect(groups[1]?.rows[0]).toMatchObject({ driver_code: "HUL", promoted_by: ["LAW"] });
    expect(groups[2]?.rows[0]).toMatchObject({ driver_code: "ALB", promoted_by: ["LAW"] });
  });

  it("labels a car with no time at all, and a first group that is not the last part", () => {
    const blank = { ...byCode("HAM"), part: null, q1: null, q2: null, q3: null };
    const q2 = { ...byCode("HUL") };

    expect(qualifyingGroups([blank])[0]?.cut).toBe("No time set");
    expect(qualifyingGroups([q2])[0]?.cut).toBe("Knocked out in Q2");
    expect(lastTime(blank)).toBeNull();
    expect(lastTime(byCode("ALB"))).toEqual({ part: "Q1", time: "1:18.630" });
  });

  it("scales each gap bar against the widest gap in its own part", () => {
    expect(gapFraction(byCode("BOT"), qualifying)).toBe(1);
    expect(gapFraction(byCode("HUL"), qualifying)).toBeCloseTo(0.578 / 2.511, 3);
    expect(gapFraction(byCode("HAM"), qualifying)).toBe(0);
    // Pole's own bar is a sliver, never invisible, when it has a gap to draw.
    expect(gapFraction({ ...byCode("RUS"), part_gap: "+0.000" }, qualifying)).toBe(0.004);
  });

  it("names the pole margin and who set the fastest lap of each part", () => {
    const margin = poleMargin(qualifying);

    expect(margin?.seconds).toBe("0.009");
    expect(qualifyingTitle(margin, "Qualifying")).toBe("Lewis Hamilton takes pole by 0.009 s");
    expect(partLeaders(qualifying).map((l) => [l.label, l.entry.driver_code])).toEqual([
      ["Q1", "HAM"],
      ["Q2", "NOR"],
      ["Q3", "HAM"],
    ]);
  });

  it("falls back to the session name when there is no margin to state", () => {
    expect(poleMargin([byCode("HAM")])).toBeNull();
    expect(qualifyingTitle(null, "Sprint Qualifying")).toBe("Sprint Qualifying classification");
    expect(partLeaders([])).toEqual([]);
  });

  it("counts only the disqualification as a decision that changed the order", () => {
    const card = stewardsCard(qualifying);
    expect(card.title).toBe("One decision changed this order");
    expect(card.body).toContain("Liam Lawson disqualified after the session");
    expect(stewardsCard(qualifying.filter((e) => !isDsq(e))).title).toBe("No decision changed this order");
    const two = [byCode("LAW"), { ...byCode("LAW"), driver_code: "XXX", driver_name: "X Driver" }];
    expect(stewardsCard(two).title).toBe("Two decisions changed this order");
    expect(stewardsCard(Array.from({ length: 6 }, () => byCode("LAW"))).title).toBe("6 decisions changed this order");
  });

  it("counts FP1's nine stand-ins", () => {
    expect(standInCount(fp1.entries)).toBe(9);
  });
});
