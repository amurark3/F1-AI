import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import {
  driverKpis,
  formGuide,
  gridColumns,
  gridTitle,
  h2hRule,
  h2hTitle,
  headToHead,
  pointsColumns,
  pointsScale,
  pointsTitle,
  standingLine,
} from "./driverModel";

import type { DriverProfile, DriverRound, Finish } from "../../profiles/profilesModel";

const { verstappen, hamilton, lawson, hirakawa } = PROFILE_PAGES_2026;

function finish(over: Partial<Finish> = {}): Finish {
  return {
    number: 44,
    position: 8,
    position_text: "8",
    grid: 8,
    points: 4,
    positions_gained: 0,
    reason_retired: null,
    fastest_lap: false,
    pole: false,
    status: "finished",
    pit_lane: false,
    ...over,
  };
}

function round(over: Partial<DriverRound> = {}): DriverRound {
  return {
    round: 1,
    name: "Australian Grand Prix",
    short_name: "Australian GP",
    date: "2026-03-08",
    status: "complete",
    team_id: "ferrari",
    race: finish(),
    sprint: null,
    teammate: null,
    ...over,
  };
}

function profile(over: Partial<DriverProfile>): DriverProfile {
  return { ...hamilton, ...over };
}

describe("standingLine", () => {
  it("names the gap to the driver ahead", () => {
    expect(standingLine(verstappen)).toBe("P2 in the championship · 279 points · 111 behind Antonelli");
    expect(standingLine(hamilton)).toBe("P4 in the championship · 261 points · 1 behind Russell");
  });

  it("says level when the gap is nothing", () => {
    const level = profile({ rivals: { ahead: { ...hamilton.rivals.ahead!, points: 261 }, behind: null } });
    expect(standingLine(level)).toBe("P4 in the championship · 261 points · level with Russell on points");
  });

  it("says how far clear a leader is, with the races left", () => {
    const leader = profile({
      standing: { position: 1, points: 300 },
      rivals: { ahead: null, behind: { ...verstappen.rivals.ahead!, points: 290 } },
      rounds: [round({ status: "pending" }), round({ status: "pending" }), round()],
    });
    expect(standingLine(leader)).toBe("Leads the championship · 300 points · 10 clear of Antonelli with 2 races left");
    const one = profile({ ...leader, rounds: [round({ status: "pending" })] });
    expect(standingLine(one)).toBe("Leads the championship · 300 points · 10 clear of Antonelli with 1 race left");
    const done = profile({ ...leader, rounds: [round()] });
    expect(standingLine(done)).toBe("Leads the championship · 300 points · 10 clear of Antonelli");
  });

  it("covers a tied leader, a lone leader, a missing rival and an unranked driver", () => {
    const base = profile({ standing: { position: 1, points: 300 }, rounds: [round()] });
    const tied = profile({ ...base, rivals: { ahead: null, behind: { ...verstappen.rivals.ahead!, points: 300 } } });
    expect(standingLine(tied)).toBe("Leads the championship · 300 points · level with Antonelli on points");
    expect(standingLine(profile({ ...base, rivals: { ahead: null, behind: null } }))).toBe(
      "Leads the championship · 300 points",
    );
    const orphan = profile({ standing: { position: 3, points: 12.5 }, rivals: { ahead: null, behind: null } });
    expect(standingLine(orphan)).toBe("P3 in the championship · 12.5 points");
    expect(standingLine(profile({ standing: { position: null, points: 0 } }))).toBe("0 points");
  });
});

describe("driverKpis", () => {
  it("reads Verstappen: three wins, four retirements by round", () => {
    const kpis = driverKpis(verstappen);
    expect(kpis.podiums).toEqual({ value: 12, unit: "of 20", sub: "3 wins" });
    expect(kpis.wins).toEqual({ value: 3, sub: "R16, R17, R19" });
    expect(kpis.poles.sub).toBe("R16, R17");
    expect(kpis.fastestLaps.sub).toBe("4 retirements (R2, R6, R9, R12)");
  });

  it("reads Hamilton: one win, one pole and one retirement, each named", () => {
    const kpis = driverKpis(hamilton);
    expect(kpis.podiums).toEqual({ value: 7, unit: "of 20", sub: "Win: Barcelona-Catalunya GP (R7)" });
    expect(kpis.wins).toEqual({ value: 1, sub: "Round 7" });
    expect(kpis.poles).toEqual({ value: 1, sub: "Mexican GP (R19)" });
    expect(kpis.fastestLaps).toEqual({ value: 2, sub: "1 retirement (Spanish GP)" });
  });

  it("says so when there are no wins, poles or retirements", () => {
    const kpis = driverKpis(lawson);
    expect(kpis.podiums.sub).toBe("No wins");
    expect(kpis.wins.sub).toBe("—");
    expect(kpis.poles.sub).toBe("—");
    const clean = driverKpis(profile({ rounds: [round()], wins: [] }));
    expect(clean.fastestLaps.sub).toBe("No retirements");
  });
});

describe("formGuide", () => {
  it("lists the last five rounds with a race row, the number only for a finisher", () => {
    expect(formGuide(verstappen).map((chip) => [chip.axis, chip.text, chip.tone])).toEqual([
      ["R16", "1", "win"],
      ["R17", "1", "win"],
      ["R18", "3", "podium"],
      ["R19", "1", "win"],
      ["R20", "2", "podium"],
    ]);
    expect(formGuide(hamilton).map((chip) => chip.text)).toEqual(["3", "6", "4", "2", "9"]);
    expect(formGuide(hamilton)[2]?.tone).toBe("plain");
  });

  it("shows a retirement as its code, in words for assistive tech, and skips rounds with no race", () => {
    const chips = formGuide(
      profile({
        rounds: [
          round({ round: 1, race: null }),
          round({ round: 2, race: finish({ status: "dnf", position: 20, reason_retired: "Spun off", points: 0 }) }),
        ],
      }),
    );
    expect(chips).toHaveLength(1);
    expect(chips[0]).toMatchObject({ axis: "R2", text: "DNF", tone: "out" });
    expect(chips[0]?.sentence).toBe("R2 Australian GP: retired (Spun off), classified P20 · 0 pts");
  });

  it("holds one chip for a single race, and none for no rounds", () => {
    expect(formGuide(hirakawa)).toHaveLength(1);
    expect(formGuide(profile({ rounds: [] }))).toEqual([]);
  });
});

describe("gridToFinish", () => {
  it("never draws a loss for a retirement: VER R9 reads DNF and no -13 exists", () => {
    const items = gridColumns(verstappen);
    const r9 = items.find((item) => item.axis === "R9");
    expect(r9).toMatchObject({ value: null, marker: "DNF", markerTone: "alert" });
    expect(items.map((item) => item.valueText ?? "").join(" ")).not.toContain("−13");
    expect(items.map((item) => item.description).join(" ")).not.toContain("-13");
    expect(gridTitle(verstappen)).toBe("Verstappen gained 53 places over the season");
  });

  it("reads Hamilton and Hirakawa", () => {
    expect(gridTitle(hamilton)).toBe("Hamilton gained 13 places over the season");
    expect(gridColumns(hamilton).find((item) => item.axis === "R14")).toMatchObject({ marker: "DNF" });
    expect(gridTitle(hirakawa)).toBe("Hirakawa gained 8 places over the season");
  });

  it("keeps a pit-lane finisher's bar and says how it was counted", () => {
    expect(gridTitle(lawson)).toBe("Lawson gained 47 places over the season");
    const r13 = gridColumns(lawson).find((item) => item.axis === "R13");
    expect(r13?.value).toBe(8);
    expect(r13?.description).toContain("pit lane → P14 (+8, counted from the back of the grid)");
  });

  it("signs a bar, colours it by gain or loss, and marks a round not raced", () => {
    const items = gridColumns(
      profile({
        rounds: [
          round({ round: 1, race: finish({ positions_gained: 3 }) }),
          round({ round: 2, race: finish({ positions_gained: -2 }) }),
          round({ round: 3, race: finish({ positions_gained: 0 }) }),
          round({ round: 4, race: finish({ positions_gained: null }) }),
          round({ round: 5, race: null }),
          round({ round: 6, status: "pending", race: null }),
        ],
      }),
    );
    expect(items).toHaveLength(5);
    expect(items[0]).toMatchObject({ value: 3, valueText: "+3", color: "#00d66b" });
    expect(items[1]).toMatchObject({ value: -2, valueText: "−2", color: "#ff4655" });
    expect(items[2]).toMatchObject({ value: 0, valueText: "0" });
    expect(items[2]?.color).toBeUndefined();
    expect(items[3]).toMatchObject({ value: null, marker: "—", markerTone: "muted" });
    expect(items[4]).toMatchObject({ value: null, marker: "—", markerTone: "muted" });
  });

  it("titles a season by what it gained, lost, or cancelled", () => {
    const gained = (places: number) => profile({ rounds: [round({ race: finish({ positions_gained: places }) })] });
    expect(gridTitle(gained(1))).toBe("Hamilton gained 1 place over the season");
    expect(gridTitle(gained(-3))).toBe("Hamilton lost 3 places over the season");
    expect(gridTitle(gained(-1))).toBe("Hamilton lost 1 place over the season");
    expect(gridTitle(gained(0))).toBe("Hamilton: places gained and lost cancel out");
    // A finish with no gain on record counts as none.
    expect(gridTitle(profile({ rounds: [round({ race: finish({ positions_gained: null }) })] }))).toBe(
      "Hamilton: places gained and lost cancel out",
    );
  });
});

describe("headToHead", () => {
  it("reads Verstappen against Hadjar, with Lawson's rounds set aside", () => {
    const h2h = headToHead(verstappen)!;
    expect(h2h).toMatchObject({ compared: 17, ahead: 14, behind: 3, bothOut: 0, gridAhead: 12, gridBehind: 5 });
    expect(h2h.teammate.id).toBe("isack-hadjar");
    expect(h2h.notCounted).toEqual(["Not counted: R12–14 alongside Lawson."]);
    expect(h2hTitle(verstappen, h2h)).toBe("Verstappen finished ahead 14 times in 17");
  });

  it("reads Hamilton against Leclerc", () => {
    const h2h = headToHead(hamilton)!;
    expect(h2h).toMatchObject({ compared: 20, ahead: 10, behind: 10, gridAhead: 8, gridBehind: 12 });
    expect(h2hTitle(hamilton, h2h)).toBe("Hamilton finished ahead 10 times in 20");
  });

  it("reads Lawson, setting aside a round the teammate did not start", () => {
    const h2h = headToHead(lawson)!;
    expect(h2h).toMatchObject({ compared: 16, ahead: 12, behind: 4, gridAhead: 11, gridBehind: 5 });
    expect(h2h.notCounted).toEqual([
      "Not counted: R12–14 alongside Verstappen.",
      "Not counted: R5 (Lindblad did not start).",
    ]);
  });

  it("counts a teammate's retirement as finishing behind, with a time in the singular", () => {
    const h2h = headToHead(hirakawa)!;
    expect(h2h).toMatchObject({ compared: 1, ahead: 1, behind: 0, gridAhead: 0, gridBehind: 1 });
    expect(h2hTitle(hirakawa, h2h)).toBe("Hirakawa finished ahead 1 time in 1");
  });

  it("counts a round both cars retired in for neither, and a driver who did not start in a note", () => {
    const mate = (race: Finish) => ({ driver_id: "charles-leclerc", race });
    const out = finish({ status: "dnf", position: null, points: 0 });
    const h2h = headToHead(
      profile({
        teammates: [hamilton.teammates[0]],
        rounds: [
          round({ round: 1, race: out, teammate: mate(out) }),
          round({ round: 2, race: finish({ status: "dns", position: null }), teammate: mate(finish()) }),
          round({
            round: 3,
            race: finish({ position: 5, grid: null, pit_lane: true }),
            teammate: mate(finish({ position: 6, grid: null, pit_lane: true })),
          }),
          round({ round: 5, race: null }),
          round({ round: 6, race: finish() }),
        ],
      }),
    )!;
    expect(h2h).toMatchObject({ compared: 1, ahead: 1, behind: 0, bothOut: 1, gridAhead: 0, gridBehind: 0 });
    expect(h2h.notCounted).toEqual(["Not counted: R2 (Hamilton did not start)."]);
    expect(h2hRule(h2h)).toBe(
      "A retirement or disqualification counts as finishing behind; a pit-lane start counts as starting behind. Both out in 1 race: counted for neither.",
    );
  });

  it("states the rule, and the both-out count in the plural", () => {
    expect(h2hRule({ ...headToHead(hamilton)!, bothOut: 0 })).toBe(
      "A retirement or disqualification counts as finishing behind; a pit-lane start counts as starting behind.",
    );
    expect(h2hRule({ ...headToHead(hamilton)!, bothOut: 2 })).toContain("Both out in 2 races: counted for neither.");
  });

  it("is null with no teammate or no round together", () => {
    expect(headToHead(profile({ teammates: [] }))).toBeNull();
    expect(headToHead(profile({ rounds: [round()] }))).toBeNull();
  });
});

describe("pointsPerRace", () => {
  it("titles by the races that scored", () => {
    expect(pointsTitle(verstappen)).toBe("Scored in 16 of 20 races");
    expect(pointsTitle(hamilton)).toBe("Scored in 19 of 20 races");
    expect(pointsTitle(hirakawa)).toBe("Scored in 1 of 1 race");
    const none = profile({
      rounds: [round({ race: finish({ points: 0 }) }), round({ round: 2, race: finish({ points: 0 }) })],
    });
    expect(pointsTitle(none)).toBe("No points yet in 2 races");
  });

  it("makes the win gold and every other bar the colour of the team that round", () => {
    const r7 = pointsColumns(hamilton).find((item) => item.axis === "R7");
    expect(r7?.color).toBe("#ffc93c");
    const r8 = pointsColumns(hamilton).find((item) => item.axis === "R8");
    expect(r8?.color).toBe(hamilton.driver.color);
    const r12 = pointsColumns(lawson).find((item) => item.axis === "R12");
    expect(r12?.color).toBe("#3671C6");
    const r1 = pointsColumns(lawson).find((item) => item.axis === "R1");
    expect(r1?.color).toBe("#6692FF");
  });

  it("falls back to the driver's colour for a round with no team", () => {
    const items = pointsColumns(profile({ rounds: [round({ team_id: null })] }));
    expect(items[0]?.color).toBe(hamilton.driver.color);
  });

  it("shows a retirement with no points as its code and one that scored as a bar saying retired", () => {
    const items = pointsColumns(
      profile({
        rounds: [
          round({ round: 1, race: finish({ status: "dnf", position: null, points: 0, reason_retired: "Engine" }) }),
          round({ round: 2, race: finish({ status: "dnf", position: 8, points: 4, reason_retired: "Spun off" }) }),
          round({ round: 3, race: finish({ points: 0 }) }),
          round({ round: 4, race: null }),
        ],
      }),
    );
    expect(items[0]).toMatchObject({ value: null, marker: "DNF", markerTone: "alert" });
    expect(items[1]).toMatchObject({ value: 4, valueText: "4" });
    expect(items[1]?.description).toContain("retired (Spun off)");
    expect(items[2]).toMatchObject({ value: 0, valueText: "0" });
    expect(items[3]).toMatchObject({ value: null, marker: "—", markerTone: "muted" });
  });

  it("scales to a win at least", () => {
    expect(pointsScale(hamilton)).toBe(25);
    expect(pointsScale(profile({ rounds: [round({ race: finish({ points: 30 }) })] }))).toBe(30);
  });
});
